from __future__ import annotations

import hashlib
import math
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .data import DataError, MarketData, fetch_market_data
from .lexicon import (
    BEARISH_TERMS,
    BULLISH_TERMS,
    SHOCK_TERMS,
    TIER_ONE_DOMAINS,
)
from .models import Bar, NewsAnalysis, NewsItem
from .news import fetch_news


CN_TZ = timezone(timedelta(hours=8))


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _signed_bar_weight(bar: Bar) -> float:
    span = max(bar.high - bar.low, 1e-9)
    return math.tanh((bar.close - bar.open) / (span * 0.35))


def _directional_window(bars: list[Bar]) -> tuple[float, float, float]:
    buy_volume = 0.0
    sell_volume = 0.0
    for bar in bars:
        weight = _signed_bar_weight(bar)
        buy_volume += bar.volume * max(weight, 0.0)
        sell_volume += bar.volume * max(-weight, 0.0)
    return buy_volume, sell_volume, sum(bar.volume for bar in bars)


def analyze_bars(
    bars: list[Bar],
    now: datetime,
    stale_after_minutes: int = 30,
) -> dict[str, Any]:
    usable = [bar for bar in bars if bar.close > 0 and bar.volume >= 0]
    if len(usable) < 20:
        raise ValueError("至少需要 20 根有效价格数据")
    latest = usable[-1]
    recent_count = 3
    recent = usable[-recent_count:]
    buy_volume, sell_volume, recent_volume = _directional_window(recent)
    directional_total = buy_volume + sell_volume
    signed_ratio = (
        (buy_volume - sell_volume) / directional_total
        if directional_total > 0
        else 0.0
    )
    baseline_start = max(0, len(usable) - 220)
    baseline_bars = usable[baseline_start:-recent_count]
    group_volumes = [
        sum(bar.volume for bar in baseline_bars[index : index + recent_count])
        for index in range(0, len(baseline_bars) - recent_count + 1, recent_count)
    ]
    positive_volumes = [volume for volume in group_volumes if volume > 0]
    baseline_volume = statistics.median(positive_volumes) if positive_volumes else recent_volume
    volume_ratio = recent_volume / baseline_volume if baseline_volume > 0 else 1.0
    volume_ratio = max(0.0, min(volume_ratio, 10.0))

    previous_15m = usable[-4].close if len(usable) >= 4 else usable[0].close
    previous_1h = usable[-13].close if len(usable) >= 13 else usable[0].close
    return_15m = latest.close / previous_15m - 1
    return_1h = latest.close / previous_1h - 1
    bar_returns = [
        math.log(usable[index].close / usable[index - 1].close)
        for index in range(max(1, len(usable) - 80), len(usable))
        if usable[index - 1].close > 0 and usable[index].close > 0
    ]
    bar_volatility = statistics.pstdev(bar_returns) if len(bar_returns) > 2 else 0.001
    normal_15m = max(bar_volatility * math.sqrt(3), 0.0007)
    normal_1h = max(bar_volatility * math.sqrt(12), 0.0012)
    move_15 = _clamp(return_15m / (normal_15m * 2.5))
    move_1h = _clamp(return_1h / (normal_1h * 2.5))
    momentum_score = _clamp(0.4 * move_15 + 0.6 * move_1h)
    flow_score = _clamp(signed_ratio * min(volume_ratio / 1.8, 1.0))
    market_score = _clamp(0.55 * flow_score + 0.45 * momentum_score)
    age_minutes = max(0.0, (now - latest.timestamp.astimezone(timezone.utc)).total_seconds() / 60)
    is_fresh = age_minutes <= stale_after_minutes
    large_buy = (
        volume_ratio >= 1.45
        and signed_ratio >= 0.22
        and return_15m >= 0.0003
    )
    large_sell = (
        volume_ratio >= 1.45
        and signed_ratio <= -0.22
        and return_15m <= -0.0003
    )
    price_shock = min(1.0, abs(return_15m) / 0.012)
    volume_shock = min(1.0, max(0.0, volume_ratio - 1.0) / 2.0)
    return {
        "price": latest.close,
        "bar_time": latest.timestamp,
        "age_minutes": age_minutes,
        "is_fresh": is_fresh,
        "market_status": "交易中" if is_fresh else "休市或数据延迟",
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "recent_volume": recent_volume,
        "volume_ratio": volume_ratio,
        "signed_volume_ratio": signed_ratio,
        "return_15m": return_15m,
        "return_1h": return_1h,
        "market_score": market_score,
        "momentum_score": momentum_score,
        "flow_score": flow_score,
        "large_buy": large_buy,
        "large_sell": large_sell,
        "price_shock": price_shock,
        "volume_shock": volume_shock,
        "chart_points": [
            {
                "time": bar.timestamp.astimezone(CN_TZ).isoformat(),
                "price": round(bar.close, 2),
            }
            for bar in usable[-96:]
        ],
    }


def _score_headline(text: str) -> tuple[float, list[str]]:
    lowered = text.lower()
    matched: list[str] = []
    bullish = 0.0
    bearish = 0.0

    def contains(phrase: str) -> bool:
        if phrase.isascii() and any(character.isalpha() for character in phrase):
            pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
            return re.search(pattern, lowered) is not None
        return phrase in lowered

    for phrase, weight in BULLISH_TERMS.items():
        if contains(phrase):
            bullish += weight
            matched.append(f"+{phrase}")
    for phrase, weight in BEARISH_TERMS.items():
        if contains(phrase):
            bearish += weight
            matched.append(f"-{phrase}")
    total = bullish + bearish
    if total == 0:
        return 0.0, matched
    return _clamp((bullish - bearish) / max(total, 1.5)), matched


def _importance(item: NewsItem, now: datetime) -> float:
    age_hours = 48.0
    if item.published_at:
        age_hours = max(
            0.0,
            (now - item.published_at.astimezone(timezone.utc)).total_seconds() / 3600,
        )
    recency = math.exp(-age_hours / 18)
    source = item.url.lower()
    tier = 1.0 if any(domain in source for domain in TIER_ONE_DOMAINS) else 0.5
    shock_hits = sum(1 for term in SHOCK_TERMS if term in item.title.lower())
    shock = min(1.0, shock_hits / 2)
    return _clamp(0.45 * recency + 0.3 * tier + 0.25 * shock, 0.0, 1.0)


def analyze_news(
    items: list[NewsItem],
    now: datetime,
    source_status: list[str] | None = None,
) -> tuple[NewsAnalysis, list[NewsItem]]:
    scored: list[NewsItem] = []
    for item in items:
        sentiment, terms = _score_headline(item.title)
        item.sentiment = round(sentiment, 4)
        item.matched_terms = terms
        item.importance = round(_importance(item, now), 4)
        scored.append(item)
    scored.sort(
        key=lambda item: (item.importance, abs(item.sentiment)),
        reverse=True,
    )
    selected = scored[:20]
    weight_sum = sum(max(0.05, item.importance) for item in selected)
    news_score = (
        sum(item.sentiment * max(0.05, item.importance) for item in selected) / weight_sum
        if weight_sum
        else 0.0
    )
    strong_items = [item for item in selected if abs(item.sentiment) >= 0.15]
    strong_weight = sum(max(0.05, item.importance) for item in strong_items)
    strong_signal = (
        sum(abs(item.sentiment) * item.importance for item in strong_items)
        / strong_weight
        if strong_weight
        else 0.0
    )
    coverage = min(1.0, len(strong_items) / 8)
    impact = _clamp(0.55 * strong_signal + 0.45 * coverage, 0.0, 1.0)
    if news_score >= 0.25:
        summary = "利好黄金的新闻占优"
    elif news_score <= -0.25:
        summary = "利空黄金的新闻占优"
    else:
        summary = "新闻方向分化或偏中性"
    return (
        NewsAnalysis(
            score=round(_clamp(news_score), 4),
            impact=round(_clamp(impact, 0.0, 1.0), 4),
            summary=summary,
            item_count=len(items),
            source_status=source_status or [],
        ),
        scored,
    )


def _macro_score(market: MarketData) -> tuple[float, list[str]]:
    scores: list[float] = []
    reasons: list[str] = []
    for point in market.macro_points:
        if point.key == "DX-Y.NYB":
            change_text = point.change_label.removesuffix("%")
            change = float(change_text or 0)
            value = _clamp(-change / 0.6)
            scores.append(value)
            reasons.append(point.bias)
        elif point.key == "^TNX":
            change_text = point.change_label.removesuffix(" bp")
            change_bp = float(change_text or 0)
            value = _clamp(-change_bp / 18)
            scores.append(value)
            reasons.append(point.bias)
    return (_clamp(sum(scores) / len(scores)) if scores else 0.0, reasons)


def _decision(
    action_score: float,
    market: dict[str, Any],
    news: NewsAnalysis,
) -> tuple[str, str, str]:
    if not market["is_fresh"]:
        return (
            "WATCH",
            "休市观察",
            "当前没有新鲜价格数据，继续监测新闻和宏观风险；恢复交易后再判断买卖方向。",
        )
    if market["large_sell"] and action_score <= -0.12:
        return (
            "SELL",
            "大量抛售，风险偏空",
            "成交量显著放大且卖盘方向占优，建议降低仓位、收紧止损并避免逆势抄底。",
        )
    if market["large_buy"] and action_score >= 0.12:
        return (
            "BUY",
            "大量买入，风险偏多",
            "成交量显著放大且买盘方向占优，可考虑小仓分批，但必须以价格重新站稳关键位为前提。",
        )
    if action_score >= 0.28:
        return (
            "BUY",
            "综合信号偏多",
            "价格、新闻与宏观信号整体偏多，可等待回踩确认后分批执行。",
        )
    if action_score <= -0.28:
        return (
            "SELL",
            "综合信号偏空",
            "价格、新闻与宏观信号整体偏空，优先控制仓位和回撤。",
        )
    if news.score <= -0.25 and news.impact >= 0.25:
        return (
            "WATCH",
            "利空新闻占优，等待价格确认",
            "新闻风险较高但成交量方向尚未形成一致信号，暂不追价。",
        )
    return (
        "HOLD",
        "观望",
        "当前信号不够一致，等待成交量、价格方向与新闻冲击形成共振。",
    )


def compose_snapshot(
    market: MarketData | None,
    raw_news: list[NewsItem],
    news_status: list[str],
    market_error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated = now or datetime.now(timezone.utc)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    news, scored_news = analyze_news(raw_news, generated, news_status)
    if market:
        market_metrics = analyze_bars(market.bars, generated)
        macro_score, macro_reasons = _macro_score(market)
        price = market.price
        price_change_pct = (
            (market.price / market.previous_close - 1) * 100
            if market.previous_close
            else 0.0
        )
        day_high = market.day_high
        day_low = market.day_low
        market_time = market.market_time
        source_status = market.source_status
        macro_points = [asdict(point) for point in market.macro_points]
    else:
        market_metrics = {
            "price": None,
            "bar_time": None,
            "age_minutes": None,
            "is_fresh": False,
            "market_status": "行情获取失败",
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "recent_volume": 0.0,
            "volume_ratio": 0.0,
            "signed_volume_ratio": 0.0,
            "return_15m": 0.0,
            "return_1h": 0.0,
            "market_score": 0.0,
            "momentum_score": 0.0,
            "flow_score": 0.0,
            "large_buy": False,
            "large_sell": False,
            "price_shock": 0.0,
            "volume_shock": 0.0,
            "chart_points": [],
        }
        macro_score = 0.0
        macro_reasons = []
        price = None
        price_change_pct = 0.0
        day_high = None
        day_low = None
        market_time = None
        source_status = [f"行情: 获取失败 - {market_error or 'unknown error'}"]
        macro_points = []

    if market and market_metrics["is_fresh"]:
        action_score = _clamp(
            0.55 * market_metrics["market_score"]
            + 0.28 * news.score
            + 0.17 * macro_score
        )
    else:
        action_score = _clamp(0.75 * news.score + 0.25 * macro_score)
    signal_type, decision, action_text = _decision(action_score, market_metrics, news)
    risk_score = round(
        100
        * _clamp(
            0.3 * market_metrics["price_shock"]
            + 0.2 * market_metrics["volume_shock"]
            + 0.4 * news.impact
            + 0.1 * abs(macro_score),
            0.0,
            1.0,
        ),
        1,
    )
    agreement = 1.0 - min(
        1.0,
        abs(market_metrics["market_score"] - news.score)
        + abs(market_metrics["market_score"] - macro_score),
    ) / 2
    confidence = round(
        100
        * _clamp(
            0.22 * float(market_metrics["is_fresh"])
            + 0.13 * min(len(raw_news) / 20, 1.0)
            + 0.2 * agreement
            + 0.15 * min(len(macro_points) / 2, 1.0)
            + 0.3 * min(abs(action_score), 1.0),
            0.0,
            1.0,
        ),
        1,
    )
    reasons: list[str] = []
    if market:
        reasons.append(
            f"15 分钟成交量为基准的 {market_metrics['volume_ratio']:.2f} 倍，"
            f"方向成交差 {market_metrics['signed_volume_ratio']:+.0%}"
        )
        reasons.append(
            f"15 分钟涨跌 {market_metrics['return_15m']:+.2%}，"
            f"1 小时涨跌 {market_metrics['return_1h']:+.2%}"
        )
    reasons.extend(macro_reasons)
    if news.item_count:
        reasons.append(
            f"黄金新闻 {news.item_count} 条，情绪分 {news.score:+.2f}，{news.summary}"
        )

    alerts: list[dict[str, Any]] = []
    if market_metrics["is_fresh"] and market_metrics["large_buy"]:
        alerts.append(
            {
                "type": "BUY",
                "severity": "高" if risk_score >= 60 else "中",
                "title": "检测到显著买盘",
                "message": (
                    f"15 分钟成交量异常放大至 {market_metrics['volume_ratio']:.2f} 倍，"
                    f"买盘方向占优，现价 {price:,.2f} 美元。"
                ),
            }
        )
    if market_metrics["is_fresh"] and market_metrics["large_sell"]:
        alerts.append(
            {
                "type": "SELL",
                "severity": "高" if risk_score >= 60 else "中",
                "title": "检测到大量抛售",
                "message": (
                    f"15 分钟成交量异常放大至 {market_metrics['volume_ratio']:.2f} 倍，"
                    f"卖盘方向占优，现价 {price:,.2f} 美元。"
                ),
            }
        )
    if abs(news.score) >= 0.28 and news.impact >= 0.3:
        direction = "利好" if news.score > 0 else "利空"
        alerts.append(
            {
                "type": "NEWS",
                "severity": "高" if news.impact >= 0.5 else "中",
                "title": f"重大{direction}黄金新闻",
                "message": (
                    f"新闻情绪分 {news.score:+.2f}、冲击度 {news.impact:.2f}，"
                    f"{news.summary}。"
                ),
            }
        )
    if risk_score >= 70:
        alerts.append(
            {
                "type": "RISK",
                "severity": "高",
                "title": "综合风险处于高位",
                "message": f"波动、成交异常与新闻冲击共同推高至 {risk_score:.1f}/100。",
            }
        )

    alert_signature_source = "|".join(
        f"{alert['type']}:{alert['title']}:{alert['severity']}"
        for alert in alerts
    )
    alert_signature = hashlib.sha256(
        alert_signature_source.encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema_version": 1,
        "generated_at": generated.astimezone(timezone.utc),
        "generated_at_china": generated.astimezone(CN_TZ),
        "market_time": market_time,
        "symbol": market.symbol if market else "GC=F",
        "price": price,
        "price_change_pct": price_change_pct,
        "day_high": day_high,
        "day_low": day_low,
        "market_status": market_metrics["market_status"],
        "data_age_minutes": market_metrics["age_minutes"],
        "buy_volume_proxy": market_metrics["buy_volume"],
        "sell_volume_proxy": market_metrics["sell_volume"],
        "volume_ratio": market_metrics["volume_ratio"],
        "signed_volume_ratio": market_metrics["signed_volume_ratio"],
        "return_15m": market_metrics["return_15m"],
        "return_1h": market_metrics["return_1h"],
        "market_score": market_metrics["market_score"],
        "momentum_score": market_metrics["momentum_score"],
        "flow_score": market_metrics["flow_score"],
        "news_score": news.score,
        "news_impact": news.impact,
        "news_summary": news.summary,
        "macro_score": macro_score,
        "composite_score": action_score,
        "risk_score": risk_score,
        "confidence": confidence,
        "signal_type": signal_type,
        "decision": decision,
        "action_text": action_text,
        "reasons": reasons,
        "alerts": alerts,
        "alert_signature": alert_signature,
        "macro_points": macro_points,
        "news": [
            {
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "published_at": item.published_at,
                "sentiment": item.sentiment,
                "importance": item.importance,
                "matched_terms": item.matched_terms,
            }
            for item in scored_news[:30]
        ],
        "chart_points": market_metrics["chart_points"],
        "source_status": source_status + news.source_status,
        "methodology": {
            "flow": "按 5 分钟 K 线方向和相对实体强度分配成交量，属于买卖压力代理",
            "news": "对 24 小时新闻标题做多来源去重、时效、来源级别和词袋情绪评分",
            "note": "未接入逐笔成交、盘口和完整新闻正文；该工具用于风险提醒，不构成投资建议",
        },
    }


def build_live_snapshot(symbol: str = "GC=F", news_limit: int = 60) -> dict[str, Any]:
    market: MarketData | None = None
    market_error: str | None = None
    raw_news: list[NewsItem] = []
    news_status: list[str] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        market_future = pool.submit(fetch_market_data, symbol)
        news_future = pool.submit(fetch_news, news_limit)
        try:
            market = market_future.result()
        except (DataError, ValueError, Exception) as exc:
            market_error = str(exc)
        try:
            raw_news, news_status = news_future.result()
        except (DataError, ValueError, Exception) as exc:
            news_status = [f"新闻: 获取失败 - {exc}"]
    return compose_snapshot(
        market=market,
        raw_news=raw_news,
        news_status=news_status,
        market_error=market_error,
    )


def demo_snapshot(direction: str = "sell") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    bars: list[Bar] = []
    start_price = 3600.0
    for index in range(80):
        price = start_price + index * 0.1
        bars.append(
            Bar(
                timestamp=now - timedelta(minutes=5 * (79 - index)),
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price + 0.2,
                volume=100,
            )
        )
    last_price = bars[-1].close
    for index in range(3):
        if direction == "buy":
            open_price = last_price + index * 4
            close_price = open_price + 4
        else:
            open_price = last_price - index * 4
            close_price = open_price - 4
        bars.append(
            Bar(
                timestamp=now - timedelta(minutes=5 * (3 - index)),
                open=open_price,
                high=max(open_price, close_price) + 1,
                low=min(open_price, close_price) - 1,
                close=close_price,
                volume=350,
            )
        )
    market = MarketData(
        symbol="GC=F",
        bars=bars,
        price=bars[-1].close,
        previous_close=bars[-4].close,
        day_high=max(bar.high for bar in bars[-40:]),
        day_low=min(bar.low for bar in bars[-40:]),
        market_time=now,
        currency="USD",
        source_status=["演示数据"],
    )
    news = [
        NewsItem(
            title=(
                "Gold rallies as rate cut hopes lift bullion demand"
                if direction == "buy"
                else "Gold plunges as Fed rate hike fears and forced liquidation hit bullion"
            ),
            url="https://example.com/demo-news",
            source="演示新闻",
            published_at=now - timedelta(minutes=10),
        )
    ]
    return compose_snapshot(market, news, ["演示新闻: 1 条"], now=now)

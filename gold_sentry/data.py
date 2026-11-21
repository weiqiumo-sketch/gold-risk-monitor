from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models import Bar, MarketPoint


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36 GoldSentry/1.0"
)
YAHOO_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")


@dataclass
class MarketData:
    symbol: str
    bars: list[Bar]
    price: float
    previous_close: float
    day_high: float
    day_low: float
    market_time: datetime
    currency: str
    source_status: list[str] = field(default_factory=list)
    macro_points: list[MarketPoint] = field(default_factory=list)


class DataError(RuntimeError):
    pass


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def fetch_bytes(url: str, accept: str = "*/*", attempts: int = 3) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.6",
            "Cache-Control": "no-cache",
        },
    )
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                request, timeout=25, context=_ssl_context()
            ) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.8 * (attempt + 1))
    raise DataError(f"request failed after {attempts} attempts: {last_error}")


def fetch_json(url: str, attempts: int = 3) -> dict[str, Any]:
    payload = fetch_bytes(url, "application/json", attempts)
    return json.loads(payload.decode("utf-8"))


def _yahoo_chart(symbol: str, interval: str, range_: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(symbol, safe="")
    path = (
        f"/v8/finance/chart/{encoded}"
        f"?interval={urllib.parse.quote(interval)}"
        f"&range={urllib.parse.quote(range_)}"
        "&includePrePost=true&events=div%2Csplits"
    )
    errors: list[str] = []
    for host in YAHOO_HOSTS:
        try:
            data = fetch_json(host + path)
            result = data.get("chart", {}).get("result")
            if not result:
                error = data.get("chart", {}).get("error", "empty result")
                raise DataError(str(error))
            return result[0]
        except Exception as exc:
            errors.append(f"{host}: {exc}")
    raise DataError("; ".join(errors))


def fetch_chart(symbol: str, interval: str, range_: str) -> tuple[list[Bar], dict[str, Any]]:
    result = _yahoo_chart(symbol, interval, range_)
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {}).get("quote") or [{}]
    quote = indicators[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    bars: list[Bar] = []
    for index, timestamp in enumerate(timestamps):
        try:
            values = (
                opens[index],
                highs[index],
                lows[index],
                closes[index],
                volumes[index] if index < len(volumes) else 0,
            )
        except IndexError:
            continue
        if any(value is None for value in values[:4]):
            continue
        volume = 0.0 if values[4] is None else max(0.0, float(values[4]))
        bars.append(
            Bar(
                timestamp=datetime.fromtimestamp(int(timestamp), tz=timezone.utc),
                open=float(values[0]),
                high=float(values[1]),
                low=float(values[2]),
                close=float(values[3]),
                volume=volume,
            )
        )
    if not bars:
        raise DataError(f"{symbol} returned no usable bars")
    return bars, result.get("meta", {})


def _market_point(symbol: str, label: str, is_yield: bool = False) -> MarketPoint:
    bars, meta = fetch_chart(symbol, "60m", "5d")
    latest = bars[-1].close
    previous = bars[-2].close if len(bars) > 1 else latest
    if is_yield:
        change = latest - previous
        change_label = f"{change * 100:+.1f} bp"
        if abs(change) < 0.02:
            bias = "中性"
        elif change > 0:
            bias = "收益率上升，压制黄金"
        else:
            bias = "收益率下降，支持黄金"
        value_round = round(latest, 3)
    else:
        change_pct = (latest / previous - 1) * 100 if previous else 0.0
        change_label = f"{change_pct:+.2f}%"
        if abs(change_pct) < 0.1:
            bias = "中性"
        elif change_pct > 0:
            bias = "美元走强，压制黄金"
        else:
            bias = "美元走弱，支持黄金"
        value_round = round(latest, 2)
    return MarketPoint(
        key=symbol,
        label=label,
        value=value_round,
        change_label=change_label,
        bias=bias,
    )


def fetch_market_data(symbol: str = "GC=F") -> MarketData:
    bars, meta = fetch_chart(symbol, "5m", "5d")
    statuses = [f"{symbol}: Yahoo Finance 5-minute chart"]
    price = bars[-1].close
    previous_close = float(meta.get("previousClose") or (bars[-2].close if len(bars) > 1 else price))
    day_high = float(meta.get("regularMarketDayHigh") or max(bar.high for bar in bars[-80:]))
    day_low = float(meta.get("regularMarketDayLow") or min(bar.low for bar in bars[-80:]))
    market_epoch = meta.get("regularMarketTime")
    market_time = (
        datetime.fromtimestamp(int(market_epoch), tz=timezone.utc)
        if market_epoch
        else bars[-1].timestamp
    )
    macro_points: list[MarketPoint] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_map = {
            pool.submit(_market_point, "DX-Y.NYB", "美元指数"): "DX-Y.NYB",
            pool.submit(_market_point, "^TNX", "美国10年期收益率", True): "^TNX",
        }
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                macro_points.append(future.result())
                statuses.append(f"{key}: Yahoo Finance hourly chart")
            except Exception as exc:
                statuses.append(f"{key}: 获取失败 - {exc}")
    order = {"DX-Y.NYB": 0, "^TNX": 1}
    macro_points.sort(key=lambda point: order.get(point.key, 99))
    return MarketData(
        symbol=symbol,
        bars=bars,
        price=price,
        previous_close=previous_close,
        day_high=day_high,
        day_low=day_low,
        market_time=market_time,
        currency=str(meta.get("currency") or "USD"),
        source_status=statuses,
        macro_points=macro_points,
    )

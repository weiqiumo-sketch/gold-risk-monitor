from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape

from .data import TROY_OUNCE_GRAMS, DataError, fetch_bytes


CN_TZ = timezone(timedelta(hours=8))


@dataclass
class DomesticGoldQuote:
    symbol: str
    name: str
    contract: str
    price_cny_per_gram: float
    previous_close: float
    open: float
    high: float
    low: float
    volume: float
    updated_at: datetime
    change_pct: float
    source: str


@dataclass
class InternationalGoldQuote:
    symbol: str
    name: str
    price_usd_per_oz: float
    high_usd_per_oz: float | None
    low_usd_per_oz: float | None
    updated_at: datetime
    source: str


def _parse_sge_timestamp(value: str) -> datetime:
    parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=CN_TZ)


def _fetch_sina_quote(symbol: str) -> tuple[list[str], str]:
    url = f"https://hq.sinajs.cn/list={urllib.parse.quote(symbol, safe='_')}"
    payload = fetch_bytes(
        url,
        "text/plain",
        headers={
            "Referer": "https://finance.sina.com.cn/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    text = payload.decode("gbk", errors="replace")
    match = re.search(rf'hq_str_{re.escape(symbol)}="([^"]*)"', text)
    if not match:
        raise DataError(f"{symbol} quote was not present in response")
    return [unescape(value.strip()) for value in match.group(1).split(",")], text


def _fetch_domestic_primary() -> DomesticGoldQuote:
    fields, _ = _fetch_sina_quote("SGE_AU9999")
    if len(fields) < 18:
        raise DataError(f"SGE quote had only {len(fields)} fields")
    try:
        change_text = fields[17].removesuffix("%")
    except (IndexError, AttributeError):
        change_text = ""
    return DomesticGoldQuote(
        symbol=fields[0],
        name=fields[1],
        contract=fields[2],
        price_cny_per_gram=float(fields[3]),
        previous_close=float(fields[5]),
        open=float(fields[6]),
        high=float(fields[7]),
        low=float(fields[8]),
        volume=float(fields[14]),
        updated_at=_parse_sge_timestamp(fields[16]),
        change_pct=float(change_text) if change_text else 0.0,
        source="Sina Finance · SGE Au99.99",
    )


def _fetch_domestic_last_session() -> DomesticGoldQuote:
    fields, _ = _fetch_sina_quote("gds_AU9999")
    if len(fields) < 14:
        raise DataError(f"SGE last-session quote had only {len(fields)} fields")
    price = float(fields[0])
    previous_close = float(fields[7])
    updated_at = datetime.fromisoformat(f"{fields[12]}T{fields[6]}+08:00")
    return DomesticGoldQuote(
        symbol="AU9999",
        name=fields[13],
        contract="Au99.99",
        price_cny_per_gram=price,
        previous_close=previous_close,
        open=float(fields[8]),
        high=float(fields[4]),
        low=float(fields[5]),
        volume=float(fields[9]),
        updated_at=updated_at.astimezone(CN_TZ),
        change_pct=(price / previous_close - 1) * 100 if previous_close else 0.0,
        source="Sina Finance · SGE Au99.99 last completed session",
    )


def fetch_domestic_sge() -> DomesticGoldQuote:
    primary = _fetch_domestic_primary()
    if primary.updated_at > datetime.now(timezone.utc).astimezone(CN_TZ) + timedelta(
        minutes=30
    ):
        try:
            return _fetch_domestic_last_session()
        except Exception:
            pass
    return primary


def _fetch_gold_api_spot() -> InternationalGoldQuote:
    payload = fetch_bytes(
        "https://api.gold-api.com/price/XAU",
        "application/json",
        headers={"Referer": "https://gold-api.com/"},
    )
    data = json.loads(payload.decode("utf-8"))
    updated_text = str(data.get("updatedAt") or "")
    updated_at = datetime.fromisoformat(updated_text.replace("Z", "+00:00"))
    return InternationalGoldQuote(
        symbol="XAU/USD",
        name="国际现货黄金",
        price_usd_per_oz=float(data["price"]),
        high_usd_per_oz=None,
        low_usd_per_oz=None,
        updated_at=updated_at.astimezone(timezone.utc),
        source="Gold API · XAU/USD",
    )


def _fetch_sina_spot_fallback() -> InternationalGoldQuote:
    url = "https://hq.sinajs.cn/list=hf_XAU"
    payload = fetch_bytes(
        url,
        "text/plain",
        headers={"Referer": "https://finance.sina.com.cn/"},
    )
    text = payload.decode("gbk", errors="replace")
    match = re.search(r'hq_str_hf_XAU="([^"]*)"', text)
    if not match:
        raise DataError("international XAU quote was not present in response")
    fields = [value.strip() for value in match.group(1).split(",")]
    if len(fields) < 13:
        raise DataError(f"international XAU quote had only {len(fields)} fields")
    date_text = fields[12]
    updated_at = datetime.fromisoformat(f"{date_text}T{fields[6]}+08:00")
    return InternationalGoldQuote(
        symbol="XAU/USD",
        name="伦敦金（现货黄金）",
        price_usd_per_oz=float(fields[0]),
        high_usd_per_oz=float(fields[4]),
        low_usd_per_oz=float(fields[5]),
        updated_at=updated_at.astimezone(timezone.utc),
        source="Sina Finance · London spot fallback",
    )


def fetch_international_spot() -> InternationalGoldQuote:
    try:
        primary = _fetch_gold_api_spot()
        try:
            fallback = _fetch_sina_spot_fallback()
            primary.high_usd_per_oz = fallback.high_usd_per_oz
            primary.low_usd_per_oz = fallback.low_usd_per_oz
        except Exception:
            pass
        return primary
    except Exception as primary_error:
        try:
            return _fetch_sina_spot_fallback()
        except Exception as fallback_error:
            raise DataError(
                f"international spot failed: {primary_error}; fallback: {fallback_error}"
            ) from fallback_error


def build_comparison(
    domestic: DomesticGoldQuote | None,
    international: InternationalGoldQuote | None,
    fx_usd_cny: float | None,
    error: str | None = None,
) -> dict:
    if domestic is None or international is None or fx_usd_cny is None:
        return {
            "available": False,
            "status": "价格对比暂不可用",
            "error": error or "缺少国内价格、国际价格或汇率",
            "domestic": None,
            "international": None,
            "spread": None,
        }
    international_cny = international.price_usd_per_oz * fx_usd_cny / TROY_OUNCE_GRAMS
    spread = domestic.price_cny_per_gram - international_cny
    spread_pct = (
        spread / international_cny * 100 if international_cny > 0 else 0.0
    )
    if spread_pct >= 0.5:
        status = "国内升水"
    elif spread_pct <= -0.5:
        status = "国内折价"
    else:
        status = "接近国际换算价"
    time_gap_minutes = abs(
        (domestic.updated_at - international.updated_at).total_seconds() / 60
    )
    aligned = time_gap_minutes <= 120
    return {
        "available": True,
        "status": status,
        "time_aligned": aligned,
        "time_gap_minutes": round(time_gap_minutes, 1),
        "fx_usd_cny": round(fx_usd_cny, 6),
        "domestic": {
            "symbol": domestic.symbol,
            "name": domestic.name,
            "contract": domestic.contract,
            "price_cny_per_gram": round(domestic.price_cny_per_gram, 2),
            "change_pct": round(domestic.change_pct, 4),
            "high_cny_per_gram": round(domestic.high, 2),
            "low_cny_per_gram": round(domestic.low, 2),
            "volume": domestic.volume,
            "updated_at": domestic.updated_at,
            "source": domestic.source,
        },
        "international": {
            "symbol": international.symbol,
            "name": international.name,
            "price_usd_per_oz": round(international.price_usd_per_oz, 2),
            "price_cny_per_gram": round(international_cny, 2),
            "high_cny_per_gram": (
                round(international.high_usd_per_oz * fx_usd_cny / TROY_OUNCE_GRAMS, 2)
                if international.high_usd_per_oz is not None
                else None
            ),
            "low_cny_per_gram": (
                round(international.low_usd_per_oz * fx_usd_cny / TROY_OUNCE_GRAMS, 2)
                if international.low_usd_per_oz is not None
                else None
            ),
            "updated_at": international.updated_at,
            "source": international.source,
        },
        "spread": {
            "cny_per_gram": round(spread, 2),
            "pct": round(spread_pct, 4),
            "label": status,
        },
        "note": (
            "国内价为上金所 Au99.99，国际价为伦敦现货 XAU/USD 换算值。"
            "价差受交易时段、汇率、税费、运输保险和国内供需影响，不能直接视为无风险套利。"
        ),
    }

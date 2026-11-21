from __future__ import annotations

import email.utils
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from typing import Callable

from .data import DataError, fetch_bytes, fetch_json
from .lexicon import EXCLUDE_CONTEXT_TERMS, GOLD_TERMS, MARKET_CONTEXT_TERMS
from .models import NewsItem


QUERY = 'gold price OR bullion OR XAUUSD OR "precious metals" OR 黄金 OR 金价'


def _real_link(link: str) -> str:
    parsed = urllib.parse.urlparse(link)
    if parsed.netloc.endswith("bing.com"):
        nested = urllib.parse.parse_qs(parsed.query).get("url")
        if nested:
            return urllib.parse.unquote(nested[0])
    return link


def _source_from_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    return host or "未知来源"


def _parse_rss(payload: bytes, feed_name: str) -> list[NewsItem]:
    root = ET.fromstring(payload)
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[NewsItem] = []
    for node in channel.findall("item"):
        title = unescape((node.findtext("title") or "").strip())
        raw_link = (node.findtext("link") or "").strip()
        if not title or not raw_link:
            continue
        link = _real_link(raw_link)
        pub_text = (node.findtext("pubDate") or node.findtext("{*}date") or "").strip()
        published: datetime | None = None
        if pub_text:
            try:
                published = email.utils.parsedate_to_datetime(pub_text)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                published = None
        source_node = node.findtext("source") or ""
        source = unescape(source_node).strip() or _source_from_url(link) or feed_name
        title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title).strip()
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=source,
                published_at=published,
            )
        )
    return items


def _fetch_rss(name: str, url: str) -> tuple[str, list[NewsItem]]:
    payload = fetch_bytes(url, "application/rss+xml, application/xml, text/xml")
    return name, _parse_rss(payload, name)


def _fetch_gdelt() -> tuple[str, list[NewsItem]]:
    query = urllib.parse.quote("(gold OR bullion OR XAUUSD OR 黄金 OR 金价)", safe="")
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={query}&mode=artlist&maxrecords=75&format=json"
        "&timespan=24h&sort=hybridrel"
    )
    data = fetch_json(url)
    items: list[NewsItem] = []
    for article in data.get("articles", []):
        title = unescape(str(article.get("title") or "")).strip()
        link = str(article.get("url") or "").strip()
        if not title or not link:
            continue
        published = None
        raw_date = str(article.get("seendate") or "")
        try:
            published = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=str(article.get("domain") or _source_from_url(link)),
                published_at=published,
            )
        )
    return "GDELT", items


def _normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title.lower())[:120]


def _is_gold_related(title: str) -> bool:
    lowered = title.lower()
    if not any(term in lowered for term in GOLD_TERMS):
        return False
    if any(term in lowered for term in EXCLUDE_CONTEXT_TERMS):
        return False
    return any(term in lowered for term in MARKET_CONTEXT_TERMS)


def fetch_news(limit: int = 60) -> tuple[list[NewsItem], list[str]]:
    encoded_query = urllib.parse.quote_plus(QUERY)
    sources: list[tuple[str, Callable[[], tuple[str, list[NewsItem]]]]] = [
        (
            "Bing News",
            lambda: _fetch_rss(
                "Bing News",
                f"https://www.bing.com/news/search?q={encoded_query}&format=rss&setlang=en-US",
            ),
        ),
        (
            "Google News",
            lambda: _fetch_rss(
                "Google News",
                "https://news.google.com/rss/search?"
                f"q={encoded_query}&hl=en-US&gl=US&ceid=US:en",
            ),
        ),
        (
            "Yahoo Finance",
            lambda: _fetch_rss(
                "Yahoo Finance",
                "https://feeds.finance.yahoo.com/rss/2.0/headline?"
                "s=GC%3DF&region=US&lang=en-US",
            ),
        ),
        (
            "Investing.com",
            lambda: _fetch_rss(
                "Investing.com",
                "https://www.investing.com/rss/news_25.rss",
            ),
        ),
        ("GDELT", _fetch_gdelt),
    ]
    all_items: list[NewsItem] = []
    statuses: list[str] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        future_map = {pool.submit(loader): name for name, loader in sources}
        for future in as_completed(future_map):
            source_name = future_map[future]
            try:
                name, items = future.result()
                all_items.extend(items)
                statuses.append(f"{name}: {len(items)} 条")
            except Exception as exc:
                statuses.append(f"{source_name}: 获取失败 - {exc}")
    deduplicated: dict[str, NewsItem] = {}
    for item in all_items:
        if not _is_gold_related(item.title):
            continue
        key = _normalized_title(item.title)
        if not key:
            continue
        current = deduplicated.get(key)
        if current is None or (
            item.published_at
            and (current.published_at is None or item.published_at > current.published_at)
        ):
            deduplicated[key] = item
    items = sorted(
        deduplicated.values(),
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    statuses.sort()
    return items[:limit], statuses

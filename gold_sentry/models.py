from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published_at: datetime | None
    sentiment: float = 0.0
    importance: float = 0.0
    matched_terms: list[str] = field(default_factory=list)


@dataclass
class NewsAnalysis:
    score: float
    impact: float
    summary: str
    item_count: int
    source_status: list[str]


@dataclass
class MarketPoint:
    key: str
    label: str
    value: float
    change_label: str
    bias: str


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from gold_sentry.engine import analyze_bars, analyze_news, compose_snapshot
from gold_sentry.models import Bar, NewsItem


def make_bars(direction: str, now: datetime) -> list[Bar]:
    bars: list[Bar] = []
    price = 3600.0
    for index in range(80):
        current = price + index * 0.1
        bars.append(
            Bar(
                timestamp=now - timedelta(minutes=5 * (79 - index)),
                open=current,
                high=current + 1,
                low=current - 1,
                close=current + 0.2,
                volume=100,
            )
        )
    price = bars[-1].close
    for index in range(3):
        if direction == "buy":
            open_price = price + index * 4
            close_price = open_price + 4
        else:
            open_price = price - index * 4
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
    return bars


class MarketAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

    def test_large_buying_pressure_is_detected(self) -> None:
        result = analyze_bars(make_bars("buy", self.now), self.now)
        self.assertTrue(result["is_fresh"])
        self.assertTrue(result["large_buy"])
        self.assertFalse(result["large_sell"])
        self.assertGreater(result["flow_score"], 0)
        self.assertGreater(result["volume_ratio"], 1.45)

    def test_large_selling_pressure_is_detected(self) -> None:
        result = analyze_bars(make_bars("sell", self.now), self.now)
        self.assertTrue(result["is_fresh"])
        self.assertTrue(result["large_sell"])
        self.assertFalse(result["large_buy"])
        self.assertLess(result["flow_score"], 0)
        self.assertLess(result["signed_volume_ratio"], -0.22)

    def test_old_data_is_marked_stale(self) -> None:
        bars = make_bars("sell", self.now - timedelta(hours=3))
        result = analyze_bars(bars, self.now)
        self.assertFalse(result["is_fresh"])
        self.assertEqual(result["market_status"], "休市或数据延迟")

    def test_buy_and_sell_demo_snapshots_differ(self) -> None:
        from gold_sentry.engine import demo_snapshot

        buy = demo_snapshot("buy")
        sell = demo_snapshot("sell")
        self.assertEqual(buy["signal_type"], "BUY")
        self.assertEqual(sell["signal_type"], "SELL")
        self.assertGreater(buy["composite_score"], 0)
        self.assertLess(sell["composite_score"], 0)


class NewsAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

    def test_hawkish_and_selloff_headline_is_bearish(self) -> None:
        items = [
            NewsItem(
                title="Gold plunges as hawkish Fed raises rate hike fears",
                url="https://example.com/bearish",
                source="example.com",
                published_at=self.now - timedelta(minutes=15),
            )
        ]
        analysis, scored = analyze_news(items, self.now)
        self.assertLess(analysis.score, -0.3)
        self.assertGreater(analysis.impact, 0)
        self.assertLess(scored[0].sentiment, 0)

    def test_dovish_headline_is_bullish(self) -> None:
        items = [
            NewsItem(
                title="Gold rallies as Fed signals rate cut and dollar falls",
                url="https://example.com/bullish",
                source="example.com",
                published_at=self.now - timedelta(minutes=15),
            )
        ]
        analysis, scored = analyze_news(items, self.now)
        self.assertGreater(analysis.score, 0.3)
        self.assertGreater(scored[0].sentiment, 0)

    def test_news_is_still_counted_when_market_is_missing(self) -> None:
        items = [
            NewsItem(
                title="Gold crashes as forced liquidation spreads",
                url="https://example.com/crash",
                source="example.com",
                published_at=self.now - timedelta(minutes=10),
            )
        ]
        snapshot = compose_snapshot(
            market=None,
            raw_news=items,
            news_status=["demo"],
            market_error="market unavailable",
            now=self.now,
        )
        self.assertEqual(snapshot["market_status"], "行情获取失败")
        self.assertLess(snapshot["news_score"], 0)
        self.assertTrue(snapshot["alerts"])


if __name__ == "__main__":
    unittest.main()

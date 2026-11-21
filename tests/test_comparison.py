from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from gold_sentry.comparison import (
    DomesticGoldQuote,
    InternationalGoldQuote,
    build_comparison,
)


class GoldComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 21, 4, 0, tzinfo=timezone.utc)
        self.domestic = DomesticGoldQuote(
            symbol="AU9999",
            name="沪金99",
            contract="Au99.99",
            price_cny_per_gram=766.0,
            previous_close=764.55,
            open=770.5,
            high=773.5,
            low=760.0,
            volume=8932,
            updated_at=self.now,
            change_pct=0.2,
            source="SGE",
        )
        self.international = InternationalGoldQuote(
            symbol="XAU/USD",
            name="国际现货黄金",
            price_usd_per_oz=3539.0,
            high_usd_per_oz=3636.63,
            low_usd_per_oz=3502.73,
            updated_at=self.now,
            source="Gold API",
        )

    def test_domestic_premium_is_calculated_in_cny_per_gram(self) -> None:
        result = build_comparison(self.domestic, self.international, 6.68)
        self.assertTrue(result["available"])
        self.assertAlmostEqual(
            result["international"]["price_cny_per_gram"],
            760.06,
            places=2,
        )
        self.assertAlmostEqual(result["spread"]["cny_per_gram"], 5.94, places=2)
        self.assertAlmostEqual(result["spread"]["pct"], 0.78, places=2)
        self.assertEqual(result["status"], "国内升水")
        self.assertTrue(result["time_aligned"])

    def test_large_time_gap_marks_comparison_as_not_aligned(self) -> None:
        self.domestic.updated_at = self.now - timedelta(hours=6)
        result = build_comparison(self.domestic, self.international, 6.68)
        self.assertFalse(result["time_aligned"])
        self.assertGreater(result["time_gap_minutes"], 120)

    def test_missing_fx_returns_explicit_unavailable_state(self) -> None:
        result = build_comparison(self.domestic, self.international, None)
        self.assertFalse(result["available"])
        self.assertIn("汇率", result["error"])


if __name__ == "__main__":
    unittest.main()

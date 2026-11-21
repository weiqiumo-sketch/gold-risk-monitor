from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from gold_sentry.portfolio import (
    PortfolioConfig,
    evaluate_portfolio_alert,
    read_portfolio_from_env,
)


LEVELS = {
    "buy": {"target1_cny": 775.24},
    "sell": {"breakdown_entry_cny": 752.31, "target1_cny": 738.45},
}


class PortfolioTests(unittest.TestCase):
    def test_env_portfolio_is_read_without_exposing_it(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOLD_HOLDINGS_GRAMS": "2100",
                "GOLD_COST_BASIS_CNY": "1000",
            },
            clear=False,
        ):
            portfolio = read_portfolio_from_env()
        self.assertEqual(portfolio, PortfolioConfig(2100, 1000))

    def test_current_loss_triggers_generic_warning(self) -> None:
        portfolio = PortfolioConfig(2100, 1000)
        state, alert = evaluate_portfolio_alert(portfolio, 760.06, LEVELS)
        self.assertEqual(state["state"], "loss_warning")
        self.assertEqual(alert["type"], "PORTFOLIO")
        self.assertNotIn("2100", alert["message"])
        self.assertNotIn("1000", alert["message"])

    def test_defense_and_breakeven_states_have_priority(self) -> None:
        portfolio = PortfolioConfig(2100, 1000)
        defense_state, defense_alert = evaluate_portfolio_alert(
            portfolio, 752.0, LEVELS
        )
        breakeven_state, breakeven_alert = evaluate_portfolio_alert(
            portfolio, 1000.0, LEVELS
        )
        self.assertEqual(defense_state["state"], "defense_triggered")
        self.assertEqual(defense_alert["severity"], "高")
        self.assertEqual(breakeven_state["state"], "breakeven_reached")
        self.assertEqual(breakeven_alert["severity"], "中")


if __name__ == "__main__":
    unittest.main()

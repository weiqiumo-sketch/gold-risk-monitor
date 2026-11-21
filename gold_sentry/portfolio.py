from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PortfolioConfig:
    holdings_grams: float
    cost_basis_cny: float


def read_portfolio_from_env() -> PortfolioConfig | None:
    try:
        grams = float(os.getenv("GOLD_HOLDINGS_GRAMS", ""))
        cost = float(os.getenv("GOLD_COST_BASIS_CNY", ""))
    except ValueError:
        return None
    if grams <= 0 or cost <= 0:
        return None
    return PortfolioConfig(holdings_grams=grams, cost_basis_cny=cost)


def evaluate_portfolio_alert(
    portfolio: PortfolioConfig | None,
    price_cny: float | None,
    trade_levels: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if portfolio is None:
        return None, None
    state: dict[str, Any] = {
        "configured": True,
        "state": "waiting",
        "message": "个人持仓云端监测已启用。",
    }
    if price_cny is None:
        return state, None
    cost = portfolio.cost_basis_cny
    loss_pct = (price_cny / cost - 1) * 100
    buy_target_1 = (
        trade_levels["buy"]["target1_cny"] if trade_levels else None
    )
    sell_breakdown = (
        trade_levels["sell"]["breakdown_entry_cny"] if trade_levels else None
    )
    sell_target_1 = (
        trade_levels["sell"]["target1_cny"] if trade_levels else None
    )

    if price_cny >= cost:
        state.update(
            {
                "state": "breakeven_reached",
                "message": "个人持仓价格已达到成本或以上，请分批管理仓位。",
            }
        )
        alert = {
            "type": "PORTFOLIO",
            "severity": "中",
            "title": "个人持仓达到回本区",
            "message": "价格已达到个人成本区；建议按既定计划分批调整仓位。",
        }
    elif sell_target_1 is not None and price_cny <= sell_target_1:
        state.update(
            {
                "state": "deep_risk",
                "message": "个人持仓进入深度风险区，优先保护剩余本金。",
            }
        )
        alert = {
            "type": "PORTFOLIO",
            "severity": "高",
            "title": "个人持仓进入深度风险区",
            "message": "价格跌破第二级防守区域；不要补仓摊平，按计划核查机动仓风险。",
        }
    elif sell_breakdown is not None and price_cny <= sell_breakdown:
        state.update(
            {
                "state": "defense_triggered",
                "message": "个人持仓跌破短期防守位。",
            }
        )
        alert = {
            "type": "PORTFOLIO",
            "severity": "高",
            "title": "个人持仓跌破防守位",
            "message": "价格跌破短期防守位；暂停补仓，按分阶段计划评估机动仓。",
        }
    elif buy_target_1 is not None and price_cny >= buy_target_1:
        state.update(
            {
                "state": "rebound_target",
                "message": "个人持仓进入第一反弹目标区。",
            }
        )
        alert = {
            "type": "PORTFOLIO",
            "severity": "中",
            "title": "个人持仓进入反弹目标区",
            "message": "价格达到第一反弹目标；按计划分批处理机动仓并移动止损。",
        }
    elif loss_pct <= -20:
        state.update(
            {
                "state": "loss_warning",
                "message": "个人持仓价格仍显著低于成本，保持风险控制。",
            }
        )
        alert = {
            "type": "PORTFOLIO",
            "severity": "中",
            "title": "个人持仓亏损警戒",
            "message": "价格仍显著低于个人成本；不要使用杠杆或持续补仓摊平。",
        }
    return state, alert

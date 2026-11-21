from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any


ISSUE_TITLE = "GoldSentry 黄金风险提醒"


class GitHubIssueNotifier:
    def __init__(self) -> None:
        self.token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        self.repository = os.getenv("GITHUB_REPOSITORY")
        self.api = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repository)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        if not self.enabled:
            raise RuntimeError("GITHUB_TOKEN or GITHUB_REPOSITORY is missing")
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.api + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "GoldSentry/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {exc.code}: {detail}") from exc

    def _open_alert_issue(self) -> dict[str, Any] | None:
        assert self.repository
        path = (
            f"/repos/{self.repository}/issues"
            "?state=open&labels=gold-risk&per_page=100"
        )
        issues = self._request("GET", path)
        for issue in issues:
            if issue.get("title") == ISSUE_TITLE and "pull_request" not in issue:
                return issue
        return None

    def _issue_body(self, snapshot: dict[str, Any]) -> str:
        price = snapshot.get("price")
        price_text = f"{price:,.2f} 美元/盎司" if isinstance(price, (int, float)) else "暂无"
        lines = [
            "## 当前信号",
            "",
            f"- **黄金价格：** {price_text}",
            f"- **市场状态：** {snapshot.get('market_status')}",
            f"- **建议：** {snapshot.get('decision')}",
            f"- **综合评分：** {float(snapshot.get('composite_score', 0)):+.2f}（-1 偏空，+1 偏多）",
            f"- **风险：** {snapshot.get('risk_score', 0)}/100",
            f"- **置信度：** {snapshot.get('confidence', 0)}%",
            "",
            "## 触发提醒",
            "",
        ]
        for alert in snapshot.get("alerts", []):
            lines.append(
                f"- **[{alert.get('severity')}] {alert.get('title')}：** "
                f"{alert.get('message')}"
            )
        levels = snapshot.get("trade_levels")
        if levels:
            active = {
                "BUY": "买入 / 做多",
                "SELL": "卖出 / 做空",
                "NEUTRAL": "中性",
            }.get(levels.get("active_side"), "中性")
            buy = levels["buy"]
            sell = levels["sell"]
            lines.extend(
                [
                    "",
                    "## 行动价位",
                    "",
                    f"- **当前偏向：** {active}",
                    f"- **买入 / 做多：** 突破 `{buy['breakout_entry']:,.1f}`，"
                    f"回踩 `{buy['pullback_zone'][0]:,.1f}—{buy['pullback_zone'][1]:,.1f}`，"
                    f"止损 `{buy['stop']:,.1f}`，目标 "
                    f"`{buy['target1']:,.1f}` / `{buy['target2']:,.1f}`。"
                    f"状态：{buy['status']}",
                    f"- **卖出 / 做空：** 破位 `{sell['breakdown_entry']:,.1f}`，"
                    f"反抽 `{sell['rebound_zone'][0]:,.1f}—{sell['rebound_zone'][1]:,.1f}`，"
                    f"止损 `{sell['stop']:,.1f}`，目标 "
                    f"`{sell['target1']:,.1f}` / `{sell['target2']:,.1f}`。"
                    f"状态：{sell['status']}",
                    f"- **计算口径：** ATR `{levels.get('atr', 0):,.1f}`，"
                    f"结构高 `{levels.get('structure_high', 0):,.1f}`，"
                    f"结构低 `{levels.get('structure_low', 0):,.1f}`。",
                    f"- **重要限制：** {levels.get('note', '')}",
                ]
            )
        lines.extend(["", "## 主要新闻", ""])
        for item in snapshot.get("news", [])[:6]:
            sentiment = float(item.get("sentiment", 0))
            label = "利好" if sentiment > 0.1 else "利空" if sentiment < -0.1 else "中性"
            lines.append(
                f"- [{item.get('title')}]({item.get('url')}) "
                f"（{item.get('source')}，{label} {sentiment:+.2f}）"
            )
        lines.extend(
            [
                "",
                "## 判断依据",
                "",
                *[f"- {reason}" for reason in snapshot.get("reasons", [])],
                "",
                "> 数据来自 Yahoo Finance、新闻 RSS 与 GDELT。买卖方向为 K 线成交量代理，"
                "不是逐笔主动成交数据。此提醒仅用于风险监控，不构成投资建议。",
                "",
                f"<!-- gold-sentry-signature:{snapshot.get('alert_signature', '')} -->",
            ]
        )
        return "\n".join(lines)

    def publish(self, snapshot: dict[str, Any]) -> str:
        if not self.enabled:
            return "GitHub 提醒未启用：当前环境没有 GITHUB_TOKEN。"
        assert self.repository
        issue = self._open_alert_issue()
        alerts = snapshot.get("alerts", [])
        body = self._issue_body(snapshot) if alerts else ""
        signature = str(snapshot.get("alert_signature", ""))
        marker = f"gold-sentry-signature:{signature}"
        if alerts and issue is None:
            payload = {
                "title": ISSUE_TITLE,
                "body": body,
                "labels": ["gold-risk"],
            }
            created = self._request(
                "POST",
                f"/repos/{self.repository}/issues",
                payload,
            )
            return f"已创建风险 Issue #{created.get('number')}"
        if alerts and issue:
            if marker in str(issue.get("body", "")):
                return f"风险 Issue #{issue.get('number')} 未变化"
            self._request(
                "PATCH",
                f"/repos/{self.repository}/issues/{issue['number']}",
                {"body": body},
            )
            return f"已更新风险 Issue #{issue.get('number')}"
        if not alerts and issue:
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            self._request(
                "POST",
                f"/repos/{self.repository}/issues/{issue['number']}/comments",
                {"body": f"风险阈值已回落，GoldSentry 于 {now} 自动关闭提醒。"},
            )
            self._request(
                "PATCH",
                f"/repos/{self.repository}/issues/{issue['number']}",
                {"state": "closed", "state_reason": "completed"},
            )
            return f"风险解除，已关闭 Issue #{issue.get('number')}"
        return "当前没有达到提醒阈值的风险。"

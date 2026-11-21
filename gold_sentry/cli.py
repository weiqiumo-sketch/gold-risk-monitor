from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .engine import build_live_snapshot, demo_snapshot
from .models import json_default
from .notifier import GitHubIssueNotifier


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "site" / "data" / "latest.json"


def load_config() -> dict[str, Any]:
    path = ROOT / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_snapshot(snapshot: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2,
            default=json_default,
        )
        + "\n",
        encoding="utf-8",
    )
    temp.replace(destination)


def print_snapshot(snapshot: dict[str, Any]) -> None:
    price = snapshot.get("price")
    print(f"GoldSentry | {snapshot.get('decision')}")
    print(
        "价格: "
        + (f"{price:,.2f} {snapshot.get('symbol')}" if isinstance(price, (int, float)) else "暂无")
    )
    print(
        f"综合评分: {snapshot.get('composite_score', 0):+.2f} | "
        f"风险: {snapshot.get('risk_score', 0)}/100 | "
        f"置信度: {snapshot.get('confidence', 0)}%"
    )
    print(f"市场: {snapshot.get('market_status')} | 新闻: {snapshot.get('news_summary')}")
    alerts = snapshot.get("alerts", [])
    if alerts:
        print("提醒:")
        for alert in alerts:
            print(f"  [{alert['severity']}] {alert['title']} - {alert['message']}")
    else:
        print("提醒: 当前没有触发阈值")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GoldSentry gold price and news risk monitor"
    )
    parser.add_argument("--once", action="store_true", help="运行一次并输出结果")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    parser.add_argument(
        "--update-web",
        nargs="?",
        const=str(DEFAULT_OUTPUT),
        help="将结果写入 GitHub Pages 使用的 JSON 文件",
    )
    parser.add_argument(
        "--demo",
        choices=("buy", "sell"),
        help="使用确定性的买卖盘演示数据",
    )
    parser.add_argument(
        "--github-issue",
        action="store_true",
        help="使用 GITHUB_TOKEN 创建或更新风险 Issue",
    )
    args = parser.parse_args(argv)
    config = load_config()
    try:
        snapshot = (
            demo_snapshot(args.demo)
            if args.demo
            else build_live_snapshot(
                symbol=str(config.get("symbol", "GC=F")),
                news_limit=int(config.get("news_limit", 60)),
            )
        )
    except Exception as exc:
        print(f"GoldSentry 采集失败: {exc}", file=sys.stderr)
        return 1
    if args.update_web:
        write_snapshot(snapshot, Path(args.update_web))
        print(f"已写入 {args.update_web}")
    if args.github_issue:
        try:
            result = GitHubIssueNotifier().publish(snapshot)
            print(result)
        except Exception as exc:
            print(f"GitHub Issue 提醒失败: {exc}", file=sys.stderr)
            return 2
    if args.json:
        print(
            json.dumps(
                snapshot,
                ensure_ascii=False,
                indent=2,
                default=json_default,
            )
        )
    elif not args.update_web:
        print_snapshot(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

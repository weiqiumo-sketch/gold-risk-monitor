from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Any

from .cli import ROOT, load_config
from .engine import build_live_snapshot


BG = "#0a0f18"
PANEL = "#111a28"
PANEL_2 = "#172335"
TEXT = "#edf4ff"
MUTED = "#93a4bb"
GREEN = "#34d399"
RED = "#fb7185"
AMBER = "#fbbf24"
BLUE = "#60a5fa"


def format_cny(value: Any) -> str:
    return f"{float(value):,.2f}" if isinstance(value, (int, float)) else "--"


class GoldSentryApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GoldSentry 黄金风险哨兵")
        self.root.geometry("1120x780")
        self.root.minsize(900, 650)
        self.root.configure(bg=BG)
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.config = load_config()
        self.loading = False
        self.auto_refresh = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="准备刷新")
        self.price_var = tk.StringVar(value="--")
        self.change_var = tk.StringVar(value="--")
        self.flow_var = tk.StringVar(value="--")
        self.risk_var = tk.StringVar(value="--")
        self.decision_var = tk.StringVar(value="等待数据")
        self.action_var = tk.StringVar(value="正在获取行情和新闻…")
        self.levels_var = tk.StringVar(value="正在计算买卖价位…")
        self.comparison_var = tk.StringVar(value="正在读取国内外金价…")
        self.last_signature = ""
        self._build_style()
        self._build_layout()
        self.refresh()
        self.root.after(500, self._poll_queue)

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL_2,
            foreground=MUTED,
            borderwidth=0,
            padding=7,
        )
        style.map("Treeview", background=[("selected", "#244566")])
        style.configure(
            "TButton",
            background=BLUE,
            foreground="#06101e",
            padding=(14, 8),
            borderwidth=0,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map("TButton", background=[("active", "#93c5fd")])

    def _card(self, parent: tk.Widget) -> tuple[tk.Frame, tk.Label, tk.Label]:
        frame = tk.Frame(parent, bg=PANEL, padx=16, pady=12)
        title = tk.Label(frame, text="", bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 9))
        title.pack(anchor="w")
        value = tk.Label(
            frame,
            text="--",
            bg=PANEL,
            fg=TEXT,
            font=("Microsoft YaHei UI", 20, "bold"),
        )
        value.pack(anchor="w", pady=(3, 0))
        return frame, title, value

    def _build_layout(self) -> None:
        header = tk.Frame(self.root, bg=BG, padx=22, pady=16)
        header.pack(fill="x")
        tk.Label(
            header,
            text="GOLDSENTRY",
            bg=BG,
            fg=AMBER,
            font=("Segoe UI", 22, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text="黄金价格 · 成交压力 · 重大新闻",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", padx=14, pady=(8, 0))
        ttk.Button(header, text="立即刷新", command=self.refresh).pack(side="right")
        tk.Checkbutton(
            header,
            text="自动刷新",
            variable=self.auto_refresh,
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=TEXT,
            selectcolor=PANEL,
        ).pack(side="right", padx=14)

        cards = tk.Frame(self.root, bg=BG, padx=18)
        cards.pack(fill="x")
        price_card, price_title, price_value = self._card(cards)
        price_card.grid(row=0, column=0, sticky="nsew", padx=4)
        price_title.configure(text="黄金价格 · 元/克")
        price_value.configure(textvariable=self.price_var)
        change_card, change_title, change_value = self._card(cards)
        change_card.grid(row=0, column=1, sticky="nsew", padx=4)
        change_title.configure(text="日涨跌")
        change_value.configure(textvariable=self.change_var)
        flow_card, flow_title, flow_value = self._card(cards)
        flow_card.grid(row=0, column=2, sticky="nsew", padx=4)
        flow_title.configure(text="成交方向代理")
        flow_value.configure(textvariable=self.flow_var)
        risk_card, risk_title, risk_value = self._card(cards)
        risk_card.grid(row=0, column=3, sticky="nsew", padx=4)
        risk_title.configure(text="风险分")
        risk_value.configure(textvariable=self.risk_var, fg=AMBER)
        self.risk_value_label = risk_value
        for column in range(4):
            cards.grid_columnconfigure(column, weight=1)

        signal = tk.Frame(self.root, bg=PANEL_2, padx=20, pady=15)
        signal.pack(fill="x", padx=22, pady=14)
        tk.Label(
            signal,
            textvariable=self.decision_var,
            bg=PANEL_2,
            fg=TEXT,
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            signal,
            textvariable=self.action_var,
            bg=PANEL_2,
            fg=MUTED,
            justify="left",
            wraplength=1020,
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            signal,
            textvariable=self.comparison_var,
            bg=PANEL_2,
            fg=AMBER,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w", pady=(8, 0))

        body = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            bg=BG,
            sashwidth=8,
            borderwidth=0,
        )
        body.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        left = tk.Frame(body, bg=PANEL)
        right = tk.Frame(body, bg=BG)
        body.add(left, minsize=380)
        body.add(right, minsize=420)

        tk.Label(
            left,
            text="黄金 5 分钟走势",
            bg=PANEL,
            fg=TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 4))
        self.canvas = tk.Canvas(left, bg=PANEL, highlightthickness=0, height=220)
        self.canvas.pack(fill="x", padx=10, pady=6)
        self.canvas.bind("<Configure>", lambda _event: self._draw_chart())
        tk.Label(
            left,
            text="买卖点计划",
            bg=PANEL,
            fg=TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(7, 3))
        tk.Label(
            left,
            textvariable=self.levels_var,
            bg=PANEL,
            fg=MUTED,
            justify="left",
            anchor="w",
            wraplength=520,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(
            left,
            text="风险提醒",
            bg=PANEL,
            fg=TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(8, 4))
        self.alerts_list = tk.Listbox(
            left,
            bg=PANEL,
            fg=TEXT,
            selectbackground="#244566",
            relief="flat",
            highlightthickness=0,
            height=9,
            font=("Microsoft YaHei UI", 9),
        )
        self.alerts_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tk.Label(
            right,
            text="相关重大新闻",
            bg=BG,
            fg=TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 5))
        columns = ("importance", "sentiment", "source", "title")
        self.news_tree = ttk.Treeview(right, columns=columns, show="headings")
        self.news_tree.heading("importance", text="重要度")
        self.news_tree.heading("sentiment", text="情绪")
        self.news_tree.heading("source", text="来源")
        self.news_tree.heading("title", text="标题（双击打开）")
        self.news_tree.column("importance", width=62, anchor="center")
        self.news_tree.column("sentiment", width=58, anchor="center")
        self.news_tree.column("source", width=110, anchor="w")
        self.news_tree.column("title", width=480, anchor="w")
        scrollbar = ttk.Scrollbar(right, orient="vertical", command=self.news_tree.yview)
        self.news_tree.configure(yscrollcommand=scrollbar.set)
        self.news_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.news_tree.bind("<Double-1>", self._open_news)

        footer = tk.Frame(self.root, bg=BG, padx=22, pady=8)
        footer.pack(fill="x")
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        tk.Label(
            footer,
            text="仅供风险监控，不构成投资建议",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="right")
        self.snapshot: dict[str, Any] = {}

    def refresh(self) -> None:
        if self.loading:
            return
        self.loading = True
        self.status_var.set("正在抓取行情与新闻…")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self) -> None:
        try:
            snapshot = build_live_snapshot(
                symbol=str(self.config.get("symbol", "GC=F")),
                news_limit=int(self.config.get("news_limit", 60)),
            )
            self.queue.put({"ok": True, "snapshot": snapshot})
        except Exception as exc:
            self.queue.put({"ok": False, "error": str(exc)})

    def _poll_queue(self) -> None:
        try:
            result = self.queue.get_nowait()
        except queue.Empty:
            self.root.after(500, self._poll_queue)
            return
        self.loading = False
        if result["ok"]:
            self._render(result["snapshot"])
        else:
            self.status_var.set(f"刷新失败：{result['error']}")
        self.root.after(500, self._poll_queue)
        if self.auto_refresh.get():
            minutes = int(self.config.get("desktop_refresh_minutes", 10))
            self.root.after(max(60_000, minutes * 60_000), self.refresh)

    def _render(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        price = snapshot.get("display_price")
        self.price_var.set(f"{price:,.2f}" if isinstance(price, (int, float)) else "--")
        change = float(snapshot.get("price_change_pct", 0))
        self.change_var.set(f"{change:+.2f}%")
        signed = float(snapshot.get("signed_volume_ratio", 0))
        self.flow_var.set(f"{signed:+.0%}")
        self.risk_var.set(f"{snapshot.get('risk_score', 0):.1f}")
        self.decision_var.set(str(snapshot.get("decision", "观望")))
        self.action_var.set(str(snapshot.get("action_text", "")))
        comparison = snapshot.get("gold_comparison")
        if comparison and comparison.get("available"):
            domestic = comparison["domestic"]["price_cny_per_gram"]
            international = comparison["international"]["price_cny_per_gram"]
            spread = comparison["spread"]
            timing = (
                ""
                if comparison.get("time_aligned")
                else " · 交易时段不同"
            )
            self.comparison_var.set(
                f"国内 {domestic:,.2f} | 国际 {international:,.2f} | "
                f"{spread['label']} {spread['pct']:+.2f}%{timing}"
            )
        else:
            self.comparison_var.set("国内外金价对比暂不可用")
        levels = snapshot.get("trade_levels")
        if levels:
            buy = levels["buy"]
            sell = levels["sell"]
            self.levels_var.set(
                f"买入：突破 {format_cny(buy['breakout_entry_cny'])}，回踩 "
                f"{format_cny(buy['pullback_zone_cny'][0])}—{format_cny(buy['pullback_zone_cny'][1])}，"
                f"止损 {format_cny(buy['stop_cny'])}，目标 {format_cny(buy['target1_cny'])} / "
                f"{format_cny(buy['target2_cny'])} 元/克\n"
                f"卖出：破位 {format_cny(sell['breakdown_entry_cny'])}，反抽 "
                f"{format_cny(sell['rebound_zone_cny'][0])}—{format_cny(sell['rebound_zone_cny'][1])}，"
                f"止损 {format_cny(sell['stop_cny'])}，目标 {format_cny(sell['target1_cny'])} / "
                f"{format_cny(sell['target2_cny'])} 元/克"
            )
        else:
            self.levels_var.set("行情不足，暂不计算买卖价位。")
        signal_type = snapshot.get("signal_type")
        color = GREEN if signal_type == "BUY" else RED if signal_type == "SELL" else AMBER
        self.risk_value_label.configure(fg=color)
        self.alerts_list.delete(0, tk.END)
        alerts = snapshot.get("alerts", [])
        if not alerts:
            self.alerts_list.insert(tk.END, "当前没有达到提醒阈值的风险")
        for alert in alerts:
            self.alerts_list.insert(
                tk.END,
                f"[{alert.get('severity')}] {alert.get('title')} — {alert.get('message')}",
            )
        for item in self.news_tree.get_children():
            self.news_tree.delete(item)
        for index, item in enumerate(snapshot.get("news", [])):
            sentiment = float(item.get("sentiment", 0))
            label = "利好" if sentiment > 0.1 else "利空" if sentiment < -0.1 else "中性"
            self.news_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    f"{float(item.get('importance', 0)):.0%}",
                    label,
                    item.get("source", "")[:20],
                    item.get("title", ""),
                ),
            )
        generated = snapshot.get("generated_at_china", "")
        self.status_var.set(
            f"{snapshot.get('market_status')} · {snapshot.get('news_summary')} · 更新 {generated}"
        )
        self._draw_chart()
        signature = str(snapshot.get("alert_signature", ""))
        if alerts and signature and signature != self.last_signature:
            self.last_signature = signature
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except (ImportError, RuntimeError):
                pass
            messagebox.showwarning(
                "GoldSentry 风险提醒",
                "\n\n".join(
                    f"[{alert.get('severity')}] {alert.get('title')}\n{alert.get('message')}"
                    for alert in alerts
                ),
            )

    def _draw_chart(self) -> None:
        self.canvas.delete("all")
        points = self.snapshot.get("chart_points", [])
        width = max(100, self.canvas.winfo_width())
        height = max(100, self.canvas.winfo_height())
        if len(points) < 2:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="暂无图表数据",
                fill=MUTED,
                font=("Microsoft YaHei UI", 10),
            )
            return
        prices = [float(point["price"]) for point in points]
        low, high = min(prices), max(prices)
        span = max(high - low, 0.01)
        margin = 18
        coords: list[float] = []
        for index, price in enumerate(prices):
            x = margin + index * (width - margin * 2) / (len(prices) - 1)
            y = margin + (high - price) * (height - margin * 2) / span
            coords.extend((x, y))
        color = GREEN if prices[-1] >= prices[0] else RED
        self.canvas.create_line(*coords, fill=color, width=2, smooth=True)
        self.canvas.create_text(
            10,
            8,
            text=f"{high:,.2f}",
            fill=MUTED,
            anchor="nw",
            font=("Segoe UI", 9),
        )
        self.canvas.create_text(
            10,
            height - 8,
            text=f"{low:,.2f}",
            fill=MUTED,
            anchor="sw",
            font=("Segoe UI", 9),
        )

    def _open_news(self, _event: tk.Event) -> None:
        selected = self.news_tree.selection()
        if not selected or not self.snapshot:
            return
        index = int(selected[0])
        news = self.snapshot.get("news", [])
        if 0 <= index < len(news):
            webbrowser.open(str(news[index].get("url", "")))


def run_gui() -> None:
    root = tk.Tk()
    GoldSentryApp(root)
    root.mainloop()

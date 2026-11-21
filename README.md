# GoldSentry 黄金风险哨兵

**线上看板：** https://weiqiumo-sketch.github.io/gold-risk-monitor/

GoldSentry 将黄金价格、成交量方向代理、美元指数、美国 10 年期收益率和相关新闻合并为一个风险评分。它支持：

- Windows 桌面监控，每 10 分钟自动刷新并弹窗提醒。
- GitHub Actions 定时运行，即使本机没有开机也能生成新快照。
- GitHub Pages 公开展示价格、风险、成交压力、宏观因子和重大新闻。
- 高风险时创建或更新标题为“GoldSentry 黄金风险提醒”的 GitHub Issue，用于手机通知。
- 休市或数据过期时明确标记，不把旧行情当成实时买卖信号。
- 同时给出买入/做多的突破位、回踩区、止损位、目标位，以及卖出/做空的破位位、反抽区、止损位和目标位。

## 信号含义

综合评分范围为 `-1` 到 `+1`：

- `+1`：价格、买盘压力、新闻和宏观因素都偏多。
- `-1`：价格、卖盘压力、新闻和宏观因素都偏空。
- 接近 `0`：信号分化，等待确认。

“大量买入”和“大量抛售”使用 5 分钟 K 线方向、实体强度与成交量构建方向成交量代理。提醒需要同时满足：

1. 最近 15 分钟成交量至少达到近期基准的 `1.45` 倍。
2. 买盘或卖盘方向成交差至少为 `22%`。
3. 最近 15 分钟价格方向与成交量方向一致。
4. 综合评分达到相应方向阈值。

普通免费行情源没有逐笔主动成交和盘口数据，因此这不是交易所认证的“主动买/主动卖”指标。

## 买卖点计算

程序始终提供两套条件计划：

- 买入计划：突破最近约 2 小时结构高点后确认，或等待价格回踩买入区。
- 卖出计划：跌破最近约 2 小时结构低点后确认，或等待价格反抽卖出区。

价位使用最近 14 根 5 分钟 K 线的 ATR 作为波动缓冲。止损放在结构位外侧，第一目标为 `1.5R`，第二目标为 `2.5R`。当前价格进入突破、回踩、破位或反抽区域时，对应计划会高亮并显示状态。

这些价格是条件提醒，不保证成交。休市或行情超过 30 分钟未更新时，所有价位会标记为“下一交易时段复评”。

## 新闻评分

程序同时尝试 Google News、Bing News、Yahoo Finance、Investing.com 和 GDELT，并进行：

- 黄金相关性过滤
- 多来源标题去重
- 时效和来源级别加权
- 加息、降息、美元、收益率、避险、抛售、强制平仓等方向词评分
- 重大事件覆盖度和冲击度评分

新闻列表按重要度排序。完整正文不在免费 RSS 中，因此重大消息必须打开链接核对原文。

## 本地运行

双击 `run.bat` 启动 Windows 图形界面。

命令行运行一次：

```bat
run_console.bat
```

使用确定性的买卖盘演示数据：

```bat
python app.py --demo buy
python app.py --demo sell
```

运行测试：

```bat
python -m unittest discover -s tests -v
```

运行一次并更新网页快照：

```bat
python app.py --update-web site/data/latest.json
```

程序只使用 Python 标准库，需要 Python 3.11 或更高版本。

## GitHub 部署

仓库内的 `.github/workflows/monitor.yml` 每 10 分钟执行一次：

1. 运行测试。
2. 抓取行情和新闻。
3. 更新 `site/data/latest.json`。
4. 达到阈值时创建或更新 `gold-risk` Issue。
5. 发布 `site/` 到 GitHub Pages。

首次部署需要在仓库的 `Settings > Pages` 中将 Source 设置为 `GitHub Actions`。之后可以在 `Actions > Gold risk monitor and Pages > Run workflow` 手动触发。

GitHub Actions 的定时任务可能因平台负载延迟数分钟。仓库连续 60 天无活动时，GitHub 也可能自动暂停公开仓库的定时工作流；此时手动运行一次或提交一次更新即可恢复。

如需接收 Issue 通知，请在 GitHub 的 Watch 设置中选择 All Activity，或在手机 GitHub App 中开启对应通知。

## 配置

`config.json` 可调整：

```json
{
  "symbol": "GC=F",
  "news_limit": 60,
  "desktop_refresh_minutes": 10,
  "stale_after_minutes": 30
}
```

`GC=F` 是 COMEX 黄金期货。不同平台的现货黄金价格会因交易时段、点差和合约月份而略有差异。

## 风险和限制

- 没有接入逐笔成交、盘口深度、ETF 申赎和期权数据。
- 新闻标题情绪无法理解所有反讽、条件和复杂因果。
- 数据源可能在休市、限流或网络故障时暂时不可用。
- GitHub Actions 不是毫秒级交易系统。
- 本工具用于风险监控和研究，不构成投资建议，也不会自动下单。

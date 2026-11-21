const $ = (selector) => document.querySelector(selector);

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

function formatNumber(value, digits = 2) {
  return Number.isFinite(Number(value))
    ? Number(value).toLocaleString("zh-CN", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
    : "--";
}

function formatPercent(value, digits = 2, signed = true) {
  if (!Number.isFinite(Number(value))) return "--";
  const numeric = Number(value) * 100;
  const sign = signed && numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(digits)}%`;
}

function setTone(element, value) {
  element.classList.remove("positive", "negative", "neutral");
  element.classList.add(value > 0.0001 ? "positive" : value < -0.0001 ? "negative" : "neutral");
}

function setText(selector, text) {
  const element = $(selector);
  if (element) element.textContent = text;
}

function ageMinutes(isoTime) {
  const timestamp = Date.parse(isoTime);
  return Number.isFinite(timestamp) ? Math.max(0, (Date.now() - timestamp) / 60000) : Infinity;
}

function renderAlerts(alerts) {
  const host = $("#alerts");
  host.replaceChildren();
  if (!alerts || alerts.length === 0) {
    const empty = document.createElement("article");
    empty.className = "alert";
    const content = document.createElement("div");
    const title = document.createElement("strong");
    const message = document.createElement("p");
    title.textContent = "当前没有达到阈值的风险";
    message.textContent = "成交量、价格与新闻信号尚未形成一致冲击。";
    content.append(title, message);
    empty.append(content);
    host.append(empty);
    return;
  }
  for (const alert of alerts) {
    const card = document.createElement("article");
    card.className = `alert ${String(alert.type || "").toLowerCase()}`;
    const content = document.createElement("div");
    const title = document.createElement("strong");
    const message = document.createElement("p");
    title.textContent = `[${alert.severity || "提示"}] ${alert.title || "风险提醒"}`;
    message.textContent = alert.message || "";
    content.append(title, message);
    card.append(content);
    host.append(card);
  }
}

function renderChart(points) {
  const host = $("#chart");
  host.replaceChildren();
  if (!Array.isArray(points) || points.length < 2) {
    const empty = document.createElement("div");
    empty.className = "empty-chart";
    empty.textContent = "暂无价格曲线";
    host.append(empty);
    return;
  }
  const width = 1000;
  const height = 320;
  const padX = 16;
  const padY = 22;
  const prices = points.map((item) => Number(item.price)).filter(Number.isFinite);
  const minimum = Math.min(...prices);
  const maximum = Math.max(...prices);
  const span = Math.max(maximum - minimum, 0.01);
  const coordinates = prices.map((price, index) => {
    const x = padX + index * (width - padX * 2) / (prices.length - 1);
    const y = padY + (maximum - price) * (height - padY * 2) / span;
    return [x, y];
  });
  const line = coordinates.map((point) => point.join(",")).join(" ");
  const area = `${padX},${height - padY} ${line} ${width - padX},${height - padY}`;
  const color = prices.at(-1) >= prices[0] ? "#44d7a4" : "#ff7186";
  const gradientId = `chart-gradient-${Date.now()}`;
  host.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity=".25"></stop>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"></stop>
        </linearGradient>
      </defs>
      <polygon points="${area}" fill="url(#${gradientId})"></polygon>
      <polyline points="${line}" fill="none" stroke="${color}" stroke-width="3"
        vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
    <span class="chart-max">${formatNumber(maximum)}</span>
    <span class="chart-min">${formatNumber(minimum)}</span>
    <span class="chart-last">${formatNumber(prices.at(-1))}</span>
  `;
}

function renderMacro(points) {
  const host = $("#macro-list");
  host.replaceChildren();
  if (!Array.isArray(points) || points.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "宏观数据暂不可用";
    host.append(empty);
    return;
  }
  for (const point of points) {
    const row = document.createElement("div");
    row.className = "macro-item";
    const name = document.createElement("strong");
    const value = document.createElement("b");
    const detail = document.createElement("small");
    name.textContent = point.label;
    value.textContent = Number(point.value).toFixed(point.key === "^TNX" ? 3 : 2);
    detail.textContent = `${point.change_label || ""} · ${point.bias || ""}`;
    row.append(name, value, detail);
    host.append(row);
  }
}

function renderReasons(reasons) {
  const host = $("#reasons");
  host.replaceChildren();
  for (const reason of reasons || []) {
    const item = document.createElement("li");
    item.textContent = reason;
    host.append(item);
  }
  if (!host.children.length) {
    const item = document.createElement("li");
    item.textContent = "当前没有可解释的判断依据。";
    host.append(item);
  }
}

function renderNews(news) {
  const host = $("#news-list");
  host.replaceChildren();
  if (!Array.isArray(news) || news.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "最近 24 小时没有获取到相关新闻";
    host.append(empty);
    return;
  }
  for (const item of news.slice(0, 14)) {
    const anchor = document.createElement("a");
    anchor.className = "news-item";
    anchor.href = item.url || "#";
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    const sentiment = Number(item.sentiment || 0);
    const mark = document.createElement("span");
    mark.className = `sentiment-mark ${sentiment > 0.1 ? "up" : sentiment < -0.1 ? "down" : ""}`;
    mark.textContent = sentiment > 0.1 ? "利好" : sentiment < -0.1 ? "利空" : "中性";
    const body = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = item.title;
    const meta = document.createElement("div");
    meta.className = "news-meta";
    const source = document.createElement("span");
    source.textContent = item.source || "未知来源";
    const importance = document.createElement("span");
    importance.textContent = `重要度 ${Math.round(Number(item.importance || 0) * 100)}%`;
    const when = document.createElement("span");
    when.textContent = item.published_at ? dateFormatter.format(new Date(item.published_at)) : "时间未知";
    meta.append(source, importance, when);
    body.append(title, meta);
    anchor.append(mark, body);
    host.append(anchor);
  }
}

function render(snapshot) {
  const price = Number(snapshot.price);
  const change = Number(snapshot.price_change_pct || 0) / 100;
  setText("#price", Number.isFinite(price) ? `$${formatNumber(price)}` : "--");
  setText("#price-change", formatPercent(change));
  setTone($("#price-change"), change);
  setText("#decision", snapshot.decision || "观望");
  setText("#action-text", snapshot.action_text || "");
  const composite = Number(snapshot.composite_score || 0);
  setText("#composite-score", `${composite > 0 ? "+" : ""}${composite.toFixed(2)}`);
  const scoreBar = $("#score-bar");
  scoreBar.style.width = `${Math.abs(composite) * 50}%`;
  scoreBar.style.left = composite >= 0 ? "50%" : `${50 - Math.abs(composite) * 50}%`;
  scoreBar.style.background = composite >= 0 ? "var(--green)" : "var(--red)";

  const risk = Number(snapshot.risk_score || 0);
  setText("#risk-score", risk.toFixed(0));
  $("#risk-ring").style.setProperty("--risk", `${Math.max(0, Math.min(100, risk))}%`);
  $("#risk-ring").style.setProperty("--amber", risk >= 70 ? "#ff7186" : risk >= 40 ? "#f5c35d" : "#44d7a4");

  const flow = Number(snapshot.signed_volume_ratio || 0);
  setText("#flow-ratio", `${flow > 0 ? "+" : ""}${(flow * 100).toFixed(0)}%`);
  setTone($("#flow-ratio"), flow);
  setText("#flow-caption", `15 分钟成交量为基准的 ${Number(snapshot.volume_ratio || 0).toFixed(2)} 倍`);
  const buyShare = Math.max(0, Math.min(1, (flow + 1) / 2));
  $("#buy-flow").style.width = `${buyShare * 100}%`;
  $("#sell-flow").style.width = `${(1 - buyShare) * 100}%`;

  setText("#confidence", `${Number(snapshot.confidence || 0).toFixed(0)}%`);
  setText("#day-high", formatNumber(snapshot.day_high));
  setText("#day-low", formatNumber(snapshot.day_low));
  const return15 = Number(snapshot.return_15m || 0);
  const return1h = Number(snapshot.return_1h || 0);
  setText("#return-15m", formatPercent(return15));
  setText("#return-1h", formatPercent(return1h));
  setTone($("#return-15m"), return15);
  setTone($("#return-1h"), return1h);
  setText("#volume-ratio", `${Number(snapshot.volume_ratio || 0).toFixed(2)}×`);
  setText("#news-impact", `${Math.round(Number(snapshot.news_impact || 0) * 100)}/100`);
  setText("#news-summary", snapshot.news_summary || "新闻中性");
  const macroScore = Number(snapshot.macro_score || 0);
  setText("#macro-score", `${macroScore > 0 ? "+" : ""}${macroScore.toFixed(2)}`);
  setTone($("#macro-score"), macroScore);

  renderAlerts(snapshot.alerts);
  renderChart(snapshot.chart_points);
  renderMacro(snapshot.macro_points);
  renderReasons(snapshot.reasons);
  renderNews(snapshot.news);

  const generatedAge = ageMinutes(snapshot.generated_at);
  const marketAge = Number(snapshot.data_age_minutes);
  const isFresh = snapshot.market_status === "交易中" && marketAge < 30;
  const market = $("#market-status");
  market.className = `pill ${isFresh ? "live" : "stale"}`;
  market.textContent = isFresh ? snapshot.market_status : "休市 / 数据延迟";
  const generatedText = snapshot.generated_at_china
    ? dateFormatter.format(new Date(snapshot.generated_at_china))
    : "时间未知";
  setText("#last-updated", `分析更新 ${generatedText} · 快照 ${generatedAge.toFixed(0)} 分钟前`);
  if (generatedAge > 30) {
    $("#last-updated").textContent += " · 请谨慎使用";
  }
  $("#sources").textContent = `数据状态：${(snapshot.source_status || []).join("；")}`;
}

function renderError(error) {
  $("#market-status").className = "pill error";
  $("#market-status").textContent = "数据加载失败";
  const host = $("#alerts");
  host.replaceChildren();
  const card = document.createElement("article");
  card.className = "alert risk";
  const content = document.createElement("div");
  const title = document.createElement("strong");
  const message = document.createElement("p");
  title.textContent = "无法读取风险快照";
  message.textContent = String(error);
  content.append(title, message);
  card.append(content);
  host.append(card);
}

async function loadSnapshot() {
  try {
    const response = await fetch(`data/latest.json?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    renderError(error.message || error);
  }
}

loadSnapshot();
setInterval(loadSnapshot, 60_000);

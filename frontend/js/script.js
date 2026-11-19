/* ChainResQ UI - talks to /api/scenarios, /api/analyze, /api/data/{name} */
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => "$" + Math.round(n || 0).toLocaleString();
const num = (n) => Math.round(n || 0).toLocaleString();

const AGENTS = [
  { key: "DisruptionAnalyst", name: "Disruption analyst", job: "Classifies the event" },
  { key: "ImpactAssessor", name: "Impact assessor", job: "Sizes stock-out and order risk" },
  { key: "SourcingAgent", name: "Sourcing", job: "Finds backup suppliers" },
  { key: "LogisticsOptimizer", name: "Logistics", job: "Reroutes shipments" },
  { key: "StrategyAgent", name: "Strategy", job: "Compares recovery plans" },
  { key: "ReportAgent", name: "Report", job: "Writes the action plan" },
];
const KIND = {
  supplier_failure: { label: "Supplier failure", color: "#E5675C" },
  shipment_delay: { label: "Shipment delay", color: "#E8A200" },
  inventory_shortage: { label: "Demand surge", color: "#6FB3C8" },
};

let scenarios = [], current = 0, last = null, timer = null;

/* ---------------------------------------------------------------- init */
async function init() {
  document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => switchView(b.dataset.view)));
  $("run").onclick = run;
  $("copy").onclick = copyReport;
  $("download").onclick = downloadReport;
  renderPipeline();
  try {
    const h = await (await fetch("/api/health")).json();
    $("apiDot").className = "dot ok";
    $("apiText").textContent = "API online" + (h.langgraph ? " - LangGraph" : "");
  } catch { $("apiDot").className = "dot bad"; $("apiText").textContent = "API unreachable"; }
  try { scenarios = await (await fetch("/api/scenarios")).json(); renderQueue(); selectScenario(0); }
  catch (e) { showNotice("error", "Could not load incidents", [String(e.message || e)]); }
}

function switchView(v) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("is-active", b.dataset.view === v));
  $("view-incident").hidden = v !== "incident";
  $("view-data").hidden = v !== "data";
  if (v === "data" && !$("dataTable").dataset.loaded) loadData("suppliers");
}

/* ---------------------------------------------------------------- queue */
function parts(label) { const i = label.indexOf(" - "); return i < 0 ? [label, ""] : [label.slice(0, i), label.slice(i + 3)]; }
function renderQueue() {
  $("queue").innerHTML = scenarios.map((s, i) => {
    const [kind, detail] = parts(s.label);
    const k = KIND[s.payload.type] || { color: "#8FA6B0" };
    return `<li><button class="q-item" data-i="${i}" style="--k:${k.color}"><b>${esc(kind)}</b><small>${esc(detail)}</small></button></li>`;
  }).join("");
  document.querySelectorAll(".q-item").forEach((b) => (b.onclick = () => selectScenario(+b.dataset.i)));
}
function selectScenario(i) {
  current = i;
  document.querySelectorAll(".q-item").forEach((b) => b.classList.toggle("is-active", +b.dataset.i === i));
  const [kind, detail] = parts(scenarios[i].label);
  $("incTitle").textContent = kind;
  $("incSub").textContent = detail;
  $("results").hidden = true; $("empty").hidden = false; $("notice").innerHTML = "";
  renderPipeline();
}

/* ---------------------------------------------------------------- pipeline */
function renderPipeline(state = {}) {
  $("pipeline").innerHTML = AGENTS.map((a, i) => {
    const cls = state[a.key]?.status ? " is-" + state[a.key].status : "";
    return `<li class="step${cls}"><div class="n"><i></i>Agent ${i + 1}</div><strong>${a.name}</strong><span class="job">${a.job}</span></li>`;
  }).join("");
}
function startAnimation() {
  let idx = 0; const st = {};
  const tick = () => {
    AGENTS.forEach((a, i) => (st[a.key] = { status: i < idx ? "done" : i === idx ? "active" : "" }));
    renderPipeline(st);
    if (idx < AGENTS.length - 1) idx++;
  };
  tick(); timer = setInterval(tick, 500);
}
function stopAnimation() { clearInterval(timer); timer = null; }
function finalPipeline(trace) {
  const seen = new Set((trace || []).map((t) => (t.match(/^\[(\w+)\]/) || [])[1]));
  const st = {}; AGENTS.forEach((a) => (st[a.key] = { status: seen.has(a.key) ? "done" : "skipped" }));
  renderPipeline(st);
}

/* ---------------------------------------------------------------- run */
async function run() {
  $("run").disabled = true; $("run").textContent = "Analysing...";
  $("notice").innerHTML = ""; startAnimation();
  const started = Date.now();
  try {
    const res = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scenarios[current].payload) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    const wait = Math.max(0, 1800 - (Date.now() - started));   // let the pipeline be seen on fast runs
    await new Promise((r) => setTimeout(r, wait));
    last = data; stopAnimation(); finalPipeline(data.trace); render(data);
  } catch (e) {
    stopAnimation(); renderPipeline();
    showNotice("error", "Analysis failed", [String(e.message || e), "Check that the API is running: uvicorn backend.api:app --reload"]);
  }
  $("run").disabled = false; $("run").textContent = "Run analysis again";
}
function showNotice(kind, title, lines) {
  $("notice").innerHTML = `<div class="notice ${kind === "error" ? "error" : ""}"><strong>${esc(title)}</strong>${lines.length ? "<ul>" + lines.map((l) => `<li>${esc(l)}</li>`).join("") + "</ul>" : ""}</div>`;
}

/* ---------------------------------------------------------------- render */
function render(d) {
  const imp = d.impact, rec = d.recommendation;
  $("empty").hidden = true;
  if (d.abort || !imp || !rec) {
    $("results").hidden = true;
    const stopped = (d.warnings || []).length ? d.warnings : ["The workflow ended early with no action needed."];
    showNotice("error", d.abort && !imp ? "Input rejected - no plan generated" : "Workflow stopped early", stopped);
    return;
  }
  $("results").hidden = false;
  if ((d.warnings || []).length) showNotice("warn", "Assumptions and data gaps", d.warnings);

  $("reco").innerHTML = `
    <div>
      <h2>Recommended plan</h2>
      <div class="name">${esc(rec.name)}</div>
      <p class="desc">${esc(rec.description)}</p>
      <ul>${rec.actions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
    </div>
    <div class="reco-stats">
      <div><b>${money(rec.est_cost)}</b><span>Total cost</span></div>
      <div><b>${money(rec.premium_cost)}</b><span>Premium over normal</span></div>
      <div><b>${rec.recovery_days}<small> days</small></b><span>To first delivery</span></div>
      <div><b>${rec.orders_protected_pct}%</b><span>At-risk orders protected</span></div>
    </div>`;

  $("kpis").innerHTML = [
    ["Risk level", `<span class="risk-${imp.risk_level}">${esc(imp.risk_level[0] + imp.risk_level.slice(1).toLowerCase())}</span>`],
    ["Stock runs out in", `${imp.stockout_days}<small>days</small>`],
    ["Shortfall", `${num(imp.shortfall_qty)}<small>units</small>`],
    ["Units to recover", `${num(imp.recovery_qty)}<small>units</small>`],
    ["Orders at risk", `${imp.orders_at_risk.length}`],
    ["Inbound lost or late", `${num(imp.inbound_lost)}<small>units</small>`],
  ].map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`).join("");

  drawChart(imp, rec);
  renderOrders(imp, rec);
  renderStrategies(d.strategies);
  $("report").textContent = d.report || "";
  $("trace").innerHTML = (d.trace || []).map((t) => {
    const m = t.match(/^\[(\w+)\]\s*(.*)$/); const a = AGENTS.find((x) => x.key === (m && m[1]));
    return `<li><b>${esc(a ? a.name : m ? m[1] : "Agent")}</b>${esc(m ? m[2] : t)}</li>`;
  }).join("");
  $("results").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

/* supply vs demand (cumulative units over the 30-day planning horizon) */
function drawChart(imp, rec) {
  const W = 640, H = 300, L = 54, R = 14, T = 14, B = 34, DAYS = 30;
  const added = rec.supply_added || 0, base = imp.supply_base, dem = imp.demand_horizon;
  const maxY = Math.max(dem, base + added) * 1.08 || 1;
  const x = (d) => L + (d / DAYS) * (W - L - R), y = (v) => T + (1 - v / maxY) * (H - T - B);
  const k = (v) => (v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + "k" : Math.round(v));
  const so = imp.stockout_days, rd = Math.min(rec.recovery_days, DAYS);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative demand against available supply over 30 days">`;
  for (let i = 0; i <= 4; i++) { const v = (maxY / 4) * i; svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#E8ECED"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${k(v)}</text>`; }
  for (let d = 0; d <= DAYS; d += 5) svg += `<text x="${x(d)}" y="${H - 12}" text-anchor="middle">${d}</text>`;
  svg += `<text x="${(L + W - R) / 2}" y="${H - 0}" text-anchor="middle">Days from today</text>`;
  if (so < DAYS) {   // shortage area
    const yd = (d) => dem * (d / DAYS);
    svg += `<polygon points="${x(so)},${y(base)} ${x(DAYS)},${y(base)} ${x(DAYS)},${y(dem)}" fill="#FBE6E3" stroke="#E8B4AE" stroke-width="1"/>`;
    svg += `<line x1="${x(so)}" x2="${x(so)}" y1="${T}" y2="${H - B}" stroke="#C2362B" stroke-dasharray="4 4"/><text x="${x(so) - 6}" y="${T + 12}" text-anchor="end" fill="#C2362B" style="fill:#C2362B;font-weight:600">Stock-out, day ${so}</text>`;
  }
  svg += `<line x1="${x(0)}" y1="${y(0)}" x2="${x(DAYS)}" y2="${y(dem)}" stroke="#13222B" stroke-width="2.5"/>`;
  svg += `<line x1="${x(0)}" y1="${y(base)}" x2="${x(DAYS)}" y2="${y(base)}" stroke="#1D4F5E" stroke-width="2.5"/>`;
  if (added > 0) svg += `<polyline points="${x(0)},${y(base)} ${x(rd)},${y(base)} ${x(rd)},${y(base + added)} ${x(DAYS)},${y(base + added)}" fill="none" stroke="#E8A200" stroke-width="3" stroke-dasharray="7 5"/>`;
  svg += `</svg>`;
  $("chart").innerHTML = svg;
  $("legend").innerHTML = `
    <li><i style="--c:#13222B"></i>Cumulative demand</li>
    <li><i style="--c:#1D4F5E"></i>Stock plus shipments still arriving</li>
    ${added > 0 ? `<li><i class="dash" style="--c:#E8A200"></i>With ${esc(rec.name)}</li>` : ""}
    ${so < DAYS ? `<li><i class="area"></i>Unmet demand</li>` : ""}`;
}

function renderOrders(imp, rec) {
  if (!imp.orders_at_risk.length) { $("orders").innerHTML = `<p class="muted">No customer orders are at risk.</p>`; return; }
  const safe = new Set(rec.orders_protected || []);
  $("orders").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Order</th><th class="num">Units</th><th class="num">Due</th><th>Priority</th><th>With this plan</th></tr></thead><tbody>` +
    imp.orders_at_risk.map((o) => `<tr><td><b>${esc(o.order_id)}</b><br><span class="muted small">${esc(o.customer)}</span></td><td class="num">${num(o.qty)}</td><td class="num">${o.due_in_days}d</td>
      <td><span class="pill ${esc(o.priority)}">${esc(o.priority)}</span></td>
      <td><span class="pill ${safe.has(o.order_id) ? "ok" : "bad"}">${safe.has(o.order_id) ? "Protected" : "Notify customer"}</span></td></tr>`).join("") +
    `</tbody></table></div>`;
}

function renderStrategies(list) {
  const bar = (p) => `<span class="bar"><i class="${p >= 80 ? "" : p >= 40 ? "mid" : "low"}" style="width:${p}%"></i></span>${p}%`;
  $("strategies").innerHTML = `<table><thead><tr><th>Strategy</th><th class="num">Cost</th><th class="num">First delivery</th><th>Supply cover</th><th>Orders protected</th><th class="num">Score</th></tr></thead><tbody>` +
    list.map((s, i) => `
      <tr class="row ${s.recommended ? "is-rec" : ""}" data-i="${i}" tabindex="0" aria-expanded="false">
        <td><b>${esc(s.name)}</b>${s.recommended ? '<span class="pill rec">Recommended</span>' : ""}<br><span class="muted small">${esc(s.description)}</span></td>
        <td class="num">${money(s.est_cost)}</td><td class="num">${s.recovery_days ? s.recovery_days + " days" : "Immediate"}</td>
        <td>${bar(s.fulfilment_pct)}</td><td>${bar(s.orders_protected_pct)}</td><td class="num"><b>${s.score}</b></td></tr>
      <tr class="detail" id="d${i}" hidden><td colspan="6"><ul>${s.actions.map((a) => `<li>${esc(a)}</li>`).join("") || "<li>No actions</li>"}</ul></td></tr>`).join("") +
    `</tbody></table>`;
  document.querySelectorAll("#strategies tr.row").forEach((r) => {
    const toggle = () => { const d = $("d" + r.dataset.i); d.hidden = !d.hidden; r.setAttribute("aria-expanded", String(!d.hidden)); };
    r.onclick = toggle; r.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
  });
}

/* ---------------------------------------------------------------- report actions */
async function copyReport() {
  try { await navigator.clipboard.writeText(last?.report || ""); flash($("copy"), "Copied"); } catch { flash($("copy"), "Copy failed"); }
}
function downloadReport() {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([last?.report || ""], { type: "text/plain" }));
  a.download = "chainresq-action-plan.txt"; a.click(); URL.revokeObjectURL(a.href);
}
function flash(btn, text) { const o = btn.textContent; btn.textContent = text; setTimeout(() => (btn.textContent = o), 1400); }

/* ---------------------------------------------------------------- network data */
const DATASETS = [["suppliers", "Suppliers"], ["inventory", "Inventory"], ["shipments", "Shipments"], ["orders", "Orders"]];
async function loadData(name) {
  $("dataTabs").innerHTML = DATASETS.map(([k, l]) => `<button class="subtab ${k === name ? "is-active" : ""}" data-k="${k}">${l}</button>`).join("");
  document.querySelectorAll(".subtab").forEach((b) => (b.onclick = () => loadData(b.dataset.k)));
  try {
    const rows = await (await fetch("/api/data/" + name)).json();
    const cols = Object.keys(rows[0] || {});
    const cell = (c, v) => (["status", "priority"].includes(c) ? `<span class="pill ${esc(String(v).replace(" ", "-"))}">${esc(v)}</span>` : typeof v === "number" ? `<span>${v.toLocaleString()}</span>` : esc(v));
    $("dataTable").innerHTML = `<table><thead><tr>${cols.map((c) => `<th class="${typeof rows[0][c] === "number" ? "num" : ""}">${esc(c.replace(/_/g, " "))}</th>`).join("")}</tr></thead><tbody>` +
      rows.map((r) => `<tr>${cols.map((c) => `<td class="${typeof r[c] === "number" ? "num" : ""}">${cell(c, r[c])}</td>`).join("")}</tr>`).join("") + `</tbody></table>`;
    $("dataTable").dataset.loaded = "1";
  } catch (e) { $("dataTable").innerHTML = `<p class="muted" style="padding:14px">Could not load ${esc(name)}: ${esc(e.message)}</p>`; }
}

init();

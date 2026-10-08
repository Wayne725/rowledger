"use strict";
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="rowledger-session"]').content;
const state = {batch: null, page: 1, selected: {}, focused: null, busy: false, request: 0};
const labels = {matched: "自動配對", manual_matched: "人工配對", unmatched: "未配對", invalid: "資料無效", duplicate_key: "編號重複", blocked_invalid: "對方無效", amount_mismatch: "金額不同", currency_mismatch: "幣別不同"};
const actions = {created: "建立批次", review_saved: "保存確認", closed: "關閉批次", reopened: "重新開啟"};
function node(tag, text, className) { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (className) element.className = className; return element; }
function date(value) { return new Date(value).toLocaleString("zh-TW", {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"}); }
let noticeTimer;
function notice(message, error = false) { clearTimeout(noticeTimer); $("notice").textContent = message; $("notice").className = `notice${error ? " error" : ""}`; $("notice").hidden = false; noticeTimer = setTimeout(() => { $("notice").hidden = true; }, 7000); }
async function api(path, payload) {
  const response = await fetch(path, {method: payload === undefined ? "GET" : "POST", headers: {"X-RowLedger-Token": token, ...(payload === undefined ? {} : {"Content-Type": "application/json"})}, ...(payload === undefined ? {} : {body: JSON.stringify(payload)})});
  if (!response.ok) { const problem = await response.json(); const error = new Error(problem.error || "操作失敗。"); error.status = response.status; throw error; }
  return response.headers.get("Content-Type").startsWith("application/zip") ? response.blob() : response.json();
}
async function perform(operation) {
  if (state.busy) return;
  state.busy = true;
  document.body.setAttribute("aria-busy", "true");
  try { await operation(); }
  catch (error) { notice(error.status === 409 ? "批次已有變更，已重新載入。請確認最新資料再操作。" : error.message, true); if (error.status === 409 && state.batch) { state.selected = {}; await loadBatch(state.batch.id); } }
  finally { state.busy = false; document.body.removeAttribute("aria-busy"); }
}
async function refreshList() {
  const result = await api("/api/batches");
  $("batch-list").replaceChildren();
  if (!result.batches.length) $("batch-list").append(node("p", "還沒有對帳批次", "empty"));
  for (const batch of result.batches) {
    const button = node("button", undefined, `batch-item${state.batch?.id === batch.id ? " active" : ""}`);
    button.append(node("strong", batch.title), node("span", `${date(batch.updated)} / ${batch.state === "closed" ? "已關閉" : `${batch.summary.needs_attention} 列待確認`}`));
    button.addEventListener("click", () => perform(async () => { state.page = 1; state.selected = {}; state.focused = null; await loadBatch(batch.id); await refreshList(); }));
    $("batch-list").append(button);
  }
  return result.batches;
}
async function loadBatch(id) {
  const request = ++state.request;
  const params = new URLSearchParams({page: String(state.page), q: $("search").value, status: $("status").value, side: $("side").value});
  const batch = await api(`/api/batches/${id}?${params}`);
  if (request !== state.request) return;
  if (state.batch?.id !== batch.id || state.batch?.revision !== batch.revision) { state.selected = {}; state.focused = null; }
  state.batch = batch;
  $("welcome").hidden = true; $("workspace").hidden = false;
  $("batch-title").textContent = batch.title;
  $("batch-date").textContent = `建立 ${date(batch.created)} / 版本 ${batch.revision}`;
  $("batch-state").textContent = batch.state === "closed" ? "已關閉" : "處理中";
  $("batch-state").className = `tag${batch.state === "open" ? " green" : ""}`;
  const metrics = [["來源資料", batch.summary.rows, "每列保留原始來源"], ["已配對", batch.summary.matched_pairs, "訂單與收款配對數"], ["需要確認", batch.summary.needs_attention, "尚未配對或資料有差異"], ["人工確認", batch.decisions.length, "已保存的人工配對"]];
  $("metrics").replaceChildren(...metrics.map(([title, value, detail]) => { const element = node("div", undefined, "metric"); element.append(node("span", title), node("strong", String(value)), node("small", detail)); return element; }));
  renderRows(); renderHistory(); renderSelection();
  $("toggle-state").textContent = batch.state === "closed" ? "重新開啟批次" : "關閉批次";
  $("attention-ack").hidden = batch.state === "closed" || !batch.summary.needs_attention;
  $("acknowledge").checked = false;
}
function renderRows() {
  const batch = state.batch;
  $("rows").replaceChildren();
  for (const row of batch.rows) {
    const tr = node("tr");
    if (state.focused?.row_id === row.row_id) tr.className = "selected";
    const source = node("td"); source.append(node("strong", row.key || "（缺少編號）"), node("small", `${row.side === "orders" ? "訂單" : "收款"} / ${row.location}`));
    const amount = node("td", `${row.currency} ${row.amount}`, "amount");
    const status = node("td"); status.append(node("span", labels[row.status], `tag ${row.status.includes("matched") && row.status !== "unmatched" ? "green" : row.status === "invalid" ? "red" : "yellow"}`));
    const controls = node("td"); const buttons = node("div", undefined, "row-actions");
    const view = node("button", "查看", "secondary"); view.addEventListener("click", () => { state.focused = row; renderRows(); renderSelection(); }); buttons.append(view);
    if (!row.errors.length && !["matched", "manual_matched"].includes(row.status) && batch.state === "open") {
      const select = node("button", state.selected[row.side]?.row_id === row.row_id ? "已選取" : "選取", "secondary");
      select.addEventListener("click", () => { state.selected[row.side] = state.selected[row.side]?.row_id === row.row_id ? null : row; state.focused = row; renderRows(); renderSelection(); }); buttons.append(select);
    }
    controls.append(buttons); tr.append(source, amount, status, controls); $("rows").append(tr);
  }
  $("no-rows").hidden = batch.rows.length > 0;
  $("row-count").textContent = `${batch.total} 列符合篩選`;
  $("page-number").textContent = `${batch.page} / ${batch.pages}`;
  $("previous").disabled = batch.page <= 1;
  $("next").disabled = batch.page >= batch.pages;
}
function renderSelection() {
  $("selected-order").textContent = state.selected.orders ? `${state.selected.orders.key} / ${state.selected.orders.amount}` : "尚未選取";
  $("selected-payment").textContent = state.selected.payments ? `${state.selected.payments.key} / ${state.selected.payments.amount}` : "尚未選取";
  $("save-pair").disabled = !state.selected.orders || !state.selected.payments || state.batch.state !== "open";
  $("undo-pair").hidden = state.focused?.status !== "manual_matched" || state.batch.state !== "open";
  const target = $("source-detail"); target.replaceChildren();
  if (!state.focused) { target.append(node("p", "點選一列，查看原始值與判定依據。", "muted")); return; }
  const row = state.focused;
  target.append(node("h3", row.key || "（缺少編號）"), node("p", `${row.source} / ${row.sheet ? `${row.sheet} / ` : ""}${row.location}`, "muted"), node("p", row.explanation));
  const raw = node("div", undefined, "raw-list");
  for (const [key, value] of Object.entries(row.raw)) { const item = node("div", undefined, "raw-item"); item.append(node("span", key), node("strong", value)); raw.append(item); }
  target.append(raw);
  if (row.review) target.append(node("p", `${row.review.reviewer}：${row.review.reason}`));
}
function renderHistory() {
  $("events").replaceChildren(...state.batch.events.map(event => { const item = node("div", undefined, "event"); item.append(node("time", date(event.at)), node("span", `${actions[event.action]} / ${event.revision}`, "event-action"), node("span", event.actor), node("span", event.note)); return item; }));
}
function reviewIdentity() {
  if (!$("review-form").reportValidity()) return null;
  const actor = $("reviewer").value.trim(), note = $("reason").value.trim();
  if (!actor || !note) { notice("請填寫確認人與原因。", true); return null; }
  return {actor, note};
}
async function saveDecisions(decisions, identity) {
  const id = state.batch.id;
  await api(`/api/batches/${id}/review`, {revision: state.batch.revision, document: {schema_version: 1, run_id: state.batch.snapshot, decisions}, ...identity});
  state.selected = {}; state.focused = null; $("reason").value = "";
  await loadBatch(id); await refreshList(); notice("確認已保存，關閉視窗後仍會保留。");
}
$("save-pair").addEventListener("click", () => perform(async () => {
  const identity = reviewIdentity(); if (!identity) return;
  const order = state.selected.orders, payment = state.selected.payments;
  if (!order || !payment) return;
  if (order.currency !== payment.currency || order.amount_minor !== payment.amount_minor) { notice("兩筆資料的幣別與金額需完全相同。", true); return; }
  await saveDecisions([...state.batch.decisions, {order_row_id: order.row_id, payment_row_id: payment.row_id, reviewer: identity.actor, reason: identity.note}], identity);
}));
$("undo-pair").addEventListener("click", () => perform(async () => {
  const identity = reviewIdentity(); if (!identity || !state.focused) return;
  await saveDecisions(state.batch.decisions.filter(item => item.order_row_id !== state.focused.row_id && item.payment_row_id !== state.focused.row_id), identity);
}));
$("toggle-state").addEventListener("click", () => perform(async () => {
  const identity = reviewIdentity(); if (!identity) return;
  const id = state.batch.id;
  await api(`/api/batches/${id}/state`, {revision: state.batch.revision, state: state.batch.state === "open" ? "closed" : "open", acknowledge_attention: $("acknowledge").checked, ...identity});
  state.selected = {}; state.focused = null; $("reason").value = "";
  await loadBatch(id); await refreshList(); notice(state.batch.state === "closed" ? "批次已凍結；未解決差異仍保留在結果中。" : "批次已重新開啟。");
}));
$("export").addEventListener("click", () => perform(async () => {
  const blob = await api(`/api/batches/${state.batch.id}/export?revision=${state.batch.revision}`);
  const url = URL.createObjectURL(blob), link = node("a"); link.href = url; link.download = `rowledger-${state.batch.id}-r${state.batch.revision}.zip`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000); notice("已準備完整 ZIP，請確認瀏覽器下載結果。");
}));
async function openBatch(result) {
  state.page = 1; state.selected = {}; state.focused = null;
  $("search").value = ""; $("status").value = "attention"; $("side").value = "";
  await loadBatch(result.batch.id); await refreshList(); $("import-dialog").close();
  notice(result.reused ? "相同來源與設定已匯入，已開啟既有批次。" : "批次已匯入，原始檔案與結果已保存在本機。");
}
for (const id of ["welcome-demo", "import-demo"]) $(id).addEventListener("click", () => perform(async () => openBatch(await api("/api/demo", {}))));
function openImport() { $("import-error").hidden = true; $("import-dialog").showModal(); }
$("new-batch").addEventListener("click", openImport); $("welcome-import").addEventListener("click", openImport);
$("import-dialog").addEventListener("cancel", event => { if (state.busy) event.preventDefault(); });
$("close-dialog").addEventListener("click", () => { if (!state.busy) $("import-dialog").close(); });
async function encodedFile(file) {
  if (!file || !file.size || file.size > 10 * 1024 * 1024) throw new Error("每份檔案需為 1 byte 至 10 MiB。");
  const bytes = new Uint8Array(await file.arrayBuffer()); let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32768) binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  return {name: file.name, content: btoa(binary)};
}
$("import-form").addEventListener("submit", event => {
  event.preventDefault();
  perform(async () => {
    const button = $("import-submit"); button.disabled = true; button.textContent = "正在核對…"; $("import-error").hidden = true;
    try {
      const mapping = side => Object.fromEntries(["key", "amount", "currency", "sheet"].map(key => [key, $("import-form").elements.namedItem(`${side}-${key}`).value.trim() || null]));
      const scales = {};
      for (const item of $("currency-scales").value.split(",")) { const match = item.trim().match(/^([A-Z]{3})\s*=\s*([0-6])$/); if (!match || Object.hasOwn(scales, match[1])) throw new Error("幣別設定格式為 USD=2, TWD=0，幣別不可重複。"); scales[match[1]] = Number(match[2]); }
      const [orders, payments] = await Promise.all([encodedFile($("orders-file").files[0]), encodedFile($("payments-file").files[0])]);
      const result = await api("/api/batches", {title: $("import-title").value, orders, payments, rules: {orders: mapping("orders"), payments: mapping("payments"), minor_units: scales, trim_keys: true}});
      await openBatch(result);
    } catch (error) { $("import-error").textContent = error.message; $("import-error").hidden = false; }
    finally { button.disabled = false; button.textContent = "匯入並核對"; }
  });
});
let searchTimer;
function filterChanged() { state.page = 1; if (state.batch) loadBatch(state.batch.id).catch(error => notice(error.message, true)); }
$("search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(filterChanged, 250); });
$("status").addEventListener("change", filterChanged); $("side").addEventListener("change", filterChanged);
$("previous").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; loadBatch(state.batch.id).catch(error => notice(error.message, true)); } });
$("next").addEventListener("click", () => { if (state.page < state.batch.pages) { state.page += 1; loadBatch(state.batch.id).catch(error => notice(error.message, true)); } });
refreshList().then(async batches => { if (batches.length) { await loadBatch(batches[0].id); await refreshList(); } }).catch(error => { $("connection").textContent = "無法連接工作台"; notice(error.message, true); });

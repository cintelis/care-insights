/* Care Insights showcase: interactive charts drawn from assets/data/gold.json (plain SVG, no libraries). */
(() => {
  "use strict";
  const STATUS = { "On track": "#0ca30c", "Under-used": "#fab219", "Over budget": "#d03b3b" };
  const STATUS_ORDER = ["Under-used", "On track", "Over budget"];
  const SERIES = "#2a78d6";
  const TYPES = { "Duplicate invoice": "#2a78d6", "Above price cap": "#eb6834", "Unknown participant": "#1baf7a" };
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s) => document.querySelector(s);
  const aud = (v) => "$" + Math.round(v).toLocaleString("en-AU");
  const audK = (v) => (Math.abs(v) >= 1000 ? "$" + (v / 1000).toFixed(v >= 100000 ? 0 : 1) + "k" : aud(v));
  const pct = (v, d = 1) => (v * 100).toFixed(d) + "%";
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  let D = null;
  let region = "";
  let active = "budget";

  /* ---------- tooltip ---------- */
  const tip = $("#tip");
  function showTip(e, html) {
    tip.innerHTML = html;
    tip.classList.add("on");
    const r = tip.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
  const hideTip = () => tip.classList.remove("on");

  /* ---------- svg helpers ---------- */
  function el(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function svg(host, w, h) {
    host.innerHTML = "";
    const s = el("svg", { viewBox: `0 0 ${w} ${h}`, width: w, height: h, role: "img" }, host);
    return s;
  }
  // rect with 4px rounding only on the data end (top for columns, right for bars)
  function colPath(x, y, w, h, r = 4, roundTop = true) {
    if (h <= 0 || w <= 0) return "";
    r = Math.min(r, w / 2, h);
    if (!roundTop) return `M${x},${y}h${w}v${h}h${-w}z`;
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}z`;
  }
  function barPath(x, y, w, h, r = 4, roundEnd = true) {
    if (h <= 0 || w <= 0) return "";
    r = Math.min(r, h / 2, w);
    if (!roundEnd) return `M${x},${y}h${w}v${h}h${-w}z`;
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}z`;
  }
  function hover(node, html, group) {
    node.classList.add("mark");
    const on = (e) => {
      showTip(e, html);
      if (group) { group.classList.add("dim"); node.classList.add("on"); }
    };
    node.addEventListener("pointermove", on);
    node.addEventListener("pointerleave", () => { hideTip(); if (group) { group.classList.remove("dim"); node.classList.remove("on"); } });
  }
  const widthOf = (host) => Math.max(280, Math.floor(host.getBoundingClientRect().width));
  // a step from 1/2/2.5/5 x 10^n giving at most `n` intervals, and the rounded-up max
  function ticks(max, n = 5) {
    const raw = (max || 1) / n, p = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((k) => k * p).find((k) => k >= raw);
    return { step, max: Math.ceil((max || 1) / step) * step };
  }
  function legend(host, items) {
    host.innerHTML = items.map(([label, c]) => `<span><i style="background:${c}"></i>${esc(label)}</span>`).join("");
  }
  function kpis(host, items) {
    host.innerHTML = items.map(([v, l]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  }

  /* ---------- budgets ---------- */
  function renderBudget() {
    const pts = D.budget_points.filter((p) => !region || p.region === region);
    const n = pts.length || 1;
    const under = pts.filter((p) => p.status === "Under-used");
    const over = pts.filter((p) => p.status === "Over budget");
    const onTrack = pts.filter((p) => p.status === "On track").length;
    const lost = pts.reduce((a, p) => a + p.lost, 0);
    const overspend = over.reduce((a, p) => a + Math.max(p.forecast - p.budget, 0), 0);
    kpis($("#k-budget"), [
      [pct(onTrack / n), "participants on track"],
      [aud(lost), `at risk of being lost · ${under.length} under-used`],
      [aud(overspend), `forecast overspend · ${over.length} over budget`],
      [n.toLocaleString(), "participants" + (region ? " in " + esc(region) : "")],
    ]);

    // histogram, 5-point bins from 0 to 160 (values above clipped into the last bin), stacked by status
    const host = $("#c-hist"), W = widthOf(host), H = 250, m = { l: 34, r: 8, t: 18, b: 26 };
    const s = svg(host, W, H), iw = W - m.l - m.r, ih = H - m.t - m.b;
    const BW = 5, LO = 0, HI = 160, NB = (HI - LO) / BW;
    const bins = Array.from({ length: NB }, () => ({ "Under-used": 0, "On track": 0, "Over budget": 0 }));
    for (const p of pts) {
      const v = Math.min(Math.max(p.fpct * 100, LO), HI - 0.001);
      bins[Math.floor((v - LO) / BW)][p.status]++;
    }
    const tot = bins.map((b) => b["Under-used"] + b["On track"] + b["Over budget"]);
    const tk = ticks(Math.max(...tot, 1), 5), ymax = tk.max;
    const x = (v) => m.l + ((v - LO) / (HI - LO)) * iw, y = (v) => m.t + ih - (v / ymax) * ih;
    for (let v = 0; v <= ymax + 1e-9; v += tk.step) {
      el("line", { class: "grid", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }, s);
      el("text", { x: m.l - 6, y: y(v) + 4, "text-anchor": "end" }, s).textContent = Math.round(v);
    }
    for (let v = 0; v <= HI; v += 20) el("text", { x: x(v), y: H - 8, "text-anchor": "middle" }, s).textContent = v + (v === HI ? "%+" : "%");
    const g = el("g", {}, s);
    const bw = iw / NB;
    bins.forEach((b, i) => {
      let acc = 0;
      const top = STATUS_ORDER.filter((k) => b[k] > 0).pop();
      for (const k of STATUS_ORDER) {
        if (!b[k]) continue;
        const y0 = y(acc + b[k]), h = y(acc) - y0;
        const gap = acc > 0 ? 2 : 0; // 2px surface gap between stacked segments
        const node = el("path", { d: colPath(x(LO + i * BW) + 1, y0, bw - 2, h - gap, 4, k === top), fill: STATUS[k] }, g);
        const lo = LO + i * BW, hi = lo + BW;
        hover(node, `<b>${esc(k)}</b><br>${lo}–${hi === HI ? HI + "+" : hi}% of budget<br>${b[k]} participant${b[k] > 1 ? "s" : ""}`, g);
        acc += b[k];
      }
    });
    for (const [v, label] of [[70, "70% under-use line"], [100, "Budget"]]) {
      el("line", { class: "ref", x1: x(v), x2: x(v), y1: m.t - 4, y2: m.t + ih }, s);
      el("text", { x: x(v) + (v === 70 ? -4 : 4), y: m.t - 7, "text-anchor": v === 70 ? "end" : "start" }, s).textContent = label;
    }
    legend($("#l-hist"), STATUS_ORDER.map((k) => [k, STATUS[k]]));

    // funds at risk by region (always all regions; the selected one is emphasised)
    const byR = {};
    for (const p of D.budget_points) byR[p.region] = (byR[p.region] || 0) + p.lost;
    const rows = Object.entries(byR).sort((a, b) => b[1] - a[1]);
    hBars($("#c-region"), rows.map(([r, v]) => ({ label: r, value: v, color: SERIES, faded: region && r !== region,
      tip: `<b>${esc(r)}</b><br>${aud(v)} at risk of being lost` })), audK, 120);

    // action list
    const act = pts.filter((p) => p.status !== "On track")
      .map((p) => ({ ...p, prio: p.lost + Math.max(p.forecast - p.budget, 0) }))
      .sort((a, b) => b.prio - a.prio).slice(0, 25);
    const maxPct = 1.6;
    $("#tb-budget").innerHTML = `<thead><tr><th>Participant</th><th>Status</th><th>Region</th><th class="num">Budget</th><th class="num">Spent</th><th class="num">Forecast</th><th class="num">Forecast % of budget</th><th class="num">At risk / over</th></tr></thead><tbody>` +
      act.map((p) => `<tr><td>${p.id}</td><td><span class="pill ${p.status === "Over budget" ? "critical" : "warning"}">${p.status}</span></td><td>${esc(p.region)}</td>` +
        `<td class="num">${aud(p.budget)}</td><td class="num">${aud(p.spend)}</td><td class="num">${aud(p.forecast)}</td>` +
        `<td class="num"><span class="bar-cell"><span class="track"><b style="width:${Math.min(p.fpct / maxPct, 1) * 100}%"></b></span>${pct(p.fpct)}</span></td>` +
        `<td class="num">${p.status === "Over budget" ? "+" + aud(p.forecast - p.budget) : aud(p.lost)}</td></tr>`).join("") +
      (act.length ? "" : `<tr><td colspan="8">No participants need action.</td></tr>`) + "</tbody>";
  }

  /* horizontal bar chart with direct value labels */
  function hBars(host, rows, fmt, labelW = 110, ref) {
    const W = widthOf(host), rowH = 26, m = { l: labelW, r: 64, t: ref ? 22 : 6, b: 6 };
    const H = m.t + m.b + rows.length * rowH;
    const s = svg(host, W, H), iw = W - m.l - m.r;
    const vmax = Math.max(...rows.map((r) => (r.stack ? r.stack.reduce((a, x) => a + x.value, 0) : r.value)), ref ? ref.value : 0, 1e-9);
    const x = (v) => m.l + (v / vmax) * iw;
    const g = el("g", {}, s);
    rows.forEach((r, i) => {
      const y0 = m.t + i * rowH + 5, h = rowH - 10;
      const t = el("text", { x: m.l - 8, y: y0 + h / 2 + 4, "text-anchor": "end" }, s);
      t.textContent = r.label;
      if (r.bold) t.setAttribute("style", "fill:var(--text);font-weight:600");
      const parts = r.stack || [{ value: r.value, color: r.color, tip: r.tip }];
      let acc = 0;
      parts.forEach((p, j) => {
        if (p.value <= 0) return;
        const last = j === parts.length - 1 || parts.slice(j + 1).every((q) => q.value <= 0);
        const gap = acc > 0 ? 2 : 0;
        const node = el("path", { d: barPath(x(acc) + gap, y0, x(acc + p.value) - x(acc) - gap, h, 4, last), fill: p.color, opacity: r.faded ? 0.3 : 1 }, g);
        hover(node, p.tip || r.tip, g);
        acc += p.value;
      });
      el("text", { class: "val", x: x(acc) + 6, y: y0 + h / 2 + 4 }, s).textContent = fmt(acc);
    });
    if (ref) {
      el("line", { class: "ref", x1: x(ref.value), x2: x(ref.value), y1: m.t - 4, y2: H }, s);
      if (ref.label) el("text", { x: x(ref.value) + 4, y: m.t - 8 }, s).textContent = ref.label;
    }
  }

  /* ---------- visits ---------- */
  function renderVisits() {
    const byDay = new Map();
    for (const r of D.visits_daily) {
      if (region && r.region !== region) continue;
      const a = byDay.get(r.d) || { d: r.d, sched: 0, ontime: 0, late: 0, missed: 0, deliv: 0 };
      a.sched += r.sched; a.ontime += r.ontime; a.late += r.late; a.missed += r.missed; a.deliv += r.deliv;
      byDay.set(r.d, a);
    }
    const days = [...byDay.values()].sort((a, b) => (a.d < b.d ? -1 : 1));
    const last = days.slice(-30);
    const sum = (arr, k) => arr.reduce((a, r) => a + r[k], 0);
    kpis($("#k-visits"), [
      [pct(sum(last, "ontime") / Math.max(sum(last, "sched"), 1)), "on time · last 30 days"],
      [sum(last, "missed").toLocaleString(), "missed · last 30 days"],
      [sum(last, "late").toLocaleString(), "late (>15 min) · last 30 days"],
      [sum(last, "sched").toLocaleString(), "scheduled · last 30 days"],
    ]);
    const roll = days.map((r, i) => {
      const w = days.slice(Math.max(0, i - 6), i + 1);
      return { d: r.d, v: sum(w, "ontime") / Math.max(sum(w, "sched"), 1), r };
    }).slice(6);
    lineChart($("#c-ontime"), roll);
    columnChart($("#c-missed"), days.map((r) => ({ d: r.d, v: r.missed, r })));
  }
  const fmtDate = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-AU", { day: "numeric", month: "short" });

  function timeAxis(s, pts, x, m, H) {
    const months = pts.filter((p, i) => i === 0 || p.d.slice(5, 7) !== pts[i - 1].d.slice(5, 7));
    for (const p of months) {
      el("text", { x: x(p.i), y: H - 8, "text-anchor": "start" }, s).textContent =
        new Date(p.d + "T00:00:00").toLocaleDateString("en-AU", { month: "short" });
    }
  }

  function lineChart(host, data) {
    const W = widthOf(host), H = 220, m = { l: 40, r: 12, t: 12, b: 26 };
    const s = svg(host, W, H), iw = W - m.l - m.r, ih = H - m.t - m.b;
    const vals = data.map((p) => p.v);
    const lo = Math.max(0, Math.floor((Math.min(...vals) - 0.02) * 20) / 20), hi = 1;
    const x = (i) => m.l + (i / Math.max(data.length - 1, 1)) * iw, y = (v) => m.t + ih - ((v - lo) / (hi - lo)) * ih;
    for (let v = lo; v <= hi + 1e-9; v += 0.05) {
      el("line", { class: "grid", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }, s);
      el("text", { x: m.l - 6, y: y(v) + 4, "text-anchor": "end" }, s).textContent = Math.round(v * 100) + "%";
    }
    timeAxis(s, data.map((p, i) => ({ d: p.d, i })), x, m, H);
    el("path", { d: data.map((p, i) => (i ? "L" : "M") + x(i).toFixed(1) + "," + y(p.v).toFixed(1)).join(""), fill: "none", stroke: SERIES, "stroke-width": 2, "stroke-linejoin": "round" }, s);
    const lastP = data[data.length - 1];
    if (lastP) el("text", { class: "val", x: x(data.length - 1) - 2, y: y(lastP.v) - 8, "text-anchor": "end" }, s).textContent = pct(lastP.v);
    // crosshair
    const cross = el("line", { class: "ref", y1: m.t, y2: m.t + ih, visibility: "hidden" }, s);
    const dot = el("circle", { r: 4.5, fill: SERIES, stroke: "#fff", "stroke-width": 2, visibility: "hidden" }, s);
    const hit = el("rect", { class: "hit", x: m.l, y: m.t, width: iw, height: ih }, s);
    hit.addEventListener("pointermove", (e) => {
      const r = s.getBoundingClientRect();
      const px = ((e.clientX - r.left) / r.width) * W;
      const i = Math.max(0, Math.min(data.length - 1, Math.round(((px - m.l) / iw) * (data.length - 1))));
      const p = data[i];
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(p.v)); dot.setAttribute("visibility", "visible");
      showTip(e, `<b>${fmtDate(p.d)}</b><br>${pct(p.v)} on time (7-day)<br>${p.r.sched} scheduled that day, ${p.r.missed} missed`);
    });
    hit.addEventListener("pointerleave", () => { hideTip(); cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); });
  }

  function columnChart(host, data) {
    const W = widthOf(host), H = 170, m = { l: 40, r: 12, t: 10, b: 26 };
    const s = svg(host, W, H), iw = W - m.l - m.r, ih = H - m.t - m.b;
    const tk = ticks(Math.max(...data.map((p) => p.v), 1), 2), ymax = tk.max;
    const bw = iw / data.length, x = (i) => m.l + i * bw, y = (v) => m.t + ih - (v / ymax) * ih;
    for (let v = 0; v <= ymax + 1e-9; v += tk.step) {
      el("line", { class: "grid", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }, s);
      el("text", { x: m.l - 6, y: y(v) + 4, "text-anchor": "end" }, s).textContent = Math.round(v);
    }
    timeAxis(s, data.map((p, i) => ({ d: p.d, i })), (i) => x(i), m, H);
    const g = el("g", {}, s);
    data.forEach((p, i) => {
      const h = y(0) - y(p.v);
      const gap = bw > 4 ? 1 : 0.5;
      if (h > 0) el("path", { d: colPath(x(i) + gap / 2, y(p.v), Math.max(bw - gap, 1), h, Math.min(2, bw / 2)), fill: SERIES }, g);
      const hit = el("rect", { class: "hit", x: x(i), y: m.t, width: bw, height: ih }, s);
      hit.addEventListener("pointermove", (e) => showTip(e, `<b>${fmtDate(p.d)}</b><br>${p.v} missed of ${p.r.sched} scheduled`));
      hit.addEventListener("pointerleave", hideTip);
    });
  }

  /* ---------- workers ---------- */
  function renderWorkers() {
    const ws = D.workers.filter((w) => !region || w.region === region);
    const flagged = ws.filter((w) => w.flag);
    const sched = ws.reduce((a, w) => a + w.sched, 0), late = ws.reduce((a, w) => a + w.late, 0);
    kpis($("#k-workers"), [
      [ws.length, "workers" + (region ? " based in " + esc(region) : "")],
      [flagged.length, "need review (late rate > 20%)"],
      [pct(late / Math.max(sched, 1)), "average late rate"],
      [flagged.length ? flagged.map((w) => w.id).join(", ") : "–", "flagged"],
    ]);
    const top = ws.slice().sort((a, b) => b.late_rate - a.late_rate).slice(0, 15);
    hBars($("#c-workers"), top.map((w) => ({
      label: w.id + (w.flag ? " ⚑" : ""), value: w.late_rate, color: w.flag ? "#d03b3b" : SERIES, bold: w.flag,
      tip: `<b>${w.id}</b> · ${esc(w.region)} · ${w.emp.replace("_", " ")}<br>${pct(w.late_rate)} late (${w.late} of ${w.sched})<br>avg ${w.avg_late} min late · ${pct(w.missed_rate)} missed` +
        (w.flag ? "<br><b>Needs review</b>" : ""),
    })), (v) => pct(v), 80, { value: 0.2, label: "20% review line" });
    legend($("#l-workers"), [["Needs review ⚑", "#d03b3b"], ["Within threshold", SERIES]]);
  }

  /* ---------- invoices ---------- */
  function renderInvoices() {
    const t = D.invoice_types, total = t.reduce((a, r) => a + r.at_risk, 0), n = t.reduce((a, r) => a + r.n, 0);
    const by = Object.fromEntries(t.map((r) => [r.kind, r]));
    kpis($("#k-invoices"), [
      [aud(total), `held back · ${n} exceptions`],
      [by["Duplicate invoice"]?.n ?? 0, "duplicate invoices"],
      [by["Above price cap"]?.n ?? 0, "above the price cap"],
      [by["Unknown participant"]?.n ?? 0, "unknown participants"],
    ]);
    const prov = {};
    for (const r of D.invoice_providers) {
      const p = (prov[r.id] = prov[r.id] || { id: r.id, name: r.pname, total: 0, parts: {} });
      p.parts[r.kind] = r; p.total += r.at_risk;
    }
    const kinds = Object.keys(TYPES);
    const rows = Object.values(prov).sort((a, b) => b.total - a.total).slice(0, 8).map((p) => ({
      label: p.id,
      stack: kinds.map((k) => ({ value: p.parts[k]?.at_risk || 0, color: TYPES[k],
        tip: `<b>${esc(p.name)}</b><br>${esc(k)}: ${p.parts[k]?.n || 0} invoices, ${aud(p.parts[k]?.at_risk || 0)}<br>Provider total ${aud(p.total)}` })),
    }));
    hBars($("#c-prov"), rows, audK, 64);
    legend($("#l-prov"), kinds.map((k) => [k, TYPES[k]]));
    hBars($("#c-types"), t.map((r) => ({ label: r.kind, value: r.at_risk, color: TYPES[r.kind] || SERIES,
      tip: `<b>${esc(r.kind)}</b><br>${r.n} invoices<br>${aud(r.at_risk)} at risk` })), (v) => audK(v), 130);
  }

  /* ---------- wiring ---------- */
  const RENDER = { budget: renderBudget, visits: renderVisits, workers: renderWorkers, invoices: renderInvoices };
  function render() { if (D) RENDER[active](); }

  const tabs = [...document.querySelectorAll('.tabs [role="tab"]')];
  function select(tab, focus) {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    }
    active = tab.id.slice(2);
    try { localStorage.setItem("ci-tab", active); } catch (_) { /* storage unavailable */ }
    if (focus) tab.focus();
    render();
  }
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => select(t));
    t.addEventListener("keydown", (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (d) { e.preventDefault(); select(tabs[(i + d + tabs.length) % tabs.length], true); }
    });
  });
  $("#region").addEventListener("change", (e) => { region = e.target.value; render(); });
  let rt;
  addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(render, 120); });

  fetch("assets/data/gold.json")
    .then((r) => r.json())
    .then((d) => {
      D = d;
      const regions = [...new Set(d.budget_points.map((p) => p.region))].sort();
      $("#region").insertAdjacentHTML("beforeend", regions.map((r) => `<option>${esc(r)}</option>`).join(""));
      let saved = null;
      try { saved = localStorage.getItem("ci-tab"); } catch (_) { /* storage unavailable */ }
      const t = saved && document.getElementById("t-" + saved);
      if (t) select(t); else render();
    })
    .catch(() => { $("#demo-app .panel").innerHTML = "<p>Couldn't load the demo data.</p>"; });
})();

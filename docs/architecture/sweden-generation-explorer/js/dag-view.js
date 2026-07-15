"use strict";

// Existing DAG explorer (ETL band, SVG DAG, Structure/Individual/Manual modes,
// population overlay). Extracted verbatim from the former single-file page.
// ---- ETL band (HTML) ----
(function buildEtl() {
  const host = document.getElementById("etl");
  SPEC.etl.forEach((b, i) => {
    if (i > 0) {
      const a = document.createElement("div");
      a.className = "arw"; a.setAttribute("aria-hidden", "true"); a.textContent = "→";
      host.appendChild(a);
    }
    const box = document.createElement("div");
    box.className = "box" + (b.cls ? " " + b.cls : "");
    const t = document.createElement("div"); t.className = "bt"; t.textContent = b.label;
    const s = document.createElement("div"); s.className = "bs"; s.textContent = b.sub;
    box.appendChild(t); box.appendChild(s);
    host.appendChild(box);
  });
})();

// ---- DAG (SVG) ----
const SVGNS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("dag");
const NW = 178, NH = 62;
const VX = x => 100 + (x - 0.55) * 116;
const VY = y => 74 + (9.3 - y) * 80;
const nodeById = {};
SPEC.nodes.forEach(n => { n.cx = VX(n.x); n.cy = VY(n.y); nodeById[n.id] = n; });

function el(tag, attrs, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

// defs / arrow markers
const defs = el("defs", {}, svg);
function marker(id, cls) {
  const m = el("marker", { id, viewBox: "0 0 10 10", refX: "8.5", refY: "5",
    markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse" }, defs);
  el("path", { d: "M0,0 L10,5 L0,10 z", class: cls }, m);
}
marker("mk-solid", "mk-solid");
marker("mk-employed", "mk-employed");
marker("mk-age", "mk-age");
marker("mk-option", "mk-option");
// marker fills follow theme via CSS
const mkStyle = document.createElement("style");
mkStyle.textContent =
  ".mk-solid{fill:var(--edge)}.mk-employed{fill:var(--e-employed)}" +
  ".mk-age{fill:var(--e-age)}.mk-option{fill:var(--accent)}";
document.head.appendChild(mkStyle);

// section labels + marginal enclosure
el("text", { x: 18, y: 28, class: "sec-label" }, svg).textContent = "sample_one — per individual, ~14 conditional draws";
const encY = VY(0.7) - 46;
el("rect", { x: 14, y: encY, width: 1152, height: 118, rx: 12, class: "enclosure" }, svg);
el("text", { x: 22, y: encY - 8, class: "sec-sub" }, svg).textContent = "Independent marginals — no conditioning";

// layers: edges below, nodes above
const edgeLayer = el("g", {}, svg);
const optLayer = el("g", {}, svg);
const chipLayer = el("g", {}, svg);
const nodeLayer = el("g", {}, svg);

function anchor(a, b) {
  const dx = b.cx - a.cx, dy = b.cy - a.cy;
  if (Math.abs(dy) >= Math.abs(dx)) return [a.cx, dy > 0 ? a.cy + NH / 2 : a.cy - NH / 2];
  return [dx > 0 ? a.cx + NW / 2 : a.cx - NW / 2, a.cy];
}

const edgeEls = []; // {src,dst,el}
SPEC.edges.forEach(([s, d, kind]) => {
  const a = nodeById[s], b = nodeById[d];
  const [x0, y0] = anchor(a, b), [x1, y1] = anchor(b, a);
  const mk = kind === "employed" ? "mk-employed" : kind === "age" ? "mk-age" : "mk-solid";
  const line = el("line", { x1: x0, y1: y0, x2: x1, y2: y1,
    class: "edge " + kind, "marker-end": `url(#${mk})` }, edgeLayer);
  edgeEls.push({ src: s, dst: d, el: line, option: false, kind });
});

// option edges (1) — one per node that carries an `option`, all from the hub
const optionEls = [];
SPEC.nodes.filter(n => n.option).forEach(n => {
  const a = nodeById["agesex"], b = n;
  const [x0, y0] = anchor(a, b), [x1, y1] = anchor(b, a);
  const line = el("line", { x1: x0, y1: y0, x2: x1, y2: y1,
    class: "option-edge", "marker-end": "url(#mk-option)" }, optLayer);
  optionEls.push({ src: "agesex", dst: n.id, el: line, option: true });
  // dimension chip near the target node (revealed with the toggle)
  const txt = "+ " + n.option.dims.join(" · ");
  const cw = 24 + txt.length * 7;
  const gx = b.cx - cw / 2, gy = b.cy - NH / 2 - 24;
  const g = el("g", { class: "option-chip" }, chipLayer);
  el("rect", { x: gx, y: gy, width: cw, height: 19, rx: 9 }, g);
  el("text", { x: b.cx, y: gy + 13, "text-anchor": "middle" }, g).textContent = txt;
});
const allEdgeEls = edgeEls.concat(optionEls);

// nodes
const nodeGById = {};
SPEC.nodes.forEach(n => {
  const g = el("g", { class: "node " + n.kind, tabindex: "0", role: "button",
    "aria-label": `${n.label}, ${n.kind}. ${n.caption}. Press Enter for details.` }, nodeLayer);
  g.dataset.id = n.id;
  nodeGById[n.id] = g;
  el("rect", { class: "body", x: n.cx - NW / 2, y: n.cy - NH / 2, width: NW, height: NH, rx: 12 }, g);
  el("text", { class: "step", x: n.cx - NW / 2 + 9, y: n.cy - NH / 2 + 17 }, g).textContent = n.step;
  el("text", { class: "lab", x: n.cx, y: n.cy - 2 }, g).textContent = n.label;
  el("text", { class: "cap", x: n.cx, y: n.cy + 17 }, g).textContent = n.caption;

  g.addEventListener("click", () => select(n.id));
  g.addEventListener("keydown", ev => {
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(n.id); }
  });
  g.addEventListener("mouseenter", () => highlight(n.id));
  g.addEventListener("mouseleave", clearHighlight);
  g.addEventListener("focus", () => highlight(n.id));
  g.addEventListener("blur", clearHighlight);
});

// ---- hover / focus highlight ----
function highlight(id) {
  const adj = new Set([id]);
  const showOpt = svg.classList.contains("show-options");
  allEdgeEls.forEach(e => {
    const incident = (e.src === id || e.dst === id) && (!e.option || showOpt);
    if (incident) { e.el.classList.add("hot"); e.el.classList.remove("dim-edge"); adj.add(e.src); adj.add(e.dst); }
    else { e.el.classList.remove("hot"); e.el.classList.add("dim-edge"); }
  });
  document.querySelectorAll(".node").forEach(g => {
    g.classList.toggle("dim", !adj.has(g.dataset.id));
  });
}
function clearHighlight() {
  allEdgeEls.forEach(e => e.el.classList.remove("hot", "dim-edge"));
  document.querySelectorAll(".node").forEach(g => g.classList.remove("dim"));
}

// ---- selection / detail panel ----
const panel = document.getElementById("panel");
let selectedId = null;

function chipRow(list, cls) {
  return `<div class="chips">${list.map(c => `<span class="chip ${cls || ""}">${esc(c)}</span>`).join("")}</div>`;
}
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

const VERDICT_LABEL = {
  equivalent: "bulk = per-individual",
  option: "hides real conditioning",
  marginal: "marginal by design",
};

// ===================================================================
//  Embedded source distributions + mode engine (Structure / Individual / Manual)
// ===================================================================

// ---- parse the embedded-dist island (self-contained; never throws on load) ----
let DIST = null;
(function parseDist() {
  const island = document.getElementById("embedded-dist");
  if (!island) return;
  const raw = island.textContent && island.textContent.trim();
  if (!raw) return;
  try { DIST = JSON.parse(raw); } catch (e) { DIST = null; }
})();

const AGE_GROUPS = (DIST && DIST.constants.AGE_GROUPS) || [];
function ageToGroup(age) {
  if (!DIST || age == null) return null;
  for (const b of DIST.constants.AGE_GROUP_BOUNDS) {
    if (age >= b[0] && age <= b[1]) return b[2];
  }
  return null;
}
function isEmployedLabel(l) {
  return !!(l && DIST && DIST.constants.IS_EMPLOYED.includes(String(l).toLowerCase()));
}
function isSwedishBirth(l) {
  return !!(DIST && DIST.constants.SWEDEN_LABELS.includes(l));
}
function fmtGroup(g) { return g ? String(g).replace("-", "–") : g; }

// ---- context: the parent-relevant attributes needed to slice any node ----
function ctxFromIndividual(ind) {
  const sex = lbl(ind.biological_sex);
  return {
    age: ind.age, age_group: ageToGroup(ind.age), sex,
    education: lbl(ind.education_level),
    employment_status: lbl(ind.employment_status),
    birth_location: lbl(ind.birth_location),
  };
}
function ctxFromManual() {
  let age_group = null, sex = null;
  if (manual.agesex) { const p = manual.agesex.split("|"); age_group = p[0]; sex = p[1]; }
  return {
    age: null, age_group, sex,
    education: manual.education || null,
    employment_status: manual.employment || null,
    birth_location: manual.birthloc || null,
  };
}
function deriveRole(role, ctx) {
  const C = DIST.constants;
  switch (role) {
    case "age_group": return ctx.age_group;
    case "sex": return ctx.sex;
    case "aku_edu": return ctx.education ? (C.SUN2020_TO_AKU_EDU[String(ctx.education).toLowerCase()] || null) : null;
    case "inc_emp": return ctx.employment_status ? (C.AKU_TO_INC_EMP[String(ctx.employment_status).toLowerCase()] || null) : null;
    case "inc_age": return ctx.age_group ? (C.AGE_GROUP_TO_INC_AGE[ctx.age_group] || null) : null;
    default: return null;
  }
}
function gateState(nodeId, ctx) {
  const g = DIST.schema[nodeId].gate;
  if (g === "employed") return { na: !isEmployedLabel(ctx.employment_status), reason: "unemployed" };
  if (g === "foreign_born") return { na: isSwedishBirth(ctx.birth_location), reason: "born in Sweden" };
  return { na: false, reason: null };
}

// ---- distribution slicing with honest fallback ----
function poolDists(list) {
  const out = {}; let n = 0;
  list.forEach(d => { n++; for (const k in d) out[k] = (out[k] || 0) + d[k]; });
  if (!n) return null;
  for (const k in out) out[k] /= n;
  return out;
}
function nearestGroups(ag) {
  const i = AGE_GROUPS.indexOf(ag);
  if (i < 0) return AGE_GROUPS.slice();
  const order = [];
  for (let d = 1; d < AGE_GROUPS.length; d++) {
    if (i - d >= 0) order.push(AGE_GROUPS[i - d]);
    if (i + d < AGE_GROUPS.length) order.push(AGE_GROUPS[i + d]);
  }
  return order;
}
// returns { dist, parents, values, fallback, kind } or null
function resolveNode(nodeId, ctx) {
  const spec = DIST && DIST.schema[nodeId];
  if (!spec) return null;
  if (spec.kind === "marginal" || spec.kind === "hub") {
    const dist = DIST.marginal[spec.field];
    return dist ? { dist, parents: [], values: [], fallback: null, kind: spec.kind } : null;
  }
  const raw = DIST.conditional[spec.field];
  if (!raw) return null;
  const parents = spec.parents;
  const values = parents.map(r => deriveRole(r, ctx));
  // 1. exact
  if (values.every(v => v != null)) {
    const key = values.join("|");
    if (raw[key]) return { dist: raw[key], parents, values, fallback: null, kind: "conditional" };
  }
  const agIdx = parents.indexOf("age_group");
  // 2. nearest age_group (other parents intact)
  if (agIdx >= 0 && values[agIdx] != null && values.every((v, i) => i === agIdx || v != null)) {
    for (const ag of nearestGroups(values[agIdx])) {
      const v2 = values.slice(); v2[agIdx] = ag;
      const key = v2.join("|");
      if (raw[key]) return { dist: raw[key], parents, values, fallback: "nearest: " + fmtGroup(ag), kind: "conditional" };
    }
  }
  // 3. drop sex — pool across sexes (exact age_group, then nearest)
  const sexIdx = parents.indexOf("sex");
  if (sexIdx >= 0) {
    const agList = (agIdx >= 0 && values[agIdx] != null) ? [values[agIdx]].concat(nearestGroups(values[agIdx])) : [null];
    for (const ag of agList) {
      const matches = [];
      for (const key in raw) {
        const kp = key.split("|");
        let ok = true;
        parents.forEach((r, i) => {
          if (i === sexIdx) return;
          const want = (i === agIdx && ag != null) ? ag : values[i];
          if (want != null && kp[i] !== want) ok = false;
        });
        if (ok) matches.push(raw[key]);
      }
      if (matches.length) {
        const note = "pooled across sex" + (ag != null && ag !== values[agIdx] ? ", nearest: " + fmtGroup(ag) : "");
        return { dist: poolDists(matches), parents, values, fallback: note, kind: "conditional" };
      }
    }
  }
  // 4. whole-attribute marginal
  const all = Object.values(raw);
  if (all.length) return { dist: poolDists(all), parents, values, fallback: "marginal", kind: "conditional" };
  return null;
}
function argmax(dist) {
  let best = null, bp = -Infinity;
  for (const k in dist) { if (dist[k] > bp) { bp = dist[k]; best = k; } }
  return best;
}

// ---- panel rendering: conditioning line + ranked probability list ----
function ctxLineHtml(nodeId, res) {
  const label = nodeById[nodeId].label;
  if (res.kind === "marginal" || res.kind === "hub") {
    return `<div class="cond-line"><b>${esc(label)}</b> — marginal (same for everyone)</div>`;
  }
  const pooledSex = res.fallback && res.fallback.indexOf("pooled") === 0;
  const parts = [];
  DIST.schema[nodeId].parents.forEach((r, i) => {
    const v = res.values[i];
    if (v == null) return;
    if (r === "sex" && pooledSex) return;
    parts.push(r === "age_group" ? "age " + fmtGroup(v) : v);
  });
  let s = `<b>${esc(label)}</b> | ${esc(parts.join(", "))}`;
  if (res.fallback) s += ` <span class="fallback">(${esc(res.fallback)})</span>`;
  return `<div class="cond-line">${s}</div>`;
}
function fmtP(p) {
  if (p >= 0.10) return p.toFixed(2);
  if (p >= 0.01) return p.toFixed(3);
  if (p > 0) return p.toExponential(1);
  return "0";
}
function probListHtml(nodeId, res, currentValue, selectable) {
  const entries = Object.entries(res.dist).sort((a, b) => b[1] - a[1]);
  const max = entries.length ? entries[0][1] : 1;
  const rows = entries.map(([val, p]) => {
    const cur = currentValue != null && val === currentValue;
    const w = max > 0 ? Math.max(2, Math.round(p / max * 100)) : 0;
    const a = selectable ? ` role="radio" tabindex="0" aria-checked="${cur}" data-val="${esc(val)}"` : "";
    return `<div class="prob-row${cur ? " current" : ""}"${a}>`
      + `<span class="radio" aria-hidden="true"></span>`
      + `<span class="pv">${esc(val)}</span>`
      + `<span class="pbar"><i style="width:${w}%"></i></span>`
      + `<span class="pp">${fmtP(p)}</span></div>`;
  }).join("");
  const cls = "problist" + (selectable ? " selectable" : "");
  const role = selectable ? ` role="radiogroup" aria-label="${esc(nodeById[nodeId].label)} values"` : "";
  return `<div class="${cls}"${role}>${rows}</div>`;
}

// dist-key form of each node's value (for highlighting the current row)
const KEY_EXTRACT = {
  agesex:        (i, ctx) => (ctx.age_group && lbl(i.biological_sex)) ? `${ctx.age_group}|${lbl(i.biological_sex)}` : null,
  education:     i => lbl(i.education_level),
  employment:    i => lbl(i.employment_status),
  industry:      i => i.industry_sector ? lbl(i.industry_sector) : null,
  emptype:       i => i.employment_type ? `${lbl(i.employment_type.attachment)}|${lbl(i.employment_type.hours)}` : null,
  income_source: i => lbl(i.income_source),
  socio:         i => lbl(i.socioeconomic_class),
  civil:         i => lbl(i.civil_status),
  birthloc:      i => lbl(i.birth_location),
  birthdetail:   i => lbl(i.birth_country_detail),
  region:        i => lbl(i.region),
  parental:      i => lbl(i.parental_structure),
  housing:       i => lbl(i.housing_tenure),
  household:     i => lbl(i.household_size),
};
function manualChipDisplay(nodeId, val) {
  if (val == null) return null;
  if (nodeId === "agesex" || nodeId === "emptype") return val.replace("|", " · ");
  return val;
}

// build the mode-specific value line + probability list ("" in Structure mode)
function probeSection(id) {
  if (MODE === "structure" || !DIST || !DIST.schema[id]) return "";
  let ctx, current, curDisplay, gate;
  if (MODE === "individual") {
    if (curIndex == null || !POP) return "";
    const ind = POP.individuals[curIndex];
    ctx = ctxFromIndividual(ind);
    gate = gateState(id, ctx);
    current = gate.na ? null : (KEY_EXTRACT[id] ? KEY_EXTRACT[id](ind, ctx) : null);
    curDisplay = VALUE_EXTRACT[id] ? VALUE_EXTRACT[id](ind) : null;
  } else {
    ctx = ctxFromManual();
    gate = gateState(id, ctx);
    current = manual[id];
    curDisplay = manualChipDisplay(id, manual[id]);
  }
  const who = MODE === "individual" ? `This individual (#${esc(curIndex)})` : "Your selection";
  if (gate.na) {
    return `<div class="indiv-val na">${who}: <b>not applicable (${esc(gate.reason)})</b></div>`;
  }
  let html = `<div class="indiv-val">${who}: <b>${esc(curDisplay == null ? "—" : curDisplay)}</b></div>`;
  const res = resolveNode(id, ctx);
  if (!res) return html;
  html += ctxLineHtml(id, res);
  html += probListHtml(id, res, current, MODE === "manual");
  return html;
}
function attachProbHandlers(id) {
  if (MODE !== "manual") return;
  const list = panel.querySelector(".problist.selectable");
  if (!list) return;
  list.querySelectorAll(".prob-row").forEach(row => {
    const pick = () => {
      manual[id] = row.dataset.val;
      recomputeManual();
      applyManualOverlay();
      select(id);
      const cur = panel.querySelector(".problist .prob-row.current");
      if (cur) cur.focus();
    };
    row.addEventListener("click", pick);
    row.addEventListener("keydown", ev => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(); }
    });
  });
}

// ---- manual mode state ----
let manual = {};
let manualSeeded = false;
const MANUAL_ORDER = ["agesex", "birthloc", "education", "employment", "socio", "civil",
  "income_source", "industry", "emptype", "birthdetail", "region", "parental", "household", "housing"];
function recomputeManual() {
  MANUAL_ORDER.forEach(id => {
    const ctx = ctxFromManual();
    if (gateState(id, ctx).na) { manual[id] = null; return; }
    const res = resolveNode(id, ctx);
    if (!res) { manual[id] = null; return; }
    if (manual[id] != null && res.dist[manual[id]] != null) return; // keep still-valid pick
    manual[id] = argmax(res.dist);
  });
}
function seedManual() {
  manual = {};
  if (DIST) manual.agesex = argmax(DIST.marginal.age_sex_group);
  recomputeManual();
}
function applyManualOverlay() {
  svg.classList.add("show-values");
  let industryNa = false, emptypeNa = false;
  SPEC.nodes.forEach(n => {
    const ctx = ctxFromManual();
    const isNa = gateState(n.id, ctx).na;
    setChip(n.id, manualChipDisplay(n.id, manual[n.id]), isNa);
    nodeGById[n.id].classList.toggle("na", isNa);
    if (n.id === "industry") industryNa = isNa;
    if (n.id === "emptype") emptypeNa = isNa;
  });
  edgeEls.forEach(e => {
    if (e.kind === "employed") {
      const na = (e.dst === "industry" && industryNa) || (e.dst === "emptype" && emptypeNa);
      e.el.classList.toggle("na-dim", na);
    }
  });
}

// ---- mode switch ----
let MODE = "individual";
const MODE_DESC = {
  structure: "Structure only — no individual data, values, or probabilities.",
  individual: "One generated individual overlaid, with its conditioned probabilities.",
  manual: "Pick values yourself and watch downstream distributions recompute.",
};
const modeBtns = Array.from(document.querySelectorAll(".modeswitch .seg"));
const modeDesc = document.getElementById("modeDesc");
const popCtl = document.getElementById("popCtl");
const manualCtl = document.getElementById("manualCtl");
const resetManualBtn = document.getElementById("resetManualBtn");
function setMode(mode) {
  MODE = mode;
  modeBtns.forEach(b => {
    const on = b.dataset.mode === mode;
    b.setAttribute("aria-checked", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;
  });
  modeDesc.textContent = MODE_DESC[mode];
  popCtl.hidden = (mode !== "individual");
  manualCtl.hidden = (mode !== "manual");
  popError.textContent = "";
  if (mode === "structure") {
    clearOverlay();
  } else if (mode === "individual") {
    if (POP && curIndex != null) applyOverlay(POP.individuals[curIndex]);
    else if (POP) selectIndividual(0);
    else clearOverlay();
  } else {
    clearOverlay();
    if (!manualSeeded) { seedManual(); manualSeeded = true; }
    applyManualOverlay();
  }
  if (selectedId) select(selectedId);
}
modeBtns.forEach((b, i) => {
  b.addEventListener("click", () => setMode(b.dataset.mode));
  b.addEventListener("keydown", ev => {
    let j = null;
    if (ev.key === "ArrowRight" || ev.key === "ArrowDown") j = (i + 1) % modeBtns.length;
    else if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") j = (i - 1 + modeBtns.length) % modeBtns.length;
    if (j == null) return;
    ev.preventDefault();
    modeBtns[j].focus();
    setMode(modeBtns[j].dataset.mode);
  });
});
resetManualBtn.addEventListener("click", () => {
  seedManual();
  applyManualOverlay();
  if (selectedId) select(selectedId);
});
modeDesc.textContent = MODE_DESC.individual;

function select(id) {
  selectedId = id;
  const n = nodeById[id];
  document.querySelectorAll(".node").forEach(g => g.classList.toggle("selected", g.dataset.id === id));

  const showOpt = svg.classList.contains("show-options");
  let html = "";
  html += `<div class="step-tag">step ${esc(n.step)}</div>`;
  html += `<span class="verdict ${n.verdict}">${VERDICT_LABEL[n.verdict]}</span>`;
  html += `<h3>${esc(n.label)}</h3>`;
  html += probeSection(id);
  html += `<div class="mono" style="color:var(--muted);margin-bottom:2px">${esc(n.tableName)}</div>`;

  html += `<div class="field"><div class="k">SCB table</div><div class="v mono table-id">${esc(n.table)}</div></div>`;
  html += `<div class="field"><div class="k">PxWeb query</div><div class="v mono">${esc(n.query)}</div></div>`;

  html += `<div class="field"><div class="k">Category values (${n.categories.length})</div>`;
  html += chipRow(n.categories);
  if (n.sexes) html += `<div class="subhead" style="margin-top:6px">sex</div>` + chipRow(n.sexes);
  html += `</div>`;

  html += `<div class="field"><div class="k">Conditioning used</div>`;
  if (n.used.length) html += chipRow(n.used, "parent");
  else html += `<div class="chips"><span class="chip none">${n.id === "agesex" ? "root draw — none" : "none — marginal"}</span></div>`;
  html += `</div>`;

  html += `<div class="field"><div class="k">Available but unused</div>`;
  if (n.option) {
    html += chipRow(n.option.dims, "opt");
    if (!showOpt) html += `<div class="opt-hint">Enable the toggle above to draw this as a dashed edge.</div>`;
    html += `<div class="note-box">${esc(n.option.note)}</div>`;
  } else if (n.marginal) {
    html += `<div class="chips"><span class="chip none">no SCB cross-tab available</span></div>`;
    html += `<div class="note-box marg">${esc(n.note)}</div>`;
  } else {
    html += `<div class="chips"><span class="chip none">none — all supported conditioning is used</span></div>`;
    if (n.note) html += `<div class="note-box">${esc(n.note)}</div>`;
  }
  html += `</div>`;

  panel.innerHTML = html;
  attachProbHandlers(id);
}

// ---- toggle ----
const toggle = document.getElementById("optToggle");
toggle.addEventListener("change", () => {
  svg.classList.toggle("show-options", toggle.checked);
  if (selectedId) select(selectedId); // refresh the opt-hint state
});

// ---- population load + individual overlay ----
const GATED = new Set(["industry", "emptype"]); // null when unemployed → "not applicable" + dimmed
function lbl(o) { return (o && o.label != null) ? o.label : null; }

// map each SPEC node id → this individual's value for that attribute
const VALUE_EXTRACT = {
  agesex:        i => `${i.age} · ${lbl(i.biological_sex) ?? "?"}`,
  education:     i => lbl(i.education_level),
  employment:    i => lbl(i.employment_status),
  industry:      i => i.industry_sector ? lbl(i.industry_sector) : null,
  emptype:       i => i.employment_type ? `${lbl(i.employment_type.attachment)} · ${lbl(i.employment_type.hours)}` : null,
  income_source: i => lbl(i.income_source),
  socio:         i => lbl(i.socioeconomic_class),
  civil:         i => lbl(i.civil_status),
  birthloc:      i => lbl(i.birth_location),
  birthdetail:   i => lbl(i.birth_country_detail),
  region:        i => lbl(i.region),
  parental:      i => lbl(i.parental_structure),
  housing:       i => lbl(i.housing_tenure),
  household:     i => lbl(i.household_size),
};

// one value chip per node, drawn just below its box (same idiom as the caption/chips)
const valueLayer = el("g", {}, svg);
const valueChipById = {};
SPEC.nodes.forEach(n => {
  const gy = n.cy + NH / 2 + 8;
  const g = el("g", { class: "value-chip" }, valueLayer);
  const rect = el("rect", { x: n.cx - 30, y: gy, width: 60, height: 20, rx: 10 }, g);
  const text = el("text", { x: n.cx, y: gy + 14, "text-anchor": "middle" }, g);
  valueChipById[n.id] = { g, rect, text, node: n };
});
function setChip(id, value, isNa) {
  const c = valueChipById[id];
  c.text.textContent = isNa ? "not applicable" : (value == null ? "—" : String(value));
  const cw = Math.max(48, 22 + c.text.textContent.length * 7);
  c.rect.setAttribute("x", c.node.cx - cw / 2);
  c.rect.setAttribute("width", cw);
  c.g.classList.toggle("na", !!isNa);
}

let POP = null;
let curIndex = null;

const popFile = document.getElementById("popFile");
const loadBtn = document.getElementById("loadBtn");
const popSummary = document.getElementById("popSummary");
const popError = document.getElementById("popError");
const indivCtl = document.getElementById("indivCtl");
const idInput = document.getElementById("idInput");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const randBtn = document.getElementById("randBtn");
const clearBtn = document.getElementById("clearBtn");

loadBtn.addEventListener("click", () => popFile.click());

// Shared load path — used by both the file picker and the embedded auto-load.
// `data` must already be a parsed object with a non-empty `individuals` array.
function loadPopulation(data) {
  if (!data || !Array.isArray(data.individuals) || data.individuals.length === 0) {
    failLoad('file has no non-empty "individuals" array.'); return false;
  }
  POP = data;
  showSummary();
  indivCtl.hidden = false;
  idInput.max = String(POP.individuals.length - 1);
  selectIndividual(0);
  return true;
}

popFile.addEventListener("change", async ev => {
  const f = ev.target.files && ev.target.files[0];
  popFile.value = ""; // allow re-loading the same file name
  if (!f) return;
  popError.textContent = "";
  let data;
  try {
    data = JSON.parse(await f.text());
  } catch (e) {
    failLoad("not valid JSON — " + e.message); return;
  }
  loadPopulation(data); // a picked file overrides the embedded snapshot
});

function failLoad(msg) {
  POP = null; curIndex = null;
  indivCtl.hidden = true;
  clearOverlay();
  popSummary.classList.add("empty");
  popSummary.textContent = "No population loaded — load a generated SCB population JSON to overlay one individual onto the DAG.";
  popError.textContent = "Could not load population: " + msg;
  if (selectedId) select(selectedId);
}

function showSummary() {
  const m = POP.metadata || {};
  const n = POP.individuals.length;
  const bits = [`<b>${n.toLocaleString("en-US")}</b> individuals loaded`];
  if (m.source) bits.push(`source <b>${esc(m.source)}</b>`);
  if (m.n != null) bits.push(`n=<b>${esc(m.n)}</b>`);
  if (m.seed != null) bits.push(`seed <b>${esc(m.seed)}</b>`);
  if (m.data_vintage) bits.push(`vintage <b>${esc(m.data_vintage)}</b>`);
  popSummary.classList.remove("empty");
  popSummary.innerHTML = bits.join(" · ");
}

function selectIndividual(index) {
  if (!POP) return;
  const n = POP.individuals.length;
  index = Math.max(0, Math.min(n - 1, Math.trunc(index)));
  curIndex = index;
  idInput.value = String(index);
  applyOverlay(POP.individuals[index]);
  if (selectedId) select(selectedId); // refresh detail panel with the individual line
}

function applyOverlay(ind) {
  svg.classList.add("show-values");
  let industryNa = false, emptypeNa = false;
  SPEC.nodes.forEach(n => {
    const ex = VALUE_EXTRACT[n.id];
    const val = ex ? ex(ind) : null;
    const isNa = (val == null) && GATED.has(n.id);
    setChip(n.id, val, isNa);
    nodeGById[n.id].classList.toggle("na", isNa);
    if (n.id === "industry") industryNa = isNa;
    if (n.id === "emptype") emptypeNa = isNa;
  });
  // dim the "if employed" edges feeding the skipped nodes
  edgeEls.forEach(e => {
    if (e.kind === "employed") {
      const na = (e.dst === "industry" && industryNa) || (e.dst === "emptype" && emptypeNa);
      e.el.classList.toggle("na-dim", na);
    }
  });
}

function clearOverlay() {
  svg.classList.remove("show-values");
  SPEC.nodes.forEach(n => nodeGById[n.id].classList.remove("na"));
  edgeEls.forEach(e => e.el.classList.remove("na-dim"));
}

function clearIndividual() {
  curIndex = null;
  idInput.value = "";
  clearOverlay();
  if (selectedId) select(selectedId);
}

idInput.addEventListener("change", () => {
  const v = parseInt(idInput.value, 10);
  if (Number.isFinite(v)) selectIndividual(v);
});
prevBtn.addEventListener("click", () => selectIndividual((curIndex == null ? 0 : curIndex - 1)));
nextBtn.addEventListener("click", () => selectIndividual((curIndex == null ? 0 : curIndex + 1)));
randBtn.addEventListener("click", () => { if (POP) selectIndividual(Math.floor(Math.random() * POP.individuals.length)); });
clearBtn.addEventListener("click", clearIndividual);

// ---- embedded snapshot auto-load ----
// Reconstruct full individual objects (matching the schema the picker consumes)
// from the compact array-of-arrays embedded in the #embedded-pop island. Columns
// are mapped by name from the payload header, so the row layout is not hardcoded
// twice. Missing/empty/unparseable island → do nothing (leave the picker as the
// manual path); never throw on page load.
function reconstructFromEmbedded(payload) {
  const cols = payload.columns;
  const ix = {};
  cols.forEach((name, j) => { ix[name] = j; });
  const wrap = v => (v == null ? null : { label: v });
  const individuals = payload.rows.map((r, i) => {
    const attachment = r[ix.attachment], hours = r[ix.hours], industry = r[ix.industry_sector];
    return {
      id: i,
      age: r[ix.age],
      biological_sex: { label: r[ix.sex_label] },
      education_level: wrap(r[ix.education_level]),
      employment_status: wrap(r[ix.employment_status]),
      socioeconomic_class: wrap(r[ix.socioeconomic_class]),
      birth_location: wrap(r[ix.birth_location]),
      region: wrap(r[ix.region]),
      civil_status: wrap(r[ix.civil_status]),
      industry_sector: industry == null ? null : { label: industry },
      employment_type: attachment == null
        ? null
        : { attachment: { label: attachment }, hours: { label: hours } },
      housing_tenure: wrap(r[ix.housing_tenure]),
      household_size: wrap(r[ix.household_size]),
      income_source: wrap(r[ix.income_source]),
      birth_country_detail: wrap(r[ix.birth_country_detail]),
      parental_structure: wrap(r[ix.parental_structure]),
    };
  });
  return { metadata: payload.metadata || {}, individuals };
}

function autoLoadEmbedded() {
  const island = document.getElementById("embedded-pop");
  if (!island) return;
  const raw = island.textContent && island.textContent.trim();
  if (!raw) return;
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (e) {
    return; // malformed island — silently fall back to the manual picker
  }
  if (!payload || !Array.isArray(payload.columns) || !Array.isArray(payload.rows) || payload.rows.length === 0) {
    return;
  }
  try {
    loadPopulation(reconstructFromEmbedded(payload)); // same path + auto-select id 0
  } catch (e) {
    // any reconstruction hiccup must not break the page; leave the picker usable
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", autoLoadEmbedded);
} else {
  autoLoadEmbedded();
}

// count sanity (module-scope; visible in console only if mismatched)
(function selfCheck() {
  const nNodes = SPEC.nodes.length;
  const nOpt = SPEC.nodes.filter(n => n.option).length;
  if (nNodes !== 14 || edgeEls.length !== 11 || nOpt !== 1) {
    console.error("SPEC count mismatch", { nodes: nNodes, edges: edgeEls.length, options: nOpt });
  }
})();

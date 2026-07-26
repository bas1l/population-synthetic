"use strict";

// "Population statistics" tab — the default/main view.
// For each demographic category in the embedded reference SCB population
// (the July-16 merge-status-edu snapshot baked into #embedded-pop), render the
// proportion of every value as a horizontal bar + percentage.
//
// It reads the columnar #embedded-pop island DIRECTLY rather than the shared
// `POP` global, so it always summarises the baked-in reference population and is
// unaffected by whatever file the Generation-DAG tab may load. Self-contained:
// borrows only CSS classes (.problist/.prob-row) and the embedded data islands.
(function () {
  const root = document.getElementById("stats-root");
  if (!root) return;
  let built = false;

  // --- helpers ---------------------------------------------------------------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, c => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function fmtPct(p) {
    if (p <= 0) return "0%";
    if (p < 0.001) return "<0.1%";
    return (p * 100).toFixed(1) + "%";
  }
  function readIsland(id) {
    const el = document.getElementById(id);
    if (!el) throw new Error(`stats-view: missing data island #${id}`);
    return JSON.parse(el.textContent);
  }
  // Leading integer of a label, for ordinal ordering ("18-24"->18, "2 persons"->2).
  function naturalKey(label) {
    const m = String(label).match(/-?\d+/);
    return m ? Number(m[0]) : Number.POSITIVE_INFINITY;
  }

  // Column key -> presentation label. Order = the generation-ish column order.
  // `applies` = the gate reason: gated columns carry null for non-applicable
  // persons, who are excluded from that attribute's denominator.
  // `badge` = a small annotation chip. `bin: "age"` bins the raw integer age.
  const ATTRS = [
    { key: "age",                  label: "Age", bin: "age" },
    { key: "sex_label",            label: "Biological sex" },
    { key: "education_level",      label: "Education level" },
    { key: "employment_status",    label: "Employment status" },
    { key: "industry_sector",      label: "Industry sector",       applies: "employed persons" },
    { key: "attachment",           label: "Employment attachment", applies: "employed persons" },
    { key: "hours",                label: "Working hours",         applies: "employed persons" },
    { key: "income_source",        label: "Income source" },
    { key: "socioeconomic_class",  label: "Socioeconomic class" },
    { key: "civil_status",         label: "Civil status" },
    { key: "birth_location",       label: "Birth location", badge: "deprecated from analysis" },
    { key: "birth_country_detail", label: "Birth country (detail)", applies: "foreign-born persons" },
    { key: "region",               label: "Region" },
    { key: "parental_structure",   label: "Parental structure" },
    { key: "housing_tenure",       label: "Housing tenure" },
    { key: "household_size",       label: "Household size" },
  ];
  // Ordinal columns keep natural (numeric) order; the rest sort by share, desc.
  const ORDINAL = new Set(["age", "household_size"]);

  function ageBinner(bounds) {
    // bounds: [[min, max, label], ...]; population is 18-85 so out-of-range
    // draws (if any) clamp to the nearest edge band rather than vanish.
    return function (age) {
      const a = Number(age);
      for (const b of bounds) if (a >= b[0] && a <= b[1]) return b[2];
      if (!bounds.length) return String(age);
      return a < bounds[0][0] ? bounds[0][2] : bounds[bounds.length - 1][2];
    };
  }

  function tally(rows, colIdx, mapFn) {
    const counts = new Map();
    let applicable = 0;
    for (const r of rows) {
      const v = r[colIdx];
      if (v === null || v === undefined || v === "") continue;
      applicable++;
      const key = mapFn ? mapFn(v) : String(v);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return { counts, applicable };
  }

  function barRowsHtml(entries, ordinal) {
    const total = entries.reduce((s, e) => s + e[1], 0);
    const list = entries.slice();
    if (ordinal) list.sort((a, b) => naturalKey(a[0]) - naturalKey(b[0]));
    else list.sort((a, b) => b[1] - a[1]);
    const maxC = list.reduce((m, e) => Math.max(m, e[1]), 0) || 1; // bar scaled to max for contrast; % is exact
    return list.map(([lbl, c]) => {
      const p = total ? c / total : 0;
      const w = (c / maxC) * 100;
      return `<div class="prob-row"><i class="radio"></i>` +
        `<span class="pv">${esc(lbl)}</span>` +
        `<div class="pbar"><i style="width:${w.toFixed(1)}%"></i></div>` +
        `<span class="pp" title="${c.toLocaleString()} of ${total.toLocaleString()}">${fmtPct(p)}</span></div>`;
    }).join("");
  }

  function metaCardHtml(meta) {
    const gen = meta.generated_at ? String(meta.generated_at).slice(0, 10) : "—";
    const items = [
      ["Source", meta.source || "—"],
      ["Individuals", meta.n != null ? Number(meta.n).toLocaleString() : "—"],
      ["Seed", meta.seed != null ? meta.seed : "—"],
      ["Data vintage", meta.data_vintage || "—"],
      ["Generated", gen],
    ];
    return `<div class="sv-meta">` + items.map(([k, v]) =>
      `<div class="sv-meta-item"><span class="sv-meta-k">${esc(k)}</span><span class="sv-meta-v">${esc(v)}</span></div>`
    ).join("") + `</div>`;
  }

  function build() {
    if (built) return;
    built = true;
    let pop, dist;
    try {
      pop = readIsland("embedded-pop");
      dist = readIsland("embedded-dist");
    } catch (e) {
      root.innerHTML = `<p class="sv-error">${esc(e.message)}</p>`;
      return;
    }
    const cols = pop.columns || [];
    const rows = pop.rows || [];
    const ix = {};
    cols.forEach((c, j) => { ix[c] = j; });
    const total = rows.length;
    const binAge = ageBinner((dist.constants && dist.constants.AGE_GROUP_BOUNDS) || []);

    const parts = [metaCardHtml(pop.metadata || {})];
    for (const a of ATTRS) {
      const j = ix[a.key];
      if (j === undefined) continue; // column absent from this population -> skip
      const { counts, applicable } = tally(rows, j, a.bin === "age" ? binAge : null);
      const entries = Array.from(counts.entries());
      const gated = applicable < total;
      const badge = a.badge ? `<span class="sv-badge">${esc(a.badge)}</span>` : "";
      const denom = gated
        ? `applies to ${applicable.toLocaleString()} of ${total.toLocaleString()} (${fmtPct(applicable / total)})` +
          (a.applies ? ` — ${esc(a.applies)} only` : "")
        : `n = ${applicable.toLocaleString()}`;
      parts.push(
        `<section class="sv-block">` +
        `<div class="sv-head"><h3>${esc(a.label)}</h3>${badge}` +
        `<span class="sv-count">${entries.length} value${entries.length === 1 ? "" : "s"}</span></div>` +
        `<span class="sv-denom">${denom}</span>` +
        `<div class="problist">${barRowsHtml(entries, ORDINAL.has(a.key))}</div>` +
        `</section>`
      );
    }
    root.innerHTML = parts.join("");
  }

  window.buildStats = build;
  // Default/main tab: render immediately — the data islands precede this script
  // in the DOM, so they are already parsed by the time this runs.
  build();
})();

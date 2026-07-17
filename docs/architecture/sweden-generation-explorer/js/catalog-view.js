"use strict";

// "By output category" view — one block per output attribute. Each block lays the
// candidate SCB source tables side by side (no edges: they are alternatives, not a
// chain). Clicking a table box renders its detail panel on the right, where the
// user picks values for the table's filter categories; for the fetched table the
// sliced output distribution recomputes live.
//
// Reuses globals declared by dag-view.js (loaded before this file) and data.js:
//   DIST, resolveNode, probListHtml, esc, chipRow, fmtGroup, AGE_GROUPS,
//   SPEC, CATALOG_SOURCES.
(function () {
  const root = document.getElementById("catalog-root");
  if (!root) return;

  const C = (typeof DIST !== "undefined" && DIST && DIST.constants) || {};
  const OVERRIDES = (typeof CATALOG_SOURCES !== "undefined" && CATALOG_SOURCES) || {};

  // ---- filter-field option lists, derived from the embedded distributions so
  //      every offered value is one resolveNode() can actually slice ----
  function ascii(s) { return /^[\x00-\x7F]*$/.test(String(s)); }

  const SEX_OPTS = C.SEX_CODES ? Object.keys(C.SEX_CODES) : ["men", "women"];

  function bucketOptions(condField, part, mapObj) {
    const cond = (typeof DIST !== "undefined" && DIST && DIST.conditional && DIST.conditional[condField]) || null;
    if (!cond || !mapObj) return [];
    const present = new Set(Object.keys(cond).map(k => k.split("|")[part]));
    return Object.keys(mapObj).filter(k => ascii(k) && present.has(mapObj[k]));
  }
  // distinct values of one "|"-joined key component across a conditional field.
  function keyParts(condField, part) {
    const cond = (typeof DIST !== "undefined" && DIST && DIST.conditional && DIST.conditional[condField]) || null;
    if (!cond) return [];
    return Array.from(new Set(Object.keys(cond).map(k => k.split("|")[part]))).filter(ascii);
  }
  // employment_status (inc_emp role) → register status labels whose income bucket is
  // present in the income dist. Education IS a live conditioning dimension again: the
  // status×education merge is now the DEFAULT path, so employment conditions on
  // age×education×sex — EDU_OPTS are the casefolded ISCED97 labels keying that merge.
  const EDU_OPTS = keyParts("employment_status_by_edu", 1);
  const EMP_OPTS = bucketOptions("income_source_by_employment_age", 0, C.STATUS_TO_INC_EMP);

  const ROLE_FIELD = { age_group: "age_group", inc_age: "age_group", sex: "sex", education: "education", inc_emp: "employment_status" };
  const FIELD_LABEL = { age_group: "age group", sex: "sex", education: "education", employment_status: "employment status" };
  function fieldOptions(field) {
    if (field === "age_group") return AGE_GROUPS || [];
    if (field === "sex") return SEX_OPTS;
    if (field === "education") return EDU_OPTS;
    if (field === "employment_status") return EMP_OPTS;
    return [];
  }
  // distinct filter fields a DIST-backed node conditions on (parent roles → fields)
  function liveFieldsFor(nodeId) {
    const sc = (typeof DIST !== "undefined" && DIST && DIST.schema && DIST.schema[nodeId]) || null;
    if (!sc || !sc.parents || !sc.parents.length) return [];
    const out = [];
    sc.parents.forEach(r => { const f = ROLE_FIELD[r]; if (f && out.indexOf(f) < 0) out.push(f); });
    return out;
  }

  const TAG_LABEL = { used: "used by sampler", chosen: "candidate", declared: "declared, unused", alt: "alternative", merge: "opt-in merge" };
  function titleize(s) { s = String(s); return s.charAt(0).toUpperCase() + s.slice(1); }
  function shortId(id) { const parts = String(id).split("/"); return parts[parts.length - 1] || id; }

  // ---- card model: the table boxes for one output category ----
  function cardsForNode(node) {
    const ov = OVERRIDES[node.id];
    if (ov && ov.tables && ov.tables.length) {
      return ov.tables.map(t => ({
        id: t.id, name: t.name, query: t.query, outputs: t.outputs || [],
        note: t.note || "", tag: t.tag || "alt", ageNote: t.ageNote || "",
        filters: t.filters || null, nodeId: t.nodeId || null,
      }));
    }
    return [{
      id: node.table, name: node.tableName, query: node.query, outputs: node.categories || [],
      note: node.note || "", tag: "used", ageNote: "", filters: null, nodeId: node.id,
    }];
  }

  function condSummary(card) {
    if (card.nodeId) {
      const fs = liveFieldsFor(card.nodeId).map(f => FIELD_LABEL[f] || f);
      return fs.length ? fs.join(" · ") : "marginal";
    }
    if (card.filters && card.filters.length) return card.filters.map(f => f.label).join(" · ");
    return "marginal";
  }

  function ctxFor(block) {
    const s = block.sel;
    return {
      age: null,
      age_group: s.age_group || (AGE_GROUPS && AGE_GROUPS[0]) || null,
      sex: s.sex || SEX_OPTS[0] || null,
      education: s.education || EDU_OPTS[0] || null,
      employment_status: s.employment_status || EMP_OPTS[0] || null,
      birth_location: null,
    };
  }

  // ---- rendering ----
  function renderBoxes(block) {
    return block.cards.map((c, i) => {
      const on = i === block.selIdx;
      return `<button type="button" class="tbox k-${esc(block.node.kind)} ${esc(c.tag)}${on ? " sel" : ""}" data-idx="${i}" aria-pressed="${on}">`
        + `<span class="tbox-tag">${esc(TAG_LABEL[c.tag] || c.tag)}</span>`
        + `<span class="tbox-id">${esc(shortId(c.id))}</span>`
        + `<span class="tbox-cond">| ${esc(condSummary(c))}</span>`
        + `</button>`;
    }).join("");
  }

  function liveFilterHtml(block, field) {
    const opts = fieldOptions(field);
    const cur = block.sel[field];
    const chips = opts.map(o => {
      const on = o === cur;
      const disp = field === "age_group" ? fmtGroup(o) : titleize(o);
      return `<button type="button" class="filter-opt${on ? " on" : ""}" data-field="${esc(field)}" data-val="${esc(o)}" aria-pressed="${on}">${esc(disp)}</button>`;
    }).join("");
    return `<div class="filtergroup"><div class="fg-label">${esc(FIELD_LABEL[field] || field)}</div><div class="fg-opts">${chips}</div></div>`;
  }

  function staticFilterHtml(block, gi, flt) {
    const cur = block.staticSel[gi];
    const chips = (flt.values || []).map(v => {
      const on = v === cur;
      return `<button type="button" class="filter-opt${on ? " on" : ""}" data-sidx="${gi}" data-val="${esc(v)}" aria-pressed="${on}">${esc(v)}</button>`;
    }).join("");
    return `<div class="filtergroup"><div class="fg-label">${esc(flt.label)}</div><div class="fg-opts">${chips}</div></div>`;
  }

  function renderPanel(block) {
    const card = block.cards[block.selIdx];
    const node = block.node;
    let html = "";
    html += `<div class="cat-taghead"><span class="ttag ${esc(card.tag)}">${esc(TAG_LABEL[card.tag] || card.tag)}</span></div>`;
    html += `<div class="mono cat-tname">${esc(card.name)}</div>`;
    html += `<div class="field"><div class="k">SCB table</div><div class="v mono table-id">${esc(card.id)}</div></div>`;
    html += `<div class="field"><div class="k">PxWeb query</div><div class="v mono">${esc(card.query)}</div></div>`;
    if (card.ageNote) html += `<div class="field"><div class="k">Age granularity</div><div class="v">${esc(card.ageNote)}</div></div>`;
    html += `<div class="field"><div class="k">Output categories (${card.outputs.length})</div>${chipRow(card.outputs)}</div>`;

    html += `<div class="field"><div class="k">Filter categories &mdash; pick a value</div>`;
    if (card.nodeId) {
      const fields = liveFieldsFor(card.nodeId);
      if (!fields.length) html += `<div class="chips"><span class="chip none">none &mdash; marginal (same for everyone)</span></div>`;
      else html += fields.map(f => liveFilterHtml(block, f)).join("");
    } else if (card.filters && card.filters.length) {
      html += card.filters.map((flt, i) => staticFilterHtml(block, i, flt)).join("");
    } else {
      html += `<div class="chips"><span class="chip none">none</span></div>`;
    }
    html += `</div>`;

    if (card.nodeId && typeof resolveNode === "function") {
      const res = resolveNode(card.nodeId, ctxFor(block));
      if (res) {
        html += `<div class="field"><div class="k">P( ${esc(node.label)} | filters )</div>`;
        if (res.fallback) html += `<div class="cond-line"><span class="fallback">(${esc(res.fallback)})</span></div>`;
        html += probListHtml(card.nodeId, res, null, false);
        html += `</div>`;
      } else {
        html += `<div class="note-box">No embedded distribution available for this slice.</div>`;
      }
    } else {
      html += `<div class="note-box">Distribution not embedded &mdash; this table is not fetched by the pipeline, so no probabilities are shown. The filter categories above are the real breakdowns the table offers.</div>`;
    }
    if (card.note) html += `<div class="note-box marg">${esc(card.note)}</div>`;

    block.panelEl.innerHTML = html;
    attachFilterHandlers(block);
  }

  function attachFilterHandlers(block) {
    block.panelEl.querySelectorAll(".filter-opt").forEach(btn => {
      btn.addEventListener("click", () => {
        if (btn.dataset.field != null) block.sel[btn.dataset.field] = btn.dataset.val;
        else if (btn.dataset.sidx != null) block.staticSel[btn.dataset.sidx] = btn.dataset.val;
        renderPanel(block);
      });
    });
  }

  function selectCard(block, idx) {
    if (idx < 0 || idx >= block.cards.length) return;
    block.selIdx = idx;
    const card = block.cards[idx];
    if (card.nodeId) liveFieldsFor(card.nodeId).forEach(f => { if (block.sel[f] == null) block.sel[f] = fieldOptions(f)[0] || null; });
    block.boxesEl.innerHTML = renderBoxes(block);
    renderPanel(block);
  }

  function buildBlock(node) {
    const block = { node: node, cards: cardsForNode(node), selIdx: 0, sel: {}, staticSel: {} };
    const ov = OVERRIDES[node.id];
    const n = block.cards.length;
    const section = document.createElement("section");
    section.className = "cat-block";
    section.innerHTML =
      `<div class="cat-head"><h3>${esc(node.label)}</h3>`
      + `<span class="cat-sub">${n > 1 ? n + " candidate tables" : "1 table"}</span></div>`
      + (ov && ov.intro ? `<p class="cat-insight">${esc(ov.intro)}</p>` : "")
      + `<div class="cat-body"><div class="cat-boxes"></div><aside class="cat-panel"></aside></div>`;
    root.appendChild(section);
    block.boxesEl = section.querySelector(".cat-boxes");
    block.panelEl = section.querySelector(".cat-panel");
    block.boxesEl.addEventListener("click", ev => {
      const b = ev.target.closest(".tbox");
      if (b) selectCard(block, parseInt(b.dataset.idx, 10));
    });
    selectCard(block, 0);
    return block;
  }

  let built = false;
  // Lazy: build only when the catalog tab is first opened (keeps DAG view fast).
  window.buildCatalog = function buildCatalog() {
    if (built) return;
    built = true;
    if (typeof SPEC === "undefined" || !SPEC.nodes) return;
    SPEC.nodes.forEach(buildBlock);
  };
})();

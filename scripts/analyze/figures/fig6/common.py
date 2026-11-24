"""Shared data + layout for the Figure 6 gallery (P01..Pnn): why generated individuals are lost.

Data (read-only):
  * validation_attrition/swedish_02_attrition.csv   funnel per combination (Figure 6's source)
  * figure6_labelling_2026-10-19/figure6_answer_labels.xlsx   label per distinct unmapped answer
        final label = author_label if filled, else suggested_label  (A = LLM failure,
        B = statistics-table limitation, M = mapping gap)
  * figure6_labelling_2026-10-19/persona_unmapped_answers.csv   persona -> unmapped answers
        joined on (attribute, key_id); key_id prefixes collide across attributes
        (hou* = housing_tenure and household_size, emp* = employment_type and
        employment_status), so the attribute is part of the key.
  * realism_ranking/swedish_02/worst_clash_split.csv   class C per combination (of 100 selected)

Persona rule (precedence A > B > M): lost to the LLM if any unmapped answer is A; else to the
tables if any is B; else (all M) to our mapping.

Denominator (the author, 2026-10-19): every share is of the FINISHED individuals, raw_valid in the
attrition CSV (= generated minus those failing the raw completeness check, validate_raw). The
incomplete individuals are out of scope and appear in no design, so in every cell
retained + LLM + tables + mapping = 100% of finished, and the retained share is clean / raw_valid
(not the published retention_rate = clean / generated). The attrition data are not edited.

Every statistic is computed here and handed to the drawing code as finished numbers.
"""
from __future__ import annotations
import os

import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ["DATA_DIR"])
ANALYSIS = DATA / "03_Analysis"
LABDIR = DATA / "figure6_labelling_2026-10-19"
COUNTRY = "swedish_02"

from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from population_synthetic.analysis.utils.cap_index import load_cap_index  # noqa: E402
from population_synthetic.analysis.utils.labels import (  # noqa: E402
    attribute_label, figure_term, method_key_lines, method_letters, model_labels,
)
from population_synthetic.analysis.utils.model_order import ranked_model_order  # noqa: E402
from population_synthetic.analysis.utils.palette import (  # noqa: E402
    BASELINE_DARK, FOOTNOTE_GREY, HOST_COLORS, MUTED_GREY,
)
from population_synthetic.analysis.utils.style import LEGEND_LABEL, TICK_LABEL, TICK_LABEL_LARGE  # noqa: E402
from population_synthetic.analysis.utils.table_style import HOST_LABELS  # noqa: E402

# --------------------------------------------------------------------------- causes
CAUSES = ["retained", "llm", "mapping", "tables"]
CAUSE_LABEL = {
    "retained": "retained",
    "llm": "LLM failure",
    "mapping": "mapping gap",
    "tables": "table limit",
    "incomplete": "incomplete",
    "classc": "combination outside SCB definitions",
    "llm_alsoB": "LLM failure + table limit",
}
# Okabe-Ito categorical. LLM = black (the set's own black), so neither cause hue sits next to
# the hosted blue / locally-served orange of the model labels. Mapping = bluish green and
# tables = reddish purple, the colours the worst-clash palette already gives "pipeline" and
# "C: SCB category limitation" (the same meanings).
CAUSE_COLOR = {
    "retained": "#E4E4E4",
    "llm": "#000000",
    "mapping": "#009E73",
    "tables": "#CC79A7",
    "incomplete": "#FFFFFF",
    "classc": "#CC79A7",
}
LABEL_TO_CAUSE = {"A": "llm", "M": "mapping", "B": "tables"}

# --------------------------------------------------------------------------- funnel
_att = pd.read_csv(ANALYSIS / "validation_attrition" / f"{COUNTRY}_attrition.csv")
_att["excluded"] = _att["excluded"].astype(str).str.lower().eq("true")
assert len(_att) == 65 and _att.slug.is_unique
assert (_att.clean == _att.mapped_valid).all(), "clean != mapped_valid: another gate rejects"
STRATS = strategy_complexity_order(sorted(_att.strategy.unique()))
LETTER = method_letters(STRATS)
METHODS = [LETTER[s] for s in STRATS]
KEY_LINES = method_key_lines(STRATS)


@lru_cache(None)
def _models():
    perf = json.load(open(ANALYSIS / "model_ranking" / f"{COUNTRY}_performance.json", encoding="utf-8"))
    ranked = ranked_model_order(perf, load_cap_index(DATA))
    extra = sorted(set(_att.model) - set(ranked))
    for m in extra:
        assert _att.loc[_att.model == m, "excluded"].all(), m
    return ranked + extra


MODELS = _models()
assert len(MODELS) == 13
# Display names: labels.py, plus the two version suffixes the published Figure 6 artwork prints.
LABEL_OVERRIDES = {"claude_haiku": "Claude Haiku 4.5", "claude_sonnet": "Claude Sonnet 5"}
MLAB = model_labels(MODELS)
MLAB.update({m: v for m, v in LABEL_OVERRIDES.items() if m in MLAB})


def _hosting():
    from population_synthetic.analysis.model_ranking.hosting import classify_hosting, load_hosting_config
    from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values
    repo = Path(os.environ["POPSYNTH_REPO"])
    return classify_hosting(discover_axis_values("models"),
                            load_hosting_config(repo / "config" / "analysis" / "model_ranking" / "provider_hosting.json"))


HOSTING = {m: _hosting()[m] for m in MODELS}
REFERENCE = figure_term("reference")

# --------------------------------------------------------------------------- labels + join
_x = pd.read_excel(LABDIR / "figure6_answer_labels.xlsx", sheet_name=None)
_lab = pd.concat([v for k, v in _x.items() if "author_label" in v.columns], ignore_index=True)
_lab["final"] = _lab.author_label.where(_lab.author_label.notna(), _lab.suggested_label).astype(str).str.strip()
assert set(_lab.final) <= {"A", "B", "M"}, set(_lab.final)
assert not _lab.duplicated(["attribute", "key_id"]).any()
N_AUTHOR_OVERRIDES = int(_lab.author_label.notna().sum())
N_AUTHOR_CHANGED = int((_lab.author_label.notna() & (_lab.author_label != _lab.suggested_label)).sum())

# Which (persona, attribute) pairs are unmapped NOW is read from validate_mapped (one CSV per
# combination), so a re-run of mapping/validate_mapped/population_cap/validation_attrition is picked
# up without code changes: answers the fixed config now maps simply drop out. The label of each
# still-unmapped pair comes from the labelled snapshot (persona_unmapped_answers.csv joined to the
# xlsx on (attribute, key_id)). A pair the snapshot does not hold -- an answer that was not unmapped
# when the sheet was built, e.g. after re-generation -- raises: it needs labelling first.
_snap = pd.read_csv(LABDIR / "persona_unmapped_answers.csv", encoding="utf-8-sig")
_snap = _snap.merge(_lab[["attribute", "key_id", "normalised_key", "final"]], on=["attribute", "key_id"],
                    how="left", suffixes=("", "_lab"), validate="many_to_one")
assert _snap.final.notna().all(), "snapshot answers without a label (attribute, key_id)"
assert not _snap.duplicated(["combination", "persona", "attribute"]).any()
N_KEY_MISMATCH = int((_snap.normalised_key.fillna("") != _snap.normalised_key_lab.fillna("")).sum())
N_SNAPSHOT = len(_snap)

#: FIG6_SOURCE=snapshot pins the unmapped set to the labelled snapshot (the state P01-P14 were drawn
#: from, before the 2026-10-19 16:2x mapping re-run); unset or "live" reads validate_mapped as it is now.
import os  # noqa: E402

SOURCE = os.environ.get("FIG6_SOURCE", "live")
if SOURCE not in ("live", "snapshot"):
    raise ValueError(f"FIG6_SOURCE must be 'live' or 'snapshot', got {SOURCE!r}")
_vm_rows = []
for slug in ([] if SOURCE == "snapshot" else _att.slug):
    v = pd.read_csv(ANALYSIS / "validate_mapped" / f"{slug}.csv", dtype={"unmapped_fields": str})
    rv = pd.read_csv(ANALYSIS / "validate_raw" / f"{slug}.csv")
    raw_ok = set(rv.loc[rv.passed.astype(str).str.lower() == "true", "persona_id"])
    fail = v[(v.passed.astype(str).str.lower() != "true") & v.persona_id.isin(raw_ok)]
    for pid, f in zip(fail.persona_id, fail.unmapped_fields.fillna("")):
        attrs = [x for x in f.split(";") if x]
        assert attrs, f"{slug}/{pid} failed validate_mapped without an unmapped field"
        _vm_rows += [(slug, pid, a) for a in attrs]
_vm = (pd.DataFrame(_vm_rows, columns=["combination", "persona", "attribute"]) if SOURCE == "live"
       else _snap[["combination", "persona", "attribute"]].copy())
ANS = _vm.merge(_snap, on=["combination", "persona", "attribute"], how="left", validate="one_to_one")
_new = ANS[ANS.final.isna()]
if len(_new):
    raise ValueError(f"{len(_new)} unmapped (persona, attribute) pairs have no label in the snapshot; "
                     f"first: {_new.head(5).to_dict('records')}")
N_SNAPSHOT_RESOLVED = N_SNAPSHOT - len(ANS)   # snapshot answers no longer unmapped (0 before the re-run)
ANS["cause"] = ANS.final.map(LABEL_TO_CAUSE)

_p = ANS.groupby(["combination", "persona"]).final.agg(lambda s: "".join(sorted(set(s))))
PERSONA = _p.rename("labels").reset_index()
# Precedence (coordinator, 2026-10-19): A > B > M -- a persona with a mapping gap AND a table
# limit is lost to the tables, since fixing our mapping would not save it. The briefed order
# A > M > B is kept as CAUSE_AMB for the claim check; the two differ only on the B+M personas.
PRECEDENCE = "ABM"


def _cause(labels: pd.Series, order: str) -> np.ndarray:
    first, second = order[0], order[1]
    return np.where(labels.str.contains(first), LABEL_TO_CAUSE[first],
                    np.where(labels.str.contains(second), LABEL_TO_CAUSE[second], LABEL_TO_CAUSE[order[2]]))


PERSONA["cause_AMB"] = _cause(PERSONA.labels, "AMB")
PERSONA["cause_ABM"] = _cause(PERSONA.labels, "ABM")
PERSONA["cause"] = PERSONA[f"cause_{PRECEDENCE}"]
N_ORDER_DIFF = int((PERSONA.cause_AMB != PERSONA.cause_ABM).sum())
assert N_ORDER_DIFF == int(PERSONA.labels.eq("BM").sum())
MIXED = PERSONA.labels.value_counts().to_dict()
# LLM-lost individuals that ALSO gave at least one table-limit answer (A and B): drawn as a hatched
# sub-slice of the LLM slice wherever a design has one.
PERSONA["llm_alsoB"] = (PERSONA.cause == "llm") & PERSONA.labels.str.contains("B")

# --------------------------------------------------------------------------- per combination
_cnt = PERSONA.pivot_table(index="combination", columns="cause", values="persona", aggfunc="count", fill_value=0)
C = _att.set_index("slug")[["model", "strategy", "generated", "raw_valid", "mapped_valid", "clean",
                            "selected", "retention_rate", "excluded"]].copy()
for c in ("llm", "mapping", "tables"):
    C[c] = _cnt.reindex(C.index)[c].fillna(0).astype(int) if c in _cnt else 0
C["llm_alsoB"] = PERSONA[PERSONA.llm_alsoB].groupby("combination").size().reindex(C.index).fillna(0).astype(int)
C["retained"] = C.clean
C["finished"] = C.raw_valid                     # the denominator of every share
C["incomplete"] = C.generated - C.raw_valid     # reported in facts only; drawn nowhere
assert (C.llm + C.mapping + C.tables == C.raw_valid - C.mapped_valid).all(), "rejected != labelled personas"
assert (C[["retained", "llm", "mapping", "tables"]].sum(axis=1) == C.finished).all()
for c in CAUSES:
    C[f"s_{c}"] = C[c] / C.finished
assert np.allclose(C.s_retained, C.clean / C.raw_valid), "retained share != clean / raw_valid"
C["rejected"] = C.llm + C.mapping + C.tables
C["s_llm_alsoB"] = C.llm_alsoB / C.finished
C["method"] = C.strategy.map(LETTER)

_wc = pd.read_csv(ANALYSIS / "realism_ranking" / COUNTRY / "worst_clash_split.csv")
_wc = _wc[~_wc.is_real_reference.astype(bool)].set_index("slug")
C["classc"] = _wc.n_c_scb_category_limitation.reindex(C.index)
C["classc_n"] = _wc.n_individuals.reindex(C.index)
assert C.loc[~C.excluded, "classc"].notna().all() and C.loc[C.excluded, "classc"].isna().all()
assert (C.classc.fillna(0) <= C.selected).all()
C["r3_impossible"] = _wc.n_r3_impossible.reindex(C.index)
_sel = C[~C.excluded]
SEL_BY_METHOD = _sel.groupby("method").selected.sum().reindex(METHODS)
WC_IMPOSSIBLE = {"total": int(_sel.r3_impossible.sum()),
                 "by_method": _sel.groupby("method").r3_impossible.sum().reindex(METHODS)}
HOST_LABEL_SHORT = {"hosted": "hosted", "local": "locally served"}
REF_CLASSC = _wc_ref = int(pd.read_csv(ANALYSIS / "realism_ranking" / COUNTRY / "worst_clash_split.csv")
                           .query("is_real_reference").n_c_scb_category_limitation.iloc[0])

# CELL[method][model] -> row (Series) ; withdrawn flag kept, never dropped
CELL = {m: {} for m in METHODS}
for slug, r in C.iterrows():
    CELL[r.method][r.model] = r
assert all(len(CELL[m]) == 13 for m in METHODS)


def matrix(key: str, *, mask_withdrawn: bool = False) -> np.ndarray:
    out = np.array([[CELL[m][mod][key] for mod in MODELS] for m in METHODS], float)
    if mask_withdrawn:
        wd = withdrawn_mask()
        out[wd] = np.nan
    return out


def withdrawn_mask() -> np.ndarray:
    return np.array([[bool(CELL[m][mod].excluded) for mod in MODELS] for m in METHODS])


# --------------------------------------------------------------------------- per attribute
ATTRS_ALL = sorted(ANS.attribute.unique())
ALAB = {a: attribute_label(a) for a in ATTRS_ALL}
# occurrences by label per attribute
OCC = ANS.pivot_table(index="attribute", columns="cause", values="persona", aggfunc="count", fill_value=0)
OCC = OCC.reindex(columns=["llm", "mapping", "tables"], fill_value=0)
OCC["total"] = OCC.sum(axis=1)
OCC = OCC.sort_values("total", ascending=False)
ATTRS = list(OCC.index)
# table-limit occurrences by attribute x strategy
TAB_AS = ANS[ANS.cause == "tables"].merge(C[["method"]], left_on="combination", right_index=True) \
    .pivot_table(index="attribute", columns="method", values="persona", aggfunc="count", fill_value=0) \
    .reindex(index=ATTRS, columns=METHODS, fill_value=0)
# personas lost to the tables, by the attribute(s) that carried the B answer
TAB_PERS_ATTR = ANS[ANS.cause == "tables"].merge(PERSONA[PERSONA.cause == "tables"][["combination", "persona"]]) \
    .groupby("attribute").persona.count().reindex(ATTRS, fill_value=0)

# --------------------------------------------------------------------------- pooled summaries
def pooled(by: str) -> pd.DataFrame:
    g = C.groupby(by)[["generated", "finished", "retained", "llm", "mapping", "tables", "incomplete",
                       "llm_alsoB"]].sum()
    for c in CAUSES + ["llm_alsoB"]:
        g[f"s_{c}"] = g[c] / g.finished
    return g


BY_METHOD = pooled("method").reindex(METHODS)
BY_MODEL = pooled("model").reindex(MODELS)
C["hosting"] = C.model.map(HOSTING)
BY_HOST = pooled("hosting")
TOTAL = C[["generated", "finished", "retained", "llm", "mapping", "tables", "incomplete", "llm_alsoB"]].sum()

# --------------------------------------------------------------------------- shared furniture
def method_key_text() -> list[str]:
    """Two lines of the A-E key, in the graphic."""
    parts = [k.replace(" — ", " ") for k in KEY_LINES]
    title = figure_term("strategy_key_title")
    return [f"{title}:  " + "   ".join(parts[:3]), "   ".join(parts[3:])]


def host_handles():
    from matplotlib.patches import Patch
    return [Patch(facecolor=HOST_COLORS[c], edgecolor="none", label=HOST_LABELS[c]) for c in ("hosted", "local")]


def alsoB_handle():
    from matplotlib.patches import Patch
    return Patch(facecolor=CAUSE_COLOR["llm"], edgecolor=CAUSE_COLOR["tables"], hatch="////", linewidth=0,
                 label=CAUSE_LABEL["llm_alsoB"])


def cause_handles(causes=("retained", "llm", "mapping", "tables"), *, edge=True, alsoB=False):
    from matplotlib.patches import Patch
    out = []
    for c in causes:
        out.append(Patch(facecolor=CAUSE_COLOR[c], edgecolor=MUTED_GREY if c in ("retained", "incomplete") else "none",
                         linewidth=0.4, label=CAUSE_LABEL[c]))
        if c == "llm" and alsoB:
            out.append(alsoB_handle())
    return out


# --------------------------------------------------------------------------- exclusive A/B groups (P23+)
# Mapping gaps ignored: an individual is grouped by its A and B answers only. "mapping_only" (M and
# nothing else) is not drawn in the A/B designs and is reported in their note.
PERSONA["group"] = np.select(
    [PERSONA.labels.str.contains("A") & PERSONA.labels.str.contains("B"),
     PERSONA.labels.str.contains("A"), PERSONA.labels.str.contains("B")],
    ["both", "llm_only", "tables_only"], default="mapping_only")
GROUPS = ["llm_only", "both", "tables_only"]
_g = PERSONA.pivot_table(index="combination", columns="group", values="persona", aggfunc="count", fill_value=0)
for k in GROUPS + ["mapping_only"]:
    C[f"g_{k}"] = _g.reindex(C.index)[k].fillna(0).astype(int) if k in _g else 0
    C[f"sg_{k}"] = C[f"g_{k}"] / C.finished
assert (C[[f"g_{k}" for k in GROUPS + ["mapping_only"]]].sum(axis=1) == C.rejected).all()
CELL = {m: {} for m in METHODS}   # rebuilt so the cell rows carry the group columns
for slug, r in C.iterrows():
    CELL[r.method][r.model] = r
GROUP_TOTAL = {k: int(C[f"g_{k}"].sum()) for k in GROUPS + ["mapping_only"]}
BY_METHOD_G = C.groupby("method")[[f"g_{k}" for k in GROUPS] + ["finished"]].sum().reindex(METHODS)

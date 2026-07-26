"""Unit tests for the persona-realism IO / plotting / reporting layer (Phase 4).

Covers the pure sinks (``csv_writer``, ``report``) on a fixture ``RealismStats``,
the cost aggregation + cost-coverage marker, and the ``artifacts`` orchestrator's
idempotent-skip behaviour over a tiny stub verdict cache. No live judge / CLI and
no matplotlib display (charts use the ``Agg`` backend via ``save_figure``).
"""

from __future__ import annotations

import csv
import dataclasses
import json

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.generation_metadata.pricing import PricingTable
from population_synthetic.analysis.persona_realism import artifacts as A
from population_synthetic.analysis.persona_realism.csv_writer import FIELDNAMES, RealismRow, write_realism_csv
from population_synthetic.analysis.persona_realism.judge import Issue, RoundVerdict
from population_synthetic.analysis.persona_realism.reduce import reduce_combo, reduce_persona
from population_synthetic.analysis.persona_realism.report import write_combo_report, write_run_report
from population_synthetic.analysis.persona_realism.runner import JudgeConfig
from population_synthetic.analysis.persona_realism.stats import compute_realism_stats

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"
_BOOT = {"iterations": 200, "seed": 20260723, "ci_level": 0.95}
# Price every selectable judge dropdown model (mirrors model_pricing.yaml raw-string
# rows) so cost lookups resolve whichever model the judge config defaults to.
_PRICING = PricingTable(
    rates={
        "claude-sonnet-5": (3.0, 15.0),
        "claude-opus-4-8": (5.0, 25.0),
        "claude-haiku-4-5": (1.0, 5.0),
        "claude-fable-5": (10.0, 50.0),
    },
    observed_date="2026-07-23", source="unit-test", currency="USD",
)


def _cfg() -> JudgeConfig:
    return JudgeConfig.load(_CONFIG_DIR)


def _possible(typicality, issues=()):
    return RoundVerdict(can_exist=True, typicality=typicality, issues=tuple(issues), reasoning="")


def _impossible(issues=(Issue(("age_group", "education_level"), "S3", "hard"),)):
    return RoundVerdict(can_exist=False, typicality=None, issues=tuple(issues), reasoning="")


def _combo():
    p1 = reduce_persona([_possible(8), _possible(9)], persona_id="p1")
    p2 = reduce_persona([_possible(3), _possible(4)], persona_id="p2")
    p3 = reduce_persona([_impossible(), _impossible()], persona_id="p3")
    return reduce_combo([p1, p2, p3], "combo_x")


def _scb_ref():
    return reduce_combo(
        [reduce_persona([_possible(5), _possible(5)], persona_id=f"s{i}") for i in range(3)],
        "real_swedish",
    )


def _stats(combo=None, scb=None):
    return compute_realism_stats(combo or _combo(), scb or _scb_ref(), bootstrap=_BOOT)


# --------------------------------------------------------------------------- #
# csv_writer                                                                   #
# --------------------------------------------------------------------------- #


def test_realism_row_fieldnames_match_dataclass():
    assert FIELDNAMES == tuple(f.name for f in dataclasses.fields(RealismRow))


def test_write_realism_csv_roundtrip(tmp_path):
    stats = _stats()
    validation = {"agreement": 0.9, "recall_on_rule_impossibilities": 1.0}
    row = A._build_row(stats, {"total_tokens": 300, "usd": 0.5}, validation)
    path = write_realism_csv([row], tmp_path / "combo_x.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert tuple(reader.fieldnames) == FIELDNAMES
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["combo_label"] == "combo_x"
    assert rows[0]["n_personas"] == "3"
    assert rows[0]["total_tokens"] == "300"
    assert rows[0]["hard_rules_agreement"] == "0.9"


# --------------------------------------------------------------------------- #
# report writers                                                              #
# --------------------------------------------------------------------------- #


def test_write_combo_report_carries_meta_and_validity_anchor(tmp_path):
    stats = _stats()
    path = write_combo_report(
        tmp_path / "combo_x.json",
        stats=stats,
        clash_taxonomy=[{"pair": ["age_group", "education_level"], "severity": "S3", "n_personas": 1}],
        cost={"usd": 0.01, "total_tokens": 300},
        cost_coverage={"judged_this_run": 3, "total_personas": 3, "status": "complete"},
        validation={"agreement": 0.9, "recall_on_rule_impossibilities": 1.0},
        provenance={"judge_model": "claude-fable-5", "n_rounds": 3},
        pricing={"observed_date": "2026-07-23", "source": "unit-test", "currency": "USD"},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["process"] == "persona_realism"
    assert payload["combo_label"] == "combo_x"
    # reliability is labelled self-consistency; the hard-rules block is the validity anchor.
    assert "reliability_note" in payload and "validity" in payload["reliability_note"].lower()
    assert payload["hard_rules_validation"]["agreement"] == 0.9
    assert payload["cost_coverage"]["status"] == "complete"
    assert payload["provenance"]["judge_model"] == "claude-fable-5"
    # impossibility/dispersion/reliability blocks are serialised verbatim from stats.
    assert payload["impossibility"]["rate"] == pytest.approx(1.0 / 3.0)


def test_write_run_report_structure(tmp_path):
    path = write_run_report(
        tmp_path / "run_report.json",
        combos=[{"combo_label": "combo_x", "n_personas": 3}],
        headline={"measure": "variance", "reference": "real_swedish", "points": []},
        provenance={"judge_model": "claude-fable-5"},
        pricing={"currency": "USD"},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["headline_map"]["measure"] == "variance"
    assert payload["combos"][0]["combo_label"] == "combo_x"


# --------------------------------------------------------------------------- #
# cost aggregation + cost-coverage marker                                     #
# --------------------------------------------------------------------------- #


def _write_cache(combo_dir, persona_id, attributes, verdicts):
    """Write one persona verdict cache at the combo root (no ``raw/`` subdir)."""
    combo_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "persona_id": persona_id,
        "combo": "combo_x",
        "judge_model": "claude-fable-5",
        "n_rounds": len(verdicts),
        "successful_rounds": len(verdicts),
        "failed_rounds": 0,
        "status": "complete",
        "attributes": attributes,
        "rounds": [dataclasses.asdict(v) for v in verdicts],
    }
    (combo_dir / f"{persona_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(out_dir, persona_ids, *, tokens=(100, 50)):
    """Write one ``persona_XXXXX.jsonl`` telemetry file per persona at the combo root."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for pid in persona_ids:
        line = json.dumps({
            "persona_id": pid, "category": "persona_realism", "method": "judge",
            "prompt_tokens": tokens[0], "completion_tokens": tokens[1], "total_tokens": sum(tokens),
        })
        (out_dir / f"{pid}.jsonl").write_text(line + "\n", encoding="utf-8")


def test_combo_cost_sums_tokens_and_reports_complete_coverage(tmp_path):
    out_dir = tmp_path / "combo_x"
    _write_jsonl(out_dir, ["persona_00000", "persona_00001"])
    cost, coverage = A._combo_cost(out_dir, "claude-fable-5", _PRICING, n_cached_personas=2)
    assert cost["total_tokens"] == 300
    assert cost["usd"] == pytest.approx(2 * (100 * 10 / 1e6 + 50 * 50 / 1e6))
    assert coverage == {"judged_this_run": 2, "total_personas": 2, "status": "complete"}


def test_combo_cost_complete_coverage_on_resume(tmp_path):
    # Telemetry is now per-persona and 1:1 with the verdict cache, so a resumed run
    # has one .jsonl per cached persona -> coverage is complete (no truncation gap).
    out_dir = tmp_path / "combo_x"
    _write_jsonl(out_dir, ["persona_00000", "persona_00001", "persona_00002"])
    _cost, coverage = A._combo_cost(out_dir, "claude-fable-5", _PRICING, n_cached_personas=3)
    assert coverage["judged_this_run"] == 3 and coverage["total_personas"] == 3
    assert coverage["status"] == "complete"


def test_combo_cost_partial_on_genuine_per_file_gap(tmp_path):
    # The only residual partial case: fewer per-persona telemetry files than cached
    # verdicts (a genuine gap), not a whole-run truncation artefact.
    out_dir = tmp_path / "combo_x"
    _write_jsonl(out_dir, ["persona_00000"])  # one log, but more personas cached
    _cost, coverage = A._combo_cost(out_dir, "claude-fable-5", _PRICING, n_cached_personas=5)
    assert coverage["judged_this_run"] == 1 and coverage["total_personas"] == 5
    assert coverage["status"] == "partial"


def test_combo_cost_no_log_is_none_status(tmp_path):
    out_dir = tmp_path / "combo_x"
    out_dir.mkdir()
    cost, coverage = A._combo_cost(out_dir, "claude-fable-5", _PRICING, n_cached_personas=3)
    assert cost["usd"] is None and cost["n_calls"] == 0
    assert coverage["status"] == "none"


def test_combo_cost_fail_fast_on_missing_pricing_row(tmp_path):
    out_dir = tmp_path / "combo_x"
    _write_jsonl(out_dir, ["persona_00000"])
    empty = PricingTable(rates={}, observed_date="x", source="x", currency="USD")
    with pytest.raises(KeyError):
        A._combo_cost(out_dir, "claude-fable-5", empty, n_cached_personas=1)


# --------------------------------------------------------------------------- #
# artifacts orchestrator: idempotent skip + force                             #
# --------------------------------------------------------------------------- #


def _seed_combo_dir(tmp_path):
    out_dir = tmp_path / "combo_x"
    attrs = {"age_group": "25-34", "education_level": "Upper-Secondary"}
    _write_cache(out_dir, "persona_00000", attrs, [_possible(8), _possible(9)])
    _write_cache(out_dir, "persona_00001", attrs, [_possible(3), _possible(4)])
    _write_cache(out_dir, "persona_00002", attrs, [_impossible(), _impossible()])
    _write_jsonl(out_dir, ["persona_00000", "persona_00001", "persona_00002"])
    return out_dir


def test_write_combo_artifacts_writes_all_and_is_idempotent(tmp_path):
    out_dir = _seed_combo_dir(tmp_path)
    ca = A.write_combo_artifacts(
        out_dir, "combo_x",
        scb_ref=_scb_ref(), cfg=_cfg(), dpi=80, force=False,
        hard_rules=(), pricing=_PRICING,
    )
    expected = {
        out_dir / "combo_x.csv", out_dir / "combo_x.json",
        out_dir / "typicality.png", out_dir / "typicality.svg",
        out_dir / "clash_taxonomy.png", out_dir / "clash_taxonomy.svg",
    }
    assert expected.issubset(set(ca.paths))
    for p in expected:
        assert p.exists(), p
    assert ca.stats.combo_label == "combo_x"
    assert ca.cost_coverage["status"] == "complete"
    # cost flowed into the row and the report.
    report = json.loads((out_dir / "combo_x.json").read_text(encoding="utf-8"))
    assert report["cost"]["total_tokens"] == 450  # 3 personas x 150

    # Re-run without force must not fail and must leave the files in place.
    mtimes = {p: p.stat().st_mtime_ns for p in expected}
    ca2 = A.write_combo_artifacts(
        out_dir, "combo_x",
        scb_ref=_scb_ref(), cfg=_cfg(), dpi=80, force=False,
        hard_rules=(), pricing=_PRICING,
    )
    assert expected.issubset(set(ca2.paths))
    for p in expected:
        assert p.stat().st_mtime_ns == mtimes[p], f"{p} was rewritten on a no-force re-run"


def test_write_combo_artifacts_force_rewrites(tmp_path):
    out_dir = _seed_combo_dir(tmp_path)
    A.write_combo_artifacts(out_dir, "combo_x", scb_ref=_scb_ref(), cfg=_cfg(), dpi=80,
                            force=False, hard_rules=(), pricing=_PRICING)
    csv_path = out_dir / "combo_x.csv"
    before = csv_path.stat().st_mtime_ns
    A.write_combo_artifacts(out_dir, "combo_x", scb_ref=_scb_ref(), cfg=_cfg(), dpi=80,
                            force=True, hard_rules=(), pricing=_PRICING)
    assert csv_path.stat().st_mtime_ns != before


def test_write_headline_map_renders_map_and_summary(tmp_path):
    scb_dir = _seed_combo_dir(tmp_path / "scb")
    combo_dir = _seed_combo_dir(tmp_path / "syn")
    cfg = _cfg()
    scb_combo, _present = A.load_combo_realism(scb_dir, "real_swedish")
    scb_ca = A.write_combo_artifacts(scb_dir, "real_swedish", scb_ref=None, cfg=cfg, dpi=80,
                                     force=True, hard_rules=(), pricing=_PRICING)
    syn_ca = A.write_combo_artifacts(combo_dir, "combo_x", scb_ref=scb_combo, cfg=cfg, dpi=80,
                                     force=True, hard_rules=(), pricing=_PRICING)
    out_root = tmp_path / "root"
    A.write_headline_map([scb_ca, syn_ca], out_root, cfg=cfg, dpi=80, force=True,
                         scb_label="real_swedish", pricing=_PRICING)
    assert (out_root / "headline_map.png").exists()
    assert (out_root / "headline_map.svg").exists()
    assert (out_root / "realism_summary.csv").exists()
    run_report = json.loads((out_root / "run_report.json").read_text(encoding="utf-8"))
    labels = {p["label"]: p for p in run_report["headline_map"]["points"]}
    assert labels["real_swedish"]["is_reference"] is True
    assert labels["real_swedish"]["dispersion_distance"] == 0.0
    assert "combo_x" in labels
    # combined CSV carries one row per combo.
    with open(out_root / "realism_summary.csv", newline="", encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == 2

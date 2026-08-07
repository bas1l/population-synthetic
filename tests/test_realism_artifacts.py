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
from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.persona_realism.report import write_combo_report
from population_synthetic.analysis.persona_realism.stats import compute_realism_stats
from population_synthetic.analysis.persona_realism.clash_explanations_csv import (
    FIELDNAMES as EXPLANATION_FIELDNAMES,
)
from population_synthetic.analysis.utils.realism_clash_csv import (
    FIELDNAMES as CLASH_FIELDNAMES,
)
from population_synthetic.analysis.utils.realism_clash_csv import (
    SCHEMA_VERSION as CLASH_CSV_SCHEMA_VERSION,
)
from population_synthetic.analysis.utils.realism_clash_csv import read_realism_clashes_csv
from population_synthetic.analysis.utils.realism_csv import (
    SEVERITY_COUNT_FIELDS,
    SEVERITY_LEVELS,
    read_realism_personas_csv,
)

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


def _stats(combo=None):
    return compute_realism_stats(combo or _combo(), bootstrap=_BOOT)


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
        cfg=_cfg(), dpi=80, force=False,
        hard_rules=(), pricing=_PRICING,
    )
    expected = {
        out_dir / "combo_x.csv", out_dir / "combo_x.json", out_dir / "combo_x_personas.csv",
        out_dir / "combo_x_clashes.csv", out_dir / "combo_x_clash_explanations.csv",
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
        cfg=_cfg(), dpi=80, force=False,
        hard_rules=(), pricing=_PRICING,
    )
    assert expected.issubset(set(ca2.paths))
    for p in expected:
        assert p.stat().st_mtime_ns == mtimes[p], f"{p} was rewritten on a no-force re-run"


def test_write_combo_artifacts_force_rewrites(tmp_path):
    out_dir = _seed_combo_dir(tmp_path)
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80,
                            force=False, hard_rules=(), pricing=_PRICING)
    csv_path = out_dir / "combo_x.csv"
    before = csv_path.stat().st_mtime_ns
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80,
                            force=True, hard_rules=(), pricing=_PRICING)
    assert csv_path.stat().st_mtime_ns != before


# --------------------------------------------------------------------------- #
# per-combination isolation: no field depends on any other combination        #
# --------------------------------------------------------------------------- #


def test_combo_report_carries_no_reference_dependent_field(tmp_path):
    """The split's load-bearing property: a combination's report describes only itself.

    A ``distance_to_scb`` / ``variance_equality`` / ``scb_reference`` key here would mean
    the file could not be produced without first judging a *different* combination --
    the connascence of execution order the split exists to remove.
    """
    out_dir = _seed_combo_dir(tmp_path)
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    report = json.loads((out_dir / "combo_x.json").read_text(encoding="utf-8"))
    dispersion = report["dispersion"]
    for banned in ("distance_to_scb", "variance_equality", "scb_reference"):
        assert banned not in dispersion, banned
    assert set(FIELDNAMES).isdisjoint(
        {"dist_variance", "dist_entropy", "dist_tail_coverage",
         "variance_equality_stat", "variance_equality_p"}
    )


def test_combo_artifacts_are_byte_identical_regardless_of_order(tmp_path):
    """Judging a slug before or after any other slug produces identical bytes.

    Two combo dirs seeded from the same verdicts are written in opposite orders; if
    anything in the artifact layer accumulated state across units (a reference held in
    memory, a running aggregate), the two reports would differ.
    """
    first = _seed_combo_dir(tmp_path / "a")
    second = _seed_combo_dir(tmp_path / "b")
    cfg = _cfg()

    A.write_combo_artifacts(first, "combo_x", cfg=cfg, dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    other = _seed_combo_dir(tmp_path / "other")
    A.write_combo_artifacts(other, "combo_y", cfg=cfg, dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    A.write_combo_artifacts(second, "combo_x", cfg=cfg, dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)

    for name in ("combo_x.json", "combo_x.csv", "combo_x_personas.csv",
                 "combo_x_clashes.csv", "combo_x_clash_explanations.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_personas_csv_row_count_matches_report_n_personas(tmp_path):
    """The completeness marker the aggregator gates on."""
    out_dir = _seed_combo_dir(tmp_path)
    A.write_combo_artifacts(
        out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
        country="swedish", model="claude_haiku", strategy="all_pick",
        hard_rules=(), pricing=_PRICING,
    )
    report = json.loads((out_dir / "combo_x.json").read_text(encoding="utf-8"))
    rows = read_realism_personas_csv(out_dir / "combo_x_personas.csv",
                                     expected_rows=report["n_personas"])
    assert len(rows) == 3
    by_id = {r.persona_id: r for r in rows}
    # The impossible persona: majority false, and NO typicality at all -- absent, not 0.0.
    assert by_id["persona_00002"].can_exist_majority is False
    assert by_id["persona_00002"].typicality_mean is None
    assert by_id["persona_00002"].max_severity == "S3"
    # A possible persona keeps its per-round series and its axis identity.
    assert by_id["persona_00000"].typicality_rounds == (8, 9)
    assert by_id["persona_00000"].can_exist_true_votes == 2
    assert by_id["persona_00000"].model == "claude_haiku"
    assert by_id["persona_00000"].is_real_reference is False


def test_personas_csv_marks_the_real_competitor_without_model_or_strategy(tmp_path):
    out_dir = _seed_combo_dir(tmp_path)
    A.write_combo_artifacts(
        out_dir, "real_swedish", cfg=_cfg(), dpi=80, force=True,
        country="swedish", is_real_reference=True, hard_rules=(), pricing=_PRICING,
    )
    rows = read_realism_personas_csv(out_dir / "real_swedish_personas.csv")
    assert rows and all(r.is_real_reference for r in rows)
    assert all(r.model == "" and r.strategy == "" for r in rows)


def test_personas_csv_carries_per_severity_counts_from_the_verdict_cache(tmp_path):
    """The severity dimension's input, sourced from the cached clashes -- no re-judging.

    The persona below carries an S3 *and* an S2 in the same round, so it must be
    countable at both levels; ``max_severity`` alone would file it under S3 and hide the
    S2 entirely.
    """
    out_dir = tmp_path / "combo_x"
    attrs = {"age_group": "25-34", "education_level": "Upper-Secondary"}
    both = _impossible(issues=(
        Issue(("age_group", "education_level"), "S3", "hard"),
        Issue(("income_bracket", "occupation"), "S2", "near"),
    ))
    _write_cache(out_dir, "persona_00000", attrs, [both, both])
    _write_cache(out_dir, "persona_00001", attrs,
                 [_possible(7, issues=(Issue(("a", "b"), "S1", "unusual"),))] * 2)
    _write_cache(out_dir, "persona_00002", attrs, [_possible(8), _possible(8)])
    _write_jsonl(out_dir, ["persona_00000", "persona_00001", "persona_00002"])

    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    rows = {r.persona_id: r
            for r in read_realism_personas_csv(out_dir / "combo_x_personas.csv")}

    double = rows["persona_00000"]
    assert double.max_severity == "S3"                       # the partition view
    assert double.clash_count_s3 == 1 and double.clash_count_s2 == 1   # both countable
    assert double.clash_count_s1 == 0
    assert double.clash_count == 2

    assert rows["persona_00001"].clash_count_s1 == 1
    assert rows["persona_00001"].clash_count_s2 == 0
    # A clean persona is at zero on every level.
    clean = rows["persona_00002"]
    assert (clean.clash_count_s1, clean.clash_count_s2, clean.clash_count_s3) == (0, 0, 0)
    assert clean.max_severity == ""


def test_personas_csv_row_count_mismatch_raises(tmp_path):
    out_dir = _seed_combo_dir(tmp_path)
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    with pytest.raises(ValueError, match="n_personas=99"):
        read_realism_personas_csv(out_dir / "combo_x_personas.csv", expected_rows=99)


# --------------------------------------------------------------------------- #
# per-clash CSV + explanation side file                                        #
# --------------------------------------------------------------------------- #

#: Attributes covering every axis the clash fixtures below name, so a value join
#: succeeds unless a test deliberately makes it fail.
_CLASH_ATTRS = {
    "age_group": "25-34", "education_level": "Upper-Secondary",
    "income_bracket": "Low", "occupation": "Student",
}


def _seed_clash_combo_dir(tmp_path):
    """Three personas x two rounds: one with two clashes, one with one, one clean."""
    out_dir = tmp_path / "combo_x"
    both = _impossible(issues=(
        Issue(("age_group", "education_level"), "S3", "hard, with a comma"),
        Issue(("income_bracket", "occupation"), "S2", "near"),
    ))
    _write_cache(out_dir, "persona_00000", _CLASH_ATTRS, [both, both])
    _write_cache(out_dir, "persona_00001", _CLASH_ATTRS,
                 [_possible(7, issues=(Issue(("occupation", "age_group"), "S1", "unusual"),))] * 2)
    _write_cache(out_dir, "persona_00002", _CLASH_ATTRS, [_possible(8), _possible(8)])
    _write_jsonl(out_dir, ["persona_00000", "persona_00001", "persona_00002"])
    return out_dir


def _expected_clash_counts(personas_csv):
    """The per-level distinct-clash totals the personas CSV declares."""
    rows = read_realism_personas_csv(personas_csv)
    return {
        level: sum(getattr(r, SEVERITY_COUNT_FIELDS[level]) for r in rows)
        for level in SEVERITY_LEVELS
    }


def test_clashes_csv_reconciles_with_the_personas_csv(tmp_path):
    """The completeness invariant: the same quantity, counted from two files.

    Distinct ``(persona, pair, severity)`` per level in ``{combo}_clashes.csv`` must
    equal the summed ``clash_count_s{L}`` of ``{combo}_personas.csv``. Both are
    written from one pass over one verdict cache, so a disagreement means the tree
    holds two generations of the same combination.
    """
    out_dir = _seed_clash_combo_dir(tmp_path)
    A.write_combo_artifacts(
        out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
        country="swedish_02", model="claude_haiku", strategy="all_pick_v2",
        hard_rules=(), pricing=_PRICING,
    )
    personas_csv = out_dir / "combo_x_personas.csv"
    expected = _expected_clash_counts(personas_csv)
    assert expected == {"S3": 1, "S2": 1, "S1": 1}

    rows = read_realism_clashes_csv(
        out_dir / "combo_x_clashes.csv",
        expected_counts=expected, expected_counts_source=personas_csv,
    )
    # 2 clashes x 2 rounds for the first persona, 1 x 2 for the second, none for the third.
    assert len(rows) == 6
    assert sorted({r.round_index for r in rows}) == [0, 1]      # the round dimension survives
    assert all(r.slug == "combo_x" and r.model == "claude_haiku" for r in rows)
    joined = {(r.attr_a, r.attr_b): r for r in rows}
    assert joined[("age_group", "education_level")].value_a == "25-34"
    assert joined[("age_group", "education_level")].value_b == "Upper-Secondary"
    # The judge named (occupation, age_group); the row carries the sorted pair.
    assert ("age_group", "occupation") in joined
    assert not any(r.unresolved for r in rows)


def test_clashes_csv_reconciliation_raises_on_a_corrupted_file(tmp_path):
    """Deleting a clash from the file must be caught, naming both files and the fix."""
    out_dir = _seed_clash_combo_dir(tmp_path)
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    clashes_csv = out_dir / "combo_x_clashes.csv"
    personas_csv = out_dir / "combo_x_personas.csv"
    kept = [ln for ln in clashes_csv.read_text(encoding="utf-8").splitlines() if ",S1," not in ln]
    clashes_csv.write_text("\n".join(kept) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="rewrite-artifacts"):
        read_realism_clashes_csv(
            clashes_csv,
            expected_counts=_expected_clash_counts(personas_csv),
            expected_counts_source=personas_csv,
        )


def test_clashes_csv_rejects_an_uncanonical_attribute_pair(tmp_path):
    """A pair written the other way round would rank one driver twice."""
    out_dir = _seed_clash_combo_dir(tmp_path)
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    clashes_csv = out_dir / "combo_x_clashes.csv"
    swapped = clashes_csv.read_text(encoding="utf-8").replace(
        "age_group,education_level", "education_level,age_group",
    )
    clashes_csv.write_text(swapped, encoding="utf-8")
    with pytest.raises(ValueError, match="unsorted"):
        read_realism_clashes_csv(clashes_csv)


def test_clashes_csv_is_header_only_when_no_clash_was_raised(tmp_path):
    """"No clashes" must stay distinguishable from "never processed"."""
    out_dir = tmp_path / "combo_clean"
    _write_cache(out_dir, "persona_00000", _CLASH_ATTRS, [_possible(8), _possible(9)])
    _write_cache(out_dir, "persona_00001", _CLASH_ATTRS, [_possible(6), _possible(7)])
    _write_jsonl(out_dir, ["persona_00000", "persona_00001"])
    A.write_combo_artifacts(out_dir, "combo_clean", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)

    clashes_csv = out_dir / "combo_clean_clashes.csv"
    explanations_csv = out_dir / "combo_clean_clash_explanations.csv"
    assert clashes_csv.read_text(encoding="utf-8").splitlines() == [",".join(CLASH_FIELDNAMES)]
    assert explanations_csv.read_text(encoding="utf-8").splitlines() == [
        ",".join(EXPLANATION_FIELDNAMES)
    ]
    assert read_realism_clashes_csv(clashes_csv, expected_counts={}) == []


def test_a_persona_with_no_successful_round_contributes_no_clash_rows(tmp_path):
    """It is uncached by construction: absent from these rows, present in n_failed."""
    out_dir = _seed_clash_combo_dir(tmp_path)
    roster = ["persona_00000", "persona_00001", "persona_00002", "persona_00003"]
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            expected_ids=roster, hard_rules=(), pricing=_PRICING)
    report = json.loads((out_dir / "combo_x.json").read_text(encoding="utf-8"))
    assert report["n_failed"] == 1 and report["n_personas"] == 3
    rows = read_realism_clashes_csv(out_dir / "combo_x_clashes.csv")
    assert "persona_00003" not in {r.persona_id for r in rows}


def test_a_hallucinated_attribute_is_written_unresolved_and_does_not_fail_the_run(tmp_path):
    out_dir = tmp_path / "combo_x"
    _write_cache(out_dir, "persona_00000", _CLASH_ATTRS,
                 [_possible(7, issues=(Issue(("age_group", "zodiac_sign"), "S2", "invented"),))])
    _write_jsonl(out_dir, ["persona_00000"])
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    (row,) = read_realism_clashes_csv(out_dir / "combo_x_clashes.csv")
    assert row.unresolved is True
    assert (row.value_a, row.value_b) == ("", "")
    # It is still a counted clash: the personas CSV declares it, and the two reconcile.
    read_realism_clashes_csv(
        out_dir / "combo_x_clashes.csv",
        expected_counts=_expected_clash_counts(out_dir / "combo_x_personas.csv"),
    )


def test_clash_explanations_side_file_joins_row_for_row(tmp_path):
    out_dir = _seed_clash_combo_dir(tmp_path)
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    clashes = read_realism_clashes_csv(out_dir / "combo_x_clashes.csv")
    with open(out_dir / "combo_x_clash_explanations.csv", newline="", encoding="utf-8") as fh:
        explanations = list(csv.DictReader(fh))
    key = ("persona_id", "round_index", "attr_a", "attr_b", "severity")
    assert [tuple(str(getattr(r, f)) for f in key) for r in clashes] == [
        tuple(e[f] for f in key) for e in explanations
    ]
    # The free text survives its comma intact (quoted, not split across columns).
    texts = {e["explanation"] for e in explanations}
    assert "hard, with a comma" in texts


def test_clash_csv_schema_version_is_stamped_beside_the_persona_one(tmp_path):
    out_dir = _seed_clash_combo_dir(tmp_path)
    A.write_combo_artifacts(out_dir, "combo_x", cfg=_cfg(), dpi=80, force=True,
                            hard_rules=(), pricing=_PRICING)
    provenance = json.loads((out_dir / "combo_x.json").read_text(encoding="utf-8"))["provenance"]
    assert provenance["clash_csv_schema_version"] == CLASH_CSV_SCHEMA_VERSION
    # Two independently versioned contracts -> two keys, never one folded number.
    assert "persona_csv_schema_version" in provenance

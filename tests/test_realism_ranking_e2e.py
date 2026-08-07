"""End-to-end integration: judge several combinations, then rank them.

Drives the *real* two-task pipeline on a ``tmp_path`` output base with a stubbed judge
client -- no live ``claude`` CLI, no network. Three synthetic combinations and the real
competitor are judged one at a time (each in complete isolation from the others), then
the ranking task consumes what they wrote.

The properties under test are the ones the split exists to guarantee:

* the judge produces combination directories only -- no country-level aggregate;
* judging order does not affect any judged combination's bytes;
* the ranking reads the on-disk contract and needs no re-judging, so it costs nothing
  and can be run repeatedly;
* every declared ranking output appears and the JSON satisfies the honesty contract.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from typing import Any

import matplotlib
import pytest

matplotlib.use("Agg")

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.generation_metadata.pricing import PricingTable  # noqa: E402
from population_synthetic.analysis.model_ranking.loader import scheme_attributes  # noqa: E402
from population_synthetic.analysis.persona_realism import artifacts as A  # noqa: E402
from population_synthetic.analysis.persona_realism.config import JudgeConfig  # noqa: E402
from population_synthetic.analysis.persona_realism.runner import run_combo_judgements  # noqa: E402
from population_synthetic.analysis.realism_ranking.builder import (  # noqa: E402
    build_ranking,
    scb_contrast_rows,
    severity_driver_rows,
    severity_driver_value_rows,
    severity_pair_summary,
    summary_rows,
)
from population_synthetic.analysis.realism_ranking.charts import (  # noqa: E402
    plot_headline_map,
    plot_impossibility_forest,
    plot_impossibility_heatmap,
    plot_severity_heatmap,
    plot_severity_pair_summary,
)
from population_synthetic.analysis.realism_ranking.loader import load_competitors  # noqa: E402
from population_synthetic.analysis.utils.capped_source import MAPPED_SUBDIR  # noqa: E402
from population_synthetic.analysis.utils.figures import save_figure  # noqa: E402
from population_synthetic.analysis.utils.registry import analysis_output_dir  # noqa: E402

from tests.test_persona_realism_smoke import _stub_factory  # noqa: E402

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"
_COUNTRY = "swedish"
_PRICING = PricingTable(
    rates={"claude-sonnet-5": (3.0, 15.0), "claude-fable-5": (10.0, 50.0),
           "claude-opus-4-8": (5.0, 25.0), "claude-haiku-4-5": (1.0, 5.0)},
    observed_date="2026-07-23", source="e2e-test", currency="USD",
)

# Three synthetic combinations spanning two models x two methods, so the factor tests
# have >=2 levels on each axis, plus the real competitor.
_COMBOS = [
    ("swedish_all_pick_claude_haiku", "claude_haiku", "all_pick", 1),
    ("swedish_all_pick_claude_sonnet", "claude_sonnet", "all_pick", 0),
    ("swedish_all_pick_dag_claude_haiku", "claude_haiku", "all_pick_dag", 2),
]
_AXIS_IDS = ([_COUNTRY], ["all_pick", "all_pick_dag"], ["claude_haiku", "claude_sonnet"])


def _cfg() -> JudgeConfig:
    import dataclasses

    return dataclasses.replace(
        JudgeConfig.load(_CONFIG_DIR),
        n_rounds=2, workers=2,
        bootstrap={"iterations": 200, "seed": 20260723, "ci_level": 0.95},
    )


def _population(attrs: list[str], *, n_impossible: int, n_possible: int, offset: int = 0):
    """A tiny mapped population: *n_impossible* contradictory personas, then possible ones.

    The possible personas alternate the stub judge's S2 / S1 clash markers, so every
    severity level has something to attribute: the driver tables are per level, and a
    fixture that only ever produced S3 would leave two thirds of them untested.
    """
    marker = attrs[0]
    people: list[dict[str, Any]] = []
    for i in range(n_impossible + n_possible):
        person = {attr: f"val_{j}" for j, attr in enumerate(attrs)}
        person[marker] = "IMPOSSIBLE" if i < n_impossible else f"TYP{(i + offset) % 9 + 1}"
        if i >= n_impossible:
            person[attrs[1]] = "S2_CLASH" if (i - n_impossible) % 2 == 0 else "S1_CLASH"
        person["id"] = f"persona_{i:05d}"
        people.append(person)
    return people


def _judge(base, label, *, model, strategy, n_impossible, is_real=False, offset=0):
    """Run the judge for one combination, exactly as the driver script does."""
    cfg = _cfg()
    attrs = scheme_attributes(_COUNTRY)
    out_dir = analysis_output_dir("persona_realism", base) / _COUNTRY / label
    population = _population(attrs, n_impossible=n_impossible, n_possible=5, offset=offset)
    summary = run_combo_judgements(
        population, label, attrs, out_dir, cfg, client_factory=_stub_factory(),
    )
    return A.write_combo_artifacts(
        out_dir, label, cfg=cfg, dpi=80, force=True,
        country=_COUNTRY, model=model, strategy=strategy, is_real_reference=is_real,
        expected_ids=list(summary.selected_ids), hard_rules=(), pricing=_PRICING,
    )


def _rank(records, **kwargs):
    """``build_ranking`` with this fixture's driver bounds.

    The bounds are required arguments -- the builder reads no config and the CLI owns
    the defaults -- and this fixture's cells hold a handful of personas, so it ranks
    from one persona up rather than from the CLI's production floor.
    """
    kwargs.setdefault("driver_top_n", 5)
    kwargs.setdefault("driver_min_count", 1)
    return build_ranking(
        records, _COUNTRY, bootstrap=_cfg().bootstrap, variance_center="median", **kwargs
    )


def _write_index(base, slugs):
    mapped = analysis_output_dir("population_cap", base) / MAPPED_SUBDIR
    mapped.mkdir(parents=True, exist_ok=True)
    (mapped / "_index.json").write_text(
        json.dumps([{"slug": slug, "synthetic_file": f"{slug}.json"} for slug in slugs]),
        encoding="utf-8",
    )


@pytest.fixture
def judged_base(tmp_path):
    """An output base with three synthetic combinations and the real competitor judged."""
    base = tmp_path / "base"
    _write_index(base, [slug for slug, *_ in _COMBOS])
    for offset, (slug, model, strategy, n_impossible) in enumerate(_COMBOS):
        _judge(base, slug, model=model, strategy=strategy,
               n_impossible=n_impossible, offset=offset)
    _judge(base, f"real_{_COUNTRY}", model="", strategy="",
           n_impossible=0, is_real=True, offset=3)
    return base


def test_judge_emits_combination_directories_only(judged_base):
    country_root = analysis_output_dir("persona_realism", judged_base) / _COUNTRY
    entries = sorted(p.name for p in country_root.iterdir())
    assert entries == sorted([slug for slug, *_ in _COMBOS] + [f"real_{_COUNTRY}"])
    assert all((country_root / name).is_dir() for name in entries)


def test_ranking_produces_every_declared_output(judged_base, tmp_path):
    records, skipped = load_competitors(judged_base, axis_ids=_AXIS_IDS)
    assert skipped == []
    assert len(records) == 4

    ranking = _rank(records)
    out_dir = tmp_path / "ranking" / _COUNTRY
    out_dir.mkdir(parents=True)

    (out_dir / "realism_ranking.json").write_text(json.dumps(ranking, indent=2), encoding="utf-8")
    for name, rows in (("realism_summary.csv", summary_rows(ranking)),
                       ("scb_contrast.csv", scb_contrast_rows(ranking))):
        assert rows, name
        (out_dir / name).write_text("ok", encoding="utf-8")
    save_figure(plot_headline_map(ranking), out_dir / "headline_map.png", dpi=80)
    save_figure(plot_impossibility_forest(ranking), out_dir / "impossibility_forest.png", dpi=80)
    save_figure(plot_impossibility_heatmap(ranking), out_dir / "impossibility_heatmap.png", dpi=80)
    for level in ("S1", "S2", "S3"):
        save_figure(plot_severity_heatmap(ranking, level),
                    out_dir / f"severity_heatmap_{level.lower()}.png", dpi=80)
        # The heatmap's complement, computed from the records rather than the ranking --
        # it must see the full per-clash series, not the per-cell-truncated driver block.
        save_figure(plot_severity_pair_summary(severity_pair_summary(records, level, top_n=15)),
                    out_dir / f"severity_pair_summary_{level.lower()}.png", dpi=80)

    for name in ("realism_ranking.json", "realism_summary.csv", "scb_contrast.csv",
                 "headline_map.png", "headline_map.svg",
                 "impossibility_forest.png", "impossibility_forest.svg",
                 "impossibility_heatmap.png", "impossibility_heatmap.svg",
                 "severity_heatmap_s1.png", "severity_heatmap_s1.svg",
                 "severity_heatmap_s2.png", "severity_heatmap_s2.svg",
                 "severity_heatmap_s3.png", "severity_heatmap_s3.svg",
                 "severity_pair_summary_s1.png", "severity_pair_summary_s1.svg",
                 "severity_pair_summary_s2.png", "severity_pair_summary_s2.svg",
                 "severity_pair_summary_s3.png", "severity_pair_summary_s3.svg"):
        assert (out_dir / name).is_file(), name


def test_ranking_emits_the_two_severity_driver_tables(judged_base, tmp_path):
    """Judge -> rank on a fresh base produces both driver grains, all levels in one file.

    Serialised through ``csv.DictWriter`` rather than asserted in memory, because the
    flatteners' contract is that every value is a scalar a CSV cell can hold: a nested
    list would round-trip as its ``repr`` and nobody would notice until the table was
    read months later. Written twice to the same bytes, because the merged tables carry
    their level as data and an unstable sort would only show up as a churning diff.
    """
    records, skipped = load_competitors(judged_base, axis_ids=_AXIS_IDS)
    assert skipped == []
    ranking = _rank(records)

    out_dir = tmp_path / "drivers" / _COUNTRY
    out_dir.mkdir(parents=True)
    for name, rows in (
        ("severity_drivers.csv", severity_driver_rows(ranking)),
        ("severity_driver_values.csv", severity_driver_value_rows(ranking)),
    ):
        assert rows, name
        assert {row["severity"] for row in rows} == {"S3", "S2", "S1"}, name
        path = out_dir / name
        for _ in range(2):
            written_before = path.read_bytes() if path.exists() else None
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            if written_before is not None:
                assert path.read_bytes() == written_before, f"{name} is not byte-stable"

    assert sorted(p.name for p in out_dir.iterdir()) == [
        "severity_driver_values.csv", "severity_drivers.csv"]

    # The stub judge's S3 clash is age_group x education_level, and the two contradictory
    # personas of one combination are the cell it drove.
    pair_rows = severity_driver_rows(ranking)
    s3 = [row for row in pair_rows
          if row["severity"] == "S3" and row["slug"] == "swedish_all_pick_dag_claude_haiku"]
    assert [(row["attr_a"], row["attr_b"], row["n_personas"]) for row in s3] == [
        ("age_group", "education_level", 2)
    ]
    assert s3[0]["denominator"] == 7 and s3[0]["penalised"] is True
    # The real population is an ordinary competitor here too, and S1 is not a defect --
    # the one column that keeps an S1 row from reading as one now that they share a file.
    s1 = [row for row in pair_rows if row["severity"] == "S1"]
    assert any(row["is_real_reference"] for row in s1)
    assert all(row["penalised"] is False for row in s1)
    assert all(row["penalised"] is True for row in pair_rows if row["severity"] != "S1")


def test_ranking_json_satisfies_the_honesty_contract(judged_base):
    records, _ = load_competitors(judged_base, axis_ids=_AXIS_IDS)
    cfg = _cfg()
    ranking = _rank(records)

    assert ranking["axis_a"]["correction"] == "holm"
    assert all(e["denominator"] is not None for e in ranking["axis_a"]["ranking"])
    assert {c["id"] for c in ranking["caveats"]} == {
        "pseudo_replication", "single_run_per_combination"
    }
    for contrast in ranking["axis_a"]["scb_contrast"]:
        assert contrast["effect_h"] is not None
        assert contrast["correction"] == "holm"
    prov = ranking["provenance"]
    assert prov["bootstrap_seed"] == cfg.bootstrap["seed"]
    assert prov["n_rounds"] == cfg.n_rounds
    assert len(prov["consumed_artifacts"]) == 4
    # The real population is a ranked competitor, and held out of the factor tests.
    assert any(e["is_real_reference"] for e in ranking["axis_a"]["ranking"])
    assert "" not in ranking["factor_significance"]["by_model"]["groups"]


def test_ranking_is_reproducible_and_re_reads_without_re_judging(judged_base):
    """The aggregator is free to re-run: it reads files and touches no verdict cache."""
    caches = sorted(
        (analysis_output_dir("persona_realism", judged_base) / _COUNTRY).rglob("persona_[0-9]*.json")
    )
    before = {path: path.stat().st_mtime_ns for path in caches}
    assert before, "fixture should have produced verdict caches"

    first = _rank(_loaded(judged_base)[0])
    second = _rank(_loaded(judged_base)[0])

    assert first["axis_a"]["ranking"] == second["axis_a"]["ranking"]
    for path, mtime in before.items():
        assert path.stat().st_mtime_ns == mtime, f"{path} was touched by the ranking task"


def _loaded(base):
    records, _skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    return records, _COUNTRY


def test_judging_order_does_not_change_a_combination_s_bytes(tmp_path):
    """Judge A then B on one base, B then A on another: A's artifacts must match."""
    slug_a, model_a, strategy_a, imp_a = _COMBOS[0]
    slug_b, model_b, strategy_b, imp_b = _COMBOS[1]

    forward = tmp_path / "forward"
    _judge(forward, slug_a, model=model_a, strategy=strategy_a, n_impossible=imp_a)
    _judge(forward, slug_b, model=model_b, strategy=strategy_b, n_impossible=imp_b, offset=1)

    reverse = tmp_path / "reverse"
    _judge(reverse, slug_b, model=model_b, strategy=strategy_b, n_impossible=imp_b, offset=1)
    _judge(reverse, slug_a, model=model_a, strategy=strategy_a, n_impossible=imp_a)

    root = lambda base: analysis_output_dir("persona_realism", base) / _COUNTRY / slug_a  # noqa: E731
    for name in (f"{slug_a}.json", f"{slug_a}.csv", f"{slug_a}_personas.csv"):
        assert (root(forward) / name).read_bytes() == (root(reverse) / name).read_bytes(), name


_SCRIPT = PROJECT_ROOT / "scripts" / "analyze" / "rank_persona_realism.py"
_PAIR_SUMMARIES = tuple(f"severity_pair_summary_s{n}" for n in (1, 2, 3))


def _run_ranking_script(base, *extra):
    """Drive the real CLI on *base* and return the country's output directory.

    A subprocess rather than an in-process call to ``main``: the flags, the argument
    resolution at the edge and the chart wiring are exactly what this test is about, and
    calling the builder directly would assert the test's own emulation of them.
    """
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--country", _COUNTRY,
         "--output-base", str(base), "--force", *extra],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return analysis_output_dir("realism_ranking", base) / _COUNTRY


def test_the_driver_script_emits_the_pair_summaries_and_honours_no_charts(judged_base):
    """The three figures are wired to the CLI, and ``--no-charts`` really skips them."""
    out_dir = _run_ranking_script(judged_base, "--no-charts")
    assert (out_dir / "realism_ranking.json").is_file()
    assert sorted(p.name for p in out_dir.glob("*.png")) == []
    assert sorted(p.name for p in out_dir.glob("*.svg")) == []

    out_dir = _run_ranking_script(judged_base)
    for name in _PAIR_SUMMARIES:
        assert (out_dir / f"{name}.png").is_file(), name
        assert (out_dir / f"{name}.svg").is_file(), name
    # Beside the heatmaps they complement, in the registry-resolved folder.
    assert all((out_dir / f"severity_heatmap_s{n}.png").is_file() for n in (1, 2, 3))


def test_a_single_slug_judged_alone_produces_its_complete_artifact_set(tmp_path):
    """Isolation: no other combination -- and no real competitor -- need exist."""
    base = tmp_path / "solo"
    slug, model, strategy, n_impossible = _COMBOS[0]
    _judge(base, slug, model=model, strategy=strategy, n_impossible=n_impossible)

    combo_dir = analysis_output_dir("persona_realism", base) / _COUNTRY / slug
    for name in (f"{slug}.json", f"{slug}.csv", f"{slug}_personas.csv",
                 "typicality.png", "clash_taxonomy.png"):
        assert (combo_dir / name).is_file(), name
    country_root = combo_dir.parent
    assert [p.name for p in country_root.iterdir()] == [slug]   # no real_* directory
    report = json.loads((combo_dir / f"{slug}.json").read_text(encoding="utf-8"))
    assert "distance_to_scb" not in report["dispersion"]

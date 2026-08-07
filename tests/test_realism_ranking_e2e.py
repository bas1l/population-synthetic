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

import json
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
    summary_rows,
)
from population_synthetic.analysis.realism_ranking.charts import (  # noqa: E402
    plot_headline_map,
    plot_impossibility_forest,
    plot_impossibility_heatmap,
    plot_severity_heatmap,
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
    """A tiny mapped population: *n_impossible* contradictory personas, then possible ones."""
    marker = attrs[0]
    people: list[dict[str, Any]] = []
    for i in range(n_impossible + n_possible):
        person = {attr: f"val_{j}" for j, attr in enumerate(attrs)}
        person[marker] = "IMPOSSIBLE" if i < n_impossible else f"TYP{(i + offset) % 9 + 1}"
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

    cfg = _cfg()
    ranking = build_ranking(records, _COUNTRY, bootstrap=cfg.bootstrap, variance_center="median")
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

    for name in ("realism_ranking.json", "realism_summary.csv", "scb_contrast.csv",
                 "headline_map.png", "headline_map.svg",
                 "impossibility_forest.png", "impossibility_forest.svg",
                 "impossibility_heatmap.png", "impossibility_heatmap.svg",
                 "severity_heatmap_s1.png", "severity_heatmap_s1.svg",
                 "severity_heatmap_s2.png", "severity_heatmap_s2.svg",
                 "severity_heatmap_s3.png", "severity_heatmap_s3.svg"):
        assert (out_dir / name).is_file(), name


def test_ranking_json_satisfies_the_honesty_contract(judged_base):
    records, _ = load_competitors(judged_base, axis_ids=_AXIS_IDS)
    cfg = _cfg()
    ranking = build_ranking(records, _COUNTRY, bootstrap=cfg.bootstrap, variance_center="median")

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
    cfg = _cfg()
    caches = sorted(
        (analysis_output_dir("persona_realism", judged_base) / _COUNTRY).rglob("persona_[0-9]*.json")
    )
    before = {path: path.stat().st_mtime_ns for path in caches}
    assert before, "fixture should have produced verdict caches"

    first = build_ranking(*_loaded(judged_base), bootstrap=cfg.bootstrap, variance_center="median")
    second = build_ranking(*_loaded(judged_base), bootstrap=cfg.bootstrap, variance_center="median")

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

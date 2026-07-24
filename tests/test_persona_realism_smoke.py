"""End-to-end smoke test for the persona-realism subpackage (Phase 5).

Drives the *real* runner -> artifacts pipeline the CLI script drives, but with a
**stubbed** judge client injected via ``run_combo_judgements(..., client_factory=)``
-- no live ``claude`` CLI, no network. A tiny synthetic combo plus a tiny real
reference are judged, reduced, scored, and rendered on a ``tmp_path``; the test
asserts the durable ``raw/`` cache, the per-combo CSV/JSON, the figures, and the
cross-combo ``headline_map`` / ``run_report.json`` are written and that the head
metrics (impossibility rate, dispersion, reliability, cost) are well-formed.

Matplotlib is forced onto the non-interactive ``Agg`` backend before any figure
is built (mirrors the other analysis tests).
"""

from __future__ import annotations

import dataclasses
import json
import re

import matplotlib
import pytest

matplotlib.use("Agg")

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.generation_metadata.pricing import PricingTable  # noqa: E402
from population_synthetic.analysis.model_ranking.loader import scheme_attributes  # noqa: E402
from population_synthetic.analysis.persona_realism import artifacts as A  # noqa: E402
from population_synthetic.analysis.persona_realism.runner import (  # noqa: E402
    JudgeConfig,
    run_combo_judgements,
)

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"
# Price every selectable judge dropdown model (mirrors model_pricing.yaml raw-string
# rows) so cost lookups resolve whichever model the judge config defaults to.
_PRICING = PricingTable(
    rates={
        "claude-sonnet-5": (3.0, 15.0),
        "claude-opus-4-8": (5.0, 25.0),
        "claude-haiku-4-5": (1.0, 5.0),
        "claude-fable-5": (10.0, 50.0),
    },
    observed_date="2026-07-23", source="smoke-test", currency="USD",
)
_TYP_RE = re.compile(r"TYP(\d+)")


# --------------------------------------------------------------------------- #
# stub judge client                                                           #
# --------------------------------------------------------------------------- #


class _StubClient:
    """Deterministic judge stub.

    ``generate_content`` keys entirely off the rendered *user* prompt (the only
    thing the judge layer passes it): a persona carrying the ``IMPOSSIBLE`` marker
    returns a hard (S3) impossible verdict; otherwise it returns a possible verdict
    whose typicality is read from the persona's ``TYP<n>`` marker. ``last_metadata``
    supplies the token telemetry the cost chain aggregates.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.last_metadata: dict[str, object] = {}

    def generate_content(self, user: str, *, model: str, system_instruction: str) -> str:
        self.last_metadata = {
            "provider": "stub", "model": model,
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
            "elapsed_ms": 1,
        }
        if self._fail:
            raise RuntimeError("stub judge failure")
        if "IMPOSSIBLE" in user:
            return json.dumps({
                "can_exist": False,
                "typicality": None,
                "issues": [{
                    "attributes": ["age_group", "education_level"],
                    "severity": "S3",
                    "explanation": "hard contradiction",
                }],
                "reasoning": "impossible",
            })
        match = _TYP_RE.search(user)
        typicality = int(match.group(1)) if match else 5
        return json.dumps({
            "can_exist": True,
            "typicality": typicality,
            "issues": [],
            "reasoning": "possible",
        })


def _stub_factory(*, fail: bool = False):
    return lambda: _StubClient(fail=fail)


# --------------------------------------------------------------------------- #
# fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _cfg() -> JudgeConfig:
    """The real judge config, trimmed for a fast headless run."""
    base = JudgeConfig.load(_CONFIG_DIR)
    return dataclasses.replace(
        base,
        n_rounds=2,
        workers=2,
        bootstrap={"iterations": 200, "seed": 20260723, "ci_level": 0.95},
    )


def _persona(attrs: list[str], marker_attr: str, marker: str) -> dict[str, str]:
    """Build a persona carrying every analyzed axis; the marker rides one axis."""
    persona = {attr: f"val_{i}" for i, attr in enumerate(attrs)}
    persona[marker_attr] = marker
    return persona


def _synthetic_population(attrs: list[str]) -> list[dict[str, str]]:
    marker_attr = attrs[0]
    return [
        _persona(attrs, marker_attr, "TYP8"),         # possible, high typicality
        _persona(attrs, marker_attr, "TYP3"),         # possible, low typicality
        _persona(attrs, marker_attr, "IMPOSSIBLE"),   # S3 hard contradiction
        _persona(attrs, marker_attr, "TYP6"),         # possible, mid typicality
    ]


def _real_population(attrs: list[str]) -> list[dict[str, str]]:
    marker_attr = attrs[0]
    return [
        _persona(attrs, marker_attr, "TYP5"),
        _persona(attrs, marker_attr, "TYP5"),
        _persona(attrs, marker_attr, "TYP4"),
    ]


# --------------------------------------------------------------------------- #
# end-to-end smoke                                                            #
# --------------------------------------------------------------------------- #


def test_persona_realism_end_to_end(tmp_path):
    cfg = _cfg()
    attrs = scheme_attributes("swedish")
    out_root = tmp_path / "persona_realism"
    slug = "swedish_all_pick_claude_haiku"

    # --- real reference -------------------------------------------------------
    real_dir = out_root / "real_swedish"
    real_summary = run_combo_judgements(
        _real_population(attrs), "real_swedish", attrs, real_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert real_summary.failed == 0
    assert real_summary.written == 3
    real_ca = A.write_combo_artifacts(
        real_dir, "real_swedish", scb_ref=None, cfg=cfg, dpi=80, force=True,
        hard_rules=(), pricing=_PRICING,
    )

    # --- synthetic combo (real reference as scb_ref) --------------------------
    syn_dir = out_root / slug
    syn_summary = run_combo_judgements(
        _synthetic_population(attrs), slug, attrs, syn_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert syn_summary.failed == 0
    assert syn_summary.written == 4
    syn_ca = A.write_combo_artifacts(
        syn_dir, slug, scb_ref=real_ca.combo, cfg=cfg, dpi=80, force=True,
        hard_rules=(), pricing=_PRICING,
    )

    # --- per-persona verdict cache -------------------------------------------
    for idx in range(4):
        assert (syn_dir / "raw" / f"persona_{idx:05d}.json").is_file()
    assert (syn_dir / "llm_interactions.jsonl").is_file()

    # --- per-combo artifacts --------------------------------------------------
    for name in (f"{slug}.csv", f"{slug}.json", "typicality.png", "typicality.svg",
                 "clash_taxonomy.png", "clash_taxonomy.svg"):
        assert (syn_dir / name).is_file(), name

    # --- metrics well-formed --------------------------------------------------
    assert syn_ca.stats.n_personas == 4
    assert syn_ca.stats.n_failed == 0
    assert syn_ca.stats.impossibility["rate"] == pytest.approx(0.25)   # 1 of 4 impossible
    assert real_ca.stats.impossibility["rate"] == pytest.approx(0.0)
    # dispersion is characterised against the real reference.
    assert "variance" in syn_ca.stats.dispersion
    assert "distance_to_scb" in syn_ca.stats.dispersion
    # cost flowed from the stubbed telemetry (4 personas x 2 rounds x 150 tokens).
    combo_report = json.loads((syn_dir / f"{slug}.json").read_text(encoding="utf-8"))
    assert combo_report["cost"]["total_tokens"] == 4 * 2 * 150
    assert combo_report["cost"]["usd"] is not None
    assert combo_report["cost_coverage"]["status"] == "complete"

    # --- cross-combo headline map + summary + run report ----------------------
    written = A.write_headline_map(
        [real_ca, syn_ca], out_root, cfg=cfg, dpi=80, force=True,
        scb_label="real_swedish", pricing=_PRICING,
    )
    assert (out_root / "headline_map.png").is_file()
    assert (out_root / "headline_map.svg").is_file()
    assert (out_root / "realism_summary.csv").is_file()
    run_report = json.loads((out_root / "run_report.json").read_text(encoding="utf-8"))
    points = {p["label"]: p for p in run_report["headline_map"]["points"]}
    assert points["real_swedish"]["is_reference"] is True
    assert points["real_swedish"]["dispersion_distance"] == 0.0
    assert slug in points
    assert written  # non-empty list of paths


def test_runner_resumes_without_force(tmp_path):
    """A second run without ``force`` re-judges nothing (skip-if-exists cache)."""
    cfg = _cfg()
    attrs = scheme_attributes("swedish")
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    population = _synthetic_population(attrs)

    first = run_combo_judgements(
        population, "swedish_all_pick_claude_haiku", attrs, combo_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert first.written == 4 and first.skipped == 0

    second = run_combo_judgements(
        population, "swedish_all_pick_claude_haiku", attrs, combo_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert second.skipped == 4 and second.requested == 0


def test_failed_calls_are_distinct_from_possible(tmp_path):
    """A stub that always errors yields failed (uncached) personas, not possible ones."""
    cfg = _cfg()
    attrs = scheme_attributes("swedish")
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"

    summary = run_combo_judgements(
        _synthetic_population(attrs), "swedish_all_pick_claude_haiku", attrs, combo_dir, cfg,
        client_factory=_stub_factory(fail=True),
    )
    assert summary.written == 0
    assert summary.failed == 4
    # No persona cache written for a fully-failed persona (retryable on a later run).
    assert not list((combo_dir / "raw").glob("persona_*.json"))

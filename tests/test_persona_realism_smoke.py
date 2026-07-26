"""End-to-end smoke test for the persona-realism subpackage (Phase 5).

Drives the *real* runner -> artifacts pipeline the CLI script drives, but with a
**stubbed** judge client injected via ``run_combo_judgements(..., client_factory=)``
-- no live ``claude`` CLI, no network. A tiny synthetic combo plus a tiny real
reference are judged, reduced, scored, and rendered on a ``tmp_path``; the test
asserts the durable per-persona ``persona_XXXXX.{json,jsonl}`` cache at the combo
root (no ``raw/`` subdir), the per-combo CSV/JSON, the figures, and the cross-combo
``headline_map`` / ``run_report.json`` are written and that the head metrics
(impossibility rate, dispersion, reliability, cost) are well-formed. A separate
test drives the round-count-aware top-up (rounds=1 -> rounds=2 appends -> skip).

Further tests pin the per-persona INCREMENTAL write contract: each persona writes
its own ``persona_XXXXX.{json,jsonl}`` the moment its rounds finish (not in one
batched end-of-run write), so a later persona sees earlier siblings already on
disk, and a persona whose every round fails is left uncached while its siblings
persist intact -- the interrupt-safety property.

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
    RunnerSummary,
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
    country_root = out_root / "swedish"          # nested one level per country
    slug = "swedish_all_pick_claude_haiku"

    # --- real reference -------------------------------------------------------
    real_dir = country_root / "real_swedish"
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
    syn_dir = country_root / slug
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

    # --- per-persona verdict cache + telemetry (combo root, no raw/) ----------
    for idx in range(4):
        assert (syn_dir / f"persona_{idx:05d}.json").is_file()
        assert (syn_dir / f"persona_{idx:05d}.jsonl").is_file()
    assert not (syn_dir / "raw").exists()
    assert not (syn_dir / "llm_interactions.jsonl").exists()

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

    # --- per-country headline map + summary + run report ----------------------
    written = A.write_headline_map(
        [real_ca, syn_ca], country_root, cfg=cfg, dpi=80, force=True,
        scb_label="real_swedish", pricing=_PRICING,
    )
    assert (country_root / "headline_map.png").is_file()
    assert (country_root / "headline_map.svg").is_file()
    assert (country_root / "realism_summary.csv").is_file()
    run_report = json.loads((country_root / "run_report.json").read_text(encoding="utf-8"))
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


def test_real_sample_size_override_selects_first_n_prefix(tmp_path):
    """``sample_size_override`` caps the real combo to the first-N personas (deterministic
    prefix, not the seeded draw), while a synthetic combo with ``sample_size=None`` judges
    all. Guards the real-reference cap wiring: real population of 5, override=2 -> only
    personas 00000, 00001 are judged (indices 0..N-1)."""
    attrs = scheme_attributes("swedish")
    marker_attr = attrs[0]
    cfg = dataclasses.replace(_cfg(), sample_size=None)  # synthetic combos judge all

    # --- real reference: population of 5, capped to first 2 by the override -----
    real_pop = [_persona(attrs, marker_attr, f"TYP{i}") for i in range(5)]
    real_dir = tmp_path / "swedish" / "real_swedish"
    real_summary = run_combo_judgements(
        real_pop, "real_swedish", attrs, real_dir, cfg,
        client_factory=_stub_factory(), sample_size_override=2,
    )
    assert real_summary.n_selected == 2 and real_summary.written == 2
    # First-N prefix: personas 00000 + 00001 judged; 00002..00004 are not.
    assert (real_dir / "persona_00000.json").is_file()
    assert (real_dir / "persona_00001.json").is_file()
    for idx in (2, 3, 4):
        assert not (real_dir / f"persona_{idx:05d}.json").exists()

    # --- synthetic combo: no override, sample_size=None -> all 4 judged ---------
    syn_dir = tmp_path / "swedish" / "swedish_all_pick_claude_haiku"
    syn_summary = run_combo_judgements(
        _synthetic_population(attrs), "swedish_all_pick_claude_haiku", attrs, syn_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert syn_summary.n_selected == 4 and syn_summary.written == 4


def test_runner_tops_up_rounds_and_appends_telemetry(tmp_path):
    """Re-running at a higher ``--rounds`` appends rounds (verdicts + telemetry).

    rounds=1 -> each persona cached with 1 round + a 1-line telemetry file;
    rounds=2 (no force) -> tops up each persona to 2 rounds and APPENDS the new
    pass's calls to the same ``.jsonl`` (not truncated); a third rounds=2 run skips
    everything (already at the target).
    """
    attrs = scheme_attributes("swedish")
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    population = _synthetic_population(attrs)
    label = "swedish_all_pick_claude_haiku"
    base = _cfg()
    cfg1 = dataclasses.replace(base, n_rounds=1)
    cfg2 = dataclasses.replace(base, n_rounds=2)

    persona0 = combo_dir / "persona_00000.json"
    jsonl0 = combo_dir / "persona_00000.jsonl"

    # --- pass 1: rounds=1 -----------------------------------------------------
    first = run_combo_judgements(population, label, attrs, combo_dir, cfg1,
                                 client_factory=_stub_factory())
    assert first.written == 4 and first.topped_up == 0 and first.skipped == 0
    assert len(json.loads(persona0.read_text(encoding="utf-8"))["rounds"]) == 1
    assert len(jsonl0.read_text(encoding="utf-8").splitlines()) == 1

    # --- pass 2: rounds=2 -> top-up (append, not truncate) --------------------
    second = run_combo_judgements(population, label, attrs, combo_dir, cfg2,
                                  client_factory=_stub_factory())
    assert second.topped_up == 4 and second.written == 0 and second.skipped == 0
    assert second.requested == 4
    payload0 = json.loads(persona0.read_text(encoding="utf-8"))
    assert len(payload0["rounds"]) == 2                 # appended, not overwritten
    assert payload0["successful_rounds"] == 2 and payload0["status"] == "complete"
    assert len(jsonl0.read_text(encoding="utf-8").splitlines()) == 2  # both passes' calls

    # --- pass 3: rounds=2 -> already at target, skip --------------------------
    third = run_combo_judgements(population, label, attrs, combo_dir, cfg2,
                                 client_factory=_stub_factory())
    assert third.skipped == 4 and third.requested == 0 and third.topped_up == 0
    assert len(jsonl0.read_text(encoding="utf-8").splitlines()) == 2  # untouched


def test_runner_force_rejudges_and_truncates_telemetry(tmp_path):
    """``force`` re-judges from scratch: verdict overwritten, telemetry truncated."""
    attrs = scheme_attributes("swedish")
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    population = _synthetic_population(attrs)
    label = "swedish_all_pick_claude_haiku"
    cfg2 = dataclasses.replace(_cfg(), n_rounds=2)
    jsonl0 = combo_dir / "persona_00000.jsonl"

    run_combo_judgements(population, label, attrs, combo_dir, cfg2, client_factory=_stub_factory())
    assert len(jsonl0.read_text(encoding="utf-8").splitlines()) == 2

    forced = run_combo_judgements(population, label, attrs, combo_dir, cfg2, force=True,
                                  client_factory=_stub_factory())
    assert forced.written == 4 and forced.topped_up == 0 and forced.skipped == 0
    # Truncated + re-judged from scratch: still exactly 2 lines (not 4).
    assert len(jsonl0.read_text(encoding="utf-8").splitlines()) == 2
    assert len(json.loads((combo_dir / "persona_00000.json").read_text(encoding="utf-8"))["rounds"]) == 2


def _load_driver():
    """Load the CLI driver script by file path (scripts/ is not an importable package)."""
    import importlib.util

    path = PROJECT_ROOT / "scripts" / "analyze" / "analyze_persona_realism.py"
    spec = importlib.util.spec_from_file_location("analyze_persona_realism", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary(label: str, out_dir, *, written: int = 0, topped_up: int = 0, skipped: int = 0):
    return RunnerSummary(
        combo_label=label, n_selected=written + topped_up + skipped,
        requested=written + topped_up, written=written, topped_up=topped_up,
        skipped=skipped, failed=0, total_rounds=written + topped_up,
        successful_rounds=written + topped_up, failed_rounds=0, passes=1, out_dir=out_dir,
    )


def test_cli_combo_dispatch_tops_up_even_when_report_exists(tmp_path, monkeypatch):
    """The CLI ``_run_one_combo`` must ALWAYS invoke the runner (the per-persona gate
    is the authority), even when the combo report already exists.

    Regression guard for the combo-level ``combo_done`` short-circuit that skipped the
    whole combo -- defeating a ``--rounds 1`` -> ``--rounds 2`` per-persona top-up. Also
    checks the artifact-rewrite decision: a top-up (data changed, files exist) forces a
    rewrite; a no-op leaves artifacts untouched.
    """
    driver = _load_driver()
    cfg = _cfg()
    attrs = scheme_attributes("swedish")
    label = "swedish_all_pick_claude_haiku"
    out_dir = tmp_path / label
    out_dir.mkdir(parents=True)
    (out_dir / f"{label}.json").write_text("{}", encoding="utf-8")  # report already exists

    calls: dict[str, object] = {}

    def _spy_runner(individuals, combo_label, analyzed_attrs, o, c, *, force=False,
                    sample_size_override=None, logger=None):
        calls["runner_called"] = True
        calls["force"] = force
        return _summary(combo_label, o, topped_up=len(individuals))  # runner tops up

    def _spy_artifacts(o, combo_label, *, scb_ref, cfg, dpi, force, hard_rules, pricing, logger=None):
        calls["artifacts_force"] = force
        return object()

    monkeypatch.setattr(driver, "run_combo_judgements", _spy_runner)
    monkeypatch.setattr(driver, "write_combo_artifacts", _spy_artifacts)

    result = driver._run_one_combo(
        label=label, individuals=[{"a": 1}, {"a": 2}], analyzed_attrs=attrs,
        out_dir=out_dir, scb_ref=None, cfg=cfg, dpi=80, force=False,
        hard_rules=(), pricing=_PRICING,
    )
    # Runner was called despite the pre-existing report (gate no longer short-circuits).
    assert calls["runner_called"] is True
    # Runner topped up personas -> artifacts must be force-rewritten (data changed).
    assert calls["artifacts_force"] is True
    assert result is not None


def test_cli_combo_dispatch_skips_rewrite_when_nothing_changed(tmp_path, monkeypatch):
    """When the report exists and the runner does no work, artifacts are NOT rewritten
    (idempotent), but the runner is still consulted (cheap, no LLM)."""
    driver = _load_driver()
    cfg = _cfg()
    attrs = scheme_attributes("swedish")
    label = "swedish_all_pick_claude_haiku"
    out_dir = tmp_path / label
    out_dir.mkdir(parents=True)
    (out_dir / f"{label}.json").write_text("{}", encoding="utf-8")

    calls: dict[str, object] = {}

    def _spy_runner(individuals, combo_label, analyzed_attrs, o, c, *, force=False,
                    sample_size_override=None, logger=None):
        calls["runner_called"] = True
        return _summary(combo_label, o, skipped=len(individuals))  # everything already cached

    def _spy_artifacts(o, combo_label, *, scb_ref, cfg, dpi, force, hard_rules, pricing, logger=None):
        calls["artifacts_force"] = force
        return object()

    monkeypatch.setattr(driver, "run_combo_judgements", _spy_runner)
    monkeypatch.setattr(driver, "write_combo_artifacts", _spy_artifacts)

    driver._run_one_combo(
        label=label, individuals=[{"a": 1}], analyzed_attrs=attrs,
        out_dir=out_dir, scb_ref=None, cfg=cfg, dpi=80, force=False,
        hard_rules=(), pricing=_PRICING,
    )
    assert calls["runner_called"] is True
    assert calls["artifacts_force"] is False  # nothing changed -> no forced rewrite


def test_write_persona_file_derives_age_group_from_raw_age(tmp_path):
    """A real mapped persona carries integer ``age`` (no ``age_group``): the verdict
    file must store a derived ``age_group`` bracket string and NOT crash.

    Reproduce-then-guard for the end-of-run ``_write_persona_file`` KeyError: the
    analyzed axis includes ``age_group`` but the raw mapped record has only ``age``.
    Resolution now goes through the canonical ``attr_value`` accessor (which bins
    ``age``), mirroring ``prompt.render_persona_block``.
    """
    cfg = dataclasses.replace(_cfg(), n_rounds=1)
    attrs = scheme_attributes("swedish")
    assert attrs[0] == "age_group"  # the axis that has no raw column
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    label = "swedish_all_pick_claude_haiku"

    # One persona with raw integer age (42 -> "35-44") and NO pre-binned age_group,
    # every other analyzed axis present, and the stub's TYP marker on a non-age axis.
    persona = {attr: f"val_{i}" for i, attr in enumerate(attrs)}
    del persona["age_group"]
    persona["age"] = 42
    persona[attrs[1]] = "TYP7"

    summary = run_combo_judgements(
        [persona], label, attrs, combo_dir, cfg, client_factory=_stub_factory(),
    )
    assert summary.written == 1 and summary.failed == 0  # did not raise

    payload = json.loads((combo_dir / "persona_00000.json").read_text(encoding="utf-8"))
    assert payload["attributes"]["age_group"] == "35-44"  # derived bracket, not raw 42
    assert payload["attributes"][attrs[1]] == "TYP7"


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
    # No persona cache OR telemetry written for a fully-failed persona (retryable later).
    assert not list(combo_dir.glob("persona_[0-9]*.json"))
    assert not list(combo_dir.glob("persona_[0-9]*.jsonl"))


def test_runner_writes_incrementally_not_batched(tmp_path):
    """Each persona writes its OWN files the instant its rounds finish (incremental),
    not in one end-of-run batch. With ``workers=1`` personas judge in submission order,
    so by the time persona K is judged every earlier persona's verdict file is already
    on disk -- an observation impossible under the old batched end-of-run write.
    """
    attrs = scheme_attributes("swedish")
    marker_attr = attrs[0]
    cfg = dataclasses.replace(_cfg(), n_rounds=1, workers=1)
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    label = "swedish_all_pick_claude_haiku"

    population = [_persona(attrs, marker_attr, f"TYP{i}") for i in range(1, 5)]  # 4 personas
    seen_before: list[int] = []

    class _SnapshotClient(_StubClient):
        """Records how many persona verdict files exist on disk when each call runs."""

        def generate_content(self, user, *, model, system_instruction):
            seen_before.append(len(list(combo_dir.glob("persona_[0-9]*.json"))))
            return super().generate_content(user, model=model, system_instruction=system_instruction)

    summary = run_combo_judgements(
        population, label, attrs, combo_dir, cfg, client_factory=lambda: _SnapshotClient(),
    )
    assert summary.written == 4
    # Persona 0 sees 0 files; each later persona sees its predecessors already written.
    assert seen_before == [0, 1, 2, 3]
    for idx in range(4):
        assert (combo_dir / f"persona_{idx:05d}.json").is_file()
        assert (combo_dir / f"persona_{idx:05d}.jsonl").is_file()


def test_runner_failed_persona_leaves_siblings_intact(tmp_path):
    """A persona whose every round fails is left uncached (no json, no jsonl) while its
    siblings are written completely and independently -- per-persona writes mean one
    persona's failure never loses another's work (the interrupt-safety property).
    """
    attrs = scheme_attributes("swedish")
    marker_attr = attrs[0]
    cfg = dataclasses.replace(_cfg(), n_rounds=2, workers=2)
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    label = "swedish_all_pick_claude_haiku"

    # Persona 2 carries FAILME; the stub raises for it on every round.
    population = [
        _persona(attrs, marker_attr, "TYP8"),
        _persona(attrs, marker_attr, "TYP3"),
        _persona(attrs, marker_attr, "FAILME"),
        _persona(attrs, marker_attr, "TYP6"),
    ]

    class _SelectiveFailClient(_StubClient):
        def generate_content(self, user, *, model, system_instruction):
            if "FAILME" in user:
                raise RuntimeError("stub judge failure for FAILME")
            return super().generate_content(user, model=model, system_instruction=system_instruction)

    summary = run_combo_judgements(
        population, label, attrs, combo_dir, cfg, client_factory=lambda: _SelectiveFailClient(),
    )
    assert summary.written == 3
    assert summary.failed == 1
    # Siblings written completely and independently.
    for idx in (0, 1, 3):
        assert (combo_dir / f"persona_{idx:05d}.json").is_file()
        assert (combo_dir / f"persona_{idx:05d}.jsonl").is_file()
        payload = json.loads((combo_dir / f"persona_{idx:05d}.json").read_text(encoding="utf-8"))
        assert len(payload["rounds"]) == 2 and payload["status"] == "complete"
    # The fully-failed persona: neither file (retryable on a later run).
    assert not (combo_dir / "persona_00002.json").exists()
    assert not (combo_dir / "persona_00002.jsonl").exists()

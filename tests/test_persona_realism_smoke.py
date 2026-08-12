"""End-to-end smoke test for the persona-realism subpackage.

Drives the *real* runner -> artifacts pipeline the CLI script drives, but with a
**stubbed** judge client injected via ``run_combo_judgements(..., client_factory=)``
-- no live ``claude`` CLI, no network. A tiny synthetic combination plus the tiny real
competitor are judged, reduced, scored, and rendered on a ``tmp_path``; the test
asserts the durable per-persona ``persona_XXXXX.{json,jsonl}`` cache at the combo
root (no ``raw/`` subdir), the per-combo CSV/JSON, the per-persona tidy CSV and the
figures are written, that the head metrics (impossibility rate, dispersion,
reliability, cost) are well-formed, and that **no country-level aggregate** is
produced -- cross-combination output belongs to ``realism_ranking``. A separate test
drives the round-count-aware top-up (rounds=1 -> rounds=2 appends -> skip).

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
from typing import Any

import matplotlib
import pytest

matplotlib.use("Agg")

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.generation_metadata.pricing import PricingTable  # noqa: E402
from population_synthetic.analysis.model_ranking.loader import scheme_attributes  # noqa: E402
from population_synthetic.analysis.persona_realism import artifacts as A  # noqa: E402
from population_synthetic.analysis.persona_realism.config import JudgeConfig  # noqa: E402
from population_synthetic.analysis.persona_realism.runner import (  # noqa: E402
    RunnerSummary,
    run_combo_judgements,
)
from population_synthetic.analysis.utils.realism_csv import (  # noqa: E402
    read_realism_personas_csv,
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


def _persona(attrs: list[str], marker_attr: str, marker: str, pid: Any = None) -> dict[str, Any]:
    """Build a persona carrying every analyzed axis; the marker rides one axis.

    ``pid`` becomes the record's ``id``, mirroring a real mapped individual: the
    verdict cache is keyed on it (never on the list index), so a fixture without one
    is not representative of anything the runner reads.
    """
    persona: dict[str, Any] = {attr: f"val_{i}" for i, attr in enumerate(attrs)}
    persona[marker_attr] = marker
    if pid is not None:
        persona["id"] = pid
    return persona


def _synthetic_population(attrs: list[str]) -> list[dict[str, Any]]:
    """Ids run 0..n-1 in list order, so index and id coincide -- the *uncapped* case."""
    marker_attr = attrs[0]
    return [
        _persona(attrs, marker_attr, "TYP8", "persona_00000"),        # possible, high typicality
        _persona(attrs, marker_attr, "TYP3", "persona_00001"),        # possible, low typicality
        _persona(attrs, marker_attr, "IMPOSSIBLE", "persona_00002"),  # S3 hard contradiction
        _persona(attrs, marker_attr, "TYP6", "persona_00003"),        # possible, mid typicality
    ]


def _real_population(attrs: list[str]) -> list[dict[str, Any]]:
    """The real reference carries INTEGER ids (as SCB mapped records do)."""
    marker_attr = attrs[0]
    return [
        _persona(attrs, marker_attr, "TYP5", 0),
        _persona(attrs, marker_attr, "TYP5", 1),
        _persona(attrs, marker_attr, "TYP4", 2),
    ]


# --------------------------------------------------------------------------- #
# end-to-end smoke                                                            #
# --------------------------------------------------------------------------- #


def test_persona_realism_end_to_end(tmp_path):
    """One synthetic combination and the real competitor, each judged in isolation.

    Neither call sees the other: the real population is an ordinary competitor here,
    judged with its own cap and scored by the same code path, and no artifact of either
    unit references the other.
    """
    cfg = _cfg()
    attrs = scheme_attributes("swedish")
    out_root = tmp_path / "persona_realism"
    country_root = out_root / "swedish"          # nested one level per country
    slug = "swedish_all_pick_claude_haiku"

    # --- real competitor ------------------------------------------------------
    real_dir = country_root / "real_swedish"
    real_summary = run_combo_judgements(
        _real_population(attrs), "real_swedish", attrs, real_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert real_summary.failed == 0
    assert real_summary.written == 3
    assert real_summary.selected_ids == ("persona_00000", "persona_00001", "persona_00002")
    real_ca = A.write_combo_artifacts(
        real_dir, "real_swedish", cfg=cfg, dpi=80, force=True,
        country="swedish", is_real_reference=True,
        expected_ids=list(real_summary.selected_ids),
        hard_rules=(), pricing=_PRICING,
    )

    # --- synthetic combination (no reference threaded in) ---------------------
    syn_dir = country_root / slug
    syn_summary = run_combo_judgements(
        _synthetic_population(attrs), slug, attrs, syn_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert syn_summary.failed == 0
    assert syn_summary.written == 4
    syn_ca = A.write_combo_artifacts(
        syn_dir, slug, cfg=cfg, dpi=80, force=True,
        country="swedish", model="claude_haiku", strategy="all_pick",
        expected_ids=list(syn_summary.selected_ids),
        hard_rules=(), pricing=_PRICING,
    )

    # --- per-persona verdict cache + telemetry (combo root, no raw/) ----------
    for idx in range(4):
        assert (syn_dir / f"persona_{idx:05d}.json").is_file()
        assert (syn_dir / f"persona_{idx:05d}.jsonl").is_file()
    assert not (syn_dir / "raw").exists()
    assert not (syn_dir / "llm_interactions.jsonl").exists()

    # --- per-combo artifacts --------------------------------------------------
    for name in (f"{slug}.csv", f"{slug}.json", f"{slug}_personas.csv",
                 "typicality.png", "typicality.svg",
                 "clash_taxonomy.png", "clash_taxonomy.svg"):
        assert (syn_dir / name).is_file(), name

    # --- metrics well-formed --------------------------------------------------
    assert syn_ca.stats.n_personas == 4
    assert syn_ca.stats.n_failed == 0
    assert syn_ca.stats.impossibility["rate"] == pytest.approx(0.25)   # 1 of 4 impossible
    assert real_ca.stats.impossibility["rate"] == pytest.approx(0.0)
    # Dispersion describes this combination alone -- no reference-dependent key.
    assert "variance" in syn_ca.stats.dispersion
    assert "distance_to_scb" not in syn_ca.stats.dispersion
    # cost flowed from the stubbed telemetry (4 personas x 2 rounds x 150 tokens).
    combo_report = json.loads((syn_dir / f"{slug}.json").read_text(encoding="utf-8"))
    assert combo_report["cost"]["total_tokens"] == 4 * 2 * 150
    assert combo_report["cost"]["usd"] is not None
    assert combo_report["cost_coverage"]["status"] == "complete"

    # --- the inter-task contract ---------------------------------------------
    rows = read_realism_personas_csv(syn_dir / f"{slug}_personas.csv",
                                     expected_rows=combo_report["n_personas"])
    assert len(rows) == 4
    assert {r.persona_id for r in rows} == {f"persona_{i:05d}" for i in range(4)}
    assert all(r.slug == slug and r.country == "swedish" for r in rows)

    # --- NO country-level aggregate is produced by this task ------------------
    for orphan in ("headline_map.png", "headline_map.svg", "realism_summary.csv",
                   "run_report.json"):
        assert not (country_root / orphan).exists(), orphan
    assert {p.name for p in country_root.iterdir()} == {"real_swedish", slug}


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
    real_pop = [_persona(attrs, marker_attr, f"TYP{i}", i) for i in range(5)]
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


def test_plan_only_makes_no_judge_call_even_when_rounds_would_top_up(tmp_path):
    """``plan_only`` is zero-cost by construction, not by the operator's care.

    The trap it closes: personas cached at 1 round under a config whose ``n_rounds`` is
    3. A normal run correctly tops each of them up -- which is a full re-judge in all but
    name. An artifact rewrite must never trigger that, so the flag stops the runner
    before any call while still returning the roster the artifact layer needs.
    """
    attrs = scheme_attributes("swedish")
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    label = "swedish_all_pick_claude_haiku"
    population = _synthetic_population(attrs)
    cfg1 = dataclasses.replace(_cfg(), n_rounds=1)
    cfg3 = dataclasses.replace(_cfg(), n_rounds=3)

    run_combo_judgements(population, label, attrs, combo_dir, cfg1,
                         client_factory=_stub_factory())
    jsonl0 = combo_dir / "persona_00000.jsonl"
    assert len(jsonl0.read_text(encoding="utf-8").splitlines()) == 1

    calls: list[str] = []

    class _CountingClient(_StubClient):
        def generate_content(self, user, *, model, system_instruction):
            calls.append(user)
            return super().generate_content(user, model=model, system_instruction=system_instruction)

    summary = run_combo_judgements(
        population, label, attrs, combo_dir, cfg3, plan_only=True,
        client_factory=lambda: _CountingClient(),
    )
    assert calls == []                       # not one judge call
    assert summary.requested == 0 and summary.written == 0 and summary.topped_up == 0
    # ... while the roster the artifact layer needs is still resolved.
    assert summary.selected_ids == tuple(f"persona_{i:05d}" for i in range(4))
    # ... and nothing on disk moved.
    assert len(jsonl0.read_text(encoding="utf-8").splitlines()) == 1
    assert len(json.loads((combo_dir / "persona_00000.json").read_text(encoding="utf-8"))["rounds"]) == 1


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
    """Load the CLI driver script by file path (scripts/ is not an importable package).

    The module is registered in ``sys.modules`` **before** it is executed: a dataclass
    declared at module scope resolves its own module through ``sys.modules`` while it
    is being processed, so an unregistered spec-loaded module raises on the class
    definition rather than on any behaviour under test.
    """
    import importlib.util
    import sys

    path = PROJECT_ROOT / "scripts" / "analyze" / "analyze_persona_realism.py"
    spec = importlib.util.spec_from_file_location("analyze_persona_realism", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _combo_of(driver, label: str, *, country: str = "swedish"):
    """The driver's ``_Combo`` DTO for a synthetic unit (dispatch-test fixture)."""
    return driver._Combo(
        label=label, country=country, strategy="all_pick", model="claude_haiku",
        is_real_reference=False, sample_size_override=None,
    )


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
                    plan_only=False, sample_size_override=None, logger=None):
        calls["runner_called"] = True
        calls["force"] = force
        calls["plan_only"] = plan_only
        return _summary(combo_label, o, topped_up=len(individuals))  # runner tops up

    def _spy_artifacts(o, combo_label, *, cfg, dpi, force, country="", model="", strategy="",
                       is_real_reference=False, expected_ids=None, hard_rules=None,
                       pricing=None, logger=None):
        calls["artifacts_force"] = force
        return object()

    monkeypatch.setattr(driver, "run_combo_judgements", _spy_runner)
    monkeypatch.setattr(driver, "write_combo_artifacts", _spy_artifacts)

    result = driver._run_one_combo(
        combo=_combo_of(driver, label), individuals=[{"a": 1}, {"a": 2}], analyzed_attrs=attrs,
        out_dir=out_dir, cfg=cfg, dpi=80, force=False,
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
                    plan_only=False, sample_size_override=None, logger=None):
        calls["runner_called"] = True
        calls["force"] = force
        calls["plan_only"] = plan_only
        return _summary(combo_label, o, skipped=len(individuals))  # everything already cached

    def _spy_artifacts(o, combo_label, *, cfg, dpi, force, country="", model="", strategy="",
                       is_real_reference=False, expected_ids=None, hard_rules=None,
                       pricing=None, logger=None):
        calls["artifacts_force"] = force
        return object()

    monkeypatch.setattr(driver, "run_combo_judgements", _spy_runner)
    monkeypatch.setattr(driver, "write_combo_artifacts", _spy_artifacts)

    driver._run_one_combo(
        combo=_combo_of(driver, label), individuals=[{"a": 1}], analyzed_attrs=attrs,
        out_dir=out_dir, cfg=cfg, dpi=80, force=False,
        hard_rules=(), pricing=_PRICING,
    )
    assert calls["runner_called"] is True
    assert calls["artifacts_force"] is False  # nothing changed -> no forced rewrite

    # --rewrite-artifacts rewrites the derived files WITHOUT asking the runner to
    # re-judge: the supported zero-LLM-cost path after an output-schema change.
    calls.clear()
    driver._run_one_combo(
        combo=_combo_of(driver, label), individuals=[{"a": 1}], analyzed_attrs=attrs,
        out_dir=out_dir, cfg=cfg, dpi=80, force=False, rewrite_artifacts=True,
        hard_rules=(), pricing=_PRICING,
    )
    assert calls["artifacts_force"] is True   # artifacts rewritten
    assert calls["force"] is False            # ... but nothing was re-judged
    assert calls["plan_only"] is True         # ... and the runner made no judge call at all


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
    persona["id"] = "persona_00000"

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

    population = [_persona(attrs, marker_attr, f"TYP{i}", f"persona_{i - 1:05d}") for i in range(1, 5)]  # 4 personas
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
        _persona(attrs, marker_attr, "TYP8", "persona_00000"),
        _persona(attrs, marker_attr, "TYP3", "persona_00001"),
        _persona(attrs, marker_attr, "FAILME", "persona_00002"),
        _persona(attrs, marker_attr, "TYP6", "persona_00003"),
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


# --------------------------------------------------------------------------- #
# verdict-cache identity: keyed on the persona id, never on the list index     #
# --------------------------------------------------------------------------- #


def test_cache_is_keyed_on_persona_id_not_list_index(tmp_path):
    """A capped population holds a SPARSE id set: files follow the ids, not 0..n-1.

    ``population_cap`` seeded-draws n personas out of the clean pool, so the mapped
    file the judge reads is a sparse subset (ids 3, 17, 42) whose list indices are
    0, 1, 2. Keying the cache on the index would name persona_00042's verdicts
    ``persona_00002.json`` -- and a later cap, drawing a different subset, would
    silently hand those rounds to whoever landed at index 2 next.
    """
    cfg = dataclasses.replace(_cfg(), n_rounds=1)
    attrs = scheme_attributes("swedish")
    marker_attr = attrs[0]
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    population = [
        _persona(attrs, marker_attr, "TYP8", "persona_00003"),
        _persona(attrs, marker_attr, "TYP5", "persona_00017"),
        _persona(attrs, marker_attr, "TYP6", "persona_00042"),
    ]

    summary = run_combo_judgements(
        population, "swedish_all_pick_claude_haiku", attrs, combo_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert summary.written == 3 and summary.failed == 0

    for pid in ("persona_00003", "persona_00017", "persona_00042"):
        assert (combo_dir / f"{pid}.json").is_file()
        assert (combo_dir / f"{pid}.jsonl").is_file()
        assert json.loads((combo_dir / f"{pid}.json").read_text(encoding="utf-8"))["persona_id"] == pid
    # The index-named files the old key would have produced must not exist.
    for idx in range(len(population)):
        assert not (combo_dir / f"persona_{idx:05d}.json").exists()


def test_cached_verdicts_for_a_different_persona_raise(tmp_path):
    """A cache file whose stored ``persona_id`` disagrees with the record raises.

    The guard against a re-drawn cap: reusing those rounds would attribute one
    persona's verdicts to another, and nothing downstream could detect it.
    """
    cfg = dataclasses.replace(_cfg(), n_rounds=1)
    attrs = scheme_attributes("swedish")
    marker_attr = attrs[0]
    combo_dir = tmp_path / "swedish_all_pick_claude_haiku"
    combo_dir.mkdir(parents=True)
    population = [_persona(attrs, marker_attr, "TYP8", "persona_00007")]

    # A stale cache under the right NAME but holding another persona's verdicts.
    (combo_dir / "persona_00007.json").write_text(
        json.dumps({"persona_id": "persona_00312", "rounds": [{"can_exist": True}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="persona_00312"):
        run_combo_judgements(
            population, "swedish_all_pick_claude_haiku", attrs, combo_dir, cfg,
            client_factory=_stub_factory(),
        )


@pytest.mark.parametrize(
    "bad_id, match",
    [
        (None, "carries no 'id'"),
        ("", "carries no 'id'"),
        ("p-312", "persona_<digits>"),
        (True, "boolean 'id'"),
    ],
)
def test_unusable_persona_id_raises(tmp_path, bad_id, match):
    """No silent fallback to the index: an id the readers could not glob fails loudly."""
    cfg = dataclasses.replace(_cfg(), n_rounds=1)
    attrs = scheme_attributes("swedish")
    marker_attr = attrs[0]
    persona = _persona(attrs, marker_attr, "TYP8")
    if bad_id is not None:
        persona["id"] = bad_id

    with pytest.raises(ValueError, match=match):
        run_combo_judgements(
            [persona], "swedish_all_pick_claude_haiku", attrs,
            tmp_path / "swedish_all_pick_claude_haiku", cfg,
            client_factory=_stub_factory(),
        )


def test_integer_ids_are_normalised_to_the_persona_glob_shape(tmp_path):
    """The real reference carries integer ids; files must still match persona_[0-9]*."""
    cfg = dataclasses.replace(_cfg(), n_rounds=1)
    attrs = scheme_attributes("swedish")
    real_dir = tmp_path / "real_swedish"

    summary = run_combo_judgements(
        _real_population(attrs), "real_swedish", attrs, real_dir, cfg,
        client_factory=_stub_factory(),
    )
    assert summary.written == 3
    for idx in range(3):
        path = real_dir / f"persona_{idx:05d}.json"
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8"))["persona_id"] == f"persona_{idx:05d}"

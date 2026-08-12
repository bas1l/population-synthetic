"""Unit tests for the ``realism_ranking`` loader: discovery + the two consumption gates.

The loader's job is to refuse the two inputs that would silently produce plausible but
wrong numbers -- a combination that is only half-written, and a consumption set judged
by more than one judge -- so most of these tests are about what it *rejects*.

Fixtures fabricate a minimal output base on ``tmp_path``: the capped mapped index the
discovery walk reads, plus per-combination judge artifacts under the registry-resolved
``persona_realism`` folder. No LLM, no real output base.

Two fixture families, because the loader has two source contracts. The hand-written one
(:func:`_write_combo`) fabricates the published artifacts directly and writes **no**
verdict cache, which is what makes it a proof for the default path: a test using it that
passes could not have taken the round-cap path, since that path reads caches and would
raise on their absence. The cache-backed one (:func:`_write_cached_combo`) writes real
verdict caches and then derives the published artifacts from them through the producer's
own ``write_combo_artifacts``, so the capped re-reduction can be compared against
artifacts it did not itself produce.
"""

from __future__ import annotations

import dataclasses
import json
import logging

import matplotlib
import pytest

matplotlib.use("Agg")

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.analysis.generation_metadata.pricing import PricingTable  # noqa: E402
from population_synthetic.analysis.persona_realism.artifacts import (  # noqa: E402
    write_combo_artifacts,
)
from population_synthetic.analysis.persona_realism.config import JudgeConfig  # noqa: E402
from population_synthetic.analysis.realism_ranking.loader import load_competitors  # noqa: E402
from population_synthetic.analysis.utils.capped_source import MAPPED_SUBDIR  # noqa: E402
from population_synthetic.analysis.utils.realism_clash_csv import (  # noqa: E402
    RealismClashRow,
    write_realism_clashes_csv,
)
from population_synthetic.analysis.utils.realism_csv import (  # noqa: E402
    RealismPersonaRow,
    write_realism_personas_csv,
)
from population_synthetic.analysis.utils.registry import analysis_output_dir  # noqa: E402

_COUNTRY = "swedish"
_AXIS_IDS = (
    [_COUNTRY],
    ["all_pick", "all_pick_dag"],
    ["claude_haiku", "claude_sonnet"],
)
_PROVENANCE = {
    "judge_model": "claude-sonnet-5",
    "prompt_template_sha256": "abc123",
    "n_rounds": 2,
}


def _persona_row(pid: str, slug: str, *, impossible: bool, typicality: float | None,
                 model: str = "claude_haiku", strategy: str = "all_pick",
                 is_real: bool = False) -> RealismPersonaRow:
    return RealismPersonaRow(
        persona_id=pid,
        slug=slug,
        country=_COUNTRY,
        model=model,
        strategy=strategy,
        is_real_reference=is_real,
        n_rounds_attempted=2,
        n_rounds_successful=2,
        can_exist_true_votes=0 if impossible else 2,
        can_exist_majority=not impossible,
        typicality_mean=typicality,
        typicality_sd=None,
        typicality_rounds=() if typicality is None else (int(typicality), int(typicality)),
        max_severity="S3" if impossible else "",
        clash_count=1 if impossible else 0,
        clash_count_s3=1 if impossible else 0,
    )


def _clash_row(row: RealismPersonaRow) -> RealismClashRow:
    """The one S3 clash the impossible personas above declare, as a contract row.

    Kept in step with :func:`_persona_row` on purpose: the loader reconciles the two
    files, so a fixture whose clash rows disagree with its ``clash_count_s3`` column
    would fail every test for the wrong reason.
    """
    return RealismClashRow(
        persona_id=row.persona_id, slug=row.slug, country=row.country, model=row.model,
        strategy=row.strategy, is_real_reference=row.is_real_reference, round_index=0,
        attr_a="age_group", attr_b="education_level",
        value_a="16-19", value_b="Doctorate", severity="S3", unresolved=False,
    )


def _write_combo(
    base, slug, *, n_impossible=1, n_possible=3, model="claude_haiku", strategy="all_pick",
    is_real=False, provenance=None, report=True, personas_csv=True, clashes_csv=True,
    n_personas_override=None,
):
    """Write one combination's judge artifacts under the registry-resolved folder."""
    combo_dir = analysis_output_dir("persona_realism", base) / _COUNTRY / slug
    combo_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        _persona_row(f"persona_{i:05d}", slug, impossible=True, typicality=None,
                     model=model, strategy=strategy, is_real=is_real)
        for i in range(n_impossible)
    ] + [
        _persona_row(f"persona_{n_impossible + i:05d}", slug, impossible=False,
                     typicality=float(4 + i), model=model, strategy=strategy, is_real=is_real)
        for i in range(n_possible)
    ]
    if personas_csv:
        write_realism_personas_csv(rows, combo_dir / f"{slug}_personas.csv")
    if clashes_csv:
        write_realism_clashes_csv(
            [_clash_row(row) for row in rows if row.clash_count_s3],
            combo_dir / f"{slug}_clashes.csv",
        )
    if report:
        payload = {
            "process": "persona_realism",
            "combo_label": slug,
            "n_personas": n_personas_override if n_personas_override is not None else len(rows),
            "n_failed": 0,
            "impossibility": {"rate": n_impossible / len(rows), "lo": 0.0, "hi": 1.0},
            "dispersion": {"n": n_possible, "variance": 1.0, "entropy": 1.5,
                           "tail_coverage": 0.0, "tail_threshold": 3.0},
            "reliability": {},
            "provenance": dict(provenance or _PROVENANCE),
        }
        (combo_dir / f"{slug}.json").write_text(json.dumps(payload), encoding="utf-8")
    return combo_dir


def _write_index(base, slugs):
    mapped = analysis_output_dir("population_cap", base) / MAPPED_SUBDIR
    mapped.mkdir(parents=True, exist_ok=True)
    entries = [{"slug": slug, "synthetic_file": f"{slug}.json"} for slug in slugs]
    (mapped / "_index.json").write_text(json.dumps(entries), encoding="utf-8")


def _base(tmp_path, slugs):
    _write_index(tmp_path, slugs)
    return tmp_path


_SLUG_A = "swedish_all_pick_claude_haiku"
_SLUG_B = "swedish_all_pick_dag_claude_sonnet"
_REAL = f"real_{_COUNTRY}"


# --------------------------------------------------------------------------- #
# discovery                                                                    #
# --------------------------------------------------------------------------- #


def test_loads_synthetic_combinations_and_the_real_competitor(tmp_path):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, model="claude_sonnet", strategy="all_pick_dag")
    _write_combo(base, _REAL, is_real=True, model="", strategy="")

    records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    assert skipped == []
    assert {r.slug for r in records} == {_SLUG_A, _SLUG_B, _REAL}
    real = next(r for r in records if r.is_real_reference)
    assert real.model == "" and real.strategy == ""
    # The bootstrap's sampling unit is rebuilt from the tidy rows, not read from the report.
    record = next(r for r in records if r.slug == _SLUG_A)
    assert record.impossible_indicators == (1, 0, 0, 0)
    assert record.typicality_means == (4.0, 5.0, 6.0)


def test_missing_real_competitor_is_a_skip_not_a_failure(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A)
    records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    assert [r.slug for r in records] == [_SLUG_A]
    assert any(slug == _REAL for slug, _ in skipped)


# --------------------------------------------------------------------------- #
# gate 1: completeness                                                         #
# --------------------------------------------------------------------------- #


def test_partial_directory_without_report_is_skipped_with_reason(tmp_path):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, report=False)  # verdict caches but no report
    records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    assert [r.slug for r in records] == [_SLUG_A]
    reason = dict(skipped)[_SLUG_B]
    assert "no combination report" in reason


def test_partial_directory_raises_under_strict(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, report=False)
    with pytest.raises(RuntimeError, match="not consumable"):
        load_competitors(base, axis_ids=_AXIS_IDS, strict=True)


def test_missing_personas_csv_is_skipped_with_an_actionable_reason(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, personas_csv=False)
    _records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    assert "--rewrite-artifacts" in dict(skipped)[_SLUG_A]


def test_missing_clashes_csv_is_skipped_with_an_actionable_reason(tmp_path):
    """The third contract file gates exactly as the second does.

    An output base judged before the per-clash contract existed has every other
    artifact in place, so nothing but this check distinguishes it from a complete one --
    and consuming it would report every severity cell as having no drivers at all.
    """
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, clashes_csv=False)
    _records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    reason = dict(skipped)[_SLUG_A]
    assert "no per-clash CSV" in reason
    assert "--rewrite-artifacts" in reason


def test_missing_clashes_csv_raises_under_strict(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, clashes_csv=False)
    with pytest.raises(RuntimeError, match="not consumable"):
        load_competitors(base, axis_ids=_AXIS_IDS, strict=True)


def test_clash_rows_are_reconciled_against_the_per_persona_counts(tmp_path):
    """A clashes CSV written from a different state of the cache must raise.

    The two files are joined on ``persona_id`` to produce a driver prevalence, so a
    numerator from one state over a denominator from another is exactly the silently
    plausible wrong number the gate exists for.
    """
    base = _base(tmp_path, [_SLUG_A])
    combo_dir = _write_combo(base, _SLUG_A, n_impossible=2)
    write_realism_clashes_csv([], combo_dir / f"{_SLUG_A}_clashes.csv")  # header only
    with pytest.raises(ValueError, match="--rewrite-artifacts"):
        load_competitors(base, axis_ids=_AXIS_IDS)


def test_loaded_record_carries_its_clash_rows(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, n_impossible=2)
    records, _ = load_competitors(base, axis_ids=_AXIS_IDS)
    record = next(r for r in records if r.slug == _SLUG_A)
    assert len(record.clashes) == 2
    assert {row.severity for row in record.clashes} == {"S3"}
    assert {row.attr_a for row in record.clashes} == {"age_group"}


def test_row_count_disagreement_raises(tmp_path):
    """A CSV and a report describing different persona sets is corruption, not progress."""
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, n_personas_override=99)
    with pytest.raises(ValueError, match="n_personas=99"):
        load_competitors(base, axis_ids=_AXIS_IDS)


def test_malformed_report_raises_naming_the_upstream_script(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    combo_dir = _write_combo(base, _SLUG_A)
    (combo_dir / f"{_SLUG_A}.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="analyze_persona_realism.py"):
        load_competitors(base, axis_ids=_AXIS_IDS)


# --------------------------------------------------------------------------- #
# gate 2: homogeneity                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "key, value",
    [("judge_model", "claude-haiku-4-5"), ("prompt_template_sha256", "deadbeef"), ("n_rounds", 5)],
)
def test_heterogeneous_judge_raises_naming_the_offender(tmp_path, key, value):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, model="claude_sonnet", strategy="all_pick_dag",
                 provenance={**_PROVENANCE, key: value})
    with pytest.raises(ValueError, match=_SLUG_B):
        load_competitors(base, axis_ids=_AXIS_IDS)


def test_homogeneous_set_passes_the_guard(tmp_path):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, model="claude_sonnet", strategy="all_pick_dag")
    records, _ = load_competitors(base, axis_ids=_AXIS_IDS)
    assert len(records) == 2


# --------------------------------------------------------------------------- #
# the round cap: cache-backed fixtures                                         #
# --------------------------------------------------------------------------- #

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"

#: A rate-less pricing table. These fixtures write verdict caches directly and lay no
#: judge-call telemetry beside them, so the cost chain returns before any rate lookup;
#: an empty table therefore states the truth (nothing was spent) instead of pricing
#: calls that were never made.
_PRICING = PricingTable(
    rates={}, observed_date="2026-08-12", source="loader-test", currency="USD",
)

#: The one attribute pair every fixture clash names, and the persona values it joins
#: against -- kept together because a per-clash row carries both, and a pair the persona
#: does not hold would be written ``unresolved`` and stop testing what it looks like.
_CLASH_PAIR = ("age_group", "education_level")
_ATTRIBUTES = {"age_group": "16-19", "education_level": "Doctorate"}


def _judge_cfg(**overrides) -> JudgeConfig:
    """The real judge config with a small seeded bootstrap (fast and deterministic).

    Loaded from ``config/`` rather than fabricated: the bootstrap seed and the
    reliability parameters are exactly what the cap path recomputes a competitor under,
    so a test config would prove parity against something the pipeline never uses.
    """
    return dataclasses.replace(
        JudgeConfig.load(_CONFIG_DIR),
        bootstrap={"iterations": 200, "seed": 20260812, "ci_level": 0.95},
        **overrides,
    )


def _cached_round(*, can_exist: bool, typicality: int | None, severity: str) -> dict:
    """One cached round, in the shape ``judge.parse_round_verdict`` re-validates."""
    return {
        "can_exist": can_exist,
        "typicality": typicality,
        "issues": [
            {"attributes": list(_CLASH_PAIR), "severity": severity,
             "explanation": "fixture clash"}
        ],
        "reasoning": "",
    }


def _write_cached_combo(
    base, slug, *, depth, model="claude_haiku", strategy="all_pick", is_real=False,
    cfg=None, n_impossible=1, n_possible=3,
):
    """Write one combination's verdict cache at *depth* rounds, then its artifacts.

    The published files come from the producer's own ``write_combo_artifacts`` rather
    than being fabricated, so a record re-reduced at the full cached depth is compared
    against artifacts computed independently of the cap path.

    Typicality rises with the round index, so trimming the cache genuinely moves the
    numbers below it -- a fixture whose rounds were identical would let a cap that
    silently kept every round pass by coincidence.
    """
    cfg = cfg or _judge_cfg(n_rounds=depth)
    combo_dir = analysis_output_dir("persona_realism", base) / _COUNTRY / slug
    combo_dir.mkdir(parents=True, exist_ok=True)
    persona_ids = []
    for index in range(n_impossible + n_possible):
        persona_id = f"persona_{index:05d}"
        persona_ids.append(persona_id)
        impossible = index < n_impossible
        rounds = [
            _cached_round(
                can_exist=not impossible,
                typicality=None if impossible else min(10, 2 + index + r),
                severity="S3" if impossible else "S1",
            )
            for r in range(depth)
        ]
        (combo_dir / f"{persona_id}.json").write_text(
            json.dumps({
                "persona_id": persona_id, "attributes": dict(_ATTRIBUTES),
                "rounds": rounds, "failed_rounds": 0,
            }),
            encoding="utf-8",
        )
    write_combo_artifacts(
        combo_dir, slug, cfg=cfg, dpi=60, force=True,
        country=_COUNTRY, model=model, strategy=strategy, is_real_reference=is_real,
        expected_ids=persona_ids, hard_rules=(), pricing=_PRICING,
    )
    return combo_dir


# --------------------------------------------------------------------------- #
# the round cap: the default path is untouched                                 #
# --------------------------------------------------------------------------- #


def test_rounds_cap_none_yields_exactly_the_published_records(tmp_path):
    """Passing the cap arguments explicitly as ``None`` changes nothing.

    The hand-written fixture lays down no verdict cache at all, so a run that reached
    the cap path would raise rather than compare equal -- which is what makes this a
    guard on the *path taken* and not merely on the values returned.
    """
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, model="claude_sonnet", strategy="all_pick_dag")

    baseline, baseline_skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    explicit, explicit_skipped = load_competitors(
        base, axis_ids=_AXIS_IDS, rounds_cap=None, judge_cfg=_judge_cfg(),
    )

    assert explicit == baseline
    assert explicit_skipped == baseline_skipped


def test_a_homogeneous_set_never_enters_the_cap_path(tmp_path):
    """Auto-derivation is a recovery step, so an agreeing set must not trigger it."""
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, model="claude_sonnet", strategy="all_pick_dag")

    records, _ = load_competitors(base, axis_ids=_AXIS_IDS, judge_cfg=_judge_cfg())

    assert [record.provenance["n_rounds_source"] for record in records] == ["report", "report"]
    # The published artifacts really were the source: there is nothing else to read.
    judge_root = analysis_output_dir("persona_realism", base)
    assert not list(judge_root.rglob("persona_[0-9]*.json"))


# --------------------------------------------------------------------------- #
# the round cap: an explicit --rounds                                          #
# --------------------------------------------------------------------------- #


def test_a_round_heterogeneous_set_loads_under_a_cap_and_raises_without_one(tmp_path):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_cached_combo(base, _SLUG_A, depth=5)
    _write_cached_combo(base, _SLUG_B, depth=2, model="claude_sonnet", strategy="all_pick_dag")

    records, _ = load_competitors(base, axis_ids=_AXIS_IDS, rounds_cap=2, judge_cfg=_judge_cfg())
    assert {record.slug for record in records} == {_SLUG_A, _SLUG_B}

    # Without a cap -- and without the config the auto path would need -- the set is
    # exactly the heterogeneity the gate has always refused.
    with pytest.raises(ValueError, match="Heterogeneous judge"):
        load_competitors(base, axis_ids=_AXIS_IDS)


@pytest.mark.parametrize("key", ["judge_model", "prompt_template_sha256"])
def test_a_differing_judge_or_prompt_still_raises_with_a_cap_active(tmp_path, key):
    """The cap relaxes the round count and nothing else: no cap repairs a new judge."""
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_cached_combo(base, _SLUG_A, depth=3)
    if key == "judge_model":
        odd = _judge_cfg(n_rounds=3, judge_model="claude-haiku-4-5")
    else:
        template = tmp_path / "other_prompt.md"
        template.write_text("a different prompt template", encoding="utf-8")
        odd = _judge_cfg(n_rounds=3, prompt_template=template)
    _write_cached_combo(base, _SLUG_B, depth=3, model="claude_sonnet",
                        strategy="all_pick_dag", cfg=odd)

    with pytest.raises(ValueError, match=key):
        load_competitors(base, axis_ids=_AXIS_IDS, rounds_cap=2, judge_cfg=_judge_cfg())


def test_a_cap_deeper_than_the_cache_raises_naming_the_shortfall(tmp_path):
    """A shortfall is a hard failure, never a competitor quietly ranked short."""
    base = _base(tmp_path, [_SLUG_A])
    _write_cached_combo(base, _SLUG_A, depth=2)

    with pytest.raises(ValueError) as excinfo:
        load_competitors(base, axis_ids=_AXIS_IDS, rounds_cap=3, judge_cfg=_judge_cfg())

    message = str(excinfo.value)
    assert _SLUG_A in message
    assert "persona_00000" in message
    assert "at 3 round(s)" in message
    assert "only 2 cached" in message


def test_a_capped_record_stamps_the_consumed_count_and_its_source(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_cached_combo(base, _SLUG_A, depth=5)

    (record,), _ = load_competitors(
        base, axis_ids=_AXIS_IDS, rounds_cap=2, judge_cfg=_judge_cfg(),
    )
    assert record.provenance["n_rounds"] == 2
    assert record.provenance["n_rounds_source"] == "cap"


def test_a_cap_at_the_full_cached_depth_reproduces_the_published_record(tmp_path):
    """The cap is a no-op at full depth -- the strongest check on the re-reduction.

    The published blocks were computed by ``persona_realism`` from the same cache and
    read back off disk; the capped ones are recomputed here. Their agreeing is what
    says the cap path measures the same thing the artifacts do, only over fewer rounds.
    """
    base = _base(tmp_path, [_SLUG_A])
    _write_cached_combo(base, _SLUG_A, depth=5)

    (published,), _ = load_competitors(base, axis_ids=_AXIS_IDS)
    (capped,), _ = load_competitors(
        base, axis_ids=_AXIS_IDS, rounds_cap=5, judge_cfg=_judge_cfg(),
    )

    assert capped.impossibility == published.impossibility
    assert capped.dispersion == published.dispersion
    assert capped.personas == published.personas
    assert capped.clashes == published.clashes
    assert (capped.n_personas, capped.n_failed) == (published.n_personas, published.n_failed)


def test_capped_clash_rows_hold_no_round_beyond_the_cap(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_cached_combo(base, _SLUG_A, depth=5)

    (published,), _ = load_competitors(base, axis_ids=_AXIS_IDS)
    assert max(row.round_index for row in published.clashes) == 4

    (capped,), _ = load_competitors(
        base, axis_ids=_AXIS_IDS, rounds_cap=2, judge_cfg=_judge_cfg(),
    )
    assert capped.clashes
    assert all(row.round_index < 2 for row in capped.clashes)


# --------------------------------------------------------------------------- #
# the round cap: auto-derivation when --rounds is blank                        #
# --------------------------------------------------------------------------- #


def test_auto_derivation_ranks_at_the_shallowest_cached_depth(tmp_path, caplog):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_cached_combo(base, _SLUG_A, depth=5)
    _write_cached_combo(base, _SLUG_B, depth=2, model="claude_sonnet", strategy="all_pick_dag")

    with caplog.at_level(logging.WARNING):
        records, _ = load_competitors(base, axis_ids=_AXIS_IDS, judge_cfg=_judge_cfg())

    assert {record.provenance["n_rounds"] for record in records} == {2}
    assert {record.provenance["n_rounds_source"] for record in records} == {"auto"}
    assert "shallowest cached depth of 2" in caplog.text
    assert _SLUG_A in caplog.text          # the trimmed combination is named
    assert _SLUG_B not in caplog.text      # the shallowest one was not trimmed


def test_auto_derivation_does_not_mask_a_differing_judge_model(tmp_path):
    """Differing on the judge *and* the round count is terminal, not recoverable."""
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_cached_combo(base, _SLUG_A, depth=5)
    _write_cached_combo(base, _SLUG_B, depth=2, model="claude_sonnet", strategy="all_pick_dag",
                        cfg=_judge_cfg(n_rounds=2, judge_model="claude-haiku-4-5"))

    with pytest.raises(ValueError, match="judge_model"):
        load_competitors(base, axis_ids=_AXIS_IDS, judge_cfg=_judge_cfg())

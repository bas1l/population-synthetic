"""Tests for the population_cap analysis process (the pipeline root).

Locks the behavior of the pre-mapping cap and its read-redirect contract:

- ``utils.sampling.select_indices``      -- reproducible seeded draw; distinct indices;
                                            ``n >= total`` returns all; algorithmic
                                            consistency with ``subsample_population``.
- ``population_cap.cap_combo``            -- over/under-generation, ancillary copy,
                                            ``force`` semantics, 0-persona edge, seed 0.
- ``utils.capped_source`` resolvers       -- return the mirror when present; **raise
                                            ``FileNotFoundError`` when absent, with NO
                                            fallback to ``01_Raw``**.
- integration                             -- cap -> mapping loader sees exactly N;
                                            cap -> ``generation_metadata.summarize``
                                            aggregates over N (not M); no-mirror
                                            fail-fast on both consumer seams.

Fixtures materialize a minimal ``01_Raw`` combo (``persona_*/identity.json`` +
``llm_interactions.jsonl`` + optional combo-level ancillary files) so the tests exercise
the real on-disk layout the cap mirrors.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from population_synthetic.analysis.generation_metadata import summarize
from population_synthetic.analysis.mapping.synthetic_mapper import load_synthetic_population
from population_synthetic.analysis.population_cap import cap_combo
from population_synthetic.analysis.utils.capped_source import (
    resolve_combo_source,
    resolve_stage_source,
)
from population_synthetic.analysis.utils.registry import analysis_output_dir
from population_synthetic.analysis.utils.sampling import select_indices, subsample_population

# A slug that decomposes into (country=swedish, strategy=all_pick, model=claude_haiku);
# claude_haiku is a genuinely-priced model in the real pricing config, so
# generation_metadata can compute cost over the capped fixture.
_SLUG = "swedish_all_pick_claude_haiku"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


def _tokened_entries() -> list[dict]:
    return [
        {
            "request_sent_at": "2026-07-23T10:00:00",
            "response_received_at": "2026-07-23T10:00:10",
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "attempt": 1,
            "error": None,
        },
        {
            "request_sent_at": "2026-07-23T10:00:10",
            "response_received_at": "2026-07-23T10:00:20",
            "prompt_tokens": 200,
            "completion_tokens": 60,
            "total_tokens": 260,
            "attempt": 1,
            "error": None,
        },
    ]


def _make_raw_combo(
    output_base: Path,
    slug: str,
    m: int,
    *,
    with_ancillary: bool = False,
) -> Path:
    """Materialize ``01_Raw/{slug}/`` with *m* persona dirs; return the combo dir.

    Each persona carries an ``identity.json`` (so the mapping loader sees it) and an
    ``llm_interactions.jsonl`` (so generation_metadata sees telemetry). With
    ``with_ancillary``, the combo-level ``logs/``, ``run_metadata.json`` and
    ``manifest_snapshot.yaml`` are written too.
    """
    combo = output_base / "01_Raw" / slug
    for i in range(1, m + 1):
        pdir = combo / f"persona_{i:05d}"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "identity.json").write_text(
            json.dumps({"name": f"person_{i}"}), encoding="utf-8"
        )
        with open(pdir / "llm_interactions.jsonl", "w", encoding="utf-8") as fh:
            for rec in _tokened_entries():
                fh.write(json.dumps(rec) + "\n")
    if with_ancillary:
        (combo / "logs").mkdir(parents=True, exist_ok=True)
        (combo / "logs" / "run_0.log").write_text("run log line\n", encoding="utf-8")
        (combo / "run_metadata.json").write_text(
            json.dumps({"run": 1}), encoding="utf-8"
        )
        (combo / "manifest_snapshot.yaml").write_text("key: value\n", encoding="utf-8")
    return combo


def _cap_stage(output_base: Path) -> Path:
    """The capped-mirror stage dir: ``03_Analysis/population_cap/``."""
    return analysis_output_dir("population_cap", output_base)


def _persona_dirs(combo_dir: Path) -> list[str]:
    return sorted(p.name for p in combo_dir.glob("persona_*") if p.is_dir())


# --------------------------------------------------------------------------- #
# (a) select_indices
# --------------------------------------------------------------------------- #


def test_select_indices_reproducible_for_fixed_seed():
    a = select_indices(50, 10, seed=7)
    b = select_indices(50, 10, seed=7)
    assert a == b
    assert len(a) == 10


def test_select_indices_distinct_and_in_range():
    idx = select_indices(30, 12, seed=3)
    assert len(set(idx)) == len(idx) == 12
    assert all(0 <= i < 30 for i in idx)
    assert idx == sorted(idx)


def test_select_indices_n_ge_total_returns_all():
    assert select_indices(6, 6, seed=0) == list(range(6))
    assert select_indices(6, 100, seed=0) == list(range(6))


def test_select_indices_matches_subsample_population():
    # subsample_population routes its draw through select_indices, so the retained
    # index-tagged rows must equal the shared primitive's output for the same triple.
    total, n, seed = 40, 9, 5
    pop = {
        "individuals": [{"id": i} for i in range(total)],
        "metadata": {"n": total},
    }
    capped = subsample_population(pop, n, seed=seed)
    retained_ids = [ind["id"] for ind in capped["individuals"]]
    assert retained_ids == select_indices(total, n, seed)


# --------------------------------------------------------------------------- #
# (b) cap_combo
# --------------------------------------------------------------------------- #


def test_cap_combo_over_generation_selects_exactly_n(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=10)
    dest = _cap_stage(tmp_path) / _SLUG

    summary = cap_combo(raw, 4, 0, dest)

    assert summary["available"] == 10
    assert summary["selected"] == 4
    assert summary["requested_n"] == 4
    assert summary["truncated"] is True
    assert len(summary["selected_ids"]) == 4
    assert _persona_dirs(dest) == sorted(summary["selected_ids"])
    assert len(_persona_dirs(dest)) == 4


def test_cap_combo_over_generation_deterministic_for_fixed_seed(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=10)
    dest_a = _cap_stage(tmp_path) / "run_a"
    dest_b = _cap_stage(tmp_path) / "run_b"

    a = cap_combo(raw, 4, 42, dest_a)
    b = cap_combo(raw, 4, 42, dest_b)
    assert a["selected_ids"] == b["selected_ids"]


def test_cap_combo_under_generation_copies_all_and_warns(tmp_path: Path, caplog):
    raw = _make_raw_combo(tmp_path, _SLUG, m=3)
    dest = _cap_stage(tmp_path) / _SLUG

    with caplog.at_level("WARNING"):
        summary = cap_combo(raw, 5, 0, dest)

    assert summary["available"] == 3
    assert summary["selected"] == 3
    assert summary["requested_n"] == 5
    # Under-generation is not a truncation: nothing was dropped.
    assert summary["truncated"] is False
    assert len(_persona_dirs(dest)) == 3
    assert any("fewer than the requested" in rec.message for rec in caplog.records)


def test_cap_combo_copies_ancillary_files(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=4, with_ancillary=True)
    dest = _cap_stage(tmp_path) / _SLUG

    cap_combo(raw, 2, 0, dest)

    assert (dest / "logs" / "run_0.log").is_file()
    assert (dest / "run_metadata.json").is_file()
    assert (dest / "manifest_snapshot.yaml").is_file()


def test_cap_combo_without_force_raises_on_existing_dest(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=6)
    dest = _cap_stage(tmp_path) / _SLUG
    cap_combo(raw, 3, 0, dest)

    with pytest.raises(FileExistsError):
        cap_combo(raw, 3, 0, dest)


def test_cap_combo_force_fully_replaces_stale_personas(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=8)
    dest = _cap_stage(tmp_path) / _SLUG

    first = cap_combo(raw, 5, 0, dest)
    assert len(_persona_dirs(dest)) == 5

    # A smaller cap with force must not leave any of the first draw's stale dirs behind.
    second = cap_combo(raw, 3, 1, dest, force=True)
    assert len(_persona_dirs(dest)) == 3
    assert _persona_dirs(dest) == sorted(second["selected_ids"])
    stale = set(first["selected_ids"]) - set(second["selected_ids"])
    for name in stale:
        assert not (dest / name).exists()


def test_cap_combo_zero_persona_dirs_handled(tmp_path: Path, caplog):
    combo = tmp_path / "01_Raw" / _SLUG
    combo.mkdir(parents=True)  # combo dir exists but holds no persona_* dirs
    dest = _cap_stage(tmp_path) / _SLUG

    with caplog.at_level("WARNING"):
        summary = cap_combo(combo, 4, 0, dest)

    assert summary["available"] == 0
    assert summary["selected"] == 0
    assert summary["truncated"] is False
    assert dest.is_dir()
    assert _persona_dirs(dest) == []


def test_cap_combo_seed_zero_is_honored_not_unset(tmp_path: Path):
    # 0 must behave as a genuine seed: reproducible and (generally) distinct from other seeds.
    raw = _make_raw_combo(tmp_path, _SLUG, m=12)
    dest0a = _cap_stage(tmp_path) / "s0a"
    dest0b = _cap_stage(tmp_path) / "s0b"
    dest9 = _cap_stage(tmp_path) / "s9"

    s0a = cap_combo(raw, 4, 0, dest0a)
    s0b = cap_combo(raw, 4, 0, dest0b)
    s9 = cap_combo(raw, 4, 9, dest9)

    assert s0a["selected_ids"] == s0b["selected_ids"]      # seed 0 is reproducible
    assert s0a["selected_ids"] != s9["selected_ids"]       # and not a no-op / "unset"


# --------------------------------------------------------------------------- #
# (c) capped_source resolvers -- fail-fast, NO 01_Raw fallback
# --------------------------------------------------------------------------- #


def test_resolve_combo_source_returns_mirror_when_present(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=5)
    dest = _cap_stage(tmp_path) / _SLUG
    cap_combo(raw, 3, 0, dest)

    resolved = resolve_combo_source(_SLUG, tmp_path)
    assert resolved == dest
    assert resolved.is_dir()


def test_resolve_stage_source_returns_stage_when_present(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=5)
    cap_combo(raw, 3, 0, _cap_stage(tmp_path) / _SLUG)

    resolved = resolve_stage_source(tmp_path)
    assert resolved == _cap_stage(tmp_path)
    assert resolved.is_dir()


def test_resolve_combo_source_raises_when_mirror_absent_no_raw_fallback(tmp_path: Path):
    # 01_Raw exists (populated) but the capped mirror was never produced: the resolver
    # must still raise, proving there is no silent fallback to the uncapped raw dir.
    _make_raw_combo(tmp_path, _SLUG, m=5)
    with pytest.raises(FileNotFoundError):
        resolve_combo_source(_SLUG, tmp_path)


def test_resolve_stage_source_raises_when_stage_absent_no_raw_fallback(tmp_path: Path):
    _make_raw_combo(tmp_path, _SLUG, m=5)
    with pytest.raises(FileNotFoundError):
        resolve_stage_source(tmp_path)


# --------------------------------------------------------------------------- #
# (d) integration -- cap -> consumers see exactly N
# --------------------------------------------------------------------------- #


def test_cap_then_mapping_loader_sees_exactly_n(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=9)
    cap_combo(raw, 4, 0, _cap_stage(tmp_path) / _SLUG)

    # The mapping stage reads personas from the resolved capped mirror, not 01_Raw.
    seed_root = resolve_combo_source(_SLUG, tmp_path)
    raw_pop = load_synthetic_population(seed_root)
    assert len(raw_pop["individuals"]) == 4


def test_cap_then_summarize_aggregates_over_n_not_m(tmp_path: Path):
    _make_raw_combo(tmp_path, _SLUG, m=6)
    cap_combo(tmp_path / "01_Raw" / _SLUG, 4, 0, _cap_stage(tmp_path) / _SLUG)

    written = summarize(output_base=tmp_path, countries=["swedish"], charts=False)
    assert "swedish" in written

    payload = json.loads(written["swedish"]["json"].read_text(encoding="utf-8"))
    combo = next(c for c in payload["combos"] if c["model"] == "claude_haiku")
    # Per-persona aggregates must cover the 4 capped personas, never the original 6.
    assert combo["n_personas"] == 4


def test_summarize_fail_fast_when_mirror_absent(tmp_path: Path):
    # Raw exists but population_cap was never run: summarize must raise, not read 01_Raw.
    _make_raw_combo(tmp_path, _SLUG, m=6)
    with pytest.raises(FileNotFoundError):
        summarize(output_base=tmp_path, countries=["swedish"], charts=False)


def test_mapping_seam_fail_fast_when_mirror_absent(tmp_path: Path):
    # The seam map_populations uses (resolve_combo_source) must raise with no mirror.
    _make_raw_combo(tmp_path, _SLUG, m=6)
    with pytest.raises(FileNotFoundError):
        resolve_combo_source(_SLUG, tmp_path)

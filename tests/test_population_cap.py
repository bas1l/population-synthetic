"""Tests for the population_cap analysis process (last node of the validation gate).

Locks the behavior of the seeded clean-pool cap and its read-redirect contract. The cap
runs last of the gate (``validate_raw`` -> ``mapping`` -> ``validate_mapped`` ->
``population_cap``): it intersects the two per-combo validity CSVs to the CLEAN persona
ids, seeded-selects N of them, copies the selected raw ``persona_*`` dirs into the capped
telemetry mirror, and writes a capped mapped file (the mapping index filtered to the same
N) into ``_mapped/``.

- ``utils.sampling.select_indices``      -- reproducible seeded draw; distinct indices;
                                            ``n >= total`` returns all; algorithmic
                                            consistency with ``subsample_population``.
- ``population_cap.cap_combo``            -- over/under-generation, ancillary copy,
                                            ``force`` semantics, 0-clean edge, seed 0,
                                            the capped mapped file's exact-N guarantee, and
                                            read-only (synced-placeholder) sources/mirrors.
- ``utils.capped_source`` resolvers       -- return the mirror when present; **raise
                                            ``FileNotFoundError`` when absent, with NO
                                            fallback to ``01_Raw``**.
- integration                             -- cap -> capped mapped file holds exactly N;
                                            cap -> ``generation_metadata.summarize``
                                            aggregates over N (not M); no-mirror
                                            fail-fast on both consumer seams.

Fixtures materialize a minimal ``01_Raw`` combo (``persona_*/identity.json`` +
``llm_interactions.jsonl`` + optional combo-level ancillary files) plus the two validity
CSVs and the full mapping output the cap consumes, so the tests exercise the real on-disk
layout the cap reads and mirrors.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from population_synthetic.analysis.generation_metadata import summarize
from population_synthetic.analysis.population_cap import cap_combo
from population_synthetic.analysis.utils.capped_source import (
    MAPPED_SUBDIR,
    resolve_combo_source,
    resolve_stage_source,
)
from population_synthetic.analysis.utils.registry import analysis_output_dir
from population_synthetic.analysis.utils.sampling import select_indices, subsample_population
from population_synthetic.analysis.utils.validity_csv import write_validity_csv

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


_COUNTRY = "swedish"

_VR_HEADER = ("persona_id", "passed", "has_identity_json", "missing_categories")
_VM_HEADER = ("persona_id", "passed", "unmapped_fields")


def _write_gate_inputs(
    output_base: Path,
    slug: str,
    raw_slug_dir: Path,
    *,
    country: str = _COUNTRY,
) -> tuple[Path, Path, Path]:
    """Write the two ALL-PASSING validity CSVs + the full mapping output for one combo.

    Mirrors the on-disk state the cap consumes when every persona is clean: one
    ``validate_raw/{slug}.csv`` and ``validate_mapped/{slug}.csv`` row per persona dir
    (all ``passed``), plus a ``mapping/{slug}.json`` carrying one individual per persona
    (``id`` = the ``persona_XXXXX`` dir name) and a ``mapping/real_{country}.json``.

    Returns ``(validate_raw_csv, validate_mapped_csv, mapping_dir)``.
    """
    persona_ids = _persona_dirs(raw_slug_dir)

    vr_csv = analysis_output_dir("validate_raw", output_base) / f"{slug}.csv"
    vm_csv = analysis_output_dir("validate_mapped", output_base) / f"{slug}.csv"
    write_validity_csv(vr_csv, _VR_HEADER, [(pid, True, True, "") for pid in persona_ids])
    write_validity_csv(vm_csv, _VM_HEADER, [(pid, True, "") for pid in persona_ids])

    mapping_dir = analysis_output_dir("mapping", output_base)
    mapping_dir.mkdir(parents=True, exist_ok=True)
    mapped = {
        "metadata": {"n": len(persona_ids)},
        "individuals": [{"id": pid, "age_group": "25-34"} for pid in persona_ids],
    }
    (mapping_dir / f"{slug}.json").write_text(json.dumps(mapped), encoding="utf-8")
    (mapping_dir / f"real_{country}.json").write_text(
        json.dumps({"metadata": {"n": 2}, "individuals": [{"id": "r1"}, {"id": "r2"}]}),
        encoding="utf-8",
    )
    return vr_csv, vm_csv, mapping_dir


def _mapped_dest(output_base: Path) -> Path:
    """The capped mapped dir: ``population_cap/_mapped/``."""
    return analysis_output_dir("population_cap", output_base) / MAPPED_SUBDIR


def _cap(
    output_base: Path,
    raw_slug_dir: Path,
    n: int,
    seed: int,
    dest: Path,
    *,
    slug: str = _SLUG,
    country: str = _COUNTRY,
    force: bool = False,
):
    """Wire the gate inputs for one combo and invoke the new keyword-only ``cap_combo``."""
    vr_csv, vm_csv, mapping_dir = _write_gate_inputs(
        output_base, slug, raw_slug_dir, country=country
    )
    return cap_combo(
        slug=slug,
        country=country,
        raw_slug_dir=raw_slug_dir,
        mapping_dir=mapping_dir,
        validate_raw_csv=vr_csv,
        validate_mapped_csv=vm_csv,
        n=n,
        seed=seed,
        dest_dir=dest,
        mapped_dest_dir=_mapped_dest(output_base),
        force=force,
    )


def _capped_mapped_file(output_base: Path, slug: str = _SLUG) -> Path:
    return _mapped_dest(output_base) / f"{slug}.json"


def _capped_mapped_count(output_base: Path, slug: str = _SLUG) -> int:
    payload = json.loads(_capped_mapped_file(output_base, slug).read_text(encoding="utf-8"))
    return len(payload["individuals"])


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

    summary = _cap(tmp_path, raw, 4, 0, dest)

    assert summary["clean_available"] == 10
    assert summary["selected"] == 4
    assert summary["requested_n"] == 4
    assert summary["truncated"] is True
    assert len(summary["selected_ids"]) == 4
    assert _persona_dirs(dest) == sorted(summary["selected_ids"])
    assert len(_persona_dirs(dest)) == 4
    # NEW core guarantee: the capped mapped file holds exactly `selected` individuals.
    assert summary["mapped_n"] == 4
    assert _capped_mapped_count(tmp_path) == 4


def test_cap_combo_over_generation_deterministic_for_fixed_seed(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=10)
    dest_a = _cap_stage(tmp_path) / "run_a"
    dest_b = _cap_stage(tmp_path) / "run_b"

    a = _cap(tmp_path, raw, 4, 42, dest_a)
    b = _cap(tmp_path, raw, 4, 42, dest_b)
    assert a["selected_ids"] == b["selected_ids"]


def test_cap_combo_under_generation_copies_all_and_warns(tmp_path: Path, caplog):
    raw = _make_raw_combo(tmp_path, _SLUG, m=3)
    dest = _cap_stage(tmp_path) / _SLUG

    with caplog.at_level("WARNING"):
        summary = _cap(tmp_path, raw, 5, 0, dest)

    assert summary["clean_available"] == 3
    assert summary["selected"] == 3
    assert summary["requested_n"] == 5
    # Under-generation is not a truncation: nothing was dropped.
    assert summary["truncated"] is False
    assert len(_persona_dirs(dest)) == 3
    assert any("fewer than the requested" in rec.message for rec in caplog.records)
    # All clean personas flow into the capped mapped file too.
    assert _capped_mapped_count(tmp_path) == 3


def test_cap_combo_copies_ancillary_files(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=4, with_ancillary=True)
    dest = _cap_stage(tmp_path) / _SLUG

    _cap(tmp_path, raw, 2, 0, dest)

    assert (dest / "logs" / "run_0.log").is_file()
    assert (dest / "run_metadata.json").is_file()
    assert (dest / "manifest_snapshot.yaml").is_file()


def test_cap_combo_without_force_raises_on_existing_dest(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=6)
    dest = _cap_stage(tmp_path) / _SLUG
    _cap(tmp_path, raw, 3, 0, dest)

    with pytest.raises(FileExistsError):
        _cap(tmp_path, raw, 3, 0, dest)


def test_cap_combo_force_fully_replaces_stale_personas(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=8)
    dest = _cap_stage(tmp_path) / _SLUG

    first = _cap(tmp_path, raw, 5, 0, dest)
    assert len(_persona_dirs(dest)) == 5

    # A smaller cap with force must not leave any of the first draw's stale dirs behind.
    second = _cap(tmp_path, raw, 3, 1, dest, force=True)
    assert len(_persona_dirs(dest)) == 3
    assert _persona_dirs(dest) == sorted(second["selected_ids"])
    stale = set(first["selected_ids"]) - set(second["selected_ids"])
    for name in stale:
        assert not (dest / name).exists()
    # Force also rewrites the capped mapped file down to the smaller N.
    assert _capped_mapped_count(tmp_path) == 3


def test_cap_combo_zero_persona_dirs_handled(tmp_path: Path, caplog):
    combo = tmp_path / "01_Raw" / _SLUG
    combo.mkdir(parents=True)  # combo dir exists but holds no persona_* dirs
    dest = _cap_stage(tmp_path) / _SLUG

    with caplog.at_level("WARNING"):
        summary = _cap(tmp_path, combo, 4, 0, dest)

    assert summary["clean_available"] == 0
    assert summary["selected"] == 0
    assert summary["truncated"] is False
    assert dest.is_dir()
    assert _persona_dirs(dest) == []
    # The capped mapped file exists but is empty (no clean personas to carry).
    assert _capped_mapped_count(tmp_path) == 0


def test_cap_combo_seed_zero_is_honored_not_unset(tmp_path: Path):
    # 0 must behave as a genuine seed: reproducible and (generally) distinct from other seeds.
    raw = _make_raw_combo(tmp_path, _SLUG, m=12)
    dest0a = _cap_stage(tmp_path) / "s0a"
    dest0b = _cap_stage(tmp_path) / "s0b"
    dest9 = _cap_stage(tmp_path) / "s9"

    s0a = _cap(tmp_path, raw, 4, 0, dest0a)
    s0b = _cap(tmp_path, raw, 4, 0, dest0b)
    s9 = _cap(tmp_path, raw, 4, 9, dest9)

    assert s0a["selected_ids"] == s0b["selected_ids"]      # seed 0 is reproducible
    assert s0a["selected_ids"] != s9["selected_ids"]       # and not a no-op / "unset"


# --------------------------------------------------------------------------- #
# (b2) read-only (OneDrive placeholder) sources and mirrors
# --------------------------------------------------------------------------- #


def _set_writable(path: Path, writable: bool) -> None:
    """Toggle the owner write bit on *path* (Windows: the ReadOnly attribute)."""
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IWRITE if writable else mode & ~stat.S_IWRITE)


def test_cap_combo_force_replaces_readonly_mirror(tmp_path: Path):
    # A previous mirror copied out of a OneDrive-dehydrated source carries the source's
    # read-only bit. `shutil.rmtree` cannot remove such a tree (WinError 5 on rmdir), so
    # the force path must clear the bit and retry rather than crash.
    raw = _make_raw_combo(tmp_path, _SLUG, m=8, with_ancillary=True)
    dest = _cap_stage(tmp_path) / _SLUG
    _cap(tmp_path, raw, 5, 0, dest)

    read_only = [dest / "logs", *(dest / name for name in _persona_dirs(dest))]
    for path in read_only:
        _set_writable(path, False)
    try:
        summary = _cap(tmp_path, raw, 3, 1, dest, force=True)
    finally:
        for path in read_only:
            if path.exists():
                _set_writable(path, True)

    assert len(_persona_dirs(dest)) == 3
    assert _persona_dirs(dest) == sorted(summary["selected_ids"])


def test_cap_combo_does_not_leave_the_mirror_readonly(tmp_path: Path):
    # copytree/copy2 propagate a read-only source mode to the copy, which would make the
    # mirror we just wrote undeletable on the next run. The cap clears it on its own output.
    raw = _make_raw_combo(tmp_path, _SLUG, m=4, with_ancillary=True)
    sources = [raw / "logs", *(raw / name for name in _persona_dirs(raw))]
    for path in sources:
        _set_writable(path, False)
    dest = _cap_stage(tmp_path) / _SLUG
    try:
        _cap(tmp_path, raw, 2, 0, dest)
    finally:
        for path in sources:
            _set_writable(path, True)

    for path in [dest, dest / "logs", *(dest / name for name in _persona_dirs(dest))]:
        assert os.access(path, os.W_OK), f"capped mirror left read-only: {path}"
    # The real reference is copied with copy2 from the same synced pool: a read-only copy
    # would break the NEXT run's copy2 before it ever reached the rmtree.
    assert os.access(_mapped_dest(tmp_path) / f"real_{_COUNTRY}.json", os.W_OK)


# --------------------------------------------------------------------------- #
# (c) capped_source resolvers -- fail-fast, NO 01_Raw fallback
# --------------------------------------------------------------------------- #


def test_resolve_combo_source_returns_mirror_when_present(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=5)
    dest = _cap_stage(tmp_path) / _SLUG
    _cap(tmp_path, raw, 3, 0, dest)

    resolved = resolve_combo_source(_SLUG, tmp_path)
    assert resolved == dest
    assert resolved.is_dir()


def test_resolve_stage_source_returns_stage_when_present(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=5)
    _cap(tmp_path, raw, 3, 0, _cap_stage(tmp_path) / _SLUG)

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


def test_cap_then_capped_mapped_file_has_exactly_n(tmp_path: Path):
    # The mapped-file consumers (fidelity, multivariate, ...) read the CAPPED mapped
    # file population_cap writes into _mapped/, which must hold exactly N individuals --
    # the capped-N guarantee that replaces the old "mapping reads the capped mirror".
    raw = _make_raw_combo(tmp_path, _SLUG, m=9)
    summary = _cap(tmp_path, raw, 4, 0, _cap_stage(tmp_path) / _SLUG)

    assert summary["mapped_n"] == 4
    capped = json.loads(_capped_mapped_file(tmp_path).read_text(encoding="utf-8"))
    assert len(capped["individuals"]) == 4
    # The retained ids are exactly the seeded selection.
    assert sorted(ind["id"] for ind in capped["individuals"]) == sorted(summary["selected_ids"])


def test_cap_then_summarize_aggregates_over_n_not_m(tmp_path: Path):
    raw = _make_raw_combo(tmp_path, _SLUG, m=6)
    _cap(tmp_path, raw, 4, 0, _cap_stage(tmp_path) / _SLUG)

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

"""Unit tests for the analysis registry accessor (Phase 1: no behavior change).

Proves the registry reproduces today's on-disk output paths for every canonical id,
that loading fails loudly on malformed/missing config, and that ``resolve_output_base``
honors the CLI value then falls back to ``experiment_defaults.yaml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from population_synthetic.analysis.utils import registry
from population_synthetic.analysis.utils.registry import (
    ANALYSIS_STAGE_DIR,
    AnalysisProcess,
    analysis_output_dir,
    get_process,
    load_registry,
    resolve_output_base,
)

# Canonical id -> canonical on-disk folder. `mapping` is aligned to its id (`mapping/`);
# the pre-rename `mapped/` folder is reachable only via the legacy-read fallback.
_EXPECTED_FOLDERS = {
    "mapping": "mapping",
    "fidelity": "fidelity",
    "multivariate_fidelity": "multivariate_fidelity",
    "consistency": "consistency",
    "model_ranking": "model_ranking",
    "method_significance": "method_significance",
    "pairwise_comparison": "pairwise_comparison",
    "run_analytics_per_run": "run_analytics",
    "run_analytics_cross_run": "run_analytics/_comparison",
    "cross_country": "cross_country",
}


def test_stage_dir_constant() -> None:
    assert ANALYSIS_STAGE_DIR == "03_Analysis"


def test_registry_has_all_ten_processes() -> None:
    reg = load_registry()
    assert set(reg) == set(_EXPECTED_FOLDERS)
    assert all(isinstance(p, AnalysisProcess) for p in reg.values())


def test_get_process_populates_dataclass() -> None:
    proc = get_process("fidelity")
    assert proc.id == "fidelity"
    assert proc.label
    assert proc.description
    assert proc.folder == "fidelity"
    assert proc.script == "scripts/analyze/score_fidelity_all.py"
    assert proc.dispatch == "slugs"


@pytest.mark.parametrize("process_id,folder", sorted(_EXPECTED_FOLDERS.items()))
def test_analysis_output_dir_for_every_id(process_id: str, folder: str) -> None:
    base = Path("F:/some/output_base")
    expected = base / "03_Analysis" / folder
    assert analysis_output_dir(process_id, base) == expected


def test_analysis_output_dir_accepts_string_base() -> None:
    assert analysis_output_dir("fidelity", "/tmp/base") == Path("/tmp/base") / "03_Analysis" / "fidelity"


# --- mapped -> mapping rename: canonical write folder + legacy-read fallback ---


def test_mapping_process_declares_legacy_folder() -> None:
    proc = get_process("mapping")
    assert proc.folder == "mapping"
    assert proc.legacy_folder == "mapped"


def test_mapping_writes_to_canonical_folder(tmp_path: Path) -> None:
    # Writers (for_read=False, the default) always target the canonical `mapping/` folder,
    # even when a legacy `mapped/` folder already exists on disk.
    (tmp_path / "03_Analysis" / "mapped").mkdir(parents=True)
    assert analysis_output_dir("mapping", tmp_path) == tmp_path / "03_Analysis" / "mapping"
    assert analysis_output_dir("mapping", tmp_path, for_read=False) == tmp_path / "03_Analysis" / "mapping"


def test_mapping_reader_falls_back_to_legacy_when_only_legacy_exists(tmp_path: Path) -> None:
    legacy = tmp_path / "03_Analysis" / "mapped"
    legacy.mkdir(parents=True)
    assert analysis_output_dir("mapping", tmp_path, for_read=True) == legacy


def test_mapping_reader_prefers_canonical_when_both_exist(tmp_path: Path) -> None:
    canonical = tmp_path / "03_Analysis" / "mapping"
    canonical.mkdir(parents=True)
    (tmp_path / "03_Analysis" / "mapped").mkdir(parents=True)
    assert analysis_output_dir("mapping", tmp_path, for_read=True) == canonical


def test_mapping_reader_returns_canonical_when_neither_exists(tmp_path: Path) -> None:
    # Nothing on disk yet: the reader points at the canonical path so the caller fails
    # loudly on the canonical location (never a stale legacy path).
    assert analysis_output_dir("mapping", tmp_path, for_read=True) == tmp_path / "03_Analysis" / "mapping"


def test_for_read_ignored_for_process_without_legacy_folder(tmp_path: Path) -> None:
    # A process with no legacy_folder resolves identically for read and write.
    assert analysis_output_dir("fidelity", tmp_path, for_read=True) == tmp_path / "03_Analysis" / "fidelity"


def test_get_process_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        get_process("not_a_real_process")


def test_load_registry_missing_file_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(registry, "_REGISTRY_PATH", tmp_path / "does_not_exist.yaml")
    with pytest.raises(FileNotFoundError):
        load_registry()


def test_load_registry_missing_stage_dir_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = tmp_path / "reg.yaml"
    bad.write_text("processes:\n  fidelity:\n    label: x\n", encoding="utf-8")
    monkeypatch.setattr(registry, "_REGISTRY_PATH", bad)
    with pytest.raises(ValueError):
        load_registry()


def test_load_registry_missing_required_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = tmp_path / "reg.yaml"
    bad.write_text(
        "stage_dir: '03_Analysis'\n"
        "processes:\n"
        "  fidelity:\n"
        "    label: 'Compare'\n"
        "    description: 'desc'\n"
        "    folder: 'fidelity'\n"
        "    # script and dispatch missing\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_REGISTRY_PATH", bad)
    with pytest.raises(ValueError):
        load_registry()


def test_load_registry_empty_processes_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = tmp_path / "reg.yaml"
    bad.write_text("stage_dir: '03_Analysis'\nprocesses: {}\n", encoding="utf-8")
    monkeypatch.setattr(registry, "_REGISTRY_PATH", bad)
    with pytest.raises(ValueError):
        load_registry()


def test_resolve_output_base_honors_cli_value() -> None:
    assert resolve_output_base("F:/explicit/base") == Path("F:/explicit/base")


def test_resolve_output_base_falls_back_to_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    defaults = tmp_path / "experiment_defaults.yaml"
    defaults.write_text("parameters:\n  output_base: 'F:/from/defaults'\n", encoding="utf-8")
    monkeypatch.setattr(registry, "_DEFAULTS_PATH", defaults)
    assert resolve_output_base(None) == Path("F:/from/defaults")


def test_resolve_output_base_missing_defaults_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(registry, "_DEFAULTS_PATH", tmp_path / "missing.yaml")
    with pytest.raises(FileNotFoundError):
        resolve_output_base(None)


def test_resolve_output_base_no_output_base_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    defaults = tmp_path / "experiment_defaults.yaml"
    defaults.write_text("parameters:\n  mode: 'configurable'\n", encoding="utf-8")
    monkeypatch.setattr(registry, "_DEFAULTS_PATH", defaults)
    with pytest.raises(ValueError):
        resolve_output_base(None)

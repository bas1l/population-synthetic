"""Integration test for the real-population-stats CLI (Phase 3, task 3.2).

Exercises the real CLI edge (``scripts/analyze/analyze_real_population_stats.py``)
end-to-end via subprocess against a tiny, in-memory real-population fixture written
to a ``tmp_path`` ``03_Analysis/mapping/real_swedish.json`` layout -- the same shape
``map_populations.py`` produces. Covers the full artifact set, the idempotent skip,
``--force`` overwrite, and the fail-fast message on a missing mapped file.

The fixture individuals are deliberately tiny and country-agnostic in construction:
built generically from ``load_scheme("swedish").attributes`` (never a hardcoded
attribute list), so every analyzed attribute has a non-null value and none of the 14
axes come out all-null (which would otherwise legitimately skip that attribute's
artifacts per the Phase 1 contract).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.fidelity.scheme import load_scheme

SCRIPT = PROJECT_ROOT / "scripts" / "analyze" / "analyze_real_population_stats.py"
COUNTRY = "swedish"


def _build_individuals(n: int = 5) -> list[dict]:
    """A handful of synthetic individuals covering every analyzed swedish attribute.

    ``age_group`` is derived on the fly from a raw ``age`` int (attr_value's
    contract); every other analyzed attribute gets an arbitrary but non-null string
    so its N > 0 and it is not skipped as all-null.
    """
    attrs = load_scheme(COUNTRY).attributes
    individuals = []
    for i in range(n):
        ind: dict = {}
        for attr in attrs:
            if attr == "age_group":
                ind["age"] = 20 + i  # falls in the "18-24" bound
            else:
                ind[attr] = f"val_{i % 2}"
        individuals.append(ind)
    return individuals


def _write_mapped_real_population(output_base: Path, n: int = 5) -> Path:
    mapping_dir = output_base / "03_Analysis" / "mapping"
    mapping_dir.mkdir(parents=True, exist_ok=True)
    real_path = mapping_dir / f"real_{COUNTRY}.json"
    real_pop = {
        "metadata": {"country": COUNTRY, "source": "unit-test fixture"},
        "individuals": _build_individuals(n),
    }
    real_path.write_text(json.dumps(real_pop), encoding="utf-8")
    return real_path


def _run_cli(output_base: Path, *extra_args: str) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable, str(SCRIPT),
        "--output-base", str(output_base),
        "--country-id", COUNTRY,
        *extra_args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))


def _out_dir(output_base: Path) -> Path:
    return output_base / "03_Analysis" / "real_population_stats" / COUNTRY


def test_full_artifact_set_written(tmp_path: Path):
    _write_mapped_real_population(tmp_path)
    result = _run_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    out_dir = _out_dir(tmp_path)

    attrs = load_scheme(COUNTRY).attributes
    for attr in attrs:
        assert (out_dir / f"{attr}.png").is_file(), f"missing {attr}.png"
        assert (out_dir / f"{attr}.svg").is_file(), f"missing {attr}.svg"
        assert (out_dir / f"{attr}.csv").is_file(), f"missing {attr}.csv"

    assert (out_dir / "overview.png").is_file()
    assert (out_dir / "overview.svg").is_file()


def test_rerun_without_force_skips(tmp_path: Path):
    _write_mapped_real_population(tmp_path)
    first = _run_cli(tmp_path)
    assert first.returncode == 0, first.stderr

    out_dir = _out_dir(tmp_path)
    sample_file = out_dir / f"{load_scheme(COUNTRY).attributes[0]}.png"
    mtime_before = sample_file.stat().st_mtime_ns

    second = _run_cli(tmp_path)
    assert second.returncode == 0, second.stderr
    assert "SKIP" in second.stdout

    assert sample_file.stat().st_mtime_ns == mtime_before


def test_force_overwrites(tmp_path: Path):
    _write_mapped_real_population(tmp_path)
    first = _run_cli(tmp_path)
    assert first.returncode == 0, first.stderr

    out_dir = _out_dir(tmp_path)
    sample_file = out_dir / f"{load_scheme(COUNTRY).attributes[0]}.png"
    mtime_before = sample_file.stat().st_mtime_ns

    forced = _run_cli(tmp_path, "--force")
    assert forced.returncode == 0, forced.stderr
    assert "SKIP" not in forced.stdout

    assert sample_file.stat().st_mtime_ns >= mtime_before


def test_missing_mapped_real_population_fails_fast_naming_mapping_task(tmp_path: Path):
    # No 03_Analysis/mapping/real_swedish.json written at all.
    result = _run_cli(tmp_path)

    assert result.returncode != 0
    assert "mapping" in result.stderr
    assert f"real_{COUNTRY}.json" in result.stderr

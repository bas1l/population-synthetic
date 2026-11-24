"""CLI-edge tests for ``scripts/analyze/summarize_generation_metadata.py`` (Phase 4).

Exercises the thin CLI wrapper's argument surface via subprocess -- specifically the
``--metrics`` subset validation added when the standalone per-run / cross-run LLM
metrics scripts were absorbed into this unified task:

- an unknown ``--metrics`` key fails fast (non-zero exit, names the offender);
- valid ``--metrics`` keys are accepted and thread through cleanly (an empty
  ``01_Raw`` yields the benign "no reports" exit, proving the flag parses/validates
  and reaches ``summarize`` without error).

These stay data-free (an empty capped-mirror stage) so they never touch real telemetry.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.utils.registry import analysis_output_dir

SCRIPT = PROJECT_ROOT / "scripts" / "analyze" / "summarize_generation_metadata.py"


def _run_cli(output_base: Path, *extra_args: str) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable, str(SCRIPT),
        "--output-base", str(output_base),
        *extra_args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))


def _empty_raw_base(tmp_path: Path) -> Path:
    # generation_metadata reads the capped mirror, not 01_Raw; an empty (but present)
    # capped stage is the new-contract equivalent of "no data": resolve_stage_source
    # succeeds, then there are simply no slug dirs to summarize (benign "no reports").
    analysis_output_dir("population_cap", tmp_path).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_unknown_metric_key_fails_fast(tmp_path: Path):
    base = _empty_raw_base(tmp_path)
    result = _run_cli(base, "--metrics", "cost", "not_a_metric")

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "not_a_metric" in combined
    assert "metric key" in combined.lower()


def test_valid_metric_keys_accepted(tmp_path: Path):
    base = _empty_raw_base(tmp_path)
    result = _run_cli(base, "--metrics", "cost", "total_tokens", "--no-charts")

    # Empty 01_Raw -> no slugs -> benign "no reports" exit, but the flag validated
    # and reached summarize without raising.
    assert result.returncode == 0, result.stderr
    assert "No generation-metadata reports" in result.stdout

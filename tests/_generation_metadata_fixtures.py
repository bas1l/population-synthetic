"""Observed ``generation_metadata`` CSV contract, pinned from a real run.

The ``cost_efficiency`` process reads ``03_Analysis/generation_metadata/
{country}_summary.csv``. Its loader must be written against the columns that
process *actually emits*, not against ``report_writer.py`` read by eye, so
:data:`OBSERVED_COLUMNS` records the header row verbatim from the run described
in :data:`PROVENANCE`. A loader test asserting its expected column set against
this tuple fails the day the producer's header changes, which is the point:
the seam between the two processes is an on-disk contract, and a contract that
is never asserted is a contract that drifts.

:func:`make_row` builds one complete row over that header (unknown override keys
raise, so a renamed column cannot be silently ignored) and
:func:`build_summary_csv` materialises a ``{country}_summary.csv`` under a
``tmp_path`` at the path ``analysis_output_dir`` resolves -- never a path literal.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from population_synthetic.analysis.utils.registry import analysis_output_dir

# How OBSERVED_COLUMNS was obtained. Re-derive with this exact command if the
# producer changes; do not hand-edit the tuple below.
PROVENANCE = (
    "python scripts/analyze/summarize_generation_metadata.py --country swedish_02 --strict "
    "(2026-08-20; 58 rows x 71 columns over the swedish_02 capped mirror)"
)

OBSERVED_COUNTRY = "swedish_02"

# The header row of swedish_02_summary.csv, verbatim and in order. Structure:
# 4 identity/availability columns, then <metric>_{mean,std,median,q1,q3,n} for
# each of the 8 distribution metrics, then 3 scalar diagnostics, then
# <metric>_{model,method}_group compact-letter-display columns.
OBSERVED_COLUMNS: tuple[str, ...] = (
    "model",
    "method",
    "n_personas",
    "has_token_data",
    "time_mean",
    "time_std",
    "time_median",
    "time_q1",
    "time_q3",
    "time_n",
    "input_tokens_mean",
    "input_tokens_std",
    "input_tokens_median",
    "input_tokens_q1",
    "input_tokens_q3",
    "input_tokens_n",
    "output_tokens_mean",
    "output_tokens_std",
    "output_tokens_median",
    "output_tokens_q1",
    "output_tokens_q3",
    "output_tokens_n",
    "total_tokens_mean",
    "total_tokens_std",
    "total_tokens_median",
    "total_tokens_q1",
    "total_tokens_q3",
    "total_tokens_n",
    "calls_mean",
    "calls_std",
    "calls_median",
    "calls_q1",
    "calls_q3",
    "calls_n",
    "retry_rate_mean",
    "retry_rate_std",
    "retry_rate_median",
    "retry_rate_q1",
    "retry_rate_q3",
    "retry_rate_n",
    "error_rate_mean",
    "error_rate_std",
    "error_rate_median",
    "error_rate_q1",
    "error_rate_q3",
    "error_rate_n",
    "cost_mean",
    "cost_std",
    "cost_median",
    "cost_q1",
    "cost_q3",
    "cost_n",
    "latency_p95",
    "latency_max",
    "success_rate",
    "time_model_group",
    "time_method_group",
    "input_tokens_model_group",
    "input_tokens_method_group",
    "output_tokens_model_group",
    "output_tokens_method_group",
    "total_tokens_model_group",
    "total_tokens_method_group",
    "calls_model_group",
    "calls_method_group",
    "retry_rate_model_group",
    "retry_rate_method_group",
    "error_rate_model_group",
    "error_rate_method_group",
    "cost_model_group",
    "cost_method_group",
)

# Observed cell shapes, pinned alongside the names because the loader parses them:
#   * ``has_token_data`` serialises as the Python repr ``True`` / ``False``
#     (capitalised), NOT ``true`` / ``false``.
#   * ``n_personas`` and every ``<metric>_n`` are exact integer counts.
#   * every other numeric cell is a float rounded to 6 decimals, and is written
#     EMPTY (not ``0``) when the underlying value is absent.
#   * ``<metric>_<factor>_group`` cells are compact-letter-display strings.
OBSERVED_HAS_TOKEN_DATA_TRUE = "True"
OBSERVED_HAS_TOKEN_DATA_FALSE = "False"

# Axis values present in the pinned run: 12 models x 5 methods spans 60 cells but
# only 58 rows were written. The grid is deliberately incomplete -- an excluded
# combination has no capped mirror, so generation_metadata emits no row for it at
# all (of swedish_02's 7 withdrawals, 5 are a 13th model -- ollama_llama31_8b,
# withdrawn under every method and so absent here entirely -- and 2 are holes in
# this grid). That is exactly why validation_attrition, not this file, is the
# source for withdrawals.
OBSERVED_MODELS = (
    "claude_haiku",
    "claude_sonnet",
    "ollama_deepseek_r1_14b",
    "ollama_gemma4_e4b",
    "ollama_mistral_nemo_12b",
    "openrouter_glm_52",
    "openrouter_gpt56_sol",
    "openrouter_gpt_oss_120b",
    "openrouter_kimi_k3",
    "openrouter_mistral_medium",
    "openrouter_opus_5",
    "openrouter_qwen35_flash",
)
OBSERVED_METHODS = (
    "all_pick_v2",
    "all_pick_dag_v2",
    "all_generate_pick_v2",
    "all_generate_evaluate_pick_v2",
    "all_generate_evaluate_random_pick_v2",
)

# Defaults for a synthetic row. Deliberately non-zero for the float columns: a
# 0.0 default would make every unspecified cost cell read as an unmetered model.
_DEFAULT_COUNT = 100
_DEFAULT_FLOAT = 1.0
_DEFAULT_GROUP = "a"


def _default_cell(column: str) -> Any:
    """The default value for one column, keyed on the column's role."""
    if column == "n_personas" or column.endswith("_n"):
        return _DEFAULT_COUNT
    if column == "has_token_data":
        return OBSERVED_HAS_TOKEN_DATA_TRUE
    if column.endswith("_group"):
        return _DEFAULT_GROUP
    return _DEFAULT_FLOAT


def make_row(model: str, method: str, **overrides: Any) -> dict[str, Any]:
    """One complete summary row over :data:`OBSERVED_COLUMNS`.

    *overrides* set individual cells; ``None`` means absent and is written as an
    empty cell. An override naming a column that is not in the observed header
    raises -- a fixture that silently accepts a stale column name would let a
    loader test pass against a contract the producer no longer emits.
    """
    unknown = sorted(set(overrides) - set(OBSERVED_COLUMNS))
    if unknown:
        raise KeyError(
            f"Unknown generation_metadata column(s) {unknown}; "
            f"the observed header is pinned in {__name__}.OBSERVED_COLUMNS ({PROVENANCE})"
        )
    row = {column: _default_cell(column) for column in OBSERVED_COLUMNS}
    row["model"] = model
    row["method"] = method
    row.update(overrides)
    return row


def build_summary_csv(
    tmp_path: Path,
    rows: list[dict[str, Any]],
    *,
    country: str = OBSERVED_COUNTRY,
) -> Path:
    """Materialise ``generation_metadata/{country}_summary.csv`` under *tmp_path*.

    *rows* are written in order under :data:`OBSERVED_COLUMNS`; each must cover
    exactly those columns (build them with :func:`make_row`). ``None`` cells are
    written empty, matching the producer. Returns the CSV path; *tmp_path* is the
    output_base the analysis processes resolve against.
    """
    for index, row in enumerate(rows):
        if set(row) != set(OBSERVED_COLUMNS):
            missing = sorted(set(OBSERVED_COLUMNS) - set(row))
            extra = sorted(set(row) - set(OBSERVED_COLUMNS))
            raise ValueError(
                f"Row {index} does not match the observed header "
                f"(missing={missing}, extra={extra}); build rows with make_row()"
            )

    output_dir = analysis_output_dir("generation_metadata", tmp_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{country}_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(OBSERVED_COLUMNS)
        for row in rows:
            writer.writerow(["" if row[column] is None else row[column] for column in OBSERVED_COLUMNS])
    return csv_path

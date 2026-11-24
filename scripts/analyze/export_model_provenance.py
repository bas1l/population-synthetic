"""
export_model_provenance.py -- Emit the model-provenance table as a CSV.

Figures name a model the way its maker does -- "Kimi K3", not "openrouter_kimi_k3" --
because no journal leaderboard puts the serving layer on an axis. The serving layer is
nonetheless real provenance for this project: OpenRouter can reroute a model to a
different quantization under an unchanged name, and the two Ollama hosts are different
GPUs. This script is where that dropped provenance is preserved, in the place
HELM-style papers keep it: a table beside the figures rather than text on them.

One row per model axis YAML, with the columns
``model_id, model, provider, api_model, endpoint, host, host_label, discarded``:

- ``model``      the display name printed on figures -- the join back to a chart.
- ``api_model``  the exact string the provider was asked for.
- ``endpoint``   the base URL; EMPTY for a remote provider, meaning its SDK's own
                 endpoint, which the axis config deliberately does not pin.
- ``host``       the machine that answered; EMPTY for a remote provider.
- ``discarded``  whether the model axis has retired itself from the sweep.

Everything is read from config alone -- no run, no generated persona and no analysis
output is consulted -- so the table is reproducible from a clean checkout and is
identical whichever machine emits it.

Output. Defaults to ``{output_base}/03_Analysis/model_provenance/model_provenance.csv``.
The folder is deliberately NOT an analysis-registry process: the registry's entries are
DAG nodes with run inputs, a GUI task and dependents, and this table has none of those.
It sits beside them because that is where a reader of the figures will look for it.

Usage:
    python scripts/analyze/export_model_provenance.py
    python scripts/analyze/export_model_provenance.py --output-base /path/to/02_Data
    python scripts/analyze/export_model_provenance.py --output some/where/provenance.csv
    python scripts/analyze/export_model_provenance.py --stdout
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from population_synthetic.analysis.utils.labels import PROVENANCE_COLUMNS, model_provenance_rows
from population_synthetic.analysis.utils.registry import ANALYSIS_STAGE_DIR, resolve_output_base
from population_synthetic.analysis.utils.tidy_csv import encode_bool, write_rows

# The output folder and filename. Named here rather than in the registry for the reason
# given in the module docstring; the ``03_Analysis`` stage segment still comes from the
# registry, which is the only place that literal is defined.
PROVENANCE_FOLDER = "model_provenance"
PROVENANCE_FILENAME = "model_provenance.csv"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit the model-provenance table (provider, endpoint, host per model axis) as a CSV."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Explicit CSV path. Defaults to "
        f"{{output_base}}/{ANALYSIS_STAGE_DIR}/{PROVENANCE_FOLDER}/{PROVENANCE_FILENAME}.",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Analysis output base; falls back to config/synthetic/experiment_defaults.yaml. "
        "Ignored when --output is given.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write the CSV to standard output instead of to a file.",
    )
    return parser.parse_args(argv)


def _encode(rows: list[dict[str, object]]) -> list[list[str]]:
    """Render each record as its CSV cells, in :data:`PROVENANCE_COLUMNS` order."""
    encoded: list[list[str]] = []
    for row in rows:
        encoded.append(
            [encode_bool(row[column]) if column == "discarded" else str(row[column]) for column in PROVENANCE_COLUMNS]
        )
    return encoded


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = _encode(model_provenance_rows())

    if args.stdout:
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(list(PROVENANCE_COLUMNS))
        writer.writerows(rows)
        return 0

    if args.output:
        path = Path(args.output)
    else:
        base = resolve_output_base(args.output_base)
        path = base / ANALYSIS_STAGE_DIR / PROVENANCE_FOLDER / PROVENANCE_FILENAME

    write_rows(path, PROVENANCE_COLUMNS, rows)
    print(f"Wrote {len(rows)} model provenance rows to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

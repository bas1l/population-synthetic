"""
artifacts.py -- Single point that fans a comparison report out to disk.

One shared writer, :func:`write_comparison_artifacts`, so every fidelity driver
(``score_fidelity_sweden`` / ``score_fidelity_italy`` / ``score_fidelity_all``) emits the
*same* set of files. Before this module the fan-out was copy-pasted into each
driver and had drifted -- ISTAT emitted neither the association CSV nor the
heatmap, and only some drivers cleaned the charts dir.

This is a leaf: it imports the pure CSV writers from ``evaluator`` and the figure
functions from ``charts`` (neither of which imports this module), so no import
cycle is introduced.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Any

from population_synthetic.analysis.fidelity.charts import (
    plot_association_heatmap,
    plot_c2st,
    plot_coherence,
    plot_combination_plausibility,
    plot_comparison_charts,
    plot_joint_chi_sq,
    plot_joint_fidelity,
    plot_radar_comparison,
)
from population_synthetic.analysis.fidelity.evaluator import (
    write_association_csv,
    write_c2st_csv,
    write_coherence_csv,
    write_combination_plausibility_csv,
    write_csv_summary,
    write_joint_chi_sq_csv,
    write_joint_fidelity_csv,
)


def _clear_readonly_and_retry(func, target, _exc) -> None:
    """rmtree error handler: clear the read-only bit and retry the failed unlink/rmdir.

    Accepts the three positional args of both ``shutil.rmtree(onerror=...)`` (<3.12) and
    ``onexc=...`` (>=3.12); the third arg (exc-info tuple vs exception) is ignored.
    """
    os.chmod(target, stat.S_IWRITE)
    func(target)


def _rmtree_resilient(path: Path, *, attempts: int = 5, base_delay: float = 0.5) -> None:
    """Recursively delete *path*, tolerating read-only files and transient sync locks.

    A plain ``shutil.rmtree`` raises ``PermissionError`` (WinError 5) on Windows when a file
    in the tree is read-only or momentarily locked -- the common case when the output lives
    in a OneDrive/SharePoint-synced folder the sync engine is mid-upload on. The per-file
    handler clears the read-only bit and retries the offending removal; the outer loop
    retries the whole tree with exponential backoff to ride out a transient lock. Re-raises
    the last error if every attempt fails (fail-fast invariant).
    """
    for attempt in range(attempts):
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=_clear_readonly_and_retry)
            else:
                shutil.rmtree(path, onerror=_clear_readonly_and_retry)
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


def write_comparison_artifacts(
    report: dict[str, Any],
    real_pop: dict,
    synthetic_pop: dict,
    output_path: Path,
    scheme: Any,
    *,
    slug: str,
    real_label: str,
    charts_dir: Path | None = None,
    no_charts: bool = False,
    radar_tv_only: bool = False,
    include_legacy: bool = True,
    clean_charts_dir: bool = True,
) -> None:
    """Write the JSON report, every CSV table, and (unless *no_charts*) every figure.

    *output_path* is the ``.../{slug}/{slug}.json`` path; the CSVs are written as
    its siblings (``{stem}.csv``, ``{stem}_association.csv``, ...) and the charts
    land in *charts_dir* (default ``output_path.parent / output_path.stem``).

    The legacy tier (joint chi-squared + coherence) is gated by *include_legacy*
    so it can be dropped in one call. Every writer/figure degrades gracefully on a
    missing block or a tiny/failed synthetic B (header-only CSV, ``None`` figure).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport written to {output_path}")

    _write_tables(report, output_path, include_legacy=include_legacy)

    if not no_charts:
        _write_charts(
            report, real_pop, synthetic_pop, output_path, scheme,
            slug=slug, real_label=real_label, charts_dir=charts_dir,
            radar_tv_only=radar_tv_only, include_legacy=include_legacy,
            clean_charts_dir=clean_charts_dir,
        )


def _write_tables(report: dict[str, Any], output_path: Path, *, include_legacy: bool) -> None:
    """Emit the CSV tables next to *output_path* (the JSON report)."""
    def _sibling(suffix: str) -> Path:
        # {stem}.csv, {stem}_association.csv, {stem}_c2st.csv, ...
        return output_path.with_name(f"{output_path.stem}{suffix}.csv")

    tables: list[tuple[str, Any]] = [
        ("", write_csv_summary),                                   # marginals
        ("_association", write_association_csv),
        ("_c2st", write_c2st_csv),
        ("_joint_fidelity", write_joint_fidelity_csv),
        ("_combination_plausibility", write_combination_plausibility_csv),
    ]
    if include_legacy:
        tables += [
            ("_joint_chi_sq", write_joint_chi_sq_csv),
            ("_coherence", write_coherence_csv),
        ]

    for suffix, writer in tables:
        path = _sibling(suffix)
        writer(report, path)
        print(f"CSV written to {path}")


def _write_charts(
    report: dict[str, Any],
    real_pop: dict,
    synthetic_pop: dict,
    output_path: Path,
    scheme: Any,
    *,
    slug: str,
    real_label: str,
    charts_dir: Path | None,
    radar_tv_only: bool,
    include_legacy: bool,
    clean_charts_dir: bool,
) -> None:
    """Render every figure into the charts dir."""
    charts_dir = Path(charts_dir) if charts_dir is not None else output_path.parent / output_path.stem
    if clean_charts_dir and charts_dir.exists():
        _rmtree_resilient(charts_dir)

    plot_comparison_charts(
        real_pop,
        synthetic_pop,
        charts_dir,
        pop_a_label=real_label,
        pop_b_label=slug,
        prefix=slug,
        attributes=scheme.attributes,
        categories=scheme.categories,
    )
    print(f"Charts written to {charts_dir}")

    # Each of these returns a Path (or None when nothing was plottable).
    figures = [
        plot_radar_comparison(
            report["marginals"], charts_dir, pop_a_label=real_label, pop_b_label=slug,
            show_chi_sq=not radar_tv_only, prefix=slug, attributes=scheme.attributes,
        ),
        plot_association_heatmap(report, charts_dir, prefix=slug, attributes=scheme.attributes),
        plot_c2st(report, charts_dir, prefix=slug),
        plot_joint_fidelity(report, charts_dir, prefix=slug, attributes=scheme.attributes),
        plot_combination_plausibility(report, charts_dir, prefix=slug),
    ]
    if include_legacy:
        figures += [
            plot_joint_chi_sq(report, charts_dir, prefix=slug),
            plot_coherence(report, charts_dir, prefix=slug),
        ]

    for path in figures:
        if path is not None:
            print(f"Figure written to {path}")

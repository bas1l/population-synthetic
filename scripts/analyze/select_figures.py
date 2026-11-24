"""
select_figures.py -- Publish a config-declared figure set out of the analysis stage.

Terminal node of the analysis DAG, and the one task that COMPUTES NOTHING. It draws no
figure, imports no chart module and makes no publication decision: it reads the roster in
``config/analysis/figure_selection.yaml``, resolves each entry against the analysis stage
(``03_Analysis``), and copies the files the presentation layer already wrote into the
figures stage (``04_Figures``) -- in every published format, under two namings.

Per country and set, the emitted layout is::

    04_Figures/{country}/{set}/
        as_generated/   the source filenames verbatim (traceable back by name alone)
        numbered/       F07_model_x_method_heatmap.{png,svg,eps} (the manuscript's own
                        numbering, taken from the roster's `n`)
        _index.json     provenance: output_base, country, set, run timestamp, and per
                        entry the resolved source path, size, mtime and SHA-256 of every
                        format, plus both destination filenames

Resolve-all, validate-all, THEN copy: an unknown set, an unregistered process id, a stem
with nothing behind it, a figure present in fewer than every published format, a duplicate
figure number or a destination-filename collision each raise before a single byte moves, so
a run that is going to fail leaves the figures stage exactly as it found it. A missing
figure is reported with EVERY other missing figure, not just the first.

There is no default country: publishing a roster is a targeted act, and the other declared
country axes have no analysis stage on a typical tree, so a default would either publish
the wrong country or fail on it. ``--set`` defaults only when the roster declares exactly
one set; from the second set onward the choice is the operator's and a bare invocation
raises, listing them.

Re-runs overwrite what they publish. A destination file the current roster no longer claims
is reported at WARNING and left in place -- it is usually a previous, larger set -- unless
``--force`` clears the set's two naming folders first, which is how a shrinking roster
leaves nothing stale behind. ``--force`` is bounded to ``{country}/{set}/``: no other
country, set or stage is touched.

Usage:
    python scripts/analyze/select_figures.py --country-id swedish_02
    python scripts/analyze/select_figures.py --country-id swedish_02 --set manuscript
    python scripts/analyze/select_figures.py --country-id swedish_02 --country-id italian
    python scripts/analyze/select_figures.py --country-id swedish_02 --force

Flags:
--country-id    Country axis ID to publish for. Repeatable. REQUIRED (no default).
--set           Figure set name from config/analysis/figure_selection.yaml.
                Default: the only declared set, when the roster declares exactly one.
--output-base   Base output directory (parent of BOTH stage folders).
                Default: config/synthetic/experiment_defaults.yaml.
--force         Clear the set's two naming folders before copying, so a roster that
                shrank leaves nothing stale behind.
"""

from __future__ import annotations

import argparse
import logging
import sys

from population_synthetic.analysis.figure_selection.config import known_set_names, load_figure_set
from population_synthetic.analysis.figure_selection.export import (
    NAMINGS,
    ExportResult,
    export_figure_set,
)
from population_synthetic.analysis.utils.country_config import known_country_ids
from population_synthetic.analysis.utils.registry import resolve_output_base

# The copier reports through the logging module -- notably the WARNING naming every
# destination file the current roster no longer claims -- so a bare run must configure a
# handler or that report is silently dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy a config-declared set of figures out of the analysis stage into "
        "the figures stage, in every published format and under both namings."
    )
    parser.add_argument(
        "--country-id",
        dest="country_ids",
        action="append",
        required=True,
        metavar="COUNTRY_ID",
        help="Country axis ID to publish the set for (e.g. 'swedish_02'). May be repeated. "
        "Required: there is no default country.",
    )
    parser.add_argument(
        "--set",
        dest="set_name",
        default=None,
        metavar="SET",
        help="Figure set to publish, from config/analysis/figure_selection.yaml. "
        "Default: the only declared set, when the roster declares exactly one.",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the parent of both stage folders). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear the set's two naming folders before copying, so a figure dropped from "
        "the roster leaves nothing stale behind (bounded to {country}/{set}/).",
    )
    return parser.parse_args()


def _resolve_set_name(requested: str | None) -> str:
    """Resolve ``--set`` against the roster's declared sets (fail-fast).

    An unknown name raises listing the known ones. An omitted name resolves only while
    the roster declares exactly one set -- there is no baked-in default set name, so the
    moment a second set exists the choice becomes the operator's rather than this
    script's.
    """
    known = known_set_names()
    if requested:
        if requested not in known:
            raise ValueError(
                f"Unknown figure set {requested!r}: known sets are {list(known)}."
            )
        return requested
    if len(known) == 1:
        return known[0]
    raise ValueError(
        f"--set is required: the roster declares {len(known)} sets {list(known)}, so which "
        "one to publish is not inferable."
    )


def _validate_countries(country_ids: list[str]) -> list[str]:
    """Validate the requested country ids against the country axis, preserving order."""
    known = known_country_ids()
    unknown = [cid for cid in country_ids if cid not in known]
    if unknown:
        raise ValueError(f"Unknown country id(s) {unknown}: valid ids are {sorted(known)}.")
    ordered: list[str] = []
    for country in country_ids:
        if country not in ordered:
            ordered.append(country)
    return ordered


def _print_result(result: ExportResult) -> None:
    """Report one published (country, set): what landed, and what was left beside it."""
    print(f"  {len(result.figures)} figure(s) -> {result.n_files} file(s) in {result.set_dir}")
    for naming in NAMINGS:
        print(f"    {naming}/")
    print(f"  Manifest: {result.index_path}")
    if result.unclaimed:
        print(
            f"  WARNING: {len(result.unclaimed)} file(s) in the destination were not written "
            "by this run and were left in place (re-run with --force to clear them)."
        )


def main() -> None:
    args = _parse_args()

    try:
        set_name = _resolve_set_name(args.set_name)
        countries = _validate_countries(args.country_ids)
        figure_set = load_figure_set(set_name)
        output_base = resolve_output_base(args.output_base)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Figure set {set_name!r}: {len(figure_set.entries)} entry/entries, output base {output_base}")

    published = 0
    for country in countries:
        print(f"=== {country.upper()} ===")
        try:
            result = export_figure_set(
                figure_set, country=country, output_base=output_base, force=args.force,
            )
        except (FileNotFoundError, ValueError) as exc:
            # One country per invocation is the GUI's dispatch, so a failure here is the
            # whole unit of work. Anything already published for an earlier --country-id
            # is complete and stays: each (country, set) is its own atomic export.
            print(f"ERROR: {exc}", file=sys.stderr)
            if published:
                print(
                    f"Published {published} country/countries before the failure; "
                    "they are complete and were not rolled back.",
                    file=sys.stderr,
                )
            sys.exit(1)
        _print_result(result)
        print()
        published += 1

    print(f"Published figure set {set_name!r} for {published} country/countries.")


if __name__ == "__main__":
    main()

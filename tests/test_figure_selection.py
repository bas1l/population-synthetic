"""Unit and integration tests for figure selection: the roster, its resolver, the copier.

Three things are proved here. First, that the schema's two placeholders plus literal
segments express **all six** path shapes the analysis stage actually uses -- the
acceptance test the plan sets for the schema. Second, that every row of the validation
contract raises, and raises naming what was wrong, before any byte is copied. Third,
that a set publishes into both namings in every format with a manifest that accounts
for each file -- and that a set which fails any gate leaves the figures stage exactly
as it found it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.figure_selection.config import (
    FigureEntry,
    FigureSet,
    SlugSpec,
    known_set_names,
    load_figure_set,
)
from population_synthetic.analysis.figure_selection.export import (
    INDEX_FILENAME,
    NAMING_AS_GENERATED,
    NAMING_NUMBERED,
    export_figure_set,
)
from population_synthetic.analysis.figure_selection.resolve import (
    check_basename_collisions,
    check_sources_exist,
    resolve_entry,
    resolve_set,
)
from population_synthetic.analysis.utils.country_config import known_country_ids
from population_synthetic.analysis.utils.figures import OUTPUT_SUFFIXES
from population_synthetic.analysis.utils.registry import (
    ANALYSIS_STAGE_DIR,
    FIGURES_STAGE_DIR,
    STAGE_FIGURES,
    get_process,
)
from population_synthetic.generators.synthetic.manifest_loader import axis_slug
from population_synthetic.gui.commands import build_per_country_cmds
from population_synthetic.gui.workflow_config_model import WorkflowConfigModel
from population_synthetic.gui.workflow_state import WorkflowState

COUNTRY = "swedish_02"
MODEL = "claude_sonnet"
STRATEGY = "all_pick_v2"
SLUG = axis_slug(MODEL, STRATEGY, COUNTRY)

# The six live path shapes, as {label: (source stem, slug block or None, resolved stem)}.
# Shapes 5 and 6 pin a literal segment: `generation_metadata`'s per-combo chart folder
# is keyed `{strategy}_{model}` with no country in it (so it is not an axis slug and
# {slug} does not describe it), and the marginal-progression model is a research
# decision about which panel is published rather than a run-varying coordinate.
_SHAPES: dict[str, tuple[str, dict[str, str] | None, str]] = {
    "process/country_name": (
        "model_ranking/{country}_model_method_heatmap",
        None,
        f"model_ranking/{COUNTRY}_model_method_heatmap",
    ),
    "process/country/name": (
        "realism_ranking/{country}/impossibility_forest",
        None,
        f"realism_ranking/{COUNTRY}/impossibility_forest",
    ),
    "process/country/slug/name": (
        "persona_realism/{country}/{slug}/typicality",
        {"model": MODEL, "strategy": STRATEGY},
        f"persona_realism/{COUNTRY}/{SLUG}/typicality",
    ),
    "process/slug/slug/slug_attr": (
        "fidelity/{slug}/{slug}/{slug}_age_group",
        {"model": MODEL, "strategy": STRATEGY},
        f"fidelity/{SLUG}/{SLUG}/{SLUG}_age_group",
    ),
    "process/charts/combo/name": (
        f"generation_metadata/charts/{STRATEGY}_{MODEL}/latency_by_category",
        None,
        f"generation_metadata/charts/{STRATEGY}_{MODEL}/latency_by_category",
    ),
    "process/country_sub/model/attr": (
        "method_significance/{country}_marginal_progression/claude_haiku/age_group",
        None,
        f"method_significance/{COUNTRY}_marginal_progression/claude_haiku/age_group",
    ),
}


def _write_roster(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "figure_selection.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _shape_roster(tmp_path: Path) -> Path:
    lines = ["sets:", "  probe:"]
    for number, (source, slug, _) in enumerate(_SHAPES.values(), start=1):
        lines += [f"    - n: {number}", f"      name: shape_{number}", f'      source: "{source}"']
        if slug is not None:
            lines.append(f"      slug: {{model: {slug['model']}, strategy: {slug['strategy']}}}")
    return _write_roster(tmp_path, "\n".join(lines) + "\n")


def _touch_figure(base: Path, stem: str, suffixes: tuple[str, ...] = OUTPUT_SUFFIXES) -> None:
    """Create one figure's files in a fixture analysis tree."""
    path = base / ANALYSIS_STAGE_DIR / stem
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in suffixes:
        path.with_name(path.name + suffix).write_bytes(b"x")


# --- the shipped roster ------------------------------------------------------


def test_shipped_roster_declares_the_manuscript_set() -> None:
    assert "manuscript" in known_set_names()


def test_shipped_manuscript_set_loads_and_is_ordered() -> None:
    figure_set = load_figure_set("manuscript")
    assert figure_set.name == "manuscript"
    assert len(figure_set.entries) == 22
    numbers = [entry.n for entry in figure_set.entries]
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == len(numbers)


def test_shipped_manuscript_set_resolves_without_a_tree(tmp_path: Path) -> None:
    # Resolution is pure path arithmetic: no analysis tree is needed to produce paths,
    # only to check they exist. Every entry must survive the collision gate.
    resolved = resolve_set(load_figure_set("manuscript"), country=COUNTRY, output_base=tmp_path)
    assert len(resolved) == 22
    assert len({figure.basename for figure in resolved}) == 22


# --- the six live path shapes ------------------------------------------------


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_every_live_path_shape_resolves(shape: str, tmp_path: Path) -> None:
    _, _, expected_stem = _SHAPES[shape]
    figure_set = load_figure_set("probe", _shape_roster(tmp_path))
    _touch_figure(tmp_path, expected_stem)

    figure = next(f for f in resolve_set(figure_set, country=COUNTRY, output_base=tmp_path)
                  if f.stem == expected_stem)
    check_sources_exist([figure], set_name="probe")
    assert all(path.is_file() for path in figure.paths.values())
    assert figure.basename == expected_stem.rsplit("/", 1)[-1]


def test_all_six_shapes_pass_the_existence_gate_together(tmp_path: Path) -> None:
    figure_set = load_figure_set("probe", _shape_roster(tmp_path))
    for _, _, stem in _SHAPES.values():
        _touch_figure(tmp_path, stem)
    resolved = resolve_set(figure_set, country=COUNTRY, output_base=tmp_path)
    check_sources_exist(resolved, set_name="probe")
    assert len(resolved) == len(_SHAPES)


def test_slug_is_composed_through_axis_slug(tmp_path: Path) -> None:
    entry = FigureEntry(n=1, name="x", source="fidelity/{slug}/{slug}_age_group",
                        slug=SlugSpec(model=MODEL, strategy=STRATEGY))
    figure = resolve_entry(entry, country=COUNTRY, output_base=tmp_path)
    assert figure.stem == f"fidelity/{SLUG}/{SLUG}_age_group"


def test_country_is_substituted_everywhere_it_appears(tmp_path: Path) -> None:
    entry = FigureEntry(n=1, name="x", source="realism_ranking/{country}/{country}_probe")
    figure = resolve_entry(entry, country="italian_01", output_base=tmp_path)
    assert figure.stem == "realism_ranking/italian_01/italian_01_probe"


def test_numbered_basename_uses_the_figure_number_and_name(tmp_path: Path) -> None:
    entry = FigureEntry(n=7, name="model_x_method_heatmap", source="model_ranking/{country}_x")
    figure = resolve_entry(entry, country=COUNTRY, output_base=tmp_path)
    assert figure.numbered_basename == "F07_model_x_method_heatmap"


# --- the format list is borrowed, not restated -------------------------------


def test_formats_are_exactly_output_suffixes(tmp_path: Path) -> None:
    entry = FigureEntry(n=1, name="x", source="model_ranking/{country}_x")
    figure = resolve_entry(entry, country=COUNTRY, output_base=tmp_path)
    assert set(figure.paths) == set(OUTPUT_SUFFIXES)
    for suffix, path in figure.paths.items():
        assert path.name.endswith(suffix)


def test_paths_hang_off_the_registry_stage_folder(tmp_path: Path) -> None:
    entry = FigureEntry(n=1, name="x", source="model_ranking/{country}_x")
    figure = resolve_entry(entry, country=COUNTRY, output_base=tmp_path)
    assert figure.paths[".png"] == (
        tmp_path / ANALYSIS_STAGE_DIR / "model_ranking" / f"{COUNTRY}_x.png"
    )


# --- the raise paths ---------------------------------------------------------


def test_unknown_set_raises_listing_the_known_sets(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, 'sets:\n  manuscript:\n    - {n: 1, name: a, source: "fidelity/a"}\n')
    with pytest.raises(KeyError, match="manuscript"):
        load_figure_set("deck", roster)


def test_missing_roster_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="figure_selection"):
        load_figure_set("manuscript", tmp_path / "figure_selection.yaml")


def test_empty_sets_mapping_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sets"):
        load_figure_set("manuscript", _write_roster(tmp_path, "sets: {}\n"))


def test_unregistered_process_id_raises_naming_it(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, 'sets:\n  s:\n    - {n: 1, name: a, source: "not_a_process/a"}\n')
    with pytest.raises(ValueError, match="not_a_process"):
        load_figure_set("s", roster)


def test_source_without_a_stem_below_the_process_raises(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, 'sets:\n  s:\n    - {n: 1, name: a, source: "fidelity"}\n')
    with pytest.raises(ValueError, match="extension-less stem"):
        load_figure_set("s", roster)


def test_unknown_placeholder_raises_naming_it(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, 'sets:\n  s:\n    - {n: 1, name: a, source: "fidelity/{model}_x"}\n')
    with pytest.raises(ValueError, match="unknown placeholder"):
        load_figure_set("s", roster)


def test_slug_placeholder_without_a_slug_block_raises(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, 'sets:\n  s:\n    - {n: 1, name: a, source: "fidelity/{slug}/x"}\n')
    with pytest.raises(ValueError, match="declares no 'slug' block"):
        load_figure_set("s", roster)


def test_slug_block_without_the_placeholder_raises(tmp_path: Path) -> None:
    roster = _write_roster(
        tmp_path,
        "sets:\n  s:\n    - n: 1\n      name: a\n      source: \"fidelity/{country}_x\"\n"
        f"      slug: {{model: {MODEL}, strategy: {STRATEGY}}}\n",
    )
    with pytest.raises(ValueError, match="never uses"):
        load_figure_set("s", roster)


def test_incomplete_slug_block_raises(tmp_path: Path) -> None:
    roster = _write_roster(
        tmp_path,
        "sets:\n  s:\n    - n: 1\n      name: a\n      source: \"fidelity/{slug}/x\"\n"
        f"      slug: {{model: {MODEL}}}\n",
    )
    with pytest.raises(ValueError, match="strategy"):
        load_figure_set("s", roster)


def test_duplicate_figure_number_raises_naming_both(tmp_path: Path) -> None:
    roster = _write_roster(
        tmp_path,
        'sets:\n  s:\n    - {n: 3, name: a, source: "fidelity/a"}\n'
        '    - {n: 3, name: b, source: "fidelity/b"}\n',
    )
    with pytest.raises(ValueError, match="repeats figure number"):
        load_figure_set("s", roster)


def test_repeated_source_stem_raises(tmp_path: Path) -> None:
    roster = _write_roster(
        tmp_path,
        'sets:\n  s:\n    - {n: 1, name: a, source: "fidelity/a"}\n'
        '    - {n: 2, name: b, source: "fidelity/a"}\n',
    )
    with pytest.raises(ValueError, match="repeats source stem"):
        load_figure_set("s", roster)


def test_non_integer_figure_number_raises(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, 'sets:\n  s:\n    - {n: "3b", name: a, source: "fidelity/a"}\n')
    with pytest.raises(ValueError, match="positive integer"):
        load_figure_set("s", roster)


def test_unknown_entry_key_raises(tmp_path: Path) -> None:
    roster = _write_roster(
        tmp_path, 'sets:\n  s:\n    - {n: 1, name: a, source: "fidelity/a", format: png}\n'
    )
    with pytest.raises(ValueError, match="format"):
        load_figure_set("s", roster)


def test_colliding_basenames_raise_naming_both_sources(tmp_path: Path) -> None:
    # Distinct stems, same last segment: the analysis stage disambiguates by directory,
    # `as_generated/` cannot.
    roster = _write_roster(
        tmp_path,
        'sets:\n  s:\n    - {n: 1, name: a, source: "realism_ranking/{country}/overview"}\n'
        '    - {n: 2, name: b, source: "real_population_stats/{country}/overview"}\n',
    )
    figure_set = load_figure_set("s", roster)
    with pytest.raises(ValueError, match="same as_generated basename"):
        resolve_set(figure_set, country=COUNTRY, output_base=tmp_path)


def test_missing_png_raises_listing_every_offender(tmp_path: Path) -> None:
    entries = [
        FigureEntry(n=1, name="present", source="model_ranking/{country}_present"),
        FigureEntry(n=2, name="absent_a", source="model_ranking/{country}_absent_a"),
        FigureEntry(n=3, name="absent_b", source="model_ranking/{country}_absent_b"),
    ]
    _touch_figure(tmp_path, f"model_ranking/{COUNTRY}_present")
    resolved = [resolve_entry(e, country=COUNTRY, output_base=tmp_path) for e in entries]
    with pytest.raises(FileNotFoundError) as excinfo:
        check_sources_exist(resolved, set_name="s")
    message = str(excinfo.value)
    assert "absent_a" in message and "absent_b" in message
    assert "2 figure(s) not found" in message


def test_missing_vector_sibling_raises_as_a_partial_format_set(tmp_path: Path) -> None:
    _touch_figure(tmp_path, f"model_ranking/{COUNTRY}_partial", suffixes=(".png", ".svg"))
    entry = FigureEntry(n=1, name="partial", source="model_ranking/{country}_partial")
    resolved = [resolve_entry(entry, country=COUNTRY, output_base=tmp_path)]
    with pytest.raises(FileNotFoundError, match="partial format set is never copied"):
        check_sources_exist(resolved, set_name="s")


def test_blank_country_raises(tmp_path: Path) -> None:
    entry = FigureEntry(n=1, name="a", source="model_ranking/{country}_a")
    with pytest.raises(ValueError, match="non-empty country"):
        resolve_entry(entry, country="  ", output_base=tmp_path)


def test_basename_collision_check_accepts_a_distinct_set(tmp_path: Path) -> None:
    entries = [
        FigureEntry(n=1, name="a", source="model_ranking/{country}_a"),
        FigureEntry(n=2, name="b", source="model_ranking/{country}_b"),
    ]
    resolved = [resolve_entry(e, country=COUNTRY, output_base=tmp_path) for e in entries]
    check_basename_collisions(resolved, set_name="s")


def test_source_climbing_out_of_its_process_folder_raises(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, 'sets:\n  s:\n    - {n: 1, name: a, source: "fidelity/../mapping/a"}\n')
    with pytest.raises(ValueError, match="stay inside its process folder"):
        load_figure_set("s", roster)


def test_source_with_backslash_separators_raises(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, "sets:\n  s:\n    - {n: 1, name: a, source: 'fidelity\\a'}\n")
    with pytest.raises(ValueError, match="stay inside its process folder"):
        load_figure_set("s", roster)


# --- the copier and its manifest (Phase 3) -----------------------------------


def _figure_bytes(stem: str, suffix: str) -> bytes:
    """Distinguishable content per file, so a copy can be proved byte-for-byte."""
    return f"{stem}{suffix}".encode("utf-8")


def _write_figure(base: Path, stem: str, suffixes: tuple[str, ...] = OUTPUT_SUFFIXES) -> None:
    """Create one figure's files with per-file content in a fixture analysis tree."""
    path = base / ANALYSIS_STAGE_DIR / stem
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in suffixes:
        path.with_name(path.name + suffix).write_bytes(_figure_bytes(stem, suffix))


def _export_roster(tmp_path: Path, *, entries: tuple[tuple[int, str, str], ...]) -> Path:
    lines = ["sets:", "  s:"]
    for number, name, source in entries:
        lines += [f"    - n: {number}", f"      name: {name}", f'      source: "{source}"']
    return _write_roster(tmp_path, "\n".join(lines) + "\n")


_EXPORT_ENTRIES = (
    (2, "reference_proportions", "real_population_stats/{country}/overview"),
    (7, "model_x_method_heatmap", "model_ranking/{country}_model_method_heatmap"),
    (19, "axisA_impossibility", "realism_ranking/{country}/impossibility_heatmap"),
)


def _stage_a_set(
    tmp_path: Path,
    *,
    country: str = COUNTRY,
    entries: tuple[tuple[int, str, str], ...] = _EXPORT_ENTRIES,
) -> FigureSet:
    """Build a fixture analysis tree for *entries* and return the loaded set."""
    figure_set = load_figure_set("s", _export_roster(tmp_path, entries=entries))
    for entry in figure_set.entries:
        _write_figure(tmp_path, entry.source.format(country=country))
    return figure_set


def _set_dir(tmp_path: Path, country: str = COUNTRY, set_name: str = "s") -> Path:
    return tmp_path / FIGURES_STAGE_DIR / country / set_name


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Every file under *root*, as relative path -> content."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_export_emits_both_namings_in_every_format(tmp_path: Path) -> None:
    figure_set = _stage_a_set(tmp_path)
    result = export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)

    as_generated = _set_dir(tmp_path) / NAMING_AS_GENERATED
    numbered = _set_dir(tmp_path) / NAMING_NUMBERED
    assert sorted(path.name for path in as_generated.iterdir()) == sorted(
        f"{stem}{suffix}"
        for stem in ("overview", f"{COUNTRY}_model_method_heatmap", "impossibility_heatmap")
        for suffix in OUTPUT_SUFFIXES
    )
    assert sorted(path.name for path in numbered.iterdir()) == sorted(
        f"{stem}{suffix}"
        for stem in ("F02_reference_proportions", "F07_model_x_method_heatmap", "F19_axisA_impossibility")
        for suffix in OUTPUT_SUFFIXES
    )
    assert result.n_files == len(_EXPORT_ENTRIES) * len(OUTPUT_SUFFIXES) * 2


def test_export_copies_bytes_verbatim(tmp_path: Path) -> None:
    figure_set = _stage_a_set(tmp_path)
    result = export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)

    for copied in result.figures:
        for published in copied.formats:
            expected = _figure_bytes(copied.figure.stem, published.suffix)
            assert published.source.read_bytes() == expected
            for destination in published.destinations.values():
                assert destination.read_bytes() == expected


def test_manifest_round_trips_the_provenance_of_every_file(tmp_path: Path) -> None:
    figure_set = _stage_a_set(tmp_path)
    result = export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)

    manifest = json.loads(result.index_path.read_text(encoding="utf-8"))
    assert result.index_path == _set_dir(tmp_path) / INDEX_FILENAME
    assert manifest["output_base"] == str(tmp_path)
    assert manifest["country"] == COUNTRY
    assert manifest["set"] == "s"
    assert manifest["generated_at"] == result.generated_at
    assert manifest["n_figures"] == len(_EXPORT_ENTRIES)
    assert [figure["n"] for figure in manifest["figures"]] == [2, 7, 19]

    for record, copied in zip(manifest["figures"], result.figures):
        assert record["name"] == copied.figure.entry.name
        assert record["source_stem"] == copied.figure.stem
        assert set(record["formats"]) == set(OUTPUT_SUFFIXES)
        for suffix, published in record["formats"].items():
            source = Path(published["source_path"])
            assert source == copied.figure.paths[suffix]
            assert published["size_bytes"] == source.stat().st_size
            assert published["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
            assert datetime.fromisoformat(published["mtime"]).tzinfo is not None
            for naming in (NAMING_AS_GENERATED, NAMING_NUMBERED):
                assert (_set_dir(tmp_path) / naming / published[naming]).is_file()


def test_a_failing_entry_leaves_the_figures_stage_untouched(tmp_path: Path) -> None:
    # A first, complete run publishes; a second run whose roster gained an entry with
    # no `.eps` must abort before writing, leaving the stage byte-identical.
    figure_set = _stage_a_set(tmp_path)
    export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)
    before = _tree_snapshot(tmp_path / FIGURES_STAGE_DIR)

    partial = (*_EXPORT_ENTRIES, (20, "partial", "realism_ranking/{country}/severity_heatmap_s1"))
    grown = load_figure_set("s", _export_roster(tmp_path, entries=partial))
    _write_figure(tmp_path, f"realism_ranking/{COUNTRY}/severity_heatmap_s1", suffixes=(".png", ".svg"))

    with pytest.raises(FileNotFoundError, match="partial format set is never copied"):
        export_figure_set(grown, country=COUNTRY, output_base=tmp_path)
    assert _tree_snapshot(tmp_path / FIGURES_STAGE_DIR) == before


def test_a_missing_figure_creates_no_figures_stage_at_all(tmp_path: Path) -> None:
    # A country whose analysis was never run: nothing resolves, nothing is created.
    figure_set = load_figure_set("s", _export_roster(tmp_path, entries=_EXPORT_ENTRIES))
    with pytest.raises(FileNotFoundError, match="not found in the analysis stage"):
        export_figure_set(figure_set, country="italian_01", output_base=tmp_path)
    assert not (tmp_path / FIGURES_STAGE_DIR).exists()


def test_an_entry_citing_an_unrun_process_raises_naming_the_figure(tmp_path: Path) -> None:
    # `consistency` is a registered process the workflow ships disabled: the roster
    # loads, and the missing-file gate reports it -- by figure, not by process.
    entries = ((30, "consistency_panel", "consistency/{country}_panel"),)
    figure_set = load_figure_set("s", _export_roster(tmp_path, entries=entries))
    with pytest.raises(FileNotFoundError) as excinfo:
        export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)
    assert "F30 'consistency_panel'" in str(excinfo.value)


def test_a_set_of_one_figure_exports(tmp_path: Path) -> None:
    figure_set = _stage_a_set(tmp_path, entries=((1, "solo", "model_ranking/{country}_models_table"),))
    result = export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)
    assert len(result.figures) == 1
    assert (_set_dir(tmp_path) / NAMING_NUMBERED / "F01_solo.png").is_file()


def test_two_countries_share_one_figures_stage_without_colliding(tmp_path: Path) -> None:
    entries = ((3, "impossibility", "realism_ranking/{country}/impossibility_heatmap"),)
    for country in (COUNTRY, "italian_01"):
        figure_set = _stage_a_set(tmp_path, country=country, entries=entries)
        export_figure_set(figure_set, country=country, output_base=tmp_path)

    for country in (COUNTRY, "italian_01"):
        staged = _set_dir(tmp_path, country) / NAMING_AS_GENERATED / "impossibility_heatmap.png"
        assert staged.read_bytes() == _figure_bytes(
            f"realism_ranking/{country}/impossibility_heatmap", ".png"
        )


def test_a_dropped_figure_survives_without_force_and_is_reported(tmp_path: Path) -> None:
    figure_set = _stage_a_set(tmp_path)
    export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)

    shrunk = load_figure_set("s", _export_roster(tmp_path, entries=_EXPORT_ENTRIES[:2]))
    result = export_figure_set(shrunk, country=COUNTRY, output_base=tmp_path)

    stale = _set_dir(tmp_path) / NAMING_AS_GENERATED / "impossibility_heatmap.png"
    assert stale.is_file()
    assert stale in result.unclaimed
    # Both namings swept, all three formats of the dropped entry.
    assert len(result.unclaimed) == len(OUTPUT_SUFFIXES) * 2
    assert _set_dir(tmp_path) / NAMING_NUMBERED / "F19_axisA_impossibility.eps" in result.unclaimed


def test_force_clears_a_dropped_figure_from_both_namings(tmp_path: Path) -> None:
    figure_set = _stage_a_set(tmp_path)
    export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)

    shrunk = load_figure_set("s", _export_roster(tmp_path, entries=_EXPORT_ENTRIES[:2]))
    result = export_figure_set(shrunk, country=COUNTRY, output_base=tmp_path, force=True)

    assert result.unclaimed == ()
    assert not (_set_dir(tmp_path) / NAMING_AS_GENERATED / "impossibility_heatmap.png").exists()
    assert not (_set_dir(tmp_path) / NAMING_NUMBERED / "F19_axisA_impossibility.eps").exists()
    assert (_set_dir(tmp_path) / NAMING_AS_GENERATED / f"{COUNTRY}_model_method_heatmap.png").is_file()


def test_force_does_not_escape_the_country_and_set_subtree(tmp_path: Path) -> None:
    entries = ((3, "impossibility", "realism_ranking/{country}/impossibility_heatmap"),)
    other_country = _stage_a_set(tmp_path, country="italian_01", entries=entries)
    export_figure_set(other_country, country="italian_01", output_base=tmp_path)
    figure_set = _stage_a_set(tmp_path, entries=entries)
    export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)

    sibling = load_figure_set(
        "deck_probe",
        _write_roster(
            tmp_path,
            "sets:\n  deck_probe:\n    - {n: 1, name: solo, "
            'source: "realism_ranking/{country}/impossibility_heatmap"}\n',
        ),
    )
    export_figure_set(sibling, country=COUNTRY, output_base=tmp_path)

    neighbours = _tree_snapshot(tmp_path / FIGURES_STAGE_DIR / "italian_01")
    sibling_set = _tree_snapshot(_set_dir(tmp_path, COUNTRY, "deck_probe"))
    export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path, force=True)

    assert _tree_snapshot(tmp_path / FIGURES_STAGE_DIR / "italian_01") == neighbours
    assert _tree_snapshot(_set_dir(tmp_path, COUNTRY, "deck_probe")) == sibling_set


def test_a_re_run_overwrites_a_redrawn_figure(tmp_path: Path) -> None:
    entries = ((7, "heatmap", "model_ranking/{country}_model_method_heatmap"),)
    figure_set = _stage_a_set(tmp_path, entries=entries)
    export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)

    source = tmp_path / ANALYSIS_STAGE_DIR / "model_ranking" / f"{COUNTRY}_model_method_heatmap.png"
    source.write_bytes(b"redrawn")
    result = export_figure_set(figure_set, country=COUNTRY, output_base=tmp_path)

    staged = _set_dir(tmp_path) / NAMING_NUMBERED / "F07_heatmap.png"
    assert staged.read_bytes() == b"redrawn"
    assert result.unclaimed == ()
    manifest = json.loads(result.index_path.read_text(encoding="utf-8"))
    assert manifest["figures"][0]["formats"][".png"]["sha256"] == hashlib.sha256(b"redrawn").hexdigest()


# --- the CLI entry point and the DAG wiring (Phase 4) ------------------------

#: The process's canonical id -- simultaneously the registry key, the GUI workflow task
#: key and (for an analysis-stage process) the output-folder name.
PROCESS_ID = "figure_selection"

#: The figure-producing tasks the node orders itself behind: every one of them, and ONLY
#: the ones the shipped workflow enables. A disabled task never enters ``completed_tasks``,
#: so depending on one would park this node at ``SKIPPED_DEP`` forever.
_EXPECTED_DEPENDENCIES = {
    "fidelity",
    "model_ranking",
    "method_significance",
    "real_population_stats",
    "generation_metadata",
    "persona_realism",
    "realism_ranking",
    "validation_attrition",
    "cost_efficiency",
}


def _shipped_workflow_model() -> WorkflowConfigModel:
    return WorkflowConfigModel(PROJECT_ROOT / "config" / "gui" / "flows" / "analysis_workflow.yaml")


def test_registry_declares_a_figures_stage_per_country_process() -> None:
    process = get_process(PROCESS_ID)
    assert process.stage == STAGE_FIGURES
    assert process.dispatch == "per_country"
    # A figures-stage process owns the stage root, so it declares no subfolder.
    assert process.folder is None
    assert (PROJECT_ROOT / process.script).is_file()


def test_workflow_node_renders_from_the_registry() -> None:
    """The GUI draws the node from registry-owned metadata, not from the flow YAML.

    ``get_task_meta`` is what the node widget reads; it raises on an id the registry does
    not declare, so this is the assertion that the node can be drawn at all.
    """
    meta = _shipped_workflow_model().get_task_meta(PROCESS_ID)
    process = get_process(PROCESS_ID)
    assert meta["label"] == process.label
    assert meta["script"] == process.script
    assert meta["dispatch"] == "per_country"
    assert meta["supports_force"] is True


def test_workflow_node_ships_disabled_with_the_curated_roster_selected() -> None:
    """Opt-in, because a sweep must not fail at its last step over an uncurated roster."""
    model = _shipped_workflow_model()
    assert model.is_task_enabled(PROCESS_ID) is False
    assert model.get_task_bypass(PROCESS_ID) is False
    assert model.get_task_force(PROCESS_ID) is False
    options = model.get_task_options(PROCESS_ID)
    assert set(options) == {"set", "output-base"}
    # The declared set must exist in the roster: the GUI can only edit an option the flow
    # already declares, so a name that drifted from the roster would fail at run time only.
    assert options["set"] in known_set_names()


def test_workflow_dependencies_are_exactly_the_enabled_figure_producers() -> None:
    """Every declared upstream, and every one of them enabled.

    The second half is the load-bearing one: ``depends_on`` gives ordering only, but a
    dependency that ships ``enabled: false`` is never marked complete, so it would leave
    this node permanently dep-blocked.
    """
    model = _shipped_workflow_model()
    dependencies = model.get_task_dependencies(PROCESS_ID)
    assert set(dependencies) == _EXPECTED_DEPENDENCIES
    assert len(dependencies) == len(_EXPECTED_DEPENDENCIES)
    disabled = [name for name in dependencies if not model.is_task_enabled(name)]
    assert disabled == []


def test_the_shipped_dag_orders_the_node_after_every_upstream() -> None:
    state = WorkflowState(_shipped_workflow_model().to_plain(), PROJECT_ROOT)
    state.validate()
    order = [task.name for task in state.ordered_tasks()]
    assert order[-1] == PROCESS_ID  # terminal node of the analysis DAG
    for dependency in _EXPECTED_DEPENDENCIES:
        assert order.index(dependency) < order.index(PROCESS_ID)


def test_the_node_unlocks_only_once_every_upstream_completes() -> None:
    """The dependency gate, read on the node itself.

    ``enabled`` is flipped on in the snapshot (the shipped node is opt-in), so the only
    thing ``can_run`` is reporting here is ``depends_on`` -- and it stays False until the
    LAST of the nine is marked complete.
    """
    snapshot = _shipped_workflow_model().to_plain()
    snapshot["tasks"][PROCESS_ID]["enabled"] = True
    state = WorkflowState(snapshot, PROJECT_ROOT)

    dependencies = sorted(_EXPECTED_DEPENDENCIES)
    for dependency in dependencies[:-1]:
        assert not state.can_run(PROCESS_ID)
        state.mark_completed(dependency)
    assert not state.can_run(PROCESS_ID)
    state.mark_completed(dependencies[-1])
    assert state.can_run(PROCESS_ID)


def test_the_shipped_node_stays_dep_blocked_while_it_is_opt_in() -> None:
    """Even with every upstream complete, the shipped node does not fire unasked."""
    state = WorkflowState(_shipped_workflow_model().to_plain(), PROJECT_ROOT)
    for dependency in _EXPECTED_DEPENDENCIES:
        state.mark_completed(dependency)
    assert not state.can_run(PROCESS_ID)  # enabled: false in the shipped YAML


def test_the_set_option_reaches_the_built_command_vector() -> None:
    """``--set <name>`` is translated out of the flow YAML by the per_country builder.

    Read from the shipped flow rather than a literal: the GUI TRANSLATES the YAML into a
    CLI vector and the spawned script never reads the flow file, so this option can only
    reach a run through this vector.
    """
    model = _shipped_workflow_model()
    options = model.get_task_options(PROCESS_ID)
    script = Path(get_process(PROCESS_ID).script)
    combos = [(MODEL, STRATEGY, COUNTRY), ("claude_haiku", STRATEGY, COUNTRY)]

    (cmd,) = build_per_country_cmds(script, combos, force=False, options=options)

    assert cmd == [
        sys.executable, str(script),
        "--country-id", COUNTRY,
        "--set", options["set"],
    ]
    # Blank output-base falls through to the script's own default rather than emitting
    # an empty flag, and Force is the node's own checkbox.
    assert "--output-base" not in cmd
    assert "--force" not in cmd
    assert "--force" in build_per_country_cmds(script, combos, force=True, options=options)[0]


def _load_cli() -> object:
    """Load ``scripts/analyze/select_figures.py`` as a module (the CLI edge under test)."""
    path = PROJECT_ROOT / "scripts" / "analyze" / "select_figures.py"
    spec = importlib.util.spec_from_file_location("select_figures", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_cli_parses_the_four_documented_flags(monkeypatch) -> None:
    """The plan's CLI contract: ``--country-id`` (repeatable), ``--set``, ``--output-base``, ``--force``."""
    cli = _load_cli()
    monkeypatch.setattr(
        sys, "argv",
        ["select_figures.py", "--country-id", COUNTRY, "--country-id", "italian",
         "--set", "manuscript", "--output-base", "out", "--force"],
    )
    args = cli._parse_args()
    assert args.country_ids == [COUNTRY, "italian"]
    assert args.set_name == "manuscript"
    assert args.output_base == "out"
    assert args.force is True


def test_the_cli_defaults_leave_set_base_and_force_to_their_resolvers(monkeypatch) -> None:
    cli = _load_cli()
    monkeypatch.setattr(sys, "argv", ["select_figures.py", "--country-id", COUNTRY])
    args = cli._parse_args()
    assert (args.set_name, args.output_base, args.force) == (None, None, False)


def test_the_cli_requires_a_country(monkeypatch) -> None:
    """There is no default country: a bare invocation must not publish a guessed one."""
    cli = _load_cli()
    monkeypatch.setattr(sys, "argv", ["select_figures.py", "--set", "manuscript"])
    with pytest.raises(SystemExit):
        cli._parse_args()


def test_resolve_set_name_defaults_to_the_only_declared_set(monkeypatch) -> None:
    cli = _load_cli()
    monkeypatch.setattr(cli, "known_set_names", lambda: ("manuscript",))
    assert cli._resolve_set_name(None) == "manuscript"


def test_resolve_set_name_without_a_choice_raises_once_a_second_set_exists(monkeypatch) -> None:
    """No baked-in default set name: from the second set on, the choice is the operator's."""
    cli = _load_cli()
    monkeypatch.setattr(cli, "known_set_names", lambda: ("deck", "manuscript"))
    with pytest.raises(ValueError, match=r"--set is required.*deck.*manuscript"):
        cli._resolve_set_name(None)


def test_resolve_set_name_rejects_an_unknown_set_listing_the_known_ones() -> None:
    cli = _load_cli()
    with pytest.raises(ValueError, match=r"Unknown figure set 'ghost'.*manuscript"):
        cli._resolve_set_name("ghost")


def test_the_cli_accepts_every_shipped_set_name() -> None:
    cli = _load_cli()
    for name in known_set_names():
        assert cli._resolve_set_name(name) == name


def test_unknown_country_raises_listing_the_valid_ids() -> None:
    cli = _load_cli()
    with pytest.raises(ValueError, match=r"Unknown country id\(s\) \['atlantis'\]"):
        cli._validate_countries(["atlantis"])


def test_repeated_country_ids_collapse_in_first_seen_order() -> None:
    cli = _load_cli()
    ids = known_country_ids()
    assert cli._validate_countries([ids[0], ids[0]]) == [ids[0]]

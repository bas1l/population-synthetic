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
import json
from datetime import datetime
from pathlib import Path

import pytest

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
from population_synthetic.analysis.utils.figures import OUTPUT_SUFFIXES
from population_synthetic.analysis.utils.registry import ANALYSIS_STAGE_DIR, FIGURES_STAGE_DIR
from population_synthetic.generators.synthetic.manifest_loader import axis_slug

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
    assert len(figure_set.entries) == 19
    numbers = [entry.n for entry in figure_set.entries]
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == len(numbers)


def test_shipped_manuscript_set_resolves_without_a_tree(tmp_path: Path) -> None:
    # Resolution is pure path arithmetic: no analysis tree is needed to produce paths,
    # only to check they exist. Every entry must survive the collision gate.
    resolved = resolve_set(load_figure_set("manuscript"), country=COUNTRY, output_base=tmp_path)
    assert len(resolved) == 19
    assert len({figure.basename for figure in resolved}) == 19


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

"""Unit tests for the figure-selection roster and its resolver (Phase 2).

Two things are proved here. First, that the schema's two placeholders plus literal
segments express **all six** path shapes the analysis stage actually uses -- the
acceptance test the plan sets for the schema. Second, that every row of the validation
contract raises, and raises naming what was wrong, before any byte is copied.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from population_synthetic.analysis.figure_selection.config import (
    FigureEntry,
    SlugSpec,
    known_set_names,
    load_figure_set,
)
from population_synthetic.analysis.figure_selection.resolve import (
    check_basename_collisions,
    check_sources_exist,
    resolve_entry,
    resolve_set,
)
from population_synthetic.analysis.utils.figures import OUTPUT_SUFFIXES
from population_synthetic.analysis.utils.registry import ANALYSIS_STAGE_DIR
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

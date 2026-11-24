"""Tests for the per-module source + signature capture stage.

Runs against the committed fixture package ``tests/fixtures/samplepkg`` (the same
one the extractor tests use), which now carries a couple of neutral defs/classes
so signatures exist to assert. Requires no git or grimp — ``capture_sources``
walks the filesystem and AST-parses.
"""

from __future__ import annotations

from pathlib import Path

from graphdiff.sources import ModuleSource, capture_sources

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FIXTURE_REL_PATH = "tools/graph-diff/tests/fixtures/samplepkg"

_ALL_MODULES = {
    "samplepkg",
    "samplepkg.core",
    "samplepkg.alpha",
    "samplepkg.beta",
}


def test_capture_returns_all_modules_from_bare_name():
    sources = capture_sources(_FIXTURES_DIR, "samplepkg")
    assert set(sources) == _ALL_MODULES
    assert all(isinstance(v, ModuleSource) for v in sources.values())


def test_capture_returns_all_modules_from_repo_relative_path():
    sources = capture_sources(_REPO_ROOT, _FIXTURE_REL_PATH)
    assert set(sources) == _ALL_MODULES


def test_path_maps_init_to_package_name():
    sources = capture_sources(_FIXTURES_DIR, "samplepkg")
    # __init__.py maps to the bare package name, not 'samplepkg.__init__'.
    assert "samplepkg.__init__" not in sources
    assert sources["samplepkg"].path.endswith("samplepkg/__init__.py")
    assert sources["samplepkg.core"].path.endswith("samplepkg/core.py")


def test_function_signature_with_return_annotation():
    sources = capture_sources(_FIXTURES_DIR, "samplepkg")
    sigs = sources["samplepkg.core"].signatures
    assert "def get_constant() -> int" in sigs


def test_class_and_method_signatures():
    sources = capture_sources(_FIXTURES_DIR, "samplepkg")
    sigs = sources["samplepkg.alpha"].signatures
    assert "class Alpha" in sigs
    # Method rendered (indented) with its arg names and return annotation.
    assert any(s.strip() == "def scaled(self, factor: int) -> int" for s in sigs)


def test_async_function_signature():
    sources = capture_sources(_FIXTURES_DIR, "samplepkg")
    sigs = sources["samplepkg.beta"].signatures
    assert any(s.startswith("async def combine(") for s in sigs)


def test_source_and_line_count_populated():
    sources = capture_sources(_FIXTURES_DIR, "samplepkg")
    core = sources["samplepkg.core"]
    assert "CONSTANT = 1" in core.source
    assert core.line_count == len(core.source.splitlines())
    assert core.line_count > 0


def test_exclude_drops_matching_module():
    sources = capture_sources(_FIXTURES_DIR, "samplepkg", exclude=["beta"])
    assert "samplepkg.beta" not in sources
    assert "samplepkg.alpha" in sources


def test_exclude_multiple_substrings():
    sources = capture_sources(_FIXTURES_DIR, "samplepkg", exclude=["alpha", "beta"])
    assert set(sources) == {"samplepkg", "samplepkg.core"}

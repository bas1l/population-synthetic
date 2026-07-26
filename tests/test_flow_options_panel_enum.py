"""Unit tests for the Flow Runner options panel's config-sourced judge-model enum.

The ``judge-model`` dropdown in :mod:`population_synthetic.gui.widgets.flow_options_panel`
is populated at import from the persona_realism ``judge.yaml`` ``model_options`` list
(config is the single source of truth; no hardcoded model ids). These tests assert the
enum table is filled from that config -- the leading ``("(default)", None)`` sentinel plus
one ``(m, m)`` pair per configured model -- and that the shape-dispatch routes it to a combo
box. The panel module imports PyQt5 at top level, so the whole module is skipped when Qt is
unavailable (e.g. a truly headless CI without the Qt libs).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.gui.widgets import flow_options_panel as panel  # noqa: E402


def test_judge_model_enum_populated_from_config() -> None:
    """The enum table carries a judge-model entry sourced from judge.yaml model_options."""
    assert "judge-model" in panel._OPTION_ENUMS
    entries = panel._OPTION_ENUMS["judge-model"]

    # Leading sentinel preserves "blank = use judge.yaml default" (saved None -> flag omitted).
    assert entries[0] == ("(default)", None)

    # Remaining entries are the config model_options as (label, saved) identity pairs.
    import yaml

    judge_yaml = PROJECT_ROOT / "config" / "analysis" / "persona_realism" / "judge.yaml"
    model_options = yaml.safe_load(judge_yaml.read_text(encoding="utf-8"))["model_options"]
    assert entries[1:] == [(m, m) for m in model_options]

    # The config's default model must be selectable (first real option).
    assert "claude-fable-5" in [saved for _label, saved in entries]


def test_judge_model_dispatches_to_enum_widget() -> None:
    """A null judge-model value still resolves to the combo-box ('enum') shape."""
    assert panel.option_widget_kind("judge-model", None) == "enum"


def test_option_header_uses_label_override() -> None:
    """An overridden key gets its friendly label; others fall back to title-case."""
    assert panel._OPTION_LABELS["real-sample"] == "Real Database N Sample"
    assert panel._option_header("real-sample") == "Real Database N Sample"
    assert panel._option_header("workers") == "Workers"

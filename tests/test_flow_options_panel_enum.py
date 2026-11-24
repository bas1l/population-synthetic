"""Unit tests for the Flow Runner options panel's config-sourced enums.

Two dropdowns in :mod:`population_synthetic.gui.widgets.flow_options_panel` are
populated at import from config, never from a hardcoded Python list:

- ``judge-model`` -- from the persona_realism ``judge.yaml`` ``model_options`` list,
  with a leading ``("(default)", None)`` sentinel preserving "blank = use the
  judge.yaml default".
- ``ollama-host`` -- from ``config/synthetic/ollama_hosts.yaml``, as ``(label, id)``
  pairs and deliberately **without** a sentinel: a ``None`` saved value would omit
  the flag and let the run silently resolve ``default_host``, which is the
  wrong-GPU failure the option exists to prevent.

These tests assert each table is filled from its config and that the shape-dispatch
routes it to a combo box. The panel module imports PyQt5 at top level, so the whole
module is skipped when Qt is unavailable (e.g. a truly headless CI without the Qt libs).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from population_synthetic._paths import PROJECT_ROOT  # noqa: E402
from population_synthetic.generators.synthetic.ollama_hosts import load_hosts  # noqa: E402
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


def test_ollama_host_enum_populated_from_registry() -> None:
    """The enum table carries an ollama-host entry sourced from the host registry."""
    assert "ollama-host" in panel._OPTION_ENUMS
    entries = panel._OPTION_ENUMS["ollama-host"]

    hosts = load_hosts()
    # (display label, saved value) = (host label, host id), in registry order.
    assert entries == [(host.label, host.id) for host in hosts.values()]

    # Both documented hosts are selectable, and the id is what gets saved.
    assert [saved for _label, saved in entries] == ["linux_3060", "windows_4070tis"]


def test_ollama_host_enum_has_no_default_sentinel() -> None:
    """No ``("(default)", None)`` row: an explicit host on every run is the point.

    A saved ``None`` would omit ``--ollama-host`` entirely and let composition fall
    back to ``default_host`` -- reintroducing the implicit endpoint the registry
    removed.
    """
    entries = panel._OPTION_ENUMS["ollama-host"]
    assert ("(default)", None) not in entries
    assert all(saved is not None for _label, saved in entries)


def test_ollama_host_dispatches_to_enum_widget() -> None:
    """A saved host id resolves to the combo-box ('enum') shape, not free text."""
    assert panel.option_widget_kind("ollama-host", "linux_3060") == "enum"


def test_ollama_reconfigure_dispatches_to_checkbox() -> None:
    """A boolean option needs no enum table -- shape dispatch renders it as a checkbox."""
    assert "ollama-reconfigure" not in panel._OPTION_ENUMS
    assert panel.option_widget_kind("ollama-reconfigure", True) == "bool"


def test_option_header_uses_label_override() -> None:
    """An overridden key gets its friendly label; others fall back to title-case."""
    assert panel._OPTION_LABELS["real-sample"] == "Real Database N Sample"
    assert panel._option_header("real-sample") == "Real Database N Sample"
    assert panel._OPTION_LABELS["ollama-host"] == "Ollama Host"
    # Without the override the key would title-case to "Ollama-Host".
    assert panel._option_header("ollama-host") == "Ollama Host"
    assert panel._option_header("ollama-reconfigure") == "Reconfigure Ollama Host"
    assert panel._option_header("workers") == "Workers"

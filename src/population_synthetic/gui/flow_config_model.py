"""Round-trip editable model for a flow's per-flow YAML config.

Slim port of the reference AnalysisRunnerGUI ``dag_config_model.py``
(``social-touch-semi-controlled-analysis``): ruamel.yaml in round-trip mode so
save/reload cycles preserve comments, key order, and quoting; a dirty flag;
and atomic writes (mkstemp + ``Path.replace``).

Typed accessors target the script-flow schema (``options:`` / ``selection:`` /
optional ``force:``). Workflow configs (``tasks:``-based) load fine through the
generic round-trip machinery, but the option/selection/force accessors
fail fast (raise) when the corresponding block is absent — the
workflow-specific subclass arrives in Phase 6.

Execution contract: Save is persistence only — on Run the GUI TRANSLATES this
YAML into CLI invocations of the existing scripts; the spawned scripts do NOT
read this file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

_MISSING = object()


class FlowConfigModel:
    """In-memory representation of one flow YAML with round-trip fidelity."""

    def __init__(self, config_path: Path) -> None:
        self._path = Path(config_path)
        self._yaml = YAML()  # round-trip mode by default
        self._yaml.preserve_quotes = True
        self._data = self._load_file(self._path)
        self._dirty = False

    def _load_file(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8") as fh:
            data = self._yaml.load(fh)
        if data is None:
            raise ValueError(f"Flow config is empty: {path}")
        if not isinstance(data, dict):  # CommentedMap is a dict subclass
            raise ValueError(f"Flow config must be a YAML mapping, got {type(data).__name__}: {path}")
        return data

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _native_type(value: Any) -> Any:
        """Normalize ruamel scalar wrappers (ScalarInt/ScalarFloat/…) to builtins.

        ruamel.yaml round-trip mode may hand back ``ScalarInt``/``ScalarFloat``
        (etc.) instances; writing user-edited values back through those types
        can re-serialize them incorrectly. Coerce scalars to plain Python
        builtins; non-scalars (lists, mappings, ``None``) pass through.
        """
        if value is None:
            return None
        if isinstance(value, bool):  # before int — bool is an int subclass
            return bool(value)
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float):
            return float(value)
        if isinstance(value, str):
            return str(value)
        return value

    # ------------------------------------------------------------------
    # Options (script flows)
    # ------------------------------------------------------------------

    def _options_block(self) -> dict:
        options = self._data.get("options", _MISSING)
        if options is _MISSING:
            raise KeyError(f"Flow config {self._path} has no 'options:' block (workflow configs use 'tasks:')")
        if not isinstance(options, dict):
            raise ValueError(f"Flow config {self._path}: 'options:' must be a mapping, got {type(options).__name__}")
        return options

    def get_options(self) -> dict[str, Any]:
        """Return a plain-dict snapshot of the ``options:`` block (values normalized)."""
        return {key: self._native_type(value) for key, value in self._options_block().items()}

    def get_option(self, key: str) -> Any:
        options = self._options_block()
        if key not in options:
            raise KeyError(f"Flow config {self._path}: unknown option '{key}'")
        return self._native_type(options[key])

    def set_option(self, key: str, value: Any) -> None:
        """Set an existing option (fail-fast on unknown keys — keys are CLI flag names)."""
        options = self._options_block()
        if key not in options:
            raise KeyError(f"Flow config {self._path}: unknown option '{key}' — options cannot be added from the GUI")
        options[key] = self._native_type(value)
        self._dirty = True

    # ------------------------------------------------------------------
    # Selection (models / strategies / countries)
    # ------------------------------------------------------------------

    def _selection_block(self) -> dict:
        selection = self._data.get("selection", _MISSING)
        if selection is _MISSING:
            raise KeyError(f"Flow config {self._path} has no 'selection:' block")
        if not isinstance(selection, dict):
            raise ValueError(
                f"Flow config {self._path}: 'selection:' must be a mapping, got {type(selection).__name__}"
            )
        return selection

    def get_selection(self, axis: str) -> list[str]:
        """Return the checked ids for *axis* (``models``/``strategies``/``countries``)."""
        selection = self._selection_block()
        if axis not in selection:
            raise KeyError(f"Flow config {self._path}: no '{axis}' key in 'selection:'")
        value = selection[axis]
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"Flow config {self._path}: selection '{axis}' must be a list, got {type(value).__name__}")
        return [str(item) for item in value]

    def set_selection(self, axis: str, ids: list[str]) -> None:
        """Write *ids* for an existing *axis* as a flow-style YAML list (``[a, b]``)."""
        selection = self._selection_block()
        if axis not in selection:
            raise KeyError(f"Flow config {self._path}: no '{axis}' key in 'selection:'")
        seq = CommentedSeq([str(item) for item in ids])
        seq.fa.set_flow_style()
        selection[axis] = seq
        self._dirty = True

    # ------------------------------------------------------------------
    # Force (generate flows only)
    # ------------------------------------------------------------------

    def has_force(self) -> bool:
        """Return True if this flow declares a top-level ``force:`` key."""
        return "force" in self._data

    def get_force(self) -> bool:
        if "force" not in self._data:
            raise KeyError(f"Flow config {self._path} has no 'force:' key (generate flows only)")
        value = self._data["force"]
        if not isinstance(value, bool):
            raise ValueError(f"Flow config {self._path}: 'force:' must be a boolean, got {value!r}")
        return bool(value)

    def set_force(self, force: bool) -> None:
        if "force" not in self._data:
            raise KeyError(f"Flow config {self._path} has no 'force:' key (generate flows only)")
        self._data["force"] = bool(force)
        self._dirty = True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write back to the original file atomically, preserving comments."""
        self.save_as(self._path)

    def save_as(self, path: Path) -> None:
        """Write the current state to *path* atomically (mkstemp + replace).

        Saving to a different path exports a copy: the model stays bound to
        its original :attr:`path` and, if dirty, remains dirty relative to it.
        """
        path = Path(path)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".yaml", dir=str(path.parent))
        try:
            with open(tmp_fd, "w", encoding="utf-8") as fh:
                self._yaml.dump(self._data, fh)
            Path(tmp_path).replace(path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        if path == self._path:
            self._dirty = False

    def reload(self) -> None:
        """Re-read the file from disk, discarding in-memory changes."""
        self._data = self._load_file(self._path)
        self._dirty = False

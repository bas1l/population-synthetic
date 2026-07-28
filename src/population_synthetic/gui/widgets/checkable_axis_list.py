"""CheckableAxisList — scrollable checkbox list for one selection axis.

``CheckableAxisList`` is a ``QWidget`` holding a titled group box of
``QCheckBox`` items inside a ``QScrollArea``, with All/None buttons. It backs
one axis (models, strategies, or countries) and emits ``selection_changed``
with the checked item IDs.

It also offers an optional **facet filter**: a row of chips partitioning the
populated items into named groups (:meth:`set_facets`), narrowing which rows are
on screen. The filter is deliberately *generic* — this widget backs all three
axes, so the facet vocabulary (``v1``/``v2``, ``Active``/``Discarded``, …) stays
entirely in the caller, and so does the choice of which chips start checked
(``set_facets(..., initially_checked=...)``).

Filtering is a pure **view** operation and obeys one retaining rule::

    visible = matches(active facets) OR isChecked()

A checked item is never hidden, so the invariant
``set(visible_ids()) >= set(selected_ids())`` holds at all times: everything
that will run is on screen. Chips carry no state anything else reads — toggling
one emits no signal, changes no check state, and never touches the bound model.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Styling for a "retained" row: checked, but outside the active facets. It stays
# on screen (the retaining rule) and is de-emphasised so the filter still reads
# as applied.
_RETAINED_STYLE = "color: palette(mid); font-style: italic;"

# Trailing marker appended to a retained row's label, e.g. "all_pick  · v1 kept".
_RETAINED_MARKER = "  · {facet} kept"


class CheckableAxisList(QWidget):
    selection_changed = pyqtSignal(list)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []
        self._checkboxes: list[QCheckBox] = []
        # Facet state: the chips themselves, plus id -> group name for the
        # retained-row marker. Empty == no filtering (every item is "active").
        self._facet_boxes: list[tuple[QCheckBox, frozenset[str]]] = []
        self._facet_of: dict[str, str] = {}

        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(4, 4, 4, 4)
        group_layout.setSpacing(2)

        btn_row = QHBoxLayout()
        self._btn_all = QPushButton("All")
        self._btn_none = QPushButton("None")
        btn_row.addWidget(self._btn_all)
        btn_row.addWidget(self._btn_none)
        btn_row.addStretch()
        # The facet strip shares the All/None row: right-aligned after the
        # stretch so it costs zero extra vertical space. That matters — the
        # strategies list is the tightest column (stretch weight 8, ~3-row
        # floor), and a chip row of its own would eat a whole item row.
        self._facet_label = QLabel()
        self._facet_label.setVisible(False)
        btn_row.addWidget(self._facet_label)
        self._facet_row = btn_row
        group_layout.addLayout(btn_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        # Height is the parent layout's call, not the content's: `Ignored`
        # drops the "as tall as my N checkboxes" size hint, so an axis gets
        # exactly the share its AxisSelector stretch weight asks for (a 20-item
        # axis would otherwise claim 20 rows before stretch ever applies). The
        # minimum keeps a short axis readable — roughly three rows — instead of
        # collapsing to the scrollbar.
        self._scroll.setMinimumHeight(60)
        self._scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(2, 2, 2, 2)
        self._scroll_layout.setSpacing(1)
        self._scroll_layout.addStretch()
        self._scroll.setWidget(self._scroll_content)
        group_layout.addWidget(self._scroll)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(group)

        self._btn_all.clicked.connect(self._select_all)
        self._btn_none.clicked.connect(self._select_none)

    def populate(self, items: list[dict]) -> None:
        """Rebuild the checkbox rows from *items* (checks survive by id).

        Any facet chips are dropped: :meth:`set_facets` validated its groups as a
        partition of the *previous* item set, so keeping them would leave ids
        belonging to no group. Callers that face a repopulate must re-call
        :meth:`set_facets` with groups derived from the new items.
        """
        previously_checked = set(self.selected_ids())
        self._clear_facets()

        for cb in self._checkboxes:
            cb.setParent(None)
        self._checkboxes.clear()

        self._scroll_layout.takeAt(self._scroll_layout.count() - 1)

        self._items = list(items)
        for item in self._items:
            cb = QCheckBox(item["label"])
            cb.setChecked(item["id"] in previously_checked)
            cb.toggled.connect(self._on_toggle)
            self._scroll_layout.addWidget(cb)
            self._checkboxes.append(cb)

        self._scroll_layout.addStretch()
        self._apply_content_ceiling()
        self._apply_filter()

    # ------------------------------------------------------------------
    # Facet filter (generic — the facet vocabulary belongs to the caller)
    # ------------------------------------------------------------------

    def set_facets(
        self,
        title: str,
        groups: list[tuple[str, list[str]]],
        *,
        initially_checked: set[str] | None = None,
    ) -> None:
        """Show a chip row filtering the populated items by *groups*.

        *groups* is ``[(chip_label, [item_id, ...]), ...]`` and must be a strict
        **partition** of the populated ids: every populated id in exactly one
        group, no unknown ids. A missing, duplicated, or unknown id raises
        :class:`ValueError` — a silently ungrouped item would be permanently
        filtered out of the list with no way to reach it. Chip labels must be
        unique: a label is how a group is named in *initially_checked* and in
        the retained-row marker.

        *initially_checked* names the chips that start checked; ``None`` (the
        default) starts every chip checked, i.e. no filtering. A name that is
        not a declared group label raises rather than being ignored — a typo
        would otherwise hand the axis a filter nobody asked for. Starting a chip
        unchecked is safe by construction: the retaining rule below hides only
        *unchecked* rows, so a default filter can never hide part of what a
        bound flow is about to run.

        Call after :meth:`populate`.
        """
        populated = [item["id"] for item in self._items]
        populated_set = set(populated)

        labels = [chip_label for chip_label, _members in groups]
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            raise ValueError(
                f"{self.__class__.__name__} facet groups for '{title}': duplicate chip labels "
                f"{duplicates}; a label names a group, so it must be unique."
            )
        if initially_checked is not None:
            unknown_chips = sorted(set(initially_checked) - set(labels))
            if unknown_chips:
                raise ValueError(
                    f"{self.__class__.__name__} facet groups for '{title}': initially_checked names "
                    f"unknown chips {unknown_chips} (declared: {labels})."
                )

        facet_of: dict[str, str] = {}
        for chip_label, member_ids in groups:
            for item_id in member_ids:
                if item_id in facet_of:
                    raise ValueError(
                        f"{self.__class__.__name__} facet groups for '{title}': id {item_id!r} appears in "
                        f"both {facet_of[item_id]!r} and {chip_label!r}; groups must partition the items."
                    )
                if item_id not in populated_set:
                    raise ValueError(
                        f"{self.__class__.__name__} facet groups for '{title}': id {item_id!r} in group "
                        f"{chip_label!r} is not a populated item (populated: {sorted(populated_set)})."
                    )
                facet_of[item_id] = chip_label
        ungrouped = [item_id for item_id in populated if item_id not in facet_of]
        if ungrouped:
            raise ValueError(
                f"{self.__class__.__name__} facet groups for '{title}': populated ids {ungrouped} belong to "
                f"no group (groups: {[label for label, _ in groups]}); groups must partition the items."
            )

        self._clear_facets()
        self._facet_of = facet_of
        self._facet_label.setText(f"{title}:")
        self._facet_label.setVisible(True)
        for chip_label, member_ids in groups:
            chip = QCheckBox(chip_label)
            chip.setChecked(initially_checked is None or chip_label in initially_checked)
            chip.toggled.connect(self._on_facet_toggled)
            self._facet_row.addWidget(chip)
            self._facet_boxes.append((chip, frozenset(member_ids)))
        self._apply_filter()

    def visible_ids(self) -> list[str]:
        """Ids whose checkbox is currently on screen (in populated order)."""
        return [
            self._items[i]["id"]
            for i, cb in enumerate(self._checkboxes)
            if not cb.isHidden()
        ]

    def _clear_facets(self) -> None:
        for chip, _members in self._facet_boxes:
            chip.setParent(None)
        self._facet_boxes.clear()
        self._facet_of = {}
        self._facet_label.setVisible(False)

    def _active_ids(self) -> set[str]:
        """Ids matched by the checked chips — every id when no facets are set."""
        if not self._facet_boxes:
            return {item["id"] for item in self._items}
        active: set[str] = set()
        for chip, members in self._facet_boxes:
            if chip.isChecked():
                active |= members
        return active

    def _apply_filter(self) -> None:
        """Apply ``visible = matches(active facets) OR isChecked()``.

        The ``OR isChecked()`` half is the retaining rule and the reason
        ``visible_ids() >= selected_ids()`` cannot be violated: a row is hidden
        only when it is unchecked. Retained rows (checked but out of filter) are
        re-labelled and re-styled from the *pristine* item label every pass, so
        the marker can never accumulate across toggles.
        """
        active = self._active_ids()
        for i, cb in enumerate(self._checkboxes):
            item_id = self._items[i]["id"]
            retained = cb.isChecked() and item_id not in active
            cb.setVisible(item_id in active or cb.isChecked())
            label = self._items[i]["label"]
            marker = _RETAINED_MARKER.format(facet=self._facet_of[item_id]) if retained else ""
            cb.setText(label + marker)
            cb.setStyleSheet(_RETAINED_STYLE if retained else "")
        # The ceiling is derived from the scroll content's sizeHint, which
        # shrinks as rows hide — without this the box stays sized for the full
        # item count while showing a filtered subset.
        self._scroll_layout.activate()
        self._apply_content_ceiling()

    def _on_facet_toggled(self) -> None:
        """A chip changed: re-filter the view and nothing else.

        Deliberately no check-state change, no ``selection_changed`` emission and
        no model write — the chip row is a view control, so a filter toggle must
        never dirty the flow YAML.
        """
        self._apply_filter()

    def _apply_content_ceiling(self) -> None:
        """Cap the list at the height its own items need.

        Without a ceiling a short axis handed a tall column keeps the surplus as
        blank space below its last checkbox. Capping at the content height sends
        that surplus back to the layout, which passes it to an axis that still
        has rows to reveal. Recomputed on every :meth:`populate` so the ceiling
        follows the discovered item count — never a fixed pixel budget.
        """
        content_height = self._scroll_content.sizeHint().height() + 2 * self._scroll.frameWidth()
        self._scroll.setMaximumHeight(max(content_height, self._scroll.minimumHeight()))
        # Qt does not propagate a layout's maximum up to the parent widget, so
        # the ceiling has to be restated on this widget or the group box keeps
        # the surplus as padding under the capped list. Chrome (group title +
        # All/None row + margins) is this widget's minimum minus the list's.
        chrome = max(self.minimumSizeHint().height() - self._scroll.minimumHeight(), 0)
        self.setMaximumHeight(chrome + self._scroll.maximumHeight())

    def selected_ids(self) -> list[str]:
        return [
            self._items[i]["id"]
            for i, cb in enumerate(self._checkboxes)
            if cb.isChecked()
        ]

    def set_selected(self, ids: list[str]) -> None:
        id_set = set(ids)
        for i, cb in enumerate(self._checkboxes):
            cb.blockSignals(True)
            cb.setChecked(self._items[i]["id"] in id_set)
            cb.blockSignals(False)
        # Before the emit: a restored id that the current chips filter out is
        # retained (checked ⇒ visible), so loading an older flow can never hide
        # part of what it is about to run.
        self._apply_filter()
        self.selection_changed.emit(self.selected_ids())

    def _select_all(self) -> None:
        for cb in self._checkboxes:
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self._apply_filter()  # "All" checks filtered-out items too — retain them
        self.selection_changed.emit(self.selected_ids())

    def _select_none(self) -> None:
        for cb in self._checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._apply_filter()  # nothing is retained any more — drop the markers
        self.selection_changed.emit(self.selected_ids())

    def _on_toggle(self) -> None:
        self._apply_filter()  # un-checking a retained row releases it from the view
        self.selection_changed.emit(self.selected_ids())

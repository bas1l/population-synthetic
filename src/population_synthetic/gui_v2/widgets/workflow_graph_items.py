"""Workflow graph items — task node (with checkboxes + run-state overlay) and edge.

Port of the reference AnalysisRunnerGUI ``dag_graph_items.py``
(``social-touch-semi-controlled-analysis``): a :class:`WorkflowTaskNode`
(``QGraphicsRectItem``) carrying embedded ``Enabled`` / ``Force`` checkbox
:class:`QGraphicsProxyWidget`s, drawn gray @ 0.55 opacity when disabled, plus a
directed :class:`WorkflowEdge`. New over the reference: a
:meth:`WorkflowTaskNode.set_status` run-state overlay
(:class:`~population_synthetic.gui_v2.workflow_state.TaskStatus`) so the graph
doubles as the live run report.

The ``Force`` checkbox is present only for tasks whose YAML declares
``supports_force: true``; the ``Enabled`` checkbox is always present. Checkbox
toggles emit ``enabled_changed`` / ``force_changed`` for the view to write
through :class:`~population_synthetic.gui_v2.workflow_config_model.WorkflowConfigModel`.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt5.QtWidgets import (
    QCheckBox,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsProxyWidget,
    QGraphicsRectItem,
    QHBoxLayout,
    QLabel,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from population_synthetic.gui_v2.workflow_config_model import WorkflowConfigModel
from population_synthetic.gui_v2.workflow_state import TaskStatus

_NODE_H = 92
_MIN_NODE_W = 200
_LABEL_FONT_SIZE = 12
_H_PADDING = 44
_CORNER_RADIUS = 6
_INSET = 6
_DRAG_THRESHOLD = 4  # scene-units of movement before a press counts as a drag, not a click

_COLOR_BG_ENABLED = QColor("#d0e8ff")
_COLOR_BORDER_ENABLED = QColor("#2255aa")
_COLOR_BG_DISABLED = QColor("#e8e8e8")
_COLOR_BORDER_DISABLED = QColor("#888888")
_COLOR_SELECTION = QColor("#ff8800")
_COLOR_EDGE = QColor("#555555")

# Run-state overlay: (fill override | None, border color, border width, dim?, glyph).
# A None fill keeps the base enabled/disabled fill; `dim` forces 0.55 opacity.
_STATUS_OVERLAY: dict[TaskStatus, tuple[QColor | None, QColor, float, bool, str]] = {
    TaskStatus.PENDING:          (None, _COLOR_BORDER_ENABLED, 1.5, False, ""),
    TaskStatus.RUNNING:          (None, QColor("#1565c0"), 3.0, False, "▶"),
    TaskStatus.COMPLETED:        (None, QColor("#2e7d32"), 2.5, False, "✓"),
    TaskStatus.FAILED:           (None, QColor("#c62828"), 2.5, False, "✗"),
    TaskStatus.SKIPPED_DISABLED: (QColor("#f0e0c0"), QColor("#aa6600"), 1.5, True, "–"),
    TaskStatus.SKIPPED_DEP:      (QColor("#f0e0c0"), QColor("#aa6600"), 1.5, True, "–"),
    TaskStatus.SKIPPED_GUARD:    (QColor("#ffe0a0"), QColor("#aa6600"), 2.0, True, "!"),
    TaskStatus.ABORTED:          (QColor("#f0d0d0"), QColor("#888888"), 1.5, True, "⊘"),
}


class WorkflowTaskNode(QGraphicsRectItem):
    """Graph node for one workflow task, with Enabled/Force checkboxes."""

    class _Signals(QObject):
        node_clicked = pyqtSignal(str)
        enabled_changed = pyqtSignal(str, bool)
        force_changed = pyqtSignal(str, bool)
        position_changed = pyqtSignal(str, float, float)  # name, x, y

    def __init__(
        self,
        task_name: str,
        model: WorkflowConfigModel,
        parent: QGraphicsItem | None = None,
    ) -> None:
        meta = model.get_task_meta(task_name)
        label = meta["label"]

        _lf = QFont()
        _lf.setBold(True)
        _lf.setPointSize(_LABEL_FONT_SIZE)
        node_w = max(_MIN_NODE_W, QFontMetrics(_lf).horizontalAdvance(label) + _H_PADDING)

        super().__init__(0, 0, node_w, _NODE_H, parent)
        self._task_name = task_name
        self._updating = False
        self._press_scene_pos: QPointF | None = None
        self._dragged = False
        self._status = TaskStatus.PENDING
        self._enabled = model.is_task_enabled(task_name)
        self._has_force = bool(meta["supports_force"])

        self.signals = WorkflowTaskNode._Signals()

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(4, 4, 4, 4)
        inner_layout.setSpacing(2)

        self._label = QLabel(label)
        self._label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        self._label.setWordWrap(False)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents)
        inner_layout.addWidget(self._label)

        cb_row = QWidget()
        cb_row.setStyleSheet("background: transparent;")
        cb_layout = QHBoxLayout(cb_row)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setSpacing(6)

        self._cb_enabled = QCheckBox("Enabled")
        self._cb_enabled.setChecked(self._enabled)
        self._cb_enabled.stateChanged.connect(self._on_enabled_changed)
        cb_layout.addWidget(self._cb_enabled)

        self._cb_force: QCheckBox | None = None
        if self._has_force:
            self._cb_force = QCheckBox("Force")
            self._cb_force.setChecked(model.get_task_force(task_name))
            self._cb_force.stateChanged.connect(self._on_force_changed)
            cb_layout.addWidget(self._cb_force)

        cb_layout.addStretch()
        inner_layout.addWidget(cb_row)

        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(inner)
        proxy.setPos(_INSET, _INSET)
        proxy.resize(node_w - 2 * _INSET, _NODE_H - 2 * _INSET)

    # ------------------------------------------------------------------
    # Run-state overlay
    # ------------------------------------------------------------------

    def set_status(self, status: TaskStatus) -> None:
        """Set the transient run-state overlay and repaint."""
        self._status = status
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        fill_override, border_color, border_w, dim_status, glyph = _STATUS_OVERLAY[self._status]

        if self._enabled:
            base_bg = _COLOR_BG_ENABLED
        else:
            base_bg = _COLOR_BG_DISABLED
        bg = fill_override if fill_override is not None else base_bg
        # A disabled node also uses the disabled border when the overlay is neutral.
        if self._status is TaskStatus.PENDING and not self._enabled:
            border_color = _COLOR_BORDER_DISABLED
        dim = dim_status or (not self._enabled and self._status is TaskStatus.PENDING)

        painter.setOpacity(0.55 if dim else 1.0)
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)

        painter.fillPath(path, QBrush(bg))
        painter.strokePath(path, QPen(border_color, border_w))

        if option.state & QStyle.State_Selected:
            painter.strokePath(path, QPen(_COLOR_SELECTION, 2.0))

        if glyph:
            painter.setOpacity(1.0)
            badge_font = QFont()
            badge_font.setBold(True)
            badge_font.setPointSize(13)
            painter.setFont(badge_font)
            painter.setPen(QPen(border_color))
            painter.drawText(
                QRectF(rect.right() - 22, rect.top() + 2, 20, 20),
                Qt.AlignCenter,
                glyph,
            )
        painter.setOpacity(1.0)

    def boundingRect(self) -> QRectF:
        return self.rect().adjusted(-2, -2, 2, 2)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        # Record the press so mouseReleaseEvent can tell a click (select) from a
        # drag (move). Emitting node_clicked on press would fire mid-drag and,
        # e.g., steal focus to the options pane every time a node is nudged.
        self._press_scene_pos = event.scenePos()
        self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        if self._press_scene_pos is not None:
            moved = (event.scenePos() - self._press_scene_pos).manhattanLength()
            if moved > _DRAG_THRESHOLD:
                self._dragged = True

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._press_scene_pos is not None and not self._dragged:
            self.signals.node_clicked.emit(self._task_name)
        self._press_scene_pos = None
        self._dragged = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.signals.position_changed.emit(self._task_name, value.x(), value.y())
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    # Checkbox handlers
    # ------------------------------------------------------------------

    def _on_enabled_changed(self, _state: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self._enabled = self._cb_enabled.isChecked()
            self.update()  # repaint gray/colored (no re-layout needed)
            self.signals.enabled_changed.emit(self._task_name, self._enabled)
        finally:
            self._updating = False

    def _on_force_changed(self, _state: int) -> None:
        if self._updating or self._cb_force is None:
            return
        self._updating = True
        try:
            self.signals.force_changed.emit(self._task_name, self._cb_force.isChecked())
        finally:
            self._updating = False


class WorkflowEdge(QGraphicsPathItem):
    """Directed arrow edge from *source* node to *target* node."""

    _ARROW_SIZE = 8

    def __init__(
        self,
        source: WorkflowTaskNode,
        target: WorkflowTaskNode,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._target = target
        self.setPen(QPen(_COLOR_EDGE, 1.5, Qt.SolidLine))
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setZValue(-1)
        self.update_path()

    def update_path(self) -> None:
        src_rect = self._source.sceneBoundingRect()
        tgt_rect = self._target.sceneBoundingRect()
        src_pt = QPointF(src_rect.right(), src_rect.center().y())
        tgt_pt = QPointF(tgt_rect.left(), tgt_rect.center().y())

        ctrl_offset = 60.0
        c1 = QPointF(src_pt.x() + ctrl_offset, src_pt.y())
        c2 = QPointF(tgt_pt.x() - ctrl_offset, tgt_pt.y())

        path = QPainterPath(src_pt)
        path.cubicTo(c1, c2, tgt_pt)
        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self.pen())
        painter.drawPath(self.path())

        painter.setBrush(QBrush(_COLOR_EDGE))
        painter.setPen(Qt.NoPen)
        tgt_rect = self._target.sceneBoundingRect()
        tip = self.mapFromScene(QPointF(tgt_rect.left(), tgt_rect.center().y()))
        half = self._ARROW_SIZE / 2.0
        base_x = tip.x() - self._ARROW_SIZE
        arrow = QPolygonF([
            QPointF(base_x, tip.y() - half),
            QPointF(tip.x(), tip.y()),
            QPointF(base_x, tip.y() + half),
        ])
        painter.drawPolygon(arrow)

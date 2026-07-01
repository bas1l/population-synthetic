"""Graphics items for the strategy-DAG view: nodes and edges.

``DagCategoryNode`` is a movable ``QGraphicsRectItem`` rendering one category,
colour-coded by generation method, with a centred label and click/move
signals. ``DagEdge`` is a ``QGraphicsPathItem`` drawing a cubic-Bezier
dependency arrow between two nodes.
"""
import math

from PyQt5.QtCore import QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsProxyWidget,
    QGraphicsRectItem,
    QGraphicsScene,
    QLabel,
    QVBoxLayout,
    QWidget,
)


_NODE_H = 90
_MIN_NODE_W = 180
_CORNER_RADIUS = 6
_BADGE_SIZE = 10
_ARROW_SIZE = 8
_CTRL_OFFSET = 60

_METHOD_COLORS = {
    "pick":                          ("#d0e8ff", "#2255aa"),
    "generate_pick":                 ("#d0ffe8", "#006633"),
    "generate_evaluate_pick":        ("#ffe0b0", "#aa6600"),
    "generate_evaluate_random_pick": ("#ffd0ff", "#662299"),
}
_FALLBACK_COLORS = ("#f0f0f0", "#666666")


class _Signals(QObject):
    node_clicked = pyqtSignal(str)
    position_changed = pyqtSignal(str, float, float)


class DagCategoryNode(QGraphicsRectItem):
    def __init__(self, name: str, method: str, depends_on: list[str], parent=None):
        fill, border = _METHOD_COLORS.get(method, _FALLBACK_COLORS)
        font = QFont("Arial", 11, QFont.Bold)
        fm = QFontMetrics(font)
        node_w = max(_MIN_NODE_W, fm.horizontalAdvance(name) + 40)

        super().__init__(QRectF(0, 0, node_w, _NODE_H), parent)

        self.name = name
        self.method = method
        self.depends_on = depends_on
        self._fill = fill
        self._border = border
        self._node_w = node_w

        self.signals = _Signals()

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        label = QLabel(name)
        label.setFont(font)
        label.setAlignment(Qt.AlignCenter)
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        label.setStyleSheet("background: transparent;")

        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(label)
        proxy.setAcceptedMouseButtons(Qt.NoButton)
        label_w = min(node_w - 8, fm.horizontalAdvance(name) + 20)
        label_h = fm.height() + 4
        proxy.setPos(
            (node_w - label_w) / 2,
            (_NODE_H - label_h) / 2,
        )
        proxy.resize(label_w, label_h)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        fill_color = QColor(self._fill)
        border_color = QColor(self._border)

        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(border_color, 1.5))
        painter.drawRoundedRect(self.rect(), _CORNER_RADIUS, _CORNER_RADIUS)

        if self.isSelected():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#ff8800"), 2.0))
            painter.drawRoundedRect(self.rect(), _CORNER_RADIUS, _CORNER_RADIUS)

        badge_x = self.rect().right() - _BADGE_SIZE
        badge_y = self.rect().top()
        painter.setBrush(QBrush(border_color))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(badge_x, badge_y, _BADGE_SIZE, _BADGE_SIZE))

    def right_center(self) -> QPointF:
        r = self.rect()
        return self.mapToScene(QPointF(r.right(), r.center().y()))

    def left_center(self) -> QPointF:
        r = self.rect()
        return self.mapToScene(QPointF(r.left(), r.center().y()))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.signals.position_changed.emit(self.name, value.x(), value.y())
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.signals.node_clicked.emit(self.name)
        super().mousePressEvent(event)


class DagEdge(QGraphicsPathItem):
    def __init__(self, source: DagCategoryNode, target: DagCategoryNode, parent=None):
        super().__init__(parent)
        self._source = source
        self._target = target

        pen = QPen(QColor("#555555"), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self.setPen(pen)
        self.setZValue(-1)

        self._arrow = QGraphicsPolygonItem(self)
        self._arrow.setBrush(QBrush(QColor("#555555")))
        self._arrow.setPen(QPen(Qt.NoPen))

        self.update_path()

    def update_path(self):
        src_pt = self._source.right_center()
        tgt_pt = self._target.left_center()

        c1 = QPointF(src_pt.x() + _CTRL_OFFSET, src_pt.y())
        c2 = QPointF(tgt_pt.x() - _CTRL_OFFSET, tgt_pt.y())

        path = QPainterPath(src_pt)
        path.cubicTo(c1, c2, tgt_pt)
        self.setPath(path)

        angle = math.atan2(tgt_pt.y() - c2.y(), tgt_pt.x() - c2.x())
        tip = tgt_pt
        sz = _ARROW_SIZE
        p0 = tip
        p1 = QPointF(tip.x() - sz * math.cos(angle - 0.4), tip.y() - sz * math.sin(angle - 0.4))
        p2 = QPointF(tip.x() - sz * math.cos(angle + 0.4), tip.y() - sz * math.sin(angle + 0.4))

        self._arrow.setPolygon(QPolygonF([p0, p1, p2]))

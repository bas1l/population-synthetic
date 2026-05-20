import json
import math
from pathlib import Path

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QPolygonF
from PyQt5.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)


NODE_W, NODE_H = 140, 40
LAYER_SPACING = 100
NODE_SPACING = 160

METHOD_COLORS = {
    "pick": "#d0e8ff",
    "generate_pick": "#d0ffd0",
    "generate_evaluate_pick": "#ffe0b0",
    "generate_evaluate_random_pick": "#ffd0d0",
}


def _topo_layers(categories: dict) -> list[list[str]]:
    in_degree: dict[str, int] = {name: 0 for name in categories}
    adjacency: dict[str, list[str]] = {name: [] for name in categories}

    for name, cfg in categories.items():
        for dep in cfg.get("depends_on", []):
            if dep in categories:
                adjacency[dep].append(name)
                in_degree[name] += 1

    layers: list[list[str]] = []
    queue = [name for name, deg in in_degree.items() if deg == 0]

    while queue:
        layers.append(sorted(queue))
        next_queue: list[str] = []
        for node in queue:
            for child in adjacency[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_queue.append(child)
        queue = next_queue

    return layers


def _layout_positions(layers: list[list[str]]) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    for layer_idx, layer in enumerate(layers):
        y = layer_idx * LAYER_SPACING
        size = len(layer)
        for node_idx, name in enumerate(layer):
            x = (node_idx - (size - 1) / 2.0) * NODE_SPACING
            positions[name] = (x, y)
    return positions


class DagGraphWidget(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHint(QPainter.Antialiasing)

    def populate(self, strategy_path: Path | None) -> None:
        self._scene.clear()
        if strategy_path is None or not strategy_path.exists():
            text = QGraphicsTextItem("No strategy file")
            self._scene.addItem(text)
            return
        try:
            data = json.loads(strategy_path.read_text(encoding="utf-8"))
        except Exception:
            text = QGraphicsTextItem("Invalid strategy file")
            self._scene.addItem(text)
            return
        categories = data.get("categories")
        if not isinstance(categories, dict) or not categories:
            text = QGraphicsTextItem("No categories found in strategy file")
            self._scene.addItem(text)
            return
        self._render(categories)

    def wheelEvent(self, event) -> None:
        if event.angleDelta().y() > 0:
            self.scale(1.15, 1.15)
        else:
            self.scale(1 / 1.15, 1 / 1.15)

    def _render(self, categories: dict) -> None:
        layers = _topo_layers(categories)
        positions = _layout_positions(layers)

        node_centers: dict[str, tuple[float, float]] = {}

        for name, (x, y) in positions.items():
            cfg = categories[name]
            method = cfg.get("method", "")
            depends_on = cfg.get("depends_on", [])
            color_hex = METHOD_COLORS.get(method, "#e0e0e0")

            rect_x = x - NODE_W / 2
            rect_y = y - NODE_H / 2

            rect_item = QGraphicsRectItem(rect_x, rect_y, NODE_W, NODE_H)
            rect_item.setBrush(QBrush(QColor(color_hex)))
            rect_item.setPen(QPen(Qt.black, 1))
            rect_item.setToolTip(
                f"{name}\nMethod: {method}\nDeps: {', '.join(depends_on) or 'none'}"
            )
            self._scene.addItem(rect_item)

            label = QGraphicsTextItem(name)
            label.setTextWidth(NODE_W - 4)
            label_rect = label.boundingRect()
            label.setPos(
                rect_x + (NODE_W - label_rect.width()) / 2,
                rect_y + (NODE_H - label_rect.height()) / 2,
            )
            self._scene.addItem(label)

            node_centers[name] = (x, y)

        for target_name, cfg in categories.items():
            for source_name in cfg.get("depends_on", []):
                if source_name not in node_centers or target_name not in node_centers:
                    continue
                sx, sy = node_centers[source_name]
                tx, ty = node_centers[target_name]

                src_bottom = QPointF(sx, sy + NODE_H / 2)
                tgt_top = QPointF(tx, ty - NODE_H / 2)

                edge_pen = QPen(QColor("#888888"), 1.5)
                line = QGraphicsLineItem(
                    src_bottom.x(), src_bottom.y(), tgt_top.x(), tgt_top.y()
                )
                line.setPen(edge_pen)
                self._scene.addItem(line)

                dx = tgt_top.x() - src_bottom.x()
                dy = tgt_top.y() - src_bottom.y()
                angle = math.atan2(dy, dx)

                tip = tgt_top
                arrow_len = 10.0
                arrow_half_w = 6.0
                base_x = tip.x() - arrow_len * math.cos(angle)
                base_y = tip.y() - arrow_len * math.sin(angle)
                perp_x = -math.sin(angle)
                perp_y = math.cos(angle)

                p0 = QPointF(tip.x(), tip.y())
                p1 = QPointF(base_x + arrow_half_w * perp_x, base_y + arrow_half_w * perp_y)
                p2 = QPointF(base_x - arrow_half_w * perp_x, base_y - arrow_half_w * perp_y)

                arrow = QGraphicsPolygonItem(QPolygonF([p0, p1, p2]))
                arrow.setBrush(QBrush(QColor("#888888")))
                arrow.setPen(QPen(Qt.NoPen))
                self._scene.addItem(arrow)

        bounding = self._scene.itemsBoundingRect()
        if not bounding.isNull():
            bounding.adjust(-20, -20, 20, 20)
            self.fitInView(bounding, Qt.KeepAspectRatio)

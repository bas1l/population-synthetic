"""DagGraphView — interactive view of a strategy's category dependency DAG.

``DagGraphView`` (a ``QGraphicsView``, aliased ``DagGraphWidget``) reads a
strategy JSON's ``categories``, builds ``DagCategoryNode``/``DagEdge`` items,
and lays them out per connected component via grandalf's Sugiyama layout. It
supports zoom, middle-button pan, and persists manual node positions to a
``.layout.json`` sidecar.
"""
import json
from pathlib import Path

from grandalf.graphs import Edge as GEdge
from grandalf.graphs import Graph, Vertex
from grandalf.layouts import SugiyamaLayout
from PyQt5.QtCore import QLineF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence, QPainter, QPen
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsTextItem, QGraphicsView, QShortcut

from population_synthetic.gui.widgets.dag_graph_items import GRID_SIZE, DagCategoryNode, DagEdge

_SPACING_FACTOR = 1.4
_COLOR_GRID = QColor("#e8e8e8")  # faint grey; visible but unobtrusive against the scene background


class _VertexView:
    def __init__(self, w: float, h: float):
        self.w = w
        self.h = h
        self.xy = (0.0, 0.0)


class DagGraphView(QGraphicsView):
    node_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)

        self._nodes: dict[str, DagCategoryNode] = {}
        self._edges: list[DagEdge] = []
        self._strategy_path: Path | None = None
        self._pan_last = None

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(800)
        self._debounce_timer.timeout.connect(self._save_layout)

        fit_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        fit_shortcut.activated.connect(self.fit_all)

    def populate(self, strategy_path: Path | None) -> None:
        self._scene.clear()
        self._nodes = {}
        self._edges = []
        self._strategy_path = strategy_path

        if strategy_path is None or not strategy_path.exists():
            self._scene.addItem(QGraphicsTextItem("No strategy file"))
            return

        try:
            data = json.loads(strategy_path.read_text(encoding="utf-8"))
        except Exception:
            self._scene.addItem(QGraphicsTextItem("Invalid strategy file"))
            return

        categories = data.get("categories")
        if not isinstance(categories, dict) or not categories:
            self._scene.addItem(QGraphicsTextItem("No categories found in strategy file"))
            return

        # --- Build nodes ---
        for name, cfg in categories.items():
            method = cfg.get("method", "")
            depends_on = cfg.get("depends_on", [])
            node = DagCategoryNode(name, method, depends_on)
            node.signals.node_clicked.connect(self.node_clicked)
            node.signals.position_changed.connect(self._on_node_moved)
            self._scene.addItem(node)
            self._nodes[name] = node

        # --- Build grandalf graph ---
        vertices: dict[str, Vertex] = {}
        for name, node in self._nodes.items():
            v = Vertex(name)
            r = node.rect()
            v.view = _VertexView(r.width(), r.height())
            vertices[name] = v

        g_edges = []
        for name, cfg in categories.items():
            for dep in cfg.get("depends_on", []):
                if dep in vertices and name in vertices:
                    g_edges.append(GEdge(vertices[dep], vertices[name]))

        graph = Graph(list(vertices.values()), g_edges)

        # --- Layout each connected component side-by-side ---
        x_offset = 0.0
        for component in graph.C:
            layout = SugiyamaLayout(component)
            layout.init_all(optimize=True)
            layout.draw()

            comp_max_x = 0.0
            comp_max_w = 0.0
            for v in component.sV:
                vx, vy = v.view.xy
                nx = vx * _SPACING_FACTOR + x_offset
                ny = vy * _SPACING_FACTOR
                node = self._nodes.get(v.data)
                if node is not None:
                    node.setPos(nx, ny)
                    comp_max_x = max(comp_max_x, nx)
                    comp_max_w = max(comp_max_w, node.rect().width())

            x_offset = comp_max_x + comp_max_w * 1.4 * 1.5

        # --- Build edges ---
        for name, cfg in categories.items():
            for dep in cfg.get("depends_on", []):
                if dep in self._nodes and name in self._nodes:
                    edge = DagEdge(self._nodes[dep], self._nodes[name])
                    self._scene.addItem(edge)
                    self._edges.append(edge)

        # --- Load or fit ---
        if not self._load_layout():
            self.fit_all()

    def drawBackground(self, painter: QPainter, rect) -> None:
        """Paint a faint grid matching the node snap step (see ``GRID_SIZE``)."""
        super().drawBackground(painter, rect)
        # A zero-width pen is *cosmetic*: it stays 1 device-pixel wide at any zoom,
        # so the grid reads as a hairline whether the view is zoomed in or out.
        painter.setPen(QPen(_COLOR_GRID, 0))

        first_x = rect.left() - (rect.left() % GRID_SIZE)
        first_y = rect.top() - (rect.top() % GRID_SIZE)

        lines: list[QLineF] = []
        x = first_x
        while x < rect.right():
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
            x += GRID_SIZE
        y = first_y
        while y < rect.bottom():
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            y += GRID_SIZE
        painter.drawLines(lines)

    def fit_all(self) -> None:
        bounding = self._scene.itemsBoundingRect()
        if not bounding.isNull():
            bounding.adjust(-20, -20, 20, 20)
            self.fitInView(bounding, Qt.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        if event.angleDelta().y() > 0:
            self.scale(1.15, 1.15)
        else:
            self.scale(1 / 1.15, 1 / 1.15)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            self._pan_last = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MiddleButton and self._pan_last is not None:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            self.setCursor(Qt.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)

    def _on_node_moved(self, name: str, x: float, y: float) -> None:
        for edge in self._edges:
            edge.update_path()
        self._debounce_timer.start()

    def _save_layout(self) -> None:
        if self._strategy_path is None:
            return
        layout_path = self._strategy_path.with_suffix(".layout.json")
        positions = {name: [node.pos().x(), node.pos().y()] for name, node in self._nodes.items()}
        try:
            layout_path.write_text(json.dumps(positions, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _load_layout(self) -> bool:
        if self._strategy_path is None:
            return False
        layout_path = self._strategy_path.with_suffix(".layout.json")
        if not layout_path.exists():
            return False
        try:
            saved = json.loads(layout_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        loaded_any = False
        for name, xy in saved.items():
            if name in self._nodes and isinstance(xy, list) and len(xy) == 2:
                self._nodes[name].setPos(xy[0], xy[1])
                loaded_any = True
        if loaded_any:
            for edge in self._edges:
                edge.update_path()
        return loaded_any


DagGraphWidget = DagGraphView

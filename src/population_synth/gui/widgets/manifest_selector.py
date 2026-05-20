from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget

from population_synth.gui.manifest_model import ManifestDisplayInfo


class ManifestSelector(QWidget):
    manifest_changed = pyqtSignal(object)

    def __init__(self, manifests_dir: Path, parent=None):
        super().__init__(parent)
        self._manifests_dir = manifests_dir

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Manifest"))

        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_index_changed)
        layout.addWidget(self._combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        self._populate()

    def _populate(self) -> None:
        previous = self.current_manifest()
        self._combo.blockSignals(True)
        self._combo.clear()
        manifests = ManifestDisplayInfo.load_all(self._manifests_dir)
        for info in manifests:
            self._combo.addItem(info.display_name, userData=info)
        self._combo.blockSignals(False)
        current = self.current_manifest()
        if current is not previous:
            self.manifest_changed.emit(current)

    def refresh(self) -> None:
        self._populate()

    def _on_index_changed(self, _index: int) -> None:
        self.manifest_changed.emit(self.current_manifest())

    def current_manifest(self) -> ManifestDisplayInfo | None:
        if self._combo.count() == 0:
            return None
        return self._combo.currentData()

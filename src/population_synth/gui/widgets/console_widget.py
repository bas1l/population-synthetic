import re
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


class ProcessOutputReader(QThread):
    line_received = pyqtSignal(str)
    cr_line_received = pyqtSignal(str)

    def __init__(self, process: subprocess.Popen, parent=None):
        super().__init__(parent)
        self._process = process
        self._stop = False

    def run(self) -> None:
        stdout = self._process.stdout
        if stdout is None:
            return
        buffer = b""
        while not self._stop:
            chunk = stdout.read(1)
            if not chunk:
                break
            buffer += chunk
            if chunk in (b'\n', b'\r'):
                line = buffer.decode("utf-8", errors="replace")
                clean = _ANSI_RE.sub("", line)
                if clean.endswith('\r') and not clean.endswith('\n'):
                    self.cr_line_received.emit(clean.rstrip('\r'))
                else:
                    self.line_received.emit(clean.rstrip('\n').rstrip('\r'))
                buffer = b""
        if buffer:
            line = buffer.decode("utf-8", errors="replace")
            clean = _ANSI_RE.sub("", line).rstrip('\r\n')
            if clean:
                self.line_received.emit(clean)

    def stop(self) -> None:
        self._stop = True


class ConsoleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(10000)

        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.Monospace)
        self._text.setFont(font)

        palette = self._text.palette()
        palette.setColor(QPalette.Base, QColor("#1e1e1e"))
        palette.setColor(QPalette.Text, QColor("#d4d4d4"))
        self._text.setPalette(palette)

        layout.addWidget(self._text)

        bottom_bar = QHBoxLayout()
        self._autoscroll = QCheckBox("Auto-scroll")
        self._autoscroll.setChecked(True)
        bottom_bar.addWidget(self._autoscroll)

        bottom_bar.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_console)
        bottom_bar.addWidget(clear_btn)

        layout.addLayout(bottom_bar)

    def append_line(self, text: str) -> None:
        if self._autoscroll.isChecked():
            self._text.appendPlainText(text)
            self._text.verticalScrollBar().setValue(self._text.verticalScrollBar().maximum())
        else:
            scrollbar = self._text.verticalScrollBar()
            pos = scrollbar.value()
            self._text.appendPlainText(text)
            scrollbar.setValue(pos)

    def append_cr_line(self, text: str) -> None:
        cursor = self._text.textCursor()
        cursor.movePosition(cursor.End)
        cursor.select(cursor.LineUnderCursor)
        cursor.removeSelectedText()
        cursor.insertText(text)
        if self._autoscroll.isChecked():
            self._text.setTextCursor(cursor)
            self._text.verticalScrollBar().setValue(self._text.verticalScrollBar().maximum())

    def clear_console(self) -> None:
        self._text.clear()

"""Entry point for the gui_v2 Flow Runner.

Port of the reference AnalysisRunnerGUI launch script: sets High-DPI
attributes BEFORE the ``QApplication`` is constructed, installs a
``sys.excepthook`` so unhandled exceptions in Qt slots are logged instead of
silently crashing, parses ``config/gui/v2/menu.yaml``, and shows the
:class:`FlowRunnerWindow`. Run as ``python -m population_synthetic.gui_v2.main``.
"""

import logging
import sys
import traceback

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.gui_v2.main_window import FlowRunnerWindow
from population_synthetic.gui_v2.menu_config import parse_menu_config

# High-DPI awareness — must be set BEFORE QApplication is constructed, otherwise
# showMaximized() on Windows with display scaling renders a ~half-screen window
# with a title bar drawn at the unscaled size.
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

_logger = logging.getLogger(__name__)


def _install_exception_hook() -> None:
    """Replace sys.excepthook so that unhandled exceptions in Qt slots are
    logged instead of silently crashing the application."""

    def _hook(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _logger.critical("Unhandled exception in Qt callback:\n%s", msg)
        print(msg, file=sys.stderr, flush=True)

    sys.excepthook = _hook


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _install_exception_hook()

    menu_yaml = PROJECT_ROOT / "config" / "gui" / "v2" / "menu.yaml"
    if not menu_yaml.is_file():
        print(f"Error: gui_v2 menu config not found at {menu_yaml}")
        sys.exit(1)

    entries = parse_menu_config(menu_yaml, PROJECT_ROOT)

    app = QApplication(sys.argv)
    app.setApplicationName("Population Synth Flow Runner")

    window = FlowRunnerWindow(entries)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

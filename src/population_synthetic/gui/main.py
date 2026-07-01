"""Entry point for the Population Synth PyQt5 launcher.

Creates the ``QApplication``, parses ``config/gui/launcher.yaml`` via
``parse_launcher_config``, and shows the ``LauncherWindow``. Run as
``python -m population_synthetic.gui.main``.
"""
import sys

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.gui.launcher_config import parse_launcher_config
from population_synthetic.gui.main_window import LauncherWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Population Synth Launcher")
    app.setFont(QFont(app.font().family(), 12))

    launcher_yaml = PROJECT_ROOT / "config" / "gui" / "launcher.yaml"
    config = parse_launcher_config(launcher_yaml)

    window = LauncherWindow(config=config)
    window.setWindowTitle("Population Synth Launcher")
    window.resize(1300, 750)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

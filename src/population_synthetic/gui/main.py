"""Entry point for the **deprecated** original Population Synth PyQt5 launcher.

.. deprecated::
    This ``LauncherWindow`` launcher has been superseded by the config-driven
    Flow Runner GUI, ``python -m population_synthetic.gui_v2.main``, which is now
    the primary GUI. This entry point still works as a fallback, but the ``gui/``
    package is retained mainly because ``gui_v2`` reuses its widgets and runners
    as shared substrate. New work should target ``gui_v2``.

Creates the ``QApplication``, parses ``config/gui/launcher.yaml`` via
``parse_launcher_config``, and shows the ``LauncherWindow``. Run as
``python -m population_synthetic.gui.main``.
"""
import sys
import warnings

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.gui.launcher_config import parse_launcher_config
from population_synthetic.gui.main_window import LauncherWindow

_DEPRECATION_MESSAGE = (
    "population_synthetic.gui.main is the deprecated original launcher. "
    "Use the primary Flow Runner GUI instead: "
    "python -m population_synthetic.gui_v2.main"
)


def main():
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    print(f"\n\033[33m[DEPRECATED] {_DEPRECATION_MESSAGE}\033[0m\n", file=sys.stderr)

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

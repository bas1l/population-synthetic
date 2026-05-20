import sys

from PyQt5.QtWidgets import QApplication

from population_synth._paths import PROJECT_ROOT
from population_synth.gui.launcher_config import parse_launcher_config
from population_synth.gui.main_window import LauncherWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Population Synth Launcher")

    launcher_yaml = PROJECT_ROOT / "config" / "gui_launcher.yaml"
    actions = parse_launcher_config(launcher_yaml)
    manifests_dir = PROJECT_ROOT / "config" / "seed_manifests"

    window = LauncherWindow(actions=actions, manifests_dir=manifests_dir)
    window.setWindowTitle("Population Synth Launcher")
    window.resize(1100, 750)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

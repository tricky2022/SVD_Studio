import sys

from PySide6.QtWidgets import QApplication

from svdstudio import __title__, __version__
from svdstudio.ui.app_icon import make_app_icon
from svdstudio.ui.main_window import MainWindow
from svdstudio.ui.theme import apply_theme


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(__title__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SVD Studio")
    app.setWindowIcon(make_app_icon())
    apply_theme(app, "light")
    w = MainWindow()
    w.setWindowIcon(make_app_icon())
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

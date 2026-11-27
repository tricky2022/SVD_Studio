"""SVD Studio desktop launcher.

    SVDStudio.exe                     # GUI
    svdstudio-cli.exe validate a.svd   # console CLI
    svdstudio-cli.exe --version
"""
import sys

from svdstudio import __title__, __version__


def _run_gui():
    from PySide6.QtWidgets import QApplication

    from svdstudio.ui.app_icon import make_app_icon
    from svdstudio.ui.main_window import MainWindow
    from svdstudio.ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName(__title__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SVD Studio")
    app.setWindowIcon(make_app_icon())
    apply_theme(app, "light")
    window = MainWindow()
    window.setWindowIcon(make_app_icon())
    window.show()
    return app.exec()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--version", "-V", "version"):
        print(f"{__title__} {__version__}")
        return 0
    if argv and argv[0] in ("--help", "-h"):
        print(__doc__)
        return 0
    if argv and argv[0] == "--mcp":
        print("This build provides the command-line interface through svdstudio.", file=sys.stderr)
        return 2
    if argv and argv[0] == "--cli":
        from svdstudio.cli import main as cli_main
        return cli_main(argv[1:])
    return _run_gui()


if __name__ == "__main__":
    raise SystemExit(main())

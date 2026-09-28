"""Unified entry point: GUI by default, CLI and MCP from the same binary.

A single frozen executable serves all three interfaces, so shipping an
``.exe`` to a colleague also ships the automation surface:

    SVDStudio.exe                     # GUI
    SVDStudio.exe --cli validate a.svd
    SVDStudio.exe --cli import-table regs.csv out.svd --device MYDEV
    SVDStudio.exe --mcp               # MCP stdio server for AI agents
    SVDStudio.exe --version

``svdstudio-cli.exe`` (console build) exposes the same flags without the
Qt window subsystem, which is what MCP clients expect on stdout.
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
        from svdstudio.mcp_server import main as mcp_main
        return mcp_main()
    if argv and argv[0] == "--cli":
        from svdstudio.cli import main as cli_main
        return cli_main(argv[1:])
    return _run_gui()


if __name__ == "__main__":
    raise SystemExit(main())

"""TL Studio Pro - application entry point.

    python app.py                 start the desktop app
    python app.py my.qrstudio.json   open a project
    python app.py --selftest      headless check that rendering and every export format work
                                  (used to verify packaged builds; exit code 0 = OK)
"""
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        from src.selftest import run_selftest

        return run_selftest()
    if "--version" in argv:
        from src.version import APP_NAME, VERSION

        print(f"{APP_NAME} {VERSION}")
        return 0

    # Let the GUI thread take the interpreter lock back quickly while previews render in the background.
    sys.setswitchinterval(0.001)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from src.services.app_prefs import AppPrefs
    from src.ui.main_window import check_icon_path
    from src.ui.theme import apply_theme, resolve_mode, setup_fonts
    from src.utils.logging_config import get_logger, setup_logging
    from src.version import APP_NAME, ORG_NAME

    log_path = setup_logging()
    log = get_logger("app")

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    prefs = AppPrefs.load()
    setup_fonts(app)
    apply_theme(app, prefs.theme, check_icon_path())

    from src import i18n
    i18n.install(app, prefs.language)
    from src.ui.hub import HubWindow
    hub = HubWindow(prefs)
    i18n.retranslate(hub)
    hub.show()
    for arg in argv[1:]:
        if not arg.startswith("-") and arg.lower().endswith((".qrsp", ".json")):
            hub.open_tool("qr", arg)          # a project file opens straight in QR Studio
            break
    log.info("started (log: %s)", log_path.name)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))

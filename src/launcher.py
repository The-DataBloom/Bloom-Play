import os
import platform
import sys
import threading
import logging

import uvicorn
from PyQt5 import QtWidgets

from api.server import app
from overlay.main_window import MainWindow
from collectors import hwmonitor
from collectors.fps import find_presentmon
from utils.elevate import is_admin, relaunch_as_admin

_IS_WINDOWS = platform.system() == "Windows"

_skip_admin_prompt = False

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def _fix_windowed_io():
    if not getattr(sys, "frozen", False):
        return
    if sys.stdout is None or sys.stderr is None:
        try:
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            log_dir = os.path.join(base, "BloomPlay")
            os.makedirs(log_dir, exist_ok=True)
            handle = open(os.path.join(log_dir, "BloomPlay-api.log"), "a", encoding="utf-8")
        except Exception:
            handle = open(os.devnull, "w")
        if sys.stdout is None:
            sys.stdout = handle
        if sys.stderr is None:
            sys.stderr = handle


def _maybe_elevate():
    global _skip_admin_prompt
    needs_admin = hwmonitor.dll_present() or bool(find_presentmon())
    if not (_IS_WINDOWS and needs_admin):
        return
    if is_admin():
        return
    if _skip_admin_prompt:
        return

    if relaunch_as_admin():
        sys.exit(0)
    else:
        _skip_admin_prompt = True


def start_api():
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="warning",
            access_log=False,
        )
    except Exception as e:
        print(f"[API] Failed to start server: {e}")


def main():
    _fix_windowed_io()
    _maybe_elevate()

    api_thread = threading.Thread(
        target=start_api,
        daemon=True,
        name="BloomPlay-API",
    )
    api_thread.start()

    qt_app = QtWidgets.QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()

    sys.exit(qt_app.exec_())


if __name__ == "__main__":
    main()

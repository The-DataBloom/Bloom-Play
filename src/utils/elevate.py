from __future__ import annotations

import ctypes
import platform
import sys

_IS_WINDOWS = platform.system() == "Windows"


def is_admin() -> bool:
    if not _IS_WINDOWS:
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    if not _IS_WINDOWS:
        return False

    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv[1:])
        else:
            exe = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv)

        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return int(result) > 32
    except Exception as e:
        print(f"[elevate] Could not relaunch as admin: {e}")
        return False

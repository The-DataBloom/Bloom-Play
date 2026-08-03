from __future__ import annotations

import os
import sys
import tempfile

import qrcode


def _default_path() -> str:
    if getattr(sys, "frozen", False):
        base = tempfile.gettempdir()
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, "qr.png")


def create_qr(url: str, path: str | None = None) -> str | None:
    try:
        target = path or _default_path()
        img = qrcode.make(url)
        img.save(target)
        return target
    except Exception as e:
        print(f"[qr] Could not create QR: {e}")
        return None

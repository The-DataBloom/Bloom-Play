from __future__ import annotations

import threading

from PyQt5.QtCore import QSettings

_lock = threading.Lock()
_settings: QSettings | None = None
_listeners = []

DEFAULT_COLOR = "#22d3a7"
DEFAULT_POSITION = "top-right"
DEFAULT_FONT_SIZE = 14
DEFAULT_FONT_FAMILY = "Consolas, 'Segoe UI', monospace"
FONT_FAMILIES = [
    "Consolas, 'Segoe UI', monospace",
    "'Segoe UI', Tahoma, sans-serif",
    "'Courier New', monospace",
    "Arial, sans-serif",
    "Tahoma, sans-serif",
]

POSITIONS = ["top-left", "top-right", "bottom-left", "bottom-right"]
ALL_FIELDS = [
    ("cpu", "CPU %"),
    ("cpu_temp", "CPU Temp"),
    ("gpu", "GPU %"),
    ("gpu_temp", "GPU Temp"),
    ("ram", "RAM"),
    ("fps", "FPS"),
    ("download", "Download"),
    ("upload", "Upload"),
    ("ping", "Ping"),
    ("battery", "Battery"),
]
DEFAULT_FIELDS = ["cpu", "cpu_temp", "gpu", "gpu_temp", "fps"]


def bind(settings: QSettings):
    global _settings
    with _lock:
        _settings = settings


def _ensure_settings() -> QSettings:
    global _settings
    if _settings is None:
        _settings = QSettings("BloomPlay", "BloomPlay")
    return _settings


def get_config() -> dict:
    s = _ensure_settings()
    with _lock:
        fields_raw = s.value("overlay_fields", ",".join(DEFAULT_FIELDS), type=str)
        fields = [f for f in fields_raw.split(",") if f] or DEFAULT_FIELDS
        if "network" in fields:
            fields.remove("network")
            for nf in ["download", "upload", "ping"]:
                if nf not in fields:
                    fields.append(nf)
        position = s.value("overlay_position", DEFAULT_POSITION, type=str)
        return {
            "enabled": s.value("overlay_enabled", False, type=bool),
            "color": s.value("overlay_color", DEFAULT_COLOR, type=str),
            "position": position if position in POSITIONS else DEFAULT_POSITION,
            "font_size": s.value("overlay_font_size", DEFAULT_FONT_SIZE, type=int),
            "fields": fields,
            "hotkey": s.value("overlay_hotkey", "Ctrl+Shift+O", type=str),
            "font_family": s.value("overlay_font_family", DEFAULT_FONT_FAMILY, type=str),
        }


def update_config(**kwargs) -> dict:
    s = _ensure_settings()
    with _lock:
        if "enabled" in kwargs and kwargs["enabled"] is not None:
            s.setValue("overlay_enabled", bool(kwargs["enabled"]))
        if "color" in kwargs and kwargs["color"]:
            s.setValue("overlay_color", str(kwargs["color"]))
        if "position" in kwargs and kwargs["position"] in POSITIONS:
            s.setValue("overlay_position", kwargs["position"])
        if "font_size" in kwargs and kwargs["font_size"]:
            size = max(8, min(int(kwargs["font_size"]), 36))
            s.setValue("overlay_font_size", size)
        if "fields" in kwargs and kwargs["fields"] is not None:
            valid = {k for k, _ in ALL_FIELDS}
            fields = [f for f in kwargs["fields"] if f in valid]
            s.setValue("overlay_fields", ",".join(fields))

        if "font_family" in kwargs and kwargs["font_family"]:
            s.setValue("overlay_font_family", str(kwargs["font_family"]))
        if "hotkey" in kwargs and kwargs["hotkey"]:
            s.setValue("overlay_hotkey", str(kwargs["hotkey"]).strip())
        s.sync()

    snapshot = get_config()
    for cb in list(_listeners):
        try:
            cb(snapshot)
        except Exception:
            pass
    return snapshot


def add_listener(callback):
    _listeners.append(callback)

import platform

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import pyqtSignal

from api import overlay_config

_IS_WINDOWS = platform.system() == "Windows"

try:
    import win32gui
    import win32con
except Exception:
    win32gui = None
    win32con = None

ALL_FIELDS = overlay_config.ALL_FIELDS
DEFAULT_FIELDS = overlay_config.DEFAULT_FIELDS
POSITIONS = overlay_config.POSITIONS
DEFAULT_POSITION = overlay_config.DEFAULT_POSITION
DEFAULT_COLOR = overlay_config.DEFAULT_COLOR
DEFAULT_FONT_SIZE = overlay_config.DEFAULT_FONT_SIZE
DEFAULT_FONT_FAMILY = overlay_config.DEFAULT_FONT_FAMILY
FONT_FAMILIES = overlay_config.FONT_FAMILIES


class OverlayWidget(QtWidgets.QWidget):
    external_config_changed = pyqtSignal(dict)

    def __init__(self, settings: QtCore.QSettings):
        super().__init__()
        self.settings = settings
        overlay_config.bind(settings)
        overlay_config.add_listener(self.external_config_changed.emit)
        self.external_config_changed.connect(self._on_external_config_changed)

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self.label = QtWidgets.QLabel(self)
        self.label.setTextFormat(QtCore.Qt.RichText)
        self.label.setWordWrap(False)
        layout.addWidget(self.label)

        self._apply_style()
        self.label.setText("BloomPlay Overlay")
        self.adjustSize()
        self._reposition()

    def _on_external_config_changed(self, _config: dict):
        self.refresh_appearance()
        self.apply_enabled_state()

    def get_enabled(self) -> bool:
        return self.settings.value("overlay_enabled", False, type=bool)

    def get_color(self) -> str:
        return self.settings.value("overlay_color", DEFAULT_COLOR, type=str)

    def get_font_size(self) -> int:
        return self.settings.value("overlay_font_size", DEFAULT_FONT_SIZE, type=int)

    def get_font_family(self) -> str:
        return self.settings.value("overlay_font_family", DEFAULT_FONT_FAMILY, type=str)

    def get_position(self) -> str:
        pos = self.settings.value("overlay_position", DEFAULT_POSITION, type=str)
        return pos if pos in POSITIONS else DEFAULT_POSITION

    def get_fields(self) -> list:
        raw = self.settings.value("overlay_fields", ",".join(DEFAULT_FIELDS), type=str)
        fields = [f for f in raw.split(",") if f]
        return fields or DEFAULT_FIELDS

    def _apply_style(self):
        color = self.get_color()
        font_size = self.get_font_size()
        font_family = self.get_font_family()
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(10, 14, 26, 190);
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: 10px;
            }}
            QLabel {{
                color: {color};
                font-family: {font_family};
                font-size: {font_size}px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
        """)

    def _reposition(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        margin = 16
        w, h = self.width(), self.height()
        position = self.get_position()

        if position == "top-left":
            x, y = geo.left() + margin, geo.top() + margin
        elif position == "bottom-left":
            x, y = geo.left() + margin, geo.bottom() - h - margin
        elif position == "bottom-right":
            x, y = geo.right() - w - margin, geo.bottom() - h - margin
        else:
            x, y = geo.right() - w - margin, geo.top() + margin

        self.move(int(x), int(y))

    def refresh_appearance(self):
        self._apply_style()
        self.adjustSize()
        self._reposition()

    def apply_enabled_state(self):
        if self.get_enabled():
            self.show()
            self._reassert_topmost()
        else:
            self.hide()

    def _reassert_topmost(self):
        if not (_IS_WINDOWS and win32gui and win32con and self.isVisible()):
            return
        try:
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
            )
        except Exception:
            pass

    def update_stats(self, data: dict):
        if not self.get_enabled():
            return

        fields = self.get_fields()
        lines = []

        gpu = data.get("gpu") or {}
        ram = data.get("ram") or {}
        net = data.get("network") or {}
        battery = data.get("battery") or {}
        fps = data.get("fps") or {}

        if "cpu" in fields:
            lines.append(f"CPU  {data.get('cpu', 0)}%")
        if "cpu_temp" in fields:
            t = data.get("cpu_temp")
            lines.append(f"CPU°  {t if t is not None else 'N/A'}°C")
        if "gpu" in fields:
            lines.append(f"GPU  {gpu.get('usage', 0)}%")
        if "gpu_temp" in fields:
            t = gpu.get("temp")
            lines.append(f"GPU°  {t if t is not None else 'N/A'}°C")
        if "ram" in fields:
            lines.append(f"RAM  {ram.get('used', 0)} GB")
        if "fps" in fields:
            f = fps.get("fps")
            lines.append(f"FPS  {f if f is not None else 'N/A'}")
        if "download" in fields:
            lines.append(f"DL  {net.get('download', 0)} Mbps")
        if "upload" in fields:
            lines.append(f"UL  {net.get('upload', 0)} Mbps")
        if "ping" in fields:
            lines.append(f"Ping  {net.get('ping', 0)}ms")
        if "battery" in fields:
            pct = battery.get("percent", "N/A")
            lines.append(f"BAT  {pct}%")

        if not lines:
            lines = ["No fields selected — pick some in Settings"]

        self.label.setText("<br>".join(lines))
        self.adjustSize()
        self._reposition()
        self._reassert_topmost()

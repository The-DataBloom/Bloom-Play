from __future__ import annotations

import os
import platform
import time
import webbrowser

from PyQt5 import QtWidgets, QtGui, QtCore, QtPrintSupport
from PyQt5.QtCore import QThread, pyqtSignal, QSettings, QAbstractNativeEventFilter

from api import state, overlay_config
from engine import get_all_stats
from utils.ip import get_local_ip
from utils.qr import create_qr
from collectors.hardware import get_hardware_info, build_pdf_sections
from overlay.overlay_widget import OverlayWidget, ALL_FIELDS, DEFAULT_FIELDS, POSITIONS, DEFAULT_POSITION, DEFAULT_COLOR, FONT_FAMILIES

_IS_WINDOWS = platform.system() == "Windows"


_WIDGET_TR = {
    "N/A": "نامشخص",
    "Great": "عالی",
    "Good": "خوب",
    "Fair": "متوسط",
    "Poor": "ضعیف",
    "Perfect": "عالی",
    "Excellent": "عالی",
    "No Battery": "بدون باتری",
    "No storage info available": "اطلاعات فضای ذخیره موجود نیست",
    "Unavailable": "در دسترس نیست",
    "Degraded": "کاهش یافته",
    "Desktop PC": "رایانه رومیزی",
}


def _qtr(text: str) -> str:
    try:
        lang = QSettings("BloomPlay", "Settings").value("language", "en", type=str)
    except Exception:
        lang = "en"
    if lang == "fa":
        return _WIDGET_TR.get(text, text)
    return text


def _is_fa() -> bool:
    try:
        return QSettings("BloomPlay", "Settings").value("language", "en", type=str) == "fa"
    except Exception:
        return False

WM_HOTKEY = 0x0312
HOTKEY_ID_OVERLAY = 1
HOTKEY_ID_SS_FULL = 2
HOTKEY_ID_SS_WIN = 3
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
VK_O = 0x4F
DEFAULT_HOTKEY = "Ctrl+Shift+O"
DEFAULT_SS_FULL_HOTKEY = "Ctrl+Shift+F"
DEFAULT_SS_WIN_HOTKEY = "Ctrl+Shift+W"


class _GlobalHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, handlers):
        super().__init__()
        self._handlers = dict(handlers)

    def nativeEventFilter(self, event_type, message):
        if _IS_WINDOWS and event_type == b"windows_generic_MSG":
            try:
                import ctypes
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    cb = self._handlers.get(msg.wParam)
                    if cb is not None:
                        cb()
            except Exception:
                pass
        return False, 0


class HealthArc(QtWidgets.QWidget):
    ARC_START = 180 * 16
    ARC_SPAN = 180 * 16

    def __init__(self, icon: str, title: str, accent: str, unit: str = "%",
                 max_val: float = 100, warn: float = 70, crit: float = 85,
                 invert: bool = False, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.unit = unit
        self.max_val = max_val
        self.warn = warn
        self.crit = crit
        self.invert = invert
        self.value = None
        self.setMinimumSize(120, 120)

    def set_value(self, value):
        self.value = value
        self.update()

    def _threshold_color(self, v):
        if v is None:
            return "#374151"
        if self.invert:
            if v <= self.crit:
                return "#ef4444"
            if v <= self.warn:
                return "#f59e0b"
        else:
            if v >= self.crit:
                return "#ef4444"
            if v >= self.warn:
                return "#f59e0b"
        return self.accent

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, int(h * 0.60)
        radius = int(min(w, h * 0.90) // 2 - 8)
        rect = QtCore.QRect(cx - radius, cy - radius, radius * 2, radius * 2)

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(6, 2, w - 12, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        p.setPen(QtGui.QPen(QtGui.QColor("#222238"), 8,
                QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        p.drawArc(rect, self.ARC_START, -self.ARC_SPAN)

        if self.value is not None:
            v = max(0.0, min(float(self.value), self.max_val))
            frac = v / self.max_val
            span = int(-self.ARC_SPAN * frac)
            color = self._threshold_color(self.value)

            p.setPen(QtGui.QPen(QtGui.QColor(color), 8,
                    QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
            p.drawArc(rect, self.ARC_START, span)

            text = f"{v:.0f}{self.unit}"
        else:
            text = _qtr("N/A")

        p.setPen(QtGui.QColor("#ffffff"))
        f = p.font()
        f.setPointSize(14 if len(text) <= 5 else 11)
        f.setBold(True)
        p.setFont(f)
        vr = QtCore.QRect(2, int(cy + radius * 0.30), w - 4, int(h - cy - radius * 0.30))
        p.drawText(vr, QtCore.Qt.AlignCenter, text)


class HeatPipe(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, accent: str,
                 max_temp: float = 100, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.max_temp = max_temp
        self.value = None
        self.setMinimumSize(96, 120)

    def set_value(self, value):
        self.value = value
        self.update()

    def _temp_color(self, v):
        if v is None:
            return "#374151"
        if v >= 85:
            return "#ef4444"
        if v >= 70:
            return "#f59e0b"
        return self.accent

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx = w // 2
        pipe_w = 18
        top_margin = 26
        bot_margin = 22
        pipe_h = h - top_margin - bot_margin
        pipe_x = cx - pipe_w // 2
        radius = pipe_w // 2

        p.setPen(QtGui.QPen(QtGui.QColor("#1c1c38"), 1))
        p.setBrush(QtGui.QColor("#0a0e1a"))
        p.drawRoundedRect(pipe_x, top_margin, pipe_w, pipe_h, radius, radius)

        if self.value is not None:
            v = max(0.0, min(float(self.value), self.max_temp))
            frac = v / self.max_temp
            fill_col = self._temp_color(self.value)
            fill_h = int(pipe_h * frac)
            fill_y = top_margin + pipe_h - fill_h
            fill_r = QtCore.QRect(pipe_x + 2, fill_y, pipe_w - 4, fill_h)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(fill_col))
            p.drawRoundedRect(fill_r, radius - 2, radius - 2)

            if v >= 60:
                glow = QtGui.QColor(fill_col)
                glow.setAlpha(40)
                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(glow)
                p.drawEllipse(QtCore.QPoint(cx, fill_y), pipe_w, pipe_w // 2)

            text = f"{self.value}°"
        else:
            text = _qtr("N/A")

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(4, 2, w - 8, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        p.setPen(QtGui.QColor("#ffffff"))
        f = p.font()
        f.setPointSize(14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(0, h - bot_margin + 2, w, bot_margin - 4),
                   QtCore.Qt.AlignCenter, text)


class BlockMeter(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.value = None
        self.sub_text = ""
        self.setMinimumSize(150, 92)

    def set_value(self, value, sub_text=""):
        self.value = value
        self.sub_text = sub_text
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(8, 2, w - 16, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        v = 0.0 if self.value is None else max(0.0, min(float(self.value), 100.0))
        num_blocks = 8
        block_h = 24
        block_gap = 3
        blocks_top = 26
        total_w = w - 24
        block_w = (total_w - block_gap * (num_blocks - 1)) // num_blocks
        filled = int((v / 100.0) * num_blocks + 0.99)

        for i in range(num_blocks):
            bx = 12 + i * (block_w + block_gap)
            br = QtCore.QRect(bx, blocks_top, block_w, block_h)
            if self.value is not None and i < filled:
                if i < 5:
                    color = self.accent
                elif i < 7:
                    color = "#f59e0b"
                else:
                    color = "#ef4444"

                if i == filled - 1 and filled > 0:
                    glow = QtGui.QColor(color)
                    glow.setAlpha(50)
                    p.setPen(QtCore.Qt.NoPen)
                    p.setBrush(glow)
                    p.drawRoundedRect(br.adjusted(-2, -2, 2, 2), 5, 5)

                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(QtGui.QColor(color))
                p.drawRoundedRect(br, 3, 3)

                hl = QtGui.QColor(255, 255, 255, 35)
                p.setBrush(hl)
                p.drawRoundedRect(
                    QtCore.QRect(bx + 2, blocks_top + 2,
                                 block_w - 4, (block_h - 4) // 2), 2, 2)
            else:
                p.setPen(QtGui.QPen(QtGui.QColor("#1c1c38"), 1))
                p.setBrush(QtGui.QColor("#0a0e1a"))
                p.drawRoundedRect(br, 3, 3)

        p.setPen(QtGui.QColor("#ffffff"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        pct = f"{self.value}%" if self.value is not None else _qtr("N/A")
        p.drawText(QtCore.QRect(12, blocks_top + block_h + 2, total_w, 16),
                   QtCore.Qt.AlignCenter, pct)

        if self.sub_text:
            p.setPen(QtGui.QColor("#ffffff"))
            f.setPointSize(9)
            f.setBold(False)
            p.setFont(f)
            p.drawText(QtCore.QRect(8, blocks_top + block_h + 22, w - 16, 16),
                       QtCore.Qt.AlignLeft, self.sub_text)


class WaveDash(QtWidgets.QWidget):
    @property
    def accent(self):
        return self.color

    def __init__(self, icon: str, title: str, color: str,
                 unit: str = "Mbps", parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.color = color
        self.unit = unit
        self.history = []
        self.value = None
        self.setMinimumSize(155, 80)

    def set_value(self, value: float):
        self.value = value
        self.history.append(max(value, 0.0))
        if len(self.history) > 40:
            self.history.pop(0)
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(8, 2, w - 16, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        val_text = f"{self.value:.1f} {self.unit}" if self.value is not None else _qtr("N/A")
        p.setPen(QtGui.QColor(self.color))
        f = p.font()
        f.setPointSize(14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(8, 24, w - 16, 20), QtCore.Qt.AlignLeft, val_text)

        chart = QtCore.QRect(8, 46, w - 16, h - 50)
        if chart.height() < 10 or chart.width() < 10:
            return

        p.setPen(QtGui.QPen(QtGui.QColor("#2e2e52"), 1))
        p.setBrush(QtGui.QColor(30, 34, 66, 120))
        p.drawRoundedRect(chart, 8, 8)

        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 18), 1))
        for frac in (0.25, 0.5, 0.75):
            gy = chart.bottom() - int(chart.height() * frac)
            p.drawLine(chart.left(), gy, chart.right(), gy)
        p.setPen(QtGui.QPen(QtGui.QColor("#3b4a6b"), 1))
        p.drawLine(chart.bottomLeft(), chart.bottomRight())

        if len(self.history) < 2:
            p.setPen(QtGui.QColor("#8b93b8"))
            f = p.font()
            f.setPointSize(9)
            f.setBold(False)
            p.setFont(f)
            p.drawText(chart, QtCore.Qt.AlignCenter, _qtr("Waiting for data…"))
            return

        max_v = max(max(self.history), 1.0)
        step_x = chart.width() / (len(self.history) - 1)
        pts = []
        for i, val in enumerate(self.history):
            pts.append(QtCore.QPointF(
                chart.x() + i * step_x,
                chart.bottom() - (val / max_v) * chart.height()
            ))

        def _bezier(path, pts):
            path.moveTo(pts[0])
            for i in range(len(pts) - 1):
                p0, p1 = pts[i], pts[i + 1]
                d = (p1.x() - p0.x()) * 0.4
                path.cubicTo(p0.x() + d, p0.y(),
                             p1.x() - d, p1.y(),
                             p1.x(), p1.y())

        fill_path = QtGui.QPainterPath()
        fill_path.moveTo(chart.x(), chart.bottom())
        fill_path.lineTo(pts[0])
        _bezier(fill_path, pts)
        fill_path.lineTo(chart.right(), chart.bottom())
        fill_path.closeSubpath()
        grad = QtGui.QLinearGradient(0, chart.top(), 0, chart.bottom())
        c1 = QtGui.QColor(self.color)
        c1.setAlpha(120)
        c2 = QtGui.QColor(self.color)
        c2.setAlpha(10)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(fill_path)

        line_path = QtGui.QPainterPath()
        _bezier(line_path, pts)
        glow = QtGui.QColor(self.color)
        glow.setAlpha(55)
        p.setPen(QtGui.QPen(glow, 5.5, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(line_path)
        p.setPen(QtGui.QPen(QtGui.QColor(self.color), 2.5,
                QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        p.drawPath(line_path)

        if pts:
            c = QtGui.QColor(self.color)
            c.setAlpha(80)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(pts[-1], 6, 6)
            p.setBrush(QtGui.QColor(self.color))
            p.drawEllipse(pts[-1], 3, 3)


class NeonBadge(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, accent: str,
                 quality_mode: str = None, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.quality_mode = quality_mode
        self.value = None
        self.sub_text = ""
        self.setMinimumSize(95, 85)

    def set_value(self, value, sub_text=""):
        self.value = value
        self.sub_text = sub_text
        self.update()

    def _quality_color(self, v):
        try:
            val = float(v) if v is not None else None
        except (ValueError, TypeError):
            val = None
        if val is None:
            return ("#374151", "")
        if self.quality_mode == "ping":
            if val < 50:
                return ("#22c55e", _qtr("Great"))
            if val < 100:
                return ("#eab308", _qtr("Good"))
            if val < 200:
                return ("#f97316", _qtr("Fair"))
            return ("#ef4444", _qtr("Poor"))
        if self.quality_mode == "health":
            if val >= 80:
                return ("#22c55e", _qtr("Excellent"))
            if val >= 60:
                return ("#eab308", _qtr("Good"))
            if val >= 40:
                return ("#f97316", _qtr("Fair"))
            return ("#ef4444", _qtr("Poor"))
        return (self.accent, "")

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(6, 2, w - 12, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        cx, cy = w // 2, int(h * 0.50)
        r = int(min(w, h * 0.6) // 2 - 6)
        c = QtGui.QColor(self.accent)
        c.setAlpha(8)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(QtCore.QPoint(cx, cy), r + 8, r + 8)
        c.setAlpha(15)
        p.setBrush(c)
        p.drawEllipse(QtCore.QPoint(cx, cy), r, r)

        text = str(self.value) if self.value is not None else _qtr("N/A")
        p.setPen(QtGui.QColor(self.accent))
        f = p.font()
        f.setPointSize(20 if len(text) <= 4 else 14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(2, 26, w - 4, int(cy - r - 6)),
                   QtCore.Qt.AlignCenter, text)

        if self.quality_mode and self.value is not None:
            q_color, q_label = self._quality_color(self.value)
            bar_y = int(h * 0.65)
            bar_w = int(w * 0.50)
            bar_x = (w - bar_w) // 2
            bar_h = 4
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor("#1c1c38"))
            p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 2, 2)
            fill_frac = 1.0
            if self.quality_mode == "ping":
                try:
                    v = float(self.value)
                except (ValueError, TypeError):
                    v = 200
                fill_frac = max(0.0, min(1.0, 1.0 - (v / 200.0)))
            elif self.quality_mode == "health":
                try:
                    v = float(self.value)
                except (ValueError, TypeError):
                    v = 0
                fill_frac = max(0.0, min(1.0, v / 100.0))
            fill_w = int(bar_w * fill_frac)
            if fill_w > 0:
                p.setBrush(QtGui.QColor(q_color))
                p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 2, 2)
            p.setPen(QtGui.QColor(q_color))
            f.setPointSize(8)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QtCore.QRect(0, bar_y + 6, w, 14),
                       QtCore.Qt.AlignCenter, q_label)

        elif self.sub_text:
            p.setPen(QtGui.QColor("#e5e7eb"))
            f.setPointSize(9)
            f.setBold(False)
            p.setFont(f)
            p.drawText(QtCore.QRect(4, h - 28, w - 8, 24),
                       QtCore.Qt.AlignCenter, self.sub_text)


class BatteryIcon(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.value = None
        self.charging = False
        self.setMinimumSize(130, 88)

    def set_value(self, value, charging=False):
        self.value = value
        self.charging = charging
        self.update()

    def _fill_color(self, v):
        if v is None:
            return "#374151"
        if v >= 80:
            return "#22c55e"
        if v >= 60:
            return "#86efac"
        if v >= 40:
            return "#eab308"
        if v >= 20:
            return "#f97316"
        return "#ef4444"

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(6, 2, w - 12, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        has_battery = self.value is not None and self.value != "N/A"

        if not has_battery:
            p.setPen(QtGui.QColor("#e5e7eb"))
            f.setPointSize(12)
            f.setBold(False)
            p.setFont(f)
            p.drawText(QtCore.QRect(4, int(h * 0.40), w - 8, 24),
                       QtCore.Qt.AlignCenter, _qtr("No Battery"))
            return

        bar_h = 24
        bar_y = max(30, int(h * 0.32))
        bar_w = int(w * 0.65)
        bar_x = (w - bar_w) // 2
        term_w = 6
        term_x = bar_x + bar_w - term_w
        term_y = bar_y + (bar_h - 12) // 2

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#94a3b8"))
        p.drawRoundedRect(term_x, term_y, term_w, 12, 2, 2)

        body_rect = QtCore.QRect(bar_x, bar_y, bar_w - term_w, bar_h)
        p.setPen(QtGui.QPen(QtGui.QColor("#4a5a7a"), 1.5))
        p.setBrush(QtGui.QColor("#0a0e1a"))
        p.drawRoundedRect(body_rect, 5, 5)

        if self.value is not None:
            v = max(0.0, min(float(self.value), 100.0))
            fill_w = int((bar_w - term_w - 4) * (v / 100.0))
            fill_color = self._fill_color(self.value)
            if fill_w > 0:
                fill_rect = QtCore.QRect(bar_x + 2, bar_y + 2, fill_w, bar_h - 4)
                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(QtGui.QColor(fill_color))
                p.drawRoundedRect(fill_rect, 3, 3)

        if self.charging:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor("#facc15"))
            mid_y = bar_y + bar_h // 2
            bx = bar_x + bar_w - term_w - 18
            bolt = QtGui.QPainterPath()
            bolt.moveTo(bx, mid_y - 7)
            bolt.lineTo(bx + 6, mid_y)
            bolt.lineTo(bx + 3, mid_y)
            bolt.lineTo(bx + 9, mid_y + 7)
            bolt.lineTo(bx + 6, mid_y + 7)
            bolt.lineTo(bx, mid_y)
            p.drawPath(bolt)

        pct = f"{self.value}%" if self.value is not None else _qtr("N/A")
        p.setPen(QtGui.QColor("#ffffff"))
        f = p.font()
        f.setPointSize(16)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(0, bar_y + bar_h + 10, w, 20),
                   QtCore.Qt.AlignCenter, pct)


class PingGauge(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.value = None
        self.setMinimumSize(95, 95)

    def set_value(self, value):
        self.value = value
        self.update()

    def _ping_info(self, v):
        if v is None:
            return (0, "#374151", "")
        raw = str(v).strip().lower().replace("ms", "").replace(" ", "")
        try:
            val = float(raw) if raw else None
        except (ValueError, TypeError):
            val = None
        if val is None:
            return (0, "#374151", "")
        if val < 20:
            return (5, "#22c55e", _qtr("Perfect"))
        if val < 50:
            return (4, "#22c55e", _qtr("Great"))
        if val < 100:
            return (3, "#eab308", _qtr("Good"))
        if val < 200:
            return (2, "#f97316", _qtr("Fair"))
        return (1, "#ef4444", _qtr("Poor"))

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(6, 2, w - 12, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        text = f"{self.value}" if self.value is not None else _qtr("N/A")
        p.setPen(QtGui.QColor("#ffffff"))
        f = p.font()
        f.setPointSize(18 if len(text) <= 4 else 13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(0, 26, w, 22), QtCore.Qt.AlignCenter, text)

        if self.value is not None:
            p.setPen(QtGui.QColor("#e5e7eb"))
            f.setPointSize(9)
            f.setBold(False)
            p.setFont(f)
            p.drawText(QtCore.QRect(0, 50, w, 10), QtCore.Qt.AlignCenter, "ms")

        num_bars, tier_color, label = self._ping_info(self.value)
        bar_count = 5
        bar_w = 6
        max_bar_h = 28
        bar_gap = 4
        bars_top = 62
        total_bars_w = bar_count * bar_w + (bar_count - 1) * bar_gap
        bars_left = (w - total_bars_w) // 2
        bar_heights = [6, 12, 18, 24, 28]

        for i in range(bar_count):
            bh = bar_heights[i]
            bx = bars_left + i * (bar_w + bar_gap)
            by = bars_top + (max_bar_h - bh)
            br = QtCore.QRect(bx, by, bar_w, bh)
            if i < num_bars:
                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(QtGui.QColor(tier_color))
                p.drawRoundedRect(br, 2, 2)
                hl = QtGui.QColor(255, 255, 255, 45)
                p.setBrush(hl)
                p.drawRoundedRect(QtCore.QRect(bx + 1, by + 1,
                                                bar_w - 2, bh // 2), 2, 2)
            else:
                p.setPen(QtGui.QPen(QtGui.QColor("#1c1c38"), 1))
                p.setBrush(QtGui.QColor("#0f1729"))
                p.drawRoundedRect(br, 2, 2)

        if label:
            p.setPen(QtGui.QColor(tier_color))
            f.setPointSize(9)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QtCore.QRect(0, bars_top + max_bar_h + 2, w, 14),
                       QtCore.Qt.AlignCenter, label)


class FPSBar(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent        
        self.value = None
        self.history = []
        self.setMinimumSize(95, 80)

    def set_value(self, value, sub_text=""):
        if isinstance(value, dict):
            value = value.get("fps", 0)
        try:
            n = max(0, int(value))
        except (ValueError, TypeError):
            n = 0
        self.value = n
        self.history.append(n if n > 0 else 1)
        if len(self.history) > 30:
            self.history.pop(0)
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(6, 2, w - 12, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        text = str(self.value) if self.value is not None else _qtr("N/A")
        p.setPen(QtGui.QColor(self.accent))
        f = p.font()
        f.setPointSize(22 if len(text) <= 4 else 16)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(4, 26, w - 8, 22), QtCore.Qt.AlignCenter, text)

        chart_y = 52
        chart_h = h - chart_y - 6
        if chart_h > 6:
            chart_r = QtCore.QRect(8, chart_y, w - 16, chart_h)
            p.setPen(QtGui.QPen(QtGui.QColor("#2e2e52"), 1))
            p.setBrush(QtGui.QColor(30, 34, 66, 120))
            p.drawRoundedRect(chart_r, 8, 8)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 16), 1))
            for frac in (1.0 / 3.0, 2.0 / 3.0):
                gy = chart_r.bottom() - int(chart_r.height() * frac)
                p.drawLine(chart_r.left(), gy, chart_r.right(), gy)
            p.setPen(QtGui.QPen(QtGui.QColor("#3b4a6b"), 1))
            p.drawLine(chart_r.bottomLeft(), chart_r.bottomRight())

            if len(self.history) < 2:
                p.setPen(QtGui.QColor("#8b93b8"))
                f = p.font()
                f.setPointSize(8)
                f.setBold(False)
                p.setFont(f)
                p.drawText(chart_r, QtCore.Qt.AlignCenter, _qtr("Waiting for data…"))
                return

            max_v = max(max(self.history), 1)
            step_x = chart_r.width() / (len(self.history) - 1)
            pts = [QtCore.QPointF(
                chart_r.x() + i * step_x,
                chart_r.bottom() - (v / max_v) * chart_r.height()
            ) for i, v in enumerate(self.history)]

            fill = QtGui.QPainterPath()
            fill.moveTo(chart_r.x(), chart_r.bottom())
            fill.lineTo(pts[0])
            for i in range(len(pts) - 1):
                p0, p1 = pts[i], pts[i + 1]
                d = (p1.x() - p0.x()) * 0.3
                fill.cubicTo(p0.x() + d, p0.y(), p1.x() - d, p1.y(), p1.x(), p1.y())
            fill.lineTo(chart_r.right(), chart_r.bottom())
            fill.closeSubpath()
            grad = QtGui.QLinearGradient(0, chart_r.top(), 0, chart_r.bottom())
            g1 = QtGui.QColor(self.accent)
            g1.setAlpha(120)
            g2 = QtGui.QColor(self.accent)
            g2.setAlpha(10)
            grad.setColorAt(0.0, g1)
            grad.setColorAt(1.0, g2)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(grad)
            p.drawPath(fill)

            line = QtGui.QPainterPath()
            line.moveTo(pts[0])
            for i in range(len(pts) - 1):
                p0, p1 = pts[i], pts[i + 1]
                d = (p1.x() - p0.x()) * 0.3
                line.cubicTo(p0.x() + d, p0.y(), p1.x() - d, p1.y(), p1.x(), p1.y())
            glow = QtGui.QColor(self.accent)
            glow.setAlpha(50)
            p.setPen(QtGui.QPen(glow, 4.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawPath(line)
            p.setPen(QtGui.QPen(QtGui.QColor(self.accent), 1.5,
                    QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
            p.drawPath(line)


class VRAMMeter(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.value = None
        self.sub_text = ""
        self.setMinimumSize(95, 80)

    def set_value(self, value, sub_text=""):
        self.value = value
        self.sub_text = sub_text
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(6, 2, w - 12, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        text = str(self.value) if self.value is not None else _qtr("N/A")
        p.setPen(QtGui.QColor(self.accent))
        f = p.font()
        f.setPointSize(18 if len(text) <= 6 else 13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(4, 26, w - 8, 18), QtCore.Qt.AlignCenter, text)

        bar_y = 50
        bar_h = 10
        bar_w = int(w * 0.80)
        bar_x = (w - bar_w) // 2

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#1c1c38"))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 5, 5)

        if self.value is not None:
            try:
                v = max(0.0, min(100.0, float(self.value)))
            except (ValueError, TypeError):
                v = 0.0
            fill_w = int((bar_w - 4) * (v / 100.0))
            if fill_w > 0:
                col = self.accent if v < 85 else ("#f59e0b" if v < 95 else "#ef4444")
                p.setBrush(QtGui.QColor(col))
                p.drawRoundedRect(bar_x + 2, bar_y + 2, fill_w, bar_h - 4, 4, 4)

        if self.sub_text:
            p.setPen(QtGui.QColor("#e5e7eb"))
            f.setPointSize(9)
            f.setBold(False)
            p.setFont(f)
            p.drawText(QtCore.QRect(4, bar_y + bar_h + 4, w - 8, 16),
                       QtCore.Qt.AlignCenter, self.sub_text)


class HealthGauge(QtWidgets.QWidget):

    def __init__(self, icon: str, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.value = None
        self.setMinimumSize(130, 100)

    def set_value(self, value):
        self.value = value
        self.update()

    def _quality_info(self, v):
        if v is None:
            return ("#374151", "")
        raw = str(v).strip().replace("%", "").replace(" ", "")
        try:
            val = float(raw) if raw else None
        except (ValueError, TypeError):
            val = None
        if val is None:
            return ("#374151", "")
        if val >= 80:
            return ("#22c55e", _qtr("Excellent"))
        if val >= 60:
            return ("#eab308", _qtr("Good"))
        if val >= 40:
            return ("#f97316", _qtr("Fair"))
        return ("#ef4444", _qtr("Poor"))

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(6, 2, w - 12, 22),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        bar_h = 18
        bar_y = int(h * 0.38)
        bar_x = 10
        bar_w = max(20, w - 20)
        radius = bar_h // 2

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#1c1c38"))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, radius, radius)

        if self.value is not None:
            try:
                raw = str(self.value).strip().replace("%", "").replace(" ", "")
                v = max(0.0, min(100.0, float(raw)))
            except (ValueError, TypeError):
                v = 0.0
            fill_color, _ = self._quality_info(self.value)
            fill_w = int((bar_w - 4) * (v / 100.0))
            if fill_w > 0:
                glow = QtGui.QColor(fill_color)
                glow.setAlpha(45)
                p.setBrush(glow)
                p.drawRoundedRect(bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4,
                                  radius + 2, radius + 2)
                p.setBrush(QtGui.QColor(fill_color))
                p.drawRoundedRect(bar_x + 2, bar_y + 2, fill_w, bar_h - 4,
                                  max(2, radius - 2), max(2, radius - 2))
            text = f"{v:.0f}%"
        else:
            text = _qtr("N/A")
            fill_color = "#374151"

        p.setPen(QtGui.QColor("#ffffff"))
        f = p.font()
        f.setPointSize(15)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(0, bar_y + bar_h + 6, w, 20), QtCore.Qt.AlignCenter, text)

        if self.value is not None:
            _, label = self._quality_info(self.value)
            if label:
                p.setPen(QtGui.QColor(fill_color))
                f.setPointSize(10)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QtCore.QRect(0, bar_y + bar_h + 26, w, 16),
                           QtCore.Qt.AlignCenter, label)


class DiskBar(QtWidgets.QWidget):
    def __init__(self, icon: str, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = title
        self.accent = accent
        self.drives = []
        self.setMinimumSize(200, 80)

    def set_value(self, drives):
        self.drives = drives or []
        row_h = 14 + 14 + 6
        min_h = 28 + len(self.drives) * row_h + 10
        self.setMinimumHeight(max(80, min_h))
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QtGui.QColor("#e5e7eb"))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(8, 2, w - 16, 20),
                   (QtCore.Qt.AlignRight if _is_fa() else QtCore.Qt.AlignLeft),
                   f"{self.icon} {self.title}")

        if not self.drives:
            p.setPen(QtGui.QColor("#e5e7eb"))
            f.setPointSize(10)
            f.setBold(False)
            p.setFont(f)
            p.drawText(QtCore.QRect(8, 30, w - 16, 20),
                       QtCore.Qt.AlignLeft, _qtr("No storage info available"))
            return

        bar_y = 28
        bar_h = 14
        bar_gap = 6
        label_h = 14
        row_h = bar_h + label_h + bar_gap

        for idx, d in enumerate(self.drives):
            dname = d.get("name", "?")
            dtype = d.get("type", "?")
            dused = d.get("used", 0)
            dtotal = d.get("total", 0)
            dpct = d.get("percent", 0)

            drive_letter = dname.rstrip("\\").upper() if "\\" in dname else dname
            color = "#22c55e" if dtype == "SSD" else ("#60a5fa" if dtype == "HDD" else "#94a3b8")
            icon = "💿" if dtype == "SSD" else "💽"

            y = bar_y + idx * row_h

            label_text = f"{icon} {drive_letter}  [{dtype}]"
            p.setPen(QtGui.QColor("#e5e7eb"))
            f.setPointSize(9)
            f.setBold(True)
            p.setFont(f)
            lb = QtCore.QRect(8, y, w - 16, label_h)
            p.drawText(lb, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, label_text)

            usg = f"{dused}/{dtotal} GB  ({dpct}%)"
            p.setPen(QtGui.QColor("#ffffff"))
            f.setPointSize(9)
            f.setBold(False)
            p.setFont(f)
            p.drawText(lb, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, usg)

            bar_x = 8
            bw = w - 16
            by = y + label_h + 1
            br_track = QtCore.QRect(bar_x, by, bw, bar_h)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor("#1c1c38"))
            p.drawRoundedRect(br_track, 4, 4)

            if dtotal > 0 and dpct > 0:
                fill_w = int((bw - 4) * (dpct / 100.0))
                br_fill = QtCore.QRect(bar_x + 2, by + 2, fill_w, bar_h - 4)
                if dpct < 70:
                    fill_color = color
                elif dpct < 90:
                    fill_color = "#f59e0b"
                else:
                    fill_color = "#ef4444"
                p.setBrush(QtGui.QColor(fill_color))
                p.drawRoundedRect(br_fill, 3, 3)

class StatsWorker(QThread):
    stats_ready = pyqtSignal(dict)

    def run(self):
        try:
            data = get_all_stats()
            self.stats_ready.emit(data)
        except Exception:
            self.stats_ready.emit({})


def _app_icon_path() -> str:
    import sys
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "Data Bloom icon.svg")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Data Bloom icon.svg")


class MainWindow(QtWidgets.QWidget):

    PAGE_STATS = 0
    PAGE_HARDWARE = 1
    PAGE_MOBILE = 2
    PAGE_SCREENSHOT = 3
    PAGE_SETTINGS = 4

    def __init__(self):
        super().__init__()

        self.settings = QSettings("BloomPlay", "Settings")

        try:
            self.ip = get_local_ip()
            self.url = f"http://{self.ip}:8000/?token={state.ACCESS_TOKEN}"
        except Exception:
            self.ip = "127.0.0.1"
            self.url = f"http://127.0.0.1:8000/?token={state.ACCESS_TOKEN}"

        try:
            self.hardware = get_hardware_info()
        except Exception:
            self.hardware = {}

        self.qr_path = create_qr(self.url)

        self.cached_stats: dict = {}
        self.stats_worker: StatsWorker | None = None

        self.overlay = OverlayWidget(self.settings)
        self._register_global_hotkey()
        try:
            overlay_config.add_listener(self._on_shared_config_change)
        except Exception:
            pass

        self.setup_window()
        self._apply_theme()
        self.setup_tray()

        try:
            self.cached_stats = get_all_stats()
        except Exception:
            self.cached_stats = {}

        self.setup_ui()
        self.setup_timer()
        self._apply_startup_language()

        self.overlay.apply_enabled_state()

    def setup_window(self):
        self.setWindowTitle("BloomPlay")
        self.setWindowIcon(QtGui.QIcon(_app_icon_path()))
        self.setFixedSize(700, 420)

        self.setStyleSheet("""
            QWidget {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0e1a, stop:1 #111827
                );
                color: #ffffff;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }
            QPushButton {
                background-color: #1f2937;
                color: #ffffff;
                border: 1px solid #2a3a55;
                border-radius: 12px;
                padding: 10px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2a3a55;
                border-color: #3b5a8a;
            }
            QPushButton:pressed { background-color: #374151; }
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:vertical {
                background-color: #0f1729;
                width: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #2a3a55;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #3b5a8a; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px; border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QCheckBox { font-size: 12px; color: #ffffff; spacing: 8px; }
            QComboBox {
                background-color: #1f2937;
                border: 1px solid #2a3a55;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                color: #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #1f2937;
                color: #ffffff;
                selection-background-color: #2a3a55;
            }
            QLabel.section-title {
                font-size: 14px;
                font-weight: 700;
                color: #ffffff;
                letter-spacing: 0.5px;
            }
        """)

    DARK_STYLE = """
        QWidget {
            background-color: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #0a0e1a, stop:1 #111827
            );
            color: #ffffff;
            font-family: 'Inter', 'Segoe UI', sans-serif;
        }
        QPushButton {
            background-color: #1f2937; color: #ffffff;
            border: 1px solid #2a3a55; border-radius: 12px;
            padding: 10px; font-size: 13px; font-weight: 600;
        }
        QPushButton:hover {
            background-color: #2a3a55; border-color: #3b5a8a;
        }
        QPushButton:pressed { background-color: #374151; }
        QScrollArea { border: none; background-color: transparent; }
        QScrollBar:vertical {
            background-color: #0f1729; width: 8px;
            border-radius: 4px; margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: #2a3a55; border-radius: 4px; min-height: 30px;
        }
        QScrollBar::handle:vertical:hover { background: #3b5a8a; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px; border: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: transparent;
        }
        QCheckBox { font-size: 12px; color: #ffffff; spacing: 8px; }
        QComboBox {
            background-color: #1f2937; border: 1px solid #2a3a55;
            border-radius: 8px; padding: 6px 10px;
            font-size: 12px; color: #ffffff;
        }
        QComboBox QAbstractItemView {
            background-color: #1f2937; color: #ffffff;
            selection-background-color: #2a3a55;
        }
        QLabel.section-title {
            font-size: 14px; font-weight: 700;
            color: #ffffff; letter-spacing: 0.5px;
        }
    """

    TRANSLATIONS = {
        "CONNECTED": "متصل",
        "Connected now": "اکنون متصل",
        "📊 Stats": "📊 آمار",
        "🖥 Hardware": "🖥 سخت‌افزار",
        "📱 Mobile": "📱 موبایل",
        "📷 Screenshot": "📷 عکس برداری",
        "⚙ Settings": "⚙ تنظیمات",
        "Stats": "آمار",
        "Hardware": "سخت‌افزار",
        "Mobile": "موبایل",
        "Screenshot": "عکس برداری",
        "Settings": "تنظیمات",
        "OVERLAY": "نمایش روی صفحه",
        "APPEARANCE": "ظاهر",
        "DISPLAY FIELDS": "فیلدهای نمایش",
        "SCREENSHOT": "اسکرین شات",
        "LANGUAGE": "زبان",
        "CAPTURE": "عکس برداری",
        "GALLERY": "گالری",
        "Color": "رنگ",
        "Custom:": "سفارشی:",
        "Pick Color": "انتخاب رنگ",
        "Font Size": "اندازه فونت",
        "Font": "فونت",
        "Position": "موقعیت",
        "Save Location": "محل ذخیره",
        "Browse...": "مرور...",
        "Open": "باز کردن",
        "Shortcuts": "میانبرها",
        "Full Screen:": "تمام صفحه :",
        "Active Window:": "پنجره فعال :",
        "Shortcut:": "میانبر :",
        "Language:": "زبان :",
        "Enable On-Screen Overlay": "فعال‌سازی نمایش روی صفحه",
        "📄 Export Hardware PDF": "📄 سخت افزار PDF خروجی",
        "QR Code": "کیوآر کد",
        "Scan to open on your phone": "برای باز کردن در تلفن خود اسکن کنید",
        "Live Stats": "آمار زنده",
        "IP Address": "آدرس آی‌پی",
        "Server URL": "آدرس سرور",
        "Made with": "ساخته شده با",
        "by Data Bloom": "توسط دیتا بلوم",
        "Open Folder": "باز کردن پوشه",
        "📂 Open Folder": "📂 باز کردن پوشه",
        "Export Hardware PDF": "سخت افزار PDF خروجی",
        "CPU%": "پردازنده",
        "CPU Temp": "دمای پردازنده",
        "GPU%": "گرافیک",
        "GPU Temp": "دمای گرافیک",
        "RAM": "حافظه",
        "Download": "دانلود",
        "Upload": "آپلود",
        "Ping": "پینگ",
        "VRAM": "حافظه گرافیک",
        "FPS": "فریم بر ثانیه",
        "Battery": "باتری",
        "Health": "سلامت",
        "Storage": "فضای ذخیره",
        "CPU": "پردازنده",
        "GPU": "گرافیک",
        "MEMORY": "حافظه",
        "NETWORK": "شبکه",
        "DISPLAY": "نمایش",
        "STORAGE": "فضای ذخیره",
        "BATTERY": "باتری",
        "LIVE STATS": "آمار زنده",
        "Model :": "مدل :",
        "Total :": "کل :",
        "TOTAL": "مجموع",
        "Monitor :": "مانیتور :",
        "Resolution :": "رزولوشن :",
        "Refresh :": "نرخ تازه‌سازی :",
        "Screen :": "صفحه :",
        "Unknown": "نامشخص",
        "Microphone": "میکروفون",
        "Headphone": "هدفون",
        "Speaker": "بلندگو",
        "Device": "دستگاه",
        "No info available": "اطلاعاتی موجود نیست",
        "No disk info available": "اطلاعات دیسک موجود نیست",
        "No monitor info available": "اطلاعات مانیتور موجود نیست",
        "No audio devices found": "دستگاه صوتی یافت نشد",
        "Name": "نام",
        "Model": "مدل",
        "Manufacturer": "سازنده",
        "Cores": "هسته‌ها",
        "Threads": "رشته‌ها",
        "Base Clock": "فرکانس پایه",
        "Boost Clock": "فرکانس بوست",
        "Socket": "سوکت",
        "Architecture": "معماری",
        "Cache": "کش",
        "Memory": "حافظه",
        "Driver": "درایور",
        "Driver Version": "نسخه درایور",
        "Total": "کل",
        "Type": "نوع",
        "Speed": "سرعت",
        "Version": "نسخه",
        "Release Date": "تاریخ انتشار",
        "Serial Number": "شماره سریال",
        "Capacity": "ظرفیت",
        "Design Capacity": "ظرفیت طراحی",
        "Full Charge Capacity": "ظرفیت شارژ کامل",
        "Chemistry": "شیمی باتری",
        "Voltage": "ولتاژ",
        "Design Voltage": "ولتاژ طراحی",
        "Status": "وضعیت",
        "Family": "خانواده",
        "Frequency": "فرکانس",
        "Vram": "حافظه گرافیک",
        "Used": "مصرف شده",
        "Available": "موجود",
        "System": "سیستم",
        "Os": "سیستم عامل",
        "Bios": "بایوس",
        "Gpu": "گرافیک",
        "Ram": "حافظه",
        "Disk": "دیسک",
        "Cpu": "پردازنده",
        "Display": "نمایش",
        "Audio": "صدا",
        "Connected": "متصل",
        "Disconnected": "قطع",
        "Scan with phone camera": "با دوربین گوشی اسکن کنید",
        "QR": "کیوآر",
        "✅ Copied!": "✅ کپی شد!",
        "No screenshots yet": "هنوز عکسی گرفته نشده",
        "No screenshots folder yet.\nTake a screenshot to create it.": "پوشه عکس‌ها هنوز ساخته نشده.\nبرای ساخت آن یک عکس بگیرید.",
        "0 files": "۰ فایل",
        "files": "فایل",
        "N/A": "نامشخص",
        "Brand": "برند",
        "Vendor": "سازنده",
        "Size": "اندازه",
        "Form Factor": "فرم فاکتور",
        "Slots": "اسلات‌ها",
        "Hostname": "نام میزبان",
        "Arch": "معماری",
        "Kernel": "کرنل",
        "Board": "برد",
        "Serial": "سریال",
        "Screen Size": "اندازه صفحه",
        "Adapter": "آداپتور",
        "Primary Resolution": "رزولوشن اصلی",
        "Refresh Rate": "نرخ تازه‌سازی",
        "Monitors": "مانیتورها",
        "Primary Device": "دستگاه اصلی",
        "Devices": "دستگاه‌ها",
        "Device Id": "شناسه دستگاه",
        "L2 Cache": "کش L2",
        "L3 Cache": "کش L3",
        "Processor": "پردازنده",
        "Graphics": "گرافیک",
        "Motherboard": "مادربرد",
        "DISK": "دیسک",
        "BIOS": "بایوس",
        "OS": "سیستم عامل",
        "MONITOR": "مانیتور",
        "AUDIO": "صدا",
        "POWER": "باتری",
        "MOBILE": "موبایل",
        "STATS": "آمار",
        "SETTINGS": "تنظیمات",
        "HARDWARE": "سخت‌افزار",
        "Network": "شبکه",
        "Full Screen": "تمام صفحه",
        "🖥 Full Screen": "🖥 تمام صفحه",
        "Active Window": "پنجره فعال",
        "🪟 Active Window": "🪟 پنجره فعال",
        "Color changed to": "رنگ به",
        "Position changed to": "موقعیت به",
        "Font changed": "قلم تغییر کرد",
        "Overlay": "نمایش روی صفحه",
        "enabled": "فعال شد",
        "disabled": "غیرفعال شد",
        "Screenshot saved": "عکس ذخیره شد",
        "Screenshot saved to": "عکس در این مسیر ذخیره شد",
        "Screenshot copied to clipboard": "عکس در کلیپ‌بورد کپی شد",
        "CONNECT REMOTE": "اتصال از راه دور",
        "Open camera & scan QR code": "دوربین را باز کنید و کد QR را اسکن کنید",
        "Tap the pop-up link that appears": "روی لینک بازشده ضربه بزنید",
        "View live system stats on phone": "آمار زنده سیستم را در گوشی مشاهده کنید",
        "Click to copy": "برای کپی کلیک کنید",
        "Same Wi-Fi only — auto-discovers connected devices": "فقط با وایفای مشترک — دستگاه‌های متصل را خودکار پیدا می‌کند",
    }

    def _tr(self, text: str) -> str:
        lang = self.settings.value("language", "en", type=str)
        if lang == "fa":
            return self.TRANSLATIONS.get(text, text)
        return text

    def _apply_theme(self):
        self.setStyleSheet(self.DARK_STYLE)
    def _apply_startup_language(self):
        lang = self.settings.value("language", "en", type=str)
        if lang != "fa":
            return
        self.setLayoutDirection(QtCore.Qt.RightToLeft)
        builders = [
            (self.PAGE_STATS, self._build_stats_page),
            (self.PAGE_HARDWARE, self._build_hardware_page),
            (self.PAGE_MOBILE, self._build_mobile_page),
            (self.PAGE_SCREENSHOT, self._build_screenshot_page),
            (self.PAGE_SETTINGS, self._build_settings_page),
        ]
        cur_idx = self.stack.currentIndex()
        for page_idx, builder in builders:
            old_w = self.stack.widget(page_idx)
            new_p = builder()
            self.stack.insertWidget(page_idx, new_p)
            self.stack.removeWidget(old_w)
            old_w.deleteLater()
        self.stack.setCurrentIndex(cur_idx)
        root_layout = self.layout()
        old_nav = self.findChild(QtWidgets.QFrame, "nav_rail")
        if old_nav:
            root_layout.removeWidget(old_nav)
            old_nav.deleteLater()
        new_nav = self._build_nav_rail()
        root_layout.addWidget(new_nav)
        if hasattr(self, "lang_combo") and self.lang_combo is not None:
            idx = self.lang_combo.findData(lang)
            if idx >= 0 and self.lang_combo.currentIndex() != idx:
                self.lang_combo.setCurrentIndex(idx)

    def _on_language_changed(self, idx):
        lang = self.lang_combo.itemData(idx)
        self.settings.setValue("language", lang)
        self.settings.sync()
        self.setLayoutDirection(QtCore.Qt.RightToLeft if lang == "fa" else QtCore.Qt.LeftToRight)
        builders = [
            (self.PAGE_STATS, self._build_stats_page),
            (self.PAGE_HARDWARE, self._build_hardware_page),
            (self.PAGE_MOBILE, self._build_mobile_page),
            (self.PAGE_SCREENSHOT, self._build_screenshot_page),
            (self.PAGE_SETTINGS, self._build_settings_page),
        ]
        cur_idx = self.stack.currentIndex()
        for page_idx, builder in builders:
            old_w = self.stack.widget(page_idx)
            new_p = builder()
            self.stack.insertWidget(page_idx, new_p)
            self.stack.removeWidget(old_w)
            old_w.deleteLater()
        self.stack.setCurrentIndex(cur_idx)
        root_layout = self.layout()
        old_nav = self.findChild(QtWidgets.QFrame, "nav_rail")
        if old_nav:
            root_layout.removeWidget(old_nav)
            old_nav.deleteLater()
        new_nav = self._build_nav_rail()
        root_layout.addWidget(new_nav)


    def setup_ui(self):
        root = QtWidgets.QHBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(12, 12, 12, 12)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._build_stats_page())
        self.stack.addWidget(self._build_hardware_page())
        self.stack.addWidget(self._build_mobile_page())
        self.stack.addWidget(self._build_screenshot_page())
        self.stack.addWidget(self._build_settings_page())

        root.addWidget(self.stack, 1)
        root.addWidget(self._build_nav_rail())

        saved_lang = self.settings.value("language", "en", type=str)
        if saved_lang == "fa":
            self.setLayoutDirection(QtCore.Qt.RightToLeft)
        else:
            self.setLayoutDirection(QtCore.Qt.LeftToRight)

        self.set_page(self.PAGE_STATS)
        self._render_live_stats()
        self._render_hardware()

    def _panel_frame(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        bg = "#0f1729"
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: none;
                border-radius: 12px;
            }}""")
        return frame

    def _build_stats_section(self, icon: str, title: str, widgets: list,
                               accent: str = "#94a3b8"):
        section = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(section)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(6)

        accent_dash = QtWidgets.QFrame()
        accent_dash.setFixedWidth(20)
        accent_dash.setFixedHeight(2)
        accent_dash.setStyleSheet(f"background-color: {accent}; border-radius: 1px;")
        icon_label = QtWidgets.QLabel(icon)
        icon_label.setStyleSheet("font-size: 14px;")
        title_lbl = QtWidgets.QLabel(title.upper())
        title_lbl.setStyleSheet(f"""
            font-size: 10px; font-weight: 700; color: {accent};
            letter-spacing: 1px;
        """)

        trail_line = QtWidgets.QFrame()
        trail_line.setFixedHeight(1)
        trail_line.setStyleSheet(f"background-color: {accent}; border: none;")
        trail_line.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        header.addWidget(accent_dash)
        header.addWidget(icon_label)
        header.addWidget(title_lbl)
        header.addWidget(trail_line)

        outer.addLayout(header)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        for w in widgets:
            row.addWidget(self._wrap_stat_card(w), 1)
        outer.addLayout(row)

        return section        
    def _wrap_stat_card(self, widget: QtWidgets.QWidget) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        bg = "#0f1729"
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: none;
                border-radius: 8px;
            }}
        """)
        outer = QtWidgets.QVBoxLayout(card)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(widget)
        return card

    def _build_stats_page(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        page = QtWidgets.QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 10, 2)
        layout.setSpacing(14)

        self.cpu_gauge = HealthArc("🖥", self._tr("CPU%"), "#60a5fa", unit="%")
        self.cpu_temp_gauge = HeatPipe("🌡", self._tr("CPU Temp"), "#60a5fa")
        self.gpu_gauge = HealthArc("🎮", self._tr("GPU%"), "#a78bfa", unit="%")
        self.gpu_temp_gauge = HeatPipe("🌡", self._tr("GPU Temp"), "#a78bfa")
        self.ram_gauge = BlockMeter("🧠", self._tr("RAM"), "#f472b6")
        self.download_wave = WaveDash("⬇", self._tr("Download"), "#22d3ee")
        self.upload_wave = WaveDash("⬆", self._tr("Upload"), "#22d3ee")
        self.ping_gauge = PingGauge("📶", self._tr("Ping"), "#22d3ee")
        self.vram_meter = VRAMMeter("💾", self._tr("VRAM"), "#a78bfa")
        self.fps_bar = FPSBar("🎯", self._tr("FPS"), "#a78bfa")
        self.battery_gauge = BatteryIcon("🔋", self._tr("Battery"), "#fb923c")
        self.battery_health_gauge = HealthGauge("💚", self._tr("Health"), "#fb923c")
        self.disk_bar = DiskBar("💾", self._tr("Storage"), "#fbbf24")

        layout.addWidget(self._build_stats_section(
            "🖥", "Processor",
            [self.cpu_gauge, self.cpu_temp_gauge],
            accent="#60a5fa",
        ))
        layout.addWidget(self._build_stats_grid_section(
            "🎮", "Graphics",
            [(self.gpu_gauge, 0, 0), (self.gpu_temp_gauge, 0, 1),
             (self.vram_meter, 1, 0), (self.fps_bar, 1, 1)],
            accent="#a78bfa",
        ))
        layout.addWidget(self._build_stats_section(
            "🧠", "Memory",
            [self.ram_gauge],
            accent="#f472b6",
        ))
        layout.addWidget(self._build_stats_section(
            "🌐", "Network",
            [self.download_wave, self.upload_wave, self.ping_gauge],
            accent="#22d3ee",
        ))
        layout.addWidget(self._build_stats_section(
            "🔋", "Power",
            [self.battery_gauge, self.battery_health_gauge],
            accent="#fb923c",
        ))
        layout.addWidget(self._build_stats_section(
            "💾", "Storage",
            [self.disk_bar],
            accent="#fbbf24",
        ))

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _build_stats_grid_section(self, icon: str, title: str,
                               grid_items: list,
                               accent: str = "#94a3b8"):
        section = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(section)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(6)

        accent_dash = QtWidgets.QFrame()
        accent_dash.setFixedWidth(20)
        accent_dash.setFixedHeight(2)
        accent_dash.setStyleSheet(f"background-color: {accent}; border-radius: 1px;")
        icon_label = QtWidgets.QLabel(icon)
        icon_label.setStyleSheet("font-size: 14px;")
        title_lbl = QtWidgets.QLabel(title.upper())
        title_lbl.setStyleSheet(f"""
            font-size: 10px; font-weight: 700; color: {accent};
            letter-spacing: 1px;
        """)

        trail_line = QtWidgets.QFrame()
        trail_line.setFixedHeight(1)
        trail_line.setStyleSheet(f"background-color: {accent}; border: none;")
        trail_line.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        header.addWidget(accent_dash)
        header.addWidget(icon_label)
        header.addWidget(title_lbl)
        header.addWidget(trail_line)

        outer.addLayout(header)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(8)
        for widget, row, col in grid_items:
            grid.addWidget(self._wrap_stat_card(widget), row, col)
        outer.addLayout(grid)
        return section

    def _build_hw_card(self, icon: str, title: str, accent: str, tag: str) -> tuple:
        card = QtWidgets.QFrame()
        if self.settings.value("language", "en", type=str) == "fa":
            card.setLayoutDirection(QtCore.Qt.RightToLeft)
        else:
            card.setLayoutDirection(QtCore.Qt.LeftToRight)
        bg = "#0f1729"
        card.setStyleSheet(f"""
            QFrame#hwCard {{
                background-color: {bg};
                border: none;
                border-radius: 14px;
            }}
        """)
        card.setObjectName("hwCard")
        outer = QtWidgets.QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent_bar = QtWidgets.QFrame()
        accent_bar.setFixedHeight(4)
        accent_bar.setStyleSheet(f"""
            background-color: {accent};
            border-top-left-radius: 14px;
            border-top-right-radius: 14px;
        """)
        outer.addWidget(accent_bar)

        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(8)
        outer.addWidget(body)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        icon_badge = QtWidgets.QLabel(icon)
        icon_badge.setFixedSize(32, 32)
        icon_badge.setAlignment(QtCore.Qt.AlignCenter)
        icon_badge.setStyleSheet(f"""
            background-color: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 9px;
            font-size: 15px;
        """)
        title_label = QtWidgets.QLabel(self._tr(title))
        title_label.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {accent};")
        title_label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        if self.settings.value("language", "en", type=str) == "fa":
            title_label.setLayoutDirection(QtCore.Qt.LeftToRight)
            title_label.setAlignment(QtCore.Qt.AlignRight)
        else:
            title_label.setAlignment(QtCore.Qt.AlignLeft)
        tag_label = QtWidgets.QLabel(tag)
        tag_label.setFixedHeight(18)
        tag_label.setStyleSheet(f"""
            font-size: 9px; font-weight: 700; color: {accent};
            background: rgba(255,255,255,0.05); border-radius: 999px;
            padding: 2px 8px;
        """)
        header.addWidget(icon_badge, 0)
        header.addWidget(title_label, 0)
        header.addStretch(1)
        header.addWidget(tag_label, 0)
        layout.addLayout(header)

        content = QtWidgets.QLabel()
        content.setTextFormat(QtCore.Qt.RichText)
        content.setWordWrap(True)
        if self.settings.value("language", "en", type=str) == "fa":
            content.setLayoutDirection(QtCore.Qt.RightToLeft)
            content.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)
        else:
            content.setLayoutDirection(QtCore.Qt.LeftToRight)
            content.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        content.setStyleSheet("font-size: 12px; line-height: 1.5;")
        layout.addWidget(content)

        return card, content

    def _build_hardware_page(self):
        page = QtWidgets.QWidget()
        if self.settings.value("language", "en", type=str) == "fa":
            page.setLayoutDirection(QtCore.Qt.RightToLeft)
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
        """)

        inner = QtWidgets.QWidget()
        inner.setStyleSheet("background: transparent;")
        grid = QtWidgets.QGridLayout(inner)
        grid.setSpacing(10)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        specs = [
            ("cpu", "🖥", self._tr("Processor"), "#60a5fa", "CPU"),
            ("gpu", "🎮", self._tr("Graphics"), "#a78bfa", "GPU"),
            ("ram", "🧠", self._tr("Memory"), "#f472b6", "RAM"),
            ("disk", "💾", self._tr("Storage"), "#fbbf24", "DISK"),
            ("bios", "🔧", self._tr("Motherboard"), "#fb923c", "BIOS"),
            ("system", "🪟", self._tr("System"), "#22d3ee", "OS"),
            ("display", "🖥️", self._tr("Display"), "#34d399", "MONITOR"),
            ("audio", "🎧", self._tr("Audio"), "#14b8a6", "AUDIO"),
            ("battery", "🔋", self._tr("Battery"), "#84cc16", "POWER"),
        ]
        self.hw_cards = {}
        self.hw_accents = {}
        for i, (key, icon, title, accent, tag) in enumerate(specs):
            card, content = self._build_hw_card(icon, title, accent, tag)
            self.hw_cards[key] = content
            self.hw_accents[key] = accent
            grid.addWidget(card, i // 2, i % 2)

        grid.setRowStretch(len(specs) // 2 + 1, 1)
        scroll_area.setWidget(inner)
        page_layout.addWidget(scroll_area, 1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)

        export_btn = QtWidgets.QPushButton(self._tr("Export Hardware PDF"))
        export_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        export_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 12px; font-weight: 600; color: '#e5e7eb';
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(34,211,238,0.1), stop:1 rgba(168,85,247,0.1));
                border: 1px solid rgba(34,211,238,0.25);
                border-radius: 10px; padding: 8px 16px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(34,211,238,0.2), stop:1 rgba(168,85,247,0.2));
                border-color: rgba(34,211,238,0.45);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(34,211,238,0.3), stop:1 rgba(168,85,247,0.3));
            }}
        """)
        export_btn.clicked.connect(self._export_hardware_pdf)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        page_layout.addLayout(btn_row)

        return page

    def _hw_report_sections(self) -> list:
        try:
            stats_bat = (self.cached_stats or {}).get("battery", {}) or {}
        except Exception:
            stats_bat = {}
        return build_pdf_sections(self.hardware or {}, battery_stats=stats_bat)

    def _export_hardware_pdf(self):
        try:
            import socket
            computer_name = socket.gethostname()
        except Exception:
            computer_name = "MyPC"
        default_name = f"{computer_name}_Hardware.pdf"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Hardware Report", default_name, "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"


        def _esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        sections_html = []
        for label, accent, rows in self._hw_report_sections():
            rows_html = ""
            for lab, val in rows:
                if not lab:
                    rows_html += (
                        '<tr><td colspan="2" bgcolor="#f3f4f6" '
                        f'style="color:#374151;">{_esc(val)}</td></tr>'
                    )
                else:
                    rows_html += (
                        '<tr>'
                        f'<td width="42%" bgcolor="#f3f4f6" style="color:{accent}; font-weight:bold;">'
                        f'{_esc(lab)}</td>'
                        f'<td bgcolor="#ffffff" style="color:#111827;">{_esc(val)}</td>'
                        '</tr>'
                    )
            sections_html.append(
                '<table width="100%" cellspacing="0" cellpadding="8" border="1" '
                f'style="border-color:#e5e7eb; background-color:#ffffff; margin-top:14px;">'
                f'<tr><td colspan="2" bgcolor="{accent}" style="color:#111827; '
                f'font-size:13pt; font-weight:bold;">{_esc(label.upper())}</td></tr>{rows_html}</table>'
            )

        host = "PC"
        try:
            host = (self.hardware or {}).get("system", {}).get("hostname", "PC")
        except Exception:
            pass
        date_str = time.strftime("%Y-%m-%d %H:%M")

        doc_html = f"""
        <html>
        <body style="font-family:'Segoe UI', Arial, sans-serif; background-color:#ffffff; color:#1f2937; margin:0;">
        <table width="100%" cellspacing="0" cellpadding="22" style="background-color:#ffffff;">
        <tr><td>
          <div style="color:#7c3aed; font-size:10pt; font-weight:bold;">BLOOMPLAY</div>
          <div style="color:#111827; font-size:24pt; font-weight:bold; margin-top:2px;">Hardware Report</div>
          <div style="color:#6b7280; font-size:10pt; margin-top:4px;">Host: {host} &nbsp;·&nbsp; Generated {date_str}</div>
          <div style="border-top:3px solid #a78bfa; margin-top:10px;"></div>
          {"".join(sections_html)}
          <div style="margin-top:22px; color:#9ca3af; font-size:8pt; text-align:center;">
            <a href="https://linktr.ee/Data_Bloom" style="color:#7c3aed; text-decoration:none;">BloomPlay</a> · Hardware Report
          </div>
        </td></tr>
        </table>
        </body>
        </html>
        """

        document = QtGui.QTextDocument()
        document.setHtml(doc_html)

        printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.HighResolution)
        printer.setOutputFormat(QtPrintSupport.QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        document.print_(printer)

        QtWidgets.QMessageBox.information(self, "Export complete", f"Saved to:\n{path}")

    def _build_mobile_page(self):
        page = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        qr_card = QtWidgets.QFrame()
        qr_card.setStyleSheet("""
            QFrame {
                background-color: #0f1729;
                border: 1px solid #1e293b;
                border-radius: 14px;
            }
        """)
        qr_layout = QtWidgets.QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(14, 12, 14, 12)
        qr_layout.setAlignment(QtCore.Qt.AlignCenter)
        qr_layout.setSpacing(6)

        status_row = QtWidgets.QHBoxLayout()
        status_row.setSpacing(5)
        status_row.setAlignment(QtCore.Qt.AlignCenter)
        self._qr_status_dot = QtWidgets.QFrame()
        self._qr_status_dot.setFixedSize(8, 8)
        self._qr_status_dot.setStyleSheet("background-color: #f87171; border-radius: 4px;")
        status_row.addWidget(self._qr_status_dot)
        self.phone_status = QtWidgets.QLabel(self._tr("Disconnected"))
        self.phone_status.setStyleSheet("font-size: 12px; font-weight: 700; color: #f87171;")
        status_row.addWidget(self.phone_status)
        qr_layout.addLayout(status_row)

        qr_label = QtWidgets.QLabel()
        qr_label.setAlignment(QtCore.Qt.AlignCenter)
        if self.qr_path:
            pix = QtGui.QPixmap(self.qr_path)
            qr_sz = min(140, pix.width(), pix.height())
            pix = pix.scaled(qr_sz, qr_sz, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            qr_label.setPixmap(pix)
            qr_label.setFixedSize(qr_sz + 10, qr_sz + 10)
            qr_label.setStyleSheet("background: #ffffff; border-radius: 8px; padding: 5px;")
        else:
            qr_label.setText(self._tr("QR") + "\n" + self._tr("N/A"))
            qr_label.setStyleSheet("color: #e5e7eb; font-size: 12px;")
        qr_layout.addWidget(qr_label, 0, QtCore.Qt.AlignCenter)

        scan_label = QtWidgets.QLabel(self._tr("Scan with phone camera"))
        scan_label.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 500;")
        scan_label.setAlignment(QtCore.Qt.AlignCenter)
        qr_layout.addWidget(scan_label)

        right_card = QtWidgets.QFrame()
        right_card.setStyleSheet("""
            QFrame {
                background-color: #0f1729;
                border: 1px solid #1e293b;
                border-radius: 14px;
            }
        """)
        right_layout = QtWidgets.QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(8)

        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(8)
        ab = QtWidgets.QFrame()
        ab.setFixedWidth(3); ab.setFixedHeight(16)
        ab.setStyleSheet("background: #22d3ee; border-radius: 2px;")
        title_row.addWidget(ab)
        tl = QtWidgets.QLabel(self._tr("CONNECT REMOTE"))
        tl.setStyleSheet("font-size: 14px; font-weight: 800; color: #22d3ee; letter-spacing: 1px;")
        title_row.addWidget(tl)
        title_row.addStretch()
        right_layout.addLayout(title_row)

        steps = [
            ("1", "#22d3ee", self._tr("Open camera & scan QR code")),
            ("2", "#34d399", self._tr("Tap the pop-up link that appears")),
            ("3", "#60a5fa", self._tr("View live system stats on phone")),
        ]
        for num, color, text in steps:
            sr = QtWidgets.QHBoxLayout()
            sr.setSpacing(8)
            badge = QtWidgets.QLabel(num)
            badge.setFixedSize(22, 22)
            badge.setAlignment(QtCore.Qt.AlignCenter)
            badge.setStyleSheet(f"""
                background: rgba(255,255,255,0.06);
                border: 1px solid {color};
                color: {color};
                border-radius: 11px;
                font-size: 10px;
                font-weight: 700;
            """)
            st = QtWidgets.QLabel(text)
            st.setWordWrap(True)
            st.setStyleSheet("font-size: 12px; color: #e5e7eb; font-weight: 500;")
            sr.addWidget(badge, 0)
            sr.addWidget(st, 1)
            right_layout.addLayout(sr)

        sep = QtWidgets.QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #1e293b;")
        right_layout.addWidget(sep)

        net_label = QtWidgets.QLabel(self._tr("NETWORK"))
        net_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #ffffff; letter-spacing: 1px;")
        right_layout.addWidget(net_label)

        self.ip_label = QtWidgets.QLabel(self.url)
        self.ip_label.setWordWrap(True)
        self.ip_label.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.ip_label.setToolTip(self._tr("Click to copy"))
        self.ip_label.setStyleSheet("""
            color: #93c5fd; font-size: 14px; font-weight: 700;
            background: rgba(96,165,250,0.08);
            border: 1px solid rgba(96,165,250,0.25);
            border-radius: 6px; padding: 6px 10px;
        """)
        self.ip_label.mousePressEvent = self.copy_ip_to_clipboard
        right_layout.addWidget(self.ip_label)

        dev_hdr = QtWidgets.QHBoxLayout()
        dev_hdr.setSpacing(6)
        self.device_count_label = QtWidgets.QLabel(self._tr("CONNECTED"))
        self.device_count_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #34d399; letter-spacing: 1px;")
        dev_hdr.addWidget(self.device_count_label)
        self.device_badge = QtWidgets.QLabel("0")
        self.device_badge.setFixedSize(20, 20)
        self.device_badge.setAlignment(QtCore.Qt.AlignCenter)
        self.device_badge.setStyleSheet("""
            background: rgba(52, 211, 153, 0.15);
            color: #34d399;
            border: 1px solid rgba(52, 211, 153, 0.3);
            border-radius: 10px;
            font-size: 9px;
            font-weight: 800;
        """)
        dev_hdr.addWidget(self.device_badge)
        dev_hdr.addStretch()
        right_layout.addLayout(dev_hdr)

        self.device_list_widget = QtWidgets.QWidget()
        self.device_list_layout = QtWidgets.QVBoxLayout(self.device_list_widget)
        self.device_list_layout.setContentsMargins(0, 0, 0, 0)
        self.device_list_layout.setSpacing(3)

        ds = QtWidgets.QScrollArea()
        ds.setWidgetResizable(True)
        ds.setFixedHeight(90)
        ds.setStyleSheet("QScrollArea { border: none; background: transparent; }"
                         "QScrollBar:vertical { width: 4px; background: transparent; }"
                         "QScrollBar::handle:vertical { background: #2a3a55; border-radius: 2px; }")
        ds.setWidget(self.device_list_widget)
        right_layout.addWidget(ds)

        hint = QtWidgets.QLabel(self._tr("Same Wi-Fi only — auto-discovers connected devices"))
        hint.setStyleSheet("color: #ffffff; font-size: 9px; font-weight: 500;")
        right_layout.addWidget(hint)

        row.addWidget(qr_card, 0)
        row.addWidget(right_card, 1)

        try:
            from api import state as _api_state
            QtCore.QTimer.singleShot(
                150, lambda d=_api_state.get_connected_devices():
                    self._refresh_device_list(d) if hasattr(self, '_refresh_device_list') else None
            )
            self._devices_timer = QtCore.QTimer()
            self._devices_timer.timeout.connect(lambda: (
                self._refresh_device_list(
                    _api_state.get_connected_devices()
                ) if hasattr(self, '_refresh_device_list') else None
            ))
            self._devices_timer.start(2000)
        except Exception:
            pass

        return page

    def _build_screenshot_page(self):
        page = QtWidgets.QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 10, 4)
        layout.setSpacing(14)

        capture_section = self._sett_panel()
        capture_layout = QtWidgets.QVBoxLayout(capture_section)
        capture_layout.setContentsMargins(14, 12, 14, 12)
        capture_layout.setSpacing(10)

        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(8)
        ab = QtWidgets.QFrame()
        ab.setFixedWidth(3); ab.setFixedHeight(18)
        ab.setStyleSheet("background: #fb923c; border-radius: 2px;")
        hdr.addWidget(ab)
        hdr_lbl = QtWidgets.QLabel(self._tr("CAPTURE"))
        hdr_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;")
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        capture_layout.addLayout(hdr)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(12)

        self.ss_full_btn = QtWidgets.QPushButton(self._tr("🖥 Full Screen"))
        self.ss_full_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.ss_full_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px; font-weight: 600; color: #e5e7eb;
                background: rgba(251,146,60,0.12);
                border: 1px solid rgba(251,146,60,0.3);
                border-radius: 10px;
                padding: 10px 20px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: rgba(251,146,60,0.22);
                border-color: rgba(251,146,60,0.5);
            }
            QPushButton:pressed {
                background: rgba(251,146,60,0.35);
            }
        """)
        self.ss_full_btn.clicked.connect(self._ss_capture_full)
        btn_row.addWidget(self.ss_full_btn)

        self.ss_win_btn = QtWidgets.QPushButton(self._tr("🪟 Active Window"))
        self.ss_win_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.ss_win_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px; font-weight: 600; color: #e5e7eb;
                background: rgba(52,211,153,0.12);
                border: 1px solid rgba(52,211,153,0.3);
                border-radius: 10px;
                padding: 10px 20px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: rgba(52,211,153,0.22);
                border-color: rgba(52,211,153,0.5);
            }
            QPushButton:pressed {
                background: rgba(52,211,153,0.35);
            }
        """)
        self.ss_win_btn.clicked.connect(self._ss_capture_window)
        btn_row.addWidget(self.ss_win_btn)

        btn_row.addStretch()
        capture_layout.addLayout(btn_row)

        self.ss_status = QtWidgets.QLabel("")
        self.ss_status.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 600;")
        self.ss_status.setAlignment(QtCore.Qt.AlignCenter)
        capture_layout.addWidget(self.ss_status)

        gallery_section = self._sett_panel()
        gallery_layout = QtWidgets.QVBoxLayout(gallery_section)
        gallery_layout.setContentsMargins(14, 12, 14, 12)
        gallery_layout.setSpacing(8)

        hdr3 = QtWidgets.QHBoxLayout()
        hdr3.setSpacing(8)
        ab3 = QtWidgets.QFrame()
        ab3.setFixedWidth(3); ab3.setFixedHeight(18)
        ab3.setStyleSheet("background: #a78bfa; border-radius: 2px;")
        hdr3.addWidget(ab3)
        hdr3_lbl = QtWidgets.QLabel(self._tr("GALLERY"))
        hdr3_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;")
        hdr3.addWidget(hdr3_lbl)

        self.ss_gallery_refresh_btn = QtWidgets.QPushButton("🔄")
        self.ss_gallery_refresh_btn.setFixedSize(28, 28)
        self.ss_gallery_refresh_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.ss_gallery_refresh_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                background: transparent;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 14px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
            }
        """)
        self.ss_gallery_refresh_btn.clicked.connect(self._ss_refresh_gallery)
        hdr3.addWidget(self.ss_gallery_refresh_btn)

        self.ss_open_gallery_btn = QtWidgets.QPushButton(self._tr("📂 Open Folder"))
        self.ss_open_gallery_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.ss_open_gallery_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 600; color: #e5e7eb;
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
            }
        """)
        self.ss_open_gallery_btn.clicked.connect(self._ss_open_gallery_folder)
        hdr3.addWidget(self.ss_open_gallery_btn)

        hdr3.addStretch()

        self.ss_gallery_count = QtWidgets.QLabel("")
        self.ss_gallery_count.setStyleSheet("color:#e5e7eb;font-size:11px;font-weight:600;")
        hdr3.addWidget(self.ss_gallery_count)
        gallery_layout.addLayout(hdr3)

        self.ss_gallery_scroll = QtWidgets.QScrollArea()
        self.ss_gallery_scroll.setWidgetResizable(True)
        self.ss_gallery_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.ss_gallery_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.ss_gallery_scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.ss_gallery_scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 8px;
                background: rgba(0,0,0,0.2);
            }
            QScrollBar:vertical {
                background: #0f1729;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #2a3a55;
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b5a8a;
            }
        """)
        self.ss_gallery_container = QtWidgets.QWidget()
        self.ss_gallery_container.setStyleSheet("background: transparent;")
        self.ss_gallery_grid = QtWidgets.QVBoxLayout(self.ss_gallery_container)
        self.ss_gallery_grid.setSpacing(8)
        self.ss_gallery_grid.setContentsMargins(8, 8, 8, 8)
        self.ss_gallery_scroll.setWidget(self.ss_gallery_container)
        self.ss_gallery_scroll.setMaximumHeight(200)
        gallery_layout.addWidget(self.ss_gallery_scroll)

        layout.addWidget(capture_section)
        layout.addWidget(gallery_section)

        QtCore.QTimer.singleShot(200, self._ss_refresh_gallery)
        return page

        while self.ss_gallery_grid.count():
            item = self.ss_gallery_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not os.path.exists(folder):
            lbl = QtWidgets.QLabel(self._tr("No screenshots folder yet.\nTake a screenshot to create it."))
            lbl.setStyleSheet("color: #e5e7eb; font-size: 12px; padding: 30px;")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            self.ss_gallery_grid.addWidget(lbl)
            self.ss_gallery_count.setText(self._tr("0 files"))
            return
        
        files = []
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.bmp"]:
            files.extend(glob.glob(os.path.join(folder, ext)))
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        
        if not files:
            lbl = QtWidgets.QLabel(self._tr("No screenshots yet"))
            lbl.setStyleSheet("color: #e5e7eb; font-size: 12px; padding: 30px;")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            self.ss_gallery_grid.addWidget(lbl)
            self.ss_gallery_count.setText(self._tr("0 files"))
            return
        
        self.ss_gallery_count.setText(f"{len(files)} {self._tr('files')}")
        
        cols = 2
        for idx, fpath in enumerate(files[:60]):
            try:
                pix = QtGui.QPixmap(fpath)
                if pix.isNull() or pix.width() < 10:
                    continue
                
                frame = QtWidgets.QFrame()
                frame.setStyleSheet("""
                    QFrame {
                        background: rgba(255,255,255,0.03);
                        border: 1px solid rgba(255,255,255,0.06);
                        border-radius: 8px;
                    }
                    QFrame:hover {
                        background: rgba(255,255,255,0.08);
                        border-color: rgba(255,255,255,0.15);
                    }
                """)
                frame.setFixedHeight(150)
                
                frame.mouseDoubleClickEvent = lambda e, p=fpath: self._ss_open_file(p)
                
                row_layout = QtWidgets.QHBoxLayout(frame)
                row_layout.setContentsMargins(6, 4, 6, 4)
                row_layout.setSpacing(8)
                
                thumb = pix.scaled(90, 70, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                thumb_lbl = QtWidgets.QLabel()
                thumb_lbl.setPixmap(thumb)
                thumb_lbl.setFixedSize(90, 70)
                thumb_lbl.setStyleSheet("border-radius: 4px; background: rgba(0,0,0,0.2);")
                row_layout.addWidget(thumb_lbl)
                
                info_col = QtWidgets.QVBoxLayout()
                info_col.setSpacing(2)
                
                fname = os.path.basename(fpath)
                name_lbl = QtWidgets.QLabel(fname[:20] + ("..." if len(fname) > 20 else ""))
                name_lbl.setStyleSheet("color: #e5e7eb; font-size: 10px; font-weight: 600;")
                info_col.addWidget(name_lbl)
                
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                time_lbl = QtWidgets.QLabel(mtime.strftime("%Y-%m-%d %H:%M"))
                time_lbl.setStyleSheet("color: #e5e7eb; font-size: 8px;")
                info_col.addWidget(time_lbl)
                
                info_col.addStretch()
                row_layout.addLayout(info_col, 1)
                
                row, col = divmod(idx, cols)
                self.ss_gallery_grid.addWidget(frame, row, col)
                
            except Exception:
                continue
        
        if self.ss_gallery_grid.count() == 0:
            lbl = QtWidgets.QLabel("No valid screenshots found")
            lbl.setStyleSheet("color: #e5e7eb; font-size: 12px; padding: 30px;")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            self.ss_gallery_grid.addWidget(lbl, 0, 0, 1, 4)

    def _ss_save_pixmap(self, pix):
        try:
            import datetime
            folder = self.settings.value("screenshot_path", "", type=str)
            if not folder:
                folder = os.path.join(os.path.expanduser("~"), "Pictures", "BloomPlay")
            os.makedirs(folder, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            fpath = os.path.join(folder, f"Screenshot_{ts}.png")
            if pix.save(fpath, "PNG"):
                self._ss_show_status(f"Saved: {fpath}")
                QtCore.QTimer.singleShot(150, self._ss_refresh_gallery)
            else:
                self._ss_show_status("Save failed")
        except Exception:
            self._ss_show_status("Save failed")

    def _ss_show_status(self, msg: str):
        self.ss_status.setText(msg)
        QtCore.QTimer.singleShot(
            3000, lambda: self.ss_status.setText("")
            if self.ss_status.text() == msg else None)

    def _ss_browse_path(self):
        current = self.settings.value("screenshot_path", "", type=str)
        if not current:
            current = os.path.join(os.path.expanduser("~"), "Pictures", "BloomPlay")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose Screenshot Folder", current)
        if folder:
            self.settings.setValue("screenshot_path", folder)
            if hasattr(self, "ss_path_edit_sett"):
                self.ss_path_edit_sett.setText(folder)
            if hasattr(self, "ss_path_edit"):
                self.ss_path_edit.setText(folder)
            self._ss_show_status("Save path: " + folder)

    def _ss_capture_full(self):
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen is None:
                self._ss_show_status("No screen available")
                return
            pix = screen.grabWindow(0)
            self._ss_save_pixmap(pix)
        except Exception:
            self._ss_show_status("Capture failed")

    def _ss_capture_window(self):
        try:
            win = QtWidgets.QApplication.activeWindow()
            if win is None:
                self._ss_show_status("No active window")
                return
            pix = win.grab()
            self._ss_save_pixmap(pix)
        except Exception:
            self._ss_show_status("Capture failed")

    def _ss_on_full_hotkey_changed(self):
        try:
            for attr in ("ss_full_hotkey_edit", "ss_hotkey_edit", "ss_full_hk"):
                edit = getattr(self, attr, None)
                if edit is not None:
                    key_str = edit.keySequence().toString()
                    if not key_str:
                        return
                    self.settings.setValue("screenshot_full_hotkey", key_str)
                    self._ss_show_status("Shortcut: " + key_str)
                    self._register_global_hotkey()
                    break
        except Exception:
            pass

    def _ss_on_win_hotkey_changed(self):
        try:
            for attr in ("ss_win_hotkey_edit", "ss_hotkey_edit", "ss_win_hk"):
                edit = getattr(self, attr, None)
                if edit is not None:
                    key_str = edit.keySequence().toString()
                    if not key_str:
                        return
                    self.settings.setValue("screenshot_win_hotkey", key_str)
                    self._ss_show_status("Shortcut: " + key_str)
                    self._register_global_hotkey()
                    break
        except Exception:
            pass

    def _ss_open_file(self, path):
        try:
            os.startfile(path)
        except Exception:
            self._ss_show_status("Cannot open")

    def _ss_open_gallery_folder(self):
        folder = self.settings.value("screenshot_path", "", type=str)
        if not folder:
            folder = os.path.join(os.path.expanduser("~"), "Pictures", "BloomPlay")
        if not os.path.exists(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception:
                self._ss_show_status("Cannot create folder")
                return
        try:
            os.startfile(folder)
        except Exception:
            self._ss_show_status("Cannot open folder")

    def _ss_open_save_folder(self):
        folder = self.settings.value("screenshot_path", "", type=str)
        if not folder:
            folder = os.path.join(os.path.expanduser("~"), "Pictures", "BloomPlay")
        if not os.path.exists(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception:
                self._ss_show_status("Cannot create folder")
                return
        try:
            os.startfile(folder)
        except Exception:
            self._ss_show_status("Cannot open folder")

    def _ss_refresh_gallery(self):
        import glob
        import datetime
        folder = self.settings.value("screenshot_path", "", type=str)
        if not folder:
            folder = os.path.join(os.path.expanduser("~"), "Pictures", "BloomPlay")
        if not os.path.exists(folder):
            if hasattr(self, "ss_gallery_count"):
                self.ss_gallery_count.setText("Folder not found")
            return

        while self.ss_gallery_grid.count():
            item = self.ss_gallery_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        files = []
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.bmp"]:
            files.extend(glob.glob(os.path.join(folder, ext)))
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        if not files:
            lbl = QtWidgets.QLabel(
                "No screenshots yet\nPress Full Screen or Active Window to capture")
            lbl.setStyleSheet("color: #e5e7eb; font-size: 12px; padding: 20px;")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            self.ss_gallery_grid.addWidget(lbl)
            if hasattr(self, "ss_gallery_count"):
                self.ss_gallery_count.setText("0 files")
            return

        total = len(files)
        files = files[:20]
        if hasattr(self, "ss_gallery_count"):
            self.ss_gallery_count.setText(f"{total} {self._tr('files')}")

        for fpath in files:
            try:
                pix = QtGui.QPixmap(fpath)
                if pix.isNull():
                    continue
                thumb = pix.scaled(120, 80, QtCore.Qt.KeepAspectRatio,
                                   QtCore.Qt.SmoothTransformation)
                frame = QtWidgets.QFrame()
                frame.setStyleSheet(
                    "QFrame { background: rgba(255,255,255,0.03);"
                    " border: 1px solid rgba(255,255,255,0.06);"
                    " border-radius: 6px; }")
                row2 = QtWidgets.QHBoxLayout(frame)
                row2.setContentsMargins(6, 4, 6, 4)
                row2.setSpacing(10)
                thumb_lbl = QtWidgets.QLabel()
                thumb_lbl.setPixmap(thumb)
                row2.addWidget(thumb_lbl)
                info_col = QtWidgets.QVBoxLayout()
                info_col.setSpacing(2)
                fname = os.path.basename(fpath)
                name_lbl = QtWidgets.QLabel(
                    fname[:30] + ("..." if len(fname) > 30 else ""))
                name_lbl.setStyleSheet(
                    "color: #e5e7eb; font-size: 11px; font-weight: 600;")
                info_col.addWidget(name_lbl)
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                time_lbl = QtWidgets.QLabel(mtime.strftime("%Y-%m-%d %H:%M"))
                time_lbl.setStyleSheet("color: #e5e7eb; font-size: 9px;")
                info_col.addWidget(time_lbl)
                info_col.addStretch()
                row2.addLayout(info_col, 1)
                view_btn = QtWidgets.QPushButton("\U0001f441 Open")
                view_btn.setFixedSize(60, 24)
                view_btn.setStyleSheet(
                    "QPushButton { font-size: 10px; font-weight: 600;"
                    " color: #a78bfa; background: rgba(167,139,250,0.1);"
                    " border: 1px solid rgba(167,139,250,0.2);"
                    " border-radius: 4px; padding: 2px 6px; }")
                view_btn.clicked.connect(
                    lambda checked, p=fpath: self._ss_open_file(p))
                row2.addWidget(view_btn)
                self.ss_gallery_grid.addWidget(frame)
            except Exception:
                continue

    def _build_settings_page(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        page = QtWidgets.QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 10, 4)
        layout.setSpacing(14)

        toggle_section = self._sett_panel()
        toggle_layout = QtWidgets.QVBoxLayout(toggle_section)
        toggle_layout.setContentsMargins(14, 12, 14, 12)
        toggle_layout.setSpacing(10)

        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(8)
        ab = QtWidgets.QFrame()
        ab.setFixedWidth(3); ab.setFixedHeight(18)
        ab.setStyleSheet("background: #22d3ee; border-radius: 2px;")
        hdr.addWidget(ab)
        hdr_lbl = QtWidgets.QLabel(self._tr("OVERLAY"))
        hdr_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;")
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        toggle_layout.addLayout(hdr)

        self.overlay_enabled = QtWidgets.QCheckBox(self._tr("Enable On-Screen Overlay"))
        self.overlay_enabled.setStyleSheet("""
            QCheckBox {
                font-size: 13px; font-weight: 400; color: #e5e7eb; spacing: 10px;
            }
            QCheckBox::indicator {
                width: 44px; height: 22px; border-radius: 11px;
                background: #374151; border: none;
            }
            QCheckBox::indicator:checked {
                background: #22d3ee;
            }
            QCheckBox::indicator:hover {
                background: #4a5a7a;
            }
            QCheckBox::indicator:checked:hover {
                background: #2dd4bf;
            }
        """)
        self.overlay_enabled.toggled.connect(self._on_overlay_toggle)
        toggle_layout.addWidget(self.overlay_enabled)

        hotkey_row = QtWidgets.QHBoxLayout()
        hotkey_row.setSpacing(10)
        hotkey_lbl = QtWidgets.QLabel(self._tr("Shortcut:"))
        hotkey_lbl.setStyleSheet("font-size: 13px; font-weight: 400; color: #e5e7eb;")
        hotkey_row.addWidget(hotkey_lbl)
        actual_hk = self.settings.value("overlay_hotkey", "Ctrl+Shift+O", type=str)
        self.hotkey_edit = QtWidgets.QKeySequenceEdit(QtGui.QKeySequence(actual_hk))
        self.hotkey_edit.setFixedWidth(160)
        self.hotkey_edit.setStyleSheet("""
            QKeySequenceEdit {
                background: #1f2937;
                border: 1px solid #2a3a55;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
                color: #fbbf24;
                font-weight: 700;
            }
            QKeySequenceEdit:focus {
                border-color: #fbbf24;
            }
        """)
        self.hotkey_edit.keySequenceChanged.connect(self._on_hotkey_changed)
        hotkey_row.addWidget(self.hotkey_edit)
        hotkey_row.addStretch()
        toggle_layout.addLayout(hotkey_row)

        self.overlay_enabled.blockSignals(True)
        self.overlay_enabled.setChecked(self.overlay.get_enabled())
        self.overlay_enabled.blockSignals(False)

        appear_section = self._sett_panel()
        appear_layout = QtWidgets.QVBoxLayout(appear_section)
        appear_layout.setContentsMargins(14, 12, 14, 12)
        appear_layout.setSpacing(10)

        hdr2 = QtWidgets.QHBoxLayout()
        hdr2.setSpacing(8)
        ab2 = QtWidgets.QFrame()
        ab2.setFixedWidth(3); ab2.setFixedHeight(18)
        ab2.setStyleSheet("background: #a78bfa; border-radius: 2px;")
        hdr2.addWidget(ab2)
        hdr2_lbl = QtWidgets.QLabel(self._tr("APPEARANCE"))
        hdr2_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;")
        hdr2.addWidget(hdr2_lbl)
        hdr2.addStretch()
        appear_layout.addLayout(hdr2)

        appear_layout.addWidget(QtWidgets.QLabel(self._tr("Color")))
        color_row = QtWidgets.QHBoxLayout()
        color_row.setSpacing(8)
        preset_colors = [
            ("#22d3a7", "Teal"), ("#22d3ee", "Cyan"), ("#60a5fa", "Blue"),
            ("#a78bfa", "Purple"), ("#f472b6", "Pink"), ("#fb923c", "Orange"),
            ("#34d399", "Green"), ("#fbbf24", "Yellow"), ("#f87171", "Red"),
            ("#e5e7eb", "White"),
        ]
        self._color_btns = []
        for hex_c, name in preset_colors:
            btn = QtWidgets.QPushButton()
            btn.setFixedSize(28, 28)
            btn.setToolTip(f"{name} ({hex_c})")
            btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {hex_c}; border-radius: 14px;
                    border: 2px solid transparent;
                }}
                QPushButton:hover {{
                    border-color: rgba(255,255,255,0.4);
                }}
            """)
            btn.clicked.connect(lambda checked, c=hex_c: self._sett_set_color(c))
            color_row.addWidget(btn)
            self._color_btns.append((btn, hex_c))
        color_row.addStretch()
        appear_layout.addLayout(color_row)

        cc_row = QtWidgets.QHBoxLayout()
        cc_row.setSpacing(10)
        cc_row.addWidget(QtWidgets.QLabel(self._tr("Custom:")))
        cc_btn = QtWidgets.QPushButton(self._tr("Pick Color"))
        cc_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        cc_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px; font-weight: 600; color: #e5e7eb;
                background: rgba(168,85,247,0.1);
                border: 1px solid rgba(168,85,247,0.3);
                border-radius: 8px; padding: 6px 14px;
            }
            QPushButton:hover {
                background: rgba(168,85,247,0.2);
                border-color: rgba(168,85,247,0.5);
            }
            QPushButton:pressed {
                background: rgba(168,85,247,0.3);
            }
        """)
        cc_btn.clicked.connect(self._sett_pick_custom_color)
        cc_row.addWidget(cc_btn)
        cc_row.addStretch()
        appear_layout.addLayout(cc_row)

        appear_layout.addWidget(QtWidgets.QLabel(self._tr("Font Size")))
        fs_row = QtWidgets.QHBoxLayout()
        fs_row.setSpacing(10)
        self.font_size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.font_size_slider.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.font_size_slider.wheelEvent = lambda e: None
        self.font_size_slider.setRange(8, 36)
        self.font_size_slider.setValue(self.overlay.get_font_size())
        self.font_size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px; background: #1e293b; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px; height: 16px; margin: -5px 0;
                background: #22d3ee; border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #2dd4bf;
            }
            QSlider::sub-page:horizontal {
                background: #22d3ee; border-radius: 3px;
            }
        """)
        self.font_size_slider.valueChanged.connect(self._sett_set_font_size)
        fs_row.addWidget(self.font_size_slider, 1)

        self.font_size_label = QtWidgets.QLabel(f"{self.overlay.get_font_size()}px")
        self.font_size_label.setStyleSheet("color: #22d3ee; font-size: 12px; font-weight: 700;")
        fs_row.addWidget(self.font_size_label)
        appear_layout.addLayout(fs_row)

        appear_layout.addWidget(QtWidgets.QLabel(self._tr("Font")))
        ff_row = QtWidgets.QHBoxLayout()
        ff_row.setSpacing(10)
        self.font_family_combo = QtWidgets.QComboBox()
        self.font_family_combo.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.font_family_combo.wheelEvent = lambda e: None
        current_font = self.overlay.get_font_family()
        for ff in FONT_FAMILIES:
            label = ff.split(",")[0].strip().strip("'")
            self.font_family_combo.addItem(label, ff)
            if ff == current_font:
                self.font_family_combo.setCurrentIndex(self.font_family_combo.count() - 1)
        self.font_family_combo.setStyleSheet("""
            QComboBox {
                background: #1f2937;
                border: 1px solid #2a3a55;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                color: #ffffff;
                min-width: 140px;
            }
            QComboBox:hover {
                border-color: #3b5a8a;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #1f2937;
                color: #ffffff;
                selection-background-color: #2a3a55;
                border: 1px solid #2a3a55;
                border-radius: 4px;
            }
        """)
        self.font_family_combo.currentIndexChanged.connect(self._sett_set_font_family)
        ff_row.addWidget(self.font_family_combo, 1)
        ff_row.addStretch()
        appear_layout.addLayout(ff_row)

        appear_layout.addWidget(QtWidgets.QLabel(self._tr("Position")))
        pos_row = QtWidgets.QHBoxLayout()
        pos_row.setSpacing(8)
        positions = [
            ("top-left", "\u2196"), ("top-right", "\u2197"),
            ("bottom-left", "\u2199"), ("bottom-right", "\u2198"),
        ]
        self._pos_btns = []
        current_pos = self.overlay.get_position()
        for pos_id, icon in positions:
            btn = QtWidgets.QPushButton(icon)
            btn.setFixedSize(50, 36)
            btn.setCheckable(True)
            btn.setChecked(pos_id == current_pos)
            btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            btn.setToolTip(pos_id)
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-size: 16px; font-weight: 700;
                    background: rgba(255,255,255,0.05);
                    border: 2px solid {"#22d3ee" if pos_id == current_pos else "#1e293b"};
                    border-radius: 8px;
                }}
                QPushButton:hover {{
                    border-color: #22d3ee;
                    background: rgba(34,211,238,0.1);
                }}
                QPushButton:checked {{
                    border-color: #22d3ee;
                    background: rgba(34,211,238,0.1);
                }}
            """)
            btn.clicked.connect(lambda checked, p=pos_id: self._sett_set_position(p))
            pos_row.addWidget(btn)
            self._pos_btns.append((btn, pos_id))
        pos_row.addStretch()
        appear_layout.addLayout(pos_row)

        fields_section = self._sett_panel()
        fields_layout = QtWidgets.QVBoxLayout(fields_section)
        fields_layout.setContentsMargins(14, 12, 14, 12)
        fields_layout.setSpacing(8)

        hdr3 = QtWidgets.QHBoxLayout()
        hdr3.setSpacing(8)
        ab3 = QtWidgets.QFrame()
        ab3.setFixedWidth(3); ab3.setFixedHeight(18)
        ab3.setStyleSheet("background: #34d399; border-radius: 2px;")
        hdr3.addWidget(ab3)
        hdr3_lbl = QtWidgets.QLabel(self._tr("DISPLAY FIELDS"))
        hdr3_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;")
        hdr3.addWidget(hdr3_lbl)
        hdr3.addStretch()
        fields_layout.addLayout(hdr3)

        field_grid = QtWidgets.QGridLayout()
        field_grid.setSpacing(6)
        self._field_checks = {}
        current_fields = set(self.overlay.get_fields())
        for idx, (fkey, flabel) in enumerate(ALL_FIELDS):
            cb = QtWidgets.QCheckBox(flabel)
            cb.setChecked(fkey in current_fields)
            cb.setStyleSheet("""
                QCheckBox {
                    font-size: 12px; font-weight: 600; color: #e5e7eb; spacing: 6px;
                }
                QCheckBox::indicator {
                    width: 18px; height: 18px; border-radius: 4px;
                    background: #1e293b; border: 1px solid #334155;
                }
                QCheckBox::indicator:checked {
                    background: #22d3ee; border-color: #22d3ee;
                }
                QCheckBox::indicator:hover {
                    border-color: #60a5fa;
                }
            """)
            cb.toggled.connect(lambda checked, k=fkey: self._sett_toggle_field(k, checked))
            field_grid.addWidget(cb, idx // 2, idx % 2)
            self._field_checks[fkey] = cb
        fields_layout.addLayout(field_grid)

        ss_section = self._sett_panel()
        ss_layout = QtWidgets.QVBoxLayout(ss_section)
        ss_layout.setContentsMargins(14, 12, 14, 12)
        ss_layout.setSpacing(10)

        hdr4 = QtWidgets.QHBoxLayout()
        hdr4.setSpacing(8)
        ab4 = QtWidgets.QFrame()
        ab4.setFixedWidth(3); ab4.setFixedHeight(18)
        ab4.setStyleSheet("background: #fb923c; border-radius: 2px;")
        hdr4.addWidget(ab4)
        hdr4_lbl = QtWidgets.QLabel(self._tr("SCREENSHOT"))
        hdr4_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;")
        hdr4.addWidget(hdr4_lbl)
        hdr4.addStretch()
        ss_layout.addLayout(hdr4)

        ss_layout.addWidget(QtWidgets.QLabel(self._tr("Save Location")))
        path_row = QtWidgets.QHBoxLayout()
        path_row.setSpacing(8)
        saved_path = self.settings.value("screenshot_path", "", type=str)
        if not saved_path:
            saved_path = os.path.join(os.path.expanduser("~"), "Pictures", "BloomPlay")

        self.ss_path_edit = QtWidgets.QLineEdit(saved_path)
        self.ss_path_edit.setReadOnly(True)
        self.ss_path_edit.setStyleSheet("""
            QLineEdit {
                background: #1f2937;
                border: 1px solid #2a3a55;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                color: #e5e7eb;
            }
        """)
        path_row.addWidget(self.ss_path_edit, 1)

        self.ss_browse_btn = QtWidgets.QPushButton(self._tr("Browse..."))
        self.ss_browse_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.ss_browse_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 600; color: #e5e7eb;
                background: rgba(52,211,153,0.1);
                border: 1px solid rgba(52,211,153,0.3);
                border-radius: 8px; padding: 6px 14px;
            }
            QPushButton:hover {
                background: rgba(52,211,153,0.2);
                border-color: rgba(52,211,153,0.5);
            }
        """)
        self.ss_browse_btn.clicked.connect(self._ss_browse_path)
        path_row.addWidget(self.ss_browse_btn)

        self.ss_open_folder_btn = QtWidgets.QPushButton("📂 " + self._tr("Open"))
        self.ss_open_folder_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.ss_open_folder_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 600; color: #e5e7eb;
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px; padding: 6px 14px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
            }
        """)
        self.ss_open_folder_btn.clicked.connect(self._ss_open_save_folder)
        path_row.addWidget(self.ss_open_folder_btn)
        ss_layout.addLayout(path_row)

        ss_layout.addWidget(QtWidgets.QLabel(self._tr("Shortcuts")))

        fs_row = QtWidgets.QHBoxLayout()
        fs_row.setSpacing(10)
        fs_row.addWidget(QtWidgets.QLabel(self._tr("Full Screen:")))
        current_fs_hk = self.settings.value("screenshot_full_hotkey", "Ctrl+Shift+F", type=str)
        self.ss_full_hotkey_edit = QtWidgets.QKeySequenceEdit(QtGui.QKeySequence(current_fs_hk))
        self.ss_full_hotkey_edit.setFixedWidth(160)
        self.ss_full_hotkey_edit.setStyleSheet("""
            QKeySequenceEdit {
                background: #1f2937;
                border: 1px solid #2a3a55;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
                color: #fb923c;
                font-weight: 700;
            }
            QKeySequenceEdit:focus {
                border-color: #fb923c;
            }
        """)
        self.ss_full_hotkey_edit.keySequenceChanged.connect(self._ss_on_full_hotkey_changed)
        fs_row.addWidget(self.ss_full_hotkey_edit)
        fs_row.addStretch()
        ss_layout.addLayout(fs_row)

        win_row = QtWidgets.QHBoxLayout()
        win_row.setSpacing(10)
        win_row.addWidget(QtWidgets.QLabel(self._tr("Active Window:")))
        current_win_hk = self.settings.value("screenshot_win_hotkey", "Ctrl+Shift+W", type=str)
        self.ss_win_hotkey_edit = QtWidgets.QKeySequenceEdit(QtGui.QKeySequence(current_win_hk))
        self.ss_win_hotkey_edit.setFixedWidth(160)
        self.ss_win_hotkey_edit.setStyleSheet("""
            QKeySequenceEdit {
                background: #1f2937;
                border: 1px solid #2a3a55;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
                color: #34d399;
                font-weight: 700;
            }
            QKeySequenceEdit:focus {
                border-color: #34d399;
            }
        """)
        self.ss_win_hotkey_edit.keySequenceChanged.connect(self._ss_on_win_hotkey_changed)
        win_row.addWidget(self.ss_win_hotkey_edit)
        win_row.addStretch()
        ss_layout.addLayout(win_row)

        theme_section = self._sett_panel()
        theme_layout = QtWidgets.QVBoxLayout(theme_section)
        theme_layout.setContentsMargins(14, 12, 14, 12)
        theme_layout.setSpacing(10)

        hdr5 = QtWidgets.QHBoxLayout()
        hdr5.setSpacing(8)
        ab5 = QtWidgets.QFrame()
        ab5.setFixedWidth(3); ab5.setFixedHeight(18)
        ab5.setStyleSheet("background: #a78bfa; border-radius: 2px;")
        hdr5.addWidget(ab5)
        hdr5_lbl = QtWidgets.QLabel(self._tr("LANGUAGE"))
        hdr5_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;")
        hdr5.addWidget(hdr5_lbl)
        hdr5.addStretch()
        theme_layout.addLayout(hdr5)


        lang_row = QtWidgets.QHBoxLayout()
        lang_row.setSpacing(10)
        lang_lbl = QtWidgets.QLabel(self._tr("Language:"))
        lang_lbl.setStyleSheet("font-size: 13px; font-weight: 400; color: #e5e7eb;")
        lang_row.addWidget(lang_lbl)
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItem("\U0001f1ec\U0001f1e7  English", "en")
        self.lang_combo.addItem("\U0001f1ee\U0001f1f7  \u0641\u0627\u0631\u0633\u06cc", "fa")
        current_lang = self.settings.value("language", "en", type=str)
        lidx = self.lang_combo.findData(current_lang)
        if lidx >= 0:
            self.lang_combo.setCurrentIndex(lidx)
        self.lang_combo.setFixedWidth(160)
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background-color: #1f2937; border: 1px solid #2a3a55;
                border-radius: 8px; padding: 6px 10px;
                font-size: 12px; color: #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #1f2937; color: #ffffff;
                selection-background-color: #2a3a55;
            }
        """)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self.lang_combo.wheelEvent = lambda e: None
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch()
        theme_layout.addLayout(lang_row)

        layout.addWidget(theme_section)

        layout.addWidget(toggle_section)
        layout.addWidget(appear_section)
        layout.addWidget(fields_section)
        layout.addWidget(ss_section)

        layout.addStretch()

        self.creator_btn = QtWidgets.QPushButton(self._tr("Made with") + " ❤️ " + self._tr("by Data Bloom"))
        self.creator_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.creator_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0,
                    x2:1, y2:0,
                    stop:0 rgba(167, 139, 250, 0.12),
                    stop:1 rgba(244, 114, 182, 0.12)
                );
                color: #a78bfa;
                border: 1px solid rgba(167, 139, 250, 0.2);
                border-radius: 12px;
                padding: 10px;
                font-size: 13px;
                font-weight: 600;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0,
                    x2:1, y2:0,
                    stop:0 rgba(167, 139, 250, 0.2),
                    stop:1 rgba(244, 114, 182, 0.2)
                );
                border-color: rgba(167, 139, 250, 0.35);
            }
            QPushButton:pressed {
                background: qlineargradient(
                    x1:0, y1:0,
                    x2:1, y2:0,
                    stop:0 rgba(167, 139, 250, 0.3),
                    stop:1 rgba(244, 114, 182, 0.3)
                );
            }
        """)
        self.creator_btn.clicked.connect(
            lambda: webbrowser.open("https://linktr.ee/Data_Bloom")
        )
        layout.addWidget(self.creator_btn)


        scroll.setWidget(page)
        return scroll        
    def _sett_panel(self):
        f = QtWidgets.QFrame()
        bg = "#0f1729"
        f.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: none;
                border-radius: 14px;
            }}""")
        return f

    def _sett_show_status(self, msg: str):
        if hasattr(self, "settings_status"):
            self.settings_status.setText(msg)
            QtCore.QTimer.singleShot(2000, lambda: self.settings_status.setText(""))

    def _sett_set_color(self, color: str):
        self.settings.setValue("overlay_color", color)
        for btn, c in self._color_btns:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c}; border-radius: 14px;
                    border: 2px solid {'#22d3ee' if c == color else 'transparent'};
                }}
                QPushButton:hover {{
                    border-color: rgba(255,255,255,0.4);
                }}
            """)
        self.overlay.refresh_appearance()
        self._sett_show_status(f"{self._tr('Color changed to')} {color}")

    def _sett_set_position(self, pos_id: str):
        self.settings.setValue("overlay_position", pos_id)
        for btn, p in self._pos_btns:
            btn.setChecked(p == pos_id)
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-size: 16px; font-weight: 700;
                    background: rgba(255,255,255,0.05);
                    border: 2px solid {'#22d3ee' if p == pos_id else '#1e293b'};
                    border-radius: 8px;
                }}
                QPushButton:hover {{
                    border-color: #22d3ee;
                    background: rgba(34,211,238,0.1);
                }}
                QPushButton:checked {{
                    border-color: #22d3ee;
                    background: rgba(34,211,238,0.1);
                }}
            """)
        self.overlay.refresh_appearance()
        self._sett_show_status(f"{self._tr('Position changed to')} {pos_id}")

    def _sett_set_font_size(self, size: int):
        self.settings.setValue("overlay_font_size", size)
        self.font_size_label.setText(f"{size}px")
        self.overlay.refresh_appearance()

    def _sett_set_font_family(self, index: int):
        font_family = self.font_family_combo.itemData(index)
        self.settings.setValue("overlay_font_family", font_family)
        self.overlay.refresh_appearance()
        self._sett_show_status(self._tr("Font changed"))

    def _sett_toggle_field(self, field_key: str, checked: bool):
        current = set(self.overlay.get_fields())
        if checked:
            current.add(field_key)
        else:
            current.discard(field_key)
        self.settings.setValue("overlay_fields", ",".join(current))
        self.overlay.refresh_appearance()

    def _sett_pick_custom_color(self):
        current = QtGui.QColor(self.settings.value("overlay_color", DEFAULT_COLOR, type=str))
        color = QtWidgets.QColorDialog.getColor(current, self, "Pick Custom Color")
        if color.isValid():
            hex_color = color.name()
            self._sett_set_color(hex_color)

    def _on_overlay_toggle(self, checked: bool):
        self.settings.setValue("overlay_enabled", checked)
        self.overlay.apply_enabled_state()
        self._sett_show_status(self._tr("Overlay") + " " + (self._tr("enabled") if checked else self._tr("disabled")))

    def _on_hotkey_changed(self):
        seq = self.hotkey_edit.keySequence()
        if seq.isEmpty():
            return
        self.settings.setValue("overlay_hotkey", seq.toString())
        self._register_global_hotkey()

    def _build_nav_rail(self) -> QtWidgets.QFrame:
        rail = QtWidgets.QFrame()
        rail.setObjectName("nav_rail")
        rail.setFixedWidth(64)
        old_nav = self.findChild(QtWidgets.QFrame, "nav_rail")
        if old_nav:
            old_nav.setParent(None)
            old_nav.deleteLater()
        rail.setStyleSheet("""
            QFrame {
                background-color: #0f1729;
                border: none;
                border-radius: 12px;
            }
        """)
        layout = QtWidgets.QVBoxLayout(rail)
        layout.setContentsMargins(6, 14, 6, 14)
        layout.setSpacing(10)
        layout.setAlignment(QtCore.Qt.AlignTop)

        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)

        nav_items = [
            (self.PAGE_STATS, "📊", "Stats"),
            (self.PAGE_HARDWARE, "💻", "Hardware"),
            (self.PAGE_MOBILE, "📱", "Mobile"),
            (self.PAGE_SCREENSHOT, "📷", "Screenshot"),
            (self.PAGE_SETTINGS, "⚙️", "Settings"),
        ]

        for page_index, icon, tooltip in nav_items:
            btn = QtWidgets.QToolButton()
            btn.setText(icon)
            btn.setToolTip(self._tr(tooltip))
            btn.setCheckable(True)
            btn.setFixedSize(52, 52)
            btn.setStyleSheet("""
                QToolButton {
                    background-color: #1f2937;
                    border: 1px solid #2a3a55;
                    border-radius: 12px;
                    font-size: 20px;
                }
                QToolButton:hover {
                    background-color: #2a3a55;
                    border-color: #3b5a8a;
                }
                QToolButton:checked {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 #22d3a7, stop:1 #60a5fa
                    );
                    border-color: #22d3a7;
                }
            """)
            btn.clicked.connect(lambda _checked, p=page_index: self.set_page(p))
            self.nav_group.addButton(btn, page_index)
            layout.addWidget(btn)

        layout.addStretch()

        exit_btn = QtWidgets.QToolButton()
        exit_btn.setText("⏻")
        exit_btn.setToolTip("Exit")
        exit_btn.setFixedSize(52, 52)
        exit_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(239,68,68,0.15);
                border: 1px solid rgba(239,68,68,0.3);
                border-radius: 12px;
                font-size: 22px;
            }
            QToolButton:hover {
                background-color: rgba(239,68,68,0.3);
                border-color: rgba(239,68,68,0.5);
            }
            QToolButton:pressed {
                background-color: rgba(239,68,68,0.5);
            }
        """)
        exit_btn.clicked.connect(self._quit_app)
        layout.addWidget(exit_btn)

        return rail

    def set_page(self, index: int):
        self.stack.setCurrentIndex(index)
        btn = self.nav_group.button(index)
        if btn:
            btn.setChecked(True)
        if index == self.PAGE_HARDWARE:
            self._render_hardware()

    def setup_tray(self):
        self.tray = QtWidgets.QSystemTrayIcon(self)
        self.tray.setIcon(QtGui.QIcon(_app_icon_path()))

        menu = QtWidgets.QMenu()
        show_action = menu.addAction("Show")
        exit_action = menu.addAction("Exit")
        show_action.triggered.connect(self.show_window)
        exit_action.triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_click)
        self.tray.show()

    def _quit_app(self):
        self._unregister_global_hotkey()
        self.tray.hide()
        self.overlay.close()
        QtWidgets.QApplication.quit()

    _F_KEY_TO_VK = {getattr(QtCore.Qt, f"Key_F{i}"): 0x70 + (i - 1) for i in range(1, 13)}
    _PUNCT_KEY_TO_VK = {
        QtCore.Qt.Key_QuoteLeft: 0xC0,
        QtCore.Qt.Key_Minus: 0xBD,
        QtCore.Qt.Key_Equal: 0xBB,
        QtCore.Qt.Key_Semicolon: 0xBA,
        QtCore.Qt.Key_Comma: 0xBC,
        QtCore.Qt.Key_Period: 0xBE,
        QtCore.Qt.Key_Slash: 0xBF,
    }

    def _qkeyseq_to_win32(self, seq: QtGui.QKeySequence):
        if seq.isEmpty():
            return None
        combo = seq[0]
        mod_bits = combo & 0xFE000000
        key_bits = combo & 0x01FFFFFF

        mods = 0
        if mod_bits & QtCore.Qt.ControlModifier:
            mods |= MOD_CONTROL
        if mod_bits & QtCore.Qt.ShiftModifier:
            mods |= MOD_SHIFT
        if mod_bits & QtCore.Qt.AltModifier:
            mods |= MOD_ALT
        if mod_bits & QtCore.Qt.MetaModifier:
            mods |= MOD_WIN

        if (0x30 <= key_bits <= 0x39) or (0x41 <= key_bits <= 0x5A):
            vk = key_bits
        elif key_bits in self._F_KEY_TO_VK:
            vk = self._F_KEY_TO_VK[key_bits]
        elif key_bits in self._PUNCT_KEY_TO_VK:
            vk = self._PUNCT_KEY_TO_VK[key_bits]
        else:
            return None
        return mods, vk

    def _register_global_hotkey(self):
        self._unregister_global_hotkey()
        if not _IS_WINDOWS:
            return

        import ctypes

        specs = [
            (HOTKEY_ID_OVERLAY, "overlay_hotkey", DEFAULT_HOTKEY, self._on_global_hotkey),
            (HOTKEY_ID_SS_FULL, "screenshot_full_hotkey", DEFAULT_SS_FULL_HOTKEY, self._ss_capture_full),
            (HOTKEY_ID_SS_WIN, "screenshot_win_hotkey", DEFAULT_SS_WIN_HOTKEY, self._ss_capture_window),
        ]

        handlers = {}
        for hk_id, key_name, default, callback in specs:
            seq_text = self.settings.value(key_name, default, type=str) or default
            parsed = self._qkeyseq_to_win32(QtGui.QKeySequence(seq_text))
            if parsed is None:
                print(f"[hotkey] Stored shortcut '{seq_text}' isn't supported - falling back to {default}")
                parsed = self._qkeyseq_to_win32(QtGui.QKeySequence(default))
            if parsed is None:
                continue
            mods, vk = parsed
            try:
                ok = ctypes.windll.user32.RegisterHotKey(None, hk_id, mods, vk)
                if ok:
                    handlers[hk_id] = callback
                else:
                    print(f"[hotkey] '{seq_text}' is already in use by another app")
            except Exception as e:
                print(f"[hotkey] Could not register global hotkey '{seq_text}': {e}")

        if handlers:
            self._hotkey_filter = _GlobalHotkeyFilter(handlers)
            QtWidgets.QApplication.instance().installNativeEventFilter(self._hotkey_filter)
            self._hotkey_registered = True
        else:
            self._hotkey_registered = False

    def _unregister_global_hotkey(self):
        if not _IS_WINDOWS:
            return
        if not getattr(self, "_hotkey_registered", False):
            return
        try:
            import ctypes
            for hk_id in (HOTKEY_ID_OVERLAY, HOTKEY_ID_SS_FULL, HOTKEY_ID_SS_WIN):
                try:
                    ctypes.windll.user32.UnregisterHotKey(None, hk_id)
                except Exception:
                    pass
        except Exception:
            pass
        if getattr(self, "_hotkey_filter", None) is not None:
            try:
                QtWidgets.QApplication.instance().removeNativeEventFilter(self._hotkey_filter)
            except Exception:
                pass
            self._hotkey_filter = None
        self._hotkey_registered = False

    def _on_global_hotkey(self):
        new_state = not self.overlay.get_enabled()
        self.settings.setValue("overlay_enabled", new_state)
        self.overlay.apply_enabled_state()
        if hasattr(self, "overlay_enabled"):
            self.overlay_enabled.blockSignals(True)
            self.overlay_enabled.setChecked(new_state)
            self.overlay_enabled.blockSignals(False)

    def _on_shared_config_change(self, cfg):
        try:
            if (cfg or {}).get("hotkey") is not None:
                QtCore.QTimer.singleShot(0, self._register_global_hotkey)
        except Exception:
            pass

    def setup_timer(self):
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _tick(self):
        self.update_phone_status()

        if self.stats_worker is None or not self.stats_worker.isRunning():
            self.stats_worker = StatsWorker(self)
            self.stats_worker.stats_ready.connect(self.on_stats_ready)
            self.stats_worker.start()

    def on_stats_ready(self, data: dict):
        if data:
            self.cached_stats = data
        if self.stack.currentIndex() == self.PAGE_STATS:
            self._render_live_stats()
        self.overlay.update_stats(self.cached_stats)

    def _render_live_stats(self):
        s = self.cached_stats if self.cached_stats else {}

        cpu_val = s.get("cpu", 0)
        self.cpu_gauge.set_value(cpu_val)

        cpu_temp = s.get("cpu_temp")
        if cpu_temp is not None and isinstance(cpu_temp, (int, float)) and cpu_temp >= 0 and cpu_temp < 120:
            self.cpu_temp_gauge.set_value(cpu_temp)
        else:
            self.cpu_temp_gauge.set_value(None)

        gpu_data = s.get("gpu", {})
        gpu_usage = gpu_data.get("usage", 0)
        self.gpu_gauge.set_value(gpu_usage)
        self.gpu_temp_gauge.set_value(gpu_data.get("temp"))

        vram_used = gpu_data.get("vram_used", 0)
        vram_total = gpu_data.get("vram_total", 0)
        if vram_total > 0:
            self.vram_meter.set_value(f"{vram_used:.0f} / {vram_total:.0f} MB")
        else:
            self.vram_meter.set_value("N/A")

        ram = s.get("ram", {})
        ram_pct = ram.get("percent", 0)
        ram_used = ram.get("used", 0)
        ram_total = ram.get("total", 0)
        self.ram_gauge.set_value(ram_pct, f"{ram_used} / {ram_total}")

        net = s.get("network", {})
        dl = net.get("download", 0) / (1024 * 1024)
        ul = net.get("upload", 0) / (1024 * 1024)
        self.download_wave.set_value(dl)
        self.upload_wave.set_value(ul)
        self.ping_gauge.set_value(net.get('ping', 0))

        fps_data = s.get("fps", {})
        fps = fps_data.get("fps")
        if fps is not None:
            self.fps_bar.set_value(f"{fps:.0f}")
        else:
            self.fps_bar.set_value("N/A")

        bat = s.get("battery", {})
        bat_pct = bat.get("percent")
        if bat_pct is not None and bat_pct != "N/A":
            self.battery_gauge.set_value(bat_pct)
        else:
            self.battery_gauge.set_value(None)

        health = bat.get("health_percent")
        if health is not None:
            self.battery_health_gauge.set_value(health)
        else:
            self.battery_health_gauge.set_value(None)

        disk_data = self.hardware.get("disk", [])
        self.disk_bar.set_value(disk_data)

    _HIDDEN_NAMES = {
        "", "unknown", "default", "default monitor", "generic pnp monitor",
        "monitor", "generic monitor", "not applicable", "none", "n/a",
        "unknown unknown", "default default",
    }

    def _hw_name_ok(self, name) -> bool:
        if name is None:
            return False
        n = str(name).strip().lower()
        if not n or n in self._HIDDEN_NAMES:
            return False
        if n.startswith("default "):
            return False
        return True

    def _render_hardware(self):
        hw = self.hardware
        if not hw:
            return

        for key, content_label in self.hw_cards.items():
            info = hw.get(key, {})
            if not info:
                content_label.setText(self._tr("No info available"))
                continue

            accent = self.hw_accents.get(key, "#e5e7eb")

            if key == "disk":
                if info:
                    drives = {}
                    for d in info:
                        dmodel = d.get("model", "") or self._tr("Unknown")
                        dtype = d.get("type", "?")
                        dtotal = d.get("total", 0)
                        if dmodel not in drives:
                            drives[dmodel] = {"type": dtype, "total": 0}
                        drives[dmodel]["total"] += dtotal

                    fa_mode = self.settings.value("language", "en", type=str) == "fa"
                    rle = "\u202b" if fa_mode else ""
                    pdf = "\u202c" if fa_mode else ""
                    align = " align='right'" if fa_mode else ""
                    lines_hw = []
                    for model, data in drives.items():
                        dtype = data["type"]
                        dtotal = data["total"]
                        icon = "💿" if dtype == "SSD" else "💽"
                        color = "#22c55e" if dtype == "SSD" else ("#60a5fa" if dtype == "HDD" else "#94a3b8")
                        short_model = model[:40] + "..." if len(model) > 43 else model
                        lines_hw.append(
                            f"<div{align} style='margin:{('8' if fa_mode else '4')}px 0;font-size:12px;line-height:1.6;'>"
                            f"{rle}<b style='color:{accent};font-size:12px;'>{self._tr('Model :')}</b> <span style='color:#ffffff;font-size:12px;'>{short_model}</span> "
                            f"<span style='color:{color};font-size:10px;font-weight:700;background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:999px;'>[{dtype}]</span>{pdf}"
                            f"<br>{rle}<b style='color:{accent};font-size:11px;'>{self._tr('Total :')}</b> <span style='color:#ffffff;font-size:11px;'>{dtotal} GB</span>{pdf}"
                            f"</div>"
                        )
                    total_storage = self.hardware.get("total_storage", "Unknown")
                    lines_hw.append(
                        f"<div{align} style='margin-top:6px;padding-top:6px;border-top:1px solid {'#1a1a2e'};'>"
                        f"{rle}<span style='color:#ffffff;font-size:12px;font-weight:700;'>{self._tr('TOTAL')}: <span style='color:#fbbf24;'>{total_storage}</span></span>{pdf}"
                        f"</div>"
                    )
                    text = "".join(lines_hw)
                else:
                    text = "<span style='color:#ffffff;'>" + self._tr("No disk info available") + "</span>"
                content_label.setText(text)
                continue

            if key == "display":
                monitors = [m for m in info.get("monitors", [])
                            if self._hw_name_ok(m.get("name"))]
                if monitors:
                    primary = next((m for m in monitors if m.get("primary")), monitors[0])
                    if self.settings.value("language", "en", type=str) == "fa":
                        html = ""
                        html += f"<div align='right' style='margin:8px 0;'>\u202b<b style='color:{accent};'>{self._tr('Monitor :')}</b> <span style='color:#ffffff;'>{primary.get('name', self._tr('Unknown'))}</span>\u202c</div>"
                        html += f"<div align='right' style='margin:8px 0;'>\u202b<b style='color:{accent};'>{self._tr('Resolution :')}</b> <span style='color:#ffffff;'>{info.get('primary_resolution', self._tr('Unknown'))}</span>\u202c</div>"
                        html += f"<div align='right' style='margin:8px 0;'>\u202b<b style='color:{accent};'>{self._tr('Refresh :')}</b> <span style='color:#ffffff;'>{info.get('refresh_rate', self._tr('Unknown'))}</span>\u202c</div>"
                        html += f"<div align='right' style='margin:8px 0;'>\u202b<b style='color:{accent};'>{self._tr('Screen :')}</b> <span style='color:#ffffff;'>{info.get('screen_size', self._tr('Unknown'))}</span>\u202c</div>"
                    else:
                        html = ""
                        html += f"<b style='color:{accent};'>{self._tr('Monitor :')}</b> <span style='color:#ffffff;'>{primary.get('name', self._tr('Unknown'))}</span><br><br>"
                        html += f"<b style='color:{accent};'>{self._tr('Resolution :')}</b> <span style='color:#ffffff;'>{info.get('primary_resolution', self._tr('Unknown'))}</span><br><br>"
                        html += f"<b style='color:{accent};'>{self._tr('Refresh :')}</b> <span style='color:#ffffff;'>{info.get('refresh_rate', self._tr('Unknown'))}</span><br><br>"
                        html += f"<b style='color:{accent};'>{self._tr('Screen :')}</b> <span style='color:#ffffff;'>{info.get('screen_size', self._tr('Unknown'))}</span>"
                else:
                    html = "<span style='color:#ffffff;'>" + self._tr("No monitor info available") + "</span>"
                content_label.setText(html)
                continue

            if key == "audio":
                devices = [d for d in info.get("devices", [])
                           if self._hw_name_ok(d.get("name"))]
                if devices:
                    fa_mode = self.settings.value("language", "en", type=str) == "fa"
                    rle = "\u202b" if fa_mode else ""
                    pdf = "\u202c" if fa_mode else ""
                    align = " align='right'" if fa_mode else ""
                    html_parts = []
                    for d in devices:
                        dname = d.get("name", "Unknown")
                        dmfr = d.get("manufacturer", "")
                        dn = dname.lower()
                        if "microphone" in dn or "mic" in dn:
                            dicon = self._tr("Microphone")
                        elif "headphone" in dn or "headset" in dn:
                            dicon = self._tr("Headphone")
                        elif "speaker" in dn or "output" in dn:
                            dicon = self._tr("Speaker")
                        else:
                            dicon = self._tr("Device")
                        line = f"<div{align} style='margin:{('8' if fa_mode else '4')}px 0;font-size:12px;line-height:1.6;'>"
                        line += f"{rle}<b style='color:{accent};'>{dicon} :</b> <span style='color:#ffffff;font-weight:600;'>{dname}</span>"
                        if dmfr and dmfr != "Unknown":
                            line += f" <span style='color:#e5e7eb;font-size:11px;font-weight:500;'>- {dmfr}</span>"
                        line += f"{pdf}</div>"
                        html_parts.append(line)
                    html = "".join(html_parts)
                else:
                    html = "<span style='color:#ffffff;'>" + self._tr("No audio devices found") + "</span>"
                content_label.setText(html)
                continue

            html_parts = []
            fa_mode = self.settings.value("language", "en", type=str) == "fa"
            for k, v in info.items():
                if not self._hw_name_ok(str(v)):
                    continue
                label = k.replace("_", " ").title()
                if fa_mode:
                    html_parts.append(
                        f"<div align='right' style='margin:8px 0;'>\u202b<b style='color:{accent};'>{self._tr(label)} :</b> "
                        f"<span style='color:#ffffff;'>{v}\u202c</div>"
                    )
                else:
                    html_parts.append(f"<b style='color:{accent};'>{self._tr(label)} :</b> <span style='color:#ffffff;'>{v}</span>")
            if fa_mode:
                content_label.setText("".join(html_parts))
            else:
                content_label.setText("<br><br>".join(html_parts))

    def update_phone_status(self):
        try:
            from api.state import get_connected_devices
            devices = get_connected_devices()
            count = len(devices)
            connected = count > 0
        except Exception:
            devices = []
            connected = False
            count = 0
        self._set_phone_status_style(connected)
        if hasattr(self, "device_list_widget") and self.device_list_widget is not None:
            self._refresh_device_list(devices)

    def _set_phone_status_style(self, connected: bool):
        if connected:
            self.phone_status.setText(self._tr("Connected"))
            self.phone_status.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 600;")
        else:
            self.phone_status.setText(self._tr("Disconnected"))
            self.phone_status.setStyleSheet("color: #f87171; font-size: 12px; font-weight: 600;")
        if hasattr(self, "_qr_status_dot"):
            c = "#34d399" if connected else "#f87171"
            self._qr_status_dot.setStyleSheet(f"background-color: {c}; border-radius: 4px;")

    def copy_ip_to_clipboard(self, _event):
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(self.url)
        old_text = self.ip_label.text()
        self.ip_label.setText(self._tr("✅ Copied!"))
        QtCore.QTimer.singleShot(2000, lambda: self.ip_label.setText(old_text))

    def _refresh_device_list(self, devices: list):
        if not hasattr(self, "device_list_layout") or self.device_list_layout is None:
            return
        layout = self.device_list_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not devices:
            placeholder = QtWidgets.QLabel("No devices connected")
            placeholder.setStyleSheet("color: #e5e7eb; font-size: 11px; padding: 8px;")
            placeholder.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(placeholder)
        else:
            for dev in devices:
                dev_frame = self._build_device_row(dev)
                layout.addWidget(dev_frame)
        layout.addStretch()

    def _build_device_row(self, dev: dict) -> QtWidgets.QFrame:
        ip = dev.get("ip", "?")
        ua = dev.get("user_agent", "")
        ua_lower = ua.lower()
        if "iphone" in ua_lower or "ipad" in ua_lower:
            device_icon = "🍎"
            device_type = "Apple"
        elif "android" in ua_lower:
            device_icon = "🤖"
            device_type = "Android"
        elif "windows" in ua_lower:
            device_icon = "🪟"
            device_type = "Windows"
        elif "macintosh" in ua_lower or "mac os" in ua_lower:
            device_icon = "💻"
            device_type = "macOS"
        elif "linux" in ua_lower:
            device_icon = "🐧"
            device_type = "Linux"
        else:
            device_icon = "📱"
            device_type = self._tr("Unknown")

        frame = QtWidgets.QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 8px;
            }
        """)
        row = QtWidgets.QHBoxLayout(frame)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)

        icon_lbl = QtWidgets.QLabel(device_icon)
        icon_lbl.setStyleSheet("font-size: 16px;")
        row.addWidget(icon_lbl)

        info_col = QtWidgets.QVBoxLayout()
        info_col.setSpacing(1)
        name_lbl = QtWidgets.QLabel(f"{device_type} • {ip}")
        name_lbl.setStyleSheet("color: #e5e7eb; font-size: 12px; font-weight: 600;")
        info_col.addWidget(name_lbl)

        since_lbl = QtWidgets.QLabel(self._tr("Connected now"))
        since_lbl.setStyleSheet("color: #e5e7eb; font-size: 9px;")
        info_col.addWidget(since_lbl)
        row.addLayout(info_col, 1)

        disconnect_btn = QtWidgets.QPushButton("✕")
        disconnect_btn.setFixedSize(24, 24)
        disconnect_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239,68,68,0.15);
                color: #ef4444;
                border: 1px solid rgba(239,68,68,0.3);
                border-radius: 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(239,68,68,0.3);
            }
        """)
        disconnect_btn.clicked.connect(lambda checked, ip=ip: self._disconnect_device(ip))
        row.addWidget(disconnect_btn)

        return frame

    def _disconnect_device(self, device_ip: str):
        try:
            from api.state import disconnect_device
            ok = disconnect_device(device_ip)
            if ok:
                self.update_phone_status()
        except Exception:
            pass

    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def on_tray_click(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self.show_window()


def main():
    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    app.exec_()


if __name__ == "__main__":
    main()
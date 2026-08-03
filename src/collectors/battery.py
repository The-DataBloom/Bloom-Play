import os
import platform
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

import psutil

_health_cache = {"percent": None, "checked_at": 0.0}
_HEALTH_CACHE_TTL = 6 * 60 * 60


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1].lower()


def _read_health_percent_windows():
    if platform.system() != "Windows":
        return None

    tmp_path = os.path.join(tempfile.gettempdir(), "bloomplay_battery_report.xml")

    try:
        subprocess.run(
            ["powercfg", "/batteryreport", "/output", tmp_path, "/xml"],
            capture_output=True,
            timeout=15,
            check=True,
        )
    except Exception:
        return None

    try:
        tree = ET.parse(tmp_path)
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    def _num(text):
        try:
            return float((text or "").strip())
        except (ValueError, TypeError):
            return None

    pairs = []

    def _collect_children(parent):
        design = full = None
        for el in parent.iter():
            name = _local_tag(el.tag)
            if name == "designcapacity" and design is None:
                design = _num(el.text)
            elif name == "fullchargecapacity" and full is None:
                full = _num(el.text)
        if design and full:
            pairs.append((design, full))

    root = tree.getroot()
    for el in root.iter():
        if _local_tag(el.tag) == "batteryreport":
            _collect_children(el)
    for el in root.iter():
        if _local_tag(el.tag) == "battery":
            _collect_children(el)

    if not pairs:
        return None

    health = max(full / design for design, full in pairs if design)
    return round(max(0.0, min(100.0, health * 100.0)), 1)


def _get_health_percent():
    now = time.time()
    if _health_cache["checked_at"] and (now - _health_cache["checked_at"]) < _HEALTH_CACHE_TTL:
        return _health_cache["percent"]

    percent = _read_health_percent_windows()
    _health_cache["percent"] = percent
    _health_cache["checked_at"] = now
    return percent


def _health_label(health_percent):
    if health_percent is None:
        return "Unavailable"
    if health_percent >= 80:
        return "Excellent"
    if health_percent >= 60:
        return "Good"
    if health_percent >= 40:
        return "Fair"
    return "Poor"


def get_battery_specs_windows() -> dict:
    defaults = {
        "name": "Unknown",
        "manufacturer": "Unknown",
        "design_capacity": "Unknown",
        "full_charge_capacity": "Unknown",
        "serial_number": "Unknown",
        "chemistry": "Unknown",
        "design_voltage": "Unknown",
        "device_id": "Unknown",
    }
    if platform.system() != "Windows":
        return defaults

    try:
        import pythoncom
    except Exception:
        pythoncom = None
    try:
        import wmi
    except Exception:
        wmi = None

    if wmi is None:
        return defaults

    try:
        if pythoncom is not None:
            pythoncom.CoInitialize()
        w = wmi.WMI()
        batteries = w.Win32_Battery()
        if not batteries:
            return defaults
        b = batteries[0]

        def _s(prop, default="Unknown"):
            val = str(getattr(b, prop, '') or '').strip()
            return val if val else default

        def _n(prop):
            val = getattr(b, prop, None)
            return val if val is not None else None

        name = _s('Name')
        manufacturer = _s('Manufacturer')
        serial = _s('SerialNumber')
        device_id = _s('DeviceID')

        chemistries = {
            "1": "Lead Acid", "2": "Nickel Cadmium",
            "3": "Nickel Metal Hydride", "4": "Lithium Ion",
            "5": "Lithium Polymer", "6": "Zinc Air",
            "7": "Lithium Iron Disulfide",
        }
        chemistry_raw = _s('Chemistry')
        chemistry = chemistries.get(chemistry_raw, chemistry_raw if chemistry_raw != 'Unknown' else defaults['chemistry'])

        dc = _n('DesignCapacity')
        design_cap = f'{int(dc)} mWh' if dc is not None else defaults['design_capacity']

        fcc = _n('FullChargeCapacity')
        full_cap = f'{int(fcc)} mWh' if fcc is not None else defaults['full_charge_capacity']

        dv = _n('DesignVoltage')
        design_voltage = f'{int(dv)} mV' if dv is not None else defaults['design_voltage']

        result = {}
        for k, v in [
            ('name', name),
            ('manufacturer', manufacturer),
            ('design_capacity', design_cap),
            ('full_charge_capacity', full_cap),
            ('serial_number', serial),
            ('chemistry', chemistry),
            ('design_voltage', design_voltage),
            ('device_id', device_id),
        ]:
            if v != 'Unknown':
                result[k] = v
        return result
    except Exception as e:
        print(f"[battery] WMI error reading specs: {e}")
        return defaults


def get_battery_stats() -> dict:
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None

    if battery is None:
        return {
            "percent": "N/A",
            "charging": None,
            "health_percent": None,
            "health_label": "Desktop PC",
        }

    health_percent = _get_health_percent()

    return {
        "percent": round(battery.percent),
        "charging": bool(battery.power_plugged),
        "health_percent": health_percent,
        "health_label": _health_label(health_percent),
    }

import platform
import psutil

from collectors import hwmonitor

_status = "Not read yet"


def _sane_temp(v):
    if v is None:
        return None
    try:
        t = float(v)
        return t if 0.0 <= t <= 100.0 else None
    except (ValueError, TypeError):
        return None


def _wmi_temp():
    if platform.system() != "Windows":
        return None
    try:
        import wmi
        w = wmi.WMI(namespace="root\\WMI")
        temps = w.MSAcpi_ThermalZoneTemperature()
        values = [_sane_temp((t.CurrentTemperature / 10) - 273.15) for t in temps]
        values = [v for v in values if v is not None]
        if values:
            return round(max(values), 1)
    except Exception:
        pass
    return None


def _wmi_perfcounter_temp():
    if platform.system() != "Windows":
        return None
    try:
        import wmi
        w = wmi.WMI(namespace="root\\CIMV2")
        zones = w.Win32_PerfFormattedData_Counters_ThermalZoneInformation()
        values = []
        for z in zones:
            raw = getattr(z, "Temperature", None) or getattr(z, "HighPrecisionTemperature", None)
            if raw:
                v = _sane_temp((float(raw) / 10) - 273.15)
                if v is not None:
                    values.append(v)
        if values:
            return round(max(values), 1)
    except Exception:
        pass
    return None


def _psutil_temp():
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, Exception):
        return None
    if not temps:
        return None
    for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
        if key in temps and temps[key]:
            values = [t.current for t in temps[key] if t.current]
            values = [v for v in values if _sane_temp(v) is not None]
            if values:
                return round(max(values), 1)
    for _, entries in temps.items():
        values = [t.current for t in entries if t.current]
        values = [v for v in values if _sane_temp(v) is not None]
        if values:
            return round(max(values), 1)
    return None


def get_cpu_temp():
    global _status

    v = _wmi_temp()
    if v is not None:
        _status = "ACPI thermal zone"
        return v

    v = _wmi_perfcounter_temp()
    if v is not None:
        _status = "Windows thermal-zone performance counter"
        return v

    v = _psutil_temp()
    if v is not None:
        _status = "psutil sensors"
        return v

    v = hwmonitor.get_cpu_temp()
    if v is not None:
        _status = "LibreHardwareMonitorLib (optional, libs/)"
        return v

    if platform.system() == "Windows":
        _status = "Not exposed by this board/driver to any built-in Windows API (a hardware limitation, not a BloomPlay bug)"
    else:
        _status = "No CPU temperature sensor exposed on this machine"
    return None


def get_cpu_temp_status() -> str:
    return _status


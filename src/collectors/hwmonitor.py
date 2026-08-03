from __future__ import annotations

import os
import platform
import threading

_IS_WINDOWS = platform.system() == "Windows"

_lock = threading.Lock()
_computer = None
_init_attempted = False
_init_error: str | None = None


def _dll_path() -> str | None:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "libs"))
    path = os.path.join(base_dir, "LibreHardwareMonitorLib.dll")
    return path if os.path.exists(path) else None


def dll_present() -> bool:
    return _IS_WINDOWS and _dll_path() is not None


def _ensure_initialized():
    global _computer, _init_attempted, _init_error

    if _init_attempted:
        return
    with _lock:
        if _init_attempted:
            return
        _init_attempted = True

        if not _IS_WINDOWS:
            _init_error = "Not on Windows"
            return

        dll_path = _dll_path()
        if not dll_path:
            _init_error = "LibreHardwareMonitorLib.dll not found in libs/"
            return

        try:
            import sys
            import clr

            dll_dir = os.path.dirname(dll_path)
            if dll_dir not in sys.path:
                sys.path.append(dll_dir)

            clr.AddReference("LibreHardwareMonitorLib")
            from LibreHardwareMonitor.Hardware import Computer

            computer = Computer()
            computer.IsCpuEnabled = True
            computer.IsGpuEnabled = True
            computer.IsMemoryEnabled = True
            computer.IsMotherboardEnabled = True
            computer.IsStorageEnabled = True
            computer.Open()

            _computer = computer
        except Exception as e:
            _init_error = f"Failed to load LibreHardwareMonitorLib: {e}"
            _computer = None


def _update_all():
    for hw in _computer.Hardware:
        hw.Update()
        for sub in hw.SubHardware:
            sub.Update()


def _collect_sensor_values(sensor_type_name: str, name_hints=None):
    values = []
    for hw in _computer.Hardware:
        groups = [hw.Sensors] + [sub.Sensors for sub in hw.SubHardware]
        for sensors in groups:
            for sensor in sensors:
                try:
                    if str(sensor.SensorType) != sensor_type_name:
                        continue
                    value = sensor.Value
                    if value is None:
                        continue
                    if name_hints:
                        sname = (sensor.Name or "").lower()
                        if not any(h in sname for h in name_hints):
                            continue
                    values.append(float(value))
                except Exception:
                    continue
    return values


def _query(sensor_type_name: str, name_hints=None):
    _ensure_initialized()
    if _computer is None:
        return None
    with _lock:
        try:
            _update_all()
            values = _collect_sensor_values(sensor_type_name, name_hints)
            return round(max(values), 1) if values else None
        except Exception as e:
            global _init_error
            _init_error = f"Sensor read failed: {e}"
            return None


def get_cpu_temp():
    return _query("Temperature", name_hints=("cpu package", "cpu core", "core max", "tctl", "cpu"))


def get_gpu_temp():
    return _query("Temperature", name_hints=("gpu core", "gpu hot spot", "gpu"))


def get_gpu_load():
    return _query("Load", name_hints=("gpu core", "d3d 3d", "gpu"))



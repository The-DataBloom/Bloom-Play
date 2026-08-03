from collectors.system import get_cpu, get_ram
from collectors.temperature import get_cpu_temp, get_cpu_temp_status
from collectors.gpu import get_gpu_stats
from collectors.network import get_network
from collectors.battery import get_battery_stats
from collectors.fps import get_fps, get_fps_status


DEFAULT_GPU = {
    "name": "Unknown GPU",
    "usage": 0,
    "vram_used": 0,
    "vram_total": 0,
    "temp": None,
}


def _safe_cpu():
    try:
        cpu = get_cpu()
        return cpu if cpu is not None else 0
    except Exception:
        return 0


def _safe_gpu():
    try:
        gpu = get_gpu_stats()
        return gpu if gpu else DEFAULT_GPU.copy()
    except Exception:
        return DEFAULT_GPU.copy()


def _safe_ram():
    try:
        return get_ram()
    except Exception:
        return {"used": 0, "total": 0, "percent": 0}


def _safe_network():
    try:
        return get_network()
    except Exception:
        return {"upload": 0, "download": 0, "ping": 0}


def _safe_battery():
    try:
        return get_battery_stats()
    except Exception:
        return {"percent": "N/A", "charging": None, "health_percent": None, "health_label": "Unknown"}


def _safe_cpu_temp():
    try:
        return get_cpu_temp()
    except Exception:
        return None


def _safe_cpu_temp_status():
    try:
        return get_cpu_temp_status()
    except Exception:
        return ""


def _safe_fps():
    try:
        return {"fps": get_fps(), "status": get_fps_status()}
    except Exception:
        return {"fps": None, "status": "Error"}


def get_all_stats():
    return {
        "cpu": _safe_cpu(),
        "cpu_temp": _safe_cpu_temp(),
        "cpu_temp_status": _safe_cpu_temp_status(),
        "ram": _safe_ram(),
        "gpu": _safe_gpu(),
        "network": _safe_network(),
        "battery": _safe_battery(),
        "fps": _safe_fps(),
    }

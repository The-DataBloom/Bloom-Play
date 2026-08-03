from collectors import hwmonitor

_gpu_ready = False
_pynvml = None


def init_gpu():
    global _gpu_ready, _pynvml
    if _gpu_ready:
        return True
    try:
        import pynvml
        pynvml.nvmlInit()
        _pynvml = pynvml
        _gpu_ready = True
    except Exception:
        _gpu_ready = False
        _pynvml = None
    return _gpu_ready


def _get_nvidia_stats():
    if not _gpu_ready or _pynvml is None:
        return None
    try:
        handle = _pynvml.nvmlDeviceGetHandleByIndex(0)
        util = _pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = _pynvml.nvmlDeviceGetMemoryInfo(handle)
        temp = _pynvml.nvmlDeviceGetTemperature(
            handle, _pynvml.NVML_TEMPERATURE_GPU
        )

        try:
            name = _pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="ignore")
        except Exception:
            name = "NVIDIA GPU"

        return {
            "name": name,
            "usage": round(float(util.gpu), 1),
            "vram_used": round(mem.used / (1024 ** 3), 1),
            "vram_total": round(mem.total / (1024 ** 3), 1),
            "temp": int(temp) if temp is not None else None,
        }
    except Exception:
        return None


def _get_fallback_stats():
    temp = hwmonitor.get_gpu_temp()
    load = hwmonitor.get_gpu_load()
    if temp is None and load is None:
        return None
    return {
        "name": "GPU (via LibreHardwareMonitor)",
        "usage": load if load is not None else 0,
        "vram_used": 0,
        "vram_total": 0,
        "temp": temp,
    }


def get_gpu_stats():
    stats = _get_nvidia_stats()
    if stats is not None:
        return stats
    return _get_fallback_stats()

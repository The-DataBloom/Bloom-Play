import psutil


def get_cpu() -> float:
    return psutil.cpu_percent(interval=None)


def get_ram() -> dict:
    mem = psutil.virtual_memory()
    return {
        "used": round(mem.used / (1024 ** 3), 1),
        "total": round(mem.total / (1024 ** 3), 1),
        "percent": mem.percent,
    }

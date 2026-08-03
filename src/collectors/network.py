import threading
import time

import psutil

try:
    from ping3 import ping  # type: ignore
except Exception:
    ping = None


_lock = threading.Lock()

_ping_value = 0.0
_download_mbps = 0.0
_upload_mbps = 0.0

_ping_thread_started = False
_net_thread_started = False


def _ping_worker():
    global _ping_value
    while True:
        try:
            if ping is None:
                _ping_value = 0.0
            else:
                result = ping("8.8.8.8", timeout=1)
                with _lock:
                    _ping_value = round(result * 1000, 1) if result else 0.0
        except Exception:
            with _lock:
                _ping_value = 0.0
        time.sleep(2)


def _net_worker():
    global _download_mbps, _upload_mbps
    try:
        last_io = psutil.net_io_counters()
    except Exception:
        last_io = None
    last_time = time.time()

    while True:
        time.sleep(1)
        try:
            io = psutil.net_io_counters()
        except Exception:
            continue
        now = time.time()
        elapsed = max(now - last_time, 0.001)

        if last_io is not None:
            down = round(((io.bytes_recv - last_io.bytes_recv) * 8 / 1_000_000) / elapsed, 2)
            up = round(((io.bytes_sent - last_io.bytes_sent) * 8 / 1_000_000) / elapsed, 2)
            with _lock:
                _download_mbps = max(down, 0.0)
                _upload_mbps = max(up, 0.0)

        last_io, last_time = io, now


def start_ping_thread():
    global _ping_thread_started
    if _ping_thread_started:
        return
    _ping_thread_started = True
    t = threading.Thread(target=_ping_worker, daemon=True, name="ping-worker")
    t.start()


def start_net_thread():
    global _net_thread_started
    if _net_thread_started:
        return
    _net_thread_started = True
    t = threading.Thread(target=_net_worker, daemon=True, name="net-worker")
    t.start()


def get_network() -> dict:
    start_net_thread()
    start_ping_thread()
    with _lock:
        return {
            "upload": _upload_mbps,
            "download": _download_mbps,
            "ping": _ping_value,
        }

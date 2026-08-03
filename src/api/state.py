import threading
import time
import secrets
from collections import OrderedDict

CLIENT_TIMEOUT = 10

BLOCK_DURATION = 60

_lock = threading.Lock()

_connected_devices: OrderedDict = OrderedDict()

_blocked_ips: dict = {}


def touch(client_ip: str = "unknown", user_agent: str = ""):
    global _connected_devices
    now = time.time()
    with _lock:
        _clean_blocked_locked()
        if client_ip in _blocked_ips:
            return False
        if client_ip not in _connected_devices:
            _connected_devices[client_ip] = {
                "ip": client_ip,
                "user_agent": user_agent or "Unknown",
                "connected_since": now,
            }
        _connected_devices[client_ip]["last_seen"] = now
        _clean_stale_locked()
        return True


def _clean_stale_locked():
    now = time.time()
    stale = [ip for ip, info in _connected_devices.items()
             if now - info["last_seen"] > CLIENT_TIMEOUT]
    for ip in stale:
        del _connected_devices[ip]


def _clean_blocked_locked():
    now = time.time()
    expired = [ip for ip, until in _blocked_ips.items() if now >= until]
    for ip in expired:
        del _blocked_ips[ip]


def get_connected_devices() -> list:
    with _lock:
        _clean_stale_locked()
        return list(_connected_devices.values())


def get_blocked_devices() -> list:
    with _lock:
        _clean_blocked_locked()
        now = time.time()
        return [
            {"ip": ip, "remaining_seconds": int(until - now)}
            for ip, until in _blocked_ips.items()
        ]


def unblock_device(device_ip: str) -> bool:
    with _lock:
        if device_ip in _blocked_ips:
            del _blocked_ips[device_ip]
            return True
        return False


def disconnect_device(device_ip: str) -> bool:
    with _lock:
        if device_ip in _connected_devices:
            del _connected_devices[device_ip]
            _blocked_ips[device_ip] = time.time() + BLOCK_DURATION
            return True
        return False


ACCESS_TOKEN = secrets.token_urlsafe(16)

import ctypes
import glob
import os
import platform
import subprocess
import threading
import time
from collections import deque

from utils.elevate import is_admin

_lock = threading.Lock()
_fps_value = None
_status = "Not started"

_proc = None
_proc_target_exe = None
_reader_thread = None
_stop_flag = threading.Event()

_FRAME_WINDOW = 30

_RETRY_INTERVAL = 5.0

_FPS_COLUMN_NAMES = ["msbetweenpresents", "frametime", "presentinterval", "timeinseconds"]

_CSV_HEADER = None
_FPS_COLUMN_IDX = None

_IGNORED_PROCESSES = {
    "explorer.exe", "bloomplay.exe", "python.exe", "pythonw.exe",
    "searchhost.exe", "shellexperiencehost.exe", "textinputhost.exe",
    "applicationframehost.exe", "systemsettings.exe",
}


def find_presentmon():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "libs"))
    matches = glob.glob(os.path.join(base_dir, "*presentmon*.exe")) + \
        glob.glob(os.path.join(base_dir, "*PresentMon*.exe"))
    matches = sorted(set(matches))
    return matches[0] if matches else None


def _get_foreground_process_name():
    if platform.system() != "Windows":
        return None
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None

        try:
            buf = ctypes.create_unicode_buffer(260)
            size = ctypes.c_ulong(260)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None
    return None


def _stop_presentmon():
    global _proc, _proc_target_exe, _CSV_HEADER, _FPS_COLUMN_IDX
    if _proc is not None:
        try:
            _proc.terminate()
        except Exception:
            pass
    _proc = None
    _proc_target_exe = None
    _CSV_HEADER = None
    _FPS_COLUMN_IDX = None


def _reader_loop():
    global _proc, _proc_target_exe, _fps_value, _status

    while not _stop_flag.is_set():
        presentmon_path = find_presentmon()
        if not presentmon_path:
            with _lock:
                _status = "No PresentMon*.exe found in libs/"
                _fps_value = None
            _stop_flag.wait(_RETRY_INTERVAL)
            continue

        if platform.system() == "Windows" and not is_admin():
            with _lock:
                _status = "Needs Administrator — PresentMon can't capture without it (restart BloomPlay elevated)"
                _fps_value = None
            _stop_flag.wait(_RETRY_INTERVAL)
            continue

        frame_times = deque(maxlen=_FRAME_WINDOW)

        while not _stop_flag.is_set():
            target = _get_foreground_process_name()

            if target is None or target.lower() in _IGNORED_PROCESSES:
                _stop_presentmon()
                with _lock:
                    _status = "Waiting for a game window to be focused"
                    _fps_value = None
                time.sleep(1.0)
                continue

            if target != _proc_target_exe:
                _stop_presentmon()
                frame_times.clear()
                try:
                    creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                    _proc = subprocess.Popen(
                        [
                            presentmon_path,
                            "--process_name", target,
                            "--output_stdout",
                            "--stop_existing_session",
                            "--terminate_on_proc_exit",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        creationflags=creationflags,
                    )
                    _proc_target_exe = target
                    with _lock:
                        _status = f"Capturing {target}"
                except Exception as e:
                    with _lock:
                        _status = f"Failed to start PresentMon: {e}"
                        _fps_value = None
                    time.sleep(2.0)
                    continue

            if _proc and _proc.stdout:
                line = _proc.stdout.readline()
                if line:
                    ms_between_presents = _parse_ms_between_presents(line)
                    if ms_between_presents and ms_between_presents > 0:
                        frame_times.append(ms_between_presents)
                        avg_ms = sum(frame_times) / len(frame_times)
                        with _lock:
                            _fps_value = round(1000.0 / avg_ms, 1)
                elif _proc.poll() is not None:
                    err = ""
                    try:
                        if _proc.stderr:
                            err = _proc.stderr.read(500).strip()
                    except Exception:
                        pass
                    _stop_presentmon()
                    with _lock:
                        _status = f"PresentMon exited: {err}" if err else "PresentMon exited (game closed or capture failed)"
                        _fps_value = None
                    time.sleep(1.0)


def _parse_ms_between_presents(line: str):
    global _CSV_HEADER, _FPS_COLUMN_IDX

    parts = line.strip().split(",")
    if not parts:
        return None

    if _CSV_HEADER is None:
        header_names = [p.strip().lower().strip('"') for p in parts]
        for i, col_name in enumerate(header_names):
            if col_name in _FPS_COLUMN_NAMES:
                _CSV_HEADER = parts
                _FPS_COLUMN_IDX = i
                break
        return None

    if _FPS_COLUMN_IDX is not None and _FPS_COLUMN_IDX < len(parts):
        try:
            return float(parts[_FPS_COLUMN_IDX])
        except (ValueError, IndexError):
            return None
    return None


def start_fps_thread():
    global _reader_thread
    if _reader_thread is not None and _reader_thread.is_alive():
        return
    _stop_flag.clear()
    _reader_thread = threading.Thread(target=_reader_loop, daemon=True, name="fps-worker")
    _reader_thread.start()


def get_fps():
    with _lock:
        return _fps_value


def get_fps_status() -> str:
    with _lock:
        return _status

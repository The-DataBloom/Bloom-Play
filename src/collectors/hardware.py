import platform
import psutil
from collectors.battery import get_battery_specs_windows

_IS_WINDOWS = platform.system() == "Windows"

pythoncom = None
wmi = None
GPUtil = None

if _IS_WINDOWS:
    try:
        import pythoncom
    except Exception:
        pythoncom = None
    try:
        import wmi
    except Exception:
        wmi = None

try:
    import GPUtil
except Exception:
    GPUtil = None


DEFAULTS = {
    "cpu": {
        "name": "Unknown",
        "brand": "Unknown",
        "cores": 0,
        "threads": 0,
        "base_clock": 0,
        "cache": "Unknown",
        "architecture": "Unknown",
    },
    "gpu": {
        "name": "Unknown",
        "vendor": "Unknown",
        "memory": "Unknown",
        "driver": "Unknown",
    },
    "ram": {
        "size": "Unknown",
        "type": "Unknown",
        "speed": 0,
        "brand": "Unknown",
        "form_factor": "Unknown",
        "slots": 0,
    },
    "system": {
        "os": "Unknown",
        "hostname": "Unknown",
        "arch": "Unknown",
        "kernel": "Unknown",
    },
    "bios": {"board": "Unknown", "bios": "Unknown", "serial": "Unknown"},
    "display": {
        "monitors": [],
        "primary_resolution": "Unknown",
        "refresh_rate": "Unknown",
        "adapter": "Unknown",
        "screen_size": "Unknown",
    },
    "audio": {
        "devices": [],
        "primary_device": "Unknown",
        "manufacturer": "Unknown",
    },
    "battery": {
        "name": "Unknown",
        "manufacturer": "Unknown",
        "design_capacity": "Unknown",
        "full_charge_capacity": "Unknown",
        "serial_number": "Unknown",
        "chemistry": "Unknown",
        "design_voltage": "Unknown",
        "device_id": "Unknown",
    },
}


def _init_com():
    if _IS_WINDOWS and pythoncom is not None:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass


def _get_cpu_info() -> dict:
    info = DEFAULTS["cpu"].copy()
    try:
        info["name"] = platform.processor() or "Unknown"
        info["cores"] = psutil.cpu_count(logical=False) or 0
        info["threads"] = psutil.cpu_count(logical=True) or 0
        info["architecture"] = platform.machine() or "Unknown"

        if _IS_WINDOWS and wmi is not None:
            try:
                w = wmi.WMI()
                cpu = w.Win32_Processor()[0]

                info["name"] = (cpu.Name or info["name"]).strip()
                max_clock = getattr(cpu, "MaxClockSpeed", 0) or 0
                info["base_clock"] = round(max_clock / 1000, 2) if max_clock else 0

                lname = info["name"].lower()
                if "intel" in lname:
                    info["brand"] = "Intel"
                elif "amd" in lname:
                    info["brand"] = "AMD"

                l2 = getattr(cpu, "L2CacheSize", 0) or 0
                l3 = getattr(cpu, "L3CacheSize", 0) or 0
                cache_parts = []
                if l2:
                    cache_parts.append(f"{l2}KB L2")
                if l3:
                    cache_parts.append(f"{l3}KB L3")
                if cache_parts:
                    info["cache"] = ", ".join(cache_parts)
            except Exception:
                pass

        if not info["base_clock"]:
            try:
                freq = psutil.cpu_freq()
                if freq and freq.max:
                    info["base_clock"] = round(freq.max / 1000, 2)
            except Exception:
                pass

        if info["brand"] == "Unknown":
            lname = info["name"].lower()
            if "intel" in lname:
                info["brand"] = "Intel"
            elif "amd" in lname:
                info["brand"] = "AMD"
            elif "apple" in lname or "arm" in lname:
                info["brand"] = "ARM"
    except Exception as e:
        print(f"[hardware] CPU error: {e}")
    return info


def _get_gpu_info() -> dict:
    info = DEFAULTS["gpu"].copy()
    try:
        if GPUtil is not None:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    g = gpus[0]
                    info["name"] = g.name or info["name"]
                    if g.memoryTotal:
                        info["memory"] = f"{round(g.memoryTotal)} MB"
                    info["driver"] = g.driver or info["driver"]
            except Exception:
                pass

        if _IS_WINDOWS and wmi is not None and info["name"] == "Unknown":
            try:
                w = wmi.WMI()
                for controller in w.Win32_VideoController():
                    name = (controller.Name or "").strip()
                    if name and "Microsoft" not in name and "Basic" not in name:
                        info["name"] = name
                        ram = getattr(controller, "AdapterRAM", 0) or 0
                        if ram:
                            info["memory"] = f"{round(ram / (1024 ** 3), 1)} GB"
                        driver = getattr(controller, "DriverVersion", "") or ""
                        if driver:
                            info["driver"] = driver
                        break
            except Exception:
                pass

        lname = info["name"].lower()
        if "nvidia" in lname:
            info["vendor"] = "NVIDIA"
        elif "amd" in lname or "radeon" in lname:
            info["vendor"] = "AMD"
        elif "intel" in lname:
            info["vendor"] = "Intel"
        elif "apple" in lname:
            info["vendor"] = "Apple"
    except Exception as e:
        print(f"[hardware] GPU error: {e}")
    return info


def _get_ram_info() -> dict:
    info = DEFAULTS["ram"].copy()
    try:
        total_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        info["size"] = f"{total_gb} GB"

        if _IS_WINDOWS and wmi is not None:
            try:
                w = wmi.WMI()
                memories = w.Win32_PhysicalMemory()
                if memories:
                    info["slots"] = len(memories)
                    first = memories[0]

                    manufacturer = (getattr(first, "Manufacturer", "") or "").strip()
                    if manufacturer:
                        info["brand"] = manufacturer

                    type_map = {
                        20: "DDR", 21: "DDR2", 24: "DDR3",
                        26: "DDR4", 34: "DDR5",
                    }
                    mem_type = getattr(first, "SMBIOSMemoryType", None)
                    info["type"] = type_map.get(mem_type, "Unknown")

                    speed = getattr(first, "Speed", None)
                    if speed:
                        info["speed"] = int(speed)

                    form_map = {8: "DIMM", 12: "SODIMM"}
                    form = getattr(first, "FormFactor", None)
                    info["form_factor"] = form_map.get(form, "Unknown")
            except Exception as e:
                print(f"[hardware] WMI RAM error: {e}")
    except Exception as e:
        print(f"[hardware] RAM error: {e}")
    return info


def _get_disk_type_by_drive_letter() -> dict:
    result = {}
    if not (_IS_WINDOWS and wmi is not None):
        return result

    media_by_index = {}
    model_by_index = {}
    try:
        w_storage = wmi.WMI(namespace="root\\Microsoft\\Windows\\Storage")
        for pd in w_storage.MSFT_PhysicalDisk():
            try:
                media_type = int(getattr(pd, "MediaType", 0) or 0)
                dtype = {3: "HDD", 4: "SSD"}.get(media_type, "Unknown")
                media_by_index[int(pd.DeviceId)] = dtype
            except Exception:
                continue
    except Exception:
        pass

    try:
        w = wmi.WMI()
        for disk in w.Win32_DiskDrive():
            try:
                idx = int(disk.Index)
            except Exception:
                continue

            model_str = (disk.Model or "").strip() if hasattr(disk, "Model") else ""
            model_by_index[idx] = model_str

            dtype = media_by_index.get(idx)
            if not dtype or dtype == "Unknown":
                model_upper = model_str.upper()
                media = (getattr(disk, "MediaType", "") or "").upper()
                if "SSD" in model_upper or "NVME" in model_upper or "SSD" in media:
                    dtype = "SSD"
                else:
                    dtype = dtype or "Unknown"

            try:
                for partition in disk.associators(wmi_result_class="Win32_DiskPartition"):
                    for logical in partition.associators(wmi_result_class="Win32_LogicalDisk"):
                        result[logical.DeviceID] = (dtype or "Unknown", model_str)
            except Exception:
                continue
    except Exception as e:
        print(f"[hardware] disk-type mapping error: {e}")

    return result


def _get_disk_info():
    disks = []
    total_storage = 0
    seen = set()

    disk_type_by_letter = _get_disk_type_by_drive_letter()

    try:
        for part in psutil.disk_partitions(all=False):
            try:
                opts = (part.opts or "").lower()
                if "cdrom" in opts or part.device in seen:
                    continue
                seen.add(part.device)
                usage = psutil.disk_usage(part.mountpoint)

                total_gb = round(usage.total / (1024 ** 3))
                total_storage += total_gb

                drive_letter = part.device.rstrip("\\").upper()
                dtype, dmodel = disk_type_by_letter.get(drive_letter, ("Unknown", ""))
                if dtype == "Unknown" and not _IS_WINDOWS:
                    fstype = (part.fstype or "").lower()
                    if "ssd" in fstype or "nvme" in fstype:
                        dtype = "SSD"

                disks.append({
                    "name": part.device,
                    "type": dtype,
                    "model": dmodel,
                    "total": total_gb,
                    "used": round(usage.used / (1024 ** 3)),
                    "free": round(usage.free / (1024 ** 3)),
                    "percent": round(usage.percent),
                })
            except PermissionError:
                continue
            except Exception as e:
                print(f"[hardware] Disk partition error: {e}")
    except Exception as e:
        print(f"[hardware] Storage error: {e}")

    return disks, f"{round(total_storage)} GB" if total_storage else "Unknown"


def _get_system_info() -> dict:
    info = DEFAULTS["system"].copy()
    try:
        info["os"] = f"{platform.system()} {platform.release()}".strip()
        info["hostname"] = platform.node() or "Unknown"
        info["arch"] = platform.machine() or "Unknown"
        try:
            if _IS_WINDOWS:
                info["kernel"] = platform.version() or "Unknown"
            else:
                info["kernel"] = platform.release() or "Unknown"
        except Exception:
            pass
    except Exception as e:
        print(f"[hardware] System error: {e}")
    return info


def _get_bios_info() -> dict:
    info = DEFAULTS["bios"].copy()
    if not (_IS_WINDOWS and wmi is not None):
        return info
    try:
        w = wmi.WMI()
        board = w.Win32_BaseBoard()[0]
        bios = w.Win32_BIOS()[0]
        info["board"] = f"{(board.Manufacturer or '').strip()} {(board.Product or '').strip()}".strip() or "Unknown"
        info["bios"] = bios.SMBIOSBIOSVersion or "Unknown"
        info["serial"] = getattr(board, "SerialNumber", "") or "Unknown"
    except Exception as e:
        print(f"[hardware] BIOS error: {e}")
    return info


def _get_display_info() -> dict:
    info = DEFAULTS["display"].copy()
    monitors = []

    if _IS_WINDOWS and wmi is not None:
        try:
            w = wmi.WMI()
            desktop_monitors = w.Win32_DesktopMonitor()
            for idx, dm in enumerate(desktop_monitors):
                try:
                    name = (dm.Name or "").strip() or (dm.MonitorManufacturerName or "").strip() or "Unknown"
                    sw = int(getattr(dm, "ScreenWidth", 0) or 0)
                    sh = int(getattr(dm, "ScreenHeight", 0) or 0)
                    resolution = f"{sw}x{sh}" if sw and sh else ""
                    ref_rate = int(getattr(dm, "RefreshRate", 0) or 0)
                    monitors.append({
                        "name": name,
                        "resolution": resolution,
                        "refresh_rate": f"{ref_rate} Hz" if ref_rate else "",
                        "primary": idx == 0,
                    })
                except Exception:
                    continue

            for vc in w.Win32_VideoController():
                try:
                    vc_name = (vc.Name or "").strip()
                    if not vc_name or "Microsoft" in vc_name or "Basic" in vc_name:
                        continue
                    csw = int(getattr(vc, "CurrentHorizontalResolution", 0) or 0)
                    csh = int(getattr(vc, "CurrentVerticalResolution", 0) or 0)
                    vc_res = f"{csw}x{csh}" if csw and csh else ""
                    vc_ref = int(getattr(vc, "CurrentRefreshRate", 0) or 0)

                    if monitors:
                        mon = monitors[0]
                        if not mon["resolution"] and vc_res:
                            mon["resolution"] = vc_res
                        if not mon["refresh_rate"] and vc_ref:
                            mon["refresh_rate"] = f"{vc_ref} Hz"
                        if mon["name"] == "Unknown" and vc_name:
                            mon["name"] = vc_name.split("(")[0].strip() if "(" in vc_name else vc_name
                    else:
                        monitors.append({
                            "name": vc_name.split("(")[0].strip() if "(" in vc_name else vc_name,
                            "resolution": vc_res,
                            "refresh_rate": f"{vc_ref} Hz" if vc_ref else "",
                            "primary": True,
                        })
                except Exception:
                    continue
        except Exception as e:
            print(f"[hardware] Display WMI error: {e}")

    if _IS_WINDOWS and (not monitors or not monitors[0].get("resolution")):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            sw = user32.GetSystemMetrics(0)
            sh = user32.GetSystemMetrics(1)
            if sw > 0 and sh > 0:
                res = f"{sw}x{sh}"
                if monitors:
                    if not monitors[0]["resolution"]:
                        monitors[0]["resolution"] = res
                    if not monitors[0]["name"] or monitors[0]["name"] == "Unknown":
                        monitors[0]["name"] = "Primary Display"
                else:
                    monitors.append({
                        "name": "Primary Display",
                        "resolution": res,
                        "refresh_rate": "",
                        "primary": True,
                    })
        except Exception:
            pass

    if not monitors:
        try:
            import tkinter as tk
            root = tk.Tk()
            try:
                root.withdraw()
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
                monitors.append({
                    "name": "Primary Display",
                    "resolution": f"{sw}x{sh}",
                    "refresh_rate": "Unknown",
                    "primary": True,
                })
            finally:
                root.destroy()
        except Exception:
            pass

    screen_size = "Unknown"
    if _IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            dc = user32.GetDC(0)
            if dc:
                try:
                    mm_w = gdi32.GetDeviceCaps(dc, 4)
                    mm_h = gdi32.GetDeviceCaps(dc, 6)
                    if mm_w > 0 and mm_h > 0:
                        diag_inches = ((mm_w ** 2 + mm_h ** 2) ** 0.5) / 25.4
                        screen_size = f"{diag_inches:.1f}\""
                finally:
                    user32.ReleaseDC(0, dc)
        except Exception:
            pass

    for m in monitors:
        for mk in ("name", "resolution", "refresh_rate"):
            if not m.get(mk):
                m[mk] = "Unknown"

    info["monitors"] = monitors
    info["screen_size"] = screen_size
    if monitors:
        primary = next((m for m in monitors if m.get("primary")), monitors[0])
        info["primary_resolution"] = primary.get("resolution") or "Unknown"
        info["refresh_rate"] = primary.get("refresh_rate") or "Unknown"
        info["adapter"] = primary.get("name") or "Unknown"

    return info


def _get_audio_info() -> dict:
    info = DEFAULTS["audio"].copy()
    devices = []

    if _IS_WINDOWS and wmi is not None:
        try:
            w = wmi.WMI()
            for sd in w.Win32_SoundDevice():
                try:
                    name = (sd.Name or "").strip()
                    if not name:
                        continue
                    manufacturer = (sd.Manufacturer or "").strip()
                    status = (sd.Status or "").strip()
                    clean_name = name.split("(")[0].strip() if "(" in name else name
                    devices.append({
                        "name": clean_name or name,
                        "manufacturer": manufacturer or "Unknown",
                        "status": status or "OK",
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"[hardware] Audio WMI error: {e}")

    info["devices"] = devices
    if devices:
        info["primary_device"] = devices[0]["name"]
        info["manufacturer"] = devices[0]["manufacturer"]

    return info


def _get_battery_info() -> dict:
    try:
        return get_battery_specs_windows()
    except Exception as e:
        print(f"[hardware] Battery error: {e}")
        return DEFAULTS["battery"].copy()


def get_hardware_info() -> dict:
    _init_com()

    disks, total_storage = _get_disk_info()

    return {
        "cpu": _get_cpu_info(),
        "gpu": _get_gpu_info(),
        "ram": _get_ram_info(),
        "disk": disks,
        "system": _get_system_info(),
        "bios": _get_bios_info(),
        "display": _get_display_info(),
        "audio": _get_audio_info(),
        "battery": _get_battery_info(),
        "total_storage": total_storage,
    }


PDF_SECTION_ACCENTS = {
    "Processor": "#60a5fa",
    "Graphics": "#a78bfa",
    "Memory": "#f472b6",
    "Storage": "#fbbf24",
    "System": "#22d3ee",
    "Motherboard": "#fb923c",
    "Display": "#34d399",
    "Audio": "#14b8a6",
    "Battery": "#84cc16",
}

_UNKNOWN_VALUES = {"", "unknown", "unknown device", "n/a", "none", "-", "—", "0", "0.0"}


def _pdf_clean(x):
    if x is None:
        return None
    s = str(x).strip()
    if not s or s.lower() in _UNKNOWN_VALUES:
        return None
    return s


def _pdf_add(rows, label, value):
    v = _pdf_clean(value)
    if v is not None:
        rows.append((label, v))


def build_pdf_sections(hw: dict, battery_stats: dict | None = None) -> list:
    hw = hw or {}
    sections = []

    cpu = hw.get("cpu", {}) or {}
    rows = []
    _pdf_add(rows, "Model", cpu.get("name"))
    _pdf_add(rows, "Brand", cpu.get("brand"))
    _pdf_add(rows, "Cores", cpu.get("cores"))
    _pdf_add(rows, "Threads", cpu.get("threads"))
    _pdf_add(rows, "Base Clock", cpu.get("base_clock"))
    _pdf_add(rows, "Boost Clock", cpu.get("boost_clock"))
    _pdf_add(rows, "Cache", cpu.get("cache"))
    _pdf_add(rows, "Architecture", cpu.get("architecture"))
    if rows:
        sections.append(("Processor", PDF_SECTION_ACCENTS["Processor"], rows))

    gpu = hw.get("gpu", {}) or {}
    rows = []
    _pdf_add(rows, "Model", gpu.get("name"))
    _pdf_add(rows, "Vendor", gpu.get("vendor"))
    _pdf_add(rows, "VRAM", gpu.get("memory"))
    _pdf_add(rows, "Driver", gpu.get("driver"))
    if rows:
        sections.append(("Graphics", PDF_SECTION_ACCENTS["Graphics"], rows))

    ram = hw.get("ram", {}) or {}
    rows = []
    _pdf_add(rows, "Total Size", ram.get("size"))
    _pdf_add(rows, "Type", ram.get("type"))
    _pdf_add(rows, "Speed", ram.get("speed"))
    _pdf_add(rows, "Brand", ram.get("brand"))
    _pdf_add(rows, "Form Factor", ram.get("form_factor"))
    _pdf_add(rows, "Slots", ram.get("slots"))
    if rows:
        sections.append(("Memory", PDF_SECTION_ACCENTS["Memory"], rows))

    disk_rows = []
    for d in hw.get("disk", []) or []:
        dname = _pdf_clean(d.get("model") or d.get("name"))
        if not dname:
            continue
        dtype = _pdf_clean(d.get("type"))
        dlabel = dname + (f"  ({dtype})" if dtype else "")
        try:
            dtotal = float(d.get("total", 0) or 0)
        except (TypeError, ValueError):
            dtotal = 0
        if dtotal <= 0:
            continue
        dused = d.get("used", 0)
        dpct = d.get("percent", 0)
        disk_rows.append((dlabel, f"{dused}/{dtotal:g} GB  ({dpct}%)"))
    total_storage = _pdf_clean(hw.get("total_storage"))
    if total_storage:
        disk_rows.append(("Total Storage", total_storage))
    if disk_rows:
        sections.append(("Storage", PDF_SECTION_ACCENTS["Storage"], disk_rows))

    sysi = hw.get("system", {}) or {}
    rows = []
    _pdf_add(rows, "Operating System", sysi.get("os"))
    _pdf_add(rows, "Hostname", sysi.get("hostname"))
    _pdf_add(rows, "Architecture", sysi.get("arch"))
    _pdf_add(rows, "Kernel", sysi.get("kernel"))
    if rows:
        sections.append(("System", PDF_SECTION_ACCENTS["System"], rows))

    bios = hw.get("bios", {}) or {}
    rows = []
    _pdf_add(rows, "Board", bios.get("board"))
    _pdf_add(rows, "BIOS", bios.get("bios"))
    _pdf_add(rows, "Serial", bios.get("serial"))
    if rows:
        sections.append(("Motherboard", PDF_SECTION_ACCENTS["Motherboard"], rows))

    disp = hw.get("display", {}) or {}
    disp_rows = []
    monitors = [m for m in disp.get("monitors", []) or [] if _pdf_clean(m.get("name"))]
    if monitors:
        multiple = len(monitors) > 1
        for i, m in enumerate(monitors):
            suffix = f" {i + 1}" if multiple else ""
            mname = _pdf_clean(m.get("name"))
            if mname:
                disp_rows.append((f"Monitor{suffix}", mname))
            _pdf_add(disp_rows, f"Resolution{suffix}", m.get("resolution"))
            _pdf_add(disp_rows, f"Refresh Rate{suffix}", m.get("refresh_rate"))
    else:
        _pdf_add(disp_rows, "Resolution", disp.get("primary_resolution"))
        _pdf_add(disp_rows, "Refresh Rate", disp.get("refresh_rate"))
    _pdf_add(disp_rows, "Screen Size", disp.get("screen_size"))
    if disp_rows:
        sections.append(("Display", PDF_SECTION_ACCENTS["Display"], disp_rows))

    aud = hw.get("audio", {}) or {}
    audio_rows = []
    for a in aud.get("devices", []) or []:
        aname = _pdf_clean(a.get("name"))
        if not aname:
            continue
        amfr = _pdf_clean(a.get("manufacturer"))
        astatus = _pdf_clean(a.get("status"))
        extra = " · ".join(x for x in (amfr, astatus) if x)
        audio_rows.append((aname, extra))
    if not audio_rows:
        pname = _pdf_clean(aud.get("primary_device"))
        if pname:
            audio_rows.append((pname, _pdf_clean(aud.get("manufacturer")) or ""))
    if audio_rows:
        sections.append(("Audio", PDF_SECTION_ACCENTS["Audio"], audio_rows))

    bat = hw.get("battery", {}) or {}
    bat_rows = []
    _pdf_add(bat_rows, "Name", bat.get("name"))
    _pdf_add(bat_rows, "Manufacturer", bat.get("manufacturer"))
    _pdf_add(bat_rows, "Design Capacity", bat.get("design_capacity"))
    _pdf_add(bat_rows, "Full Charge Capacity", bat.get("full_charge_capacity"))
    _pdf_add(bat_rows, "Chemistry", bat.get("chemistry"))
    _pdf_add(bat_rows, "Serial Number", bat.get("serial_number"))
    _pdf_add(bat_rows, "Design Voltage", bat.get("design_voltage"))
    stats = battery_stats or {}
    if stats.get("health_percent") is not None:
        hp = stats.get("health_percent")
        hl = _pdf_clean(stats.get("health_label"))
        bat_rows.append(("Health", f"{hp}%  ({hl})" if hl else f"{hp}%"))
    if stats.get("percent") is not None:
        bat_rows.append(("Charge Level", f"{stats['percent']}%"))
    if bat_rows:
        sections.append(("Battery", PDF_SECTION_ACCENTS["Battery"], bat_rows))

    return sections

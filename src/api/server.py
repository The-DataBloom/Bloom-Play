from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Literal, Optional, List

from api import state
from api import overlay_config
from engine import get_all_stats
from collectors.gpu import init_gpu
from collectors.network import start_ping_thread
from collectors.fps import start_fps_thread
from collectors.hardware import get_hardware_info, build_pdf_sections


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DASHBOARD_DIR = BASE_DIR / "dashboard"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_gpu()
    start_ping_thread()
    start_fps_thread()
    yield


app = FastAPI(title="BloomPlay API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_hardware_cache: dict | None = None


def _get_hardware_cached() -> dict:
    global _hardware_cache
    if _hardware_cache is None:
        _hardware_cache = get_hardware_info()
    return _hardware_cache


def _verify_token(token: str = Query(default=None)):
    if token != state.ACCESS_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing token")
    return True


@app.get("/stats", dependencies=[Depends(_verify_token)])
def stats(request: Request):
    allowed = state.touch(
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Device blocked")
    return get_all_stats()


@app.get("/hardware", dependencies=[Depends(_verify_token)])
def hardware(request: Request):
    allowed = state.touch(
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Device blocked")
    return _get_hardware_cached()


@app.get("/devices", dependencies=[Depends(_verify_token)])
def list_devices():
    return {"devices": state.get_connected_devices()}


@app.post("/devices/disconnect", dependencies=[Depends(_verify_token)])
def disconnect_device(ip: str = Query(...)):
    ok = state.disconnect_device(ip)
    return {"disconnected": ok}


@app.get("/devices/blocked", dependencies=[Depends(_verify_token)])
def list_blocked_devices():
    return {"blocked": state.get_blocked_devices()}


@app.post("/devices/unblock", dependencies=[Depends(_verify_token)])
def unblock_device(ip: str = Query(...)):
    ok = state.unblock_device(ip)
    return {"unblocked": ok}


class OverlayConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    color: Optional[str] = None
    position: Optional[str] = None
    font_size: Optional[int] = None
    font_family: Optional[str] = None
    fields: Optional[List[str]] = None
    hotkey: Optional[str] = None


@app.get("/overlay/config", dependencies=[Depends(_verify_token)])
def get_overlay_config():
    return {
        **overlay_config.get_config(),
        "available_fields": overlay_config.ALL_FIELDS,
        "available_positions": overlay_config.POSITIONS,
        "available_fonts": overlay_config.FONT_FAMILIES,
    }


@app.post("/overlay/config", dependencies=[Depends(_verify_token)])
def set_overlay_config(payload: OverlayConfigUpdate):
    return overlay_config.update_config(**payload.dict(exclude_unset=True))


@app.get("/health")
def health():
    return {"status": "ok"}


SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".bmp"}


def _screenshot_folder() -> Path:
    try:
        from PyQt5.QtCore import QSettings
        saved = QSettings("BloomPlay", "Settings").value("screenshot_path", "", type=str)
    except Exception:
        saved = ""
    if saved:
        return Path(saved)
    return Path.home() / "Pictures" / "BloomPlay"


class ScreenshotCaptureRequest(BaseModel):
    kind: Literal["full", "window"] = "full"


def _grab_screen(kind: str):
    from PIL import ImageGrab

    if kind == "window":
        bbox = _foreground_window_rect()
        if bbox is not None:
            try:
                return ImageGrab.grab(bbox=bbox)
            except Exception:
                pass
    return ImageGrab.grab()


def _foreground_window_rect():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


@app.post("/screenshot/capture", dependencies=[Depends(_verify_token)])
def capture_screenshot(payload: ScreenshotCaptureRequest, request: Request):
    import datetime

    allowed = state.touch(
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Device blocked")

    folder = _screenshot_folder()
    folder.mkdir(parents=True, exist_ok=True)

    try:
        img = _grab_screen(payload.kind)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Capture failed: {e}")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"Screenshot_{stamp}.png"
    path = folder / name
    try:
        img.save(str(path), "PNG")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save screenshot: {e}")
    return {"name": name, "path": str(path), "size": path.stat().st_size}


@app.get("/screenshot/list", dependencies=[Depends(_verify_token)])
def list_screenshots(request: Request):
    state.touch(
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    folder = _screenshot_folder()
    items = []
    if folder.exists():
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in SCREENSHOT_EXTS:
                try:
                    items.append({
                        "name": p.name,
                        "size": p.stat().st_size,
                        "mtime": int(p.stat().st_mtime),
                    })
                except Exception:
                    continue
    items.sort(key=lambda d: d["mtime"], reverse=True)
    return {"folder": str(folder), "screenshots": items, "total": len(items)}


@app.get("/screenshot/file", dependencies=[Depends(_verify_token)])
def get_screenshot_file(name: str = Query(...), request: Request = None):
    state.touch(
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    folder = _screenshot_folder()
    safe = Path(name).name
    path = folder / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)


class ScreenshotDeleteRequest(BaseModel):
    name: str


@app.post("/screenshot/delete", dependencies=[Depends(_verify_token)])
def delete_screenshot(payload: ScreenshotDeleteRequest, request: Request):
    state.touch(
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    folder = _screenshot_folder()
    safe = Path(payload.name).name
    path = folder / safe
    if path.is_file():
        try:
            path.unlink()
            return {"deleted": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"deleted": False}


@app.post("/export/pdf", dependencies=[Depends(_verify_token)])
def export_hardware_pdf(request: Request):
    state.touch(
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    hw = _get_hardware_cached()

    try:
        import io

        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF engine unavailable: {e}")

    sections = _pdf_sections(hw)
    pages = _render_pdf_pages(sections, ImageDraw, ImageFont, Image)
    if not pages:
        raise HTTPException(status_code=500, detail="PDF generation failed")

    buf = io.BytesIO()
    try:
        pages[0].save(buf, "PDF", save_all=True, append_images=pages[1:], resolution=120.0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    host = hw.get("system", {}).get("hostname", "PC")
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="BloomPlay_Hardware_{host}.pdf"'
        },
    )


def _pdf_sections(hw: dict) -> list:
    try:
        from collectors.battery import get_battery_stats as _get_bat
        stats_bat = _get_bat() or {}
    except Exception:
        stats_bat = {}
    return [(t, rows) for t, _accent, rows in build_pdf_sections(hw, battery_stats=stats_bat)]


def _pdf_font(size: int, bold: bool = False, ImageFont=None):
    if ImageFont is None:
        from PIL import ImageFont as _IF
        ImageFont = _IF
    regular = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold_paths = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf"]
    candidates = (bold_paths if bold else []) + regular
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _render_pdf_pages(sections, ImageDraw, ImageFont, Image):
    W, H = 1240, 1754
    MARGIN = 80
    CARD_PAD = 46
    LINE_H = 40

    import time as _time

    def _f(size, bold=False):
        return _pdf_font(size, bold=bold, ImageFont=ImageFont)

    brand_font = _f(20, bold=True)
    title_font = _f(44, bold=True)
    sub_font = _f(20)
    hdr_font = _f(25, bold=True)
    lbl_font = _f(19)
    val_font = _f(19, bold=True)
    foot_font = _f(16)

    BG = (255, 255, 255)
    CARD = (250, 250, 252)
    CARD_BORDER = (226, 232, 240)
    MUTED = (107, 114, 128)
    DARK = (17, 24, 39)

    SECTION_ACCENT = {
        "Processor": (96, 165, 250),
        "Graphics": (167, 139, 250),
        "Memory": (244, 114, 182),
        "Storage": (251, 191, 36),
        "System": (34, 211, 238),
        "Motherboard": (251, 146, 60),
        "Display": (52, 211, 153),
        "Audio": (20, 184, 166),
        "Battery": (132, 204, 22),
    }
    DEFAULT_ACCENT = (124, 58, 237)

    host = "PC"
    for title, rows in sections:
        if title == "System":
            for label, value in rows:
                if label == "Hostname":
                    host = value

    def _blend(c1, c2, t):
        return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

    def _rounded(x0, y0, x1, y1, r, fill=None, outline=None, width=1):
        if hasattr(d, "rounded_rectangle"):
            d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill,
                                outline=outline, width=width)
        else:
            d.rectangle([x0, y0, x1, y1], fill=fill, outline=outline)

    def _tw(text, font):
        if hasattr(d, "textlength"):
            return d.textlength(text, font=font)
        return d.textsize(text, font=font)[0]

    def _wrap(text, font, max_w):
        words = text.split(" ")
        lines, cur = [], ""
        for wd in words:
            if _tw(wd, font) > max_w:
                if cur:
                    lines.append(cur)
                    cur = ""
                while wd:
                    cut = len(wd)
                    while cut > 1 and _tw(wd[:cut], font) > max_w:
                        cut -= 1
                    lines.append(wd[:cut])
                    wd = wd[cut:]
                continue
            t = (cur + " " + wd).strip()
            if _tw(t, font) <= max_w or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines or [""]

    pages = []
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    page_no = 1

    def _new_page():
        nonlocal img, d, y, page_no
        t = f"BloomPlay · Hardware Report — Page {page_no}"
        fw = _tw(t, foot_font)
        d.text(((W - fw) / 2, H - 58), t, font=foot_font, fill=MUTED)
        pages.append(img)
        page_no += 1
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        y = MARGIN

    for i in range(0, 340):
        t = i / 340.0
        d.line([(0, i), (W, i)], fill=_blend((243, 244, 252), BG, min(1.0, t * 1.6)))
    d.text((MARGIN, 58), "BLOOMPLAY", font=brand_font, fill=(124, 58, 237))
    d.text((MARGIN, 100), "Hardware Report", font=title_font, fill=DARK)
    stamp = f"Host: {host}   ·   Generated {_time.strftime('%Y-%m-%d %H:%M')}"
    d.text((MARGIN, 168), stamp, font=sub_font, fill=MUTED)
    gy = 232
    colors = [(124, 108, 255), (255, 107, 157), (45, 212, 167)]
    seg = (W - 2 * MARGIN) / (len(colors) - 1)
    for i in range(len(colors) - 1):
        x0 = MARGIN + i * seg
        d.line([(x0, gy), (x0 + seg, gy)], fill=colors[i], width=7)
    y = 270

    card_w = W - 2 * MARGIN
    for title, rows in sections:
        accent = SECTION_ACCENT.get(title, DEFAULT_ACCENT)
        lbl_col = accent

        labels = [str(l) for l, _ in rows]
        label_w = max((_tw(l, lbl_font) for l in labels), default=220) + 40
        val_w = card_w - 2 * CARD_PAD - label_w

        rows_h = 0
        for _l, value in rows:
            v = str(value) if value not in (None, "") else "—"
            rows_h += len(_wrap(v, val_font, val_w)) * LINE_H
        card_h = CARD_PAD + 58 + rows_h + 26

        if y + card_h > H - 96:
            _new_page()

        x0, x1 = MARGIN, W - MARGIN
        _rounded(x0, y, x1, y + card_h, 24, fill=CARD, outline=CARD_BORDER, width=2)
        _rounded(x0 + 14, y + 18, x0 + 24, y + card_h - 18, 6, fill=accent)
        ty = y + 20
        d.text((x0 + CARD_PAD, ty), title.upper(), font=hdr_font, fill=accent)
        d.line([(x0 + CARD_PAD, ty + 46), (x1 - CARD_PAD, ty + 46)], fill=CARD_BORDER, width=2)
        ry = y + 20 + 58
        vx = x0 + CARD_PAD + label_w
        for label, value in rows:
            v = str(value) if value not in (None, "") else "—"
            d.text((x0 + CARD_PAD, ry), str(label), font=lbl_font, fill=lbl_col)
            for ln in _wrap(v, val_font, val_w):
                d.text((vx, ry), ln, font=val_font, fill=DARK)
                ry += LINE_H
        y += card_h + 26

    t = f"BloomPlay · Hardware Report — Page {page_no}"
    fw = _tw(t, foot_font)
    d.text(((W - fw) / 2, H - 58), t, font=foot_font, fill=MUTED)
    pages.append(img)
    return pages


@app.get("/system", dependencies=[Depends(_verify_token)])
def system_info():
    hw = _get_hardware_cached()
    return {
        "hostname": hw.get("system", {}).get("hostname", "PC"),
        "os": hw.get("system", {}).get("os", ""),
        "total_storage": hw.get("total_storage", ""),
    }


@app.post("/shutdown", dependencies=[Depends(_verify_token)])
def shutdown():
    import os
    import threading

    def _exit_soon():
        import time
        time.sleep(0.3)
        os._exit(0)

    threading.Thread(target=_exit_soon, daemon=True).start()
    return {"status": "shutting down"}


if DASHBOARD_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(DASHBOARD_DIR)),
        name="static",
    )


@app.get("/")
def dashboard():
    index_file = DASHBOARD_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(
            {
                "error": "dashboard/index.html not found",
                "dashboard_path": str(index_file),
            },
            status_code=404,
        )
    return FileResponse(index_file)

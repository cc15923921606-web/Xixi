"""Launch Xixi Studio as a single-instance Windows desktop application."""
from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from ctypes import wintypes

# pywebview's Windows backend calls platform.machine() while importing
# pythonnet. On this machine that system query can block indefinitely.
if sys.platform == "win32":
    platform.system = lambda: "Windows"  # type: ignore[assignment]
    platform.win32_ver = lambda: ("", "", "", "")  # type: ignore[assignment]
    platform.machine = lambda: "AMD64"  # type: ignore[assignment]

import webview
from webview.guilib import initialize as initialize_webview_gui

from app.runtime_paths import activate_runtime_environment, resolve_runtime_paths


def _edition_identity(public_release: bool) -> dict[str, object]:
    if public_release:
        return {
            "name": "public",
            "window_title": "昔夕",
            "call_overlay_title": "昔夕通话",
            "call_avatar_title": "昔夕",
            "mutex_name": r"Local\XixiStudioDesktopPublic",
            "app_user_model_id": "Xixi.Studio.Public",
            "studio_port": 8766,
            "startup_value_name": "XixiStudioPublic",
            "credential_service": "xixi-desktop-public",
        }
    return {
        "name": "personal",
        "window_title": "昔夕控制中心（个人版）",
        "call_overlay_title": "昔夕通话悬浮窗（个人版）",
        "call_avatar_title": "昔夕通话头像（个人版）",
        "mutex_name": r"Local\XixiStudioDesktopPersonal",
        "app_user_model_id": "Xixi.Studio.Personal",
        "studio_port": 8765,
        "startup_value_name": "XixiStudioPersonal",
        "credential_service": "xixi-ai-companion",
    }


IS_PUBLIC_RELEASE = bool(getattr(sys, "frozen", False))
EDITION = _edition_identity(IS_PUBLIC_RELEASE)
WINDOW_TITLE = str(EDITION["window_title"])
CALL_OVERLAY_TITLE = str(EDITION["call_overlay_title"])
CALL_AVATAR_BUBBLE_TITLE = str(EDITION["call_avatar_title"])
MUTEX_NAME = str(EDITION["mutex_name"])
ERROR_ALREADY_EXISTS = 183
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SPI_GETWORKAREA = 0x0030
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
LWA_ALPHA = 0x00000002
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
APP_USER_MODEL_ID = str(EDITION["app_user_model_id"])
ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
RUNTIME_PATHS = resolve_runtime_paths(
    ROOT,
    public_release=IS_PUBLIC_RELEASE,
)
activate_runtime_environment(RUNTIME_PATHS)


def _load_assistant_name() -> str:
    settings_path = RUNTIME_PATHS.data_dir / "studio_settings.json"
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return "昔夕"
    name = " ".join(str(payload.get("assistant_name") or "昔夕").split()).strip()
    return name[:24] or "昔夕"


ASSISTANT_NAME = _load_assistant_name()
WINDOW_TITLE = (
    ASSISTANT_NAME
    if IS_PUBLIC_RELEASE
    else f"{ASSISTANT_NAME}控制中心（个人版）"
)
CALL_OVERLAY_TITLE = (
    f"{ASSISTANT_NAME}通话"
    if IS_PUBLIC_RELEASE
    else f"{ASSISTANT_NAME}通话悬浮窗（个人版）"
)
CALL_AVATAR_BUBBLE_TITLE = (
    ASSISTANT_NAME
    if IS_PUBLIC_RELEASE
    else f"{ASSISTANT_NAME}通话头像（个人版）"
)
CREATE_NO_WINDOW = 0x08000000
STUDIO_PORT = int(EDITION["studio_port"])
STUDIO_URL = f"http://127.0.0.1:{STUDIO_PORT}"
CALL_OVERLAY_URL = f"{STUDIO_URL}/call_overlay.html"
CALL_OVERLAY_WIDTH = 380
CALL_OVERLAY_HEIGHT = 254
CALL_OVERLAY_COLLAPSED_SIZE = 64
CALL_OVERLAY_ANIMATION_SECONDS = 0.3
CALL_OVERLAY_CORNER_RADIUS = 12
CALL_OVERLAY_MIN_WIDTH = 320
CALL_OVERLAY_MIN_HEIGHT = 210
CALL_OVERLAY_MAX_WIDTH = 960
CALL_OVERLAY_MAX_HEIGHT = 760
CALL_OVERLAY_RESIZE_EDGES = frozenset({
    "west",
    "east",
    "north",
    "north-west",
    "north-east",
    "south",
    "south-west",
    "south-east",
})
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
CALL_OVERLAY_THEME_KEYS = frozenset({
    "canvas",
    "surface",
    "surface-soft",
    "surface-strong",
    "ink",
    "ink-strong",
    "muted",
    "line",
    "line-soft",
    "accent",
    "accent-deep",
    "accent-soft",
    "blue",
    "danger",
})
WEBVIEW2_BACKGROUND_FLAGS = (
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
)

logger = logging.getLogger("xixi_desktop")
PREFERENCES_PATH = RUNTIME_PATHS.data_dir / "desktop_preferences.json"
DEFAULT_PREFERENCES = {
    "close_to_tray": False,
    "start_with_windows": False,
    "remember_window": True,
    "microphone_enabled": None,
    "x": None,
    "y": None,
    "width": 1440,
    "height": 900,
    "maximized": True,
    "call_overlay_width": CALL_OVERLAY_WIDTH,
    "call_overlay_height": CALL_OVERLAY_HEIGHT,
    "call_overlay_opacity": 1.0,
}
STARTUP_VALUE_NAME = str(EDITION["startup_value_name"])


def _configure_frozen_release_environment() -> None:
    """Keep a packaged public install isolated and lightweight on first run."""
    if not getattr(sys, "frozen", False):
        return

    public_edition = _edition_identity(True)
    os.environ["XIXI_EDITION"] = "public"
    os.environ["XIXI_CREDENTIAL_SERVICE"] = str(public_edition["credential_service"])
    os.environ.setdefault("XIXI_STUDIO_PORT", str(public_edition["studio_port"]))
    napcat_root = RUNTIME_PATHS.components_dir / "NapCat"
    legacy_napcat_root = ROOT / "runtime" / "NapCat"
    if not napcat_root.exists() and legacy_napcat_root.exists():
        napcat_root = legacy_napcat_root
    os.environ["NAPCAT_ROOT"] = str(napcat_root)
    voice_root = RUNTIME_PATHS.components_dir / "GPT-SoVITS"
    legacy_voice_root = ROOT / "runtime" / "GPT-SoVITS"
    if not voice_root.exists() and legacy_voice_root.exists():
        voice_root = legacy_voice_root
    os.environ["GPT_SOVITS_ROOT"] = str(voice_root)
    os.environ.setdefault("WHISPER_DEVICE", "cpu")
    os.environ.setdefault("WHISPER_COMPUTE_TYPE", "int8")
    os.environ.setdefault("WHISPER_FALLBACK_COMPUTE_TYPE", "int8")
    if (RUNTIME_PATHS.data_dir / "studio_settings.json").is_file():
        os.environ.pop("XIXI_IGNORE_SAVED_MODEL_CREDENTIALS", None)
        return

    first_run_defaults = {
        "BRAIN_ENABLED": "0",
        "VOICE_ENABLED": "0",
        "VISION_ENABLED": "0",
        "LEARNING_ENABLED": "0",
        "INTEREST_REFLECTION_ENABLED": "0",
        "ANIME_LEARNING_ENABLED": "0",
        "KNOWLEDGE_REFLECTION_ENABLED": "0",
        "AUTONOMOUS_GROUP_ENABLED": "0",
        "AUTONOMOUS_PRIVATE_ENABLED": "0",
        "QQ_ENABLED": "0",
        "USE_OPENAI": "0",
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URL": "",
        "OPENAI_MODEL": "",
        "LANGUAGE_API_TYPE": "auto",
        "VISION_API_KEY": "",
        "VISION_BASE_URL": "",
        "VISION_MODEL": "",
        "VISION_API_TYPE": "auto",
        "OWNER_DISPLAY_NAME": "主人",
        "OWNER_RELATIONSHIP": "重要的人",
        "OWNER_ADDRESSES": "主人",
        "SETUP_COMPLETE": "0",
        "XIXI_IGNORE_SAVED_MODEL_CREDENTIALS": "1",
    }
    for name, value in first_run_defaults.items():
        os.environ[name] = value


def _window_position_is_visible(x: object, y: object, width: object, height: object) -> bool:
    """Return whether a saved window has a usable area on any current display."""
    try:
        left = int(x)
        top = int(y)
        window_width = max(1, int(width))
        window_height = max(1, int(height))
    except (TypeError, ValueError):
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    virtual_left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    virtual_top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    virtual_right = virtual_left + user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    virtual_bottom = virtual_top + user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    overlap_width = min(left + window_width, virtual_right) - max(left, virtual_left)
    overlap_height = min(top + window_height, virtual_bottom) - max(top, virtual_top)
    return overlap_width >= min(160, window_width) and overlap_height >= min(100, window_height)


def _load_preferences() -> dict[str, object]:
    preferences = dict(DEFAULT_PREFERENCES)
    try:
        saved = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            preferences.update({key: saved[key] for key in preferences.keys() & saved.keys()})
    except FileNotFoundError:
        pass
    except Exception:
        logger.exception("could not load desktop preferences")
    # Closing the desktop window always exits the application. Keep this
    # migration here so an older saved preference cannot restore tray mode.
    preferences["close_to_tray"] = False
    if not isinstance(preferences.get("microphone_enabled"), bool):
        preferences["microphone_enabled"] = None
    has_saved_position = preferences.get("x") is not None and preferences.get("y") is not None
    if preferences.get("remember_window") and has_saved_position and not _window_position_is_visible(
        preferences.get("x"),
        preferences.get("y"),
        preferences.get("width"),
        preferences.get("height"),
    ):
        logger.warning(
            "saved window position is outside current displays; using the default position"
        )
        preferences["x"] = None
        preferences["y"] = None
    try:
        preferences["call_overlay_width"] = min(
            CALL_OVERLAY_MAX_WIDTH,
            max(CALL_OVERLAY_MIN_WIDTH, int(preferences["call_overlay_width"])),
        )
        preferences["call_overlay_height"] = min(
            CALL_OVERLAY_MAX_HEIGHT,
            max(CALL_OVERLAY_MIN_HEIGHT, int(preferences["call_overlay_height"])),
        )
    except (TypeError, ValueError):
        preferences["call_overlay_width"] = CALL_OVERLAY_WIDTH
        preferences["call_overlay_height"] = CALL_OVERLAY_HEIGHT
    try:
        preferences["call_overlay_opacity"] = min(
            1.0,
            max(0.45, float(preferences["call_overlay_opacity"])),
        )
    except (TypeError, ValueError):
        preferences["call_overlay_opacity"] = 1.0
    return preferences


def _save_preferences(preferences: dict[str, object]) -> None:
    preferences["close_to_tray"] = False
    PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PREFERENCES_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(PREFERENCES_PATH)


def _set_webview_microphone_permission(window: webview.Window | None, enabled: bool) -> bool:
    """Apply the stored microphone choice to the active WebView2 profile."""
    native = getattr(window, "native", None) if window else None
    if native is None or getattr(native, "IsDisposed", False):
        return False

    ready = threading.Event()
    outcome: dict[str, object] = {}

    def begin_update() -> None:
        try:
            from Microsoft.Web.WebView2.Core import (
                CoreWebView2PermissionKind,
                CoreWebView2PermissionState,
            )

            browser = getattr(native, "browser", None)
            control = getattr(browser, "webview", None)
            core = getattr(control, "CoreWebView2", None)
            if core is None:
                raise RuntimeError("WebView2 尚未准备好")
            state = (
                CoreWebView2PermissionState.Allow
                if enabled
                else CoreWebView2PermissionState.Deny
            )
            outcome["task"] = core.Profile.SetPermissionStateAsync(
                CoreWebView2PermissionKind.Microphone,
                STUDIO_URL,
                state,
            )
        except Exception as exc:
            outcome["error"] = exc
        finally:
            ready.set()

    try:
        if bool(getattr(native, "InvokeRequired", False)):
            from System import Action

            native.BeginInvoke(Action(begin_update))
        else:
            begin_update()
    except Exception:
        logger.exception("could not schedule WebView2 microphone permission update")
        return False

    if not ready.wait(5):
        logger.warning("WebView2 microphone permission update did not start in time")
        return False
    if outcome.get("error") is not None:
        logger.warning("could not update WebView2 microphone permission: %s", outcome["error"])
        return False

    task = outcome.get("task")
    try:
        if task is not None and not bool(task.Wait(5000)):
            logger.warning("WebView2 microphone permission update timed out")
            return False
    except Exception:
        logger.exception("WebView2 microphone permission update failed")
        return False
    return True


def _set_app_user_model_id() -> None:
    """Give the desktop window its own taskbar identity instead of Python's."""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    setter = shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [wintypes.LPCWSTR]
    setter.restype = wintypes.LONG
    setter(APP_USER_MODEL_ID)


def _configure_webview_background_runtime() -> str:
    """Keep microphone processing alive while the desktop window is minimized."""
    variable = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"
    existing = os.environ.get(variable, "").strip()
    arguments = existing.split() if existing else []
    for flag in WEBVIEW2_BACKGROUND_FLAGS:
        if flag not in arguments:
            arguments.append(flag)
    value = " ".join(arguments)
    os.environ[variable] = value
    return value


def _user32_window_api() -> ctypes.WinDLL:
    """Return user32 with pointer-safe signatures for native window helpers."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    user32.SetWindowRgn.restype = ctypes.c_int
    user32.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE]
    user32.GetWindowRgn.restype = ctypes.c_int
    user32.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND,
        wintypes.COLORREF,
        wintypes.BYTE,
        wintypes.DWORD,
    ]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    user32.EnableWindow.restype = wintypes.BOOL
    user32.IsWindowEnabled.argtypes = [wintypes.HWND]
    user32.IsWindowEnabled.restype = wintypes.BOOL
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SystemParametersInfoW.argtypes = [
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    user32.SystemParametersInfoW.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    try:
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        user32.GetDpiForWindow.restype = wintypes.UINT
    except AttributeError:
        pass
    return user32


def _round_call_overlay_window(title: str = CALL_OVERLAY_TITLE) -> bool:
    """Clip the expanded WebView window so its desktop corners are truly rounded."""
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    width = max(1, int(rect.right - rect.left))
    height = max(1, int(rect.bottom - rect.top))

    try:
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        corner_preference = ctypes.c_int(DWMWCP_ROUND)
        if dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner_preference),
            ctypes.sizeof(corner_preference),
        ) == 0:
            # A custom GDI region disables Windows 11's antialiased DWM corners.
            user32.SetWindowRgn(hwnd, None, True)
            return True
    except (AttributeError, OSError):
        logger.debug("DWM rounded corners are unavailable; using the GDI fallback")

    try:
        dpi = max(96, int(user32.GetDpiForWindow(hwnd)))
    except (AttributeError, OSError, TypeError, ValueError):
        dpi = 96
    if width <= 96 and height <= 96:
        ellipse_width = width
        ellipse_height = height
    else:
        diameter = max(2, round(CALL_OVERLAY_CORNER_RADIUS * 2 * dpi / 96))
        ellipse_width = diameter
        ellipse_height = diameter

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi32.CreateRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    gdi32.CreateRectRgn.restype = wintypes.HANDLE
    gdi32.CreateRoundRectRgn.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE
    gdi32.GetRgnBox.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.RECT)]
    gdi32.GetRgnBox.restype = ctypes.c_int
    gdi32.PtInRegion.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int]
    gdi32.PtInRegion.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL

    current_region = gdi32.CreateRectRgn(0, 0, 0, 0)
    if current_region:
        try:
            region_type = user32.GetWindowRgn(hwnd, current_region)
            region_box = wintypes.RECT()
            gdi32.GetRgnBox(current_region, ctypes.byref(region_box))
            matching_bounds = (
                abs(int(region_box.right - region_box.left) - width) <= 1
                and abs(int(region_box.bottom - region_box.top) - height) <= 1
            )
            corners_are_clipped = all(
                not gdi32.PtInRegion(current_region, x, y)
                for x, y in (
                    (0, 0),
                    (max(0, width - 1), 0),
                    (0, max(0, height - 1)),
                    (max(0, width - 1), max(0, height - 1)),
                )
            )
            if region_type in {2, 3} and matching_bounds and corners_are_clipped:
                return True
        finally:
            gdi32.DeleteObject(current_region)

    region = gdi32.CreateRoundRectRgn(
        0,
        0,
        width + 1,
        height + 1,
        ellipse_width,
        ellipse_height,
    )
    if not region:
        return False
    if user32.SetWindowRgn(hwnd, region, True):
        return True
    gdi32.DeleteObject(region)
    return False


def _set_window_opacity(title: str, opacity: float) -> bool:
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    normalized = min(1.0, max(0.45, float(opacity)))
    extended_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, extended_style | WS_EX_LAYERED)
    return bool(user32.SetLayeredWindowAttributes(
        hwnd,
        0,
        round(normalized * 255),
        LWA_ALPHA,
    ))


def _call_overlay_resize_bounds(
    edge: str,
    start_bounds: tuple[int, int, int, int],
    start_cursor: tuple[int, int],
    current_cursor: tuple[int, int],
    desktop_bounds: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    x, y, width, height = start_bounds
    desktop_left, desktop_top, desktop_right, desktop_bottom = desktop_bounds
    left, top, right, bottom = x, y, x + width, y + height
    delta_x = int(current_cursor[0]) - int(start_cursor[0])
    delta_y = int(current_cursor[1]) - int(start_cursor[1])
    if edge in {"west", "north-west", "south-west"}:
        left = max(desktop_left, right - CALL_OVERLAY_MAX_WIDTH, min(left + delta_x, right - CALL_OVERLAY_MIN_WIDTH))
    if edge in {"east", "north-east", "south-east"}:
        right = min(desktop_right, left + CALL_OVERLAY_MAX_WIDTH, max(right + delta_x, left + CALL_OVERLAY_MIN_WIDTH))
    if edge in {"north", "north-west", "north-east"}:
        top = max(desktop_top, bottom - CALL_OVERLAY_MAX_HEIGHT, min(top + delta_y, bottom - CALL_OVERLAY_MIN_HEIGHT))
    if edge in {"south", "south-west", "south-east"}:
        bottom = min(desktop_bottom, top + CALL_OVERLAY_MAX_HEIGHT, max(bottom + delta_y, top + CALL_OVERLAY_MIN_HEIGHT))
    return left, top, max(1, right - left), max(1, bottom - top)


def _ensure_window_interactive(title: str) -> bool:
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    user32.EnableWindow(hwnd, True)
    return bool(user32.IsWindowEnabled(hwnd))


def _show_webview_window_preserving_placement(window: webview.Window, title: str) -> None:
    """Show a hidden window without forcing a maximized window back to normal bounds."""
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    was_minimized = bool(hwnd and user32.IsIconic(hwnd))
    window.show()
    if not hwnd:
        hwnd = user32.FindWindowW(None, title)
    if hwnd and was_minimized:
        user32.ShowWindow(hwnd, SW_RESTORE)


class NativeCallAvatarBubble:
    """A WebView-free circular avatar window for the collapsed call state."""

    def __init__(self, avatar_path: Path, on_activate) -> None:
        self._avatar_path = avatar_path
        self._on_activate = on_activate
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._form = None
        self._action_type = None
        self._point_type = None
        self._size_type = None
        self._region_type = None
        self._graphics_path_type = None
        self._application = None
        self._closed = False
        self._requested_visible = False
        self._x = 24
        self._y = 24
        self._width = CALL_OVERLAY_COLLAPSED_SIZE
        self._height = CALL_OVERLAY_COLLAPSED_SIZE

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._closed = False
            self._thread = threading.Thread(
                target=self._run,
                name="xixi-native-call-avatar",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)
            import clr

            clr.AddReference("System")
            clr.AddReference("System.Drawing")
            clr.AddReference("System.Windows.Forms")
            from System import Action
            from System.Drawing import Bitmap, Point, Region, Size
            from System.Drawing.Drawing2D import GraphicsPath
            from System.Windows.Forms import (
                Application,
                ApplicationContext,
                AutoScaleMode,
                Control,
                Cursors,
                Form,
                FormBorderStyle,
                FormStartPosition,
                ImageLayout,
                MouseButtons,
            )

            form = Form()
            form.Text = CALL_AVATAR_BUBBLE_TITLE
            form.AutoScaleMode = getattr(AutoScaleMode, "None")
            form.FormBorderStyle = getattr(FormBorderStyle, "None")
            form.ShowInTaskbar = False
            form.TopMost = True
            form.StartPosition = FormStartPosition.Manual
            form.Cursor = Cursors.Hand
            form.BackgroundImageLayout = ImageLayout.Stretch
            bitmap = Bitmap(str(self._avatar_path))
            form.BackgroundImage = bitmap
            drag: dict[str, object] = {}

            def apply_shape(width: int, height: int) -> None:
                form.ClientSize = Size(max(1, int(width)), max(1, int(height)))
                path = GraphicsPath()
                path.AddEllipse(0, 0, form.ClientSize.Width, form.ClientSize.Height)
                previous = form.Region
                form.Region = Region(path)
                path.Dispose()
                if previous is not None:
                    previous.Dispose()

            def apply_no_activate_style() -> None:
                hwnd = wintypes.HWND(form.Handle.ToInt64())
                user32 = _user32_window_api()
                style = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
                user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                )
                user32.SetWindowPos(
                    hwnd,
                    HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                )

            def mouse_down(_sender, event) -> None:
                if event.Button != MouseButtons.Left:
                    return
                cursor = Control.MousePosition
                location = form.Location
                drag.clear()
                drag.update({
                    "start_x": int(cursor.X),
                    "start_y": int(cursor.Y),
                    "window_x": int(location.X),
                    "window_y": int(location.Y),
                    "moved": False,
                })
                form.Capture = True

            def mouse_move(_sender, event) -> None:
                if not drag or event.Button != MouseButtons.Left:
                    return
                cursor = Control.MousePosition
                delta_x = int(cursor.X) - int(drag["start_x"])
                delta_y = int(cursor.Y) - int(drag["start_y"])
                if not drag["moved"] and (delta_x * delta_x + delta_y * delta_y) < 25:
                    return
                drag["moved"] = True
                target_x, target_y = _clamp_window_position(
                    int(drag["window_x"]) + delta_x,
                    int(drag["window_y"]) + delta_y,
                    int(form.Width),
                    int(form.Height),
                    _virtual_desktop_bounds(),
                )
                form.Location = Point(target_x, target_y)
                with self._lock:
                    self._x = target_x
                    self._y = target_y

            def mouse_up(_sender, event) -> None:
                if event.Button != MouseButtons.Left or not drag:
                    return
                moved = bool(drag.get("moved"))
                drag.clear()
                form.Capture = False
                if moved:
                    return
                with self._lock:
                    self._requested_visible = False
                form.Hide()
                threading.Thread(
                    target=self._on_activate,
                    name="xixi-native-call-avatar-open",
                    daemon=True,
                ).start()

            form.MouseDown += mouse_down
            form.MouseMove += mouse_move
            form.MouseUp += mouse_up
            apply_shape(self._width, self._height)
            form.Location = Point(self._x, self._y)
            _ = form.Handle
            apply_no_activate_style()
            context = ApplicationContext()
            with self._lock:
                self._form = form
                self._action_type = Action
                self._point_type = Point
                self._size_type = Size
                self._region_type = Region
                self._graphics_path_type = GraphicsPath
                self._application = Application
            self._ready.set()
            with self._lock:
                requested_visible = self._requested_visible
            if requested_visible:
                form.Show()
                apply_no_activate_style()
            Application.Run(context)
            form.MouseDown -= mouse_down
            form.MouseMove -= mouse_move
            form.MouseUp -= mouse_up
            form.Close()
            bitmap.Dispose()
        except Exception:
            logger.exception("native call avatar failed")
        finally:
            with self._lock:
                self._form = None
                self._application = None
                self._region_type = None
                self._graphics_path_type = None
            self._ready.set()
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass

    def _invoke(self, action) -> bool:
        if not self._ready.wait(3):
            return False
        with self._lock:
            form = self._form
            action_type = self._action_type
        if form is None or action_type is None or form.IsDisposed:
            return False
        try:
            form.BeginInvoke(action_type(action))
            return True
        except Exception:
            logger.debug("could not update native call avatar", exc_info=True)
            return False

    def show_at(self, x: int, y: int, width: int, height: int) -> bool:
        with self._lock:
            self._requested_visible = True
            self._x = int(x)
            self._y = int(y)
            self._width = max(1, int(width))
            self._height = max(1, int(height))

        def show() -> None:
            with self._lock:
                form = self._form
                point = self._point_type
                size = self._size_type
                region_type = self._region_type
                graphics_path_type = self._graphics_path_type
                position = (self._x, self._y)
                dimensions = (self._width, self._height)
            if (
                form is None
                or point is None
                or size is None
                or region_type is None
                or graphics_path_type is None
            ):
                return
            form.ClientSize = size(*dimensions)
            path = graphics_path_type()
            path.AddEllipse(0, 0, form.ClientSize.Width, form.ClientSize.Height)
            previous = form.Region
            form.Region = region_type(path)
            path.Dispose()
            if previous is not None:
                previous.Dispose()
            form.Location = point(*position)
            if not form.Visible:
                form.Show()
            hwnd = wintypes.HWND(form.Handle.ToInt64())
            user32 = _user32_window_api()
            style = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            )
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )

        return self._invoke(show)

    def hide(self) -> bool:
        with self._lock:
            self._requested_visible = False
        return self._invoke(lambda: self._form.Hide() if self._form is not None else None)

    def position(self) -> tuple[int, int, int, int]:
        with self._lock:
            return self._x, self._y, self._width, self._height

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._requested_visible = False

        def shutdown() -> None:
            if self._form is not None:
                self._form.Hide()
            if self._application is not None:
                self._application.ExitThread()

        self._invoke(shutdown)


def _window_hidden_or_minimized(title: str) -> bool:
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    return not hwnd or not user32.IsWindowVisible(hwnd) or bool(user32.IsIconic(hwnd))


def _set_window_visible_without_focus(title: str, visible: bool) -> bool:
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    if not visible:
        user32.ShowWindow(hwnd, SW_HIDE)
        return True
    if title == CALL_OVERLAY_TITLE:
        _ensure_window_interactive(title)
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
    )
    if title == CALL_OVERLAY_TITLE:
        _round_call_overlay_window(title)
    return True


def _resize_window_without_focus(
    title: str,
    width: int,
    height: int,
    *,
    visible: bool,
) -> bool:
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    flags = SWP_NOMOVE | SWP_NOACTIVATE
    if visible:
        flags |= SWP_SHOWWINDOW
    resized = bool(user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0,
        0,
        max(1, int(width)),
        max(1, int(height)),
        flags,
    ))
    if resized and title == CALL_OVERLAY_TITLE:
        _round_call_overlay_window(title)
    return resized


def _set_window_bounds_without_focus(
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    visible: bool,
) -> bool:
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    flags = SWP_NOACTIVATE
    if visible:
        flags |= SWP_SHOWWINDOW
    positioned = bool(user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        int(x),
        int(y),
        max(1, int(width)),
        max(1, int(height)),
        flags,
    ))
    if positioned and title == CALL_OVERLAY_TITLE:
        _round_call_overlay_window(title)
    return positioned


def _window_bounds(title: str) -> tuple[int, int, int, int] | None:
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return (
        int(rect.left),
        int(rect.top),
        max(1, int(rect.right - rect.left)),
        max(1, int(rect.bottom - rect.top)),
    )


def _virtual_desktop_bounds() -> tuple[int, int, int, int]:
    user32 = _user32_window_api()
    left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    if width > 0 and height > 0:
        return left, top, left + width, top + height
    work_area = wintypes.RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0):
        return (
            int(work_area.left),
            int(work_area.top),
            int(work_area.right),
            int(work_area.bottom),
        )
    return 0, 0, 1920, 1080


def _clamp_window_position(
    x: int,
    y: int,
    width: int,
    height: int,
    desktop_bounds: tuple[int, int, int, int],
) -> tuple[int, int]:
    left, top, right, bottom = desktop_bounds
    max_x = max(left, right - max(1, int(width)))
    max_y = max(top, bottom - max(1, int(height)))
    return min(max(int(x), left), max_x), min(max(int(y), top), max_y)


def _animate_window_resize_without_focus(
    title: str,
    target_width: int,
    target_height: int,
    *,
    duration_seconds: float = CALL_OVERLAY_ANIMATION_SECONDS,
) -> bool:
    user32 = _user32_window_api()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    start_width = max(1, int(rect.right - rect.left))
    start_height = max(1, int(rect.bottom - rect.top))
    target_width = max(1, int(target_width))
    target_height = max(1, int(target_height))
    duration_seconds = max(0.01, float(duration_seconds))
    started_at = time.perf_counter()
    while True:
        progress = min(1.0, (time.perf_counter() - started_at) / duration_seconds)
        eased = 1.0 - pow(1.0 - progress, 4)
        width = round(start_width + (target_width - start_width) * eased)
        height = round(start_height + (target_height - start_height) * eased)
        _resize_window_without_focus(title, width, height, visible=True)
        if progress >= 1.0:
            break
        time.sleep(1 / 60)
    return True


def _call_overlay_position(width: int, height: int) -> tuple[int, int]:
    user32 = _user32_window_api()
    work_area = wintypes.RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0):
        return max(work_area.left, work_area.right - width - 24), max(
            work_area.top,
            work_area.bottom - height - 24,
        )
    return 24, 24


def _should_show_call_overlay(payload: dict[str, object], main_window_hidden: bool) -> bool:
    return bool(payload.get("active")) and (
        bool(payload.get("minimized")) or main_window_hidden
    )


def _call_overlay_menu_visible(payload: dict[str, object]) -> bool:
    return bool(payload.get("active"))


def _set_window_icon(icon_path: Path) -> bool:
    """Apply the Xixi icon to the native window used by the EdgeChromium backend."""
    if not icon_path.is_file():
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.LoadImageW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM

    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    big_icon = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
    small_icon = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
    if big_icon:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big_icon)
    if small_icon:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small_icon)
    return bool(big_icon or small_icon)


def _set_startup(enabled: bool) -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    if getattr(sys, "frozen", False):
        command = subprocess.list2cmdline([str(Path(sys.executable).resolve())])
    else:
        pythonw = ROOT / "venv" / "Scripts" / "pythonw.exe"
        executable = pythonw if pythonw.is_file() else Path(sys.executable)
        command = subprocess.list2cmdline([str(executable), str(Path(__file__).resolve())])
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, STARTUP_VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass


class DesktopApi:
    def __init__(self, preferences: dict[str, object]) -> None:
        self._preferences = preferences
        self._window: webview.Window | None = None
        self._call_overlay_window: webview.Window | None = None
        self._avatar_bubble: NativeCallAvatarBubble | None = None
        self._call_overlay_lock = threading.RLock()
        self._call_overlay_animation_lock = threading.Lock()
        self._call_overlay_resize_lock = threading.Lock()
        self._call_overlay_collapsed = False
        self._call_overlay_width = min(
            CALL_OVERLAY_MAX_WIDTH,
            max(CALL_OVERLAY_MIN_WIDTH, int(preferences.get("call_overlay_width", CALL_OVERLAY_WIDTH))),
        )
        self._call_overlay_height = min(
            CALL_OVERLAY_MAX_HEIGHT,
            max(CALL_OVERLAY_MIN_HEIGHT, int(preferences.get("call_overlay_height", CALL_OVERLAY_HEIGHT))),
        )
        self._call_overlay_opacity = min(
            1.0,
            max(0.45, float(preferences.get("call_overlay_opacity", 1.0))),
        )
        self._call_overlay_state: dict[str, object] = {
            "active": False,
            "minimized": False,
            "assistant_name": ASSISTANT_NAME,
            "status": "通话中",
            "duration": "00:00",
            "entries": [],
            "theme": {},
        }

    def bind_windows(self, window: webview.Window, call_overlay: webview.Window) -> None:
        self._window = window
        self._call_overlay_window = call_overlay

    def bind_avatar_bubble(self, avatar_bubble: NativeCallAvatarBubble) -> None:
        self._avatar_bubble = avatar_bubble

    def expanded_call_overlay_size(self) -> tuple[int, int]:
        with self._call_overlay_lock:
            return self._call_overlay_width, self._call_overlay_height

    def apply_call_overlay_opacity(self) -> bool:
        with self._call_overlay_lock:
            opacity = self._call_overlay_opacity
        return _set_window_opacity(CALL_OVERLAY_TITLE, opacity)

    @staticmethod
    def _normalize_call_overlay_state(values: object) -> dict[str, object]:
        payload = values if isinstance(values, dict) else {}
        entries: list[dict[str, str]] = []
        raw_entries = payload.get("entries")
        if isinstance(raw_entries, list):
            for item in raw_entries[-6:]:
                if not isinstance(item, dict):
                    continue
                text = " ".join(str(item.get("text") or "").split())[:240]
                if not text:
                    continue
                role = "user" if str(item.get("role") or "") == "user" else "assistant"
                entries.append({"role": role, "text": text})
        theme: dict[str, str] = {}
        raw_theme = payload.get("theme")
        if isinstance(raw_theme, dict):
            for key in CALL_OVERLAY_THEME_KEYS:
                value = " ".join(str(raw_theme.get(key) or "").split())[:64]
                if value:
                    theme[key] = value
            theme["colorScheme"] = (
                "dark" if raw_theme.get("colorScheme") == "dark" else "light"
            )
        return {
            "active": bool(payload.get("active")),
            "minimized": bool(payload.get("minimized")),
            "assistant_name": " ".join(
                str(payload.get("assistant_name") or ASSISTANT_NAME).split()
            )[:24] or ASSISTANT_NAME,
            "status": " ".join(str(payload.get("status") or "通话中").split())[:60],
            "duration": " ".join(str(payload.get("duration") or "00:00").split())[:16],
            "entries": entries,
            "theme": theme,
        }

    def sync_call_overlay(self, values: object) -> dict[str, object]:
        normalized = self._normalize_call_overlay_state(values)
        reset_collapsed = False
        with self._call_overlay_lock:
            was_active = bool(self._call_overlay_state.get("active"))
            self._call_overlay_state = normalized
            if not normalized["active"] or not was_active:
                reset_collapsed = self._call_overlay_collapsed
                self._call_overlay_collapsed = False
        if reset_collapsed:
            if self._avatar_bubble:
                self._avatar_bubble.hide()
            width, height = self.expanded_call_overlay_size()
            _resize_window_without_focus(
                CALL_OVERLAY_TITLE,
                width,
                height,
                visible=False,
            )
        if not normalized["active"]:
            if self._avatar_bubble:
                self._avatar_bubble.hide()
            _set_window_visible_without_focus(CALL_OVERLAY_TITLE, False)
        return {"ok": True, "active": normalized["active"]}

    def call_overlay_state(self) -> dict[str, object]:
        with self._call_overlay_lock:
            payload = dict(self._call_overlay_state)
            payload["collapsed"] = self._call_overlay_collapsed
            payload["opacity"] = self._call_overlay_opacity
            return json.loads(json.dumps(payload, ensure_ascii=False))

    def call_overlay_collapsed(self) -> bool:
        with self._call_overlay_lock:
            return self._call_overlay_collapsed

    def _run_main_window_script(self, script: str, *, restore: bool = False) -> None:
        def run() -> None:
            window = self._window
            if not window:
                return
            try:
                if restore:
                    _show_webview_window_preserving_placement(window, WINDOW_TITLE)
                window.evaluate_js(script)
            except Exception:
                logger.debug("could not control main window from call overlay", exc_info=True)

        threading.Thread(target=run, name="xixi-call-overlay-action", daemon=True).start()

    def restore_call(self) -> dict[str, bool]:
        with self._call_overlay_lock:
            self._call_overlay_state["minimized"] = False
            self._call_overlay_collapsed = False
        if self._avatar_bubble:
            self._avatar_bubble.hide()
        width, height = self.expanded_call_overlay_size()
        _resize_window_without_focus(
            CALL_OVERLAY_TITLE,
            width,
            height,
            visible=False,
        )
        _set_window_visible_without_focus(CALL_OVERLAY_TITLE, False)
        self._run_main_window_script("restoreVoiceCall()", restore=True)
        return {"ok": True}

    def collapse_call_overlay(self) -> dict[str, bool]:
        with self._call_overlay_animation_lock:
            with self._call_overlay_lock:
                if not self._call_overlay_state.get("active"):
                    return {"ok": False}
            resized = _animate_window_resize_without_focus(
                CALL_OVERLAY_TITLE,
                CALL_OVERLAY_COLLAPSED_SIZE,
                CALL_OVERLAY_COLLAPSED_SIZE,
            )
            if resized:
                bounds = _window_bounds(CALL_OVERLAY_TITLE)
                if self._avatar_bubble and bounds:
                    with self._call_overlay_lock:
                        self._call_overlay_collapsed = True
                    _set_window_visible_without_focus(CALL_OVERLAY_TITLE, False)
                    self._avatar_bubble.show_at(*bounds)
                else:
                    width, height = self.expanded_call_overlay_size()
                    _animate_window_resize_without_focus(
                        CALL_OVERLAY_TITLE,
                        width,
                        height,
                    )
                    resized = False
        return {"ok": resized}

    def hide_call_overlay(self) -> dict[str, bool]:
        return self.collapse_call_overlay()

    def show_call_overlay(self) -> dict[str, bool]:
        with self._call_overlay_animation_lock:
            with self._call_overlay_lock:
                was_collapsed = self._call_overlay_collapsed
                payload = dict(self._call_overlay_state)
                if was_collapsed:
                    self._call_overlay_collapsed = False
            should_show = _should_show_call_overlay(
                payload,
                _window_hidden_or_minimized(WINDOW_TITLE),
            )
            if was_collapsed:
                bubble_bounds = (
                    self._avatar_bubble.position()
                    if self._avatar_bubble
                    else _window_bounds(CALL_OVERLAY_TITLE)
                )
                if self._avatar_bubble:
                    self._avatar_bubble.hide()
                overlay = self._call_overlay_window
                if overlay:
                    try:
                        overlay.evaluate_js(
                            "window.expandCallOverlayFromNative && "
                            "window.expandCallOverlayFromNative();"
                        )
                    except Exception:
                        logger.debug("could not start native overlay expansion", exc_info=True)
                if bubble_bounds:
                    positioned = _set_window_bounds_without_focus(
                        CALL_OVERLAY_TITLE,
                        bubble_bounds[0],
                        bubble_bounds[1],
                        bubble_bounds[2],
                        bubble_bounds[3],
                        visible=should_show,
                    )
                else:
                    positioned = True
                width, height = self.expanded_call_overlay_size()
                resized = positioned and _animate_window_resize_without_focus(
                    CALL_OVERLAY_TITLE,
                    width,
                    height,
                )
            else:
                width, height = self.expanded_call_overlay_size()
                resized = _resize_window_without_focus(
                    CALL_OVERLAY_TITLE,
                    width,
                    height,
                    visible=should_show,
                )
            if resized:
                with self._call_overlay_lock:
                    self._call_overlay_collapsed = False
            elif was_collapsed:
                with self._call_overlay_lock:
                    self._call_overlay_collapsed = True
            if resized and not should_show:
                _set_window_visible_without_focus(CALL_OVERLAY_TITLE, False)
        return {"ok": resized}

    def resize_call_overlay(self, edge: str) -> dict[str, object]:
        edge = str(edge)
        with self._call_overlay_lock:
            if (
                edge not in CALL_OVERLAY_RESIZE_EDGES
                or self._call_overlay_collapsed
                or not self._call_overlay_state.get("active")
            ):
                return {"ok": False}
        if not self._call_overlay_resize_lock.acquire(blocking=False):
            return {"ok": False}
        start_bounds = _window_bounds(CALL_OVERLAY_TITLE)
        user32 = _user32_window_api()
        start_cursor = wintypes.POINT()
        if not start_bounds or not user32.GetCursorPos(ctypes.byref(start_cursor)):
            self._call_overlay_resize_lock.release()
            return {"ok": False}

        def resize_while_dragging() -> None:
            latest_bounds = start_bounds
            desktop_bounds = _virtual_desktop_bounds()
            deadline = time.monotonic() + 20
            try:
                while time.monotonic() < deadline:
                    cursor = wintypes.POINT()
                    if not user32.GetCursorPos(ctypes.byref(cursor)):
                        break
                    target_bounds = _call_overlay_resize_bounds(
                        edge,
                        start_bounds,
                        (int(start_cursor.x), int(start_cursor.y)),
                        (int(cursor.x), int(cursor.y)),
                        desktop_bounds,
                    )
                    if target_bounds != latest_bounds:
                        _set_window_bounds_without_focus(
                            CALL_OVERLAY_TITLE,
                            *target_bounds,
                            visible=True,
                        )
                        latest_bounds = target_bounds
                    if not user32.GetAsyncKeyState(0x01) & 0x8000:
                        break
                    time.sleep(1 / 60)
                bounds = _window_bounds(CALL_OVERLAY_TITLE) or latest_bounds
                _, _, width, height = bounds
                with self._call_overlay_lock:
                    self._call_overlay_width = width
                    self._call_overlay_height = height
                    self._preferences["call_overlay_width"] = width
                    self._preferences["call_overlay_height"] = height
                    _save_preferences(self._preferences)
                self.apply_call_overlay_opacity()
                _round_call_overlay_window()
            finally:
                self._call_overlay_resize_lock.release()

        threading.Thread(
            target=resize_while_dragging,
            name="xixi-call-overlay-resize",
            daemon=True,
        ).start()
        return {"ok": True}

    def set_call_overlay_opacity(self, value: object) -> dict[str, object]:
        try:
            opacity = min(1.0, max(0.45, float(value)))
        except (TypeError, ValueError):
            return {"ok": False}
        with self._call_overlay_lock:
            self._call_overlay_opacity = opacity
            self._preferences["call_overlay_opacity"] = opacity
            _save_preferences(self._preferences)
        applied = self.apply_call_overlay_opacity()
        return {"ok": applied, "opacity": opacity}

    def show_collapsed_avatar(self) -> bool:
        bubble = self._avatar_bubble
        if not bubble or not self.call_overlay_collapsed():
            return False
        x, y, width, height = bubble.position()
        return bubble.show_at(x, y, width, height)

    def hide_collapsed_avatar(self) -> bool:
        return bool(self._avatar_bubble and self._avatar_bubble.hide())

    def hangup_call(self) -> dict[str, bool]:
        with self._call_overlay_lock:
            self._call_overlay_state["active"] = False
            self._call_overlay_collapsed = False
        if self._avatar_bubble:
            self._avatar_bubble.hide()
        width, height = self.expanded_call_overlay_size()
        _resize_window_without_focus(
            CALL_OVERLAY_TITLE,
            width,
            height,
            visible=False,
        )
        _set_window_visible_without_focus(CALL_OVERLAY_TITLE, False)
        self._run_main_window_script("endVoiceCall()")
        threading.Thread(
            target=_stop_game_companion_session,
            name="xixi-call-overlay-stop-game",
            daemon=True,
        ).start()
        return {"ok": True}

    def get_preferences(self) -> dict[str, object]:
        return {
            "start_with_windows": bool(self._preferences.get("start_with_windows")),
            "remember_window": bool(self._preferences.get("remember_window")),
            "microphone_enabled": self._preferences.get("microphone_enabled"),
        }

    def save_preferences(self, values: dict[str, object]) -> dict[str, object]:
        self._preferences["close_to_tray"] = False
        for key in ("start_with_windows", "remember_window"):
            if key in values:
                self._preferences[key] = bool(values[key])
        _set_startup(bool(self._preferences["start_with_windows"]))
        self.capture_window()
        _save_preferences(self._preferences)
        return self.get_preferences()

    def set_microphone_permission(self, enabled: object) -> dict[str, object]:
        allowed = bool(enabled)
        self._preferences["microphone_enabled"] = allowed
        _save_preferences(self._preferences)
        applied = _set_webview_microphone_permission(self._window, allowed)
        return {
            "enabled": allowed,
            "decided": True,
            "applied": applied,
        }

    def open_microphone_privacy_settings(self) -> dict[str, bool]:
        try:
            os.startfile("ms-settings:privacy-microphone")
        except Exception:
            logger.exception("could not open Windows microphone privacy settings")
            return {"ok": False}
        return {"ok": True}

    def capture_window(self) -> None:
        window = self._window
        if not window or not self._preferences.get("remember_window"):
            return
        try:
            user32 = _user32_window_api()
            hwnd = user32.FindWindowW(None, WINDOW_TITLE)
            if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return

            maximized = bool(user32.IsZoomed(hwnd))
            self._preferences["maximized"] = maximized
            if maximized:
                return

            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return
            width = max(960, int(rect.right - rect.left))
            height = max(640, int(rect.bottom - rect.top))
            if _window_position_is_visible(rect.left, rect.top, width, height):
                self._preferences.update({
                    "x": int(rect.left),
                    "y": int(rect.top),
                    "width": width,
                    "height": height,
                })
        except Exception:
            logger.debug("could not capture desktop window bounds", exc_info=True)


class CallOverlayApi:
    def __init__(self, desktop_api: DesktopApi) -> None:
        self._desktop_api = desktop_api

    def get_state(self) -> dict[str, object]:
        return self._desktop_api.call_overlay_state()

    def restore(self) -> dict[str, bool]:
        return self._desktop_api.restore_call()

    def hide(self) -> dict[str, bool]:
        return self._desktop_api.hide_call_overlay()

    def collapse(self) -> dict[str, bool]:
        return self._desktop_api.collapse_call_overlay()

    def expand(self) -> dict[str, bool]:
        return self._desktop_api.show_call_overlay()

    def resize(self, edge: str) -> dict[str, object]:
        return self._desktop_api.resize_call_overlay(edge)

    def set_opacity(self, value: object) -> dict[str, object]:
        return self._desktop_api.set_call_overlay_opacity(value)

    def hangup(self) -> dict[str, bool]:
        return self._desktop_api.hangup_call()


def _configure_logging() -> None:
    log_path = RUNTIME_PATHS.logs_dir / "desktop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )


def _record_server_bootstrap_failure(exc: BaseException) -> None:
    """Persist failures that happen before app.studio can configure logging."""
    RUNTIME_PATHS.logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    message = f"\n{timestamp} [ERROR] studio bootstrap failed\n{detail}\n"
    for name in ("studio-startup.log", "app.log"):
        try:
            with (RUNTIME_PATHS.logs_dir / name).open("a", encoding="utf-8") as stream:
                stream.write(message)
        except OSError:
            pass


def _focus_existing_window() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if WINDOW_TITLE in buffer.value:
            matches.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback_type(callback), 0)
    if matches:
        user32.ShowWindow(matches[0], SW_RESTORE)
        user32.SetForegroundWindow(matches[0])


def _open_edge_fallback() -> None:
    """Open the studio in an isolated Edge app window if WebView2 is unavailable."""
    candidates = (
        Path(os.environ.get("PROGRAMFILES(X86)", ""))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES", ""))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
    )
    profile = RUNTIME_PATHS.webview_dir / "edge_studio_profile"
    profile.mkdir(parents=True, exist_ok=True)
    arguments = [
        f"--app={STUDIO_URL}",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
    ]
    for edge in candidates:
        if edge.is_file():
            subprocess.Popen(
                [str(edge), *arguments],
                cwd=str(ROOT),
                creationflags=CREATE_NO_WINDOW,
            )
            return
    import webbrowser

    webbrowser.open(STUDIO_URL)


def _acquire_single_instance() -> tuple[int, bool]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle), ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def _close_handle(handle: int) -> None:
    if handle:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(handle)


def _show_error(message: str) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MessageBoxW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.UINT,
    ]
    user32.MessageBoxW(
        None,
        message,
        f"{ASSISTANT_NAME}启动失败",
        0x10,
    )


def _stop_game_companion_session(timeout_seconds: float = 6.0) -> bool:
    import urllib.request

    request = urllib.request.Request(
        f"{STUDIO_URL}/api/game/stop",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return 200 <= int(response.status) < 300
    except Exception:
        logger.warning("could not stop game companion session", exc_info=True)
        return False


def main() -> int:
    _configure_logging()
    mutex_handle = 0
    studio_server_pid: int | None = None
    stop_studio_server_callback = None
    studio_server_lock = threading.RLock()

    def remember_studio_server(process_id: int | None) -> None:
        nonlocal studio_server_pid
        if not process_id:
            return
        with studio_server_lock:
            studio_server_pid = int(process_id)

    def stop_owned_studio_server() -> None:
        if stop_studio_server_callback is None:
            return
        with studio_server_lock:
            process_id = studio_server_pid
        try:
            if stop_studio_server_callback(process_id):
                logger.info("studio service stopped for desktop exit")
            else:
                logger.warning("studio service did not stop cleanly")
        except Exception:
            logger.exception("could not stop studio service during desktop exit")

    try:
        mutex_handle, is_first_instance = _acquire_single_instance()
        if not is_first_instance:
            _focus_existing_window()
            return 0

        logger.info("desktop launcher starting")
        _set_app_user_model_id()
        _configure_webview_background_runtime()
        logger.info("initializing native WebView2 backend")
        initialize_webview_gui("edgechromium")
        logger.info("native WebView2 backend initialized")

        # Import QQ and studio modules only after WebView2 has initialized.
        # Their Python.NET imports can otherwise deadlock the WinForms backend.
        from start_xixi_studio import (
            ensure_studio_server,
            stop_studio_server,
            studio_ready,
        )

        stop_studio_server_callback = stop_studio_server

        logger.info("ensuring studio service")
        desktop_parent_pid = os.getpid()
        remember_studio_server(
            ensure_studio_server(parent_pid=desktop_parent_pid)
        )
        logger.info("studio service ready")
        if _stop_game_companion_session():
            logger.info("game companion session reset for desktop startup")

        preferences = _load_preferences()
        desktop_api = DesktopApi(preferences)
        storage_path = RUNTIME_PATHS.webview_dir / "desktop_webview"
        storage_path.mkdir(parents=True, exist_ok=True)
        icon_path = ROOT / "studio" / "assets" / "xixi-v3.ico"
        window = webview.create_window(
            WINDOW_TITLE,
            STUDIO_URL,
            js_api=desktop_api,
            width=int(preferences["width"]),
            height=int(preferences["height"]),
            x=int(preferences["x"]) if preferences["remember_window"] and preferences["x"] is not None else None,
            y=int(preferences["y"]) if preferences["remember_window"] and preferences["y"] is not None else None,
            min_size=(960, 640),
            resizable=True,
            maximized=bool(preferences["maximized"]),
            background_color="#f4f5f7",
            text_select=True,
        )
        if window is None:
            raise RuntimeError("无法创建桌面窗口")
        overlay_width, overlay_height = desktop_api.expanded_call_overlay_size()
        overlay_x, overlay_y = _call_overlay_position(overlay_width, overlay_height)
        call_overlay = webview.create_window(
            CALL_OVERLAY_TITLE,
            CALL_OVERLAY_URL,
            js_api=CallOverlayApi(desktop_api),
            width=overlay_width,
            height=overlay_height,
            x=overlay_x,
            y=overlay_y,
            min_size=(CALL_OVERLAY_COLLAPSED_SIZE, CALL_OVERLAY_COLLAPSED_SIZE),
            resizable=True,
            hidden=True,
            frameless=True,
            easy_drag=False,
            shadow=False,
            focus=False,
            on_top=True,
            background_color="#ffffff",
            text_select=False,
            zoomable=False,
        )
        if call_overlay is None:
            raise RuntimeError("无法创建通话悬浮窗")
        logger.info("desktop webview window created")
        desktop_api.bind_windows(window, call_overlay)
        avatar_bubble = NativeCallAvatarBubble(
            ROOT / "studio" / "assets" / "xixi-avatar-v3.png",
            desktop_api.show_call_overlay,
        )
        desktop_api.bind_avatar_bubble(avatar_bubble)
        force_exit = threading.Event()
        tray_holder: dict[str, pystray.Icon] = {}
        shutdown_lock = threading.RLock()
        shutdown_state = {
            "overlay_destroyed": False,
            "window_destroyed": False,
            "game_stopped": False,
        }

        def stop_game_once() -> None:
            with shutdown_lock:
                if shutdown_state["game_stopped"]:
                    return
                shutdown_state["game_stopped"] = True
            if _stop_game_companion_session():
                logger.info("game companion session stopped for desktop exit")

        def destroy_window_once(key: str, target: webview.Window) -> None:
            with shutdown_lock:
                if shutdown_state[key]:
                    return
                shutdown_state[key] = True
            try:
                target.destroy()
            except Exception:
                logger.debug("desktop window was already closed", exc_info=True)

        def destroy_call_overlay_once() -> None:
            avatar_bubble.close()
            destroy_window_once("overlay_destroyed", call_overlay)

        def destroy_main_window_once() -> None:
            destroy_window_once("window_destroyed", window)

        def show_window(_icon: pystray.Icon | None = None, _item: object = None) -> None:
            _show_webview_window_preserving_placement(window, WINDOW_TITLE)

        def show_call_overlay(_icon: pystray.Icon | None = None, _item: object = None) -> None:
            desktop_api.show_call_overlay()

        def exit_application(icon: pystray.Icon | None = None, _item: object = None) -> None:
            force_exit.set()
            desktop_api.capture_window()
            _save_preferences(preferences)
            stop_game_once()
            if icon:
                icon.stop()
            destroy_call_overlay_once()
            destroy_main_window_once()

        def on_closing() -> bool:
            force_exit.set()
            desktop_api.capture_window()
            _save_preferences(preferences)
            stop_game_once()
            tray = tray_holder.get("icon")
            if tray:
                tray.stop()
            threading.Thread(
                target=destroy_call_overlay_once,
                name="xixi-call-overlay-close",
                daemon=True,
            ).start()
            return True

        window.events.closing += on_closing

        def start_tray() -> None:
            # Import pystray after WebView2 has initialized. Its Windows
            # backend touches COM during import and can block pythonnet's
            # WinForms initialization when imported at module load time.
            import pystray
            from PIL import Image

            image_path = icon_path if icon_path.is_file() else ROOT / "studio" / "assets" / "xixi-avatar-v3.png"
            tray = pystray.Icon(
                "xixi-studio",
                Image.open(image_path),
                WINDOW_TITLE,
                menu=pystray.Menu(
                pystray.MenuItem(f"显示{ASSISTANT_NAME}", show_window, default=True),
                    pystray.MenuItem(
                        "显示通话小窗",
                        show_call_overlay,
                        visible=lambda _item: _call_overlay_menu_visible(
                            desktop_api.call_overlay_state()
                        ),
                    ),
                    pystray.MenuItem("退出", exit_application),
                ),
            )
            tray_holder["icon"] = tray
            tray.run()

        def apply_window_icon() -> None:
            # Start the tray only after WebView2 has initialized. Some
            # pystray backends initialize COM on their worker thread and can
            # otherwise interfere with WinForms/WebView2 startup.
            threading.Thread(target=start_tray, name="xixi-tray", daemon=True).start()
            if not window.events.shown.wait(10):
                return
            avatar_bubble.start()
            for _ in range(20):
                if _set_window_icon(icon_path):
                    return
                time.sleep(0.1)

        def service_watchdog() -> None:
            while not force_exit.wait(12):
                if studio_ready():
                    continue
                logger.warning("studio service unavailable; attempting recovery")
                try:
                    remember_studio_server(
                        ensure_studio_server(parent_pid=desktop_parent_pid)
                    )
                    window.load_url(STUDIO_URL)
                    logger.info("studio service recovered")
                except Exception:
                    logger.exception("studio service recovery failed")

        def call_overlay_watchdog() -> None:
            visible = False
            bubble_visible = False
            last_payload = ""
            last_menu_active = False
            overlay_ready = False
            last_round_check = 0.0
            while not force_exit.wait(0.25):
                payload = desktop_api.call_overlay_state()
                menu_active = _call_overlay_menu_visible(payload)
                if menu_active != last_menu_active:
                    tray = tray_holder.get("icon")
                    if tray:
                        tray.update_menu()
                    last_menu_active = menu_active
                serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if serialized != last_payload:
                    try:
                        updated = call_overlay.evaluate_js(
                            "Boolean(window.updateCallOverlay && "
                            f"(window.updateCallOverlay({serialized}), true));"
                        )
                        if updated:
                            overlay_ready = True
                            last_payload = serialized
                    except Exception:
                        logger.debug("call overlay is not ready for updates", exc_info=True)
                should_show = _should_show_call_overlay(
                    payload,
                    _window_hidden_or_minimized(WINDOW_TITLE),
                )
                should_show_bubble = should_show and bool(payload.get("collapsed"))
                should_show_overlay = should_show and not should_show_bubble and overlay_ready
                if should_show_bubble != bubble_visible:
                    if should_show_bubble:
                        bubble_visible = desktop_api.show_collapsed_avatar()
                    else:
                        desktop_api.hide_collapsed_avatar()
                        bubble_visible = False
                if should_show_overlay != visible:
                    if should_show_overlay:
                        desktop_api.apply_call_overlay_opacity()
                    if _set_window_visible_without_focus(
                        CALL_OVERLAY_TITLE,
                        should_show_overlay,
                    ):
                        visible = should_show_overlay
                if should_show_overlay and visible:
                    now = time.monotonic()
                    if now - last_round_check >= 0.75:
                        _round_call_overlay_window(CALL_OVERLAY_TITLE)
                        last_round_check = now
                else:
                    last_round_check = 0.0

        def desktop_startup_watchdog() -> None:
            # WebView2 can hang during native initialization without raising an
            # exception. Keep the desktop shortcut usable in that case.
            if window.events.shown.wait(45):
                return
            logger.warning("WebView2 did not show the desktop window within 45 seconds")
            try:
                _open_edge_fallback()
                logger.warning("opened Edge app fallback for the studio")
            except Exception:
                logger.exception("could not open Edge app fallback")
            time.sleep(1)
            os._exit(0)

        threading.Thread(target=service_watchdog, name="xixi-watchdog", daemon=True).start()
        threading.Thread(
            target=call_overlay_watchdog,
            name="xixi-call-overlay-watchdog",
            daemon=True,
        ).start()
        threading.Thread(
            target=desktop_startup_watchdog,
            name="xixi-desktop-startup-watchdog",
            daemon=True,
        ).start()
        logger.info("starting native WebView2 GUI")
        webview.start(
            func=apply_window_icon,
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=str(storage_path),
            icon=str(icon_path) if icon_path.is_file() else None,
        )
        logger.info("native WebView2 GUI returned")
        force_exit.set()
        stop_game_once()
        destroy_call_overlay_once()
        tray = tray_holder.get("icon")
        if tray:
            tray.stop()
        desktop_api.capture_window()
        _save_preferences(preferences)
        logger.info("desktop window closed")
        return 0
    except Exception as exc:
        logger.exception("desktop startup failed")
        _show_error(
            f"{ASSISTANT_NAME}本地应用启动失败：\n\n{exc}\n\n"
            f"详情见 {RUNTIME_PATHS.logs_dir / 'desktop.log'}"
        )
        return 1
    finally:
        stop_owned_studio_server()
        _close_handle(mutex_handle)


if __name__ == "__main__":
    _configure_frozen_release_environment()
    if "--server" in sys.argv:
        try:
            from app.studio import main as server_main

            server_main()
        except Exception as exc:
            _record_server_bootstrap_failure(exc)
            raise SystemExit(1) from None
    else:
        raise SystemExit(main())

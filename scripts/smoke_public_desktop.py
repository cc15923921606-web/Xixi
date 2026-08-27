from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path
from typing import Any


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def _wait_for_health(port: int, timeout: float = 55.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health",
                timeout=2.0,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("ok"):
                return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.4)
    raise RuntimeError("desktop backend did not become ready") from last_error


def _visible_window_for_process(process_id: int) -> bool:
    user32 = ctypes.windll.user32
    found = False

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def inspect(hwnd: int, _lparam: int) -> bool:
        nonlocal found
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == process_id and user32.IsWindowVisible(hwnd):
            found = True
            return False
        return True

    user32.EnumWindows(callback_type(inspect), 0)
    return found


def _close_visible_window_for_process(process_id: int) -> bool:
    user32 = ctypes.windll.user32
    wm_close = 0x0010
    closed = False
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def close_window(hwnd: int, _lparam: int) -> bool:
        nonlocal closed
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == process_id and user32.IsWindowVisible(hwnd):
            closed = bool(user32.PostMessageW(hwnd, wm_close, 0, 0))
            return False
        return True

    user32.EnumWindows(callback_type(close_window), 0)
    return closed


def run_desktop_smoke(executable: Path, smoke_root: Path) -> dict[str, Any]:
    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"public executable not found: {executable}")
    port = 8766
    if _port_open(port):
        raise RuntimeError(f"public desktop port {port} is already in use")

    smoke_root.mkdir(parents=True, exist_ok=True)
    data_home = Path(tempfile.mkdtemp(prefix="desktop-", dir=smoke_root)).resolve()
    environment = os.environ.copy()
    environment.update(
        {
            "XIXI_DATA_HOME": str(data_home),
            "BRAIN_ENABLED": "0",
            "VOICE_ENABLED": "0",
            "VISION_ENABLED": "0",
            "QQ_ENABLED": "0",
            "LEARNING_ENABLED": "0",
            "SETUP_COMPLETE": "0",
        }
    )
    process = subprocess.Popen(
        [str(executable)],
        cwd=executable.parent,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    result: dict[str, Any] = {}
    try:
        health = _wait_for_health(port)
        window_deadline = time.monotonic() + 35.0
        while time.monotonic() < window_deadline:
            if process.poll() is not None:
                break
            if _visible_window_for_process(process.pid):
                break
            time.sleep(0.4)
        result.update(
            {
                "desktop_process_started": process.poll() is None,
                "health_ok": bool(health.get("ok")),
                "edition": health.get("edition"),
                "visible_window": _visible_window_for_process(process.pid),
            }
        )
        result["close_requested"] = _close_visible_window_for_process(process.pid)
        close_deadline = time.monotonic() + 20.0
        while process.poll() is None and time.monotonic() < close_deadline:
            time.sleep(0.25)
        result["desktop_stopped_after_window_close"] = process.poll() is not None
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        close_deadline = time.monotonic() + 15.0
        while _port_open(port) and time.monotonic() < close_deadline:
            time.sleep(0.25)
        result["backend_stopped_after_desktop_exit"] = not _port_open(port)
        cleanup_deadline = time.monotonic() + 15.0
        while data_home.exists() and time.monotonic() < cleanup_deadline:
            shutil.rmtree(data_home, ignore_errors=True)
            if data_home.exists():
                time.sleep(0.25)
        result["smoke_data_cleaned"] = not data_home.exists()
        try:
            smoke_root.rmdir()
        except OSError:
            pass

    result["passed"] = all(
        (
            result.get("desktop_process_started"),
            result.get("health_ok"),
            result.get("edition") == "public",
            result.get("visible_window"),
            result.get("close_requested"),
            result.get("desktop_stopped_after_window_close"),
            result.get("backend_stopped_after_desktop_exit"),
            result.get("smoke_data_cleaned"),
        )
    )
    return result


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--executable",
        type=Path,
        default=project_root / "packaging" / "dist" / "Xixi" / "Xixi.exe",
    )
    parser.add_argument(
        "--smoke-root",
        type=Path,
        default=project_root.parent / "_xixi_public_desktop_smoke",
    )
    args = parser.parse_args()
    result = run_desktop_smoke(args.executable, args.smoke_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())

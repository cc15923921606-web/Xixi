from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected response from {url}")
    return payload


def _wait_for_health(base_url: str, timeout: float = 35.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return _get_json(f"{base_url}/api/health", timeout=2.0)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.4)
    raise RuntimeError("packaged server did not become ready") from last_error


def _wait_for_environment(base_url: str, timeout: float = 15.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            latest = _get_json(f"{base_url}/api/environment", timeout=5.0)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.4)
            continue
        states = {
            str(item.get("key") or ""): str(item.get("state") or "")
            for item in latest.get("items") or []
            if isinstance(item, dict)
        }
        if states.get("speech_recognition") == "ok":
            return latest
        time.sleep(0.5)
    if not latest and last_error is not None:
        raise RuntimeError("packaged environment status did not become readable") from last_error
    return latest


def _get_text_with_retry(url: str, timeout: float = 12.0) -> tuple[int, str]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5.0) as response:
                return int(response.status), response.read().decode("utf-8")
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.35)
    raise RuntimeError(f"packaged page did not become readable: {url}") from last_error


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_smoke(
    executable: Path,
    smoke_root: Path,
    *,
    keep_data: bool = False,
    use_default_data: bool = False,
    simulate_existing_voice_setting: bool = False,
) -> dict[str, Any]:
    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"public executable not found: {executable}")
    app_root = executable.parent
    pointer = app_root / "数据目录.txt"
    pointer_backup = pointer.read_bytes() if pointer.is_file() else None

    if use_default_data:
        install_root = app_root.parent if app_root.name == "程序文件" else app_root
        data_home = (install_root / "用户数据").resolve()
        if data_home.exists():
            raise FileExistsError(f"default smoke-test data already exists: {data_home}")
    else:
        smoke_root.mkdir(parents=True, exist_ok=True)
        data_home = Path(tempfile.mkdtemp(prefix="review-", dir=smoke_root)).resolve()
    if simulate_existing_voice_setting:
        settings_root = data_home / "运行数据"
        settings_root.mkdir(parents=True, exist_ok=True)
        (settings_root / "studio_settings.json").write_text(
            json.dumps(
                {
                    "setup_complete": True,
                    "brain_enabled": False,
                    "voice_enabled": True,
                    "qq_enabled": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update(
        {
            "XIXI_STUDIO_PORT": str(port),
            "BRAIN_ENABLED": "0",
            "VOICE_ENABLED": "0",
            "VISION_ENABLED": "0",
            "QQ_ENABLED": "0",
            "LEARNING_ENABLED": "0",
            "SETUP_COMPLETE": "0",
        }
    )
    if use_default_data:
        environment.pop("XIXI_DATA_HOME", None)
    else:
        environment["XIXI_DATA_HOME"] = str(data_home)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result: dict[str, Any] = {}
    desktop_sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    environment["XIXI_DESKTOP_PARENT_PID"] = str(desktop_sentinel.pid)
    process = subprocess.Popen(
        [str(executable), "--server"],
        cwd=app_root,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    try:
        health = _wait_for_health(base_url)
        bootstrap = _get_json(f"{base_url}/api/bootstrap")
        environment_status = _wait_for_environment(base_url)
        privacy = _get_json(f"{base_url}/api/privacy")
        providers = _get_json(f"{base_url}/api/model/providers")
        setup_status, setup_html = _get_text_with_retry(f"{base_url}/setup.html")

        settings = bootstrap.get("settings") or {}
        status = bootstrap.get("status") or {}
        model_connection = bootstrap.get("model_connection") or {}
        language_connection = model_connection.get("language") or {}
        vision_connection = model_connection.get("vision") or {}
        provider_items = providers.get("items") or providers.get("providers") or []
        runtime_config_path = data_home / "运行配置.json"
        runtime_config = json.loads(runtime_config_path.read_text(encoding="utf-8"))
        environment_items = environment_status.get("items") or []
        environment_states = {
            str(item.get("key") or ""): str(item.get("state") or "")
            for item in environment_items
            if isinstance(item, dict)
        }
        result.update({
            "process_started": process.poll() is None,
            "health_ok": bool(health.get("ok")),
            "edition": health.get("edition"),
            "setup_complete": bool(settings.get("setup_complete")),
            "brain_enabled": bool((status.get("model") or {}).get("enabled")),
            "voice_enabled": bool((status.get("voice") or {}).get("enabled")),
            "qq_enabled": bool((status.get("qq") or {}).get("enabled")),
            "environment_items": len(environment_items),
            "environment_ready_count": int(environment_status.get("ready_count") or 0),
            "environment_states": environment_states,
            "privacy_paused": bool(privacy.get("paused")),
            "provider_count": len(provider_items),
            "language_api_key_configured": bool(
                language_connection.get("api_key_configured")
            ),
            "vision_api_key_configured": bool(
                vision_connection.get("api_key_configured")
            ),
            "language_base_url": str(language_connection.get("base_url") or ""),
            "setup_http_status": setup_status,
            "setup_title_found": "昔夕配置中心" in setup_html,
            "runtime_edition": runtime_config.get("edition"),
            "runtime_data_root": runtime_config.get("data_root"),
            "runtime_directories": {
                name: (data_home / name).is_dir()
                for name in ("运行数据", "WebView数据", "日志", "下载", "本地组件", "本地模型")
            },
            "pointer_matches": pointer.is_file()
            and pointer.read_text(encoding="utf-8-sig").strip() == str(data_home),
            "smoke_data_home": str(data_home),
            "default_data_mode": use_default_data,
            "simulated_existing_voice_setting": simulate_existing_voice_setting,
            "data_inside_install": (
                not use_default_data
                or data_home.parent == app_root.parent
            ),
        })
    finally:
        _stop_process(desktop_sentinel)
        exit_deadline = time.monotonic() + 12.0
        while process.poll() is None and time.monotonic() < exit_deadline:
            time.sleep(0.2)
        result["parent_watchdog_stopped"] = process.poll() is not None
        _stop_process(process)
        if pointer_backup is None:
            pointer.unlink(missing_ok=True)
        else:
            pointer.write_bytes(pointer_backup)
        if not keep_data:
            shutil.rmtree(data_home, ignore_errors=True)
            result["smoke_data_cleaned"] = not data_home.exists()
            if not use_default_data:
                try:
                    smoke_root.rmdir()
                except OSError:
                    pass

    profile_checks = (
        (
            result["setup_complete"],
            result["voice_enabled"],
        )
        if simulate_existing_voice_setting
        else (
            not result["setup_complete"],
            not result["voice_enabled"],
            result["provider_count"] == 0,
            not result["language_api_key_configured"],
            not result["vision_api_key_configured"],
            not result["language_base_url"],
            result["setup_title_found"],
        )
    )
    required_checks = (
        result["health_ok"],
        result["edition"] == "public",
        not result["brain_enabled"],
        not result["qq_enabled"],
        result["environment_items"] >= 6,
        result["environment_states"].get("speech_recognition") in {"ok", "optional"},
        result["environment_states"].get("screen_observation") == "ok",
        result["setup_http_status"] == 200,
        result["runtime_edition"] == "public",
        result["runtime_data_root"] == str(data_home),
        all(result["runtime_directories"].values()),
        result["pointer_matches"],
        result["parent_watchdog_stopped"],
        result["data_inside_install"],
        *profile_checks,
    )
    result["passed"] = all(required_checks)
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
        default=project_root.parent / "_xixi_public_smoke",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="keep the isolated smoke-test data for manual inspection",
    )
    parser.add_argument(
        "--default-data",
        action="store_true",
        help="verify the installed default user-data directory instead of an isolated override",
    )
    parser.add_argument(
        "--simulate-existing-voice-setting",
        action="store_true",
        help="start with an existing voice-enabled setting while optional public models are absent",
    )
    args = parser.parse_args()
    result = run_smoke(
        args.executable,
        args.smoke_root,
        keep_data=args.keep_data,
        use_default_data=args.default_data,
        simulate_existing_voice_setting=args.simulate_existing_voice_setting,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())

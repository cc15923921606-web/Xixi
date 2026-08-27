"""Launch the integrated Xixi desktop studio and hand QQ over to it."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from start_xixi_qq import (
    CREATE_NO_WINDOW,
    ROOT,
    RUNTIME_PATHS,
    configured_identity,
    launch_napcat,
    onebot_login,
    powershell_lines,
    status,
    ws_port_ready,
    xixi_runtime_environment,
)


STUDIO_PORT = int(os.environ.get("XIXI_STUDIO_PORT", "8765"))
STUDIO_URL = f"http://127.0.0.1:{STUDIO_PORT}"
STUDIO_EDITION = os.environ.get(
    "XIXI_EDITION",
    "public" if getattr(sys, "frozen", False) else "personal",
).strip().casefold()


def _workspace_id(root: Path = ROOT) -> str:
    normalized = str(root.resolve()).replace("/", "\\").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


STUDIO_WORKSPACE_ID = _workspace_id()


def _read_log_tail(path: Path, *, max_chars: int = 2400) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return text[-max_chars:]


def _startup_failure_message(exit_code: int | None, startup_log: Path) -> str:
    app_log = RUNTIME_PATHS.logs_dir / "app.log"
    details = _read_log_tail(app_log) or _read_log_tail(startup_log)
    prefix = (
        f"控制中心进程启动失败（退出码 {exit_code}）。"
        if exit_code is not None
        else "控制中心未能在规定时间内启动。"
    )
    if details:
        return f"{prefix}\n\n最后的启动记录：\n{details}"
    return (
        f"{prefix}\n\n请检查安装目录是否完整，或查看：\n"
        f"{app_log}\n{startup_log}"
    )


def _may_cleanup_source_processes() -> bool:
    """A packaged public release must never stop the personal source edition."""
    return not bool(getattr(sys, "frozen", False))


def studio_health() -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(f"{STUDIO_URL}/api/health", timeout=1.5) as response:
            if response.status != 200:
                return None
            payload = json.load(response)
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def studio_ready() -> bool:
    health = studio_health()
    return bool(
        health
        and health.get("ok") is True
        and str(health.get("edition") or "").casefold() == STUDIO_EDITION
        and str(health.get("workspace_id") or "") == STUDIO_WORKSPACE_ID
    )


def studio_port_in_use() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", STUDIO_PORT), timeout=0.25):
            return True
    except OSError:
        return False


def process_ids(command_fragment: str) -> list[int]:
    escaped = command_fragment.replace("'", "''")
    script = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -in @('python.exe','pythonw.exe') -and "
        f"$_.CommandLine -like '*{escaped}*' }}; "
        "$p | ForEach-Object { $_.ProcessId }"
    )
    return [int(line) for line in powershell_lines(script) if line.isdigit()]


def stop_process_trees(process_ids_to_stop: list[int]) -> None:
    for process_id in process_ids_to_stop:
        subprocess.run(
            ["taskkill.exe", "/PID", str(process_id), "/T", "/F"],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )


def open_studio_window() -> None:
    candidates = (
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    )
    for edge in candidates:
        if edge.is_file():
            subprocess.Popen(
                [str(edge), f"--app={STUDIO_URL}", "--start-maximized"],
                creationflags=CREATE_NO_WINDOW,
            )
            return
    import webbrowser

    webbrowser.open(STUDIO_URL)


def ensure_napcat() -> None:
    bot_qq = str(configured_identity()["bot_qq_id"])
    login = onebot_login()
    if login and str(login.get("user_id")) == bot_qq and ws_port_ready():
        status(f"NapCat 已在线：{login.get('nickname', '昔夕')}（{bot_qq}）")
        return
    login = launch_napcat(bot_qq)
    status(f"QQ 登录成功：{login.get('nickname', '昔夕')}（{bot_qq}）")


def studio_process_id() -> int | None:
    if not studio_ready():
        return None
    result = subprocess.run(
        ["netstat.exe", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if (
            len(parts) >= 5
            and parts[0].upper() == "TCP"
            and parts[1].rsplit(":", 1)[-1] == str(STUDIO_PORT)
            and parts[3].upper() == "LISTENING"
            and parts[-1].isdigit()
        ):
            return int(parts[-1])
    return None


def stop_studio_server(process_id: int | None = None) -> bool:
    if not studio_ready():
        return True
    owner_pid = studio_process_id()
    if owner_pid is None:
        return False
    process_id = owner_pid
    subprocess.run(
        ["taskkill.exe", "/PID", str(process_id), "/T", "/F"],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if not studio_port_in_use():
            return True
        time.sleep(0.2)
    return not studio_port_in_use()


def ensure_studio_server(*, parent_pid: int | None = None) -> int | None:
    if studio_ready():
        current_pid = studio_process_id()
        if parent_pid:
            status("正在接管并重启遗留的昔夕后台……")
            if not stop_studio_server(current_pid):
                raise RuntimeError("遗留的昔夕后台无法停止，请结束后重试。")
            time.sleep(0.5)
        else:
            status("昔夕控制中心已经在运行。")
            return current_pid
    if studio_port_in_use():
        health = studio_health() or {}
        other_edition = str(health.get("edition") or "旧版或未知程序")
        raise RuntimeError(
            f"本地端口 {STUDIO_PORT} 已被{other_edition}占用，"
            "为保护不同安装的数据，昔夕拒绝连接到错误后台。"
        )

    stale_studio = process_ids("-m app.studio") if _may_cleanup_source_processes() else []
    if stale_studio:
        status("正在清理未正常启动的控制中心进程……")
        stop_process_trees(stale_studio)
        time.sleep(1)

    standalone = process_ids("-m app.main --qq") if _may_cleanup_source_processes() else []
    if standalone:
        status("正在把 QQ 从独立模式交给控制中心……")
        stop_process_trees(standalone)
        time.sleep(1)

    env = xixi_runtime_environment()
    env["XIXI_STUDIO_PORT"] = str(STUDIO_PORT)
    if parent_pid:
        env["XIXI_DESKTOP_PARENT_PID"] = str(int(parent_pid))
    else:
        env.pop("XIXI_DESKTOP_PARENT_PID", None)
    if getattr(sys, "frozen", False):
        server = ROOT / "Xixi.exe"
        if not server.is_file():
            raise FileNotFoundError(f"找不到昔夕后台服务：{server}")
        command = [str(server), "--server"]
    else:
        pythonw = ROOT / "venv" / "Scripts" / "pythonw.exe"
        if not pythonw.is_file():
            raise FileNotFoundError(f"找不到昔夕的 Python 环境：{pythonw}")
        command = [str(pythonw), "-u", "-m", "app.studio"]
    startup_log = RUNTIME_PATHS.logs_dir / "studio-startup.log"
    startup_log.parent.mkdir(parents=True, exist_ok=True)
    with startup_log.open("ab", buffering=0) as stream:
        marker = (
            f"\r\n[{datetime.now().astimezone().isoformat(timespec='seconds')}] "
            f"starting: {' '.join(command)}\r\n"
        )
        stream.write(marker.encode("utf-8", errors="replace"))
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    try:
        startup_timeout = float(os.environ.get("XIXI_STUDIO_STARTUP_TIMEOUT_S", "180"))
    except (TypeError, ValueError):
        startup_timeout = 180.0
    deadline = time.monotonic() + max(30.0, min(300.0, startup_timeout))
    while time.monotonic() < deadline:
        if studio_ready():
            status("昔夕控制中心已启动。")
            return process.pid
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(_startup_failure_message(exit_code, startup_log))
        time.sleep(0.5)
    stop_process_trees([process.pid])
    raise RuntimeError(_startup_failure_message(None, startup_log))


def launch_studio() -> None:
    ensure_studio_server()
    open_studio_window()


def main() -> int:
    try:
        launch_studio()
        status("启动完成。")
        return 0
    except Exception as exc:
        status(f"启动失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

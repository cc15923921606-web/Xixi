"""Start NapCat and Xixi's QQ bot in the correct order."""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from threading import Event, RLock
from typing import Mapping

try:
    import winreg
except ImportError:  # pragma: no cover - Windows is the supported desktop target.
    winreg = None  # type: ignore[assignment]

from app.napcat_runtime import (
    clear_napcat_qrcodes,
    ensure_napcat_launch_root,
    find_napcat_qrcode,
    provision_packaged_napcat,
    release_napcat_launch_root,
    resolve_napcat_root,
)
from app.qq_identity import load_qq_identity
from app.runtime_paths import activate_runtime_environment, resolve_runtime_paths
from app.voice_runtime import resolve_voice_root


ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
RUNTIME_PATHS = resolve_runtime_paths(
    ROOT,
    public_release=bool(getattr(sys, "frozen", False)),
)
activate_runtime_environment(RUNTIME_PATHS)


def resolve_napcat_dir(
    root: Path = ROOT,
    components_root: Path = RUNTIME_PATHS.components_dir,
    environ: Mapping[str, str] = os.environ,
) -> Path:
    configured = str(environ.get("NAPCAT_ROOT") or "").strip()
    if configured:
        configured_root = resolve_napcat_root(
            root,
            components_root,
            environ,
            discover=False,
        )
        if configured_root is not None:
            return configured_root
    provisioned = provision_packaged_napcat(root, components_root)
    if provisioned is not None:
        return provisioned
    resolved = resolve_napcat_root(
        root,
        components_root,
        environ,
        discover=True,
    )
    if resolved is not None:
        return resolved
    if configured:
        return Path(configured).expanduser()
    return components_root / "NapCat"


ONEBOT_API = "http://127.0.0.1:3000"
ONEBOT_WS_PORT = 3001
CREATE_NO_WINDOW = 0x08000000
MANAGED_ACCOUNTS_FILENAME = "qq_managed_accounts.json"
MANAGED_PROCESSES_FILENAME = "qq_managed_processes.json"
_MANAGED_ACCOUNTS_LOCK = RLock()
_WEBUI_TOKEN_RE = re.compile(r"WebUi Token:\s*([A-Za-z0-9_-]{8,128})", re.IGNORECASE)
_WEBUI_URL_RE = re.compile(r"WebUi User Panel Url:\s*(https?://\S+)", re.IGNORECASE)


def _default_gpt_sovits_root() -> Path:
    default_root = (
        RUNTIME_PATHS.components_dir / "GPT-SoVITS"
        if getattr(sys, "frozen", False)
        else ROOT.parent / "work" / "GPT-SoVITS"
    )
    return resolve_voice_root(default_root, allow_registered_fallback=True, discover=True)


class QQLaunchCancelled(RuntimeError):
    """Raised when a Studio QQ launch is cancelled by a newer operation."""


def _normalized_qq_id(value: int | str) -> str:
    text = str(value).strip()
    if not text.isdigit() or not 5 <= len(text) <= 12 or text.startswith("0"):
        raise ValueError("QQ account must be a 5 to 12 digit number")
    return text


def _managed_accounts_file(
    root: Path | None = None,
    *,
    data_root: Path | None = None,
) -> Path:
    if data_root is not None:
        return Path(data_root) / MANAGED_ACCOUNTS_FILENAME
    if root is not None:
        return Path(root) / "data" / MANAGED_ACCOUNTS_FILENAME
    return RUNTIME_PATHS.data_dir / MANAGED_ACCOUNTS_FILENAME


def managed_qq_accounts(
    root: Path | None = None,
    *,
    data_root: Path | None = None,
) -> set[int]:
    path = _managed_accounts_file(root, data_root=data_root)
    with _MANAGED_ACCOUNTS_LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            values = payload.get("accounts", []) if isinstance(payload, dict) else []
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return set()
        accounts: set[int] = set()
        for value in values:
            try:
                accounts.add(int(_normalized_qq_id(value)))
            except ValueError:
                continue
        return accounts


def _write_managed_qq_accounts(
    accounts: set[int],
    root: Path | None = None,
    *,
    data_root: Path | None = None,
) -> None:
    path = _managed_accounts_file(root, data_root=data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not accounts:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"accounts": sorted(accounts)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def register_managed_qq_account(
    bot_qq_id: int | str,
    root: Path | None = None,
    *,
    data_root: Path | None = None,
) -> None:
    account = int(_normalized_qq_id(bot_qq_id))
    with _MANAGED_ACCOUNTS_LOCK:
        accounts = managed_qq_accounts(root, data_root=data_root)
        accounts.add(account)
        _write_managed_qq_accounts(accounts, root, data_root=data_root)


def unregister_managed_qq_account(
    bot_qq_id: int | str,
    root: Path | None = None,
    *,
    data_root: Path | None = None,
) -> None:
    account = int(_normalized_qq_id(bot_qq_id))
    with _MANAGED_ACCOUNTS_LOCK:
        accounts = managed_qq_accounts(root, data_root=data_root)
        accounts.discard(account)
        _write_managed_qq_accounts(accounts, root, data_root=data_root)


def _managed_processes_file(
    root: Path | None = None,
    *,
    data_root: Path | None = None,
) -> Path:
    if data_root is not None:
        return Path(data_root) / MANAGED_PROCESSES_FILENAME
    if root is not None:
        return Path(root) / "data" / MANAGED_PROCESSES_FILENAME
    return RUNTIME_PATHS.data_dir / MANAGED_PROCESSES_FILENAME


def managed_qq_processes(
    bot_qq_id: int | str,
    root: Path | None = None,
    *,
    data_root: Path | None = None,
) -> set[int]:
    account = _normalized_qq_id(bot_qq_id)
    path = _managed_processes_file(root, data_root=data_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return set()
    values = payload.get(account, []) if isinstance(payload, dict) else []
    return {int(value) for value in values if str(value).isdigit() and int(value) > 0}


def _write_managed_qq_processes(
    payload: dict[str, list[int]],
    root: Path | None = None,
    *,
    data_root: Path | None = None,
) -> None:
    path = _managed_processes_file(root, data_root=data_root)
    cleaned = {
        str(account): sorted({int(pid) for pid in pids if int(pid) > 0})
        for account, pids in payload.items()
        if pids
    }
    if not cleaned:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def register_managed_qq_process(bot_qq_id: int | str, pid: int) -> None:
    account = _normalized_qq_id(bot_qq_id)
    path = _managed_processes_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    current = {int(value) for value in payload.get(account, []) if str(value).isdigit()}
    current.add(int(pid))
    payload[account] = sorted(current)
    _write_managed_qq_processes(payload)


def unregister_managed_qq_processes(bot_qq_id: int | str) -> None:
    account = _normalized_qq_id(bot_qq_id)
    path = _managed_processes_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.pop(account, None)
    _write_managed_qq_processes(payload)


def _raise_if_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise QQLaunchCancelled("QQ launch was cancelled")


def configured_assistant_name() -> str:
    try:
        payload = json.loads(
            (RUNTIME_PATHS.data_dir / "studio_settings.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, TypeError):
        return "昔夕"
    name = " ".join(str(payload.get("assistant_name") or "昔夕").split()).strip()
    return name[:24] or "昔夕"


def status(message: str) -> None:
    name = configured_assistant_name()
    text = f"[{name}] {str(message).replace('昔夕', name)}"
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        printable = text.encode(encoding, errors="replace").decode(encoding)
        print(printable, flush=True)


def onebot_login() -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(f"{ONEBOT_API}/get_login_info", timeout=2) as response:
            payload = json.load(response)
        if payload.get("status") == "ok" and payload.get("retcode") == 0:
            return payload.get("data")
    except Exception:
        pass
    return None


def ws_port_ready() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", ONEBOT_WS_PORT), timeout=1):
            return True
    except OSError:
        return False


def _read_napcat_log(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-12000:]
    except OSError:
        return ""


def _napcat_webui_connection(log_path: Path) -> tuple[str, str] | None:
    text = _read_napcat_log(log_path)
    token_matches = _WEBUI_TOKEN_RE.findall(text)
    url_matches = _WEBUI_URL_RE.findall(text)
    if not token_matches or not url_matches:
        return None
    parsed = urllib.parse.urlparse(url_matches[-1].rstrip(".\r\n"))
    port = parsed.port or 6099
    return f"http://127.0.0.1:{port}", token_matches[-1]


def _napcat_webui_request(
    base_url: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    credential: str = "",
) -> object:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2.5) as response:
        result = json.load(response)
    if isinstance(result, dict) and result.get("code") not in {None, 0}:
        raise RuntimeError(str(result.get("message") or "NapCat WebUI request failed"))
    return result.get("data") if isinstance(result, dict) else result


def _napcat_webui_qrcode(log_path: Path, target: Path) -> tuple[bool, Path | None]:
    connection = _napcat_webui_connection(log_path)
    if connection is None:
        return False, None
    base_url, token = connection
    credential_data = _napcat_webui_request(
        base_url,
        "/api/auth/login",
        payload={"hash": hashlib.sha256(f"{token}.napcat".encode()).hexdigest()},
    )
    if isinstance(credential_data, dict):
        credential = str(
            credential_data.get("Credential")
            or credential_data.get("credential")
            or ""
        )
    else:
        credential = str(credential_data or "")
    if not credential:
        return False, None
    login_data = _napcat_webui_request(
        base_url,
        "/api/QQLogin/CheckLoginStatus",
        credential=credential,
    )
    logged_in = bool(
        login_data.get("isLogin") if isinstance(login_data, dict) else login_data
    )
    if logged_in:
        return True, None
    qrcode_data = _napcat_webui_request(
        base_url,
        "/api/QQLogin/GetQQLoginQrcode",
        credential=credential,
    )
    if isinstance(qrcode_data, dict):
        qrcode_text = str(
            qrcode_data.get("qrcode")
            or qrcode_data.get("url")
            or qrcode_data.get("data")
            or ""
        )
    else:
        qrcode_text = str(qrcode_data or "")
    if not qrcode_text:
        _napcat_webui_request(
            base_url,
            "/api/QQLogin/RefreshQRcode",
            credential=credential,
        )
        qrcode_data = _napcat_webui_request(
            base_url,
            "/api/QQLogin/GetQQLoginQrcode",
            credential=credential,
        )
        qrcode_text = str(
            qrcode_data.get("qrcode")
            or qrcode_data.get("url")
            or qrcode_data.get("data")
            or ""
        ) if isinstance(qrcode_data, dict) else str(qrcode_data or "")
    if not qrcode_text:
        return False, None
    import qrcode

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    image = qrcode.make(qrcode_text)
    image.save(temporary, format="PNG")
    os.replace(temporary, target)
    return False, target


def _napcat_log_reports_logged_in(log_path: Path, bot_qq: str) -> bool:
    text = _read_napcat_log(log_path)
    patterns = (
        rf"当前账号\s*[（(]?{re.escape(bot_qq)}[）)]?\s*已登录",
        rf"账号\s*[（(]?{re.escape(bot_qq)}[）)]?\s*已经登录",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def napcat_module_url(path: Path) -> str:
    """Build a file URL without resolving an ASCII launch alias.

    ``Path.resolve()`` expands a ``subst`` drive back to its original path.
    When that path contains non-ASCII characters NapCat's injector can stall
    before the QR code is generated. ``absolute().as_uri()`` keeps the mapped
    drive while still producing a valid JavaScript import URL.
    """
    return Path(path).absolute().as_uri()


def _ensure_onebot_network(payload: object) -> tuple[dict[str, object], bool]:
    """Repair a NapCat config payload without discarding account-specific settings."""
    changed = False
    if not isinstance(payload, dict):
        payload = {}
        changed = True
    network = payload.get("network")
    if not isinstance(network, dict):
        network = {}
        payload["network"] = network
        changed = True
    for key in (
        "httpServers",
        "httpSseServers",
        "httpClients",
        "websocketServers",
        "websocketClients",
        "plugins",
    ):
        if not isinstance(network.get(key), list):
            network[key] = []
            changed = True

    required_servers = {
        "httpServers": {
            "name": "xixi-http-server",
            "enable": True,
            "host": "127.0.0.1",
            "port": 3000,
            "messagePostFormat": "array",
            "reportSelfMessage": False,
            "token": "",
            "debug": False,
        },
        "websocketServers": {
            "name": "xixi-ws-server",
            "enable": True,
            "host": "127.0.0.1",
            "port": 3001,
            "messagePostFormat": "array",
            "reportSelfMessage": False,
            "token": "",
        },
    }
    for collection_name, required in required_servers.items():
        servers = network[collection_name]
        existing = next(
            (
                server
                for server in servers
                if isinstance(server, dict)
                and (
                    str(server.get("port") or "") == str(required["port"])
                    or str(server.get("name") or "") == required["name"]
                )
            ),
            None,
        )
        if existing is None:
            servers.append(dict(required))
            changed = True
            continue
        for key, value in required.items():
            if existing.get(key) != value:
                existing[key] = value
                changed = True
    return payload, changed


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_onebot_config(
    bot_qq_id: int | str,
    napcat_dir: Path | None = None,
) -> tuple[Path, bool]:
    """Ensure both current and legacy NapCat config layouts expose OneBot locally."""
    bot_qq = _normalized_qq_id(bot_qq_id)
    root = Path(napcat_dir) if napcat_dir is not None else resolve_napcat_dir()
    config_paths = (
        root / "config" / f"onebot11_{bot_qq}.json",
        root / "config" / f"napcat_{bot_qq}.json",
    )
    changed_any = False
    for config_path in config_paths:
        existed = config_path.is_file()
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
            payload = {}
        payload, changed = _ensure_onebot_network(payload)
        changed = changed or not existed
        if changed:
            _write_json_atomic(config_path, payload)
            changed_any = True

    return config_paths[0], changed_any


def powershell_lines(script: str) -> list[str]:
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            check=False,
            timeout=4,
        )
    except subprocess.TimeoutExpired:
        # WMI can stall independently of the QQ or Studio process. A failed
        # optional process scan must never prevent the application from booting.
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def bot_process_running() -> bool:
    script = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -in @('python.exe','pythonw.exe') -and "
        "($_.CommandLine -like '*-m app.main*--qq*' -or "
        "$_.CommandLine -like '*-m app.studio*') }; "
        "if ($p) { 'yes' }"
    )
    return "yes" in powershell_lines(script)


def configured_identity() -> dict[str, int]:
    return load_qq_identity(
        ROOT,
        data_root=RUNTIME_PATHS.data_dir,
        create_if_missing=True,
    )


def resolve_qq_executable(environ: Mapping[str, str] = os.environ) -> Path:
    configured = str(environ.get("QQ_EXECUTABLE") or "").strip().strip('"')
    candidates: list[Path] = [Path(configured)] if configured else []
    running = powershell_lines(
        "Get-CimInstance Win32_Process -Filter \"Name='QQ.exe'\" | "
        "Where-Object { $_.ExecutablePath } | Select-Object -First 1 -ExpandProperty ExecutablePath"
    )
    candidates.extend(Path(line) for line in running)

    if winreg is not None:
        registry_paths = (
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
        )
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key_path in registry_paths:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        uninstall, _ = winreg.QueryValueEx(key, "UninstallString")
                except OSError:
                    continue
                uninstall_path = Path(str(uninstall).strip().strip('"'))
                candidates.append(uninstall_path.parent / "QQ.exe")

    local_app_data = Path(environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates.extend((
        local_app_data / "Programs" / "Tencent" / "QQNT" / "QQ.exe",
        Path(environ.get("ProgramFiles", r"C:\Program Files")) / "Tencent" / "QQNT" / "QQ.exe",
        Path(environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tencent" / "QQNT" / "QQ.exe",
    ))
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("没有找到 QQ.exe，请先安装最新版 QQ，或设置 QQ_EXECUTABLE 指向 QQ.exe")


def injected_qq_pids(bot_qq_id: int | str) -> list[int]:
    bot_qq = _normalized_qq_id(bot_qq_id)
    script = (
        "$p = Get-CimInstance Win32_Process -Filter \"Name='QQ.exe'\" | "
        f"Where-Object {{ $_.CommandLine -match '(?:^|\\s)-q\\s+{bot_qq}(?:\\s|$)' }}; "
        "$p | ForEach-Object { $_.ProcessId }"
    )
    return [int(line) for line in powershell_lines(script) if line.isdigit()]


def stop_stale_bot_qq(bot_qq_id: int | str) -> bool:
    bot_qq_id = int(_normalized_qq_id(bot_qq_id))
    pids = sorted(set(injected_qq_pids(bot_qq_id)) | managed_qq_processes(bot_qq_id))
    if not pids:
        release_napcat_launch_root()
        unregister_managed_qq_account(bot_qq_id)
        unregister_managed_qq_processes(bot_qq_id)
        return True
    for pid in pids:
        status(f"正在结束昔夕专用 QQ 进程（PID {pid}）...")
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and injected_qq_pids(bot_qq_id):
        time.sleep(0.2)
    stopped = not injected_qq_pids(bot_qq_id)
    unregister_managed_qq_processes(bot_qq_id)
    if stopped:
        release_napcat_launch_root()
        unregister_managed_qq_account(bot_qq_id)
    return stopped


def wait_for_napcat(
    bot_qq_id: int | str,
    seconds: int,
    cancel_event: Event | None = None,
) -> dict[str, object] | None:
    bot_qq = str(bot_qq_id)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _raise_if_cancelled(cancel_event)
        login = onebot_login()
        if login and str(login.get("user_id")) == bot_qq and ws_port_ready():
            return login
        if cancel_event is not None:
            if cancel_event.wait(timeout=0.5):
                _raise_if_cancelled(cancel_event)
        else:
            time.sleep(2)
    return None


def launch_napcat(
    bot_qq_id: int | str,
    cancel_event: Event | None = None,
) -> dict[str, object]:
    bot_qq = _normalized_qq_id(bot_qq_id)
    napcat_dir = resolve_napcat_dir()
    qq_executable = resolve_qq_executable()

    _raise_if_cancelled(cancel_event)
    config_path, config_changed = ensure_onebot_config(bot_qq, napcat_dir)
    status(f"已检查 OneBot 本机连接配置：{config_path.name}")
    register_managed_qq_account(bot_qq)

    if injected_qq_pids(bot_qq) or managed_qq_processes(bot_qq):
        if not config_changed:
            status("检测到昔夕 QQ 正在启动，先等待 NapCat 就绪...")
            login = wait_for_napcat(bot_qq, 20, cancel_event)
            if login:
                return login
        else:
            status("OneBot 配置已补齐，正在重启昔夕专用 QQ 使其生效...")
        stop_stale_bot_qq(bot_qq)

    _raise_if_cancelled(cancel_event)
    register_managed_qq_account(bot_qq)

    launch_dir = ensure_napcat_launch_root(napcat_dir)
    boot = launch_dir / "NapCatWinBootMain.exe"
    hook = launch_dir / "NapCatWinBootHook.dll"
    main_module = launch_dir / "napcat.mjs"
    for required in (boot, hook, main_module, launch_dir / "qqnt.json"):
        if not required.is_file():
            release_napcat_launch_root()
            raise FileNotFoundError(f"QQ 通道文件不完整：{required}")

    log_dir = napcat_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "one_click_start.log"
    clear_napcat_qrcodes(napcat_dir)
    load_path = launch_dir / "loadNapCat.js"
    main_module_url = napcat_module_url(main_module)
    load_path.write_text(
        f"(async () => {{await import({json.dumps(main_module_url, ensure_ascii=False)})}})()\n",
        encoding="utf-8",
    )
    launch_environment = os.environ.copy()
    launch_environment.update({
        "NAPCAT_PATCH_PACKAGE": str(launch_dir / "qqnt.json"),
        "NAPCAT_LOAD_PATH": str(load_path),
        "NAPCAT_INJECT_PATH": str(hook),
        "NAPCAT_LAUNCHER_PATH": str(boot),
        "NAPCAT_MAIN_PATH": str(main_module),
    })
    status("正在启动 NapCat 和昔夕 QQ...")
    with log_path.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [str(boot), str(qq_executable), str(hook), bot_qq],
            cwd=launch_dir,
            env=launch_environment,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    register_managed_qq_process(bot_qq, process.pid)

    status("正在等待 QQ 登录；如果出现登录窗口，请按提示完成登录...")
    try:
        deadline = time.monotonic() + 600
        qr_deadline = time.monotonic() + 45
        logged_in_service_deadline: float | None = None
        next_webui_probe = time.monotonic() + 2
        qr_reported = False
        login = None
        while time.monotonic() < deadline:
            _raise_if_cancelled(cancel_event)
            login = onebot_login()
            if login and str(login.get("user_id")) == bot_qq and ws_port_ready():
                break
            qrcode = find_napcat_qrcode(napcat_dir)
            if qrcode is not None and not qr_reported:
                status(f"登录二维码已经生成：{qrcode}")
                qr_reported = True
            now = time.monotonic()
            if (
                logged_in_service_deadline is None
                and _napcat_log_reports_logged_in(log_path, bot_qq)
            ):
                logged_in_service_deadline = now + 120
                qr_reported = True
                status("检测到目标 QQ 已登录，正在等待消息通道就绪...")
            if qrcode is None and now >= next_webui_probe:
                next_webui_probe = now + 2
                try:
                    webui_logged_in, webui_qrcode = _napcat_webui_qrcode(
                        log_path,
                        napcat_dir / "cache" / "xixi-login-qrcode.png",
                    )
                except Exception:
                    pass
                else:
                    if webui_qrcode is not None and not qr_reported:
                        status(f"已从 NapCat 登录页面取得二维码：{webui_qrcode}")
                        qr_reported = True
                    if webui_logged_in and logged_in_service_deadline is None:
                        logged_in_service_deadline = now + 120
                        qr_reported = True
                        status("QQ 已登录，正在等待消息通道就绪...")
            if process.poll() is not None and login is None:
                try:
                    tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-16:])
                except OSError:
                    tail = ""
                raise RuntimeError(f"NapCat 启动后提前退出。{tail[-900:]}")
            if logged_in_service_deadline is not None and now >= logged_in_service_deadline:
                raise RuntimeError(
                    "QQ 已登录，但 NapCat 消息通道没有在 2 分钟内就绪。"
                    "请关闭正在运行的 QQ 后重新登录，应用会自动修复 OneBot 配置。"
                )
            if not qr_reported and now >= qr_deadline:
                try:
                    tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-16:])
                except OSError:
                    tail = ""
                raise RuntimeError(
                    "NapCat 已启动但 45 秒内没有生成二维码。请确认 QQ 可正常打开后重试。"
                    + (f" 启动日志：{tail[-700:]}" if tail else "")
                )
            if cancel_event is not None:
                if cancel_event.wait(timeout=0.5):
                    _raise_if_cancelled(cancel_event)
            else:
                time.sleep(0.5)
    except QQLaunchCancelled:
        stop_stale_bot_qq(bot_qq)
        raise
    except Exception:
        stop_stale_bot_qq(bot_qq)
        raise
    if not login:
        stop_stale_bot_qq(bot_qq)
        raise RuntimeError(
            "NapCat 在 10 分钟内没有完成扫码登录。请重新点击“登录二维码”获取新二维码；"
            f"详细日志位于 {log_path}。"
        )
    return login


def xixi_runtime_environment() -> dict[str, str]:
    identity = configured_identity()
    bot_qq = str(identity["bot_qq_id"])
    owner_qq = str(identity["owner_qq_id"])
    env = os.environ.copy()
    napcat_dir = resolve_napcat_dir()
    voice_root = _default_gpt_sovits_root()
    if not RUNTIME_PATHS.public_release:
        voice_root = Path(os.environ.get("GPT_SOVITS_ROOT", str(voice_root)))
    env.update(
        {
            "PYTHONUTF8": "1",
            "XIXI_DATA_HOME": str(RUNTIME_PATHS.data_home),
            "XIXI_DATA_DIR": str(RUNTIME_PATHS.data_dir),
            "XIXI_LOG_DIR": str(RUNTIME_PATHS.logs_dir),
            "XIXI_DOWNLOAD_DIR": str(RUNTIME_PATHS.downloads_dir),
            "XIXI_COMPONENTS_DIR": str(RUNTIME_PATHS.components_dir),
            "XIXI_MODELS_DIR": str(RUNTIME_PATHS.models_dir),
            "NAPCAT_ROOT": str(napcat_dir),
            "GPT_SOVITS_ROOT": str(voice_root),
            "QQ_USER_ID": owner_qq,
            "BOT_QQ_ID": bot_qq,
            "ONEBOT_API": ONEBOT_API,
            "ONEBOT_WS": f"ws://127.0.0.1:{ONEBOT_WS_PORT}",
            "LLM_MODEL": "qwen2.5:3b",
            "USE_OPENAI": "0",
            "OPENAI_MODEL": "",
            "WEB_SEARCH_ENABLED": "1",
            "WEB_SEARCH_TIMEOUT_S": "10",
            "WEB_SEARCH_MAX_RESULTS": "5",
            "WEB_SEARCH_CACHE_MINUTES": "10",
            "VISION_ENABLED": "0",
            "VISION_MODEL": "",
            "VISION_TIMEOUT_S": "75",
            "VISION_MAX_IMAGES": "4",
            "VISION_MAX_IMAGE_BYTES": "10485760",
            "VISION_DETAIL": "high",
            "LEARNING_INTEREST_INTERVAL_HOURS": "2",
            "LEARNING_GENERAL_INTERVAL_HOURS": "12",
            "LEARNING_ACADEMIC_INTERVAL_HOURS": "24",
            "INTEREST_REFLECTION_ENABLED": "1",
            "INTEREST_REFLECTION_INTERVAL_HOURS": "6",
            "ANIME_LEARNING_ENABLED": "1",
            "ANIME_LEARNING_INTERVAL_HOURS": "2",
            "ANIME_LEARNING_LIMIT": "15",
            "KNOWLEDGE_REFLECTION_ENABLED": "1",
            "KNOWLEDGE_REFLECTION_BATCH_SIZE": "6",
            "OWNER_ADDRESS_CHANCE": "0.55",
            "OWNER_ADDRESS_MAX_GAP": "3",
            "OWNER_ADDRESSES": "主人",
            "WEATHER_ENABLED": "0",
            "WEATHER_LOCATION": "未设置",
            "WEATHER_CACHE_MINUTES": "10",
            "WEATHER_ALERT_ENABLED": "0",
            "WEATHER_ALERT_CHECK_MINUTES": "10",
            "WEATHER_ALERT_GROUP_ENABLED": "1",
            "WEATHER_ALERT_MAX_GROUP_MENTIONS": "20",
            "WEATHER_ALERT_EXCLUDED_QQ_IDS": bot_qq if bot_qq != "0" else "",
            "AUTONOMOUS_GROUP_IDS": "",
            "AUTONOMOUS_GROUP_COOLDOWN_S": "0",
            "AUTONOMOUS_GROUP_CONTEXT_IDLE_S": "1800",
            "AUTONOMOUS_GROUP_BUFFER_MESSAGES": "200",
            "AUTONOMOUS_GROUP_CONTEXT_MESSAGES": "24",
            "AUTONOMOUS_PRIVATE_INITIAL_MIN_MINUTES": "5",
            "AUTONOMOUS_PRIVATE_INITIAL_MAX_MINUTES": "20",
            "AUTONOMOUS_PRIVATE_MIN_INTERVAL_HOURS": "0.5",
            "AUTONOMOUS_PRIVATE_MAX_INTERVAL_HOURS": "2",
            "AUTONOMOUS_PRIVATE_MAX_PER_DAY": "6",
        }
    )
    overrides_path = RUNTIME_PATHS.data_dir / "runtime_overrides.json"
    try:
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        overrides = {}
    if isinstance(overrides, dict):
        env.update({str(key): str(value) for key, value in overrides.items()})
    return env


def launch_xixi_bot() -> None:
    if bot_process_running():
        status("昔夕聊天程序已经在运行，无需重复启动。")
        return

    pythonw = ROOT / "venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        raise FileNotFoundError(f"找不到昔夕的 Python 3.12 环境：{pythonw}")

    env = xixi_runtime_environment()
    owner_qq = str(configured_identity()["owner_qq_id"])
    subprocess.Popen(
        [str(pythonw), "-u", "-m", "app.main", "--qq", "--qq-user", owner_qq],
        cwd=ROOT,
        env=env,
        creationflags=CREATE_NO_WINDOW,
    )

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if bot_process_running():
            status("昔夕聊天程序已启动。")
            return
        time.sleep(1)
    raise RuntimeError(
        f"昔夕聊天程序启动失败，请查看 {RUNTIME_PATHS.logs_dir / 'app.log'}。"
    )


def main() -> int:
    try:
        bot_qq = str(configured_identity()["bot_qq_id"])
        login = onebot_login()
        if login and str(login.get("user_id")) == bot_qq and ws_port_ready():
            status(f"NapCat 已在线：{login.get('nickname', '昔夕')}（{bot_qq}）")
        else:
            login = launch_napcat(bot_qq)
            status(f"QQ 登录成功：{login.get('nickname', '昔夕')}（{bot_qq}）")

        launch_xixi_bot()
        status("启动完成，现在可以直接在 QQ 里和昔夕聊天。")
        return 0
    except Exception as exc:
        status(f"启动失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

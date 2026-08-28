from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import locale
import logging
import os
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import closing
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from .napcat_runtime import (
    find_napcat_root,
    provision_packaged_napcat,
    register_napcat_root,
    resolve_napcat_root,
)
from .voice_runtime import (
    VOICE_FAST_LANGDETECT_FILES,
    VOICE_G2PW_MODEL_FILES,
    VOICE_HF_MODEL_FILES,
    VOICE_NLTK_DATA_FILES,
    VOICE_SOURCE_FILES,
    chinese_sovits_path,
    multilingual_gpt_path,
    multilingual_sovits_path,
    register_voice_root,
    resolve_voice_root,
    voice_missing_artifacts,
    voice_nltk_data_root,
    voice_required_artifacts,
    voice_requirements_path,
    voice_root_ready,
)

logger = logging.getLogger("studio.capabilities")


class EnvironmentInstallCancelled(RuntimeError):
    """Raised inside an environment worker after the user cancels it."""


class EnvironmentDownloadTooSlow(RuntimeError):
    """Raised when a resumable mirror remains unusably slow for too long."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ActivityJournal:
    """Small append-only journal used by the control center for observability."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(
        self,
        category: str,
        title: str,
        *,
        status: str = "completed",
        detail: str = "",
        source: str = "studio",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": f"{time.time_ns():x}",
            "created_at": _now(),
            "category": str(category)[:40],
            "title": str(title)[:160],
            "status": str(status)[:24],
            "detail": str(detail)[:2000],
            "source": str(source)[:40],
            "metadata": metadata or {},
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def recent(self, limit: int = 100, category: str = "") -> dict[str, Any]:
        limit = max(1, min(300, int(limit)))
        if not self.path.is_file():
            return {"items": []}
        with self._lock:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        items: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if category and item.get("category") != category:
                continue
            items.append(item)
            if len(items) >= limit:
                break
        return {"items": items}


class BackupManager:
    def __init__(
        self,
        root: Path,
        journal: ActivityJournal,
        memory_db: Path | None = None,
        *,
        data_root: Path | None = None,
        persona_file: Path | None = None,
        interest_profile_file: Path | None = None,
        knowledge_file: Path | None = None,
        learning_sources_file: Path | None = None,
        meme_lexicon_file: Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.data_root = Path(data_root) if data_root else self.root / "data"
        self.journal = journal
        self.memory_db = Path(memory_db) if memory_db else self.data_root / "xixi_memory.db"
        self.memory_archive_name = f"data/{self.memory_db.name}"
        self.backup_files = {
            "persona.txt": Path(persona_file) if persona_file else self.root / "persona.txt",
            "interest_profile.json": (
                Path(interest_profile_file)
                if interest_profile_file
                else self.root / "interest_profile.json"
            ),
            "knowledge.txt": Path(knowledge_file) if knowledge_file else self.root / "knowledge.txt",
            "learning_sources.json": (
                Path(learning_sources_file)
                if learning_sources_file
                else self.root / "learning_sources.json"
            ),
            "meme_lexicon.json": (
                Path(meme_lexicon_file)
                if meme_lexicon_file
                else self.root / "meme_lexicon.json"
            ),
            "data/studio_settings.json": self.data_root / "studio_settings.json",
            "data/desktop_preferences.json": self.data_root / "desktop_preferences.json",
            "data/game_settings.json": self.data_root / "game_settings.json",
            "data/qq_identity.json": self.data_root / "qq_identity.json",
            "data/xixi_affective_state.json": self.data_root / "xixi_affective_state.json",
            "data/conversations.json": self.data_root / "conversations.json",
            self.memory_archive_name: self.memory_db,
        }
        self.backup_dir = self.data_root / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create(self) -> dict[str, Any]:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self.backup_dir / f"xixi-backup-{stamp}.zip"
        manifest = {
            "created_at": _now(),
            "format": 2,
            "schema": "xixi-local-backup",
            "note": "Credential files and API keys are intentionally excluded.",
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for archive_name, path in self.backup_files.items():
                if not path.is_file():
                    continue
                if path.suffix == ".db":
                    snapshot = self.backup_dir / f".{stamp}-{path.name}"
                    source = sqlite3.connect(path, timeout=30)
                    destination = sqlite3.connect(snapshot)
                    try:
                        source.backup(destination)
                    finally:
                        destination.close()
                        source.close()
                    archive.write(snapshot, archive_name)
                    snapshot.unlink(missing_ok=True)
                else:
                    archive.write(path, archive_name)
        result = {
            "name": target.name,
            "path": str(target),
            "size": target.stat().st_size,
            "created_at": manifest["created_at"],
        }
        self.journal.append("backup", "已创建本地备份", detail=target.name, metadata=result)
        return result

    def list(self) -> dict[str, Any]:
        items = []
        for path in sorted(self.backup_dir.glob("xixi-backup-*.zip"), reverse=True):
            stat = path.stat()
            items.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                }
            )
        return {"items": items[:30]}

    def import_bytes(self, data: bytes, original_name: str = "") -> dict[str, Any]:
        if not data or len(data) > 128 * 1024 * 1024:
            raise ValueError("备份文件为空或超过 128 MB")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        temp = self.backup_dir / f".import-{stamp}.zip"
        temp.write_bytes(data)
        try:
            if not zipfile.is_zipfile(temp):
                raise ValueError("选择的文件不是有效 ZIP 备份")
            with zipfile.ZipFile(temp, "r") as archive:
                if archive.testzip() is not None:
                    raise ValueError("备份文件已损坏")
                names = [item.filename.replace("\\", "/") for item in archive.infolist()]
                if "manifest.json" not in names:
                    raise ValueError("备份缺少 manifest.json")
                for name in names:
                    path = Path(name)
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError("备份中包含无效路径")
                    lowered = name.lower()
                    if any(token in lowered for token in (".env", "credential", "api_key", "secret")):
                        raise ValueError("备份中包含不应导入的凭据文件")
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                if int(manifest.get("format") or 0) not in {1, 2}:
                    raise ValueError("备份版本不受支持")
            target = self.backup_dir / f"xixi-backup-imported-{stamp}.zip"
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
        result = {
            "name": target.name,
            "path": str(target),
            "size": target.stat().st_size,
            "created_at": _now(),
            "original_name": Path(original_name).name[:200],
        }
        self.journal.append("backup", "已导入本地备份", detail=result["name"], metadata=result)
        return result

    def restore(self, name: str) -> dict[str, Any]:
        if Path(name).name != name or not name.startswith("xixi-backup-") or not name.endswith(".zip"):
            raise ValueError("备份名称无效")
        source = self.backup_dir / name
        if not source.is_file():
            raise ValueError("找不到这个备份")
        restored: list[str] = []
        with zipfile.ZipFile(source, "r") as archive:
            for member in archive.infolist():
                normalized = member.filename.replace("\\", "/")
                target = self.backup_files.get(normalized)
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_suffix(target.suffix + ".restore")
                with archive.open(member) as input_stream, temp.open("wb") as output_stream:
                    shutil.copyfileobj(input_stream, output_stream)
                if normalized == self.memory_archive_name:
                    source_db = sqlite3.connect(temp, timeout=30)
                    destination_db = sqlite3.connect(target, timeout=30)
                    try:
                        source_db.backup(destination_db)
                    finally:
                        destination_db.close()
                        source_db.close()
                    temp.unlink(missing_ok=True)
                else:
                    temp.replace(target)
                restored.append(normalized)
        if not restored:
            raise ValueError("备份中没有可恢复的数据")
        result = {"name": name, "restored_files": restored, "restored_at": _now()}
        self.journal.append("backup", "已恢复本地备份", detail=name, metadata={"files": len(restored)})
        return result


class DiagnosticCenter:
    def __init__(
        self,
        root: Path,
        memory_db: Path,
        status_provider: Callable[[], dict[str, Any]],
        journal: ActivityJournal,
        model_probe: Callable[[], tuple[str, str]] | None = None,
        storage_root: Path | None = None,
    ) -> None:
        self.root = root
        self.storage_root = Path(storage_root) if storage_root else Path(root)
        self.memory_db = memory_db
        self.status_provider = status_provider
        self.journal = journal
        self.model_probe = model_probe
        self._last: dict[str, Any] = {"checked_at": "", "items": []}

    @staticmethod
    def _item(key: str, label: str, state: str, detail: str, repair: str = "") -> dict[str, str]:
        return {"key": key, "label": label, "state": state, "detail": detail, "repair": repair}

    def run(self) -> dict[str, Any]:
        started = time.monotonic()
        status = self.status_provider()
        items: list[dict[str, str]] = []
        model = status["model"]
        model_enabled = bool(model.get("enabled", True))
        model_state = "ok" if model["online"] else ("paused" if not model_enabled else "error")
        model_detail = f"{model['name']} · {model['provider']}" if model["online"] else (
            "已按设置关闭" if not model_enabled else "未建立模型客户端，请检查密钥和中转地址"
        )
        if model["online"] and self.model_probe:
            model_state, probe_detail = self.model_probe()
            model_detail = f"{model['name']} · {probe_detail}"
        items.append(self._item(
            "model", "语言模型", model_state, model_detail,
        ))
        qq = status["qq"]
        qq_state = "ok" if qq["online"] else ("paused" if not qq["enabled"] else "error")
        qq_detail = "昔夕与 NapCat 均已连接" if qq["online"] else (
            "昔夕 QQ 已完全下线" if not qq["enabled"] and not qq.get("napcat_online") else
            "昔夕监听已关闭，但 QQ 账号仍在线" if not qq["enabled"] else "QQ 监听未连接"
        )
        items.append(self._item("qq", "QQ 通道", qq_state, qq_detail, "qq" if qq_state == "error" else ""))
        voice = status["voice"]
        voice_state = "ok" if voice.get("online") else ("paused" if not voice.get("enabled") else "error")
        items.append(self._item(
            "voice", "语音合成", voice_state,
            str(voice.get("detail") or voice.get("engine") or ("已按设置关闭" if voice_state == "paused" else "语音服务未响应")),
            "voice" if voice_state == "error" else "",
        ))
        vision = status["vision"]
        vision_state = "ok" if vision["online"] and vision["enabled"] else ("paused" if not vision["enabled"] else "error")
        items.append(self._item("vision", "图片理解", vision_state, vision["model"] if vision["enabled"] else "已按设置关闭"))
        try:
            with closing(sqlite3.connect(self.memory_db, timeout=5)) as connection:
                connection.execute("SELECT COUNT(*) FROM memories").fetchone()
                integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            memory_state = "ok" if integrity == "ok" else "error"
            memory_detail = "数据库可读写，完整性检查通过" if memory_state == "ok" else integrity
        except Exception as exc:
            memory_state, memory_detail = "error", f"数据库读取失败：{exc}"
        items.append(self._item("memory", "记忆数据库", memory_state, memory_detail))
        free = shutil.disk_usage(self.storage_root).free
        disk_state = "ok" if free >= 2 * 1024**3 else "warning"
        items.append(self._item("storage", "本地存储", disk_state, f"可用 {free / 1024**3:.1f} GB"))
        result = {
            "checked_at": _now(),
            "duration_ms": round((time.monotonic() - started) * 1000),
            "summary": {
                "ok": sum(item["state"] == "ok" for item in items),
                "attention": sum(item["state"] in {"warning", "error"} for item in items),
                "paused": sum(item["state"] == "paused" for item in items),
            },
            "items": items,
        }
        self._last = result
        self.journal.append("diagnostic", "系统检查完成", detail=f"{result['summary']['ok']} 项正常，{result['summary']['attention']} 项需留意", metadata=result["summary"])
        return result

    def latest(self) -> dict[str, Any]:
        return self._last if self._last["checked_at"] else self.run()

    def snapshot(self) -> dict[str, Any]:
        return self._last


class DependencyManager:
    """Detects runtime components and runs bounded repair jobs for Python packages."""

    _PYTHON_PACKAGES = {
        "ollama": ("ollama", "ollama>=0.3.0"),
        "whisper": ("faster_whisper", "faster-whisper>=1.0.0"),
        "sounddevice": ("sounddevice", "sounddevice>=0.4.6"),
        "screen_capture": ("mss", "mss>=9.0.0"),
        "desktop": ("webview", "pywebview>=5.4,<7"),
        "images": ("PIL", "Pillow>=10,<13"),
    }

    def __init__(self, root: Path, journal: ActivityJournal) -> None:
        self.root = Path(root)
        self.journal = journal
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def status(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        with self._lock:
            jobs = {key: dict(value) for key, value in self._jobs.items()}
        for key, (module, requirement) in self._PYTHON_PACKAGES.items():
            installed = importlib.util.find_spec(module) is not None
            job = jobs.get(key, {})
            state = str(job.get("state") or ("ok" if installed else "missing"))
            if state == "completed" and installed:
                state = "ok"
            items.append(
                {
                    "key": key,
                    "label": {
                        "ollama": "本地模型客户端",
                        "whisper": "语音识别",
                        "sounddevice": "麦克风采集",
                        "screen_capture": "屏幕采集",
                        "desktop": "本地桌面外壳",
                        "images": "图片处理",
                    }[key],
                    "state": state,
                    "detail": str(job.get("detail") or (f"已安装 {module}" if installed else f"缺少 {requirement}")),
                    "repairable": not installed and state != "installing",
                }
            )
        external = [
            {
                "key": "ollama_runtime",
                "label": "Ollama 程序",
                "state": "ok" if shutil.which("ollama") else "optional",
                "detail": shutil.which("ollama") or "当前使用云端模型时可以不安装",
                "repairable": False,
            },
            {
                "key": "ffmpeg",
                "label": "音频处理组件",
                "state": "ok" if shutil.which("ffmpeg") else "optional",
                "detail": shutil.which("ffmpeg") or "由 imageio-ffmpeg 提供内置版本",
                "repairable": False,
            },
        ]
        items.extend(external)
        return {
            "items": items,
            "ready": not any(item["state"] in {"missing", "failed"} for item in items),
            "python": sys.executable,
            "updated_at": _now(),
        }

    def repair(self, key: str) -> dict[str, Any]:
        if key not in self._PYTHON_PACKAGES:
            raise ValueError("该依赖暂不支持自动修复")
        with self._lock:
            current = self._jobs.get(key, {})
            if current.get("state") == "installing":
                return dict(current)
            requirement = self._PYTHON_PACKAGES[key][1]
            job = {"key": key, "state": "installing", "detail": f"正在安装 {requirement}", "started_at": _now()}
            self._jobs[key] = job

        def install() -> None:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", requirement],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                state = "completed" if result.returncode == 0 else "failed"
                output = (result.stdout if result.returncode == 0 else result.stderr).strip()
                detail = ("安装完成" if state == "completed" else "安装失败") + (f"：{output[-600:]}" if output else "")
            except Exception as exc:
                state, detail = "failed", f"安装失败：{exc}"
            with self._lock:
                self._jobs[key] = {**job, "state": state, "detail": detail, "finished_at": _now()}
            self.journal.append(
                "diagnostic",
                f"依赖修复{'完成' if state == 'completed' else '失败'}：{key}",
                status=state,
                detail=detail,
            )

        threading.Thread(target=install, name=f"xixi-dependency-{key}", daemon=True).start()
        return dict(job)


class EnvironmentManager:
    """Expose user-facing environment capabilities and install them concurrently.

    ``DependencyManager`` remains the low-level repair API used by the system
    diagnostics page. This manager groups those packages with external
    runtimes and models so the environment page does not expose implementation
    details as separate, duplicated features.
    """

    _OLLAMA_MODEL = os.environ.get("XIXI_LOCAL_VISION_MODEL", "qwen2.5vl:3b")
    _INSTALLABLE = frozenset({
        "local_voice",
        "qq_channel",
        "local_vision",
        "speech_recognition",
        "screen_observation",
    })
    _MAX_CONCURRENT_INSTALLS = 3
    _DOWNLOAD_SOURCE = "魔搭优先 · 多源断点续传"
    _DOWNLOAD_TRANSPORT = "后台命令行"
    _OLLAMA_DOMESTIC_RELEASE = {
        "revision": "v0.33.0",
        "size": 1_565_889_272,
        "sha256": "913230e6c251e60577dd4ef236b5a916202cb1b87481ed817e375fee4841372b",
    }
    _WHISPER_MODEL_REPOSITORY = "Systran/faster-whisper-small"
    _WHISPER_MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
    _WHISPER_MODEL_FILES = {
        "config.json": (
            2_370,
            "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828",
        ),
        "model.bin": (
            483_546_902,
            "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
        ),
        "tokenizer.json": (
            2_203_239,
            "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab",
        ),
        "vocabulary.txt": (
            459_861,
            "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913",
        ),
    }

    def __init__(
        self,
        root: Path,
        journal: ActivityJournal,
        status_provider: Callable[[], dict[str, Any]] | None = None,
        *,
        data_root: Path | None = None,
        downloads_root: Path | None = None,
        components_root: Path | None = None,
        models_root: Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.data_root = Path(data_root) if data_root else self.root / "data"
        self.downloads_root = (
            Path(downloads_root)
            if downloads_root
            else self.data_root / "environment_downloads"
        )
        self.components_root = (
            Path(components_root) if components_root else self.root / "runtime"
        )
        self.models_root = Path(models_root) if models_root else self.root
        self.journal = journal
        self.status_provider = status_provider
        self._lock = threading.RLock()
        self._managed_python_lock = threading.Lock()
        self._speech_install_lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._controls: dict[str, dict[str, Any]] = {}

    def _job(self, key: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._jobs.get(key) or {})

    def jobs(self) -> dict[str, Any]:
        with self._lock:
            jobs = {key: dict(value) for key, value in self._jobs.items()}
        return {
            "jobs": jobs,
            "max_concurrent_jobs": self._MAX_CONCURRENT_INSTALLS,
            "updated_at": _now(),
        }

    def _update_job(self, key: str, **changes: Any) -> dict[str, Any]:
        phase = str(changes.get("phase") or "")
        if phase and phase != "downloading":
            changes.setdefault("downloaded_bytes", 0)
            changes.setdefault("total_bytes", 0)
            changes.setdefault("speed_bps", 0)
            changes.setdefault("progress", None)
        with self._lock:
            current = dict(self._jobs.get(key) or {"key": key})
            current.update(changes)
            self._jobs[key] = current
            return dict(current)

    @staticmethod
    def _external_process_environment() -> dict[str, str]:
        """Remove frozen-app Python state before launching standalone tools."""
        environment = os.environ.copy()
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        environment.pop("_MEIPASS2", None)
        for name in tuple(environment):
            if name.startswith("_PYI_"):
                environment.pop(name, None)
        return environment

    @staticmethod
    def _decode_process_output(payload: bytes) -> str:
        encodings = ("utf-8", locale.getpreferredencoding(False), "gb18030")
        for encoding in dict.fromkeys(encodings):
            try:
                return payload.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return payload.decode("utf-8", errors="replace")

    @staticmethod
    def _remove_tree_with_retries(path: Path, *, attempts: int = 24) -> None:
        last_error: OSError | None = None
        for attempt in range(max(1, attempts)):
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                return
            except OSError as exc:
                last_error = exc
            if not path.exists():
                return
            time.sleep(min(0.15 * (attempt + 1), 0.75))
        raise RuntimeError("Python 运行环境文件正被占用，请稍候重试") from last_error

    def _control_for(self, key: str) -> dict[str, Any]:
        with self._lock:
            control = self._controls.get(key)
        if control is None:
            raise EnvironmentInstallCancelled("安装任务已经结束")
        return control

    def _raise_if_cancelled(self, key: str) -> None:
        if self._control_for(key)["cancel"].is_set():
            raise EnvironmentInstallCancelled("用户取消了安装")

    @staticmethod
    def _set_process_suspended(process: subprocess.Popen[Any], suspended: bool) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            process_suspend_resume = 0x0800
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            ntdll = ctypes.WinDLL("ntdll")
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            handle = kernel32.OpenProcess(process_suspend_resume, False, process.pid)
            if not handle:
                raise OSError(ctypes.get_last_error(), "无法控制下载进程")
            try:
                operation = ntdll.NtSuspendProcess if suspended else ntdll.NtResumeProcess
                operation.argtypes = [wintypes.HANDLE]
                operation.restype = ctypes.c_long
                status = operation(handle)
                if status != 0:
                    raise OSError(f"下载进程控制失败：0x{status & 0xFFFFFFFF:08x}")
            finally:
                kernel32.CloseHandle(handle)
            return
        os.kill(process.pid, signal.SIGSTOP if suspended else signal.SIGCONT)

    @staticmethod
    def _terminate_process(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=15,
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def control(self, key: str, action: str) -> dict[str, Any]:
        key = str(key or "").strip()
        action = str(action or "").strip().lower()
        if key not in self._INSTALLABLE:
            raise ValueError("未知的环境安装任务")
        with self._lock:
            job = dict(self._jobs.get(key) or {})
            control = self._controls.get(key)
        if not job or control is None or job.get("state") not in {"installing", "paused", "cancelling"}:
            raise ValueError("该安装任务当前没有运行")

        process = control.get("process")
        if action == "pause":
            if job.get("state") == "paused":
                return job
            if not job.get("can_pause"):
                raise ValueError("当前阶段暂不支持暂停，可以取消后重新安装")
            if process is not None and process.poll() is None and not control.get("process_suspended"):
                self._set_process_suspended(process, True)
                control["process_suspended"] = True
            control["pause"].set()
            return self._update_job(
                key,
                state="paused",
                detail="下载已暂停，临时文件会保留",
                speed_bps=0,
                can_pause=False,
                can_resume=True,
                can_cancel=True,
            )

        if action == "resume":
            if job.get("state") != "paused":
                raise ValueError("该任务当前没有暂停")
            if process is not None and process.poll() is None and control.get("process_suspended"):
                self._set_process_suspended(process, False)
                control["process_suspended"] = False
            control["pause"].clear()
            return self._update_job(
                key,
                state="installing",
                detail="正在继续下载",
                can_pause=True,
                can_resume=False,
                can_cancel=True,
            )

        if action == "cancel":
            if job.get("state") == "cancelling":
                return job
            control["cancel"].set()
            control["pause"].clear()
            cancelling = self._update_job(
                key,
                state="cancelling",
                detail="正在取消任务",
                speed_bps=0,
                can_pause=False,
                can_resume=False,
                can_cancel=False,
            )
            if process is not None and process.poll() is None:
                if control.get("process_suspended"):
                    try:
                        self._set_process_suspended(process, False)
                    except OSError:
                        logger.warning("could not resume environment process before cancellation")
                    control["process_suspended"] = False
                self._terminate_process(process)
            with self._lock:
                return dict(self._jobs.get(key) or cancelling)

        raise ValueError("不支持的任务操作")

    @staticmethod
    def _python_module(module: str) -> bool:
        return importlib.util.find_spec(module) is not None

    def _ollama_executable(self) -> Path | None:
        candidates: list[Path] = []
        found = shutil.which("ollama")
        if found:
            candidates.append(Path(found))
        candidates.extend(
            [
                Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
                Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Ollama" / "ollama.exe",
                self.root.parent / "ollama" / "ollama.exe",
            ]
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _napcat_root(self, *, provision: bool = True) -> Path | None:
        if provision:
            provisioned = provision_packaged_napcat(self.root, self.components_root)
            if provisioned is not None:
                return provisioned
        return resolve_napcat_root(
            self.root,
            self.components_root,
            discover=provision,
        )

    def _voice_root(self) -> Path:
        public_frozen = bool(getattr(sys, "frozen", False))
        default_root = (
            self.components_root / "GPT-SoVITS"
            if public_frozen
            else self.root.parent / "work" / "GPT-SoVITS"
        )
        return resolve_voice_root(
            default_root,
            allow_registered_fallback=not public_frozen,
            discover=not public_frozen,
        )

    @staticmethod
    def _path_uses_reparse_point(path: Path) -> bool:
        """Return whether an existing Windows path crosses a link or mount point."""
        current = Path(os.path.abspath(path))
        while True:
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                pass
            except OSError as exc:
                if getattr(exc, "winerror", None) == 448:
                    return True
            else:
                attributes = int(getattr(info, "st_file_attributes", 0))
                reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
                if attributes & reparse_flag or current.is_symlink():
                    return True
            parent = current.parent
            if parent == current:
                return False
            current = parent

    @classmethod
    def _supported_venv_python(cls, candidate: Path) -> bool:
        if not candidate.is_file():
            return False
        if cls._path_uses_reparse_point(candidate):
            logger.warning("skipping Python runtime behind a reparse point: %s", candidate)
            return False
        try:
            result = subprocess.run(
                [
                    str(candidate),
                    "-I",
                    "-c",
                    (
                        "import _socket, email.parser, json, socket, ssl, sys, venv; "
                        "print(json.dumps([sys.executable, "
                        "getattr(sys, '_base_executable', '')], ensure_ascii=True)); "
                        "raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)"
                    ),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=12,
                cwd=str(candidate.parent),
                env=cls._external_process_environment(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if result.returncode != 0:
            return False
        try:
            runtime_paths = json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return False
        if not isinstance(runtime_paths, list):
            return False
        for runtime_path in runtime_paths:
            if runtime_path and cls._path_uses_reparse_point(Path(str(runtime_path))):
                logger.warning(
                    "skipping Python launcher backed by a reparse-point runtime: %s -> %s",
                    candidate,
                    runtime_path,
                )
                return False
        return True

    def _existing_supported_python(self) -> Path | None:
        candidates: list[Path] = []
        configured = str(os.environ.get("XIXI_VOICE_PYTHON") or "").strip().strip('"')
        if configured:
            candidates.append(Path(os.path.expandvars(os.path.expanduser(configured))))

        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        candidates.append(
            local_app_data / "Programs" / "Python" / "Python310" / "python.exe"
        )

        launcher = shutil.which("py")
        if launcher:
            for version in ("3.10",):
                try:
                    result = subprocess.run(
                        [launcher, f"-{version}", "-I", "-c", "import sys; print(sys.executable)"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=8,
                        env=self._external_process_environment(),
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except (OSError, subprocess.SubprocessError):
                    continue
                if result.returncode == 0 and result.stdout.strip():
                    candidates.append(Path(result.stdout.strip().splitlines()[-1]))

        for name in ("python3.10", "python"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

        seen: set[str] = set()
        for candidate in candidates:
            key = os.path.normcase(os.path.abspath(candidate))
            if key in seen:
                continue
            seen.add(key)
            if self._supported_venv_python(candidate):
                return candidate
        return None

    def _managed_python(
        self,
        key: str = "local_voice",
        purpose: str = "昔夕本地语音系统",
        *,
        force_managed: bool = False,
    ) -> Path:
        with self._managed_python_lock:
            managed_root = self.components_root / "Python310"
            managed = managed_root / "python.exe"
            if self._supported_venv_python(managed):
                return managed
            if managed_root.exists():
                self._update_job(
                    key,
                    phase="preparing",
                    detail=f"正在修复{purpose}所需的 Python 3.10 运行环境",
                )
                self._remove_tree_with_retries(managed_root)
            if not getattr(sys, "frozen", False):
                return Path(sys.executable)
            if not force_managed:
                existing = self._existing_supported_python()
                if existing is not None:
                    self._update_job(
                        key,
                        phase="preparing",
                        detail=f"已发现可复用的 Python {existing.parent.name} 运行环境",
                    )
                    return existing

            archive_path = self.downloads_root / "python-3.10.11.nupkg"
            self.data_root.mkdir(parents=True, exist_ok=True)
            self.components_root.mkdir(parents=True, exist_ok=True)
            for attempt in range(2):
                archive = self._download_from_mirrors(
                    key,
                    (
                        "https://www.nuget.org/api/v2/package/python/3.10.11",
                        "https://api.nuget.org/v3-flatcontainer/python/3.10.11/python.3.10.11.nupkg",
                        "https://globalcdn.nuget.org/packages/python.3.10.11.nupkg",
                    ),
                    archive_path,
                    detail=f"正在下载{purpose}所需的 Python 运行环境",
                )
                extract_root = Path(
                    tempfile.mkdtemp(prefix="xixi-python310-extract-", dir=str(self.data_root))
                )
                staging_root = Path(
                    tempfile.mkdtemp(prefix=".Python310-install-", dir=str(self.components_root))
                )
                try:
                    self._update_job(
                        key,
                        phase="installing",
                        detail=f"正在校验并部署{purpose}专用 Python 3.10 运行环境",
                    )
                    try:
                        self._extract_zip_safely(key, archive, extract_root)
                    except zipfile.BadZipFile:
                        archive.unlink(missing_ok=True)
                        if attempt == 0:
                            self._update_job(
                                key,
                                phase="preparing",
                                detail="运行环境下载文件不完整，正在自动重新下载",
                            )
                            continue
                        raise RuntimeError("Python 运行环境下载文件不完整") from None
                    self._update_job(
                        key,
                        phase="installing",
                        detail="正在复制并校验 Python 3.10 运行环境",
                    )
                    portable_root = extract_root / "tools"
                    if not (portable_root / "python.exe").is_file():
                        archive.unlink(missing_ok=True)
                        raise RuntimeError("Python 运行环境压缩包结构无效")
                    shutil.copytree(portable_root, staging_root, dirs_exist_ok=True)
                    staged_python = staging_root / "python.exe"
                    if not self._supported_venv_python(staged_python):
                        archive.unlink(missing_ok=True)
                        if attempt == 0:
                            self._update_job(
                                key,
                                phase="preparing",
                                detail="运行环境完整性校验未通过，正在自动重新下载",
                            )
                            continue
                        raise RuntimeError("Python 运行环境完整性校验未通过")
                    if managed_root.exists():
                        self._remove_tree_with_retries(managed_root)
                    os.replace(staging_root, managed_root)
                finally:
                    shutil.rmtree(extract_root, ignore_errors=True)
                    shutil.rmtree(staging_root, ignore_errors=True)
                if self._supported_venv_python(managed):
                    return managed
                archive.unlink(missing_ok=True)
                if managed_root.exists():
                    self._remove_tree_with_retries(managed_root)
                self._update_job(
                    key,
                    phase="preparing",
                    detail="部署后的运行环境校验未通过，正在自动修复",
                )
            raise RuntimeError("Python 运行环境安装完成后仍不可用")

    @staticmethod
    def _is_untrusted_mount_error(exc: BaseException) -> bool:
        detail = str(exc).casefold()
        return (
            getattr(exc, "winerror", None) == 448
            or "winerror 448" in detail
            or "不受信任的装入点" in detail
            or "untrusted mount point" in detail
        )

    def _create_voice_venv(self, root: Path) -> None:
        target = root / ".venv"
        base_python = self._managed_python()
        try:
            self._run_command(
                "local_voice",
                [str(base_python), "-I", "-m", "venv", str(target)],
                timeout=600,
                cwd=base_python.parent,
                phase="installing",
                detail="正在创建昔夕本地语音运行环境",
            )
        except (OSError, RuntimeError) as exc:
            if not self._is_untrusted_mount_error(exc):
                raise
            logger.warning(
                "external Python could not create the voice environment; "
                "retrying with Xixi-managed Python: %s",
                base_python,
            )
            shutil.rmtree(target, ignore_errors=True)
            self._update_job(
                "local_voice",
                phase="installing",
                detail="检测到不兼容的外部 Python，正在切换到昔夕专用运行环境",
                progress=None,
            )
            base_python = self._managed_python(force_managed=True)
            self._run_command(
                "local_voice",
                [str(base_python), "-I", "-m", "venv", str(target)],
                timeout=600,
                cwd=base_python.parent,
                phase="installing",
                detail="正在重新创建昔夕本地语音运行环境",
            )

    def _local_voice_ready(self) -> bool:
        return voice_root_ready(self._voice_root())

    def _voice_package_models_root(self) -> Path:
        candidates = (
            self.root / "runtime" / "voice" / "package" / "models",
            self.root / "packaging" / "staging" / "voice_models",
            self.root / "packaging" / "dist" / "Xixi" / "runtime" / "voice" / "package" / "models",
        )
        required = {
            "xixi_voice_multilingual.ckpt",
            "xixi_voice_multilingual.pth",
            "xixi_voice_chinese.pth",
        }
        for candidate in candidates:
            if all((candidate / name).is_file() for name in required):
                return candidate
        return candidates[0]

    def _voice_package_engine_root(self) -> Path:
        candidates = (
            self.root / "runtime" / "voice" / "package" / "engine",
            self.root / "packaging" / "staging" / "voice_engine",
            self.root / "packaging" / "dist" / "Xixi" / "runtime" / "voice" / "package" / "engine",
        )
        for candidate in candidates:
            if all((candidate / Path(relative)).is_file() for relative in VOICE_SOURCE_FILES):
                return candidate
        return candidates[0]

    def _voice_package_nltk_data_root(self) -> Path:
        candidates = (
            self.root / "runtime" / "voice" / "package" / "nltk_data",
            self.root / "packaging" / "staging" / "voice_nltk_data",
            self.root / "packaging" / "dist" / "Xixi" / "runtime" / "voice" / "package" / "nltk_data",
        )
        for candidate in candidates:
            if all((candidate / Path(relative)).is_file() for relative in VOICE_NLTK_DATA_FILES):
                return candidate
        return candidates[0]

    def _seed_packaged_voice_assets(self, root: Path) -> None:
        """Place Xixi's release voice files before any network installation."""
        package_models = self._voice_package_models_root()
        model_targets = {
            "xixi_voice_multilingual.ckpt": multilingual_gpt_path(root),
            "xixi_voice_multilingual.pth": multilingual_sovits_path(root),
            "xixi_voice_chinese.pth": chinese_sovits_path(root),
            "s1v3.ckpt": root / "GPT_SoVITS" / "pretrained_models" / "s1v3.ckpt",
        }
        for name, target in model_targets.items():
            if target.is_file():
                continue
            source = package_models / name
            if not source.is_file():
                if name == "s1v3.ckpt":
                    continue
                raise RuntimeError(f"安装包缺少昔夕语音模型：{name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        packaged_config = self.root / "runtime" / "voice" / "xixi_voice_tts_infer.yaml"
        target_config = root / "xixi_voice_tts_infer.yaml"
        if packaged_config.is_file() and not target_config.is_file():
            shutil.copy2(packaged_config, target_config)

    def _seed_packaged_voice_engine(self, root: Path) -> bool:
        package_engine = self._voice_package_engine_root()
        if not package_engine.is_dir():
            return False
        self._merge_missing_tree("local_voice", package_engine, root)
        return all((root / Path(relative)).is_file() for relative in VOICE_SOURCE_FILES)

    def _seed_packaged_nltk_data(self, root: Path) -> bool:
        package_nltk_data = self._voice_package_nltk_data_root()
        if not package_nltk_data.is_dir():
            return False
        self._merge_missing_tree(
            "local_voice",
            package_nltk_data,
            voice_nltk_data_root(root),
        )
        return all(
            (voice_nltk_data_root(root) / Path(relative)).is_file()
            for relative in VOICE_NLTK_DATA_FILES
        )

    def _voice_requirements_for_install(self, root: Path) -> Path:
        """Remove packages installed separately with known Windows wheels."""
        source = voice_requirements_path(root)
        target = root / "requirements-xixi-windows.txt"
        skipped = {"pyopenjtalk", "torch", "torchaudio", "torchvision"}
        filtered: list[str] = []
        for raw_line in source.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                filtered.append(raw_line)
                continue
            if stripped.startswith("--no-binary"):
                continue
            package_name = stripped.split(";", 1)[0].strip()
            package_name = package_name.split("[", 1)[0]
            package_name = package_name.split("=", 1)[0]
            package_name = package_name.split("<", 1)[0]
            package_name = package_name.split(">", 1)[0].strip().casefold()
            if package_name in skipped:
                continue
            filtered.append(raw_line)
        target.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
        return target

    def _packaged_pyopenjtalk_wheel(self) -> Path | None:
        wheel_root = self.root / "runtime" / "voice" / "package" / "wheels"
        return next(iter(sorted(wheel_root.glob("pyopenjtalk_plus-*-cp310-*-win_amd64.whl"))), None)

    def _uv_executable(self) -> Path | None:
        candidates = (
            self.root / "runtime" / "install_tools" / "uv.exe",
            self.root / "packaging" / "staging" / "install_tools" / "uv.exe",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        found = shutil.which("uv")
        return Path(found) if found else None

    def _python_package_install_command(
        self,
        python_path: Path,
        arguments: list[str],
    ) -> list[str]:
        """Use uv's concurrent resolver when available, with pip as fallback."""
        uv = self._uv_executable()
        if uv is None:
            return [str(python_path), "-I", "-m", "pip", "install", *arguments]
        cache_root = self.downloads_root / "uv-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        filtered = [argument for argument in arguments if argument != "--prefer-binary"]
        return [
            str(uv),
            "pip",
            "install",
            "--python",
            str(python_path),
            "--cache-dir",
            str(cache_root),
            "--link-mode",
            "copy",
            "--index-strategy",
            "unsafe-best-match",
            *filtered,
        ]

    @staticmethod
    def _python_imports(
        python_path: Path,
        *modules: str,
        attempts: int = 1,
        timeout: float = 60,
    ) -> bool:
        if not python_path.is_file():
            return False
        imports = "; ".join(f"import {module}" for module in modules)
        attempts = max(1, int(attempts))
        last_detail = ""
        for attempt in range(attempts):
            try:
                result = subprocess.run(
                    [str(python_path), "-I", "-c", imports],
                    capture_output=True,
                    timeout=max(1, float(timeout)),
                    cwd=str(python_path.parent),
                    env=EnvironmentManager._external_process_environment(),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                last_detail = str(exc)
            else:
                if result.returncode == 0:
                    return True
                output = result.stderr or result.stdout or b""
                if isinstance(output, bytes):
                    last_detail = output.decode("utf-8", errors="replace")
                else:
                    last_detail = str(output)
                last_detail = last_detail.strip() or f"exit code {result.returncode}"
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
        logger.warning(
            "Python import verification failed: runtime=%s modules=%s detail=%s",
            python_path,
            ",".join(modules),
            last_detail[-1200:],
        )
        return False

    def _whisper_model_ready(self) -> bool:
        configured = os.environ.get("WHISPER_MODEL_PATH", "").strip()
        candidates = [Path(configured)] if configured else []
        candidates.append(self.models_root / "whisper-small-full")
        candidates.append(self.root / "whisper-small-full")
        return any(
            candidate.is_dir()
            and (candidate / "model.bin").is_file()
            and (candidate / "model.bin").stat().st_size > 100_000_000
            and (candidate / "config.json").is_file()
            and (candidate / "tokenizer.json").is_file()
            for candidate in candidates
        )

    def _ollama_models(self, executable: Path | None) -> tuple[set[str], str]:
        if executable is None:
            return set(), "Ollama 程序未检测到"
        try:
            result = subprocess.run(
                [str(executable), "list"],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return set(), f"本地模型服务暂不可用：{exc}"
        if result.returncode != 0:
            return set(), "Ollama 程序已安装，模型服务尚未响应"
        models: set[str] = set()
        for line in result.stdout.splitlines()[1:]:
            name = line.strip().split(maxsplit=1)[0] if line.strip() else ""
            if name:
                models.add(name)
        return models, ""

    @staticmethod
    def _status_label(state: str) -> str:
        return {
            "ok": "已就绪",
            "optional": "可稍后配置",
            "missing": "未安装",
            "installing": "安装中",
            "paused": "已暂停",
            "cancelling": "正在取消",
            "cancelled": "已取消",
            "failed": "安装失败",
        }.get(state, "待检查")

    def _base_item(
        self,
        key: str,
        state: str,
        detail: str,
        *,
        repairable: bool = False,
        action: str = "none",
        status_label: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job = self._job(key)
        job_state = str(job.get("state") or "")
        if state != "ok" and job_state in {"installing", "paused", "cancelling"}:
            state = job_state
            detail = str(job.get("detail") or "正在安装")
        elif job.get("state") == "failed" and state != "ok":
            state = "failed"
            detail = str(job.get("detail") or "安装失败，请重试")
        elif job.get("state") == "cancelled" and state != "ok":
            state = "cancelled"
            detail = str(job.get("detail") or "安装已取消，可以重新开始")
        return {
            "key": key,
            "state": state,
            "status_label": status_label or self._status_label(state),
            "detail": detail,
            "repairable": bool(repairable and state not in {"ok", "installing", "paused", "cancelling"}),
            "action": action,
            "job": job,
            **(extra or {}),
        }

    def status(self) -> dict[str, Any]:
        runtime = self.status_provider() if self.status_provider else {}
        model = runtime.get("model") or {}
        voice = runtime.get("voice") or {}
        qq = runtime.get("qq") or {}

        ollama = self._ollama_executable()
        ollama_models, ollama_detail = self._ollama_models(ollama)
        local_vision_ready = self._OLLAMA_MODEL in ollama_models
        cloud_vision_ready = bool((runtime.get("vision") or {}).get("online"))
        frozen = bool(getattr(sys, "frozen", False))
        whisper_modules_ready = self._python_module("faster_whisper") and self._python_module("sounddevice")
        whisper_model_ready = self._whisper_model_ready()
        whisper_ready = whisper_modules_ready and whisper_model_ready
        screen_ready = self._python_module("mss") and self._python_module("PIL")
        voice_root = self._voice_root()
        voice_total = len(voice_required_artifacts(voice_root))
        voice_ready = self._local_voice_ready()
        voice_missing = {} if voice_ready else voice_missing_artifacts(voice_root)
        napcat_ready = self._napcat_root(provision=False) is not None
        packaged_voice_models = self._voice_package_models_root()
        trained_voice_ready = all(
            (packaged_voice_models / name).is_file()
            for name in (
                "xixi_voice_multilingual.ckpt",
                "xixi_voice_multilingual.pth",
                "xixi_voice_chinese.pth",
            )
        )
        model_configured = bool(model.get("name") and model.get("provider"))
        model_state = (
            "ok"
            if model.get("online")
            else ("failed" if model_configured and model.get("enabled", True) else "optional")
        )

        items = [
            self._base_item(
                "chat_model",
                model_state,
                f"{model.get('name') or '聊天模型'} · {model.get('provider') or '未连接'}"
                if model.get("online") else (
                    "聊天模型连接异常，请检查供应商配置"
                    if model_configured else "聊天模型尚未配置，可进入“模型与 API”后连接"
                ),
                action="configure",
                status_label="连接异常" if model_state == "failed" else ("待配置" if model_state == "optional" else ""),
            ),
            self._base_item(
                "local_voice",
                "ok" if voice_ready else "optional",
                f"昔夕本地语音系统已安装并运行；已核验 {voice_total} 个关键文件" if voice_ready and voice.get("online") else (
                    f"昔夕本地语音系统已安装；已核验 {voice_total} 个关键文件，服务会在使用时启动"
                    if voice_ready else (
                        f"训练音色已随安装包就绪；运行环境缺少 {len(voice_missing)}/{voice_total} 项，修复时只补缺失内容"
                        if trained_voice_ready else
                        f"检测到缺少 {len(voice_missing)}/{voice_total} 项；修复时只补缺失内容"
                    )
                ),
                repairable=not voice_ready,
                action="install",
                status_label=(
                    f"缺少 {len(voice_missing)} 项"
                    if voice_missing else ""
                ),
                extra={
                    "missing_count": len(voice_missing),
                    "total_count": voice_total,
                    "trained_voice_ready": trained_voice_ready,
                },
            ),
            self._base_item(
                "qq_channel",
                "ok" if napcat_ready else "optional",
                "QQ 通道已连接" if qq.get("online") else (
                    "QQ 通道已安装，等待账号登录" if napcat_ready else "QQ 通道可在进入应用后按需配置并登录"
                ),
                repairable=not napcat_ready,
                action="install",
            ),
            self._base_item(
                "local_vision",
                "ok" if local_vision_ready else "optional",
                f"Ollama 已安装，已找到 {self._OLLAMA_MODEL}" if local_vision_ready else (
                    f"云端图片理解已就绪；可按需安装本地备用模型 {self._OLLAMA_MODEL}"
                    if cloud_vision_ready else (
                        "本地视觉可在进入应用后按需配置"
                    )
                ),
                repairable=True,
                action="install",
            ),
            self._base_item(
                "speech_recognition",
                "ok" if whisper_ready else ("failed" if frozen and not whisper_modules_ready else "optional"),
                "语音识别组件和本机模型已就绪" if whisper_ready else (
                    "当前安装文件缺少语音识别组件，请重新安装最新版"
                    if frozen and not whisper_modules_ready else "语音识别模型可在此处自动补齐"
                ),
                repairable=not (frozen and not whisper_modules_ready),
                action="none" if frozen and not whisper_modules_ready else "install",
                status_label="安装文件异常" if frozen and not whisper_modules_ready else "",
            ),
            self._base_item(
                "screen_observation",
                "ok" if screen_ready else ("failed" if frozen else "optional"),
                "屏幕观察与截图已内置" if screen_ready else (
                    "当前安装文件缺少屏幕观察组件，请重新安装最新版"
                    if frozen else "屏幕观察组件可自动补齐"
                ),
                repairable=not screen_ready and not frozen,
                action="install" if not screen_ready and not frozen else "none",
                status_label="安装文件异常" if frozen and not screen_ready else "",
            ),
        ]
        with self._lock:
            jobs = {key: dict(value) for key, value in self._jobs.items()}
        ready = sum(item["state"] in {"ok", "optional"} for item in items)
        return {
            "items": items,
            "ready": ready == len(items),
            "ready_count": ready,
            "python": sys.executable,
            "updated_at": _now(),
            "jobs": jobs,
            "max_concurrent_jobs": self._MAX_CONCURRENT_INSTALLS,
            "local_vision_model": self._OLLAMA_MODEL,
            "download_source": self._DOWNLOAD_SOURCE,
            "download_transport": self._DOWNLOAD_TRANSPORT,
        }

    def _run_command(
        self,
        key: str,
        command: list[str],
        *,
        timeout: int = 7200,
        cwd: Path | None = None,
        phase: str = "installing",
        detail: str = "正在安装组件",
        pausable: bool = False,
    ) -> str:
        self._raise_if_cancelled(key)
        self._update_job(
            key,
            state="installing",
            phase=phase,
            detail=detail,
            downloaded_bytes=0,
            total_bytes=0,
            progress=None,
            speed_bps=0,
            can_pause=pausable,
            can_resume=False,
            can_cancel=True,
            step_started_at=_now(),
            heartbeat_at=_now(),
            elapsed_seconds=0,
        )
        control = self._control_for(key)
        started = time.monotonic()
        last_tick = started
        last_heartbeat = started
        active_seconds = 0.0
        with tempfile.TemporaryFile(mode="w+b") as output_stream:
            process = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd else None,
                stdout=output_stream,
                stderr=subprocess.STDOUT,
                env=self._external_process_environment(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._lock:
                control["process"] = process
                control["process_suspended"] = False
            try:
                while process.poll() is None:
                    now = time.monotonic()
                    elapsed = now - last_tick
                    last_tick = now
                    if control["cancel"].is_set():
                        self._terminate_process(process)
                        raise EnvironmentInstallCancelled("用户取消了安装")
                    paused = control["pause"].is_set()
                    if paused and pausable and not control.get("process_suspended"):
                        self._set_process_suspended(process, True)
                        control["process_suspended"] = True
                    elif not paused and control.get("process_suspended"):
                        self._set_process_suspended(process, False)
                        control["process_suspended"] = False
                    if not paused:
                        active_seconds += elapsed
                    if now - last_heartbeat >= 1.0:
                        self._update_job(
                            key,
                            heartbeat_at=_now(),
                            elapsed_seconds=max(0, int(active_seconds)),
                        )
                        last_heartbeat = now
                    if active_seconds > timeout:
                        self._terminate_process(process)
                        raise RuntimeError("安装步骤等待超时")
                    time.sleep(0.2)
                self._raise_if_cancelled(key)
                output_stream.seek(0)
                output = self._decode_process_output(output_stream.read()).strip()
                if process.returncode != 0:
                    raise RuntimeError(output[-900:] or f"命令退出码 {process.returncode}")
                return output[-900:]
            finally:
                if process.poll() is None:
                    if control.get("process_suspended"):
                        try:
                            self._set_process_suspended(process, False)
                        except OSError:
                            logger.warning("could not resume environment process before cleanup")
                    self._terminate_process(process)
                with self._lock:
                    control["process"] = None
                    control["process_suspended"] = False

    @staticmethod
    def _remote_size_from_response(response: Any, *, request_method: str) -> int:
        headers = getattr(response, "headers", None)
        if headers is None:
            return 0
        content_range = str(headers.get("Content-Range") or "")
        match = re.search(r"/\s*(\d+)\s*$", content_range)
        if match:
            return max(0, int(match.group(1)))
        status = int(getattr(response, "status", 0) or 0)
        if request_method == "GET" and status == 206:
            return 0
        try:
            return max(0, int(headers.get("Content-Length") or 0))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _probe_remote_size(
        cls,
        url: str,
        headers: dict[str, str],
        *,
        timeout: float = 5.0,
    ) -> int:
        probe_headers = {**headers, "Accept-Encoding": "identity"}
        requests = (
            urllib.request.Request(url, headers=probe_headers, method="HEAD"),
            urllib.request.Request(
                url,
                headers={**probe_headers, "Range": "bytes=0-0"},
                method="GET",
            ),
        )
        for request in requests:
            try:
                with closing(urllib.request.urlopen(request, timeout=timeout)) as response:
                    size = cls._remote_size_from_response(
                        response,
                        request_method=request.get_method(),
                    )
                    if size > 0:
                        return size
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                continue
        return 0

    def _download_file(
        self,
        key: str,
        url: str,
        target: Path,
        *,
        detail: str,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        minimum_speed_bps: int = 0,
        slow_grace_seconds: float = 7.0,
        slow_probe_bytes: int = 384 * 1024,
        expected_size: int = 0,
    ) -> Path:
        """Download one file through a hidden command-line transfer process.

        The desktop process only supervises curl and reports the growing part
        file. This keeps downloads resumable and gives pause/cancel control the
        same process boundary in both source and frozen builds.
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(f"{target.name}.part")
        request_headers = {
            "User-Agent": "Xixi-Environment-Installer/1.0",
            **(headers or {}),
        }
        control = self._control_for(key)

        def finish_download(size: int, total: int | None = None) -> Path:
            completed_total = int(total or size)
            self._update_job(
                key,
                state="installing",
                phase="downloading",
                detail=f"{detail}（文件已就绪）",
                downloaded_bytes=size,
                total_bytes=completed_total,
                progress=100,
                speed_bps=0,
                can_pause=False,
                can_resume=False,
                can_cancel=True,
            )
            return target

        def promote_part(size: int, total: int | None = None) -> Path:
            for attempt in range(5):
                try:
                    os.replace(part, target)
                    return finish_download(size, total)
                except PermissionError:
                    if target.is_file() and target.stat().st_size == size:
                        part.unlink(missing_ok=True)
                        return finish_download(size, total)
                    if attempt == 4:
                        raise
                    time.sleep(0.25 * (attempt + 1))
            raise RuntimeError("无法保存已下载的文件")

        if target.is_file() and target.stat().st_size > 0:
            existing_size = target.stat().st_size
            part.unlink(missing_ok=True)
            return finish_download(existing_size)
        if target.exists():
            target.unlink(missing_ok=True)
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise RuntimeError("系统缺少 curl 命令行下载器，请先更新 Windows 系统组件")

        known_total = max(0, int(expected_size or 0))
        if not known_total:
            self._update_job(
                key,
                state="installing",
                phase="downloading",
                detail=f"{detail}（正在获取文件总大小）",
                downloaded_bytes=part.stat().st_size if part.is_file() else 0,
                total_bytes=0,
                progress=None,
                speed_bps=0,
                can_pause=False,
                can_resume=False,
                can_cancel=True,
            )
            known_total = self._probe_remote_size(url, request_headers)
        if known_total and part.is_file() and part.stat().st_size == known_total:
            return promote_part(known_total, known_total)

        range_reset = False
        attempts = max(1, int(max_retries) + 1)
        for attempt in range(1, attempts + 1):
            self._raise_if_cancelled(key)
            while control["pause"].is_set():
                self._raise_if_cancelled(key)
                time.sleep(0.2)

            command = [
                curl,
                "--location",
                "--fail",
                "--show-error",
                "--silent",
                "--connect-timeout", "5",
                "--retry", "1",
                "--retry-max-time", "15",
                "--retry-delay", "1",
                "--retry-all-errors",
                "--continue-at", "-",
                "--output", str(part),
            ]
            for name, value in request_headers.items():
                command.extend(["--header", f"{name}: {value}"])
            command.append(url)

            downloaded = part.stat().st_size if part.is_file() else 0
            self._update_job(
                key,
                state="installing",
                phase="downloading",
                detail=detail,
                downloaded_bytes=downloaded,
                total_bytes=known_total,
                progress=round(downloaded * 100 / known_total, 2) if known_total else None,
                speed_bps=0,
                can_pause=True,
                can_resume=False,
                can_cancel=True,
                download_source=self._source_label(url),
                download_transport=self._DOWNLOAD_TRANSPORT,
            )
            started_at = time.monotonic()
            sample_at = started_at
            sample_bytes = downloaded
            source_start_bytes = downloaded
            last_progress_at = started_at
            last_observed_size = downloaded
            paused_at: float | None = None
            paused_seconds = 0.0
            slow_since: float | None = None
            with tempfile.TemporaryFile(mode="w+b") as output_stream:
                with self._lock:
                    control["part_path"] = part
                process = subprocess.Popen(
                    command,
                    stdout=output_stream,
                    stderr=subprocess.STDOUT,
                    env=self._external_process_environment(),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                with self._lock:
                    control["process"] = process
                    control["process_suspended"] = False
                try:
                    while process.poll() is None:
                        if control["cancel"].is_set():
                            self._terminate_process(process)
                            raise EnvironmentInstallCancelled("用户取消了下载")
                        if control["pause"].is_set() and not control.get("process_suspended"):
                            self._set_process_suspended(process, True)
                            control["process_suspended"] = True
                        elif not control["pause"].is_set() and control.get("process_suspended"):
                            self._set_process_suspended(process, False)
                            control["process_suspended"] = False
                        now = time.monotonic()
                        current_size = part.stat().st_size if part.is_file() else 0
                        paused = control["pause"].is_set()
                        if paused and paused_at is None:
                            paused_at = now
                        elif not paused and paused_at is not None:
                            paused_seconds += now - paused_at
                            paused_at = None
                            slow_since = None
                            last_progress_at = now
                            sample_at = now
                            sample_bytes = current_size
                        if current_size > last_observed_size:
                            last_progress_at = now
                            last_observed_size = current_size
                        active_elapsed = max(
                            0.0,
                            now - started_at - paused_seconds - ((now - paused_at) if paused_at is not None else 0.0),
                        )
                        if now - sample_at >= 0.25:
                            speed = 0 if paused else max(
                                0, int((current_size - sample_bytes) / (now - sample_at))
                            )
                            self._update_job(
                                key,
                                downloaded_bytes=current_size,
                                total_bytes=known_total,
                                progress=(
                                    round(min(current_size, known_total) * 100 / known_total, 2)
                                    if known_total else None
                                ),
                                speed_bps=speed,
                                heartbeat_at=_now(),
                                elapsed_seconds=max(0, int(active_elapsed)),
                            )
                            source_bytes = max(0, current_size - source_start_bytes)
                            average_speed = int(source_bytes / active_elapsed) if active_elapsed > 0 else 0
                            stalled = (
                                active_elapsed >= slow_grace_seconds
                                and now - last_progress_at >= slow_grace_seconds
                            )
                            consistently_slow = (
                                active_elapsed >= slow_grace_seconds
                                and average_speed < minimum_speed_bps
                            )
                            if minimum_speed_bps > 0 and not paused and (stalled or consistently_slow):
                                slow_since = slow_since or now
                                if now - slow_since >= slow_grace_seconds:
                                    self._terminate_process(process)
                                    raise EnvironmentDownloadTooSlow(
                                        (
                                            "下载源长时间没有返回数据"
                                            if stalled and source_bytes < slow_probe_bytes
                                            else f"下载速度持续低于 {minimum_speed_bps // 1024} KB/s"
                                        )
                                    )
                            else:
                                slow_since = None
                            sample_at = now
                            sample_bytes = current_size
                        time.sleep(0.12)

                    output_stream.seek(0)
                    output = self._decode_process_output(output_stream.read()).strip()
                    current_size = part.stat().st_size if part.is_file() else 0
                    if process.returncode == 0 and current_size > 0:
                        if known_total and current_size != known_total:
                            if current_size > known_total and not range_reset:
                                part.unlink(missing_ok=True)
                                range_reset = True
                                self._update_job(
                                    key,
                                    detail=f"{detail}（本地续传文件无效，正在重新下载）",
                                    downloaded_bytes=0,
                                    total_bytes=known_total,
                                    progress=0,
                                    speed_bps=0,
                                )
                                continue
                            raise RuntimeError(f"下载文件大小不完整：{current_size}/{known_total}")
                        if not known_total and downloaded > 0 and current_size == downloaded and not range_reset:
                            part.unlink(missing_ok=True)
                            range_reset = True
                            self._update_job(
                                key,
                                detail=f"{detail}（正在校正无法确认的续传文件）",
                                downloaded_bytes=0,
                                total_bytes=0,
                                progress=None,
                                speed_bps=0,
                            )
                            continue
                        result = promote_part(current_size, known_total or current_size)
                        with self._lock:
                            control["part_path"] = None
                        return result
                    if process.returncode == 33 and current_size > 0 and not range_reset:
                        part.unlink(missing_ok=True)
                        range_reset = True
                        self._update_job(
                            key,
                            detail=f"{detail}（续传信息已失效，正在重新下载）",
                            downloaded_bytes=0,
                            total_bytes=known_total,
                            progress=0 if known_total else None,
                            speed_bps=0,
                        )
                        continue
                    if attempt >= attempts:
                        raise RuntimeError(output[-900:] or f"命令行下载失败，退出码 {process.returncode}")
                    self._update_job(
                        key,
                        detail=f"{detail}（网络异常，正在自动重试 {attempt}/{attempts - 1}）",
                        speed_bps=0,
                    )
                    time.sleep(min(1.5 * attempt, 4.5))
                finally:
                    if process.poll() is None:
                        if control.get("process_suspended"):
                            try:
                                self._set_process_suspended(process, False)
                            except OSError:
                                logger.warning("could not resume download process before cleanup")
                        self._terminate_process(process)
                    with self._lock:
                        control["process"] = None
                        control["process_suspended"] = False
        raise RuntimeError(f"命令行下载失败：{target.name}")

    @classmethod
    def _source_label(cls, url: str) -> str:
        normalized = str(url).casefold()
        if "modelscope.cn" in normalized:
            return "魔搭 ModelScope"
        if any(host in normalized for host in ("ghfast.top", "gh-proxy.com", "ghproxy.net")):
            return "GitHub 加速备用源"
        if "github.com" in normalized or "githubusercontent.com" in normalized:
            return "GitHub 官方源"
        if "hf-mirror.com" in normalized:
            return "Hugging Face 镜像"
        if "huggingface.co" in normalized:
            return "Hugging Face 官方源"
        return "官方或备用下载源"

    @staticmethod
    def _modelscope_url(repository: str, revision: str, relative: str) -> str:
        return (
            f"https://www.modelscope.cn/models/{repository}/resolve/"
            f"{quote(revision, safe='')}/{quote(relative, safe='/')}"
        )

    def _download_from_mirrors(
        self,
        key: str,
        urls: tuple[str, ...],
        target: Path,
        *,
        detail: str,
    ) -> Path:
        last_error: Exception | None = None
        for index, url in enumerate(urls, start=1):
            try:
                return self._download_file(
                    key,
                    url,
                    target,
                    detail=detail if index == 1 else f"{detail}（正在切换备用下载源）",
                    max_retries=0 if index < len(urls) else 2,
                    minimum_speed_bps=64 * 1024 if index < len(urls) else 0,
                    slow_grace_seconds=6.0,
                    slow_probe_bytes=96 * 1024,
                )
            except EnvironmentInstallCancelled:
                raise
            except (EnvironmentDownloadTooSlow, RuntimeError, urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                logger.warning(
                    "environment download source failed: target=%s source=%s/%s error=%s",
                    target,
                    index,
                    len(urls),
                    exc,
                )
        raise RuntimeError(f"所有下载源均不可用：{target.name}") from last_error

    @staticmethod
    def _file_matches_release(
        path: Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> bool:
        if not path.is_file() or path.stat().st_size != expected_size:
            return False
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            return False
        return digest.hexdigest().casefold() == expected_sha256.casefold()

    def _download_verified_from_mirrors(
        self,
        key: str,
        urls: tuple[str, ...],
        target: Path,
        *,
        detail: str,
        expected_size: int,
        expected_sha256: str,
    ) -> Path:
        part = target.with_name(f"{target.name}.part")
        if self._file_matches_release(
            target,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        ):
            part.unlink(missing_ok=True)
            return target
        if target.exists():
            target.unlink(missing_ok=True)

        last_error: Exception | None = None
        for index, url in enumerate(urls, start=1):
            try:
                result = self._download_file(
                    key,
                    url,
                    target,
                    detail=detail if index == 1 else f"{detail}（正在切换备用下载源）",
                    max_retries=0 if index < len(urls) else 2,
                    minimum_speed_bps=48 * 1024 if index < len(urls) else 0,
                    slow_grace_seconds=8.0,
                    slow_probe_bytes=96 * 1024,
                    expected_size=expected_size,
                )
            except EnvironmentInstallCancelled:
                raise
            except (EnvironmentDownloadTooSlow, RuntimeError, urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                logger.warning(
                    "verified environment download source failed: target=%s source=%s/%s error=%s",
                    target,
                    index,
                    len(urls),
                    exc,
                )
                continue

            self._update_job(
                key,
                phase="installing",
                detail=f"正在校验下载文件：{target.name}",
            )
            if self._file_matches_release(
                result,
                expected_size=expected_size,
                expected_sha256=expected_sha256,
            ):
                return result
            last_error = RuntimeError("文件大小或校验值不一致")
            logger.warning("downloaded environment file failed verification: %s", target)
            target.unlink(missing_ok=True)
            part.unlink(missing_ok=True)

        target.unlink(missing_ok=True)
        raise RuntimeError(f"下载源暂时不可用，请检查网络后重试：{target.name}") from last_error

    def _extract_zip_safely(self, key: str, archive_path: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        target_root = target.resolve()
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            for member in members:
                self._raise_if_cancelled(key)
                member_path = (target / member.filename).resolve()
                if target_root not in member_path.parents and member_path != target_root:
                    raise RuntimeError("安装包包含无效路径")
            self._update_job(
                key,
                phase="installing",
                detail="正在高速解压并部署组件",
                downloaded_bytes=0,
                total_bytes=0,
                progress=0 if members else 100,
                speed_bps=0,
                can_pause=False,
                can_resume=False,
                can_cancel=True,
            )
            update_interval = max(1, len(members) // 100)
            for index, member in enumerate(members, start=1):
                self._raise_if_cancelled(key)
                archive.extract(member, target)
                if index == len(members) or index % update_interval == 0:
                    self._update_job(
                        key,
                        progress=round(index * 100 / len(members), 2),
                        heartbeat_at=_now(),
                    )

    def _merge_missing_tree(self, key: str, source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        items = list(source.rglob("*"))
        self._update_job(
            key,
            phase="installing",
            detail="正在整理语音系统核心文件",
            progress=0 if items else 100,
        )
        update_interval = max(1, len(items) // 100)
        for index, item in enumerate(items, start=1):
            self._raise_if_cancelled(key)
            destination = target / item.relative_to(source)
            if item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)
            if index == len(items) or index % update_interval == 0:
                self._update_job(
                    key,
                    progress=round(index * 100 / len(items), 2),
                    heartbeat_at=_now(),
                )

    def _ensure_speech_recognition(self, job_key: str) -> str:
        purpose = "语音识别模型"
        with self._speech_install_lock:
            frozen = bool(getattr(sys, "frozen", False))
            modules_ready = self._python_module("faster_whisper") and self._python_module("sounddevice")
            python_path = Path(sys.executable)
            if not modules_ready:
                if frozen:
                    raise RuntimeError("当前安装文件缺少语音识别组件，请重新安装最新版")
                self._run_command(
                    job_key,
                    [
                        str(python_path),
                        "-I",
                        "-m",
                        "pip",
                        "install",
                        "faster-whisper>=1.0.0",
                        "sounddevice>=0.4.6",
                    ],
                    timeout=1800,
                    cwd=python_path.parent,
                    phase="downloading",
                    detail=f"正在下载并安装{purpose}运行组件",
                    pausable=True,
                )
            if self._whisper_model_ready():
                return f"{purpose}已经就绪"
            model_dir = self.models_root / "whisper-small-full"
            model_dir.mkdir(parents=True, exist_ok=True)
            pending = [
                (name, expected_size, expected_sha256)
                for name, (expected_size, expected_sha256) in self._WHISPER_MODEL_FILES.items()
                if not self._file_matches_release(
                    model_dir / name,
                    expected_size=expected_size,
                    expected_sha256=expected_sha256,
                )
            ]
            for index, (name, expected_size, expected_sha256) in enumerate(pending, start=1):
                encoded_name = quote(name, safe="")
                repository = self._WHISPER_MODEL_REPOSITORY
                revision = self._WHISPER_MODEL_REVISION
                self._download_verified_from_mirrors(
                    job_key,
                    (
                        self._modelscope_url(repository, "master", name),
                        f"https://hf-mirror.com/{repository}/resolve/{revision}/{encoded_name}",
                        f"https://huggingface.co/{repository}/resolve/{revision}/{encoded_name}",
                    ),
                    model_dir / name,
                    detail=f"正在下载{purpose} {index}/{len(pending)}：{name}",
                    expected_size=expected_size,
                    expected_sha256=expected_sha256,
                )
            if not self._whisper_model_ready():
                raise RuntimeError(f"{purpose}下载完成后完整性校验未通过")
            shutil.rmtree(model_dir / ".cache", ignore_errors=True)
            return f"{purpose}安装完成"

    def _install_speech_recognition(self) -> str:
        return self._ensure_speech_recognition("speech_recognition")

    def _download_ollama_installer(self) -> Path:
        target_dir = self.downloads_root
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "OllamaSetup.exe"
        release = self._OLLAMA_DOMESTIC_RELEASE
        revision = str(release["revision"])
        expected_size = int(release["size"])
        expected_sha256 = str(release["sha256"])
        metadata_path = target.with_name(f"{target.name}.release.json")
        expected_metadata = {
            "revision": revision,
            "size": expected_size,
            "sha256": expected_sha256,
        }
        current_metadata: dict[str, Any] = {}
        if metadata_path.is_file():
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    current_metadata = payload
            except (OSError, json.JSONDecodeError):
                current_metadata = {}
        if current_metadata != expected_metadata:
            target.unlink(missing_ok=True)
            target.with_name(f"{target.name}.part").unlink(missing_ok=True)
        metadata_path.write_text(
            json.dumps(expected_metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        github_url = (
            f"https://github.com/ollama/ollama/releases/download/{revision}/OllamaSetup.exe"
        )
        return self._download_verified_from_mirrors(
            "local_vision",
            (
                self._modelscope_url("Lixiang/ollama-release", revision, "OllamaSetup.exe"),
                github_url,
                f"https://ghfast.top/{github_url}",
                f"https://gh-proxy.com/{github_url}",
                f"https://ghproxy.net/{github_url}",
            ),
            target,
            detail="正在通过国内高速源下载本地视觉运行环境",
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )

    def _install_local_vision(self) -> str:
        executable = self._ollama_executable()
        if executable is None:
            installer: Path | None = None
            try:
                installer = self._download_ollama_installer()
                self._run_command(
                    "local_vision",
                    [str(installer), "/VERYSILENT", "/NORESTART"],
                    timeout=1800,
                    phase="installing",
                    detail="正在安装本地视觉运行环境",
                )
                try:
                    installer.unlink(missing_ok=True)
                    installer.with_name(f"{installer.name}.release.json").unlink(missing_ok=True)
                except OSError:
                    logger.warning("could not remove completed Ollama installer cache: %s", installer)
            except EnvironmentInstallCancelled:
                raise
            except Exception as download_error:
                winget = shutil.which("winget.exe") or shutil.which("winget")
                if not winget:
                    raise RuntimeError(
                        "Ollama 下载源暂时无法连接，且系统没有可用的 winget 备用安装器"
                    ) from download_error
                self._run_command(
                    "local_vision",
                    [
                        winget,
                        "install",
                        "--id", "Ollama.Ollama",
                        "--exact",
                        "--silent",
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                        "--disable-interactivity",
                    ],
                    timeout=1800,
                    phase="installing",
                    detail="直连下载不可用，正在通过 Windows 软件源安装本地视觉运行环境",
                )
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline and executable is None:
                self._raise_if_cancelled("local_vision")
                time.sleep(2)
                executable = self._ollama_executable()
        if executable is None:
            raise RuntimeError("Ollama 安装程序已运行，但没有找到 Ollama 程序")
        self._run_command(
            "local_vision",
            [str(executable), "pull", self._OLLAMA_MODEL],
            timeout=7200,
            phase="downloading",
            detail=f"正在下载本地视觉模型 {self._OLLAMA_MODEL}",
            pausable=True,
        )
        models, detail = self._ollama_models(executable)
        if self._OLLAMA_MODEL not in models:
            raise RuntimeError(detail or f"本地视觉模型下载完成后仍未找到 {self._OLLAMA_MODEL}")
        return "本地视觉模型安装完成"

    def _download_napcat(self) -> str:
        existing = self._napcat_root()
        if existing is not None:
            register_napcat_root(existing)
            return f"已发现并复用 QQ 通道：{existing}"
        target = self.components_root / "NapCat"
        target.mkdir(parents=True, exist_ok=True)
        packaged = self.root / "runtime" / "components" / "NapCat"
        if packaged.is_dir():
            self._update_job(
                "qq_channel",
                phase="installing",
                detail="正在从安装包补齐 QQ 通道组件",
                progress=None,
                speed_bps=0,
                can_pause=False,
                can_resume=False,
                can_cancel=True,
            )
            self._merge_missing_tree("qq_channel", packaged, target)
            installed_root = find_napcat_root(target, max_depth=4)
            if installed_root is not None:
                register_napcat_root(installed_root)
                return "QQ 通道已从安装包恢复，无需联网下载"
        request = urllib.request.Request(
            "https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Xixi-Environment-Installer/1.0"},
        )
        url = ""
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                release = json.loads(response.read().decode("utf-8"))
            assets = release.get("assets") if isinstance(release, dict) else []
            asset = next(
                (
                    item for item in assets or []
                    if isinstance(item, dict)
                    and str(item.get("name") or "").lower().endswith(".zip")
                    and "shell" in str(item.get("name") or "").lower()
                ),
                None,
            )
            url = str((asset or {}).get("browser_download_url") or "")
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            logger.warning("could not query latest QQ channel release; using stable latest URL")
        if not url:
            url = "https://github.com/NapNeko/NapCatQQ/releases/latest/download/NapCat.Shell.Windows.zip"
        archive_path = self.downloads_root / "napcat.zip"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        proxy_urls = tuple(
            candidate
            for candidate in (
                url,
                f"https://ghfast.top/{url}" if url.startswith("https://github.com/") else "",
                f"https://gh-proxy.com/{url}" if url.startswith("https://github.com/") else "",
                f"https://ghproxy.net/{url}" if url.startswith("https://github.com/") else "",
            )
            if candidate
        )
        self._download_from_mirrors(
            "qq_channel",
            proxy_urls,
            archive_path,
            detail="正在下载 QQ 通道组件",
        )
        self._update_job(
            "qq_channel",
            phase="installing",
            detail="正在解压 QQ 通道组件",
            progress=None,
            speed_bps=0,
            can_pause=False,
            can_resume=False,
            can_cancel=True,
        )
        try:
            self._extract_zip_safely("qq_channel", archive_path, target)
        except zipfile.BadZipFile:
            archive_path.unlink(missing_ok=True)
            raise RuntimeError("QQ 通道下载文件不完整，请重新安装") from None
        archive_path.unlink(missing_ok=True)
        installed_root = find_napcat_root(target, max_depth=4)
        if installed_root is None:
            raise RuntimeError("QQ 通道解压完成后仍未找到启动器")
        register_napcat_root(installed_root)
        return "QQ 通道安装完成，未改动登录配置"

    def _install_local_voice(self) -> str:
        root = self._voice_root()
        root.mkdir(parents=True, exist_ok=True)
        self._update_job(
            "local_voice",
            phase="preparing",
            detail="正在部署昔夕训练音色",
            progress=None,
        )
        self._seed_packaged_voice_assets(root)
        self._seed_packaged_voice_engine(root)
        self._seed_packaged_nltk_data(root)
        engine_tree_ready = (
            voice_requirements_path(root).is_file()
            and all((root / Path(relative)).is_file() for relative in VOICE_SOURCE_FILES)
        )
        if not engine_tree_ready:
            archive = self._download_from_mirrors(
                "local_voice",
                (
                    "https://codeload.github.com/RVC-Boss/GPT-SoVITS/zip/refs/heads/main",
                    "https://github.com/RVC-Boss/GPT-SoVITS/archive/refs/heads/main.zip",
                    "https://ghfast.top/https://github.com/RVC-Boss/GPT-SoVITS/archive/refs/heads/main.zip",
                    "https://gh-proxy.com/https://github.com/RVC-Boss/GPT-SoVITS/archive/refs/heads/main.zip",
                    "https://ghproxy.net/https://github.com/RVC-Boss/GPT-SoVITS/archive/refs/heads/main.zip",
                ),
                self.downloads_root / "gpt-sovits.zip",
                detail="正在下载语音系统核心程序（仅首次安装需要）",
            )
            self.data_root.mkdir(parents=True, exist_ok=True)
            extract_root = Path(
                tempfile.mkdtemp(prefix="xixi-gpt-sovits-", dir=str(self.data_root))
            )
            try:
                try:
                    self._extract_zip_safely("local_voice", archive, extract_root)
                except zipfile.BadZipFile:
                    archive.unlink(missing_ok=True)
                    raise RuntimeError("昔夕本地语音系统下载文件不完整，请重新安装") from None
                source = next((item for item in extract_root.iterdir() if item.is_dir()), None)
                if source is None:
                    archive.unlink(missing_ok=True)
                    raise RuntimeError("昔夕本地语音系统压缩包结构无效")
                self._merge_missing_tree("local_voice", source, root)
            finally:
                shutil.rmtree(extract_root, ignore_errors=True)

        source_repairs = [
            relative
            for relative in VOICE_SOURCE_FILES
            if not (root / Path(relative)).is_file()
        ]
        if not voice_requirements_path(root).is_file():
            source_repairs.append("requirements.txt")
        for index, relative in enumerate(source_repairs, start=1):
            target = root / Path(relative)
            encoded_relative = quote(relative, safe="/")
            self._download_from_mirrors(
                "local_voice",
                (
                    self._modelscope_url("RVC-Boss/GPT-SoVITS", "master", relative),
                    f"https://raw.githubusercontent.com/RVC-Boss/GPT-SoVITS/main/{encoded_relative}",
                    f"https://ghfast.top/https://raw.githubusercontent.com/RVC-Boss/GPT-SoVITS/main/{encoded_relative}",
                    f"https://gh-proxy.com/https://raw.githubusercontent.com/RVC-Boss/GPT-SoVITS/main/{encoded_relative}",
                    f"https://ghproxy.net/https://raw.githubusercontent.com/RVC-Boss/GPT-SoVITS/main/{encoded_relative}",
                ),
                target,
                detail=f"正在补齐核心程序文件 {index}/{len(source_repairs)}：{Path(relative).name}",
            )

        nltk_root = voice_nltk_data_root(root)
        missing_nltk_data = [
            relative
            for relative in VOICE_NLTK_DATA_FILES
            if not (nltk_root / Path(relative)).is_file()
        ]
        for index, relative in enumerate(missing_nltk_data, start=1):
            encoded_relative = quote(relative, safe="/")
            self._download_from_mirrors(
                "local_voice",
                (
                    f"https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/{encoded_relative}",
                    f"https://ghfast.top/https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/{encoded_relative}",
                    f"https://gh-proxy.com/https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/{encoded_relative}",
                    f"https://ghproxy.net/https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/{encoded_relative}",
                ),
                nltk_root / Path(relative),
                detail=f"正在补齐英语语音数据 {index}/{len(missing_nltk_data)}：{Path(relative).name}",
            )

        python_path = root / ".venv" / "Scripts" / "python.exe"
        if python_path.is_file() and not self._supported_venv_python(python_path):
            self._update_job(
                "local_voice",
                phase="installing",
                detail="正在更换为兼容的 Python 3.10 语音运行环境",
                progress=None,
            )
            shutil.rmtree(root / ".venv", ignore_errors=True)
        if not python_path.is_file():
            self._create_voice_venv(root)
        dependency_modules = (
            "torch",
            "torchaudio",
            "fastapi",
            "numpy",
            "yaml",
            "librosa",
            "transformers",
            "pypinyin",
            "opencc",
            "pyopenjtalk",
        )
        dependencies_ready = self._python_imports(python_path, *dependency_modules)
        if not dependencies_ready:
            self._run_command(
                "local_voice",
                self._python_package_install_command(
                    python_path,
                    [
                        "--upgrade", "pip", "setuptools", "wheel",
                        "--index-url", "https://mirrors.nju.edu.cn/pypi/web/simple",
                        "--extra-index-url", "https://pypi.org/simple",
                    ],
                ),
                timeout=1800,
                cwd=python_path.parent,
                phase="installing",
                detail="正在使用高速安装器准备语音依赖",
                pausable=True,
            )
            if not self._python_imports(python_path, "torch", "torchaudio"):
                torch_arguments = [
                    "torch==2.5.1+cu121", "torchaudio==2.5.1+cu121",
                    "--index-url", "https://mirrors.nju.edu.cn/pytorch/whl/cu121",
                ]
                try:
                    self._run_command(
                        "local_voice",
                        self._python_package_install_command(python_path, torch_arguments),
                        timeout=7200,
                        cwd=python_path.parent,
                        phase="installing",
                        detail="正在并发下载 NVIDIA 语音计算依赖",
                        pausable=True,
                    )
                except RuntimeError:
                    torch_arguments[-1] = "https://download.pytorch.org/whl/cu121"
                    self._run_command(
                        "local_voice",
                        self._python_package_install_command(python_path, torch_arguments),
                        timeout=7200,
                        cwd=python_path.parent,
                        phase="installing",
                        detail="加速源不可用，正在切换官方源继续安装",
                        pausable=True,
                    )
            if not self._python_imports(python_path, "pyopenjtalk"):
                wheel = self._packaged_pyopenjtalk_wheel()
                pyopenjtalk_source = str(wheel) if wheel is not None else "pyopenjtalk-plus==0.4.1.post8"
                self._run_command(
                    "local_voice",
                    self._python_package_install_command(
                        python_path,
                        [
                            pyopenjtalk_source,
                            "--index-url", "https://mirrors.nju.edu.cn/pypi/web/simple",
                            "--extra-index-url", "https://pypi.org/simple",
                        ],
                    ),
                    timeout=1800,
                    cwd=python_path.parent,
                    phase="installing",
                    detail="正在安装预编译的日语发音组件",
                    pausable=True,
                )
            requirements = self._voice_requirements_for_install(root)
            self._run_command(
                "local_voice",
                self._python_package_install_command(
                    python_path,
                    [
                        "-r", str(requirements),
                        "--prefer-binary",
                        "--index-url", "https://mirrors.nju.edu.cn/pypi/web/simple",
                        "--extra-index-url", "https://pypi.org/simple",
                    ],
                ),
                timeout=7200,
                cwd=root,
                phase="installing",
                detail="正在并发补齐语音依赖；缓存和已安装内容会直接复用",
                pausable=True,
            )
        if not self._python_imports(
            python_path,
            *dependency_modules,
            attempts=3,
            timeout=180,
        ):
            failed_modules = [
                module
                for module in dependency_modules
                if not self._python_imports(
                    python_path,
                    module,
                    attempts=2,
                    timeout=120,
                )
            ]
            detail = "、".join(failed_modules) or "批量加载检查"
            raise RuntimeError(f"昔夕本地语音依赖自检未通过：{detail}")

        pretrained = root / "GPT_SoVITS" / "pretrained_models"
        missing_base_models = [
            relative
            for relative in VOICE_HF_MODEL_FILES
            if not (pretrained / Path(relative)).is_file()
        ]
        for index, relative in enumerate(missing_base_models, start=1):
            encoded = quote(relative, safe="/")
            self._download_from_mirrors(
                "local_voice",
                (
                    self._modelscope_url("AI-ModelScope/GPT-SoVITS", "master", relative),
                    f"https://hf-mirror.com/lj1995/GPT-SoVITS/resolve/main/{encoded}",
                    f"https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/{encoded}",
                ),
                pretrained / Path(relative),
                detail=f"正在补齐基础模型 {index}/{len(missing_base_models)}：{Path(relative).name}",
            )

        fast_langdetect_root = pretrained / "fast_langdetect"
        missing_language_models = [
            relative
            for relative in VOICE_FAST_LANGDETECT_FILES
            if not (fast_langdetect_root / relative).is_file()
        ]
        for index, relative in enumerate(missing_language_models, start=1):
            self._download_from_mirrors(
                "local_voice",
                (
                    "https://dl.fbaipublicfiles.com/fasttext/"
                    f"supervised-models/{quote(relative, safe='/')}",
                ),
                fast_langdetect_root / relative,
                detail=(
                    f"正在补齐语言识别模型 {index}/{len(missing_language_models)}："
                    f"{Path(relative).name}"
                ),
            )

        g2pw_root = root / "GPT_SoVITS" / "text" / "G2PWModel"
        missing_g2pw = [
            relative
            for relative in VOICE_G2PW_MODEL_FILES
            if not (g2pw_root / relative).is_file()
        ]
        if missing_g2pw:
            archive = self._download_file(
                "local_voice",
                "https://www.modelscope.cn/models/kamiorinn/g2pw/resolve/master/G2PWModel_1.1.zip",
                self.downloads_root / "g2pw-model-1.1.zip",
                detail=f"正在下载多音字组件包；用于补齐 {len(missing_g2pw)} 个缺失文件",
            )
            extract_root = Path(
                tempfile.mkdtemp(prefix="xixi-g2pw-", dir=str(self.data_root))
            )
            try:
                try:
                    self._extract_zip_safely("local_voice", archive, extract_root)
                except zipfile.BadZipFile:
                    archive.unlink(missing_ok=True)
                    raise RuntimeError("多音字组件下载文件不完整，请重新修复") from None
                source = next(
                    (
                        path
                        for path in extract_root.rglob("*")
                        if path.is_dir() and path.name.casefold() in {"g2pwmodel", "g2pwmodel_1.1"}
                    ),
                    None,
                )
                if source is None:
                    raise RuntimeError("多音字组件压缩包结构无效")
                for relative in missing_g2pw:
                    source_file = source / relative
                    if not source_file.is_file():
                        raise RuntimeError(f"多音字组件缺少文件：{relative}")
                    target = g2pw_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, target)
            finally:
                shutil.rmtree(extract_root, ignore_errors=True)

        missing_after = voice_missing_artifacts(root)
        if missing_after:
            names = "、".join(path.name for path in missing_after.values())
            raise RuntimeError(f"增量修复完成后仍缺少 {len(missing_after)} 项：{names}")
        register_voice_root(root)
        return (
            "昔夕本地语音系统检查完成；完整文件已复用，仅补齐了缺失项"
        )

    def _existing_install_detail(self, key: str) -> str | None:
        if key == "local_voice" and self._local_voice_ready():
            return "昔夕本地语音系统已经就绪，无需重复下载"
        if key == "qq_channel":
            root = self._napcat_root()
            if root is not None:
                register_napcat_root(root)
                return f"已发现可用的 QQ 通道：{root}"
        if key == "local_vision":
            executable = self._ollama_executable()
            models, _ = self._ollama_models(executable)
            if self._OLLAMA_MODEL in models:
                return f"本地视觉模型 {self._OLLAMA_MODEL} 已经就绪"
        if key == "speech_recognition" and (
            self._python_module("faster_whisper")
            and self._python_module("sounddevice")
            and self._whisper_model_ready()
        ):
            return "语音识别组件和模型已经就绪"
        if key == "screen_observation" and (
            self._python_module("mss") and self._python_module("PIL")
        ):
            return "屏幕观察与截图组件已经就绪"
        return None

    def _install_screen_observation(self) -> str:
        if getattr(sys, "frozen", False):
            raise RuntimeError("当前安装文件缺少屏幕观察组件，请重新安装最新版")
        self._run_command(
            "screen_observation",
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "mss>=9.0.0",
                "Pillow>=10,<13",
            ],
            timeout=1200,
            phase="downloading",
            detail="正在下载并安装屏幕观察组件",
            pausable=True,
        )
        if not self._python_module("mss") or not self._python_module("PIL"):
            raise RuntimeError("屏幕观察组件安装完成后仍无法导入")
        return "屏幕观察与截图组件已补齐"

    def install(self, key: str) -> dict[str, Any]:
        key = str(key or "").strip()
        if key not in self._INSTALLABLE:
            raise ValueError("该环境功能不支持自动安装")
        existing_detail = self._existing_install_detail(key)
        if existing_detail:
            completed = {
                "key": key,
                "state": "completed",
                "phase": "completed",
                "detail": existing_detail,
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "progress": 100,
                "speed_bps": 0,
                "can_pause": False,
                "can_resume": False,
                "can_cancel": False,
                "started_at": _now(),
                "finished_at": _now(),
            }
            with self._lock:
                self._jobs[key] = completed
                self._controls.pop(key, None)
            return dict(completed)
        with self._lock:
            current = self._jobs.get(key, {})
            if current.get("state") in {"installing", "paused", "cancelling"}:
                return dict(current)
            active_jobs = [
                job for job in self._jobs.values()
                if job.get("state") in {"installing", "paused", "cancelling"}
            ]
            if len(active_jobs) >= self._MAX_CONCURRENT_INSTALLS:
                raise ValueError(
                    f"已有 {len(active_jobs)} 项安装任务正在运行，请稍候自动继续"
                )
            job = {
                "key": key,
                "state": "installing",
                "phase": "preparing",
                "detail": "正在准备安装，请保持应用运行",
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "progress": None,
                "speed_bps": 0,
                "can_pause": False,
                "can_resume": False,
                "can_cancel": True,
                "started_at": _now(),
            }
            self._jobs[key] = job
            self._controls[key] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }

        installers: dict[str, Callable[[], str]] = {
            "local_voice": self._install_local_voice,
            "qq_channel": self._download_napcat,
            "local_vision": self._install_local_vision,
            "speech_recognition": self._install_speech_recognition,
            "screen_observation": self._install_screen_observation,
        }

        def run() -> None:
            try:
                detail = self._existing_install_detail(key) or installers[key]()
                state = "completed"
            except EnvironmentInstallCancelled:
                with self._lock:
                    control = self._controls.get(key) or {}
                    part_path = control.get("part_path")
                if part_path:
                    Path(part_path).unlink(missing_ok=True)
                state = "cancelled"
                detail = "下载或安装已取消"
            except Exception as exc:
                logger.exception("environment installation failed: %s", key)
                state = "failed"
                detail = f"安装失败：{str(exc)[:700]}"
            with self._lock:
                current_job = dict(self._jobs.get(key) or job)
                self._jobs[key] = {
                    **current_job,
                    "state": state,
                    "phase": "completed" if state == "completed" else state,
                    "detail": detail,
                    "downloaded_bytes": 0,
                    "total_bytes": 0,
                    "progress": 100 if state == "completed" else None,
                    "speed_bps": 0,
                    "can_pause": False,
                    "can_resume": False,
                    "can_cancel": False,
                    "finished_at": _now(),
                }
                self._controls.pop(key, None)
            self.journal.append(
                "diagnostic",
                f"环境组件安装{ {'completed': '完成', 'cancelled': '取消'}.get(state, '失败') }：{key}",
                status=state,
                detail=detail,
            )

        threading.Thread(target=run, name=f"xixi-environment-{key}", daemon=True).start()
        return dict(job)


class GameControl:
    """Read-only primary-screen sharing and capture."""

    _MIN_CAPTURE_WIDTH = 320
    _MIN_CAPTURE_HEIGHT = 180
    _MANUAL_CAPTURE_LIMIT = 10

    def __init__(self, data_dir: Path, journal: ActivityJournal) -> None:
        self.settings_file = data_dir / "game_settings.json"
        self.capture_dir = data_dir / "game_captures"
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self._prune_capture_files()
        self.journal = journal
        self._lock = threading.RLock()
        self._active = False
        self._observation_interval_s = 6.0
        self._change_threshold = 0.015
        self._max_idle_cycles = 2
        self._companion_interval_s = 12.0
        self._companion_enabled = True
        self._auto_voice_call = True
        self._load()

    def _prune_capture_files(self) -> None:
        for pattern in ("annotated-live-*.jpg", "*.tmp"):
            for path in self.capture_dir.glob(pattern):
                try:
                    path.unlink()
                except OSError:
                    logger.debug("could not remove stale game capture: %s", path, exc_info=True)

        manual_captures = sorted(
            self.capture_dir.glob("capture-*.png"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for path in manual_captures[self._MANUAL_CAPTURE_LIMIT:]:
            try:
                path.unlink()
            except OSError:
                logger.debug("could not prune old game capture: %s", path, exc_info=True)

    def _load(self) -> None:
        if not self.settings_file.is_file():
            self._save()
            return
        try:
            payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
            # Window selection was removed. Keep accepting old files, but do
            # not carry a stale HWND into the screen-sharing runtime.
            self._observation_interval_s = max(
                4.0,
                min(30.0, float(payload.get("observation_interval_s", self._observation_interval_s))),
            )
            self._change_threshold = max(
                0.005,
                min(0.25, float(payload.get("change_threshold", self._change_threshold))),
            )
            self._max_idle_cycles = max(
                1,
                min(20, int(payload.get("max_idle_cycles", self._max_idle_cycles))),
            )
            self._companion_interval_s = max(
                6.0,
                min(30.0, float(payload.get("companion_interval_s", self._companion_interval_s))),
            )
            self._companion_enabled = bool(payload.get("companion_enabled", self._companion_enabled))
            self._auto_voice_call = bool(payload.get("auto_voice_call", self._auto_voice_call))
        except Exception:
            logger.warning("could not load game observation settings", exc_info=True)
        self._save()

    def _save(self) -> None:
        payload = {
            "mode": "observe",
            "observation_interval_s": self._observation_interval_s,
            "change_threshold": self._change_threshold,
            "max_idle_cycles": self._max_idle_cycles,
            "companion_interval_s": self._companion_interval_s,
            "companion_enabled": self._companion_enabled,
            "auto_voice_call": self._auto_voice_call,
        }
        temp = self.settings_file.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.settings_file)

    def _screen_region(self) -> dict[str, int]:
        try:
            import mss
        except ImportError as exc:
            raise RuntimeError("当前环境未安装 mss，无法共享屏幕") from exc
        with mss.MSS() as capture:
            monitors = capture.monitors
            if len(monitors) < 2:
                raise RuntimeError("没有检测到可共享的显示器")
            monitor = monitors[1]
        width = int(monitor["width"])
        height = int(monitor["height"])
        if width < self._MIN_CAPTURE_WIDTH or height < self._MIN_CAPTURE_HEIGHT:
            raise ValueError(f"主显示器画面太小（{width}×{height}），无法共享屏幕")
        return {
            "left": int(monitor["left"]),
            "top": int(monitor["top"]),
            "width": width,
            "height": height,
        }

    def windows(self) -> dict[str, Any]:
        """Compatibility response for older local clients."""
        region = self._screen_region()
        return {
            "items": [{
                "hwnd": 0,
                "title": "整个屏幕（自动）",
                "width": region["width"],
                "height": region["height"],
                "usable": True,
                "reason": "",
                "source": "screen",
            }]
        }

    def status(self) -> dict[str, Any]:
        try:
            region = self._screen_region()
            width, height = region["width"], region["height"]
            screen_ready, screen_warning = True, ""
        except Exception as exc:
            width = height = 0
            screen_ready, screen_warning = False, str(exc)
        return {
            "active": self._active,
            "mode": "observe",
            "hwnd": 0,
            "window_title": "整个屏幕（自动）",
            "window_ready": screen_ready,
            "window_width": width,
            "window_height": height,
            "window_warning": screen_warning,
            "capture_source": "screen",
            "screen_name": "主显示器",
            "observation_interval_s": self._observation_interval_s,
            "change_threshold": self._change_threshold,
            "max_idle_cycles": self._max_idle_cycles,
            "companion_interval_s": self._companion_interval_s,
            "companion_enabled": self._companion_enabled,
            "auto_voice_call": self._auto_voice_call,
            "input": {
                "enabled": False,
                "reason": "昔夕现在只观察游戏，不会操作键盘或鼠标",
            },
        }

    def configure(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._active:
                raise ValueError("请先结束当前游戏观察会话再修改设置")
            # Legacy HWND values are intentionally ignored.
            if "observation_interval_s" in payload:
                self._observation_interval_s = max(
                    4.0,
                    min(30.0, float(payload["observation_interval_s"])),
                )
            if "change_threshold" in payload:
                self._change_threshold = max(
                    0.005,
                    min(0.25, float(payload["change_threshold"])),
                )
            if "max_idle_cycles" in payload:
                self._max_idle_cycles = max(1, min(20, int(payload["max_idle_cycles"])))
            if "companion_interval_s" in payload:
                self._companion_interval_s = max(
                    6.0,
                    min(30.0, float(payload["companion_interval_s"])),
                )
            if "companion_enabled" in payload:
                self._companion_enabled = bool(payload["companion_enabled"])
            if "auto_voice_call" in payload:
                self._auto_voice_call = bool(payload["auto_voice_call"])
            self._save()
        return self.status()

    def start(self) -> dict[str, Any]:
        self._screen_region()
        with self._lock:
            was_active = self._active
            self._active = True
        if not was_active:
            self.journal.append(
                "game",
                "游戏观察会话已开始",
                detail="主显示器",
                metadata={"mode": "observe"},
            )
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            was_active = self._active
            self._active = False
        if was_active:
            self.journal.append(
                "game",
                "游戏观察会话已停止",
                status="stopped",
                detail=self.status()["window_title"],
            )
        return self.status()

    def window_region(self, hwnd: int | None = None) -> dict[str, int]:
        del hwnd
        return self._screen_region()

    def capture(self) -> dict[str, Any]:
        try:
            import mss
        except ImportError as exc:
            raise RuntimeError("当前环境未安装 mss，无法截取游戏画面") from exc
        region = self._screen_region()
        target = self.capture_dir / f"capture-{int(time.time())}.png"
        with mss.MSS() as capture:
            shot = capture.grab(region)
            from mss import tools as mss_tools
            mss_tools.to_png(shot.rgb, shot.size, output=str(target))
        self._prune_capture_files()
        self.journal.append("game", "已截取游戏画面", detail=target.name)
        return {
            "path": str(target),
            "url": f"/api/game/capture/{target.name}",
            "width": region["width"],
            "height": region["height"],
        }

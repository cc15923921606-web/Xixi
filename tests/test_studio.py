from __future__ import annotations

import asyncio
import base64
import ctypes
import hashlib
import http.server
import io
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx

from app.asr_bus import (
    build_asr_hotwords,
    build_asr_prompt,
    create_whisper_model,
    correct_asr_with_context,
    normalize_asr_transcript,
    prewarm_whisper_model,
    transcribe_synthesized_speech,
    transcribe_speech,
)
from app.agent_workspace import AgentWorkspace
from app.config import Config
from app.memory_store import MemoryStore
from app.studio import (
    StudioRuntime,
    StudioServer,
    _chinese_voice_match,
    _decode_data_url,
    _start_runtime_services,
)
from app.studio_capabilities import (
    ActivityJournal,
    BackupManager,
    DependencyManager,
    DiagnosticCenter,
    EnvironmentDownloadTooSlow,
    EnvironmentManager,
    GameControl,
)
from app.voice_runtime import VOICE_NLTK_DATA_FILES, voice_required_artifacts, voice_nltk_data_root


@contextmanager
def local_download_server(
    payload: bytes,
    *,
    chunk_size: int = 64 * 1024,
    chunk_delay: float = 0.0,
    truncate_first_request_at: int = 0,
    initial_body_delay: float = 0.0,
):
    class DownloadHandler(http.server.BaseHTTPRequestHandler):
        request_count = 0

        def log_message(self, format: str, *args: object) -> None:
            return None

        def do_GET(self) -> None:
            type(self).request_count += 1
            range_header = self.headers.get("Range") or ""
            start = 0
            if range_header.startswith("bytes="):
                start_text = range_header.removeprefix("bytes=").split("-", 1)[0]
                start = int(start_text or 0)
            if start >= len(payload):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(payload)}")
                self.end_headers()
                return
            self.send_response(206 if start else 200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(payload) - start))
            if start:
                self.send_header("Content-Range", f"bytes {start}-{len(payload) - 1}/{len(payload)}")
            self.end_headers()
            if initial_body_delay:
                time.sleep(initial_body_delay)
            stop = len(payload)
            if type(self).request_count == 1 and truncate_first_request_at > start:
                stop = min(stop, truncate_first_request_at)
            try:
                for offset in range(start, stop, chunk_size):
                    self.wfile.write(payload[offset:min(offset + chunk_size, stop)])
                    self.wfile.flush()
                    if chunk_delay:
                        time.sleep(chunk_delay)
            except (BrokenPipeError, ConnectionResetError):
                return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), DownloadHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/download", DownloadHandler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


class FakeBrain:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.openai_api_key = "test-key"
        self.openai_base_url = "https://example.com/v1"
        self.openai_client = object()
        self.environment = MagicMock()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.reload_count = 0
        self.interest_profile = {}
        self.sessions: dict[str, list[dict[str, str]]] = {}
        self.workspace = AgentWorkspace(cfg.memory_db)

    def think(self, text: str, **kwargs: object) -> str:
        self.calls.append((text, kwargs))
        return "这张图挺有意思的，一眼就能看出是在故意搞怪。"

    def translate_reply(self, text: str, target_language: str) -> str:
        translations = {
            "zh": "这张图挺有意思的。",
            "ja": "この画像、なかなか面白いね。",
            "en": "This image is pretty interesting.",
        }
        return translations[target_language]

    def reload_persona(self) -> None:
        self.reload_count += 1

    def _load_interest_profile(self) -> dict[str, object]:
        return self.interest_profile

    def _save_sessions(self) -> None:
        return None


class StudioTests(unittest.TestCase):
    def test_runtime_startup_skips_missing_optional_voice_models(self) -> None:
        runtime = MagicMock()
        runtime.environment._local_voice_ready.return_value = False
        runtime.environment._whisper_model_ready.return_value = False
        cfg = MagicMock(voice_enabled=True, qq_enabled=False)

        with patch("app.studio.prewarm_voice_language") as prewarm:
            _start_runtime_services(runtime, cfg)

        prewarm.assert_not_called()
        runtime.start_asr_prewarm.assert_not_called()
        runtime.stop_qq.assert_called_once_with(logout_account=True)

    def test_runtime_startup_keeps_background_services_alive_after_qq_failure(self) -> None:
        runtime = MagicMock()
        runtime.environment._local_voice_ready.return_value = False
        runtime.environment._whisper_model_ready.return_value = False
        runtime.stop_qq.side_effect = RuntimeError("QQ cleanup failed")
        cfg = MagicMock(voice_enabled=False, qq_enabled=False)

        _start_runtime_services(runtime, cfg)

        runtime.start_background_services.assert_called_once_with()

    def test_verified_component_is_not_hidden_by_a_stale_install_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["qq_channel"] = {
                "key": "qq_channel",
                "state": "installing",
                "detail": "stale download",
            }

            item = manager._base_item("qq_channel", "ok", "已经检测到 QQ 通道")

            self.assertEqual(item["state"], "ok")
            self.assertEqual(item["detail"], "已经检测到 QQ 通道")

    def test_existing_component_completes_install_without_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            with (
                patch.object(manager, "_existing_install_detail", return_value="已经存在"),
                patch.object(manager, "_download_napcat") as download,
            ):
                job = manager.install("qq_channel")

            self.assertEqual(job["state"], "completed")
            download.assert_not_called()

    def test_download_mirror_switch_preserves_the_same_resume_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            target = Path(tmp) / "component.zip"
            manager._jobs["qq_channel"] = {"key": "qq_channel", "state": "installing"}
            manager._controls["qq_channel"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            with patch.object(
                manager,
                "_download_file",
                side_effect=[EnvironmentDownloadTooSlow("slow"), target],
            ) as download:
                result = manager._download_from_mirrors(
                    "qq_channel",
                    ("https://slow.test/file", "https://fast.test/file"),
                    target,
                    detail="正在下载",
                )

            self.assertEqual(result, target)
            self.assertEqual(download.call_count, 2)
            self.assertEqual(download.call_args_list[0].args[2], target)
            self.assertEqual(download.call_args_list[1].args[2], target)
            self.assertEqual(download.call_args_list[0].kwargs["max_retries"], 0)
            self.assertEqual(download.call_args_list[0].kwargs["minimum_speed_bps"], 64 * 1024)

    def test_environment_download_abandons_a_connected_source_that_never_sends_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["qq_channel"] = {"key": "qq_channel", "state": "installing"}
            manager._controls["qq_channel"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = Path(tmp) / "stalled.bin"

            with local_download_server(b"eventual-data", initial_body_delay=2.0) as (download_url, _):
                with self.assertRaises(EnvironmentDownloadTooSlow):
                    manager._download_file(
                        "qq_channel",
                        download_url,
                        target,
                        detail="正在测试停滞下载源",
                        max_retries=0,
                        minimum_speed_bps=1,
                        slow_grace_seconds=0.2,
                        slow_probe_bytes=1,
                        expected_size=len(b"eventual-data"),
                    )

            self.assertFalse(target.exists())

    def test_local_vision_falls_back_to_winget_when_direct_download_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["local_vision"] = {"key": "local_vision", "state": "installing"}
            manager._controls["local_vision"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            ollama = Path("ollama.exe")
            with (
                patch.object(manager, "_ollama_executable", side_effect=[None, ollama]),
                patch.object(
                    manager,
                    "_download_ollama_installer",
                    side_effect=RuntimeError("network unavailable"),
                ),
                patch.object(manager, "_run_command", return_value="") as run,
                patch.object(manager, "_ollama_models", return_value=({manager._OLLAMA_MODEL}, "")),
                patch("app.studio_capabilities.shutil.which", return_value="winget.exe"),
            ):
                result = manager._install_local_vision()

            self.assertEqual(result, "本地视觉模型安装完成")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[1][:4], [
                "winget.exe", "install", "--id", "Ollama.Ollama",
            ])
            self.assertEqual(run.call_args_list[1].args[1], [
                str(ollama), "pull", manager._OLLAMA_MODEL,
            ])

    def test_ollama_installer_prefers_verified_modelscope_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["local_vision"] = {"key": "local_vision", "state": "installing"}
            manager._controls["local_vision"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = manager.downloads_root / "OllamaSetup.exe"

            with patch.object(
                manager,
                "_download_verified_from_mirrors",
                return_value=target,
            ) as download:
                result = manager._download_ollama_installer()

            self.assertEqual(result, target)
            urls = download.call_args.args[1]
            self.assertIn("modelscope.cn/models/Lixiang/ollama-release", urls[0])
            self.assertIn("/v0.33.0/OllamaSetup.exe", urls[0])
            self.assertEqual(download.call_args.kwargs["expected_size"], 1_565_889_272)
            self.assertEqual(
                download.call_args.kwargs["expected_sha256"],
                "913230e6c251e60577dd4ef236b5a916202cb1b87481ed817e375fee4841372b",
            )
            metadata = json.loads(
                target.with_name("OllamaSetup.exe.release.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["revision"], "v0.33.0")

    def test_ollama_installer_discards_partial_file_from_another_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["local_vision"] = {"key": "local_vision", "state": "installing"}
            manager._controls["local_vision"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = manager.downloads_root / "OllamaSetup.exe"
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name("OllamaSetup.exe.part")
            part.write_bytes(b"old-release")
            target.with_name("OllamaSetup.exe.release.json").write_text(
                json.dumps({"revision": "old"}),
                encoding="utf-8",
            )

            def verify_clean_start(*args: object, **kwargs: object) -> Path:
                self.assertFalse(part.exists())
                return target

            with patch.object(
                manager,
                "_download_verified_from_mirrors",
                side_effect=verify_clean_start,
            ):
                manager._download_ollama_installer()

    def test_dependency_repair_uses_current_python_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = MagicMock()
            manager = DependencyManager(Path(tmp), journal)
            completed = MagicMock(returncode=0, stdout="installed", stderr="")
            packages = {"sample": ("xixi_missing_sample", "xixi-sample>=1.0")}

            with (
                patch.object(DependencyManager, "_PYTHON_PACKAGES", packages),
                patch("app.studio_capabilities.importlib.util.find_spec", return_value=None),
                patch("app.studio_capabilities.subprocess.run", return_value=completed) as run,
            ):
                started = manager.repair("sample")
                self.assertEqual(started["state"], "installing")
                for _ in range(100):
                    if manager._jobs.get("sample", {}).get("state") != "installing" and journal.append.called:
                        break
                    time.sleep(0.01)

            command = run.call_args.args[0]
            self.assertEqual(command, [sys.executable, "-m", "pip", "install", "xixi-sample>=1.0"])
            self.assertEqual(manager._jobs["sample"]["state"], "completed")
            journal.append.assert_called_once()

    def test_environment_status_groups_user_facing_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "xixi"
            root.mkdir()
            voice_root = root.parent / "work" / "GPT-SoVITS"
            for path in (
                *voice_required_artifacts(voice_root).values(),
                root / "whisper-small-full" / "model.bin",
                root.parent / "napcat" / "launcher-user.bat",
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            manager = EnvironmentManager(
                root,
                MagicMock(),
                lambda: {
                    "model": {"online": True, "enabled": True, "name": "test-model", "provider": "test"},
                    "voice": {"online": True},
                    "qq": {"online": False},
                    "vision": {"online": True},
                },
            )

            with (
                patch.object(EnvironmentManager, "_python_module", return_value=True),
                patch.object(manager, "_napcat_root", return_value=root.parent / "napcat"),
                patch.object(manager, "_ollama_executable", return_value=Path("ollama.exe")),
                patch.object(manager, "_ollama_models", return_value=({"qwen2.5vl:3b"}, "")),
                patch.object(manager, "_whisper_model_ready", return_value=True),
            ):
                payload = manager.status()

            self.assertEqual(
                [item["key"] for item in payload["items"]],
                [
                    "chat_model",
                    "local_voice",
                    "qq_channel",
                    "local_vision",
                    "speech_recognition",
                    "screen_observation",
                ],
            )
            states = {item["key"]: item["state"] for item in payload["items"]}
            self.assertEqual(states["local_voice"], "ok")
            self.assertEqual(states["qq_channel"], "ok")
            self.assertEqual(states["local_vision"], "ok")
            self.assertEqual(states["speech_recognition"], "ok")
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["ready_count"], 6)
            self.assertEqual(payload["download_source"], "魔搭优先 · 多源断点续传")
            self.assertEqual(payload["download_transport"], "后台命令行")

    def test_local_voice_does_not_depend_on_speech_recognition_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(
                Path(tmp),
                MagicMock(),
                lambda: {"voice": {"online": True}},
            )
            with (
                patch.object(manager, "_local_voice_ready", return_value=True),
                patch.object(manager, "_whisper_model_ready", return_value=False),
                patch.object(manager, "_python_module", return_value=True),
                patch.object(manager, "_napcat_root", return_value=None),
                patch.object(manager, "_ollama_executable", return_value=None),
                patch.object(manager, "_ollama_models", return_value=(set(), "")),
            ):
                payload = manager.status()
                existing = manager._existing_install_detail("local_voice")

            item = next(entry for entry in payload["items"] if entry["key"] == "local_voice")
            self.assertEqual(item["state"], "ok")
            self.assertFalse(item["repairable"])
            self.assertNotIn("verification_ready", item)
            self.assertEqual(existing, "昔夕本地语音系统已经就绪，无需重复下载")

    def test_qq_install_restores_packaged_component_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "app"
            components = Path(tmp) / "user-components"
            packaged = root / "runtime" / "components" / "NapCat"
            packaged.mkdir(parents=True)
            (packaged / "launcher-user.bat").write_text("@echo off", encoding="utf-8")
            (packaged / "napcat.mjs").write_text("packaged", encoding="utf-8")
            (packaged / "NapCatWinBootHook.dll").write_bytes(b"hook")
            (packaged / "NapCatWinBootMain.exe").write_bytes(b"boot")
            manager = EnvironmentManager(
                root,
                MagicMock(),
                components_root=components,
            )
            manager._jobs["qq_channel"] = {"key": "qq_channel", "state": "installing"}
            manager._controls["qq_channel"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }

            with (
                patch.object(manager, "_napcat_root", return_value=None),
                patch("app.studio_capabilities.urllib.request.urlopen") as download,
                patch("app.studio_capabilities.register_napcat_root") as register,
            ):
                result = manager._download_napcat()

            restored = components / "NapCat"
            self.assertEqual((restored / "napcat.mjs").read_text(encoding="utf-8"), "packaged")
            self.assertIn("无需联网下载", result)
            register.assert_called_once_with(restored)
            download.assert_not_called()

    def test_environment_reuses_registered_voice_system_with_original_weight_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "public-app"
            components = Path(tmp) / "public-data" / "components"
            voice_root = Path(tmp) / "existing-voice" / "GPT-SoVITS"
            root.mkdir()
            non_voice_models = [
                path
                for name, path in voice_required_artifacts(voice_root).items()
                if not name.startswith("voice_model:")
            ]
            for path in (
                *non_voice_models,
                voice_root / "GPT_weights_v2Pro" / "xixi_voice_v2Pro-e10.ckpt",
                voice_root / "SoVITS_weights_v2Pro" / "xixi_voice_v2Pro_e4_s1572.pth",
                voice_root / "SoVITS_weights_v2Pro" / "xixi_voice_v2Pro_e2e4_blend30.pth",
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            manager = EnvironmentManager(
                root,
                MagicMock(),
                components_root=components,
            )

            with (
                patch.dict(
                    "os.environ",
                    {"GPT_SOVITS_ROOT": str(components / "GPT-SoVITS")},
                ),
                patch("app.voice_runtime.registered_voice_root", return_value=voice_root),
            ):
                self.assertEqual(manager._voice_root(), voice_root)
                self.assertTrue(manager._local_voice_ready())

    def test_public_environment_does_not_report_personal_voice_engine_as_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "public-app"
            components = Path(tmp) / "public-data" / "components"
            personal_voice = Path(tmp) / "personal" / "GPT-SoVITS"
            root.mkdir()
            personal_voice.mkdir(parents=True)
            manager = EnvironmentManager(
                root,
                MagicMock(),
                components_root=components,
            )

            with (
                patch("app.studio_capabilities.sys.frozen", True, create=True),
                patch("app.voice_runtime.registered_voice_root", return_value=personal_voice),
                patch(
                    "app.voice_runtime.voice_root_ready",
                    side_effect=lambda candidate: Path(candidate) == personal_voice,
                ),
            ):
                self.assertEqual(manager._voice_root(), components / "GPT-SoVITS")
                self.assertFalse(manager._local_voice_ready())

    def test_cloud_vision_keeps_environment_ready_without_optional_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "xixi"
            root.mkdir()
            manager = EnvironmentManager(
                root,
                MagicMock(),
                lambda: {
                    "model": {"online": True, "enabled": True},
                    "voice": {"online": True},
                    "qq": {"online": False},
                    "vision": {"online": True},
                },
            )
            with (
                patch.object(EnvironmentManager, "_python_module", return_value=True),
                patch.object(manager, "_local_voice_ready", return_value=True),
                patch.object(manager, "_napcat_root", return_value=Path("napcat")),
                patch.object(manager, "_whisper_model_ready", return_value=True),
                patch.object(manager, "_ollama_executable", return_value=Path("ollama.exe")),
                patch.object(manager, "_ollama_models", return_value=(set(), "模型尚未安装")),
            ):
                payload = manager.status()

            local_vision = next(item for item in payload["items"] if item["key"] == "local_vision")
            self.assertEqual(local_vision["state"], "optional")
            self.assertTrue(local_vision["repairable"])
            self.assertIn("云端图片理解已就绪", local_vision["detail"])
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["ready_count"], 6)

    def test_optional_environment_capabilities_do_not_report_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "xixi"
            root.mkdir()
            manager = EnvironmentManager(
                root,
                MagicMock(),
                lambda: {
                    "model": {"online": False, "enabled": False},
                    "voice": {"online": False},
                    "qq": {"online": False},
                    "vision": {"online": False},
                },
            )
            with (
                patch.object(EnvironmentManager, "_python_module", return_value=False),
                patch.object(manager, "_local_voice_ready", return_value=False),
                patch.object(manager, "_napcat_root", return_value=None),
                patch.object(manager, "_whisper_model_ready", return_value=False),
                patch.object(manager, "_ollama_executable", return_value=None),
                patch.object(manager, "_ollama_models", return_value=(set(), "")),
            ):
                payload = manager.status()

            states = {item["key"]: item["state"] for item in payload["items"]}
            labels = {item["key"]: item["status_label"] for item in payload["items"]}
            for key in (
                "chat_model",
                "local_voice",
                "qq_channel",
                "local_vision",
                "speech_recognition",
                "screen_observation",
            ):
                self.assertEqual(states[key], "optional")
                expected_label = {
                    "chat_model": "待配置",
                }.get(key, "可稍后配置")
                self.assertEqual(labels[key], expected_label)
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["ready_count"], 6)

    def test_partially_configured_chat_model_is_not_reported_as_install_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(
                Path(tmp),
                MagicMock(),
                lambda: {
                    "model": {"online": False, "enabled": True, "name": "", "provider": "gateway.test"},
                    "voice": {"online": False},
                    "qq": {"online": False},
                    "vision": {"online": False},
                },
            )
            with (
                patch.object(EnvironmentManager, "_python_module", return_value=False),
                patch.object(manager, "_local_voice_ready", return_value=False),
                patch.object(manager, "_napcat_root", return_value=None),
                patch.object(manager, "_whisper_model_ready", return_value=False),
                patch.object(manager, "_ollama_executable", return_value=None),
                patch.object(manager, "_ollama_models", return_value=(set(), "")),
            ):
                chat = next(item for item in manager.status()["items"] if item["key"] == "chat_model")

            self.assertEqual(chat["state"], "optional")
            self.assertEqual(chat["status_label"], "待配置")
            self.assertNotIn("安装失败", chat["detail"])

    def test_environment_install_jobs_run_three_at_a_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = MagicMock()
            manager = EnvironmentManager(Path(tmp), journal)
            started = threading.Event()
            release = threading.Event()
            counter_lock = threading.Lock()
            started_count = 0

            def blocked_install() -> str:
                nonlocal started_count
                with counter_lock:
                    started_count += 1
                    if started_count == 3:
                        started.set()
                release.wait(timeout=2)
                return "安装完成"

            with (
                patch.object(manager, "_existing_install_detail", return_value=None),
                patch.object(manager, "_install_local_vision", side_effect=blocked_install),
                patch.object(manager, "_install_speech_recognition", side_effect=blocked_install),
                patch.object(manager, "_download_napcat", side_effect=blocked_install),
                patch.object(manager, "_install_local_voice", side_effect=blocked_install),
            ):
                jobs = [
                    manager.install("local_vision"),
                    manager.install("speech_recognition"),
                    manager.install("qq_channel"),
                ]
                self.assertTrue(all(job["state"] == "installing" for job in jobs))
                self.assertTrue(started.wait(timeout=1))
                with self.assertRaisesRegex(ValueError, "已有 3 项安装任务"):
                    manager.install("local_voice")
                release.set()
                for _ in range(100):
                    if all(
                        manager._jobs[key]["state"] != "installing"
                        for key in ("local_vision", "speech_recognition", "qq_channel")
                    ):
                        break
                    time.sleep(0.01)

            self.assertTrue(all(
                manager._jobs[key]["state"] == "completed"
                for key in ("local_vision", "speech_recognition", "qq_channel")
            ))
            self.assertEqual(journal.append.call_count, 3)

    def test_voice_dependency_install_prefers_packaged_uv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uv = root / "runtime" / "install_tools" / "uv.exe"
            uv.parent.mkdir(parents=True)
            uv.touch()
            manager = EnvironmentManager(root, MagicMock())

            command = manager._python_package_install_command(
                Path("voice-python.exe"),
                ["sample-package", "--prefer-binary"],
            )

            self.assertEqual(Path(command[0]), uv)
            self.assertIn("--python", command)
            self.assertIn("voice-python.exe", command)
            self.assertIn("--cache-dir", command)
            self.assertNotIn("--prefer-binary", command)

    def test_public_release_bundles_the_high_speed_installer(self) -> None:
        root = Path(__file__).parents[1]
        build_script = (root / "packaging" / "build_public_release.ps1").read_text(encoding="utf-8")
        spec = (root / "packaging" / "xixi_public.spec").read_text(encoding="utf-8")

        self.assertIn('Get-Command uv', build_script)
        self.assertIn('install_tools\\uv.exe', build_script)
        self.assertIn('runtime\\install_tools\\uv.exe', build_script)
        self.assertIn('(str(staging / "install_tools"), "runtime/install_tools")', spec)
        self.assertIn('"dxcam", "comtypes", "mss"', spec)

    def test_game_companion_frontend_has_cross_device_microphone_fallback(self) -> None:
        studio_root = Path(__file__).parents[1] / "studio"
        source = (studio_root / "app.js").read_text(encoding="utf-8")
        page = (studio_root / "index.html").read_text(encoding="utf-8")

        self.assertIn("async function requestMicrophoneStream({ allowPermissionRetry = true } = {})", source)
        self.assertIn('getUserMedia({ audio: true })', source)
        self.assertGreaterEqual(source.count("requestMicrophoneStream("), 5)
        self.assertIn("set_microphone_permission", source)
        self.assertIn("open_microphone_privacy_settings", source)
        self.assertIn('id="microphone-permission-dialog"', page)
        self.assertIn('id="microphone-permission-toggle"', page)
        self.assertIn("事件感知运行中", source)

    def test_qq_control_frontend_deduplicates_completed_notifications(self) -> None:
        source = (Path(__file__).parents[1] / "studio" / "app.js").read_text(encoding="utf-8")

        self.assertIn("candidate.dataset.toastKey === key", source)
        self.assertIn("if (!settled) void monitorQqControl(action, generation);", source)

    def test_public_release_bundles_offline_english_voice_data(self) -> None:
        root = Path(__file__).parents[1]
        build_script = (root / "packaging" / "build_public_release.ps1").read_text(encoding="utf-8")
        spec = (root / "packaging" / "xixi_public.spec").read_text(encoding="utf-8")

        self.assertIn('voice_nltk_data', build_script)
        self.assertIn('(str(staging / "voice_nltk_data"), "runtime/voice/package/nltk_data")', spec)
        for relative in VOICE_NLTK_DATA_FILES:
            self.assertTrue((root / "packaging" / "voice_nltk_data" / relative).is_file())

    def test_verified_environment_download_rejects_bad_file_and_uses_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = EnvironmentManager(root, MagicMock())
            manager._jobs["speech_recognition"] = {
                "key": "speech_recognition",
                "state": "installing",
            }
            manager._controls["speech_recognition"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = root / "model.bin"
            expected = b"verified-model"
            attempts: list[str] = []

            def fake_download(key: str, url: str, path: Path, **kwargs: object) -> Path:
                attempts.append(url)
                path.write_bytes(b"invalid-model" if len(attempts) == 1 else expected)
                return path

            with patch.object(manager, "_download_file", side_effect=fake_download):
                result = manager._download_verified_from_mirrors(
                    "speech_recognition",
                    ("https://mirror.test/model.bin", "https://official.test/model.bin"),
                    target,
                    detail="正在下载模型",
                    expected_size=len(expected),
                    expected_sha256=hashlib.sha256(expected).hexdigest(),
                )

            self.assertEqual(result.read_bytes(), expected)
            self.assertEqual(len(attempts), 2)

    def test_frozen_speech_install_uses_resumable_mirrors_without_python_downloader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_root = root / "models"
            manager = EnvironmentManager(root, MagicMock(), models_root=models_root)
            manager._jobs["speech_recognition"] = {
                "key": "speech_recognition",
                "state": "installing",
            }
            manager._controls["speech_recognition"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            downloads: list[tuple[tuple[str, ...], Path]] = []

            def fake_download(
                key: str,
                urls: tuple[str, ...],
                target: Path,
                **kwargs: object,
            ) -> Path:
                downloads.append((urls, target))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
                return target

            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(manager, "_python_module", return_value=True),
                patch.object(manager, "_whisper_model_ready", side_effect=[False, True]),
                patch.object(manager, "_download_verified_from_mirrors", side_effect=fake_download),
                patch.object(manager, "_managed_python") as managed_python,
                patch.object(manager, "_run_command") as run_command,
            ):
                result = manager._install_speech_recognition()

            self.assertIn("安装完成", result)
            self.assertEqual(
                {target.name for _, target in downloads},
                set(EnvironmentManager._WHISPER_MODEL_FILES),
            )
            self.assertTrue(all("modelscope.cn" in urls[0] for urls, _ in downloads))
            self.assertTrue(all(urls[1].startswith("https://hf-mirror.com/") for urls, _ in downloads))
            self.assertTrue(all(urls[2].startswith("https://huggingface.co/") for urls, _ in downloads))
            self.assertTrue(all(EnvironmentManager._WHISPER_MODEL_REVISION in urls[1] for urls, _ in downloads))
            managed_python.assert_not_called()
            run_command.assert_not_called()

    def test_environment_download_can_pause_resume_and_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = EnvironmentManager(root, MagicMock())
            payload = b"xixi-download" * 500_000
            target = root / "data" / "environment_downloads" / "test.bin"

            def install_download() -> str:
                manager._download_file(
                    "qq_channel",
                    download_url,
                    target,
                    detail="正在下载测试组件",
                    expected_size=len(payload),
                )
                return "测试组件安装完成"

            with local_download_server(payload, chunk_delay=0.006) as (download_url, _):
                with (
                    patch.object(manager, "_existing_install_detail", return_value=None),
                    patch.object(manager, "_download_napcat", side_effect=install_download),
                ):
                    manager.install("qq_channel")
                    for _ in range(400):
                        job = manager._job("qq_channel")
                        if job.get("can_pause") and target.with_name("test.bin.part").is_file():
                            break
                        time.sleep(0.01)
                    paused = manager.control("qq_channel", "pause")
                    self.assertEqual(paused["state"], "paused")
                    time.sleep(0.08)
                    paused_size = target.with_name("test.bin.part").stat().st_size
                    time.sleep(0.08)
                    self.assertEqual(target.with_name("test.bin.part").stat().st_size, paused_size)
                    resumed = manager.control("qq_channel", "resume")
                    self.assertEqual(resumed["state"], "installing")
                    for _ in range(800):
                        if manager._job("qq_channel").get("state") == "completed":
                            break
                        time.sleep(0.01)

            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(manager._job("qq_channel")["progress"], 100)

            target.unlink()
            with local_download_server(payload, chunk_delay=0.006) as (download_url, _):
                with (
                    patch.object(manager, "_existing_install_detail", return_value=None),
                    patch.object(manager, "_download_napcat", side_effect=install_download),
                ):
                    manager.install("qq_channel")
                    for _ in range(400):
                        job = manager._job("qq_channel")
                        if job.get("can_pause") and target.with_name("test.bin.part").is_file():
                            break
                        time.sleep(0.01)
                    manager.control("qq_channel", "cancel")
                    for _ in range(400):
                        if manager._job("qq_channel").get("state") == "cancelled":
                            break
                        time.sleep(0.01)

            self.assertEqual(manager._job("qq_channel")["state"], "cancelled")
            self.assertFalse(target.exists())
            self.assertFalse(target.with_name("test.bin.part").exists())

    def test_environment_command_runner_initializes_timeout_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }

            output = manager._run_command(
                "local_voice",
                [sys.executable, "-c", "print('command-ok')"],
                timeout=10,
            )

            self.assertIn("command-ok", output)
            self.assertIsNone(manager._controls["local_voice"]["process"])
            job = manager._job("local_voice")
            self.assertEqual(job["downloaded_bytes"], 0)
            self.assertEqual(job["total_bytes"], 0)
            self.assertIsNone(job["progress"])

    def test_supported_voice_python_rejects_reparse_point_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "python.exe"
            candidate.touch()

            with (
                patch.object(EnvironmentManager, "_path_uses_reparse_point", return_value=True),
                patch("app.studio_capabilities.subprocess.run") as run,
            ):
                supported = EnvironmentManager._supported_venv_python(candidate)

            self.assertFalse(supported)
            run.assert_not_called()

    def test_supported_voice_python_uses_isolated_complete_runtime_smoke_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "python.exe"
            candidate.touch()
            completed = MagicMock(
                returncode=0,
                stdout=json.dumps([str(candidate), str(candidate)]),
            )

            with (
                patch.object(EnvironmentManager, "_path_uses_reparse_point", return_value=False),
                patch.dict(os.environ, {"PYTHONPATH": "unsafe-app-runtime"}, clear=False),
                patch("app.studio_capabilities.subprocess.run", return_value=completed) as run,
            ):
                supported = EnvironmentManager._supported_venv_python(candidate)

            self.assertTrue(supported)
            command = run.call_args.args[0]
            self.assertIn("-I", command)
            self.assertIn("import _socket", command[-1])
            self.assertNotIn("PYTHONPATH", run.call_args.kwargs["env"])

    def test_supported_voice_python_rejects_launcher_backed_by_uv_junction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "python3.10.exe"
            candidate.touch()
            uv_runtime = (
                "C:/Users/test/AppData/Roaming/uv/python/"
                "cpython-3.10-windows-x86_64-none/python.exe"
            )
            completed = MagicMock(
                returncode=0,
                stdout=json.dumps([uv_runtime, uv_runtime]),
            )

            with (
                patch.object(
                    EnvironmentManager,
                    "_path_uses_reparse_point",
                    side_effect=lambda path: Path(path) != candidate,
                ),
                patch("app.studio_capabilities.subprocess.run", return_value=completed),
            ):
                supported = EnvironmentManager._supported_venv_python(candidate)

            self.assertFalse(supported)

    def test_existing_voice_python_does_not_probe_uv_managed_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_data = Path(tmp) / "Roaming"
            uv_python = (
                app_data
                / "uv"
                / "python"
                / "cpython-3.10-windows-x86_64-none"
                / "python.exe"
            )
            uv_python.parent.mkdir(parents=True)
            uv_python.touch()
            manager = EnvironmentManager(Path(tmp) / "xixi", MagicMock())

            with (
                patch.dict(
                    os.environ,
                    {
                        "APPDATA": str(app_data),
                        "LOCALAPPDATA": str(Path(tmp) / "Local"),
                        "XIXI_VOICE_PYTHON": "",
                    },
                    clear=False,
                ),
                patch("app.studio_capabilities.shutil.which", return_value=None),
            ):
                result = manager._existing_supported_python()

            self.assertIsNone(result)

    def test_voice_venv_retries_with_managed_python_after_winerror_448(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp) / "xixi", MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            voice_root = Path(tmp) / "voice"
            external = Path("C:/Users/test/AppData/Roaming/uv/python/python.exe")
            managed = manager.components_root / "Python310" / "python.exe"
            commands: list[list[str]] = []

            def fake_run(key: str, command: list[str], **kwargs: object) -> str:
                commands.append(command)
                if len(commands) == 1:
                    raise OSError(
                        "[WinError 448] 无法遍历该路径，因为它包含不受信任的装入点"
                    )
                return ""

            with (
                patch.object(manager, "_managed_python", side_effect=[external, managed]) as python,
                patch.object(manager, "_run_command", side_effect=fake_run),
            ):
                manager._create_voice_venv(voice_root)

            self.assertEqual(python.call_args_list, [call(), call(force_managed=True)])
            self.assertEqual(commands[0][0], str(external))
            self.assertEqual(commands[1][0], str(managed))
            self.assertNotEqual(commands[1][0], commands[0][0])

    def test_python_import_check_retries_a_transient_first_load_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            python_path = Path(tmp) / "python.exe"
            python_path.touch()
            failed = MagicMock(returncode=1, stderr=b"temporary file scan failure", stdout=b"")
            succeeded = MagicMock(returncode=0, stderr=b"", stdout=b"")

            with (
                patch(
                    "app.studio_capabilities.subprocess.run",
                    side_effect=[failed, succeeded],
                ) as run,
                patch("app.studio_capabilities.time.sleep") as sleep,
            ):
                ready = EnvironmentManager._python_imports(
                    python_path,
                    "torch",
                    "pyopenjtalk",
                    attempts=3,
                    timeout=180,
                )

            self.assertTrue(ready)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.kwargs["timeout"], 180)
            self.assertEqual(run.call_args.kwargs["cwd"], str(python_path.parent))
            sleep.assert_called_once_with(1.5)

    def test_local_voice_install_uses_supported_python_and_cuda_torch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "xixi"
            project_root.mkdir()
            voice_root = Path(tmp) / "voice-engine"
            python_path = voice_root / ".venv" / "Scripts" / "python.exe"
            for path in voice_required_artifacts(voice_root).values():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            package_models = project_root / "runtime" / "voice" / "package" / "models"
            for name in (
                "xixi_voice_multilingual.ckpt",
                "xixi_voice_multilingual.pth",
                "xixi_voice_chinese.pth",
            ):
                (package_models / name).parent.mkdir(parents=True, exist_ok=True)
                (package_models / name).write_bytes(b"model")

            manager = EnvironmentManager(project_root, MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            commands: list[list[str]] = []

            def record_command(key: str, command: list[str], **kwargs: object) -> str:
                commands.append(command)
                return ""

            with (
                patch.object(manager, "_voice_root", return_value=voice_root),
                patch.object(manager, "_managed_python", return_value=Path("python-3.10.exe")),
                patch.object(manager, "_run_command", side_effect=record_command),
                patch.object(manager, "_supported_venv_python", return_value=True),
                patch.object(manager, "_python_imports", side_effect=[False, False, False, True]),
                patch("app.studio_capabilities.register_voice_root") as register,
            ):
                result = manager._install_local_voice()

            self.assertIn("检查完成", result)
            flattened = [part for command in commands for part in command]
            self.assertIn("torch==2.5.1+cu121", flattened)
            self.assertIn("torchaudio==2.5.1+cu121", flattened)
            self.assertIn("https://mirrors.nju.edu.cn/pytorch/whl/cu121", flattened)
            self.assertIn("https://mirrors.nju.edu.cn/pypi/web/simple", flattened)
            self.assertFalse(any("mirrors.tuna.tsinghua.edu.cn" in part for part in flattened))
            self.assertTrue(any("requirements-xixi-windows.txt" in part for part in flattened))
            self.assertIn("pyopenjtalk-plus==0.4.1.post8", flattened)
            register.assert_called_once_with(voice_root)

    def test_local_voice_install_seeds_offline_english_voice_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "xixi"
            project_root.mkdir()
            voice_root = Path(tmp) / "voice-engine"
            for name, path in voice_required_artifacts(voice_root).items():
                if name.startswith("nltk_data:"):
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            package_nltk = project_root / "runtime" / "voice" / "package" / "nltk_data"
            for relative in VOICE_NLTK_DATA_FILES:
                path = package_nltk / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"offline nltk data")

            manager = EnvironmentManager(project_root, MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }

            with (
                patch.object(manager, "_voice_root", return_value=voice_root),
                patch.object(manager, "_supported_venv_python", return_value=True),
                patch.object(manager, "_python_imports", return_value=True),
                patch.object(manager, "_run_command"),
                patch.object(manager, "_download_file") as download,
                patch("app.studio_capabilities.register_voice_root") as register,
            ):
                result = manager._install_local_voice()

            self.assertIn("检查完成", result)
            self.assertTrue(all((voice_nltk_data_root(voice_root) / relative).is_file() for relative in VOICE_NLTK_DATA_FILES))
            download.assert_not_called()
            register.assert_called_once_with(voice_root)

    def test_local_voice_repair_downloads_only_the_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "xixi"
            project_root.mkdir()
            voice_root = Path(tmp) / "voice-engine"
            artifacts = voice_required_artifacts(voice_root)
            for path in artifacts.values():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            missing = artifacts["base_model:s1v3.ckpt"]
            missing.unlink()

            manager = EnvironmentManager(project_root, MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            downloads: list[Path] = []

            def fake_download(key: str, url: str, target: Path, **kwargs: object) -> Path:
                downloads.append(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
                return target

            with (
                patch.object(manager, "_voice_root", return_value=voice_root),
                patch.object(manager, "_download_file", side_effect=fake_download),
                patch.object(manager, "_supported_venv_python", return_value=True),
                patch.object(manager, "_python_imports", return_value=True),
                patch.object(manager, "_run_command") as run,
                patch.object(manager, "_managed_python") as managed_python,
                patch("app.studio_capabilities.register_voice_root") as register,
            ):
                result = manager._install_local_voice()

            self.assertEqual(downloads, [missing])
            self.assertIn("仅补齐了缺失项", result)
            run.assert_not_called()
            managed_python.assert_not_called()
            register.assert_called_once_with(voice_root)

    def test_local_voice_repairs_fast_language_detector_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "xixi"
            project_root.mkdir()
            voice_root = Path(tmp) / "voice-engine"
            artifacts = voice_required_artifacts(voice_root)
            for path in artifacts.values():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            missing = artifacts["language_detector:lid.176.bin"]
            missing.unlink()

            manager = EnvironmentManager(project_root, MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            downloads: list[tuple[str, Path]] = []

            def fake_download(key: str, url: str, target: Path, **kwargs: object) -> Path:
                downloads.append((url, target))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
                return target

            with (
                patch.object(manager, "_voice_root", return_value=voice_root),
                patch.object(manager, "_download_file", side_effect=fake_download),
                patch.object(manager, "_supported_venv_python", return_value=True),
                patch.object(manager, "_python_imports", return_value=True),
                patch.object(manager, "_run_command") as run,
                patch("app.studio_capabilities.register_voice_root") as register,
            ):
                result = manager._install_local_voice()

            self.assertEqual([target for _, target in downloads], [missing])
            self.assertIn("dl.fbaipublicfiles.com", downloads[0][0])
            self.assertIn("仅补齐了缺失项", result)
            run.assert_not_called()
            register.assert_called_once_with(voice_root)

    def test_voice_windows_requirements_exclude_source_only_runtime_packages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "GPT-SoVITS"
            root.mkdir(parents=True)
            (root / "requirements.txt").write_text(
                "\n".join((
                    "fastapi>=0.115",
                    "pyopenjtalk>=0.4.1",
                    "torch",
                    "torchaudio",
                    "torchvision>=0.20",
                    "pypinyin",
                )) + "\n",
                encoding="utf-8",
            )
            manager = EnvironmentManager(Path(tmp) / "xixi", MagicMock())

            filtered = manager._voice_requirements_for_install(root).read_text(encoding="utf-8")

            self.assertIn("fastapi>=0.115", filtered)
            self.assertIn("pypinyin", filtered)
            self.assertNotIn("pyopenjtalk", filtered)
            self.assertNotIn("torchaudio", filtered)
            self.assertNotIn("torchvision", filtered)
            self.assertNotIn("\ntorch\n", f"\n{filtered}")

    def test_frozen_managed_python_uses_supported_310_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "xixi"
            project_root.mkdir()
            manager = EnvironmentManager(project_root, MagicMock())
            managed = manager.components_root / "Python310" / "python.exe"
            downloaded: list[tuple[str, Path]] = []

            def fake_download(
                key: str,
                url: str,
                target: Path,
                **kwargs: object,
            ) -> Path:
                downloaded.append((url, target))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
                return target

            def fake_extract(key: str, archive: Path, target: Path) -> None:
                portable = target / "tools" / "python.exe"
                portable.parent.mkdir(parents=True, exist_ok=True)
                portable.touch()

            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(manager, "_existing_supported_python", return_value=None),
                patch.object(
                    manager,
                    "_supported_venv_python",
                    side_effect=lambda candidate: candidate.is_file(),
                ),
                patch.object(manager, "_download_file", side_effect=fake_download),
                patch.object(manager, "_download_from_mirrors", side_effect=lambda key, urls, target, **kwargs: fake_download(key, urls[0], target, **kwargs)),
                patch.object(manager, "_extract_zip_safely", side_effect=fake_extract),
            ):
                result = manager._managed_python()

            self.assertEqual(result, managed)
            self.assertEqual(len(downloaded), 1)
            url, target = downloaded[0]
            self.assertIn("package/python/3.10.11", url)
            self.assertEqual(target.name, "python-3.10.11.nupkg")
            self.assertFalse(any(manager.components_root.glob(".Python310-install-*")))

    def test_environment_download_reuses_completed_target_and_discards_stale_part(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = Path(tmp) / "python-installer.exe"
            part = target.with_name(f"{target.name}.part")
            target.write_bytes(b"completed-download")
            part.write_bytes(b"stale-duplicate")

            with patch("app.studio_capabilities.urllib.request.urlopen") as open_download:
                result = manager._download_file(
                    "local_voice",
                    "https://example.test/python.exe",
                    target,
                    detail="正在下载运行环境",
                )

            self.assertEqual(result, target)
            self.assertEqual(target.read_bytes(), b"completed-download")
            self.assertFalse(part.exists())
            open_download.assert_not_called()

    def test_environment_download_recovers_from_http_416(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = Path(tmp) / "python-installer.exe"
            part = target.with_name(f"{target.name}.part")
            part.write_bytes(b"outdated-file-that-is-too-large")
            payload = b"fresh-download"

            with local_download_server(payload) as (download_url, handler):
                result = manager._download_file(
                    "local_voice",
                    download_url,
                    target,
                    detail="正在下载运行环境",
                )

            self.assertEqual(result.read_bytes(), payload)
            self.assertGreaterEqual(handler.request_count, 2)
            self.assertFalse(part.exists())

    def test_environment_download_promotes_complete_part_after_http_416(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = Path(tmp) / "python-installer.exe"
            part = target.with_name(f"{target.name}.part")
            payload = b"already-complete"
            part.write_bytes(payload)

            with patch("app.studio_capabilities.subprocess.Popen") as popen:
                result = manager._download_file(
                    "local_voice",
                    "https://example.test/python.exe",
                    target,
                    detail="正在下载运行环境",
                    expected_size=len(payload),
                )

            self.assertEqual(result.read_bytes(), payload)
            self.assertFalse(part.exists())
            self.assertEqual(manager._job("local_voice")["progress"], 100)
            popen.assert_not_called()

    def test_environment_remote_size_probe_uses_content_length(self) -> None:
        response = MagicMock()
        response.status = 200
        response.headers = {"Content-Length": "4096"}

        with patch(
            "app.studio_capabilities.urllib.request.urlopen",
            return_value=response,
        ) as open_remote:
            size = EnvironmentManager._probe_remote_size(
                "https://example.test/model.bin",
                {"User-Agent": "Xixi-Test"},
            )

        self.assertEqual(size, 4096)
        self.assertEqual(open_remote.call_args.args[0].get_method(), "HEAD")
        response.close.assert_called_once_with()

    def test_environment_remote_size_probe_falls_back_to_content_range(self) -> None:
        head_response = MagicMock()
        head_response.status = 200
        head_response.headers = {}
        range_response = MagicMock()
        range_response.status = 206
        range_response.headers = {"Content-Range": "bytes 0-0/8192"}

        with patch(
            "app.studio_capabilities.urllib.request.urlopen",
            side_effect=[head_response, range_response],
        ) as open_remote:
            size = EnvironmentManager._probe_remote_size(
                "https://example.test/model.bin",
                {"User-Agent": "Xixi-Test"},
            )

        self.assertEqual(size, 8192)
        self.assertEqual(open_remote.call_count, 2)
        range_request = open_remote.call_args_list[1].args[0]
        self.assertEqual(range_request.get_method(), "GET")
        self.assertEqual(range_request.get_header("Range"), "bytes=0-0")

    def test_environment_download_probes_total_for_progress_when_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["local_voice"] = {"key": "local_voice", "state": "installing"}
            manager._controls["local_voice"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = Path(tmp) / "model.bin"
            payload = b"xixi-progress" * 100_000

            with local_download_server(payload) as (download_url, _):
                with patch.object(
                    manager,
                    "_probe_remote_size",
                    return_value=len(payload),
                ) as probe:
                    result = manager._download_file(
                        "local_voice",
                        download_url,
                        target,
                        detail="正在下载模型",
                    )

            self.assertEqual(result.read_bytes(), payload)
            self.assertEqual(manager._job("local_voice")["total_bytes"], len(payload))
            self.assertEqual(manager._job("local_voice")["progress"], 100)
            probe.assert_called_once()

    def test_environment_download_resumes_when_response_ends_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(Path(tmp), MagicMock())
            manager._jobs["qq_channel"] = {"key": "qq_channel", "state": "installing"}
            manager._controls["qq_channel"] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
                "process": None,
                "process_suspended": False,
            }
            target = Path(tmp) / "component.zip"
            payload = b"0123456789abcdefghijklmnopqrstuvwxyz"

            with local_download_server(payload, truncate_first_request_at=10) as (download_url, handler):
                result = manager._download_file(
                    "qq_channel",
                    download_url,
                    target,
                    detail="正在下载组件",
                    expected_size=len(payload),
                )

            self.assertEqual(result.read_bytes(), payload)
            self.assertGreaterEqual(handler.request_count, 2)

    def test_frozen_environment_does_not_offer_impossible_self_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = EnvironmentManager(
                Path(tmp),
                MagicMock(),
                lambda: {
                    "model": {"online": False, "enabled": False},
                    "voice": {"online": False},
                    "qq": {"online": False},
                    "vision": {"online": False},
                },
            )
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(EnvironmentManager, "_python_module", return_value=False),
                patch.object(manager, "_local_voice_ready", return_value=False),
                patch.object(manager, "_napcat_root", return_value=None),
                patch.object(manager, "_whisper_model_ready", return_value=False),
                patch.object(manager, "_ollama_executable", return_value=None),
                patch.object(manager, "_ollama_models", return_value=(set(), "")),
            ):
                items = {item["key"]: item for item in manager.status()["items"]}

            for key in ("speech_recognition", "screen_observation"):
                self.assertEqual(items[key]["state"], "failed")
                self.assertEqual(items[key]["status_label"], "安装文件异常")
                self.assertFalse(items[key]["repairable"])
                self.assertEqual(items[key]["action"], "none")

    def test_whisper_prewarm_runs_initial_inference(self) -> None:
        model = MagicMock()
        model.transcribe.return_value = (iter(()), MagicMock())
        with patch("app.asr_bus.create_whisper_model", return_value=model):
            warmed = prewarm_whisper_model(Config(sample_rate=16000))

        self.assertIs(warmed, model)
        self.assertFalse(model.transcribe.call_args.kwargs["vad_filter"])
        self.assertEqual(model.transcribe.call_args.kwargs["language"], "zh")

    def test_synthesized_speech_transcription_skips_mic_processing(self) -> None:
        model = MagicMock()
        model.transcribe.return_value = (
            iter([MagicMock(text="你好呀，希希。今天想和我聊点什么？")]),
            MagicMock(language="zh"),
        )
        cfg = Config(whisper_audio_preprocess=True, whisper_beam_size=5)

        with patch(
            "app.asr_bus._prepare_asr_audio",
            side_effect=AssertionError("clean TTS must not use microphone preprocessing"),
        ):
            text, _ = transcribe_synthesized_speech(
                model,
                "clean-synthesized.wav",
                cfg,
                language="zh",
            )

        self.assertEqual(text, "你好呀，昔夕。今天想和我聊点什么？")
        self.assertEqual(model.transcribe.call_args.args[0], "clean-synthesized.wav")
        kwargs = model.transcribe.call_args.kwargs
        self.assertFalse(kwargs["vad_filter"])
        self.assertFalse(kwargs["condition_on_previous_text"])
        self.assertIsNone(kwargs["initial_prompt"])
        self.assertIsNone(kwargs["hotwords"])
        self.assertEqual(kwargs["beam_size"], 8)
        self.assertEqual(kwargs["best_of"], 8)

    def test_whisper_prewarm_falls_back_to_cpu_after_lazy_cuda_failure(self) -> None:
        gpu_model = MagicMock()
        gpu_model.transcribe.side_effect = RuntimeError("cublas64_12.dll is not found")
        cpu_model = MagicMock()
        cpu_model.transcribe.return_value = (iter(()), MagicMock())
        cfg = Config(sample_rate=16000, whisper_device="cuda")

        with patch(
            "app.asr_bus.create_whisper_model",
            side_effect=[gpu_model, cpu_model],
        ) as create_model:
            warmed = prewarm_whisper_model(cfg)

        self.assertIs(warmed, cpu_model)
        self.assertEqual(create_model.call_count, 2)
        self.assertEqual(create_model.call_args_list[1].kwargs["device_override"], "cpu")

    def test_whisper_retries_only_after_low_confidence_decode(self) -> None:
        model = MagicMock()
        model.transcribe.side_effect = [
            (
                [MagicMock(text="陈池在测试。", start=0.0, end=1.0, avg_logprob=-0.9)],
                MagicMock(language="zh"),
            ),
            (
                [MagicMock(text="测试用户在测试。", start=0.0, end=1.0, avg_logprob=-0.2)],
                MagicMock(language="zh"),
            ),
        ]
        cfg = Config(whisper_audio_preprocess=False)

        text, _ = transcribe_speech(model, "unused.wav", cfg, language="zh")

        self.assertEqual(text, "测试用户在测试。")
        self.assertEqual(model.transcribe.call_count, 2)
        self.assertEqual(model.transcribe.call_args_list[0].kwargs["beam_size"], 5)
        self.assertEqual(model.transcribe.call_args_list[1].kwargs["beam_size"], 8)
        self.assertIsNone(model.transcribe.call_args_list[1].kwargs["initial_prompt"])
        self.assertIsNone(model.transcribe.call_args_list[1].kwargs["hotwords"])

    def test_whisper_keeps_single_pass_for_confident_decode(self) -> None:
        model = MagicMock()
        model.transcribe.return_value = (
            [MagicMock(text="语音识别正常。", start=0.0, end=1.0, avg_logprob=-0.2)],
            MagicMock(language="zh"),
        )
        cfg = Config(whisper_audio_preprocess=False)

        text, _ = transcribe_speech(model, "unused.wav", cfg, language="zh")

        self.assertEqual(text, "语音识别正常。")
        self.assertEqual(model.transcribe.call_count, 1)

    def test_whisper_retries_prompt_leakage_without_hints(self) -> None:
        model = MagicMock()
        model.transcribe.side_effect = [
            (
                [
                    MagicMock(
                        text="用户：Hello 啊，cc 昔夕�我又回来了。用户：爸爸：老爸：小夕",
                        start=0.0,
                        end=3.0,
                        avg_logprob=-0.2,
                    )
                ],
                MagicMock(language="zh"),
            ),
            (
                [MagicMock(text="Hello啊，小夕，我又回来了。", start=0.0, end=3.0, avg_logprob=-0.3)],
                MagicMock(language="zh"),
            ),
        ]
        cfg = Config(whisper_audio_preprocess=False)

        text, _ = transcribe_speech(
            model,
            "unused.wav",
            cfg,
            language="zh",
            context="爸爸 老爸 昔夕 小夕",
        )

        self.assertEqual(text, "Hello啊，小夕，我又回来了。")
        self.assertEqual(model.transcribe.call_count, 2)
        self.assertIsNone(model.transcribe.call_args_list[1].kwargs["initial_prompt"])
        self.assertIsNone(model.transcribe.call_args_list[1].kwargs["hotwords"])

    def test_whisper_rejects_repeated_hotword_hallucination_on_short_speech(self) -> None:
        model = MagicMock()
        repeated = "，".join(["测试昵称"] * 20)
        model.transcribe.side_effect = [
            (
                [MagicMock(text="嗯。", start=0.0, end=0.4, avg_logprob=-1.1)],
                MagicMock(language="zh"),
            ),
            (
                [MagicMock(text=repeated, start=0.0, end=1.0, avg_logprob=-0.1)],
                MagicMock(language="zh"),
            ),
        ]
        cfg = Config(whisper_audio_preprocess=False)

        text, _ = transcribe_speech(model, "unused.wav", cfg, language="zh")

        self.assertEqual(text, "嗯。")
        self.assertEqual(model.transcribe.call_count, 2)
        retry_kwargs = model.transcribe.call_args_list[1].kwargs
        self.assertIsNone(retry_kwargs["initial_prompt"])
        self.assertIsNone(retry_kwargs["hotwords"])
        self.assertEqual(retry_kwargs["no_repeat_ngram_size"], 3)
        self.assertEqual(retry_kwargs["max_new_tokens"], 64)

    def test_whisper_retries_known_subtitle_hallucination(self) -> None:
        model = MagicMock()
        model.transcribe.side_effect = [
            (
                [
                    MagicMock(
                        text="本文字幕由 Amara.org 社区提供",
                        start=0.0,
                        end=0.7,
                        avg_logprob=-0.1,
                    )
                ],
                MagicMock(language="zh"),
            ),
            (
                [MagicMock(text="温", start=0.0, end=0.5, avg_logprob=-0.8)],
                MagicMock(language="zh"),
            ),
        ]
        cfg = Config(whisper_audio_preprocess=False)

        text, _ = transcribe_speech(model, "unused.wav", cfg, language="zh")

        self.assertEqual(text, "嗯")
        self.assertEqual(model.transcribe.call_count, 2)
        self.assertIsNone(model.transcribe.call_args_list[1].kwargs["initial_prompt"])

    def test_whisper_short_hallucination_retries_with_original_audio(self) -> None:
        model = MagicMock()
        model.transcribe.side_effect = [
            (
                [
                    MagicMock(
                        text="本文字幕由 Amara.org 社区提供",
                        start=0.0,
                        end=0.7,
                        avg_logprob=-0.1,
                    )
                ],
                MagicMock(language="zh"),
            ),
            (
                [MagicMock(text="嗯", start=0.0, end=0.5, avg_logprob=-0.6)],
                MagicMock(language="zh"),
            ),
        ]
        cfg = Config(whisper_audio_preprocess=True)

        with patch("app.asr_bus._prepare_asr_audio", return_value=("processed.wav", None)):
            text, _ = transcribe_speech(model, "original.webm", cfg, language="zh")

        self.assertEqual(text, "嗯")
        self.assertEqual(model.transcribe.call_args_list[0].args[0], "processed.wav")
        self.assertEqual(model.transcribe.call_args_list[1].args[0], "original.webm")

    def test_whisper_retries_primary_model_with_gpu_int8_before_fallback(self) -> None:
        cfg = Config(
            whisper_model_path="large-local",
            whisper_fallback_model_path="small-local",
            whisper_device="cuda",
            whisper_compute_type="int8_float16",
            whisper_fallback_compute_type="float16",
        )
        loaded = MagicMock()
        with (
            patch("app.asr_bus._local_whisper_model_ready", return_value=True),
            patch("app.asr_bus.WhisperModel", side_effect=[RuntimeError("out of memory"), loaded]) as constructor,
        ):
            result = create_whisper_model(cfg)

        self.assertIs(result, loaded)
        self.assertEqual(constructor.call_count, 2)
        self.assertEqual(constructor.call_args_list[0].args[0], "large-local")
        self.assertEqual(constructor.call_args_list[0].kwargs["compute_type"], "int8_float16")
        self.assertEqual(constructor.call_args_list[1].args[0], "large-local")
        self.assertEqual(constructor.call_args_list[1].kwargs["compute_type"], "int8")

    def test_whisper_cpu_override_forces_int8(self) -> None:
        cfg = Config(
            whisper_model_path="large-local",
            whisper_fallback_model_path="small-local",
            whisper_device="cuda",
            whisper_compute_type="int8_float16",
            whisper_fallback_compute_type="float16",
        )
        loaded = MagicMock()
        with (
            patch("app.asr_bus._local_whisper_model_ready", return_value=True),
            patch("app.asr_bus.WhisperModel", return_value=loaded) as constructor,
        ):
            result = create_whisper_model(cfg, device_override="cpu")

        self.assertIs(result, loaded)
        self.assertEqual(constructor.call_args.kwargs["device"], "cpu")
        self.assertEqual(constructor.call_args.kwargs["compute_type"], "int8")

    def make_config(self, root: Path) -> Config:
        persona = root / "persona.txt"
        persona.write_text("你是昔夕。", encoding="utf-8")
        (root / "interest_profile.json").write_text(
            json.dumps({"version": 1, "interests": []}),
            encoding="utf-8",
        )
        return Config(
            root=root,
            persona_file=persona,
            logs_dir=root / "logs",
            memory_file=root / "data" / "conversations.json",
            memory_db=root / "data" / "memory.db",
            learning_sources_file=root / "learning_sources.json",
            meme_lexicon_file=root / "meme_lexicon.json",
            qq_user_id=1000000001,
            bot_qq_id=1000000002,
            use_openai=True,
            weather_enabled=False,
        )

    def make_runtime(self, root: Path) -> StudioRuntime:
        cfg = self.make_config(root)
        cfg.ensure_dirs()
        with patch("app.studio.Brain", FakeBrain):
            return StudioRuntime(cfg)

    def test_decode_data_url_validates_size_and_encoding(self) -> None:
        encoded = base64.b64encode(b"hello").decode("ascii")
        data, mime_type = _decode_data_url(
            f"data:text/plain;base64,{encoded}",
            max_bytes=10,
        )
        self.assertEqual(data, b"hello")
        self.assertEqual(mime_type, "text/plain")
        with self.assertRaises(ValueError):
            _decode_data_url("not-a-data-url", max_bytes=10)
        with self.assertRaises(ValueError):
            _decode_data_url(f"data:text/plain;base64,{encoded}", max_bytes=2)

    def test_advanced_info_reports_runtime_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            payload = runtime.advanced_info()

            self.assertRegex(payload["release"], r"^\d{4}\.\d{2}\.\d{2}$")
            self.assertTrue(any(item["key"] == "studio-backend" for item in payload["windows"]))
            self.assertTrue(any(item["key"] == "memory" for item in payload["paths"]))
            self.assertNotIn("test-key", json.dumps(payload, ensure_ascii=False))

    def test_transcription_uses_vad_and_safe_vocabulary_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime._asr_model = MagicMock()
            runtime._asr_model.transcribe.return_value = (
                [MagicMock(text="爸爸，语音功能正常。")],
                MagicMock(),
            )
            audio = base64.b64encode(b"fake-audio").decode("ascii")

            result = runtime.transcribe(
                {
                    "audio": f"data:audio/mpeg;base64,{audio}",
                    "context": "我们正在讨论昔夕的语音功能",
                }
            )

            self.assertEqual(result["text"], "爸爸，语音功能正常。")
            kwargs = runtime._asr_model.transcribe.call_args.kwargs
            self.assertTrue(kwargs["vad_filter"])
            self.assertEqual(kwargs["beam_size"], 5)
            self.assertFalse(kwargs["condition_on_previous_text"])
            self.assertIn("小夕", kwargs["initial_prompt"])
            self.assertIn("昔夕", kwargs["hotwords"])
            self.assertNotIn("用户", kwargs["initial_prompt"])
            self.assertNotIn("语音功能", kwargs["initial_prompt"])
            self.assertNotIn("语音功能", kwargs["hotwords"])
            self.assertEqual(kwargs["vad_parameters"]["speech_pad_ms"], 300)

    def test_transcription_uses_selected_call_language_without_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime._asr_model = MagicMock()
            runtime._asr_model.transcribe.return_value = (
                [MagicMock(text="こんにちは。")],
                MagicMock(),
            )
            audio = base64.b64encode(b"fake-audio").decode("ascii")

            result = runtime.transcribe(
                {
                    "audio": f"data:audio/webm;base64,{audio}",
                    "language": "ja",
                }
            )

            self.assertEqual(result["language"], "ja")
            self.assertEqual(runtime._asr_model.transcribe.call_args.kwargs["language"], "ja")

    def test_voice_call_input_defaults_to_chinese_independent_of_reply_voice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.cfg.voice_language = "ja"
            runtime._asr_model = MagicMock()
            runtime._asr_model.transcribe.return_value = (
                [MagicMock(text="我想继续聊刚才的话题。")],
                MagicMock(language="zh"),
            )
            audio = base64.b64encode(b"fake-audio").decode("ascii")

            result = runtime.transcribe({
                "audio": f"data:audio/webm;base64,{audio}",
                "call_mode": True,
            })

            self.assertEqual(result["language"], "zh")
            self.assertEqual(runtime._asr_model.transcribe.call_args.kwargs["language"], "zh")

    def test_transcription_normalizes_xixi_proper_name_variants(self) -> None:
        self.assertEqual(
            normalize_asr_transcript("小西说Xixi的语音通话好了，小溪边朝朝夕夕都很安静"),
            "小夕说昔夕的语音通话好了，小溪边朝朝夕夕都很安静",
        )

    def test_transcription_normalizes_only_isolated_short_acknowledgement(self) -> None:
        self.assertEqual(normalize_asr_transcript("温"), "嗯")
        self.assertEqual(normalize_asr_transcript("恩。"), "嗯。")
        self.assertEqual(normalize_asr_transcript("温度刚好"), "温度刚好")

    def test_transcription_normalizes_chinese_to_simplified_without_touching_japanese(self) -> None:
        self.assertEqual(normalize_asr_transcript("對，妳回來了嗎？"), "对，你回来了吗？")
        self.assertEqual(
            normalize_asr_transcript("對，戻ってきた？", language="ja"),
            "對，戻ってきた？",
        )

    def test_transcription_uses_unique_homophone_from_recent_context(self) -> None:
        self.assertEqual(
            correct_asr_with_context(
                "这个孩可以继续使用",
                "用户：这个还可以继续使用。昔夕：嗯，可以继续。",
            ),
            "这个还可以继续使用",
        )

    def test_transcription_keeps_ambiguous_homophones_unchanged(self) -> None:
        self.assertEqual(
            correct_asr_with_context(
                "你去那里看看",
                "用户：哪里和那里都需要检查。",
            ),
            "你去那里看看",
        )

    def test_image_chat_passes_visual_context_to_shared_brain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.vision.analyze_bytes = AsyncMock(  # type: ignore[method-assign]
                return_value="图片1：鸡头西装角色站在爆炸前。"
            )
            image = base64.b64encode(b"fake-image").decode("ascii")

            result = runtime.chat(
                {
                    "text": "你看看这个",
                    "images": [f"data:image/png;base64,{image}"],
                    "voice": False,
                }
            )

            self.assertIn("故意搞怪", result["reply"])
            runtime.vision.analyze_bytes.assert_awaited_once()
            fake = runtime.raw_brain
            self.assertIsInstance(fake, FakeBrain)
            self.assertEqual(fake.calls[0][0], "你看看这个")
            self.assertIn("鸡头西装角色", fake.calls[0][1]["attachment_context"])
            self.assertIn("一两个关键点", fake.calls[0][1]["turn_instruction"])

    def test_persona_save_is_atomic_and_hot_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))

            saved = runtime.save_persona("你是昔夕。\n说话自然一点。")

            self.assertIn("说话自然一点", saved["content"])
            self.assertEqual(runtime.raw_brain.reload_count, 1)
            self.assertFalse(runtime.cfg.persona_file.with_suffix(".tmp").exists())

    def test_group_relay_result_is_grounded_in_real_action_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.qq_actions._execute_private_relay_steps = AsyncMock(  # type: ignore[method-assign]
                return_value=["群代发成功：测试群 -> 小明（QQ 99）"]
            )

            with patch.object(runtime, "_qq_status", return_value={"online": True}):
                runtime.chat(
                    {
                        "text": "去测试群给小明发消息说今晚八点开黑",
                        "images": [],
                        "voice": False,
                    }
                )

            fake = runtime.raw_brain
            self.assertIsInstance(fake, FakeBrain)
            turn_instruction = fake.calls[0][1]["turn_instruction"]
            self.assertIn("程序动作已经按执行计划实际运行", turn_instruction)
            self.assertIn("群代发成功", turn_instruction)

    def test_group_relay_is_blocked_while_xixi_qq_is_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.qq_actions._execute_private_relay_steps = AsyncMock()  # type: ignore[method-assign]

            runtime.chat(
                {
                    "text": "去2000000001群里给小明发消息说：今晚八点开黑。",
                    "images": [],
                    "voice": False,
                }
            )

            runtime.qq_actions._execute_private_relay_steps.assert_not_awaited()
            fake = runtime.raw_brain
            self.assertIsInstance(fake, FakeBrain)
            self.assertIn("昔夕 QQ 当前已下线", fake.calls[0][1]["turn_instruction"])

    def test_qq_status_exposes_connection_components_for_settings_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "xixi"
            root.mkdir()
            launcher = root.parent / "napcat" / "launcher-user.bat"
            launcher.parent.mkdir()
            launcher.touch()
            runtime = self.make_runtime(root)
            runtime._napcat_status = MagicMock(  # type: ignore[method-assign]
                return_value={
                    "online": True,
                    "service_online": True,
                    "user_id": runtime.cfg.bot_qq_id,
                    "nickname": "昔夕",
                }
            )
            runtime._qq_enabled_event.set()
            runtime._qq_connection_state = "online"
            runtime.qq_thread = MagicMock()
            runtime.qq_thread.is_alive.return_value = True

            status = runtime._qq_status()

            self.assertTrue(status["online"])
            self.assertTrue(status["qq_process_online"])
            self.assertTrue(status["qq_login_online"])
            self.assertTrue(status["napcat_service_online"])
            self.assertTrue(status["onebot_online"])
            self.assertTrue(status["napcat_installed"])

    def test_qq_listener_can_go_offline_and_online_in_same_process(self) -> None:
        async def fake_listener(
            cfg: Config,
            user_id: int,
            brain: object,
            *,
            enabled_event: threading.Event,
            stop_event: threading.Event,
            state_callback: object,
        ) -> None:
            del cfg, user_id, brain
            callback = state_callback
            while not stop_event.is_set():
                callback("online" if enabled_event.is_set() else "offline")  # type: ignore[operator]
                await asyncio.sleep(0.01)
            callback("offline")  # type: ignore[operator]

        def wait_for_state(runtime: StudioRuntime, expected: str) -> None:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if runtime._qq_connection_state == expected:
                    return
                time.sleep(0.01)
            self.fail(f"QQ state did not become {expected}")

        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            napcat = {"online": True, "user_id": 1000000002, "nickname": "昔夕"}
            try:
                with (
                    patch("app.studio.run_ws_listener", side_effect=fake_listener),
                    patch.object(runtime, "_napcat_status", return_value=napcat),
                    patch.object(runtime, "_stop_napcat_account", return_value=True),
                ):
                    runtime.start_qq()
                    wait_for_state(runtime, "online")
                    self.assertTrue(runtime._qq_status()["online"])

                    offline = runtime.control_qq("offline")["qq"]
                    wait_for_state(runtime, "offline")
                    self.assertFalse(offline["enabled"])
                    self.assertTrue(offline["napcat_online"])
                    self.assertTrue(runtime.qq_thread and runtime.qq_thread.is_alive())

                    runtime.control_qq("online")
                    wait_for_state(runtime, "online")
                    self.assertTrue(runtime._qq_status()["online"])
            finally:
                runtime.shutdown_qq()

    def test_qq_online_does_not_block_while_napcat_is_starting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            release_launch = threading.Event()
            launch_started = threading.Event()

            def slow_launch(
                _bot_qq_id: int,
                _cancel_event: threading.Event | None = None,
            ) -> dict[str, object]:
                launch_started.set()
                release_launch.wait(timeout=2)
                return {"user_id": runtime.cfg.bot_qq_id, "nickname": "昔夕"}

            runtime._napcat_status = MagicMock(  # type: ignore[method-assign]
                return_value={"online": False, "user_id": None, "nickname": ""}
            )
            runtime._launch_napcat_account = MagicMock(  # type: ignore[method-assign]
                side_effect=slow_launch
            )
            runtime._start_service_thread = MagicMock()  # type: ignore[method-assign]
            started = time.monotonic()
            result = runtime.control_qq("online")["qq"]
            elapsed = time.monotonic() - started
            try:
                self.assertLess(elapsed, 0.5)
                self.assertTrue(result["enabled"])
                self.assertTrue(launch_started.wait(timeout=0.5))
                self.assertTrue(runtime.cfg.qq_enabled)
            finally:
                release_launch.set()
                if runtime._qq_launch_thread:
                    runtime._qq_launch_thread.join(timeout=2)

    def test_qq_offline_during_startup_discards_late_napcat_login(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            release_launch = threading.Event()

            def slow_launch(
                _bot_qq_id: int,
                _cancel_event: threading.Event | None = None,
            ) -> dict[str, object]:
                release_launch.wait(timeout=2)
                return {"user_id": runtime.cfg.bot_qq_id, "nickname": "昔夕"}

            runtime._napcat_status = MagicMock(  # type: ignore[method-assign]
                return_value={"online": False, "user_id": None, "nickname": ""}
            )
            runtime._launch_napcat_account = MagicMock(side_effect=slow_launch)  # type: ignore[method-assign]
            runtime._stop_napcat_account = MagicMock(return_value=True)  # type: ignore[method-assign]
            runtime._start_service_thread = MagicMock()  # type: ignore[method-assign]

            runtime.control_qq("online")
            runtime.control_qq("offline")
            release_launch.set()
            if runtime._qq_launch_thread:
                runtime._qq_launch_thread.join(timeout=2)

            self.assertFalse(runtime.cfg.qq_enabled)
            self.assertFalse(runtime._qq_enabled_event.is_set())
            self.assertGreaterEqual(runtime._stop_napcat_account.call_count, 2)

    def test_qq_identity_save_rebuilds_bridge_without_logging_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.start_background_services = MagicMock()  # type: ignore[method-assign]
            runtime._napcat_status = MagicMock(  # type: ignore[method-assign]
                return_value={"online": False, "user_id": None, "nickname": ""}
            )
            result = runtime.save_qq_identity(
                {"bot_qq_id": "12345678", "owner_qq_id": "87654321"}
            )
            self.assertEqual(runtime.cfg.bot_qq_id, 12345678)
            self.assertEqual(runtime.cfg.qq_user_id, 87654321)
            self.assertEqual(runtime.qq_actions.bot_user_id, 12345678)
            self.assertEqual(result["qq_identity"]["bot_qq_id"], "12345678")
            runtime.start_background_services.assert_called_once_with()

    def test_qq_account_switch_commits_only_after_verified_login(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime._napcat_status = MagicMock(  # type: ignore[method-assign]
                return_value={"online": False, "user_id": None, "nickname": ""}
            )
            runtime._stop_napcat_account = MagicMock()  # type: ignore[method-assign]
            runtime._launch_napcat_account = MagicMock(  # type: ignore[method-assign]
                return_value={"user_id": 12345678, "nickname": "new-xixi"}
            )
            runtime.start_qq = MagicMock(  # type: ignore[method-assign]
                return_value={"online": True}
            )
            runtime.shutdown_qq = MagicMock()  # type: ignore[method-assign]
            result = runtime.switch_qq_account(
                {"bot_qq_id": 12345678, "owner_qq_id": 87654321}
            )
            self.assertTrue(result["accepted"])
            assert runtime._qq_launch_thread is not None
            runtime._qq_launch_thread.join(timeout=2)
            self.assertEqual(runtime.cfg.bot_qq_id, 12345678)
            self.assertEqual(runtime.cfg.qq_user_id, 87654321)
            self.assertTrue(runtime.cfg.qq_enabled)
            self.assertEqual(runtime._qq_status()["account_state"], "online")
            runtime._launch_napcat_account.assert_called_once()
            self.assertEqual(runtime._launch_napcat_account.call_args.args[0], 12345678)

    def test_failed_qq_account_switch_preserves_previous_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)
            runtime._napcat_status = MagicMock(  # type: ignore[method-assign]
                return_value={"online": False, "user_id": None, "nickname": ""}
            )
            runtime._stop_napcat_account = MagicMock()  # type: ignore[method-assign]
            runtime._launch_napcat_account = MagicMock(  # type: ignore[method-assign]
                return_value={"user_id": 99999999, "nickname": "wrong"}
            )
            runtime.shutdown_qq = MagicMock()  # type: ignore[method-assign]
            runtime.start_background_services = MagicMock()  # type: ignore[method-assign]
            result = runtime.switch_qq_account(
                {"bot_qq_id": 12345678, "owner_qq_id": 87654321}
            )
            self.assertTrue(result["accepted"])
            assert runtime._qq_launch_thread is not None
            runtime._qq_launch_thread.join(timeout=2)
            self.assertEqual(runtime.cfg.bot_qq_id, 1000000002)
            self.assertEqual(runtime.cfg.qq_user_id, 1000000001)
            status = runtime._qq_status()
            self.assertEqual(status["account_state"], "error")
            self.assertIn("实际登录账号", status["account_error"])
            saved = json.loads(
                (root / "data" / "qq_identity.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved["bot_qq_id"], 1000000002)
            self.assertEqual(saved["owner_qq_id"], 1000000001)

    def test_failed_first_qq_account_switch_keeps_unconfigured_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)
            runtime.cfg.bot_qq_id = 0
            runtime.cfg.qq_user_id = 0
            runtime._napcat_status = MagicMock(  # type: ignore[method-assign]
                return_value={"online": False, "user_id": None, "nickname": ""}
            )
            runtime._stop_napcat_account = MagicMock()  # type: ignore[method-assign]
            runtime._launch_napcat_account = MagicMock(  # type: ignore[method-assign]
                return_value={"user_id": 99999999, "nickname": "wrong"}
            )
            runtime.shutdown_qq = MagicMock()  # type: ignore[method-assign]
            runtime.start_background_services = MagicMock()  # type: ignore[method-assign]

            result = runtime.switch_qq_account(
                {"bot_qq_id": 12345678, "owner_qq_id": 87654321}
            )

            self.assertTrue(result["accepted"])
            assert runtime._qq_launch_thread is not None
            runtime._qq_launch_thread.join(timeout=2)
            self.assertEqual(runtime.cfg.bot_qq_id, 0)
            self.assertEqual(runtime.cfg.qq_user_id, 0)
            self.assertEqual(runtime._qq_status()["account_state"], "error")
            self.assertFalse((root / "data" / "qq_identity.json").exists())

    def test_settings_are_clamped_persisted_and_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)
            MemoryStore(runtime.cfg.memory_db)

            with patch("app.studio.prewarm_voice_language") as prewarm:
                applied = runtime.update_settings(
                    {
                        "owner_addresses": "爸爸、爹爹、队长",
                        "owner_address_chance": 4,
                        "gpt_sovits_chinese_speed": 1.12,
                        "voice_language": "ja",
                        "weather_location": "成都",
                        "unknown_setting": "ignored",
                    }
                )

            prewarm.assert_called_once_with("ja")

            self.assertEqual(applied["owner_address_chance"], 1.0)
            self.assertEqual(applied["owner_addresses"], "爸爸、爹爹、队长")
            self.assertEqual(applied["gpt_sovits_chinese_speed"], 1.12)
            self.assertEqual(runtime.cfg.weather_location, "成都")
            runtime.raw_brain.environment.invalidate_weather.assert_called_once_with()
            persisted = json.loads(runtime.settings_file.read_text(encoding="utf-8"))
            self.assertNotIn("unknown_setting", persisted)

            with patch("app.studio.Brain", FakeBrain):
                reloaded = StudioRuntime(self.make_config(root))
            self.assertEqual(reloaded.cfg.weather_location, "成都")
            self.assertEqual(reloaded.cfg.gpt_sovits_chinese_speed, 1.12)
            self.assertEqual(reloaded.cfg.voice_language, "ja")
            self.assertEqual(reloaded.cfg.owner_addresses, "爸爸、爹爹、队长")

    def test_assistant_name_persists_and_updates_default_wake_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)

            applied = runtime.update_settings({"assistant_name": "星璃"})

            self.assertEqual(applied["assistant_name"], "星璃")
            self.assertEqual(applied["qq_group_wake_names"], "星璃")
            self.assertEqual(runtime.cfg.assistant_name, "星璃")
            self.assertEqual(runtime.raw_brain.reload_count, 1)
            with patch("app.studio.Brain", FakeBrain):
                reloaded = StudioRuntime(self.make_config(root))
            self.assertEqual(reloaded.cfg.assistant_name, "星璃")
            self.assertEqual(reloaded.cfg.qq_group_wake_names, "星璃")

    def test_assistant_rename_preserves_custom_wake_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.update_settings({"qq_group_wake_names": "夕宝、搭档"})

            first = runtime.update_settings({"assistant_name": "星璃"})
            second = runtime.update_settings({"assistant_name": "阿澄"})

            self.assertEqual(first["qq_group_wake_names"], "星璃、夕宝、搭档")
            self.assertEqual(second["qq_group_wake_names"], "阿澄、夕宝、搭档")

    def test_invalid_assistant_names_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            for value in ("", "第一行\n第二行", "名" * 25):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        runtime.update_settings({"assistant_name": value})

    def test_asr_hints_and_normalization_follow_assistant_name(self) -> None:
        cfg = Config(assistant_name="星璃")

        self.assertIn("星璃", build_asr_prompt(cfg) or "")
        self.assertIn("星璃", build_asr_hotwords(cfg) or "")
        self.assertEqual(
            normalize_asr_transcript("Xixi你在吗", assistant_name="星璃"),
            "星璃你在吗",
        )

    def test_qq_group_wake_settings_normalize_persist_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)

            applied = runtime.update_settings({
                "qq_group_at_wake_enabled": False,
                "qq_group_name_wake_enabled": True,
                "qq_group_wake_names": " 昔夕，小夕\nXX、xx ",
            })

            self.assertFalse(applied["qq_group_at_wake_enabled"])
            self.assertTrue(applied["qq_group_name_wake_enabled"])
            self.assertEqual(applied["qq_group_wake_names"], "昔夕、小夕、XX")
            persisted = json.loads(runtime.settings_file.read_text(encoding="utf-8"))
            self.assertEqual(persisted["qq_group_wake_names"], "昔夕、小夕、XX")

            with patch("app.studio.Brain", FakeBrain):
                reloaded = StudioRuntime(self.make_config(root))
            self.assertFalse(reloaded.cfg.qq_group_at_wake_enabled)
            self.assertTrue(reloaded.cfg.qq_group_name_wake_enabled)
            self.assertEqual(reloaded.cfg.qq_group_wake_names, "昔夕、小夕、XX")

    def test_qq_group_name_wake_requires_an_alias_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))

            with self.assertRaisesRegex(ValueError, "至少填写一个唤醒名称"):
                runtime.update_settings({"qq_group_wake_names": "，、\n"})

            applied = runtime.update_settings({
                "qq_group_name_wake_enabled": False,
                "qq_group_wake_names": "",
            })
            self.assertFalse(applied["qq_group_name_wake_enabled"])
            self.assertEqual(applied["qq_group_wake_names"], "")

    def test_studio_voice_translates_audio_only_to_selected_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.cfg.voice_language = "ja"

            with patch("app.studio.generate_tts_audio", new=AsyncMock()) as generate:
                result = runtime.chat(
                    {"text": "说给我听", "images": [], "voice": True}
                )

            self.assertIn("故意搞怪", result["reply"])
            self.assertTrue(result["audio_url"].startswith("/api/audio/"))
            self.assertEqual(generate.await_args.args[0], "この画像、なかなか面白いね。")
            self.assertEqual(generate.await_args.kwargs["forced_language"], "ja")

    def test_studio_voice_can_use_english_without_changing_text_reply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.cfg.voice_language = "en"

            with patch("app.studio.generate_tts_audio", new=AsyncMock()) as generate:
                result = runtime.chat(
                    {"text": "说给我听", "images": [], "voice": True}
                )

            self.assertIn("故意搞怪", result["reply"])
            self.assertEqual(generate.await_args.args[0], "This image is pretty interesting.")
            self.assertEqual(generate.await_args.kwargs["forced_language"], "en")

    def test_render_voice_call_mode_uses_complete_call_tts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            with (
                patch("app.studio.generate_call_tts_audio", new=AsyncMock()) as call_generate,
                patch("app.studio.generate_tts_audio", new=AsyncMock()) as regular_generate,
            ):
                result = runtime.render_voice({
                    "text": "这波稳住。",
                    "language": "zh",
                    "call_mode": True,
                })

            self.assertTrue(result["audio_url"].startswith("/api/audio/"))
            call_generate.assert_awaited_once()
            regular_generate.assert_not_awaited()
            self.assertEqual(call_generate.await_args.kwargs["forced_language"], "zh")

    def test_render_voice_translates_chinese_before_japanese_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            with patch(
                "app.studio.generate_call_tts_audio",
                new=AsyncMock(),
            ) as generate:
                runtime.render_voice({
                    "text": "这张图挺有意思的。",
                    "language": "ja",
                    "quality": "complete",
                })

            self.assertEqual(generate.await_args.args[0], "この画像、なかなか面白いね。")
            self.assertEqual(generate.await_args.kwargs["forced_language"], "ja")

    def test_render_voice_translates_chinese_before_english_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            with patch(
                "app.studio.generate_call_tts_audio",
                new=AsyncMock(),
            ) as generate:
                runtime.render_voice({
                    "text": "这张图挺有意思的。",
                    "language": "en",
                    "quality": "complete",
                })

            self.assertEqual(generate.await_args.args[0], "This image is pretty interesting.")
            self.assertEqual(generate.await_args.kwargs["forced_language"], "en")

    def test_render_voice_normalizes_mixed_reply_before_selected_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            with patch(
                "app.studio.generate_call_tts_audio",
                new=AsyncMock(),
            ) as generate:
                runtime.render_voice({
                    "text": "今晚陪你聊，let's take it easy，今夜ものんびり話そうね。",
                    "language": "ja",
                    "quality": "complete",
                })

            self.assertEqual(generate.await_args.args[0], "この画像、なかなか面白いね。")
            self.assertEqual(generate.await_args.kwargs["forced_language"], "ja")

    def test_chinese_voice_match_rejects_missing_phrase(self) -> None:
        accepted, score, metrics = _chinese_voice_match(
            "等水开了我会给你泡一杯热茶，再慢慢讲给你听。",
            "等水开了我会给你泡茶。",
        )

        self.assertFalse(accepted)
        self.assertLess(score, 0.9)
        self.assertLess(metrics["length_ratio"], 0.92)

    def test_chinese_voice_match_accepts_homophone_transcript(self) -> None:
        accepted, score, _ = _chinese_voice_match(
            "昔夕会认真听你说。",
            "西西会认真听你说。",
        )

        self.assertTrue(accepted)
        self.assertGreater(score, 0.9)

    def test_chinese_voice_match_accepts_homophone_identifier_transcript(self) -> None:
        accepted, score, metrics = _chinese_voice_match(
            "西西，你好呀。",
            "嘻嘻，你好呀。",
        )

        self.assertTrue(accepted)
        self.assertGreater(score, 0.8)
        self.assertEqual(metrics["phonetic_similarity"], 1.0)

    def test_chinese_voice_match_normalizes_latin_identifier_transcript(self) -> None:
        accepted, score, _ = _chinese_voice_match(
            "西西，你好呀。",
            "CC，你好呀。",
        )

        self.assertTrue(accepted)
        self.assertEqual(score, 1.0)

    def test_chinese_voice_match_rejects_wrong_identifier_pronunciation(self) -> None:
        accepted, _, metrics = _chinese_voice_match(
            "西西，你好呀。",
            "谢谢，你好呀。",
        )

        self.assertFalse(accepted)
        self.assertLess(metrics["phonetic_similarity"], 0.9)

    def test_chinese_voice_match_normalizes_arabic_numbers(self) -> None:
        accepted, score, _ = _chinese_voice_match(
            "晚上好，1。",
            "晚上好一",
        )

        self.assertTrue(accepted)
        self.assertGreater(score, 0.95)

    def test_chinese_voice_match_rejects_wrong_key_character_in_short_sentence(self) -> None:
        accepted, _, _ = _chinese_voice_match(
            "第一句，我已经把窗户关好了。",
            "第一季，我已经把窗户关好了。",
        )

        self.assertFalse(accepted)


    def test_call_mode_uses_low_latency_brain_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))

            result = runtime.chat(
                {"text": "你在听吗", "images": [], "voice": False, "call_mode": True}
            )

            _, kwargs = runtime.raw_brain.calls[-1]
            self.assertTrue(kwargs["realtime_mode"])
            self.assertEqual(kwargs["max_tokens_override"], 80)
            self.assertIn("实时语音通话", str(kwargs["turn_instruction"]))
            self.assertTrue(result["voice_text"])
            self.assertEqual(result["voice_language"], "zh")

    def test_call_mode_includes_active_game_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.games.status = MagicMock(return_value={  # type: ignore[method-assign]
                "active": True,
                "mode": "observe",
                "hwnd": 321,
                "window_title": "FCBrowser",
            })
            runtime._game_observation.update({
                "analysis": "角色正在移动教学，画面提示按 A、D。",
                "state": "watching",
            })

            runtime.chat({
                "text": "我现在该做什么",
                "images": [],
                "voice": False,
                "call_mode": True,
                "game_context": True,
            })

            _, kwargs = runtime.raw_brain.calls[-1]
            instruction = str(kwargs["turn_instruction"])
            self.assertIn("边玩游戏边通话", instruction)
            self.assertIn("FCBrowser", instruction)
            self.assertIn("角色正在移动教学", instruction)
            self.assertIn("观察状态：watching", instruction)

    def test_voice_language_setting_accepts_english_and_rejects_unknown_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))

            with patch("app.studio.prewarm_voice_language") as prewarm:
                applied = runtime.update_settings({"voice_language": "en"})

            self.assertEqual(applied["voice_language"], "en")
            self.assertEqual(runtime.cfg.voice_language, "en")
            prewarm.assert_called_once_with("en")

            with self.assertRaisesRegex(ValueError, "语音语言只能是中文、日文或英文"):
                runtime.update_settings({"voice_language": "ko"})

            self.assertEqual(runtime.cfg.voice_language, "en")

    def test_voice_status_exposes_live_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.cfg.voice_language = "ja"

            with patch(
                "app.studio.voice_service_status",
                return_value={"online": True},
            ):
                status = runtime._voice_status()

            self.assertEqual(status["language"], "ja")
            self.assertTrue(status["enabled"])

    def test_public_voice_status_hides_voice_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            status = runtime._public_voice_status({
                "online": True,
                "voice": "昔夕语音系统",
                "release": "Xixi Voice System 2026-08-11",
                "profiles": {"zh": "trained"},
                "missing_assets": ["xixi_voice.pth"],
                "engine": "GPT-SoVITS",
            })

            self.assertEqual(status["engine"], "GPT-SoVITS")
            self.assertNotIn("voice", status)
            self.assertNotIn("release", status)
            self.assertNotIn("profiles", status)
            self.assertNotIn("missing_assets", status)

    def test_all_editable_settings_reach_the_live_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            values = {
                "qq_enabled": False,
                "qq_group_at_wake_enabled": True,
                "qq_group_name_wake_enabled": True,
                "qq_group_wake_names": "昔夕、小夕、xx",
                "voice_enabled": False,
                "voice_language": "ja",
                "openai_model": "test-chat-model",
                "vision_model": "test-vision-model",
                "vision_enabled": False,
                "web_search_enabled": False,
                "learning_enabled": False,
                "anime_learning_enabled": False,
                "weather_enabled": True,
                "weather_alert_enabled": False,
                "weather_location": "成都",
                "autonomous_group_enabled": False,
                "autonomous_private_enabled": False,
                "owner_address_chance": 0.25,
                "learning_interest_interval_hours": 1.5,
                "learning_general_interval_hours": 8,
                "learning_academic_interval_hours": 24,
                "autonomous_private_min_interval_hours": 0.25,
                "autonomous_private_max_interval_hours": 1.25,
                "gpt_sovits_chinese_speed": 1.08,
                "tts_rate": "+8%",
            }

            applied = runtime.update_settings(values)

            self.assertEqual(applied, values)
            for name, value in values.items():
                self.assertEqual(getattr(runtime.cfg, name), value)
            self.assertFalse(runtime.vision.enabled)
            self.assertEqual(runtime.vision.model, "test-vision-model")
            with (
                patch.object(
                    runtime,
                    "_napcat_status",
                    return_value={"online": False, "user_id": None, "nickname": ""},
                ),
                patch.object(runtime, "_voice_status", return_value={"online": True}),
                patch.object(
                    runtime,
                    "_database_counts",
                    return_value={
                        "memories": 0,
                        "web_memories": 0,
                        "pending_reflections": 0,
                    },
                ),
            ):
                self.assertFalse(runtime.status()["vision"]["enabled"])

    def test_model_connection_summary_never_exposes_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))

            connection = runtime.model_connection()
            bootstrap = runtime.bootstrap()

            self.assertTrue(connection["api_key_configured"])
            self.assertTrue(connection["language"]["api_key_configured"])
            self.assertTrue(connection["vision"]["api_key_configured"])
            self.assertNotIn("api_key", connection)
            self.assertNotIn("api_key", connection["language"])
            self.assertNotIn("api_key", connection["vision"])
            self.assertNotIn("test-key", json.dumps(bootstrap))

    def test_public_first_run_does_not_seed_legacy_model_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XIXI_EDITION": "public"}):
                runtime = self.make_runtime(Path(tmp))

            self.assertEqual(runtime.model_providers()["items"], [])
            self.assertTrue(runtime.workspace.model_provider_seed_completed())

    def test_active_provider_restores_missing_primary_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.workspace.save_model_provider({
                "id": "saved-provider",
                "name": "Saved provider",
                "base_url": "https://saved.example/v1",
                "api_type": "openai_chat",
                "enabled": True,
            })
            runtime.workspace.save_model_provider_model({
                "id": "saved-language-model",
                "provider_id": "saved-provider",
                "name": "Saved language model",
                "model_name": "saved-model",
                "capabilities": ["language"],
                "enabled": True,
            })
            runtime.cfg.openai_model = "saved-model"
            runtime.cfg.use_openai = False
            runtime.raw_brain.openai_base_url = "https://saved.example/v1"
            runtime.raw_brain.openai_api_key = ""
            runtime.raw_brain.openai_client = None
            runtime.raw_brain.use_openai = False

            def credential(username: str, fallback: str = "") -> str:
                del fallback
                return "saved-secret" if username == "model_provider:saved-provider" else ""

            with (
                patch.object(runtime, "_read_model_credential", side_effect=credential),
                patch.object(runtime, "_store_model_credential") as store,
            ):
                runtime._restore_active_model_credentials()

            self.assertTrue(runtime.cfg.use_openai)
            self.assertTrue(runtime.raw_brain.use_openai)
            self.assertEqual(runtime.raw_brain.openai_api_key, "saved-secret")
            self.assertEqual(runtime.raw_brain.openai_base_url, "https://saved.example/v1")
            self.assertEqual(runtime.raw_brain.model_api_type, "openai_chat")
            self.assertIsNotNone(runtime.raw_brain.openai_client)
            store.assert_not_called()

    def test_deleting_last_provider_does_not_reseed_legacy_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)
            initial = runtime.model_providers()["items"]
            self.assertTrue(initial)

            first_result = runtime.delete_model_provider(initial[0]["id"])

            self.assertTrue(first_result["deleted"])
            self.assertNotIn(initial[0]["id"], {
                item["id"] for item in first_result["items"]
            })
            for provider in list(first_result["items"]):
                result = runtime.delete_model_provider(provider["id"])

            self.assertTrue(result["deleted"])
            self.assertEqual(result["items"], [])
            self.assertEqual(runtime.model_providers()["items"], [])

            with patch("app.studio.Brain", FakeBrain):
                reloaded = StudioRuntime(self.make_config(root))
            self.assertEqual(reloaded.model_providers()["items"], [])

    def test_deleting_last_model_does_not_reseed_legacy_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            models = [
                model
                for provider in runtime.model_providers()["items"]
                for model in provider["models"]
            ]
            self.assertTrue(models)
            result = {}
            for model in models:
                result = runtime.delete_model_provider_model(model["id"])

            self.assertTrue(result["deleted"])
            self.assertEqual(result["items"], [])
            self.assertEqual(runtime.model_providers()["items"], [])

    def test_failed_model_connection_does_not_replace_live_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            original_model = runtime.cfg.openai_model
            original_key = runtime.raw_brain.openai_api_key

            with patch("app.model_api.httpx.post", side_effect=httpx.TimeoutException("timeout")):
                with self.assertRaisesRegex(RuntimeError, "连接测试超时"):
                    runtime.configure_model_connection({
                        "language": {
                            "base_url": "https://language.example/v1",
                            "api_key": "new-language-secret",
                            "model": "new-model",
                        },
                        "vision": {
                            "base_url": "https://vision.example/v1",
                            "api_key": "new-vision-secret",
                            "model": "new-vision",
                        },
                    })

            self.assertEqual(runtime.cfg.openai_model, original_model)
            self.assertEqual(runtime.raw_brain.openai_api_key, original_key)
            self.assertFalse(runtime.settings_file.exists())

    def test_first_run_model_endpoints_are_applied_independently_and_secured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            original_vision_model = runtime.cfg.vision_model

            def detected(**values: object) -> dict[str, object]:
                capability = str(values["capability"])
                return {
                    "ok": True,
                    "provider": "compatible",
                    "api_type": "openai_chat",
                    "api_label": "OpenAI Chat Completions",
                    "base_url": str(values["base_url"]),
                    "model": str(values["model"]),
                    "capability": capability,
                    "message": "连接正常",
                }

            with (
                patch("app.studio.detect_model_api", side_effect=detected) as detect,
                patch.object(runtime, "_store_model_credential") as store,
                patch.object(runtime, "status", return_value={"model": {"online": True}}),
            ):
                language = runtime.configure_model_endpoint({
                    "target": "language",
                    "provider_name": "语言供应商",
                    "connection": {
                        "base_url": "https://language.example/v1/",
                        "api_key": "language-secret",
                        "model": "language-model",
                    },
                })
                self.assertEqual(runtime.cfg.openai_model, "language-model")
                self.assertEqual(runtime.raw_brain.openai_base_url, "https://language.example/v1")
                self.assertEqual(runtime.raw_brain.openai_api_key, "language-secret")
                self.assertEqual(runtime.cfg.vision_model, original_vision_model)
                self.assertEqual(language["target"], "language")

                vision = runtime.configure_model_endpoint({
                    "target": "vision",
                    "provider_name": "视觉供应商",
                    "connection": {
                        "base_url": "https://vision.example/v1/",
                        "api_key": "vision-secret",
                        "model": "vision-model",
                    },
                })

            self.assertEqual(detect.call_count, 2)
            self.assertEqual(runtime.cfg.openai_model, "language-model")
            self.assertEqual(runtime.cfg.vision_model, "vision-model")
            self.assertEqual(runtime.vision.base_url, "https://vision.example/v1")
            self.assertEqual(runtime.vision.api_key, "vision-secret")
            self.assertEqual(vision["target"], "vision")
            self.assertGreaterEqual(store.call_count, 6)
            providers = runtime.model_providers()["items"]
            capabilities = {
                model["model_name"]: set(model["capabilities"])
                for provider in providers
                for model in provider["models"]
            }
            self.assertEqual(capabilities["language-model"], {"language"})
            self.assertEqual(capabilities["vision-model"], {"vision"})
            persisted = runtime.settings_file.read_text(encoding="utf-8")
            self.assertNotIn("language-secret", persisted)
            self.assertNotIn("vision-secret", persisted)
            self.assertNotIn("api_key", persisted)

    def test_model_connection_is_tested_secured_and_hot_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            response = MagicMock(status_code=200)
            response.json.return_value = {
                "choices": [{"message": {"content": "OK"}}],
                "model": "new-model",
            }
            requests: list[tuple[str, str]] = []

            def post(url: str, **kwargs: object) -> MagicMock:
                headers = kwargs.get("headers")
                assert isinstance(headers, dict)
                requests.append((url, str(headers.get("Authorization") or "")))
                return response

            with (
                patch("app.model_api.httpx.post", side_effect=post),
                patch("app.studio.keyring.get_password", return_value=None),
                patch("app.studio.keyring.set_password") as set_password,
            ):
                result = runtime.configure_model_connection({
                    "language": {
                        "base_url": "https://language.example/v1/",
                        "api_key": "new-language-secret",
                        "model": "new-model",
                    },
                    "vision": {
                        "base_url": "https://vision.example/v1/",
                        "api_key": "new-vision-secret",
                        "model": "new-vision",
                    },
                    "web_search_enabled": False,
                })

            self.assertTrue(result["test"]["ok"])
            self.assertEqual(runtime.cfg.openai_model, "new-model")
            self.assertEqual(runtime.cfg.vision_model, "new-vision")
            self.assertFalse(runtime.cfg.web_search_enabled)
            self.assertEqual(runtime.raw_brain.openai_api_key, "new-language-secret")
            self.assertEqual(runtime.raw_brain.openai_base_url, "https://language.example/v1")
            self.assertEqual(runtime.raw_brain.model_api_type, "openai_chat")
            self.assertIsNotNone(runtime.raw_brain.openai_client)
            self.assertEqual(runtime.vision.api_key, "new-vision-secret")
            self.assertEqual(runtime.vision.base_url, "https://vision.example/v1")
            self.assertEqual(runtime.vision.api_type, "openai_chat")
            self.assertGreaterEqual(set_password.call_count, 4)
            self.assertEqual(
                requests,
                [
                    ("https://language.example/v1/chat/completions", "Bearer new-language-secret"),
                    ("https://vision.example/v1/chat/completions", "Bearer new-vision-secret"),
                ],
            )
            self.assertTrue(result["tests"]["language"]["ok"])
            self.assertTrue(result["tests"]["vision"]["ok"])
            persisted = runtime.settings_file.read_text(encoding="utf-8")
            self.assertNotIn("new-language-secret", persisted)
            self.assertNotIn("new-vision-secret", persisted)
            self.assertNotIn("api_key", persisted)

    def test_voice_control_starts_stops_and_persists_service_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            with (
                patch(
                    "app.studio.start_voice_service",
                    return_value={
                        "online": True,
                        "engine": "GPT-SoVITS",
                        "voice": "XixiVoice",
                    },
                ) as start_service,
                patch(
                    "app.studio.stop_voice_service",
                    return_value={
                        "online": False,
                        "engine": "GPT-SoVITS",
                        "voice": "XixiVoice",
                    },
                ) as stop_service,
                patch("app.studio.prewarm_voice_language") as prewarm,
            ):
                online = runtime.control_voice("online")["voice"]
                self.assertTrue(online["online"])
                self.assertTrue(online["enabled"])
                self.assertTrue(runtime.cfg.voice_enabled)
                start_service.assert_called_once_with()
                prewarm.assert_called_once_with("zh")

                offline = runtime.control_voice("offline")["voice"]
                self.assertFalse(offline["online"])
                self.assertFalse(offline["enabled"])
                self.assertFalse(runtime.cfg.voice_enabled)
                stop_service.assert_called_once_with()

            persisted = json.loads(runtime.settings_file.read_text(encoding="utf-8"))
            self.assertFalse(persisted["voice_enabled"])

    def test_model_control_persists_and_blocks_studio_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))

            offline = runtime.control_model("offline")["model"]

            self.assertFalse(offline["enabled"])
            self.assertFalse(offline["online"])
            with self.assertRaisesRegex(RuntimeError, "大脑功能当前已关闭"):
                runtime.chat({"text": "你好", "images": [], "voice": False})
            self.assertEqual(runtime.raw_brain.calls, [])
            persisted = json.loads(runtime.settings_file.read_text(encoding="utf-8"))
            self.assertFalse(persisted["brain_enabled"])

            online = runtime.control_model("online")["model"]
            self.assertTrue(online["enabled"])
            self.assertTrue(online["online"])

    def test_locked_brain_skips_model_methods_while_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.cfg.brain_enabled = False

            self.assertEqual(runtime.brain.think("不会执行"), "")
            self.assertEqual(runtime.raw_brain.calls, [])

    def test_failed_voice_start_does_not_change_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.cfg.voice_enabled = False

            with patch(
                "app.studio.start_voice_service",
                side_effect=RuntimeError("start failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "start failed"):
                    runtime.control_voice("online")

            self.assertFalse(runtime.cfg.voice_enabled)
            self.assertFalse(runtime.settings_file.exists())

    def test_voice_start_requires_complete_local_voice_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.cfg.voice_enabled = False

            with (
                patch.object(runtime.environment, "_local_voice_ready", return_value=False),
                patch("app.studio.start_voice_service") as start_service,
            ):
                with self.assertRaisesRegex(RuntimeError, "环境配置"):
                    runtime.control_voice("online")

            start_service.assert_not_called()
            self.assertFalse(runtime.cfg.voice_enabled)

    def test_invalid_settings_batch_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            original_chance = runtime.cfg.owner_address_chance

            with self.assertRaises(ValueError):
                runtime.update_settings(
                    {"owner_address_chance": 0.2, "tts_rate": "not-a-rate"}
                )

            self.assertEqual(runtime.cfg.owner_address_chance, original_chance)
            self.assertFalse(runtime.settings_file.exists())

    def test_first_run_settings_reload_with_unconfigured_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)
            runtime.update_settings({
                "brain_enabled": False,
                "voice_enabled": False,
                "vision_enabled": False,
                "learning_enabled": False,
                "openai_model": "",
                "vision_model": "",
                "owner_display_name": "测试用户",
                "owner_relationship": "朋友与搭档",
                "owner_addresses": "朋友,搭档",
                "setup_complete": True,
            })

            with patch("app.studio.Brain", FakeBrain):
                reloaded = StudioRuntime(self.make_config(root))

            self.assertTrue(reloaded.cfg.setup_complete)
            self.assertFalse(reloaded.cfg.brain_enabled)
            self.assertFalse(reloaded.cfg.voice_enabled)
            self.assertFalse(reloaded.cfg.vision_enabled)
            self.assertFalse(reloaded.cfg.learning_enabled)
            self.assertEqual(reloaded.cfg.openai_model, "")
            self.assertEqual(reloaded.cfg.vision_model, "")
            self.assertEqual(reloaded.cfg.owner_display_name, "测试用户")

    def test_qq_offline_preference_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)

            runtime._stop_napcat_account = MagicMock(return_value=True)  # type: ignore[method-assign]
            result = runtime.control_qq("offline")

            self.assertFalse(result["qq"]["enabled"])
            self.assertFalse(runtime.cfg.qq_enabled)
            persisted = json.loads(runtime.settings_file.read_text(encoding="utf-8"))
            self.assertFalse(persisted["qq_enabled"])
            runtime._stop_napcat_account.assert_called_once_with(runtime.cfg.bot_qq_id)
            with patch("app.studio.Brain", FakeBrain):
                reloaded = StudioRuntime(self.make_config(root))
            self.assertFalse(reloaded.cfg.qq_enabled)

    def test_qq_offline_reports_failure_if_dedicated_process_stays_alive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime._stop_napcat_account = MagicMock(return_value=False)  # type: ignore[method-assign]

            with self.assertRaisesRegex(RuntimeError, "没有正常退出"):
                runtime.control_qq("offline")

            self.assertFalse(runtime.cfg.qq_enabled)
            runtime._stop_napcat_account.assert_called_once_with(runtime.cfg.bot_qq_id)

    def test_qq_offline_cleans_registered_account_from_previous_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            managed_file = root / "data" / "qq_managed_accounts.json"
            managed_file.parent.mkdir(parents=True, exist_ok=True)
            managed_file.write_text(
                json.dumps({"accounts": [2113357857]}),
                encoding="utf-8",
            )
            runtime = self.make_runtime(root)
            stopped: list[int] = []

            def stop_account(account: int) -> bool:
                stopped.append(account)
                return True

            runtime._stop_napcat_account = MagicMock(side_effect=stop_account)  # type: ignore[method-assign]
            runtime.control_qq("offline")

            self.assertEqual(set(stopped), {2113357857, runtime.cfg.bot_qq_id})

    def test_qq_offline_cancels_pending_switch_and_cleans_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            launch_started = threading.Event()

            def wait_for_cancel(
                _account: int,
                cancel_event: threading.Event | None = None,
            ) -> dict[str, object]:
                launch_started.set()
                assert cancel_event is not None
                cancel_event.wait(timeout=2)
                raise RuntimeError("cancelled")

            runtime.shutdown_qq = MagicMock()  # type: ignore[method-assign]
            runtime._launch_napcat_account = MagicMock(side_effect=wait_for_cancel)  # type: ignore[method-assign]
            runtime._stop_napcat_account = MagicMock(return_value=True)  # type: ignore[method-assign]
            runtime.switch_qq_account(
                {"bot_qq_id": 2113357857, "owner_qq_id": 1000000001}
            )
            self.assertTrue(launch_started.wait(timeout=1))

            runtime.control_qq("offline")

            self.assertFalse(runtime.cfg.qq_enabled)
            self.assertEqual(runtime._qq_status()["account_state"], "idle")
            stopped = {call.args[0] for call in runtime._stop_napcat_account.call_args_list}
            self.assertIn(2113357857, stopped)
            self.assertIn(runtime.cfg.bot_qq_id, stopped)

    def test_activity_journal_and_memory_management_are_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)
            MemoryStore(runtime.cfg.memory_db)
            now = "2026-08-12T12:00:00+08:00"
            with closing(sqlite3.connect(runtime.cfg.memory_db)) as connection:
                connection.execute(
                    """INSERT INTO memories
                    (scope, category, content, normalized, source_type, source_name,
                     source_url, confidence, importance, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("global", "fact", "旧内容", "旧内容", "test", "", "", 0.5, 4, "active", now, now),
                )
                memory_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
                connection.commit()

            runtime.update_memory(memory_id, {"content": "新内容", "category": "preference", "importance": 8, "confidence": 0.9})
            item = runtime.memories(query="新内容")["items"][0]
            self.assertEqual(item["category"], "preference")
            self.assertEqual(item["importance"], 8)
            self.assertEqual(
                runtime.memories(category="preference")["items"][0]["id"],
                memory_id,
            )
            self.assertIn(
                {"name": "preference", "count": 1},
                runtime.memories()["categories"],
            )
            self.assertTrue(runtime.delete_memory(memory_id)["ok"])
            self.assertEqual(runtime.memories(query="新内容")["items"], [])
            events = runtime.activities(category="memory")["items"]
            self.assertEqual([event["category"] for event in events], ["memory", "memory"])

    def test_importance_ten_memory_must_be_lowered_before_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)
            MemoryStore(runtime.cfg.memory_db)
            now = "2026-08-12T12:00:00+08:00"
            with closing(sqlite3.connect(runtime.cfg.memory_db)) as connection:
                connection.execute(
                    """INSERT INTO memories
                    (scope, category, content, normalized, source_type, source_name,
                     source_url, confidence, importance, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("global", "self_identity", "不可直接删除的重要记忆", "不可直接删除的重要记忆", "test", "", "", 1.0, 10, "active", now, now),
                )
                memory_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
                connection.commit()

            with self.assertRaisesRegex(
                ValueError,
                "此记忆很重要不能直接删除，一定要删除的话请手动降低重要度",
            ):
                runtime.delete_memory(memory_id)
            self.assertEqual(runtime.memories(query="不可直接删除的重要记忆")["items"][0]["importance"], 10)

            runtime.update_memory(memory_id, {
                "content": "不可直接删除的重要记忆",
                "category": "self_identity",
                "importance": 9,
                "confidence": 1.0,
            })
            self.assertTrue(runtime.delete_memory(memory_id)["ok"])

    def test_studio_conversation_history_is_filtered_and_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self.make_runtime(root)
            MemoryStore(runtime.cfg.memory_db)
            now = "2026-08-12T12:00:00+08:00"
            with closing(sqlite3.connect(runtime.cfg.memory_db)) as connection:
                connection.executemany(
                    """
                    INSERT INTO shared_conversation_events
                    (session_id, subject_user_id, role, speaker, content, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ("studio:owner", "1000000001", "user", "cc", "第一条", now),
                        ("studio:owner", "1000000001", "assistant", "昔夕", "第二条", now),
                        ("private:other", "1", "user", "other", "不能看见", now),
                    ),
                )
                connection.commit()

            history = runtime.conversation_history()
            self.assertEqual([item["content"] for item in history["items"]], ["第一条", "第二条"])
            self.assertEqual(runtime.conversation_history(query="第二")["count"], 1)

    def test_clear_chat_history_hides_transcript_but_preserves_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            MemoryStore(runtime.cfg.memory_db)
            runtime.raw_brain.sessions["studio:owner"] = [
                {"role": "user", "content": "请记住这件事"},
                {"role": "assistant", "content": "我记住了"},
            ]
            now = "2026-08-23T22:00:00+08:00"
            with closing(sqlite3.connect(runtime.cfg.memory_db)) as connection:
                connection.executemany(
                    """
                    INSERT INTO shared_conversation_events
                    (session_id, subject_user_id, role, speaker, content, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ("studio:owner", "1000000001", "user", "cc", "旧消息", now),
                        ("studio:owner", "1000000001", "assistant", "昔夕", "旧回复", now),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO memories
                    (scope, category, content, normalized, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("owner", "preference", "爸爸喜欢安静的陪伴", "爸爸喜欢安静的陪伴", now, now),
                )
                connection.commit()

            result = runtime.clear_studio_chat_history()

            self.assertTrue(result["ok"])
            self.assertEqual(runtime.conversation_history()["items"], [])
            self.assertNotIn("studio:owner", runtime.raw_brain.sessions)
            with closing(sqlite3.connect(runtime.cfg.memory_db)) as connection:
                event_count = connection.execute(
                    "SELECT COUNT(*) FROM shared_conversation_events WHERE session_id = 'studio:owner'"
                ).fetchone()[0]
                memory_count = connection.execute(
                    "SELECT COUNT(*) FROM memories WHERE status = 'active'"
                ).fetchone()[0]
                connection.execute(
                    """
                    INSERT INTO shared_conversation_events
                    (session_id, subject_user_id, role, speaker, content, created_at)
                    VALUES ('studio:owner', '1000000001', 'user', 'cc', '新消息', ?)
                    """,
                    (now,),
                )
                connection.commit()

            self.assertEqual(event_count, 2)
            self.assertEqual(memory_count, 1)
            self.assertEqual(
                [item["content"] for item in runtime.conversation_history()["items"]],
                ["新消息"],
            )

    def test_notifications_use_real_activity_without_forcing_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.status = MagicMock(return_value={  # type: ignore[method-assign]
                "qq": {"enabled": False, "online": False},
                "model": {"enabled": True, "online": True},
                "vision": {"enabled": True, "online": True},
                "voice": {"enabled": True, "online": True},
            })
            runtime.activity_journal.append("backup", "备份完成", detail="本地备份")
            runtime.diagnostics._last = {"checked_at": "", "items": []}

            result = runtime.notifications()

            self.assertEqual(result["items"][0]["title"], "备份完成")
            self.assertEqual(runtime.diagnostics._last["checked_at"], "")

    def test_weather_scheduler_lifecycle_is_not_exposed_as_notifications(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.status = MagicMock(return_value={  # type: ignore[method-assign]
                "qq": {"enabled": False, "online": False},
                "model": {"enabled": True, "online": True},
                "vision": {"enabled": True, "online": True},
                "voice": {"enabled": True, "online": True},
            })
            runtime.diagnostics._last = {"checked_at": "", "items": []}
            (runtime.cfg.logs_dir / "app.log").write_text(
                "2026-08-17 00:25:54 [INFO] weather_alerts: "
                "extreme weather alert scheduler started, location=重庆\n"
                "2026-08-17 00:25:54 [INFO] weather_alerts: "
                "extreme weather alert scheduler paused\n",
                encoding="utf-8",
            )

            weather_activities = runtime.activities(category="weather")["items"]
            result = runtime.notifications()

            self.assertEqual(len(weather_activities), 2)
            self.assertTrue(all(
                item["metadata"].get("internal_lifecycle")
                for item in weather_activities
            ))
            self.assertTrue(all("[IN" not in item["created_at"] for item in weather_activities))
            self.assertFalse(any(
                item["title"].startswith("天气提醒")
                for item in result["items"]
            ))

    def test_weather_failure_notification_is_localized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.status = MagicMock(return_value={  # type: ignore[method-assign]
                "qq": {"enabled": False, "online": False},
                "model": {"enabled": True, "online": True},
                "vision": {"enabled": True, "online": True},
                "voice": {"enabled": True, "online": True},
            })
            runtime.diagnostics._last = {"checked_at": "", "items": []}
            (runtime.cfg.logs_dir / "app.log").write_text(
                "2026-08-23 12:54:50 [ERROR] weather_alerts: "
                "extreme weather alert cycle failed: QQ is offline\n",
                encoding="utf-8",
            )

            activity = runtime.activities(category="weather")["items"][0]
            notification = next(
                item for item in runtime.notifications()["items"]
                if item["title"] == "天气提醒"
            )

            expected = "QQ 当前未上线，天气提醒会在 QQ 上线后自动恢复"
            self.assertEqual(activity["detail"], expected)
            self.assertEqual(notification["detail"], expected)
            self.assertNotIn("weather_alerts", notification["detail"])
            self.assertNotIn("offline", notification["detail"].lower())

    def test_weather_status_distinguishes_enabled_from_delivery_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.cfg.weather_enabled = True
            runtime.cfg.weather_alert_enabled = True
            with patch.object(runtime, "_qq_status", return_value={
                "enabled": False,
                "online": False,
            }):
                weather = runtime.status()["weather"]

            self.assertTrue(weather["online"])
            self.assertTrue(weather["alerts_enabled"])
            self.assertFalse(weather["delivery_ready"])

    def test_failed_regeneration_restores_latest_exchange(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            MemoryStore(runtime.cfg.memory_db)
            runtime.raw_brain.sessions["studio:owner"] = [
                {"role": "user", "content": "原问题"},
                {"role": "assistant", "content": "原回答"},
            ]
            runtime.raw_brain._save_sessions()
            now = "2026-08-12T12:00:00+08:00"
            with closing(sqlite3.connect(runtime.cfg.memory_db)) as connection:
                connection.executemany(
                    """
                    INSERT INTO shared_conversation_events
                    (session_id, subject_user_id, role, speaker, content, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ("studio:owner", str(runtime.cfg.qq_user_id), "user", "创造者 cc", "原问题", now),
                        ("studio:owner", str(runtime.cfg.qq_user_id), "assistant", "昔夕", "原回答", now),
                    ),
                )
                connection.commit()
            runtime.brain.think = MagicMock(side_effect=RuntimeError("模型失败"))  # type: ignore[method-assign]

            with self.assertRaisesRegex(RuntimeError, "模型失败"):
                runtime.chat({"text": "原问题", "regenerate": True})

            self.assertEqual(
                runtime.raw_brain.sessions["studio:owner"],
                [
                    {"role": "user", "content": "原问题"},
                    {"role": "assistant", "content": "原回答"},
                ],
            )
            self.assertEqual(
                [item["content"] for item in runtime.conversation_history()["items"]],
                ["原问题", "原回答"],
            )

    def test_backup_excludes_credentials_and_can_restore_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "persona.txt").write_text("原始人格", encoding="utf-8")
            (root / ".env").write_text("OPENAI_API_KEY=secret", encoding="utf-8")
            journal = ActivityJournal(root / "data" / "activities.jsonl")
            manager = BackupManager(root, journal)
            created = manager.create()
            with zipfile.ZipFile(created["path"], "r") as archive:
                self.assertIn("persona.txt", archive.namelist())
                self.assertNotIn(".env", archive.namelist())
            (root / "persona.txt").write_text("已修改", encoding="utf-8")
            restored = manager.restore(created["name"])
            self.assertIn("persona.txt", restored["restored_files"])
            self.assertEqual((root / "persona.txt").read_text(encoding="utf-8"), "原始人格")

    def test_backup_import_validates_zip_paths_credentials_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "persona.txt").write_text("人格", encoding="utf-8")
            manager = BackupManager(root, ActivityJournal(root / "data" / "activities.jsonl"))
            created = manager.create()

            imported = manager.import_bytes(Path(created["path"]).read_bytes(), "另一台电脑.zip")
            self.assertTrue(Path(imported["path"]).is_file())
            self.assertEqual(imported["original_name"], "另一台电脑.zip")

            for member in ("../escape.txt", "data/api_key.txt"):
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w") as archive:
                    archive.writestr("manifest.json", json.dumps({"format": 2}))
                    archive.writestr(member, "bad")
                with self.subTest(member=member), self.assertRaises(ValueError):
                    manager.import_bytes(stream.getvalue(), "unsafe.zip")
            with self.assertRaisesRegex(ValueError, "有效 ZIP"):
                manager.import_bytes(b"not-a-zip", "broken.zip")

    def test_restore_backup_rebinds_workspace_and_migrations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            goal = runtime.workspace.create_goal("保留在备份里的目标")
            backup = runtime.backups.create()
            runtime.workspace.update_goal(goal["id"], "completed")

            result = runtime.restore_backup(backup["name"])

            self.assertTrue(result["migrations"]["up_to_date"])
            self.assertIs(runtime.workspace, runtime.raw_brain.workspace)
            self.assertEqual(runtime.workspace.goals()[0]["status"], "active")

    def test_diagnostic_center_run_reports_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_db = root / "memory.db"
            with closing(sqlite3.connect(memory_db)) as connection:
                connection.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY)")
            status = {
                "model": {"online": True, "enabled": True, "name": "test", "provider": "local"},
                "qq": {"online": True, "enabled": True},
                "voice": {"online": False, "enabled": False, "engine": "GPT-SoVITS"},
                "vision": {"online": True, "enabled": True, "model": "test-vision"},
            }
            diagnostics = DiagnosticCenter(root, memory_db, lambda: status, MagicMock())

            result = diagnostics.run()

            self.assertGreaterEqual(result["duration_ms"], 0)
            self.assertEqual(result["summary"], {"ok": 5, "attention": 0, "paused": 1})
            self.assertEqual(len(result["items"]), 6)


    def test_game_control_discards_legacy_input_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings = data_dir / "game_settings.json"
            settings.write_text(json.dumps({
                "mode": "auto",
                "allowed_keys": ["space", "numpad1"],
                "coop_p2_enabled": True,
                "player_learning_enabled": True,
                "hwnd": 12345,
                "observation_interval_s": 3,
                "vision_model": "legacy-game-vision",
                "companion_enabled": True,
            }), encoding="utf-8")

            game = GameControl(data_dir, MagicMock())
            status = game.status()
            saved = json.loads(settings.read_text(encoding="utf-8"))

            self.assertEqual(status["mode"], "observe")
            self.assertFalse(status["input"]["enabled"])
            self.assertFalse(hasattr(game, "press"))
            self.assertFalse(hasattr(game, "focus"))
            self.assertNotIn("allowed_keys", saved)
            self.assertNotIn("coop_p2_enabled", saved)
            self.assertNotIn("player_learning_enabled", saved)
            self.assertNotIn("hwnd", saved)
            self.assertNotIn("vision_model", saved)

    def test_game_control_only_journals_real_session_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = MagicMock()
            game = GameControl(Path(tmp), journal)

            game.stop()
            journal.append.assert_not_called()

            with patch.object(game, "_screen_region", return_value={
                "left": 0,
                "top": 0,
                "width": 1920,
                "height": 1080,
            }):
                game.start()
                game.start()
            game.stop()
            game.stop()

            self.assertEqual(journal.append.call_count, 2)
            self.assertEqual(journal.append.call_args_list[0].args[1], "游戏观察会话已开始")
            self.assertEqual(journal.append.call_args_list[1].args[1], "游戏观察会话已停止")

    def test_game_control_prunes_stale_and_excess_capture_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            capture_dir = data_dir / "game_captures"
            capture_dir.mkdir()
            (capture_dir / "annotated-live-0.jpg").write_bytes(b"legacy")
            (capture_dir / "screen-0.jpg").write_bytes(b"current")
            for index in range(12):
                capture = capture_dir / f"capture-{index:02d}.png"
                capture.write_bytes(str(index).encode("ascii"))
                capture.touch()
                time.sleep(0.002)

            GameControl(data_dir, MagicMock())

            self.assertFalse((capture_dir / "annotated-live-0.jpg").exists())
            self.assertTrue((capture_dir / "screen-0.jpg").exists())
            self.assertEqual(len(list(capture_dir.glob("capture-*.png"))), 10)
            self.assertFalse((capture_dir / "capture-00.png").exists())
            self.assertFalse((capture_dir / "capture-01.png").exists())

    def test_runtime_status_includes_game_overview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.games.status = MagicMock(return_value={  # type: ignore[method-assign]
                "active": False,
                "mode": "observe",
                "window_title": "",
            })

            self.assertEqual(runtime.status()["game"]["mode"], "observe")

    def test_game_loop_skips_unchanged_frames_and_tracks_perception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            capture = runtime.root / "data" / "game_captures" / "frame.png"
            capture.parent.mkdir(parents=True, exist_ok=True)
            capture.write_bytes(b"frame")
            runtime.games.status = MagicMock(return_value={  # type: ignore[method-assign]
                "active": True,
                "mode": "observe",
                "change_threshold": 0.025,
                "max_idle_cycles": 4,
                "observation_interval_s": 2,
            })
            runtime.games.capture = MagicMock(return_value={  # type: ignore[method-assign]
                "path": str(capture), "url": "/api/game/capture/frame.png"
            })
            runtime._game_frame_change_ratio = MagicMock(return_value=0.001)  # type: ignore[method-assign]
            runtime.vision.analyze_bytes = AsyncMock(return_value="不应调用")  # type: ignore[method-assign]
            runtime._maybe_schedule_game_companion = MagicMock()  # type: ignore[method-assign]

            observation = runtime._game_cycle()
            status = runtime.game_status()

            self.assertTrue(observation["skipped"])
            self.assertEqual(observation["state"], "watching")
            self.assertEqual(status["perception"]["skipped_frames"], 1)
            self.assertEqual(status["perception"]["analyzed_frames"], 0)
            runtime.vision.analyze_bytes.assert_not_awaited()
            runtime._maybe_schedule_game_companion.assert_not_called()

    def test_game_assist_mode_uses_universal_temporal_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            capture = runtime.root / "data" / "game_captures" / "current-frame.png"
            capture.parent.mkdir(parents=True, exist_ok=True)
            capture.write_bytes(b"current-frame")
            runtime.games.status = MagicMock(return_value={  # type: ignore[method-assign]
                "active": True,
                "mode": "observe",
                "hwnd": 321,
                "window_title": "Slay the Spire",
                "change_threshold": 0.025,
                "max_idle_cycles": 4,
                "observation_interval_s": 2,
            })
            runtime.games.capture = MagicMock(return_value={  # type: ignore[method-assign]
                "path": str(capture), "url": "/api/game/capture/current-frame.png"
            })
            runtime._game_frame_change_ratio = MagicMock(return_value=1.0)  # type: ignore[method-assign]
            runtime._game_context_hwnd = 321
            runtime._game_recent_frames = [b"previous-frame"]
            runtime._game_observation["analysis"] = "上一轮牌组资源偏少"
            runtime.vision.analyze_bytes = AsyncMock(return_value="先防守，再根据抽牌决定。")  # type: ignore[method-assign]

            observation = runtime._game_cycle()

            images, prompt = runtime.vision.analyze_bytes.await_args.args
            self.assertEqual(images, [b"previous-frame", b"current-frame"])
            self.assertIn("Slay the Spire", prompt)
            self.assertIn("不要预设这是2D游戏", prompt)
            self.assertIn("回合制、策略和卡牌", prompt)
            self.assertIn("上一轮牌组资源偏少", prompt)
            self.assertEqual(observation["context_frames"], 2)
            self.assertEqual(observation["game_title"], "Slay the Spire")
            self.assertEqual(runtime._game_recent_frames, [b"current-frame"])
            self.assertNotIn("model_override", runtime.vision.analyze_bytes.await_args.kwargs)

    def test_manual_game_analysis_returns_json_safe_capture_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.games.status = MagicMock(return_value={  # type: ignore[method-assign]
                "active": False,
                "mode": "observe",
                "hwnd": 0,
                "window_title": "整个屏幕（自动）",
            })
            runtime._capture_game_snapshot = MagicMock(return_value={  # type: ignore[method-assign]
                "data": b"raw-image-data",
                "path": "D:/captures/current.png",
                "url": "/api/game/capture/current.png",
                "width": 1280,
                "height": 720,
                "captured_at": time.time(),
            })
            runtime.vision.analyze_bytes = AsyncMock(return_value="已经看到了当前画面。")  # type: ignore[method-assign]

            result = runtime.analyze_game({})

            self.assertNotIn("data", result["capture"])
            self.assertEqual(result["capture"]["url"], "/api/game/capture/current.png")
            json.dumps(result, ensure_ascii=False)

    def test_game_loop_discards_slow_analysis_after_scene_changes(self) -> None:
        from io import BytesIO
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            previous = BytesIO()
            current = BytesIO()
            Image.new("RGB", (640, 360), (20, 20, 20)).save(previous, format="JPEG")
            Image.new("RGB", (640, 360), (235, 235, 235)).save(current, format="JPEG")
            runtime.games.status = MagicMock(return_value={  # type: ignore[method-assign]
                "active": True,
                "mode": "observe",
                "hwnd": 0,
                "window_title": "快速变化的游戏",
                "change_threshold": 0.025,
                "max_idle_cycles": 4,
                "observation_interval_s": 9,
                "companion_enabled": True,
            })
            perception = MagicMock()
            perception.running = True
            perception.snapshot.side_effect = [
                {
                    "data": previous.getvalue(),
                    "url": "/api/game/capture/old.jpg",
                    "frame_id": 10,
                    "captured_at": time.time(),
                    "change_ratio": 1.0,
                    "adapter": {},
                },
                {
                    "data": current.getvalue(),
                    "url": "",
                    "frame_id": 40,
                    "captured_at": time.time(),
                    "change_ratio": 1.0,
                    "adapter": {},
                },
            ]
            runtime.game_runtime.perception = perception
            runtime.vision.analyze_bytes = AsyncMock(return_value="旧画面中的角色正在战斗")  # type: ignore[method-assign]
            runtime._maybe_schedule_game_companion = MagicMock()  # type: ignore[method-assign]

            with patch("app.studio._GAME_ANALYSIS_COMPARE_AFTER_S", 0.0):
                observation = runtime._game_cycle()

            self.assertTrue(observation["stale_result"])
            self.assertEqual(observation["stale_reason"], "scene_changed")
            self.assertEqual(runtime._game_stale_analyses, 1)
            self.assertEqual(runtime._game_analyzed_frames, 0)
            runtime._maybe_schedule_game_companion.assert_not_called()

    def test_game_assist_context_resets_when_window_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime._game_context_hwnd = 111
            runtime._game_recent_frames = [b"old-game-frame"]
            runtime._game_observation["analysis"] = "旧游戏的判断"

            images, previous = runtime._game_assist_context(
                {"hwnd": 222, "window_title": "Another Game"},
                b"new-game-frame",
            )

            self.assertEqual(images, [b"new-game-frame"])
            self.assertEqual(previous, "")
            self.assertEqual(runtime._game_context_hwnd, 222)

    def test_game_vision_image_is_downscaled_without_changing_capture(self) -> None:
        from io import BytesIO
        from PIL import Image

        source = BytesIO()
        Image.new("RGB", (2560, 1368), (38, 52, 58)).save(source, format="PNG")

        prepared = StudioRuntime._prepare_game_vision_image(source.getvalue())

        self.assertTrue(prepared.startswith(b"\xff\xd8\xff"))
        with Image.open(BytesIO(prepared)) as image:
            self.assertLessEqual(image.width, 1024)
            self.assertLessEqual(image.height, 640)
            self.assertEqual(image.mode, "RGB")







    def test_game_loop_always_stops_runtime_when_session_ends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.games.status = MagicMock(return_value={"active": False})  # type: ignore[method-assign]
            runtime.game_runtime.stop = MagicMock()  # type: ignore[method-assign]

            runtime._run_game_loop()

            runtime.game_runtime.stop.assert_called_once_with()

    def test_game_loop_stops_closed_window_session_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.games.status = MagicMock(return_value={  # type: ignore[method-assign]
                "active": True,
                "mode": "observe",
                "observation_interval_s": 1.0,
            })
            runtime.games.stop = MagicMock(return_value={"active": False})  # type: ignore[method-assign]
            runtime._game_cycle = MagicMock(  # type: ignore[method-assign]
                side_effect=ValueError("选择的游戏窗口已经关闭")
            )
            runtime.game_runtime.stop = MagicMock()  # type: ignore[method-assign]

            runtime._run_game_loop()

            runtime.games.stop.assert_called_once_with()
            runtime.game_runtime.stop.assert_called_once_with()

    def test_game_companion_generates_event_without_chat_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.raw_brain._request_language_candidate = MagicMock(  # type: ignore[method-assign]
                return_value='{"speak":true,"text":"这波不错，继续稳住。"}'
            )
            runtime.games.status = MagicMock(return_value={"active": True})  # type: ignore[method-assign]

            runtime._generate_game_companion_event(
                0,
                {
                    "active": True,
                    "mode": "observe",
                    "window_title": "测试游戏",
                },
                {"analysis": "角色已经接近终点", "state": "watching"},
            )

            self.assertEqual(len(runtime._game_companion_events), 1)
            self.assertEqual(runtime._game_companion_events[0]["text"], "这波不错，继续稳住。")
            self.assertEqual(runtime._game_companion_events[0]["session_generation"], 0)
            self.assertGreater(
                runtime._game_companion_events[0]["expires_at_epoch"],
                runtime._game_companion_events[0]["created_at_epoch"],
            )
            runtime.raw_brain._request_language_candidate.assert_called_once()
            candidate = runtime.raw_brain._request_language_candidate.call_args.args[0]
            self.assertEqual(candidate["model_name"], runtime.cfg.openai_model)

    def test_game_companion_uses_direct_vision_reaction_without_second_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.games.status = MagicMock(return_value={"active": True})  # type: ignore[method-assign]
            runtime.raw_brain._request_language_candidate = MagicMock()  # type: ignore[method-assign]
            runtime._game_companion_last_started = time.monotonic() - 30
            runtime._game_companion_next_at = 0.0

            runtime._maybe_schedule_game_companion(
                {
                    "analysis": "首领刚刚进入第二阶段",
                    "reaction": "好，第二阶段来了，稳住别急。",
                    "captured_at_epoch": time.time(),
                    "skipped": False,
                    "stale_result": False,
                    "speak_priority": 3,
                },
                {
                    "active": True,
                    "companion_enabled": True,
                    "companion_interval_s": 12,
                },
            )

            self.assertEqual(runtime._game_companion_events[0]["text"], "好，第二阶段来了，稳住别急。")
            runtime.raw_brain._request_language_candidate.assert_not_called()

    def test_game_companion_allows_same_scene_again_after_repeat_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.games.status = MagicMock(return_value={"active": True})  # type: ignore[method-assign]
            observation = {
                "analysis": "角色正在持续挑战首领",
                "captured_at_epoch": time.time(),
            }

            self.assertTrue(runtime._publish_game_companion_event(0, {}, observation, "这一段压迫感还挺强的。"))
            self.assertFalse(runtime._publish_game_companion_event(0, {}, observation, "先稳住，别被它带乱节奏。"))
            runtime._game_companion_last_scene_at -= 25
            self.assertTrue(runtime._publish_game_companion_event(0, {}, observation, "先稳住，别被它带乱节奏。"))

    def test_game_companion_discards_superseded_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.raw_brain._request_language_candidate = MagicMock(  # type: ignore[method-assign]
                return_value='{"speak":true,"text":"刚才那一幕还挺险的。"}'
            )
            runtime.games.status = MagicMock(return_value={"active": True})  # type: ignore[method-assign]
            runtime._game_companion_generation = 4
            runtime._game_observation = {"sequence": 12, "analysis": "现在已经进入新场景"}

            runtime._generate_game_companion_event(
                4,
                {"active": True, "window_title": "测试游戏"},
                {
                    "analysis": "旧场景里角色正在结算",
                    "state": "watching",
                    "sequence": 11,
                    "captured_at_epoch": time.time(),
                },
            )

            self.assertEqual(runtime._game_companion_events, [])

    def test_game_status_expires_old_companion_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.games.status = MagicMock(return_value={  # type: ignore[method-assign]
                "active": True,
                "mode": "observe",
                "window_title": "测试游戏",
            })
            runtime._game_observation = {
                "analysis": "很久之前的画面",
                "captured_at_epoch": time.time() - 60,
                "state": "watching",
            }
            runtime._game_companion_events = [{
                "id": "expired",
                "text": "过期话题",
                "expires_at_epoch": time.time() - 1,
            }]

            status = runtime.game_status()

            self.assertFalse(status["latest"]["analysis_fresh"])
            self.assertEqual(status["companion_events"], [])

    def test_game_companion_rejects_internal_markers_and_unstructured_text(self) -> None:
        self.assertEqual(
            StudioRuntime._clean_game_companion_text(
                '{"speak":true,"text":"右边那家伙过来了，小心点。"}'
            ),
            "右边那家伙过来了，小心点。",
        )
        blocked = (
            "我先确认当前画面和输入状态，再接着走一步。SKIP",
            '{"speak":true,"text":"我先盯一眼画面状态，再决定动不动。"}',
            '{"speak":true,"text":"先往右挪一点。d"}',
            '{"speak":false,"text":""}',
            "这句没有结构化包装",
        )
        for value in blocked:
            with self.subTest(value=value):
                self.assertEqual(StudioRuntime._clean_game_companion_text(value), "")

    def test_game_vision_result_builds_structured_short_term_state(self) -> None:
        parsed = StudioRuntime._parse_game_vision_result(
            '{"phase":"combat","summary":"角色正在和首领战斗。",'
            '"event":"首领进入第二阶段。","intensity":0.9,'
            '"novelty":0.8,"confidence":0.92,"speak_priority":3,'
            '"reaction":"第二阶段来了，这下得认真一点。"}'
        )

        self.assertTrue(parsed["structured"])
        self.assertEqual(parsed["phase"], "combat")
        self.assertIn("首领进入第二阶段", parsed["analysis"])
        self.assertEqual(parsed["speak_priority"], 3)
        self.assertEqual(parsed["intensity"], 0.9)
        self.assertEqual(parsed["reaction"], "第二阶段来了，这下得认真一点。")

    def test_game_vision_result_keeps_plain_provider_fallback(self) -> None:
        parsed = StudioRuntime._parse_game_vision_result("当前正在结算，角色获得了奖励。")

        self.assertFalse(parsed["structured"])
        self.assertEqual(parsed["phase"], "other")
        self.assertEqual(parsed["speak_priority"], 1)
        self.assertIn("获得了奖励", parsed["analysis"])

    def test_game_companion_scheduler_ignores_low_priority_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime._game_companion_thread = None

            runtime._maybe_schedule_game_companion(
                {
                    "analysis": "画面没有明显变化",
                    "captured_at_epoch": time.time(),
                    "skipped": False,
                    "stale_result": False,
                    "speak_priority": 0,
                },
                {"companion_enabled": True},
            )

            self.assertIsNone(runtime._game_companion_thread)


    def test_all_frontend_api_routes_are_wired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime._napcat_status = MagicMock(  # type: ignore[method-assign]
                return_value={"online": False, "user_id": None, "nickname": ""}
            )
            runtime._voice_status = MagicMock(  # type: ignore[method-assign]
                return_value={"online": True, "engine": "test", "voice": "test"}
            )
            runtime._database_counts = MagicMock(  # type: ignore[method-assign]
                return_value={
                    "memories": 0,
                    "web_memories": 0,
                    "pending_reflections": 0,
                }
            )
            runtime.memories = MagicMock(return_value={"items": []})  # type: ignore[method-assign]
            runtime.conversation_history = MagicMock(return_value={"items": [], "count": 0})  # type: ignore[method-assign]
            runtime.clear_studio_chat_history = MagicMock(  # type: ignore[method-assign]
                return_value={"ok": True, "cleared": True, "preserved_memories": True}
            )
            runtime.notifications = MagicMock(return_value={"items": []})  # type: ignore[method-assign]
            runtime.conversation_contexts = MagicMock(return_value={"items": []})  # type: ignore[method-assign]
            runtime.chat = MagicMock(  # type: ignore[method-assign]
                return_value={"reply": "ok", "audio_url": ""}
            )
            runtime.chat_plan = MagicMock(  # type: ignore[method-assign]
                return_value={"vision": False, "web_search": False, "voice": False}
            )
            runtime.transcribe = MagicMock(return_value={"text": "ok"})  # type: ignore[method-assign]
            runtime.render_voice = MagicMock(  # type: ignore[method-assign]
                return_value={"audio_url": "/api/audio/test.mp3", "language": "zh"}
            )
            runtime.prewarm_voice = MagicMock(  # type: ignore[method-assign]
                return_value={"prewarm": {"state": "warming", "language": "zh", "error": ""}}
            )
            runtime.control_qq = MagicMock(  # type: ignore[method-assign]
                return_value={"qq": {"online": False}}
            )
            runtime.refresh_qq_qrcode = MagicMock(  # type: ignore[method-assign]
                return_value={"qq": {"online": False, "account_state": "waiting_login"}}
            )
            runtime.save_qq_identity = MagicMock(  # type: ignore[method-assign]
                return_value={"qq_identity": {"bot_qq_id": "12345678"}, "qq": {"online": False}}
            )
            runtime.switch_qq_account = MagicMock(  # type: ignore[method-assign]
                return_value={"qq_identity": {"bot_qq_id": "12345678"}, "qq": {"online": True}}
            )
            runtime.control_voice = MagicMock(  # type: ignore[method-assign]
                return_value={"voice": {"online": True}}
            )
            runtime.test_model_connection = MagicMock(  # type: ignore[method-assign]
                return_value={"ok": True, "message": "连接正常"}
            )
            runtime.configure_model_connection = MagicMock(  # type: ignore[method-assign]
                return_value={"connection": {}, "settings": {}, "test": {"ok": True}, "status": {}}
            )
            runtime.configure_model_endpoint = MagicMock(  # type: ignore[method-assign]
                return_value={"ok": True, "target": "language"}
            )
            runtime.generate_growth_reflection = MagicMock(  # type: ignore[method-assign]
                return_value={"period_type": "daily", "content": "今天的想法"}
            )
            runtime.growth_reflections = MagicMock(  # type: ignore[method-assign]
                return_value={"items": []}
            )
            runtime.repair_dependency = MagicMock(  # type: ignore[method-assign]
                return_value={"key": "images", "state": "installing"}
            )
            runtime.environment_status = MagicMock(  # type: ignore[method-assign]
                return_value={"items": [], "ready_count": 0, "updated_at": ""}
            )
            runtime.environment_jobs = MagicMock(  # type: ignore[method-assign]
                return_value={"jobs": {"local_vision": {"state": "paused"}}, "updated_at": ""}
            )
            runtime.install_environment = MagicMock(  # type: ignore[method-assign]
                return_value={"key": "local_vision", "state": "installing"}
            )
            runtime.control_environment_install = MagicMock(  # type: ignore[method-assign]
                return_value={"key": "local_vision", "state": "paused"}
            )
            server = StudioServer(("127.0.0.1", 0), runtime)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def request_json(
                path: str,
                *,
                method: str = "GET",
                payload: object | None = None,
            ) -> object:
                data = None if payload is None else json.dumps(payload).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}{path}",
                    data=data,
                    method=method,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=3) as response:
                    return json.load(response)

            try:
                for path in (
                    "/api/health",
                    "/api/bootstrap",
                    "/api/status",
                    "/api/advanced",
                    "/api/persona",
                    "/api/interests",
                    "/api/memories?query=&scope=&limit=100",
                    "/api/chat/history?query=&limit=120",
                    "/api/notifications?limit=40",
                    "/api/logs?lines=240",
                    "/api/activities?limit=20",
                    "/api/contexts?limit=20",
                    "/api/agent/dashboard",
                    "/api/context/usage",
                    "/api/growth/reflections?start=2026-08-01&end=2026-09-01&limit=62",
                    "/api/model/profiles",
                    "/api/model/usage?days=30",
                    "/api/dependencies",
                    "/api/environment",
                    "/api/environment/jobs",
                    "/api/migrations/status",
                    "/api/privacy",
                    "/api/backups",
                    "/api/game/status",
                ):
                    self.assertIsNotNone(request_json(path), path)
                runtime.growth_reflections.assert_called_once_with(
                    62,
                    start_date="2026-08-01",
                    end_date="2026-09-01",
                )
                self.assertEqual(
                    request_json("/api/chat", method="POST", payload={"text": "hi"}),
                    {"reply": "ok", "audio_url": ""},
                )
                self.assertEqual(
                    request_json("/api/chat/history", method="DELETE"),
                    {"ok": True, "cleared": True, "preserved_memories": True},
                )
                runtime.clear_studio_chat_history.assert_called_once_with()
                self.assertEqual(
                    request_json("/api/chat/plan", method="POST", payload={"text": "hi"}),
                    {"vision": False, "web_search": False, "voice": False},
                )
                self.assertEqual(
                    request_json(
                        "/api/transcribe",
                        method="POST",
                        payload={"audio": "data:audio/wav;base64,AA=="},
                    ),
                    {"text": "ok"},
                )
                self.assertEqual(
                    request_json(
                        "/api/voice/render",
                        method="POST",
                        payload={"text": "你好", "language": "zh"},
                    ),
                    {"audio_url": "/api/audio/test.mp3", "language": "zh"},
                )
                with self.assertRaises(urllib.error.HTTPError) as stream_error:
                    request_json("/api/voice/stream?text=hello&language=zh")
                self.assertEqual(stream_error.exception.code, 404)
                self.assertEqual(
                    json.loads(stream_error.exception.read().decode("utf-8")),
                    {"error": "流式语音接口已停用，请使用完整音频接口"},
                )
                stream_error.exception.close()
                self.assertEqual(
                    request_json(
                        "/api/voice/prewarm",
                        method="POST",
                        payload={"language": "zh"},
                    ),
                    {"prewarm": {"state": "warming", "language": "zh", "error": ""}},
                )
                self.assertEqual(
                    request_json(
                        "/api/qq/control",
                        method="POST",
                        payload={"action": "offline"},
                    ),
                    {"qq": {"online": False}},
                )
                self.assertEqual(
                    request_json(
                        "/api/qq/qrcode/refresh",
                        method="POST",
                        payload={},
                    )["qq"]["account_state"],
                    "waiting_login",
                )
                self.assertEqual(
                    request_json(
                        "/api/qq/identity",
                        method="PUT",
                        payload={"bot_qq_id": "12345678", "owner_qq_id": "87654321"},
                    )["qq_identity"]["bot_qq_id"],
                    "12345678",
                )
                self.assertTrue(
                    request_json(
                        "/api/qq/account/switch",
                        method="POST",
                        payload={"bot_qq_id": "12345678", "owner_qq_id": "87654321"},
                    )["qq"]["online"]
                )
                self.assertEqual(
                    request_json(
                        "/api/voice/control",
                        method="POST",
                        payload={"action": "online"},
                    ),
                    {"voice": {"online": True}},
                )
                model_result = request_json(
                    "/api/model/control",
                    method="POST",
                    payload={"action": "offline"},
                )
                self.assertFalse(model_result["model"]["enabled"])
                self.assertEqual(
                    request_json(
                        "/api/model/connection/test",
                        method="POST",
                        payload={"provider": "compatible"},
                    ),
                    {"ok": True, "message": "连接正常"},
                )
                self.assertEqual(
                    request_json(
                        "/api/model/connection/apply",
                        method="POST",
                        payload={"target": "language", "connection": {}},
                    ),
                    {"ok": True, "target": "language"},
                )
                configured = request_json(
                    "/api/model/connection",
                    method="PUT",
                    payload={"provider": "compatible"},
                )
                self.assertTrue(configured["test"]["ok"])
                goal = request_json(
                    "/api/agent/goals",
                    method="POST",
                    payload={"title": "继续完成测试目标"},
                )
                self.assertEqual(
                    request_json(
                        f"/api/agent/goals/{goal['id']}",
                        method="PUT",
                        payload={"status": "completed"},
                    )["status"],
                    "completed",
                )
                pending_id = runtime.workspace.capture_pending_thread(
                    session_id="studio:owner",
                    user_id=str(runtime.cfg.qq_user_id),
                    content="下次继续处理这个话题",
                )
                self.assertEqual(
                    request_json(
                        f"/api/agent/threads/{pending_id}",
                        method="PUT",
                        payload={"status": "completed"},
                    )["status"],
                    "completed",
                )
                policy = request_json(
                    "/api/agent/policy",
                    method="PUT",
                    payload={"daily_action_limit": 7},
                )
                self.assertEqual(policy["daily_action_limit"], 7)
                self.assertEqual(
                    request_json(
                        "/api/growth/reflections/generate",
                        method="POST",
                        payload={"period_type": "daily"},
                    )["content"],
                    "今天的想法",
                )
                profile = request_json(
                    "/api/model/profiles",
                    method="POST",
                    payload={
                        "name": "备用模型",
                        "capability": "language",
                        "base_url": "http://127.0.0.1:11434/v1",
                        "model_name": "qwen3:8b",
                        "api_type": "ollama",
                        "use_primary_key": True,
                    },
                )
                self.assertTrue(
                    request_json(
                        f"/api/model/profiles/{profile['id']}",
                        method="DELETE",
                    )["deleted"]
                )
                self.assertEqual(
                    request_json(
                        "/api/dependencies/repair",
                        method="POST",
                        payload={"key": "images"},
                    )["state"],
                    "installing",
                )
                self.assertEqual(
                    request_json(
                        "/api/environment/install",
                        method="POST",
                        payload={"key": "local_vision"},
                    )["state"],
                    "installing",
                )
                self.assertEqual(
                    request_json(
                        "/api/environment/pause",
                        method="POST",
                        payload={"key": "local_vision"},
                    )["state"],
                    "paused",
                )
                runtime.control_environment_install.assert_called_once_with("local_vision", "pause")
                self.assertTrue(
                    request_json(
                        "/api/privacy", method="POST", payload={"paused": True}
                    )["paused"]
                )
                backup = runtime.backups.create()
                encoded_backup = base64.b64encode(Path(backup["path"]).read_bytes()).decode("ascii")
                imported = request_json(
                    "/api/backups/import",
                    method="POST",
                    payload={"filename": "migrated.zip", "data": encoded_backup},
                )
                self.assertTrue(imported["name"].startswith("xixi-backup-imported-"))
                persona = runtime.get_persona()["content"]
                interests = runtime.interests()
                saved_persona = request_json(
                    "/api/persona", method="PUT", payload={"content": persona}
                )
                self.assertEqual(saved_persona["content"].strip(), persona.strip())
                self.assertEqual(
                    request_json("/api/interests", method="PUT", payload=interests),
                    interests,
                )
                self.assertEqual(
                    request_json(
                        "/api/settings",
                        method="PUT",
                        payload={"owner_address_chance": 0.4},
                    ),
                    {"owner_address_chance": 0.4},
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_frontend_voice_calls_only_use_complete_audio(self) -> None:
        source = (Path(__file__).parents[1] / "studio" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("/api/voice/stream", source)
        self.assertIn('quality: "complete"', source)
        self.assertGreaterEqual(source.count('call_mode: true'), 2)
        self.assertIn('language: "zh", call_mode: true, context: voiceRecognitionContext()', source)
        self.assertNotIn('JSON.stringify({ audio, language: selectedLanguage })', source)

    def test_frontend_message_voice_controls_are_attached_to_assistant_replies(self) -> None:
        root = Path(__file__).parents[1] / "studio"
        index = (root / "index.html").read_text(encoding="utf-8")
        source = (root / "app.js").read_text(encoding="utf-8")
        styles = (root / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="voice-reply"', index)
        self.assertNotIn("composer-voice-language", index)
        self.assertNotIn('id="inspector-voice-reply"', index)
        self.assertIn('id="clear-chat-history"', index)
        self.assertIn('data-lucide="brush"', index)
        self.assertIn('api("/api/chat/history", { method: "DELETE"', source)
        self.assertIn('message?.dataset.role !== "assistant"', source)
        self.assertIn('speak.dataset.messageAction = "speak"', source)
        self.assertIn('languageButton.dataset.messageAction = "voice-language"', source)
        self.assertIn('body: JSON.stringify({ text, language, quality: "complete" })', source)
        self.assertGreaterEqual(source.count('body: JSON.stringify({ text, images, voice: false })'), 1)
        self.assertIn("message-voice-tools", styles)
        self.assertIn("message-voice-language", styles)

    def test_frontend_memory_delete_and_current_napcat_guide_are_wired(self) -> None:
        root = Path(__file__).parents[1] / "studio"
        index = (root / "index.html").read_text(encoding="utf-8")
        source = (root / "app.js").read_text(encoding="utf-8")
        styles = (root / "styles.css").read_text(encoding="utf-8")

        self.assertIn("打开环境配置", index)
        self.assertNotIn("查看安装说明", index)
        self.assertIn('showTuningPanel("environment")', source)
        self.assertNotIn("https://napneko.github.io/guide/boot/Shell", source)
        self.assertIn("remove.dataset.memoryDeleteId = item.id", source)
        self.assertIn('data-lucide="trash-2"', source)
        self.assertIn('title: "删除这条记忆？"', source)
        self.assertIn('api(`/api/memories/${id}`, { method: "DELETE" })', source)
        self.assertIn('id="memory-shelves"', index)
        self.assertIn('id="memory-book-grid"', index)
        self.assertIn('id="memory-reading-desk"', index)
        self.assertIn("memoryCollectionCatalog", source)
        self.assertIn("memory-book-spine", styles)
        self.assertIn("memory-book-card", styles)
        self.assertIn("table-action-danger", styles)
        self.assertIn("table-action-protected", styles)
        self.assertIn("lock-keyhole", source)
        self.assertIn("此记忆很重要不能直接删除，一定要删除的话请手动降低重要度", source)

    def test_frontend_qq_group_wake_settings_are_wired(self) -> None:
        root = Path(__file__).parents[1] / "studio"
        index = (root / "index.html").read_text(encoding="utf-8")

        identity_position = index.index("QQ 身份")
        wake_position = index.index("群聊唤醒")
        weather_position = index.index("天气与提醒")
        self.assertLess(identity_position, wake_position)
        self.assertLess(wake_position, weather_position)
        self.assertIn('data-setting="qq_group_at_wake_enabled"', index)
        self.assertIn('data-setting="qq_group_name_wake_enabled"', index)
        self.assertIn('data-setting="qq_group_wake_names"', index)
        self.assertIn("保存 QQ 设置", index)

    def test_frontend_qq_identity_draft_is_not_overwritten_by_status_refresh(self) -> None:
        source = (
            Path(__file__).parents[1] / "studio" / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("qqIdentityDirty: false", source)
        self.assertIn("force || (!state.qqIdentityDirty && !state.qqAccountBusy)", source)
        self.assertIn("state.qqIdentityDirty = true;", source)
        self.assertIn("updateQqSetupGuide(state.status?.qq || {});", source)
        self.assertIn("fillQqIdentity(data.qq_identity || {}, { force: true })", source)
        self.assertNotIn("if (state.bootstrap?.qq_identity) fillQqIdentity(state.bootstrap.qq_identity);", source)

    def test_frontend_weather_city_supports_input_and_preset_selection(self) -> None:
        root = Path(__file__).parents[1] / "studio"
        index = (root / "index.html").read_text(encoding="utf-8")
        source = (root / "app.js").read_text(encoding="utf-8")
        styles = (root / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="weather-city-setting"', index)
        self.assertIn('id="weather-city-preset"', index)
        self.assertIn('<option value="重庆">重庆</option>', index)
        self.assertIn("function syncWeatherCityPreset()", source)
        self.assertIn("function chooseWeatherCityPreset(event)", source)
        self.assertIn('$("#weather-city-preset").addEventListener("change"', source)
        self.assertIn("weather-city-control", styles)

    def test_frontend_switch_thumb_stays_centered_for_variable_track_widths(self) -> None:
        styles = (
            Path(__file__).parents[1] / "studio" / "styles.css"
        ).read_text(encoding="utf-8")

        self.assertIn("--switch-thumb-size: 18px", styles)
        self.assertIn("top: 50%", styles)
        self.assertIn("transform: translateY(-50%)", styles)
        self.assertIn(
            "left: calc(100% - var(--switch-thumb-size) - var(--switch-thumb-inset))",
            styles,
        )
        self.assertNotIn("translateX(18px)", styles)

    def test_destructive_chat_and_memory_actions_use_themed_confirmation(self) -> None:
        root = Path(__file__).parents[1] / "studio"
        index = (root / "index.html").read_text(encoding="utf-8")
        source = (root / "app.js").read_text(encoding="utf-8")
        styles = (root / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="confirm-dialog"', index)
        self.assertIn('id="confirm-dialog-cancel"', index)
        self.assertIn('id="confirm-dialog-accept"', index)
        self.assertGreaterEqual(source.count("await confirmAction({"), 2)
        self.assertIn('title: "清除聊天记录？"', source)
        self.assertIn('title: "删除这条记忆？"', source)
        self.assertIn("settleConfirmation(false)", source)
        self.assertIn(".confirm-dialog", styles)
        self.assertIn("var(--surface-soft)", styles)

    def test_frontend_environment_download_controls_are_wired(self) -> None:
        root = Path(__file__).parents[1] / "studio"
        index = (root / "index.html").read_text(encoding="utf-8")
        source = (root / "app.js").read_text(encoding="utf-8")
        setup_source = (root / "setup.js").read_text(encoding="utf-8")
        styles = (root / "styles.css").read_text(encoding="utf-8")

        for action in ("pause", "resume", "cancel"):
            self.assertIn(f'`/api/environment/${{action}}`', source)
        self.assertIn("environment-progress-track", source)
        self.assertIn("downloaded_bytes", source)
        self.assertIn('id="environment-install-menu"', index)
        self.assertIn('id="environment-install-options"', index)
        self.assertIn("environmentInstallQueue", source)
        self.assertIn("pumpEnvironmentInstallQueue", source)
        self.assertIn("最多同时处理 3 项", index)
        self.assertIn("environmentPollTimer", source)
        self.assertIn('action === "configure" ? "连接异常" : "安装失败"', source)
        self.assertIn("environment-progress-indeterminate", styles)
        self.assertIn("正在计算总大小", source)
        self.assertIn("正在计算总大小", setup_source)
        self.assertIn("魔搭 ModelScope", index)
        self.assertIn('environment.download_transport || "后台命令行"', source)
        self.assertIn('job.progress !== null', source)
        self.assertIn('job.progress !== ""', source)
        self.assertIn("Math.min(100, Number(job.progress))", source)
        self.assertIn("Math.min(100, Number(job.progress))", setup_source)
        self.assertNotIn("Math.min(1, Number(job.progress))", setup_source)
        self.assertIn('track.setAttribute("aria-valuenow"', setup_source)
        self.assertGreaterEqual(source.count('const started = await api("/api/environment/install"'), 1)
        self.assertGreaterEqual(setup_source.count('const started = await api("/api/environment/install"'), 1)

    def test_qq_settings_have_a_state_driven_first_login_guide(self) -> None:
        root = Path(__file__).parents[1] / "studio"
        index = (root / "index.html").read_text(encoding="utf-8")
        source = (root / "app.js").read_text(encoding="utf-8")
        styles = (root / "styles.css").read_text(encoding="utf-8")

        self.assertIn('class="qq-setup-section"', index)
        self.assertIn('id="qq-guide-primary"', index)
        for step in ("install", "identity", "login", "connect"):
            self.assertIn(f'data-qq-step="{step}"', index)
        self.assertIn("function updateQqSetupGuide", source)
        self.assertIn("function runQqSetupGuide", source)
        self.assertIn('guide.dataset.stage = stage', source)
        self.assertIn('$("#qq-guide-primary").addEventListener("click", runQqSetupGuide)', source)
        self.assertIn('showTuningPanel("environment")', source)
        self.assertNotIn('window.open("https://napneko.github.io', source)
        self.assertIn('.qq-setup-steps li[data-state="current"]', styles)
        self.assertIn("#view-tuning .qq-connection-grid", styles)

    def test_qq_qr_dialog_tracks_login_status_until_the_flow_finishes(self) -> None:
        source = (
            Path(__file__).parents[1] / "studio" / "app.js"
        ).read_text(encoding="utf-8")
        start = source.index("async function refreshQqQrImage()")
        end = source.index("function openQqQrDialog()", start)
        refresh_source = source[start:end]

        self.assertIn('api("/api/status", { timeoutMs: 5000 })', refresh_source)
        self.assertIn("qq.qq_login_online || qq.napcat_online || qq.napcat_service_online", refresh_source)
        self.assertIn('"扫码成功，正在启动 OneBot 服务"', refresh_source)
        self.assertIn('"扫码成功，正在连接消息通道"', refresh_source)
        self.assertIn("setTimeout(closeQqQrDialog", refresh_source)
        self.assertIn("state.qqQrRefreshing = true", refresh_source)
        self.assertIn("state.qqQrRefreshing = false", refresh_source)

        open_start = end
        open_end = source.index("async function waitForQqFullyOffline()", open_start)
        open_source = source[open_start:open_end]
        self.assertIn("setInterval(refreshQqQrImage, 1000)", open_source)

    def test_first_run_setup_is_a_separate_page(self) -> None:
        root = Path(__file__).parents[1] / "studio"
        index = (root / "index.html").read_text(encoding="utf-8")
        setup = (root / "setup.html").read_text(encoding="utf-8")
        app_source = (root / "app.js").read_text(encoding="utf-8")
        setup_source = (root / "setup.js").read_text(encoding="utf-8")
        styles = (root / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="first-run-dialog"', index)
        self.assertNotIn('id="first-run-form"', index)
        self.assertIn('id="first-run-dialog"', setup)
        self.assertIn('id="first-run-form"', setup)
        self.assertIn('id="first-run-language-skip"', setup)
        self.assertIn('id="first-run-vision-skip"', setup)
        self.assertIn('id="first-run-assistant-name"', setup)
        self.assertIn('id="first-run-install-missing"', setup)
        self.assertIn('data-setting="assistant_name"', index)
        self.assertIn('assistant_name: $("#first-run-assistant-name")', setup_source)
        self.assertIn('assistant_name: characterName()', app_source)
        self.assertIn('window.location.replace("/setup.html")', app_source)
        self.assertIn('window.location.replace("/")', setup_source)
        self.assertIn("languageSkipped: false", setup_source)
        self.assertIn("visionSkipped: false", setup_source)
        self.assertIn('if (languageEnabled) {', setup_source)
        self.assertIn('if (visionEnabled) {', setup_source)
        self.assertIn('async function ensureModelTest(kind)', setup_source)
        self.assertIn('await ensureModelTest("language")', setup_source)
        self.assertIn('await ensureModelTest("vision")', setup_source)
        self.assertIn('const languageChanged = previousLanguageSignature', setup_source)
        self.assertIn('$("#first-run-language-provider").value = "";', setup_source)
        self.assertIn('$("#first-run-language-base-url").value = "";', setup_source)
        self.assertIn('$("#first-run-vision-provider").value = "";', setup_source)
        self.assertIn('setVisionMode("same", { invalidate: false });', setup_source)
        self.assertIn('data-first-run-environment-install', setup_source)
        self.assertIn('data-first-run-environment-action', setup_source)
        self.assertIn('"/api/environment/install"', setup_source)
        for action in ("pause", "resume", "cancel"):
            self.assertIn(f'`/api/environment/${{action}}`', setup_source)
        self.assertNotIn("state.bootstrap?.model_connection", setup_source)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr) auto", styles)
        self.assertIn("#first-run-next, .first-run-footer #first-run-finish", styles)

    def test_static_entry_redirects_between_setup_and_main_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            runtime.static_root = Path(__file__).parents[1] / "studio"
            server = StudioServer(("127.0.0.1", 0), runtime)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def request(path: str) -> tuple[int, str, bytes]:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=3
                )
                try:
                    connection.request("GET", path)
                    response = connection.getresponse()
                    return response.status, response.getheader("Location") or "", response.read()
                finally:
                    connection.close()

            try:
                runtime.cfg.setup_complete = False
                status, location, _ = request("/")
                self.assertEqual(status, 302)
                self.assertEqual(location, "/setup.html")
                status, _, body = request("/setup.html")
                self.assertEqual(status, 200)
                self.assertIn(b'id="first-run-form"', body)

                runtime.cfg.setup_complete = True
                status, location, _ = request("/setup.html")
                self.assertEqual(status, 302)
                self.assertEqual(location, "/")
                status, _, body = request("/")
                self.assertEqual(status, 200)
                self.assertNotIn(b'id="first-run-form"', body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_health_endpoint_runs_on_loopback_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(Path(tmp))
            server = StudioServer(("127.0.0.1", 0), runtime)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health",
                    timeout=3,
                ) as response:
                    payload = json.load(response)
                self.assertTrue(payload["ok"])
                self.assertIn(payload["edition"], {"personal", "public"})
                self.assertRegex(payload["workspace_id"], r"^[0-9a-f]{16}$")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()

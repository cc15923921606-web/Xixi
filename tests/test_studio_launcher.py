from __future__ import annotations

import os
import json
import subprocess
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.napcat_runtime import find_napcat_qrcode, napcat_root_ready
from start_xixi_qq import (
    ROOT,
    RUNTIME_PATHS,
    _default_gpt_sovits_root,
    _napcat_webui_connection,
    ensure_onebot_config,
    launch_napcat,
    napcat_module_url,
    resolve_napcat_dir,
    xixi_runtime_environment,
)
from start_xixi_studio import (
    STUDIO_EDITION,
    STUDIO_WORKSPACE_ID,
    _may_cleanup_source_processes,
    ensure_studio_server,
    stop_studio_server,
    studio_process_id,
    studio_ready,
)


class StudioLauncherIsolationTests(unittest.TestCase):
    def test_napcat_module_url_preserves_ascii_launch_drive(self) -> None:
        self.assertEqual(
            napcat_module_url(Path("Z:/NapCat/napcat.mjs")),
            "file:///Z:/NapCat/napcat.mjs",
        )

    @staticmethod
    def _make_napcat_root(root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        for name in (
            "launcher-user.bat",
            "napcat.mjs",
            "NapCatWinBootHook.dll",
            "NapCatWinBootMain.exe",
        ):
            (root / name).write_bytes(b"placeholder")
        return root

    def test_onebot_config_enables_loopback_http_and_websocket_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NapCat"
            config = root / "config" / "onebot11_2113357857.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                '{"network":{"httpServers":[],"websocketServers":[],"plugins":[{"name":"keep"}]},"custom":true}',
                encoding="utf-8",
            )

            path, changed = ensure_onebot_config(2113357857, root)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertTrue(changed)
            self.assertTrue(payload["custom"])
            self.assertEqual(payload["network"]["plugins"], [{"name": "keep"}])
            http = payload["network"]["httpServers"][0]
            websocket = payload["network"]["websocketServers"][0]
            self.assertEqual((http["host"], http["port"]), ("127.0.0.1", 3000))
            self.assertEqual((websocket["host"], websocket["port"]), ("127.0.0.1", 3001))
            self.assertEqual(http["messagePostFormat"], "array")
            self.assertEqual(websocket["messagePostFormat"], "array")
            legacy_payload = json.loads(
                (root / "config" / "napcat_2113357857.json").read_text(encoding="utf-8")
            )
            self.assertEqual(legacy_payload["network"]["httpServers"][0]["port"], 3000)
            self.assertEqual(legacy_payload["network"]["websocketServers"][0]["port"], 3001)

            second_path, second_changed = ensure_onebot_config(2113357857, root)
            second_payload = json.loads(second_path.read_text(encoding="utf-8"))
            self.assertEqual(second_path, path)
            self.assertFalse(second_changed)
            self.assertEqual(second_payload, payload)

    def test_napcat_path_falls_back_to_workspace_sibling_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / "昔夕"
            components = root / "runtime"
            sibling = workspace / "napcat"
            self._make_napcat_root(sibling)

            resolved = resolve_napcat_dir(root, components, {})

            self.assertEqual(resolved, sibling)

    def test_napcat_path_skips_a_stale_configured_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / "昔夕"
            components = root / "runtime"
            sibling = workspace / "napcat"
            self._make_napcat_root(sibling)

            resolved = resolve_napcat_dir(
                root,
                components,
                {"NAPCAT_ROOT": str(workspace / "missing-napcat")},
            )

            self.assertEqual(resolved, sibling)

    def test_napcat_path_accepts_nested_shell_archive_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / "昔夕"
            components = root / "runtime"
            nested = components / "NapCat" / "NapCat.Shell.Windows"
            self._make_napcat_root(nested)

            resolved = resolve_napcat_dir(root, components, {})

            self.assertEqual(resolved, nested)

    def test_napcat_detection_rejects_launcher_only_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NapCat"
            root.mkdir(parents=True)
            (root / "launcher-user.bat").write_text("@echo off", encoding="utf-8")

            self.assertFalse(napcat_root_ready(root))

    def test_qrcode_discovery_uses_latest_supported_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NapCat"
            older = root / "cache" / "qrcode.png"
            latest = root / "logs" / "login-qrcode.png"
            older.parent.mkdir(parents=True)
            latest.parent.mkdir(parents=True)
            older.write_bytes(b"x" * 100)
            latest.write_bytes(b"y" * 100)
            os.utime(latest, (older.stat().st_mtime + 2, older.stat().st_mtime + 2))

            self.assertEqual(find_napcat_qrcode(root), latest)

    def test_napcat_webui_connection_is_recovered_from_ansi_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "one_click_start.log"
            log.write_text(
                "\x1b[32minfo\x1b[39m WebUi Token: abcdef123456\n"
                "WebUi User Panel Url: http://[::]:6099/webui?token=abcdef123456\n",
                encoding="utf-8",
            )

            self.assertEqual(
                _napcat_webui_connection(log),
                ("http://127.0.0.1:6099", "abcdef123456"),
            )

    def test_napcat_launch_calls_bootstrap_directly_with_target_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_napcat_root(Path(tmp) / "NapCat")
            (root / "qqnt.json").write_text("{}", encoding="utf-8")
            qq = Path(tmp) / "QQ.exe"
            qq.write_bytes(b"qq")
            process = MagicMock(pid=4321)
            process.poll.return_value = None
            with (
                patch("start_xixi_qq.resolve_napcat_dir", return_value=root),
                patch("start_xixi_qq.resolve_qq_executable", return_value=qq),
                patch("start_xixi_qq.injected_qq_pids", return_value=[]),
                patch("start_xixi_qq.managed_qq_processes", return_value=set()),
                patch("start_xixi_qq.onebot_login", return_value={"user_id": 2113357857}),
                patch("start_xixi_qq.ws_port_ready", return_value=True),
                patch("start_xixi_qq.register_managed_qq_account"),
                patch("start_xixi_qq.register_managed_qq_process") as register_process,
                patch("start_xixi_qq.subprocess.Popen", return_value=process) as popen,
                patch("start_xixi_qq.status"),
            ):
                login = launch_napcat(2113357857)

            self.assertEqual(login["user_id"], 2113357857)
            command = popen.call_args.args[0]
            self.assertEqual(command, [
                str(root / "NapCatWinBootMain.exe"),
                str(qq),
                str(root / "NapCatWinBootHook.dll"),
                "2113357857",
            ])
            self.assertNotIn("cmd.exe", command)
            self.assertNotIn("-q", command)
            self.assertEqual(popen.call_args.kwargs["env"]["NAPCAT_MAIN_PATH"], str(root / "napcat.mjs"))
            self.assertEqual(
                (root / "loadNapCat.js").read_text(encoding="utf-8"),
                f'(async () => {{await import({json.dumps(napcat_module_url(root / "napcat.mjs"))})}})()\n',
            )
            register_process.assert_called_once_with("2113357857", 4321)

    def test_personal_source_edition_uses_workspace_voice_engine(self) -> None:
        expected = ROOT.parent / "work" / "GPT-SoVITS"
        with (
            patch("start_xixi_qq.sys.frozen", False, create=True),
            patch("start_xixi_qq.resolve_voice_root", return_value=expected) as resolve,
        ):
            self.assertEqual(
                _default_gpt_sovits_root(),
                expected,
            )
        resolve.assert_called_once_with(
            expected,
            allow_registered_fallback=True,
            discover=True,
        )

    def test_public_edition_uses_its_isolated_component_directory(self) -> None:
        expected = Path(RUNTIME_PATHS.components_dir) / "GPT-SoVITS"
        with (
            patch("start_xixi_qq.sys.frozen", True, create=True),
            patch("start_xixi_qq.resolve_voice_root", return_value=expected),
        ):
            self.assertEqual(
                _default_gpt_sovits_root(),
                expected,
            )

    def test_public_runtime_environment_ignores_personal_voice_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public_voice = root / "public-components" / "GPT-SoVITS"
            runtime_paths = SimpleNamespace(
                public_release=True,
                data_home=root / "data-home",
                data_dir=root / "data",
                logs_dir=root / "logs",
                downloads_dir=root / "downloads",
                components_dir=root / "public-components",
                models_dir=root / "models",
            )
            with (
                patch("start_xixi_qq.RUNTIME_PATHS", runtime_paths),
                patch("start_xixi_qq._default_gpt_sovits_root", return_value=public_voice),
                patch("start_xixi_qq.resolve_napcat_dir", return_value=root / "NapCat"),
                patch(
                    "start_xixi_qq.configured_identity",
                    return_value={"bot_qq_id": 2113357857, "owner_qq_id": 1000000001},
                ),
                patch.dict(os.environ, {"GPT_SOVITS_ROOT": str(root / "personal-voice")}),
            ):
                environment = xixi_runtime_environment()

            self.assertEqual(environment["GPT_SOVITS_ROOT"], str(public_voice))

    def test_personal_source_edition_may_clean_its_own_stale_processes(self) -> None:
        with patch("start_xixi_studio.sys.frozen", False, create=True):
            self.assertTrue(_may_cleanup_source_processes())

    def test_public_frozen_edition_never_cleans_personal_source_processes(self) -> None:
        with patch("start_xixi_studio.sys.frozen", True, create=True):
            self.assertFalse(_may_cleanup_source_processes())

    def test_studio_ready_accepts_only_the_same_edition_and_workspace(self) -> None:
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response
        response.read.return_value = b""
        payload = {
            "ok": True,
            "edition": STUDIO_EDITION,
            "workspace_id": STUDIO_WORKSPACE_ID,
        }
        with (
            patch("start_xixi_studio.urllib.request.urlopen", return_value=response),
            patch("start_xixi_studio.json.load", return_value=payload),
        ):
            self.assertTrue(studio_ready())

        for wrong_payload in (
            {**payload, "edition": "public" if STUDIO_EDITION == "personal" else "personal"},
            {**payload, "workspace_id": "another-workspace"},
            {"ok": True},
        ):
            with (
                patch("start_xixi_studio.urllib.request.urlopen", return_value=response),
                patch("start_xixi_studio.json.load", return_value=wrong_payload),
            ):
                self.assertFalse(studio_ready())

    def test_studio_process_id_reads_the_matching_listener(self) -> None:
        netstat = MagicMock()
        netstat.stdout = (
            "  TCP    127.0.0.1:8765    0.0.0.0:0    LISTENING    4321\n"
            "  TCP    127.0.0.1:9999    0.0.0.0:0    LISTENING    9876\n"
        )
        with (
            patch("start_xixi_studio.studio_ready", return_value=True),
            patch("start_xixi_studio.subprocess.run", return_value=netstat),
        ):
            self.assertEqual(studio_process_id(), 4321)

    def test_ensure_studio_server_passes_desktop_parent_to_child(self) -> None:
        process = MagicMock(pid=2468)
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Xixi.exe").write_bytes(b"placeholder")
            runtime_paths = SimpleNamespace(logs_dir=root / "logs")
            with (
                patch("start_xixi_studio.sys.frozen", True, create=True),
                patch("start_xixi_studio.ROOT", root),
                patch("start_xixi_studio.RUNTIME_PATHS", runtime_paths),
                patch("start_xixi_studio.studio_ready", side_effect=[False, True]),
                patch("start_xixi_studio.studio_port_in_use", return_value=False),
                patch("start_xixi_studio.xixi_runtime_environment", return_value={}),
                patch("start_xixi_studio.subprocess.Popen", return_value=process) as popen,
                patch("start_xixi_studio.status"),
            ):
                self.assertEqual(ensure_studio_server(parent_pid=1357), 2468)

        child_environment = popen.call_args.kwargs["env"]
        self.assertEqual(child_environment["XIXI_DESKTOP_PARENT_PID"], "1357")
        self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.STDOUT)

    def test_ensure_studio_server_reports_an_early_child_failure(self) -> None:
        process = MagicMock(pid=2468)
        process.poll.return_value = 7
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            logs.mkdir()
            (root / "Xixi.exe").write_bytes(b"placeholder")
            (logs / "studio-startup.log").write_text(
                "ImportError: missing optional runtime",
                encoding="utf-8",
            )
            runtime_paths = SimpleNamespace(logs_dir=logs)
            with (
                patch("start_xixi_studio.sys.frozen", True, create=True),
                patch("start_xixi_studio.ROOT", root),
                patch("start_xixi_studio.RUNTIME_PATHS", runtime_paths),
                patch("start_xixi_studio.studio_ready", return_value=False),
                patch("start_xixi_studio.studio_port_in_use", return_value=False),
                patch("start_xixi_studio.xixi_runtime_environment", return_value={}),
                patch("start_xixi_studio.subprocess.Popen", return_value=process),
                patch("start_xixi_studio.status"),
            ):
                with self.assertRaisesRegex(RuntimeError, "退出码 7") as raised:
                    ensure_studio_server(parent_pid=1357)

        self.assertIn("missing optional runtime", str(raised.exception))

    def test_source_desktop_restarts_existing_server_to_attach_parent_watchdog(self) -> None:
        process = MagicMock(pid=2468)
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pythonw = root / "venv" / "Scripts" / "pythonw.exe"
            pythonw.parent.mkdir(parents=True)
            pythonw.write_bytes(b"placeholder")
            runtime_paths = SimpleNamespace(logs_dir=root / "logs")
            with (
                patch("start_xixi_studio.sys.frozen", False, create=True),
                patch("start_xixi_studio.ROOT", root),
                patch("start_xixi_studio.RUNTIME_PATHS", runtime_paths),
                patch("start_xixi_studio.studio_ready", side_effect=[True, True]),
                patch("start_xixi_studio.studio_process_id", return_value=1357),
                patch("start_xixi_studio.stop_studio_server", return_value=True) as stop_server,
                patch("start_xixi_studio.studio_port_in_use", return_value=False),
                patch("start_xixi_studio.process_ids", return_value=[]),
                patch("start_xixi_studio.xixi_runtime_environment", return_value={}),
                patch("start_xixi_studio.subprocess.Popen", return_value=process) as popen,
                patch("start_xixi_studio.time.sleep"),
                patch("start_xixi_studio.status"),
            ):
                self.assertEqual(ensure_studio_server(parent_pid=9876), 2468)

        stop_server.assert_called_once_with(1357)
        self.assertEqual(
            popen.call_args.kwargs["env"]["XIXI_DESKTOP_PARENT_PID"],
            "9876",
        )

    def test_stop_studio_server_targets_verified_workspace_listener(self) -> None:
        with (
            patch("start_xixi_studio.studio_ready", return_value=True),
            patch("start_xixi_studio.studio_process_id", return_value=4321),
            patch("start_xixi_studio.studio_port_in_use", return_value=False),
            patch("start_xixi_studio.subprocess.run") as run,
        ):
            self.assertTrue(stop_studio_server(9999))

        self.assertEqual(run.call_args.args[0][0:3], ["taskkill.exe", "/PID", "4321"])


if __name__ == "__main__":
    unittest.main()

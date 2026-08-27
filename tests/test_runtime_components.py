from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from app.napcat_runtime import (
    ensure_napcat_launch_root,
    find_napcat_qrcode,
    find_napcat_root,
    provision_packaged_napcat,
    release_napcat_launch_root,
    resolve_napcat_root,
)
from app.voice_runtime import resolve_voice_root


class RuntimeComponentIsolationTests(unittest.TestCase):
    @staticmethod
    def _write_napcat_runtime(root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "launcher-user.bat").write_text("@echo off", encoding="utf-8")
        (root / "napcat.mjs").write_text("export {};", encoding="utf-8")
        (root / "NapCatWinBootHook.dll").write_bytes(b"hook")
        (root / "NapCatWinBootMain.exe").write_bytes(b"boot")

    def test_public_voice_root_can_reuse_a_complete_registered_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public_voice = root / "public-data" / "GPT-SoVITS"
            personal_voice = root / "personal" / "GPT-SoVITS"
            personal_voice.mkdir(parents=True)

            with (
                patch("app.voice_runtime.registered_voice_root", return_value=personal_voice),
                patch(
                    "app.voice_runtime.voice_root_ready",
                    side_effect=lambda candidate: Path(candidate) == personal_voice,
                ),
            ):
                resolved = resolve_voice_root(
                    public_voice,
                    {"GPT_SOVITS_ROOT": str(public_voice)},
                    allow_registered_fallback=True,
                    discover=False,
                )

            self.assertEqual(resolved, personal_voice)

    def test_personal_voice_root_can_reuse_registered_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_voice = root / "local" / "GPT-SoVITS"
            registered_voice = root / "registered" / "GPT-SoVITS"
            registered_voice.mkdir(parents=True)

            with (
                patch("app.voice_runtime.registered_voice_root", return_value=registered_voice),
                patch(
                    "app.voice_runtime.voice_root_ready",
                    side_effect=lambda candidate: Path(candidate) == registered_voice,
                ),
            ):
                resolved = resolve_voice_root(
                    local_voice,
                    {"GPT_SOVITS_ROOT": str(local_voice)},
                )

            self.assertEqual(resolved, registered_voice)

    def test_napcat_launcher_is_found_inside_nested_release_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "NapCat"
            nested = target / "NapCat.Shell.Windows" / "NapCat.Shell"
            nested.mkdir(parents=True)
            (nested / "launcher-user.bat").write_text("@echo off", encoding="utf-8")
            (nested / "napcat.mjs").write_text("export {};", encoding="utf-8")
            (nested / "NapCatWinBootHook.dll").write_bytes(b"hook")
            (nested / "NapCatWinBootMain.exe").write_bytes(b"boot")

            self.assertEqual(find_napcat_root(target), nested)

    def test_napcat_resolver_uses_registered_external_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "external" / "NapCat"
            external.mkdir(parents=True)
            (external / "launcher-user.bat").write_text("@echo off", encoding="utf-8")
            (external / "napcat.mjs").write_text("export {};", encoding="utf-8")
            (external / "NapCatWinBootHook.dll").write_bytes(b"hook")
            (external / "NapCatWinBootMain.exe").write_bytes(b"boot")

            with (
                patch("app.napcat_runtime.registered_napcat_root", return_value=external),
                patch("app.napcat_runtime.register_napcat_root"),
            ):
                resolved = resolve_napcat_root(
                    root / "app",
                    root / "components",
                    {},
                    discover=False,
                )

            self.assertEqual(resolved, external)

    def test_packaged_napcat_upgrade_adds_missing_config_without_overwriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packaged = root / "app" / "runtime" / "components" / "NapCat"
            installed = root / "components" / "NapCat"
            self._write_napcat_runtime(packaged)
            self._write_napcat_runtime(installed)
            (packaged / "config").mkdir()
            packaged_config = packaged / "config" / "napcat.json"
            packaged_config.write_text('{"consoleLog": true}', encoding="utf-8")

            with patch("app.napcat_runtime.register_napcat_root"):
                resolved = provision_packaged_napcat(root / "app", root / "components")

            installed_config = installed / "config" / "napcat.json"
            self.assertEqual(resolved, installed)
            self.assertEqual(installed_config.read_text(encoding="utf-8"), '{"consoleLog": true}')

            installed_config.write_text('{"consoleLog": false}', encoding="utf-8")
            with patch("app.napcat_runtime.register_napcat_root"):
                provision_packaged_napcat(root / "app", root / "components")
            self.assertEqual(installed_config.read_text(encoding="utf-8"), '{"consoleLog": false}')

    def test_unicode_napcat_root_uses_temporary_ascii_copy_and_exposes_qrcode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "中文目录" / "NapCat"
            data_dir = base / "data"
            self._write_napcat_runtime(source)
            (source / "qqnt.json").write_text("{}", encoding="utf-8")

            with (
                patch.dict(os.environ, {"XIXI_DATA_DIR": str(data_dir)}),
                patch("app.napcat_runtime._windows_short_path", return_value=None),
            ):
                launch_root = ensure_napcat_launch_root(source)
                try:
                    self.assertNotEqual(launch_root.resolve(), source.resolve())
                    str(launch_root).encode("ascii")
                    qrcode = launch_root / "cache" / "qrcode.png"
                    qrcode.parent.mkdir(parents=True)
                    qrcode.write_bytes(b"q" * 100)
                    self.assertEqual(find_napcat_qrcode(source), qrcode)
                finally:
                    release_napcat_launch_root()

                self.assertFalse(launch_root.exists())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.config as config_module
from app.config import Config
from app.runtime_paths import (
    DATA_POINTER_FILENAME,
    MIGRATION_FAILURE_FILENAME,
    resolve_runtime_paths,
)


class RuntimePathTests(unittest.TestCase):
    def test_public_first_launch_seeds_packaged_napcat_without_overwriting_user_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = Path(tmp) / "Xixi"
            app_root = install_root / "程序文件"
            packaged = app_root / "runtime" / "components" / "NapCat"
            packaged.mkdir(parents=True)
            (packaged / "launcher-user.bat").write_text("packaged launcher", encoding="utf-8")
            (packaged / "napcat.mjs").write_text("packaged core", encoding="utf-8")

            paths = resolve_runtime_paths(app_root, public_release=True, environ={})

            seeded = paths.components_dir / "NapCat"
            self.assertEqual(
                (seeded / "launcher-user.bat").read_text(encoding="utf-8"),
                "packaged launcher",
            )
            self.assertFalse((paths.components_dir / "components").exists())
            (seeded / "launcher-user.bat").write_text("user preserved", encoding="utf-8")
            resolve_runtime_paths(app_root, public_release=True, environ={})
            self.assertEqual(
                (seeded / "launcher-user.bat").read_text(encoding="utf-8"),
                "user preserved",
            )

    def test_personal_layout_keeps_project_data_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "xixi-source"
            paths = resolve_runtime_paths(root, public_release=False, environ={})

            self.assertEqual(paths.data_home, root)
            self.assertEqual(paths.data_dir, root / "data")
            self.assertEqual(paths.logs_dir, root / "logs")
            self.assertFalse((root / DATA_POINTER_FILENAME).exists())

            cfg = Config(root=root)
            self.assertEqual(cfg.data_root, root / "data")
            self.assertEqual(cfg.persona_file, root / "persona.txt")

    def test_public_layout_migrates_and_verifies_legacy_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "XixiPublic"
            legacy_data = root / "data"
            (legacy_data / "desktop_webview").mkdir(parents=True)
            (legacy_data / "environment_downloads").mkdir(parents=True)
            (legacy_data / "voice_assets").mkdir(parents=True)
            (root / "logs").mkdir(parents=True)
            (root / "runtime" / "GPT-SoVITS").mkdir(parents=True)
            (root / "runtime" / "NapCat").mkdir(parents=True)
            (root / "runtime" / "voice").mkdir(parents=True)
            (legacy_data / "studio_settings.json").write_text(
                '{"voice_enabled": true}', encoding="utf-8"
            )
            (legacy_data / "desktop_webview" / "cache.bin").write_bytes(b"cache")
            (legacy_data / "environment_downloads" / "package.bin").write_bytes(b"download")
            (legacy_data / "voice_assets" / "reference.mp3").write_bytes(b"resource")
            (root / "logs" / "app.log").write_text("old log", encoding="utf-8")
            (root / "runtime" / "GPT-SoVITS" / "api_v2.py").write_text(
                "# local voice", encoding="utf-8"
            )
            (root / "runtime" / "NapCat" / "launcher-user.bat").write_text(
                "@echo off", encoding="utf-8"
            )
            (root / "runtime" / "voice" / "bundled.bin").write_bytes(b"immutable")
            (root / "persona.txt").write_text("公开版人格", encoding="utf-8")
            (root / "interest_profile.json").write_text("{}", encoding="utf-8")

            paths = resolve_runtime_paths(root, public_release=True, environ={})

            self.assertEqual(paths.data_home, parent / "XixiPublic数据")
            self.assertEqual(
                (paths.data_dir / "studio_settings.json").read_text(encoding="utf-8"),
                '{"voice_enabled": true}',
            )
            self.assertEqual(
                (paths.webview_dir / "desktop_webview" / "cache.bin").read_bytes(),
                b"cache",
            )
            self.assertEqual((paths.downloads_dir / "package.bin").read_bytes(), b"download")
            self.assertEqual((paths.logs_dir / "app.log").read_text(encoding="utf-8"), "old log")
            self.assertEqual(
                (paths.components_dir / "GPT-SoVITS" / "api_v2.py").read_text(encoding="utf-8"),
                "# local voice",
            )
            self.assertEqual(
                (paths.components_dir / "NapCat" / "launcher-user.bat").read_text(encoding="utf-8"),
                "@echo off",
            )
            self.assertFalse((paths.components_dir / "voice" / "bundled.bin").exists())
            self.assertEqual((paths.data_dir / "persona.txt").read_text(encoding="utf-8"), "公开版人格")
            self.assertFalse((paths.data_dir / "voice_assets" / "reference.mp3").exists())
            self.assertEqual(
                (root / DATA_POINTER_FILENAME).read_text(encoding="utf-8").strip(),
                str(paths.data_home),
            )

            manifest = json.loads(paths.migration_manifest_file.read_text(encoding="utf-8"))
            settings_entry = next(
                item
                for item in manifest["migrated_files"]
                if item["source"].endswith("studio_settings.json")
            )
            self.assertEqual(settings_entry["size"], len(b'{"voice_enabled": true}'))
            self.assertEqual(
                settings_entry["sha256"],
                hashlib.sha256(b'{"voice_enabled": true}').hexdigest(),
            )
            runtime_config = json.loads(paths.runtime_config_file.read_text(encoding="utf-8"))
            self.assertEqual(runtime_config["schema_version"], 2)
            self.assertEqual(runtime_config["data_root"], str(paths.data_home))

    def test_existing_external_data_is_not_overwritten_on_later_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "XixiPublic"
            (root / "data").mkdir(parents=True)
            legacy = root / "data" / "studio_settings.json"
            legacy.write_text("old", encoding="utf-8")
            first = resolve_runtime_paths(root, public_release=True, environ={})
            current = first.data_dir / "studio_settings.json"
            current.write_text("new user settings", encoding="utf-8")

            second = resolve_runtime_paths(root, public_release=True, environ={})

            self.assertEqual(second.data_home, first.data_home)
            self.assertEqual(current.read_text(encoding="utf-8"), "new user settings")

    def test_classified_public_install_uses_user_data_and_migrates_flat_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = Path(tmp) / "Xixi"
            app_root = install_root / "程序文件"
            (install_root / "data").mkdir(parents=True)
            app_root.mkdir(parents=True)
            (install_root / "data" / "studio_settings.json").write_text(
                '{"assistant_name": "星璃"}', encoding="utf-8"
            )
            (install_root / "persona.txt").write_text("旧版自定义人格", encoding="utf-8")
            (app_root / "persona.txt").write_text("公开版默认人格", encoding="utf-8")

            paths = resolve_runtime_paths(app_root, public_release=True, environ={})

            self.assertEqual(paths.data_home, install_root / "用户数据")
            self.assertEqual(
                (paths.data_dir / "studio_settings.json").read_text(encoding="utf-8"),
                '{"assistant_name": "星璃"}',
            )
            self.assertEqual(
                (paths.data_dir / "persona.txt").read_text(encoding="utf-8"),
                "旧版自定义人格",
            )
            self.assertEqual(
                (app_root / DATA_POINTER_FILENAME).read_text(encoding="utf-8").strip(),
                str(paths.data_home),
            )

    def test_public_installer_keeps_runtime_files_in_classified_directories(self) -> None:
        project = Path(__file__).parents[1]
        installer = (project / "packaging" / "xixi_public.iss").read_text(encoding="utf-8")
        build_script = (project / "packaging" / "build_public_release.ps1").read_text(encoding="utf-8")

        self.assertIn('DestDir: "{app}\\程序文件"', installer)
        self.assertIn('UninstallFilesDir={app}\\卸载程序', installer)
        self.assertIn('Name: "{app}\\启动昔夕"', installer)
        self.assertIn('Filename: "{app}\\程序文件\\{#MyAppExeName}"', installer)
        self.assertIn('$AppVersion = "0.1"', build_script)
        self.assertIn('default_data_home = "用户数据"', build_script)
        self.assertIn('[switch]$OfflineBundle', build_script)
        self.assertIn('bundle_mode = if ($OfflineBundle)', build_script)
        self.assertIn('third_party_licenses\\NapCatQQ-LICENSE.txt', build_script)
        self.assertIn('third_party_licenses\\GPT-SoVITS-LICENSE.txt', build_script)
        self.assertIn('"LICENSE"', build_script)
        self.assertIn('"NOTICE"', build_script)
        self.assertIn('docs\\LICENSING.md', build_script)

        spec = (project / "packaging" / "xixi_public.spec").read_text(encoding="utf-8")
        self.assertIn('XIXI_BUILD_OFFLINE_BUNDLE', spec)
        self.assertIn('if offline_bundle:', spec)
        self.assertIn('THIRD_PARTY_NOTICES.md', spec)
        self.assertIn('project / "LICENSE"', spec)
        self.assertIn('project / "NOTICE"', spec)
        self.assertIn('project / "docs" / "LICENSING.md"', spec)
        self.assertIn('third_party_licenses', spec)
        self.assertNotIn(
            '(str(project / "whisper-small-full"), "whisper-small-full"),\n    (str(project / "data"',
            spec,
        )

    def test_public_config_uses_downloaded_whisper_model_when_not_bundled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = Path(tmp) / "Xixi"
            app_root = install_root / "程序文件"
            app_root.mkdir(parents=True)
            paths = resolve_runtime_paths(app_root, public_release=True, environ={})
            downloaded = paths.models_dir / "whisper-small-full"

            with (
                patch.object(config_module, "_PATHS", paths),
                patch.dict(os.environ, {}, clear=True),
            ):
                cfg = Config(root=app_root)

            self.assertEqual(Path(cfg.whisper_fallback_model_path), downloaded)

    def test_migration_conflict_falls_back_without_deleting_legacy_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "XixiPublic"
            (root / "data").mkdir(parents=True)
            legacy = root / "data" / "studio_settings.json"
            legacy.write_text("legacy", encoding="utf-8")
            data_home = parent / "custom-data"
            (data_home / "运行数据").mkdir(parents=True)
            (data_home / "运行数据" / "studio_settings.json").write_text(
                "different", encoding="utf-8"
            )

            paths = resolve_runtime_paths(
                root,
                public_release=True,
                environ={"XIXI_DATA_HOME": str(data_home)},
            )

            self.assertEqual(paths.data_dir, root / "data")
            self.assertEqual(legacy.read_text(encoding="utf-8"), "legacy")
            self.assertTrue((data_home / MIGRATION_FAILURE_FILENAME).is_file())
            self.assertFalse((root / DATA_POINTER_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()

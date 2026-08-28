from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import json
import tempfile
from pathlib import Path

from start_xixi_desktop import (
    CALL_OVERLAY_COLLAPSED_SIZE,
    CALL_OVERLAY_HEIGHT,
    CALL_OVERLAY_TITLE,
    CALL_OVERLAY_WIDTH,
    DEFAULT_PREFERENCES,
    DesktopApi,
    WEBVIEW2_BACKGROUND_FLAGS,
    _call_overlay_menu_visible,
    _call_overlay_resize_bounds,
    _configure_frozen_release_environment,
    _configure_webview_background_runtime,
    _edition_identity,
    _load_preferences,
    _set_webview_microphone_permission,
    initialize_webview_gui,
    _should_show_call_overlay,
    _stop_game_companion_session,
)


class ImmediateThread:
    def __init__(self, *, target, **_kwargs) -> None:
        self._target = target

    def start(self) -> None:
        self._target()


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def show(self) -> None:
        self.calls.append(("show", None))

    def restore(self) -> None:
        self.calls.append(("restore", None))

    def evaluate_js(self, script: str) -> None:
        self.calls.append(("evaluate_js", script))


class FakeAvatarBubble:
    def __init__(self, *, show_result: bool = True) -> None:
        self.calls: list[tuple[str, object]] = []
        self.bounds = (700, 400, 96, 96)
        self.show_result = show_result
        self.visible = False

    def show_at(self, x: int, y: int, width: int, height: int) -> bool:
        self.bounds = (x, y, width, height)
        self.calls.append(("show_at", self.bounds))
        self.visible = self.show_result
        return self.show_result

    def hide(self) -> bool:
        self.calls.append(("hide", None))
        self.visible = False
        return True

    def position(self) -> tuple[int, int, int, int]:
        return self.bounds

    def is_visible(self) -> bool:
        return self.visible


class DesktopLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = DesktopApi({
            "close_to_tray": False,
            "start_with_windows": False,
            "remember_window": False,
        })

    def test_close_to_tray_is_permanently_disabled(self) -> None:
        self.assertFalse(DEFAULT_PREFERENCES["close_to_tray"])

        with tempfile.TemporaryDirectory() as tmp:
            preferences_path = Path(tmp) / "desktop_preferences.json"
            preferences_path.write_text(
                json.dumps({"close_to_tray": True, "remember_window": False}),
                encoding="utf-8",
            )
            with patch("start_xixi_desktop.PREFERENCES_PATH", preferences_path):
                loaded = _load_preferences()

        self.assertFalse(loaded["close_to_tray"])

        with (
            patch("start_xixi_desktop._set_startup"),
            patch("start_xixi_desktop._save_preferences"),
        ):
            saved = self.api.save_preferences({"close_to_tray": True})
        self.assertNotIn("close_to_tray", saved)
        self.assertFalse(self.api._preferences["close_to_tray"])

        source = (Path(__file__).parents[1] / "start_xixi_desktop.py").read_text(encoding="utf-8")
        self.assertNotIn("window.hide", source)
        self.assertIn("desktop_parent_pid = os.getpid()", source)

    def test_microphone_permission_is_persisted_and_applied_to_webview(self) -> None:
        with (
            patch("start_xixi_desktop._save_preferences") as save_preferences,
            patch("start_xixi_desktop._set_webview_microphone_permission", return_value=True) as apply_permission,
        ):
            result = self.api.set_microphone_permission(True)

        self.assertEqual(result, {"enabled": True, "decided": True, "applied": True})
        self.assertTrue(self.api.get_preferences()["microphone_enabled"])
        save_preferences.assert_called_once_with(self.api._preferences)
        apply_permission.assert_called_once_with(None, True)

    def test_microphone_permission_defaults_to_undecided(self) -> None:
        self.assertIsNone(DEFAULT_PREFERENCES["microphone_enabled"])
        self.assertIsNone(self.api.get_preferences()["microphone_enabled"])

    def test_webview_microphone_permission_uses_profile_api(self) -> None:
        initialize_webview_gui("edgechromium")
        task = MagicMock()
        task.Wait.return_value = True
        profile = MagicMock()
        profile.SetPermissionStateAsync.return_value = task
        window = SimpleNamespace(native=SimpleNamespace(
            IsDisposed=False,
            InvokeRequired=False,
            browser=SimpleNamespace(
                webview=SimpleNamespace(
                    CoreWebView2=SimpleNamespace(Profile=profile),
                ),
            ),
        ))

        self.assertTrue(_set_webview_microphone_permission(window, True))
        permission_kind, origin, permission_state = profile.SetPermissionStateAsync.call_args.args
        self.assertEqual(str(permission_kind), "Microphone")
        self.assertTrue(origin.startswith("http://127.0.0.1:"))
        self.assertEqual(str(permission_state), "Allow")
        task.Wait.assert_called_once_with(5000)

    def test_public_first_run_ignores_inherited_model_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            runtime_paths = MagicMock()
            runtime_paths.data_dir = data_dir
            runtime_paths.components_dir = Path(tmp) / "components"
            inherited = {
                "XIXI_CREDENTIAL_SERVICE": "xixi-ai-companion",
                "OPENAI_API_KEY": "personal-secret",
                "OPENAI_BASE_URL": "https://personal.example/v1",
                "OPENAI_MODEL": "personal-model",
                "VISION_API_KEY": "personal-vision-secret",
                "VISION_BASE_URL": "https://personal-vision.example/v1",
                "VISION_MODEL": "personal-vision-model",
            }
            with (
                patch("start_xixi_desktop.sys.frozen", True, create=True),
                patch("start_xixi_desktop.RUNTIME_PATHS", runtime_paths),
                patch.dict("start_xixi_desktop.os.environ", inherited, clear=True),
            ):
                _configure_frozen_release_environment()
                environment = dict(__import__("os").environ)

        self.assertEqual(environment["XIXI_CREDENTIAL_SERVICE"], "xixi-desktop-public")
        self.assertEqual(environment["OPENAI_API_KEY"], "")
        self.assertEqual(environment["OPENAI_BASE_URL"], "")
        self.assertEqual(environment["OPENAI_MODEL"], "")
        self.assertEqual(environment["VISION_API_KEY"], "")
        self.assertEqual(environment["VISION_BASE_URL"], "")
        self.assertEqual(environment["VISION_MODEL"], "")
        self.assertEqual(environment["XIXI_IGNORE_SAVED_MODEL_CREDENTIALS"], "1")

    def test_normalize_call_overlay_state_keeps_last_six_entries(self) -> None:
        entries = [{"role": "user", "text": f" message {index} "} for index in range(8)]

        normalized = self.api._normalize_call_overlay_state({
            "active": 1,
            "minimized": True,
            "status": "  speaking   now  ",
            "duration": " 01:23 ",
            "entries": entries,
            "theme": {
                "surface": "#22282b",
                "accent": "#d58ca2",
                "colorScheme": "dark",
                "unknown": "ignored",
            },
        })

        self.assertTrue(normalized["active"])
        self.assertTrue(normalized["minimized"])
        self.assertEqual(normalized["status"], "speaking now")
        self.assertEqual(normalized["duration"], "01:23")
        self.assertEqual([item["text"] for item in normalized["entries"]], [
            "message 2",
            "message 3",
            "message 4",
            "message 5",
            "message 6",
            "message 7",
        ])
        self.assertEqual(normalized["theme"], {
            "surface": "#22282b",
            "accent": "#d58ca2",
            "colorScheme": "dark",
        })

    def test_personal_and_public_editions_use_independent_runtime_identity(self) -> None:
        personal = _edition_identity(False)
        public = _edition_identity(True)

        for key in (
            "window_title",
            "call_overlay_title",
            "call_avatar_title",
            "mutex_name",
            "app_user_model_id",
            "studio_port",
            "startup_value_name",
            "credential_service",
        ):
            self.assertNotEqual(personal[key], public[key])
        self.assertEqual(personal["studio_port"], 8765)
        self.assertEqual(public["studio_port"], 8766)
        self.assertEqual(personal["credential_service"], "xixi-ai-companion")
        self.assertEqual(public["credential_service"], "xixi-desktop-public")
        self.assertEqual(public["window_title"], "昔夕")
        self.assertNotIn("公开版", public["window_title"])
        self.assertNotIn("公开版", public["call_overlay_title"])
        self.assertNotIn("公开版", public["call_avatar_title"])

    def test_normalize_call_overlay_state_sanitizes_entries(self) -> None:
        normalized = self.api._normalize_call_overlay_state({
            "entries": [
                None,
                {"role": "unexpected", "text": "  hello\n world  "},
                {"role": "user", "text": "x" * 300},
                {"role": "user", "text": "   "},
            ],
        })

        self.assertEqual(normalized["entries"][0], {"role": "assistant", "text": "hello world"})
        self.assertEqual(normalized["entries"][1]["role"], "user")
        self.assertEqual(len(normalized["entries"][1]["text"]), 240)
        self.assertEqual(self.api._normalize_call_overlay_state(None)["entries"], [])

    def test_overlay_stays_visible_when_main_window_is_minimized_or_hidden(self) -> None:
        active_call = {"active": True, "minimized": False}

        self.assertTrue(_should_show_call_overlay(active_call, main_window_hidden=True))
        self.assertFalse(_should_show_call_overlay(active_call, main_window_hidden=False))
        self.assertTrue(_should_show_call_overlay(
            {"active": True, "minimized": True},
            main_window_hidden=False,
        ))
        self.assertFalse(_should_show_call_overlay(
            {"active": False, "minimized": True},
            main_window_hidden=True,
        ))

    def test_call_overlay_tray_item_is_only_visible_during_a_call(self) -> None:
        self.assertFalse(_call_overlay_menu_visible({"active": False}))
        self.assertFalse(_call_overlay_menu_visible({}))
        self.assertTrue(_call_overlay_menu_visible({"active": True}))

        source = (Path(__file__).parents[1] / "start_xixi_desktop.py").read_text(encoding="utf-8")
        self.assertIn("visible=lambda _item: _call_overlay_menu_visible", source)
        self.assertIn("tray.update_menu()", source)

    def test_overlay_resize_bounds_follow_the_drag_and_keep_minimum_size(self) -> None:
        desktop = (0, 0, 1920, 1080)
        self.assertEqual(
            _call_overlay_resize_bounds(
                "south-east",
                (100, 100, 380, 254),
                (480, 354),
                (600, 434),
                desktop,
            ),
            (100, 100, 500, 334),
        )
        self.assertEqual(
            _call_overlay_resize_bounds(
                "north-west",
                (100, 100, 380, 254),
                (100, 100),
                (500, 500),
                desktop,
            ),
            (160, 144, 320, 210),
        )

    def test_webview_background_runtime_preserves_existing_arguments(self) -> None:
        with patch.dict(
            "start_xixi_desktop.os.environ",
            {"WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": "--existing-flag"},
            clear=False,
        ):
            value = _configure_webview_background_runtime()
            self.assertIn("--existing-flag", value)
            for flag in WEBVIEW2_BACKGROUND_FLAGS:
                self.assertEqual(value.split().count(flag), 1)
            self.assertEqual(_configure_webview_background_runtime(), value)

    def test_voice_call_meter_uses_background_audio_processing(self) -> None:
        source = (Path(__file__).parents[1] / "studio" / "app.js").read_text(encoding="utf-8")

        self.assertIn('new AudioWorkletNode(context, "xixi-voice-call-meter"', source)
        self.assertIn('state.voiceCallMeterMode = "script-processor"', source)
        self.assertIn("keepVoiceCallAudioAlive", source)
        self.assertNotIn("requestAnimationFrame(() => runVoiceCallMeter", source)

    def test_restore_call_updates_state_and_restores_main_window(self) -> None:
        window = FakeWindow()
        self.api.bind_windows(window, MagicMock())
        self.api.sync_call_overlay({"active": True, "minimized": True})

        with (
            patch("start_xixi_desktop._set_window_visible_without_focus") as set_visible,
            patch("start_xixi_desktop.threading.Thread", ImmediateThread),
        ):
            result = self.api.restore_call()

        self.assertEqual(result, {"ok": True})
        self.assertFalse(self.api.call_overlay_state()["minimized"])
        set_visible.assert_called_once_with(CALL_OVERLAY_TITLE, False)
        self.assertEqual(window.calls, [
            ("show", None),
            ("evaluate_js", "restoreVoiceCall()"),
        ])

    def test_overlay_collapses_to_bubble_until_explicitly_expanded(self) -> None:
        overlay = FakeWindow()
        bubble = FakeAvatarBubble()
        self.api.bind_windows(FakeWindow(), overlay)
        self.api.bind_avatar_bubble(bubble)
        self.api.sync_call_overlay({"active": True, "minimized": True})

        with (
            patch("start_xixi_desktop._animate_window_resize_without_focus", return_value=True) as resize,
            patch("start_xixi_desktop._window_bounds", return_value=(700, 400, 96, 96)),
            patch("start_xixi_desktop._set_window_visible_without_focus") as set_visible,
        ):
            self.assertEqual(self.api.collapse_call_overlay(), {"ok": True})
            self.api.sync_call_overlay({"active": True, "minimized": True, "duration": "00:01"})

        self.assertTrue(self.api.call_overlay_collapsed())
        self.assertIn(("show_at", (700, 400, 96, 96)), bubble.calls)
        set_visible.assert_called_once_with(CALL_OVERLAY_TITLE, False)
        resize.assert_called_once_with(
            CALL_OVERLAY_TITLE,
            CALL_OVERLAY_COLLAPSED_SIZE,
            CALL_OVERLAY_COLLAPSED_SIZE,
        )

        with (
            patch("start_xixi_desktop._window_hidden_or_minimized", return_value=True),
            patch("start_xixi_desktop._animate_window_resize_without_focus", return_value=True) as resize,
            patch("start_xixi_desktop._set_window_bounds_without_focus", return_value=True) as set_bounds,
        ):
            self.assertEqual(self.api.show_call_overlay(), {"ok": True})

        self.assertFalse(self.api.call_overlay_collapsed())
        self.assertEqual(bubble.calls[-1], ("hide", None))
        set_bounds.assert_called_once_with(
            CALL_OVERLAY_TITLE,
            700,
            400,
            96,
            96,
            visible=True,
        )
        resize.assert_called_once_with(
            CALL_OVERLAY_TITLE,
            CALL_OVERLAY_WIDTH,
            CALL_OVERLAY_HEIGHT,
        )

    def test_new_call_clears_manual_overlay_hide(self) -> None:
        with (
            patch("start_xixi_desktop._set_window_visible_without_focus"),
            patch("start_xixi_desktop._resize_window_without_focus", return_value=True),
            patch("start_xixi_desktop._animate_window_resize_without_focus", return_value=True),
        ):
            self.api.sync_call_overlay({"active": True, "minimized": True})
            self.api.collapse_call_overlay()
            self.api.sync_call_overlay({"active": False})
            self.api.sync_call_overlay({"active": True, "minimized": True})

        self.assertFalse(self.api.call_overlay_collapsed())

    def test_overlay_collapse_keeps_webview_fallback_when_avatar_cannot_show(self) -> None:
        bubble = FakeAvatarBubble(show_result=False)
        self.api.bind_windows(FakeWindow(), FakeWindow())
        self.api.bind_avatar_bubble(bubble)
        self.api.sync_call_overlay({"active": True, "minimized": True})

        with (
            patch("start_xixi_desktop._animate_window_resize_without_focus", return_value=True),
            patch("start_xixi_desktop._window_bounds", return_value=(700, 400, 64, 64)),
            patch("start_xixi_desktop._set_window_visible_without_focus") as set_visible,
        ):
            result = self.api.collapse_call_overlay()

        self.assertEqual(result, {"ok": True})
        self.assertTrue(self.api.call_overlay_collapsed())
        self.assertFalse(self.api.collapsed_avatar_visible())
        self.assertEqual(bubble.calls[-1], ("show_at", (700, 400, 64, 64)))
        set_visible.assert_called_once_with(CALL_OVERLAY_TITLE, True)

    def test_overlay_header_uses_avatar_restore_and_hide_button(self) -> None:
        studio = Path(__file__).parents[1] / "studio"
        html = (studio / "call_overlay.html").read_text(encoding="utf-8")
        script = (studio / "call_overlay.js").read_text(encoding="utf-8")
        styles = (studio / "call_overlay.css").read_text(encoding="utf-8")

        self.assertIn('id="overlay-avatar"', html)
        self.assertIn('id="overlay-hide"', html)
        self.assertIn('id="overlay-settings-trigger"', html)
        self.assertIn('id="overlay-opacity"', html)
        self.assertIn('data-resize-edge="south-east"', html)
        self.assertLess(html.index('id="overlay-hide"'), html.index('id="overlay-settings-trigger"'))
        self.assertNotIn('id="overlay-restore"', html)
        self.assertIn('invokeNative("restore")', script)
        self.assertIn('invokeNative("collapse")', script)
        self.assertIn('invokeNative("expand")', script)
        self.assertIn("animateOverlayTransition(true)", script)
        self.assertIn("animateOverlayTransition(false)", script)
        self.assertIn("expandCallOverlayFromNative", script)
        self.assertNotIn('invokeNative("begin_drag")', script)
        self.assertNotIn('addEventListener("pointerdown"', script)
        self.assertNotIn(".call-overlay-avatar::after", styles)
        self.assertIn("--overlay-radius: 12px", styles)
        self.assertIn("applyOverlayTheme(payload.theme)", script)
        self.assertIn('invokeNative("set_opacity", opacity)', script)
        self.assertIn('invokeNative("resize", handle.dataset.resizeEdge)', script)
        launcher = (studio.parent / "start_xixi_desktop.py").read_text(encoding="utf-8")
        self.assertIn("class NativeCallAvatarBubble", launcher)
        self.assertIn("CreateRoundRectRgn", launcher)
        self.assertIn("SetWindowRgn", launcher)
        self.assertIn("SetLayeredWindowAttributes", launcher)
        self.assertIn("GetAsyncKeyState", launcher)
        self.assertIn("def _call_overlay_resize_bounds", launcher)
        self.assertNotIn("WS_THICKFRAME", launcher)
        self.assertIn("resizable=True", launcher)
        self.assertNotIn("transparent=True", launcher)
        self.assertIn('background_color="#ffffff"', launcher)
        self.assertIn("GetWindowRgn", launcher)
        self.assertIn("corners_are_clipped", launcher)
        self.assertIn("last_round_check", launcher)
        self.assertIn("DwmSetWindowAttribute", launcher)
        self.assertIn("DWMWA_WINDOW_CORNER_PREFERENCE", launcher)
        self.assertIn(
            "min_size=(CALL_OVERLAY_COLLAPSED_SIZE, CALL_OVERLAY_COLLAPSED_SIZE)",
            launcher,
        )

    def test_overlay_opacity_is_clamped_persisted_and_applied(self) -> None:
        with (
            patch("start_xixi_desktop._set_window_opacity", return_value=True) as set_opacity,
            patch("start_xixi_desktop._save_preferences") as save_preferences,
        ):
            result = self.api.set_call_overlay_opacity(0.2)

        self.assertEqual(result, {"ok": True, "opacity": 0.45})
        self.assertEqual(self.api.call_overlay_state()["opacity"], 0.45)
        set_opacity.assert_called_once_with(CALL_OVERLAY_TITLE, 0.45)
        save_preferences.assert_called_once()

    def test_overlay_resize_persists_the_new_expanded_size(self) -> None:
        self.api.sync_call_overlay({"active": True})
        with (
            patch("start_xixi_desktop._window_bounds", return_value=(300, 200, 380, 254)),
            patch("start_xixi_desktop.threading.Thread") as resize_thread,
        ):
            result = self.api.resize_call_overlay("south-east")

        self.assertEqual(result, {"ok": True})
        resize_thread.return_value.start.assert_called_once()

    def test_game_companion_stop_posts_to_local_studio(self) -> None:
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response

        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            self.assertTrue(_stop_game_companion_session(timeout_seconds=0.5))

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8765/api/game/stop")
        self.assertEqual(request.get_method(), "POST")

    def test_hangup_call_updates_state_and_notifies_main_window(self) -> None:
        window = FakeWindow()
        self.api.bind_windows(window, MagicMock())
        self.api.sync_call_overlay({"active": True, "minimized": True})

        with (
            patch("start_xixi_desktop._set_window_visible_without_focus") as set_visible,
            patch("start_xixi_desktop._stop_game_companion_session", return_value=True) as stop_game,
            patch("start_xixi_desktop.threading.Thread", ImmediateThread),
        ):
            result = self.api.hangup_call()

        self.assertEqual(result, {"ok": True})
        self.assertFalse(self.api.call_overlay_state()["active"])
        set_visible.assert_called_once_with(CALL_OVERLAY_TITLE, False)
        stop_game.assert_called_once_with()
        self.assertEqual(window.calls, [("evaluate_js", "endVoiceCall()")])

    def test_voice_call_hangup_stops_game_companion_in_web_app(self) -> None:
        source = (Path(__file__).parents[1] / "studio" / "app.js").read_text(encoding="utf-8")

        hangup = source[source.index("function endVoiceCall(options = {})"):]
        self.assertIn('api("/api/game/stop"', hangup[:5000])


if __name__ == "__main__":
    unittest.main()

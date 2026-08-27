from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from app.game_runtime import (
    FramePacket,
    GameAdapterRegistry,
    GameRuntime,
    RealtimeGamePerception,
    WindowFrameCapture,
)


class FakeObservationControl:
    def window_region(self, hwnd: int) -> dict[str, int]:
        self.last_hwnd = hwnd
        return {"left": 10, "top": 20, "width": 640, "height": 360}


class FakeScreenObservationControl(FakeObservationControl):
    def window_region(self, hwnd: int) -> dict[str, int]:
        self.last_hwnd = hwnd
        return {"left": 0, "top": 0, "width": 1920, "height": 1080}


class GameRuntimeTests(unittest.TestCase):
    def test_window_capture_reads_pixels_without_input(self) -> None:
        control = FakeObservationControl()
        capture = WindowFrameCapture(control.window_region)
        image = np.full((360, 640, 3), 128, dtype=np.uint8)
        with patch.object(capture, "_capture_window", return_value=image):
            packet = capture.capture(42)
        self.assertEqual(control.last_hwnd, 42)
        self.assertEqual(packet.backend, "window")
        self.assertEqual(packet.window_rect, (10, 20, 640, 360))
        self.assertEqual(packet.image.shape, (360, 640, 3))

    def test_screen_capture_skips_window_api_when_hwnd_is_zero(self) -> None:
        control = FakeScreenObservationControl()
        capture = WindowFrameCapture(control.window_region)
        image = np.full((1080, 1920, 3), 128, dtype=np.uint8)
        with (
            patch.object(capture, "_capture_window") as window_capture,
            patch.object(capture, "_capture_dxcam", return_value=image),
        ):
            packet = capture.capture(0)

        self.assertEqual(packet.backend, "dxcam")
        window_capture.assert_not_called()
        self.assertEqual(control.last_hwnd, 0)

    def test_window_capture_rejects_black_window_frame_and_uses_fallback(self) -> None:
        control = FakeObservationControl()
        capture = WindowFrameCapture(control.window_region)
        black = np.zeros((360, 640, 3), dtype=np.uint8)
        fallback = np.full((360, 640, 3), 128, dtype=np.uint8)
        with (
            patch.object(capture, "_capture_window", return_value=black),
            patch.object(capture, "_capture_dxcam", return_value=fallback),
            patch.object(capture, "_capture_mss") as mss_capture,
        ):
            packet = capture.capture(42)

        self.assertEqual(packet.backend, "dxcam")
        self.assertEqual(packet.image.shape, (360, 640, 3))
        self.assertGreater(packet.non_black_ratio, 0.9)
        self.assertIn("自动切换到 dxcam", packet.capture_warning)
        mss_capture.assert_not_called()

    def test_window_capture_reports_when_all_backends_return_black(self) -> None:
        control = FakeObservationControl()
        capture = WindowFrameCapture(control.window_region)
        black = np.zeros((360, 640, 3), dtype=np.uint8)
        with (
            patch.object(capture, "_capture_window", return_value=black),
            patch.object(capture, "_capture_dxcam", return_value=black),
            patch.object(capture, "_capture_mss", return_value=black),
        ):
            with self.assertRaisesRegex(RuntimeError, "接近全黑"):
                capture.capture(42)

    def test_adapter_keeps_generic_games_visible(self) -> None:
        image = np.full((360, 640, 3), 180, dtype=np.uint8)
        state = GameAdapterRegistry().inspect("Unknown Game", image)
        self.assertEqual(state["id"], "generic")
        self.assertEqual(state["name"], "通用游戏")
        self.assertEqual(state["canvas"], {"x": 0, "y": 0, "width": 640, "height": 360})

    def test_adapter_can_crop_a_browser_game_canvas(self) -> None:
        image = np.full((720, 1280, 3), 230, dtype=np.uint8)
        image[80:680, 100:1180] = 10
        state = GameAdapterRegistry().inspect("4399 小游戏", image)
        self.assertEqual(state["id"], "browser_game")
        self.assertTrue(state["valid"])
        self.assertGreater(state["canvas"]["width"], 1000)

    def test_realtime_perception_reports_observation_only(self) -> None:
        control = FakeObservationControl()
        with tempfile.TemporaryDirectory() as temp:
            perception = RealtimeGamePerception(control, Path(temp), target_fps=4)
            packet = FramePacket(
                frame_id=1,
                image=np.full((360, 640, 3), 90, dtype=np.uint8),
                captured_at=time.time(),
                capture_ms=3.5,
                backend="test",
                window_rect=(10, 20, 640, 360),
            )
            perception._capture.capture = MagicMock(return_value=packet)
            perception.start(hwnd=42, title="Test Game")
            try:
                snapshot = perception.snapshot()
                status = perception.status()
            finally:
                perception.stop()
        self.assertEqual(snapshot["width"], 640)
        self.assertTrue(status["running"])
        self.assertGreaterEqual(status["captured_frames"], 1)
        self.assertTrue(status["preview_url"].startswith("/api/game/capture/screen-"))
        self.assertGreaterEqual(status["preview_frame_id"], 1)
        self.assertNotIn("actions", status)
        self.assertNotIn("recording", status)

    def test_realtime_perception_emits_coalesced_visual_events(self) -> None:
        control = FakeObservationControl()
        with tempfile.TemporaryDirectory() as temp:
            perception = RealtimeGamePerception(control, Path(temp), target_fps=4)
            first = np.zeros((54, 96), dtype=np.uint8)
            changed = np.full((54, 96), 255, dtype=np.uint8)
            with (
                perception._lock,
                patch("app.game_runtime.time.monotonic", side_effect=[10.0, 12.0]),
            ):
                perception._register_visual_event(
                    frame_id=1,
                    gray=first,
                    adapter_id="generic",
                    frame_change=1.0,
                )
                perception._register_visual_event(
                    frame_id=2,
                    gray=changed,
                    adapter_id="generic",
                    frame_change=0.02,
                )

            self.assertEqual(perception._event_id, 2)
            self.assertEqual(perception._event_frame_id, 2)
            self.assertEqual(perception._event_kind, "scene")
            self.assertGreater(perception._event_change_ratio, 0.9)

    def test_realtime_perception_wait_returns_latest_event_without_worker(self) -> None:
        control = FakeObservationControl()
        with tempfile.TemporaryDirectory() as temp:
            perception = RealtimeGamePerception(control, Path(temp), target_fps=4)
            perception._event_id = 3
            perception._event_frame_id = 9
            perception._event_kind = "activity"
            perception._event_change_ratio = 0.18

            event = perception.wait_for_visual_event(2, 0.0)

        self.assertTrue(event["triggered"])
        self.assertEqual(event["event_id"], 3)
        self.assertEqual(event["kind"], "activity")

    def test_game_runtime_has_no_action_or_learning_components(self) -> None:
        control = FakeObservationControl()
        with tempfile.TemporaryDirectory() as temp:
            runtime = GameRuntime(control, Path(temp), Path(temp) / "captures")
        self.assertTrue(hasattr(runtime, "perception"))
        self.assertFalse(hasattr(runtime, "actions"))
        self.assertFalse(hasattr(runtime, "coop_p2"))
        self.assertFalse(hasattr(runtime, "recorder"))
        self.assertFalse(hasattr(runtime, "player_learning"))
        self.assertEqual(set(runtime.status()), {"perception"})


if __name__ == "__main__":
    unittest.main()

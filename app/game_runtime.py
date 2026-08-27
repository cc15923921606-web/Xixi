from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np


logger = logging.getLogger("game.runtime")


@dataclass(slots=True)
class FramePacket:
    frame_id: int
    image: np.ndarray
    captured_at: float
    capture_ms: float
    backend: str
    window_rect: tuple[int, int, int, int]
    frame_mean: float = 0.0
    non_black_ratio: float = 0.0
    capture_warning: str = ""


class WindowFrameCapture:
    """Capture the shared desktop without focusing or interacting with it."""

    def __init__(self, region_provider: Callable[[int], dict[str, int]]) -> None:
        self._region_provider = region_provider
        self._lock = threading.RLock()
        self._dxcam: Any = None
        self._dxcam_failures = 0
        self._dxcam_retry_after = 0.0
        self._frame_id = 0

    @staticmethod
    def _capture_window(hwnd: int) -> np.ndarray | None:
        try:
            from PIL import ImageGrab

            grabbed = ImageGrab.grab(window=hwnd, scale_down=False)
            image = np.asarray(grabbed)
            if image.size == 0:
                return None
            if image.ndim == 2:
                return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            if image.shape[2] == 4:
                return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        except Exception as exc:
            logger.debug("direct window capture unavailable: %s", exc)
            return None

    def _capture_dxcam(self, region: tuple[int, int, int, int]) -> np.ndarray | None:
        if time.monotonic() < self._dxcam_retry_after:
            return None
        try:
            import dxcam

            with self._lock:
                if self._dxcam is None:
                    self._dxcam = dxcam.create(output_color="BGR")
                frame = self._dxcam.grab(region=region)
            if frame is None or frame.size == 0:
                self._dxcam_retry_after = time.monotonic() + 2.0
                return None
            self._dxcam_failures = 0
            self._dxcam_retry_after = 0.0
            return np.ascontiguousarray(frame[:, :, :3])
        except Exception as exc:
            logger.debug("DXCam capture unavailable, falling back to MSS: %s", exc)
            self._dxcam_failures += 1
            self._dxcam_retry_after = time.monotonic() + min(
                60.0,
                5.0 * (2 ** min(self._dxcam_failures - 1, 3)),
            )
            self._release_dxcam()
            return None

    @staticmethod
    def _capture_mss(region: tuple[int, int, int, int]) -> np.ndarray:
        try:
            import mss
        except ImportError as exc:
            raise RuntimeError("当前环境缺少 dxcam 和 mss，无法截取游戏画面") from exc
        left, top, right, bottom = region
        with mss.mss() as capture:
            shot = capture.grab({
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
            })
        return np.ascontiguousarray(np.asarray(shot, dtype=np.uint8)[:, :, :3])

    @staticmethod
    def _frame_quality(image: np.ndarray) -> tuple[float, float, float]:
        """Return simple quality signals used to reject successful black captures."""
        if image.size == 0:
            return 0.0, 0.0, 0.0
        gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray))
        non_black_ratio = float(np.mean(gray > 10))
        histogram = cv2.calcHist([gray], [0], None, [64], [0, 256]).ravel()
        probabilities = histogram / max(float(histogram.sum()), 1.0)
        entropy = float(-np.sum(probabilities[probabilities > 0] * np.log2(probabilities[probabilities > 0])))
        return mean, non_black_ratio, entropy

    @classmethod
    def _usable_frame(cls, image: np.ndarray | None) -> bool:
        if image is None or image.size == 0 or image.ndim != 3:
            return False
        height, width = image.shape[:2]
        if width < 160 or height < 90:
            return False
        mean, non_black_ratio, entropy = cls._frame_quality(image)
        # A game may be dark, but a frame with almost no lit pixels and no
        # tonal variation is the common "capture succeeded, image is black" case.
        return not (mean <= 5.0 and non_black_ratio <= 0.02 and entropy <= 0.35)

    def capture(self, hwnd: int) -> FramePacket:
        position = self._region_provider(hwnd)
        left = int(position["left"])
        top = int(position["top"])
        width = int(position["width"])
        height = int(position["height"])
        if width < 160 or height < 90:
            raise ValueError(f"游戏窗口画面太小（{width}×{height}），请重新选择实际游戏窗口")
        region = (left, top, left + width, top + height)
        started = time.perf_counter()
        # Screen-sharing mode passes hwnd=0. In that mode the region is the
        # primary monitor and we deliberately skip all window APIs.
        attempts: list[tuple[str, np.ndarray | None]] = []
        if hwnd:
            attempts.append(("window", self._capture_window(hwnd)))
        image = attempts[0][1] if attempts else None
        if not self._usable_frame(image):
            attempts.append(("dxcam", self._capture_dxcam(region)))
            image = attempts[-1][1]
        if not self._usable_frame(image):
            attempts.append(("mss", self._capture_mss(region)))
            image = attempts[-1][1]
        if not self._usable_frame(image):
            if image is not None and image.size:
                mean, non_black_ratio, entropy = self._frame_quality(image)
                raise RuntimeError(
                    "捕获到的游戏窗口画面为空或接近全黑，"
                    f"（亮度 {mean:.1f}，有效像素 {non_black_ratio:.1%}）。"
                    "请确认游戏已显示在桌面上，或重新选择游戏窗口。"
                )
            raise RuntimeError("无法捕获游戏画面，请确认游戏窗口仍在桌面上")
        backend = next(name for name, candidate in reversed(attempts) if candidate is image)
        frame_mean, non_black_ratio, _ = self._frame_quality(image)
        attempted_backends = [name for name, candidate in attempts if candidate is not None]
        capture_warning = ""
        if hwnd and backend != "window":
            capture_warning = f"窗口捕获返回黑帧，已自动切换到 {backend}"
        self._frame_id += 1
        return FramePacket(
            frame_id=self._frame_id,
            image=image,
            captured_at=time.time(),
            capture_ms=(time.perf_counter() - started) * 1000,
            backend=backend,
            window_rect=(left, top, width, height),
            frame_mean=round(frame_mean, 2),
            non_black_ratio=round(non_black_ratio, 4),
            capture_warning=capture_warning,
        )

    def _release_dxcam(self) -> None:
        with self._lock:
            camera, self._dxcam = self._dxcam, None
        if camera is None:
            return
        try:
            camera.stop()
        except Exception:
            pass
        try:
            camera.release()
        except Exception:
            pass

    def close(self) -> None:
        self._release_dxcam()


class GameAdapterRegistry:
    """Find a likely game canvas while keeping all recognition read-only."""

    _BROWSER_GAME_HINTS = ("造梦西游", "4399", "fcbrowser", "flash")

    @staticmethod
    def _canvas_candidate(image: np.ndarray) -> tuple[int, int, int, int] | None:
        height, width = image.shape[:2]
        scale = min(1.0, 1280.0 / max(width, 1))
        sample = image if scale == 1.0 else cv2.resize(
            image,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
        gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
        dark = cv2.inRange(gray, 0, 42)
        contours, _ = cv2.findContours(dark, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        image_area = sample.shape[0] * sample.shape[1]
        candidates: list[tuple[float, tuple[int, int, int, int]]] = []
        for contour in contours:
            x, y, candidate_width, candidate_height = cv2.boundingRect(contour)
            area_ratio = candidate_width * candidate_height / max(image_area, 1)
            aspect = candidate_width / max(candidate_height, 1)
            if area_ratio < 0.28 or not 1.45 <= aspect <= 1.9:
                continue
            candidates.append((area_ratio, (x, y, candidate_width, candidate_height)))
        if not candidates:
            return None
        _, (x, y, candidate_width, candidate_height) = max(candidates, key=lambda item: item[0])
        inverse = 1.0 / scale
        return (
            max(0, round(x * inverse)),
            max(0, round(y * inverse)),
            max(20, round(candidate_width * inverse)),
            max(20, round(candidate_height * inverse)),
        )

    def inspect(self, title: str, image: np.ndarray) -> dict[str, Any]:
        image_height, image_width = image.shape[:2]
        canvas = self._canvas_candidate(image)
        title_matches = any(hint in title.casefold() for hint in self._BROWSER_GAME_HINTS)
        if canvas and title_matches:
            adapter_id, name, confidence = "browser_game", "网页游戏", 0.9
        elif canvas:
            adapter_id, name, confidence = "detected_canvas", "游戏画面", 0.7
        else:
            adapter_id, name, confidence = "generic", "通用游戏", 0.4
            canvas = (0, 0, image_width, image_height)
        x, y, width, height = canvas
        width = min(width, image_width - x)
        height = min(height, image_height - y)
        return {
            "id": adapter_id,
            "name": name,
            "confidence": confidence,
            "valid": width >= 20 and height >= 20,
            "stage": "visible",
            "canvas": {"x": x, "y": y, "width": width, "height": height},
        }


class RealtimeGamePerception:
    def __init__(
        self,
        control: Any,
        capture_dir: Path,
        *,
        target_fps: float = 8.0,
    ) -> None:
        self._control = control
        self.capture_dir = capture_dir
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self._capture = WindowFrameCapture(control.window_region)
        self._adapters = GameAdapterRegistry()
        self._target_fps = max(2.0, min(15.0, target_fps))
        self._lock = threading.RLock()
        self._event_condition = threading.Condition(self._lock)
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd = 0
        self._title = ""
        self._latest: FramePacket | None = None
        self._adapter_state: dict[str, Any] = {}
        self._previous_gray: np.ndarray | None = None
        self._event_reference_gray: np.ndarray | None = None
        self._change_ratio = 1.0
        self._reference_change_ratio = 1.0
        self._change_baseline = 0.0
        self._change_threshold = 0.025
        self._event_id = 0
        self._event_frame_id = 0
        self._event_kind = ""
        self._event_change_ratio = 0.0
        self._event_created_at = 0.0
        self._last_event_monotonic = 0.0
        self._last_adapter_id = ""
        self._fps = 0.0
        self._frame_count = 0
        self._capture_errors = 0
        self._last_error = ""
        self._started_monotonic = 0.0
        self._preview_url = ""
        self._preview_frame_id = 0
        self._preview_width = 0
        self._preview_height = 0
        self._preview_updated_at = 0.0
        self._preview_published_monotonic = 0.0

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @staticmethod
    def _change(previous: np.ndarray | None, current: np.ndarray) -> tuple[float, np.ndarray]:
        gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (96, 54), interpolation=cv2.INTER_AREA)
        if previous is None or previous.shape != gray.shape:
            return 1.0, gray
        difference = cv2.absdiff(previous, gray)
        return float(np.mean(difference) / 255.0), gray

    @staticmethod
    def _gray_change(previous: np.ndarray | None, current: np.ndarray) -> float:
        if previous is None or previous.shape != current.shape:
            return 1.0
        return float(np.mean(cv2.absdiff(previous, current)) / 255.0)

    def _register_visual_event(
        self,
        *,
        frame_id: int,
        gray: np.ndarray,
        adapter_id: str,
        frame_change: float,
    ) -> None:
        now = time.monotonic()
        reference_change = self._gray_change(self._event_reference_gray, gray)
        self._reference_change_ratio = reference_change
        if self._change_baseline <= 0:
            self._change_baseline = min(frame_change, 0.12)
        else:
            self._change_baseline = (
                self._change_baseline * 0.94 + min(frame_change, 0.20) * 0.06
            )

        event_kind = ""
        if self._event_reference_gray is None:
            event_kind = "initial"
        elif adapter_id and self._last_adapter_id and adapter_id != self._last_adapter_id:
            event_kind = "layout"
        else:
            activity_threshold = max(
                0.045,
                self._change_threshold * 1.6,
                min(0.12, self._change_baseline * 2.2),
            )
            scene_threshold = max(0.12, self._change_threshold * 4.0)
            if reference_change >= scene_threshold:
                event_kind = "scene"
            elif reference_change >= activity_threshold:
                event_kind = "activity"

        self._last_adapter_id = adapter_id
        if not event_kind:
            return
        minimum_gap = 0.0 if event_kind == "initial" else 1.25
        if now - self._last_event_monotonic < minimum_gap:
            return
        self._event_id += 1
        self._event_frame_id = int(frame_id)
        self._event_kind = event_kind
        self._event_change_ratio = reference_change
        self._event_created_at = time.time()
        self._last_event_monotonic = now
        self._event_reference_gray = gray.copy()
        self._event_condition.notify_all()

    def start(self, *, hwnd: int, title: str, change_threshold: float = 0.025) -> None:
        self.stop()
        with self._lock:
            self._hwnd = int(hwnd)
            self._title = title
            self._latest = None
            self._adapter_state = {}
            self._previous_gray = None
            self._event_reference_gray = None
            self._change_ratio = 1.0
            self._reference_change_ratio = 1.0
            self._change_baseline = 0.0
            self._change_threshold = max(0.005, min(0.25, float(change_threshold)))
            self._event_id = 0
            self._event_frame_id = 0
            self._event_kind = ""
            self._event_change_ratio = 0.0
            self._event_created_at = 0.0
            self._last_event_monotonic = 0.0
            self._last_adapter_id = ""
            self._fps = 0.0
            self._frame_count = 0
            self._capture_errors = 0
            self._last_error = ""
            self._started_monotonic = time.monotonic()
            self._preview_url = ""
            self._preview_frame_id = 0
            self._preview_width = 0
            self._preview_height = 0
            self._preview_updated_at = 0.0
            self._preview_published_monotonic = 0.0
            self._stop_event = threading.Event()
            self._ready_event = threading.Event()
            self._thread = threading.Thread(target=self._run, name="xixi-game-observer", daemon=True)
            self._thread.start()
        if not self._ready_event.wait(2.5):
            self.stop()
            raise RuntimeError("游戏画面捕获没有及时启动")
        with self._lock:
            startup_error = (self._last_error or "没有获取到游戏画面") if self._latest is None else ""
        if startup_error:
            self.stop()
            raise RuntimeError(startup_error)

    def _run(self) -> None:
        interval = 1.0 / self._target_fps
        while not self._stop_event.is_set():
            cycle_started = time.perf_counter()
            try:
                packet = self._capture.capture(self._hwnd)
                adapter_state = self._adapters.inspect(self._title, packet.image)
                canvas = adapter_state.get("canvas") or {}
                x = int(canvas.get("x") or 0)
                y = int(canvas.get("y") or 0)
                width = int(canvas.get("width") or packet.image.shape[1])
                height = int(canvas.get("height") or packet.image.shape[0])
                view = packet.image[y:y + height, x:x + width]
                if view.size == 0:
                    view = packet.image
                change_ratio, gray = self._change(self._previous_gray, view)
                self._previous_gray = gray
                self._publish_preview(packet.image, packet.frame_id)
                with self._lock:
                    self._register_visual_event(
                        frame_id=packet.frame_id,
                        gray=gray,
                        adapter_id=str(adapter_state.get("id") or ""),
                        frame_change=change_ratio,
                    )
                    self._latest = packet
                    self._adapter_state = adapter_state
                    self._change_ratio = change_ratio
                    self._frame_count += 1
                    elapsed = max(0.001, time.monotonic() - self._started_monotonic)
                    self._fps = self._frame_count / elapsed
                    self._last_error = ""
            except Exception as exc:
                with self._lock:
                    self._capture_errors += 1
                    self._last_error = str(exc)[:300]
                logger.debug("game observation capture failed: %s", exc)
            finally:
                self._ready_event.set()
            remaining = interval - (time.perf_counter() - cycle_started)
            if remaining > 0:
                self._stop_event.wait(remaining)

    def _publish_preview(self, image: np.ndarray, frame_id: int) -> None:
        now = time.monotonic()
        with self._lock:
            if now - self._preview_published_monotonic < 0.75:
                return
            self._preview_published_monotonic = now
        try:
            image_bytes = self._encode_jpeg(image, max_width=1280, quality=72)
            target = self.capture_dir / f"screen-{frame_id % 3}.jpg"
            temporary = target.with_name(f"{target.name}.tmp")
            temporary.write_bytes(image_bytes)
            temporary.replace(target)
        except Exception as exc:
            logger.debug("could not publish live screen preview: %s", exc)
            return
        with self._lock:
            self._preview_url = f"/api/game/capture/{target.name}"
            self._preview_frame_id = frame_id
            self._preview_width = int(image.shape[1])
            self._preview_height = int(image.shape[0])
            self._preview_updated_at = time.time()

    @staticmethod
    def _encode_jpeg(image: np.ndarray, *, max_width: int = 1280, quality: int = 80) -> bytes:
        height, width = image.shape[:2]
        prepared = image
        if width > max_width:
            prepared = cv2.resize(
                image,
                (max_width, max(1, round(height * max_width / width))),
                interpolation=cv2.INTER_AREA,
            )
        ok, encoded = cv2.imencode(".jpg", prepared, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("无法编码游戏画面")
        return encoded.tobytes()

    def snapshot(self, *, save_preview: bool = True) -> dict[str, Any]:
        if not self._ready_event.wait(2.0):
            raise RuntimeError("游戏观察尚未就绪")
        with self._lock:
            packet = self._latest
            adapter_state = dict(self._adapter_state)
            change_ratio = self._change_ratio
            reference_change_ratio = self._reference_change_ratio
            event_id = self._event_id
            event_frame_id = self._event_frame_id
            event_kind = self._event_kind
            event_change_ratio = self._event_change_ratio
            event_created_at = self._event_created_at
            last_error = self._last_error
        if packet is None:
            raise RuntimeError(last_error or "没有可用的游戏画面")
        canvas = adapter_state.get("canvas") or {}
        x = max(0, int(canvas.get("x") or 0))
        y = max(0, int(canvas.get("y") or 0))
        width = max(1, int(canvas.get("width") or packet.image.shape[1]))
        height = max(1, int(canvas.get("height") or packet.image.shape[0]))
        view = packet.image[y:min(packet.image.shape[0], y + height), x:min(packet.image.shape[1], x + width)]
        if view.size == 0:
            x, y = 0, 0
            view = packet.image
        image_bytes = self._encode_jpeg(view)
        preview_url = ""
        preview_path = ""
        if save_preview:
            target = self.capture_dir / f"live-{packet.frame_id % 3}.jpg"
            target.write_bytes(image_bytes)
            preview_path = str(target)
            preview_url = f"/api/game/capture/{target.name}"
        return {
            "data": image_bytes,
            "path": preview_path,
            "url": preview_url,
            "width": int(view.shape[1]),
            "height": int(view.shape[0]),
            "source_width": int(packet.image.shape[1]),
            "source_height": int(packet.image.shape[0]),
            "canvas": {"x": x, "y": y, "width": int(view.shape[1]), "height": int(view.shape[0])},
            "frame_id": packet.frame_id,
            "captured_at": packet.captured_at,
            "change_ratio": change_ratio,
            "reference_change_ratio": reference_change_ratio,
            "event_id": event_id,
            "event_frame_id": event_frame_id,
            "event_kind": event_kind,
            "event_change_ratio": event_change_ratio,
            "event_created_at": event_created_at,
            "adapter": adapter_state,
        }

    def wait_for_visual_event(self, after_event_id: int, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._event_condition:
            while (
                self.running
                and not self._stop_event.is_set()
                and self._event_id <= int(after_event_id)
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._event_condition.wait(remaining)
            return {
                "event_id": self._event_id,
                "frame_id": self._event_frame_id,
                "kind": self._event_kind,
                "change_ratio": self._event_change_ratio,
                "created_at": self._event_created_at,
                "triggered": self._event_id > int(after_event_id),
            }

    def stop(self) -> None:
        self._stop_event.set()
        with self._event_condition:
            self._event_condition.notify_all()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.5)
        self._thread = None
        self._capture.close()

    def status(self) -> dict[str, Any]:
        with self._lock:
            latest = self._latest
            return {
                "running": self.running,
                "fps": round(self._fps, 1),
                "target_fps": self._target_fps,
                "captured_frames": self._frame_count,
                "latest_frame_id": latest.frame_id if latest else 0,
                "latest_captured_at": latest.captured_at if latest else 0.0,
                "capture_ms": round(latest.capture_ms, 1) if latest else None,
                "backend": latest.backend if latest else "",
                "frame_mean": latest.frame_mean if latest else None,
                "non_black_ratio": latest.non_black_ratio if latest else None,
                "capture_warning": latest.capture_warning if latest else "",
                "preview_url": self._preview_url,
                "preview_frame_id": self._preview_frame_id,
                "preview_width": self._preview_width,
                "preview_height": self._preview_height,
                "preview_updated_at": self._preview_updated_at,
                "change_ratio": round(self._change_ratio, 4),
                "reference_change_ratio": round(self._reference_change_ratio, 4),
                "event_id": self._event_id,
                "event_frame_id": self._event_frame_id,
                "event_kind": self._event_kind,
                "event_change_ratio": round(self._event_change_ratio, 4),
                "event_created_at": self._event_created_at,
                "event_driven": True,
                "capture_errors": self._capture_errors,
                "error": self._last_error,
                "adapter": dict(self._adapter_state),
                "local_vision": {},
            }


class GameRuntime:
    """Read-only runtime used by the game companionship session."""

    def __init__(self, control: Any, data_dir: Path, capture_dir: Path) -> None:
        del data_dir
        self.control = control
        self.perception = RealtimeGamePerception(control, capture_dir)

    def start(self, game: dict[str, Any]) -> None:
        try:
            self.perception.start(
                hwnd=int(game.get("hwnd") or 0),
                title=str(game.get("window_title") or ""),
                change_threshold=float(game.get("change_threshold") or 0.025),
            )
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        self.perception.stop()

    def status(self) -> dict[str, Any]:
        return {"perception": self.perception.status()}

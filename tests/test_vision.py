from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.config import Config
from app.vision import (
    DownloadedImage,
    VisionAnalyzer,
    VisionError,
    _detect_image_mime,
    _validate_public_image_url,
)


class VisionTests(unittest.IsolatedAsyncioTestCase):
    def test_detects_supported_image_headers(self) -> None:
        self.assertEqual(_detect_image_mime(b"\x89PNG\r\n\x1a\nrest"), "image/png")
        self.assertEqual(_detect_image_mime(b"\xff\xd8\xffrest"), "image/jpeg")
        self.assertEqual(_detect_image_mime(b"GIF89arest"), "image/gif")
        self.assertEqual(
            _detect_image_mime(b"RIFF\x00\x00\x00\x00WEBPrest"),
            "image/webp",
        )
        with self.assertRaises(VisionError):
            _detect_image_mime(b"not an image")

    async def test_private_network_image_url_is_rejected(self) -> None:
        for url in (
            "http://127.0.0.1/image.png",
            "http://10.0.0.5/image.png",
            "http://[::1]/image.png",
        ):
            with self.subTest(url=url), self.assertRaises(VisionError):
                await _validate_public_image_url(url)

    async def test_analyze_limits_images_and_preserves_order(self) -> None:
        analyzer = VisionAnalyzer(
            Config(vision_max_images=2),
            api_key="test-key",
        )
        analyzer._download_image = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                DownloadedImage(b"\x89PNG\r\n\x1a\n1", "image/png"),
                DownloadedImage(b"\x89PNG\r\n\x1a\n2", "image/png"),
            ]
        )
        analyzer._analyze_images = AsyncMock(  # type: ignore[method-assign]
            return_value="看到了两张图。"
        )

        result = await analyzer.analyze(
            ["https://example.com/1.png", "https://example.com/2.png", "https://example.com/3.png"],
            "分别是什么？",
        )

        self.assertEqual(result, "看到了两张图。")
        self.assertEqual(analyzer._download_image.await_count, 2)
        requested = [call.args[1] for call in analyzer._download_image.await_args_list]
        self.assertEqual(
            requested,
            ["https://example.com/1.png", "https://example.com/2.png"],
        )

    async def test_vision_payload_contains_high_detail_data_url(self) -> None:
        analyzer = VisionAnalyzer(
            Config(vision_detail="high"),
            api_key="test-key",
            base_url="https://vision.example/v1",
        )
        captured: dict[str, object] = {}

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"choices": [{"message": {"content": "图片1：测试图。"}}]}

        class FakeClient:
            def __init__(self, **kwargs: object) -> None:
                captured["client_kwargs"] = kwargs

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def post(self, url: str, **kwargs: object) -> FakeResponse:
                captured["url"] = url
                captured.update(kwargs)
                return FakeResponse()

        with patch("app.vision.httpx.AsyncClient", FakeClient):
            result = await analyzer._analyze_images(
                [DownloadedImage(b"\x89PNG\r\n\x1a\nrest", "image/png")],
                "图里写了什么？",
            )

        self.assertEqual(result, "图片1：测试图。")
        self.assertEqual(captured["url"], "https://vision.example/v1/chat/completions")
        payload = captured["json"]
        assert isinstance(payload, dict)
        content = payload["messages"][0]["content"]  # type: ignore[index]
        image_part = next(item for item in content if item["type"] == "image_url")
        self.assertEqual(image_part["image_url"]["detail"], "high")
        self.assertTrue(image_part["image_url"]["url"].startswith("data:image/png;base64,"))

        with patch("app.vision.httpx.AsyncClient", FakeClient):
            await analyzer._analyze_images(
                [DownloadedImage(b"\x89PNG\r\n\x1a\nrest", "image/png")],
                "快速判断游戏画面",
                detail="low",
                max_tokens=320,
            )
        payload = captured["json"]
        assert isinstance(payload, dict)
        content = payload["messages"][0]["content"]  # type: ignore[index]
        image_part = next(item for item in content if item["type"] == "image_url")
        self.assertEqual(image_part["image_url"]["detail"], "low")
        self.assertEqual(payload["max_tokens"], 320)

    async def test_analyze_bytes_validates_headers_and_size(self) -> None:
        analyzer = VisionAnalyzer(
            Config(vision_max_image_bytes=256_000),
            api_key="test-key",
        )
        analyzer._analyze_images = AsyncMock(return_value="图片1：测试。")  # type: ignore[method-assign]

        result = await analyzer.analyze_bytes(
            [b"\x89PNG\r\n\x1a\nrest"],
            "看看",
        )

        self.assertEqual(result, "图片1：测试。")
        with self.assertRaises(VisionError):
            await analyzer.analyze_bytes([b"not-an-image"], "看看")
        with self.assertRaises(VisionError):
            await analyzer.analyze_bytes([b"\x89PNG\r\n\x1a\n" + b"x" * 256_001], "看看")

    async def test_primary_failure_uses_enabled_vision_fallback_and_records_usage(self) -> None:
        usage = Mock()
        analyzer = VisionAnalyzer(
            Config(vision_model="primary-vision"),
            api_key="primary-key",
            base_url="https://primary.example/v1",
            profile_provider=lambda: [{
                "id": "fallback",
                "name": "备用视觉",
                "capability": "vision",
                "base_url": "https://fallback.example/v1",
                "model_name": "fallback-vision",
                "api_type": "openai_chat",
                "enabled": True,
                "use_primary_key": False,
            }],
            credential_provider=lambda _profile: "fallback-key",
            usage_recorder=usage,
        )
        analyzer._request_candidate = AsyncMock(  # type: ignore[method-assign]
            side_effect=[VisionError("主模型不可用"), "备用模型看到了画面。"]
        )

        result = await analyzer._analyze_images(
            [DownloadedImage(b"\x89PNG\r\n\x1a\nrest", "image/png")],
            "看看画面",
        )

        self.assertEqual(result, "备用模型看到了画面。")
        self.assertEqual(analyzer._request_candidate.await_count, 2)
        fallback = analyzer._request_candidate.await_args_list[1].args[0]
        self.assertEqual(fallback["model_name"], "fallback-vision")
        self.assertEqual(fallback["api_key"], "fallback-key")
        self.assertEqual(usage.call_count, 2)
        self.assertFalse(usage.call_args_list[0].kwargs["success"])
        self.assertTrue(usage.call_args_list[1].kwargs["success"])

    async def test_game_model_override_falls_back_to_current_visual_model(self) -> None:
        analyzer = VisionAnalyzer(
            Config(vision_model="current-vision"),
            api_key="primary-key",
            base_url="https://primary.example/v1",
        )
        analyzer._request_candidate = AsyncMock(  # type: ignore[method-assign]
            side_effect=[VisionError("快速模型不可用"), "当前视觉模型完成了分析。"]
        )

        result = await analyzer._analyze_images(
            [DownloadedImage(b"\x89PNG\r\n\x1a\nrest", "image/png")],
            "快速判断游戏画面",
            model_override="fast-game-vision",
        )

        self.assertEqual(result, "当前视觉模型完成了分析。")
        models = [call.args[0]["model_name"] for call in analyzer._request_candidate.await_args_list]
        self.assertEqual(models, ["fast-game-vision", "current-vision"])


if __name__ == "__main__":
    unittest.main()

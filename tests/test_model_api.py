from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.model_api import (
    ModelAPIError,
    detect_model_api,
    discover_model_catalog,
    extract_chat_response,
    base_url_variants,
    normalize_base_url,
    request_chat_completion,
    request_ollama_chat,
)


class ModelAPITests(unittest.TestCase):
    @staticmethod
    def response(status: int, body: dict[str, object]) -> MagicMock:
        response = MagicMock(status_code=status)
        response.json.return_value = body
        response.text = ""
        return response

    def test_normalizes_full_endpoint_urls(self) -> None:
        self.assertEqual(
            normalize_base_url("https://relay.example/v1/chat/completions"),
            "https://relay.example/v1",
        )
        self.assertEqual(
            normalize_base_url("http://127.0.0.1:11434/api/chat"),
            "http://127.0.0.1:11434",
        )

    def test_adds_v1_variant_before_root_for_openai_compatible_gateways(self) -> None:
        self.assertEqual(
            base_url_variants("https://max2.jojocode.com/"),
            ["https://max2.jojocode.com/v1", "https://max2.jojocode.com"],
        )

    def test_detects_chat_completions_and_uses_bearer_key(self) -> None:
        response = self.response(
            200,
            {"choices": [{"message": {"content": "OK"}}]},
        )
        with patch("app.model_api.httpx.post", return_value=response) as post:
            result = detect_model_api(
                base_url="https://relay.example/v1",
                api_key="secret",
                model="chat-model",
                capability="language",
            )

        self.assertEqual(result["api_type"], "openai_chat")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertFalse(post.call_args.kwargs["json"]["stream"])

    def test_reads_openai_compatible_sse_response(self) -> None:
        response = self.response(200, {})
        response.json.side_effect = ValueError("not json")
        response.text = (
            'data: {"choices":[{"delta":{"content":"O"}}]}\n'
            'data: {"choices":[{"delta":{"content":"K"}}]}\n'
            "data: [DONE]\n"
        )

        self.assertEqual(extract_chat_response(response), "OK")

    def test_reports_empty_chat_response_instead_of_json_decoder_error(self) -> None:
        response = self.response(200, {})
        response.json.side_effect = ValueError("Expecting value")
        response.text = ""

        with self.assertRaisesRegex(ModelAPIError, "返回空响应"):
            extract_chat_response(response)

    def test_rejects_html_success_page_as_wrong_api_path(self) -> None:
        response = self.response(200, {})
        response.json.side_effect = ValueError("not json")
        response.headers = {"content-type": "text/html; charset=utf-8"}
        response.text = "<!doctype html><html>login</html>"

        with self.assertRaisesRegex(ModelAPIError, "网页内容.*v1"):
            extract_chat_response(response)

    def test_chat_request_forces_non_streaming_mode(self) -> None:
        response = self.response(200, {"choices": [{"message": {"content": "OK"}}]})
        with patch("app.model_api.httpx.post", return_value=response) as post:
            result = request_chat_completion(
                base_url="https://relay.example/v1",
                api_key="secret",
                model="chat-model",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=12,
                timeout=5,
            )

        self.assertEqual(result, "OK")
        self.assertFalse(post.call_args.kwargs["json"]["stream"])

    def test_detects_root_input_using_v1_chat_endpoint(self) -> None:
        response = self.response(
            200,
            {"choices": [{"message": {"content": "OK"}}]},
        )
        with patch("app.model_api.httpx.post", return_value=response) as post:
            result = detect_model_api(
                base_url="https://max2.jojocode.com/",
                api_key="secret",
                model="chat-model",
                capability="language",
            )

        self.assertEqual(result["base_url"], "https://max2.jojocode.com/v1")
        self.assertEqual(post.call_args.args[0], "https://max2.jojocode.com/v1/chat/completions")

    def test_falls_back_to_native_ollama_detection(self) -> None:
        responses = [
            self.response(404, {"error": "not found"}),
            self.response(200, {"message": {"content": "OK"}}),
        ]
        with patch("app.model_api.httpx.post", side_effect=responses) as post:
            result = detect_model_api(
                base_url="http://127.0.0.1:11434",
                api_key="",
                model="qwen2.5:3b",
                capability="language",
            )

        self.assertEqual(result["api_type"], "ollama")
        self.assertEqual(post.call_args_list[1].args[0], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["options"]["num_gpu"], 0)

    def test_local_ollama_chat_forces_cpu_execution(self) -> None:
        response = self.response(200, {"message": {"content": "OK"}})
        with patch("app.model_api.httpx.post", return_value=response) as post:
            result = request_ollama_chat(
                base_url="http://localhost:11434/v1",
                api_key="",
                model="qwen2.5:3b",
                messages=[{"role": "user", "content": "OK"}],
                max_tokens=8,
                timeout=5,
            )
        self.assertEqual(result, "OK")
        self.assertEqual(post.call_args.kwargs["json"]["options"], {"num_predict": 8, "num_gpu": 0})

    def test_authentication_error_is_not_misidentified_as_another_protocol(self) -> None:
        response = self.response(401, {"error": {"message": "invalid key"}})
        with patch("app.model_api.httpx.post", return_value=response) as post:
            with self.assertRaisesRegex(ModelAPIError, "鉴权失败"):
                detect_model_api(
                    base_url="https://relay.example/v1",
                    api_key="wrong",
                    model="chat-model",
                    capability="language",
                )
        self.assertEqual(post.call_count, 1)

    def test_detects_native_anthropic_provider(self) -> None:
        response = self.response(200, {"content": [{"type": "text", "text": "OK"}]})
        with patch("app.model_api.httpx.post", return_value=response) as post:
            result = detect_model_api(
                base_url="https://api.anthropic.com/v1",
                api_key="anthropic-key",
                model="claude-sonnet",
                capability="language",
            )

        self.assertEqual(result["api_type"], "anthropic")
        self.assertEqual(post.call_args.args[0], "https://api.anthropic.com/v1/messages")
        self.assertEqual(post.call_args.kwargs["headers"]["x-api-key"], "anthropic-key")

    def test_detects_native_gemini_provider(self) -> None:
        response = self.response(
            200,
            {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]},
        )
        with patch("app.model_api.httpx.post", return_value=response) as post:
            result = detect_model_api(
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key="gemini-secret",
                model="gemini-2.5-flash",
                capability="language",
            )

        self.assertEqual(result["api_type"], "gemini")
        self.assertEqual(
            post.call_args.args[0],
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        )
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "gemini-secret")

    def test_discovers_openai_compatible_models(self) -> None:
        response = self.response(
            200,
            {"data": [{"id": "model-b"}, {"id": "model-a"}]},
        )
        with patch("app.model_api.httpx.get", return_value=response) as get:
            result = discover_model_catalog(
                base_url="https://relay.example/v1",
                api_key="secret",
            )

        self.assertEqual([item["id"] for item in result["models"]], ["model-a", "model-b"])
        self.assertEqual(get.call_args.args[0], "https://relay.example/v1/models")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer secret")


if __name__ == "__main__":
    unittest.main()

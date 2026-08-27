from __future__ import annotations

import base64
import json
import time
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx


API_TYPE_AUTO = "auto"
API_TYPE_OPENAI_RESPONSES = "openai_responses"
API_TYPE_OPENAI_CHAT = "openai_chat"
API_TYPE_OLLAMA = "ollama"
API_TYPE_ANTHROPIC = "anthropic"
API_TYPE_GEMINI = "gemini"
SUPPORTED_API_TYPES = frozenset(
    {
        API_TYPE_OPENAI_RESPONSES,
        API_TYPE_OPENAI_CHAT,
        API_TYPE_OLLAMA,
        API_TYPE_ANTHROPIC,
        API_TYPE_GEMINI,
    }
)
API_TYPE_LABELS = {
    API_TYPE_AUTO: "等待自动识别",
    API_TYPE_OPENAI_RESPONSES: "OpenAI Responses",
    API_TYPE_OPENAI_CHAT: "Chat Completions",
    API_TYPE_OLLAMA: "Ollama",
    API_TYPE_ANTHROPIC: "Anthropic Messages",
    API_TYPE_GEMINI: "Google Gemini",
}
OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"
_TEST_IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ModelAPIError(RuntimeError):
    pass


class ModelAPINotMatched(ModelAPIError):
    pass


def normalize_base_url(value: str) -> str:
    base_url = str(value or "").strip().rstrip("/")
    if not base_url:
        return ""
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("API 地址必须是有效的 http 或 https 地址")
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/messages", "/api/chat"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunparse(parsed._replace(path=path, params="", query="", fragment="")).rstrip("/")


def base_url_variants(value: str) -> list[str]:
    """Return compatible API roots, preferring the conventional OpenAI /v1 root."""
    endpoint = normalize_base_url(value)
    if not endpoint:
        return []
    parsed = urlparse(endpoint)
    path = parsed.path.rstrip("/")
    variants = [endpoint]
    if (parsed.hostname or "").casefold() in {"127.0.0.1", "localhost", "::1"} and parsed.port == 11434:
        return variants
    if not path.endswith(("/v1", "/v1beta")):
        v1 = urlunparse(parsed._replace(path=f"{path}/v1" if path else "/v1"))
        variants.insert(0, v1.rstrip("/"))
    return list(dict.fromkeys(variants))


def infer_saved_api_type(value: str, base_url: str, *, capability: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in SUPPORTED_API_TYPES:
        return normalized
    hostname = (urlparse(base_url).hostname or "").casefold()
    if capability == "language" and hostname == "api.openai.com":
        return API_TYPE_OPENAI_RESPONSES
    if "anthropic" in hostname:
        return API_TYPE_ANTHROPIC
    if "googleapis.com" in hostname or "generativelanguage" in hostname:
        return API_TYPE_GEMINI
    return API_TYPE_OPENAI_CHAT


def api_type_label(api_type: str) -> str:
    return API_TYPE_LABELS.get(api_type, API_TYPE_LABELS[API_TYPE_AUTO])


def auth_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def protocol_headers(api_key: str, api_type: str) -> dict[str, str]:
    """Return authentication headers for the selected provider protocol."""
    if api_type == API_TYPE_ANTHROPIC:
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if api_key.strip():
            headers["x-api-key"] = api_key.strip()
        return headers
    if api_type == API_TYPE_GEMINI:
        headers = {"Content-Type": "application/json"}
        if api_key.strip():
            headers["x-goog-api-key"] = api_key.strip()
        return headers
    return auth_headers(api_key)


def _response_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:180]
    if not isinstance(body, dict):
        return str(body)[:180]
    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("detail") or "")[:180]
    return str(body.get("message") or body.get("detail") or error or "")[:180]


def _raise_for_endpoint(response: httpx.Response, label: str) -> None:
    if response.status_code in {404, 405}:
        raise ModelAPINotMatched(f"{label} 端点不存在")
    if response.status_code in {401, 403}:
        raise ModelAPIError(f"{label} 鉴权失败，请检查 API 密钥")
    if response.status_code >= 400:
        detail = _response_detail(response)
        suffix = f"：{detail}" if detail else ""
        raise ModelAPIError(f"{label} 返回 HTTP {response.status_code}{suffix}")


def extract_chat_text(body: dict[str, Any]) -> str:
    content: Any = None
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else None
        delta = first.get("delta") if isinstance(first, dict) else None
        if isinstance(message, dict):
            content = message.get("content")
        if content is None and isinstance(delta, dict):
            content = delta.get("content")
        if content is None and isinstance(first, dict):
            content = first.get("text")
    if content is None and body.get("output_text"):
        content = body.get("output_text")
    if content is None and isinstance(body.get("content"), (str, list)):
        content = body.get("content")
    if content is None:
        raise ModelAPIError("Chat Completions 返回格式无法读取")
    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text") or item.get("content") or "")
            for item in content
            if isinstance(item, dict)
        )
    result = str(content or "").strip()
    if not result:
        raise ModelAPIError("Chat Completions 返回了空内容")
    return result


def _extract_sse_chat_text(value: str) -> str:
    """Collect text from OpenAI-compatible SSE responses when a relay ignores stream=false."""
    parts: list[str] = []
    for line in value.splitlines():
        line = line.strip()
        if not line or line.startswith(":") or line.startswith("event:"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            try:
                text = extract_chat_text(payload)
            except ModelAPIError:
                text = ""
            if text:
                parts.append(text)
    return "".join(parts).strip()


def extract_chat_response(response: httpx.Response, label: str = "Chat Completions") -> str:
    """Read JSON, SSE, or a plain-text response without leaking JSON decoder errors."""
    try:
        body = response.json()
    except (TypeError, ValueError):
        text = response.text.strip()
        streamed = _extract_sse_chat_text(text) if text else ""
        if streamed:
            return streamed
        content_type = str(response.headers.get("content-type") or "").casefold()
        if "text/html" in content_type or text.startswith("<"):
            raise ModelAPIError(
                f"{label} 返回了网页内容，请确认 API 地址包含正确的 /v1 接口路径"
            )
        if text and not text.startswith("<"):
            return text[:20_000]
        if not text:
            raise ModelAPIError(f"{label} 返回空响应，请确认供应商支持非流式 Chat Completions")
        raise ModelAPIError(f"{label} 返回了无法解析的内容")
    if not isinstance(body, dict):
        raise ModelAPIError(f"{label} 返回格式无法读取")
    return extract_chat_text(body)


def extract_responses_text(body: dict[str, Any]) -> str:
    direct = str(body.get("output_text") or "").strip()
    if direct:
        return direct
    parts: list[str] = []
    output = body.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                    parts.append(str(part.get("text") or ""))
    result = "\n".join(part for part in parts if part).strip()
    if not result:
        raise ModelAPIError("Responses API 返回了空内容")
    return result


def extract_ollama_text(body: dict[str, Any]) -> str:
    message = body.get("message")
    result = str(message.get("content") if isinstance(message, dict) else "").strip()
    if not result:
        raise ModelAPIError("Ollama 返回了空内容")
    return result


def extract_anthropic_text(body: dict[str, Any]) -> str:
    content = body.get("content")
    parts = (
        [str(item.get("text") or "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        if isinstance(content, list)
        else []
    )
    result = "\n".join(parts).strip()
    if not result:
        raise ModelAPIError("Anthropic 返回了空内容")
    return result


def extract_gemini_text(body: dict[str, Any]) -> str:
    parts: list[str] = []
    candidates = body.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            values = content.get("parts") if isinstance(content, dict) else None
            if isinstance(values, list):
                parts.extend(
                    str(item.get("text") or "")
                    for item in values
                    if isinstance(item, dict) and item.get("text")
                )
    result = "\n".join(parts).strip()
    if not result:
        raise ModelAPIError("Gemini 返回了空内容")
    return result


def _chat_payload(model: str, capability: str) -> dict[str, Any]:
    if capability == "vision":
        encoded = base64.b64encode(_TEST_IMAGE).decode("ascii")
        content: Any = [
            {"type": "text", "text": "Reply with OK only."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "low"},
            },
        ]
    else:
        content = "Reply with OK only."
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 12,
        "stream": False,
    }


def _ollama_payload(model: str, capability: str) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "user", "content": "Reply with OK only."}
    if capability == "vision":
        message["images"] = [base64.b64encode(_TEST_IMAGE).decode("ascii")]
    return {
        "model": model,
        "messages": [message],
        "stream": False,
        "options": {"num_predict": 12},
    }


def _anthropic_payload(model: str, capability: str) -> dict[str, Any]:
    content: Any = "Reply with OK only."
    if capability == "vision":
        content = [
            {"type": "text", "text": "Reply with OK only."},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(_TEST_IMAGE).decode("ascii"),
                },
            },
        ]
    return {
        "model": model,
        "max_tokens": 12,
        "messages": [{"role": "user", "content": content}],
    }


def _gemini_payload(capability: str) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"text": "Reply with OK only."}]
    if capability == "vision":
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": base64.b64encode(_TEST_IMAGE).decode("ascii"),
            }
        })
    return {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"maxOutputTokens": 12},
    }


def _test_responses(base_url: str, api_key: str, model: str, timeout: float) -> str:
    response = httpx.post(
        f"{base_url}/responses",
        headers=auth_headers(api_key),
        json={"model": model, "input": "Reply with OK only.", "max_output_tokens": 12},
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Responses API")
    return extract_responses_text(response.json())


def _test_chat(
    base_url: str,
    api_key: str,
    model: str,
    capability: str,
    timeout: float,
) -> str:
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers=auth_headers(api_key),
        json=_chat_payload(model, capability),
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Chat Completions")
    return extract_chat_response(response)


def _test_chat_variants(
    base_url: str,
    api_key: str,
    model: str,
    capability: str,
    timeout: float,
) -> tuple[str, str]:
    errors: list[Exception] = []
    variants = base_url_variants(base_url)
    for endpoint in variants:
        try:
            _test_chat(endpoint, api_key, model, capability, timeout)
            return endpoint, ""
        except ModelAPINotMatched as exc:
            errors.append(exc)
        except ModelAPIError as exc:
            errors.append(exc)
            format_mismatch = any(
                marker in str(exc)
                for marker in ("返回格式", "无法解析", "返回空响应", "返回了空内容")
            )
            if format_mismatch:
                continue
            raise
    detail = "；".join(str(error) for error in errors) or "Chat Completions 端点不存在"
    raise ModelAPINotMatched(detail)


def ollama_root(base_url: str) -> str:
    return base_url[:-3] if base_url.endswith("/v1") else base_url


def is_local_ollama_url(base_url: str) -> bool:
    """Identify the local Ollama service so its machine-specific safeguards apply."""
    if not str(base_url or "").strip():
        return True
    hostname = (urlparse(str(base_url)).hostname or "").casefold()
    return hostname in {"127.0.0.1", "localhost", "::1"}


def _test_ollama(
    base_url: str,
    api_key: str,
    model: str,
    capability: str,
    timeout: float,
) -> tuple[str, str]:
    root = ollama_root(base_url)
    payload = _ollama_payload(model, capability)
    if is_local_ollama_url(root):
        payload["options"]["num_gpu"] = 0
    response = httpx.post(
        f"{root}/api/chat",
        headers=auth_headers(api_key),
        json=payload,
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Ollama")
    return extract_ollama_text(response.json()), root


def _test_anthropic(
    base_url: str,
    api_key: str,
    model: str,
    capability: str,
    timeout: float,
) -> str:
    response = httpx.post(
        f"{base_url}/messages",
        headers=protocol_headers(api_key, API_TYPE_ANTHROPIC),
        json=_anthropic_payload(model, capability),
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Anthropic Messages")
    return extract_anthropic_text(response.json())


def _test_gemini(
    base_url: str,
    api_key: str,
    model: str,
    capability: str,
    timeout: float,
) -> str:
    model_path = model.removeprefix("models/")
    response = httpx.post(
        f"{base_url}/models/{quote(model_path, safe='')}:generateContent",
        headers=protocol_headers(api_key, API_TYPE_GEMINI),
        json=_gemini_payload(capability),
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Google Gemini")
    return extract_gemini_text(response.json())


def detect_model_api(
    *,
    base_url: str,
    api_key: str,
    model: str,
    capability: str,
    timeout: float = 20.0,
) -> dict[str, Any]:
    endpoint = normalize_base_url(base_url)
    if not endpoint:
        raise ValueError("请填写 API 地址")
    model = str(model or "").strip()
    if not model or len(model) > 200:
        raise ValueError("模型名称无效")
    if capability not in {"language", "vision"}:
        raise ValueError("模型能力类型无效")

    hostname = (urlparse(endpoint).hostname or "").casefold()
    if "anthropic" in hostname:
        candidates = [API_TYPE_ANTHROPIC, API_TYPE_OPENAI_CHAT, API_TYPE_OLLAMA]
    elif "googleapis.com" in hostname or "generativelanguage" in hostname:
        candidates = [API_TYPE_GEMINI, API_TYPE_OPENAI_CHAT, API_TYPE_OLLAMA]
    elif capability == "language" and hostname == "api.openai.com":
        candidates = [API_TYPE_OPENAI_RESPONSES, API_TYPE_OPENAI_CHAT]
    else:
        candidates = [API_TYPE_OPENAI_CHAT, API_TYPE_OLLAMA, API_TYPE_ANTHROPIC, API_TYPE_GEMINI]
    started = time.monotonic()
    unmatched: list[str] = []
    try:
        for api_type in candidates:
            try:
                if api_type == API_TYPE_OPENAI_RESPONSES:
                    _test_responses(endpoint, api_key, model, timeout)
                elif api_type == API_TYPE_OPENAI_CHAT:
                    endpoint, _ = _test_chat_variants(
                        endpoint, api_key, model, capability, timeout
                    )
                elif api_type == API_TYPE_OLLAMA:
                    _, endpoint = _test_ollama(
                        endpoint, api_key, model, capability, timeout
                    )
                elif api_type == API_TYPE_ANTHROPIC:
                    _test_anthropic(endpoint, api_key, model, capability, timeout)
                else:
                    _test_gemini(endpoint, api_key, model, capability, timeout)
                latency = round((time.monotonic() - started) * 1000)
                return {
                    "ok": True,
                    "api_type": api_type,
                    "api_label": api_type_label(api_type),
                    "provider": urlparse(endpoint).hostname or endpoint,
                    "base_url": endpoint,
                    "model": model,
                    "capability": capability,
                    "latency_ms": latency,
                    "message": f"已识别 {api_type_label(api_type)} · {latency} ms",
                }
            except ModelAPINotMatched as exc:
                unmatched.append(str(exc))
                continue
    except httpx.TimeoutException as exc:
        raise ModelAPIError("连接测试超时，请检查 API 地址或网络") from exc
    except httpx.HTTPError as exc:
        raise ModelAPIError(f"无法连接模型接口：{str(exc)[:160]}") from exc
    detail = "；".join(unmatched) or "没有接口返回可识别的数据"
    raise ModelAPIError(f"无法自动识别接口类型：{detail}")


def discover_model_catalog(
    *,
    base_url: str,
    api_key: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Read a provider model catalog without exposing its credential."""
    endpoint = normalize_base_url(base_url)
    if not endpoint:
        raise ValueError("请填写 API 地址")
    hostname = (urlparse(endpoint).hostname or "").casefold()
    if "anthropic" in hostname:
        candidates = [API_TYPE_ANTHROPIC]
    elif "googleapis.com" in hostname or "generativelanguage" in hostname:
        candidates = [API_TYPE_GEMINI]
    elif hostname in {"127.0.0.1", "localhost"} and ":11434" in endpoint:
        candidates = [API_TYPE_OLLAMA, API_TYPE_OPENAI_CHAT]
    else:
        candidates = [API_TYPE_OPENAI_CHAT, API_TYPE_OLLAMA]

    unmatched: list[str] = []
    try:
        for api_type in candidates:
            if api_type == API_TYPE_OLLAMA:
                endpoint_candidates = [ollama_root(endpoint)]
            elif api_type == API_TYPE_OPENAI_CHAT:
                endpoint_candidates = base_url_variants(endpoint)
            else:
                endpoint_candidates = [endpoint]
            response = None
            selected_endpoint = endpoint
            for selected_endpoint in endpoint_candidates:
                catalog_url = (
                    f"{selected_endpoint}/api/tags"
                    if api_type == API_TYPE_OLLAMA
                    else f"{selected_endpoint}/models"
                )
                response = httpx.get(
                    catalog_url,
                    headers=protocol_headers(api_key, api_type),
                    timeout=timeout,
                )
                if response.status_code not in {404, 405}:
                    break
            if response is None:
                continue
            if response.status_code in {404, 405}:
                unmatched.append(f"{api_type_label(api_type)} 不提供模型列表")
                continue
            if response.status_code in {401, 403}:
                raise ModelAPIError("获取模型列表鉴权失败，请检查 API 密钥")
            if response.status_code >= 400:
                detail = _response_detail(response)
                suffix = f"：{detail}" if detail else ""
                raise ModelAPIError(f"获取模型列表返回 HTTP {response.status_code}{suffix}")
            try:
                body = response.json()
            except (TypeError, ValueError) as exc:
                raise ModelAPIError(
                    "获取模型列表返回了无法解析的内容，请确认 API 地址是模型接口地址"
                ) from exc
            if not isinstance(body, dict):
                raise ModelAPIError("获取模型列表返回格式无法读取")
            rows = body.get("models", []) if api_type in {API_TYPE_OLLAMA, API_TYPE_GEMINI} else body.get("data", [])
            models: list[dict[str, str]] = []
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    model_id = str(row.get("id") or row.get("name") or row.get("model") or "").strip()
                    if api_type == API_TYPE_GEMINI:
                        model_id = model_id.removeprefix("models/")
                    if not model_id or len(model_id) > 200:
                        continue
                    display_name = str(row.get("display_name") or row.get("displayName") or model_id).strip()
                    models.append({"id": model_id, "name": display_name[:120]})
            models = list({item["id"]: item for item in models}.values())
            models.sort(key=lambda item: item["id"].casefold())
            return {
                "ok": True,
                "api_type": api_type,
                "api_label": api_type_label(api_type),
                "provider": urlparse(endpoint).hostname or endpoint,
                "base_url": selected_endpoint,
                "models": models[:500],
                "count": len(models),
            }
    except httpx.TimeoutException as exc:
        raise ModelAPIError("获取模型列表超时，请检查 API 地址或网络") from exc
    except httpx.HTTPError as exc:
        raise ModelAPIError(f"无法连接供应商：{str(exc)[:160]}") from exc
    detail = "；".join(unmatched) or "供应商没有返回模型目录"
    raise ModelAPIError(f"无法获取模型列表：{detail}，仍可手动填写模型 ID")


def request_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    timeout: float,
) -> str:
    response = httpx.post(
        f"{normalize_base_url(base_url)}/chat/completions",
        headers=auth_headers(api_key),
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Chat Completions")
    return extract_chat_response(response)


def request_ollama_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    timeout: float,
) -> str:
    root = ollama_root(normalize_base_url(base_url))
    options: dict[str, Any] = {"num_predict": max_tokens}
    if is_local_ollama_url(root):
        options["num_gpu"] = 0
    response = httpx.post(
        f"{root}/api/chat",
        headers=auth_headers(api_key),
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        },
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Ollama")
    return extract_ollama_text(response.json())


def request_anthropic_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    timeout: float,
) -> str:
    system = "\n\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "system"
    )
    user_messages = [message for message in messages if message.get("role") != "system"]
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": user_messages,
    }
    if system:
        payload["system"] = system
    response = httpx.post(
        f"{normalize_base_url(base_url)}/messages",
        headers=protocol_headers(api_key, API_TYPE_ANTHROPIC),
        json=payload,
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Anthropic Messages")
    return extract_anthropic_text(response.json())


def request_gemini_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    timeout: float,
) -> str:
    system = "\n\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "system"
    )
    contents: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "system":
            continue
        role = "model" if message.get("role") == "assistant" else "user"
        raw_content = message.get("content")
        raw_parts = raw_content if isinstance(raw_content, list) else [raw_content]
        parts = [{"text": str(part.get("text") or "") if isinstance(part, dict) else str(part or "")} for part in raw_parts]
        contents.append({"role": role, "parts": parts})
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    model_path = model.removeprefix("models/")
    response = httpx.post(
        f"{normalize_base_url(base_url)}/models/{quote(model_path, safe='')}:generateContent",
        headers=protocol_headers(api_key, API_TYPE_GEMINI),
        json=payload,
        timeout=timeout,
    )
    _raise_for_endpoint(response, "Google Gemini")
    return extract_gemini_text(response.json())

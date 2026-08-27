from __future__ import annotations

import re


_INTERNAL_PROTOCOL_MARKER_RE = re.compile(
    r"\bCPA\b|传输协议|输出协议|响应协议|"
    r"transport\s+protocol|response\s+protocol|output\s+protocol",
    re.IGNORECASE,
)
_INTERNAL_FINAL_MARKER_RE = re.compile(
    r"最终(?:回答|答案|输出|回复)|final\s+(?:answer|output|response)",
    re.IGNORECASE,
)
_INTERNAL_REQUIREMENT_MARKER_RE = re.compile(
    r"要求|规则|规范|约束|必须|应当|需要|requirements?|rules?|constraints?|must|should",
    re.IGNORECASE,
)
_INTERNAL_STANDALONE_RE = re.compile(
    r"保留模型的原生决定"
    r"|正确的下一步输出是.{0,56}(?:工具|tool)"
    r"|(?:普通的)?助手文本.{0,32}(?:最终|输出)"
    r"|(?:system|developer|assistant)\s+(?:message|prompt|instruction)"
    r"|(?:analysis|commentary|final)\s+(?:channel|通道)"
    r"|(?:系统|开发者|助手)(?:消息|提示词|指令)\s*[：:]"
    r"|(?:内部|隐藏)(?:提示词|指令|协议|规则)\s*[：:]",
    re.IGNORECASE,
)


def find_internal_instruction_start(text: str) -> int | None:
    """Find the first position of leaked model/runtime instructions."""
    value = str(text or "")
    standalone = _INTERNAL_STANDALONE_RE.search(value)
    starts = [standalone.start()] if standalone else []

    protocol_matches = list(_INTERNAL_PROTOCOL_MARKER_RE.finditer(value))
    final_matches = list(_INTERNAL_FINAL_MARKER_RE.finditer(value))
    requirement_matches = list(_INTERNAL_REQUIREMENT_MARKER_RE.finditer(value))
    for protocol in protocol_matches:
        window_start = max(0, protocol.start() - 96)
        window_end = min(len(value), protocol.end() + 128)
        nearby_final = [
            match
            for match in final_matches
            if match.start() < window_end and match.end() > window_start
        ]
        if not nearby_final:
            continue
        nearby_requirement = any(
            match.start() < window_end and match.end() > window_start
            for match in requirement_matches
        )
        if not nearby_requirement and protocol.group(0).strip().casefold() != "cpa":
            continue
        candidates = [protocol.start(), *(match.start() for match in nearby_final)]
        cpa = re.search(r"\bCPA\b", value[window_start:window_end], re.IGNORECASE)
        if cpa:
            candidates.append(window_start + cpa.start())
        starts.append(min(candidates))

    return min(starts) if starts else None


def has_internal_instruction(text: str) -> bool:
    return find_internal_instruction_start(text) is not None


def strip_internal_instruction(text: str) -> str:
    value = str(text or "")
    start = find_internal_instruction_start(value)
    if start is None:
        return value
    return value[:start].rstrip(" \t\r\n，,；;：:-")

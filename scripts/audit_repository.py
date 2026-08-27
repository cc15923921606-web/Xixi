from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRIVATE_DENYLIST = ROOT / "packaging" / "private_release_denylist.txt"
MAX_GIT_FILE_BYTES = 95 * 1024 * 1024

SECRET_PATTERNS = (
    re.compile(rb"sk-proj-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"sk-(?!ecdsa-sha2-)[A-Za-z0-9_-]{24,}"),
    re.compile(rb"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._-]{16,}"),
    re.compile(rb"(?i)(api[_-]?key|password|secret)\s*[:=]\s*[\"'][^\"']{16,}[\"']"),
)
WINDOWS_USER_PATH = re.compile(rb"(?i)[A-Z]:\\Users\\[^\\\r\n\t\"']+")
TEXT_SUFFIXES = {
    ".bat",
    ".css",
    ".html",
    ".ini",
    ".iss",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".spec",
    ".txt",
    ".yaml",
    ".yml",
}
BLOCKED_FILE_NAMES = {
    ".env",
    "interest_profile.json",
    "knowledge.txt",
    "persona.txt",
    "private_release_denylist.txt",
}
BLOCKED_ROOTS = {
    "logs",
    "temp",
    "venv",
    "whisper-large-v3-ct2",
    "whisper-small-full",
}
BLOCKED_PACKAGING_DIRS = {"build", "dist", "staging", "private_assets"}
ALLOWED_DATA_FILES = {
    ("data", "readme.md"),
    ("data", "voice_assets", "readme.md"),
}
ALLOWED_RUNTIME_FILES = {("runtime", "readme.md")}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def private_values() -> tuple[str, ...]:
    if not PRIVATE_DENYLIST.is_file():
        return ()
    values = []
    for line in PRIVATE_DENYLIST.read_text(encoding="utf-8-sig").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            values.append(value)
    return tuple(dict.fromkeys(values))


def encoded_needles(values: tuple[str, ...]) -> list[tuple[str, bytes]]:
    needles = []
    for value in values:
        for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
            needles.append((value, value.encode(encoding)))
    return needles


def blocked_path(relative: Path) -> str | None:
    parts = tuple(part.casefold() for part in relative.parts)
    if not parts:
        return None
    if relative.name.casefold() in BLOCKED_FILE_NAMES:
        return "private runtime file"
    if parts[0] in BLOCKED_ROOTS or "__pycache__" in parts:
        return "generated or machine-local directory"
    if parts[0] == "data" and parts not in ALLOWED_DATA_FILES:
        return "personal data or private voice asset"
    if parts[0] == "runtime" and parts not in ALLOWED_RUNTIME_FILES:
        return "downloaded runtime"
    if parts[0] == "packaging" and len(parts) > 1:
        if parts[1] in BLOCKED_PACKAGING_DIRS:
            return "build output or private release input"
        if parts[1] in {"voice_nltk_data", "voice_verification_fixtures"}:
            if relative.name.casefold() != "readme.md":
                return "private release fixture"
    if relative.suffix.casefold() in {".exe", ".msi", ".pth", ".ckpt", ".whl"}:
        return "release binary or model weight"
    return None


def audit() -> list[str]:
    findings = []
    values = private_values()
    needles = encoded_needles(values)
    for path in tracked_files():
        relative = path.relative_to(ROOT)
        reason = blocked_path(relative)
        if reason:
            findings.append(f"{relative}: {reason}")
            continue
        if not path.is_file():
            findings.append(f"{relative}: tracked path is missing")
            continue
        size = path.stat().st_size
        if size > MAX_GIT_FILE_BYTES:
            findings.append(f"{relative}: file exceeds 95 MiB")
        data = path.read_bytes()
        for label, needle in needles:
            if needle and needle in data:
                findings.append(f"{relative}: contains private denylist value {label!r}")
        if path.suffix.casefold() in TEXT_SUFFIXES:
            if WINDOWS_USER_PATH.search(data):
                findings.append(f"{relative}: contains a local Windows user path")
            for pattern in SECRET_PATTERNS:
                if pattern.search(data):
                    findings.append(f"{relative}: contains credential-like text")
                    break
    return findings


def main() -> int:
    try:
        findings = audit()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Repository audit could not run: {exc}")
        return 2
    if findings:
        print("\n".join(findings))
        return 1
    print(f"Repository audit passed: {len(tracked_files())} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

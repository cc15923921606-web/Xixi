from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRIVATE_DENYLIST = PROJECT_ROOT / "packaging" / "private_release_denylist.txt"
SECRET_PATTERNS = (
    re.compile(rb"sk-proj-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"sk-(?!ecdsa-sha2-)[A-Za-z0-9_-]{24,}"),
    re.compile(rb"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._-]{16,}"),
)
WINDOWS_USER_PATH = re.compile(
    rb"(?i)[A-Z]:\\Users\\[^\\\r\n\t\"']+"
)

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
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
FIRST_PARTY_DIRS = {"data", "runtime", "studio"}
TRUSTED_BINARY_SECRET_SCAN_EXCLUSIONS = {
    ("runtime", "install_tools", "uv.exe"),
}


def load_private_denylist() -> tuple[str, ...]:
    configured = os.environ.get("XIXI_RELEASE_DENYLIST", "").strip()
    source = Path(configured).expanduser() if configured else DEFAULT_PRIVATE_DENYLIST
    if not source.is_file():
        return ()
    values = []
    for raw_line in source.read_text(encoding="utf-8-sig").splitlines():
        value = raw_line.strip()
        if value and not value.startswith("#"):
            values.append(value)
    return tuple(dict.fromkeys(values))


def encoded_needles(texts: tuple[str, ...]) -> list[tuple[str, bytes]]:
    values: list[tuple[str, bytes]] = []
    for text in texts:
        for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
            values.append((text, text.encode(encoding)))
    return values


def is_first_party_text(path: Path, target: Path) -> bool:
    if path.suffix.casefold() not in TEXT_SUFFIXES:
        return False
    if target.is_file():
        return True
    relative = path.relative_to(target)
    return len(relative.parts) == 1 or relative.parts[0].casefold() in FIRST_PARTY_DIRS


def audit_file(
    path: Path,
    target: Path,
    *,
    private_values: tuple[str, ...],
    archive_only: bool = False,
) -> list[str]:
    data = path.read_bytes()
    findings = []
    relative = path.relative_to(target) if target.is_dir() else Path(path.name)
    relative_key = tuple(part.casefold() for part in relative.parts)
    text_needles = encoded_needles(private_values) if is_first_party_text(path, target) else (
        (text, text.encode("ascii"))
        for text in private_values
        if text.isascii()
    )
    for label, needle in text_needles:
        if needle and needle in data:
            findings.append(f"{path}: forbidden text {label!r}")
    if not archive_only and is_first_party_text(path, target):
        if WINDOWS_USER_PATH.search(data):
            findings.append(f"{path}: local Windows user path")
    trusted_binary = relative_key in TRUSTED_BINARY_SECRET_SCAN_EXCLUSIONS and data.startswith(b"MZ")
    if not trusted_binary:
        for pattern in SECRET_PATTERNS:
            if pattern.search(data):
                findings.append(f"{path}: possible API credential")
    if not archive_only and private_values:
        lowered = path.name.casefold()
        if any(value.casefold() in lowered for value in private_values if len(value) >= 3):
            findings.append(f"{path}: private value in filename")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--archive-only", action="store_true")
    args = parser.parse_args()
    target = args.target.resolve()
    private_values = load_private_denylist()
    files = [target] if target.is_file() else [
        item
        for item in target.rglob("*")
        if item.is_file()
        and item.suffix.casefold() != ".pyc"
        and "__pycache__" not in {part.casefold() for part in item.parts}
    ]
    findings: list[str] = []
    for path in files:
        findings.extend(
            audit_file(
                path,
                target,
                private_values=private_values,
                archive_only=args.archive_only,
            )
        )
    if findings:
        print("\n".join(findings))
        return 1
    print(f"Privacy audit passed: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

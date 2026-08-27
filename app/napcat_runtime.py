from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

try:
    import winreg
except ImportError:  # pragma: no cover - Windows is the supported desktop target.
    winreg = None  # type: ignore[assignment]


_REGISTRY_KEY = r"Software\Xixi\Components"
_REGISTRY_VALUE = "NapCatRoot"
_LAUNCHER_NAME = "launcher-user.bat"
_NAPCAT_DIRECTORY_NAMES = ("NapCat", "napcat", "NapCat.Shell", "NapCatQQ")
_SKIPPED_DRIVE_DIRECTORIES = frozenset({
    "$recycle.bin",
    "program files",
    "program files (x86)",
    "programdata",
    "recovery",
    "system volume information",
    "windows",
})


def napcat_root_ready(root: Path) -> bool:
    root = Path(root)
    return all(
        (root / name).is_file()
        for name in (
            _LAUNCHER_NAME,
            "napcat.mjs",
            "NapCatWinBootHook.dll",
            "NapCatWinBootMain.exe",
        )
    )


def provision_packaged_napcat(app_root: Path, components_root: Path) -> Path | None:
    """Copy or upgrade the bundled runtime in the writable component area.

    Older public builds can pass the basic readiness check while still missing
    a newly bundled config or runtime dependency. Merge the package on every
    provisioning pass so an in-place upgrade repairs those installs without
    deleting account-specific QQ data.
    """
    target = Path(components_root) / "NapCat"
    packaged = Path(app_root) / "runtime" / "components" / "NapCat"
    if not napcat_root_ready(packaged):
        if napcat_root_ready(target):
            register_napcat_root(target)
            return target
        return None
    target.mkdir(parents=True, exist_ok=True)
    for item in packaged.rglob("*"):
        destination = target / item.relative_to(packaged)
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        relative = item.relative_to(packaged)
        user_config = bool(relative.parts and relative.parts[0].casefold() == "config")
        should_copy = not destination.is_file()
        if not should_copy and not user_config:
            source_stat = item.stat()
            destination_stat = destination.stat()
            should_copy = (
                destination_stat.st_size != source_stat.st_size
                or destination_stat.st_mtime_ns < source_stat.st_mtime_ns
            )
        if should_copy:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
    if not napcat_root_ready(target):
        return None
    register_napcat_root(target)
    return target


def _path_is_ascii(path: Path) -> bool:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _windows_short_path(path: Path) -> Path | None:
    if os.name != "nt":
        return None
    try:
        get_short_path = ctypes.windll.kernel32.GetShortPathNameW
        size = int(get_short_path(str(path), None, 0))
        if size <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(size)
        if int(get_short_path(str(path), buffer, size)) <= 0:
            return None
    except (AttributeError, OSError):
        return None
    candidate = Path(buffer.value)
    return candidate if _path_is_ascii(candidate) and napcat_root_ready(candidate) else None


def _junction_bases() -> tuple[Path, ...]:
    system_drive = os.environ.get("SystemDrive", "C:")
    program_data = Path(os.environ.get("ProgramData", f"{system_drive}\\ProgramData"))
    public = Path(os.environ.get("PUBLIC", f"{system_drive}\\Users\\Public"))
    return (
        program_data / "XixiRuntime" / "NapCatAliases",
        public / "XixiRuntime" / "NapCatAliases",
    )


def _subst_output() -> dict[str, Path]:
    if os.name != "nt":
        return {}
    try:
        result = subprocess.run(
            ["subst"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    mappings: dict[str, Path] = {}
    for line in result.stdout.splitlines():
        match = re.match(r"^\s*([A-Z]):\\:\s*=>\s*(.+?)\s*$", line, re.IGNORECASE)
        if match:
            mappings[f"{match.group(1).upper()}:\\"] = Path(match.group(2))
    return mappings


def _napcat_mapping_file() -> Path:
    data_dir = os.environ.get("XIXI_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / "qq_napcat_mapping.json"
    return Path.home() / ".xixi" / "qq_napcat_mapping.json"


def _napcat_launch_copy_file() -> Path:
    data_dir = os.environ.get("XIXI_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / "qq_napcat_launch_copy.json"
    return Path.home() / ".xixi" / "qq_napcat_launch_copy.json"


def _read_napcat_launch_copy() -> tuple[Path, Path] | None:
    try:
        payload = json.loads(_napcat_launch_copy_file().read_text(encoding="utf-8"))
        source = Path(str(payload.get("source") or ""))
        launch_root = Path(str(payload.get("launch_root") or ""))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if not str(source) or not str(launch_root):
        return None
    return source, launch_root


def _write_napcat_launch_copy(source: Path, launch_root: Path) -> None:
    path = _napcat_launch_copy_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"source": str(source), "launch_root": str(launch_root)},
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )


def _managed_launch_copy(source: Path, launch_root: Path) -> bool:
    digest = hashlib.sha256(str(source).casefold().encode("utf-8")).hexdigest()[:16]
    try:
        resolved = launch_root.resolve()
    except OSError:
        resolved = launch_root.absolute()
    return (
        resolved.name.casefold() == digest.casefold()
        and resolved.parent.name.casefold() == "napcat"
        and resolved.parent.parent.name.casefold() == "xixiruntime"
        and not _is_directory_link(resolved)
    )


def active_napcat_launch_root(source: Path) -> Path | None:
    state = _read_napcat_launch_copy()
    if state is None:
        return None
    recorded_source, launch_root = state
    try:
        same_source = recorded_source.resolve() == Path(source).resolve()
    except OSError:
        same_source = str(recorded_source).casefold() == str(source).casefold()
    if same_source and napcat_root_ready(launch_root):
        return launch_root
    return None


def _read_napcat_mapping() -> tuple[str, Path] | None:
    try:
        payload = json.loads(_napcat_mapping_file().read_text(encoding="utf-8"))
        drive = str(payload.get("drive") or "").upper()
        target = Path(str(payload.get("target") or ""))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if re.fullmatch(r"[A-Z]:\\", drive) and str(target):
        return drive, target
    return None


def _write_napcat_mapping(drive: str, target: Path) -> None:
    path = _napcat_mapping_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"drive": drive, "target": str(target)}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def release_napcat_launch_root() -> None:
    mapping = _read_napcat_mapping()
    if mapping is not None:
        drive, target = mapping
        current = _subst_output().get(drive)
        try:
            if current is not None and current.resolve() == target.resolve():
                subprocess.run(
                    ["subst", drive.rstrip("\\"), "/d"],
                    capture_output=True,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
        except (OSError, subprocess.SubprocessError):
            pass
        _napcat_mapping_file().unlink(missing_ok=True)

    launch_copy = _read_napcat_launch_copy()
    if launch_copy is not None:
        source, launch_root = launch_copy
        if _managed_launch_copy(source, launch_root):
            shutil.rmtree(launch_root, ignore_errors=True)
            for parent in (launch_root.parent, launch_root.parent.parent):
                try:
                    parent.rmdir()
                except OSError:
                    break
    _napcat_launch_copy_file().unlink(missing_ok=True)


def _is_directory_link(path: Path) -> bool:
    try:
        attributes = int(os.lstat(path).st_file_attributes)
    except (AttributeError, OSError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def ensure_napcat_launch_root(root: Path) -> Path:
    """Return an ASCII path that NapCat's Windows injector can load.

    NapCat's Windows injector can fail before logging when its module path
    contains non-ASCII characters. ``subst`` drives and directory junctions
    are resolved back to the original Unicode path by this injector, so use a
    short-lived physical runtime copy under the nearest writable ASCII parent.
    Account settings remain in the user's selected data directory.
    """
    resolved = Path(root).resolve()
    if not napcat_root_ready(resolved):
        raise FileNotFoundError(f"QQ 通道文件不完整：{resolved}")
    if _path_is_ascii(resolved):
        return resolved

    short_path = _windows_short_path(resolved)
    if short_path is not None:
        return short_path

    active = active_napcat_launch_root(resolved)
    if active is not None:
        return active

    digest = hashlib.sha256(str(resolved).casefold().encode("utf-8")).hexdigest()[:16]
    bases: list[Path] = []
    for parent in resolved.parents:
        if _path_is_ascii(parent):
            bases.append(parent / "XixiRuntime" / "NapCat")
            break
    bases.extend(base / "XixiRuntime" / "NapCat" for base in _junction_bases())
    errors: list[str] = []
    for base in bases:
        if not _path_is_ascii(base):
            continue
        launch_root = base / digest
        try:
            base.mkdir(parents=True, exist_ok=True)
            if launch_root.exists() and _is_directory_link(launch_root):
                os.rmdir(launch_root)
            launch_root.mkdir(parents=True, exist_ok=True)
            for item in resolved.rglob("*"):
                destination = launch_root / item.relative_to(resolved)
                if item.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                should_copy = not destination.is_file()
                if not should_copy:
                    source_stat = item.stat()
                    destination_stat = destination.stat()
                    should_copy = (
                        source_stat.st_size != destination_stat.st_size
                        or source_stat.st_mtime_ns > destination_stat.st_mtime_ns
                    )
                if should_copy:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, destination)
            if napcat_root_ready(launch_root):
                _write_napcat_launch_copy(resolved, launch_root)
                return launch_root
            errors.append(f"{launch_root} 文件复制后仍不完整")
        except OSError as exc:
            errors.append(str(exc))
    detail = "；".join(error for error in errors if error)[-600:]
    raise RuntimeError(
        "QQ 通道所在路径包含中文，且无法创建兼容运行副本。"
        + (f" 详细信息：{detail}" if detail else "")
    )


def napcat_qrcode_candidates(root: Path) -> tuple[Path, ...]:
    root = Path(root)
    roots = [root]
    active = active_napcat_launch_root(root)
    if active is not None and active != root:
        roots.append(active)
    candidates: list[Path] = []
    for candidate_root in roots:
        candidates.extend((
            candidate_root / "cache" / "qrcode.png",
            candidate_root / "logs" / "qrcode.png",
            candidate_root / "qrcode.png",
        ))
        for directory in (candidate_root / "cache", candidate_root / "logs"):
            try:
                candidates.extend(sorted(directory.glob("*qrcode*.png"), reverse=True))
            except OSError:
                continue
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return tuple(unique)


def find_napcat_qrcode(root: Path) -> Path | None:
    available: list[Path] = []
    for candidate in napcat_qrcode_candidates(root):
        try:
            if candidate.is_file() and candidate.stat().st_size > 64:
                available.append(candidate)
        except OSError:
            continue
    if not available:
        return None
    return max(available, key=lambda path: path.stat().st_mtime_ns)


def clear_napcat_qrcodes(root: Path) -> None:
    for candidate in napcat_qrcode_candidates(root):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            continue


def find_napcat_root(root: Path, *, max_depth: int = 3) -> Path | None:
    candidate = Path(root).expanduser()
    if candidate.is_file():
        return candidate.parent if candidate.name.casefold() == _LAUNCHER_NAME else None
    if not candidate.is_dir():
        return None

    queue: list[tuple[Path, int]] = [(candidate, 0)]
    seen: set[str] = set()
    while queue:
        current, depth = queue.pop(0)
        try:
            key = str(current.resolve()).casefold()
        except OSError:
            key = str(current).casefold()
        if key in seen:
            continue
        seen.add(key)
        if napcat_root_ready(current):
            return current
        if depth >= max_depth:
            continue
        try:
            children = [item for item in current.iterdir() if item.is_dir()]
        except OSError:
            continue
        queue.extend((child, depth + 1) for child in children)
    return None


def registered_napcat_root() -> Path | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _REGISTRY_VALUE)
    except OSError:
        return None
    text = str(value or "").strip().strip('"')
    return Path(os.path.expandvars(os.path.expanduser(text))) if text else None


def register_napcat_root(root: Path) -> None:
    if winreg is None or not napcat_root_ready(root):
        return
    resolved = Path(root).resolve()
    try:
        existing = registered_napcat_root()
        if existing is not None and existing.resolve() == resolved:
            return
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as key:
            winreg.SetValueEx(key, _REGISTRY_VALUE, 0, winreg.REG_SZ, str(resolved))
    except OSError:
        return


def _fixed_drive_roots() -> tuple[Path, ...]:
    if os.name != "nt":
        return ()
    try:
        mask = int(ctypes.windll.kernel32.GetLogicalDrives())
        get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
    except (AttributeError, OSError):
        return ()
    roots: list[Path] = []
    for index in range(26):
        if not mask & (1 << index):
            continue
        root = Path(f"{chr(65 + index)}:\\")
        try:
            drive_type = int(get_drive_type(str(root)))
        except OSError:
            continue
        if drive_type in {2, 3}:  # removable or fixed drive
            roots.append(root)
    return tuple(roots)


def _common_candidates(app_root: Path, components_root: Path) -> Iterable[Path]:
    home = Path.home()
    local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    bases = (
        components_root,
        app_root / "runtime",
        app_root,
        app_root.parent,
        home,
        home / "Downloads",
        home / "Desktop",
        local_app_data,
        local_app_data / "Programs",
    )
    for base in bases:
        for name in _NAPCAT_DIRECTORY_NAMES:
            yield base / name


def _drive_candidates() -> Iterable[Path]:
    for drive in _fixed_drive_roots():
        for name in _NAPCAT_DIRECTORY_NAMES:
            yield drive / name
        try:
            children = [item for item in drive.iterdir() if item.is_dir()]
        except OSError:
            continue
        for child in children:
            if child.name.casefold() in _SKIPPED_DRIVE_DIRECTORIES:
                continue
            if "napcat" in child.name.casefold():
                yield child
            for name in _NAPCAT_DIRECTORY_NAMES:
                yield child / name


@lru_cache(maxsize=16)
def _discover_napcat_root(app_root: str, components_root: str) -> Path | None:
    candidates = (
        *_common_candidates(Path(app_root), Path(components_root)),
        *_drive_candidates(),
    )
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).casefold()
        except OSError:
            key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        found = find_napcat_root(candidate)
        if found is not None:
            register_napcat_root(found)
            return found
    return None


def resolve_napcat_root(
    app_root: Path,
    components_root: Path,
    environ: Mapping[str, str] | None = None,
    *,
    discover: bool = True,
) -> Path | None:
    values = os.environ if environ is None else environ
    configured = str(values.get("NAPCAT_ROOT") or "").strip().strip('"')
    configured_root = (
        Path(os.path.expandvars(os.path.expanduser(configured)))
        if configured
        else None
    )
    candidates = (
        configured_root,
        Path(components_root) / "NapCat",
        Path(app_root) / "runtime" / "components" / "NapCat",
        Path(app_root) / "runtime" / "NapCat",
        Path(app_root).parent / "napcat",
        Path(app_root).parent / "NapCat",
        registered_napcat_root(),
    )
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            key = str(candidate.resolve()).casefold()
        except OSError:
            key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        found = find_napcat_root(candidate)
        if found is not None:
            register_napcat_root(found)
            return found
    if discover:
        return _discover_napcat_root(
            str(Path(app_root).resolve()),
            str(Path(components_root).resolve()),
        )
    return None

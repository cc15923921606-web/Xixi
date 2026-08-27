from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


DATA_POINTER_FILENAME = "数据目录.txt"
RUNTIME_CONFIG_FILENAME = "运行配置.json"
MIGRATION_MANIFEST_FILENAME = "迁移清单.json"
MIGRATION_FAILURE_FILENAME = "迁移失败记录.json"
_RESOURCE_DATA_DIRS = frozenset({"voice_assets"})
_WEBVIEW_DATA_DIRS = frozenset({"desktop_webview", "edge_studio_profile"})
_DOWNLOAD_DATA_DIRS = frozenset({"environment_downloads"})
_IMMUTABLE_RUNTIME_DIRS = frozenset({"components", "voice"})
_PUBLIC_PROGRAM_DIR_NAMES = frozenset({"程序文件"})
_PACKAGED_COMPONENT_SEEDS = (
    (Path("runtime") / "components" / "NapCat", Path("NapCat")),
)


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _public_install_root(app_root: Path) -> Path:
    if app_root.name.casefold() in {name.casefold() for name in _PUBLIC_PROGRAM_DIR_NAMES}:
        return app_root.parent
    return app_root


@dataclass(frozen=True)
class RuntimePaths:
    app_root: Path
    public_release: bool
    data_home: Path
    data_dir: Path
    webview_dir: Path
    logs_dir: Path
    downloads_dir: Path
    components_dir: Path
    models_dir: Path
    pointer_file: Path
    runtime_config_file: Path
    migration_manifest_file: Path

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.webview_dir,
            self.logs_dir,
            self.downloads_dir,
            self.components_dir,
            self.models_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalized_path(value: str, app_root: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(value.strip().strip('"')))
    path = Path(expanded)
    if not path.is_absolute():
        path = app_root / path
    return path.resolve()


def _default_public_data_home(app_root: Path) -> Path:
    install_root = _public_install_root(app_root)
    if install_root != app_root:
        return install_root / "用户数据"
    return app_root.with_name(f"{app_root.name}数据")


def _read_data_home(
    app_root: Path,
    environ: Mapping[str, str],
) -> tuple[Path, bool]:
    configured = str(environ.get("XIXI_DATA_HOME") or "").strip()
    pointer_file = app_root / DATA_POINTER_FILENAME
    if configured:
        return _normalized_path(configured, app_root), pointer_file.is_file()
    try:
        pointer_value = next(
            line.strip()
            for line in pointer_file.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        )
    except (FileNotFoundError, OSError, StopIteration):
        return _default_public_data_home(app_root).resolve(), False
    return _normalized_path(pointer_value, app_root), True


def _public_paths(app_root: Path, data_home: Path) -> RuntimePaths:
    return RuntimePaths(
        app_root=app_root,
        public_release=True,
        data_home=data_home,
        data_dir=data_home / "运行数据",
        webview_dir=data_home / "WebView数据",
        logs_dir=data_home / "日志",
        downloads_dir=data_home / "下载",
        components_dir=data_home / "本地组件",
        models_dir=data_home / "本地模型",
        pointer_file=app_root / DATA_POINTER_FILENAME,
        runtime_config_file=data_home / RUNTIME_CONFIG_FILENAME,
        migration_manifest_file=data_home / MIGRATION_MANIFEST_FILENAME,
    )


def _personal_paths(app_root: Path) -> RuntimePaths:
    data_dir = app_root / "data"
    return RuntimePaths(
        app_root=app_root,
        public_release=False,
        data_home=app_root,
        data_dir=data_dir,
        webview_dir=data_dir,
        logs_dir=app_root / "logs",
        downloads_dir=data_dir / "environment_downloads",
        components_dir=app_root / "runtime",
        models_dir=app_root,
        pointer_file=app_root / DATA_POINTER_FILENAME,
        runtime_config_file=data_dir / RUNTIME_CONFIG_FILENAME,
        migration_manifest_file=data_dir / MIGRATION_MANIFEST_FILENAME,
    )


def _legacy_public_paths(app_root: Path) -> RuntimePaths:
    legacy_root = _public_install_root(app_root)
    return RuntimePaths(
        app_root=app_root,
        public_release=True,
        data_home=legacy_root,
        data_dir=legacy_root / "data",
        webview_dir=legacy_root / "data",
        logs_dir=legacy_root / "logs",
        downloads_dir=legacy_root / "data" / "environment_downloads",
        components_dir=legacy_root / "runtime",
        models_dir=legacy_root,
        pointer_file=app_root / DATA_POINTER_FILENAME,
        runtime_config_file=legacy_root / "data" / RUNTIME_CONFIG_FILENAME,
        migration_manifest_file=legacy_root / "data" / MIGRATION_MANIFEST_FILENAME,
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_destination(base: Path, relative: Path) -> Path:
    destination = (base / relative).resolve()
    resolved_base = base.resolve()
    if destination != resolved_base and resolved_base not in destination.parents:
        raise RuntimeError(f"迁移目标越界：{relative.as_posix()}")
    return destination


def _copy_verified(source: Path, destination: Path) -> dict[str, object]:
    if source.is_symlink():
        raise RuntimeError(f"拒绝迁移符号链接：{source}")
    source_size = source.stat().st_size
    source_hash = _hash_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink():
            raise RuntimeError(f"迁移目标不能是符号链接：{destination}")
        if destination.stat().st_size != source_size or _hash_file(destination) != source_hash:
            raise RuntimeError(f"迁移目标已有不同内容：{destination}")
    else:
        temporary = destination.with_name(f".{destination.name}.migrating-{uuid.uuid4().hex}")
        try:
            shutil.copy2(source, temporary)
            if temporary.stat().st_size != source_size or _hash_file(temporary) != source_hash:
                raise RuntimeError(f"迁移校验失败：{source}")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return {
        "source": str(source),
        "destination": str(destination),
        "size": source_size,
        "sha256": source_hash,
    }


def _legacy_files(paths: RuntimePaths) -> list[tuple[Path, Path]]:
    app_root = _public_install_root(paths.app_root)
    legacy_data = app_root / "data"
    items: list[tuple[Path, Path]] = []
    for name in (
        "persona.txt",
        "interest_profile.json",
        "knowledge.txt",
        "learning_sources.json",
        "meme_lexicon.json",
    ):
        source = app_root / name
        if source.is_file():
            items.append((source, _safe_destination(paths.data_dir, Path(name))))
    if legacy_data.is_symlink():
        raise RuntimeError(f"拒绝迁移符号链接目录：{legacy_data}")
    if legacy_data.is_dir():
        for source in legacy_data.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(legacy_data)
            if relative.parts and relative.parts[0].casefold() in _RESOURCE_DATA_DIRS:
                continue
            first = relative.parts[0].casefold() if relative.parts else ""
            if first in _WEBVIEW_DATA_DIRS:
                destination = _safe_destination(paths.webview_dir, relative)
            elif first in _DOWNLOAD_DATA_DIRS:
                destination = _safe_destination(paths.downloads_dir, Path(*relative.parts[1:]))
            else:
                destination = _safe_destination(paths.data_dir, relative)
            items.append((source, destination))
    legacy_logs = app_root / "logs"
    if legacy_logs.is_symlink():
        raise RuntimeError(f"拒绝迁移符号链接目录：{legacy_logs}")
    if legacy_logs.is_dir():
        for source in legacy_logs.rglob("*"):
            if source.is_file():
                items.append(
                    (source, _safe_destination(paths.logs_dir, source.relative_to(legacy_logs)))
                )
    legacy_runtime = app_root / "runtime"
    if legacy_runtime.is_symlink():
        raise RuntimeError(f"拒绝迁移符号链接目录：{legacy_runtime}")
    if legacy_runtime.is_dir():
        for source in legacy_runtime.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(legacy_runtime)
            if relative.parts and relative.parts[0].casefold() in _IMMUTABLE_RUNTIME_DIRS:
                continue
            items.append((source, _safe_destination(paths.components_dir, relative)))
    return items


def _seed_public_files(paths: RuntimePaths) -> list[dict[str, object]]:
    seeded: list[dict[str, object]] = []
    for name in (
        "persona.txt",
        "interest_profile.json",
        "knowledge.txt",
        "learning_sources.json",
        "meme_lexicon.json",
    ):
        source = paths.app_root / name
        destination = paths.data_dir / name
        if source.is_file() and not destination.exists():
            seeded.append(_copy_verified(source, destination))
    return seeded


def _seed_public_components(paths: RuntimePaths) -> list[dict[str, object]]:
    """Copy packaged component files into writable user data without overwriting it."""
    seeded: list[dict[str, object]] = []
    for source_relative, destination_relative in _PACKAGED_COMPONENT_SEEDS:
        source_root = paths.app_root / source_relative
        if not source_root.is_dir():
            continue
        if source_root.is_symlink():
            raise RuntimeError(f"拒绝使用符号链接组件目录：{source_root}")
        destination_root = _safe_destination(paths.components_dir, destination_relative)
        for source in source_root.rglob("*"):
            if source.is_symlink():
                raise RuntimeError(f"拒绝复制符号链接组件：{source}")
            relative = source.relative_to(source_root)
            destination = _safe_destination(destination_root, relative)
            if source.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if destination.exists():
                continue
            seeded.append(_copy_verified(source, destination))
    return seeded


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_pointer(paths: RuntimePaths) -> None:
    temporary = paths.pointer_file.with_name(f".{DATA_POINTER_FILENAME}.tmp")
    try:
        temporary.write_text(f"{paths.data_home}\n", encoding="utf-8")
        temporary.replace(paths.pointer_file)
    finally:
        temporary.unlink(missing_ok=True)


def _initialize_public_paths(paths: RuntimePaths, *, migrate_legacy: bool) -> None:
    paths.ensure_directories()
    migrated: list[dict[str, object]] = []
    if migrate_legacy:
        for source, destination in _legacy_files(paths):
            migrated.append(_copy_verified(source, destination))
    seeded = _seed_public_files(paths)
    seeded_components = _seed_public_components(paths)
    now = _utc_now()
    manifest = {
        "schema_version": 1,
        "created_at_utc": now,
        "source_root": str(paths.app_root),
        "data_home": str(paths.data_home),
        "migrated_files": migrated,
        "seeded_files": seeded,
        "seeded_components": seeded_components,
    }
    if migrate_legacy or not paths.migration_manifest_file.is_file():
        _write_json_atomic(paths.migration_manifest_file, manifest)
    _write_json_atomic(
        paths.runtime_config_file,
        {
            "schema_version": 2,
            "edition": "public",
            "app_root": str(paths.app_root),
            "data_root": str(paths.data_home),
            "runtime_data": str(paths.data_dir),
            "webview_data": str(paths.webview_dir),
            "logs": str(paths.logs_dir),
            "downloads": str(paths.downloads_dir),
            "components": str(paths.components_dir),
            "models": str(paths.models_dir),
            "migration_manifest": str(paths.migration_manifest_file),
            "updated_at_utc": now,
        },
    )
    _write_pointer(paths)


def _record_migration_failure(paths: RuntimePaths, exc: Exception) -> None:
    try:
        _write_json_atomic(
            paths.data_home / MIGRATION_FAILURE_FILENAME,
            {
                "schema_version": 1,
                "failed_at_utc": _utc_now(),
                "source_root": str(paths.app_root),
                "data_home": str(paths.data_home),
                "error": str(exc),
            },
        )
    except OSError:
        pass


def resolve_runtime_paths(
    app_root: Path | None = None,
    *,
    public_release: bool | None = None,
    environ: Mapping[str, str] | None = None,
    initialize: bool = True,
) -> RuntimePaths:
    root = Path(app_root or application_root()).resolve()
    is_public = bool(getattr(sys, "frozen", False)) if public_release is None else public_release
    if not is_public:
        paths = _personal_paths(root)
        if initialize:
            paths.ensure_directories()
        return paths

    values = os.environ if environ is None else environ
    if str(values.get("XIXI_LAYOUT") or "").strip().casefold() == "legacy":
        fallback = _legacy_public_paths(root)
        if initialize:
            fallback.ensure_directories()
        return fallback
    data_home, pointer_existed = _read_data_home(root, values)
    paths = _public_paths(root, data_home)
    if not initialize:
        return paths
    try:
        needs_migration = not paths.runtime_config_file.is_file()
        _initialize_public_paths(paths, migrate_legacy=needs_migration)
        return paths
    except Exception as exc:
        _record_migration_failure(paths, exc)
        fallback = _legacy_public_paths(root)
        fallback.ensure_directories()
        return fallback


def activate_runtime_environment(paths: RuntimePaths) -> None:
    legacy_layout = paths.public_release and paths.data_dir == paths.app_root / "data"
    os.environ["XIXI_LAYOUT"] = "legacy" if legacy_layout else "external"
    os.environ["XIXI_DATA_HOME"] = str(paths.data_home)
    os.environ["XIXI_DATA_DIR"] = str(paths.data_dir)
    os.environ["XIXI_LOG_DIR"] = str(paths.logs_dir)
    os.environ["XIXI_DOWNLOAD_DIR"] = str(paths.downloads_dir)
    os.environ["XIXI_COMPONENTS_DIR"] = str(paths.components_dir)
    os.environ["XIXI_MODELS_DIR"] = str(paths.models_dir)


_ACTIVE_PATHS: RuntimePaths | None = None


def get_runtime_paths() -> RuntimePaths:
    global _ACTIVE_PATHS
    if _ACTIVE_PATHS is None:
        _ACTIVE_PATHS = resolve_runtime_paths()
        activate_runtime_environment(_ACTIVE_PATHS)
    return _ACTIVE_PATHS

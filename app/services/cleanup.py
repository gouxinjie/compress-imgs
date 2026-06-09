from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings


MANAGED_RUNTIME_DIR_NAMES = ("uploads", "compressed", "zips", "tasks")


def migrate_legacy_runtime_layout(settings: Settings) -> None:
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)

    for directory_name in MANAGED_RUNTIME_DIR_NAMES:
        legacy_dir = settings.temp_dir / directory_name
        target_dir = settings.runtime_dir / directory_name
        if not legacy_dir.exists() or legacy_dir == target_dir:
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        for child in legacy_dir.iterdir():
            target_path = target_dir / child.name
            if target_path.exists():
                continue
            try:
                child.rename(target_path)
            except OSError:
                continue

        try:
            legacy_dir.rmdir()
        except OSError:
            pass


def ensure_directories(settings: Settings) -> None:
    for path in (
        settings.temp_dir,
        settings.runtime_dir,
        settings.uploads_dir,
        settings.compressed_dir,
        settings.zips_dir,
        settings.tasks_dir,
        settings.static_dir / "css",
        settings.static_dir / "js",
    ):
        path.mkdir(parents=True, exist_ok=True)


def cleanup_expired_files(settings: Settings) -> None:
    expire_before = datetime.now(timezone.utc) - timedelta(minutes=settings.file_expire_minutes)

    expired_task_ids: list[str] = []
    for task_file in settings.tasks_dir.glob("*.json"):
        if not _is_expired(task_file, expire_before):
            continue
        expired_task_ids.append(task_file.stem)

    for task_id in expired_task_ids:
        _remove_task_runtime_artifacts(settings, task_id)

    protected_task_ids = {task_file.stem for task_file in settings.tasks_dir.glob("*.json")}
    _cleanup_orphan_runtime_artifacts(settings, expire_before, protected_task_ids)


def _remove_task_runtime_artifacts(settings: Settings, task_id: str) -> None:
    uploads_removed = _remove_dir(settings.uploads_dir / task_id)
    compressed_removed = _remove_dir(settings.compressed_dir / task_id)
    zip_path = settings.zips_dir / f"{task_id}.zip"
    zip_removed = _safe_unlink(zip_path) if zip_path.exists() else True

    if uploads_removed and compressed_removed and zip_removed:
        _safe_unlink(settings.tasks_dir / f"{task_id}.json")


def _cleanup_orphan_runtime_artifacts(
    settings: Settings,
    expire_before: datetime,
    protected_task_ids: set[str],
) -> None:
    for child in settings.uploads_dir.iterdir():
        if child.name in protected_task_ids:
            continue
        if _is_expired(child, expire_before):
            _remove_path(child)

    for child in settings.compressed_dir.iterdir():
        if child.name in protected_task_ids:
            continue
        if _is_expired(child, expire_before):
            _remove_path(child)

    for child in settings.zips_dir.iterdir():
        if child.stem in protected_task_ids:
            continue
        if _is_expired(child, expire_before):
            _remove_path(child)

    for child in settings.tasks_dir.iterdir():
        if child.suffix == ".json":
            continue
        if _is_expired(child, expire_before):
            _remove_path(child)

    for child in settings.runtime_dir.iterdir():
        if child.name in MANAGED_RUNTIME_DIR_NAMES:
            continue
        if _is_expired(child, expire_before):
            _remove_path(child)


def _is_expired(path: Path, expire_before: datetime) -> bool:
    try:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except FileNotFoundError:
        return False
    return modified_at < expire_before


def _remove_path(path: Path) -> bool:
    if path.is_dir():
        return _remove_dir(path)
    return _safe_unlink(path)


def _remove_dir(path: Path) -> bool:
    if not path.exists():
        return True

    fully_removed = True
    for child in path.iterdir():
        if child.is_dir():
            fully_removed = _remove_dir(child) and fully_removed
            continue
        if not _safe_unlink(child):
            fully_removed = False

    try:
        path.rmdir()
    except OSError:
        return False
    return fully_removed


def _safe_unlink(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True

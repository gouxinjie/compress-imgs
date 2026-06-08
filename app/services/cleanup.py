from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings


def ensure_directories(settings: Settings) -> None:
    for path in (
        settings.temp_dir,
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

    for task_file in settings.tasks_dir.glob("*.json"):
        try:
            modified_at = datetime.fromtimestamp(task_file.stat().st_mtime, tz=timezone.utc)
        except FileNotFoundError:
            continue

        if modified_at >= expire_before:
            continue

        task_id = task_file.stem
        task_file.unlink(missing_ok=True)
        _remove_dir(settings.uploads_dir / task_id)
        _remove_dir(settings.compressed_dir / task_id)
        zip_path = settings.zips_dir / f"{task_id}.zip"
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)


def _remove_dir(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
    try:
        path.rmdir()
    except OSError:
        return

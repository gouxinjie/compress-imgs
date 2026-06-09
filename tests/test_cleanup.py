from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.services import cleanup


def _touch(path: Path, *, minutes_ago: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")

    timestamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).timestamp()
    path.touch()
    path.chmod(path.stat().st_mode)
    os.utime(path, (timestamp, timestamp))


class CleanupExpiredFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.settings = Settings(
            app_name="CompressImgs",
            tinify_api_key="",
            max_files_per_upload=10,
            max_file_size_mb=10,
            max_request_size_mb=100,
            temp_dir=self.base_dir / "work" / "tmp",
            file_expire_minutes=60,
            poll_interval_ms=1000,
            rate_limit_per_minute=5,
            allowed_extensions=("png", "jpg", "jpeg", "webp"),
        )
        cleanup.ensure_directories(self.settings)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cleanup_keeps_active_task_artifacts_even_if_artifact_mtime_is_old(self) -> None:
        task_id = "task_active"
        task_file = self.settings.tasks_dir / f"{task_id}.json"
        uploads_dir = self.settings.uploads_dir / task_id
        compressed_dir = self.settings.compressed_dir / task_id
        zip_path = self.settings.zips_dir / f"{task_id}.zip"

        uploads_dir.mkdir(parents=True, exist_ok=True)
        compressed_dir.mkdir(parents=True, exist_ok=True)
        _touch(uploads_dir / "image.png", minutes_ago=120)
        _touch(compressed_dir / "image.png", minutes_ago=120)
        _touch(zip_path, minutes_ago=120)
        _touch(task_file, minutes_ago=5)

        cleanup.cleanup_expired_files(self.settings)

        self.assertTrue(task_file.exists())
        self.assertTrue(uploads_dir.exists())
        self.assertTrue(compressed_dir.exists())
        self.assertTrue(zip_path.exists())

    def test_cleanup_preserves_task_json_when_runtime_artifact_removal_is_incomplete(self) -> None:
        task_id = "task_expired"
        task_file = self.settings.tasks_dir / f"{task_id}.json"
        uploads_dir = self.settings.uploads_dir / task_id
        compressed_dir = self.settings.compressed_dir / task_id
        zip_path = self.settings.zips_dir / f"{task_id}.zip"

        uploads_dir.mkdir(parents=True, exist_ok=True)
        compressed_dir.mkdir(parents=True, exist_ok=True)
        _touch(zip_path, minutes_ago=120)
        _touch(task_file, minutes_ago=120)

        original_safe_unlink = cleanup._safe_unlink

        def flaky_safe_unlink(path: Path) -> bool:
            if path == zip_path:
                return False
            return original_safe_unlink(path)

        with patch("app.services.cleanup._safe_unlink", side_effect=flaky_safe_unlink):
            cleanup.cleanup_expired_files(self.settings)

        self.assertTrue(task_file.exists())
        self.assertTrue(zip_path.exists())
        self.assertFalse(uploads_dir.exists())
        self.assertFalse(compressed_dir.exists())


if __name__ == "__main__":
    unittest.main()

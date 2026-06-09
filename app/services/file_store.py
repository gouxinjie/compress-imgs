from __future__ import annotations

import re
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from app.config import Settings


FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class UploadLimitError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class FileStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_task_id(self) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = secrets.token_hex(3)
        return f"task_{stamp}_{suffix}"

    def prepare_task_dirs(self, task_id: str) -> tuple[Path, Path]:
        upload_dir = self.settings.uploads_dir / task_id
        compressed_dir = self.settings.compressed_dir / task_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        compressed_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir, compressed_dir

    async def save_upload(
        self,
        upload: UploadFile,
        upload_dir: Path,
        existing_names: set[str],
        *,
        max_file_size_bytes: int,
        max_request_remaining_bytes: int,
    ) -> dict[str, object]:
        original_name = Path(upload.filename or "image").name
        safe_name = self._dedupe_filename(self._sanitize_filename(original_name), existing_names)
        target_path = upload_dir / safe_name

        size = 0
        try:
            with target_path.open("wb") as buffer:
                while chunk := await upload.read(1024 * 1024):
                    next_size = size + len(chunk)
                    if next_size > max_file_size_bytes:
                        raise UploadLimitError("file_too_large", f"单张图片不能超过 {self.settings.max_file_size_mb} MB。")
                    if next_size > max_request_remaining_bytes:
                        raise UploadLimitError(
                            "request_too_large",
                            f"本次上传总大小不能超过 {self.settings.max_request_size_mb} MB。",
                        )

                    size = next_size
                    buffer.write(chunk)
        except Exception:
            existing_names.discard(safe_name)
            target_path.unlink(missing_ok=True)
            await upload.close()
            raise

        await upload.close()
        return {
            "filename": original_name,
            "stored_filename": safe_name,
            "path": target_path,
            "size": size,
        }

    def build_download_path(self, task_id: str, filename: str) -> str:
        return f"/download/{task_id}/{filename}"

    def build_zip_download_path(self, task_id: str) -> str:
        return f"/download/{task_id}/all.zip"

    def _sanitize_filename(self, filename: str) -> str:
        stem = Path(filename).stem or "image"
        suffix = Path(filename).suffix.lower()
        safe_stem = FILENAME_PATTERN.sub("-", stem).strip("-._") or "image"
        return f"{safe_stem}{suffix}"

    def _dedupe_filename(self, filename: str, existing_names: set[str]) -> str:
        candidate = filename
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        index = 2

        while candidate in existing_names:
            candidate = f"{stem}_{index}{suffix}"
            index += 1

        existing_names.add(candidate)
        return candidate

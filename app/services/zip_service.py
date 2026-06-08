from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.config import Settings


class ZipService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_zip(self, task_id: str, file_paths: list[Path]) -> Path:
        zip_path = self.settings.zips_dir / f"{task_id}.zip"
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zip_file:
            for file_path in file_paths:
                zip_file.write(file_path, arcname=file_path.name)
        return zip_path

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.config import Settings


class ZipService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_zip(self, task_id: str, file_paths: list[Path]) -> Path:
        zip_path = self.settings.zips_dir / f"{task_id}.zip"
        used_names: set[str] = set()
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as arc:
            for index, file_path in enumerate(file_paths, start=1):
                # HEIC/HEIF 经本地压缩后统一为 .jpg，可能出现同名覆盖；
                # 用“序号_原名”保证 ZIP 内条目唯一，避免相互覆盖。
                arcname = file_path.name
                if arcname in used_names:
                    arcname = f"{index}_{file_path.name}"
                used_names.add(arcname)
                arc.write(file_path, arcname=arcname)
        return zip_path

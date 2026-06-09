from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    app_name: str
    tinify_api_key: str
    max_files_per_upload: int
    max_file_size_mb: int
    max_request_size_mb: int
    temp_dir: Path
    file_expire_minutes: int
    poll_interval_ms: int
    rate_limit_per_minute: int
    allowed_extensions: tuple[str, ...]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_request_size_bytes(self) -> int:
        return self.max_request_size_mb * 1024 * 1024

    @property
    def templates_dir(self) -> Path:
        return BASE_DIR / "app" / "templates"

    @property
    def static_dir(self) -> Path:
        return BASE_DIR / "app" / "static"

    @property
    def assets_dir(self) -> Path:
        return BASE_DIR / "assets"

    @property
    def runtime_dir(self) -> Path:
        return self.temp_dir / "runtime"

    @property
    def uploads_dir(self) -> Path:
        return self.runtime_dir / "uploads"

    @property
    def compressed_dir(self) -> Path:
        return self.runtime_dir / "compressed"

    @property
    def zips_dir(self) -> Path:
        return self.runtime_dir / "zips"

    @property
    def tasks_dir(self) -> Path:
        return self.runtime_dir / "tasks"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv(BASE_DIR / ".env")

    return Settings(
        app_name="CompressImgs",
        tinify_api_key=os.getenv("TINIFY_API_KEY", "").strip(),
        max_files_per_upload=int(os.getenv("MAX_FILES_PER_UPLOAD", "10")),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "10")),
        max_request_size_mb=int(os.getenv("MAX_REQUEST_SIZE_MB", "100")),
        temp_dir=BASE_DIR / os.getenv("TEMP_DIR", "work/tmp"),
        file_expire_minutes=int(os.getenv("FILE_EXPIRE_MINUTES", "60")),
        poll_interval_ms=int(os.getenv("POLL_INTERVAL_MS", "1000")),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "5")),
        allowed_extensions=("png", "jpg", "jpeg", "webp"),
    )

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from PIL import Image, UnidentifiedImageError

from app.config import Settings

try:
    import tinify
    from tinify.errors import AccountError, ClientError, ConnectionError as TinifyConnectionError, ServerError
except ImportError:  # pragma: no cover
    tinify = None
    AccountError = ClientError = ServerError = TinifyConnectionError = Exception


@dataclass(frozen=True)
class CompressionMetrics:
    backend: str
    total_elapsed_ms: int
    shrink_elapsed_ms: int | None = None
    download_elapsed_ms: int | None = None
    local_elapsed_ms: int | None = None


class CompressionError(Exception):
    def __init__(self, code: str, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class Compressor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if tinify and settings.tinify_api_key:
            tinify.key = settings.tinify_api_key

    @property
    def backend_name(self) -> str:
        if tinify and self.settings.tinify_api_key:
            return "tinify"
        return "pillow"

    def compress(self, source_path: Path, target_path: Path) -> CompressionMetrics:
        if tinify and self.settings.tinify_api_key:
            metrics = self._compress_with_tinify(source_path, target_path)
            self._ensure_smaller_or_equal(source_path, target_path)
            return metrics

        metrics = self._compress_with_pillow(source_path, target_path)
        self._ensure_smaller_or_equal(source_path, target_path)
        return metrics

    def _compress_with_tinify(self, source_path: Path, target_path: Path) -> CompressionMetrics:
        total_started_at = perf_counter()
        shrink_started_at = perf_counter()
        try:
            source = tinify.from_file(str(source_path))
        except (AccountError, ClientError, ServerError, TinifyConnectionError) as exc:
            raise self._build_tinify_error(
                exc,
                phase="shrink_request",
                shrink_elapsed_ms=int((perf_counter() - shrink_started_at) * 1000),
            ) from exc

        shrink_elapsed_ms = int((perf_counter() - shrink_started_at) * 1000)
        download_started_at = perf_counter()
        try:
            source.to_file(str(target_path))
        except (AccountError, ClientError, ServerError, TinifyConnectionError) as exc:
            raise self._build_tinify_error(
                exc,
                phase="result_download",
                shrink_elapsed_ms=shrink_elapsed_ms,
                download_elapsed_ms=int((perf_counter() - download_started_at) * 1000),
            ) from exc

        download_elapsed_ms = int((perf_counter() - download_started_at) * 1000)
        return CompressionMetrics(
            backend="tinify",
            total_elapsed_ms=int((perf_counter() - total_started_at) * 1000),
            shrink_elapsed_ms=shrink_elapsed_ms,
            download_elapsed_ms=download_elapsed_ms,
        )

    def _ensure_smaller_or_equal(self, source_path: Path, target_path: Path) -> None:
        if not target_path.exists():
            return

        if target_path.stat().st_size <= source_path.stat().st_size:
            return

        shutil.copyfile(source_path, target_path)

    def _compress_with_pillow(self, source_path: Path, target_path: Path) -> CompressionMetrics:
        suffix = source_path.suffix.lower()
        save_kwargs: dict[str, object] = {"optimize": True}

        if suffix in {".jpg", ".jpeg"}:
            save_kwargs["quality"] = 82
            save_kwargs["progressive"] = True
            format_name = "JPEG"
        elif suffix == ".png":
            save_kwargs["compress_level"] = 9
            format_name = "PNG"
        elif suffix == ".webp":
            save_kwargs["quality"] = 82
            save_kwargs["method"] = 6
            format_name = "WEBP"
        else:
            raise CompressionError("invalid_file_type", "仅支持 PNG、JPG、JPEG、WEBP。")

        started_at = perf_counter()
        try:
            with Image.open(source_path) as image:
                if format_name == "JPEG" and image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image.save(target_path, format=format_name, **save_kwargs)
        except UnidentifiedImageError as exc:
            raise CompressionError(
                "invalid_file_type",
                "无法识别图片内容。",
                details={"phase": "local_compress", "local_elapsed_ms": int((perf_counter() - started_at) * 1000)},
            ) from exc
        except OSError as exc:
            raise CompressionError(
                "compress_failed",
                "图片压缩失败，请稍后重试。",
                details={"phase": "local_compress", "local_elapsed_ms": int((perf_counter() - started_at) * 1000)},
            ) from exc

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        return CompressionMetrics(
            backend="pillow",
            total_elapsed_ms=elapsed_ms,
            local_elapsed_ms=elapsed_ms,
        )

    def _build_tinify_error(
        self,
        exc: Exception,
        *,
        phase: str,
        shrink_elapsed_ms: int | None = None,
        download_elapsed_ms: int | None = None,
    ) -> CompressionError:
        details = {
            "phase": phase,
            "shrink_elapsed_ms": shrink_elapsed_ms,
            "download_elapsed_ms": download_elapsed_ms,
        }

        if isinstance(exc, AccountError):
            message = str(exc).lower()
            if "limit" in message or "quota" in message:
                return CompressionError("quota_exceeded", "本月压缩额度已用完。", details=details)
            return CompressionError("invalid_api_key", "Tinify 配置不可用。", details=details)
        if isinstance(exc, ClientError):
            return CompressionError("compress_failed", "图片压缩失败，请稍后重试。", details=details)
        if isinstance(exc, ServerError):
            return CompressionError("server_error", "压缩服务暂时不可用。", details=details)
        return CompressionError("server_error", "无法连接压缩服务。", details=details)

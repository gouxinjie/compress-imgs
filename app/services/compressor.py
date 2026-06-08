from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config import Settings

try:
    import tinify
    from tinify.errors import AccountError, ClientError, ServerError, ConnectionError as TinifyConnectionError
except ImportError:  # pragma: no cover
    tinify = None
    AccountError = ClientError = ServerError = TinifyConnectionError = Exception


class CompressionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Compressor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if tinify and settings.tinify_api_key:
            tinify.key = settings.tinify_api_key

    def compress(self, source_path: Path, target_path: Path) -> None:
        if tinify and self.settings.tinify_api_key:
            self._compress_with_tinify(source_path, target_path)
            return

        self._compress_with_pillow(source_path, target_path)

    def _compress_with_tinify(self, source_path: Path, target_path: Path) -> None:
        try:
            source = tinify.from_file(str(source_path))
            source.to_file(str(target_path))
        except AccountError as exc:
            message = str(exc).lower()
            if "limit" in message or "quota" in message:
                raise CompressionError("quota_exceeded", "本月压缩额度已用完。") from exc
            raise CompressionError("invalid_api_key", "Tinify 配置不可用。") from exc
        except ClientError as exc:
            raise CompressionError("compress_failed", "图片压缩失败，请稍后重试。") from exc
        except ServerError as exc:
            raise CompressionError("server_error", "压缩服务暂时不可用。") from exc
        except TinifyConnectionError as exc:
            raise CompressionError("server_error", "无法连接压缩服务。") from exc

    def _compress_with_pillow(self, source_path: Path, target_path: Path) -> None:
        suffix = source_path.suffix.lower()
        save_kwargs: dict[str, object] = {"optimize": True}

        if suffix in {".jpg", ".jpeg"}:
            save_kwargs["quality"] = 82
            format_name = "JPEG"
        elif suffix == ".png":
            format_name = "PNG"
        elif suffix == ".webp":
            save_kwargs["quality"] = 82
            method = 6
            save_kwargs["method"] = method
            format_name = "WEBP"
        else:
            raise CompressionError("invalid_file_type", "仅支持 PNG、JPG、JPEG、WEBP。")

        try:
            with Image.open(source_path) as image:
                if format_name == "JPEG" and image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image.save(target_path, format=format_name, **save_kwargs)
        except UnidentifiedImageError as exc:
            raise CompressionError("invalid_file_type", "无法识别图片内容。") from exc
        except OSError as exc:
            raise CompressionError("compress_failed", "图片压缩失败，请稍后重试。") from exc

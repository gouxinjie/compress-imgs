from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings

try:
    import tinify
    from tinify.errors import AccountError, ClientError, ConnectionError as TinifyConnectionError, ServerError
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

    @property
    def backend_name(self) -> str:
        if tinify and self.settings.tinify_api_key:
            return "tinify"
        return "pillow"

    def compress(self, source_path: Path, target_path: Path) -> None:
        if tinify and self.settings.tinify_api_key:
            self._compress_with_tinify(source_path, target_path)
            self._ensure_smaller_or_equal(source_path, target_path)
            return

        self._compress_with_pillow(source_path, target_path)
        self._ensure_smaller_or_equal(source_path, target_path)

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

    def _ensure_smaller_or_equal(self, source_path: Path, target_path: Path) -> None:
        if not target_path.exists():
            return

        if target_path.stat().st_size <= source_path.stat().st_size:
            return

        shutil.copyfile(source_path, target_path)

    def _compress_with_pillow(self, source_path: Path, target_path: Path) -> None:
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
        elif suffix in {".heic", ".heif"}:
            # iOS 默认输出 HEIC。Pillow 需 pillow_heif 才能解码，
            # 解码后统一转为 JPEG（HEIC 均为照片，转 JPEG 最稳妥）。
            self._compress_heic(source_path, target_path)
            return
        else:
            raise CompressionError("invalid_file_type", "仅支持 PNG、JPG、JPEG、WEBP、HEIC。")

        try:
            with Image.open(source_path) as image:
                # iOS 照片常带 EXIF Orientation 标签，直接保存会导致方向错乱，
                # 统一按 EXIF 旋转回正（对所有平台均有益，无损视觉信息）。
                image = ImageOps.exif_transpose(image)
                if format_name == "JPEG" and image.mode != "RGB":
                    image = image.convert("RGB")
                elif format_name in ("WEBP", "PNG") and image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")
                image.save(target_path, format=format_name, **save_kwargs)
        except UnidentifiedImageError as exc:
            raise CompressionError("invalid_file_type", "无法识别图片内容。") from exc
        except OSError as exc:
            raise CompressionError("compress_failed", "图片压缩失败，请稍后重试。") from exc

    def _compress_heic(self, source_path: Path, target_path: Path) -> None:
        try:
            import pillow_heif  # 可选依赖，未安装时给出友好提示

            pillow_heif.register_heif_opener()
        except ImportError as exc:
            raise CompressionError(
                "heic_unsupported",
                "HEIC 暂不支持本地压缩，请安装 pillow-heif 或改用 Tinify 后端，或在手机上将格式改为 JPEG。",
            ) from exc

        heic_save_kwargs: dict[str, object] = {"quality": 82, "optimize": True, "progressive": True}
        try:
            with Image.open(source_path) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode != "RGB":
                    image = image.convert("RGB")
                image.save(target_path, format="JPEG", **heic_save_kwargs)
        except UnidentifiedImageError as exc:
            raise CompressionError("invalid_file_type", "无法识别图片内容。") from exc
        except OSError as exc:
            raise CompressionError("compress_failed", "HEIC 压缩失败，请稍后重试。") from exc

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.config import Settings
from app.services import compressor as compressor_module


def build_settings(temp_dir: Path, *, tinify_api_key: str = "") -> Settings:
    return Settings(
        app_name="CompressImgs",
        tinify_api_key=tinify_api_key,
        max_files_per_upload=10,
        max_file_size_mb=10,
        max_request_size_mb=100,
        temp_dir=temp_dir,
        file_expire_minutes=30,
        poll_interval_ms=1000,
        rate_limit_per_minute=5,
        allowed_extensions=("png", "jpg", "jpeg", "webp"),
    )


class FakeTinifySource:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def to_file(self, target_path: str) -> None:
        Path(target_path).write_bytes(self.payload)


class FakeTinifyClient:
    def __init__(self) -> None:
        self.key = ""

    def from_file(self, source_path: str) -> FakeTinifySource:
        return FakeTinifySource(Path(source_path).read_bytes())


class CompressorTests(unittest.TestCase):
    def test_compress_with_pillow_returns_local_timing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            target_path = temp_path / "target.png"
            Image.new("RGB", (32, 32), color=(255, 0, 0)).save(source_path, format="PNG")

            compressor = compressor_module.Compressor(build_settings(temp_path))
            metrics = compressor.compress(source_path, target_path)

            self.assertEqual(metrics.backend, "pillow")
            self.assertIsNotNone(metrics.local_elapsed_ms)
            self.assertIsNone(metrics.shrink_elapsed_ms)
            self.assertIsNone(metrics.download_elapsed_ms)
            self.assertTrue(target_path.exists())

    def test_compress_with_tinify_returns_phase_timings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            target_path = temp_path / "target.png"
            Image.new("RGB", (32, 32), color=(0, 128, 255)).save(source_path, format="PNG")

            fake_tinify = FakeTinifyClient()
            with patch.object(compressor_module, "tinify", fake_tinify):
                compressor = compressor_module.Compressor(build_settings(temp_path, tinify_api_key="test-key"))
                metrics = compressor.compress(source_path, target_path)

            self.assertEqual(metrics.backend, "tinify")
            self.assertIsNotNone(metrics.shrink_elapsed_ms)
            self.assertIsNotNone(metrics.download_elapsed_ms)
            self.assertIsNone(metrics.local_elapsed_ms)
            self.assertTrue(target_path.exists())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app import config


class ConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        config.get_settings.cache_clear()

    def test_get_settings_defaults_file_expire_to_30_minutes(self) -> None:
        config.get_settings.cache_clear()

        with patch("app.config._load_dotenv", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                settings = config.get_settings()

        self.assertEqual(settings.file_expire_minutes, 30)

    def test_get_settings_defaults_poll_interval_to_2500_ms(self) -> None:
        config.get_settings.cache_clear()

        with patch("app.config._load_dotenv", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                settings = config.get_settings()

        self.assertEqual(settings.poll_interval_ms, 2500)


if __name__ == "__main__":
    unittest.main()

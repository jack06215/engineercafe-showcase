"""Tests for config: the shipped config.yaml loads, and mistakes in it fail at startup."""

import tempfile
import unittest
from pathlib import Path

import yaml
from pydantic import ValidationError

from packages.vibe_coding_club.vega_lite_chat.config import (
    DEFAULT_CONFIG,
    load_config,
)


class LoadConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def _write(self, document: object) -> Path:
        path = self.directory / "config.yaml"
        path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
        return path

    def test_shipped_config_loads(self) -> None:
        config = load_config()

        self.assertEqual(config.ollama.model, "qwen3.6:35b")
        self.assertEqual(config.ollama.base_url, "http://localhost:11434")
        self.assertEqual(config.ollama.keep_alive, "1h")
        self.assertFalse(config.ollama.thinking_default)
        self.assertEqual(config.chat.history_turns, 6)
        self.assertEqual(config.translator.max_calls, 3)
        self.assertEqual(config.translator.recent_requests, 3)
        self.assertEqual(config.data.row_warning, 1000)
        self.assertEqual(config.data.sample_rows, 5)
        self.assertEqual(config.data.max_listed_values, 20)
        self.assertEqual(config.chart.height, 400)

    def test_unknown_key_fails(self) -> None:
        document = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        document["ollama"]["modle"] = "typo"

        with self.assertRaises(ValidationError) as caught:
            load_config(self._write(document))

        self.assertIn("modle", str(caught.exception))

    def test_unknown_section_fails(self) -> None:
        document = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        document["extras"] = {}

        with self.assertRaises(ValidationError):
            load_config(self._write(document))

    def test_missing_key_fails(self) -> None:
        document = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        del document["translator"]["max_calls"]

        with self.assertRaises(ValidationError):
            load_config(self._write(document))

    def test_out_of_range_value_fails(self) -> None:
        document = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        document["translator"]["max_calls"] = 0

        with self.assertRaises(ValidationError):
            load_config(self._write(document))


if __name__ == "__main__":
    unittest.main()

"""Tests for langchain_util.cache."""

import tempfile
import unittest
from pathlib import Path

from langchain_core.caches import InMemoryCache
from langchain_core.globals import get_llm_cache
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, Generation

from packages.langchain_util.cache import (
    SQLiteCache,
    disable_llm_cache,
    enable_llm_cache,
)


class LlmCacheTest(unittest.TestCase):
    def tearDown(self) -> None:
        disable_llm_cache()

    def test_none_path_installs_in_memory_cache(self) -> None:
        cache = enable_llm_cache(None)

        self.assertIsInstance(cache, InMemoryCache)
        self.assertIs(get_llm_cache(), cache)

    def test_path_installs_sqlite_cache_and_creates_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "llm.sqlite"

            cache = enable_llm_cache(target)

            self.assertIs(get_llm_cache(), cache)
            self.assertTrue(target.parent.is_dir())

    def test_disable_clears_the_cache(self) -> None:
        enable_llm_cache(None)

        disable_llm_cache()

        self.assertIsNone(get_llm_cache())

    def test_cache_round_trips_a_response(self) -> None:
        cache = enable_llm_cache(None)

        cache.update("prompt", "llm-string", [Generation(text="cached")])

        cached = cache.lookup("prompt", "llm-string")
        assert cached is not None
        self.assertEqual(cached[0].text, "cached")


class SQLiteCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = SQLiteCache(Path(self._tmp.name) / "llm.sqlite")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_miss_returns_none(self) -> None:
        self.assertIsNone(self.cache.lookup("nothing", "llm"))

    def test_round_trips_chat_generation_with_its_message(self) -> None:
        # The reason for langchain's serializer rather than storing bare text:
        # chat models need the AIMessage back, not just its content.
        generation = ChatGeneration(message=AIMessage(content="hi there"))

        self.cache.update("prompt", "llm", [generation])
        cached = self.cache.lookup("prompt", "llm")

        assert cached is not None
        restored = cached[0]
        assert isinstance(restored, ChatGeneration)
        self.assertEqual(restored.message.content, "hi there")

    def test_preserves_multiple_generations_in_order(self) -> None:
        self.cache.update(
            "prompt",
            "llm",
            [Generation(text="a"), Generation(text="b"), Generation(text="c")],
        )

        cached = self.cache.lookup("prompt", "llm")

        assert cached is not None
        self.assertEqual([g.text for g in cached], ["a", "b", "c"])

    def test_update_replaces_rather_than_appends(self) -> None:
        self.cache.update("prompt", "llm", [Generation(text="old")])
        self.cache.update("prompt", "llm", [Generation(text="new")])

        cached = self.cache.lookup("prompt", "llm")

        assert cached is not None
        self.assertEqual([g.text for g in cached], ["new"])

    def test_keys_on_both_prompt_and_llm_string(self) -> None:
        self.cache.update("prompt", "llm-a", [Generation(text="a")])
        self.cache.update("prompt", "llm-b", [Generation(text="b")])

        first = self.cache.lookup("prompt", "llm-a")
        second = self.cache.lookup("prompt", "llm-b")

        assert first is not None
        assert second is not None
        self.assertEqual(first[0].text, "a")
        self.assertEqual(second[0].text, "b")

    def test_survives_a_reopen(self) -> None:
        path = Path(self._tmp.name) / "persist.sqlite"
        SQLiteCache(path).update("prompt", "llm", [Generation(text="durable")])

        cached = SQLiteCache(path).lookup("prompt", "llm")

        assert cached is not None
        self.assertEqual(cached[0].text, "durable")

    def test_clear_empties_the_cache(self) -> None:
        self.cache.update("prompt", "llm", [Generation(text="x")])

        self.cache.clear()

        self.assertIsNone(self.cache.lookup("prompt", "llm"))


if __name__ == "__main__":
    unittest.main()

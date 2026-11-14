"""Process-wide caching of LLM responses.

Identical prompts stop costing money and time, which matters most while
iterating on a prompt locally against a paid provider.
"""

import sqlite3
import threading
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

from langchain_core.caches import RETURN_VAL_TYPE, BaseCache, InMemoryCache
from langchain_core.globals import set_llm_cache
from langchain_core.load import Serializable, dumps, loads
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import (
    ChatGeneration,
    ChatGenerationChunk,
    Generation,
    GenerationChunk,
)

DEFAULT_CACHE_PATH = Path.home() / ".cache" / "langchain_util" / "llm_cache.sqlite"

_ALLOWED_CACHE_OBJECTS: list[type[Serializable]] = [
    AIMessage,
    AIMessageChunk,
    ChatGeneration,
    ChatGenerationChunk,
    Generation,
    GenerationChunk,
]
"""Exactly the classes a model response can consist of.

`loads` will revive any Serializable it is allowed to, so this stays an explicit
allowlist rather than "all" -- the cache file is ordinary on-disk data and should
not be a route to instantiating arbitrary classes.
"""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    prompt TEXT NOT NULL,
    llm TEXT NOT NULL,
    idx INTEGER NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (prompt, llm, idx)
)
"""


class SQLiteCache(BaseCache):
    """A SQLite-backed LLM response cache that survives restarts.

    Hand-rolled rather than imported from `langchain_community.cache`, which is
    being sunset. Generations are stored with langchain's own serializer so that
    `ChatGeneration` round-trips with its message intact -- storing bare text
    would silently break caching for chat models.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        with self._transaction() as connection:
            connection.execute(_SCHEMA)

    def _transaction(self) -> Any:
        connection = sqlite3.connect(self.database_path, check_same_thread=False)
        return _Transaction(connection)

    def lookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        with self._lock, self._transaction() as connection:
            rows = connection.execute(
                "SELECT value FROM cache WHERE prompt = ? AND llm = ? ORDER BY idx",
                (prompt, llm_string),
            ).fetchall()

        if not rows:
            return None

        generations: list[Generation] = [
            loads(row[0], allowed_objects=_ALLOWED_CACHE_OBJECTS) for row in rows
        ]
        return generations

    def update(
        self,
        prompt: str,
        llm_string: str,
        return_val: RETURN_VAL_TYPE,
    ) -> None:
        rows = [
            (prompt, llm_string, index, dumps(generation))
            for index, generation in enumerate(return_val)
        ]

        with self._lock, self._transaction() as connection:
            connection.execute(
                "DELETE FROM cache WHERE prompt = ? AND llm = ?",
                (prompt, llm_string),
            )
            connection.executemany(
                "INSERT INTO cache (prompt, llm, idx, value) VALUES (?, ?, ?, ?)",
                rows,
            )

    def clear(self, **kwargs: Any) -> None:
        with self._lock, self._transaction() as connection:
            connection.execute("DELETE FROM cache")


class _Transaction:
    """Commit on success, roll back on error, always close."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __enter__(self) -> sqlite3.Connection:
        return self._connection

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        with closing(self._connection):
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()


def enable_llm_cache(path: str | Path | None = DEFAULT_CACHE_PATH) -> BaseCache:
    """Install an LLM response cache for the whole process.

    A `path` gives a SQLite cache that survives restarts; `None` gives an
    in-memory one that lasts for this process only. Returns the installed cache.
    """
    cache: BaseCache = InMemoryCache() if path is None else SQLiteCache(path)
    set_llm_cache(cache)
    return cache


def disable_llm_cache() -> None:
    """Remove any cache previously installed by `enable_llm_cache`."""
    set_llm_cache(None)


def cached_generations(cache: BaseCache, prompt: str, llm_string: str) -> Sequence[Any]:
    """Convenience read-through for tests and debugging."""
    return cache.lookup(prompt, llm_string) or []

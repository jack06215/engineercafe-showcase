"""The 34 topics and primary-topic assignment (SPEC §5.7, Appendices A–C).

Pure: `TopicCatalog.from_mapping` takes the already-parsed `topics.yaml`
mapping; reading the file is the catalogue layer's job.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Topic:
    id: str
    name: str
    priority: int  # most specific first; picks the primary topic
    curriculum: int  # fundamentals first; breaks ties in the daily plan
    tags: tuple[str, ...]  # LeetCode tags mapping to this topic
    folder: str  # under packages/programming_exercise/leetcode/src/


class TopicCatalogError(ValueError):
    """`topics.yaml` is malformed. The message names the offending key."""


@dataclass(frozen=True)
class TopicCatalog:
    topics: tuple[Topic, ...]  # in priority order
    unmapped_tags: frozenset[str]
    excluded_tags: frozenset[str]
    neetcode_categories: Mapping[str, str | None]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TopicCatalog":
        """Build and validate the catalogue from parsed `topics.yaml`."""
        try:
            entries = raw["topics"]
            topics = tuple(
                Topic(
                    id=str(t["id"]),
                    name=str(t["name"]),
                    priority=int(t["priority"]),
                    curriculum=int(t["curriculum"]),
                    tags=tuple(str(tag) for tag in t["tags"]),
                    folder=str(t["folder"]),
                )
                for t in entries
            )
            unmapped = frozenset(str(t) for t in raw.get("unmapped_tags", []))
            excluded = frozenset(str(t) for t in raw.get("excluded_tags", []))
            categories = {
                str(k): (None if v is None else str(v))
                for k, v in raw.get("neetcode_categories", {}).items()
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise TopicCatalogError(f"topics.yaml: {exc!r}") from exc

        n = len(topics)
        for field in ("id", "name", "priority", "curriculum"):
            values = [getattr(t, field) for t in topics]
            if len(set(values)) != n:
                raise TopicCatalogError(f"topics.yaml: topics[].{field} must be unique")
        for field in ("priority", "curriculum"):
            if sorted(getattr(t, field) for t in topics) != list(range(1, n + 1)):
                raise TopicCatalogError(f"topics.yaml: topics[].{field} must be 1..{n}")
        seen: dict[str, str] = {}
        for t in topics:
            for tag in t.tags:
                if tag in seen:
                    raise TopicCatalogError(
                        f"topics.yaml: tag {tag!r} maps to both {seen[tag]} and {t.id}"
                    )
                seen[tag] = t.id
        ids = {t.id for t in topics}
        for category, topic_id in categories.items():
            if topic_id is not None and topic_id not in ids:
                raise TopicCatalogError(
                    f"topics.yaml: neetcode_categories.{category} names unknown topic {topic_id!r}"
                )

        return cls(
            topics=tuple(sorted(topics, key=lambda t: t.priority)),
            unmapped_tags=unmapped,
            excluded_tags=excluded,
            neetcode_categories=categories,
        )

    def get(self, topic_id: str) -> Topic:
        for t in self.topics:
            if t.id == topic_id:
                return t
        raise KeyError(topic_id)

    def ids(self) -> list[str]:
        return [t.id for t in self.topics]

    def by_curriculum(self) -> list[Topic]:
        return sorted(self.topics, key=lambda t: t.curriculum)

    def topic_for_tag(self, tag: str) -> Topic | None:
        for t in self.topics:
            if tag in t.tags:
                return t
        return None

    def primary_topic(
        self, tags: Iterable[str], neetcode_category: str | None
    ) -> str | None:
        """A LeetCode problem's primary topic id, or None (SPEC §5.7).

        1. The NeetCode category, if it maps to a topic.
        2. Otherwise the highest-priority topic any tag maps to.
        3. Otherwise none.
        """
        if neetcode_category is not None:
            mapped = self.neetcode_categories.get(neetcode_category)
            if mapped is not None:
                return mapped
        tag_set = set(tags)
        for t in self.topics:  # priority order
            if tag_set.intersection(t.tags):
                return t.id
        return None

    def is_excluded(self, tags: Iterable[str]) -> bool:
        """Whether the bank leaves this problem out (Database, Shell, Concurrency)."""
        return not self.excluded_tags.isdisjoint(tags)

    def unknown_tags(self, tags: Iterable[str]) -> set[str]:
        """Tags that are neither mapped, unmapped-but-known, nor excluded.

        A bank refresh reports these so gaps in Appendix A surface (SPEC §5.4).
        """
        known = self.unmapped_tags | self.excluded_tags
        return {
            tag for tag in tags if tag not in known and self.topic_for_tag(tag) is None
        }

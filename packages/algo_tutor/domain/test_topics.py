import json
import unittest
from pathlib import Path

import yaml

from packages.algo_tutor.domain.topics import TopicCatalog, TopicCatalogError

MANIFESTS = Path(__file__).resolve().parent.parent / "manifests"


def load_catalog() -> TopicCatalog:
    return TopicCatalog.from_mapping(
        yaml.safe_load((MANIFESTS / "topics.yaml").read_text())
    )


class TopicsYamlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_thirty_four_topics_in_priority_order(self) -> None:
        self.assertEqual(len(self.catalog.topics), 34)
        self.assertEqual(self.catalog.topics[0].name, "Monotonic Queue")
        self.assertEqual(self.catalog.topics[-1].name, "Array")
        self.assertEqual(
            [t.name for t in self.catalog.by_curriculum()][:3],
            ["Array", "String", "Hash Table"],
        )

    def test_every_neetcode_category_is_covered(self) -> None:
        rows = json.loads((MANIFESTS / "neetcode-problems.json").read_text())
        categories = {r["pattern"] for r in rows} - {"JavaScript"}
        self.assertEqual(categories, set(self.catalog.neetcode_categories))

    def test_hello_interview_topics_have_tags_or_categories(self) -> None:
        # Every Appendix A tag is spelled as LeetCode spells it, so none of the
        # Hello Interview problems' NeetCode-style topics leak in as tags.
        self.assertIsNone(self.catalog.topic_for_tag("Arrays & Hashing"))


class PrimaryTopicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_neetcode_category_wins(self) -> None:
        self.assertEqual(
            self.catalog.primary_topic(["Array", "Hash Table"], "Sliding Window"),
            "sliding-window",
        )
        self.assertEqual(
            self.catalog.primary_topic(["Array"], "Intervals"), "sweep-line"
        )

    def test_arrays_and_hashing_falls_through_to_tags(self) -> None:
        self.assertEqual(
            self.catalog.primary_topic(["Array", "Hash Table"], "Arrays & Hashing"),
            "hash-table",
        )
        self.assertEqual(
            self.catalog.primary_topic(["Array", "Sorting"], "Arrays & Hashing"),
            "array",
        )

    def test_unknown_category_falls_through(self) -> None:
        self.assertEqual(self.catalog.primary_topic(["String"], "JavaScript"), "string")

    def test_tag_priority(self) -> None:
        tags = [
            "Array",
            "Depth-First Search",
            "Breadth-First Search",
            "Union Find",
            "Graph",
        ]
        self.assertEqual(self.catalog.primary_topic(tags, None), "union-find")
        self.assertEqual(
            self.catalog.primary_topic(["Array", "Brainteaser", "Math"], None),
            "observation",
        )
        self.assertEqual(
            self.catalog.primary_topic(["Heap (Priority Queue)", "Sorting"], None),
            "priority-queue",
        )

    def test_no_mapped_tag(self) -> None:
        self.assertIsNone(
            self.catalog.primary_topic(["Segment Tree", "Interactive"], None)
        )
        self.assertIsNone(self.catalog.primary_topic([], None))

    def test_unknown_and_excluded_tags(self) -> None:
        self.assertEqual(
            self.catalog.unknown_tags(["Array", "Segment Tree", "Database", "Quantum"]),
            {"Quantum"},
        )
        self.assertTrue(self.catalog.is_excluded(["Array", "Shell"]))
        self.assertFalse(self.catalog.is_excluded(["Array"]))


class ValidationTest(unittest.TestCase):
    def test_duplicate_tag_is_rejected(self) -> None:
        raw = {
            "topics": [
                {
                    "id": "a",
                    "name": "A",
                    "priority": 1,
                    "curriculum": 1,
                    "tags": ["X"],
                    "folder": "f",
                },
                {
                    "id": "b",
                    "name": "B",
                    "priority": 2,
                    "curriculum": 2,
                    "tags": ["X"],
                    "folder": "f",
                },
            ]
        }
        with self.assertRaisesRegex(TopicCatalogError, "tag 'X'"):
            TopicCatalog.from_mapping(raw)

    def test_priority_gap_is_rejected(self) -> None:
        raw = {
            "topics": [
                {
                    "id": "a",
                    "name": "A",
                    "priority": 2,
                    "curriculum": 1,
                    "tags": [],
                    "folder": "f",
                }
            ]
        }
        with self.assertRaisesRegex(TopicCatalogError, "priority"):
            TopicCatalog.from_mapping(raw)

    def test_unknown_category_target_is_rejected(self) -> None:
        raw = {
            "topics": [
                {
                    "id": "a",
                    "name": "A",
                    "priority": 1,
                    "curriculum": 1,
                    "tags": [],
                    "folder": "f",
                }
            ],
            "neetcode_categories": {"Trees": "tree"},
        }
        with self.assertRaisesRegex(TopicCatalogError, "Trees"):
            TopicCatalog.from_mapping(raw)


if __name__ == "__main__":
    unittest.main()

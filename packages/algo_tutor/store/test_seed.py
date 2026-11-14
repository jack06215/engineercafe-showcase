import tempfile
import unittest
from pathlib import Path

import yaml
from sqlalchemy import select

from packages.algo_tutor.domain.topics import TopicCatalog
from packages.algo_tutor.store.db import create_sqlite_engine, session_factory
from packages.algo_tutor.store.migrations import migrate
from packages.algo_tutor.store.models import Pattern, Settings, Topic
from packages.algo_tutor.store.seed import (
    FoundPattern,
    ensure_settings,
    local_timezone,
    scan_patterns,
    sync_patterns,
    sync_topics,
)

MANIFESTS = Path(__file__).parent.parent / "manifests"


def catalog() -> TopicCatalog:
    return TopicCatalog.from_mapping(
        yaml.safe_load((MANIFESTS / "topics.yaml").read_text())
    )


class SeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.engine = create_sqlite_engine(self.root / "db.sqlite")
        migrate(self.engine)
        self.sessions = session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.folder.cleanup()

    def test_topics_follow_the_yaml_and_keep_notebooks(self) -> None:
        with self.sessions() as session, session.begin():
            sync_topics(session, catalog())
            array = session.get(Topic, "array")
            assert array is not None
            array.notes = "mine"
        # Swap two topics' orders: the UNIQUE columns must not collide.
        raw = yaml.safe_load((MANIFESTS / "topics.yaml").read_text())
        first, last = raw["topics"][0], raw["topics"][-1]
        first["priority"], last["priority"] = last["priority"], first["priority"]
        with self.sessions() as session, session.begin():
            sync_topics(session, TopicCatalog.from_mapping(raw))
        with self.sessions() as session:
            self.assertEqual(len(session.scalars(select(Topic)).all()), 34)
            array = session.get(Topic, "array")
            assert array is not None
            self.assertEqual((array.priority, array.notes), (1, "mine"))

    def test_patterns_are_scanned_in_number_order(self) -> None:
        patterns = self.root / "patterns"
        for folder, heading in (
            ("02_two_pointers", "# Two Pointers"),
            ("01_sliding_window", "Intro\n# Sliding Window ##"),
        ):
            (patterns / folder).mkdir(parents=True)
            (patterns / folder / "README.md").write_text(heading + "\n\nbody\n")
        (patterns / "lib").mkdir()
        (patterns / "03_no_readme").mkdir()
        found = scan_patterns(self.root, patterns)
        self.assertEqual(
            found,
            [
                FoundPattern(
                    "01_sliding_window",
                    "Sliding Window",
                    1,
                    "patterns/01_sliding_window/README.md",
                ),
                FoundPattern(
                    "02_two_pointers",
                    "Two Pointers",
                    2,
                    "patterns/02_two_pointers/README.md",
                ),
            ],
        )
        self.assertEqual(scan_patterns(self.root, self.root / "nowhere"), [])

    def test_a_vanished_pattern_is_kept_as_missing(self) -> None:
        both = [
            FoundPattern("01_a", "A", 1, "a/README.md"),
            FoundPattern("02_b", "B", 2, "b/README.md"),
        ]
        with self.sessions() as session, session.begin():
            sync_patterns(session, both)
            pattern = session.get(Pattern, "02_b")
            assert pattern is not None
            pattern.cues = "keep me"
        with self.sessions() as session, session.begin():
            sync_patterns(session, both[:1])
        with self.sessions() as session:
            b = session.get(Pattern, "02_b")
            assert b is not None
            self.assertTrue(b.missing)
            self.assertEqual(b.cues, "keep me")
        with self.sessions() as session, session.begin():
            sync_patterns(session, both)
        with self.sessions() as session:
            b = session.get(Pattern, "02_b")
            assert b is not None
            self.assertFalse(b.missing)

    def test_settings_created_once_and_timezone_refreshed(self) -> None:
        with self.sessions() as session, session.begin():
            ensure_settings(session, "Asia/Tokyo").questions_per_day = 5
        with self.sessions() as session, session.begin():
            ensure_settings(session, "Europe/London")
        with self.sessions() as session:
            s = session.get(Settings, 1)
            assert s is not None
            self.assertEqual((s.timezone, s.questions_per_day), ("Europe/London", 5))

    def test_local_timezone(self) -> None:
        nowhere = self.root / "no-localtime"
        self.assertEqual(local_timezone({"TZ": ":Asia/Tokyo"}, nowhere), "Asia/Tokyo")
        self.assertEqual(local_timezone({"TZ": "Not/AZone"}, nowhere), "UTC")
        link = self.root / "localtime"
        link.symlink_to("/usr/share/zoneinfo/Europe/Paris")
        self.assertEqual(local_timezone({}, link), "Europe/Paris")


if __name__ == "__main__":
    unittest.main()

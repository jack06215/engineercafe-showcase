import shutil
import tempfile
import unittest
from pathlib import Path

from packages.algo_tutor.catalogue.manifests import (
    MANIFEST_DIR,
    NEETCODE_FILE,
    ManifestError,
    load_manifests,
)
from packages.algo_tutor.catalogue.testing import manifests
from packages.algo_tutor.domain.enums import BundledSet, Difficulty


class ManifestsTest(unittest.TestCase):
    def test_courses(self) -> None:
        courses = manifests().courses
        self.assertEqual(len(courses[BundledSet.NEETCODE_150].slugs()), 150)
        self.assertEqual(len(courses[BundledSet.BLIND_75].slugs()), 75)
        hello = courses[BundledSet.HELLO_INTERVIEW]
        self.assertEqual((len(hello.sections), len(hello.slugs())), (16, 88))
        self.assertEqual(hello.sections[0].name, "Sliding Window")
        self.assertEqual(
            courses[BundledSet.NEETCODE_150].sections[0].name, "Arrays & Hashing"
        )
        self.assertEqual(
            courses[BundledSet.NEETCODE_150].slugs()[0], "contains-duplicate"
        )

    def test_known_problems(self) -> None:
        m = manifests()
        two_sum = m.known["two-sum"]
        self.assertEqual(
            (two_sum.number, two_sum.difficulty, two_sum.neetcode_category),
            (1, Difficulty.EASY, "Arrays & Hashing"),
        )
        # A zerotrac-only problem: title and number, no label.
        koko = m.known["koko-eating-bananas"]
        self.assertEqual(koko.number, 875)
        self.assertIs(m.find_title("  TWO SUM "), two_sum)
        self.assertIsNone(m.find_title("No Such Problem"))
        for course in m.courses.values():
            for slug in course.slugs():
                self.assertIn(slug, m.known)

    def test_an_altered_file_stops_with_its_name(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder)
            for f in MANIFEST_DIR.iterdir():
                shutil.copy(f, copy / f.name)
            with (copy / NEETCODE_FILE).open("a") as f:
                f.write(" ")
            with self.assertRaisesRegex(ManifestError, NEETCODE_FILE):
                load_manifests(copy)

    def test_a_missing_file_stops_with_its_name(self) -> None:
        with (
            tempfile.TemporaryDirectory() as folder,
            self.assertRaisesRegex(ManifestError, "topics.yaml"),
        ):
            load_manifests(Path(folder))


if __name__ == "__main__":
    unittest.main()

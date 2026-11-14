import unittest

from sqlalchemy import func, select

from packages.algo_tutor.catalogue.courses import follow_course
from packages.algo_tutor.catalogue.lists import list_entries
from packages.algo_tutor.catalogue.testing import NOW, manifests, temp_db
from packages.algo_tutor.domain.enums import BundledSet
from packages.algo_tutor.store.models import ImportBatch, Problem


class FollowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def test_neetcode_150_in_course_order_with_sections(self) -> None:
        with self.db.sessions() as session, session.begin():
            followed = follow_course(session, manifests(), BundledSet.NEETCODE_150, NOW)
            self.assertTrue(followed.created)
            self.assertEqual(followed.problems_added, 150)
            lst = followed.study_list
            self.assertEqual(
                (lst.name, lst.kind, lst.source, lst.origin),
                ("NeetCode 150", "bundled", "leetcode", "neetcode-150"),
            )
            entries = list_entries(session, lst.id)
            self.assertEqual(len(entries), 150)
            self.assertEqual(
                (entries[0].title, entries[0].section),
                ("Contains Duplicate", "Arrays & Hashing"),
            )
            # NeetCode's category gives most problems a topic before any bank download.
            with_topic = session.scalar(
                select(func.count())
                .select_from(Problem)
                .where(Problem.topic_id.is_not(None))
            )
            self.assertGreater(with_topic or 0, 100)

    def test_following_again_returns_the_same_list_and_blind_75_reuses_problems(
        self,
    ) -> None:
        with self.db.sessions() as session, session.begin():
            first = follow_course(session, manifests(), BundledSet.NEETCODE_150, NOW)
            again = follow_course(session, manifests(), BundledSet.NEETCODE_150, NOW)
            self.assertEqual(
                (again.created, again.study_list.id), (False, first.study_list.id)
            )
            blind = follow_course(session, manifests(), BundledSet.BLIND_75, NOW)
            self.assertEqual(blind.problems_added, 0)  # Blind 75 is inside NeetCode 150
            self.assertEqual(
                session.scalar(select(func.count()).select_from(ImportBatch)), 2
            )

    def test_hello_interview(self) -> None:
        with self.db.sessions() as session, session.begin():
            followed = follow_course(
                session, manifests(), BundledSet.HELLO_INTERVIEW, NOW
            )
            entries = list_entries(session, followed.study_list.id)
            self.assertEqual(len(entries), 88)
            self.assertEqual(entries[0].section, "Sliding Window")
            self.assertEqual(entries[-1].section, "Matrices")


if __name__ == "__main__":
    unittest.main()

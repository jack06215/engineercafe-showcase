import unittest

from packages.algo_tutor.catalogue.bank_file import questions_from_pages
from packages.algo_tutor.catalogue.errors import InvalidInput
from packages.algo_tutor.catalogue.problems import add_problem_by_url, title_from_slug
from packages.algo_tutor.catalogue.testing import NOW, bank_pages, manifests, temp_db


class AddProblemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def test_leetcode_from_the_manifests(self) -> None:
        with self.db.sessions() as session, session.begin():
            added = add_problem_by_url(
                session,
                manifests(),
                "https://leetcode.com/problems/two-sum/description/",
                NOW,
            )
            self.assertTrue(added.created)
            p = added.problem
            self.assertEqual(
                (p.title, p.number, p.difficulty_label, p.url),
                ("Two Sum", 1, "Easy", "https://leetcode.com/problems/two-sum/"),
            )
            self.assertEqual(p.neetcode_category, "Arrays & Hashing")
            self.assertIsNone(p.topic_id)  # no tags yet; the bank brings them
            again = add_problem_by_url(
                session, manifests(), "https://leetcode.cn/problems/two-sum", NOW
            )
            self.assertFalse(again.created)
            self.assertEqual(again.problem.id, p.id)

    def test_leetcode_from_the_last_bank_download(self) -> None:
        bank = {q.slug: q for q in questions_from_pages(bank_pages())}
        with self.db.sessions() as session, session.begin():
            p = add_problem_by_url(
                session,
                manifests(),
                "https://leetcode.com/problems/made-up-quantum-problem/",
                NOW,
                bank=bank,
            ).problem
            self.assertEqual(
                (p.title, p.number, p.source_tags, p.topic_id),
                (
                    "Made Up Quantum Problem",
                    9001,
                    ["Array", "Quantum Annealing"],
                    "array",
                ),
            )

    def test_an_unknown_slug_gets_a_readable_title(self) -> None:
        self.assertEqual(title_from_slug("some-new-problem"), "Some New Problem")
        with self.db.sessions() as session, session.begin():
            p = add_problem_by_url(
                session,
                manifests(),
                "https://leetcode.com/problems/some-new-problem/",
                NOW,
            ).problem
            self.assertEqual(p.title, "Some New Problem")

    def test_atcoder_needs_a_title(self) -> None:
        url = "https://atcoder.jp/contests/abc174/tasks/abc174_e"
        with self.db.sessions() as session, session.begin():
            with self.assertRaisesRegex(InvalidInput, "title"):
                add_problem_by_url(session, manifests(), url, NOW)
            p = add_problem_by_url(session, manifests(), url, NOW, title="Logs").problem
            self.assertEqual(
                (p.source, p.external_id, p.contest, p.title, p.topic_id),
                ("atcoder", "abc174_e", "abc174", "Logs", None),
            )
            # Once it exists, the title is optional.
            self.assertFalse(add_problem_by_url(session, manifests(), url, NOW).created)

    def test_rejects_other_urls(self) -> None:
        with (
            self.db.sessions() as session,
            session.begin(),
            self.assertRaises(InvalidInput),
        ):
            add_problem_by_url(
                session,
                manifests(),
                "https://codeforces.com/problemset/problem/1/A",
                NOW,
            )


if __name__ == "__main__":
    unittest.main()

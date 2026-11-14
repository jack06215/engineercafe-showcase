import json
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select

from packages.algo_tutor.catalogue.bank import (
    BankService,
    apply_bank,
    build_bank,
    popularity_of,
)
from packages.algo_tutor.catalogue.bank_file import (
    BankFetchError,
    BankQuestion,
    fetch_pages,
    load_saved,
    questions_from_pages,
)
from packages.algo_tutor.catalogue.problems import find_problem
from packages.algo_tutor.catalogue.testing import NOW, bank_pages, manifests, temp_db
from packages.algo_tutor.domain.enums import Difficulty, Source
from packages.algo_tutor.store.models import (
    ImportBatch,
    Problem,
    ProblemPopularity,
    RatingEstimate,
    Settings,
)


@dataclass
class FakeResponse:
    status_code: int
    body: Any

    def json(self) -> Any:
        return self.body


class FakeLeetCode:
    """Serves the recorded pages by `skip`, counting the requests."""

    def __init__(self, pages: list[Any], status: int = 200) -> None:
        self.pages = pages
        self.status = status
        self.calls: list[Mapping[str, Any]] = []

    def __call__(
        self, url: str, *, json: Any, headers: Mapping[str, str], timeout: float
    ) -> FakeResponse:
        self.calls.append(json["variables"])
        return FakeResponse(self.status, self.pages[json["variables"]["skip"] // 100])


def question(slug: str, likes: int) -> BankQuestion:
    return BankQuestion(slug, slug, Difficulty.EASY, 50.0, False, likes, 0, (), None)


class FetchTest(unittest.TestCase):
    def test_pages_until_total_with_a_pause_between(self) -> None:
        fake, pauses = FakeLeetCode(bank_pages()), []
        pages = fetch_pages(fake, pauses.append)
        self.assertEqual([c["skip"] for c in fake.calls], [0, 100])
        self.assertEqual(pauses, [0.3])
        self.assertEqual(len(questions_from_pages(pages)), 104)

    def test_an_error_status_or_odd_body_fails(self) -> None:
        with self.assertRaisesRegex(BankFetchError, "429"):
            fetch_pages(FakeLeetCode(bank_pages(), status=429), lambda _: None)
        with self.assertRaisesRegex(BankFetchError, "unexpected"):
            fetch_pages(FakeLeetCode([{"errors": ["nope"]}]), lambda _: None)

    def test_question_fields(self) -> None:
        by_slug = {q.slug: q for q in questions_from_pages(bank_pages())}
        self.assertEqual(by_slug["two-sum"].number, 1)
        self.assertIsNone(by_slug["made-up-contest-cup"].number)  # "LCP 01"
        self.assertTrue(any(q.paid_only for q in by_slug.values()))


class BuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bank = build_bank(questions_from_pages(bank_pages()), manifests())

    def test_estimates_only_for_problems_without_an_exact_rating(self) -> None:
        exact = manifests().exact_ratings
        self.assertIn("two-sum", self.bank.estimates)
        self.assertFalse(set(self.bank.estimates) & set(exact))
        self.assertRegex(self.bank.model.method, r"^ridge-v1 mae=\d+$")

    def test_keeps_algorithm_problems_rated_up_to_the_cap(self) -> None:
        kept = {q.slug for q in self.bank.kept}
        self.assertNotIn("combine-two-tables", kept)  # Database
        self.assertNotIn("combine-two-tables", self.bank.algorithms)
        self.assertNotIn("made-up-very-hard-problem", kept)  # estimated over 2000
        self.assertGreater(self.bank.estimates["made-up-very-hard-problem"], 2000)
        exact = manifests().exact_ratings
        for slug in kept:
            self.assertLessEqual(
                exact[slug].rating if slug in exact else self.bank.estimates[slug], 2000
            )

    def test_unknown_tags_are_reported(self) -> None:
        self.assertEqual(self.bank.unknown_tags, ["Quantum Annealing"])

    def test_popularity_is_the_likes_percentile(self) -> None:
        pop = popularity_of(
            [question("a", 1), question("b", 5), question("c", 5), question("d", 9)]
        )
        self.assertEqual([pop[s].percentile for s in "abcd"], [25, 75, 75, 100])


class ApplyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.bank = build_bank(questions_from_pages(bank_pages()), manifests())

    def tearDown(self) -> None:
        self.db.close()

    def test_adds_problems_with_tags_topics_and_numbers(self) -> None:
        with self.db.sessions() as session, session.begin():
            report = apply_bank(session, self.bank, manifests(), NOW)
        self.assertEqual(report.added, report.kept)
        with self.db.sessions() as session:
            two_sum = find_problem(session, Source.LEETCODE, "two-sum")
            assert two_sum is not None
            self.assertEqual((two_sum.number, two_sum.difficulty_label), (1, "Easy"))
            self.assertEqual(two_sum.source_tags, ["Array", "Hash Table"])
            self.assertEqual(two_sum.neetcode_category, "Arrays & Hashing")
            self.assertEqual(
                two_sum.topic_id, "hash-table"
            )  # Arrays & Hashing falls through to tags
            islands = find_problem(session, Source.LEETCODE, "number-of-islands")
            assert islands is not None
            self.assertEqual(
                islands.topic_id, "graph"
            )  # NeetCode's Graphs beats Union Find
            estimates = session.scalar(select(func.count()).select_from(RatingEstimate))
            self.assertGreater(estimates or 0, 0)
            popularity = session.scalar(
                select(func.count()).select_from(ProblemPopularity)
            )
            self.assertEqual(popularity, report.kept)
            settings = session.get(Settings, 1)
            assert settings is not None
            self.assertEqual(settings.bank_status, "done")
            batch = session.scalar(
                select(ImportBatch).where(ImportBatch.kind == "bank")
            )
            assert batch is not None
            self.assertEqual(batch.report["unknown_tags"], ["Quantum Annealing"])

    def test_a_refresh_never_overwrites_your_work(self) -> None:
        with self.db.sessions() as session, session.begin():
            apply_bank(session, self.bank, manifests(), NOW)
            p = find_problem(session, Source.LEETCODE, "two-sum")
            assert p is not None
            p.notes, p.title, p.topic_id, p.topic_overridden = (
                "my notes",
                "My Title",
                "array",
                True,
            )
            other = find_problem(session, Source.LEETCODE, "valid-anagram")
            assert other is not None
            other.topic_id = None  # stale topic: a refresh recomputes it
        with self.db.sessions() as session, session.begin():
            report = apply_bank(session, self.bank, manifests(), NOW)
            self.assertEqual(report.added, 0)
        with self.db.sessions() as session:
            p = find_problem(session, Source.LEETCODE, "two-sum")
            assert p is not None
            self.assertEqual(
                (p.notes, p.title, p.topic_id), ("my notes", "My Title", "array")
            )
            other = find_problem(session, Source.LEETCODE, "valid-anagram")
            assert other is not None
            self.assertEqual(other.topic_id, "hash-table")
            self.assertEqual(
                session.scalar(select(func.count()).select_from(ImportBatch)), 2
            )

    def test_problems_over_the_cap_already_in_the_library_get_metadata(self) -> None:
        with self.db.sessions() as session, session.begin():
            session.add(
                Problem(
                    id="hard",
                    source="leetcode",
                    external_id="made-up-very-hard-problem",
                    title="Hard one",
                    url="https://leetcode.com/problems/made-up-very-hard-problem/",
                    created_at="2026-01-01T00:00:00.000000Z",
                )
            )
        with self.db.sessions() as session, session.begin():
            apply_bank(session, self.bank, manifests(), NOW)
        with self.db.sessions() as session:
            hard = session.get(Problem, "hard")
            assert hard is not None
            self.assertEqual(
                (hard.source_tags, hard.topic_id, hard.number),
                (["Graph"], "graph", 9002),
            )
            self.assertIsNotNone(session.get(RatingEstimate, "hard"))


class ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.bank_file = self.db.path / "bank" / "leetcode-bank.json"

    def tearDown(self) -> None:
        self.db.close()

    def service(self, fake: FakeLeetCode) -> BankService:
        return BankService(
            self.db.sessions,
            manifests(),
            self.bank_file,
            post=fake,
            sleep=lambda _: None,
            clock=lambda: NOW,
        )

    def test_background_refresh_and_status(self) -> None:
        service = self.service(FakeLeetCode(bank_pages()))
        self.assertEqual(service.status().state, "idle")
        self.assertTrue(service.start())
        service.join(30)
        status = service.status()
        self.assertEqual(status.state, "done")
        self.assertGreater(status.problems, 50)
        self.assertEqual(status.fetched_at, "2026-11-08T09:00:00.000000Z")
        self.assertIsNotNone(status.last_report)
        saved = load_saved(self.bank_file)
        self.assertEqual(saved["two-sum"].title, "Two Sum")
        self.assertEqual(
            json.loads(self.bank_file.read_text())["fetched_at"],
            "2026-11-08T09:00:00.000000Z",
        )

    def test_a_failed_download_is_reported(self) -> None:
        service = self.service(FakeLeetCode(bank_pages(), status=503))
        with self.assertRaisesRegex(BankFetchError, "503"):
            service.refresh()
        status = service.status()
        self.assertEqual(status.state, "failed")
        self.assertIn("503", status.message or "")

    def test_a_stale_running_state_reads_as_failed(self) -> None:
        with self.db.sessions() as session, session.begin():
            settings = session.get(Settings, 1)
            assert settings is not None
            settings.bank_status = "running"
        self.assertEqual(self.service(FakeLeetCode([])).status().state, "failed")

    def test_load_saved_tolerates_a_missing_file(self) -> None:
        self.assertEqual(load_saved(self.db.path / "nope.json"), {})


if __name__ == "__main__":
    unittest.main()

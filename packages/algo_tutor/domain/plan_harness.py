"""An in-memory library for the plan tests.

It composes the rules the way the API layer will (start → finish → schedule
→ levels → plan), without a database, so upstream's server-level scenarios
can be replayed against the pure rules. Problem ids are their titles.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from packages.algo_tutor.domain.attempts import StartFacts, start_facts
from packages.algo_tutor.domain.enums import (
    Difficulty,
    Help,
    Outcome,
    PlanItemStatus,
    Source,
)
from packages.algo_tutor.domain.ladder import LadderAttempt, TopicLevel, training_levels
from packages.algo_tutor.domain.plan import (
    CurrentAttempt,
    ExistingItem,
    ListEntry,
    PlanContext,
    PlannedItem,
    ProblemFacts,
    StudyList,
    build_plan,
)
from packages.algo_tutor.domain.ratings import Rating, problem_rating
from packages.algo_tutor.domain.review import (
    RECOMMENDED,
    Choice,
    ReviewTarget,
    review_at_finish,
    snooze_target,
)
from packages.algo_tutor.domain.topics import TopicCatalog

MANIFESTS = Path(__file__).resolve().parent.parent / "manifests"


def load_catalog() -> TopicCatalog:
    return TopicCatalog.from_mapping(
        yaml.safe_load((MANIFESTS / "topics.yaml").read_text())
    )


@dataclass
class Problem:
    title: str
    source: Source
    label: Difficulty | None
    topic_id: str | None
    exact: float | None = None
    popularity: int | None = None
    paid_only: bool = False
    exposed: bool = False
    # Upstream's `legacyCompleted` (imported as already solved): never new
    # practice. algo_tutor has no history import; this stands in for a
    # problem attempted before the scenario starts, without touching levels.
    attempted_before: bool = False


@dataclass
class Done:
    id: str
    problem_id: str
    started_at: datetime
    finished_at: datetime
    outcome: Outcome
    help: Help
    active_seconds: int | None
    confidence: float | None


@dataclass
class Library:
    now: datetime
    target: int = 1850
    include_paid_only: bool = False
    catalog: TopicCatalog = field(default_factory=load_catalog)
    problems: dict[str, Problem] = field(default_factory=dict)
    attempts: list[Done] = field(default_factory=list)
    live: str | None = None  # problem in the unfinished attempt
    targets: dict[str, ReviewTarget] = field(default_factory=dict)
    lists: dict[Source, tuple[str, dict[str, datetime]]] = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.now.astimezone(UTC).date()

    def at(self, iso: str) -> None:
        self.now = datetime.fromisoformat(iso)

    def add(
        self,
        title: str,
        label: Difficulty | None = Difficulty.EASY,
        topic: str | None = None,
        *,
        source: Source = Source.LEETCODE,
        exact: float | None = None,
        popularity: int | None = None,
        paid_only: bool = False,
        attempted_before: bool = False,
    ) -> str:
        self.problems[title] = Problem(
            title,
            source,
            label,
            topic,
            exact,
            popularity,
            paid_only,
            attempted_before=attempted_before,
        )
        return title

    def rating(self, pid: str) -> Rating | None:
        p = self.problems[pid]
        return problem_rating(p.source, p.label, p.exact)

    def levels(self) -> list[TopicLevel]:
        ladder = [
            LadderAttempt(
                attempt_id=a.id,
                finished_at=a.finished_at,
                problem_title=self.problems[a.problem_id].title,
                topic_id=self.problems[a.problem_id].topic_id,
                rating=self.rating(a.problem_id),
                label=self.problems[a.problem_id].label,
                outcome=a.outcome,
                help=a.help,
                active_seconds=a.active_seconds,
                confidence=a.confidence,
            )
            for a in self.attempts
        ]
        return training_levels(
            ladder, [t.id for t in self.catalog.by_curriculum()], self.target
        )

    def level(self, topic_id: str) -> TopicLevel:
        return next(lv for lv in self.levels() if lv.topic_id == topic_id)

    def facts(self) -> list[ProblemFacts]:
        done = [a.problem_id for a in self.attempts]
        return [
            ProblemFacts(
                id=pid,
                source=p.source,
                title=p.title,
                topic_id=p.topic_id,
                rating=self.rating(pid),
                popularity=p.popularity,
                paid_only=p.paid_only,
                exposed=p.exposed or p.attempted_before,
                attempted=pid in done or pid == self.live or p.attempted_before,
                completed_attempts=done.count(pid),
                in_unfinished_attempt=pid == self.live,
                target=self.targets.get(pid),
            )
            for pid, p in self.problems.items()
        ]

    def context(self, day: date | None = None) -> PlanContext:
        return PlanContext(
            today=day or self.today,
            target=self.target,
            catalog=self.catalog,
            levels=self.levels(),
            problems=self.facts(),
            include_paid_only=self.include_paid_only,
        )

    def set_list(self, source: Source, name: str, titles: list[str]) -> None:
        """Replace the active list; re-added entries keep their original add time."""
        before = self.lists.get(source, ("", {}))[1]
        self.lists[source] = (name, {t: before.get(t, self.now) for t in titles})

    def study_list(self, source: Source) -> StudyList | None:
        if source not in self.lists:
            return None
        name, entries = self.lists[source]
        return StudyList(
            name,
            tuple(
                ListEntry(
                    pid,
                    self.problems[pid].title,
                    added,
                    tuple(a.started_at for a in self.attempts if a.problem_id == pid),
                )
                for pid, added in entries.items()
            ),
        )

    def plan(
        self,
        questions_per_day: int = 2,
        atcoder_per_day: int = 0,
        day: date | None = None,
        current: CurrentAttempt | None = None,
    ) -> list[PlannedItem]:
        return build_plan(
            self.context(day),
            questions_per_day=questions_per_day,
            atcoder_per_day=atcoder_per_day,
            leetcode_list=self.study_list(Source.LEETCODE),
            atcoder_list=self.study_list(Source.ATCODER),
            current=current,
        )

    def start(self, pid: str, item: PlannedItem | None = None) -> StartFacts:
        p = self.problems[pid]
        facts = start_facts(
            from_plan=item is not None,
            plan_item_kind=item.kind if item else None,
            exposed=p.exposed or p.attempted_before,
            has_completed_attempt=any(a.problem_id == pid for a in self.attempts),
        )
        p.exposed = True
        self.live = pid
        return facts

    def practise(
        self,
        pid: str,
        outcome: Outcome = Outcome.SOLVED,
        help: Help = Help.NONE,
        seconds: int | None = 300,
        confidence: float | None = None,
        *,
        item: PlannedItem | None = None,
        choice: Choice = RECOMMENDED,
    ) -> StartFacts:
        """Start (from a plan item, or the library) and finish an attempt now."""
        started = self.now
        facts = self.start(pid, item)
        review_of = item.review_of if item else None
        finished = review_at_finish(
            problem_id=pid,
            source=self.problems[pid].source,
            outcome=outcome,
            help=help,
            evidence=facts.evidence,
            study_date=self.today,
            choice=choice,
            own_target=self.targets.get(pid),
            review_of=review_of,
            idea_target=self.targets.get(review_of) if review_of else None,
        )
        for t in finished.targets:
            self.targets[t.problem_id] = t
        self.attempts.append(
            Done(
                f"a{len(self.attempts)}",
                pid,
                started,
                self.now,
                outcome,
                help,
                seconds,
                confidence,
            )
        )
        self.live = None
        return facts

    def snooze(self, pid: str, until: date) -> None:
        self.targets[pid] = snooze_target(self.targets.get(pid), pid, until)


def existing(
    items: list[PlannedItem],
    statuses: dict[int, PlanItemStatus] | None = None,
    started: set[int] | None = None,
) -> list[ExistingItem]:
    """Stored items for re-plans and replacements: index → new status / started."""
    statuses = statuses or {}
    started = started or set()
    out = []
    for n, i in enumerate(items):
        status = statuses.get(n, i.status)
        out.append(
            ExistingItem(
                id=f"item{n}",
                lane=i.lane,
                position=i.position,
                status=status,
                problem_id=i.problem_id,
                reason=i.reason,
                kind=i.kind,
                review_of=i.review_of,
                started=n in started
                or status in (PlanItemStatus.COMPLETED, PlanItemStatus.SKIPPED),
            )
        )
    return out

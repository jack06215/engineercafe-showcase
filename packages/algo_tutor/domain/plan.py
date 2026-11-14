"""The daily plan: what to practise today, in two lanes (SPEC §10).

Ported from BloomCode's `plans/shortlist.ts`, `plans.ts` and `study-list.ts`
(the built-in rules; Bloom's AI planning is not in the PoC), plus the AtCoder
lane. Pure: the API layer loads `ProblemFacts` for the library, the levels
from `ladder.training_levels`, and the active study lists, then writes the
returned items.

Differences from upstream, all from SPEC.md:

- A due idea's rule-based same-topic sibling is served as a hidden transfer
  check (kind None). Upstream only made Bloom's picks hidden and served the
  rule-based sibling as visible practice; here visible practice is the
  fallback when no fair sibling exists.
- Study-list picks have kind `list` (upstream: `topic`).
- An unplanned attempt in progress takes slot 0 and the study list still
  plans after it (upstream skipped the list then).
- Paid-only problems are skipped unless the setting is on.
- A re-plan or replacement never serves an idea that a kept item already checks.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from packages.algo_tutor.domain.constants import (
    CHECK_HEADROOM,
    NEAR_WINDOW,
    SHORTLIST_PER_TOPIC,
)
from packages.algo_tutor.domain.enums import Lane, PlanItemKind, PlanItemStatus, Source
from packages.algo_tutor.domain.ladder import TopicLevel
from packages.algo_tutor.domain.ratings import Rating
from packages.algo_tutor.domain.review import (
    DueCandidate,
    DueCheck,
    ReviewTarget,
    due_checks,
    is_waiting,
    title_key,
)
from packages.algo_tutor.domain.topics import TopicCatalog

TRANSFER_REASON = "Transfer check — spot the approach yourself"
LIST_REASON = "From your study list"
CURRENT_REASON = "Current attempt"
ATCODER_REVIEW_REASON = "Due for review — solve it again"


def ladder_reason(topic: str, level: int) -> str:
    return f"{topic} · your level {level}"


def practice_after_reason(topic: str, title: str) -> str:
    return f"{topic} · practice after {title}"


def repair_reason(topic: str, title: str) -> str:
    return f"{topic} · easier practice after {title}"


def named_list_reason(list_name: str) -> str:
    return f"From {list_name}"


@dataclass(frozen=True)
class ProblemFacts:
    """One library problem, as planning needs it (one row per problem)."""

    id: str
    source: Source
    title: str
    topic_id: str | None  # primary topic; always None for AtCoder
    rating: Rating | None  # from ratings.problem_rating; always None for AtCoder
    popularity: int | None = None  # likes percentile 0–100
    paid_only: bool = False
    exposed: bool = False
    attempted: bool = False  # any attempt, in any status
    completed_attempts: int = 0
    in_unfinished_attempt: bool = False
    target: ReviewTarget | None = None

    def due_candidate(self) -> DueCandidate | None:
        if self.target is None:
            return None
        return DueCandidate(
            problem_id=self.id,
            title=self.title,
            source=self.source,
            topic_id=self.topic_id,
            rating=None if self.rating is None else self.rating.value,
            target=self.target,
            completed_attempts=self.completed_attempts,
            in_unfinished_attempt=self.in_unfinished_attempt,
        )


@dataclass(frozen=True)
class PlanContext:
    """Everything the rules read. Build one per request."""

    today: date
    target: int
    catalog: TopicCatalog
    levels: Sequence[TopicLevel]  # every topic, from ladder.training_levels
    problems: Sequence[ProblemFacts]  # the whole library
    include_paid_only: bool = False

    def topic_name(self, topic_id: str) -> str:
        return self.catalog.get(topic_id).name

    def checks(self, source: Source) -> list[DueCheck]:
        """Due checks for one lane's source, oldest first (SPEC §8.3)."""
        candidates = [
            c
            for p in self.problems
            if p.source is source and (c := p.due_candidate()) is not None
        ]
        return due_checks(candidates, self.today)

    def allowed(self, p: ProblemFacts) -> bool:
        return self.include_paid_only or not p.paid_only


@dataclass(frozen=True)
class Candidate:
    problem_id: str
    title: str
    topic_id: str
    rating: int
    estimated: bool
    popularity: int | None


@dataclass(frozen=True)
class TopicCandidates:
    topic_id: str
    level: int
    problems: tuple[Candidate, ...]


@dataclass(frozen=True)
class PlanSpec:
    """A pick, before it has a position and status."""

    lane: Lane
    problem_id: str
    title: str
    reason: str
    kind: (
        PlanItemKind | None
    )  # None: a transfer check (hidden assessment) or the current attempt
    review_of: str | None = None  # the idea this item checks


@dataclass(frozen=True)
class PlannedItem:
    lane: Lane
    position: int  # within its lane
    status: PlanItemStatus
    problem_id: str
    title: str
    reason: str
    kind: PlanItemKind | None
    review_of: str | None


@dataclass(frozen=True)
class ListEntry:
    problem_id: str
    title: str
    added_at: datetime
    # `started_at` of every completed attempt at this problem.
    completed_attempt_starts: tuple[datetime, ...] = ()

    @property
    def done(self) -> bool:
        """A completed attempt was *started* on or after the entry was added (SPEC §5.10)."""
        return any(
            started >= self.added_at for started in self.completed_attempt_starts
        )


@dataclass(frozen=True)
class StudyList:
    """The active list for one source, entries in list order."""

    name: str
    entries: tuple[ListEntry, ...]


@dataclass(frozen=True)
class CurrentAttempt:
    """An unfinished attempt started outside today's plan."""

    problem_id: str
    title: str
    source: Source


@dataclass(frozen=True)
class ExistingItem:
    """A plan item already stored, for re-plans and replacements."""

    id: str
    lane: Lane
    position: int
    status: PlanItemStatus
    problem_id: str
    reason: str
    kind: PlanItemKind | None
    review_of: str | None
    # An attempt is linked, or it is completed or skipped: a re-plan keeps it.
    started: bool


def _nearest(
    pool: Iterable[ProblemFacts], aim: int, window: int, count: int
) -> list[ProblemFacts]:
    """Most popular within ±window of the aim; if too few, the closest ones fill up."""
    rated = [(p, abs(p.rating.value - aim)) for p in pool if p.rating is not None]
    near = sorted(
        (c for c in rated if c[1] <= window),
        key=lambda c: (
            -(c[0].popularity if c[0].popularity is not None else -1),
            c[1],
            title_key(c[0].title),
        ),
    )
    rest = sorted(
        (c for c in rated if c[1] > window), key=lambda c: (c[1], title_key(c[0].title))
    )
    return [p for p, _ in (near + rest)[:count]]


def _candidate(p: ProblemFacts) -> Candidate:
    assert p.topic_id is not None and p.rating is not None
    return Candidate(
        p.id, p.title, p.topic_id, p.rating.value, p.rating.estimated, p.popularity
    )


def shortlist(
    ctx: PlanContext,
    exclude: Iterable[str] = (),
    per_topic: int = SHORTLIST_PER_TOPIC,
) -> list[TopicCandidates]:
    """Candidates for ladder picks, weakest topic first (SPEC §10.2).

    Eligible: LeetCode, never attempted, not waiting, not in `exclude` (already
    planned), rated at most the target, with a primary topic, not paid-only
    unless that setting is on. Only topics below the target; up to
    `per_topic` each: within ±100 of the level, most popular first, then
    closest, then title, topped up with the nearest outside that range.
    Topics with no candidates are left out.
    """
    skip = set(exclude)
    by_topic: dict[str, list[ProblemFacts]] = defaultdict(list)
    for p in ctx.problems:
        if (
            p.source is Source.LEETCODE
            and not p.attempted
            and not is_waiting(p.target, ctx.today)
            and p.id not in skip
            and p.rating is not None
            and p.rating.value <= ctx.target
            and p.topic_id is not None
            and ctx.allowed(p)
        ):
            by_topic[p.topic_id].append(p)
    curriculum = {t.id: t.curriculum for t in ctx.catalog.topics}
    below = sorted(
        (lv for lv in ctx.levels if not lv.at_target),
        key=lambda lv: (lv.level, curriculum.get(lv.topic_id, len(curriculum) + 1)),
    )
    out = []
    for lv in below:
        picked = _nearest(
            by_topic.get(lv.topic_id, []), lv.level, NEAR_WINDOW, per_topic
        )
        if picked:
            out.append(
                TopicCandidates(
                    lv.topic_id, lv.level, tuple(_candidate(p) for p in picked)
                )
            )
    return out


def transfer_sibling(
    ctx: PlanContext, check: DueCheck, exclude: Iterable[str] = ()
) -> ProblemFacts | None:
    """A fair, different problem for a transfer check (SPEC §8.3).

    Same primary topic; never attempted, not exposed (so the attempt is
    genuinely unseen), rated at most min(target, original rating + 150).
    The closest within ±150 wins, then the most popular.
    """
    if check.topic_id is None:
        return None
    skip = set(exclude)
    ceiling = min(
        ctx.target,
        (check.rating if check.rating is not None else ctx.target) + CHECK_HEADROOM,
    )
    pool = [
        p
        for p in ctx.problems
        if p.source is Source.LEETCODE
        and p.topic_id == check.topic_id
        and p.id != check.problem_id
        and p.id not in skip
        and not p.exposed
        and not p.attempted
        and p.rating is not None
        and p.rating.value <= ceiling
        and ctx.allowed(p)
    ]
    found = _nearest(pool, check.rating or 0, CHECK_HEADROOM, 1)
    return found[0] if found else None


def serve_check(
    ctx: PlanContext,
    topics: Sequence[TopicCandidates],
    check: DueCheck,
    used: Iterable[str],
) -> PlanSpec | None:
    """What a due LeetCode check is served as today, never the problem itself.

    Repair (after a struggle): the first unused shortlist candidate in the
    topic. Transfer: a fair sibling as a hidden check; with none, visible
    practice from the topic's shortlist instead. None if nothing fits.
    """
    if check.topic_id is None:
        return None
    taken = set(used)
    topic = ctx.topic_name(check.topic_id)

    def from_shortlist() -> Candidate | None:
        for t in topics:
            if t.topic_id == check.topic_id:
                return next((c for c in t.problems if c.problem_id not in taken), None)
        return None

    if check.is_repair:
        easier = from_shortlist()
        if easier is None:
            return None
        return PlanSpec(
            Lane.LEETCODE,
            easier.problem_id,
            easier.title,
            repair_reason(topic, check.title),
            PlanItemKind.TOPIC,
            check.problem_id,
        )
    sibling = transfer_sibling(ctx, check, taken)
    if sibling is not None:
        return PlanSpec(
            Lane.LEETCODE,
            sibling.id,
            sibling.title,
            TRANSFER_REASON,
            None,
            check.problem_id,
        )
    practice = from_shortlist()
    if practice is None:
        return None
    return PlanSpec(
        Lane.LEETCODE,
        practice.problem_id,
        practice.title,
        practice_after_reason(topic, check.title),
        PlanItemKind.TOPIC,
        check.problem_id,
    )


def rule_picks(
    ctx: PlanContext,
    slots: int,
    exclude: Iterable[str] = (),
    served: Iterable[str] = (),
) -> list[PlanSpec]:
    """The LeetCode lane's built-in picks: due checks first (one slot each,
    skipping ideas in `served`), then one problem per topic per round,
    weakest topic first (SPEC §10.2 steps 3–4).
    """
    picks: list[PlanSpec] = []
    if slots <= 0:
        return picks
    excluded = set(exclude)
    topics = shortlist(ctx, excluded)
    used = set(excluded)
    already = set(served)
    for check in ctx.checks(Source.LEETCODE):
        if len(picks) >= slots:
            break
        if check.problem_id in already:
            continue
        spec = serve_check(ctx, topics, check, used)
        if spec is not None:
            used.add(spec.problem_id)
            picks.append(spec)
    added = True
    while added and len(picks) < slots:
        added = False
        for t in topics:
            if len(picks) >= slots:
                break
            c = next((x for x in t.problems if x.problem_id not in used), None)
            if c is None:
                continue
            used.add(c.problem_id)
            picks.append(
                PlanSpec(
                    Lane.LEETCODE,
                    c.problem_id,
                    c.title,
                    ladder_reason(ctx.topic_name(t.topic_id), t.level),
                    PlanItemKind.TOPIC,
                )
            )
            added = True
    return picks


def list_picks(
    study_list: StudyList | None,
    count: int,
    lane: Lane,
    reason: str,
    exclude: Iterable[str] = (),
) -> list[PlanSpec]:
    """The list's next entries that aren't done, in list order (repeats included:
    a problem solved before it was listed is still on the list)."""
    if study_list is None or count <= 0:
        return []
    skip = set(exclude)
    picks: list[PlanSpec] = []
    for e in study_list.entries:
        if len(picks) >= count:
            break
        if e.done or e.problem_id in skip:
            continue
        skip.add(e.problem_id)
        picks.append(PlanSpec(lane, e.problem_id, e.title, reason, PlanItemKind.LIST))
    return picks


def _atcoder_reviews(ctx: PlanContext, exclude: Iterable[str]) -> list[PlanSpec]:
    """Due AtCoder reviews: the same problem comes back (SPEC §8.5, §10.3)."""
    skip = set(exclude)
    return [
        PlanSpec(
            Lane.ATCODER,
            c.problem_id,
            c.title,
            ATCODER_REVIEW_REASON,
            PlanItemKind.LIST,
        )
        for c in ctx.checks(Source.ATCODER)
        if c.problem_id not in skip
    ]


def _place(
    lanes: dict[Lane, list[PlanSpec]],
    start: dict[Lane, int],
    has_active: bool,
    active_first: PlanSpec | None = None,
) -> list[PlannedItem]:
    """Positions within each lane; one item active (the current attempt's, else
    the first new one, LeetCode lane first), unless one already is."""
    order = [*lanes[Lane.LEETCODE], *lanes[Lane.ATCODER]]
    active = None if has_active else (active_first or (order[0] if order else None))
    items: list[PlannedItem] = []
    for lane in (Lane.LEETCODE, Lane.ATCODER):
        for offset, s in enumerate(lanes[lane]):
            items.append(
                PlannedItem(
                    lane=lane,
                    position=start[lane] + offset,
                    status=PlanItemStatus.ACTIVE
                    if s is active
                    else PlanItemStatus.QUEUED,
                    problem_id=s.problem_id,
                    title=s.title,
                    reason=s.reason,
                    kind=s.kind,
                    review_of=s.review_of,
                )
            )
    return items


def build_plan(
    ctx: PlanContext,
    *,
    questions_per_day: int,
    atcoder_per_day: int,
    leetcode_list: StudyList | None = None,
    atcoder_list: StudyList | None = None,
    current: CurrentAttempt | None = None,
) -> list[PlannedItem]:
    """A new day's plan (`ensure` on an untouched plan, SPEC §10.1–§10.3).

    LeetCode lane, `questions_per_day` slots: an unplanned attempt in
    progress (slot 0), the active list's next entries (dropping the last if
    the list would fill every slot while a check is due), due checks, then
    ladder picks. AtCoder lane: due AtCoder reviews (always), then up to
    `atcoder_per_day` new entries from the active AtCoder list.
    """
    lanes: dict[Lane, list[PlanSpec]] = {Lane.LEETCODE: [], Lane.ATCODER: []}
    current_spec = None
    if current is not None:
        lane = Lane.ATCODER if current.source is Source.ATCODER else Lane.LEETCODE
        current_spec = PlanSpec(
            lane, current.problem_id, current.title, CURRENT_REASON, None
        )
        lanes[lane].append(current_spec)

    lc = lanes[Lane.LEETCODE]
    remaining = questions_per_day - len(lc)
    listed = list_picks(
        leetcode_list, remaining, Lane.LEETCODE, LIST_REASON, (s.problem_id for s in lc)
    )
    if (
        listed
        and len(listed) == remaining
        and questions_per_day > 1
        and ctx.checks(Source.LEETCODE)
    ):
        listed = listed[:-1]
    lc.extend(listed)
    lc.extend(rule_picks(ctx, questions_per_day - len(lc), (s.problem_id for s in lc)))

    at = lanes[Lane.ATCODER]
    at.extend(_atcoder_reviews(ctx, (s.problem_id for s in at)))
    if atcoder_list is not None:
        at.extend(
            list_picks(
                atcoder_list,
                atcoder_per_day,
                Lane.ATCODER,
                named_list_reason(atcoder_list.name),
                (s.problem_id for s in at),
            )
        )
    return _place(lanes, {Lane.LEETCODE: 0, Lane.ATCODER: 0}, False, current_spec)


@dataclass(frozen=True)
class Rebuild:
    """A re-plan: delete `removed` (unstarted items), insert `added`."""

    removed: tuple[str, ...]
    added: tuple[PlannedItem, ...]


def rebuild_plan(
    ctx: PlanContext,
    items: Sequence[ExistingItem],
    *,
    questions_per_day: int,
    atcoder_per_day: int,
    leetcode_list: StudyList | None = None,
    atcoder_list: StudyList | None = None,
) -> Rebuild:
    """ "Re-plan today" (SPEC §10.1): keep started and finished items, re-pick the rest.

    The list takes the free slots first, then the rules; there is no
    room-for-a-check rule here, as upstream.
    """
    kept = [i for i in items if i.started]
    removed = tuple(i.id for i in items if not i.started)
    kept_ids = [i.problem_id for i in kept]
    live = [i for i in kept if i.status is not PlanItemStatus.SKIPPED]
    served = [i.review_of for i in live if i.review_of is not None]
    lanes: dict[Lane, list[PlanSpec]] = {Lane.LEETCODE: [], Lane.ATCODER: []}

    lc_free = questions_per_day - sum(1 for i in live if i.lane is Lane.LEETCODE)
    from_list = list_picks(leetcode_list, lc_free, Lane.LEETCODE, LIST_REASON, kept_ids)
    rules = rule_picks(
        ctx,
        max(0, lc_free - len(from_list)),
        [*kept_ids, *(s.problem_id for s in from_list)],
        served,
    )
    lanes[Lane.LEETCODE] = [*from_list, *rules]

    reviews = _atcoder_reviews(ctx, kept_ids)
    kept_new = sum(
        1
        for i in live
        if i.lane is Lane.ATCODER
        and i.reason not in (ATCODER_REVIEW_REASON, CURRENT_REASON)
    )
    fresh = (
        list_picks(
            atcoder_list,
            atcoder_per_day - kept_new,
            Lane.ATCODER,
            named_list_reason(atcoder_list.name),
            [*kept_ids, *(s.problem_id for s in reviews)],
        )
        if atcoder_list is not None
        else []
    )
    lanes[Lane.ATCODER] = [*reviews, *fresh]

    start = {
        lane: max((i.position for i in kept if i.lane is lane), default=-1) + 1
        for lane in (Lane.LEETCODE, Lane.ATCODER)
    }
    has_active = any(i.status is PlanItemStatus.ACTIVE for i in kept)
    return Rebuild(removed, tuple(_place(lanes, start, has_active)))


def replacement(
    ctx: PlanContext,
    item: ExistingItem,
    items: Sequence[ExistingItem],
    atcoder_list: StudyList | None = None,
) -> PlanSpec | None:
    """Replace (`swap`, SPEC §10.4): one rule-based replacement, or None
    ("No other question fits your current training levels").

    LeetCode: the rules' next pick, never a problem already on the plan nor
    an idea another live item checks. AtCoder: the active list's next entry.
    Upstream gives the replacement the swapped item's status, appends it to
    the lane, and skips the swapped item.
    """
    on_plan = [i.problem_id for i in items]
    if item.lane is Lane.ATCODER:
        if atcoder_list is None:
            return None
        picks = list_picks(
            atcoder_list, 1, Lane.ATCODER, named_list_reason(atcoder_list.name), on_plan
        )
        return picks[0] if picks else None
    served = [
        i.review_of
        for i in items
        if i.id != item.id
        and i.review_of is not None
        and i.status is not PlanItemStatus.SKIPPED
    ]
    picks = rule_picks(ctx, 1, on_plan, served)
    return picks[0] if picks else None

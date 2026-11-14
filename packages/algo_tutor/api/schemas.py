"""The HTTP contract (SPEC §15): every request and response body.

JSON field names are snake_case, the same as the database. Dates are
`YYYY-MM-DD` in the learner's timezone; timestamps are ISO-8601 UTC. The web
client's types are generated from these models (`export_schema.py`), so this
module is the single source of truth for the shapes on the wire.

Inputs forbid unknown fields. A PATCH body only changes the fields it sends
(`model_fields_set`), so `null` and "absent" mean different things there.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import (
    AttemptStatus,
    BundledSet,
    Context,
    Difficulty,
    DifficultyFeel,
    Disposition,
    Evidence,
    Help,
    HintLevel,
    HintRole,
    Lane,
    Language,
    ListKind,
    MistakeLabel,
    Outcome,
    PlanItemKind,
    PlanItemStatus,
    ReportStatus,
    Result,
    ReviewAction,
    ReviewChoice,
    ReviewStage,
    Source,
    TimerAction,
    TutorErrorKind,
)

MMSS = r"^[0-9]{1,4}:[0-5][0-9]$"
IDEMPOTENCY_KEY = r"^[A-Za-z0-9_.:-]{1,200}$"

Version = Annotated[int, Field(ge=1)]
Code = Annotated[str, StringConstraints(max_length=constants.MAX_CODE_CHARS)]
Notes = Annotated[str, StringConstraints(max_length=constants.MAX_NOTES_CHARS)]
NotebookText = Annotated[
    str, StringConstraints(max_length=constants.MAX_NOTEBOOK_CHARS)
]
Title = Annotated[
    str, StringConstraints(min_length=1, max_length=constants.MAX_TITLE_CHARS)
]


class Out(BaseModel):
    """A response body."""

    model_config = ConfigDict(from_attributes=True)


class In(BaseModel):
    """A request body: unknown fields are a 422."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- errors


class ErrorDetail(Out):
    """The code, message and optional tutor error kind of an API error."""

    code: str  # SPEC §18.1, e.g. STALE, ACTIVE_ATTEMPT, HIDDEN_ASSESSMENT
    message: str
    kind: TutorErrorKind | None = None  # only with TUTOR_UNAVAILABLE


class ErrorBody(Out):
    """The body of every error response."""

    error: ErrorDetail


class Health(Out):
    """GET /health."""

    status: Literal["ok"] = "ok"


# ---------------------------------------------------------------- shared pieces


class RatingOut(Out):
    """A problem rating, exact or estimated."""

    value: int
    estimated: bool  # shown with "≈"


class ProblemBrief(Out):
    """Enough to show a row and link out.

    Never carries topic, tags or patterns, so it is safe inside a hidden
    assessment.
    """

    id: str
    source: Source
    title: str
    url: str
    number: int | None
    contest: str | None
    difficulty: Difficulty | None
    rating: RatingOut | None


class Notebook(Out):
    """A notebook of cues, pitfalls and notes, versioned for edits."""

    cues: str
    pitfalls: str
    notes: str
    version: int
    updated_at: datetime | None


class NotebookPatch(In):
    """PATCH body for a notebook; omitted fields stay unchanged."""

    version: Version
    cues: NotebookText | None = None
    pitfalls: NotebookText | None = None
    notes: NotebookText | None = None


# ---------------------------------------------------------------- setup and settings


class SetupState(Out):
    """GET /setup: the onboarding state."""

    onboarding_complete: bool
    timezone: str
    questions_per_day: int


class SetupIn(In):
    """POST /setup: the first-run choices."""

    questions_per_day: Annotated[int, Field(ge=1, le=20)] = (
        constants.QUESTIONS_PER_DAY_DEFAULT
    )
    download_bank: bool = True
    follow: BundledSet | None = None


class BankStatus(Out):
    """The LeetCode bank download status and catalogue counts."""

    status: Literal["never", "running", "done", "failed"]
    fetched_at: datetime | None
    pages_done: int
    pages_total: int | None
    problems: int  # LeetCode problems in the catalogue
    estimated: int  # of which carry a ridge estimate
    method: str | None  # e.g. "ridge-v1 mae=148"
    unknown_tags: list[str]  # tags in neither Appendix A nor its unmapped list
    error: str | None


class SettingsOut(Out):
    """The learner's settings."""

    timezone: str
    questions_per_day: int
    atcoder_per_day: int
    target_rating: int
    include_paid_only: bool
    onboarding_complete: bool
    active_list_leetcode: str | None
    active_list_atcoder: str | None
    last_backup_at: datetime | None
    bank: BankStatus


class SettingsPatch(In):
    """PATCH body for settings; omitted fields stay unchanged."""

    questions_per_day: Annotated[int, Field(ge=1, le=20)] | None = None
    atcoder_per_day: Annotated[int, Field(ge=0, le=10)] | None = None
    target_rating: Annotated[int, Field(ge=1200, le=2600, multiple_of=50)] | None = None
    include_paid_only: bool | None = None


# ---------------------------------------------------------------- problems


class ReviewTargetOut(Out):
    """When and how a problem is next due for review."""

    problem_id: str
    recommended_date: date | None
    effective_date: date | None
    action: ReviewAction
    stage: ReviewStage
    version: int


class AttemptSummary(Out):
    """A short view of one attempt."""

    id: str
    problem_id: str
    status: AttemptStatus
    context: Context
    language: Language
    outcome: Outcome | None
    help: Help
    confidence: int | None
    active_seconds: int
    started_at: datetime
    finished_at: datetime | None
    study_date: date


class ProblemRow(Out):
    """A library row (SPEC §14 Library)."""

    problem: ProblemBrief
    topic_id: str | None
    source_tags: list[str]
    patterns: list[str]
    paid_only: bool
    popularity: int | None
    latest_outcome: Outcome | None  # None: never finished
    latest_active_seconds: int | None
    latest_confidence: int | None
    next_review_date: date | None


class ProblemPage(Out):
    """One page of the problem library."""

    items: list[ProblemRow]
    total: int
    page: int
    page_size: int


SolveTimeBucket = Literal["0-10", "10-20", "20-30", "30-45", "45+", "unknown"]
ConfidenceBucket = Literal["low", "medium", "high", "unknown"]  # <3, 3–4, ≥4
LatestFilter = Literal["solved", "not_solved", "stopped", "not_submitted"]
ProblemSort = Literal[
    "title", "difficulty", "rating", "latest", "time", "confidence", "next_review"
]


class ProblemQuery(In):
    """Query string of GET /problems."""

    q: str | None = None  # title or URL substring
    source: Source | None = None
    topic: str | None = None  # topic id, or "none"
    tag: str | None = None  # a LeetCode tag
    pattern: str | None = None  # pattern id
    difficulty: Difficulty | None = None
    latest: LatestFilter | None = None
    list_id: str | None = None
    time: SolveTimeBucket | None = None
    confidence: ConfidenceBucket | None = None
    sort: ProblemSort = "title"
    order: Literal["asc", "desc"] = "asc"
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 25


class ListRef(Out):
    """The ID and name of a study list."""

    id: str
    name: str


class ProblemDetail(Out):
    """The full view of one problem."""

    problem: ProblemBrief
    external_id: str
    paid_only: bool
    source_tags: list[str]
    neetcode_category: str | None
    topic_id: str | None
    topic_overridden: bool
    patterns: list[str]
    notes: str
    exposed: bool
    lists: list[ListRef]
    review: ReviewTargetOut | None
    attempts: list[AttemptSummary]  # newest first


class ProblemCreate(In):
    """POST body to add a problem by URL."""

    url: str
    title: Title | None = None  # required for AtCoder (never fetched)
    difficulty: Difficulty | None = None


class ProblemPatch(In):
    """PATCH body for a problem's notes, topic and pattern labels.

    Send `topic_id` to override the primary topic (null = "None"); send
    `reset_topic: true` to go back to the automatic topic.
    """

    notes: Notes | None = None
    topic_id: str | None = None
    reset_topic: bool | None = None
    patterns: list[str] | None = None


class SuggestedPath(Out):
    """A suggested solution file path, and whether the file exists."""

    path: str  # repo-relative
    exists: bool


class ReviewPatch(In):
    """PATCH body to reschedule a problem's next review."""

    version: Version
    action: ReviewAction
    review_date: date | None = None  # required for manual and snooze


# ---------------------------------------------------------------- attempts


class Signals(Out):
    """The learner's own signals about an attempt."""

    accepted_first_try: bool | None
    difficulty: DifficultyFeel | None


class Report(Out):
    """The tutor's report on an attempt, by section."""

    status: ReportStatus
    summary: str | None
    strengths: str | None
    improvements: str | None
    complexity: str | None
    practice: str | None
    error_kind: TutorErrorKind | None
    error_message: str | None
    model: str | None
    reported_at: datetime | None


class AttemptOut(Out):
    """One attempt.

    While a hidden assessment runs, the reflection fields, signals and report of
    completed attempts are null (SPEC §9).
    """

    id: str
    problem: ProblemBrief
    plan_item_id: str | None
    context: Context
    evidence: Evidence
    status: AttemptStatus
    version: int
    language: Language
    code: str
    solution_path: str | None  # None: the in-app editor
    code_copied_at: datetime | None
    notes: str
    outcome: Outcome | None
    help: Help
    confidence: int | None
    active_seconds: int
    gap_seconds: int
    running_since: datetime | None
    last_heartbeat_at: datetime | None
    needs_gap_decision: bool
    started_at: datetime
    finished_at: datetime | None
    study_date: date
    next_review_date: date | None
    strongest_hint: HintLevel | None  # prefills the finish form's Help
    takeaway: str | None
    mistake_labels: list[MistakeLabel] | None
    signals: Signals | None
    patterns: list[str] | None  # the problem's pattern labels
    report: Report | None
    server_now: datetime  # for the stopwatch display


class AttemptStart(In):
    """POST body to start an attempt."""

    problem_id: str
    plan_item_id: str | None = None
    language: Language = Language.PYTHON


class DraftPatch(In):
    """PATCH body for an attempt's draft.

    Send `solution_path` with a path to link (and copy) a file, or with null to
    switch to the in-app editor.
    """

    version: Version
    code: Code | None = None
    notes: Notes | None = None
    language: Language | None = None
    solution_path: str | None = None


class TimerIn(In):
    """A timer event for an attempt."""

    version: Version
    action: TimerAction
    include_gap: bool | None = None  # required to resume after a gap


class FinishIn(In):
    """POST body to finish an attempt."""

    version: Version
    outcome: Outcome
    help: Help
    time: Annotated[str, StringConstraints(pattern=MMSS)]
    confidence: Annotated[int, Field(ge=1, le=5)] | None = None
    review_choice: ReviewChoice = ReviewChoice.RECOMMENDED
    review_date: date | None = None  # required for manual
    language: Language
    notes: Notes = ""
    code: Code | None = None  # editor mode; a linked file is copied instead


class FinishOut(Out):
    """The finished attempt and its next review."""

    attempt: AttemptOut
    next_review_date: date | None
    review_stage: ReviewStage


class ReflectionPatch(In):
    """PATCH body for an attempt's mistake labels and takeaway."""

    version: Version
    mistake_labels: Annotated[
        list[MistakeLabel], Field(max_length=constants.MAX_MISTAKE_LABELS)
    ]
    takeaway: Annotated[str, StringConstraints(max_length=constants.MAX_TAKEAWAY_CHARS)]


class SignalsPatch(In):
    """PATCH body for an attempt's signals; omitted fields stay unchanged."""

    accepted_first_try: bool | None = None
    difficulty: DifficultyFeel | None = None


class HintMessage(Out):
    """One message of an attempt's hint conversation."""

    id: str
    position: int
    role: HintRole
    text: str
    stuck_at_seconds: int | None
    level: HintLevel | None
    hint: str | None
    analysis: str | None
    created_at: datetime


class HintConversation(Out):
    """An attempt's hint conversation and the strongest hint given."""

    messages: list[HintMessage]
    strongest_level: HintLevel | None


class HintIn(In):
    """POST body with the learner's message to the tutor."""

    text: Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class HintReply(Out):
    """The tutor's reply.

    Hints append to the attempt's notes, which bumps its version; the client
    must adopt `attempt_version` and `notes`.
    """

    message: HintMessage
    attempt_version: int
    notes: str
    strongest_level: HintLevel | None


# ---------------------------------------------------------------- plans and desk


class PlanItemOut(Out):
    """A plan row. `review_of` is never sent: it would give a transfer check away."""

    id: str
    lane: Lane
    position: int
    problem: ProblemBrief
    attempt_id: str | None
    status: PlanItemStatus
    reason: str
    kind: PlanItemKind | None  # None: a transfer check
    disposition: Disposition | None
    is_check: bool
    signals: Signals | None  # for finished items: Too easy / Too hard


class PlanOut(Out):
    """A daily plan with the items of both lanes."""

    id: str
    plan_date: date
    timezone: str
    version: int
    items: list[PlanItemOut]  # both lanes, each in position order


class ActiveAttemptBrief(Out):
    """The running attempt; its title is hidden during the assessment."""

    id: str
    problem_title: str | None  # None during a hidden assessment
    context: Context
    status: AttemptStatus


class Desk(Out):
    """GET /desk.

    During a hidden assessment only `hidden_assessment` and `active_attempt` are
    filled ("Assessment in progress" + Resume).
    """

    hidden_assessment: bool
    active_attempt: ActiveAttemptBrief | None
    today: date
    plan: PlanOut | None
    left_today: int
    total_today: int
    checks_due: int
    bank_empty: bool


class PlanVersionIn(In):
    """A body that carries only the plan version."""

    version: Version


class ReorderIn(In):
    """The new order of every item in one plan lane."""

    version: Version
    lane: Lane
    item_ids: list[str]  # every item of the lane, once


class DispositionIn(In):
    """Swap, snooze or skip a plan item."""

    version: Version
    action: Disposition
    snooze_until: date | None = None  # required for snooze, in the future


# ---------------------------------------------------------------- lists and packs


class ListSummary(Out):
    """A study list with its progress."""

    id: str
    name: str
    source: Source
    kind: ListKind
    origin: str | None
    source_url: str | None
    created_at: datetime
    active: bool
    done: int
    total: int


class ListEntryOut(Out):
    """One problem on a study list."""

    problem: ProblemBrief
    position: int
    section: str | None
    added_at: datetime
    done: bool


class UnresolvedLine(Out):
    """A pasted line that matched no problem, and why."""

    line: str
    reason: str


class ListDetail(Out):
    """A study list with its entries."""

    summary: ListSummary
    entries: list[ListEntryOut]
    # PATCH with `add_text`: the lines that couldn't be added.
    unresolved: list[UnresolvedLine] = Field(default_factory=list)


class ListEntriesIn(In):
    """Body to create lists from pasted text, one entry per line."""

    name: Title
    text: Annotated[str, StringConstraints(max_length=200_000)]  # one entry per line


class ResolvedEntry(Out):
    """A pasted line matched to a problem."""

    line: str
    problem_id: str | None  # None: will be added to the library
    title: str
    source: Source


class PreviewGroup(Out):
    """The entries that will form the list for one source."""

    source: Source
    name: str  # the list each source becomes
    entries: list[ResolvedEntry]


class ListPreview(Out):
    """Preview of the lists that pasted text would create."""

    groups: list[PreviewGroup]
    unresolved: list[str]  # lines that matched nothing
    unresolved_reasons: list[UnresolvedLine] = Field(default_factory=list)


class ListCreated(Out):
    """The lists created from pasted text, and the lines left out."""

    lists: list[ListSummary]
    unresolved: list[str]
    unresolved_reasons: list[UnresolvedLine] = Field(default_factory=list)


class ListPatch(In):
    """Own lists only.

    `problem_ids` is the full new order (drop an id to remove it); `add_text`
    resolves and appends more entries.
    """

    name: Title | None = None
    problem_ids: list[str] | None = None
    add_text: str | None = None


class PackReport(Out):
    """The result of importing or dry-running a question pack."""

    import_id: str
    dry_run: bool
    already_applied: bool
    summary: ListSummary | None
    problems_created: int
    problems_existing: int
    entries_added: int
    patterns_added: int = 0
    # A pack with questions from both sources makes one list per source.
    lists_created: list[str] = Field(default_factory=list)
    lists_extended: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- topics, patterns, mistakes


class LevelChange(Out):
    """The last change to a topic level and the attempt that caused it."""

    delta: int
    attempt_id: str
    problem_title: str
    rating: int
    estimated: bool
    result: Result
    study_date: date


class TopicLevel(Out):
    """The learner's level in one topic."""

    id: str
    name: str
    curriculum: int
    level: int
    at_target: bool
    attempts: int
    last_change: LevelChange | None


class TopicLevels(Out):
    """The learner's level in every topic."""

    target_rating: int
    topics: list[TopicLevel]  # curriculum order


class NotebookProblem(Out):
    """An attempted problem shown on a notebook page."""

    problem: ProblemBrief
    attempts: int
    latest_outcome: Outcome | None


class TopicDetail(Out):
    """A topic page: level, notebook and attempted problems."""

    level: TopicLevel
    target_rating: int
    notebook: Notebook
    problems: list[NotebookProblem]  # attempted ones only
    unseen_count: int


class PatternSummary(Out):
    """A pattern with its attempted-problem count."""

    id: str
    name: str
    position: int
    missing: bool
    problems: int


class PatternDetail(Out):
    """A pattern page: README, notebook and attempted problems."""

    pattern: PatternSummary
    readme_path: str  # repo-relative
    readme_markdown: str | None  # None: "README not found at <readme_path>"
    notebook: Notebook
    problems: list[NotebookProblem]


class MistakeEntry(Out):
    """A finished attempt with its mistake labels and takeaway."""

    attempt_id: str
    problem: ProblemBrief
    finished_at: datetime
    mistake_labels: list[MistakeLabel]
    takeaway: str


class MistakeList(Out):
    """Attempts with mistakes, newest first."""

    items: list[MistakeEntry]  # newest first


# ---------------------------------------------------------------- tutor and backups


class TutorStatus(Out):
    """The tutor's settings and pending report count."""

    enabled: bool
    provider: Literal["ollama", "openai", "azure"]
    model: str
    leaves_machine: bool  # true for openai and azure (SPEC §12.6)
    pending_reports: int


class TutorTest(Out):
    """Result of a test call to the tutor model."""

    ok: bool
    provider: str
    model: str
    latency_ms: int | None
    error_kind: TutorErrorKind | None
    message: str | None


class BackupStatus(Out):
    """The last backup and how many backups are kept."""

    last_backup_at: datetime | None
    path: str | None
    kept: int

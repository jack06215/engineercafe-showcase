"""The database schema (SPEC.md §16) as SQLAlchemy 2 models.

IDs are UUID text, dates `YYYY-MM-DD` in the learner's timezone, timestamps
ISO-8601 UTC as written by `store.timeutil.iso_utc`. Enumerated columns hold
the string values of `domain.enums`, enforced by CHECK constraints; JSON
columns are checked with `json_valid`.
"""

from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import (
    AttemptStatus,
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
    Outcome,
    PlanItemKind,
    PlanItemStatus,
    ReportStatus,
    ReviewAction,
    ReviewStage,
    Source,
    TutorErrorKind,
)

# Names constraints so a later migration can refer to them.
_NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# Room for an exception's message; the tutor worker truncates to fit.
MAX_REPORT_ERROR_MESSAGE_CHARS = 2000


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dict[str, Any]: JSON,
        list[Any]: JSON,
    }


def _one_of(column: str, values: type[StrEnum], *, nullable: bool = False) -> str:
    listed = ", ".join(f"'{v.value}'" for v in values)
    check = f"{column} IN ({listed})"
    return f"{column} IS NULL OR {check}" if nullable else check


def _between(column: str, low: int, high: int, *, nullable: bool = False) -> str:
    check = f"{column} BETWEEN {low} AND {high}"
    return f"{column} IS NULL OR {check}" if nullable else check


def _json(column: str) -> str:
    return f"json_valid({column})"


def _bool(column: str) -> Boolean:
    """A 0/1 column. The CHECK is named after the column for the naming convention."""
    return Boolean(create_constraint=True, name=column)


class Settings(Base):
    """The one settings row (id 1)."""

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            _between("questions_per_day", *constants.QUESTIONS_PER_DAY_RANGE),
            name="questions_per_day",
        ),
        CheckConstraint(
            _between("atcoder_per_day", *constants.ATCODER_PER_DAY_RANGE),
            name="atcoder_per_day",
        ),
        CheckConstraint(
            f"{_between('target_rating', constants.TARGET_MIN, constants.TARGET_MAX)}"
            f" AND target_rating % {constants.TARGET_STEP} = 0",
            name="target_rating",
        ),
        CheckConstraint(
            "bank_status IS NULL OR bank_status IN ('running', 'done', 'failed')",
            name="bank_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    timezone: Mapped[str] = mapped_column(String)
    questions_per_day: Mapped[int] = mapped_column(
        default=constants.QUESTIONS_PER_DAY_DEFAULT
    )
    atcoder_per_day: Mapped[int] = mapped_column(
        default=constants.ATCODER_PER_DAY_DEFAULT
    )
    target_rating: Mapped[int] = mapped_column(default=constants.DEFAULT_TARGET)
    include_paid_only: Mapped[bool] = mapped_column(
        _bool("include_paid_only"), default=False
    )
    onboarding_complete: Mapped[bool] = mapped_column(
        _bool("onboarding_complete"), default=False
    )
    active_list_leetcode: Mapped[str | None] = mapped_column(
        ForeignKey("lists.id", ondelete="SET NULL")
    )
    active_list_atcoder: Mapped[str | None] = mapped_column(
        ForeignKey("lists.id", ondelete="SET NULL")
    )
    bank_status: Mapped[str | None]  # running | done | failed; None = never downloaded
    bank_fetched_at: Mapped[str | None]
    last_backup_at: Mapped[str | None]


class Topic(Base):
    """One of the 34 topics, seeded from manifests/topics.yaml, with its notebook."""

    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(
        String, primary_key=True
    )  # slug, e.g. "two-pointers"
    name: Mapped[str]
    priority: Mapped[int] = mapped_column(unique=True)
    curriculum: Mapped[int] = mapped_column(unique=True)
    cues: Mapped[str] = mapped_column(Text, default="")
    pitfalls: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    notebook_version: Mapped[int] = mapped_column(default=1)
    notebook_updated_at: Mapped[str | None]


class Pattern(Base):
    """A common_coding_pattern folder, scanned at startup (SPEC §5.8), with its notebook."""

    __tablename__ = "patterns"

    id: Mapped[str] = mapped_column(
        String, primary_key=True
    )  # folder name, e.g. "01_sliding_window"
    name: Mapped[str]
    readme_path: Mapped[str]  # relative to the repo root
    position: Mapped[int]
    missing: Mapped[bool] = mapped_column(_bool("missing"), default=False)
    cues: Mapped[str] = mapped_column(Text, default="")
    pitfalls: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    notebook_version: Mapped[int] = mapped_column(default=1)
    notebook_updated_at: Mapped[str | None]


class Problem(Base):
    __tablename__ = "problems"
    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        CheckConstraint(_one_of("source", Source), name="source"),
        CheckConstraint("kind = 'problem'", name="kind"),
        CheckConstraint(
            _one_of("difficulty_label", Difficulty, nullable=True), name="difficulty"
        ),
        CheckConstraint(
            f"length(title) BETWEEN 1 AND {constants.MAX_TITLE_CHARS}", name="title"
        ),
        CheckConstraint(_json("source_tags"), name="source_tags"),
        CheckConstraint("source = 'atcoder' OR contest IS NULL", name="contest"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str]
    external_id: Mapped[str]  # LeetCode slug or AtCoder task id
    kind: Mapped[str] = mapped_column(default="problem")
    number: Mapped[int | None]  # LeetCode's problem number
    contest: Mapped[str | None]  # AtCoder only
    title: Mapped[str]
    url: Mapped[str]
    difficulty_label: Mapped[str | None]
    paid_only: Mapped[bool] = mapped_column(_bool("paid_only"), default=False)
    source_tags: Mapped[list[Any]] = mapped_column(default=list)
    neetcode_category: Mapped[str | None]
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id"), index=True)
    topic_overridden: Mapped[bool] = mapped_column(
        _bool("topic_overridden"), default=False
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    exposed: Mapped[bool] = mapped_column(_bool("exposed"), default=False)
    created_at: Mapped[str]


class ProblemPattern(Base):
    __tablename__ = "problem_patterns"

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    )
    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class RatingEstimate(Base):
    """A fitted rating for a problem without a contest rating (SPEC §5.5)."""

    __tablename__ = "rating_estimates"

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    )
    rating: Mapped[int]
    method: Mapped[str]  # e.g. "ridge-v1 mae=148"
    fitted_at: Mapped[str]


class ProblemPopularity(Base):
    __tablename__ = "problem_popularity"
    __table_args__ = (
        CheckConstraint(_between("percentile", 0, 100), name="percentile"),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    )
    likes: Mapped[int]
    dislikes: Mapped[int]
    percentile: Mapped[int]


class StudyList(Base):
    __tablename__ = "lists"
    __table_args__ = (
        CheckConstraint(_one_of("source", Source), name="source"),
        CheckConstraint(_one_of("kind", ListKind), name="kind"),
        Index("uq_lists_name_nocase", text("name COLLATE NOCASE"), unique=True),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    source: Mapped[str]
    kind: Mapped[str]
    origin: Mapped[str | None]  # bundled set id, or the pack's import id
    source_url: Mapped[str | None]
    created_at: Mapped[str]


class ListEntry(Base):
    __tablename__ = "list_entries"

    list_id: Mapped[str] = mapped_column(
        ForeignKey("lists.id", ondelete="CASCADE"), primary_key=True
    )
    problem_id: Mapped[str] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int]
    section: Mapped[str | None]
    added_at: Mapped[str]


class DailyPlan(Base):
    __tablename__ = "daily_plans"
    __table_args__ = (UniqueConstraint("date", "timezone"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[str]
    timezone: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        CheckConstraint(_one_of("lane", Lane), name="lane"),
        CheckConstraint(_one_of("status", PlanItemStatus), name="status"),
        CheckConstraint(_one_of("kind", PlanItemKind, nullable=True), name="kind"),
        CheckConstraint(
            _one_of("disposition", Disposition, nullable=True), name="disposition"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("daily_plans.id", ondelete="CASCADE"), index=True
    )
    lane: Mapped[str]
    position: Mapped[int]
    problem_id: Mapped[str] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE")
    )
    attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("attempts.id", ondelete="SET NULL", use_alter=True)
    )
    status: Mapped[str]
    reason: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str | None]  # None: a transfer check, run hidden
    review_of: Mapped[str | None] = mapped_column(
        ForeignKey("problems.id", ondelete="SET NULL")
    )
    disposition: Mapped[str | None]


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint(_one_of("context", Context), name="context"),
        CheckConstraint(_one_of("status", AttemptStatus), name="status"),
        CheckConstraint(_one_of("language", Language), name="language"),
        CheckConstraint(_one_of("evidence", Evidence), name="evidence"),
        CheckConstraint(_one_of("help", Help), name="help"),
        CheckConstraint(_one_of("outcome", Outcome, nullable=True), name="outcome"),
        CheckConstraint(_between("confidence", 1, 5, nullable=True), name="confidence"),
        CheckConstraint(
            _between("active_seconds", 0, constants.MAX_ACTIVE_SECONDS),
            name="active_seconds",
        ),
        CheckConstraint("gap_seconds IS NULL OR gap_seconds >= 0", name="gap_seconds"),
        CheckConstraint(f"length(code) <= {constants.MAX_CODE_CHARS}", name="code"),
        CheckConstraint(f"length(notes) <= {constants.MAX_NOTES_CHARS}", name="notes"),
        CheckConstraint(
            f"length(takeaway) <= {constants.MAX_TAKEAWAY_CHARS}", name="takeaway"
        ),
        CheckConstraint(
            f"{_json('mistake_labels')} AND json_array_length(mistake_labels)"
            f" <= {constants.MAX_MISTAKE_LABELS}",
            name="mistake_labels",
        ),
        CheckConstraint(_one_of("report_status", ReportStatus), name="report_status"),
        CheckConstraint(
            _one_of("report_error", TutorErrorKind, nullable=True), name="report_error"
        ),
        CheckConstraint(
            "report_error_message IS NULL OR length(report_error_message)"
            f" <= {MAX_REPORT_ERROR_MESSAGE_CHARS}",
            name="report_error_message",
        ),
        CheckConstraint("report IS NULL OR json_valid(report)", name="report"),
        CheckConstraint(
            "status = 'completed' OR outcome IS NULL", name="outcome_when_completed"
        ),
        # At most one unfinished attempt in the whole app (SPEC §6.1).
        Index(
            "uq_attempts_one_unfinished",
            text("(1)"),
            unique=True,
            sqlite_where=text("status IN ('active', 'paused')"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    problem_id: Mapped[str] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), index=True
    )
    plan_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("plan_items.id", ondelete="SET NULL")
    )
    context: Mapped[str]
    status: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    language: Mapped[str] = mapped_column(default=Language.PYTHON.value)
    code: Mapped[str] = mapped_column(Text, default="")
    solution_path: Mapped[str | None]  # relative to the repo root
    code_copied_at: Mapped[str | None]
    notes: Mapped[str] = mapped_column(Text, default="")
    takeaway: Mapped[str] = mapped_column(Text, default="")
    mistake_labels: Mapped[list[Any]] = mapped_column(default=list)
    evidence: Mapped[str]
    help: Mapped[str] = mapped_column(default=Help.UNKNOWN.value)
    outcome: Mapped[str | None]
    confidence: Mapped[int | None]
    active_seconds: Mapped[int] = mapped_column(default=0)
    gap_seconds: Mapped[int | None]
    running_since: Mapped[str | None]
    last_heartbeat_at: Mapped[str | None]
    needs_gap_decision: Mapped[bool] = mapped_column(
        _bool("needs_gap_decision"), default=False
    )
    started_at: Mapped[str]
    finished_at: Mapped[str | None]
    study_date: Mapped[str]
    next_review_date: Mapped[str | None]
    report: Mapped[dict[str, Any] | None]
    report_status: Mapped[str] = mapped_column(default=ReportStatus.NONE.value)
    report_error: Mapped[str | None]  # a TutorErrorKind
    # The failure's message, shown for the `error` kind (SPEC §12.1).
    report_error_message: Mapped[str | None] = mapped_column(Text)
    report_model: Mapped[str | None]
    reported_at: Mapped[str | None]


class AttemptSignals(Base):
    """Learner-reported results kept apart from the attempt's version (SPEC §6.7)."""

    __tablename__ = "attempt_signals"
    __table_args__ = (
        CheckConstraint(
            _one_of("difficulty", DifficultyFeel, nullable=True), name="difficulty"
        ),
    )

    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), primary_key=True
    )
    accepted_first_try: Mapped[bool | None] = mapped_column(_bool("accepted_first_try"))
    difficulty: Mapped[str | None]
    recorded_at: Mapped[str]


class HintMessage(Base):
    __tablename__ = "hint_messages"
    __table_args__ = (
        UniqueConstraint("attempt_id", "position"),
        CheckConstraint(_one_of("role", HintRole), name="role"),
        CheckConstraint(_one_of("level", HintLevel, nullable=True), name="level"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE")
    )
    position: Mapped[int]
    role: Mapped[str]
    text: Mapped[str] = mapped_column(Text)
    stuck_at_seconds: Mapped[int | None]
    level: Mapped[str | None]
    hint: Mapped[str | None]
    analysis: Mapped[str | None]
    created_at: Mapped[str]


class ReviewTarget(Base):
    """One review schedule per problem, i.e. per idea (SPEC §8.2)."""

    __tablename__ = "review_targets"
    __table_args__ = (
        CheckConstraint(_one_of("action", ReviewAction), name="action"),
        CheckConstraint(_one_of("stage", ReviewStage), name="stage"),
        CheckConstraint(
            "action <> 'none' OR effective_date IS NULL", name="none_has_no_date"
        ),
        CheckConstraint("solo_transfer_streak >= 0", name="solo_transfer_streak"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    problem_id: Mapped[str] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), unique=True
    )
    recommended_date: Mapped[str | None]
    effective_date: Mapped[str | None]
    action: Mapped[str]
    stage: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    # Consecutive solo solves at stage `transfer`; two retire an AtCoder problem (SPEC §8.5).
    solo_transfer_streak: Mapped[int] = mapped_column(default=0)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint("kind IN ('bundled', 'pack', 'bank')", name="kind"),
        CheckConstraint(_json("report"), name="report"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str]
    fingerprint: Mapped[str] = mapped_column(index=True)
    applied_at: Mapped[str]
    report: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Idempotency(Base):
    __tablename__ = "idempotency"
    __table_args__ = (CheckConstraint(_json("response"), name="response"),)

    key: Mapped[str] = mapped_column(String, primary_key=True)
    fingerprint: Mapped[str]
    response: Mapped[dict[str, Any]]
    created_at: Mapped[str]

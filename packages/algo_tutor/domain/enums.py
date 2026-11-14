"""The shared vocabulary: every enumerated value SPEC.md names.

Stored and sent as their string values, so the database, the API and the web
client all use the same spellings. Pure: no I/O, no third-party imports.
"""

from enum import StrEnum


class Source(StrEnum):
    """Where a problem lives (SPEC §5.1)."""

    LEETCODE = "leetcode"
    ATCODER = "atcoder"


class Difficulty(StrEnum):
    """LeetCode's difficulty label. AtCoder problems may have none."""

    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class Language(StrEnum):
    """Solution languages (SPEC §6.2). No C++ or Java (§2.4)."""

    PYTHON = "python"
    GO = "go"
    TYPESCRIPT = "typescript"


class AttemptStatus(StrEnum):
    """Whether an attempt is running, paused or finished."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class Context(StrEnum):
    """`mixed` is the hidden assessment (SPEC §9); everything else is `targeted`."""

    MIXED = "mixed"
    TARGETED = "targeted"


class Evidence(StrEnum):
    """What kind of evidence an attempt gives about the learner's skill."""

    RETENTION = "retention"
    NEAR_TRANSFER = "near_transfer"
    UNSEEN = "unseen"


class Outcome(StrEnum):
    """How an attempt ended."""

    SOLVED = "solved"
    NOT_SOLVED = "not_solved"
    STOPPED = "stopped"


class Help(StrEnum):
    """How much help the learner used during an attempt."""

    UNKNOWN = "unknown"
    NONE = "none"
    SMALL = "small"
    MAJOR = "major"
    SOLUTION = "solution"


class Result(StrEnum):
    """An attempt's level classification (SPEC §7.2), weakest first."""

    STRUGGLED = "struggled"
    OK = "ok"
    STRONG = "strong"


class DifficultyFeel(StrEnum):
    """The "How did it feel?" signal (SPEC §6.7)."""

    TOO_EASY = "too_easy"
    TOO_HARD = "too_hard"


class MistakeLabel(StrEnum):
    """The kind of mistake behind a failed attempt."""

    MISSED_EDGE_CASE = "missed_edge_case"
    WRONG_APPROACH = "wrong_approach"
    IMPLEMENTATION_BUG = "implementation_bug"


class ReviewAction(StrEnum):
    """How the next review of a problem was scheduled."""

    RECOMMENDED = "recommended"
    MANUAL = "manual"
    SNOOZE = "snooze"
    NONE = "none"


class ReviewStage(StrEnum):
    """Where a problem is in the spaced-review cycle."""

    REPAIR = "repair"
    RECONSTRUCTION = "reconstruction"
    TRANSFER = "transfer"
    MIXED = "mixed"
    RETIRED = "retired"
    COVERED = "covered"
    SNOOZED = "snoozed"


class ReviewChoice(StrEnum):
    """The finish form's "Next review" field (SPEC §6.6)."""

    RECOMMENDED = "recommended"
    MANUAL = "manual"
    NONE = "none"


class Lane(StrEnum):
    """A section of the daily plan (SPEC §10)."""

    LEETCODE = "leetcode"
    ATCODER = "atcoder"


class PlanItemStatus(StrEnum):
    """Where a daily-plan item is in its life cycle."""

    ACTIVE = "active"
    QUEUED = "queued"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class PlanItemKind(StrEnum):
    """A plan item's kind.

    A transfer check has no kind (None), which is what makes its attempt `mixed`
    (SPEC §6.2).
    """

    TOPIC = "topic"
    LIST = "list"


class Disposition(StrEnum):
    """What to do with a plan item that the learner does not want now."""

    SWAP = "swap"
    SNOOZE = "snooze"
    SKIP = "skip"


class ListKind(StrEnum):
    """Where a study list came from: a bundled course, the learner or a pack."""

    BUNDLED = "bundled"
    OWN = "own"
    PACK = "pack"


class ReportStatus(StrEnum):
    """Attempt report queue state (SPEC §12.4)."""

    NONE = "none"
    PENDING = "pending"
    GENERATING = "generating"
    DONE = "done"
    FAILED = "failed"


class TutorErrorKind(StrEnum):
    """Why an AI panel can't show output (SPEC §12.1)."""

    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    MODEL_MISSING = "model_missing"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    ERROR = "error"


class HintLevel(StrEnum):
    """How much a hint gives away."""

    SMALL = "small"
    MAJOR = "major"


class HintRole(StrEnum):
    """Who wrote a hint message."""

    LEARNER = "learner"
    TUTOR = "tutor"


class TimerAction(StrEnum):
    """An event that the attempt timer receives from the client."""

    HEARTBEAT = "heartbeat"
    PAUSE = "pause"
    RESUME = "resume"


class BundledSet(StrEnum):
    """The courses "Follow" can create (SPEC §5.10)."""

    NEETCODE_150 = "neetcode-150"
    BLIND_75 = "blind-75"
    HELLO_INTERVIEW = "hello-interview"

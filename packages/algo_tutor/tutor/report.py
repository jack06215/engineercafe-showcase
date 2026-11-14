"""The attempt report (SPEC §12.4): input, call, and how it's stored."""

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel

from packages.algo_tutor.config import TaskConfig
from packages.algo_tutor.domain.enums import Difficulty, Help, Language, Outcome, Source
from packages.algo_tutor.tutor import language, prompts
from packages.algo_tutor.tutor.llm import Answer, ask
from packages.algo_tutor.tutor.schemas import ReportReply

HISTORY_LIMIT = 5
# Earlier attempts' code and notes are context, not the subject: kept short.
HISTORY_CODE_CHARS = 8_000
HISTORY_NOTES_CHARS = 4_000


@dataclass(frozen=True)
class ProblemInfo:
    """Never the topic, tags or patterns (SPEC §12.5 needs the same for hints)."""

    title: str
    url: str
    source: Source
    difficulty: Difficulty | None


@dataclass(frozen=True)
class AttemptInfo:
    code: str
    notes: str
    language: Language
    outcome: Outcome
    help: Help
    time: str  # mm:ss
    confidence: int | None


@dataclass(frozen=True)
class EarlierAttempt:
    study_date: date
    outcome: Outcome
    help: Help
    time: str
    confidence: int | None
    language: Language
    notes: str
    code: str


@dataclass(frozen=True)
class CheckOf:
    title: str
    kind: Literal["transfer", "practice"]


@dataclass(frozen=True)
class ReportInput:
    problem: ProblemInfo
    attempt: AttemptInfo
    takeaway: str | None  # only for choosing the language
    history: tuple[EarlierAttempt, ...] = ()  # newest first
    check_of: CheckOf | None = None


def mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def context(report_input: ReportInput) -> dict[str, object]:
    """What the model sees, as JSON."""
    history = [
        asdict(earlier)
        | {
            "code": earlier.code[:HISTORY_CODE_CHARS],
            "notes": earlier.notes[:HISTORY_NOTES_CHARS],
        }
        for earlier in report_input.history[:HISTORY_LIMIT]
    ]
    out: dict[str, object] = {
        "problem": asdict(report_input.problem),
        "attempt": asdict(report_input.attempt),
        "history": history,
    }
    if report_input.check_of is not None:
        out["check_of"] = asdict(report_input.check_of)
    return out


def generate(
    chat: BaseChatModel, task: TaskConfig, report_input: ReportInput
) -> Answer[ReportReply]:
    lang = language.for_report(report_input.attempt.notes, report_input.takeaway)
    return ask(
        chat,
        ReportReply,
        prompts.report_instructions(report_input.problem.source),
        context(report_input),
        lang,
        task,
    )


def to_column(reply: ReportReply) -> dict[str, Any]:
    """`attempts.report` (a JSON column): the five sections."""
    return reply.model_dump()


def from_column(value: dict[str, Any] | None) -> ReportReply | None:
    if not value:
        return None
    return ReportReply.model_validate(value)

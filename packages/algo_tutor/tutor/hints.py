"""Interview hints during an attempt (SPEC §12.5)."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from langchain_core.language_models import BaseChatModel

from packages.algo_tutor.config import TaskConfig
from packages.algo_tutor.domain.enums import HintLevel, HintRole, Language
from packages.algo_tutor.tutor import language, prompts
from packages.algo_tutor.tutor.llm import Answer, ask
from packages.algo_tutor.tutor.report import ProblemInfo, mmss
from packages.algo_tutor.tutor.schemas import HintReply

CODE_CHARS = 20_000
MESSAGE_CHARS = 4_000
MESSAGES_KEPT = 20
# A message sent within this much stopwatch time of the previous one
# continues the same stuck point; later, it's a new one and gets an analysis.
# SPEC §12.5 says "whether stuck_at changed since the last hint", but a
# running stopwatch always changes, so the change has to be big enough.
NEW_STUCK_AFTER_SECONDS = 180


@dataclass(frozen=True)
class Message:
    role: HintRole
    text: str
    stuck_at_seconds: int | None = None  # learner messages only


@dataclass(frozen=True)
class HintInput:
    problem: ProblemInfo
    language: Language
    code: str  # the linked file now, or the editor's draft
    notes: str
    stuck_at_seconds: int
    history: tuple[Message, ...]  # this attempt's conversation so far, oldest first
    message: str  # what the learner just sent


def is_new_stuck(history: Sequence[Message], stuck_at_seconds: int) -> bool:
    previous = [
        m.stuck_at_seconds
        for m in history
        if m.role is HintRole.LEARNER and m.stuck_at_seconds is not None
    ]
    if not previous:
        return True
    return stuck_at_seconds - previous[-1] >= NEW_STUCK_AFTER_SECONDS


def context(hint_input: HintInput) -> dict[str, object]:
    conversation = [
        *hint_input.history,
        Message(HintRole.LEARNER, hint_input.message, hint_input.stuck_at_seconds),
    ]
    return {
        "problem": asdict(hint_input.problem),
        "language": hint_input.language,
        "code": hint_input.code[:CODE_CHARS],
        "stuck_at": mmss(hint_input.stuck_at_seconds),
        "new_stuck": is_new_stuck(hint_input.history, hint_input.stuck_at_seconds),
        "messages": [
            {
                "role": "candidate" if m.role is HintRole.LEARNER else "interviewer",
                "text": m.text[:MESSAGE_CHARS],
            }
            for m in conversation[-MESSAGES_KEPT:]
        ],
    }


def generate(
    chat: BaseChatModel, task: TaskConfig, hint_input: HintInput
) -> Answer[HintReply]:
    lang = language.for_hint(hint_input.message, hint_input.notes)
    answer = ask(
        chat,
        HintReply,
        prompts.hint_instructions(hint_input.problem.source),
        context(hint_input),
        lang,
        task,
    )
    if (
        not is_new_stuck(hint_input.history, hint_input.stuck_at_seconds)
        and answer.value.analysis is not None
    ):
        # The model was told to leave it null; don't let it into the notes anyway.
        answer = Answer(
            answer.value.model_copy(update={"analysis": None}),
            answer.repaired,
            answer.latency_ms,
        )
    return answer


def notes_block(reply: HintReply, stuck_at_seconds: int, new_stuck: bool) -> str:
    """The lines a hint adds to the attempt's notes.

    A new stuck point opens a block with the time and, if there is one, the
    analysis; a follow-up adds only its hint line.
    """
    hint_line = f"Hint ({reply.hint_level}): {reply.hint}"
    if not new_stuck:
        return hint_line
    lines = [f"[Stuck at {mmss(stuck_at_seconds)}] Asked Algo-chan for help."]
    if reply.analysis:
        lines.append(f"Where I was: {reply.analysis}")
    lines.append(hint_line)
    return "\n".join(lines)


def append_to_notes(notes: str, block: str, new_stuck: bool) -> str:
    if not notes.strip():
        return block
    separator = "\n\n" if new_stuck else "\n"
    return f"{notes.rstrip()}{separator}{block}"


def strongest(levels: Sequence[HintLevel | None]) -> HintLevel | None:
    """The finish form's Help follows the strongest hint given (SPEC §6.6)."""
    if HintLevel.MAJOR in levels:
        return HintLevel.MAJOR
    if HintLevel.SMALL in levels:
        return HintLevel.SMALL
    return None

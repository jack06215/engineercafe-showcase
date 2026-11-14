"""Settings → Test connection (SPEC §12.1)."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from packages.algo_tutor.config import TaskConfig
from packages.algo_tutor.domain.enums import TutorErrorKind
from packages.algo_tutor.tutor import prompts
from packages.algo_tutor.tutor.llm import TutorError, ask
from packages.algo_tutor.tutor.schemas import ConnectionReply


@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    provider: str
    model: str
    latency_ms: int | None
    error_kind: TutorErrorKind | None
    message: str | None


def check_connection(chat: BaseChatModel, task: TaskConfig) -> ConnectionResult:
    try:
        answer = ask(chat, ConnectionReply, prompts.CONNECTION, {}, "English", task)
    except TutorError as failure:
        return ConnectionResult(
            False, task.provider, task.model, None, failure.kind, failure.message
        )
    return ConnectionResult(
        True, task.provider, task.model, answer.latency_ms, None, None
    )

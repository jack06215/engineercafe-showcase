"""A scripted stand-in for the chat model. No Ollama or network involved."""

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedChat(BaseChatModel):
    """Answers with the scripted replies in order.

    An exception in the script is raised instead. `calls` keeps every request's
    messages.
    """

    script: list[Any]  # str | Exception
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError("the chat model was called more often than scripted")
        reply = self.script.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=str(reply)))]
        )

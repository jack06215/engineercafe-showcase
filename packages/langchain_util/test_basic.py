"""Tests for langchain_util.basic."""

import logging
import unittest
from typing import Any
from unittest.mock import Mock

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompt_values import PromptValue
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from packages.langchain_util.base import RetryPolicy
from packages.langchain_util.basic import bind_output_schema, generate

FAST = RetryPolicy(multiplier=0.0, max_wait=0.0)


class Triage(BaseModel):
    urgency: str = Field(description="low, medium, or high")
    reason: str


def _prompt(system: str = "Triage tickets.\n\n{{ format_instructions }}") -> Any:
    return ChatPromptTemplate.from_messages(
        [("system", system), ("human", "Ticket: {{ ticket }}")],
        template_format="jinja2",
    )


class _Script:
    """A chat stand-in that records every prompt and replays canned replies."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[list[BaseMessage]] = []

    def as_runnable(self) -> Any:
        def respond(prompt: PromptValue) -> AIMessage:
            self.calls.append(prompt.to_messages())
            if not self.replies:
                msg = "unexpected model call"
                raise AssertionError(msg)
            return AIMessage(content=self.replies.pop(0))

        return RunnableLambda(respond)


class GenerateTest(unittest.TestCase):
    def test_returns_the_parsed_model_with_the_schema_in_the_prompt(self) -> None:
        script = _Script('{"urgency": "high", "reason": "checkout is down"}')

        result = generate(
            prompt=_prompt(),
            output=Triage,
            chat=script.as_runnable(),
            logger=Mock(spec=logging.Logger),
            input={"ticket": "I cannot pay"},
        )

        self.assertEqual(result, Triage(urgency="high", reason="checkout is down"))
        system, human = script.calls[0]
        self.assertIn('"urgency"', system.text)
        self.assertIn("low, medium, or high", system.text)
        self.assertEqual(human.text, "Ticket: I cannot pay")

    def test_a_parse_failure_is_retried_with_feedback(self) -> None:
        script = _Script(
            '{"urgency": "high"}',
            '{"urgency": "high", "reason": "fixed"}',
        )

        result = generate(
            prompt=_prompt(),
            output=Triage,
            chat=script.as_runnable(),
            logger=Mock(spec=logging.Logger),
            input={"ticket": "x"},
            retry_policy=FAST,
        )

        self.assertEqual(result.reason, "fixed")
        self.assertEqual(len(script.calls), 2)
        self.assertIn("reason", script.calls[1][-1].text)

    def test_dry_run_goes_through_the_real_parser(self) -> None:
        script = _Script()

        result = generate(
            prompt=_prompt(),
            output=Triage,
            chat=script.as_runnable(),
            logger=Mock(spec=logging.Logger),
            input={"ticket": "x"},
            dry_run='{"urgency": "low", "reason": "canned"}',
        )

        self.assertEqual(result.reason, "canned")
        self.assertEqual(script.calls, [])

    def test_refuses_a_prompt_that_never_shows_the_schema(self) -> None:
        script = _Script()

        with self.assertRaisesRegex(ValueError, "format_instructions"):
            generate(
                prompt=_prompt(system="Triage tickets."),
                output=Triage,
                chat=script.as_runnable(),
                logger=Mock(spec=logging.Logger),
                input={"ticket": "x"},
            )

        self.assertEqual(script.calls, [])


class BindOutputSchemaTest(unittest.TestCase):
    def test_removes_format_instructions_from_the_input_variables(self) -> None:
        parser = PydanticOutputParser(pydantic_object=Triage)

        bound = bind_output_schema(_prompt(), parser)

        self.assertEqual(bound.input_variables, ["ticket"])


if __name__ == "__main__":
    unittest.main()

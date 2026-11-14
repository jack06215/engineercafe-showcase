"""Tests for langchain_util.thinking.

Each test scripts two chat stand-ins -- the writer and the reviewer -- so an
unexpected call to either fails loudly, and every prompt they were sent can be
inspected afterwards.
"""

import json
import logging
import unittest
from typing import Any
from unittest.mock import Mock

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.prompt_values import PromptValue
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from packages.langchain_util.base import RetryPolicy
from packages.langchain_util.thinking import (
    ThinkingPolicy,
    build_graph,
    think,
)

FAST = RetryPolicy(multiplier=0.0, max_wait=0.0)

CRITERIA = ("Does it name the product?", "Is it under ten words?")


class Tagline(BaseModel):
    text: str


def _answer(text: str) -> str:
    return Tagline(text=text).model_dump_json()


def _review(*passed: bool, fix: str = "Name the product") -> str:
    return json.dumps(
        {
            "verdicts": [
                {
                    "id": number,
                    "evidence": f"evidence {number}",
                    "passed": ok,
                    "fix": None if ok else fix,
                }
                for number, ok in enumerate(passed, start=1)
            ]
        }
    )


def _prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", "You write taglines.\n\n{{ format_instructions }}"),
            ("human", "Product: {{ product }}"),
        ],
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


def _think(
    writer: _Script,
    reviewer: _Script,
    **kwargs: Any,
) -> Any:
    kwargs.setdefault("criteria", CRITERIA)
    return think(
        prompt=_prompt(),
        output=Tagline,
        chat=writer.as_runnable(),
        evaluator_chat=reviewer.as_runnable(),
        logger=Mock(spec=logging.Logger),
        input={"product": "Bazel"},
        retry_policy=FAST,
        **kwargs,
    )


def _text(messages: list[BaseMessage]) -> str:
    return "\n".join(f"{message.type}: {message.text}" for message in messages)


class ThinkTest(unittest.TestCase):
    def test_a_passing_draft_is_accepted_without_revision(self) -> None:
        writer = _Script(_answer("Bazel builds fast"))
        reviewer = _Script(_review(True, True))

        result = _think(writer, reviewer)

        self.assertTrue(result.accepted)
        self.assertEqual(result.value, Tagline(text="Bazel builds fast"))
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.checks, CRITERIA)
        # The checklist reaches the writer before its first answer, not only
        # as feedback after a failure.
        draft_prompt = _text(writer.calls[0])
        self.assertIn("reviewed against this checklist", draft_prompt)
        self.assertIn("- Is it under ten words?", draft_prompt)

    def test_the_reviewer_sees_the_task_the_checks_and_the_answer(self) -> None:
        writer = _Script(_answer("Bazel builds fast"))
        reviewer = _Script(_review(True, True))

        _think(writer, reviewer)

        review_prompt = _text(reviewer.calls[0])
        self.assertIn("You write taglines.", review_prompt)
        self.assertIn("Product: Bazel", review_prompt)
        self.assertIn("1. Does it name the product?", review_prompt)
        self.assertIn("2. Is it under ten words?", review_prompt)
        self.assertIn('"text": "Bazel builds fast"', review_prompt)

    def test_a_failed_check_drives_a_revision(self) -> None:
        writer = _Script(_answer("Builds fast"), _answer("Bazel builds fast"))
        reviewer = _Script(_review(False, True), _review(True, True))

        result = _think(writer, reviewer)

        self.assertTrue(result.accepted)
        self.assertEqual(result.best_index, 1)
        self.assertEqual(result.value.text, "Bazel builds fast")
        revision = writer.calls[1]
        self.assertIsInstance(revision[-2], AIMessage)
        self.assertIn('"text": "Builds fast"', revision[-2].text)
        feedback = revision[-1].text
        self.assertIn("- Does it name the product?", feedback)
        self.assertIn("Suggested fix: Name the product", feedback)
        # What already passed is named, so the revision knows what to keep.
        self.assertIn(
            "keep whatever makes them true:\n- Is it under ten words?", feedback
        )

    def test_a_regression_returns_the_earlier_better_candidate(self) -> None:
        writer = _Script(_answer("Bazel builds"), _answer("Fast"))
        reviewer = _Script(_review(True, False), _review(False, False))

        result = _think(writer, reviewer)

        self.assertFalse(result.accepted)
        self.assertEqual(result.best_index, 0)
        self.assertEqual(result.value.text, "Bazel builds")
        # patience=1: one revision that did not improve ends the run.
        self.assertEqual(len(result.attempts), 2)

    def test_a_revision_starts_from_the_best_candidate_not_the_last(self) -> None:
        writer = _Script(_answer("best"), _answer("worse"), _answer("again"))
        reviewer = _Script(
            _review(True, False),
            _review(False, False),
            _review(False, False),
        )

        result = _think(
            writer,
            reviewer,
            policy=ThinkingPolicy(max_revisions=2, patience=2),
        )

        self.assertEqual(len(result.attempts), 3)
        self.assertIn('"text": "best"', writer.calls[2][-2].text)
        self.assertEqual(result.value.text, "best")

    def test_ties_keep_the_earlier_candidate(self) -> None:
        writer = _Script(_answer("first"), _answer("second"))
        reviewer = _Script(_review(True, False), _review(False, True))

        result = _think(writer, reviewer)

        self.assertEqual(result.value.text, "first")

    def test_stops_after_max_revisions(self) -> None:
        writer = _Script(_answer("a"), _answer("b"))
        reviewer = _Script(_review(False, False), _review(True, False))

        result = _think(writer, reviewer, policy=ThinkingPolicy(max_revisions=1))

        self.assertFalse(result.accepted)
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(result.value.text, "b")

    def test_accept_score_allows_a_partial_pass(self) -> None:
        writer = _Script(_answer("a"))
        reviewer = _Script(_review(True, False))

        result = _think(writer, reviewer, policy=ThinkingPolicy(accept_score=0.5))

        self.assertTrue(result.accepted)
        self.assertEqual(len(result.attempts), 1)

    def test_validator_problems_skip_the_review_and_become_feedback(self) -> None:
        writer = _Script(_answer("x" * 50), _answer("short"))
        reviewer = _Script(_review(True, True))

        def at_most_20_chars(tagline: Tagline) -> list[str]:
            if len(tagline.text) > 20:
                return [f"The tagline is {len(tagline.text)} characters; keep it to 20"]
            return []

        result = _think(writer, reviewer, validators=[at_most_20_chars])

        self.assertTrue(result.accepted)
        self.assertEqual(
            result.attempts[0].problems,
            ("The tagline is 50 characters; keep it to 20",),
        )
        self.assertEqual(result.attempts[0].checks, ())
        self.assertEqual(len(reviewer.calls), 1)
        self.assertIn("keep it to 20", writer.calls[1][-1].text)

    def test_fewer_validator_problems_rank_higher(self) -> None:
        writer = _Script(_answer("a"), _answer("b"), _answer("c"))
        problems = {"a": ["one", "two"], "b": ["one"], "c": ["one", "two", "three"]}
        reviewer = _Script()

        result = _think(
            writer,
            reviewer,
            criteria=(),
            validators=[lambda tagline: problems[tagline.text]],
            policy=ThinkingPolicy(max_revisions=2, patience=2),
        )

        self.assertEqual(result.value.text, "b")
        self.assertFalse(result.accepted)

    def test_a_bare_string_from_a_validator_is_one_problem(self) -> None:
        writer = _Script(_answer("a"))
        reviewer = _Script()

        result = _think(
            writer,
            reviewer,
            criteria=(),
            validators=[lambda _: "too vague"],
            policy=ThinkingPolicy(max_revisions=0),
        )

        self.assertEqual(result.attempts[0].problems, ("too vague",))

    def test_no_criteria_and_no_validators_is_a_single_call(self) -> None:
        writer = _Script(_answer("a"))
        reviewer = _Script()

        result = _think(writer, reviewer, criteria=())

        self.assertTrue(result.accepted)
        self.assertEqual(len(writer.calls), 1)
        self.assertNotIn("checklist", _text(writer.calls[0]))

    def test_criteria_are_derived_when_none_are_given(self) -> None:
        derived = [f"Check {n}?" for n in range(1, 11)]
        writer = _Script(_answer("a"))
        reviewer = _Script(json.dumps({"checks": derived}), _review(True, True, True))

        result = _think(
            writer,
            reviewer,
            criteria=None,
            policy=ThinkingPolicy(max_checks=3),
        )

        self.assertEqual(result.checks, ("Check 1?", "Check 2?", "Check 3?"))
        self.assertTrue(result.accepted)
        self.assertIn("Product: Bazel", _text(reviewer.calls[0]))
        self.assertIn("at most 3 questions", _text(reviewer.calls[0]))

    def test_a_review_that_skips_a_check_is_retried_with_feedback(self) -> None:
        writer = _Script(_answer("a"))
        incomplete = json.dumps(
            {"verdicts": [{"id": 1, "evidence": "e", "passed": True, "fix": None}]}
        )
        reviewer = _Script(incomplete, _review(True, True))

        result = _think(writer, reviewer)

        self.assertTrue(result.accepted)
        self.assertEqual(len(reviewer.calls), 2)
        self.assertIn("no verdict for check(s) 2", reviewer.calls[1][-1].text)

    def test_many_revisions_do_not_hit_the_recursion_limit(self) -> None:
        count = 14
        writer = _Script(*[_answer(str(n)) for n in range(count)])
        reviewer = _Script()

        result = _think(
            writer,
            reviewer,
            criteria=(),
            # Always improving, never passing: the loop can only stop at the cap.
            validators=[lambda tagline: ["problem"] * (100 - int(tagline.text))],
            policy=ThinkingPolicy(max_revisions=count - 1),
        )

        self.assertEqual(len(result.attempts), count)
        self.assertEqual(result.best_index, count - 1)

    def test_usage_is_summed_across_calls(self) -> None:
        result = think(
            prompt=_prompt(),
            output=Tagline,
            chat=FakeListChatModel(responses=[_answer("a")]),
            evaluator_chat=FakeListChatModel(responses=[_review(True, True)]),
            logger=Mock(spec=logging.Logger),
            input={"product": "Bazel"},
            criteria=CRITERIA,
        )

        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual(len(result.usage.prompts), 2)

    def test_refuses_a_prompt_that_never_shows_the_schema(self) -> None:
        prompt = ChatPromptTemplate.from_messages(
            [("human", "Product: {{ product }}")],
            template_format="jinja2",
        )

        with self.assertRaisesRegex(ValueError, "format_instructions"):
            think(
                prompt=prompt,
                output=Tagline,
                chat=_Script().as_runnable(),
                logger=Mock(spec=logging.Logger),
            )


class BuildGraphTest(unittest.TestCase):
    def test_a_compiled_graph_serves_several_inputs(self) -> None:
        writer = _Script(_answer("Bazel builds"), _answer("Poetry locks"))
        graph = build_graph(
            prompt=_prompt(),
            output=Tagline,
            chat=writer.as_runnable(),
            logger=Mock(spec=logging.Logger),
            criteria=(),
        )

        for product in ("Bazel", "Poetry"):
            state = graph.invoke({"input": {"product": product}}, version="v2").value
            self.assertEqual(len(state["attempts"]), 1)

        self.assertIn("Product: Poetry", _text(writer.calls[1]))


class ThinkingPolicyTest(unittest.TestCase):
    def test_rejects_settings_that_cannot_terminate_sensibly(self) -> None:
        for kwargs in (
            {"max_revisions": -1},
            {"patience": 0},
            {"accept_score": 0.0},
            {"accept_score": 1.5},
            {"max_checks": 0},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                ThinkingPolicy(**kwargs)


if __name__ == "__main__":
    unittest.main()

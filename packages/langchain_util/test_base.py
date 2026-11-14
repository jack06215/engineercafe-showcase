"""Tests for langchain_util.base.

These drive a real chain (`template | chat | parser`) rather than mocking the
whole thing out. Mocking template/chat/parser *and* overriding chain_factory --
as the previous suite did -- never exercises the retry loop, the callback
plumbing, or the prompt-repair path, which is exactly where the bugs were.
"""

import logging
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    FewShotPromptTemplate,
    PromptTemplate,
)
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_util.observability import UsageCollector
from openai import APITimeoutError
from pydantic import BaseModel

from packages.langchain_util.base import (
    DEFAULT_TITLE,
    RetryPolicy,
    _repair_template,
    ainvoke_llm,
    invoke_llm,
    invoke_llm_detailed,
    stream_llm,
)

# Zero backoff: these tests exercise retry *logic*, not wall-clock patience.
FAST = RetryPolicy(multiplier=0.0, max_wait=0.0)


class Answer(BaseModel):
    answer: str


def _logger() -> Mock:
    return Mock(spec=logging.Logger)


def _timeout_error() -> APITimeoutError:
    return APITimeoutError(request=httpx.Request("POST", "http://test.invalid"))


class _CountingChat:
    """A stand-in for a chat model that can fail on demand.

    Returned as a RunnableLambda so it slots into `template | chat | parser`
    without needing a full BaseChatModel subclass.
    """

    def __init__(self, *, errors: list[Exception], reply: str) -> None:
        self.errors = errors
        self.reply = reply
        self.calls = 0

    def as_runnable(self) -> Any:
        def respond(_: Any) -> AIMessage:
            index = self.calls
            self.calls += 1
            if index < len(self.errors):
                raise self.errors[index]
            return AIMessage(content=self.reply)

        return RunnableLambda(respond)


class RepairTemplateTest(unittest.TestCase):
    """Unit tests for the prompt-repair helper (was silently corrupting prompts)."""

    def test_preserves_partial_variables(self) -> None:
        template = PromptTemplate.from_template("Q: {q}\n{fmt}").partial(fmt="FMT")

        repaired = _repair_template(template, ValueError("nope"), "t")

        assert repaired is not None
        # The feedback rides along as a partial of its own, so the caller's
        # partials must survive next to it rather than be replaced by it.
        self.assertIn("fmt", repaired.partial_variables)
        self.assertEqual(repaired.input_variables, ["q"])
        # Renders with only `q` supplied; the old rebuild raised KeyError here.
        self.assertIn("FMT", repaired.format(q="x"))

    def test_escapes_braces_from_model_output(self) -> None:
        template = PromptTemplate.from_template("Q: {q}")
        error = OutputParserException('bad output: {"wrong_field": 1}')

        repaired = _repair_template(template, error, "t")

        assert repaired is not None
        # No new input variables invented from the model's own braces.
        self.assertEqual(repaired.input_variables, ["q"])
        rendered = repaired.format(q="x")
        self.assertIn('{"wrong_field": 1}', rendered)

    def test_jinja2_feedback_is_not_rendered_as_markup(self) -> None:
        template = PromptTemplate.from_template(
            "Q: {{ q }}",
            template_format="jinja2",
        )
        error = OutputParserException("bad output: {{ q }} and {% if wrong %}")

        repaired = _repair_template(template, error, "t")

        assert repaired is not None
        self.assertEqual(repaired.input_variables, ["q"])
        rendered = repaired.format(q="ANSWER")
        # Brace-escaped into the template text, this feedback made the repaired
        # template unrenderable (TemplateSyntaxError) rather than reporting the
        # model's own markup back to it.
        self.assertIn("bad output: {{ q }} and {% if wrong %}", rendered)
        self.assertTrue(rendered.startswith("Q: ANSWER"))

    def test_jinja2_preserves_partial_variables(self) -> None:
        template = PromptTemplate.from_template(
            "Q: {{ q }}\n{{ fmt }}",
            template_format="jinja2",
            partial_variables={"fmt": "FMT"},
        )

        repaired = _repair_template(template, ValueError("nope"), "t")

        assert repaired is not None
        self.assertEqual(repaired.input_variables, ["q"])
        self.assertIn("FMT", repaired.format(q="x"))

    def test_mustache_feedback_keeps_its_quotes(self) -> None:
        template = PromptTemplate.from_template("Q: {{q}}", template_format="mustache")
        error = OutputParserException('bad output: {"wrong_field": 1}')

        repaired = _repair_template(template, error, "t")

        assert repaired is not None
        # `{{var}}` HTML-escapes in mustache, which would report back
        # `&quot;wrong_field&quot;` and teach the model the wrong lesson.
        self.assertIn('{"wrong_field": 1}', repaired.format(q="x"))

    def test_feedback_does_not_accumulate_across_attempts(self) -> None:
        template = PromptTemplate.from_template("Q: {q}")

        first = _repair_template(template, ValueError("e1"), "t")
        assert first is not None
        second = _repair_template(template, ValueError("e2"), "t")
        assert second is not None

        self.assertEqual(second.format(q="x").count("Error in t"), 1)

    def test_chat_prompt_template_keeps_partials(self) -> None:
        template = ChatPromptTemplate.from_messages(
            [("system", "S {fmt}"), ("human", "{q}")]
        ).partial(fmt="FMT")

        repaired = _repair_template(template, ValueError("nope"), "t")

        assert isinstance(repaired, ChatPromptTemplate)
        self.assertEqual(list(repaired.partial_variables), ["fmt"])
        contents = [m.content for m in repaired.format_messages(q="y")]
        self.assertEqual(contents[0], "S FMT")
        self.assertIn("Error in t", str(contents[-1]))

    def test_returns_none_for_unsupported_template_type(self) -> None:
        template = FewShotPromptTemplate(
            examples=[{"q": "1", "a": "2"}],
            example_prompt=PromptTemplate.from_template("{q}->{a}"),
            suffix="{q}",
            input_variables=["q"],
        )

        self.assertIsNone(_repair_template(template, ValueError("x"), "t"))


class InvokeLlmSuccessTest(unittest.TestCase):
    def test_returns_parsed_value(self) -> None:
        result = invoke_llm(
            template=PromptTemplate.from_template("Say hi to {name}"),
            chat=FakeListChatModel(responses=["hello"]),
            parser=StrOutputParser(),
            logger=_logger(),
            input={"name": "jack"},
            retry_policy=FAST,
        )

        self.assertEqual(result, "hello")

    def test_logs_title_from_input(self) -> None:
        logger = _logger()

        invoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=FakeListChatModel(responses=["ok"]),
            parser=StrOutputParser(),
            logger=logger,
            input={"q": "x", "title": "my-title"},
            retry_policy=FAST,
        )

        self.assertIn("my-title", logger.info.call_args_list[0].args)

    def test_explicit_title_wins_and_non_string_falls_back(self) -> None:
        logger = _logger()
        invoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=FakeListChatModel(responses=["ok"]),
            parser=StrOutputParser(),
            logger=logger,
            input={"q": "x", "title": 123},
            retry_policy=FAST,
        )

        # A non-string "title" used to hit `assert isinstance(...)`, which also
        # vanished entirely under `python -O`.
        self.assertIn(DEFAULT_TITLE, logger.info.call_args_list[0].args)

    def test_parses_pydantic_output(self) -> None:
        parser = PydanticOutputParser(pydantic_object=Answer)

        result = invoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=FakeListChatModel(responses=['{"answer": "42"}']),
            parser=parser,
            logger=_logger(),
            input={"q": "x"},
            retry_policy=FAST,
        )

        self.assertEqual(result.answer, "42")


class CallbackPropagationTest(unittest.TestCase):
    """The wrapped-callback-manager bug: handlers stopped at the outer chain."""

    def test_caller_handlers_see_the_nested_model_run(self) -> None:
        collector = UsageCollector()

        invoke_llm(
            template=PromptTemplate.from_template("Say hi to {name}"),
            chat=FakeListChatModel(responses=["hello"]),
            parser=StrOutputParser(),
            logger=_logger(),
            input={"name": "jack"},
            config=RunnableConfig(callbacks=[collector]),
            retry_policy=FAST,
        )

        # on_chat_model_start / on_llm_end only fire for the child model run.
        self.assertEqual(collector.usage.llm_calls, 1)
        self.assertEqual(collector.usage.raw_output, "hello")
        self.assertTrue(collector.usage.prompts)

    def test_caller_config_is_not_mutated(self) -> None:
        config: RunnableConfig = {"tags": ["mytag"], "callbacks": []}

        invoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=FakeListChatModel(responses=["ok"]),
            parser=StrOutputParser(),
            logger=_logger(),
            input={"q": "x"},
            config=config,
            retry_policy=FAST,
        )

        self.assertEqual(config, {"tags": ["mytag"], "callbacks": []})


class RetryBehaviourTest(unittest.TestCase):
    def test_transient_api_error_is_retried_then_succeeds(self) -> None:
        chat = _CountingChat(errors=[_timeout_error()], reply="recovered")

        result = invoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=chat.as_runnable(),
            parser=StrOutputParser(),
            logger=_logger(),
            input={"q": "x"},
            retry_policy=FAST,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(chat.calls, 2)

    def test_programming_value_error_is_not_retried(self) -> None:
        chat = _CountingChat(errors=[ValueError("bad code")] * 10, reply="never")

        with self.assertRaises(ValueError):
            invoke_llm(
                template=PromptTemplate.from_template("{q}"),
                chat=chat.as_runnable(),
                parser=StrOutputParser(),
                logger=_logger(),
                input={"q": "x"},
                retry_policy=FAST,
            )

        # Bare ValueError used to be retryable, burning six billed calls on a
        # bug that cannot fix itself.
        self.assertEqual(chat.calls, 1)

    def test_parse_error_uses_the_whole_retry_budget(self) -> None:
        parser = PydanticOutputParser(pydantic_object=Answer)
        template = PromptTemplate.from_template("{q}\n{fmt}").partial(
            fmt=parser.get_format_instructions()
        )
        chat = FakeListChatModel(responses=["not json at all"])
        policy = RetryPolicy(attempts=3, multiplier=0.0, max_wait=0.0)
        collector = UsageCollector()

        with self.assertRaises(OutputParserException):
            invoke_llm(
                template=template,
                chat=chat,
                parser=parser,
                logger=_logger(),
                input={"q": "x"},
                config=RunnableConfig(callbacks=[collector]),
                retry_policy=policy,
            )

        # Previously the repaired template raised KeyError on attempt 2, which
        # is not retryable, so the budget silently collapsed to 2 and the real
        # parse error was masked.
        self.assertEqual(collector.usage.llm_calls, 3)

    def test_repaired_prompt_is_actually_used_and_keeps_partials(self) -> None:
        parser = PydanticOutputParser(pydantic_object=Answer)
        template = PromptTemplate.from_template("{q}\n{fmt}").partial(fmt="FMT-MARKER")
        collector = UsageCollector()

        with self.assertRaises(OutputParserException):
            invoke_llm(
                template=template,
                chat=FakeListChatModel(responses=['{"nope": 1}']),
                parser=parser,
                logger=_logger(),
                input={"q": "x"},
                config=RunnableConfig(callbacks=[collector]),
                retry_policy=RetryPolicy(attempts=2, multiplier=0.0, max_wait=0.0),
            )

        first, second = collector.usage.prompts[0], collector.usage.prompts[1]
        self.assertNotIn("Error in", first)
        self.assertIn("Error in", second)
        self.assertIn("FMT-MARKER", second)

    def test_jinja2_repair_survives_markup_in_the_model_output(self) -> None:
        parser = PydanticOutputParser(pydantic_object=Answer)
        template = PromptTemplate.from_template(
            "{{ q }}\n{{ fmt }}",
            template_format="jinja2",
            partial_variables={"fmt": "FMT-MARKER"},
        )
        collector = UsageCollector()

        with self.assertRaises(OutputParserException):
            invoke_llm(
                template=template,
                chat=FakeListChatModel(responses=["nope {{ q }} {% if x %}"]),
                parser=parser,
                logger=_logger(),
                input={"q": "x"},
                config=RunnableConfig(callbacks=[collector]),
                retry_policy=RetryPolicy(attempts=3, multiplier=0.0, max_wait=0.0),
            )

        # Escaping the feedback into the template text left a jinja2 prompt that
        # would not render at all (TemplateSyntaxError), so one parse failure
        # took the remaining attempts down with it.
        self.assertEqual(collector.usage.llm_calls, 3)
        retry_prompt = collector.usage.prompts[1]
        self.assertIn("FMT-MARKER", retry_prompt)
        self.assertIn("nope {{ q }} {% if x %}", retry_prompt)

    def test_repair_can_be_disabled(self) -> None:
        parser = PydanticOutputParser(pydantic_object=Answer)
        collector = UsageCollector()

        with self.assertRaises(OutputParserException):
            invoke_llm(
                template=PromptTemplate.from_template("{q}"),
                chat=FakeListChatModel(responses=["not json"]),
                parser=parser,
                logger=_logger(),
                input={"q": "x"},
                config=RunnableConfig(callbacks=[collector]),
                retry_policy=RetryPolicy(attempts=2, multiplier=0.0, max_wait=0.0),
                repair_prompt_on_parse_error=False,
            )

        self.assertNotIn("Error in", collector.usage.prompts[1])

    def test_retry_policy_is_per_call(self) -> None:
        chat = _CountingChat(errors=[_timeout_error()] * 10, reply="never")

        with self.assertRaises(APITimeoutError):
            invoke_llm(
                template=PromptTemplate.from_template("{q}"),
                chat=chat.as_runnable(),
                parser=StrOutputParser(),
                logger=_logger(),
                input={"q": "x"},
                retry_policy=RetryPolicy(attempts=2, multiplier=0.0, max_wait=0.0),
            )

        self.assertEqual(chat.calls, 2)

    def test_retry_warnings_go_to_the_caller_logger(self) -> None:
        chat = _CountingChat(errors=[_timeout_error()], reply="ok")
        logger = _logger()

        invoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=chat.as_runnable(),
            parser=StrOutputParser(),
            logger=logger,
            input={"q": "x"},
            title="retry-title",
            retry_policy=FAST,
        )

        # before_sleep used to be bound to the module logger at import time, so
        # the caller never saw retries on the logger they passed in.
        warned = " ".join(str(call) for call in logger.warning.call_args_list)
        self.assertIn("retry-title", warned)
        self.assertIn("APITimeoutError", warned)

    def test_failure_is_logged_to_the_caller_logger(self) -> None:
        logger = _logger()

        with self.assertRaises(ValueError):
            invoke_llm(
                template=PromptTemplate.from_template("{q}"),
                chat=_CountingChat(
                    errors=[ValueError("boom")], reply="x"
                ).as_runnable(),
                parser=StrOutputParser(),
                logger=logger,
                input={"q": "x", "title": "failing-title"},
                retry_policy=FAST,
            )

        logger.exception.assert_called_once()
        self.assertIn("failing-title", logger.exception.call_args.args)


class DetailedResultTest(unittest.TestCase):
    def test_returns_usage_attempts_and_latency(self) -> None:
        chat = _CountingChat(errors=[_timeout_error()], reply="hello")

        result = invoke_llm_detailed(
            template=PromptTemplate.from_template("{q}"),
            chat=chat.as_runnable(),
            parser=StrOutputParser(),
            logger=_logger(),
            input={"q": "x"},
            retry_policy=FAST,
        )

        self.assertEqual(result.value, "hello")
        self.assertEqual(result.attempts, 2)
        self.assertGreaterEqual(result.latency_s, 0.0)

    def test_exposes_raw_output_without_a_custom_chain_factory(self) -> None:
        result = invoke_llm_detailed(
            template=PromptTemplate.from_template("{q}"),
            chat=FakeListChatModel(responses=['{"answer": "7"}']),
            parser=PydanticOutputParser(pydantic_object=Answer),
            logger=_logger(),
            input={"q": "x"},
            retry_policy=FAST,
        )

        self.assertEqual(result.value.answer, "7")
        self.assertEqual(result.usage.raw_output, '{"answer": "7"}')


class DryRunTest(unittest.TestCase):
    def test_bypasses_the_provider_but_still_parses(self) -> None:
        def explode(_: Any) -> AIMessage:
            raise AssertionError("provider must not be called during a dry run")

        result = invoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=RunnableLambda(explode),
            parser=PydanticOutputParser(pydantic_object=Answer),
            logger=_logger(),
            input={"q": "x"},
            retry_policy=FAST,
            dry_run='{"answer": "canned"}',
        )

        self.assertEqual(result.answer, "canned")

    def test_surfaces_parse_errors_in_the_canned_response(self) -> None:
        with self.assertRaises(OutputParserException):
            invoke_llm(
                template=PromptTemplate.from_template("{q}"),
                chat=FakeListChatModel(responses=["unused"]),
                parser=PydanticOutputParser(pydantic_object=Answer),
                logger=_logger(),
                input={"q": "x"},
                retry_policy=RetryPolicy(attempts=1, multiplier=0.0, max_wait=0.0),
                dry_run="definitely not json",
            )


class DebugDumpTest(unittest.TestCase):
    def test_writes_a_redacted_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = invoke_llm_detailed(
                template=PromptTemplate.from_template("{q}"),
                chat=FakeListChatModel(responses=["sk-abcdefghijklmnop secret"]),
                parser=StrOutputParser(),
                logger=_logger(),
                input={"q": "x"},
                retry_policy=FAST,
                debug_dir=tmp,
            )

            assert result.debug_path is not None
            body = result.debug_path.read_text(encoding="utf-8")
            self.assertIn("<redacted-key>", body)
            self.assertNotIn("sk-abcdefghijklmnop", body)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_no_dump_without_a_directory(self) -> None:
        result = invoke_llm_detailed(
            template=PromptTemplate.from_template("{q}"),
            chat=FakeListChatModel(responses=["ok"]),
            parser=StrOutputParser(),
            logger=_logger(),
            input={"q": "x"},
            retry_policy=FAST,
        )

        self.assertIsNone(result.debug_path)


class StreamingTest(unittest.TestCase):
    def test_yields_chunks(self) -> None:
        chunks = list(
            stream_llm(
                template=PromptTemplate.from_template("{q}"),
                chat=FakeListChatModel(responses=["abc"]),
                parser=StrOutputParser(),
                logger=_logger(),
                input={"q": "x"},
                retry_policy=FAST,
            )
        )

        self.assertEqual("".join(chunks), "abc")

    def test_retries_only_before_the_first_chunk(self) -> None:
        chat = _CountingChat(errors=[_timeout_error()], reply="xyz")

        chunks = list(
            stream_llm(
                template=PromptTemplate.from_template("{q}"),
                chat=chat.as_runnable(),
                parser=StrOutputParser(),
                logger=_logger(),
                input={"q": "x"},
                retry_policy=FAST,
            )
        )

        self.assertEqual("".join(chunks), "xyz")
        self.assertEqual(chat.calls, 2)


class AsyncInvokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_parsed_value(self) -> None:
        result = await ainvoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=FakeListChatModel(responses=["async-hello"]),
            parser=StrOutputParser(),
            logger=_logger(),
            input={"q": "x"},
            retry_policy=FAST,
        )

        self.assertEqual(result, "async-hello")

    async def test_retries_transient_errors(self) -> None:
        chat = _CountingChat(errors=[_timeout_error()], reply="recovered")

        result = await ainvoke_llm(
            template=PromptTemplate.from_template("{q}"),
            chat=chat.as_runnable(),
            parser=StrOutputParser(),
            logger=_logger(),
            input={"q": "x"},
            retry_policy=FAST,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(chat.calls, 2)


if __name__ == "__main__":
    unittest.main()

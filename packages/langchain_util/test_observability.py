"""Tests for langchain_util.observability."""

import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, Generation, LLMResult

from packages.langchain_util.observability import (
    MODEL_PRICING,
    Usage,
    UsageCollector,
    dump_exchange,
    redact,
    register_pricing,
)


def _chat_result(
    text: str,
    *,
    usage_metadata: dict[str, int] | None = None,
    model: str | None = None,
) -> LLMResult:
    message = AIMessage(
        content=text,
        usage_metadata=usage_metadata,  # type: ignore[arg-type]
        response_metadata={"model_name": model} if model else {},
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


class RedactTest(unittest.TestCase):
    def test_redacts_api_key_shaped_strings(self) -> None:
        self.assertEqual(
            redact("token sk-abcdefghijklmnop here"),
            "token <redacted-key> here",
        )

    def test_redacts_values_of_known_secret_env_vars(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "super-secret-value-123"}):
            self.assertEqual(
                redact("key is super-secret-value-123"),
                "key is <OPENAI_API_KEY>",
            )

    def test_ignores_short_env_values(self) -> None:
        # Too short to be a real key; redacting it would mangle ordinary text.
        with patch.dict("os.environ", {"OPENAI_API_KEY": "abc"}):
            self.assertEqual(redact("abc def"), "abc def")

    def test_leaves_ordinary_text_alone(self) -> None:
        self.assertEqual(redact("a normal prompt"), "a normal prompt")


class UsageCostTest(unittest.TestCase):
    def tearDown(self) -> None:
        MODEL_PRICING.clear()

    def test_cost_is_none_without_registered_pricing(self) -> None:
        usage = Usage(model="mystery-model", input_tokens=1000, output_tokens=1000)

        self.assertIsNone(usage.cost)

    def test_cost_uses_registered_pricing(self) -> None:
        register_pricing("m", input_per_1m=1.0, output_per_1m=2.0)
        usage = Usage(model="m", input_tokens=1_000_000, output_tokens=500_000)

        assert usage.cost is not None
        self.assertAlmostEqual(usage.cost, 2.0)

    def test_describe_omits_cost_when_unknown(self) -> None:
        usage = Usage(model="m", total_tokens=5)

        described = usage.describe()
        self.assertIn("tokens=5", described)
        self.assertNotIn("cost=", described)


class UsageCollectorTest(unittest.TestCase):
    def test_reads_usage_metadata_from_the_message(self) -> None:
        collector = UsageCollector()

        collector.on_llm_end(
            _chat_result(
                "hi",
                usage_metadata={
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "total_tokens": 14,
                },
                model="gpt-test",
            ),
            run_id=uuid4(),
        )

        self.assertEqual(collector.usage.input_tokens, 10)
        self.assertEqual(collector.usage.output_tokens, 4)
        self.assertEqual(collector.usage.total_tokens, 14)
        self.assertEqual(collector.usage.model, "gpt-test")
        self.assertEqual(collector.usage.raw_output, "hi")
        self.assertEqual(collector.usage.llm_calls, 1)

    def test_falls_back_to_llm_output_token_usage(self) -> None:
        collector = UsageCollector()
        result = LLMResult(
            generations=[[Generation(text="hi")]],
            llm_output={
                "model_name": "legacy-model",
                "token_usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                    "total_tokens": 10,
                },
            },
        )

        collector.on_llm_end(result, run_id=uuid4())

        self.assertEqual(collector.usage.input_tokens, 7)
        self.assertEqual(collector.usage.output_tokens, 3)
        self.assertEqual(collector.usage.model, "legacy-model")

    def test_does_not_double_count_when_both_sources_present(self) -> None:
        collector = UsageCollector()
        message = AIMessage(
            content="hi",
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 4,
                "total_tokens": 14,
            },
        )
        result = LLMResult(
            generations=[[ChatGeneration(message=message)]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                }
            },
        )

        collector.on_llm_end(result, run_id=uuid4())

        self.assertEqual(collector.usage.total_tokens, 14)

    def test_captures_prompts_from_both_start_hooks(self) -> None:
        collector = UsageCollector()

        collector.on_llm_start({}, ["completion prompt"], run_id=uuid4())
        collector.on_chat_model_start(
            {}, [[AIMessage(content="chat prompt")]], run_id=uuid4()
        )

        self.assertEqual(len(collector.usage.prompts), 2)
        self.assertEqual(collector.usage.prompt, collector.usage.prompts[-1])
        self.assertIn("chat prompt", collector.usage.prompts[-1])

    def test_accumulates_across_retries(self) -> None:
        collector = UsageCollector()

        collector.on_llm_end(_chat_result("first"), run_id=uuid4())
        collector.on_llm_end(_chat_result("second"), run_id=uuid4())

        self.assertEqual(collector.usage.llm_calls, 2)
        self.assertEqual(collector.usage.raw_outputs, ["first", "second"])
        self.assertEqual(collector.usage.raw_output, "second")


class DumpExchangeTest(unittest.TestCase):
    def test_no_ops_without_a_target(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(dump_exchange(title="t", usage=Usage()))

    def test_uses_env_var_when_no_directory_given(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"LANGCHAIN_UTIL_DEBUG_DIR": tmp}):
                path = dump_exchange(title="t", usage=Usage())

            assert path is not None
            self.assertTrue(path.exists())

    def test_survives_an_unwritable_directory(self) -> None:
        # Debug tracing must never break the caller's actual work.
        self.assertIsNone(
            dump_exchange(
                title="t",
                usage=Usage(),
                directory="/proc/definitely/not/writable",
            )
        )


if __name__ == "__main__":
    unittest.main()

"""Prompt repair, and what a repaired call costs.

`pydantic_output.py` turns repair on, but its dry run replays a reply that
parses on the first try, so the repair never runs. This dry run scripts a model
that gets the schema wrong once and right on the second attempt, so you can see:

* the `OutputParserException` logged as a retry,
* the parser's complaint appended to the prompt as an extra human message,
  visible in `usage.prompt` for the attempt that succeeded,
* `attempts == 2` on the result, and a cost once a price is registered.

    bazel run //packages/langchain_util/examples:prompt_repair -- \\
        --dry-run "I was charged twice this month and support hasn't answered."

Against a provider, repair only happens when the model gets the schema wrong,
which a good model rarely does. Pass `--price` to see cost:

    bazel run //packages/langchain_util/examples:prompt_repair -- \\
        --provider openai --price gpt-4o-mini-2024-07-18 0.15 0.60 "..."

Two things the numbers do not say:

* `result.usage` covers the *final* attempt, the one that produced the value.
  The failed attempts were billed too, and `result.attempts` is the only sign
  of them.
* A price is looked up by the model name the *provider reports*, which is often
  a dated snapshot (`gpt-4o-mini-2024-07-18`) rather than the name you asked
  for. A price registered under the short name matches nothing, so this
  example logs the reported name whenever no cost could be computed.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from packages.common.logging_util import get_logger
from packages.langchain_util.api_client import Provider, get_langchain_client
from packages.langchain_util.base import (
    ChatLLM,
    InvocationResult,
    RetryPolicy,
    invoke_llm_detailed,
)
from packages.langchain_util.observability import register_pricing
from packages.langchain_util.prompts import load_chat_prompt

LOGGER = get_logger(name=__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"


class Triage(BaseModel):
    """A support ticket, sorted."""

    category: Literal["billing", "bug", "account", "other"] = Field(
        description="What the ticket is about",
    )
    priority: int = Field(
        ge=1,
        le=4,
        description="1 is most urgent, 4 least",
    )
    needs_human: bool = Field(
        description="True if an agent must reply personally",
    )


DRY_RUN_MODEL = "dry-run-model"

DRY_RUN_REPLIES = (
    # Two schema violations: a category outside the Literal, and a priority
    # past `le=4`. Both land in the feedback the second attempt sees.
    AIMessage(
        content='{"category": "payments", "priority": 5, "needs_human": true}',
        usage_metadata={"input_tokens": 390, "output_tokens": 22, "total_tokens": 412},
        response_metadata={"model_name": DRY_RUN_MODEL},
    ),
    AIMessage(
        content='{"category": "billing", "priority": 2, "needs_human": true}',
        # More input tokens than the first attempt: the repaired prompt carries
        # the parser's complaint.
        usage_metadata={"input_tokens": 520, "output_tokens": 21, "total_tokens": 541},
        response_metadata={"model_name": DRY_RUN_MODEL},
    ),
)


def build_prompt(parser: PydanticOutputParser[Triage]) -> ChatPromptTemplate:
    return load_chat_prompt(
        [
            ("system", "triage.system.jinja"),
            ("human", "triage.human.jinja"),
        ],
        root=PROMPT_DIR,
        partial_variables={
            "format_instructions": parser.get_format_instructions(),
        },
    )


def build_chat(*, provider: Provider, dry_run: bool) -> ChatLLM:
    """The model to call, or one that replays `DRY_RUN_REPLIES` in order.

    `dry_run=` on `invoke_llm_detailed` cannot script a failure. It repeats one
    reply on every attempt, and a reply that parses never needs repair. The
    fake also carries token counts and a model name, which is what gives the
    dry run a cost to report.
    """
    if dry_run:
        return GenericFakeChatModel(messages=iter(DRY_RUN_REPLIES))

    return get_langchain_client(provider=provider)


def triage(
    *,
    ticket: str,
    provider: Provider,
    dry_run: bool,
) -> InvocationResult[Triage]:
    parser = PydanticOutputParser(pydantic_object=Triage)

    return invoke_llm_detailed(
        template=build_prompt(parser),
        chat=build_chat(provider=provider, dry_run=dry_run),
        parser=parser,
        logger=LOGGER,
        input={"ticket": ticket},
        config=RunnableConfig(tags=["example", "prompt-repair"]),
        title="triage",
        # Only parse errors and transient API errors are retried (the default
        # `retry_on`). A bug in this file raises straight through instead of
        # costing three calls. The dry run needs two attempts, so keep at least
        # that many.
        retry_policy=RetryPolicy(attempts=3, max_wait=5.0, deadline=60.0),
        repair_prompt_on_parse_error=True,
    )


def report(result: InvocationResult[Triage]) -> None:
    """Print what the call took, including the prompt that finally worked."""
    usage = result.usage
    print(
        f"Succeeded on attempt {result.attempts} in {result.latency_s:.2f}s; "
        f"final attempt: {usage.describe()}"
    )

    if result.attempts > 1 and usage.prompt is not None:
        # The last human message is the repair. The template itself is
        # unchanged: every repair copies the original, so feedback never piles
        # up across attempts.
        print(f"\nPrompt of the successful attempt:\n{usage.prompt}\n")

    if usage.cost is None:
        LOGGER.warning(
            "No cost: no price registered for model %r. Pass --price with "
            "exactly that name",
            usage.model,
        )


def register_prices(prices: Sequence[Sequence[str]], *, dry_run: bool) -> None:
    """Register `--price` entries, plus a made-up price for the dry-run model."""
    if dry_run:
        register_pricing(DRY_RUN_MODEL, input_per_1m=0.15, output_per_1m=0.60)

    for model, input_per_1m, output_per_1m in prices:
        register_pricing(
            model,
            input_per_1m=float(input_per_1m),
            output_per_1m=float(output_per_1m),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticket", help="Support ticket text to triage")
    parser.add_argument(
        "--provider",
        choices=("openai", "azure", "ollama"),
        default="openai",
        help="Which chat client to build (default: openai)",
    )
    parser.add_argument(
        "--price",
        nargs=3,
        action="append",
        default=[],
        metavar=("MODEL", "IN_PER_1M", "OUT_PER_1M"),
        help="Token price for a model, as reported by the provider; repeatable",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Script a bad reply, then a good one, instead of calling the provider",
    )
    args = parser.parse_args()

    try:
        register_prices(args.price, dry_run=args.dry_run)
    except ValueError:
        parser.error("--price takes MODEL, then two numbers")

    try:
        result = triage(
            ticket=args.ticket,
            provider=args.provider,
            dry_run=args.dry_run,
        )
    except Exception:  # noqa: BLE001 -- CLI boundary: report and exit non-zero
        LOGGER.error("Could not triage the ticket")
        return 1

    report(result)
    print(result.value.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

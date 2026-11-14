r"""A custom `chain_factory` that strips a reasoning model's `<think>` block.

Reasoning models such as deepseek-r1 and qwen3 can put their chain of thought
in the reply itself, wrapped in `<think>...</think>`. `ChatOllama` leaves it
there unless you pass `reasoning=True`, and so can any OpenAI-compatible server
that does not split reasoning out. A `StrOutputParser` hands the block to your
caller. A `PydanticOutputParser` fails on it unless the JSON happens to be
fenced, and repair cannot help, because the model thinks again on every attempt.

The default factory builds `template | chat | parser`. This one adds a step
between the model and the parser:

    bazel run //packages/langchain_util/examples:chain_factory -- \
        --provider ollama "the Bazel build system"

`--dry-run` replays a reply that opens with a `<think>` block. Add
`--keep-reasoning` to use the default factory and see what it lets through:

    bazel run //packages/langchain_util/examples:chain_factory -- --dry-run bazel
    bazel run //packages/langchain_util/examples:chain_factory -- \
        --dry-run --keep-reasoning bazel

Two consequences of putting the step *after* the model:

* `usage.raw_output` and the `debug_dir` dump still contain the reasoning,
  because they are recorded when the model returns, before this step runs.
  That is what you want when a strange answer needs explaining.
* `stream_llm` accepts the same factory but loses streaming with it.
  `RunnableLambda` collects its whole input before calling the function, so
  the answer arrives as one chunk at the end.
"""

import argparse
import re
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import BasePromptTemplate, ChatPromptTemplate
from langchain_core.runnables import RunnableConfig, RunnableLambda

from packages.common.logging_util import get_logger
from packages.langchain_util.api_client import Provider, get_langchain_client
from packages.langchain_util.base import (
    ChainFactory,
    ChatLLM,
    Parser,
    default_chain_factory,
    invoke_llm,
)
from packages.langchain_util.prompts import load_chat_prompt

LOGGER = get_logger(name=__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

DRY_RUN_REPLY = """<think>
The user wants a short explanation of Bazel. Mention hermeticity and caching,
keep it to the requested length, and avoid lists.
</think>

Bazel builds software from an explicit graph of targets and their inputs.
Because every input is declared, it can cache and parallelise aggressively
and still give the same result on another machine."""

_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_reasoning(message: BaseMessage) -> BaseMessage:
    """Drop `<think>...</think>` blocks from a model reply.

    Returns a copy and leaves the model's own reply untouched. Content made of
    blocks instead of one string passes through unchanged. The models that tag
    their reasoning inline send plain strings.
    """
    if not isinstance(message.content, str):
        return message

    return message.model_copy(
        update={"content": _THINK_BLOCK.sub("", message.content)},
    )


def reasoning_stripping_chain_factory(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
) -> Parser:
    """`template | chat | strip_reasoning | parser`.

    The parser must stay last and must stay the one passed in. `invoke_llm`
    infers its return type from `parser`, so a factory that replaced or
    wrapped the parser would make that inferred type a lie.
    """
    return template | chat | RunnableLambda(strip_reasoning) | parser


def build_prompt() -> ChatPromptTemplate:
    """Load the explain prompt from the example templates."""
    return load_chat_prompt(
        [
            ("system", "explain.system.jinja"),
            ("human", "explain.human.jinja"),
        ],
        root=PROMPT_DIR,
    )


def build_chat(*, provider: Provider, dry_run: bool) -> ChatLLM:
    """The client to invoke, or a placeholder when nothing will be sent.

    `dry_run=` replaces the model but not the factory, so the dry-run reply
    still passes through `strip_reasoning`.
    """
    if dry_run:
        return FakeListChatModel(responses=["<replaced by dry_run>"])

    return get_langchain_client(provider=provider)


def explain(
    *,
    topic: str,
    provider: Provider,
    dry_run: bool,
    keep_reasoning: bool,
) -> str:
    """Explain *topic* with a chain that keeps or strips the model's reasoning."""
    # Annotated as the Protocol so a factory with the wrong signature fails
    # type checking here, not when the chain is built.
    factory: ChainFactory = (
        default_chain_factory if keep_reasoning else reasoning_stripping_chain_factory
    )

    return invoke_llm(
        template=build_prompt(),
        chat=build_chat(provider=provider, dry_run=dry_run),
        parser=StrOutputParser(),
        logger=LOGGER,
        chain_factory=factory,
        input={"topic": topic, "sentences": 2, "audience": ""},
        config=RunnableConfig(tags=["example", "chain-factory"]),
        title=f"explain-{topic}",
        dry_run=DRY_RUN_REPLY if dry_run else None,
    )


def main() -> int:
    """Parse the command line, run the example and return an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", help="What to explain")
    parser.add_argument(
        "--provider",
        choices=("openai", "azure", "ollama"),
        default="ollama",
        help="Which chat client to build (default: ollama)",
    )
    parser.add_argument(
        "--keep-reasoning",
        action="store_true",
        help="Use the default factory, leaving any <think> block in the answer",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Replay a canned reasoning-model reply instead of calling the provider",
    )
    args = parser.parse_args()

    try:
        answer = explain(
            topic=args.topic,
            provider=args.provider,
            dry_run=args.dry_run,
            keep_reasoning=args.keep_reasoning,
        )
    except Exception:  # noqa: BLE001 -- CLI boundary: report and exit non-zero
        LOGGER.error("Could not explain %r", args.topic)
        return 1

    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

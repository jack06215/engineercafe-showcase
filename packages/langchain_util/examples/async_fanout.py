r"""Many calls at once: `ainvoke_llm` fanned out, `astream_llm` for streaming.

Reuses the `prompts/explain.*.jinja` pair from `string_output.py`, so the only
new thing here is the concurrency.

Run it against a provider:

    bazel run //packages/langchain_util/examples:async_fanout -- \
        --provider openai bazel docker kubernetes

Or without spending anything. `--dry-run` swaps in a fake model that takes a
second per reply, so the fan-out is something you can see: four topics finish
in about one second, not four.

    bazel run //packages/langchain_util/examples:async_fanout -- \
        --dry-run bazel docker kubernetes nix

`--stream` switches to `astream_llm` and prints each answer as it arrives.
"""

import argparse
import asyncio
import time
from collections.abc import Sequence
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from packages.common.logging_util import get_logger
from packages.langchain_util.api_client import Provider, get_langchain_client
from packages.langchain_util.base import (
    ChatLLM,
    RetryPolicy,
    ainvoke_llm,
    astream_llm,
)
from packages.langchain_util.prompts import load_chat_prompt

LOGGER = get_logger(name=__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

DRY_RUN_REPLY = (
    "It describes what to build and lets a tool work out how. The payoff is "
    "that the same description gives the same result on every machine."
)

# FakeListChatModel sleeps once per reply when invoked, but once per *character*
# when streamed -- so the two paths need very different numbers.
FAKE_REPLY_DELAY_S = 1.0
FAKE_CHAR_DELAY_S = 0.01

RETRY_POLICY = RetryPolicy(attempts=3, max_wait=10.0, deadline=60.0)


def build_prompt() -> ChatPromptTemplate:
    """Load the explain prompt from the example templates."""
    return load_chat_prompt(
        [
            ("system", "explain.system.jinja"),
            ("human", "explain.human.jinja"),
        ],
        root=PROMPT_DIR,
    )


def build_chat(*, provider: Provider, dry_run: bool, fake_delay: float) -> ChatLLM:
    """One client for every task.

    It owns the HTTP connection pool, so sharing it across coroutines is the
    point rather than a hazard.

    The dry run hands `ainvoke_llm` a slow fake as the real `chat` instead of
    passing `dry_run=`: that parameter builds a model that answers instantly,
    and a fan-out that takes no time at all shows nothing about concurrency.
    """
    if dry_run:
        return FakeListChatModel(responses=[DRY_RUN_REPLY], sleep=fake_delay)

    return get_langchain_client(provider=provider)


async def explain_one(
    *,
    topic: str,
    chat: ChatLLM,
    limit: asyncio.Semaphore,
) -> str:
    """Explain one topic, holding a concurrency slot for the whole call.

    The retry backoff sleeps *inside* the semaphore, so a rate-limited call
    keeps its slot while it waits. A 429 means "send less", and giving the slot
    to the next request would do the opposite.
    """
    async with limit:
        # ainvoke_llm returns Any -- its docstring says to annotate at the call
        # site, which is what makes `-> str` above mean something.
        answer: str = await ainvoke_llm(
            template=build_prompt(),
            chat=chat,
            parser=StrOutputParser(),
            logger=LOGGER,
            input={"topic": topic, "sentences": 2, "audience": ""},
            config=RunnableConfig(tags=["example", "async-fanout"]),
            title=f"explain-{topic}",
            retry_policy=RETRY_POLICY,
        )

    return answer


async def explain_all(
    *,
    topics: Sequence[str],
    provider: Provider,
    dry_run: bool,
    max_concurrency: int,
) -> list[str | BaseException]:
    """Explain every topic concurrently, at most `max_concurrency` at a time.

    `return_exceptions=True` keeps one failed topic from discarding the rest:
    plain `gather` raises the first error, and the other results are lost even
    though their calls finished and were billed.
    """
    chat = build_chat(
        provider=provider,
        dry_run=dry_run,
        fake_delay=FAKE_REPLY_DELAY_S,
    )
    limit = asyncio.Semaphore(max_concurrency)

    return await asyncio.gather(
        *(explain_one(topic=topic, chat=chat, limit=limit) for topic in topics),
        return_exceptions=True,
    )


async def stream_all(
    *,
    topics: Sequence[str],
    provider: Provider,
    dry_run: bool,
) -> None:
    """Stream each topic in turn.

    One after another, not concurrently: several streams interleaved on one
    terminal are unreadable. In a server, each would go to its own client.
    """
    chat = build_chat(provider=provider, dry_run=dry_run, fake_delay=FAKE_CHAR_DELAY_S)

    for topic in topics:
        print(f"== {topic}")
        async for chunk in astream_llm(
            template=build_prompt(),
            chat=chat,
            parser=StrOutputParser(),
            logger=LOGGER,
            input={"topic": topic, "sentences": 2, "audience": ""},
            title=f"explain-{topic}-streaming",
            retry_policy=RETRY_POLICY,
        ):
            print(chunk, end="", flush=True)

        print()


def main() -> int:
    """Parse the command line, run the example and return an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topics", nargs="+", help="Topics to explain")
    parser.add_argument(
        "--provider",
        choices=("openai", "azure", "ollama"),
        default="openai",
        help="Which chat client to build (default: openai)",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Calls in flight at once (default: 4)",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream each answer with astream_llm instead of fanning out",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use a slow fake model instead of calling the provider",
    )
    args = parser.parse_args()

    if args.stream:
        try:
            asyncio.run(
                stream_all(
                    topics=args.topics,
                    provider=args.provider,
                    dry_run=args.dry_run,
                )
            )
        except Exception:  # noqa: BLE001 -- CLI boundary: report and exit non-zero
            LOGGER.error("Streaming stopped early")
            return 1

        return 0

    started = time.perf_counter()
    results = asyncio.run(
        explain_all(
            topics=args.topics,
            provider=args.provider,
            dry_run=args.dry_run,
            max_concurrency=args.max_concurrency,
        )
    )
    elapsed = time.perf_counter() - started

    failed = 0
    for topic, result in zip(args.topics, results, strict=True):
        print(f"== {topic}")
        if isinstance(result, BaseException):
            # ainvoke_llm already logged the traceback; one line is enough here.
            failed += 1
            print(f"(failed: {type(result).__name__})")
        else:
            print(result)

    print(
        f"-- {len(args.topics)} topic(s) in {elapsed:.2f}s with up to "
        f"{args.max_concurrency} in flight, {failed} failed"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

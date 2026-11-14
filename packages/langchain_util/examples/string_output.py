"""Free-text output: `StrOutputParser`, so `invoke_llm` returns a `str`.

The prompt lives in `prompts/explain.*.jinja`, one file per chat message, loaded
by `langchain_util.prompts.load_chat_prompt`.

Run it against a provider:

    bazel run //packages/langchain_util/examples:string_output -- \\
        --provider openai "the Bazel build system"

Or without spending anything -- `--dry-run` replays the canned reply below,
while the real templates, parser, and retry loop still run:

    bazel run //packages/langchain_util/examples:string_output -- --dry-run bazel

See `pydantic_output.py` for the structured-output counterpart.
"""

import argparse
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from packages.common.logging_util import get_logger
from packages.langchain_util.api_client import Provider, get_langchain_client
from packages.langchain_util.base import ChatLLM, RetryPolicy, invoke_llm, stream_llm
from packages.langchain_util.prompts import load_chat_prompt

LOGGER = get_logger(name=__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

DRY_RUN_REPLY = (
    "Bazel is a build system that describes every target and its dependencies "
    "explicitly. Because the graph is complete, it can cache and parallelise "
    "aggressively and still reproduce the same outputs on another machine."
)


def build_prompt() -> ChatPromptTemplate:
    """Load the system/human pair from disk.

    Loading per call rather than at import keeps an edit to a `.jinja` file one
    re-run away from being visible, instead of one restart of a long-lived
    process. Cache it in a module global if a hot loop ever makes that matter.
    """
    return load_chat_prompt(
        [
            ("system", "explain.system.jinja"),
            ("human", "explain.human.jinja"),
        ],
        # Redundant while both names are literals, and the habit worth keeping:
        # a template is executable code, so the day a name comes from anywhere
        # but this file, `root` is already the thing stopping it from escaping.
        root=PROMPT_DIR,
    )


def build_chat(*, provider: Provider, dry_run: bool) -> ChatLLM:
    """The client to invoke, or a placeholder when nothing will be sent.

    `dry_run` swaps the model out inside `invoke_llm`, so the value passed as
    `chat` is never called -- and building a real client would demand
    credentials a dry run has no use for.
    """
    if dry_run:
        return FakeListChatModel(responses=["<replaced by dry_run>"])

    return get_langchain_client(provider=provider)


def explain(
    *,
    topic: str,
    sentences: int,
    audience: str,
    provider: Provider,
    dry_run: bool,
) -> str:
    """Ask the model for a short explanation and return it verbatim."""
    # `audience` is optional *content* -- `{%- if audience %}` drops the line
    # when it is empty -- but not an optional *variable*: jinja2 would render an
    # undefined name as nothing at all, so LangChain requires every name the
    # template mentions and raises a KeyError naming the ones you left out.
    input_data = {"topic": topic, "sentences": sentences, "audience": audience}

    # StrOutputParser hands back the message text, so the overloads on
    # invoke_llm infer `str` -- no cast, no `Any` leaking into the caller.
    return invoke_llm(
        template=build_prompt(),
        chat=build_chat(provider=provider, dry_run=dry_run),
        parser=StrOutputParser(),
        logger=LOGGER,
        input=input_data,
        config=RunnableConfig(tags=["example", "string-output"]),
        title=f"explain-{topic}",
        retry_policy=RetryPolicy(attempts=3, max_wait=10.0, deadline=60.0),
        dry_run=DRY_RUN_REPLY if dry_run else None,
    )


def explain_streaming(
    *,
    topic: str,
    sentences: int,
    audience: str,
    provider: Provider,
    dry_run: bool,
) -> str:
    """Same call, printed token by token as the model produces it.

    `stream_llm` retries only until the first chunk reaches you; after that a
    restart would replay text you have already seen, so the error propagates.
    """
    chunks: list[str] = []
    for chunk in stream_llm(
        template=build_prompt(),
        chat=build_chat(provider=provider, dry_run=dry_run),
        parser=StrOutputParser(),
        logger=LOGGER,
        input={"topic": topic, "sentences": sentences, "audience": audience},
        title=f"explain-{topic}-streaming",
        dry_run=DRY_RUN_REPLY if dry_run else None,
    ):
        chunks.append(chunk)
        print(chunk, end="", flush=True)

    print()
    return "".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", help="What to explain")
    parser.add_argument(
        "--provider",
        choices=("openai", "azure", "ollama"),
        default="openai",
        help="Which chat client to build (default: openai)",
    )
    parser.add_argument("--sentences", type=int, default=3)
    parser.add_argument(
        "--audience",
        default="",
        help="Who is reading, e.g. 'new to build systems'. Omit to drop the line",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Print the answer incrementally instead of all at once",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Replay a canned reply instead of calling the provider",
    )
    args = parser.parse_args()

    run = explain_streaming if args.stream else explain
    try:
        answer = run(
            topic=args.topic,
            sentences=args.sentences,
            audience=args.audience,
            provider=args.provider,
            dry_run=args.dry_run,
        )
    except Exception:  # noqa: BLE001 -- CLI boundary: report and exit non-zero
        # invoke_llm already logged the failure, the attempt count, and the last
        # raw output; re-logging the traceback here would just duplicate it.
        LOGGER.error("Could not explain %r", args.topic)
        return 1

    if not args.stream:
        print(answer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

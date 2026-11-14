"""Response caching: identical prompts answered from disk, not the provider.

`enable_llm_cache` installs a process-wide cache that every LangChain chat model
checks before it sends a request, so `invoke_llm` takes no extra argument.

Ask the same question twice. The second call returns in milliseconds and sends
nothing:

    bazel run //packages/langchain_util/examples:llm_cache -- \\
        --provider openai --repeat 2 "What is a content-addressed cache?"

Run it again and even the first call is a hit, because the SQLite file outlives
the process. `--in-memory` gives a cache that lasts for one run only.

`--dry-run` uses a fake model that takes a second per reply, so a hit shows up
as the missing second:

    bazel run //packages/langchain_util/examples:llm_cache -- \\
        --dry-run --in-memory --repeat 3 "anything"

What the cache key is, and what that implies:

* The rendered messages plus the model's parameters. Change the model or the
  temperature and you miss; edit a `.jinja` file and you miss.
* Only replies are stored, never errors, so a rate-limit retry still goes out.
  A reply that fails to *parse* is still a reply, though, and it is cached. An
  identical retry would read the same bad reply back on every attempt.
  `repair_prompt_on_parse_error` (on by default) changes the prompt, which is
  what lets the retry miss the cache. Leave it on while the cache is on.
* A hit is not free in the logs. The cached message keeps the token counts from
  the call that filled the cache, so `usage.describe()` reports them again and
  `Usage.cost` prices tokens nobody was billed for. Trust latency, not cost, to
  tell a hit from a miss.
"""

import argparse
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from packages.common.logging_util import get_logger
from packages.langchain_util.api_client import Provider, get_langchain_client
from packages.langchain_util.base import ChatLLM, invoke_llm_detailed
from packages.langchain_util.cache import (
    DEFAULT_CACHE_PATH,
    disable_llm_cache,
    enable_llm_cache,
)
from packages.langchain_util.prompts import load_chat_prompt

LOGGER = get_logger(name=__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

DRY_RUN_REPLY = "A cache keyed by a hash of the content it stores."

FAKE_REPLY_DELAY_S = 1.0


def build_prompt() -> ChatPromptTemplate:
    return load_chat_prompt(
        [
            ("system", "explain.system.jinja"),
            ("human", "explain.human.jinja"),
        ],
        root=PROMPT_DIR,
    )


def build_chat(*, provider: Provider, dry_run: bool) -> ChatLLM:
    """The model to call, or a slow fake standing in for one.

    The fake is passed as `chat` rather than through `dry_run=`, whose model
    answers instantly and would leave nothing for a hit to save. Its cache
    entries are keyed by the fake's own model type, so they can never answer a
    prompt meant for a real provider.
    """
    if dry_run:
        return FakeListChatModel(responses=[DRY_RUN_REPLY], sleep=FAKE_REPLY_DELAY_S)

    return get_langchain_client(provider=provider)


def ask_repeatedly(
    *,
    question: str,
    repeat: int,
    provider: Provider,
    dry_run: bool,
) -> str:
    """Send the same question `repeat` times and log how long each took."""
    chat = build_chat(provider=provider, dry_run=dry_run)
    answer = ""

    for call in range(1, repeat + 1):
        # Rebuilding the template every time is deliberate. The key is the
        # rendered prompt, not the template object, so a fresh one still hits.
        result = invoke_llm_detailed(
            template=build_prompt(),
            chat=chat,
            parser=StrOutputParser(),
            logger=LOGGER,
            input={"topic": question, "sentences": 2, "audience": ""},
            config=RunnableConfig(tags=["example", "llm-cache"]),
            title=f"cached-call-{call}",
        )
        print(f"call {call}/{repeat}: {result.latency_s:.3f}s")
        answer = result.value

    return answer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="What to ask; repeated verbatim")
    parser.add_argument(
        "--provider",
        choices=("openai", "azure", "ollama"),
        default="openai",
        help="Which chat client to build (default: openai)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=2,
        help="How many times to send the question (default: 2)",
    )
    storage = parser.add_mutually_exclusive_group()
    storage.add_argument(
        "--cache-path",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help=f"SQLite cache file (default: {DEFAULT_CACHE_PATH})",
    )
    storage.add_argument(
        "--in-memory",
        action="store_true",
        help="Cache for this run only instead of on disk",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Empty the cache before asking, so the first call is a miss",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use a slow fake model instead of calling the provider",
    )
    args = parser.parse_args()

    cache = enable_llm_cache(None if args.in_memory else args.cache_path)
    print("cache: in memory" if args.in_memory else f"cache: {args.cache_path}")
    if args.clear:
        cache.clear()

    # The cache is global state. A CLI exits and takes it along, but in a
    # long-lived process or a test, pair enable with disable -- otherwise
    # every later model call in the process quietly reads from it.
    try:
        answer = ask_repeatedly(
            question=args.question,
            repeat=args.repeat,
            provider=args.provider,
            dry_run=args.dry_run,
        )
    except Exception:  # noqa: BLE001 -- CLI boundary: report and exit non-zero
        LOGGER.error("Could not answer %r", args.question)
        return 1
    finally:
        disable_llm_cache()

    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

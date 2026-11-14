r"""A prompt chosen at runtime, confined with `resolve_prompt_path`.

In the other examples every template name is a literal, so `root=` is a habit
rather than a defence. Here the name comes from the command line: `--tone
formal` loads `prompts/tones/formal.jinja` as the system message. That is the
case `root` exists for. A jinja2 template is executable code, so whoever can
choose the file can choose the code.

    bazel run //packages/langchain_util/examples:prompt_selection -- \
        --provider openai --tone terse "Hi all! Just a quick heads-up ..."

    bazel run //packages/langchain_util/examples:prompt_selection -- \
        --dry-run --tone friendly "The build is broken. Do not merge."

A name that tries to leave the tones directory is refused before anything is
read or sent:

    bazel run //packages/langchain_util/examples:prompt_selection -- \
        --dry-run --tone ../incident_report "anything"

If the set of names is fixed, argparse `choices=` is the stronger check and
makes `root` redundant. `root` is for when the directory itself is the allowlist,
so a new tone ships as a file with no code change, and for names that arrive
where argparse cannot check them, such as a request body.
"""

import argparse
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from packages.common.logging_util import get_logger
from packages.langchain_util.api_client import Provider, get_langchain_client
from packages.langchain_util.base import ChatLLM, invoke_llm
from packages.langchain_util.prompts import (
    PromptPathError,
    load_chat_prompt,
    resolve_prompt_path,
)

LOGGER = get_logger(name=__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"
TONE_DIR = PROMPT_DIR / "tones"

DRY_RUN_REPLY = (
    "Heads-up: the build is broken right now, so please hold off on merging."
)


def available_tones() -> list[str]:
    """Return the tone names that have a template in the tones folder."""
    return sorted(path.stem for path in TONE_DIR.glob("*.jinja"))


def build_prompt(tone: str) -> ChatPromptTemplate:
    """Resolve the tone inside `TONE_DIR`, then load it with the fixed message.

    Confine to the *narrowest* directory that holds the choices. With
    `root=PROMPT_DIR`, `tones/../incident_report.jinja` would pass, because it
    never leaves `prompts/`. The check is on where the name ends up, not on
    whether it contains `..`.

    Raises:
        PromptPathError: `tone` resolves outside `TONE_DIR`.
        FileNotFoundError: `tone` stays inside but names no file.
    """
    system_path = resolve_prompt_path(f"{tone}.jinja", root=TONE_DIR)

    # No `root=` on this call. `system_path` is already confined, and the human
    # message is a path this file spells out, not one anyone else supplies.
    return load_chat_prompt(
        [
            ("system", system_path),
            ("human", PROMPT_DIR / "rewrite.human.jinja"),
        ],
    )


def build_chat(*, provider: Provider, dry_run: bool) -> ChatLLM:
    """Return a fake chat model on a dry run, else the provider's client."""
    if dry_run:
        return FakeListChatModel(responses=["<replaced by dry_run>"])

    return get_langchain_client(provider=provider)


def rewrite(
    *,
    text: str,
    template: ChatPromptTemplate,
    tone: str,
    provider: Provider,
    dry_run: bool,
) -> str:
    """Rewrite *text* in *tone* with the selected template."""
    return invoke_llm(
        template=template,
        chat=build_chat(provider=provider, dry_run=dry_run),
        parser=StrOutputParser(),
        logger=LOGGER,
        # The *text* is untrusted too, but a value cannot hurt: it is
        # substituted without being rendered, so `{{ ... }}` in it stays inert.
        input={"text": text},
        config=RunnableConfig(tags=["example", "prompt-selection"]),
        title=f"rewrite-{tone}",
        dry_run=DRY_RUN_REPLY if dry_run else None,
    )


def main() -> int:
    """Parse the command line, run the example and return an exit code."""
    tones = available_tones()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help="Text to rewrite")
    parser.add_argument(
        "--tone",
        required=True,
        # Deliberately not `choices=tones`: that would stop a bad name before
        # `resolve_prompt_path` ever saw it, which is safer and also the end of
        # the demonstration.
        help=f"Name of a file in {TONE_DIR.name}/, without .jinja: {', '.join(tones)}",
    )
    parser.add_argument(
        "--provider",
        choices=("openai", "azure", "ollama"),
        default="openai",
        help="Which chat client to build (default: openai)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Replay a canned reply instead of calling the provider",
    )
    args = parser.parse_args()

    try:
        template = build_prompt(args.tone)
    except PromptPathError as exc:
        # Its own exception type so this case can be told apart from a typo: a
        # name trying to escape its directory is an attack or a bug, and in a
        # service it deserves an alert, not just a 400.
        LOGGER.error("Refused tone %r: %s", args.tone, exc)
        return 2
    except FileNotFoundError:
        LOGGER.error("No tone named %r; available: %s", args.tone, ", ".join(tones))
        return 2

    try:
        answer = rewrite(
            text=args.text,
            template=template,
            tone=args.tone,
            provider=args.provider,
            dry_run=args.dry_run,
        )
    except Exception:  # noqa: BLE001 -- CLI boundary: report and exit non-zero
        LOGGER.error("Could not rewrite the text")
        return 1

    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

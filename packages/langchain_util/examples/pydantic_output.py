r"""Structured output example.

The prompt lives in `prompts/incident_report.jinja` and is loaded by
`langchain_util.prompts.load_prompt`. Two jinja2 features earn their keep there:
a `{% for %}` over the severity vocabulary, so the allowed values are defined
once in Python, and a `{% if %}` around the known-services block, so an absent
list removes the section instead of leaving a dangling header.

Run it against a provider:

    bazel run //packages/langchain_util/examples:pydantic_output -- \
        --provider openai "The 14:00 deploy failed twice; rolled back at 14:20."

Or without spending anything -- `--dry-run` feeds the canned JSON below through
the *real* parser, which is the cheapest way to check that a schema and its
format instructions actually round-trip:

    bazel run //packages/langchain_util/examples:pydantic_output -- --dry-run "..."

Two things make the structured path different from the string one:

* `format_instructions` must reach the prompt. Bind it as a partial at load time
  so the schema travels with the template instead of every call site
  remembering it.
* A parse failure is retryable. `repair_prompt_on_parse_error` (on by default)
  hands the parser's complaint back to the next attempt -- as a *value*, so
  braces and jinja2 tags in the model's bad output are reported literally
  rather than re-rendered.

See `string_output.py` for the free-text counterpart.
"""

import argparse
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from packages.common.logging_util import get_logger
from packages.langchain_util.api_client import Provider, get_langchain_client
from packages.langchain_util.base import ChatLLM, RetryPolicy, invoke_llm_detailed
from packages.langchain_util.prompts import load_prompt

LOGGER = get_logger(name=__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

SEVERITY_LEVELS = ("low", "medium", "high", "critical")


class Action(BaseModel):
    """One follow-up item pulled out of the note."""

    description: str = Field(
        description="What needs to happen, in imperative mood",
    )
    owner: str | None = Field(
        default=None,
        description="Who owns it, or null if the note does not say",
    )


class IncidentReport(BaseModel):
    """The shape the model must produce.

    Every `description` here lands in the prompt via `get_format_instructions`,
    so they are prompt engineering, not just documentation -- vague ones produce
    vague fields.
    """

    summary: str = Field(
        description="One sentence describing what happened",
    )
    severity: str = Field(
        description=f"One of: {', '.join(SEVERITY_LEVELS)}",
    )
    root_cause: str | None = Field(
        default=None,
        description="The cause if the note states one, otherwise null",
    )
    actions: list[Action] = Field(
        default_factory=list,
        description="Follow-up items, empty if the note names none",
    )


DRY_RUN_REPLY = """
{
  "summary": "The 14:00 deploy failed twice and was rolled back at 14:20.",
  "severity": "high",
  "root_cause": null,
  "actions": [
    {"description": "Investigate why the deploy failed twice", "owner": null}
  ]
}
"""


def build_prompt(parser: PydanticOutputParser[IncidentReport]) -> PromptTemplate:
    """Load the template and bind the schema instructions to it.

    A partial is bound once, at load time, and drops out of the template's input
    variables -- so a caller cannot forget it, and cannot pass a stale copy that
    disagrees with the parser doing the actual validating.
    """
    return load_prompt(
        "incident_report.jinja",
        # Confines the name to PROMPT_DIR. Unnecessary for a literal, but this
        # is the call that must already be shaped this way if the name ever
        # starts coming from a request -- see the security note in `prompts`.
        root=PROMPT_DIR,
        partial_variables={
            "format_instructions": parser.get_format_instructions(),
        },
    )


def build_chat(*, provider: Provider, dry_run: bool) -> ChatLLM:
    """The client to invoke, or a placeholder when nothing will be sent.

    `dry_run` swaps the model out inside `invoke_llm_detailed`, so the value
    passed as `chat` is never called -- and building a real client would demand
    credentials a dry run has no use for.
    """
    if dry_run:
        return FakeListChatModel(responses=["<replaced by dry_run>"])

    return get_langchain_client(provider=provider)


def extract(
    *,
    note: str,
    known_services: list[str],
    provider: Provider,
    dry_run: bool,
    debug_dir: str | None,
) -> IncidentReport:
    """Turn a free-text note into a validated `IncidentReport`."""
    parser = PydanticOutputParser(pydantic_object=IncidentReport)

    # Every name the template mentions must be supplied, including the ones only
    # a `{% if %}`/`{% for %}` reads -- an empty list renders that section away,
    # while omitting the key raises a KeyError before any call is made.
    input_data = {
        "note": note,
        "severity_levels": list(SEVERITY_LEVELS),
        "known_services": known_services,
    }

    # invoke_llm_detailed returns the parsed value *plus* what it cost to get:
    # token counts, attempts, latency. Use plain invoke_llm when you only want
    # the value -- it is the same call with `.value` already applied.
    result = invoke_llm_detailed(
        template=build_prompt(parser),
        chat=build_chat(provider=provider, dry_run=dry_run),
        parser=parser,
        logger=LOGGER,
        input=input_data,
        config=RunnableConfig(tags=["example", "pydantic-output"]),
        title="incident-report",
        # A malformed JSON body is worth another try, and the repaired prompt
        # makes the next attempt materially more likely to succeed.
        retry_policy=RetryPolicy(attempts=4, max_wait=15.0, deadline=90.0),
        repair_prompt_on_parse_error=True,
        dry_run=DRY_RUN_REPLY if dry_run else None,
        # Writes a redacted prompt/response JSON dump per call. Handy while a
        # schema is still moving; leave it unset (and leave
        # LANGCHAIN_UTIL_DEBUG_DIR unset) in anything long-running.
        debug_dir=debug_dir,
    )

    LOGGER.info(
        "Extracted report in %.2fs over %d attempt(s): %s",
        result.latency_s,
        result.attempts,
        result.usage.describe(),
    )
    if result.debug_path is not None:
        LOGGER.info("Full exchange written to %s", result.debug_path)

    # The overloads carry the parser's type through, so this is an
    # IncidentReport to the type checker -- `.severity` below is checked.
    return result.value


def main() -> int:
    """Parse the command line, run the example and return an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note", help="Free-text incident note to structure")
    parser.add_argument(
        "--provider",
        choices=("openai", "azure", "ollama"),
        default="openai",
        help="Which chat client to build (default: openai)",
    )
    parser.add_argument(
        "--service",
        action="append",
        default=[],
        dest="known_services",
        help="Known service name; repeatable. Omit to drop the section entirely",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse a canned JSON reply instead of calling the provider",
    )
    parser.add_argument(
        "--debug-dir",
        help="Directory for redacted prompt/response dumps",
    )
    args = parser.parse_args()
    try:
        report = extract(
            note=args.note,
            known_services=args.known_services,
            provider=args.provider,
            dry_run=args.dry_run,
            debug_dir=args.debug_dir,
        )
    except Exception:  # noqa: BLE001 -- CLI boundary: report and exit non-zero
        # invoke_llm_detailed already logged the failure and the last raw output
        # (at DEBUG), which is usually the thing you actually want to read.
        LOGGER.error("Could not extract an incident report")
        return 1

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

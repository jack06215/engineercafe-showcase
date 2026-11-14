"""One-shot structured output: one prompt, one model call, one Pydantic model.

The prompt is the usual pair of `.jinja` files -- a system and a human message
-- loaded with `langchain_util.prompts.load_chat_prompt`. `generate` binds the
output schema to it, calls `invoke_llm`, and returns the parsed model:

    prompt = load_chat_prompt(
        [("system", "triage.system.jinja"), ("human", "triage.human.jinja")],
        root=PROMPT_DIR,
    )
    triage = generate(
        prompt=prompt,
        output=Triage,
        chat=chat,
        logger=LOGGER,
        input={"ticket": ticket},
    )

One of the two templates must reference `{{ format_instructions }}`. That is
where the JSON schema the parser validates against reaches the model, so a
prompt without it is refused before anything is sent.

`langchain_util.thinking` takes the same prompt and output type and puts a
generate-evaluate loop around the call, for when one pass is not good enough.
"""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from packages.langchain_util.base import (
    DEFAULT_RETRY_POLICY,
    ChatLLM,
    RetryPolicy,
    invoke_llm,
)

FORMAT_INSTRUCTIONS_VARIABLE = "format_instructions"
"""The template variable that carries the output schema into the prompt."""


def bind_output_schema[T: BaseModel](
    prompt: ChatPromptTemplate,
    parser: PydanticOutputParser[T],
) -> ChatPromptTemplate:
    """Bind `parser`'s format instructions to `prompt` as a partial.

    Bound from the parser that will do the validating, so the schema the model
    reads and the schema its reply is checked against cannot drift apart.

    Raises:
        ValueError: No message in `prompt` references `format_instructions`.
            Without it the model never sees the schema, and every reply fails
            to parse only after it has been paid for.
    """
    if FORMAT_INSTRUCTIONS_VARIABLE not in prompt.input_variables:
        msg = (
            f"the prompt never references {{{{ {FORMAT_INSTRUCTIONS_VARIABLE} }}}}, "
            f"so the model would not see the {parser.pydantic_object.__name__} schema; "
            f"its variables are {sorted(prompt.input_variables)}"
        )
        raise ValueError(msg)

    return prompt.partial(
        **{FORMAT_INSTRUCTIONS_VARIABLE: parser.get_format_instructions()},
    )


def generate[T: BaseModel](
    *,
    prompt: ChatPromptTemplate,
    output: type[T],
    chat: ChatLLM,
    logger: logging.Logger,
    input: Mapping[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> T:
    """Render `prompt`, call the model once, and parse the reply into `output`.

    "Once" means one answer, not one request: transient API errors and parse
    failures are still retried under `retry_policy`, and a parse failure is fed
    back into the next attempt -- see `invoke_llm_detailed`.

    Args:
        prompt: The system/human templates, not yet bound to a schema.
        output: The Pydantic model to return. Its field descriptions reach the
            prompt through `format_instructions`, so they are instructions.
        chat: Chat model runnable.
        logger: Caller's logger. Retries and failures are reported here.
        input: Template variables, every one the templates reference except
            `format_instructions`.
        config: Runnable config. Copied, never mutated.
        title: Label for log messages.
        retry_policy: Attempts, backoff, deadline, and retryable exceptions.
        dry_run: If set, parse this string instead of calling the provider.
        debug_dir: Write a redacted prompt/response dump here.

    Returns:
        The validated `output` instance.

    Raises:
        ValueError: `prompt` never references `format_instructions`.
    """
    parser = PydanticOutputParser(pydantic_object=output)
    return invoke_llm(
        template=bind_output_schema(prompt, parser),
        chat=chat,
        parser=parser,
        logger=logger,
        input=dict(input or {}),
        config=config,
        title=title,
        retry_policy=retry_policy,
        dry_run=dry_run,
        debug_dir=debug_dir,
    )

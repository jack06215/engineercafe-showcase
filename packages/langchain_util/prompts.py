"""Load prompt templates from `.jinja` files instead of Python string literals.

A prompt on disk diffs cleanly, keeps Python files free of multi-line strings,
and -- with `template_format="jinja2"` -- gets conditionals and loops, so an
optional section stops being a string-concatenation puzzle at the call site.

Two things about the jinja2 dialect LangChain renders:

* It renders the template *string* through a fresh `SandboxedEnvironment` with
  no filesystem loader, so `{% include %}` and `{% extends %}` do not work.
  Compose in Python instead -- `load_chat_prompt` takes one file per message.
* That environment uses jinja2's defaults, so `{%- -%}` is the only way to
  control whitespace around block tags.

Every variable a template references becomes a required input variable, and
LangChain raises a `KeyError` naming the missing ones -- a typo fails before the
provider is ever called, not silently as an empty string.

Security
--------

A jinja2 template is executable code, and the `SandboxedEnvironment` LangChain
renders it in is a hardening layer, not a boundary you can put untrusted input
on the far side of. Template *text* must always be yours; untrusted data may
only ever arrive as a variable *value*. Formatters substitute values without
rescanning them, so JSON, braces, and `{% %}` tags inside a value are inert.

That splits into three rules, all of them about who authors the text:

* Load templates from files you wrote, as these functions do. Never call
  `PromptTemplate.from_template(untrusted_text, template_format="jinja2")`.
* Do not let a *path* come from user input either -- choosing the template is
  as good as writing it. Pass `root=` to confine a name to one directory; it
  is enforced by `resolve_prompt_path`, which refuses absolute paths and any
  `..` that would climb out.
* Model output is untrusted input too. It flows back into the prompt when
  `langchain_util.base` repairs a parse error, which is why that path passes it
  as a partial *value* rather than appending it to the template text.

Prefer plain data -- `str`, `list`, `dict` -- for variable values. The sandbox
blocks dunder attributes, but ordinary attribute access and method calls still
work, so a rich object hands the template more reach than it needs.
"""

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.prompts.string import PromptTemplateFormat

DEFAULT_TEMPLATE_FORMAT: PromptTemplateFormat = "jinja2"

type MessageRole = str
"""A LangChain message role: "system", "human", "ai", ..."""


class PromptPathError(ValueError):
    """A prompt path was rejected before anything was read.

    Its own type, not a bare `ValueError`, so a caller can tell "this name tried
    to leave its root" -- worth logging loudly -- from any other bad argument.
    """


def resolve_prompt_path(name: str | Path, *, root: str | Path) -> Path:
    """Resolve `name` inside `root`, refusing anything that leaves it.

    Pass `root` whenever the name is not a literal in your source. A jinja2
    template is executable code, so choosing which file gets loaded is as good
    as writing it: `../../etc/whatever.jinja` from a request parameter is the
    same class of hole as accepting the template text itself.

    Confinement is lexical -- `..` is collapsed without touching the disk, and
    symlinks inside `root` are followed. That is deliberate: a bazel runfiles
    tree, a Kubernetes ConfigMap mount, and a Nix store are all symlink farms,
    so resolving links would reject every prompt in a normal deployment. It
    still blocks what an attacker actually supplies -- the name. Planting a
    symlink in your prompt directory needs write access to the deployment,
    which is a game already lost.

    Args:
        name: Path relative to `root`. An absolute path is refused outright --
            confinement means the caller, not the name, chooses the directory.
        root: Directory the name must stay within.

    Returns:
        The confined path, `..` collapsed, symlinks left intact.

    Raises:
        PromptPathError: The name is absolute, or escapes `root`.
    """
    candidate = Path(name)
    if candidate.is_absolute():
        msg = f"prompt path must be relative to {root}, got absolute {name!r}"
        raise PromptPathError(msg)

    root_path = Path(os.path.normpath(root))
    resolved = Path(os.path.normpath(root_path / candidate))
    if not resolved.is_relative_to(root_path):
        msg = f"prompt path {name!r} resolves outside {root_path}"
        raise PromptPathError(msg)

    return resolved


def read_template(
    path: str | Path,
    *,
    root: str | Path | None = None,
    encoding: str = "utf-8",
) -> str:
    """Read a template file, dropping the surrounding whitespace.

    The trailing newline every editor appends is not part of the prompt, and
    leaving it in shows up as a stray blank line in the rendered message.

    Args:
        path: Template file. Relative to `root` when one is given.
        root: Confine `path` to this directory -- see `resolve_prompt_path`.
        encoding: Text encoding of the file.

    Returns:
        The file's contents, stripped.

    Raises:
        PromptPathError: `root` was given and `path` escapes it.
    """
    resolved = Path(path) if root is None else resolve_prompt_path(path, root=root)
    return resolved.read_text(encoding=encoding).strip()


def load_prompt(
    path: str | Path,
    *,
    root: str | Path | None = None,
    partial_variables: Mapping[str, Any] | None = None,
    template_format: PromptTemplateFormat = DEFAULT_TEMPLATE_FORMAT,
    encoding: str = "utf-8",
) -> PromptTemplate:
    """Build a `PromptTemplate` from a template file.

    Args:
        path: Template file, conventionally `*.jinja`. Relative to `root` when
            one is given.
        root: Confine `path` to this directory -- see `resolve_prompt_path`.
            Pass it whenever `path` is not a literal in your source.
        partial_variables: Values bound now rather than at call time -- the
            usual home for a parser's `format_instructions`.
        template_format: Defaults to jinja2; pass "f-string" or "mustache" for
            a file written in one of those dialects.
        encoding: Text encoding of the file.

    Returns:
        A template whose input variables were derived from the file.

    Raises:
        PromptPathError: `root` was given and `path` escapes it.
    """
    return PromptTemplate.from_template(
        read_template(path, root=root, encoding=encoding),
        template_format=template_format,
        partial_variables=dict(partial_variables or {}),
    )


def load_chat_prompt(
    messages: Sequence[tuple[MessageRole, str | Path]],
    *,
    root: str | Path | None = None,
    partial_variables: Mapping[str, Any] | None = None,
    template_format: PromptTemplateFormat = DEFAULT_TEMPLATE_FORMAT,
    encoding: str = "utf-8",
) -> ChatPromptTemplate:
    """Build a `ChatPromptTemplate` from one template file per message.

    Args:
        messages: `(role, path)` pairs in the order they should be sent, e.g.
            `[("system", "role.jinja"), ("human", "question.jinja")]`. Each
            path is relative to `root` when one is given.
        root: Confine every path to this directory -- see
            `resolve_prompt_path`. It applies to each message, so one escaping
            path fails the whole prompt.
        partial_variables: Values bound now rather than at call time. Applied
            across the whole prompt, whichever message uses them.
        template_format: Defaults to jinja2, as in `load_prompt`.
        encoding: Text encoding of the files.

    Returns:
        A chat template whose input variables were derived from every file.

    Raises:
        PromptPathError: `root` was given and a path escapes it.
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (role, read_template(path, root=root, encoding=encoding))
            for role, path in messages
        ],
        template_format=template_format,
    )
    if partial_variables:
        return prompt.partial(**partial_variables)

    return prompt

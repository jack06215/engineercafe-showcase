"""Shell completion hints for what argparse can't say about an argument.

argparse records an argument's `choices` and `type`, which is enough to
complete a choice list or a `type=Path` file. It has no way to say that a
`type=str` is a directory, that `--profile` names an AWS profile, or that a
positional is free text rather than a file. A tool says so here, on the action
it just added, so the hint sits next to the flag and moves with it:

    folder = parser.add_argument("--folder_path", type=str, help="...")
    complete(folder, "directories")

packages/carapace reads the hint back when it writes the carapace specs that
complete `pycli` and its wrappers in dotfiles. The hint is a plain attribute on
the action, so parsing, `--help` and `python -m` runs of the tool are unchanged.
"""

import argparse
from typing import Literal

# files        a path to a file (or directory)
# directories  a path to a directory
# aws-profiles a profile from the AWS CLI config
# none         free text: complete nothing, where a positional would otherwise
#              complete files
type Hint = Literal["files", "directories", "aws-profiles", "none"]

_ATTR = "completion_hint"


def complete(action: argparse.Action, hint: Hint) -> None:
    """Record what values `action` takes, for shell completion."""
    setattr(action, _ATTR, hint)


def hint_of(action: argparse.Action) -> Hint | None:
    """The hint `complete()` recorded on `action`, if any."""
    hint: Hint | None = getattr(action, _ATTR, None)
    return hint

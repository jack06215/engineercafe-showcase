#!/usr/bin/env bash
set -euo pipefail

ruff="$(pwd)/$1"
shift
mypy="$(pwd)/$1"
shift
# The test runs in the runfiles tree, so ruff and mypy cannot find
# pyproject.toml by searching parent directories. Without an explicit path,
# both tools run with their defaults and ignore the repo settings.
config="$1"
shift

status=0
"${ruff}" check --config "${config}" "$@" || status=$?
"${mypy}" --config-file "${config}" --ignore-missing-imports \
  --explicit-package-bases "$@" || status=$?
exit "${status}"

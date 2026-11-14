#!/usr/bin/env bash
# Usage: lint_config_test.sh LINT_SH RUFF MYPY PYPROJECT UNDOCUMENTED_PY
#
# ruff's default rules do not include the pydocstyle (D) rules, and only
# pyproject.toml turns them on. Thus D103 in the output proves that lint.sh
# applied pyproject.toml.
set -euo pipefail

lint="$1"
shift

if output="$(bash "${lint}" "$@" 2>&1)"; then
  echo "error: lint.sh passed, but its input has a function without a docstring" >&2
  exit 1
fi
if ! grep -q "D103" <<<"${output}"; then
  echo "error: lint.sh did not report D103, so it did not apply pyproject.toml:" >&2
  echo "${output}" >&2
  exit 1
fi

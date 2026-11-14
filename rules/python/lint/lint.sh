#!/usr/bin/env bash
set -euo pipefail

ruff="$(pwd)/$1"
shift
mypy="$(pwd)/$1"
shift

status=0
"${ruff}" check "$@" || status=$?
"${mypy}" --ignore-missing-imports --explicit-package-bases "$@" || status=$?
exit "${status}"

#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BUILD_WORKSPACE_DIRECTORY:-}" ]]; then
  echo "error: run this target with 'bazel run', not 'bazel build/test'" >&2
  exit 1
fi

bazel_bin="$(command -v bazelisk || command -v bazel)"
cd "${BUILD_WORKSPACE_DIRECTORY}"

targets="$("${bazel_bin}" query 'attr(name, "\.lint$", //packages/...)' 2> /dev/null)"
if [[ -z "${targets}" ]]; then
  echo "no .lint targets found under //packages/..."
  exit 0
fi

# Target labels never contain whitespace, so word-splitting here is safe.
# shellcheck disable=SC2086
exec "${bazel_bin}" test ${targets}

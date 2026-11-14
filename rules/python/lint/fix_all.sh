#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BUILD_WORKSPACE_DIRECTORY:-}" ]]; then
  echo "error: run this target with 'bazel run', not 'bazel build/test'" >&2
  exit 1
fi

bazel_bin="$(command -v bazelisk || command -v bazel)"
cd "${BUILD_WORKSPACE_DIRECTORY}"

targets="$("${bazel_bin}" query 'attr(name, "\.fix$", //packages/...)' 2> /dev/null)"
if [[ -z "${targets}" ]]; then
  echo "no .fix targets found under //packages/..."
  exit 0
fi

status=0
for target in ${targets}; do
  echo "== ${target} =="
  "${bazel_bin}" run "${target}" || status=$?
done
exit "${status}"

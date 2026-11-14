#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BUILD_WORKSPACE_DIRECTORY:-}" ]]; then
  echo "error: run this target with 'bazel run', not 'bazel build'" >&2
  exit 1
fi

ruff="$(pwd)/$1"
shift
package="$1"
shift

files=()
for src in "$@"; do
  if [[ -z "${package}" ]]; then
    files+=("${src}")
  else
    files+=("${package}/${src}")
  fi
done

cd "${BUILD_WORKSPACE_DIRECTORY}"
"${ruff}" check --fix "${files[@]}"
"${ruff}" format "${files[@]}"

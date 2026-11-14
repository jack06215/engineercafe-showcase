#!/usr/bin/env bash
# Runs `markdownlint --fix` over a markdown_docs target's srcs, editing the
# files in the actual workspace (not the sandboxed runfiles copies). Must be
# invoked via `bazel run`, which sets BUILD_WORKSPACE_DIRECTORY.
# Invoked as: fix.sh <config> <package> <src>...
set -euo pipefail

if [[ -z "${BUILD_WORKSPACE_DIRECTORY:-}" ]]; then
  echo "error: run this target with 'bazel run', not 'bazel build'" >&2
  exit 1
fi

find_tool() {
  local name="$1"
  if command -v "${name}" >/dev/null 2>&1; then
    command -v "${name}"
    return
  fi
  for prefix in /opt/homebrew /usr/local; do
    if [[ -x "${prefix}/bin/${name}" ]]; then
      echo "${prefix}/bin/${name}"
      return
    fi
  done
  echo "error: ${name} not found on PATH or common Homebrew locations (try: brew install markdownlint-cli)" >&2
  exit 1
}

markdownlint="$(find_tool markdownlint)"
config="$1"
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

# Same config the `.lint` test uses -- workspace-relative, and we're now at the
# workspace root -- so fixing and checking can't disagree about the rules.
# `markdownlint --fix` exits non-zero when violations it can't fix remain; let
# that status through so the run reports them instead of silently passing.
"${markdownlint}" --fix --config "${config}" "${files[@]}"

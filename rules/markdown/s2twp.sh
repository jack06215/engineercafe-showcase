#!/usr/bin/env bash
# Rewrites a markdown_docs target's srcs from Simplified Chinese to Taiwanese
# Mandarin with `opencc -c s2twp.json`, editing the files in the actual
# workspace (not the sandboxed runfiles copies). Must be invoked via
# `bazel run`, which sets BUILD_WORKSPACE_DIRECTORY.
# Invoked as: s2twp.sh <package> <src>...
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
  echo "error: ${name} not found on PATH or common Homebrew locations (try: brew install opencc)" >&2
  exit 1
}

opencc="$(find_tool opencc)"
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

# opencc converts one file per invocation, and only overwrites the input when
# -i and -o name the same file *and* --in-place is passed.
for file in "${files[@]}"; do
  "${opencc}" --in-place -c s2twp.json -i "${file}" -o "${file}"
done

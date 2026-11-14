#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BUILD_WORKSPACE_DIRECTORY:-}" ]]; then
  echo "error: run this target with 'bazel run', not 'bazel build'" >&2
  exit 1
fi

md2docx="$1"
package="$2"
shift 2

files=()
for src in "$@"; do
  if [[ -z "${package}" ]]; then
    files+=("${src}")
  else
    files+=("${package}/${src}")
  fi
done

"${md2docx}" --output_dir build/docx --enable-mermaid "${files[@]}"

#!/usr/bin/env bash
# Runs markdownlint over a markdown_docs target's srcs, read-only. Wraps
# whatever markdownlint is found on PATH (or a common Homebrew install) -- not
# hermetic, requires it installed locally.
# Invoked as: lint.sh <config> <package> <src>...
set -euo pipefail

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
# Workspace-relative, and the runfiles root mirrors the workspace, so the same
# path works here and in fix.sh. Passed explicitly: relying on markdownlint's
# own lookup would silently fall back to defaults if the file ever stopped being
# declared as `data`.
config="$1"
shift
package="$1"
shift

# A test's working directory is the runfiles root, so the same
# `<package>/<src>` paths the workspace uses address the runfiles copies too.
# (Paths are rebuilt here rather than passed as `$(rootpath ...)`: Bazel
# re-tokenizes location expansions, which splits any path containing a space.)
files=()
for src in "$@"; do
  if [[ -z "${package}" ]]; then
    files+=("${src}")
  else
    files+=("${package}/${src}")
  fi
done

# markdownlint ignores paths that don't exist, so a mis-plumbed path would make
# this test pass while checking nothing. Fail loudly instead.
missing=()
for file in "${config}" "${files[@]}"; do
  [[ -f "${file}" ]] || missing+=("${file}")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "error: srcs missing from runfiles: ${missing[*]}" >&2
  exit 1
fi

# Violations are reported against the runfiles copies; run the matching `.fix`
# target to correct the real files.
"${markdownlint}" --config "${config}" "${files[@]}"

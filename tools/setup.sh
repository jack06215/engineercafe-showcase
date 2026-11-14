#!/usr/bin/env bash
# Gets a checkout ready to build: checks the tools that README.md lists,
# installs the web UI's packages and builds everything with Bazel.
# Runs on the bash 3.2 that macOS ships, so it avoids newer bash features.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: tools/setup.sh [options]

Checks the tools this repo needs, installs the web UI's packages and builds
everything with Bazel. Without --install it changes nothing outside the repo.

  --check     Only report the tools. Change nothing.
  --install   Install missing tools: bazelisk, markdownlint-cli and uv with
              Homebrew, Node with asdf, and a pnpm command with corepack.
  --test      Run all tests at the end: bazel test //... and the web UI's
              build, tests, type check and lint.
  --no-web    Skip the web UI (src/main/typescript).
  -h, --help  Show this help.
EOF
}

check_only=false
install=false
run_tests=false
web=true
for arg in "$@"; do
  case "$arg" in
    --check) check_only=true ;;
    --install) install=true ;;
    --test) run_tests=true ;;
    --no-web) web=false ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done
if $check_only && $install; then
  echo "error: --check and --install cannot be used together" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

ts_dir=src/main/typescript
node_version="$(awk '$1 == "nodejs" { print $2 }' .tool-versions)"
uv_min="$(sed -n 's/^required-version = ">=\(.*\)"$/\1/p' pyproject.toml)"

# Plain strings, not arrays: bash 3.2 with `set -u` fails on an empty array.
missing=""
warnings=""

have() { command -v "$1" >/dev/null 2>&1; }
ok() { printf '  %-8s %-13s %s\n' ok "$1" "$2"; }
absent() { printf '  %-8s %-13s %s\n' missing "$1" "$2"; }
note() { printf '  %-8s %-13s %s\n' - "$1" "$2"; }

# The same lookup as rules/markdown/*.sh, so the result matches what the
# markdown tests find.
find_tool() {
  local prefix
  if have "$1"; then
    command -v "$1"
    return 0
  fi
  for prefix in /opt/homebrew /usr/local; do
    if [[ -x "$prefix/bin/$1" ]]; then
      echo "$prefix/bin/$1"
      return 0
    fi
  done
  return 1
}

version_at_least() {
  local have_parts min_parts i
  IFS=. read -ra have_parts <<<"$1"
  IFS=. read -ra min_parts <<<"$2"
  for ((i = 0; i < ${#min_parts[@]}; i++)); do
    if ((${have_parts[i]:-0} > min_parts[i])); then return 0; fi
    if ((${have_parts[i]:-0} < min_parts[i])); then return 1; fi
  done
  return 0
}

brew_install() {
  if ! have brew; then
    echo "error: --install uses Homebrew (https://brew.sh) to install $1" >&2
    exit 1
  fi
  brew install "$1"
}

# Prefers asdf's install of the pinned version, because another Node (for
# example Homebrew's) can come first on PATH.
node_bin=""
find_node() {
  if have asdf && asdf where nodejs "$node_version" >/dev/null 2>&1; then
    node_bin="$(asdf where nodejs "$node_version")/bin"
  elif have node && [[ "$(node --version)" == "v$node_version" ]]; then
    node_bin="$(dirname "$(command -v node)")"
  fi
  [[ -n "$node_bin" ]]
}

echo "Tools"

platform="$(uname -s)-$(uname -m)"
case "$platform" in
  Darwin-arm64 | Darwin-x86_64 | Linux-x86_64 | Linux-aarch64) ok platform "$platform" ;;
  *)
    absent platform "$platform: MODULE.bazel pins Python for macOS and Linux on x86_64 and arm64 only"
    missing="$missing platform"
    ;;
esac

if bazel_path="$(find_tool bazel || find_tool bazelisk)"; then
  ok bazel "$bazel_path"
elif $install; then
  brew_install bazelisk
  ok bazel "$(command -v bazel)"
else
  absent bazel "brew install bazelisk"
  missing="$missing bazel"
fi

if markdownlint_path="$(find_tool markdownlint)"; then
  ok markdownlint "$markdownlint_path"
elif $install; then
  brew_install markdownlint-cli
  ok markdownlint "$(find_tool markdownlint)"
else
  absent markdownlint "brew install markdownlint-cli (the markdown lint tests need it)"
  warnings="$warnings markdownlint"
fi

if have uv && version_at_least "$(uv --version | awk '{ print $2 }')" "$uv_min"; then
  ok uv "$(uv --version | awk '{ print $2 }')"
elif $install; then
  if have uv; then brew upgrade uv; else brew_install uv; fi
  ok uv "$(uv --version | awk '{ print $2 }')"
else
  absent uv "uv >= $uv_min: brew install uv (only to change Python dependencies)"
  warnings="$warnings uv"
fi

if $web; then
  if find_node; then
    ok node "v$node_version in $node_bin"
  elif $install; then
    if ! have asdf; then brew_install asdf; fi
    if ! asdf plugin list 2>/dev/null | grep -qx nodejs; then
      asdf plugin add nodejs
    fi
    asdf install nodejs "$node_version"
    find_node
    ok node "v$node_version in $node_bin"
  else
    absent node "Node $node_version: asdf install nodejs $node_version"
    missing="$missing node"
  fi

  # The script itself runs pnpm through corepack. A `pnpm` command matters
  # for people, because Turborepo needs one on PATH to run package scripts.
  if [[ -n "$node_bin" ]]; then
    if [[ -x "$node_bin/pnpm" ]]; then
      ok pnpm "$node_bin/pnpm"
    elif $install; then
      "$node_bin/corepack" enable pnpm
      if have asdf; then asdf reshim nodejs "$node_version"; fi
      ok pnpm "$node_bin/pnpm"
    else
      absent pnpm "corepack enable pnpm (with Node $node_version)"
      warnings="$warnings pnpm"
    fi
  fi
fi

echo
echo "Optional"
for tool in opencc mmdc ollama; do
  case "$tool" in
    opencc) purpose="the .s2twp targets of rules/markdown" ;;
    mmdc) purpose="mermaid diagrams in the .docx targets" ;;
    ollama) purpose="vega_lite_chat (and its model, see its config.yaml)" ;;
  esac
  if path="$(find_tool "$tool")"; then ok "$tool" "$path"; else note "$tool" "for $purpose"; fi
done
note credentials "vega_lite_ai needs Anthropic credentials, for example ANTHROPIC_API_KEY"

if $check_only; then
  if [[ -n "$missing" ]]; then exit 1; fi
  exit 0
fi
if [[ -n "$missing" ]]; then
  echo
  echo "error: missing:$missing. Install them, or rerun with --install." >&2
  exit 1
fi

# corepack asks before it downloads the pnpm version that package.json names.
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
pnpm_cmd() { (cd "$ts_dir" && PATH="$node_bin:$PATH" "$node_bin/corepack" pnpm "$@"); }

if $web; then
  echo
  echo "Installing the web UI's packages ($ts_dir)"
  pnpm_cmd install
fi

echo
echo "Building everything with Bazel. The first build downloads Python and the"
echo "packages in uv.lock."
bazel build //...

if $run_tests; then
  echo
  echo "Running the Bazel tests"
  bazel test //...
  if $web; then
    for task in build test type:check lint; do
      echo
      echo "Running the web UI's $task"
      pnpm_cmd -r --if-present run "$task"
    done
  fi
fi

echo
echo "Done. README.md lists the commands that run each project."
if [[ -n "$warnings" ]]; then
  echo "Still missing:$warnings (see above)."
fi

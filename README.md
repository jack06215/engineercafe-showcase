# engineercafe-showcase

Projects built at [Engineer Cafe](https://engineercafe.jp/).

| Project | What it is | Stack |
| --- | --- | --- |
| [`vega_lite_ai`](packages/vega_lite_ai) | An agent that finds Fukuoka City open data and charts it, with a web page to start runs and watch them | Claude Agent SDK, Streamlit, Vega-Lite |
| [`vega_lite_chat`](packages/vega_lite_chat) | Upload a CSV and ask for charts in Japanese chat ([design](packages/vega_lite_chat/DESIGN.md)) | Streamlit, LangGraph, Ollama, Vega-Lite |
| [`fukuoka_tenki_forcast`](packages/fukuoka_tenki_forcast) | Fukuoka City forecast, 7-day outlook and rain radar in the terminal, from JMA data ([design](packages/fukuoka_tenki_forcast/DESIGN.md)) | Textual, Rich, Pillow |
| [`hello_world_20260912`](packages/hello_world_20260912) | Static Hello World pages | HTML |
| [`algo_tutor`](packages/algo_tutor) | A local tracker for coding-interview practice, with an optional AI tutor ([spec](packages/algo_tutor/SPEC.md)) | FastAPI, SQLAlchemy, SQLite, LangChain |
| [`algo-tutor-web`](src/main/typescript/packages/algo-tutor-web) | The web UI of `algo_tutor` | React 19, MUI, TanStack Router and Query, Vite |

`packages/langchain_util` and `packages/common` are shared libraries that
`vega_lite_chat` and `algo_tutor` depend on.
[`packages/vega_lite_core`](packages/vega_lite_core) is the shared chart
library of `vega_lite_chat` and `vega_lite_ai`: the chart format, its checks,
and the compiler to Vega-Lite.

The Python packages build with Bazel. `src/main/typescript` is a separate pnpm
and Turborepo workspace that Bazel ignores; see its
[README](src/main/typescript/README.md).

## System requirements

macOS or Linux, on x86_64 or arm64. `MODULE.bazel` pins a Python build for
those four platforms only. Windows is not supported.

| Tool | Needed for | Install |
| --- | --- | --- |
| [Bazelisk](https://github.com/bazelbuild/bazelisk) | Building and testing the Python packages. It runs the Bazel version in `.bazelversion`, and Bazel downloads Python 3.14.6 and the packages in `uv.lock` itself. | `brew install bazelisk` |
| `markdownlint` | The markdown `.lint` tests, which run the copy on your `PATH` | `brew install markdownlint-cli` |
| [uv](https://docs.astral.sh/uv/) 0.13.6 or later | Changing Python dependencies, or a local `.venv` for your editor | `brew install uv` |
| Node 24.22.1 | The web UI | `asdf install nodejs 24.22.1` |
| pnpm 11.22.0 | The web UI. Corepack, which comes with Node 24, runs the version that `package.json` names. | `corepack enable pnpm` |

Optional:

| Tool | Needed for |
| --- | --- |
| `opencc` | The `.s2twp` targets of `rules/markdown` |
| `mmdc` | Mermaid diagrams in the `.docx` targets of `rules/markdown` |
| [Ollama](https://ollama.com) | `vega_lite_chat`, with the model in its `config.yaml` |
| Anthropic credentials, for example `ANTHROPIC_API_KEY` | `vega_lite_ai` |

## Setup

```sh
git clone https://github.com/jack06215/engineercafe-showcase.git
cd engineercafe-showcase
tools/setup.sh
```

`tools/setup.sh` does these steps:

1. It checks the tools above and prints the install command for each missing
   one. It stops if Bazel or Node is missing.
2. It installs the web UI's packages with `pnpm install` in
   `src/main/typescript`.
3. It runs `bazel build //...`. The first build downloads Python and the
   packages in `uv.lock`, so it takes some minutes.

Options:

| Option | Does |
| --- | --- |
| `--install` | Also installs missing tools: Bazelisk, markdownlint and uv with Homebrew, Node with asdf, and a `pnpm` command with corepack |
| `--test` | Also runs `bazel test //...` and the web UI's build, tests, type check and lint |
| `--check` | Only reports the tools and changes nothing |
| `--no-web` | Skips the web UI |

Without `--install`, the script changes nothing outside the repo and the
Bazel and pnpm caches.

## Run

```sh
# Claude workshop: the web page (needs Anthropic credentials, for example ANTHROPIC_API_KEY)
bazel run //packages/vega_lite_ai:chart_app
# Claude workshop: one agent run from the terminal
bazel run //packages/vega_lite_ai:chart_agent -- 人口の推移

# vega_lite_chat (needs `ollama serve` and the model in its config.yaml)
bazel run //packages/vega_lite_chat:vega_lite_chat

# Fukuoka weather in the terminal
bazel run //packages/fukuoka_tenki_forcast:fukuoka_tenki

# algo_tutor: the API on 127.0.0.1:4317, and its command line (see its README)
bazel run //packages/algo_tutor:serve
bazel run //packages/algo_tutor:cli -- --help
# algo-tutor-web: the UI on http://127.0.0.1:5173, with the API above running
pnpm --dir src/main/typescript turbo run dev --filter algo-tutor-web
```

## Test and lint

```sh
bazel test //...
# The web UI: build, unit tests, type check, lint
cd src/main/typescript && pnpm build && pnpm test && pnpm type:check && pnpm lint
```

Every `py_library` and `py_binary` also has a `<name>.lint` test (ruff and
mypy) and a `<name>.fix` target that rewrites the files in place. Every
package with `.md` files has `docs.lint` and `docs.fix` (markdownlint, with
the rules in `.markdownlint.jsonc`):

```sh
bazel run //packages/vega_lite_core:vega_lite_core.fix
bazel run //packages/algo_tutor:docs.fix
bazel run //:buildifier.fix
```

CI ([`.github/workflows/bazel.yml`](.github/workflows/bazel.yml)) runs
`bazel run //:buildifier.check` and `bazel test //...` on each pull request
and each push to `main`. It uses the `ci` config in `.bazelrc`, so add
`--config=ci` to run the same checks locally.

## Dependencies

Edit `pyproject.toml`, then run `uv lock`. Bazel reads `uv.lock` directly.

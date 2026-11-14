# engineercafe-showcase

Projects built at [Engineer Cafe](https://engineercafe.jp/).

| Project | What it is | Stack |
| --- | --- | --- |
| [`vega_lite_ai`](packages/vega_lite_ai) | An agent that finds Fukuoka City open data and charts it, with a web page to start runs and watch them | Claude Agent SDK, Streamlit, Vega-Lite |
| [`vibe_coding_club/vega_lite_chat`](packages/vibe_coding_club/vega_lite_chat) | Upload a CSV and ask for charts in Japanese chat ([design](packages/vibe_coding_club/vega_lite_chat/DESIGN.md)) | Streamlit, LangGraph, Ollama, Vega-Lite |
| [`vibe_coding_club/fukuoka_tenki_forcast`](packages/vibe_coding_club/fukuoka_tenki_forcast) | Fukuoka City forecast, 7-day outlook and rain radar in the terminal, from JMA data ([design](packages/vibe_coding_club/fukuoka_tenki_forcast/DESIGN.md)) | Textual, Rich, Pillow |
| [`vibe_coding_club/hello_world_20260912`](packages/vibe_coding_club/hello_world_20260912) | Static Hello World pages | HTML |
| [`algo_tutor`](packages/algo_tutor) | A local tracker for coding-interview practice, with an optional AI tutor ([spec](packages/algo_tutor/SPEC.md)) | FastAPI, SQLAlchemy, SQLite, LangChain |
| [`algo-tutor-web`](src/main/typescript/packages/algo-tutor-web) | The web UI of `algo_tutor` | React 19, MUI, TanStack Router and Query, Vite |

`packages/langchain_util`, `packages/common` and `packages/cli_complete.py` are
shared libraries that `vega_lite_chat` and `algo_tutor` depend on.

The Python packages build with Bazel. `src/main/typescript` is a separate pnpm
and Turborepo workspace that Bazel ignores; see its
[README](src/main/typescript/README.md).

## Setup

- [Bazelisk](https://github.com/bazelbuild/bazelisk). It reads the Bazel
  version from `.bazelversion`.
- Bazel downloads Python 3.14.6 and the packages in `uv.lock` itself. Run
  `uv sync` only if your editor needs a local `.venv`.
- `markdownlint` (`brew install markdownlint-cli`). The markdown `.lint`
  tests run the copy on your `PATH`, not one that Bazel downloads.
- For the web UI only: Node 24.22.1 (`asdf install` reads `.tool-versions`),
  then `corepack enable pnpm` and `pnpm install` in `src/main/typescript`.

## Run

```sh
# Claude workshop: the web page (needs Anthropic credentials, for example ANTHROPIC_API_KEY)
bazel run //packages/vega_lite_ai:chart_app
# Claude workshop: one agent run from the terminal
bazel run //packages/vega_lite_ai:chart_agent -- 人口の推移

# vega_lite_chat (needs `ollama serve` and the model in its config.yaml)
bazel run //packages/vibe_coding_club/vega_lite_chat:vega_lite_chat

# Fukuoka weather in the terminal
bazel run //packages/vibe_coding_club/fukuoka_tenki_forcast:fukuoka_tenki

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
bazel run //packages/vibe_coding_club/vega_lite_chat:chart_core.fix
bazel run //packages/algo_tutor:docs.fix
bazel run //:buildifier.fix
```

## Dependencies

Edit `pyproject.toml`, then run `uv lock`. Bazel reads `uv.lock` directly.

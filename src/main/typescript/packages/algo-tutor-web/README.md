# algo-tutor-web

The web UI of [algo_tutor](../../../../../packages/algo_tutor/SPEC.md), made
from [react-vite-starter](https://github.com/jack06215/react-vite-starter) with
`turbo gen workspace --copy`. React 19, MUI (light/dark), TanStack Router and
Query, Zustand, CodeMirror 6, Vega-Lite; Vitest, Storybook.

## Running it

The PoC runs as two processes (SPEC §3.1):

```sh
bazel run //packages/algo_tutor:serve   # the API on 127.0.0.1:4317
pnpm dev                                # this UI on http://127.0.0.1:5173
```

Vite forwards `/api` to the API, rewriting `Host` to the API's own (its
local-only guard accepts nothing else) and keeping the `Origin`.

## Commands

| Command              | Does                                                                   |
| -------------------- | ---------------------------------------------------------------------- |
| `pnpm dev`           | dev server on <http://127.0.0.1:5173>, `/api` → `127.0.0.1:4317`       |
| `pnpm build`         | `vite build` into `dist/` (regenerating the route tree), then `tsc -b` |
| `pnpm test`          | Vitest, once; `pnpm test:watch` keeps it running                       |
| `pnpm type:check`    | `tsc -b` over the app, `.storybook/` and the config files              |
| `pnpm lint`          | ESLint and `prettier --check`; changes nothing                         |
| `pnpm format`        | `eslint --fix` and `prettier --write`                                  |
| `pnpm storybook:dev` | Storybook on <http://localhost:6008>                                   |
| `pnpm api:types`     | TypeScript types from `src/api/schema.json` (the API's contract)       |

## Layout

```text
src/
  api/          client.ts: fetch wrapper, ApiError, idempotency keys
  common/       providers, router, theme, mm:ss helpers, test utils
  components/   shared: charts (VegaLiteChart, LevelChart), editor (CodeEditor),
                layout (AppShell, ThemeModeSwitch), ui (ApiUnavailable, PagePlaceholder)
  features/
    attempt/    VersionedLane, useAutosave, useStopwatch; SaveStatus, StaleNotice, Stopwatch
    setup/      SetupGate
  hooks/        useBeforeUnloadGuard, useEasyQuery, useMount
  pages/        one component per screen (SPEC §14)
  routes/       file routes: `_shell` (the sidebar) around every page but /attempts/$id
```

Writes to a versioned record (an attempt's drafts, heartbeats, pause/resume)
all go through one `VersionedLane`, so they never race and always carry the
latest version; the first failure (409 `STALE` included) freezes it until
retry or "Reload saved version".

# TypeScript workspace

A pnpm workspace for the TypeScript packages in `packages/`, with tasks run
and cached by [Turborepo](https://turborepo.com).

- `packages/algo-tutor-web/`: the web UI of
  [algo_tutor](../../../packages/algo_tutor/README.md), on
  <http://127.0.0.1:5173>. Its dev server forwards `/api` to the API on
  `127.0.0.1:4317`. The package README describes it.

The workspace is not built by Bazel. `.bazelignore` lists `src/main/typescript`,
so `bazel test //...` does not see this tree or its `node_modules/`. Turborepo
builds and tests it.

## Setup

1. Node: `asdf install` picks up 24.22.1 from the repo's `.tool-versions`.
2. pnpm: `corepack enable pnpm`. Corepack then runs the version that
   `packageManager` names, 11.22.0. Turborepo needs a `pnpm` command on your
   `PATH` to run the package scripts, so `corepack pnpm` alone is not enough.
3. `pnpm install` from this directory.

Each package sees only the dependencies its own `package.json` lists: pnpm
links them into the package's `node_modules/` rather than hoisting everything
to this directory.

## Everyday commands

From this directory:

| Command | Does |
| --- | --- |
| `pnpm build` | `turbo run build`: each package into its `dist/` (`vite build && tsc -b`) |
| `pnpm test` | `turbo run test`: unit tests (Vitest) |
| `pnpm type:check` | `turbo run type:check`: `tsc -b` |
| `pnpm lint` | `turbo run lint`: ESLint and `prettier --check`, never cached |
| `pnpm turbo run dev --filter algo-tutor-web` | the Vite dev server on <http://127.0.0.1:5173> |
| `pnpm --filter <package> <script>` | any other package script, e.g. `storybook:dev`, `format`, `api:types` |
| `pnpm --filter <package> add <pkg>` | a new dependency for that package |

A second `pnpm build` or `pnpm test` with nothing changed replays from
`.turbo/` ("FULL TURBO"). Tasks are defined in `turbo.json`.

`minimumReleaseAge` in `pnpm-workspace.yaml` makes pnpm skip any version
published less than ten days ago, when adding or re-resolving.

Turborepo collects anonymous telemetry unless turned off:
`pnpm turbo telemetry disable`.

## algo_tutor and this UI

The Python side expects the UI at this path:

- `packages/algo_tutor/api/app.py` serves
  `src/main/typescript/packages/algo-tutor-web/dist/`, the output of
  `pnpm build`.
- The API schema comes from the Python models. From the repo root, write it
  and then make the TypeScript types from it:

  ```sh
  bazel run //packages/algo_tutor/api:export_schema -- \
      src/main/typescript/packages/algo-tutor-web/src/api/schema.json
  pnpm --dir src/main/typescript --filter algo-tutor-web api:types
  ```

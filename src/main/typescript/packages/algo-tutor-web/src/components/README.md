# src/components

Components used across the app. Each lives in its own folder with its story,
its test and an `index.ts` that re-exports it, and is imported through the
folder (`@/components/charts/LevelChart`):

- `charts/` data visualization: `VegaLiteChart`, `LevelChart`
- `editor/` `CodeEditor` (CodeMirror 6: Python, Go, TypeScript)
- `layout/` page structure: `AppShell`, `ThemeModeSwitch`
- `ui/` presentational building blocks: `ApiUnavailable`, `PagePlaceholder`
- `utils/` non-visual helpers: `development-tools/`

Components that only one feature uses belong in that feature's
`components/` instead (`src/features/<name>/components/`).

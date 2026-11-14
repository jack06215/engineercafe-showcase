# src/common

Code the whole app shares that isn't a component or a hook (what other
projects call `lib/`):

- `providers.tsx`: `AppProviders`, the MUI/Emotion theme (system, light or
  dark, remembered per browser), the baseline styles and the TanStack Query
  cache, above the router.
- `router.tsx`: `createAppRouter()` over the generated route tree, and the
  `Register` declaration that types `Link`/`useNavigate`/`useSearch`.
- `theme.ts`: the MUI theme, with light and dark color schemes.
- `time.ts`: the `mm:ss` format the stopwatch shows and the result form takes.
- `test-utils.tsx`: `routeRender(path)`, `themeRender(ui)` and
  `stubApi(responses)` for tests.

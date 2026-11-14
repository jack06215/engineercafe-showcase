# src/features

One folder per feature, laid out like `src/` with only the folders it needs:

- `src/features/<feature>/`
  - `assets/` data files and images only this feature uses
  - `common/` its parsing, models and API calls
  - `components/` its components (folder per component, as in
    `src/components/`)
  - `hooks/`, `store/`

Pages in `src/pages/` compose features; features don't import each other's
internals.

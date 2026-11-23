# monkeytype_analysis_console

A local Streamlit app that shows Monkeytype results again. The Surfingkeys
`yr` mapping copies a result screen as YAML: the stats, the per-second chart
and the input history. The console reads those files and redraws the result.
It only reads; it never writes a file.

```sh
bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console
```

Load results from the sidebar: upload `.yml` files, or enter a folder that
holds them. To fill the folder box on start, set `MONKEYTYPE_RESULTS_DIR`:

```sh
MONKEYTYPE_RESULTS_DIR=~/monkeytype \
  bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console
```

[`SPEC.md`](SPEC.md) is the functional spec: the pages, the definitions
behind every number, and the plan. The Result replay page is built. Result
analysis and Progress come next.

| Module | Job |
| --- | --- |
| `results.py` | Reads `yr` files into `Result` objects, reports bad files, skips duplicates |
| `metrics.py` | The definitions of §5 of the spec, such as slow words and band labels |
| `charts.py` | The Altair speed chart and the per-word speed chart |
| `history_html.py` | The input history as escaped HTML, coloured by heatmap band |
| `palette.py` | The fixed colours, readable on light and dark backgrounds |
| `ui.py` | The sidebar and the pages; `main.py` and `app_pages/` only call it |

The page files are in `app_pages/`, not `pages/`: a folder named `pages/`
turns on Streamlit's older pages-folder mode, which breaks `st.navigation`.

`testdata/` holds one real result and small files written by hand in `yr`'s
layout; `fixtures.py` says what each one covers.

## Commands

```sh
bazel test //packages/monkeytype_analysis_console/...
bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console_lib.fix
bazel run //packages/monkeytype_analysis_console:docs.fix
```

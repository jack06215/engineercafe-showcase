# monkeytype_analysis_console

A local Streamlit app for Monkeytype results. The Surfingkeys `yr` mapping
copies a result screen as YAML: the stats, the per-second chart and the input
history. The console reads those files and has four pages: Result replay
redraws one result, Result analysis shows the numbers behind it, Progress
follows many results over time, and Practice asks Claude to group the words
you keep getting wrong by cause and to write a practice text for Monkeytype's
custom mode. It only reads; it never writes a file.

```sh
bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console
```

Load results from the sidebar: upload `.yml` files, or enter a folder that
holds them. To fill the folder box on start, set `MONKEYTYPE_RESULTS_DIR`:

```sh
MONKEYTYPE_RESULTS_DIR=~/monkeytype \
  bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console
```

The Practice page needs `ANTHROPIC_API_KEY`; without it, the page shows your
problems but no buttons. It is the only part of the console that sends data
off your machine, and only when you press one of its buttons: the words,
counts, typos and key confusions shown under "What Claude gets", never your
files. Its "Claude settings" section changes the model, the effort and the
timeout; the defaults are Claude Opus 5.5, effort high for cause groups and
medium for practice text, and 120 seconds. Keep the key in `.env`, which git
ignores, and load it before you start the console:

```sh
set -a && source .env && set +a
bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console
```

[`SPEC.md`](SPEC.md) is the functional spec: the pages, the definitions
behind every number, and the plan.

| Module | Job |
| --- | --- |
| `results.py` | Reads `yr` files into `Result` objects, reports bad files, skips duplicates |
| `metrics.py` | The definitions of §5 of the spec, such as slow words, aborted results and time lost to mistakes |
| `progress.py` | The definitions over many results: trends per word list and test type, recurring problems |
| `practice.py` | The Practice page's Claude requests, and the checks of Claude's answers |
| `typos.py` | The typo classifier and keyboard model, ported from the `monkeytype-review` skill's `analyze.py` |
| `charts.py` | The Altair charts: speed, per-word speed, keyboard and progress |
| `history_html.py` | The input history as escaped HTML, coloured by heatmap band |
| `palette.py` | The fixed colours, readable on light and dark backgrounds |
| `ui.py` | The sidebar and the pages; `main.py` and `app_pages/` only call it |

The page files are in `app_pages/`, not `pages/`: a folder named `pages/`
turns on Streamlit's older pages-folder mode, which breaks `st.navigation`.

`testdata/` holds one real result and small files written by hand in `yr`'s
layout; `fixtures.py` says what each one covers. `fixtures.py` also has a fake
Anthropic client, so no test calls the API.

## Commands

```sh
bazel test //packages/monkeytype_analysis_console/...
bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console_lib.fix
bazel run //packages/monkeytype_analysis_console:docs.fix
```

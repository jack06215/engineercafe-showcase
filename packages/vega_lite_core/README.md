# vega_lite_core

The chart format that a model writes, and the code that checks it and compiles
it to Vega-Lite. A model writes a `ChartSpec`, a small subset of Vega-Lite.
`check_chart` compares it with a profile of the table, and `compile_chart`
turns it into a Vega-Lite spec. `vega_lite_chat` and `vega_lite_ai` both use
this package.

| Module | Job | Main public names |
| --- | --- | --- |
| `chart_spec.py` | The types of a chart spec (pydantic) | `ChartSpec`, `Encoding`, `Filter`, `TopN`, `CHANNELS` |
| `checks.py` | Checks a chart spec against a profile. Returns English messages that say how to fix the chart. | `check_chart`, `empty_column_errors`, `parse_iso` |
| `compiler.py` | Compiles a chart spec to Vega-Lite, and checks the result against the Vega-Lite JSON schema | `compile_chart`, `vega_lite_errors`, `with_inline_data` |
| `csv_loader.py` | Reads UTF-8 CSV bytes into a DataFrame, and turns text dates into datetimes | `load_csv`, `InputError` |
| `profile.py` | Summarises a DataFrame for a model: column types, ranges and a few rows | `profile_frame`, `DataProfile`, `profile_yaml` |

```python
from packages.vega_lite_core.checks import check_chart
from packages.vega_lite_core.compiler import compile_chart, vega_lite_errors
from packages.vega_lite_core.csv_loader import load_csv
from packages.vega_lite_core.profile import profile_frame

df = load_csv(data)
profile = profile_frame(df, sample_rows=5, seed=0, max_listed_values=20)
errors = check_chart(spec, profile)
if not errors:
    vega_lite = compile_chart(spec, profile, height=400)
```

## Dependencies

This package must not import an app or a UI: no `packages.vega_lite_chat`,
`packages.vega_lite_ai`, `streamlit`, `langchain_core`, `langgraph`, `ollama`
or `claude_agent_sdk`. Its own dependencies are `altair` (only for the
Vega-Lite JSON schema it ships), `jsonschema`, `pandas`, `pydantic` and
`pyyaml`.

## Chart rules

The rules live in the design document of `vega_lite_chat`, which is in
Japanese:

- [§3 Data](../vega_lite_chat/DESIGN.md#3-データ): how a CSV is read, and what
  a profile holds.
- [§4 `ChartSpec`](../vega_lite_chat/DESIGN.md#4-chartspecchart_specpy): the
  fields, and why they come in this order.
- [§5 Checks](../vega_lite_chat/DESIGN.md#5-検査checkspy): each rule of
  `check_chart`.
- [§6 Compiling](../vega_lite_chat/DESIGN.md#6-vega-lite-への変換compilerpy):
  how each part of a chart spec becomes Vega-Lite.

`empty_column_errors` is not one of those rules, and `check_chart` does not
call it. It refuses a chart of a column with no values, which would draw
nothing. Only `vega_lite_ai` calls it now.

## Commands

```sh
bazel test //packages/vega_lite_core/...
bazel run //packages/vega_lite_core:vega_lite_core.fix
bazel run //packages/vega_lite_core:docs.fix
```

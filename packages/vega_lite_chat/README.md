# vega_lite_chat

Chat about a CSV file and get Vega-Lite charts from a local Ollama model. A
chat model answers in prose or calls a chart tool. The tool asks a translator
model for a small chart spec, then checks the spec against the data and sends
any errors back for repair before the chart is drawn.

```sh
# Needs `ollama serve` and the model named in config.yaml
bazel run //packages/vega_lite_chat:vega_lite_chat
# Run eval_cases.yaml against the real model
bazel run //packages/vega_lite_chat:live_eval
```

`DESIGN.md` (in Japanese) covers the scope, the layers, each module and the
data flow.

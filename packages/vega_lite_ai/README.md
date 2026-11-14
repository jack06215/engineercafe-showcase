# vega_lite_ai

A Claude Agent SDK project: an agent turns a question about Fukuoka City's open
data into one Vega-Lite chart that passed a check, and a Streamlit app starts
runs and shows what they made. The agent process and the app share only a run
folder (`runs.py`).

```sh
# The web app (needs Anthropic credentials, for example ANTHROPIC_API_KEY)
bazel run //packages/vega_lite_ai:chart_app
# One agent run from the terminal
bazel run //packages/vega_lite_ai:chart_agent -- 人口の推移
```

`sample_code.py` is the smallest Agent SDK example.

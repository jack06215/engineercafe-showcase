# langchain_util

A thin layer over LangChain for OpenAI, Azure OpenAI and Ollama: client
construction, `invoke_llm` with retries and prompt repair, prompts loaded from
`.jinja` files, response caching, token usage, and a generate, evaluate and
revise loop in `thinking.py`. `templates/thinking/` holds the prompts of that
loop.

`examples/` has one runnable script per feature.

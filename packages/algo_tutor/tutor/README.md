# algo_tutor/tutor

Algo-chan, the LLM tutor: attempt reports, interview hints and the connection
test. `llm.py` is the only module that calls a model, and `worker.py` runs the
report queue on a background thread. The tests use `fake_models.py`, so they
need no Ollama and no network.

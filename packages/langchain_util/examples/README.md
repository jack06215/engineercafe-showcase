# langchain_util/examples

One runnable script per `langchain_util` feature. Each script takes
`--provider` (`openai`, `azure` or `ollama`) and `--dry-run`, which uses a fake
model so that the script runs offline:

```sh
bazel run //packages/langchain_util/examples:string_output -- --dry-run recursion
```

`prompts/` holds the `.jinja` templates that the scripts load.

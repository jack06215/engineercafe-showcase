# md2docx

Converts GitHub-flavoured Markdown to a Word document that looks like a new
Google Doc. Mermaid diagrams are rendered to images with mermaid-cli (`mmdc`).
The `markdown_docs` macro in `rules/markdown` runs it for each `.docx` target:

```sh
bazel run //packages/algo_tutor:docs.docx
```

`testdata/gfm.md` is the Markdown input of the tests.

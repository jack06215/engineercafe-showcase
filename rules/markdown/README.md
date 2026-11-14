# Markdown rules

This package supplies the `markdown_docs` macro. The macro creates targets
that check, fix, convert and export a set of Markdown files.

## Use the macro

```starlark
load("//rules/markdown:defs.bzl", "markdown_docs")

markdown_docs(
    name = "docs",
    srcs = glob(["*.md"]),
)
```

| Argument | Default | Purpose |
| --- | --- | --- |
| `name` | none | The prefix of the targets that cover all `srcs`. |
| `srcs` | none | The Markdown files, as paths relative to the package. |
| `config` | `//:.markdownlint.jsonc` | The markdownlint config for `.lint` and `.fix`. |

If `srcs` is empty, the macro creates no targets.

## Targets

For `name = "docs"`, the macro creates these targets:

| Target | Kind | What it does |
| --- | --- | --- |
| `docs.lint` | `sh_test` | Runs markdownlint on all `srcs`. It does not change files. |
| `docs.fix` | `sh_binary` | Runs `markdownlint --fix` on all `srcs`. It changes the files in the workspace. |
| `docs.s2twp` | `sh_binary` | Changes Simplified Chinese to Traditional Chinese (Taiwan) with opencc. It changes the files in the workspace. |
| `docs.docx` | `sh_binary` | Writes a Word file for each source file. It does not change the source files. |

Each file in `srcs` also gets its own `.fix`, `.s2twp` and `.docx` targets.
The target name is the file path and the suffix, for example
`//packages/algo_tutor:SPEC.md.docx`. Use these targets to change or export
one file only. There is no `.lint` target for one file.

## Check and fix

```sh
# Check. This command does not change files.
bazel test //packages/algo_tutor:docs.lint

# Fix. This command changes the files in the workspace.
bazel run //packages/algo_tutor:docs.fix
```

The `.lint` test reports problems against the copies in its runfiles. Run the
matching `.fix` target to fix the files in the workspace.

`markdownlint --fix` cannot fix all problems, for example a line that is too
long. If problems remain after the fix, the `.fix` target fails and shows
them.

The `.lint` test fails if a source file or the config is not in its runfiles.
markdownlint ignores a path that does not exist, so without this check the test
could pass and check nothing.

## Config

`.lint` and `.fix` give the config to markdownlint with `--config`. They do
not let markdownlint find a config file by itself. Thus both targets always use
the same rules.

To change the rules for one package, put a config in the package and give it
in `config`. The new config can extend the root config by a relative path:

```jsonc
{
  "extends": "../../.markdownlint.jsonc",
  "MD013": false
}
```

The macro always adds the root config to the runfiles of `.lint`. Thus a
config that extends the root config also works in the test.

## Export to Word

```sh
bazel run //packages/algo_tutor:SPEC.md.docx
```

The `.docx` targets use `//rules/markdown/md2docx`. The Word file goes to
`build/docx/` in the workspace, at the same path as the source file. For
example, `packages/algo_tutor/SPEC.md` becomes
`build/docx/packages/algo_tutor/SPEC.docx`. Git ignores `build/`.

md2docx draws each `mermaid` code block when it finds the `mmdc` command. If
md2docx does not find `mmdc`, it tells you how to install it.

## Convert Chinese text

```sh
bazel run //pkg:notes.md.s2twp
```

The `.s2twp` targets run `opencc -c s2twp.json` on each file and write the
result back to the same file.

Do not run a `.s2twp` target on Japanese text. Some Japanese kanji are also
Simplified Chinese characters, and opencc changes them. For example, `具体`
becomes `具體`.

## Tools

The scripts find `markdownlint` and `opencc` on your `PATH`. If a tool is not
on your `PATH`, the scripts also look in `/opt/homebrew/bin` and
`/usr/local/bin`. md2docx finds `mmdc`. Bazel does not download these tools.

| Tool | Used by | Install |
| --- | --- | --- |
| `markdownlint` | `.lint`, `.fix` | `brew install markdownlint-cli` |
| `opencc` | `.s2twp` | `brew install opencc` |
| `mmdc` | `.docx`, only for `mermaid` blocks | See the message from md2docx. |

## Limits

- Start each `.fix`, `.s2twp` and `.docx` target with `bazel run`. These
  scripts get the workspace path from `BUILD_WORKSPACE_DIRECTORY`, and only
  `bazel run` sets this variable. If you start a script in a different way, it
  stops with an error.
- A file name can contain spaces. A file name cannot contain a single quote
  (`'`).

## Files

| File | Purpose |
| --- | --- |
| `defs.bzl` | The `markdown_docs` macro. |
| `lint.sh` | The script that `.lint` runs. |
| `fix.sh` | The script that `.fix` runs. |
| `s2twp.sh` | The script that `.s2twp` runs. |
| `docx.sh` | The script that `.docx` runs. |

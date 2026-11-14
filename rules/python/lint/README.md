# Python lint rules

This package supplies `py_library` and `py_binary` macros. Each macro creates
the usual rules_python target and two more targets:

| Target | Kind | What it does |
| --- | --- | --- |
| `<name>.lint` | `sh_test` | Runs `ruff check` and `mypy` on the `srcs` of `<name>`. It does not change files. |
| `<name>.fix` | `sh_binary` | Runs `ruff check --fix` and `ruff format` on the `srcs` of `<name>`. It changes the files in the workspace. |

## Use the macros

Load the macros in place of the rules_python macros:

```starlark
load("//rules/python/lint:defs.bzl", "py_binary", "py_library")

py_library(
    name = "chart_core",
    srcs = ["chart_spec.py", "checks.py"],
    deps = [requirement("pydantic")],
)
```

The macros accept the same arguments as the rules_python macros. The
`py_binary` macro sets `legacy_create_init = False` if you do not give a value.
A target with no `srcs` gets no `.lint` target and no `.fix` target.

## Check or fix one target

```sh
# Check. This command does not change files.
bazel test //packages/vibe_coding_club/vega_lite_chat:chart_core.lint

# Fix and format. This command changes the files in the workspace.
bazel run //packages/vibe_coding_club/vega_lite_chat:chart_core.fix
```

Start a `.fix` target with `bazel run` only. `fix.sh` gets the workspace path
from `BUILD_WORKSPACE_DIRECTORY`, and only `bazel run` sets this variable. If
you start the script in a different way, it stops with an error.

## Check or fix all targets

A `.lint` target is a test. Thus `bazel test //...` runs all `.lint` targets
together with the unit tests.

The Python targets are in `//packages/...` and in `//rules/...`. The markdown
targets of `//rules/markdown` also have names that end in `.lint` and `.fix`.
Thus the commands below select the targets that use `lint.sh` or `fix.sh`, not
the targets that have a matching name. To run only the Python `.lint` targets:

```sh
bazel test $(bazel query 'kind(sh_test, rdeps(//..., //rules/python/lint:lint.sh, 1))')
```

`bazel run` accepts one target, so run the Python `.fix` targets one at a time:

```sh
for target in $(bazel query 'kind(sh_binary, rdeps(//..., //rules/python/lint:fix.sh, 1))'); do
  bazel run "$target"
done
```

`check_all.sh` and `fix_all.sh` select targets by name in `//packages/...`
only. Thus they also select the markdown targets, and they do not select the
targets in `//rules/...`. This package exports the two scripts, but no target
in the workspace runs them. If you add an `sh_binary` for a script, start it
with `bazel run`. Do not make it a test, because a `bazel` command in a test
action can deadlock against the Bazel server.

## How mypy finds types

`lint.sh` runs mypy with `--ignore-missing-imports` and
`--explicit-package-bases`. It runs both ruff and mypy, and the test fails if
one of them fails.

mypy must import the third-party packages of the target. If it cannot, it
treats them as `Any` and can report incorrect errors. For this reason, the
macro creates a private copy of the mypy script, `<name>.mypy_bin`, that has
the `deps` of the target.

mypy also needs the first-party modules that the target imports from the same
package. The macro adds the `srcs` of each same-package `:label` dependency to
the test data. These files are data for the test. They are not arguments to
mypy.

The macro finds a same-package dependency only if the BUILD file declares that
dependency above the target. Put each library above the targets that use it.
If the dependency is below the target, the macro does not add its files, and
mypy may not resolve the import.

## Limits

- The macros wrap only `py_library` and `py_binary`. The tests in this
  workspace use the `py_test` rule from rules_python, so test files have no
  `.lint` target.
- The macros do not check files in `data`. `streamlit_app` gives its `app` file
  to the binary as `data`. For this reason, each Streamlit `main.py` only calls
  `ui.render_app()`, and a library holds the code that the macros check.

## Files

| File | Purpose |
| --- | --- |
| `defs.bzl` | The `py_library` and `py_binary` macros. |
| `lint.sh` | The script that a `.lint` target runs. |
| `fix.sh` | The script that a `.fix` target runs. |
| `check_all.sh`, `fix_all.sh` | Scripts that run the targets with a name that ends in `.lint` or `.fix` under `//packages/...`. No target runs them. |
| `BUILD.bazel` | `:ruff` and `:mypy`. The ruff wheel has no console script, so `:ruff` extracts the ruff binary from the wheel. |

ruff and mypy come from `@monorepo_pip`, which reads `uv.lock`. To change their
versions, edit the `dev` group in `pyproject.toml` and run `uv lock`.

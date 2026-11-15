# Streamlit app rule

This package supplies the `streamlit_app` macro. The macro creates a
`py_binary` that starts `streamlit run` on one app file.

A Streamlit app does not work as `python main.py`. The `streamlit run` command
starts the server and the runtime that draws the page. A plain `py_binary` runs
only `python main.py`, so it shows nothing.

## Use the macro

```starlark
load("//rules/python/streamlit:defs.bzl", "streamlit_app")

streamlit_app(
    name = "vega_lite_chat",
    app = "main.py",
    deps = [":vega_lite_chat_lib"],
)
```

| Argument | Default | Purpose |
| --- | --- | --- |
| `name` | none | The target name. Start the app with `bazel run //pkg:name`. |
| `app` | none | The app file, as a path relative to the package. The file must be in the same package. |
| `deps` | `[]` | Libraries for the app. The macro adds `streamlit`. |
| `data` | `[]` | Files that the app reads at run time. |
| `open_browser` | `True` | If `True`, the launcher opens the app in the default browser. Set `False` for a CI target or for a server that has no screen. |
| Other arguments | none | The macro gives them to `py_binary`, for example `args` and `visibility`. |

## Run the app

```sh
bazel run //packages/vega_lite_chat:vega_lite_chat
```

The launcher gives the arguments after `--` to `streamlit run`. Use them to
set Streamlit options:

```sh
bazel run //packages/vega_lite_chat:vega_lite_chat -- --server.port=8600
```

To stop the app, press Ctrl-C. The signal stops the launcher and the Streamlit
server.

## What the launcher does

1. The launcher starts `streamlit run --server.headless=true <app>` with the
   Python interpreter of the binary.
2. If `open_browser` is `True`, the launcher tries to connect to the server
   port for about 30 seconds.
3. When the port accepts a connection, the launcher opens
   `http://<host>:<port>` in the default browser. If the port does not accept
   a connection in that time, the launcher opens no browser.

The launcher sets `--server.headless=true` because Streamlit otherwise asks
for an email address on its first run. `bazel run` then stops at that prompt.
In headless mode Streamlit does not open a browser, so the launcher opens it.

To find the server, the launcher reads `--server.address` and `--server.port`
from the arguments after `--`. It accepts `--key=value` and `--key value`. The
defaults are `localhost` and `8501`, which is the Streamlit default port. If
the address is `0.0.0.0`, the launcher opens `localhost`.

## Network address

The macro does not set `--server.address`. Without this option, Streamlit
accepts connections on all network interfaces. To accept connections only
from this computer, set the option in `args`:

```starlark
streamlit_app(
    name = "chart_app",
    app = "main.py",
    args = ["--server.address=localhost"],
    deps = [":chart_lib", ":chart_ui"],
)
```

`//packages/vega_lite_ai:chart_app` uses this setting. Each
run of that app uses your API key and runs code that a model writes.

## Lint and test

The macro uses the `py_binary` macro from `//rules/python/lint`. Thus the app
also gets a `<name>.lint` target and a `<name>.fix` target:

- `<name>.lint` checks only the generated launcher, `<name>_main.py`. The app
  file is `data`, and the lint macros do not check `data`.
- `<name>.fix` does not work. It looks for `<name>_main.py` in the workspace,
  but Bazel writes that file to the output tree.

For this reason, keep the app file short. Put the code in a `py_library`, and
make the app file call it. Each app in this workspace has a `main.py` that only
calls `ui.render_app()`. The lint targets of the library then check the code.

To test the page, use `AppTest.from_file` from `streamlit.testing.v1`. Give the
app file to the `py_test` in `data`, so that the file is in the runfiles of the
test. The `test_ui` targets in this workspace use this method.

## Files

| File | Purpose |
| --- | --- |
| `defs.bzl` | The `streamlit_app` macro. |
| `main_template.py` | The launcher template. The macro writes `<name>_main.py` from this template with `expand_template`. |

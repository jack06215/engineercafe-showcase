"""`py_library` and `py_binary` that also create `<name>.lint` and `<name>.fix`.

`<name>.lint` checks the srcs with ruff and mypy and does not change files.
`<name>.fix` runs ruff on the srcs in the workspace, so start it with
`bazel run`. See README.md in this folder.
"""

load("@rules_python//python:py_binary.bzl", native_py_binary = "py_binary")
load("@rules_python//python:py_library.bzl", native_py_library = "py_library")
load("@rules_python//python/entry_points:py_console_script_binary.bzl", "py_console_script_binary")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("@rules_shell//shell:sh_test.bzl", "sh_test")

def _canon(label_str):
    return str(native.package_relative_label(label_str))

def _same_package_dep_srcs(deps, srcs_canon):
    extra = []
    for dep in deps:
        if not dep.startswith(":"):
            continue
        rule = native.existing_rule(dep[1:])
        if rule == None:
            continue
        for src in rule.get("srcs", []):
            if _canon(src) not in srcs_canon:
                extra.append(src)
    return extra

def _lint_and_fix_targets(name, srcs, deps = []):
    if not srcs:
        return

    srcs_canon = [_canon(s) for s in srcs]

    mypy_bin = name + ".mypy_bin"
    py_console_script_binary(
        name = mypy_bin,
        pkg = "@monorepo_pip//mypy",
        script = "mypy",
        deps = deps,
        legacy_create_init = False,
        visibility = ["//visibility:private"],
    )

    sh_test(
        name = name + ".lint",
        srcs = ["//rules/python/lint:lint.sh"],
        args = [
            "$(rootpath //rules/python/lint:ruff)",
            "$(rootpath :%s)" % mypy_bin,
            "$(rootpath //:pyproject.toml)",
        ] + ["$(rootpath %s)" % src for src in srcs],
        data = srcs + _same_package_dep_srcs(deps, srcs_canon) + [
            "//:pyproject.toml",
            "//rules/python/lint:ruff",
            ":" + mypy_bin,
        ],
    )

    sh_binary(
        name = name + ".fix",
        srcs = ["//rules/python/lint:fix.sh"],
        args = [
            "$(rootpath //rules/python/lint:ruff)",
            native.package_name(),
        ] + srcs,
        data = srcs + ["//rules/python/lint:ruff"],
    )

def py_library(name, srcs = [], deps = [], **kwargs):
    native_py_library(name = name, srcs = srcs, deps = deps, **kwargs)
    _lint_and_fix_targets(name, srcs, deps)

def py_binary(name, srcs = [], deps = [], legacy_create_init = False, **kwargs):
    native_py_binary(
        name = name,
        srcs = srcs,
        deps = deps,
        legacy_create_init = legacy_create_init,
        **kwargs
    )
    _lint_and_fix_targets(name, srcs, deps)

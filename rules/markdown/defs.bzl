"""`markdown_docs`: markdownlint, opencc and Word export targets for Markdown files.

See README.md in this folder.
"""

load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("@rules_shell//shell:sh_test.bzl", "sh_test")

def _shell_quote(value):
    return "'" + value + "'"

def _script_args(srcs):
    return [_shell_quote(native.package_name())] + [_shell_quote(src) for src in srcs]

def _config_path(config):
    label = native.package_relative_label(config)
    if not label.package:
        return label.name
    return label.package + "/" + label.name

def _mutating_targets(name, srcs, config):
    sh_binary(
        name = name + ".fix",
        srcs = ["//rules/markdown:fix.sh"],
        args = [_shell_quote(_config_path(config))] + _script_args(srcs),
    )

    sh_binary(
        name = name + ".s2twp",
        srcs = ["//rules/markdown:s2twp.sh"],
        args = _script_args(srcs),
    )

    sh_binary(
        name = name + ".docx",
        srcs = ["//rules/markdown:docx.sh"],
        args = ["$(rootpath //rules/markdown/md2docx:md2docx)"] + _script_args(srcs),
        data = ["//rules/markdown/md2docx:md2docx"],
    )

def markdown_docs(name, srcs, config = "//:.markdownlint.jsonc"):
    """Generates markdownlint / opencc / docx targets for a set of markdown files.

    Args:
      name: prefix for the targets covering all of srcs, e.g. "docs" gives
        `//pkg:docs.lint`, `//pkg:docs.fix`, `//pkg:docs.s2twp` and
        `//pkg:docs.docx`.
      srcs: markdown files, relative to the package this is called from. Each
        one also gets its own `.fix`, `.s2twp` and `.docx` targets, named after
        the file, e.g. `//pkg:notes/foo.md.fix` and `//pkg:notes/foo.md.docx`.
      config: markdownlint config for `.lint` and `.fix`. A replacement may
        `"extends"` the root one by relative path; it's always in the runfiles.
    """
    if not srcs:
        return

    # The config has to be in the runfiles too -- the sandbox has no view of
    # the workspace root otherwise, and lint.sh looks for it by path.
    configs = ["//:.markdownlint.jsonc"]
    if native.package_relative_label(config) != Label("//:.markdownlint.jsonc"):
        configs.append(config)

    sh_test(
        name = name + ".lint",
        srcs = ["//rules/markdown:lint.sh"],
        args = [_shell_quote(_config_path(config))] + _script_args(srcs),
        data = srcs + configs,
    )

    _mutating_targets(name, srcs, config)

    # Per-file variants, so converting one note doesn't rewrite all the others.
    # Named after the src itself, so the label is just the file's path plus a
    # suffix.
    for src in srcs:
        _mutating_targets(src, [src], config)

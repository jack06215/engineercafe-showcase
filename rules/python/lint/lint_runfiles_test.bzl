"""`lint_runfiles_test`: checks that a `.lint` target carries the repo's pyproject.toml."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _lint_runfiles_test_impl(ctx):
    env = analysistest.begin(ctx)
    target = analysistest.target_under_test(env)
    paths = [f.short_path for f in target[DefaultInfo].default_runfiles.files.to_list()]
    asserts.true(
        env,
        "pyproject.toml" in paths,
        "the .lint target has no pyproject.toml in its runfiles, so ruff and mypy " +
        "would run with their defaults",
    )
    return analysistest.end(env)

lint_runfiles_test = analysistest.make(_lint_runfiles_test_impl)

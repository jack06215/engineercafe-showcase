"""Where algo_tutor's files live (SPEC.md §3.3)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PACKAGE = Path("packages/algo_tutor")
PATTERNS = Path("packages/programming_exercise/common_coding_pattern")
LEETCODE_SRC = Path("packages/programming_exercise/leetcode/src")
ATCODER_SRC = Path("packages/programming_exercise/atcoder/src")


class PathsError(ValueError):
    """The repo root can't be found."""


@dataclass(frozen=True)
class AppPaths:
    repo_root: Path
    config_files: tuple[Path, ...]  # read in order, later merged on top
    data_dir: Path

    @property
    def package_dir(self) -> Path:
        return self.repo_root / PACKAGE

    @property
    def database(self) -> Path:
        return self.data_dir / "algo_tutor.sqlite"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def bank_dir(self) -> Path:
        return self.data_dir / "bank"

    @property
    def bank_file(self) -> Path:
        """The last raw problem bank download."""
        return self.bank_dir / "leetcode-bank.json"

    @property
    def patterns_dir(self) -> Path:
        return self.repo_root / PATTERNS


def resolve_paths(
    repo_root: Path | None = None,
    data_dir: Path | None = None,
    config: Path | None = None,
    environ: Mapping[str, str] = os.environ,
) -> AppPaths:
    """The paths from the `--repo-root`, `--data-dir` and `--config` flags.

    The repo root comes from `--repo-root`, else `$BUILD_WORKSPACE_DIRECTORY`
    (set by `bazel run`). Everything else defaults to a place under it.
    """
    if repo_root is None:
        workspace = environ.get("BUILD_WORKSPACE_DIRECTORY")
        if not workspace:
            raise PathsError(
                "Can't find the repo root: pass --repo-root, or run through `bazel run`, "
                "which sets $BUILD_WORKSPACE_DIRECTORY."
            )
        repo_root = Path(workspace)
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise PathsError(f"The repo root {repo_root} is not a directory.")
    package = repo_root / PACKAGE
    if config is not None:
        files: tuple[Path, ...] = (config.resolve(),)
    else:
        files = (package / "config.yaml", package / "config.local.yaml")
    data = (data_dir if data_dir is not None else package / ".data").resolve()
    return AppPaths(repo_root=repo_root, config_files=files, data_dir=data)

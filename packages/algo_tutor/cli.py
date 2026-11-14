"""`cli algo_tutor`: the practice tracker's command line (SPEC.md §3.5).

Mounted in packages/cli.py. Every command takes `--repo-root`, `--data-dir`
and `--config`; under `bazel run` the repo root comes from
$BUILD_WORKSPACE_DIRECTORY. Everything but `serve` works with the server
stopped.
"""

import argparse
import dataclasses
import sys
from pathlib import Path

from pydantic import ValidationError

from packages.algo_tutor.catalogue.bank import BankService
from packages.algo_tutor.catalogue.bank_file import BankFetchError
from packages.algo_tutor.catalogue.errors import CatalogueError
from packages.algo_tutor.catalogue.manifests import ManifestError
from packages.algo_tutor.catalogue.packs import import_pack, parse_pack
from packages.algo_tutor.config import ConfigError, ServerConfig
from packages.algo_tutor.paths import PathsError
from packages.algo_tutor.runtime import (
    Runtime,
    open_runtime,
    startup_backup,
    take_backup,
)
from packages.algo_tutor.store.backups import BackupError
from packages.algo_tutor.store.migrations import SchemaTooNewError
from packages.algo_tutor.store.timeutil import now_utc


def add_location_flags(parser: argparse.ArgumentParser) -> None:
    """`--repo-root`, `--data-dir` and `--config`, shared with `serve.py`."""
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="the monorepo checkout (default: $BUILD_WORKSPACE_DIRECTORY)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="runtime data (default: <repo>/packages/algo_tutor/.data)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="config file, replacing config.yaml and config.local.yaml",
    )


def add_serve_flags(parser: argparse.ArgumentParser) -> None:
    """Add the flags that override where the server listens."""
    parser.add_argument(
        "--host", help="loopback address to listen on (default: config server.host)"
    )
    parser.add_argument(
        "--port", type=int, help="port to listen on (default: config server.port, 4317)"
    )


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for this tool, reused as a subparser parent by packages/cli.py."""
    parser = argparse.ArgumentParser(
        prog="algo_tutor",
        description="Coding-interview practice tracker: the API server, problem bank, question packs, backups.",
    )
    add_location_flags(parser)
    # Not `command`: packages/cli.py's own subparsers write that.
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    def add_subcommand(name: str, summary: str) -> argparse.ArgumentParser:
        return subparsers.add_parser(name, help=summary, description=summary)

    bank = add_subcommand("bank", "The LeetCode problem bank")
    bank_commands = bank.add_subparsers(dest="bank_command", required=True)
    bank_commands.add_parser(
        "refresh",
        help="Download LeetCode's problem list and re-rate it",
        description="Download LeetCode's problem list and re-rate it",
    )

    pack = add_subcommand(
        "import-pack", "Validate and import a question pack (version 2)"
    )
    pack.add_argument("file", type=Path, help="the pack's JSON file")
    pack.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report what would change, writing nothing",
    )

    add_subcommand("backup", "Back up the database now")

    serve_parser = add_subcommand(
        "serve", "Start the API on 127.0.0.1 (taking the daily backup first)"
    )
    add_serve_flags(serve_parser)
    return parser


def _bank_refresh(runtime: Runtime) -> None:
    service = BankService(runtime.sessions, runtime.manifests, runtime.paths.bank_file)
    print(
        "algo_tutor: downloading LeetCode's problem list (about 40 requests)…",
        file=sys.stderr,
    )
    report = service.refresh()
    print(
        f"Downloaded {report.downloaded:,} algorithm problems; kept {report.kept:,} rated up to 2000; "
        f"{report.added:,} new, {report.updated:,} updated. Estimates: {report.method}."
    )
    if report.unknown_tags:
        print("Tags not in topics.yaml: " + ", ".join(report.unknown_tags))


def _import_pack(runtime: Runtime, file: Path, dry_run: bool) -> None:
    parsed = parse_pack(file.read_bytes())
    with runtime.sessions() as session, session.begin():
        report = import_pack(
            session,
            runtime.manifests,
            parsed,
            now_utc(),
            dry_run=dry_run,
            bank=runtime.saved_bank(),
        )
    if report.already_applied:
        print(f"Already imported ({report.import_id}); nothing to do.")
        return
    verb = "Would add" if dry_run else "Added"
    print(
        f"{verb} {report.problems_created} problem(s) ({report.problems_existing} already in the library), "
        f"{report.entries_added} list entr{'y' if report.entries_added == 1 else 'ies'}, "
        f"{report.patterns_added} pattern label(s)."
    )
    for name in report.lists_created:
        print(f"  new list: {name}")
    for name in report.lists_extended:
        print(f"  extended: {name}")


def serve(
    repo_root: Path | None,
    data_dir: Path | None,
    config: Path | None,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Serve the API on loopback until interrupted (SPEC §3.1, §17).

    It opens everything first, and backs up if the last backup is over a day
    old.
    """
    # FastAPI, uvicorn and LangChain load only for `serve`.
    import uvicorn

    from packages.algo_tutor.api.app import create_app

    runtime = open_runtime(repo_root, data_dir, config)
    try:
        current = runtime.config.server
        try:
            server = ServerConfig(host=host or current.host, port=port or current.port)
        except ValidationError as exc:
            raise ConfigError(f"--host/--port: {exc.errors()[0]['msg']}") from exc
        runtime = dataclasses.replace(
            runtime, config=runtime.config.model_copy(update={"server": server})
        )
        backup = startup_backup(runtime)
        if backup is not None:
            print(f"algo_tutor: backed up to {backup.path}", file=sys.stderr)
        print(
            f"algo_tutor: serving http://{server.host}:{server.port}/api",
            file=sys.stderr,
        )
        uvicorn.run(create_app(runtime), host=server.host, port=server.port)
    finally:
        runtime.close()


def run_cli(namespace: argparse.Namespace) -> None:
    """Run the subcommand `build_parser` parsed."""
    try:
        if namespace.subcommand == "serve":
            serve(
                namespace.repo_root,
                namespace.data_dir,
                namespace.config,
                namespace.host,
                namespace.port,
            )
            return
        if namespace.subcommand == "import-pack":
            # Validate before touching the database, so a bad pack costs nothing.
            parse_pack(namespace.file.read_bytes())
        runtime = open_runtime(
            namespace.repo_root, namespace.data_dir, namespace.config
        )
        try:
            if namespace.subcommand == "bank":
                _bank_refresh(runtime)
            elif namespace.subcommand == "import-pack":
                _import_pack(runtime, namespace.file, namespace.dry_run)
            elif namespace.subcommand == "backup":
                backup = take_backup(runtime)
                print(f"Backed up to {backup.path}")
        finally:
            runtime.close()
    except (
        PathsError,
        ConfigError,
        ManifestError,
        SchemaTooNewError,
        CatalogueError,
        BankFetchError,
        BackupError,
        OSError,
    ) as error:
        sys.exit(f"algo_tutor: {error}")


def main() -> None:
    """Run the CLI with the command-line arguments."""
    run_cli(build_parser().parse_args())


if __name__ == "__main__":
    main()

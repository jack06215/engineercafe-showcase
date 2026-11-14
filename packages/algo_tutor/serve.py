"""`bazel run //packages/algo_tutor:serve`: the API on 127.0.0.1:4317 (SPEC §3.1).

The same as `cli algo_tutor serve`, with every flag after the target.
"""

import argparse

from packages.algo_tutor.cli import add_location_flags, add_serve_flags, run_cli


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="serve", description=__doc__.splitlines()[0] if __doc__ else None
    )
    add_location_flags(parser)
    add_serve_flags(parser)
    namespace = parser.parse_args()
    namespace.subcommand = "serve"
    run_cli(namespace)


if __name__ == "__main__":
    main()

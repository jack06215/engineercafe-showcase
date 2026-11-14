"""Write the HTTP contract as an OpenAPI document of component schemas.

The web client generates its TypeScript types from this file:

    bazel run //packages/algo_tutor/api:export_schema -- \\
        src/main/typescript/packages/algo-tutor-web/src/api/schema.json

Only the bodies, not the paths: the routes live in the API app, and the
client's endpoint functions are written by hand against SPEC §15.
"""

import argparse
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from packages.algo_tutor.api import schemas


def contract_models() -> list[type[BaseModel]]:
    """Every request and response model in `schemas`, in source order."""
    found = [
        obj
        for _, obj in inspect.getmembers(schemas, inspect.isclass)
        if issubclass(obj, BaseModel)
        and obj.__module__ == schemas.__name__
        and obj not in (schemas.In, schemas.Out)
    ]
    return sorted(found, key=lambda m: inspect.getsourcelines(m)[1])


def build_document() -> dict[str, Any]:
    """An OpenAPI 3.1 document whose components are the contract's models."""
    pairs: list[tuple[type[BaseModel], Literal["validation", "serialization"]]] = [
        (m, "validation" if issubclass(m, schemas.In) else "serialization")
        for m in contract_models()
    ]
    _, defs = models_json_schema(pairs, ref_template="#/components/schemas/{model}")
    return {
        "openapi": "3.1.0",
        "info": {"title": "algo_tutor", "version": "0"},
        "paths": {},
        "components": {"schemas": defs.get("$defs", {})},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "output", type=Path, help="where to write the JSON, relative to the repo root"
    )
    args = parser.parse_args(argv)
    out: Path = args.output
    if not out.is_absolute():
        out = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")) / out
    out.write_text(json.dumps(build_document(), indent=2, sort_keys=True) + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

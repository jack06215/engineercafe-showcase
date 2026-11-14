# algo_tutor/api

The FastAPI app: the routes, the HTTP contract in `schemas.py` and the
local-only guard. The routes turn store rows into domain inputs
(`engine.py`, `facts.py`) and the results back into rows; the rules themselves
live in `domain/`. `testing.py` is the harness that the `test_api_*` files
share.

## Change the contract

The web client generates its TypeScript types from the contract. After you
change a model in `schemas.py`, export the contract and regenerate the types:

```sh
bazel run //packages/algo_tutor/api:export_schema -- \
    src/main/typescript/packages/algo-tutor-web/src/api/schema.json
pnpm --dir src/main/typescript/packages/algo-tutor-web run api:types
```

Model docstrings are part of the contract: they become the `description` of
each schema and the doc comment of each generated type.

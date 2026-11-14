# algo_tutor

A local web app for deliberate coding-interview practice: a training level per
topic on LeetCode's contest-rating scale, a daily plan, reviews that check an
idea with a different problem, topic and pattern notebooks, and an optional
AI tutor. [`SPEC.md`](SPEC.md) is the functional spec.

## Run

```sh
# The API on 127.0.0.1:4317 (serve arrives with the API layer)
bazel run //packages/algo_tutor:serve

# The command line, with the server running or stopped
bazel run //packages/algo_tutor:cli -- bank refresh                     # download LeetCode's problem list (~40 requests)
bazel run //packages/algo_tutor:cli -- import-pack pack.json --dry-run  # validate a question pack, report what would change
bazel run //packages/algo_tutor:cli -- import-pack pack.json            # import it
bazel run //packages/algo_tutor:cli -- backup                           # back up the database now
```

Every command takes `--repo-root` (default `$BUILD_WORKSPACE_DIRECTORY`, set by
`bazel run`), `--data-dir` (default `packages/algo_tutor/.data/`) and
`--config` (replaces `config.yaml` + `config.local.yaml`).

## Configure

`config.yaml` holds the committed defaults: the server address (loopback
only) and the tutor's model, per task. Put overrides in `config.local.yaml`
beside it (gitignored); it's merged key by key. API keys for `openai` and
`azure` come from the environment variables `packages/langchain_util` reads;
the YAML never holds secrets.

## Data

Everything the app writes is under `.data/` (gitignored):

| File | What |
| --- | --- |
| `algo_tutor.sqlite` | The database (WAL; `-wal` and `-shm` files beside it) |
| `backups/algo_tutor-<UTC time>.sqlite` | Daily backups, newest 7 kept, mode 0600 |
| `bank/leetcode-bank.json` | The last raw LeetCode problem-list download |

A backup is taken at startup when the last one is over a day old, and by
`bazel run //packages/algo_tutor:cli -- backup` or Settings.

### Restore a backup

1. Stop the server.
2. Move `algo_tutor.sqlite`, `algo_tutor.sqlite-wal` and `algo_tutor.sqlite-shm`
   aside.
3. Copy the backup you want to `.data/algo_tutor.sqlite`.
4. Start the server.

## Layout

| Folder | What |
| --- | --- |
| `domain/` | Pure rules: ratings, ladder, reviews, plan, topics, timer |
| `store/` | SQLAlchemy models, schema versions (`PRAGMA user_version`), seeding, backups |
| `catalogue/` | Bundled manifests, the problem bank and rating model, courses, lists, question packs, setup |
| `manifests/` | Bundled data, checksum-pinned, plus `topics.yaml` (the 34 topics) |

## Attribution

algo_tutor ports rules, prompts and data handling from
[BloomCode](https://github.com/pritanb/bloomcode) (© Pritan Barai, MIT) at
`b0a6975`; its licence is in [`LICENSE-bloomcode.txt`](LICENSE-bloomcode.txt).
Ported here so far: the problem bank download and its filters, the ridge
rating model and its test, popularity, the study-list "done" rule, the
question-pack import (as version 2), backups, and the schema it all writes.

The bundled data keeps its own licences in `manifests/`:

- `neetcode-problems.json` from [neetcode-gh/leetcode](https://github.com/neetcode-gh/leetcode)
  @ `9f104d45`, MIT (`LICENSE-neetcode.txt`);
- `zerotrac-ratings.txt` from [zerotrac/leetcode_problem_rating](https://github.com/zerotrac/leetcode_problem_rating)
  @ `8c7a5400`, MIT (`LICENSE-zerotrac.txt`);
- `study-sets.json` from BloomCode, hand-made from Hello Interview's public
  table of contents (2026-10-14).

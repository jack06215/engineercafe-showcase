# Agent instructions

Rules for coding agents working in this repo. `CLAUDE.md` imports this file,
so edit the rules here.

## Working with the user

- Ask the user before you choose between options that are hard to undo:
  adding a third-party dependency, changing a public API or schema, or
  changing how packages are laid out. Before you ask, find similar code in
  this repo and cite it (`path:line`), then recommend one option and give its
  trade-offs. Make small internal choices yourself and say what you chose.
- Build what the user asked for. Before you say a task is done, check the
  change against the coding rules below. At the end of your reply, suggest
  the related work (tests, docs) that the change still needs to meet them.

## Coding rules

- Follow the style guide for each language you edit, in
  [docs/coding_style_guides](docs/coding_style_guides): `python.md`,
  `typescript.md`, `shell.md` and `markdown.md`.
- Keep secrets (API keys, tokens, passwords) in `.env`, which git ignores, and
  read them from environment variables. Check `git diff --staged` for secrets
  before every commit.
- Keep each PR to one semantic change: if its title needs "and", split it.
  Put refactors and behaviour changes in separate PRs.
- Write commit messages as [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) (`feat:`, `fix:`,
  `refactor:`) and name branches `<type>/<topic>`, such as `feat/setup-script`.
- Add or update unit tests for every behaviour change. Then run the checks in
  the [Test and lint](README.md#test-and-lint) section of the README and make
  sure they pass.
- Give each directory that has a `BUILD.bazel`, and each package in
  `src/main/typescript/packages/`, a `README.md` that says what it is for.
- Write code comments, docstrings, commit messages and PR descriptions in
  English. User-facing strings and LLM prompts may be in Japanese.

# Contributing

## Start here

1. Read `AGENTS.md` and the active package under `docs/task-packages/packages/`.
2. Confirm its dependencies are `complete` in `docs/task-packages/manifest.json`.
3. Run `scripts/bootstrap.ps1` on Windows or `scripts/bootstrap.sh` on Linux/macOS.
4. Keep changes inside the package's declared path ownership.

## Required checks

Run `python scripts/verify_local.py --quick` while iterating and
`python scripts/verify_local.py` before completing a package. Never weaken a
validator to make a failing implementation pass.

## Evidence and Git

Record summarized command results in the package evidence file. Do not include
environment values, tokens, local absolute media paths, or full provider
payloads. Do not broad-stage, commit, push, deploy, or activate live connectors
unless the user authorizes that exact action.

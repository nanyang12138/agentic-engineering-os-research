# AGENTS.md

## Cursor Cloud specific instructions

This is a **pure Python 3.12 stdlib** research codebase with **zero external dependencies** — no pip packages, no package manager, no lockfile.

### Key commands

| Action | Command | Notes |
|---|---|---|
| **Validate / Test** | `python3 scripts/validate_repo.py` | Single CI gate — validates all artifacts, contracts, fixture regeneration, and JSON integrity. Run from repo root. |
| **Run fixture pipeline** | `python3 scripts/fixture_runner.py --fixture-dir fixtures/regression --out-dir /tmp/fixture-output` | Processes regression fixtures and generates run artifacts (run.json, events.jsonl, evidence.json, regression_result.json, email_draft.md, verifier_report.json). |

### Gotchas

- The scripts import each other as sibling modules (e.g. `from capability_contract import ...`). Python automatically adds the script's directory to `sys.path` when invoked via `python3 scripts/<name>.py`, so always run from the repo root with the `scripts/` prefix.
- `validate_repo.py` is very large (~128k chars). It regenerates all fixture outputs into a temp directory and compares them byte-for-byte against the committed artifacts. If you modify any script that affects artifact generation, you must also regenerate and commit the updated `output/` artifacts. The simplest way is: run `python3 scripts/fixture_runner.py --fixture-dir fixtures/regression --out-dir output/regression`, then commit the changes.
- There is no linter or formatter configured in the repo. The CI only runs `validate_repo.py`.
- No database, no network calls, no external services required.

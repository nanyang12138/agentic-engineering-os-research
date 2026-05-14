# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is a zero-dependency Python 3.12+ research repository (Agentic Engineering OS). All scripts use Python stdlib only — no `pip install` or `package.json` needed.

### Key commands

| Action | Command |
|---|---|
| Full validation (CI equivalent) | `python3 scripts/validate_repo.py` |
| Run all regression fixtures | `python3 scripts/fixture_runner.py --fixture-dir fixtures/regression --out-dir /tmp/fixtures-out` |
| Run single fixture through pipeline | `python3 scripts/local_readonly_runner.py --log-path fixtures/regression/<case>/input.log --goal "Analyze regression" --out-dir /tmp/run-out` |

### Notes

- `validate_repo.py` is the single CI entry point — it rebuilds all artifacts into a temp directory, validates schemas/cross-references, checks idempotency against committed artifacts, and runs all 5 regression fixtures. It exits 0 on success and completes in ~2 seconds.
- `fixture_runner.py` expects `--fixture-dir` to point at the parent directory containing fixture subdirectories (e.g., `fixtures/regression`), not a single fixture case directory.
- All generated artifacts are JSON files on disk. There are no databases, servers, or containers to start.
- The GitHub Actions CI workflow (`.github/workflows/validate.yml`) runs `python scripts/validate_repo.py` on Python 3.12.

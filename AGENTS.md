# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is a **pure Python 3.12 research/validation repository** with zero third-party dependencies. All scripts use only the Python standard library. There is no `requirements.txt`, `pyproject.toml`, or any package manager manifest.

### Running the project

All commands must be run from the repository root (`/workspace`). Scripts in `scripts/` import each other, so use `python3 scripts/<script>.py` from the root.

| Task | Command |
|---|---|
| **Validate repo (CI equivalent)** | `python3 scripts/validate_repo.py` |
| **Run all regression fixtures** | `python3 scripts/fixture_runner.py --fixture-dir fixtures/regression --out-dir /tmp/fixture_output` |
| **Run a single local log** | `python3 scripts/local_readonly_runner.py --log-path fixtures/regression/all_passed/input.log --goal "Check regression" --out-dir /tmp/local_output` |

### Important caveats

- Use `python3` not `python` — the VM may not have `python` symlinked.
- Scripts must be invoked from the repo root so that relative imports within `scripts/` resolve correctly (the working directory must be such that `python3 scripts/foo.py` works, which the default `cwd=/workspace` satisfies).
- The `validate_repo.py` script is the single "lint + test + build" equivalent. It validates all artifact schemas, runs the fixture pipeline, and checks deterministic reproducibility. The CI workflow (`.github/workflows/validate.yml`) runs exactly this.
- No linter (ruff, flake8, mypy, etc.) is configured; `validate_repo.py` is the sole quality gate.
- Fixture output directories (e.g. `artifacts/runs/`) are committed artifacts. The validation script regenerates them into a temp directory and compares against the committed versions to ensure deterministic reproducibility.

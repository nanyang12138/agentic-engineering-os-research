from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from fixture_runner import EXPECTED_FIXTURES, UNSAFE_ALL_PASSED_PHRASES, run_fixture_dir  # noqa: E402


REQUIRED_FILES = [
    "README.md",
    ".cursor/plans/agentic-control-plane.plan.md",
    "docs/automation/cloud-automation-prompt.md",
    ".github/workflows/validate.yml",
    "scripts/fixture_runner.py",
]

PLAN_REQUIRED_MARKERS = [
    "Read-only Regression Evidence Demo",
    "fixture-runner --fixture-dir <fixtures/regression> --out-dir <artifacts/runs>",
    "RegressionTaskSpecV1",
    "LogEvidenceV1",
    "RegressionResultArtifactV1",
    "verifier_report.json",
    "fixtures/regression/",
    "all_passed",
    "failed_tests",
    "incomplete_jobs",
    "passed_with_warning_or_waiver",
    "ambiguous_summary",
]

AUTOMATION_REQUIRED_MARKERS = [
    "Execute the entire Agentic Engineering OS plan",
    "It is allowed to create implementation code",
    "Read-only Regression Evidence Demo",
    "Definition of Done",
    "gh pr merge --auto --squash",
    "fixture-runner --fixture-dir <fixtures/regression> --out-dir <artifacts/runs>",
]

RUN_ARTIFACTS = [
    "run.json",
    "events.jsonl",
    "evidence.json",
    "regression_result.json",
    "email_draft.md",
    "verifier_report.json",
]

REQUIRED_VERIFIER_RULES = {
    "schema.validation",
    "evidence.refs",
    "classification.consistency",
    "email_draft.uses_structured_facts",
    "fixture.expected_verdict",
}


def require_file(path: str) -> str:
    full_path = ROOT / path
    if not full_path.is_file():
        raise AssertionError(f"Missing required file: {path}")
    return full_path.read_text(encoding="utf-8")


def require_markers(label: str, text: str, markers: list[str]) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        joined = "\n  - ".join(missing)
        raise AssertionError(f"{label} is missing required markers:\n  - {joined}")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def require_fixture_inputs() -> dict[str, dict]:
    fixture_root = ROOT / "fixtures/regression"
    if not fixture_root.is_dir():
        raise AssertionError("Missing required fixture directory: fixtures/regression")

    fixtures: dict[str, dict] = {}
    for fixture_id in EXPECTED_FIXTURES:
        case_dir = fixture_root / fixture_id
        fixture_file = case_dir / "fixture.json"
        input_log = case_dir / "input.log"
        if not fixture_file.is_file():
            raise AssertionError(f"Missing fixture metadata: {fixture_file.relative_to(ROOT)}")
        if not input_log.is_file():
            raise AssertionError(f"Missing fixture input log: {input_log.relative_to(ROOT)}")
        fixture = load_json(fixture_file)
        if fixture.get("id") != fixture_id:
            raise AssertionError(f"{fixture_file.relative_to(ROOT)} id must be {fixture_id}")
        fixtures[fixture_id] = fixture

    return fixtures


def parse_events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        events.append(json.loads(line))
    if not events:
        raise AssertionError(f"{path.relative_to(ROOT)} must contain events")
    return events


def assert_no_unsafe_pass_email(fixture: dict, email: str, path: Path) -> None:
    if fixture["allowAllPassedEmail"]:
        return
    email_lower = email.lower()
    unsafe = [phrase for phrase in UNSAFE_ALL_PASSED_PHRASES if phrase in email_lower]
    if unsafe:
        raise AssertionError(
            f"{path.relative_to(ROOT)} contains unsafe pass claim for negative fixture: {unsafe}"
        )


def validate_artifact_packet(out_dir: Path, fixtures: dict[str, dict]) -> None:
    if not out_dir.is_dir():
        raise AssertionError(f"Missing artifact output directory: {out_dir.relative_to(ROOT)}")

    for fixture_id, fixture in fixtures.items():
        run_dir = out_dir / fixture_id
        if not run_dir.is_dir():
            raise AssertionError(f"Missing artifact run directory: {run_dir.relative_to(ROOT)}")

        for artifact in RUN_ARTIFACTS:
            artifact_path = run_dir / artifact
            if not artifact_path.is_file():
                raise AssertionError(f"Missing artifact: {artifact_path.relative_to(ROOT)}")

        run_json = load_json(run_dir / "run.json")
        evidence = load_json(run_dir / "evidence.json")
        result = load_json(run_dir / "regression_result.json")
        verifier = load_json(run_dir / "verifier_report.json")
        email = (run_dir / "email_draft.md").read_text(encoding="utf-8")
        events = parse_events(run_dir / "events.jsonl")

        if run_json["status"] != "completed":
            raise AssertionError(f"{run_dir.relative_to(ROOT)}/run.json status must be completed")
        if result["verdict"] != fixture["expectedVerdict"]:
            raise AssertionError(
                f"{fixture_id} verdict {result['verdict']} does not match expected {fixture['expectedVerdict']}"
            )
        if verifier["status"] != "passed":
            raise AssertionError(f"{fixture_id} verifier_report.json status must be passed")
        if not evidence:
            raise AssertionError(f"{fixture_id} evidence.json must contain at least one evidence item")

        evidence_ids = {item["id"] for item in evidence}
        result_evidence_ids = set(result["evidenceIds"])
        if not result_evidence_ids or not result_evidence_ids.issubset(evidence_ids):
            raise AssertionError(f"{fixture_id} regression_result.json has invalid evidence refs")
        if fixture["expectedVerdict"] != "unknown" and not result_evidence_ids:
            raise AssertionError(f"{fixture_id} non-unknown verdict must cite evidence")

        rule_ids = {rule["ruleId"] for rule in verifier["ruleResults"]}
        missing_rules = REQUIRED_VERIFIER_RULES.difference(rule_ids)
        if missing_rules:
            raise AssertionError(f"{fixture_id} verifier_report.json is missing rules: {sorted(missing_rules)}")
        failing_rules = [rule for rule in verifier["ruleResults"] if rule["status"] == "failed"]
        if failing_rules:
            raise AssertionError(f"{fixture_id} verifier_report.json has failing rules: {failing_rules}")
        if verifier["blockingFailures"]:
            raise AssertionError(f"{fixture_id} verifier_report.json has blocking failures")

        assert_no_unsafe_pass_email(fixture, email, run_dir / "email_draft.md")
        if result["id"] not in email or result["verdict"] not in email:
            raise AssertionError(f"{fixture_id} email_draft.md must cite result artifact and verdict")
        for evidence_id in result["evidenceIds"]:
            if evidence_id not in email:
                raise AssertionError(f"{fixture_id} email_draft.md must cite evidence id {evidence_id}")

        event_types = {event["type"] for event in events}
        required_event_types = {
            "run.created",
            "task_spec.generated",
            "capability.read_log.completed",
            "capability.extract_regression_result.completed",
            "artifact.write.completed",
            "verifier.completed",
            "run.completed",
        }
        if not required_event_types.issubset(event_types):
            raise AssertionError(f"{fixture_id} events.jsonl is missing required event types")


def validate_fixture_runner(fixtures: dict[str, dict]) -> None:
    fixture_root = ROOT / "fixtures/regression"
    committed_out_dir = ROOT / "artifacts/runs"

    validate_artifact_packet(committed_out_dir, fixtures)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_out = Path(tmp) / "runs"
        reports = run_fixture_dir(fixture_root, tmp_out)
        if len(reports) != len(EXPECTED_FIXTURES):
            raise AssertionError(f"Expected {len(EXPECTED_FIXTURES)} verifier reports, got {len(reports)}")
        validate_artifact_packet(tmp_out, fixtures)


def main() -> None:
    for path in REQUIRED_FILES:
        require_file(path)

    plan = require_file(".cursor/plans/agentic-control-plane.plan.md")
    automation_prompt = require_file("docs/automation/cloud-automation-prompt.md")

    require_markers("plan", plan, PLAN_REQUIRED_MARKERS)
    require_markers("automation prompt", automation_prompt, AUTOMATION_REQUIRED_MARKERS)
    fixtures = require_fixture_inputs()
    validate_fixture_runner(fixtures)

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import copy
import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import fixture_runner


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures/regression"
ARTIFACT_DIR = ROOT / "artifacts/runs"
FIXTURE_IDS = [
    "all_passed",
    "failed_tests",
    "incomplete_jobs",
    "passed_with_warning_or_waiver",
    "ambiguous_summary",
]
ARTIFACT_FILES = [
    "run.json",
    "events.jsonl",
    "evidence.json",
    "regression_result.json",
    "email_draft.md",
    "verifier_report.json",
]
REQUIRED_REPORT_RULES = {
    "schema_validation",
    "evidence_refs",
    "classification_consistency",
    "email_draft_uses_structured_facts",
}
PASS_STYLE_PHRASES = ["all passed", "clean pass", "passed successfully", "no failures"]


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
    "Implement Phase 1a",
    "It is allowed to create implementation code",
    "Read-only Regression Evidence Demo",
    "Definition of Done",
    "gh pr merge --auto --squash",
    "fixture-runner --fixture-dir <fixtures/regression> --out-dir <artifacts/runs>",
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


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


def require_fixture_layout() -> None:
    missing = []
    for fixture_id in FIXTURE_IDS:
        for filename in ["fixture.json", "input.log"]:
            path = FIXTURE_DIR / fixture_id / filename
            if not path.is_file():
                missing.append(str(path.relative_to(ROOT)))
    if missing:
        joined = "\n  - ".join(missing)
        raise AssertionError(f"Missing Phase 1a fixture files:\n  - {joined}")


def run_fixture_runner(out_dir: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/fixture_runner.py"),
        "--fixture-dir",
        str(FIXTURE_DIR),
        "--out-dir",
        str(out_dir),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "Fixture runner failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def validate_artifact_packet(base_dir: Path) -> None:
    for fixture_id in FIXTURE_IDS:
        fixture = load_json(FIXTURE_DIR / fixture_id / "fixture.json")
        run_dir = base_dir / fixture_id
        for filename in ARTIFACT_FILES:
            if not (run_dir / filename).is_file():
                raise AssertionError(f"Missing artifact {filename} for fixture {fixture_id} under {base_dir}")

        run = load_json(run_dir / "run.json")
        evidence = load_json(run_dir / "evidence.json")
        result = load_json(run_dir / "regression_result.json")
        report = load_json(run_dir / "verifier_report.json")
        email = (run_dir / "email_draft.md").read_text(encoding="utf-8")
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        expected_verdict = fixture["expectedVerdict"]
        allowed_verdicts = {expected_verdict, "needs_human_check"}
        if expected_verdict == "unknown":
            allowed_verdicts.add("unknown")
        if result["verdict"] not in allowed_verdicts:
            raise AssertionError(
                f"Fixture {fixture_id} produced verdict {result['verdict']}, expected one of {sorted(allowed_verdicts)}"
            )

        if run["status"] != "completed":
            raise AssertionError(f"Fixture {fixture_id} run.json status must be completed")
        if report["status"] != "passed":
            raise AssertionError(f"Fixture {fixture_id} verifier_report.json status must be passed")
        if len(report["fixtureHash"]) != 64:
            raise AssertionError(f"Fixture {fixture_id} fixtureHash must be a sha256 hex digest")

        evidence_items = evidence.get("items", [])
        if not evidence_items:
            raise AssertionError(f"Fixture {fixture_id} evidence.json must contain at least one evidence item")
        evidence_ids = {item["id"] for item in evidence_items}
        result_evidence_ids = set(result["evidenceIds"])
        if not result_evidence_ids:
            raise AssertionError(f"Fixture {fixture_id} regression_result.json must reference evidence ids")
        if not result_evidence_ids <= evidence_ids:
            raise AssertionError(f"Fixture {fixture_id} regression_result.json references unknown evidence ids")

        rule_ids = {item["ruleId"] for item in report["ruleResults"]}
        missing_rules = REQUIRED_REPORT_RULES - rule_ids
        if missing_rules:
            raise AssertionError(f"Fixture {fixture_id} verifier_report.json missing rules: {sorted(missing_rules)}")
        failing_rules = [item for item in report["ruleResults"] if item["status"] == "failed"]
        if failing_rules:
            raise AssertionError(f"Fixture {fixture_id} has failing verifier rules: {failing_rules}")
        if report["blockingFailures"]:
            raise AssertionError(f"Fixture {fixture_id} verifier_report.json must not have blocking failures")

        artifact_types = {item["artifactType"] for item in report["artifactChecks"]}
        if artifact_types != {"evidence", "regression_result", "email_draft"}:
            raise AssertionError(f"Fixture {fixture_id} artifactChecks do not cover all artifact types")
        if any(item["status"] != "passed" for item in report["artifactChecks"]):
            raise AssertionError(f"Fixture {fixture_id} has failing artifact checks")

        lower_email = email.lower()
        if result["id"].lower() not in lower_email:
            raise AssertionError(f"Fixture {fixture_id} email_draft.md must reference regression_result artifact id")
        missing_email_refs = [evidence_id for evidence_id in result["evidenceIds"] if evidence_id.lower() not in lower_email]
        if missing_email_refs:
            raise AssertionError(f"Fixture {fixture_id} email_draft.md missing evidence references: {missing_email_refs}")
        if not fixture["allowAllPassedEmail"] and any(phrase in lower_email for phrase in PASS_STYLE_PHRASES):
            raise AssertionError(f"Fixture {fixture_id} must not generate a pass-style email")

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
        if not required_event_types <= event_types:
            raise AssertionError(f"Fixture {fixture_id} events.jsonl missing required events")


def compare_artifact_packets(expected_dir: Path, actual_dir: Path) -> None:
    for fixture_id in FIXTURE_IDS:
        for filename in ARTIFACT_FILES:
            expected = expected_dir / fixture_id / filename
            actual = actual_dir / fixture_id / filename
            if not filecmp.cmp(expected, actual, shallow=False):
                raise AssertionError(
                    f"Committed artifact {expected.relative_to(ROOT)} differs from deterministic runner output"
                )


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def expect_artifact_validation_failure(
    label: str,
    source_dir: Path,
    scratch_root: Path,
    mutate,
    expected_message_fragment: str,
) -> None:
    tampered_dir = scratch_root / label
    if tampered_dir.exists():
        shutil.rmtree(tampered_dir)
    shutil.copytree(source_dir, tampered_dir)
    mutate(tampered_dir)
    try:
        validate_artifact_packet(tampered_dir)
    except AssertionError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"Forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"Forced-failure case {label} unexpectedly passed validation")


def append_pass_style_email(tampered_dir: Path) -> None:
    email_path = tampered_dir / "failed_tests/email_draft.md"
    email_path.write_text(
        email_path.read_text(encoding="utf-8") + "\nAll passed with no failures.\n",
        encoding="utf-8",
    )


def break_result_evidence_ref(tampered_dir: Path) -> None:
    result_path = tampered_dir / "all_passed/regression_result.json"
    result = load_json(result_path)
    result["evidenceIds"] = ["ev-all_passed-missing"]
    write_json(result_path, result)


def remove_required_report_rule(tampered_dir: Path) -> None:
    report_path = tampered_dir / "all_passed/verifier_report.json"
    report = load_json(report_path)
    report["ruleResults"] = [
        rule
        for rule in report["ruleResults"]
        if rule["ruleId"] != "schema_validation"
    ]
    write_json(report_path, report)


def validate_forced_failure_cases(source_dir: Path, scratch_root: Path) -> None:
    scratch_root.mkdir(parents=True, exist_ok=True)
    expect_artifact_validation_failure(
        "pass_style_negative_email",
        source_dir,
        scratch_root,
        append_pass_style_email,
        "must not generate a pass-style email",
    )
    expect_artifact_validation_failure(
        "broken_evidence_reference",
        source_dir,
        scratch_root,
        break_result_evidence_ref,
        "references unknown evidence ids",
    )
    expect_artifact_validation_failure(
        "missing_verifier_rule",
        source_dir,
        scratch_root,
        remove_required_report_rule,
        "missing rules",
    )


def main() -> None:
    for path in REQUIRED_FILES:
        require_file(path)

    plan = require_file(".cursor/plans/agentic-control-plane.plan.md")
    automation_prompt = require_file("docs/automation/cloud-automation-prompt.md")

    require_markers("plan", plan, PLAN_REQUIRED_MARKERS)
    require_markers("automation prompt", automation_prompt, AUTOMATION_REQUIRED_MARKERS)
    require_fixture_layout()

    with tempfile.TemporaryDirectory() as temp_dir:
        generated_artifacts = Path(temp_dir) / "runs"
        run_fixture_runner(generated_artifacts)
        validate_artifact_packet(generated_artifacts)
        require_forced_failure_checks(generated_artifacts)

        if not ARTIFACT_DIR.is_dir():
            raise AssertionError("Missing committed Phase 1a artifact packet directory: artifacts/runs")
        validate_artifact_packet(ARTIFACT_DIR)
        require_forced_failure_checks(ARTIFACT_DIR)
        compare_artifact_packets(ARTIFACT_DIR, generated_artifacts)
        validate_forced_failure_cases(generated_artifacts, Path(temp_dir) / "forced-failures")

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

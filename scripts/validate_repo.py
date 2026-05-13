from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fixture_runner import load_fixture, stable_hash, verify_artifacts


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
VERDICTS = {"passed", "failed", "incomplete", "warning_or_waiver", "unknown", "needs_human_check"}
EVIDENCE_CLASSES = {
    "all_passed_marker",
    "failure_marker",
    "incomplete_marker",
    "warning_marker",
    "waiver_marker",
    "metadata",
    "ambiguous",
}
EVIDENCE_CONFIDENCE = {"high", "medium", "low"}
RUN_STATUSES = {"completed", "failed"}
STEP_STATUSES = {"completed", "failed", "passed"}
EVENT_TYPES = {
    "run.created",
    "task_spec.generated",
    "capability.read_log.completed",
    "capability.extract_regression_result.completed",
    "artifact.write.completed",
    "verifier.completed",
    "run.completed",
    "run.failed",
}
EVENT_STATUSES = {"started", "completed", "failed"}
RULE_STATUSES = {"passed", "failed", "not_applicable"}
ARTIFACT_TYPES = {"regression_result", "email_draft", "evidence"}
ARTIFACT_STATUSES = {"passed", "failed"}


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


def require_fields(label: str, payload: dict, fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise AssertionError(f"{label} is missing required fields: {missing}")


def require_enum(label: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise AssertionError(f"{label} has invalid value {value!r}; expected one of {sorted(allowed)}")


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
    for fixture_id in FIXTURE_IDS:
        fixture = load_json(FIXTURE_DIR / fixture_id / "fixture.json")
        require_fields(
            f"fixture {fixture_id}",
            fixture,
            ["id", "goal", "inputLogFile", "expectedVerdict", "allowAllPassedEmail"],
        )
        if fixture["id"] != fixture_id:
            raise AssertionError(f"Fixture directory {fixture_id} must match fixture.json id {fixture['id']}")
        if fixture["inputLogFile"] != "input.log":
            raise AssertionError(f"Fixture {fixture_id} must use inputLogFile='input.log'")
        require_enum(f"fixture {fixture_id} expectedVerdict", fixture["expectedVerdict"], VERDICTS)
        if not isinstance(fixture["allowAllPassedEmail"], bool):
            raise AssertionError(f"Fixture {fixture_id} allowAllPassedEmail must be boolean")


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


def validate_rule_results(label: str, rule_results: list[dict]) -> None:
    if not isinstance(rule_results, list) or not rule_results:
        raise AssertionError(f"{label} ruleResults must be a non-empty list")
    for index, rule in enumerate(rule_results):
        rule_label = f"{label} ruleResults[{index}]"
        require_fields(rule_label, rule, ["ruleId", "status", "message", "evidenceIds"])
        require_enum(f"{rule_label}.status", rule["status"], RULE_STATUSES)
        if not isinstance(rule["evidenceIds"], list):
            raise AssertionError(f"{rule_label}.evidenceIds must be a list")


def validate_schema_structure(
    fixture_id: str,
    run: dict,
    evidence: dict,
    result: dict,
    report: dict,
    events: list[dict],
) -> None:
    require_fields(
        f"{fixture_id} run.json",
        run,
        ["schemaVersion", "id", "fixtureId", "task", "taskSpec", "steps", "events", "artifacts", "status", "generatedAt"],
    )
    if run["schemaVersion"] != "run-v1":
        raise AssertionError(f"Fixture {fixture_id} run.json schemaVersion must be run-v1")
    if run["fixtureId"] != fixture_id:
        raise AssertionError(f"Fixture {fixture_id} run.json fixtureId mismatch")
    require_enum(f"{fixture_id} run.status", run["status"], RUN_STATUSES)
    task_spec = run["taskSpec"]
    require_fields(
        f"{fixture_id} taskSpec",
        task_spec,
        [
            "id",
            "goal",
            "inputLogPath",
            "allowedActions",
            "forbiddenActions",
            "successCriteria",
            "requiredEvidence",
            "expectedArtifacts",
            "approvalPoints",
        ],
    )
    if task_spec["allowedActions"] != ["read_log", "extract_regression_result", "write_artifact"]:
        raise AssertionError(f"Fixture {fixture_id} taskSpec allowedActions changed unexpectedly")
    for field in ["forbiddenActions", "successCriteria", "requiredEvidence", "expectedArtifacts", "approvalPoints"]:
        if not isinstance(task_spec[field], list) or not task_spec[field]:
            raise AssertionError(f"Fixture {fixture_id} taskSpec.{field} must be a non-empty list")
    if not isinstance(run["steps"], list) or not run["steps"]:
        raise AssertionError(f"Fixture {fixture_id} run.steps must be a non-empty list")
    for step in run["steps"]:
        require_fields(f"{fixture_id} step", step, ["id", "capability", "status"])
        require_enum(f"{fixture_id} step.status", step["status"], STEP_STATUSES)

    require_fields(f"{fixture_id} evidence.json", evidence, ["schemaVersion", "fixtureId", "items"])
    if evidence["schemaVersion"] != "evidence-list-v1":
        raise AssertionError(f"Fixture {fixture_id} evidence.json schemaVersion must be evidence-list-v1")
    if evidence["fixtureId"] != fixture_id:
        raise AssertionError(f"Fixture {fixture_id} evidence.json fixtureId mismatch")
    if not isinstance(evidence["items"], list) or not evidence["items"]:
        raise AssertionError(f"Fixture {fixture_id} evidence.items must be a non-empty list")
    for index, item in enumerate(evidence["items"]):
        item_label = f"{fixture_id} evidence.items[{index}]"
        require_fields(item_label, item, ["id", "type", "sourcePath", "excerpt", "observedAt", "classification", "confidence"])
        if item["type"] != "log":
            raise AssertionError(f"{item_label}.type must be log")
        require_enum(f"{item_label}.classification", item["classification"], EVIDENCE_CLASSES)
        require_enum(f"{item_label}.confidence", item["confidence"], EVIDENCE_CONFIDENCE)
        if "lineRange" in item:
            line_range = item["lineRange"]
            if (
                not isinstance(line_range, list)
                or len(line_range) != 2
                or not all(isinstance(number, int) and number >= 1 for number in line_range)
                or line_range[0] > line_range[1]
            ):
                raise AssertionError(f"{item_label}.lineRange must be [start, end] positive integers")

    require_fields(
        f"{fixture_id} regression_result.json",
        result,
        ["schemaVersion", "id", "fixtureId", "verdict", "summary", "evidenceIds", "ruleResults", "generatedAt"],
    )
    if result["schemaVersion"] != "regression-result-v1":
        raise AssertionError(f"Fixture {fixture_id} regression_result.json schemaVersion must be regression-result-v1")
    if result["fixtureId"] != fixture_id:
        raise AssertionError(f"Fixture {fixture_id} regression_result.json fixtureId mismatch")
    require_enum(f"{fixture_id} regression_result.verdict", result["verdict"], VERDICTS)
    if not isinstance(result["evidenceIds"], list):
        raise AssertionError(f"Fixture {fixture_id} regression_result.evidenceIds must be a list")
    validate_rule_results(f"{fixture_id} regression_result", result["ruleResults"])

    require_fields(
        f"{fixture_id} verifier_report.json",
        report,
        [
            "schemaVersion",
            "id",
            "runId",
            "fixtureId",
            "status",
            "generatedAt",
            "fixtureHash",
            "ruleResults",
            "artifactChecks",
            "blockingFailures",
            "summary",
        ],
    )
    if report["schemaVersion"] != "verifier-report-v1":
        raise AssertionError(f"Fixture {fixture_id} verifier_report.json schemaVersion must be verifier-report-v1")
    if report["fixtureId"] != fixture_id:
        raise AssertionError(f"Fixture {fixture_id} verifier_report.json fixtureId mismatch")
    require_enum(f"{fixture_id} verifier_report.status", report["status"], ARTIFACT_STATUSES)
    validate_rule_results(f"{fixture_id} verifier_report", report["ruleResults"])
    if not isinstance(report["artifactChecks"], list) or not report["artifactChecks"]:
        raise AssertionError(f"Fixture {fixture_id} verifier_report.artifactChecks must be a non-empty list")
    for index, check in enumerate(report["artifactChecks"]):
        check_label = f"{fixture_id} artifactChecks[{index}]"
        require_fields(check_label, check, ["artifactId", "artifactType", "status", "message"])
        require_enum(f"{check_label}.artifactType", check["artifactType"], ARTIFACT_TYPES)
        require_enum(f"{check_label}.status", check["status"], ARTIFACT_STATUSES)
    if not isinstance(report["blockingFailures"], list):
        raise AssertionError(f"Fixture {fixture_id} verifier_report.blockingFailures must be a list")

    if not isinstance(events, list) or not events:
        raise AssertionError(f"Fixture {fixture_id} events.jsonl must contain events")
    for index, event in enumerate(events):
        event_label = f"{fixture_id} events[{index}]"
        require_fields(event_label, event, ["id", "runId", "fixtureId", "type", "status", "timestamp", "causalRefs"])
        if event["fixtureId"] != fixture_id:
            raise AssertionError(f"{event_label}.fixtureId mismatch")
        require_enum(f"{event_label}.type", event["type"], EVENT_TYPES)
        require_enum(f"{event_label}.status", event["status"], EVENT_STATUSES)
        if not isinstance(event["causalRefs"], list):
            raise AssertionError(f"{event_label}.causalRefs must be a list")
        if "evidenceIds" in event and not isinstance(event["evidenceIds"], list):
            raise AssertionError(f"{event_label}.evidenceIds must be a list")


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

        validate_schema_structure(fixture_id, run, evidence, result, report, events)

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

        if not ARTIFACT_DIR.is_dir():
            raise AssertionError("Missing committed Phase 1a artifact packet directory: artifacts/runs")
        validate_artifact_packet(ARTIFACT_DIR)
        compare_artifact_packets(ARTIFACT_DIR, generated_artifacts)
        validate_forced_failure_cases(generated_artifacts, Path(temp_dir) / "forced-failures")

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

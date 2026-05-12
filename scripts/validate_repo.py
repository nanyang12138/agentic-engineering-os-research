from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


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
VALID_VERDICTS = {"passed", "failed", "incomplete", "warning_or_waiver", "unknown", "needs_human_check"}
VALID_EVIDENCE_CLASSES = {
    "all_passed_marker",
    "failure_marker",
    "incomplete_marker",
    "warning_marker",
    "waiver_marker",
    "metadata",
    "ambiguous",
}
VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_EVENT_TYPES = {
    "run.created",
    "task_spec.generated",
    "capability.read_log.completed",
    "capability.extract_regression_result.completed",
    "artifact.write.completed",
    "verifier.completed",
    "run.completed",
    "run.failed",
}
VALID_EVENT_STATUSES = {"started", "completed", "failed"}
VALID_REPORT_STATUSES = {"passed", "failed"}
VALID_ARTIFACT_TYPES = {"evidence", "regression_result", "email_draft"}
VALID_RULE_STATUSES = {"passed", "failed", "not_applicable"}


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


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def missing_fields(payload: dict, required_fields: set[str]) -> list[str]:
    return sorted(field for field in required_fields if field not in payload)


def require_dict_fields(label: str, payload: Any, required_fields: set[str], failures: list[str]) -> bool:
    if not isinstance(payload, dict):
        failures.append(f"{label} must be an object")
        return False
    missing = missing_fields(payload, required_fields)
    if missing:
        failures.append(f"{label} is missing required fields: {missing}")
        return False
    return True


def require_list(label: str, payload: Any, failures: list[str]) -> bool:
    if not isinstance(payload, list):
        failures.append(f"{label} must be a list")
        return False
    return True


def validate_fixture_schema(fixture_id: str, fixture: dict) -> list[str]:
    failures: list[str] = []
    if not require_dict_fields(
        f"Fixture {fixture_id} fixture.json",
        fixture,
        {"id", "goal", "inputLogFile", "expectedVerdict", "allowAllPassedEmail"},
        failures,
    ):
        return failures
    if fixture["id"] != fixture_id:
        failures.append(f"Fixture {fixture_id} fixture.json id mismatch: {fixture['id']}")
    if fixture["inputLogFile"] != "input.log":
        failures.append(f"Fixture {fixture_id} fixture.json inputLogFile must be input.log")
    if fixture["expectedVerdict"] not in VALID_VERDICTS:
        failures.append(f"Fixture {fixture_id} has invalid expectedVerdict: {fixture['expectedVerdict']}")
    if not isinstance(fixture["allowAllPassedEmail"], bool):
        failures.append(f"Fixture {fixture_id} allowAllPassedEmail must be boolean")
    return failures


def validate_task_spec_schema(fixture_id: str, task_spec: Any) -> list[str]:
    failures: list[str] = []
    if not require_dict_fields(
        f"Fixture {fixture_id} taskSpec",
        task_spec,
        {
            "id",
            "goal",
            "inputLogPath",
            "allowedActions",
            "forbiddenActions",
            "successCriteria",
            "requiredEvidence",
            "expectedArtifacts",
            "approvalPoints",
        },
        failures,
    ):
        return failures
    for field in ["allowedActions", "forbiddenActions", "successCriteria", "requiredEvidence", "expectedArtifacts", "approvalPoints"]:
        require_list(f"Fixture {fixture_id} taskSpec.{field}", task_spec[field], failures)
    return failures


def validate_run_schema(fixture_id: str, run: dict) -> list[str]:
    failures: list[str] = []
    if not require_dict_fields(
        f"Fixture {fixture_id} run.json",
        run,
        {"schemaVersion", "id", "fixtureId", "task", "taskSpec", "steps", "events", "artifacts", "status", "generatedAt"},
        failures,
    ):
        return failures
    if run["schemaVersion"] != "run-v1":
        failures.append(f"Fixture {fixture_id} run.json schemaVersion must be run-v1")
    if run["fixtureId"] != fixture_id:
        failures.append(f"Fixture {fixture_id} run.json fixtureId mismatch: {run['fixtureId']}")
    if run["status"] not in {"completed", "failed"}:
        failures.append(f"Fixture {fixture_id} run.json has invalid status: {run['status']}")
    if not require_list(f"Fixture {fixture_id} run.json.steps", run["steps"], failures):
        return failures
    if not require_list(f"Fixture {fixture_id} run.json.events", run["events"], failures):
        return failures
    if not require_list(f"Fixture {fixture_id} run.json.artifacts", run["artifacts"], failures):
        return failures
    for index, step in enumerate(run["steps"], start=1):
        require_dict_fields(f"Fixture {fixture_id} run.json.steps[{index}]", step, {"id", "capability", "status"}, failures)
    failures.extend(validate_task_spec_schema(fixture_id, run["taskSpec"]))
    return failures


def validate_events_schema(fixture_id: str, run_id: str, events: list[dict]) -> list[str]:
    failures: list[str] = []
    if not events:
        failures.append(f"Fixture {fixture_id} events.jsonl must contain at least one event")
        return failures
    for index, event in enumerate(events, start=1):
        label = f"Fixture {fixture_id} events.jsonl[{index}]"
        if not require_dict_fields(label, event, {"id", "runId", "fixtureId", "type", "status", "timestamp", "causalRefs"}, failures):
            continue
        if event["runId"] != run_id:
            failures.append(f"{label} runId mismatch: {event['runId']}")
        if event["fixtureId"] != fixture_id:
            failures.append(f"{label} fixtureId mismatch: {event['fixtureId']}")
        if event["type"] not in VALID_EVENT_TYPES:
            failures.append(f"{label} has invalid type: {event['type']}")
        if event["status"] not in VALID_EVENT_STATUSES:
            failures.append(f"{label} has invalid status: {event['status']}")
        require_list(f"{label}.causalRefs", event["causalRefs"], failures)
        if "evidenceIds" in event:
            require_list(f"{label}.evidenceIds", event["evidenceIds"], failures)
    return failures


def validate_evidence_schema(fixture_id: str, evidence: dict) -> list[str]:
    failures: list[str] = []
    if not require_dict_fields(f"Fixture {fixture_id} evidence.json", evidence, {"schemaVersion", "fixtureId", "items"}, failures):
        return failures
    if evidence["schemaVersion"] != "evidence-list-v1":
        failures.append(f"Fixture {fixture_id} evidence.json schemaVersion must be evidence-list-v1")
    if evidence["fixtureId"] != fixture_id:
        failures.append(f"Fixture {fixture_id} evidence.json fixtureId mismatch: {evidence['fixtureId']}")
    if not require_list(f"Fixture {fixture_id} evidence.json.items", evidence["items"], failures):
        return failures
    for index, item in enumerate(evidence["items"], start=1):
        label = f"Fixture {fixture_id} evidence.json.items[{index}]"
        if not require_dict_fields(
            label,
            item,
            {"id", "type", "sourcePath", "excerpt", "observedAt", "classification", "confidence"},
            failures,
        ):
            continue
        if item["type"] != "log":
            failures.append(f"{label} type must be log")
        if item["classification"] not in VALID_EVIDENCE_CLASSES:
            failures.append(f"{label} has invalid classification: {item['classification']}")
        if item["confidence"] not in VALID_CONFIDENCE:
            failures.append(f"{label} has invalid confidence: {item['confidence']}")
        if "lineRange" in item:
            line_range = item["lineRange"]
            if (
                not isinstance(line_range, list)
                or len(line_range) != 2
                or not all(isinstance(value, int) for value in line_range)
            ):
                failures.append(f"{label} lineRange must be a two-integer list")
    return failures


def validate_rule_results_schema(fixture_id: str, label: str, rule_results: Any) -> list[str]:
    failures: list[str] = []
    if not require_list(f"Fixture {fixture_id} {label}", rule_results, failures):
        return failures
    for index, item in enumerate(rule_results, start=1):
        item_label = f"Fixture {fixture_id} {label}[{index}]"
        if not require_dict_fields(item_label, item, {"ruleId", "status", "message", "evidenceIds"}, failures):
            continue
        if item["status"] not in VALID_RULE_STATUSES:
            failures.append(f"{item_label} has invalid status: {item['status']}")
        require_list(f"{item_label}.evidenceIds", item["evidenceIds"], failures)
    return failures


def validate_result_schema(fixture_id: str, result: dict) -> list[str]:
    failures: list[str] = []
    if not require_dict_fields(
        f"Fixture {fixture_id} regression_result.json",
        result,
        {"schemaVersion", "id", "fixtureId", "verdict", "summary", "evidenceIds", "ruleResults", "generatedAt"},
        failures,
    ):
        return failures
    if result["schemaVersion"] != "regression-result-v1":
        failures.append(f"Fixture {fixture_id} regression_result.json schemaVersion must be regression-result-v1")
    if result["fixtureId"] != fixture_id:
        failures.append(f"Fixture {fixture_id} regression_result.json fixtureId mismatch: {result['fixtureId']}")
    if result["verdict"] not in VALID_VERDICTS:
        failures.append(f"Fixture {fixture_id} regression_result.json has invalid verdict: {result['verdict']}")
    require_list(f"Fixture {fixture_id} regression_result.json.evidenceIds", result["evidenceIds"], failures)
    failures.extend(validate_rule_results_schema(fixture_id, "regression_result.json.ruleResults", result["ruleResults"]))
    return failures


def validate_report_schema(fixture_id: str, report: dict) -> list[str]:
    failures: list[str] = []
    if not require_dict_fields(
        f"Fixture {fixture_id} verifier_report.json",
        report,
        {
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
        },
        failures,
    ):
        return failures
    if report["schemaVersion"] != "verifier-report-v1":
        failures.append(f"Fixture {fixture_id} verifier_report.json schemaVersion must be verifier-report-v1")
    if report["fixtureId"] != fixture_id:
        failures.append(f"Fixture {fixture_id} verifier_report.json fixtureId mismatch: {report['fixtureId']}")
    if report["status"] not in VALID_REPORT_STATUSES:
        failures.append(f"Fixture {fixture_id} verifier_report.json has invalid status: {report['status']}")
    if not isinstance(report["fixtureHash"], str) or len(report["fixtureHash"]) != 64:
        failures.append(f"Fixture {fixture_id} fixtureHash must be a sha256 hex digest")
    failures.extend(validate_rule_results_schema(fixture_id, "verifier_report.json.ruleResults", report["ruleResults"]))
    if require_list(f"Fixture {fixture_id} verifier_report.json.artifactChecks", report["artifactChecks"], failures):
        for index, item in enumerate(report["artifactChecks"], start=1):
            label = f"Fixture {fixture_id} verifier_report.json.artifactChecks[{index}]"
            if not require_dict_fields(label, item, {"artifactId", "artifactType", "status", "message"}, failures):
                continue
            if item["artifactType"] not in VALID_ARTIFACT_TYPES:
                failures.append(f"{label} has invalid artifactType: {item['artifactType']}")
            if item["status"] not in VALID_REPORT_STATUSES:
                failures.append(f"{label} has invalid status: {item['status']}")
    if require_list(f"Fixture {fixture_id} verifier_report.json.blockingFailures", report["blockingFailures"], failures):
        for index, item in enumerate(report["blockingFailures"], start=1):
            require_dict_fields(
                f"Fixture {fixture_id} verifier_report.json.blockingFailures[{index}]",
                item,
                {"ruleId", "message", "evidenceIds"},
                failures,
            )
    return failures


def verdict_matches_classes(verdict: str, classes: set[str]) -> bool:
    if "failure_marker" in classes:
        return verdict in {"failed", "needs_human_check"}
    if "incomplete_marker" in classes:
        return verdict in {"incomplete", "unknown", "needs_human_check"}
    if {"warning_marker", "waiver_marker"} & classes:
        return verdict in {"warning_or_waiver", "needs_human_check"}
    if "all_passed_marker" in classes and "ambiguous" not in classes:
        return verdict == "passed"
    return verdict in {"unknown", "needs_human_check"}


def verdict_has_matching_evidence(verdict: str, evidence_ids: set[str], evidence_by_id: dict[str, dict]) -> bool:
    classes = {evidence_by_id[evidence_id]["classification"] for evidence_id in evidence_ids if evidence_id in evidence_by_id}
    if verdict == "passed":
        return "all_passed_marker" in classes
    if verdict == "failed":
        return "failure_marker" in classes
    if verdict == "incomplete":
        return "incomplete_marker" in classes
    if verdict == "warning_or_waiver":
        return bool({"warning_marker", "waiver_marker"} & classes)
    return True


def load_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_fixture_artifacts(base_dir: Path, fixture_id: str, fixture: dict) -> list[str]:
    failures: list[str] = []
    failures.extend(validate_fixture_schema(fixture_id, fixture))
    run_dir = base_dir / fixture_id
    for filename in ARTIFACT_FILES:
        if not (run_dir / filename).is_file():
            failures.append(f"Missing artifact {filename} for fixture {fixture_id} under {base_dir}")
    if failures:
        return failures

    run = load_json(run_dir / "run.json")
    evidence = load_json(run_dir / "evidence.json")
    result = load_json(run_dir / "regression_result.json")
    report = load_json(run_dir / "verifier_report.json")
    email = (run_dir / "email_draft.md").read_text(encoding="utf-8")
    events = load_events(run_dir / "events.jsonl")

    failures.extend(validate_run_schema(fixture_id, run))
    failures.extend(validate_evidence_schema(fixture_id, evidence))
    failures.extend(validate_result_schema(fixture_id, result))
    failures.extend(validate_report_schema(fixture_id, report))
    failures.extend(validate_events_schema(fixture_id, run.get("id", ""), events))
    if failures:
        return failures

    expected_verdict = fixture["expectedVerdict"]
    allowed_verdicts = {expected_verdict, "needs_human_check"}
    if expected_verdict == "unknown":
        allowed_verdicts.add("unknown")
    if result["verdict"] not in allowed_verdicts:
        failures.append(f"Fixture {fixture_id} produced verdict {result['verdict']}, expected one of {sorted(allowed_verdicts)}")

    if run["status"] != "completed":
        failures.append(f"Fixture {fixture_id} run.json status must be completed")
    if report["status"] != "passed":
        failures.append(f"Fixture {fixture_id} verifier_report.json status must be passed")

    evidence_items = evidence["items"]
    if not evidence_items:
        failures.append(f"Fixture {fixture_id} evidence.json must contain at least one evidence item")
        return failures
    evidence_by_id = {item["id"]: item for item in evidence_items}
    evidence_ids = set(evidence_by_id)
    result_evidence_ids = set(result["evidenceIds"])
    if not result_evidence_ids:
        failures.append(f"Fixture {fixture_id} regression_result.json must reference evidence ids")
    if not result_evidence_ids <= evidence_ids:
        failures.append(f"Fixture {fixture_id} regression_result.json references unknown evidence ids")
    if not verdict_matches_classes(result["verdict"], {item["classification"] for item in evidence_items}):
        failures.append(
            f"Fixture {fixture_id} verdict {result['verdict']} conflicts with classifications "
            f"{sorted({item['classification'] for item in evidence_items})}"
        )
    if not verdict_has_matching_evidence(result["verdict"], result_evidence_ids, evidence_by_id):
        failures.append(f"Fixture {fixture_id} verdict {result['verdict']} does not reference matching evidence")

    rule_ids = {item["ruleId"] for item in report["ruleResults"]}
    missing_rules = REQUIRED_REPORT_RULES - rule_ids
    if missing_rules:
        failures.append(f"Fixture {fixture_id} verifier_report.json missing rules: {sorted(missing_rules)}")
    failing_rules = [item for item in report["ruleResults"] if item["status"] == "failed"]
    if failing_rules:
        failures.append(f"Fixture {fixture_id} has failing verifier rules: {failing_rules}")
    if report["blockingFailures"]:
        failures.append(f"Fixture {fixture_id} verifier_report.json must not have blocking failures")

    artifact_types = {item["artifactType"] for item in report["artifactChecks"]}
    if artifact_types != VALID_ARTIFACT_TYPES:
        failures.append(f"Fixture {fixture_id} artifactChecks do not cover all artifact types")
    if any(item["status"] != "passed" for item in report["artifactChecks"]):
        failures.append(f"Fixture {fixture_id} has failing artifact checks")

    lower_email = email.lower()
    if result["id"].lower() not in lower_email:
        failures.append(f"Fixture {fixture_id} email_draft.md must reference regression_result artifact id")
    if f"`{result['verdict']}`" not in email:
        failures.append(f"Fixture {fixture_id} email_draft.md must reference the structured verdict")
    missing_email_refs = [evidence_id for evidence_id in result["evidenceIds"] if evidence_id.lower() not in lower_email]
    if missing_email_refs:
        failures.append(f"Fixture {fixture_id} email_draft.md missing evidence references: {missing_email_refs}")
    if not fixture["allowAllPassedEmail"] and any(phrase in lower_email for phrase in PASS_STYLE_PHRASES):
        failures.append(f"Fixture {fixture_id} must not generate a pass-style email")

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
        failures.append(f"Fixture {fixture_id} events.jsonl missing required events")

    return failures


def validate_artifact_packet(base_dir: Path) -> None:
    for fixture_id in FIXTURE_IDS:
        fixture = load_json(FIXTURE_DIR / fixture_id / "fixture.json")
        failures = verify_fixture_artifacts(base_dir, fixture_id, fixture)
        if failures:
            joined = "\n  - ".join(failures)
            raise AssertionError(f"Artifact packet validation failed for {fixture_id}:\n  - {joined}")


def expect_tamper_failure(source_dir: Path, temp_root: Path, label: str, fixture_id: str, expected_fragment: str, mutate) -> None:
    fixture = load_json(FIXTURE_DIR / fixture_id / "fixture.json")
    tampered_root = temp_root / label
    shutil.copytree(source_dir, tampered_root)
    mutate(tampered_root / fixture_id)
    failures = verify_fixture_artifacts(tampered_root, fixture_id, fixture)
    if not failures:
        raise AssertionError(f"Tamper case {label} unexpectedly passed validation")
    if not any(expected_fragment in failure for failure in failures):
        joined = "\n  - ".join(failures)
        raise AssertionError(
            f"Tamper case {label} failed for the wrong reason; expected '{expected_fragment}'.\n"
            f"Actual failures:\n  - {joined}"
        )


def run_forced_failure_validation(source_dir: Path, temp_root: Path) -> None:
    def missing_evidence_ref(run_dir: Path) -> None:
        result_path = run_dir / "regression_result.json"
        result = load_json(result_path)
        result["evidenceIds"] = ["ev-all_passed-missing"]
        write_json(result_path, result)

    def failed_marker_forced_passed(run_dir: Path) -> None:
        result_path = run_dir / "regression_result.json"
        result = load_json(result_path)
        result["verdict"] = "passed"
        result["summary"] = "Tampered summary incorrectly claims a pass."
        write_json(result_path, result)

    def pass_style_email_injection(run_dir: Path) -> None:
        email_path = run_dir / "email_draft.md"
        email_path.write_text(
            email_path.read_text(encoding="utf-8") + "\nAll passed with no failures.\n",
            encoding="utf-8",
        )

    def malformed_schema(run_dir: Path) -> None:
        evidence_path = run_dir / "evidence.json"
        evidence = load_json(evidence_path)
        evidence.pop("schemaVersion", None)
        write_json(evidence_path, evidence)

    expect_tamper_failure(
        source_dir,
        temp_root,
        "missing-evidence-ref",
        "all_passed",
        "references unknown evidence ids",
        missing_evidence_ref,
    )
    expect_tamper_failure(
        source_dir,
        temp_root,
        "failed-marker-forced-passed",
        "failed_tests",
        "conflicts with classifications",
        failed_marker_forced_passed,
    )
    expect_tamper_failure(
        source_dir,
        temp_root,
        "pass-style-email-injection",
        "incomplete_jobs",
        "must not generate a pass-style email",
        pass_style_email_injection,
    )
    expect_tamper_failure(
        source_dir,
        temp_root,
        "malformed-schema",
        "ambiguous_summary",
        "schemaVersion",
        malformed_schema,
    )


def compare_artifact_packets(expected_dir: Path, actual_dir: Path) -> None:
    for fixture_id in FIXTURE_IDS:
        for filename in ARTIFACT_FILES:
            expected = expected_dir / fixture_id / filename
            actual = actual_dir / fixture_id / filename
            if not filecmp.cmp(expected, actual, shallow=False):
                raise AssertionError(
                    f"Committed artifact {expected.relative_to(ROOT)} differs from deterministic runner output"
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
        temp_root = Path(temp_dir)
        generated_artifacts = temp_root / "runs"
        run_fixture_runner(generated_artifacts)
        validate_artifact_packet(generated_artifacts)
        run_forced_failure_validation(generated_artifacts, temp_root / "tamper")

        if not ARTIFACT_DIR.is_dir():
            raise AssertionError("Missing committed Phase 1a artifact packet directory: artifacts/runs")
        validate_artifact_packet(ARTIFACT_DIR)
        compare_artifact_packets(ARTIFACT_DIR, generated_artifacts)

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

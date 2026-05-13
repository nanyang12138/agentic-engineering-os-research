from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


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
EVIDENCE_CLASSIFICATIONS = {
    "all_passed_marker",
    "failure_marker",
    "incomplete_marker",
    "warning_marker",
    "waiver_marker",
    "metadata",
    "ambiguous",
}
EVIDENCE_CONFIDENCE = {"high", "medium", "low"}
RULE_STATUSES = {"passed", "failed", "not_applicable"}
REPORT_STATUSES = {"passed", "failed"}
ARTIFACT_TYPES = {"evidence", "regression_result", "email_draft"}


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


def require_keys(label: str, payload: dict, keys: set[str]) -> None:
    missing = sorted(keys - payload.keys())
    if missing:
        raise AssertionError(f"{label} is missing required fields: {missing}")


def require_string(label: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{label} must be a non-empty string")


def require_string_list(label: str, value: object) -> None:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise AssertionError(f"{label} must be a non-empty list of strings")


def require_enum(label: str, value: object, allowed: set[str]) -> None:
    if value not in allowed:
        raise AssertionError(f"{label} has invalid value {value!r}; expected one of {sorted(allowed)}")


def require_schema_version(label: str, payload: dict, expected: str) -> None:
    actual = payload.get("schemaVersion")
    if actual != expected:
        raise AssertionError(f"{label} schemaVersion must be {expected!r}; got {actual!r}")


def validate_fixture_schema(fixture_id: str, fixture: dict) -> None:
    label = f"fixture {fixture_id}/fixture.json"
    require_keys(label, fixture, {"id", "goal", "inputLogFile", "expectedVerdict", "allowAllPassedEmail"})
    if fixture["id"] != fixture_id:
        raise AssertionError(f"{label} id must match directory name {fixture_id!r}")
    require_string(f"{label}.goal", fixture["goal"])
    if fixture["inputLogFile"] != "input.log":
        raise AssertionError(f"{label}.inputLogFile must be 'input.log'")
    require_enum(f"{label}.expectedVerdict", fixture["expectedVerdict"], VERDICTS)
    if not isinstance(fixture["allowAllPassedEmail"], bool):
        raise AssertionError(f"{label}.allowAllPassedEmail must be a boolean")


def validate_task_spec_schema(fixture_id: str, task_spec: dict) -> None:
    label = f"fixture {fixture_id} run.json.taskSpec"
    require_keys(
        label,
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
    )
    for field in ["id", "goal", "inputLogPath"]:
        require_string(f"{label}.{field}", task_spec[field])
    require_string_list(f"{label}.allowedActions", task_spec["allowedActions"])
    require_string_list(f"{label}.forbiddenActions", task_spec["forbiddenActions"])
    require_string_list(f"{label}.successCriteria", task_spec["successCriteria"])
    require_string_list(f"{label}.requiredEvidence", task_spec["requiredEvidence"])
    require_string_list(f"{label}.expectedArtifacts", task_spec["expectedArtifacts"])
    require_string_list(f"{label}.approvalPoints", task_spec["approvalPoints"])


def validate_rule_result_schema(label: str, rule: dict, evidence_ids: set[str]) -> None:
    require_keys(label, rule, {"ruleId", "status", "message", "evidenceIds"})
    require_string(f"{label}.ruleId", rule["ruleId"])
    require_enum(f"{label}.status", rule["status"], RULE_STATUSES)
    require_string(f"{label}.message", rule["message"])
    if not isinstance(rule["evidenceIds"], list) or any(not isinstance(item, str) for item in rule["evidenceIds"]):
        raise AssertionError(f"{label}.evidenceIds must be a list of strings")
    unknown = set(rule["evidenceIds"]) - evidence_ids
    if unknown:
        raise AssertionError(f"{label}.evidenceIds references unknown evidence ids: {sorted(unknown)}")


def validate_artifact_schema(
    fixture_id: str,
    fixture: dict,
    run: dict,
    evidence: dict,
    result: dict,
    report: dict,
    events: list[dict],
) -> None:
    validate_fixture_schema(fixture_id, fixture)

    run_label = f"fixture {fixture_id} run.json"
    require_schema_version(run_label, run, "run-v1")
    require_keys(run_label, run, {"id", "fixtureId", "task", "taskSpec", "steps", "events", "artifacts", "status", "generatedAt"})
    if run["fixtureId"] != fixture_id:
        raise AssertionError(f"{run_label}.fixtureId must be {fixture_id!r}")
    for field in ["id", "task", "generatedAt"]:
        require_string(f"{run_label}.{field}", run[field])
    require_enum(f"{run_label}.status", run["status"], {"completed", "failed"})
    if not isinstance(run["taskSpec"], dict):
        raise AssertionError(f"{run_label}.taskSpec must be an object")
    validate_task_spec_schema(fixture_id, run["taskSpec"])
    if not isinstance(run["steps"], list) or not run["steps"]:
        raise AssertionError(f"{run_label}.steps must be a non-empty list")
    for index, step in enumerate(run["steps"], start=1):
        step_label = f"{run_label}.steps[{index}]"
        if not isinstance(step, dict):
            raise AssertionError(f"{step_label} must be an object")
        require_keys(step_label, step, {"id", "capability", "status"})
        require_string(f"{step_label}.id", step["id"])
        require_string(f"{step_label}.capability", step["capability"])
        require_enum(f"{step_label}.status", step["status"], {"completed", "failed", "passed"})
    require_string_list(f"{run_label}.events", run["events"])
    require_string_list(f"{run_label}.artifacts", run["artifacts"])

    evidence_label = f"fixture {fixture_id} evidence.json"
    require_schema_version(evidence_label, evidence, "evidence-list-v1")
    require_keys(evidence_label, evidence, {"fixtureId", "items"})
    if evidence["fixtureId"] != fixture_id:
        raise AssertionError(f"{evidence_label}.fixtureId must be {fixture_id!r}")
    if not isinstance(evidence["items"], list) or not evidence["items"]:
        raise AssertionError(f"{evidence_label}.items must be a non-empty list")
    evidence_ids: set[str] = set()
    for index, item in enumerate(evidence["items"], start=1):
        item_label = f"{evidence_label}.items[{index}]"
        if not isinstance(item, dict):
            raise AssertionError(f"{item_label} must be an object")
        require_keys(item_label, item, {"id", "type", "sourcePath", "excerpt", "observedAt", "classification", "confidence"})
        require_string(f"{item_label}.id", item["id"])
        if item["id"] in evidence_ids:
            raise AssertionError(f"{item_label}.id is duplicated: {item['id']!r}")
        evidence_ids.add(item["id"])
        require_enum(f"{item_label}.type", item["type"], {"log"})
        require_string(f"{item_label}.sourcePath", item["sourcePath"])
        require_string(f"{item_label}.excerpt", item["excerpt"])
        require_string(f"{item_label}.observedAt", item["observedAt"])
        require_enum(f"{item_label}.classification", item["classification"], EVIDENCE_CLASSIFICATIONS)
        require_enum(f"{item_label}.confidence", item["confidence"], EVIDENCE_CONFIDENCE)
        if "lineRange" in item:
            line_range = item["lineRange"]
            if (
                not isinstance(line_range, list)
                or len(line_range) != 2
                or any(not isinstance(value, int) for value in line_range)
                or line_range[0] < 1
                or line_range[1] < line_range[0]
            ):
                raise AssertionError(f"{item_label}.lineRange must be [start, end] positive integers")

    result_label = f"fixture {fixture_id} regression_result.json"
    require_schema_version(result_label, result, "regression-result-v1")
    require_keys(result_label, result, {"id", "fixtureId", "verdict", "summary", "evidenceIds", "ruleResults", "generatedAt"})
    if result["fixtureId"] != fixture_id:
        raise AssertionError(f"{result_label}.fixtureId must be {fixture_id!r}")
    for field in ["id", "summary", "generatedAt"]:
        require_string(f"{result_label}.{field}", result[field])
    require_enum(f"{result_label}.verdict", result["verdict"], VERDICTS)
    require_string_list(f"{result_label}.evidenceIds", result["evidenceIds"])
    if set(result["evidenceIds"]) - evidence_ids:
        raise AssertionError(f"{result_label}.evidenceIds references unknown evidence ids")
    if not isinstance(result["ruleResults"], list) or not result["ruleResults"]:
        raise AssertionError(f"{result_label}.ruleResults must be a non-empty list")
    for index, rule in enumerate(result["ruleResults"], start=1):
        if not isinstance(rule, dict):
            raise AssertionError(f"{result_label}.ruleResults[{index}] must be an object")
        validate_rule_result_schema(f"{result_label}.ruleResults[{index}]", rule, evidence_ids)

    report_label = f"fixture {fixture_id} verifier_report.json"
    require_schema_version(report_label, report, "verifier-report-v1")
    require_keys(
        report_label,
        report,
        {"id", "runId", "fixtureId", "status", "generatedAt", "fixtureHash", "ruleResults", "artifactChecks", "blockingFailures", "summary"},
    )
    if report["runId"] != run["id"]:
        raise AssertionError(f"{report_label}.runId must match run.json id")
    if report["fixtureId"] != fixture_id:
        raise AssertionError(f"{report_label}.fixtureId must be {fixture_id!r}")
    for field in ["id", "generatedAt", "fixtureHash", "summary"]:
        require_string(f"{report_label}.{field}", report[field])
    require_enum(f"{report_label}.status", report["status"], REPORT_STATUSES)
    if not isinstance(report["ruleResults"], list) or not report["ruleResults"]:
        raise AssertionError(f"{report_label}.ruleResults must be a non-empty list")
    for index, rule in enumerate(report["ruleResults"], start=1):
        if not isinstance(rule, dict):
            raise AssertionError(f"{report_label}.ruleResults[{index}] must be an object")
        validate_rule_result_schema(f"{report_label}.ruleResults[{index}]", rule, evidence_ids)
    if not isinstance(report["artifactChecks"], list) or not report["artifactChecks"]:
        raise AssertionError(f"{report_label}.artifactChecks must be a non-empty list")
    for index, check in enumerate(report["artifactChecks"], start=1):
        check_label = f"{report_label}.artifactChecks[{index}]"
        if not isinstance(check, dict):
            raise AssertionError(f"{check_label} must be an object")
        require_keys(check_label, check, {"artifactId", "artifactType", "status", "message"})
        require_string(f"{check_label}.artifactId", check["artifactId"])
        require_enum(f"{check_label}.artifactType", check["artifactType"], ARTIFACT_TYPES)
        require_enum(f"{check_label}.status", check["status"], REPORT_STATUSES)
        require_string(f"{check_label}.message", check["message"])
    if not isinstance(report["blockingFailures"], list):
        raise AssertionError(f"{report_label}.blockingFailures must be a list")
    for index, failure in enumerate(report["blockingFailures"], start=1):
        failure_label = f"{report_label}.blockingFailures[{index}]"
        if not isinstance(failure, dict):
            raise AssertionError(f"{failure_label} must be an object")
        require_keys(failure_label, failure, {"ruleId", "message", "evidenceIds"})
        require_string(f"{failure_label}.ruleId", failure["ruleId"])
        require_string(f"{failure_label}.message", failure["message"])
        if not isinstance(failure["evidenceIds"], list) or any(not isinstance(item, str) for item in failure["evidenceIds"]):
            raise AssertionError(f"{failure_label}.evidenceIds must be a list of strings")

    if not events:
        raise AssertionError(f"fixture {fixture_id} events.jsonl must contain events")
    event_ids: set[str] = set()
    for index, event in enumerate(events, start=1):
        event_label = f"fixture {fixture_id} events.jsonl[{index}]"
        if not isinstance(event, dict):
            raise AssertionError(f"{event_label} must be an object")
        require_keys(event_label, event, {"id", "runId", "fixtureId", "type", "status", "timestamp", "causalRefs"})
        require_string(f"{event_label}.id", event["id"])
        if event["id"] in event_ids:
            raise AssertionError(f"{event_label}.id is duplicated: {event['id']!r}")
        event_ids.add(event["id"])
        if event["runId"] != run["id"]:
            raise AssertionError(f"{event_label}.runId must match run.json id")
        if event["fixtureId"] != fixture_id:
            raise AssertionError(f"{event_label}.fixtureId must be {fixture_id!r}")
        require_enum(f"{event_label}.type", event["type"], EVENT_TYPES)
        require_enum(f"{event_label}.status", event["status"], EVENT_STATUSES)
        require_string(f"{event_label}.timestamp", event["timestamp"])
        if not isinstance(event["causalRefs"], list) or any(not isinstance(item, str) for item in event["causalRefs"]):
            raise AssertionError(f"{event_label}.causalRefs must be a list of strings")
        if "evidenceIds" in event and (not isinstance(event["evidenceIds"], list) or set(event["evidenceIds"]) - evidence_ids):
            raise AssertionError(f"{event_label}.evidenceIds must reference evidence.json ids")
    if set(run["events"]) != event_ids:
        raise AssertionError(f"{run_label}.events must match events.jsonl ids")


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
        validate_artifact_schema(fixture_id, fixture, run, evidence, result, report, events)

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


def break_run_schema_version(tampered_dir: Path) -> None:
    run_path = tampered_dir / "all_passed/run.json"
    run = load_json(run_path)
    run["schemaVersion"] = "run-v0"
    write_json(run_path, run)


def break_evidence_classification(tampered_dir: Path) -> None:
    evidence_path = tampered_dir / "all_passed/evidence.json"
    evidence = load_json(evidence_path)
    evidence["items"][0]["classification"] = "unsupported_marker"
    write_json(evidence_path, evidence)


def remove_verifier_report_status(tampered_dir: Path) -> None:
    report_path = tampered_dir / "all_passed/verifier_report.json"
    report = load_json(report_path)
    del report["status"]
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
    expect_artifact_validation_failure(
        "invalid_run_schema_version",
        source_dir,
        scratch_root,
        break_run_schema_version,
        "schemaVersion must be 'run-v1'",
    )
    expect_artifact_validation_failure(
        "invalid_evidence_classification",
        source_dir,
        scratch_root,
        break_evidence_classification,
        "classification has invalid value",
    )
    expect_artifact_validation_failure(
        "missing_verifier_report_status",
        source_dir,
        scratch_root,
        remove_verifier_report_status,
        "missing required fields",
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

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
RUN_STATUSES = {"completed", "failed"}
STEP_STATUSES = {"completed", "passed", "failed"}
EVENT_STATUSES = {"started", "completed", "failed"}
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
VERDICTS = {"passed", "failed", "incomplete", "warning_or_waiver", "unknown", "needs_human_check"}
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
ARTIFACT_TYPES = {"evidence", "regression_result", "email_draft"}
EXPECTED_SCHEMA_VERSIONS = {
    "run": "run-v1",
    "evidence": "evidence-list-v1",
    "regression_result": "regression-result-v1",
    "verifier_report": "verifier-report-v1",
}
TASK_SPEC_ACTIONS = ["read_log", "extract_regression_result", "write_artifact"]
TASK_SPEC_EXPECTED_ARTIFACTS = ["evidence.json", "regression_result.json", "email_draft.md"]


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


def require_keys(label: str, payload: dict, required: set[str]) -> None:
    missing = sorted(required - set(payload))
    if missing:
        raise AssertionError(f"{label} is missing required keys: {missing}")


def require_non_empty_string(label: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{label} must be a non-empty string")


def require_string_list(label: str, value: object, *, allow_empty: bool = True) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise AssertionError(f"{label} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise AssertionError(f"{label} must not be empty")


def require_schema_version(label: str, payload: dict, expected: str) -> None:
    actual = payload.get("schemaVersion")
    if actual != expected:
        raise AssertionError(f"{label} schemaVersion must be {expected}, got {actual!r}")


def validate_fixture_schema(fixture_id: str, fixture: dict) -> None:
    require_keys(
        f"fixture {fixture_id}",
        fixture,
        {"id", "goal", "inputLogFile", "expectedVerdict", "allowAllPassedEmail"},
    )
    if fixture["id"] != fixture_id:
        raise AssertionError(f"fixture {fixture_id} id must match directory name")
    require_non_empty_string(f"fixture {fixture_id}.goal", fixture["goal"])
    if fixture["inputLogFile"] != "input.log":
        raise AssertionError(f"fixture {fixture_id} inputLogFile must be input.log")
    if fixture["expectedVerdict"] not in VERDICTS:
        raise AssertionError(f"fixture {fixture_id} expectedVerdict is invalid")
    if not isinstance(fixture["allowAllPassedEmail"], bool):
        raise AssertionError(f"fixture {fixture_id} allowAllPassedEmail must be boolean")


def validate_task_spec_schema(fixture_id: str, task_spec: dict) -> None:
    require_keys(
        f"fixture {fixture_id} taskSpec",
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
        require_non_empty_string(f"fixture {fixture_id} taskSpec.{field}", task_spec[field])
    if task_spec["allowedActions"] != TASK_SPEC_ACTIONS:
        raise AssertionError(f"fixture {fixture_id} taskSpec.allowedActions must match Phase 1a actions")
    if task_spec["expectedArtifacts"] != TASK_SPEC_EXPECTED_ARTIFACTS:
        raise AssertionError(f"fixture {fixture_id} taskSpec.expectedArtifacts must match Phase 1a artifacts")
    for field in ["forbiddenActions", "successCriteria", "requiredEvidence", "approvalPoints"]:
        require_string_list(f"fixture {fixture_id} taskSpec.{field}", task_spec[field], allow_empty=False)
    if "send_email_requires_human_approval" not in task_spec["approvalPoints"]:
        raise AssertionError(f"fixture {fixture_id} taskSpec must require human approval before sending email")


def validate_steps_schema(fixture_id: str, steps: object) -> None:
    if not isinstance(steps, list) or not steps:
        raise AssertionError(f"fixture {fixture_id} run.steps must be a non-empty list")
    for index, step in enumerate(steps, start=1):
        label = f"fixture {fixture_id} run.steps[{index}]"
        if not isinstance(step, dict):
            raise AssertionError(f"{label} must be an object")
        require_keys(label, step, {"id", "capability", "status"})
        require_non_empty_string(f"{label}.id", step["id"])
        require_non_empty_string(f"{label}.capability", step["capability"])
        if step["status"] not in STEP_STATUSES:
            raise AssertionError(f"{label}.status is invalid")


def validate_run_schema(fixture_id: str, run: dict, events: list[dict]) -> None:
    require_schema_version(f"fixture {fixture_id} run.json", run, EXPECTED_SCHEMA_VERSIONS["run"])
    require_keys(
        f"fixture {fixture_id} run.json",
        run,
        {
            "schemaVersion",
            "id",
            "fixtureId",
            "task",
            "taskSpec",
            "steps",
            "events",
            "artifacts",
            "status",
            "generatedAt",
        },
    )
    if run["fixtureId"] != fixture_id:
        raise AssertionError(f"fixture {fixture_id} run.fixtureId must match fixture id")
    for field in ["id", "task", "generatedAt"]:
        require_non_empty_string(f"fixture {fixture_id} run.{field}", run[field])
    if run["status"] not in RUN_STATUSES:
        raise AssertionError(f"fixture {fixture_id} run.status is invalid")
    validate_task_spec_schema(fixture_id, run["taskSpec"])
    validate_steps_schema(fixture_id, run["steps"])
    require_string_list(f"fixture {fixture_id} run.events", run["events"], allow_empty=False)
    require_string_list(f"fixture {fixture_id} run.artifacts", run["artifacts"], allow_empty=False)
    event_ids = [event["id"] for event in events]
    if run["events"] != event_ids:
        raise AssertionError(f"fixture {fixture_id} run.events must match events.jsonl ids")
    missing_artifacts = set(ARTIFACT_FILES) - set(run["artifacts"])
    if missing_artifacts:
        raise AssertionError(f"fixture {fixture_id} run.artifacts missing {sorted(missing_artifacts)}")


def validate_events_schema(fixture_id: str, run_id: str, events: list[dict]) -> None:
    if not events:
        raise AssertionError(f"fixture {fixture_id} events.jsonl must contain events")
    seen_ids: set[str] = set()
    for index, event in enumerate(events, start=1):
        label = f"fixture {fixture_id} events.jsonl[{index}]"
        require_keys(label, event, {"id", "runId", "fixtureId", "type", "status", "timestamp", "causalRefs"})
        for field in ["id", "runId", "fixtureId", "type", "status", "timestamp"]:
            require_non_empty_string(f"{label}.{field}", event[field])
        if event["id"] in seen_ids:
            raise AssertionError(f"{label}.id must be unique")
        if event["runId"] != run_id:
            raise AssertionError(f"{label}.runId must match run.json id")
        if event["fixtureId"] != fixture_id:
            raise AssertionError(f"{label}.fixtureId must match fixture id")
        if event["type"] not in EVENT_TYPES:
            raise AssertionError(f"{label}.type is invalid")
        if event["status"] not in EVENT_STATUSES:
            raise AssertionError(f"{label}.status is invalid")
        require_string_list(f"{label}.causalRefs", event["causalRefs"])
        unknown_refs = set(event["causalRefs"]) - seen_ids
        if unknown_refs:
            raise AssertionError(f"{label}.causalRefs points to unknown or future events: {sorted(unknown_refs)}")
        seen_ids.add(event["id"])
        for optional_field in ["inputRef", "outputRef"]:
            if optional_field in event:
                require_non_empty_string(f"{label}.{optional_field}", event[optional_field])
        if "evidenceIds" in event:
            require_string_list(f"{label}.evidenceIds", event["evidenceIds"], allow_empty=False)


def validate_evidence_schema(fixture_id: str, evidence: dict) -> set[str]:
    require_schema_version(f"fixture {fixture_id} evidence.json", evidence, EXPECTED_SCHEMA_VERSIONS["evidence"])
    require_keys(f"fixture {fixture_id} evidence.json", evidence, {"schemaVersion", "fixtureId", "items"})
    if evidence["fixtureId"] != fixture_id:
        raise AssertionError(f"fixture {fixture_id} evidence.fixtureId must match fixture id")
    items = evidence["items"]
    if not isinstance(items, list) or not items:
        raise AssertionError(f"fixture {fixture_id} evidence.items must be a non-empty list")
    evidence_ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        label = f"fixture {fixture_id} evidence.items[{index}]"
        if not isinstance(item, dict):
            raise AssertionError(f"{label} must be an object")
        require_keys(label, item, {"id", "type", "sourcePath", "excerpt", "observedAt", "classification", "confidence"})
        for field in ["id", "type", "sourcePath", "excerpt", "observedAt", "classification", "confidence"]:
            require_non_empty_string(f"{label}.{field}", item[field])
        if item["id"] in evidence_ids:
            raise AssertionError(f"{label}.id must be unique")
        evidence_ids.add(item["id"])
        if item["type"] != "log":
            raise AssertionError(f"{label}.type must be log")
        if item["classification"] not in EVIDENCE_CLASSIFICATIONS:
            raise AssertionError(f"{label}.classification is invalid")
        if item["confidence"] not in EVIDENCE_CONFIDENCE:
            raise AssertionError(f"{label}.confidence is invalid")
        if "lineRange" in item:
            line_range = item["lineRange"]
            if (
                not isinstance(line_range, list)
                or len(line_range) != 2
                or not all(isinstance(value, int) and value >= 1 for value in line_range)
                or line_range[0] > line_range[1]
            ):
                raise AssertionError(f"{label}.lineRange must be [start, end] positive integers")
    return evidence_ids


def validate_rule_results_schema(label: str, rule_results: object, evidence_ids: set[str]) -> None:
    if not isinstance(rule_results, list) or not rule_results:
        raise AssertionError(f"{label}.ruleResults must be a non-empty list")
    for index, item in enumerate(rule_results, start=1):
        item_label = f"{label}.ruleResults[{index}]"
        if not isinstance(item, dict):
            raise AssertionError(f"{item_label} must be an object")
        require_keys(item_label, item, {"ruleId", "status", "message", "evidenceIds"})
        for field in ["ruleId", "status", "message"]:
            require_non_empty_string(f"{item_label}.{field}", item[field])
        if item["status"] not in RULE_STATUSES:
            raise AssertionError(f"{item_label}.status is invalid")
        require_string_list(f"{item_label}.evidenceIds", item["evidenceIds"])
        unknown_ids = set(item["evidenceIds"]) - evidence_ids
        if unknown_ids:
            raise AssertionError(f"{item_label}.evidenceIds reference unknown ids: {sorted(unknown_ids)}")


def validate_regression_result_schema(fixture_id: str, result: dict, evidence_ids: set[str]) -> None:
    require_schema_version(
        f"fixture {fixture_id} regression_result.json",
        result,
        EXPECTED_SCHEMA_VERSIONS["regression_result"],
    )
    require_keys(
        f"fixture {fixture_id} regression_result.json",
        result,
        {"schemaVersion", "id", "fixtureId", "verdict", "summary", "evidenceIds", "ruleResults", "generatedAt"},
    )
    if result["fixtureId"] != fixture_id:
        raise AssertionError(f"fixture {fixture_id} regression_result.fixtureId must match fixture id")
    for field in ["id", "summary", "generatedAt"]:
        require_non_empty_string(f"fixture {fixture_id} regression_result.{field}", result[field])
    if result["verdict"] not in VERDICTS:
        raise AssertionError(f"fixture {fixture_id} regression_result.verdict is invalid")
    require_string_list(f"fixture {fixture_id} regression_result.evidenceIds", result["evidenceIds"], allow_empty=False)
    unknown_ids = set(result["evidenceIds"]) - evidence_ids
    if unknown_ids:
        raise AssertionError(f"fixture {fixture_id} regression_result.evidenceIds reference unknown ids: {sorted(unknown_ids)}")
    validate_rule_results_schema(f"fixture {fixture_id} regression_result", result["ruleResults"], evidence_ids)


def validate_artifact_checks_schema(label: str, artifact_checks: object) -> None:
    if not isinstance(artifact_checks, list) or not artifact_checks:
        raise AssertionError(f"{label}.artifactChecks must be a non-empty list")
    for index, item in enumerate(artifact_checks, start=1):
        item_label = f"{label}.artifactChecks[{index}]"
        if not isinstance(item, dict):
            raise AssertionError(f"{item_label} must be an object")
        require_keys(item_label, item, {"artifactId", "artifactType", "status", "message"})
        for field in ["artifactId", "artifactType", "status", "message"]:
            require_non_empty_string(f"{item_label}.{field}", item[field])
        if item["artifactType"] not in ARTIFACT_TYPES:
            raise AssertionError(f"{item_label}.artifactType is invalid")
        if item["status"] not in {"passed", "failed"}:
            raise AssertionError(f"{item_label}.status is invalid")


def validate_blocking_failures_schema(label: str, blocking_failures: object, evidence_ids: set[str]) -> None:
    if not isinstance(blocking_failures, list):
        raise AssertionError(f"{label}.blockingFailures must be a list")
    for index, item in enumerate(blocking_failures, start=1):
        item_label = f"{label}.blockingFailures[{index}]"
        if not isinstance(item, dict):
            raise AssertionError(f"{item_label} must be an object")
        require_keys(item_label, item, {"ruleId", "message", "evidenceIds"})
        require_non_empty_string(f"{item_label}.ruleId", item["ruleId"])
        require_non_empty_string(f"{item_label}.message", item["message"])
        require_string_list(f"{item_label}.evidenceIds", item["evidenceIds"])
        unknown_ids = set(item["evidenceIds"]) - evidence_ids
        if unknown_ids:
            raise AssertionError(f"{item_label}.evidenceIds reference unknown ids: {sorted(unknown_ids)}")


def validate_verifier_report_schema(fixture_id: str, report: dict, run_id: str, evidence_ids: set[str]) -> None:
    require_schema_version(
        f"fixture {fixture_id} verifier_report.json",
        report,
        EXPECTED_SCHEMA_VERSIONS["verifier_report"],
    )
    require_keys(
        f"fixture {fixture_id} verifier_report.json",
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
    )
    if report["runId"] != run_id:
        raise AssertionError(f"fixture {fixture_id} verifier_report.runId must match run.json id")
    if report["fixtureId"] != fixture_id:
        raise AssertionError(f"fixture {fixture_id} verifier_report.fixtureId must match fixture id")
    for field in ["id", "generatedAt", "fixtureHash", "summary"]:
        require_non_empty_string(f"fixture {fixture_id} verifier_report.{field}", report[field])
    if report["status"] not in {"passed", "failed"}:
        raise AssertionError(f"fixture {fixture_id} verifier_report.status is invalid")
    if len(report["fixtureHash"]) != 64 or any(char not in "0123456789abcdef" for char in report["fixtureHash"]):
        raise AssertionError(f"fixture {fixture_id} verifier_report.fixtureHash must be a sha256 hex digest")
    validate_rule_results_schema(f"fixture {fixture_id} verifier_report", report["ruleResults"], evidence_ids)
    validate_artifact_checks_schema(f"fixture {fixture_id} verifier_report", report["artifactChecks"])
    validate_blocking_failures_schema(f"fixture {fixture_id} verifier_report", report["blockingFailures"], evidence_ids)


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
        validate_fixture_schema(fixture_id, fixture)
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
        evidence_ids = validate_evidence_schema(fixture_id, evidence)
        validate_regression_result_schema(fixture_id, result, evidence_ids)
        validate_run_schema(fixture_id, run, events)
        validate_events_schema(fixture_id, run["id"], events)
        validate_verifier_report_schema(fixture_id, report, run["id"], evidence_ids)

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


def expect_artifact_packet_failure(base_dir: Path, label: str, mutate) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        mutated_dir = Path(temp_dir) / "runs"
        shutil.copytree(base_dir, mutated_dir)
        mutate(mutated_dir)
        try:
            validate_artifact_packet(mutated_dir)
        except AssertionError:
            return
        raise AssertionError(f"Schema negative validation did not fail for: {label}")


def validate_schema_negative_cases(base_dir: Path) -> None:
    def corrupt_run_schema(mutated_dir: Path) -> None:
        path = mutated_dir / "all_passed/run.json"
        payload = load_json(path)
        payload["schemaVersion"] = "run-v2"
        write_json(path, payload)

    def corrupt_evidence_classification(mutated_dir: Path) -> None:
        path = mutated_dir / "all_passed/evidence.json"
        payload = load_json(path)
        payload["items"][0]["classification"] = "model_guess"
        write_json(path, payload)

    def remove_verifier_status(mutated_dir: Path) -> None:
        path = mutated_dir / "all_passed/verifier_report.json"
        payload = load_json(path)
        del payload["status"]
        write_json(path, payload)

    expect_artifact_packet_failure(base_dir, "invalid run schemaVersion", corrupt_run_schema)
    expect_artifact_packet_failure(base_dir, "invalid evidence classification", corrupt_evidence_classification)
    expect_artifact_packet_failure(base_dir, "missing verifier status", remove_verifier_status)


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
        generated_artifacts = Path(temp_dir) / "runs"
        run_fixture_runner(generated_artifacts)
        validate_artifact_packet(generated_artifacts)

        if not ARTIFACT_DIR.is_dir():
            raise AssertionError("Missing committed Phase 1a artifact packet directory: artifacts/runs")
        validate_artifact_packet(ARTIFACT_DIR)
        compare_artifact_packets(ARTIFACT_DIR, generated_artifacts)
        validate_schema_negative_cases(generated_artifacts)

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

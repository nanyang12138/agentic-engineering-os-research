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
EVIDENCE_CLASSIFICATIONS = {
    "all_passed_marker",
    "failure_marker",
    "incomplete_marker",
    "warning_marker",
    "waiver_marker",
    "metadata",
    "ambiguous",
}
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


def require_keys(label: str, payload: dict, required_keys: set[str]) -> None:
    missing = sorted(required_keys - set(payload))
    if missing:
        raise AssertionError(f"{label} missing required keys: {missing}")


def require_schema_version(label: str, payload: dict, expected_version: str) -> None:
    actual = payload.get("schemaVersion")
    if actual != expected_version:
        raise AssertionError(f"{label} schemaVersion must be {expected_version!r}, got {actual!r}")


def require_string_list(label: str, values: object, *, allow_empty: bool = False) -> None:
    if (
        not isinstance(values, list)
        or (not allow_empty and not values)
        or not all(isinstance(value, str) and value for value in values)
    ):
        expectation = "a string list" if allow_empty else "a non-empty string list"
        raise AssertionError(f"{label} must be {expectation}")


def validate_rule_results(label: str, rule_results: object, evidence_ids: set[str]) -> None:
    if not isinstance(rule_results, list) or not rule_results:
        raise AssertionError(f"{label} ruleResults must be a non-empty list")
    for index, item in enumerate(rule_results):
        item_label = f"{label}.ruleResults[{index}]"
        if not isinstance(item, dict):
            raise AssertionError(f"{item_label} must be an object")
        require_keys(item_label, item, {"ruleId", "status", "message", "evidenceIds"})
        if item["status"] not in RULE_STATUSES:
            raise AssertionError(f"{item_label}.status has invalid value {item['status']!r}")
        require_string_list(f"{item_label}.evidenceIds", item["evidenceIds"], allow_empty=True)
        unknown_refs = set(item["evidenceIds"]) - evidence_ids
        if unknown_refs:
            raise AssertionError(f"{item_label} references unknown evidence ids: {sorted(unknown_refs)}")


def validate_fixture_schema(fixture_id: str, fixture: dict) -> None:
    require_keys(
        f"fixture {fixture_id}",
        fixture,
        {"id", "goal", "inputLogFile", "expectedVerdict", "allowAllPassedEmail"},
    )
    if fixture["id"] != fixture_id:
        raise AssertionError(f"fixture {fixture_id} id must match its directory name")
    if fixture["inputLogFile"] != "input.log":
        raise AssertionError(f"fixture {fixture_id} inputLogFile must be input.log")
    if fixture["expectedVerdict"] not in VERDICTS:
        raise AssertionError(f"fixture {fixture_id} expectedVerdict has invalid value {fixture['expectedVerdict']!r}")
    if not isinstance(fixture["allowAllPassedEmail"], bool):
        raise AssertionError(f"fixture {fixture_id} allowAllPassedEmail must be boolean")


def validate_task_spec_schema(fixture_id: str, task_spec: dict) -> None:
    require_keys(
        f"{fixture_id} taskSpec",
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
    if task_spec["allowedActions"] != ["read_log", "extract_regression_result", "write_artifact"]:
        raise AssertionError(f"{fixture_id} taskSpec allowedActions are not the Phase 1a fixed set")
    require_string_list(f"{fixture_id} taskSpec.forbiddenActions", task_spec["forbiddenActions"])
    require_string_list(f"{fixture_id} taskSpec.successCriteria", task_spec["successCriteria"])
    require_string_list(f"{fixture_id} taskSpec.requiredEvidence", task_spec["requiredEvidence"])
    if task_spec["expectedArtifacts"] != ["evidence.json", "regression_result.json", "email_draft.md"]:
        raise AssertionError(f"{fixture_id} taskSpec expectedArtifacts are not the Phase 1a fixed set")
    if task_spec["approvalPoints"] != ["send_email_requires_human_approval"]:
        raise AssertionError(f"{fixture_id} taskSpec approvalPoints must include the send-email human gate")


def validate_run_schema(fixture_id: str, run: dict) -> None:
    require_schema_version(f"{fixture_id} run.json", run, "run-v1")
    require_keys(
        f"{fixture_id} run.json",
        run,
        {"id", "fixtureId", "task", "taskSpec", "steps", "events", "artifacts", "status", "generatedAt"},
    )
    if run["fixtureId"] != fixture_id:
        raise AssertionError(f"{fixture_id} run.json fixtureId mismatch")
    if run["status"] not in {"completed", "failed"}:
        raise AssertionError(f"{fixture_id} run.json status has invalid value {run['status']!r}")
    validate_task_spec_schema(fixture_id, run["taskSpec"])
    if not isinstance(run["steps"], list) or len(run["steps"]) != 4:
        raise AssertionError(f"{fixture_id} run.json must contain the four Phase 1a steps")
    for step in run["steps"]:
        require_keys(f"{fixture_id} run step", step, {"id", "capability", "status"})
        if step["status"] not in {"completed", "passed", "failed"}:
            raise AssertionError(f"{fixture_id} run step has invalid status {step['status']!r}")
    require_string_list(f"{fixture_id} run.events", run["events"])
    require_string_list(f"{fixture_id} run.artifacts", run["artifacts"])


def validate_evidence_schema(fixture_id: str, evidence: dict) -> set[str]:
    require_schema_version(f"{fixture_id} evidence.json", evidence, "evidence-list-v1")
    require_keys(f"{fixture_id} evidence.json", evidence, {"fixtureId", "items"})
    if evidence["fixtureId"] != fixture_id:
        raise AssertionError(f"{fixture_id} evidence.json fixtureId mismatch")
    items = evidence["items"]
    if not isinstance(items, list) or not items:
        raise AssertionError(f"{fixture_id} evidence.json items must be a non-empty list")
    evidence_ids = set()
    for index, item in enumerate(items):
        item_label = f"{fixture_id} evidence.items[{index}]"
        if not isinstance(item, dict):
            raise AssertionError(f"{item_label} must be an object")
        require_keys(item_label, item, {"id", "type", "sourcePath", "excerpt", "observedAt", "classification", "confidence"})
        if item["id"] in evidence_ids:
            raise AssertionError(f"{item_label} duplicates evidence id {item['id']!r}")
        evidence_ids.add(item["id"])
        if item["type"] != "log":
            raise AssertionError(f"{item_label}.type must be 'log'")
        if item["classification"] not in EVIDENCE_CLASSIFICATIONS:
            raise AssertionError(f"{item_label}.classification has invalid value {item['classification']!r}")
        if item["confidence"] not in {"high", "medium", "low"}:
            raise AssertionError(f"{item_label}.confidence has invalid value {item['confidence']!r}")
        if "lineRange" in item:
            line_range = item["lineRange"]
            if (
                not isinstance(line_range, list)
                or len(line_range) != 2
                or not all(isinstance(value, int) and value >= 1 for value in line_range)
                or line_range[0] > line_range[1]
            ):
                raise AssertionError(f"{item_label}.lineRange must be [start, end] positive integers")
    return evidence_ids


def validate_result_schema(fixture_id: str, result: dict, evidence_ids: set[str]) -> None:
    require_schema_version(f"{fixture_id} regression_result.json", result, "regression-result-v1")
    require_keys(
        f"{fixture_id} regression_result.json",
        result,
        {"id", "fixtureId", "verdict", "summary", "evidenceIds", "ruleResults", "generatedAt"},
    )
    if result["fixtureId"] != fixture_id:
        raise AssertionError(f"{fixture_id} regression_result.json fixtureId mismatch")
    if result["verdict"] not in VERDICTS:
        raise AssertionError(f"{fixture_id} regression_result.json verdict has invalid value {result['verdict']!r}")
    require_string_list(f"{fixture_id} regression_result.evidenceIds", result["evidenceIds"])
    unknown_refs = set(result["evidenceIds"]) - evidence_ids
    if unknown_refs:
        raise AssertionError(f"{fixture_id} regression_result.json references unknown evidence ids: {sorted(unknown_refs)}")
    validate_rule_results(f"{fixture_id} regression_result.json", result["ruleResults"], evidence_ids)


def validate_verifier_report_schema(fixture_id: str, report: dict, evidence_ids: set[str]) -> None:
    require_schema_version(f"{fixture_id} verifier_report.json", report, "verifier-report-v1")
    require_keys(
        f"{fixture_id} verifier_report.json",
        report,
        {
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
    if report["fixtureId"] != fixture_id:
        raise AssertionError(f"{fixture_id} verifier_report.json fixtureId mismatch")
    if report["status"] not in {"passed", "failed"}:
        raise AssertionError(f"{fixture_id} verifier_report.json status has invalid value {report['status']!r}")
    if not isinstance(report["fixtureHash"], str) or len(report["fixtureHash"]) != 64:
        raise AssertionError(f"{fixture_id} verifier_report.json fixtureHash must be a sha256 hex digest")
    validate_rule_results(f"{fixture_id} verifier_report.json", report["ruleResults"], evidence_ids)
    if not isinstance(report["artifactChecks"], list) or not report["artifactChecks"]:
        raise AssertionError(f"{fixture_id} verifier_report.json artifactChecks must be a non-empty list")
    for index, item in enumerate(report["artifactChecks"]):
        item_label = f"{fixture_id} verifier_report.artifactChecks[{index}]"
        require_keys(item_label, item, {"artifactId", "artifactType", "status", "message"})
        if item["artifactType"] not in ARTIFACT_TYPES:
            raise AssertionError(f"{item_label}.artifactType has invalid value {item['artifactType']!r}")
        if item["status"] not in {"passed", "failed"}:
            raise AssertionError(f"{item_label}.status has invalid value {item['status']!r}")
    if not isinstance(report["blockingFailures"], list):
        raise AssertionError(f"{fixture_id} verifier_report.json blockingFailures must be a list")
    for index, item in enumerate(report["blockingFailures"]):
        item_label = f"{fixture_id} verifier_report.blockingFailures[{index}]"
        require_keys(item_label, item, {"ruleId", "message", "evidenceIds"})
        require_string_list(f"{item_label}.evidenceIds", item["evidenceIds"], allow_empty=True)


def validate_events_schema(fixture_id: str, events: list[dict], run: dict, evidence_ids: set[str]) -> None:
    if len(events) != len(run["events"]):
        raise AssertionError(f"{fixture_id} events.jsonl count must match run.json events")
    seen_event_ids = set()
    for index, event in enumerate(events):
        event_label = f"{fixture_id} events[{index}]"
        require_keys(event_label, event, {"id", "runId", "fixtureId", "type", "status", "timestamp", "causalRefs"})
        if event["id"] in seen_event_ids:
            raise AssertionError(f"{event_label} duplicates event id {event['id']!r}")
        seen_event_ids.add(event["id"])
        if event["id"] != run["events"][index]:
            raise AssertionError(f"{event_label} order must match run.json events")
        if event["runId"] != run["id"] or event["fixtureId"] != fixture_id:
            raise AssertionError(f"{event_label} runId or fixtureId mismatch")
        if event["type"] not in EVENT_TYPES:
            raise AssertionError(f"{event_label}.type has invalid value {event['type']!r}")
        if event["status"] not in EVENT_STATUSES:
            raise AssertionError(f"{event_label}.status has invalid value {event['status']!r}")
        if "evidenceIds" in event:
            require_string_list(f"{event_label}.evidenceIds", event["evidenceIds"])
            unknown_refs = set(event["evidenceIds"]) - evidence_ids
            if unknown_refs:
                raise AssertionError(f"{event_label} references unknown evidence ids: {sorted(unknown_refs)}")


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

        validate_fixture_schema(fixture_id, fixture)
        validate_run_schema(fixture_id, run)
        evidence_ids = validate_evidence_schema(fixture_id, evidence)
        validate_result_schema(fixture_id, result, evidence_ids)
        validate_verifier_report_schema(fixture_id, report, evidence_ids)
        validate_events_schema(fixture_id, events, run, evidence_ids)

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
        validate_schema_negative_cases(generated_artifacts)

        if not ARTIFACT_DIR.is_dir():
            raise AssertionError("Missing committed Phase 1a artifact packet directory: artifacts/runs")
        validate_artifact_packet(ARTIFACT_DIR)
        compare_artifact_packets(ARTIFACT_DIR, generated_artifacts)
        validate_forced_failure_cases(generated_artifacts, Path(temp_dir) / "forced-failures")

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

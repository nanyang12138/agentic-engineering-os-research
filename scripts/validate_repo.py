from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from capability_contract import (
    PHASE3_CAPABILITY_NAMES,
    build_capability_catalog,
    capability_ref,
    validate_capability_catalog,
    validate_capability_envelope,
)
from context_pack import build_context_pack, validate_context_pack
from fixture_runner import load_fixture, stable_hash, verify_artifacts
from task_spec import TASK_SPEC_SCHEMA_VERSION, build_regression_task_spec, validate_regression_task_spec


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures/regression"
ARTIFACT_DIR = ROOT / "artifacts/runs"
CAPABILITY_CATALOG_PATH = ROOT / "artifacts/capabilities/phase3_capability_catalog.json"
CONTEXT_PACK_DIR = ROOT / "artifacts/context"
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
    "scripts/local_readonly_runner.py",
    "scripts/task_spec.py",
    "scripts/capability_contract.py",
    "scripts/context_pack.py",
    "artifacts/capabilities/phase3_capability_catalog.json",
]

PLAN_REQUIRED_MARKERS = [
    "Read-only Regression Evidence Demo",
    "fixture-runner --fixture-dir <fixtures/regression> --out-dir <artifacts/runs>",
    "RegressionTaskSpecV1",
    "regression-task-spec-v1",
    "capability-metadata-v1",
    "capability-envelope-v1",
    "phase3_capability_catalog.json",
    "context-pack-v1",
    "ContextPackV1",
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


def run_local_readonly_runner(
    out_dir: Path,
    task_spec_path: Path | None = None,
    context_pack_path: Path | None = None,
) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/local_readonly_runner.py"),
        "--log-path",
        str(FIXTURE_DIR / "all_passed/input.log"),
        "--goal",
        "Confirm whether the m2b_lec_regr regression passed and draft a grounded English status email.",
        "--out-dir",
        str(out_dir),
    ]
    if task_spec_path:
        command.extend(["--task-spec-path", str(task_spec_path)])
    if context_pack_path:
        command.extend(["--context-pack-path", str(context_pack_path)])
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "Local read-only runner failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_local_readonly_context_pack_failure(context_pack_path: Path, task_spec_path: Path, scratch_root: Path) -> None:
    scratch_root.mkdir(parents=True, exist_ok=True)
    tampered_pack_path = scratch_root / "context-pack-without-log-excerpts.json"
    tampered = load_json(context_pack_path)
    tampered["contextItems"] = [
        item
        for item in tampered["contextItems"]
        if item.get("kind") != "log_excerpt"
    ]
    write_json(tampered_pack_path, tampered)

    command = [
        sys.executable,
        str(ROOT / "scripts/local_readonly_runner.py"),
        "--log-path",
        str(FIXTURE_DIR / "all_passed/input.log"),
        "--goal",
        "Confirm whether the m2b_lec_regr regression passed and draft a grounded English status email.",
        "--out-dir",
        str(scratch_root / "should-not-run"),
        "--task-spec-path",
        str(task_spec_path),
        "--context-pack-path",
        str(tampered_pack_path),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode == 0:
        raise AssertionError("Local read-only runner accepted evidence not declared by ContextPack")
    output = result.stdout + result.stderr
    if "ContextPack must declare at least one log_excerpt context item" not in output:
        raise AssertionError(
            "Local read-only runner rejected a tampered ContextPack for the wrong reason.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_local_readonly_task_spec_failure(task_spec_path: Path, scratch_root: Path) -> None:
    scratch_root.mkdir(parents=True, exist_ok=True)
    mismatched_spec_path = scratch_root / "mismatched-task-spec.json"
    mismatched = load_json(task_spec_path)
    mismatched["inputLogPath"] = str(FIXTURE_DIR / "failed_tests/input.log")
    write_json(mismatched_spec_path, mismatched)

    command = [
        sys.executable,
        str(ROOT / "scripts/local_readonly_runner.py"),
        "--log-path",
        str(FIXTURE_DIR / "all_passed/input.log"),
        "--goal",
        "Confirm whether the m2b_lec_regr regression passed and draft a grounded English status email.",
        "--out-dir",
        str(scratch_root / "should-not-run"),
        "--task-spec-path",
        str(mismatched_spec_path),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode == 0:
        raise AssertionError("Local read-only runner accepted a TaskSpec with the wrong inputLogPath")
    output = result.stdout + result.stderr
    if "TaskSpec inputLogPath must match requested --log-path" not in output:
        raise AssertionError(
            "Local read-only runner rejected a mismatched TaskSpec for the wrong reason.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def run_task_spec_builder(out_file: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/task_spec.py"),
        "--goal",
        "Confirm whether the m2b_lec_regr regression passed and draft a grounded English status email.",
        "--input-log-path",
        str(FIXTURE_DIR / "all_passed/input.log"),
        "--out",
        str(out_file),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "TaskSpec builder failed.\n"
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


def validate_artifact_consistency(fixture_id: str, fixture: dict, evidence: dict, result: dict, report: dict, email: str) -> None:
    evidence_ids = {item["id"] for item in evidence["items"]}
    unknown_result_refs = [evidence_id for evidence_id in result["evidenceIds"] if evidence_id not in evidence_ids]
    if unknown_result_refs:
        raise AssertionError(f"Fixture {fixture_id} regression_result references unknown evidence ids: {unknown_result_refs}")

    report_rule_ids = {rule["ruleId"] for rule in report["ruleResults"]}
    missing_rules = sorted(REQUIRED_REPORT_RULES - report_rule_ids)
    if missing_rules:
        raise AssertionError(f"Fixture {fixture_id} verifier_report is missing rules: {missing_rules}")

    if not fixture["allowAllPassedEmail"] and any(phrase in email.lower() for phrase in PASS_STYLE_PHRASES):
        raise AssertionError("Negative or uncertain fixtures must not generate a pass-style email")


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
        [
            "schemaVersion",
            "id",
            "fixtureId",
            "task",
            "taskSpec",
            "capabilityEnvelope",
            "steps",
            "events",
            "artifacts",
            "status",
            "generatedAt",
        ],
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
            "schemaVersion",
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
    if task_spec["schemaVersion"] != TASK_SPEC_SCHEMA_VERSION:
        raise AssertionError(f"Fixture {fixture_id} taskSpec schemaVersion must be {TASK_SPEC_SCHEMA_VERSION}")
    try:
        validate_regression_task_spec(task_spec)
    except ValueError as exc:
        raise AssertionError(f"Fixture {fixture_id} taskSpec failed validation: {exc}") from exc
    try:
        validate_capability_envelope(run["capabilityEnvelope"], PHASE3_CAPABILITY_NAMES)
    except ValueError as exc:
        raise AssertionError(f"Fixture {fixture_id} capabilityEnvelope failed validation: {exc}") from exc
    if not isinstance(run["steps"], list) or not run["steps"]:
        raise AssertionError(f"Fixture {fixture_id} run.steps must be a non-empty list")
    for step in run["steps"]:
        require_fields(f"{fixture_id} step", step, ["id", "capability", "capabilityRef", "status"])
        require_enum(f"{fixture_id} step.status", step["status"], STEP_STATUSES)
        if step["capability"] in PHASE3_CAPABILITY_NAMES:
            if step["capabilityRef"] != capability_ref(step["capability"]):
                raise AssertionError(f"Fixture {fixture_id} step {step['id']} capabilityRef mismatch")

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
        expected_capability = None
        if event["type"] == "capability.read_log.completed":
            expected_capability = "read_log"
        elif event["type"] == "capability.extract_regression_result.completed":
            expected_capability = "extract_regression_result"
        elif event["type"] == "artifact.write.completed":
            expected_capability = "write_artifact"
        elif event["type"] == "verifier.completed":
            expected_capability = "rule_verifier"
        if expected_capability:
            require_fields(event_label, event, ["capability", "capabilityRef"])
            if event["capability"] != expected_capability:
                raise AssertionError(f"{event_label}.capability must be {expected_capability}")
            if event["capabilityRef"] != capability_ref(expected_capability):
                raise AssertionError(f"{event_label}.capabilityRef mismatch")


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
        validate_artifact_consistency(fixture_id, fixture, evidence, result, report, email)

        expected_verdict = fixture["expectedVerdict"]
        allowed_verdicts = {expected_verdict, "needs_human_check"}
        if expected_verdict == "unknown":
            allowed_verdicts.add("unknown")
        if result["verdict"] not in allowed_verdicts:
            raise AssertionError(
                f"Fixture {fixture_id} produced verdict {result['verdict']}, expected one of {sorted(allowed_verdicts)}"
            )


def validate_committed_capability_catalog() -> None:
    catalog = load_json(CAPABILITY_CATALOG_PATH)
    try:
        validate_capability_catalog(catalog, PHASE3_CAPABILITY_NAMES)
    except ValueError as exc:
        raise AssertionError(f"Committed Phase 3 capability catalog failed validation: {exc}") from exc

    expected = build_capability_catalog()
    if catalog != expected:
        raise AssertionError("Committed Phase 3 capability catalog differs from deterministic generated catalog")

    tampered = json.loads(json.dumps(catalog))
    tampered["capabilityEnvelope"]["items"] = [
        item
        for item in tampered["capabilityEnvelope"]["items"]
        if item.get("name") != "rule_verifier"
    ]
    try:
        validate_capability_catalog(tampered, PHASE3_CAPABILITY_NAMES)
    except ValueError as exc:
        if "Capability envelope names must equal" not in str(exc):
            raise AssertionError(f"Capability catalog forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("Capability catalog forced-failure unexpectedly accepted missing rule_verifier")


def validate_committed_context_packs() -> None:
    if not CONTEXT_PACK_DIR.is_dir():
        raise AssertionError("Missing committed Phase 4 ContextPack directory: artifacts/context")
    for fixture_id in FIXTURE_IDS:
        context_pack_path = CONTEXT_PACK_DIR / fixture_id / "context_pack.json"
        if not context_pack_path.is_file():
            raise AssertionError(f"Missing committed ContextPack artifact: {context_pack_path.relative_to(ROOT)}")

        committed = load_json(context_pack_path)
        try:
            validate_context_pack(committed, ROOT)
        except ValueError as exc:
            raise AssertionError(f"Committed ContextPack {fixture_id} failed validation: {exc}") from exc

        expected = build_context_pack(ARTIFACT_DIR / fixture_id, FIXTURE_DIR / fixture_id, CAPABILITY_CATALOG_PATH)
        if committed != expected:
            raise AssertionError(f"Committed ContextPack {fixture_id} differs from deterministic builder output")

    tampered = load_json(CONTEXT_PACK_DIR / "all_passed/context_pack.json")
    tampered["sources"] = [
        source
        for source in tampered["sources"]
        if source.get("role") != "capability_catalog"
    ]
    try:
        validate_context_pack(tampered, ROOT)
    except ValueError as exc:
        if "missing required source roles" not in str(exc):
            raise AssertionError(f"ContextPack missing-source forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("ContextPack missing-source forced-failure unexpectedly passed validation")

    tampered = load_json(CONTEXT_PACK_DIR / "all_passed/context_pack.json")
    for source in tampered["sources"]:
        if source.get("role") == "regression_log":
            source["contentHash"] = "0" * 64
            break
    try:
        validate_context_pack(tampered, ROOT)
    except ValueError as exc:
        if "source hash mismatch" not in str(exc):
            raise AssertionError(f"ContextPack hash forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("ContextPack hash forced-failure unexpectedly passed validation")


def run_context_pack_builder(out_dir: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/context_pack.py"),
        "--run-root",
        str(ARTIFACT_DIR),
        "--fixture-root",
        str(FIXTURE_DIR),
        "--capability-catalog",
        str(CAPABILITY_CATALOG_PATH),
        "--out-dir",
        str(out_dir),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "ContextPack builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def compare_context_packs(expected_dir: Path, actual_dir: Path) -> None:
    for fixture_id in FIXTURE_IDS:
        expected = expected_dir / fixture_id / "context_pack.json"
        actual = actual_dir / fixture_id / "context_pack.json"
        if not actual.is_file():
            raise AssertionError(f"ContextPack builder did not emit {actual.relative_to(actual_dir)}")
        if not filecmp.cmp(expected, actual, shallow=False):
            raise AssertionError(
                f"Committed ContextPack {expected.relative_to(ROOT)} differs from deterministic CLI output"
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


def remove_capability_metadata_field(tampered_dir: Path) -> None:
    run_path = tampered_dir / "all_passed/run.json"
    run = load_json(run_path)
    del run["capabilityEnvelope"]["items"][0]["permission"]
    write_json(run_path, run)


def add_external_capability_side_effect(tampered_dir: Path) -> None:
    run_path = tampered_dir / "all_passed/run.json"
    run = load_json(run_path)
    for item in run["capabilityEnvelope"]["items"]:
        if item["name"] == "write_artifact":
            item["sideEffect"] = True
            break
    write_json(run_path, run)


def remove_rule_verifier_step_ref(tampered_dir: Path) -> None:
    run_path = tampered_dir / "all_passed/run.json"
    run = load_json(run_path)
    for step in run["steps"]:
        if step["capability"] == "rule_verifier":
            del step["capabilityRef"]
            break
    write_json(run_path, run)


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
        "missing_capability_permission",
        source_dir,
        scratch_root,
        remove_capability_metadata_field,
        "capabilityEnvelope failed validation",
    )
    expect_artifact_validation_failure(
        "external_capability_side_effect",
        source_dir,
        scratch_root,
        add_external_capability_side_effect,
        "must not declare external side effects",
    )
    expect_artifact_validation_failure(
        "missing_rule_verifier_capability_ref",
        source_dir,
        scratch_root,
        remove_rule_verifier_step_ref,
        "missing required fields",
    )


def expect_task_spec_validation_failure(label: str, task_spec: dict, expected_message_fragment: str) -> None:
    try:
        validate_regression_task_spec(task_spec)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"TaskSpec forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"TaskSpec forced-failure case {label} unexpectedly passed validation")


def validate_task_spec_gate(out_file: Path) -> None:
    run_task_spec_builder(out_file)
    task_spec = load_json(out_file)
    validate_regression_task_spec(task_spec)

    built_spec = build_regression_task_spec(
        "Confirm whether the m2b_lec_regr regression passed and draft a grounded English status email.",
        FIXTURE_DIR / "all_passed/input.log",
    )
    validate_regression_task_spec(built_spec)

    for field in ["allowedActions", "forbiddenActions", "successCriteria", "requiredEvidence", "approvalPoints"]:
        tampered = dict(built_spec)
        del tampered[field]
        expect_task_spec_validation_failure(f"missing_{field}", tampered, "missing required fields")


def validate_local_readonly_runner(out_dir: Path, task_spec_path: Path) -> None:
    context_pack_path = CONTEXT_PACK_DIR / "all_passed/context_pack.json"
    run_local_readonly_runner(out_dir, task_spec_path, context_pack_path)
    run_dir = out_dir / "all_passed"
    for filename in ARTIFACT_FILES:
        if not (run_dir / filename).is_file():
            raise AssertionError(f"Missing local read-only runner artifact: {filename}")

    run = load_json(run_dir / "run.json")
    expected_task_spec = load_json(task_spec_path)
    if run["taskSpec"] != expected_task_spec:
        raise AssertionError("Local read-only runner run.json must use the provided TaskSpec unchanged")
    evidence = load_json(run_dir / "evidence.json")
    result = load_json(run_dir / "regression_result.json")
    report = load_json(run_dir / "verifier_report.json")
    email = (run_dir / "email_draft.md").read_text(encoding="utf-8")
    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    validate_schema_structure("all_passed", run, evidence, result, report, events)
    if result["verdict"] != "passed":
        raise AssertionError(f"Local read-only runner expected passed verdict, got {result['verdict']}")
    if report["status"] != "passed":
        raise AssertionError(f"Local read-only runner verifier_report status must be passed, got {report['status']}")
    if result["id"].lower() not in email.lower():
        raise AssertionError("Local read-only runner email must reference regression_result artifact id")
    expect_local_readonly_task_spec_failure(task_spec_path, out_dir / "forced-failures")
    expect_local_readonly_context_pack_failure(context_pack_path, task_spec_path, out_dir / "forced-failures")


def main() -> None:
    for path in REQUIRED_FILES:
        require_file(path)

    plan = require_file(".cursor/plans/agentic-control-plane.plan.md")
    automation_prompt = require_file("docs/automation/cloud-automation-prompt.md")

    require_markers("plan", plan, PLAN_REQUIRED_MARKERS)
    require_markers("automation prompt", automation_prompt, AUTOMATION_REQUIRED_MARKERS)
    require_fixture_layout()
    validate_committed_capability_catalog()
    validate_committed_context_packs()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        generated_artifacts = temp_root / "runs"
        run_fixture_runner(generated_artifacts)
        validate_artifact_packet(generated_artifacts)

        if not ARTIFACT_DIR.is_dir():
            raise AssertionError("Missing committed Phase 1a artifact packet directory: artifacts/runs")
        validate_artifact_packet(ARTIFACT_DIR)
        compare_artifact_packets(ARTIFACT_DIR, generated_artifacts)
        validate_forced_failure_cases(generated_artifacts, Path(temp_dir) / "forced-failures")
        task_spec_path = Path(temp_dir) / "task-spec.json"
        validate_task_spec_gate(task_spec_path)
        validate_local_readonly_runner(Path(temp_dir) / "local-readonly", task_spec_path)
        generated_context_packs = temp_root / "context"
        run_context_pack_builder(generated_context_packs)
        compare_context_packs(CONTEXT_PACK_DIR, generated_context_packs)

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

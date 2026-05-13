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
from computer_runtime import (
    POLICY_MANIFEST_ARTIFACT_PATH,
    REDACTION_POLICY_ARTIFACT_PATH,
    CONTRACT_ARTIFACT_PATH,
    OBSERVATION_ARTIFACT_PATH,
    build_adapter_policy_manifest,
    build_computer_runtime_contract,
    build_observation_redaction_policy,
    build_trajectory_observation,
    validate_adapter_policy_manifest,
    validate_computer_runtime_contract,
    validate_observation_redaction_policy,
    validate_trajectory_observation,
)
from evidence_list import (
    EVIDENCE_CLASSES,
    EVIDENCE_CONFIDENCE,
    validate_evidence_list,
)
from evaluation_report import (
    REPORT_ARTIFACT_PATH as EVALUATION_REPORT_ARTIFACT_PATH,
    build_evaluation_report,
    validate_evaluation_report,
)
from durable_run_store import (
    STORE_ARTIFACT_PATH as DURABLE_RUN_STORE_ARTIFACT_PATH,
    build_durable_run_store,
    validate_durable_run_store,
)
from human_approval import (
    DECISION_ARTIFACT_PATH as HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    build_human_approval_decision,
    validate_human_approval_decision,
)
from fixture_runner import load_fixture
from ide_adapter import (
    APPROVAL_HANDOFF_ARTIFACT_PATH as IDE_APPROVAL_HANDOFF_ARTIFACT_PATH,
    CONTRACT_ARTIFACT_PATH as IDE_CONTRACT_ARTIFACT_PATH,
    OBSERVATION_ARTIFACT_PATH as IDE_OBSERVATION_ARTIFACT_PATH,
    build_approval_handoff_manifest,
    build_ide_adapter_contract,
    build_workspace_observation,
    validate_approval_handoff_manifest,
    validate_ide_adapter_contract,
    validate_workspace_observation,
)
from multi_agent_delivery import (
    DELIVERY_REPORT_ARTIFACT_PATH,
    MANIFEST_ARTIFACT_PATH as MULTI_AGENT_DELIVERY_MANIFEST_ARTIFACT_PATH,
    build_delivery_report,
    build_multi_agent_delivery_manifest,
    validate_delivery_report,
    validate_multi_agent_delivery_manifest,
)
from run_control import validate_run_control
from task_spec import TASK_SPEC_SCHEMA_VERSION, build_regression_task_spec, validate_regression_task_spec
from verifier_runtime import (
    REQUIRED_ARTIFACT_CHECK_IDS,
    REQUIRED_VERIFIER_RULE_IDS,
    build_verifier_rule_catalog,
    run_verifier_runtime,
    validate_verifier_rule_catalog,
    validate_verifier_runtime_ref,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures/regression"
ARTIFACT_DIR = ROOT / "artifacts/runs"
CAPABILITY_CATALOG_PATH = ROOT / "artifacts/capabilities/phase3_capability_catalog.json"
CONTEXT_PACK_DIR = ROOT / "artifacts/context"
VERIFIER_RULE_CATALOG_PATH = ROOT / "artifacts/verifier/phase5_verifier_rule_catalog.json"
RECOVERY_FIXTURE_DIR = ROOT / "artifacts/recovery/interrupted_after_extract"
COMPUTER_RUNTIME_CONTRACT_PATH = ROOT / CONTRACT_ARTIFACT_PATH
TRAJECTORY_OBSERVATION_PATH = ROOT / OBSERVATION_ARTIFACT_PATH
ADAPTER_POLICY_MANIFEST_PATH = ROOT / POLICY_MANIFEST_ARTIFACT_PATH
OBSERVATION_REDACTION_POLICY_PATH = ROOT / REDACTION_POLICY_ARTIFACT_PATH
IDE_ADAPTER_CONTRACT_PATH = ROOT / IDE_CONTRACT_ARTIFACT_PATH
IDE_WORKSPACE_OBSERVATION_PATH = ROOT / IDE_OBSERVATION_ARTIFACT_PATH
IDE_APPROVAL_HANDOFF_MANIFEST_PATH = ROOT / IDE_APPROVAL_HANDOFF_ARTIFACT_PATH
MULTI_AGENT_DELIVERY_MANIFEST_PATH = ROOT / MULTI_AGENT_DELIVERY_MANIFEST_ARTIFACT_PATH
DELIVERY_REPORT_PATH = ROOT / DELIVERY_REPORT_ARTIFACT_PATH
HUMAN_APPROVAL_DECISION_PATH = ROOT / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH
EVALUATION_REPORT_PATH = ROOT / EVALUATION_REPORT_ARTIFACT_PATH
DURABLE_RUN_STORE_PATH = ROOT / DURABLE_RUN_STORE_ARTIFACT_PATH
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
    *REQUIRED_VERIFIER_RULE_IDS,
}
PASS_STYLE_PHRASES = ["all passed", "clean pass", "passed successfully", "no failures"]
VERDICTS = {"passed", "failed", "incomplete", "warning_or_waiver", "unknown", "needs_human_check"}
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
    "scripts/evidence_list.py",
    "scripts/run_control.py",
    "scripts/recovery_fixture.py",
    "scripts/verifier_runtime.py",
    "scripts/computer_runtime.py",
    "scripts/ide_adapter.py",
    "scripts/multi_agent_delivery.py",
    "scripts/human_approval.py",
    "scripts/durable_run_store.py",
    "artifacts/capabilities/phase3_capability_catalog.json",
    "artifacts/verifier/phase5_verifier_rule_catalog.json",
    "artifacts/recovery/interrupted_after_extract/run.json",
    "artifacts/recovery/interrupted_after_extract/events.jsonl",
    "artifacts/computer_runtime/phase7_computer_runtime_contract.json",
    "artifacts/computer_runtime/phase7_trajectory_observation.json",
    "artifacts/computer_runtime/phase7_adapter_policy_manifest.json",
    "artifacts/computer_runtime/phase7_observation_redaction_policy.json",
    "artifacts/ide_adapter/phase8_ide_adapter_contract.json",
    "artifacts/ide_adapter/phase8_workspace_observation.json",
    "artifacts/ide_adapter/phase8_ide_approval_handoff_manifest.json",
    "artifacts/delivery/phase9_multi_agent_delivery_manifest.json",
    "artifacts/delivery/phase9_delivery_report.json",
    "artifacts/approval/phase9_human_approval_decision_fixture.json",
    "artifacts/state/post_mvp_durable_run_store.json",
    "artifacts/evaluation/phase9_mvp_evaluation_report.json",
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
    "context-budget-v1",
    "ContextPackV1",
    "verifier-runtime-v1",
    "verifier-rule-catalog-v1",
    "phase5_verifier_rule_catalog.json",
    "EvidenceListV1",
    "RunControlV1",
    "run-control-v1",
    "permission-policy-v1",
    "recovery-snapshot-v1",
    "InterruptedRecoveryFixtureV1",
    "ComputerRuntimeAdapterV1",
    "computer-runtime-adapter-contract-v1",
    "TrajectoryObservationV1",
    "trajectory-observation-v1",
    "phase7_computer_runtime_contract.json",
    "AdapterPolicyManifestV1",
    "adapter-policy-manifest-v1",
    "phase7_adapter_policy_manifest.json",
    "ObservationRedactionPolicyV1",
    "observation-redaction-policy-v1",
    "phase7_observation_redaction_policy.json",
    "IDEAdapterContractV1",
    "ide-adapter-contract-v1",
    "WorkspaceObservationV1",
    "workspace-observation-v1",
    "phase8_ide_adapter_contract.json",
    "phase8_workspace_observation.json",
    "IDEApprovalHandoffManifestV1",
    "ide-approval-handoff-manifest-v1",
    "phase8_ide_approval_handoff_manifest.json",
    "MultiAgentDeliveryManifestV1",
    "multi-agent-delivery-manifest-v1",
    "agent-handoff-v1",
    "phase9_multi_agent_delivery_manifest.json",
    "DeliveryReportV1",
    "delivery-report-v1",
    "phase9_delivery_report.json",
    "EvaluationReportV1",
    "mvp-evaluation-report-v1",
    "phase9_mvp_evaluation_report.json",
    "HumanApprovalDecisionV1",
    "human-approval-decision-v1",
    "phase9_human_approval_decision_fixture.json",
    "DurableRunStoreV1",
    "durable-run-store-v1",
    "post_mvp_durable_run_store.json",
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
    tampered["budget"]["actualLogExcerptItems"] = 0
    tampered["budget"]["actualLogExcerptLines"] = 0
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
    unknown_rules = sorted(report_rule_ids - REQUIRED_REPORT_RULES)
    if unknown_rules:
        raise AssertionError(f"Fixture {fixture_id} verifier_report has unknown rules: {unknown_rules}")

    artifact_check_ids = {check["checkId"] for check in report["artifactChecks"]}
    missing_checks = sorted(REQUIRED_ARTIFACT_CHECK_IDS - artifact_check_ids)
    if missing_checks:
        raise AssertionError(f"Fixture {fixture_id} verifier_report is missing artifact checks: {missing_checks}")

    if not fixture["allowAllPassedEmail"] and any(phrase in email.lower() for phrase in PASS_STYLE_PHRASES):
        raise AssertionError("Negative or uncertain fixtures must not generate a pass-style email")


def validate_verifier_runtime_replay(fixture_id: str, fixture: dict, run: dict, evidence: dict, result: dict, report: dict, email: str) -> None:
    expected_report = run_verifier_runtime(
        fixture_id=fixture_id,
        allow_all_passed_email=fixture["allowAllPassedEmail"],
        run_id=run["id"],
        fixture_hash=report["fixtureHash"],
        task_spec=json.loads(json.dumps(run["taskSpec"])),
        evidence=json.loads(json.dumps(evidence["items"])),
        result=json.loads(json.dumps(result)),
        email=email,
    )
    if report != expected_report:
        raise AssertionError(f"Fixture {fixture_id} verifier_report differs from deterministic VerifierRuntimeV1 replay")


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
            "runControl",
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
    try:
        validate_run_control(run, events)
    except ValueError as exc:
        raise AssertionError(f"Fixture {fixture_id} RunControlV1 failed validation: {exc}") from exc
    if not isinstance(run["steps"], list) or not run["steps"]:
        raise AssertionError(f"Fixture {fixture_id} run.steps must be a non-empty list")
    for step in run["steps"]:
        require_fields(f"{fixture_id} step", step, ["id", "capability", "capabilityRef", "status"])
        require_enum(f"{fixture_id} step.status", step["status"], STEP_STATUSES)
        if step["capability"] in PHASE3_CAPABILITY_NAMES:
            if step["capabilityRef"] != capability_ref(step["capability"]):
                raise AssertionError(f"Fixture {fixture_id} step {step['id']} capabilityRef mismatch")

    require_fields(f"{fixture_id} evidence.json", evidence, ["schemaVersion", "id", "fixtureId", "artifactBacklinks", "items"])
    if evidence["schemaVersion"] != "evidence-list-v1":
        raise AssertionError(f"Fixture {fixture_id} evidence.json schemaVersion must be evidence-list-v1")
    if evidence["id"] != f"evidence-list-{fixture_id}":
        raise AssertionError(f"Fixture {fixture_id} evidence.json id mismatch")
    if evidence["fixtureId"] != fixture_id:
        raise AssertionError(f"Fixture {fixture_id} evidence.json fixtureId mismatch")
    if not isinstance(evidence["items"], list) or not evidence["items"]:
        raise AssertionError(f"Fixture {fixture_id} evidence.items must be a non-empty list")
    for index, item in enumerate(evidence["items"]):
        item_label = f"{fixture_id} evidence.items[{index}]"
        require_fields(item_label, item, ["id", "type", "sourcePath", "sourceRef", "lineRange", "excerpt", "excerptHash", "observedAt", "classification", "confidence"])
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
            "verifierRuntime",
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
    try:
        validate_verifier_runtime_ref(report["verifierRuntime"])
    except ValueError as exc:
        raise AssertionError(f"Fixture {fixture_id} verifierRuntime failed validation: {exc}") from exc
    validate_rule_results(f"{fixture_id} verifier_report", report["ruleResults"])
    if not isinstance(report["artifactChecks"], list) or not report["artifactChecks"]:
        raise AssertionError(f"Fixture {fixture_id} verifier_report.artifactChecks must be a non-empty list")
    for index, check in enumerate(report["artifactChecks"]):
        check_label = f"{fixture_id} artifactChecks[{index}]"
        require_fields(check_label, check, ["checkId", "artifactId", "artifactType", "status", "message"])
        if check["checkId"] not in REQUIRED_ARTIFACT_CHECK_IDS:
            raise AssertionError(f"{check_label}.checkId is unknown: {check['checkId']}")
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

        try:
            validate_evidence_list(evidence, ROOT, run_dir)
        except ValueError as exc:
            raise AssertionError(f"Fixture {fixture_id} EvidenceListV1 failed validation: {exc}") from exc
        validate_schema_structure(fixture_id, run, evidence, result, report, events)
        validate_artifact_consistency(fixture_id, fixture, evidence, result, report, email)
        validate_verifier_runtime_replay(fixture_id, fixture, run, evidence, result, report, email)

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


def validate_committed_verifier_rule_catalog() -> None:
    catalog = load_json(VERIFIER_RULE_CATALOG_PATH)
    try:
        validate_verifier_rule_catalog(catalog)
    except ValueError as exc:
        raise AssertionError(f"Committed Phase 5 verifier rule catalog failed validation: {exc}") from exc

    expected = build_verifier_rule_catalog()
    if catalog != expected:
        raise AssertionError("Committed Phase 5 verifier rule catalog differs from deterministic generated catalog")

    tampered = json.loads(json.dumps(catalog))
    tampered["rules"] = [
        rule
        for rule in tampered["rules"]
        if rule.get("id") != "email_draft_uses_structured_facts"
    ]
    try:
        validate_verifier_rule_catalog(tampered)
    except ValueError as exc:
        if "Verifier rule ids must equal" not in str(exc):
            raise AssertionError(f"Verifier rule catalog forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("Verifier rule catalog forced-failure unexpectedly accepted a missing email grounding rule")


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
        evidence = load_json(ARTIFACT_DIR / fixture_id / "evidence.json")
        try:
            validate_evidence_list(evidence, ROOT, ARTIFACT_DIR / fixture_id, committed)
        except ValueError as exc:
            raise AssertionError(f"Committed EvidenceListV1 {fixture_id} failed ContextPack provenance validation: {exc}") from exc

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

    tampered = load_json(CONTEXT_PACK_DIR / "all_passed/context_pack.json")
    tampered["budget"]["maxLogExcerptLines"] = 1
    try:
        validate_context_pack(tampered, ROOT)
    except ValueError as exc:
        if "log_excerpt line budget exceeded" not in str(exc):
            raise AssertionError(f"ContextPack budget forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("ContextPack budget forced-failure unexpectedly passed validation")

    tampered = load_json(CONTEXT_PACK_DIR / "all_passed/context_pack.json")
    for item in tampered["contextItems"]:
        if item.get("kind") == "log_excerpt":
            item["evidenceId"] = "ev-all_passed-missing"
            break
    evidence = load_json(ARTIFACT_DIR / "all_passed/evidence.json")
    try:
        validate_evidence_list(evidence, ROOT, ARTIFACT_DIR / "all_passed", tampered)
    except ValueError as exc:
        if "missing log_excerpt provenance" not in str(exc):
            raise AssertionError(f"EvidenceListV1 provenance forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("EvidenceListV1 provenance forced-failure unexpectedly passed validation")


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


def run_verifier_rule_catalog_builder(out_file: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/verifier_runtime.py"),
        "--catalog-out",
        str(out_file),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "Verifier rule catalog builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def run_evidence_list_validator(fixture_id: str) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/evidence_list.py"),
        "--evidence",
        str(ARTIFACT_DIR / fixture_id / "evidence.json"),
        "--run-dir",
        str(ARTIFACT_DIR / fixture_id),
        "--context-pack",
        str(CONTEXT_PACK_DIR / fixture_id / "context_pack.json"),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "EvidenceListV1 validator failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def run_run_control_validator(fixture_id: str) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/run_control.py"),
        "--run",
        str(ARTIFACT_DIR / fixture_id / "run.json"),
        "--events",
        str(ARTIFACT_DIR / fixture_id / "events.jsonl"),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "RunControlV1 validator failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def run_recovery_fixture_builder(out_dir: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/recovery_fixture.py"),
        "--source-fixture-dir",
        str(FIXTURE_DIR / "all_passed"),
        "--out-dir",
        str(out_dir),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "InterruptedRecoveryFixtureV1 builder failed.\n"
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


def compare_interrupted_recovery_fixture(expected_dir: Path, actual_dir: Path) -> None:
    for filename in ["run.json", "events.jsonl"]:
        expected = expected_dir / filename
        actual = actual_dir / filename
        if not actual.is_file():
            raise AssertionError(f"InterruptedRecoveryFixtureV1 builder did not emit {filename}")
        if not filecmp.cmp(expected, actual, shallow=False):
            raise AssertionError(
                f"Committed InterruptedRecoveryFixtureV1 {expected.relative_to(ROOT)} differs from deterministic CLI output"
            )


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate_interrupted_recovery_fixture(run_dir: Path) -> None:
    run_path = run_dir / "run.json"
    events_path = run_dir / "events.jsonl"
    if not run_path.is_file() or not events_path.is_file():
        raise AssertionError("Missing InterruptedRecoveryFixtureV1 run.json/events.jsonl artifacts")

    run = load_json(run_path)
    events = load_jsonl(events_path)
    try:
        validate_run_control(run, events)
    except ValueError as exc:
        raise AssertionError(f"InterruptedRecoveryFixtureV1 failed RunControlV1 validation: {exc}") from exc

    if run["status"] != "interrupted":
        raise AssertionError("InterruptedRecoveryFixtureV1 run.status must be interrupted")
    if run.get("artifactRoot") != "artifacts/recovery":
        raise AssertionError("InterruptedRecoveryFixtureV1 artifactRoot must be artifacts/recovery")
    control = run["runControl"]
    snapshot = control["recoverySnapshot"]
    if control["currentState"] != "running":
        raise AssertionError("InterruptedRecoveryFixtureV1 currentState must be running")
    if events[-1]["type"] != "capability.extract_regression_result.completed":
        raise AssertionError("InterruptedRecoveryFixtureV1 must stop after result extraction")
    if snapshot["resumeMode"] != "from_last_event":
        raise AssertionError("InterruptedRecoveryFixtureV1 resumeMode must be from_last_event")
    if snapshot["nextAction"] != "resume_step":
        raise AssertionError("InterruptedRecoveryFixtureV1 nextAction must be resume_step")
    resume_target = snapshot.get("resumeTarget")
    if resume_target != {
        "capability": "write_artifact",
        "capabilityRef": capability_ref("write_artifact"),
        "inputRef": "regression_result_candidate",
        "reason": "resume_after_last_completed_event",
        "stepId": "step-write-artifact",
    }:
        raise AssertionError("InterruptedRecoveryFixtureV1 resumeTarget must point to step-write-artifact")

    tampered = json.loads(json.dumps(run))
    del tampered["runControl"]["recoverySnapshot"]["resumeTarget"]
    try:
        validate_run_control(tampered, events)
    except ValueError as exc:
        if "non-terminal snapshots must include resumeTarget" not in str(exc):
            raise AssertionError(f"InterruptedRecoveryFixtureV1 forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("InterruptedRecoveryFixtureV1 forced-failure unexpectedly accepted missing resumeTarget")


def expect_computer_runtime_validation_failure(label: str, payload: dict, validator, expected_message_fragment: str) -> None:
    try:
        validator(payload)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"ComputerRuntime forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"ComputerRuntime forced-failure case {label} unexpectedly passed validation")


def expect_trajectory_observation_validation_failure(
    label: str,
    observation: dict,
    contract: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_trajectory_observation(observation, contract, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"TrajectoryObservation forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"TrajectoryObservation forced-failure case {label} unexpectedly passed validation")


def validate_committed_computer_runtime_artifacts() -> None:
    contract = load_json(COMPUTER_RUNTIME_CONTRACT_PATH)
    observation = load_json(TRAJECTORY_OBSERVATION_PATH)
    policy_manifest = load_json(ADAPTER_POLICY_MANIFEST_PATH)
    redaction_policy = load_json(OBSERVATION_REDACTION_POLICY_PATH)
    capability_catalog = load_json(CAPABILITY_CATALOG_PATH)
    try:
        validate_computer_runtime_contract(contract)
    except ValueError as exc:
        raise AssertionError(f"Committed ComputerRuntimeAdapterV1 contract failed validation: {exc}") from exc
    try:
        validate_trajectory_observation(observation, contract, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed TrajectoryObservationV1 artifact failed validation: {exc}") from exc
    try:
        validate_adapter_policy_manifest(policy_manifest, contract, capability_catalog, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed AdapterPolicyManifestV1 artifact failed validation: {exc}") from exc
    try:
        validate_observation_redaction_policy(redaction_policy, contract, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed ObservationRedactionPolicyV1 artifact failed validation: {exc}") from exc

    expected_contract = build_computer_runtime_contract()
    if contract != expected_contract:
        raise AssertionError("Committed ComputerRuntimeAdapterV1 contract differs from deterministic builder output")

    expected_observation = build_trajectory_observation(
        ARTIFACT_DIR / "all_passed/run.json",
        ARTIFACT_DIR / "all_passed/evidence.json",
        ARTIFACT_DIR / "all_passed/events.jsonl",
        ROOT,
    )
    if observation != expected_observation:
        raise AssertionError("Committed TrajectoryObservationV1 artifact differs from deterministic builder output")

    expected_policy_manifest = build_adapter_policy_manifest(
        COMPUTER_RUNTIME_CONTRACT_PATH,
        CAPABILITY_CATALOG_PATH,
        ROOT,
    )
    if policy_manifest != expected_policy_manifest:
        raise AssertionError("Committed AdapterPolicyManifestV1 artifact differs from deterministic builder output")

    expected_redaction_policy = build_observation_redaction_policy(
        COMPUTER_RUNTIME_CONTRACT_PATH,
        ROOT,
    )
    if redaction_policy != expected_redaction_policy:
        raise AssertionError("Committed ObservationRedactionPolicyV1 artifact differs from deterministic builder output")

    tampered_contract = json.loads(json.dumps(contract))
    tampered_contract["policy"]["externalSideEffectsAllowed"] = True
    expect_computer_runtime_validation_failure(
        "external_side_effects_allowed",
        tampered_contract,
        validate_computer_runtime_contract,
        "must disallow external side effects",
    )

    tampered_contract = json.loads(json.dumps(contract))
    tampered_contract["capabilities"][1]["implemented"] = True
    expect_computer_runtime_validation_failure(
        "real_provider_capability_implemented",
        tampered_contract,
        validate_computer_runtime_contract,
        "must remain contract-only",
    )

    tampered_contract = json.loads(json.dumps(contract))
    tampered_contract["observationPolicy"]["rawScreenPixelsAllowed"] = True
    expect_computer_runtime_validation_failure(
        "raw_screen_pixels_allowed",
        tampered_contract,
        validate_computer_runtime_contract,
        "must disallow raw screen pixels",
    )

    tampered_observation = json.loads(json.dumps(observation))
    tampered_observation["externalSideEffect"] = True
    expect_trajectory_observation_validation_failure(
        "trajectory_external_side_effect",
        tampered_observation,
        contract,
        "must not declare external side effects",
    )

    tampered_observation = json.loads(json.dumps(observation))
    del tampered_observation["redactionPolicyRef"]
    expect_trajectory_observation_validation_failure(
        "trajectory_missing_redaction_policy_ref",
        tampered_observation,
        contract,
        "missing required fields",
    )

    tampered_observation = json.loads(json.dumps(observation))
    tampered_observation["policy"]["rawScreenPixelsCaptured"] = True
    expect_trajectory_observation_validation_failure(
        "trajectory_raw_screen_pixels",
        tampered_observation,
        contract,
        "must not capture raw screen pixels",
    )

    tampered_observation = json.loads(json.dumps(observation))
    tampered_observation["observations"][0]["evidenceId"] = "ev-all_passed-missing"
    expect_trajectory_observation_validation_failure(
        "trajectory_missing_evidence_binding",
        tampered_observation,
        contract,
        "must bind to existing evidence id",
    )

    tampered_observation = json.loads(json.dumps(observation))
    tampered_observation["observations"][0]["taskVerdict"] = "passed"
    expect_trajectory_observation_validation_failure(
        "trajectory_declares_task_verdict",
        tampered_observation,
        contract,
        "must not declare task verdicts",
    )

    tampered_policy_manifest = json.loads(json.dumps(policy_manifest))
    for decision in tampered_policy_manifest["decisions"]:
        if decision["permission"] == "dangerous":
            decision["scheduleWithoutApproval"] = True
            break
    try:
        validate_adapter_policy_manifest(tampered_policy_manifest, contract, capability_catalog, ROOT)
    except ValueError as exc:
        if "dangerous adapter capabilities must not be schedulable without approval" not in str(exc):
            raise AssertionError(f"AdapterPolicyManifest dangerous forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("AdapterPolicyManifest forced-failure unexpectedly accepted dangerous unapproved scheduling")

    tampered_policy_manifest = json.loads(json.dumps(policy_manifest))
    tampered_policy_manifest["schedulerPolicy"]["realProviderExecutionAllowed"] = True
    try:
        validate_adapter_policy_manifest(tampered_policy_manifest, contract, capability_catalog, ROOT)
    except ValueError as exc:
        if "must disallow real provider execution" not in str(exc):
            raise AssertionError(f"AdapterPolicyManifest provider forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("AdapterPolicyManifest forced-failure unexpectedly accepted real provider execution")

    tampered_catalog = json.loads(json.dumps(capability_catalog))
    tampered_catalog["capabilityEnvelope"]["items"].append(
        {
            "name": "computer.click",
            "ref": "computer-runtime://phase7/computer.click",
        }
    )
    tampered_policy_manifest = json.loads(json.dumps(policy_manifest))
    tampered_policy_manifest["phase3CatalogBoundary"]["registeredRunnerCapabilityRefs"].append(
        "computer-runtime://phase7/computer.click"
    )
    tampered_policy_manifest["phase3CatalogBoundary"]["adapterCapabilitiesInRunnerCatalog"] = [
        "computer-runtime://phase7/computer.click"
    ]
    try:
        validate_adapter_policy_manifest(tampered_policy_manifest, contract, tampered_catalog, ROOT)
    except ValueError as exc:
        if "must not register Phase 7 adapter capabilities" not in str(exc):
            raise AssertionError(f"AdapterPolicyManifest catalog forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("AdapterPolicyManifest forced-failure unexpectedly accepted adapter refs in runner catalog")

    tampered_redaction_policy = json.loads(json.dumps(redaction_policy))
    tampered_redaction_policy["defaults"]["rawScreenPixelsAllowed"] = True
    try:
        validate_observation_redaction_policy(tampered_redaction_policy, contract, ROOT)
    except ValueError as exc:
        if "must disallow raw screen pixels" not in str(exc):
            raise AssertionError(f"ObservationRedactionPolicy raw-screen forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("ObservationRedactionPolicy forced-failure unexpectedly accepted raw screen pixels")

    tampered_redaction_policy = json.loads(json.dumps(redaction_policy))
    for kind in tampered_redaction_policy["observationKinds"]:
        if kind["kind"] == "trajectory_event":
            kind["forbiddenDataClasses"] = [
                value for value in kind["forbiddenDataClasses"] if value != "task_verdict"
            ]
            break
    try:
        validate_observation_redaction_policy(tampered_redaction_policy, contract, ROOT)
    except ValueError as exc:
        if "must forbid task_verdict" not in str(exc):
            raise AssertionError(f"ObservationRedactionPolicy task-verdict forced-failure rejected for the wrong reason: {exc}") from exc
    else:
        raise AssertionError("ObservationRedactionPolicy forced-failure unexpectedly accepted trajectory task verdicts")


def run_computer_runtime_builder(contract_out: Path, observation_out: Path, policy_manifest_out: Path, redaction_policy_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/computer_runtime.py"),
        "--contract-out",
        str(contract_out),
        "--observation-out",
        str(observation_out),
        "--policy-manifest-out",
        str(policy_manifest_out),
        "--redaction-policy-out",
        str(redaction_policy_out),
        "--run",
        str(ARTIFACT_DIR / "all_passed/run.json"),
        "--evidence",
        str(ARTIFACT_DIR / "all_passed/evidence.json"),
        "--events",
        str(ARTIFACT_DIR / "all_passed/events.jsonl"),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "ComputerRuntimeAdapterV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_ide_adapter_validation_failure(label: str, payload: dict, validator, expected_message_fragment: str) -> None:
    try:
        validator(payload)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"IDEAdapter forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"IDEAdapter forced-failure case {label} unexpectedly passed validation")


def expect_workspace_observation_validation_failure(
    label: str,
    observation: dict,
    contract: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_workspace_observation(observation, contract, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"WorkspaceObservation forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"WorkspaceObservation forced-failure case {label} unexpectedly passed validation")


def expect_approval_handoff_validation_failure(
    label: str,
    manifest: dict,
    contract: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_approval_handoff_manifest(manifest, contract, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"IDEApprovalHandoffManifest forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"IDEApprovalHandoffManifest forced-failure case {label} unexpectedly passed validation")


def validate_committed_ide_adapter_artifacts() -> None:
    contract = load_json(IDE_ADAPTER_CONTRACT_PATH)
    observation = load_json(IDE_WORKSPACE_OBSERVATION_PATH)
    approval_handoff_manifest = load_json(IDE_APPROVAL_HANDOFF_MANIFEST_PATH)
    try:
        validate_ide_adapter_contract(contract)
    except ValueError as exc:
        raise AssertionError(f"Committed IDEAdapterContractV1 contract failed validation: {exc}") from exc
    try:
        validate_workspace_observation(observation, contract, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed WorkspaceObservationV1 artifact failed validation: {exc}") from exc
    try:
        validate_approval_handoff_manifest(approval_handoff_manifest, contract, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed IDEApprovalHandoffManifestV1 artifact failed validation: {exc}") from exc

    expected_contract = build_ide_adapter_contract()
    if contract != expected_contract:
        raise AssertionError("Committed IDEAdapterContractV1 contract differs from deterministic builder output")

    expected_observation = build_workspace_observation(
        IDE_ADAPTER_CONTRACT_PATH,
        CONTEXT_PACK_DIR / "all_passed/context_pack.json",
        ARTIFACT_DIR / "all_passed/run.json",
        ROOT,
    )
    if observation != expected_observation:
        raise AssertionError("Committed WorkspaceObservationV1 artifact differs from deterministic builder output")

    expected_manifest = build_approval_handoff_manifest(
        IDE_ADAPTER_CONTRACT_PATH,
        IDE_WORKSPACE_OBSERVATION_PATH,
        ARTIFACT_DIR / "all_passed/run.json",
        ROOT,
    )
    if approval_handoff_manifest != expected_manifest:
        raise AssertionError("Committed IDEApprovalHandoffManifestV1 artifact differs from deterministic builder output")

    tampered_contract = json.loads(json.dumps(contract))
    tampered_contract["policy"]["externalSideEffectsAllowed"] = True
    expect_ide_adapter_validation_failure(
        "external_side_effects_allowed",
        tampered_contract,
        validate_ide_adapter_contract,
        "must disallow external side effects",
    )

    tampered_contract = json.loads(json.dumps(contract))
    for capability in tampered_contract["capabilities"]:
        if capability["name"] == "ide.open_file":
            capability["externalSideEffectAllowed"] = True
            break
    expect_ide_adapter_validation_failure(
        "open_file_external_side_effect",
        tampered_contract,
        validate_ide_adapter_contract,
        "must not allow external side effects",
    )

    tampered_contract = json.loads(json.dumps(contract))
    for capability in tampered_contract["capabilities"]:
        if capability["name"] == "ide.terminal.request":
            capability["approvalRequired"] = False
            break
    expect_ide_adapter_validation_failure(
        "terminal_without_approval",
        tampered_contract,
        validate_ide_adapter_contract,
        "must require approval",
    )

    tampered_observation = json.loads(json.dumps(observation))
    tampered_observation["externalSideEffect"] = True
    expect_workspace_observation_validation_failure(
        "workspace_external_side_effect",
        tampered_observation,
        contract,
        "must not declare external side effects",
    )

    tampered_observation = json.loads(json.dumps(observation))
    del tampered_observation["observations"][0]["sourceRef"]
    expect_workspace_observation_validation_failure(
        "workspace_missing_source_ref",
        tampered_observation,
        contract,
        "missing required fields",
    )

    tampered_observation = json.loads(json.dumps(observation))
    tampered_observation["observations"][0]["taskVerdict"] = "passed"
    expect_workspace_observation_validation_failure(
        "workspace_declares_task_verdict",
        tampered_observation,
        contract,
        "must not declare task verdicts",
    )

    tampered_observation = json.loads(json.dumps(observation))
    tampered_observation["workspace"]["currentFileHash"] = "0" * 64
    expect_workspace_observation_validation_failure(
        "workspace_current_file_hash_mismatch",
        tampered_observation,
        contract,
        "currentFile source hash mismatch",
    )

    tampered_manifest = json.loads(json.dumps(approval_handoff_manifest))
    tampered_manifest["taskSpecBinding"]["requiredApprovalPoints"] = []
    expect_approval_handoff_validation_failure(
        "handoff_missing_task_spec_approval_point",
        tampered_manifest,
        contract,
        "must require TaskSpec send_email approval point",
    )

    tampered_manifest = json.loads(json.dumps(approval_handoff_manifest))
    for request in tampered_manifest["handoffRequests"]:
        if request["capability"] == "ide.terminal.request":
            request["executionAllowed"] = True
            break
    expect_approval_handoff_validation_failure(
        "handoff_terminal_execution_allowed",
        tampered_manifest,
        contract,
        "must not allow execution",
    )

    tampered_manifest = json.loads(json.dumps(approval_handoff_manifest))
    tampered_manifest["policy"]["noRealIdeExecution"] = False
    expect_approval_handoff_validation_failure(
        "handoff_real_ide_execution",
        tampered_manifest,
        contract,
        "no real IDE execution occurred",
    )


def run_ide_adapter_builder(contract_out: Path, observation_out: Path, approval_handoff_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/ide_adapter.py"),
        "--contract-out",
        str(contract_out),
        "--observation-out",
        str(observation_out),
        "--approval-handoff-out",
        str(approval_handoff_out),
        "--context-pack",
        str(CONTEXT_PACK_DIR / "all_passed/context_pack.json"),
        "--run",
        str(ARTIFACT_DIR / "all_passed/run.json"),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "IDEAdapterContractV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_multi_agent_delivery_validation_failure(
    label: str,
    manifest: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_multi_agent_delivery_manifest(manifest, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"MultiAgentDeliveryManifest forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"MultiAgentDeliveryManifest forced-failure case {label} unexpectedly passed validation")


def validate_committed_multi_agent_delivery_artifact() -> None:
    manifest = load_json(MULTI_AGENT_DELIVERY_MANIFEST_PATH)
    try:
        validate_multi_agent_delivery_manifest(manifest, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed MultiAgentDeliveryManifestV1 artifact failed validation: {exc}") from exc

    expected_manifest = build_multi_agent_delivery_manifest(
        ARTIFACT_DIR / "all_passed/run.json",
        CONTEXT_PACK_DIR / "all_passed/context_pack.json",
        ARTIFACT_DIR / "all_passed/evidence.json",
        ARTIFACT_DIR / "all_passed/regression_result.json",
        ARTIFACT_DIR / "all_passed/verifier_report.json",
        ARTIFACT_DIR / "all_passed/email_draft.md",
        IDE_APPROVAL_HANDOFF_MANIFEST_PATH,
        ROOT,
    )
    if manifest != expected_manifest:
        raise AssertionError("Committed MultiAgentDeliveryManifestV1 artifact differs from deterministic builder output")

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["agentRoles"] = [
        agent
        for agent in tampered_manifest["agentRoles"]
        if agent["name"] != "reviewer_agent"
    ]
    expect_multi_agent_delivery_validation_failure(
        "missing_reviewer_agent",
        tampered_manifest,
        "agentRoles must equal",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["ownership"]["taskVerdictOwner"] = "reporter_agent"
    expect_multi_agent_delivery_validation_failure(
        "reporter_owns_task_verdict",
        tampered_manifest,
        "task verdict owner must remain verifier-runtime-v1",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["handoffs"][1]["sideEffectAllowed"] = True
    expect_multi_agent_delivery_validation_failure(
        "handoff_side_effect_allowed",
        tampered_manifest,
        "handoffs must not allow side effects",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["deliveryReview"]["verifierStatus"] = "failed"
    expect_multi_agent_delivery_validation_failure(
        "verifier_not_passed",
        tampered_manifest,
        "verifierStatus must match verifier_report",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["deliveryArtifact"]["sendEmailAllowed"] = True
    expect_multi_agent_delivery_validation_failure(
        "delivery_email_send_allowed",
        tampered_manifest,
        "must not send email",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["deliveryArtifact"]["humanApprovalSatisfied"] = True
    expect_multi_agent_delivery_validation_failure(
        "human_approval_synthesized",
        tampered_manifest,
        "must not synthesize human approval",
    )


def run_multi_agent_delivery_builder(manifest_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/multi_agent_delivery.py"),
        "--manifest-out",
        str(manifest_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "MultiAgentDeliveryManifestV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_delivery_report_validation_failure(
    label: str,
    report: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_delivery_report(report, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"DeliveryReportV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"DeliveryReportV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_delivery_report_artifact() -> None:
    report = load_json(DELIVERY_REPORT_PATH)
    try:
        validate_delivery_report(report, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed DeliveryReportV1 artifact failed validation: {exc}") from exc

    expected_report = build_delivery_report(
        MULTI_AGENT_DELIVERY_MANIFEST_PATH,
        ARTIFACT_DIR / "all_passed/run.json",
        ARTIFACT_DIR / "all_passed/verifier_report.json",
        ARTIFACT_DIR / "all_passed/email_draft.md",
        IDE_APPROVAL_HANDOFF_MANIFEST_PATH,
        ROOT,
    )
    if report != expected_report:
        raise AssertionError("Committed DeliveryReportV1 artifact differs from deterministic builder output")

    tampered_report = json.loads(json.dumps(report))
    tampered_report["readiness"]["readyForExternalDelivery"] = True
    expect_delivery_report_validation_failure(
        "external_delivery_ready_without_approval",
        tampered_report,
        "must not mark external delivery ready without human approval",
    )

    tampered_report = json.loads(json.dumps(report))
    tampered_report["approvalBinding"]["humanApprovalSatisfied"] = True
    expect_delivery_report_validation_failure(
        "human_approval_synthesized",
        tampered_report,
        "must not synthesize human approval",
    )

    tampered_report = json.loads(json.dumps(report))
    tampered_report["blockers"] = [
        blocker
        for blocker in tampered_report["blockers"]
        if blocker.get("id") != "human_approval_missing"
    ]
    expect_delivery_report_validation_failure(
        "missing_human_approval_blocker",
        tampered_report,
        "blockers must include human_approval_missing",
    )

    tampered_report = json.loads(json.dumps(report))
    tampered_report["readiness"]["sendEmailAllowed"] = True
    expect_delivery_report_validation_failure(
        "send_email_allowed",
        tampered_report,
        "must not allow sending email",
    )

    tampered_report = json.loads(json.dumps(report))
    for source in tampered_report["sourceArtifacts"]:
        if source.get("role") == "email_draft":
            source["contentHash"] = "0" * 64
            break
    expect_delivery_report_validation_failure(
        "email_draft_hash_mismatch",
        tampered_report,
        "source hash mismatch",
    )


def run_delivery_report_builder(report_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/multi_agent_delivery.py"),
        "--delivery-report-out",
        str(report_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "DeliveryReportV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_human_approval_decision_validation_failure(
    label: str,
    decision: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_human_approval_decision(decision, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"HumanApprovalDecisionV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"HumanApprovalDecisionV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_human_approval_decision_artifact() -> None:
    decision = load_json(HUMAN_APPROVAL_DECISION_PATH)
    try:
        validate_human_approval_decision(decision, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed HumanApprovalDecisionV1 artifact failed validation: {exc}") from exc

    expected_decision = build_human_approval_decision(ROOT)
    if decision != expected_decision:
        raise AssertionError("Committed HumanApprovalDecisionV1 artifact differs from deterministic builder output")

    tampered_decision = json.loads(json.dumps(decision))
    tampered_decision["decision"]["approvalDecisionSynthesized"] = True
    expect_human_approval_decision_validation_failure(
        "approval_synthesized",
        tampered_decision,
        "must not synthesize approval decisions",
    )

    tampered_decision = json.loads(json.dumps(decision))
    tampered_decision["policyEffects"]["sendEmailAllowed"] = True
    expect_human_approval_decision_validation_failure(
        "send_email_allowed",
        tampered_decision,
        "must not allow sending email",
    )

    tampered_decision = json.loads(json.dumps(decision))
    tampered_decision["policyEffects"]["externalDeliveryAllowed"] = True
    expect_human_approval_decision_validation_failure(
        "external_delivery_allowed",
        tampered_decision,
        "must not allow external delivery",
    )

    tampered_decision = json.loads(json.dumps(decision))
    tampered_decision["deliveryReportBlockers"] = [
        blocker_id
        for blocker_id in tampered_decision["deliveryReportBlockers"]
        if blocker_id != "human_approval_missing"
    ]
    expect_human_approval_decision_validation_failure(
        "missing_delivery_report_blocker",
        tampered_decision,
        "must preserve DeliveryReportV1 blockers",
    )

    tampered_decision = json.loads(json.dumps(decision))
    for source in tampered_decision["sourceArtifacts"]:
        if source.get("role") == "delivery_report":
            source["contentHash"] = "0" * 64
            break
    expect_human_approval_decision_validation_failure(
        "delivery_report_hash_mismatch",
        tampered_decision,
        "source hash mismatch",
    )

    tampered_decision = json.loads(json.dumps(decision))
    tampered_decision["verifierBinding"]["taskVerdictOverrideAllowed"] = True
    expect_human_approval_decision_validation_failure(
        "task_verdict_override",
        tampered_decision,
        "must not override verifier verdicts",
    )


def run_human_approval_decision_builder(decision_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/human_approval.py"),
        "--decision-out",
        str(decision_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "HumanApprovalDecisionV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_durable_run_store_validation_failure(
    label: str,
    store: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_durable_run_store(store, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"DurableRunStoreV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"DurableRunStoreV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_durable_run_store_artifact() -> None:
    store = load_json(DURABLE_RUN_STORE_PATH)
    try:
        validate_durable_run_store(store, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed DurableRunStoreV1 artifact failed validation: {exc}") from exc

    expected_store = build_durable_run_store(ROOT)
    if store != expected_store:
        raise AssertionError("Committed DurableRunStoreV1 artifact differs from deterministic builder output")

    tampered_store = json.loads(json.dumps(store))
    tampered_store["persistencePolicy"]["databaseUsed"] = True
    expect_durable_run_store_validation_failure(
        "database_enabled",
        tampered_store,
        "must remain a static JSON fixture without a database",
    )

    tampered_store = json.loads(json.dumps(store))
    tampered_store["persistencePolicy"]["externalSideEffectsAllowed"] = True
    expect_durable_run_store_validation_failure(
        "external_side_effects_allowed",
        tampered_store,
        "must disallow external side effects",
    )

    tampered_store = json.loads(json.dumps(store))
    tampered_store["runIndex"]["appendOnlyEventIds"] = list(reversed(tampered_store["runIndex"]["appendOnlyEventIds"]))
    expect_durable_run_store_validation_failure(
        "event_order_drift",
        tampered_store,
        "append-only event ids must match",
    )

    tampered_store = json.loads(json.dumps(store))
    tampered_store["runIndex"]["eventLogContentHash"] = "0" * 64
    expect_durable_run_store_validation_failure(
        "event_log_hash_mismatch",
        tampered_store,
        "event log content hash must match",
    )

    tampered_store = json.loads(json.dumps(store))
    tampered_store["sourceArtifacts"] = [
        source
        for source in tampered_store["sourceArtifacts"]
        if source.get("role") != "human_approval_decision"
    ]
    expect_durable_run_store_validation_failure(
        "missing_human_approval_source",
        tampered_store,
        "source roles must equal",
    )

    tampered_store = json.loads(json.dumps(store))
    tampered_store["approvalIndex"]["approvalGranted"] = True
    expect_durable_run_store_validation_failure(
        "approval_granted",
        tampered_store,
        "must not grant external delivery approval",
    )


def run_durable_run_store_builder(store_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/durable_run_store.py"),
        "--store-out",
        str(store_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "DurableRunStoreV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_evaluation_report_validation_failure(
    label: str,
    report: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_evaluation_report(report, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"EvaluationReportV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"EvaluationReportV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_evaluation_report_artifact() -> None:
    report = load_json(EVALUATION_REPORT_PATH)
    try:
        validate_evaluation_report(report, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed EvaluationReportV1 artifact failed validation: {exc}") from exc

    expected_report = build_evaluation_report(ROOT)
    if report != expected_report:
        raise AssertionError("Committed EvaluationReportV1 artifact differs from deterministic builder output")

    tampered_report = json.loads(json.dumps(report))
    tampered_report["phaseCoverage"] = [
        phase
        for phase in tampered_report["phaseCoverage"]
        if phase.get("phase") != "phase7"
    ]
    expect_evaluation_report_validation_failure(
        "missing_phase7_coverage",
        tampered_report,
        "phaseCoverage must cover phases in order",
    )

    tampered_report = json.loads(json.dumps(report))
    tampered_report["mvpCompletionDecision"]["fullAgenticEngineeringOsComplete"] = True
    expect_evaluation_report_validation_failure(
        "full_product_claimed_complete",
        tampered_report,
        "must not claim the full Agentic Engineering OS product is complete",
    )

    tampered_report = json.loads(json.dumps(report))
    tampered_report["mvpCompletionDecision"]["readyForExternalSideEffects"] = True
    expect_evaluation_report_validation_failure(
        "external_side_effects_ready",
        tampered_report,
        "must not allow external side effects",
    )

    tampered_report = json.loads(json.dumps(report))
    for source in tampered_report["sourceArtifacts"]:
        if source.get("role") == "phase9_delivery_report":
            source["contentHash"] = "0" * 64
            break
    expect_evaluation_report_validation_failure(
        "delivery_report_hash_mismatch",
        tampered_report,
        "source hash mismatch",
    )

    tampered_report = json.loads(json.dumps(report))
    tampered_report["knownBlockers"] = [
        blocker
        for blocker in tampered_report["knownBlockers"]
        if blocker.get("id") != "real_provider_execution_out_of_scope"
    ]
    expect_evaluation_report_validation_failure(
        "missing_real_provider_blocker",
        tampered_report,
        "knownBlockers must include",
    )

    tampered_report = json.loads(json.dumps(report))
    tampered_report["outOfScope"] = [
        item
        for item in tampered_report["outOfScope"]
        if item.get("id") != "real_cua_provider_integration"
    ]
    expect_evaluation_report_validation_failure(
        "missing_cua_out_of_scope",
        tampered_report,
        "outOfScope must include",
    )


def run_evaluation_report_builder(report_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/evaluation_report.py"),
        "--report-out",
        str(report_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "EvaluationReportV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
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


def break_evidence_excerpt_hash(tampered_dir: Path) -> None:
    evidence_path = tampered_dir / "all_passed/evidence.json"
    evidence = load_json(evidence_path)
    evidence["items"][0]["excerptHash"] = "0" * 64
    write_json(evidence_path, evidence)


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


def break_run_control_transition(tampered_dir: Path) -> None:
    run_path = tampered_dir / "all_passed/run.json"
    run = load_json(run_path)
    run["runControl"]["stateHistory"][2]["state"] = "running"
    write_json(run_path, run)


def allow_external_side_effects(tampered_dir: Path) -> None:
    run_path = tampered_dir / "all_passed/run.json"
    run = load_json(run_path)
    run["runControl"]["permissionPolicy"]["externalSideEffectsAllowed"] = True
    write_json(run_path, run)


def break_recovery_last_event(tampered_dir: Path) -> None:
    run_path = tampered_dir / "all_passed/run.json"
    run = load_json(run_path)
    run["runControl"]["recoverySnapshot"]["lastEventId"] = "event-all_passed-missing"
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
        "references unknown EvidenceListV1 ids",
    )
    expect_artifact_validation_failure(
        "broken_evidence_excerpt_hash",
        source_dir,
        scratch_root,
        break_evidence_excerpt_hash,
        "excerptHash must equal sha256",
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
    expect_artifact_validation_failure(
        "illegal_run_control_transition",
        source_dir,
        scratch_root,
        break_run_control_transition,
        "stateHistory must match events.jsonl",
    )
    expect_artifact_validation_failure(
        "external_side_effects_allowed",
        source_dir,
        scratch_root,
        allow_external_side_effects,
        "must disallow external side effects",
    )
    expect_artifact_validation_failure(
        "broken_recovery_last_event",
        source_dir,
        scratch_root,
        break_recovery_last_event,
        "must point to the last event",
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
    validate_committed_verifier_rule_catalog()
    validate_committed_context_packs()
    validate_interrupted_recovery_fixture(RECOVERY_FIXTURE_DIR)
    validate_committed_computer_runtime_artifacts()
    validate_committed_ide_adapter_artifacts()
    validate_committed_multi_agent_delivery_artifact()
    validate_committed_delivery_report_artifact()
    validate_committed_human_approval_decision_artifact()
    validate_committed_durable_run_store_artifact()
    validate_committed_evaluation_report_artifact()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        generated_verifier_catalog = temp_root / "phase5_verifier_rule_catalog.json"
        run_verifier_rule_catalog_builder(generated_verifier_catalog)
        if load_json(generated_verifier_catalog) != load_json(VERIFIER_RULE_CATALOG_PATH):
            raise AssertionError("Committed verifier rule catalog differs from deterministic CLI output")
        for fixture_id in FIXTURE_IDS:
            run_evidence_list_validator(fixture_id)
            run_run_control_validator(fixture_id)
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
        generated_recovery = temp_root / "recovery"
        run_recovery_fixture_builder(generated_recovery)
        compare_interrupted_recovery_fixture(RECOVERY_FIXTURE_DIR, generated_recovery / "interrupted_after_extract")
        generated_computer_contract = temp_root / "phase7_computer_runtime_contract.json"
        generated_trajectory_observation = temp_root / "phase7_trajectory_observation.json"
        generated_policy_manifest = temp_root / "phase7_adapter_policy_manifest.json"
        generated_redaction_policy = temp_root / "phase7_observation_redaction_policy.json"
        run_computer_runtime_builder(
            generated_computer_contract,
            generated_trajectory_observation,
            generated_policy_manifest,
            generated_redaction_policy,
        )
        if load_json(generated_computer_contract) != load_json(COMPUTER_RUNTIME_CONTRACT_PATH):
            raise AssertionError("Committed ComputerRuntimeAdapterV1 contract differs from deterministic CLI output")
        if load_json(generated_trajectory_observation) != load_json(TRAJECTORY_OBSERVATION_PATH):
            raise AssertionError("Committed TrajectoryObservationV1 artifact differs from deterministic CLI output")
        if load_json(generated_policy_manifest) != load_json(ADAPTER_POLICY_MANIFEST_PATH):
            raise AssertionError("Committed AdapterPolicyManifestV1 artifact differs from deterministic CLI output")
        if load_json(generated_redaction_policy) != load_json(OBSERVATION_REDACTION_POLICY_PATH):
            raise AssertionError("Committed ObservationRedactionPolicyV1 artifact differs from deterministic CLI output")
        generated_ide_contract = temp_root / "phase8_ide_adapter_contract.json"
        generated_workspace_observation = temp_root / "phase8_workspace_observation.json"
        generated_approval_handoff_manifest = temp_root / "phase8_ide_approval_handoff_manifest.json"
        run_ide_adapter_builder(generated_ide_contract, generated_workspace_observation, generated_approval_handoff_manifest)
        if load_json(generated_ide_contract) != load_json(IDE_ADAPTER_CONTRACT_PATH):
            raise AssertionError("Committed IDEAdapterContractV1 contract differs from deterministic CLI output")
        if load_json(generated_workspace_observation) != load_json(IDE_WORKSPACE_OBSERVATION_PATH):
            raise AssertionError("Committed WorkspaceObservationV1 artifact differs from deterministic CLI output")
        if load_json(generated_approval_handoff_manifest) != load_json(IDE_APPROVAL_HANDOFF_MANIFEST_PATH):
            raise AssertionError("Committed IDEApprovalHandoffManifestV1 artifact differs from deterministic CLI output")
        generated_multi_agent_delivery_manifest = temp_root / "phase9_multi_agent_delivery_manifest.json"
        run_multi_agent_delivery_builder(generated_multi_agent_delivery_manifest)
        if load_json(generated_multi_agent_delivery_manifest) != load_json(MULTI_AGENT_DELIVERY_MANIFEST_PATH):
            raise AssertionError("Committed MultiAgentDeliveryManifestV1 artifact differs from deterministic CLI output")
        generated_delivery_report = temp_root / "phase9_delivery_report.json"
        run_delivery_report_builder(generated_delivery_report)
        if load_json(generated_delivery_report) != load_json(DELIVERY_REPORT_PATH):
            raise AssertionError("Committed DeliveryReportV1 artifact differs from deterministic CLI output")
        generated_human_approval_decision = temp_root / "phase9_human_approval_decision_fixture.json"
        run_human_approval_decision_builder(generated_human_approval_decision)
        if load_json(generated_human_approval_decision) != load_json(HUMAN_APPROVAL_DECISION_PATH):
            raise AssertionError("Committed HumanApprovalDecisionV1 artifact differs from deterministic CLI output")
        generated_durable_run_store = temp_root / "post_mvp_durable_run_store.json"
        run_durable_run_store_builder(generated_durable_run_store)
        if load_json(generated_durable_run_store) != load_json(DURABLE_RUN_STORE_PATH):
            raise AssertionError("Committed DurableRunStoreV1 artifact differs from deterministic CLI output")
        generated_evaluation_report = temp_root / "phase9_mvp_evaluation_report.json"
        run_evaluation_report_builder(generated_evaluation_report)
        if load_json(generated_evaluation_report) != load_json(EVALUATION_REPORT_PATH):
            raise AssertionError("Committed EvaluationReportV1 artifact differs from deterministic CLI output")

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

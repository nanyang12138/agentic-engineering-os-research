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
from replay_query import (
    QUERY_ARTIFACT_PATH as REPLAY_QUERY_ARTIFACT_PATH,
    build_replay_query,
    validate_replay_query,
)
from identity_bound_approval import (
    RECORD_ARTIFACT_PATH as IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH,
    build_identity_bound_approval_record,
    validate_identity_bound_approval_record,
)
from approval_audit_query import (
    AUDIT_ARTIFACT_PATH as APPROVAL_AUDIT_QUERY_ARTIFACT_PATH,
    build_approval_audit_query,
    validate_approval_audit_query,
)
from approval_revocation import (
    REVOCATION_ARTIFACT_PATH as APPROVAL_REVOCATION_ARTIFACT_PATH,
    build_approval_revocation_or_expiry,
    validate_approval_revocation_or_expiry,
)
from policy_unlock_denial import (
    UNLOCK_DENIAL_ARTIFACT_PATH as POLICY_UNLOCK_DENIAL_ARTIFACT_PATH,
    build_policy_unlock_request_denied,
    validate_policy_unlock_request_denied,
)
from coordination_contract import (
    AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
    CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    DELEGATION_MANIFEST_ARTIFACT_PATH,
    NEGOTIATION_RECORD_ARTIFACT_PATH,
    build_agent_message_manifest,
    build_broadcast_subscription_manifest,
    build_creator_verifier_pairing,
    build_delegation_manifest,
    build_negotiation_record,
    validate_agent_message_manifest,
    validate_broadcast_subscription_manifest,
    validate_creator_verifier_pairing,
    validate_delegation_manifest,
    validate_negotiation_record,
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
from test_execution_task_spec import (
    TASK_SPEC_ARTIFACT_PATH as TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    build_test_execution_task_spec,
    validate_test_execution_task_spec,
)
from test_execution_result import (
    TEST_EXECUTION_RESULT_ARTIFACT_PATH,
    build_test_execution_result,
    validate_test_execution_result,
)
from failure_triage_report import (
    FAILURE_TRIAGE_REPORT_ARTIFACT_PATH,
    build_failure_triage_report,
    validate_failure_triage_report,
)
from verifier_result import (
    VERIFIER_RESULT_ARTIFACT_PATH,
    build_verifier_result,
    validate_verifier_result,
)
from capability_manifest import (
    CAPABILITY_MANIFEST_ARTIFACT_PATH,
    build_capability_manifest,
    validate_capability_manifest,
)
from run_event_log import (
    RUN_EVENT_LOG_ARTIFACT_PATH,
    build_run_event_log,
    validate_run_event_log,
)
from delivery_manifest import (
    DELIVERY_MANIFEST_ARTIFACT_PATH,
    build_delivery_manifest,
    validate_delivery_manifest,
)
from policy_manifest import (
    POLICY_MANIFEST_ARTIFACT_PATH as POST_MVP_POLICY_MANIFEST_ARTIFACT_PATH,
    build_policy_manifest,
    validate_policy_manifest,
)
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
REPLAY_QUERY_PATH = ROOT / REPLAY_QUERY_ARTIFACT_PATH
IDENTITY_BOUND_APPROVAL_RECORD_PATH = ROOT / IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH
APPROVAL_AUDIT_QUERY_PATH = ROOT / APPROVAL_AUDIT_QUERY_ARTIFACT_PATH
APPROVAL_REVOCATION_PATH = ROOT / APPROVAL_REVOCATION_ARTIFACT_PATH
POLICY_UNLOCK_DENIAL_PATH = ROOT / POLICY_UNLOCK_DENIAL_ARTIFACT_PATH
DELEGATION_MANIFEST_PATH = ROOT / DELEGATION_MANIFEST_ARTIFACT_PATH
CREATOR_VERIFIER_PAIRING_PATH = ROOT / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH
AGENT_MESSAGE_MANIFEST_PATH = ROOT / AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH
NEGOTIATION_RECORD_PATH = ROOT / NEGOTIATION_RECORD_ARTIFACT_PATH
BROADCAST_SUBSCRIPTION_MANIFEST_PATH = ROOT / BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH
TEST_EXECUTION_TASK_SPEC_PATH = ROOT / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
TEST_EXECUTION_RESULT_PATH = ROOT / TEST_EXECUTION_RESULT_ARTIFACT_PATH
FAILURE_TRIAGE_REPORT_PATH = ROOT / FAILURE_TRIAGE_REPORT_ARTIFACT_PATH
VERIFIER_RESULT_PATH = ROOT / VERIFIER_RESULT_ARTIFACT_PATH
CAPABILITY_MANIFEST_PATH = ROOT / CAPABILITY_MANIFEST_ARTIFACT_PATH
RUN_EVENT_LOG_PATH = ROOT / RUN_EVENT_LOG_ARTIFACT_PATH
DELIVERY_MANIFEST_PATH = ROOT / DELIVERY_MANIFEST_ARTIFACT_PATH
POLICY_MANIFEST_PATH = ROOT / POST_MVP_POLICY_MANIFEST_ARTIFACT_PATH
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
    "scripts/replay_query.py",
    "scripts/identity_bound_approval.py",
    "scripts/approval_audit_query.py",
    "scripts/approval_revocation.py",
    "scripts/policy_unlock_denial.py",
    "scripts/coordination_contract.py",
    "scripts/test_execution_task_spec.py",
    "scripts/test_execution_result.py",
    "scripts/failure_triage_report.py",
    "scripts/verifier_result.py",
    "scripts/capability_manifest.py",
    "scripts/run_event_log.py",
    "scripts/delivery_manifest.py",
    "scripts/policy_manifest.py",
    "artifacts/capabilities/phase3_capability_catalog.json",
    "artifacts/capabilities/post_mvp_test_execution_capability_manifest.json",
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
    "artifacts/state/post_mvp_replay_query.json",
    "artifacts/approval/post_mvp_identity_bound_approval_record.json",
    "artifacts/approval/post_mvp_approval_audit_query.json",
    "artifacts/approval/post_mvp_approval_revocation_or_expiry.json",
    "artifacts/approval/post_mvp_policy_unlock_request_denied.json",
    "artifacts/coordination/post_mvp_delegation_manifest.json",
    "artifacts/coordination/post_mvp_creator_verifier_pairing.json",
    "artifacts/coordination/post_mvp_agent_message_manifest.json",
    "artifacts/coordination/post_mvp_negotiation_record.json",
    "artifacts/coordination/post_mvp_broadcast_subscription_manifest.json",
    "artifacts/task_specs/post_mvp_test_execution_task_spec.json",
    "artifacts/test_execution/post_mvp_test_execution_result.json",
    "artifacts/test_execution/post_mvp_failure_triage_report.json",
    "artifacts/verifier/post_mvp_verifier_result_test_execution.json",
    "artifacts/state/post_mvp_test_execution_run_event_log.json",
    "artifacts/delivery/post_mvp_test_execution_delivery_manifest.json",
    "artifacts/policy/post_mvp_test_execution_policy_manifest.json",
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
    "ReplayQueryV1",
    "replay-query-v1",
    "post_mvp_replay_query.json",
    "IdentityBoundApprovalRecordV1",
    "identity-bound-approval-record-v1",
    "post_mvp_identity_bound_approval_record.json",
    "ApprovalAuditQueryV1",
    "approval-audit-query-v1",
    "post_mvp_approval_audit_query.json",
    "ApprovalRevocationOrExpiryV1",
    "approval-revocation-or-expiry-v1",
    "post_mvp_approval_revocation_or_expiry.json",
    "PolicyUnlockRequestDeniedV1",
    "policy-unlock-request-denied-v1",
    "post_mvp_policy_unlock_request_denied.json",
    "DelegationManifestV1",
    "delegation-manifest-v1",
    "CoordinationEventV1",
    "coordination-event-v1",
    "post_mvp_delegation_manifest.json",
    "CreatorVerifierPairingV1",
    "creator-verifier-pairing-v1",
    "post_mvp_creator_verifier_pairing.json",
    "AgentMessageManifestV1",
    "agent-message-manifest-v1",
    "agent-message-v1",
    "post_mvp_agent_message_manifest.json",
    "NegotiationRecordV1",
    "negotiation-record-v1",
    "negotiation-proposal-v1",
    "negotiation-agreement-v1",
    "post_mvp_negotiation_record.json",
    "BroadcastSubscriptionManifestV1",
    "broadcast-subscription-manifest-v1",
    "broadcast-topic-v1",
    "broadcast-subscription-v1",
    "broadcast-fan-out-v1",
    "post_mvp_broadcast_subscription_manifest.json",
    "TestExecutionTaskSpecV1",
    "test-execution-task-spec-v1",
    "test_execution_failure_triage",
    "post_mvp_test_execution_task_spec.json",
    "TestExecutionResultV1",
    "test-execution-result-v1",
    "post_mvp_test_execution_result.json",
    "FailureTriageReportV1",
    "failure-triage-report-v1",
    "post_mvp_failure_triage_report.json",
    "VerifierResultV1",
    "verifier-result-v1",
    "post_mvp_verifier_result_test_execution.json",
    "CapabilityManifestV1",
    "capability-manifest-v1",
    "capability-definition-v1",
    "post_mvp_test_execution_capability_manifest.json",
    "RunEventLogV1",
    "run-event-log-v1",
    "run-event-v1",
    "run-state-machine-v1",
    "post_mvp_test_execution_run_event_log.json",
    "DeliveryManifestV1",
    "delivery-manifest-v1",
    "delivery-channel-v1",
    "post_mvp_test_execution_delivery_manifest.json",
    "PolicyManifestV1",
    "policy-manifest-v1",
    "policy-rule-v1",
    "policy-effect-class-v1",
    "policy-revocation-rule-v1",
    "post_mvp_test_execution_policy_manifest.json",
    "Agentic Engineering OS Kernel",
    "workload-independent primitives",
    "first workload: Read-only Regression Evidence Demo",
    "Automation 防走偏护栏",
    "Post-MVP slice selection priority",
    "Regression/email overfitting ban",
    "Kernel Generalization",
    "Multi-Workload Expansion",
    "Agent Coordination Runtime Contracts",
    "DelegationManifestV1",
    "CreatorVerifierPairingV1",
    "AgentMessageV1",
    "NegotiationRecordV1",
    "CoordinationEventV1",
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
    "Product boundary guardrail",
    "Regression boundary rule",
    "Post-MVP slice selection priority",
    "Slice rejection rule",
    "Agentic Engineering OS Kernel",
    "workload-independent primitives",
    "supports many engineering workload types",
    "coordination layer: delegation / creator-verifier / direct communication / negotiation / broadcast",
    "Do not run `gh pr merge --auto --squash` from Cursor Automation",
    "Auto-merge is delegated to `.github/workflows/auto-merge-cursor-pr.yml`",
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


def expect_replay_query_validation_failure(
    label: str,
    query_artifact: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_replay_query(query_artifact, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"ReplayQueryV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"ReplayQueryV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_replay_query_artifact() -> None:
    query_artifact = load_json(REPLAY_QUERY_PATH)
    try:
        validate_replay_query(query_artifact, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed ReplayQueryV1 artifact failed validation: {exc}") from exc

    expected_query = build_replay_query(ROOT)
    if query_artifact != expected_query:
        raise AssertionError("Committed ReplayQueryV1 artifact differs from deterministic builder output")

    tampered_query = json.loads(json.dumps(query_artifact))
    tampered_query["queryPolicy"]["databaseUsed"] = True
    expect_replay_query_validation_failure(
        "database_enabled",
        tampered_query,
        "must not use a database",
    )

    tampered_query = json.loads(json.dumps(query_artifact))
    tampered_query["queryPolicy"]["externalSideEffectsAllowed"] = True
    expect_replay_query_validation_failure(
        "external_side_effects_allowed",
        tampered_query,
        "must disallow external side effects",
    )

    tampered_query = json.loads(json.dumps(query_artifact))
    tampered_query["queryPolicy"]["approvalGrantAllowed"] = True
    expect_replay_query_validation_failure(
        "approval_grant_allowed",
        tampered_query,
        "must not grant approvals",
    )

    tampered_query = json.loads(json.dumps(query_artifact))
    tampered_query["queries"][0]["result"]["currentState"] = "running"
    expect_replay_query_validation_failure(
        "run_state_result_drift",
        tampered_query,
        "query results must match",
    )

    tampered_query = json.loads(json.dumps(query_artifact))
    tampered_query["queries"][3]["result"]["appendOnlyEventIds"] = list(
        reversed(tampered_query["queries"][3]["result"]["appendOnlyEventIds"])
    )
    expect_replay_query_validation_failure(
        "event_order_drift",
        tampered_query,
        "query results must match",
    )

    tampered_query = json.loads(json.dumps(query_artifact))
    for source in tampered_query["sourceArtifacts"]:
        if source.get("role") == "durable_run_store":
            source["contentHash"] = "0" * 64
            break
    expect_replay_query_validation_failure(
        "store_hash_mismatch",
        tampered_query,
        "source hash mismatch",
    )


def run_replay_query_builder(query_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/replay_query.py"),
        "--query-out",
        str(query_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "ReplayQueryV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_identity_bound_approval_validation_failure(
    label: str,
    record: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_identity_bound_approval_record(record, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"IdentityBoundApprovalRecordV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"IdentityBoundApprovalRecordV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_identity_bound_approval_record_artifact() -> None:
    record = load_json(IDENTITY_BOUND_APPROVAL_RECORD_PATH)
    try:
        validate_identity_bound_approval_record(record, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed IdentityBoundApprovalRecordV1 artifact failed validation: {exc}") from exc

    expected_record = build_identity_bound_approval_record(ROOT)
    if record != expected_record:
        raise AssertionError("Committed IdentityBoundApprovalRecordV1 artifact differs from deterministic builder output")

    tampered_record = json.loads(json.dumps(record))
    tampered_record["actorIdentity"]["actorId"] = "unbound-approver"
    expect_identity_bound_approval_validation_failure(
        "actor_identity_drift",
        tampered_record,
        "actorId must be static-human-approver-fixture",
    )

    tampered_record = json.loads(json.dumps(record))
    tampered_record["intentBinding"]["taskSpecContentHash"] = "0" * 64
    expect_identity_bound_approval_validation_failure(
        "task_spec_hash_drift",
        tampered_record,
        "taskSpecContentHash must match Run taskSpec",
    )

    tampered_record = json.loads(json.dumps(record))
    tampered_record["decisionBinding"]["approvalGranted"] = True
    expect_identity_bound_approval_validation_failure(
        "approval_granted",
        tampered_record,
        "must not grant approval",
    )

    tampered_record = json.loads(json.dumps(record))
    tampered_record["effectBoundary"]["externalSideEffectsAllowed"] = True
    expect_identity_bound_approval_validation_failure(
        "external_side_effects_allowed",
        tampered_record,
        "externalSideEffectsAllowed must be false",
    )

    tampered_record = json.loads(json.dumps(record))
    tampered_record["policyBinding"]["sendEmailRequiresApproval"] = False
    expect_identity_bound_approval_validation_failure(
        "send_email_approval_bypass",
        tampered_record,
        "policy must require approval for send_email",
    )

    tampered_record = json.loads(json.dumps(record))
    for source in tampered_record["sourceArtifacts"]:
        if source.get("role") == "replay_query":
            source["contentHash"] = "0" * 64
            break
    expect_identity_bound_approval_validation_failure(
        "replay_query_hash_mismatch",
        tampered_record,
        "source hash mismatch",
    )


def run_identity_bound_approval_record_builder(record_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/identity_bound_approval.py"),
        "--record-out",
        str(record_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "IdentityBoundApprovalRecordV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_approval_audit_query_validation_failure(
    label: str,
    audit_query: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_approval_audit_query(audit_query, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"ApprovalAuditQueryV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"ApprovalAuditQueryV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_approval_audit_query_artifact() -> None:
    audit_query = load_json(APPROVAL_AUDIT_QUERY_PATH)
    try:
        validate_approval_audit_query(audit_query, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed ApprovalAuditQueryV1 artifact failed validation: {exc}") from exc

    expected_audit_query = build_approval_audit_query(ROOT)
    if audit_query != expected_audit_query:
        raise AssertionError("Committed ApprovalAuditQueryV1 artifact differs from deterministic builder output")

    tampered_audit_query = json.loads(json.dumps(audit_query))
    tampered_audit_query["queryPolicy"]["databaseUsed"] = True
    expect_approval_audit_query_validation_failure(
        "database_enabled",
        tampered_audit_query,
        "must not use a database",
    )

    tampered_audit_query = json.loads(json.dumps(audit_query))
    tampered_audit_query["queryPolicy"]["externalSideEffectsAllowed"] = True
    expect_approval_audit_query_validation_failure(
        "external_side_effects_allowed",
        tampered_audit_query,
        "must disallow external side effects",
    )

    tampered_audit_query = json.loads(json.dumps(audit_query))
    tampered_audit_query["queries"][0]["result"]["actorId"] = "unbound-approver"
    expect_approval_audit_query_validation_failure(
        "actor_result_drift",
        tampered_audit_query,
        "query results must match",
    )

    tampered_audit_query = json.loads(json.dumps(audit_query))
    tampered_audit_query["queries"][2]["result"]["approvalGranted"] = True
    expect_approval_audit_query_validation_failure(
        "approval_granted_result_drift",
        tampered_audit_query,
        "query results must match",
    )

    tampered_audit_query = json.loads(json.dumps(audit_query))
    tampered_audit_query["queries"][4]["result"]["identityRecordSourceArtifacts"] = []
    expect_approval_audit_query_validation_failure(
        "source_hash_chain_removed",
        tampered_audit_query,
        "query results must match",
    )

    tampered_audit_query = json.loads(json.dumps(audit_query))
    for source in tampered_audit_query["sourceArtifacts"]:
        if source.get("role") == "identity_bound_approval_record":
            source["contentHash"] = "0" * 64
            break
    expect_approval_audit_query_validation_failure(
        "identity_record_hash_mismatch",
        tampered_audit_query,
        "source hash mismatch",
    )


def run_approval_audit_query_builder(audit_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/approval_audit_query.py"),
        "--audit-out",
        str(audit_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "ApprovalAuditQueryV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_approval_revocation_validation_failure(
    label: str,
    revocation: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_approval_revocation_or_expiry(revocation, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"ApprovalRevocationOrExpiryV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"ApprovalRevocationOrExpiryV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_approval_revocation_artifact() -> None:
    revocation = load_json(APPROVAL_REVOCATION_PATH)
    try:
        validate_approval_revocation_or_expiry(revocation, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed ApprovalRevocationOrExpiryV1 artifact failed validation: {exc}") from exc

    expected_revocation = build_approval_revocation_or_expiry(ROOT)
    if revocation != expected_revocation:
        raise AssertionError("Committed ApprovalRevocationOrExpiryV1 artifact differs from deterministic builder output")

    tampered_revocation = json.loads(json.dumps(revocation))
    tampered_revocation["approvalLifecycle"]["currentState"] = "active"
    expect_approval_revocation_validation_failure(
        "active_current_state",
        tampered_revocation,
        "currentState must be expired_and_revoked",
    )

    tampered_revocation = json.loads(json.dumps(revocation))
    tampered_revocation["approvalLifecycle"]["activeApproval"] = True
    expect_approval_revocation_validation_failure(
        "active_approval",
        tampered_revocation,
        "activeApproval must be false",
    )

    tampered_revocation = json.loads(json.dumps(revocation))
    tampered_revocation["effectBoundary"]["sendEmailAllowed"] = True
    expect_approval_revocation_validation_failure(
        "send_email_allowed",
        tampered_revocation,
        "effectBoundary sendEmailAllowed must be false",
    )

    tampered_revocation = json.loads(json.dumps(revocation))
    tampered_revocation["lifecyclePolicy"]["externalSideEffectsAllowed"] = True
    expect_approval_revocation_validation_failure(
        "external_side_effects_allowed",
        tampered_revocation,
        "lifecyclePolicy externalSideEffectsAllowed must be false",
    )

    tampered_revocation = json.loads(json.dumps(revocation))
    tampered_revocation["auditBinding"]["sourceHashChain"] = []
    expect_approval_revocation_validation_failure(
        "source_hash_chain_removed",
        tampered_revocation,
        "source hash chain must match",
    )

    tampered_revocation = json.loads(json.dumps(revocation))
    for source in tampered_revocation["sourceArtifacts"]:
        if source.get("role") == "approval_audit_query":
            source["contentHash"] = "0" * 64
            break
    expect_approval_revocation_validation_failure(
        "approval_audit_query_hash_mismatch",
        tampered_revocation,
        "source hash mismatch",
    )


def run_approval_revocation_builder(revocation_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/approval_revocation.py"),
        "--revocation-out",
        str(revocation_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "ApprovalRevocationOrExpiryV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_policy_unlock_denial_validation_failure(
    label: str,
    denial: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_policy_unlock_request_denied(denial, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"PolicyUnlockRequestDeniedV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"PolicyUnlockRequestDeniedV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_policy_unlock_denial_artifact() -> None:
    denial = load_json(POLICY_UNLOCK_DENIAL_PATH)
    try:
        validate_policy_unlock_request_denied(denial, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed PolicyUnlockRequestDeniedV1 artifact failed validation: {exc}") from exc

    expected_denial = build_policy_unlock_request_denied(ROOT)
    if denial != expected_denial:
        raise AssertionError("Committed PolicyUnlockRequestDeniedV1 artifact differs from deterministic builder output")

    tampered_denial = json.loads(json.dumps(denial))
    tampered_denial["denialDecision"]["unlockAllowed"] = True
    expect_policy_unlock_denial_validation_failure(
        "unlock_allowed",
        tampered_denial,
        "unlockAllowed must be false",
    )

    tampered_denial = json.loads(json.dumps(denial))
    tampered_denial["policyInputs"]["approvalCurrentState"] = "active"
    expect_policy_unlock_denial_validation_failure(
        "active_approval_state",
        tampered_denial,
        "approvalCurrentState must be expired_and_revoked",
    )

    tampered_denial = json.loads(json.dumps(denial))
    tampered_denial["effectsAfterDecision"]["sendEmailAllowed"] = True
    expect_policy_unlock_denial_validation_failure(
        "send_email_allowed_after_denial",
        tampered_denial,
        "effectsAfterDecision sendEmailAllowed must be false",
    )

    tampered_denial = json.loads(json.dumps(denial))
    tampered_denial["requestPolicy"]["externalSideEffectsAllowed"] = True
    expect_policy_unlock_denial_validation_failure(
        "request_policy_external_side_effects_allowed",
        tampered_denial,
        "requestPolicy externalSideEffectsAllowed must be false",
    )

    tampered_denial = json.loads(json.dumps(denial))
    tampered_denial["denialDecision"]["blockingReasons"] = [
        reason
        for reason in tampered_denial["denialDecision"]["blockingReasons"]
        if reason != "approval_expired_or_revoked"
    ]
    expect_policy_unlock_denial_validation_failure(
        "missing_expired_revoked_reason",
        tampered_denial,
        "blockingReasons must include",
    )

    tampered_denial = json.loads(json.dumps(denial))
    for source in tampered_denial["sourceArtifacts"]:
        if source.get("role") == "approval_revocation_or_expiry":
            source["contentHash"] = "0" * 64
            break
    expect_policy_unlock_denial_validation_failure(
        "approval_revocation_hash_mismatch",
        tampered_denial,
        "source hash mismatch",
    )


def run_policy_unlock_denial_builder(denial_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/policy_unlock_denial.py"),
        "--denial-out",
        str(denial_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "PolicyUnlockRequestDeniedV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_delegation_manifest_validation_failure(
    label: str,
    manifest: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_delegation_manifest(manifest, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"DelegationManifestV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"DelegationManifestV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_delegation_manifest_artifact() -> None:
    manifest = load_json(DELEGATION_MANIFEST_PATH)
    try:
        validate_delegation_manifest(manifest, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed DelegationManifestV1 artifact failed validation: {exc}") from exc

    expected_manifest = build_delegation_manifest(ROOT)
    if manifest != expected_manifest:
        raise AssertionError("Committed DelegationManifestV1 artifact differs from deterministic builder output")

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["creatorVerifierInvariant"]["verifierAgent"] = tampered_manifest["creatorVerifierInvariant"]["creatorAgent"]
    tampered_manifest["delegations"][0]["verifierAgent"] = tampered_manifest["delegations"][0]["creatorAgent"]
    expect_delegation_manifest_validation_failure(
        "creator_self_verifies",
        tampered_manifest,
        "creator and verifier agents must be distinct",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["delegations"][0]["requiredEvidence"] = ["source_bound_observation"]
    expect_delegation_manifest_validation_failure(
        "missing_required_evidence",
        tampered_manifest,
        "requiredEvidence must include",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_delegation_manifest_validation_failure(
        "external_side_effect_allowed",
        tampered_manifest,
        "externalSideEffectsAllowed false",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["delegations"][0]["expectedArtifacts"].append(
        {
            "artifactKind": "EmailDraftArtifactV1",
            "artifactRef": "artifacts/runs/all_passed/email_draft.md",
            "purpose": "regression_email_delivery",
        }
    )
    expect_delegation_manifest_validation_failure(
        "email_delivery_artifact_added",
        tampered_manifest,
        "workload-independent",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["coordinationEvents"][2]["causalRefs"] = ["coord-event-missing"]
    expect_delegation_manifest_validation_failure(
        "coordination_event_causal_chain_broken",
        tampered_manifest,
        "causal chain",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_delegation_manifest_validation_failure(
        "missing_non_regression_reuse_path",
        tampered_manifest,
        "non-regression workload reuse paths",
    )


def run_delegation_manifest_builder(manifest_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/coordination_contract.py"),
        "--delegation-out",
        str(manifest_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "DelegationManifestV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_creator_verifier_pairing_validation_failure(
    label: str,
    pairing: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_creator_verifier_pairing(pairing, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"CreatorVerifierPairingV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"CreatorVerifierPairingV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_creator_verifier_pairing_artifact() -> None:
    pairing = load_json(CREATOR_VERIFIER_PAIRING_PATH)
    try:
        validate_creator_verifier_pairing(pairing, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed CreatorVerifierPairingV1 artifact failed validation: {exc}") from exc

    expected_pairing = build_creator_verifier_pairing(ROOT)
    if pairing != expected_pairing:
        raise AssertionError("Committed CreatorVerifierPairingV1 artifact differs from deterministic builder output")

    tampered_pairing = json.loads(json.dumps(pairing))
    tampered_pairing["creator"]["mayVerifyArtifacts"] = True
    expect_creator_verifier_pairing_validation_failure(
        "creator_self_verifies",
        tampered_pairing,
        "creator must not verify artifacts or declare acceptance",
    )

    tampered_pairing = json.loads(json.dumps(pairing))
    tampered_pairing["acceptanceEvidence"] = [
        evidence
        for evidence in tampered_pairing["acceptanceEvidence"]
        if evidence.get("artifactKind") != "VerifierResultV1"
    ]
    expect_creator_verifier_pairing_validation_failure(
        "missing_verifier_result_acceptance_evidence",
        tampered_pairing,
        "acceptanceEvidence must include EvidenceListV1 and VerifierResultV1",
    )

    tampered_pairing = json.loads(json.dumps(pairing))
    tampered_pairing["independencePolicy"]["weakSelfVerificationAllowed"] = True
    expect_creator_verifier_pairing_validation_failure(
        "weak_self_verification_allowed",
        tampered_pairing,
        "weakSelfVerificationAllowed false",
    )

    tampered_pairing = json.loads(json.dumps(pairing))
    tampered_pairing["verifierResultBinding"]["creatorOverrideAllowed"] = True
    expect_creator_verifier_pairing_validation_failure(
        "creator_overrides_verifier_result",
        tampered_pairing,
        "must gate acceptance and forbid creator override",
    )

    tampered_pairing = json.loads(json.dumps(pairing))
    tampered_pairing["creatorOutput"]["artifactRef"] = "artifacts/runs/all_passed/email_draft.md"
    expect_creator_verifier_pairing_validation_failure(
        "email_delivery_artifact_added",
        tampered_pairing,
        "must not add regression/email delivery artifacts",
    )

    tampered_pairing = json.loads(json.dumps(pairing))
    tampered_pairing["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_creator_verifier_pairing_validation_failure(
        "missing_non_regression_reuse_path",
        tampered_pairing,
        "non-regression workload reuse paths",
    )

    tampered_pairing = json.loads(json.dumps(pairing))
    for source in tampered_pairing["sourceArtifacts"]:
        if source.get("role") == "delegation_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_creator_verifier_pairing_validation_failure(
        "delegation_manifest_hash_mismatch",
        tampered_pairing,
        "source hash mismatch",
    )


def run_creator_verifier_pairing_builder(pairing_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/coordination_contract.py"),
        "--pairing-out",
        str(pairing_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "CreatorVerifierPairingV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_agent_message_manifest_validation_failure(
    label: str,
    manifest: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_agent_message_manifest(manifest, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"AgentMessageManifestV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"AgentMessageManifestV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_agent_message_manifest_artifact() -> None:
    manifest = load_json(AGENT_MESSAGE_MANIFEST_PATH)
    try:
        validate_agent_message_manifest(manifest, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed AgentMessageManifestV1 artifact failed validation: {exc}") from exc

    expected_manifest = build_agent_message_manifest(ROOT)
    if manifest != expected_manifest:
        raise AssertionError("Committed AgentMessageManifestV1 artifact differs from deterministic builder output")

    tampered_manifest = json.loads(json.dumps(manifest))
    for channel in tampered_manifest["channels"]:
        channel["broadcastAllowed"] = True
    expect_agent_message_manifest_validation_failure(
        "channel_broadcast_allowed",
        tampered_manifest,
        "channel broadcast must be disallowed",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    for message in tampered_manifest["messages"]:
        if message["type"] == "verification.response":
            message["inReplyToMessageId"] = None
            break
    expect_agent_message_manifest_validation_failure(
        "response_not_bound_to_request",
        tampered_manifest,
        "verification.response must reply to verification.request",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    for message in tampered_manifest["messages"]:
        if message["type"] == "verification.request":
            message["payloadRefs"].append(
                {
                    "artifactKind": "ArtifactV1",
                    "artifactRef": "artifacts/runs/all_passed/email_draft.md",
                    "role": "regression_email_delivery",
                }
            )
            break
    expect_agent_message_manifest_validation_failure(
        "email_delivery_payload_added",
        tampered_manifest,
        "must not add regression/email delivery artifacts",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["messages"] = [
        message for message in tampered_manifest["messages"] if message["type"] != "verification.response"
    ]
    expect_agent_message_manifest_validation_failure(
        "missing_verification_response",
        tampered_manifest,
        "messageTypeSequence",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    for message in tampered_manifest["messages"]:
        message["carriesSideEffects"] = True
    expect_agent_message_manifest_validation_failure(
        "messages_carry_side_effects",
        tampered_manifest,
        "must not carry side effects",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    for message in tampered_manifest["messages"]:
        message["mayOverrideVerifierResult"] = True
    expect_agent_message_manifest_validation_failure(
        "messages_override_verifier_result",
        tampered_manifest,
        "must not override verifier results",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_agent_message_manifest_validation_failure(
        "policy_external_side_effects_allowed",
        tampered_manifest,
        "externalSideEffectsAllowed false",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_agent_message_manifest_validation_failure(
        "missing_non_regression_reuse_path",
        tampered_manifest,
        "non-regression workload reuse paths",
    )

    tampered_manifest = json.loads(json.dumps(manifest))
    for source in tampered_manifest["sourceArtifacts"]:
        if source.get("role") == "creator_verifier_pairing":
            source["contentHash"] = "0" * 64
            break
    expect_agent_message_manifest_validation_failure(
        "pairing_source_hash_mismatch",
        tampered_manifest,
        "source hash mismatch",
    )


def run_agent_message_manifest_builder(manifest_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/coordination_contract.py"),
        "--agent-message-out",
        str(manifest_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "AgentMessageManifestV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_negotiation_record_validation_failure(
    label: str,
    record: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_negotiation_record(record, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"NegotiationRecordV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(f"NegotiationRecordV1 forced-failure case {label} unexpectedly passed validation")


def validate_committed_negotiation_record_artifact() -> None:
    record = load_json(NEGOTIATION_RECORD_PATH)
    try:
        validate_negotiation_record(record, ROOT)
    except ValueError as exc:
        raise AssertionError(f"Committed NegotiationRecordV1 artifact failed validation: {exc}") from exc

    expected_record = build_negotiation_record(ROOT)
    if record != expected_record:
        raise AssertionError("Committed NegotiationRecordV1 artifact differs from deterministic builder output")

    tampered = json.loads(json.dumps(record))
    tampered["agreement"]["overridesVerifierResult"] = True
    expect_negotiation_record_validation_failure(
        "agreement_overrides_verifier_result",
        tampered,
        "must not override verifier results",
    )

    tampered = json.loads(json.dumps(record))
    tampered["agreement"]["mutatesExpectedArtifacts"] = True
    expect_negotiation_record_validation_failure(
        "agreement_mutates_expected_artifacts",
        tampered,
        "must not mutate delegation expectedArtifacts",
    )

    tampered = json.loads(json.dumps(record))
    tampered["agreement"]["agreedBy"] = ["creator_agent"]
    expect_negotiation_record_validation_failure(
        "agreement_missing_verifier",
        tampered,
        "agreedBy both creator and verifier",
    )

    tampered = json.loads(json.dumps(record))
    tampered["proposals"] = [tampered["proposals"][0], tampered["proposals"][-1]]
    tampered["proposalTypeSequence"] = [
        tampered["proposals"][0]["proposalType"],
        tampered["proposals"][-1]["proposalType"],
    ]
    expect_negotiation_record_validation_failure(
        "proposal_sequence_missing_counter_proposal",
        tampered,
        "proposalTypeSequence",
    )

    tampered = json.loads(json.dumps(record))
    for proposal in tampered["proposals"]:
        proposal["carriesSideEffects"] = True
    expect_negotiation_record_validation_failure(
        "proposals_carry_side_effects",
        tampered,
        "must not carry side effects",
    )

    tampered = json.loads(json.dumps(record))
    for proposal in tampered["proposals"]:
        proposal["broadcastAllowed"] = True
    expect_negotiation_record_validation_failure(
        "proposals_broadcast_allowed",
        tampered,
        "must not broadcast",
    )

    tampered = json.loads(json.dumps(record))
    for proposal in tampered["proposals"]:
        proposal["proposedDelta"]["addedClause"] = (
            "Allow send_email after agreement."
        )
        tampered["agreement"]["agreedClause"] = tampered["proposals"][-1]["proposedDelta"]["addedClause"]
    expect_negotiation_record_validation_failure(
        "email_delivery_clause_added",
        tampered,
        "regression/email delivery artifacts",
    )

    tampered = json.loads(json.dumps(record))
    tampered["policyBoundary"]["broadcastAllowed"] = True
    expect_negotiation_record_validation_failure(
        "policy_broadcast_allowed",
        tampered,
        "broadcastAllowed false",
    )

    tampered = json.loads(json.dumps(record))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_negotiation_record_validation_failure(
        "missing_non_regression_reuse_path",
        tampered,
        "non-regression workload reuse paths",
    )

    tampered = json.loads(json.dumps(record))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "agent_message_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_negotiation_record_validation_failure(
        "agent_message_manifest_source_hash_mismatch",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(record))
    tampered["messageRefs"]["verificationRequest"] = (
        "artifacts/coordination/post_mvp_agent_message_manifest.json#messages/unknown"
    )
    expect_negotiation_record_validation_failure(
        "message_refs_request_not_bound",
        tampered,
        "verification.request",
    )


def run_negotiation_record_builder(record_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/coordination_contract.py"),
        "--negotiation-out",
        str(record_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "NegotiationRecordV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_broadcast_subscription_validation_failure(
    label: str,
    manifest: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_broadcast_subscription_manifest(manifest, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"BroadcastSubscriptionManifestV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"BroadcastSubscriptionManifestV1 forced-failure case {label} unexpectedly passed validation"
    )


def validate_committed_broadcast_subscription_manifest_artifact() -> None:
    manifest = load_json(BROADCAST_SUBSCRIPTION_MANIFEST_PATH)
    try:
        validate_broadcast_subscription_manifest(manifest, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed BroadcastSubscriptionManifestV1 artifact failed validation: {exc}"
        ) from exc

    expected_manifest = build_broadcast_subscription_manifest(ROOT)
    if manifest != expected_manifest:
        raise AssertionError(
            "Committed BroadcastSubscriptionManifestV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(manifest))
    for fan_out in tampered["fanOutEvents"]:
        fan_out["carriesSideEffects"] = True
    expect_broadcast_subscription_validation_failure(
        "fan_out_carries_side_effects",
        tampered,
        "fan-out must not carry side effects",
    )

    tampered = json.loads(json.dumps(manifest))
    for fan_out in tampered["fanOutEvents"]:
        fan_out["mayOverrideVerifierResult"] = True
    expect_broadcast_subscription_validation_failure(
        "fan_out_overrides_verifier_result",
        tampered,
        "must not override verifier results",
    )

    tampered = json.loads(json.dumps(manifest))
    for topic in tampered["topics"]:
        if topic["topicId"] == "coordination.delegation_lifecycle":
            topic["subscriberAllowList"] = topic["subscriberAllowList"] + ["unauthorized_agent"]
            break
    expect_broadcast_subscription_validation_failure(
        "topic_allow_list_includes_unauthorized_agent",
        tampered,
        "subscriberAllowList for coordination.delegation_lifecycle must equal",
    )

    tampered = json.loads(json.dumps(manifest))
    for topic in tampered["topics"]:
        topic["publicAccessAllowed"] = True
    expect_broadcast_subscription_validation_failure(
        "topic_public_access_allowed",
        tampered,
        "must keep publicAccessAllowed false",
    )

    tampered = json.loads(json.dumps(manifest))
    for subscription in tampered["subscriptions"]:
        subscription["mayBroadcastDownstream"] = True
    expect_broadcast_subscription_validation_failure(
        "subscription_broadcast_downstream_allowed",
        tampered,
        "must keep mayBroadcastDownstream false",
    )

    tampered = json.loads(json.dumps(manifest))
    tampered["subscriptions"] = [
        subscription
        for subscription in tampered["subscriptions"]
        if subscription["topicId"] != "coordination.negotiation_lifecycle"
    ]
    expect_broadcast_subscription_validation_failure(
        "subscriptions_missing_negotiation_topic",
        tampered,
        "must cover every (subscriber, topic) pair",
    )

    tampered = json.loads(json.dumps(manifest))
    tampered["fanOutEvents"] = tampered["fanOutEvents"][:-1]
    expect_broadcast_subscription_validation_failure(
        "fan_out_missing_negotiation_agreement",
        tampered,
        "fan out every declared coordination event and negotiation proposal",
    )

    tampered = json.loads(json.dumps(manifest))
    tampered["broadcastInvariant"]["publicAccessAllowed"] = True
    expect_broadcast_subscription_validation_failure(
        "broadcast_invariant_public_access_allowed",
        tampered,
        "broadcastInvariant must keep publicAccessAllowed false",
    )

    tampered = json.loads(json.dumps(manifest))
    tampered["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_broadcast_subscription_validation_failure(
        "policy_external_side_effects_allowed",
        tampered,
        "policyBoundary must keep externalSideEffectsAllowed false",
    )

    tampered = json.loads(json.dumps(manifest))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_broadcast_subscription_validation_failure(
        "missing_non_regression_reuse_path",
        tampered,
        "non-regression workload reuse paths",
    )

    tampered = json.loads(json.dumps(manifest))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "negotiation_record":
            source["contentHash"] = "0" * 64
            break
    expect_broadcast_subscription_validation_failure(
        "negotiation_record_source_hash_mismatch",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(manifest))
    tampered["negotiationBinding"]["negotiationAgreementRef"] = (
        "artifacts/coordination/post_mvp_negotiation_record.json#agreement/unknown"
    )
    expect_broadcast_subscription_validation_failure(
        "negotiation_agreement_ref_unbound",
        tampered,
        "negotiationAgreementRef must bind NegotiationRecordV1 agreement",
    )


def run_broadcast_subscription_manifest_builder(manifest_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/coordination_contract.py"),
        "--broadcast-subscription-out",
        str(manifest_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "BroadcastSubscriptionManifestV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_test_execution_task_spec_validation_failure(
    label: str,
    spec: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_test_execution_task_spec(spec, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"TestExecutionTaskSpecV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"TestExecutionTaskSpecV1 forced-failure case {label} unexpectedly passed validation"
    )


def validate_committed_test_execution_task_spec_artifact() -> None:
    spec = load_json(TEST_EXECUTION_TASK_SPEC_PATH)
    try:
        validate_test_execution_task_spec(spec, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed TestExecutionTaskSpecV1 artifact failed validation: {exc}"
        ) from exc

    expected_spec = build_test_execution_task_spec(ROOT)
    if spec != expected_spec:
        raise AssertionError(
            "Committed TestExecutionTaskSpecV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(spec))
    tampered["workloadType"] = "read_only_regression_evidence_demo"
    expect_test_execution_task_spec_validation_failure(
        "workload_type_regression_reuse",
        tampered,
        "workloadType must be test_execution_failure_triage",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["taskSpecEnvelopeSchemaVersion"] = "regression-task-spec-v1"
    expect_test_execution_task_spec_validation_failure(
        "envelope_schema_regression_reuse",
        tampered,
        "taskSpecEnvelopeSchemaVersion must be task-spec-v1",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["regressionWorkloadIsolation"]["reusesRegressionTaskSpecFields"] = True
    expect_test_execution_task_spec_validation_failure(
        "regression_field_reuse_allowed",
        tampered,
        "must not reuse regression TaskSpec fields",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["regressionWorkloadIsolation"]["reusesRegressionTaskSpecSchemaVersion"] = True
    expect_test_execution_task_spec_validation_failure(
        "regression_schema_reuse_allowed",
        tampered,
        "must not reuse regression-task-spec-v1 schema version",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["expectedArtifactKinds"] = ["RegressionResultArtifactV1", "EmailDraftV1"]
    expect_test_execution_task_spec_validation_failure(
        "expected_artifact_kinds_regression_overlap",
        tampered,
        "expectedArtifactKinds must equal",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["forbiddenEffectClasses"] = [
        cls for cls in tampered["forbiddenEffectClasses"] if cls != "send_external_communication"
    ]
    expect_test_execution_task_spec_validation_failure(
        "forbidden_effects_drop_communication",
        tampered,
        "forbiddenEffectClasses must equal",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_test_execution_task_spec_validation_failure(
        "policy_external_side_effects_allowed",
        tampered,
        "policyBoundary.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["policyBoundary"]["repositoryMutationAllowed"] = True
    expect_test_execution_task_spec_validation_failure(
        "policy_repository_mutation_allowed",
        tampered,
        "policyBoundary.repositoryMutationAllowed must be false",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["verifierExpectations"]["verdictOwner"] = "creator_agent"
    expect_test_execution_task_spec_validation_failure(
        "verifier_owner_override",
        tampered,
        "verdictOwner must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["verifierExpectations"]["creatorMustNotOwnVerdict"] = False
    expect_test_execution_task_spec_validation_failure(
        "creator_owns_verdict_allowed",
        tampered,
        "verifierExpectations.creatorMustNotOwnVerdict must be true",
    )

    tampered = json.loads(json.dumps(spec))
    del tampered["coordinationBinding"]["broadcastSubscriptionManifestRef"]
    expect_test_execution_task_spec_validation_failure(
        "coordination_binding_missing_broadcast",
        tampered,
        "coordinationBinding must include",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["coordinationBinding"]["delegationManifestRef"] = "artifacts/runs/all_passed/run.json"
    expect_test_execution_task_spec_validation_failure(
        "coordination_binding_wrong_path",
        tampered,
        "coordinationBinding.delegationManifestRef must equal",
    )

    tampered = json.loads(json.dumps(spec))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_test_execution_task_spec_validation_failure(
        "non_regression_reuse_path_missing",
        tampered,
        "nonRegressionReusePath must equal",
    )

    tampered = json.loads(json.dumps(spec))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "broadcast_subscription_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_test_execution_task_spec_validation_failure(
        "source_hash_mismatch_broadcast",
        tampered,
        "source hash mismatch",
    )


def run_test_execution_task_spec_builder(spec_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/test_execution_task_spec.py"),
        "--out",
        str(spec_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "TestExecutionTaskSpecV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_test_execution_result_validation_failure(
    label: str,
    artifact: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_test_execution_result(artifact, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"TestExecutionResultV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"TestExecutionResultV1 forced-failure case {label} unexpectedly passed validation"
    )


def validate_committed_test_execution_result_artifact() -> None:
    artifact = load_json(TEST_EXECUTION_RESULT_PATH)
    try:
        validate_test_execution_result(artifact, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed TestExecutionResultV1 artifact failed validation: {exc}"
        ) from exc

    expected_artifact = build_test_execution_result(ROOT)
    if artifact != expected_artifact:
        raise AssertionError(
            "Committed TestExecutionResultV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(artifact))
    tampered["workloadType"] = "read_only_regression_evidence_demo"
    expect_test_execution_result_validation_failure(
        "workload_type_regression_reuse",
        tampered,
        "workloadType must be test_execution_failure_triage",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["kind"] = "RegressionResultArtifactV1"
    expect_test_execution_result_validation_failure(
        "kind_regression_reuse",
        tampered,
        "kind must be TestExecutionResultV1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["artifactEnvelopeSchemaVersion"] = "regression-result-artifact-v1"
    expect_test_execution_result_validation_failure(
        "envelope_schema_regression_reuse",
        tampered,
        "artifactEnvelopeSchemaVersion must be artifact-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierVerdictOwner"] = "creator_agent"
    expect_test_execution_result_validation_failure(
        "creator_owns_verdict",
        tampered,
        "verifierVerdictOwner must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierExpectations"]["creatorMustNotOwnVerdict"] = False
    expect_test_execution_result_validation_failure(
        "creator_must_not_own_verdict_disabled",
        tampered,
        "verifierExpectations.creatorMustNotOwnVerdict must be true",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecSchemaVersion"] = "regression-task-spec-v1"
    expect_test_execution_result_validation_failure(
        "task_spec_binding_regression_schema_reuse",
        tampered,
        "taskSpecSchemaVersion must equal test-execution-task-spec-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecContentHash"] = "0" * 64
    expect_test_execution_result_validation_failure(
        "task_spec_binding_hash_drift",
        tampered,
        "taskSpecBinding.taskSpecContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_test_execution_result_validation_failure(
        "policy_external_side_effects_allowed",
        tampered,
        "policyBoundary.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalCommunicationAllowed"] = True
    expect_test_execution_result_validation_failure(
        "policy_external_communication_allowed",
        tampered,
        "policyBoundary.externalCommunicationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    for case in tampered["cases"]:
        if case["id"] == "case-002":
            case["evidenceIds"] = []
            break
    expect_test_execution_result_validation_failure(
        "case_missing_evidence",
        tampered,
        "must reference at least one evidence id",
    )

    tampered = json.loads(json.dumps(artifact))
    for evidence in tampered["evidenceList"]:
        if evidence["id"] == "ev-case-001-outcome":
            evidence["payload"] = "tampered payload"
            break
    expect_test_execution_result_validation_failure(
        "evidence_content_hash_drift",
        tampered,
        "contentHash must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    for case in tampered["cases"]:
        if case["id"] == "case-002":
            case["failureClassification"] = None
            break
    expect_test_execution_result_validation_failure(
        "failed_case_missing_classification",
        tampered,
        "failed case case-002 must declare a failureClassification",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["summary"]["failedCases"] = 0
    expect_test_execution_result_validation_failure(
        "summary_count_drift",
        tampered,
        "summary must equal computed counts",
    )

    tampered = json.loads(json.dumps(artifact))
    del tampered["coordinationBinding"]["broadcastSubscriptionManifestRef"]
    expect_test_execution_result_validation_failure(
        "coordination_binding_missing_broadcast",
        tampered,
        "coordinationBinding must include",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"]["delegationManifestRef"] = (
        "artifacts/runs/all_passed/run.json"
    )
    expect_test_execution_result_validation_failure(
        "coordination_binding_wrong_path",
        tampered,
        "coordinationBinding.delegationManifestRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_test_execution_result_validation_failure(
        "non_regression_reuse_path_missing",
        tampered,
        "nonRegressionReusePath must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesEmailDraftArtifact"] = True
    expect_test_execution_result_validation_failure(
        "regression_email_draft_reuse_allowed",
        tampered,
        "must not reuse EmailDraftArtifactV1",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "test_execution_task_spec":
            source["contentHash"] = "0" * 64
            break
    expect_test_execution_result_validation_failure(
        "source_hash_mismatch_task_spec",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "broadcast_subscription_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_test_execution_result_validation_failure(
        "source_hash_mismatch_broadcast",
        tampered,
        "source hash mismatch",
    )


def run_test_execution_result_builder(artifact_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/test_execution_result.py"),
        "--out",
        str(artifact_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "TestExecutionResultV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_failure_triage_report_validation_failure(
    label: str,
    report: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_failure_triage_report(report, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"FailureTriageReportV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"FailureTriageReportV1 forced-failure case {label} unexpectedly passed validation"
    )


def validate_committed_failure_triage_report_artifact() -> None:
    artifact = load_json(FAILURE_TRIAGE_REPORT_PATH)
    try:
        validate_failure_triage_report(artifact, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed FailureTriageReportV1 artifact failed validation: {exc}"
        ) from exc

    expected_artifact = build_failure_triage_report(ROOT)
    if artifact != expected_artifact:
        raise AssertionError(
            "Committed FailureTriageReportV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(artifact))
    tampered["workloadType"] = "read_only_regression_evidence_demo"
    expect_failure_triage_report_validation_failure(
        "workload_type_regression_reuse",
        tampered,
        "workloadType must be test_execution_failure_triage",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["kind"] = "TestExecutionResultV1"
    expect_failure_triage_report_validation_failure(
        "kind_reuses_test_execution_result",
        tampered,
        "kind must be FailureTriageReportV1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["schemaVersion"] = "regression-result-artifact-v1"
    expect_failure_triage_report_validation_failure(
        "schema_regression_reuse",
        tampered,
        "schemaVersion must be failure-triage-report-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["artifactEnvelopeSchemaVersion"] = "regression-result-artifact-v1"
    expect_failure_triage_report_validation_failure(
        "envelope_schema_regression_reuse",
        tampered,
        "artifactEnvelopeSchemaVersion must be artifact-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierVerdictOwner"] = "creator_agent"
    expect_failure_triage_report_validation_failure(
        "creator_owns_verdict",
        tampered,
        "verifierVerdictOwner must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierExpectations"]["creatorMustNotOwnVerdict"] = False
    expect_failure_triage_report_validation_failure(
        "creator_must_not_own_verdict_disabled",
        tampered,
        "verifierExpectations.creatorMustNotOwnVerdict must be true",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecSchemaVersion"] = "regression-task-spec-v1"
    expect_failure_triage_report_validation_failure(
        "task_spec_binding_regression_schema_reuse",
        tampered,
        "taskSpecSchemaVersion must equal test-execution-task-spec-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["testExecutionResultBinding"]["testExecutionResultSchemaVersion"] = (
        "regression-result-artifact-v1"
    )
    expect_failure_triage_report_validation_failure(
        "test_execution_result_binding_regression_schema_reuse",
        tampered,
        "testExecutionResultSchemaVersion must equal test-execution-result-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["testExecutionResultBinding"]["testExecutionResultContentHash"] = "0" * 64
    expect_failure_triage_report_validation_failure(
        "test_execution_result_binding_hash_drift",
        tampered,
        "testExecutionResultContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_failure_triage_report_validation_failure(
        "policy_external_side_effects_allowed",
        tampered,
        "policyBoundary.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalCommunicationAllowed"] = True
    expect_failure_triage_report_validation_failure(
        "policy_external_communication_allowed",
        tampered,
        "policyBoundary.externalCommunicationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["triageFindings"] = []
    expect_failure_triage_report_validation_failure(
        "triage_findings_empty",
        tampered,
        "triageFindings must be a non-empty list",
    )

    tampered = json.loads(json.dumps(artifact))
    for finding in tampered["triageFindings"]:
        if finding["caseRef"] == "case-002":
            finding["caseRef"] = "case-001"
            break
    expect_failure_triage_report_validation_failure(
        "triages_passed_case",
        tampered,
        "must not triage a passed case",
    )

    tampered = json.loads(json.dumps(artifact))
    for finding in tampered["triageFindings"]:
        if finding["caseRef"] == "case-002":
            finding["observedStatus"] = "passed"
            break
    expect_failure_triage_report_validation_failure(
        "finding_observed_status_drift",
        tampered,
        "observedStatus must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    for finding in tampered["triageFindings"]:
        if finding["caseRef"] == "case-002":
            finding["supportingEvidenceIds"] = ["ev-case-001-outcome"]
            break
    expect_failure_triage_report_validation_failure(
        "finding_evidence_belongs_to_other_case",
        tampered,
        "belongs to another case",
    )

    tampered = json.loads(json.dumps(artifact))
    for finding in tampered["triageFindings"]:
        if finding["caseRef"] == "case-002":
            finding["supportingEvidenceIds"] = []
            break
    expect_failure_triage_report_validation_failure(
        "finding_missing_evidence",
        tampered,
        "at least one supporting evidence id",
    )

    tampered = json.loads(json.dumps(artifact))
    for finding in tampered["triageFindings"]:
        if finding["caseRef"] == "case-002":
            finding["refinedFailureClassification"] = "send_email"
            break
    expect_failure_triage_report_validation_failure(
        "finding_refined_classification_invalid",
        tampered,
        "refinedFailureClassification must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    for finding in tampered["triageFindings"]:
        if finding["caseRef"] == "case-002":
            finding["remediationCategory"] = "send_external_communication"
            break
    expect_failure_triage_report_validation_failure(
        "finding_remediation_invalid",
        tampered,
        "remediationCategory must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    for finding in tampered["triageFindings"]:
        if finding["caseRef"] == "case-002":
            finding["mayBroadcastDownstream"] = True
            break
    expect_failure_triage_report_validation_failure(
        "finding_broadcast_downstream_allowed",
        tampered,
        "mayBroadcastDownstream must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["summary"]["totalFindings"] = 0
    expect_failure_triage_report_validation_failure(
        "summary_count_drift",
        tampered,
        "summary must equal computed counts",
    )

    tampered = json.loads(json.dumps(artifact))
    del tampered["coordinationBinding"]["broadcastSubscriptionManifestRef"]
    expect_failure_triage_report_validation_failure(
        "coordination_binding_missing_broadcast",
        tampered,
        "coordinationBinding must include",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"]["delegationManifestRef"] = (
        "artifacts/runs/all_passed/run.json"
    )
    expect_failure_triage_report_validation_failure(
        "coordination_binding_wrong_path",
        tampered,
        "coordinationBinding.delegationManifestRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_failure_triage_report_validation_failure(
        "non_regression_reuse_path_missing",
        tampered,
        "nonRegressionReusePath must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesTestExecutionResultArtifactSchema"] = True
    expect_failure_triage_report_validation_failure(
        "reuses_test_execution_result_schema",
        tampered,
        "must not reuse the TestExecutionResultV1 schema",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "test_execution_result":
            source["contentHash"] = "0" * 64
            break
    expect_failure_triage_report_validation_failure(
        "source_hash_mismatch_test_execution_result",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "broadcast_subscription_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_failure_triage_report_validation_failure(
        "source_hash_mismatch_broadcast",
        tampered,
        "source hash mismatch",
    )


def run_failure_triage_report_builder(artifact_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/failure_triage_report.py"),
        "--out",
        str(artifact_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "FailureTriageReportV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_verifier_result_validation_failure(
    label: str,
    report: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_verifier_result(report, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"VerifierResultV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"VerifierResultV1 forced-failure case {label} unexpectedly passed validation"
    )


def validate_committed_verifier_result_artifact() -> None:
    artifact = load_json(VERIFIER_RESULT_PATH)
    try:
        validate_verifier_result(artifact, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed VerifierResultV1 artifact failed validation: {exc}"
        ) from exc

    expected_artifact = build_verifier_result(ROOT)
    if artifact != expected_artifact:
        raise AssertionError(
            "Committed VerifierResultV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(artifact))
    tampered["workloadType"] = "read_only_regression_evidence_demo"
    expect_verifier_result_validation_failure(
        "workload_type_regression_reuse",
        tampered,
        "workloadType must be test_execution_failure_triage",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["kind"] = "FailureTriageReportV1"
    expect_verifier_result_validation_failure(
        "kind_reuses_failure_triage_report",
        tampered,
        "kind must be VerifierResultV1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["schemaVersion"] = "regression-result-artifact-v1"
    expect_verifier_result_validation_failure(
        "schema_regression_reuse",
        tampered,
        "schemaVersion must be verifier-result-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["artifactEnvelopeSchemaVersion"] = "regression-result-artifact-v1"
    expect_verifier_result_validation_failure(
        "envelope_schema_regression_reuse",
        tampered,
        "artifactEnvelopeSchemaVersion must be artifact-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierAgent"] = "creator_agent"
    expect_verifier_result_validation_failure(
        "creator_agent_authors_verifier_result",
        tampered,
        "verifierAgent must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierVerdictOwner"] = "creator_agent"
    expect_verifier_result_validation_failure(
        "creator_owns_verdict",
        tampered,
        "verifierVerdictOwner must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["creatorAgentMustNotOwnVerdict"] = False
    expect_verifier_result_validation_failure(
        "creator_must_not_own_verdict_disabled",
        tampered,
        "creatorAgentMustNotOwnVerdict must be true",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verdict"] = "passed"
    expect_verifier_result_validation_failure(
        "verdict_overrides_failed_case",
        tampered,
        "verdict must follow workload-independent precedence",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verdict"] = "failed"
    expect_verifier_result_validation_failure(
        "verdict_failed_without_failing_rule",
        tampered,
        "verdict must follow workload-independent precedence",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verdict"] = "broadcast"
    expect_verifier_result_validation_failure(
        "verdict_outside_domain",
        tampered,
        "verdict must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verdictDomain"] = ["passed", "failed"]
    expect_verifier_result_validation_failure(
        "verdict_domain_narrowed",
        tampered,
        "verdictDomain must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecSchemaVersion"] = "regression-task-spec-v1"
    expect_verifier_result_validation_failure(
        "task_spec_binding_regression_schema_reuse",
        tampered,
        "taskSpecSchemaVersion must equal test-execution-task-spec-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecContentHash"] = "0" * 64
    expect_verifier_result_validation_failure(
        "task_spec_binding_hash_drift",
        tampered,
        "taskSpecContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["testExecutionResultBinding"]["testExecutionResultSchemaVersion"] = (
        "regression-result-artifact-v1"
    )
    expect_verifier_result_validation_failure(
        "test_execution_result_binding_regression_schema_reuse",
        tampered,
        "testExecutionResultSchemaVersion must equal test-execution-result-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["testExecutionResultBinding"]["testExecutionResultContentHash"] = "0" * 64
    expect_verifier_result_validation_failure(
        "test_execution_result_binding_hash_drift",
        tampered,
        "testExecutionResultContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["failureTriageReportBinding"]["failureTriageReportSchemaVersion"] = (
        "regression-result-artifact-v1"
    )
    expect_verifier_result_validation_failure(
        "failure_triage_report_binding_regression_schema_reuse",
        tampered,
        "failureTriageReportSchemaVersion must equal failure-triage-report-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["failureTriageReportBinding"]["failureTriageReportContentHash"] = "0" * 64
    expect_verifier_result_validation_failure(
        "failure_triage_report_binding_hash_drift",
        tampered,
        "failureTriageReportContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_verifier_result_validation_failure(
        "policy_external_side_effects_allowed",
        tampered,
        "policyBoundary.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalCommunicationAllowed"] = True
    expect_verifier_result_validation_failure(
        "policy_external_communication_allowed",
        tampered,
        "policyBoundary.externalCommunicationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["ruleResults"] = []
    expect_verifier_result_validation_failure(
        "rule_results_empty",
        tampered,
        "ruleResults must be a non-empty list",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["ruleResults"] = [
        rule for rule in tampered["ruleResults"] if rule["id"] != "evidence_provenance"
    ]
    expect_verifier_result_validation_failure(
        "rule_results_missing_required_rule",
        tampered,
        "ruleResults must include rules",
    )

    tampered = json.loads(json.dumps(artifact))
    for rule in tampered["ruleResults"]:
        if rule["id"] == "evidence_provenance":
            rule["supportingEvidenceIds"] = ["ev-case-002-missing"]
            break
    expect_verifier_result_validation_failure(
        "rule_results_unknown_evidence_id",
        tampered,
        "references unknown evidence id",
    )

    tampered = json.loads(json.dumps(artifact))
    for rule in tampered["ruleResults"]:
        if rule["id"] == "schema_validation":
            rule["kind"] = "send_email_kind"
            break
    expect_verifier_result_validation_failure(
        "rule_results_invalid_kind",
        tampered,
        "kind must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    coordination = tampered["coordinationBinding"]
    del coordination["broadcastSubscriptionManifestRef"]
    expect_verifier_result_validation_failure(
        "coordination_binding_missing_broadcast",
        tampered,
        "coordinationBinding must include",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"]["delegationManifestRef"] = (
        "artifacts/runs/all_passed/run.json"
    )
    expect_verifier_result_validation_failure(
        "coordination_binding_wrong_path",
        tampered,
        "coordinationBinding.delegationManifestRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_verifier_result_validation_failure(
        "non_regression_reuse_path_missing",
        tampered,
        "nonRegressionReusePath must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesRegressionVerifierReportArtifact"] = True
    expect_verifier_result_validation_failure(
        "reuses_regression_verifier_report_artifact",
        tampered,
        "must not reuse the regression verifier_report.json artifact",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesFailureTriageReportSchema"] = True
    expect_verifier_result_validation_failure(
        "reuses_failure_triage_report_schema",
        tampered,
        "must not reuse the FailureTriageReportV1 schema",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "failure_triage_report":
            source["contentHash"] = "0" * 64
            break
    expect_verifier_result_validation_failure(
        "source_hash_mismatch_failure_triage_report",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "test_execution_result":
            source["contentHash"] = "0" * 64
            break
    expect_verifier_result_validation_failure(
        "source_hash_mismatch_test_execution_result",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "broadcast_subscription_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_verifier_result_validation_failure(
        "source_hash_mismatch_broadcast",
        tampered,
        "source hash mismatch",
    )


def run_verifier_result_builder(artifact_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/verifier_result.py"),
        "--out",
        str(artifact_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "VerifierResultV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_capability_manifest_validation_failure(
    label: str,
    manifest: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_capability_manifest(manifest, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"CapabilityManifestV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"CapabilityManifestV1 forced-failure case {label} unexpectedly passed validation"
    )


def validate_committed_capability_manifest_artifact() -> None:
    artifact = load_json(CAPABILITY_MANIFEST_PATH)
    try:
        validate_capability_manifest(artifact, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed CapabilityManifestV1 artifact failed validation: {exc}"
        ) from exc

    expected_artifact = build_capability_manifest(ROOT)
    if artifact != expected_artifact:
        raise AssertionError(
            "Committed CapabilityManifestV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(artifact))
    tampered["workloadType"] = "read_only_regression_evidence_demo"
    expect_capability_manifest_validation_failure(
        "workload_type_regression_reuse",
        tampered,
        "workloadType must be test_execution_failure_triage",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["kind"] = "RegressionResultArtifactV1"
    expect_capability_manifest_validation_failure(
        "kind_regression_reuse",
        tampered,
        "kind must be CapabilityManifestV1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["schemaVersion"] = "regression-task-spec-v1"
    expect_capability_manifest_validation_failure(
        "schema_regression_reuse",
        tampered,
        "schemaVersion must be capability-manifest-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["artifactEnvelopeSchemaVersion"] = "regression-result-artifact-v1"
    expect_capability_manifest_validation_failure(
        "envelope_schema_regression_reuse",
        tampered,
        "artifactEnvelopeSchemaVersion must be artifact-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierVerdictOwner"] = "creator_agent"
    expect_capability_manifest_validation_failure(
        "creator_owns_verdict",
        tampered,
        "verifierVerdictOwner must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierExpectations"]["creatorMustNotOwnVerdict"] = False
    expect_capability_manifest_validation_failure(
        "creator_must_not_own_verdict_disabled",
        tampered,
        "verifierExpectations.creatorMustNotOwnVerdict must be true",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecSchemaVersion"] = "regression-task-spec-v1"
    expect_capability_manifest_validation_failure(
        "task_spec_binding_regression_schema_reuse",
        tampered,
        "taskSpecSchemaVersion must equal test-execution-task-spec-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecContentHash"] = "0" * 64
    expect_capability_manifest_validation_failure(
        "task_spec_binding_hash_drift",
        tampered,
        "taskSpecContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_capability_manifest_validation_failure(
        "policy_external_side_effects_allowed",
        tampered,
        "policyBoundary.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalCommunicationAllowed"] = True
    expect_capability_manifest_validation_failure(
        "policy_external_communication_allowed",
        tampered,
        "policyBoundary.externalCommunicationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilities"] = []
    expect_capability_manifest_validation_failure(
        "capabilities_empty",
        tampered,
        "capabilities must be a non-empty list",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilities"] = [
        capability
        for capability in tampered["capabilities"]
        if capability["name"] != "write_artifact"
    ]
    expect_capability_manifest_validation_failure(
        "capabilities_missing_required",
        tampered,
        "capability names must equal TestExecutionTaskSpecV1.allowedCapabilityClasses",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilities"].append(
        json.loads(json.dumps(tampered["capabilities"][0]))
    )
    expect_capability_manifest_validation_failure(
        "capabilities_duplicate",
        tampered,
        "duplicate capability name",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "write_artifact":
            capability["sideEffect"] = True
            break
    expect_capability_manifest_validation_failure(
        "capability_side_effect_true",
        tampered,
        "sideEffect must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "write_artifact":
            capability["permission"] = "external"
            break
    expect_capability_manifest_validation_failure(
        "capability_permission_invalid",
        tampered,
        "permission must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "write_artifact":
            capability["timeoutMs"] = 0
            break
    expect_capability_manifest_validation_failure(
        "capability_timeout_invalid",
        tampered,
        "timeoutMs must be a positive integer",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "classify_test_failure":
            capability["allowedEffectClasses"] = ["send_external_communication"]
            break
    expect_capability_manifest_validation_failure(
        "capability_allowed_effects_forbidden",
        tampered,
        "declares forbidden effect classes",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "classify_test_failure":
            capability["allowedEffectClasses"] = ["unknown_effect"]
            break
    expect_capability_manifest_validation_failure(
        "capability_allowed_effects_unknown",
        tampered,
        "allowedEffectClasses contains unknown effect",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "classify_test_failure":
            capability["forbiddenEffectClasses"] = []
            break
    expect_capability_manifest_validation_failure(
        "capability_forbidden_effects_empty",
        tampered,
        "forbiddenEffectClasses must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "write_artifact":
            capability["inputContract"] = {"schema": "", "properties": {}}
            break
    expect_capability_manifest_validation_failure(
        "capability_input_contract_empty",
        tampered,
        "inputContract.schema must be a non-empty string",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "write_artifact":
            capability["evidenceContract"]["producesEvidence"] = "yes"
            break
    expect_capability_manifest_validation_failure(
        "capability_evidence_contract_boolean",
        tampered,
        "evidenceContract.producesEvidence must be a boolean",
    )

    tampered = json.loads(json.dumps(artifact))
    for capability in tampered["capabilities"]:
        if capability["name"] == "write_artifact":
            capability["ref"] = "capability://post-mvp/test_execution/other"
            break
    expect_capability_manifest_validation_failure(
        "capability_ref_mismatch",
        tampered,
        "ref must be capability://post-mvp/test_execution/",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["permissionDomain"] = ["read"]
    expect_capability_manifest_validation_failure(
        "permission_domain_narrowed",
        tampered,
        "permissionDomain must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["effectClassDomain"] = ["read_test_execution_result"]
    expect_capability_manifest_validation_failure(
        "effect_class_domain_narrowed",
        tampered,
        "effectClassDomain must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"].pop("broadcastSubscriptionManifestRef")
    expect_capability_manifest_validation_failure(
        "coordination_binding_missing_broadcast",
        tampered,
        "coordinationBinding must include",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"]["delegationManifestRef"] = "artifacts/runs/all_passed/run.json"
    expect_capability_manifest_validation_failure(
        "coordination_binding_wrong_path",
        tampered,
        "coordinationBinding.delegationManifestRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesRegressionCapabilityCatalog"] = True
    expect_capability_manifest_validation_failure(
        "reuses_regression_capability_catalog",
        tampered,
        "must not reuse the phase3 regression capability catalog",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_capability_manifest_validation_failure(
        "non_regression_reuse_path_missing",
        tampered,
        "nonRegressionReusePath must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "test_execution_task_spec":
            source["contentHash"] = "0" * 64
            break
    expect_capability_manifest_validation_failure(
        "source_hash_mismatch_task_spec",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "broadcast_subscription_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_capability_manifest_validation_failure(
        "source_hash_mismatch_broadcast",
        tampered,
        "source hash mismatch",
    )


def run_capability_manifest_builder(artifact_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/capability_manifest.py"),
        "--out",
        str(artifact_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "CapabilityManifestV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_run_event_log_validation_failure(
    label: str,
    log: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_run_event_log(log, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"RunEventLogV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"RunEventLogV1 forced-failure case {label} unexpectedly passed validation"
    )


def validate_committed_run_event_log_artifact() -> None:
    artifact = load_json(RUN_EVENT_LOG_PATH)
    try:
        validate_run_event_log(artifact, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed RunEventLogV1 artifact failed validation: {exc}"
        ) from exc

    expected_artifact = build_run_event_log(ROOT)
    if artifact != expected_artifact:
        raise AssertionError(
            "Committed RunEventLogV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(artifact))
    tampered["workloadType"] = "read_only_regression_evidence_demo"
    expect_run_event_log_validation_failure(
        "workload_type_regression_reuse",
        tampered,
        "workloadType must be test_execution_failure_triage",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["kind"] = "RegressionResultArtifactV1"
    expect_run_event_log_validation_failure(
        "kind_regression_reuse",
        tampered,
        "kind must be RunEventLogV1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["schemaVersion"] = "regression-task-spec-v1"
    expect_run_event_log_validation_failure(
        "schema_regression_reuse",
        tampered,
        "schemaVersion must be run-event-log-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["artifactEnvelopeSchemaVersion"] = "regression-result-artifact-v1"
    expect_run_event_log_validation_failure(
        "envelope_schema_regression_reuse",
        tampered,
        "artifactEnvelopeSchemaVersion must be artifact-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierVerdictOwner"] = "creator_agent"
    expect_run_event_log_validation_failure(
        "creator_owns_verdict",
        tampered,
        "verifierVerdictOwner must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierExpectations"]["creatorMustNotOwnVerdict"] = False
    expect_run_event_log_validation_failure(
        "creator_must_not_own_verdict_disabled",
        tampered,
        "verifierExpectations.creatorMustNotOwnVerdict must be true",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecSchemaVersion"] = "regression-task-spec-v1"
    expect_run_event_log_validation_failure(
        "task_spec_binding_regression_schema_reuse",
        tampered,
        "taskSpecSchemaVersion must equal test-execution-task-spec-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecContentHash"] = "0" * 64
    expect_run_event_log_validation_failure(
        "task_spec_binding_hash_drift",
        tampered,
        "taskSpecContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilityManifestBinding"]["capabilityManifestSchemaVersion"] = "capability-envelope-v1"
    expect_run_event_log_validation_failure(
        "capability_manifest_binding_regression_schema_reuse",
        tampered,
        "capabilityManifestSchemaVersion must equal capability-manifest-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilityManifestBinding"]["capabilityManifestContentHash"] = "0" * 64
    expect_run_event_log_validation_failure(
        "capability_manifest_binding_hash_drift",
        tampered,
        "capabilityManifestContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_run_event_log_validation_failure(
        "policy_external_side_effects_allowed",
        tampered,
        "policyBoundary.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalCommunicationAllowed"] = True
    expect_run_event_log_validation_failure(
        "policy_external_communication_allowed",
        tampered,
        "policyBoundary.externalCommunicationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"] = []
    expect_run_event_log_validation_failure(
        "events_empty",
        tampered,
        "events must be a non-empty list",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][1]["sequence"] = 99
    expect_run_event_log_validation_failure(
        "event_sequence_non_contiguous",
        tampered,
        "sequence must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][2]["timestampMs"] = 0
    expect_run_event_log_validation_failure(
        "event_timestamp_non_monotonic",
        tampered,
        "timestampMs must be monotonically non-decreasing",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][0]["eventType"] = "capability.invoked"
    expect_run_event_log_validation_failure(
        "event_first_not_run_created",
        tampered,
        "first event eventType must be run.created",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][-1]["eventType"] = "capability.completed"
    expect_run_event_log_validation_failure(
        "event_last_not_run_completed",
        tampered,
        "last event must be run.completed or run.failed",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["eventType"] = "unknown.event"
    expect_run_event_log_validation_failure(
        "event_unknown_type",
        tampered,
        "eventType must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["status"] = "unknown"
    expect_run_event_log_validation_failure(
        "event_unknown_status",
        tampered,
        "status must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["sourceAgent"] = "rogue_agent"
    expect_run_event_log_validation_failure(
        "event_unknown_source_agent",
        tampered,
        "sourceAgent must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["sourceCapability"] = "rogue_capability"
    expect_run_event_log_validation_failure(
        "event_capability_not_in_manifest",
        tampered,
        "sourceCapability must be the run-kernel sentinel",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["payloadHash"] = "0" * 64
    expect_run_event_log_validation_failure(
        "event_payload_hash_mismatch",
        tampered,
        "payloadHash must equal sha256",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["runControlStateAfter"] = "unknown_state"
    expect_run_event_log_validation_failure(
        "event_state_unknown",
        tampered,
        "runControlStateAfter must be in declared states",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][1]["runControlStateAfter"] = "completed"
    expect_run_event_log_validation_failure(
        "event_state_transition_illegal",
        tampered,
        "illegal runControlStateAfter transition",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["schemaVersion"] = "regression-event-v1"
    expect_run_event_log_validation_failure(
        "event_schema_regression_reuse",
        tampered,
        "schemaVersion must be run-event-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["eventId"] = tampered["events"][2]["eventId"]
    expect_run_event_log_validation_failure(
        "event_id_duplicate",
        tampered,
        "duplicate eventId",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["events"][3]["eventId"] = "evt-rogue-0003"
    expect_run_event_log_validation_failure(
        "event_id_format_invalid",
        tampered,
        "eventId must start with",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["allowedRunControlTransitions"] = [["created", "completed"]]
    expect_run_event_log_validation_failure(
        "allowed_transitions_narrowed",
        tampered,
        "allowedRunControlTransitions must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["eventCount"] = 0
    expect_run_event_log_validation_failure(
        "event_count_drift",
        tampered,
        "eventCount must equal len(events)",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["terminalState"] = "running"
    expect_run_event_log_validation_failure(
        "terminal_state_drift",
        tampered,
        "terminalState must equal the last event runControlStateAfter",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"].pop("broadcastSubscriptionManifestRef")
    expect_run_event_log_validation_failure(
        "coordination_binding_missing_broadcast",
        tampered,
        "coordinationBinding must include",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"]["delegationManifestRef"] = "artifacts/runs/all_passed/run.json"
    expect_run_event_log_validation_failure(
        "coordination_binding_wrong_path",
        tampered,
        "coordinationBinding.delegationManifestRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesRegressionRunArtifact"] = True
    expect_run_event_log_validation_failure(
        "reuses_regression_run_artifact",
        tampered,
        "must not reuse the regression run.json artifact",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesRegressionEventsArtifact"] = True
    expect_run_event_log_validation_failure(
        "reuses_regression_events_artifact",
        tampered,
        "must not reuse the regression events.jsonl artifact",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_run_event_log_validation_failure(
        "non_regression_reuse_path_missing",
        tampered,
        "nonRegressionReusePath must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "test_execution_task_spec":
            source["contentHash"] = "0" * 64
            break
    expect_run_event_log_validation_failure(
        "source_hash_mismatch_task_spec",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "test_execution_capability_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_run_event_log_validation_failure(
        "source_hash_mismatch_capability_manifest",
        tampered,
        "source hash mismatch",
    )

    tampered = json.loads(json.dumps(artifact))
    for source in tampered["sourceArtifacts"]:
        if source.get("role") == "broadcast_subscription_manifest":
            source["contentHash"] = "0" * 64
            break
    expect_run_event_log_validation_failure(
        "source_hash_mismatch_broadcast",
        tampered,
        "source hash mismatch",
    )


def run_run_event_log_builder(artifact_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/run_event_log.py"),
        "--out",
        str(artifact_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "RunEventLogV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_delivery_manifest_validation_failure(
    label: str,
    manifest: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_delivery_manifest(manifest, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"DeliveryManifestV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"DeliveryManifestV1 forced-failure case {label} unexpectedly passed validation"
    )


def validate_committed_delivery_manifest_artifact() -> None:
    artifact = load_json(DELIVERY_MANIFEST_PATH)
    try:
        validate_delivery_manifest(artifact, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed DeliveryManifestV1 artifact failed validation: {exc}"
        ) from exc

    expected_artifact = build_delivery_manifest(ROOT)
    if artifact != expected_artifact:
        raise AssertionError(
            "Committed DeliveryManifestV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(artifact))
    tampered["workloadType"] = "read_only_regression_evidence_demo"
    expect_delivery_manifest_validation_failure(
        "workload_type_regression_reuse",
        tampered,
        "workloadType must be test_execution_failure_triage",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["kind"] = "RegressionResultArtifactV1"
    expect_delivery_manifest_validation_failure(
        "kind_regression_reuse",
        tampered,
        "kind must be DeliveryManifestV1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["schemaVersion"] = "regression-result-artifact-v1"
    expect_delivery_manifest_validation_failure(
        "schema_regression_reuse",
        tampered,
        "schemaVersion must be delivery-manifest-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["artifactEnvelopeSchemaVersion"] = "regression-result-artifact-v1"
    expect_delivery_manifest_validation_failure(
        "envelope_schema_regression_reuse",
        tampered,
        "artifactEnvelopeSchemaVersion must be artifact-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["deliveryChannelSchemaVersion"] = "regression-channel-v1"
    expect_delivery_manifest_validation_failure(
        "channel_envelope_schema_regression_reuse",
        tampered,
        "deliveryChannelSchemaVersion must be delivery-channel-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierVerdictOwner"] = "creator_agent"
    expect_delivery_manifest_validation_failure(
        "creator_owns_verdict",
        tampered,
        "verifierVerdictOwner must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierExpectations"]["creatorMustNotOwnVerdict"] = False
    expect_delivery_manifest_validation_failure(
        "creator_must_not_own_verdict_disabled",
        tampered,
        "verifierExpectations.creatorMustNotOwnVerdict must be true",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecSchemaVersion"] = "regression-task-spec-v1"
    expect_delivery_manifest_validation_failure(
        "task_spec_binding_regression_schema_reuse",
        tampered,
        "taskSpecSchemaVersion must equal test-execution-task-spec-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecContentHash"] = "0" * 64
    expect_delivery_manifest_validation_failure(
        "task_spec_binding_hash_drift",
        tampered,
        "taskSpecContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilityManifestBinding"]["capabilityManifestSchemaVersion"] = "capability-envelope-v1"
    expect_delivery_manifest_validation_failure(
        "capability_manifest_binding_regression_schema_reuse",
        tampered,
        "capabilityManifestSchemaVersion must equal capability-manifest-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilityManifestBinding"]["capabilityManifestContentHash"] = "0" * 64
    expect_delivery_manifest_validation_failure(
        "capability_manifest_binding_hash_drift",
        tampered,
        "capabilityManifestContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierResultBinding"]["verifierResultSchemaVersion"] = "regression-result-artifact-v1"
    expect_delivery_manifest_validation_failure(
        "verifier_result_binding_regression_schema_reuse",
        tampered,
        "verifierResultSchemaVersion must equal verifier-result-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierResultBinding"]["verifierResultContentHash"] = "0" * 64
    expect_delivery_manifest_validation_failure(
        "verifier_result_binding_hash_drift",
        tampered,
        "verifierResultContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["runEventLogBinding"]["runEventLogSchemaVersion"] = "regression-events-v1"
    expect_delivery_manifest_validation_failure(
        "run_event_log_binding_regression_schema_reuse",
        tampered,
        "runEventLogSchemaVersion must equal run-event-log-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["runEventLogBinding"]["runEventLogContentHash"] = "0" * 64
    expect_delivery_manifest_validation_failure(
        "run_event_log_binding_hash_drift",
        tampered,
        "runEventLogContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_delivery_manifest_validation_failure(
        "policy_external_side_effects_allowed",
        tampered,
        "policyBoundary.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["externalCommunicationAllowed"] = True
    expect_delivery_manifest_validation_failure(
        "policy_external_communication_allowed",
        tampered,
        "policyBoundary.externalCommunicationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyBoundary"]["repositoryMutationAllowed"] = True
    expect_delivery_manifest_validation_failure(
        "policy_repository_mutation_allowed",
        tampered,
        "policyBoundary.repositoryMutationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"] = []
    expect_delivery_manifest_validation_failure(
        "channels_empty",
        tampered,
        "channels must be a non-empty list",
    )

    tampered = json.loads(json.dumps(artifact))
    del tampered["channels"][0]["channelKind"]
    expect_delivery_manifest_validation_failure(
        "channel_missing_required",
        tampered,
        "missing required fields",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][1]["channelName"] = tampered["channels"][0]["channelName"]
    expect_delivery_manifest_validation_failure(
        "channel_duplicate_name",
        tampered,
        "duplicate channelName",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["channelKind"] = "external_email"
    expect_delivery_manifest_validation_failure(
        "channel_kind_unknown",
        tampered,
        "channelKind must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["channelStatus"] = "sent"
    expect_delivery_manifest_validation_failure(
        "channel_status_real_delivery",
        tampered,
        "channelStatus must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["channelStatus"] = "drafted_internal_only"
    expect_delivery_manifest_validation_failure(
        "channel_status_inconsistent_with_gates",
        tampered,
        "channelStatus must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["unlocked"] = True
    expect_delivery_manifest_validation_failure(
        "channel_unlocked_when_blocked",
        tampered,
        "unlocked must equal the gate-derived",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["policyBoundary"]["externalSideEffectsAllowed"] = True
    expect_delivery_manifest_validation_failure(
        "channel_policy_external_side_effects_allowed",
        tampered,
        "policyBoundary.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["policyBoundary"]["externalCommunicationAllowed"] = True
    expect_delivery_manifest_validation_failure(
        "channel_policy_external_communication_allowed",
        tampered,
        "policyBoundary.externalCommunicationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["approvalRef"] = "artifacts/runs/all_passed/run.json"
    expect_delivery_manifest_validation_failure(
        "channel_approval_ref_path_invalid",
        tampered,
        "approvalRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["evidenceContract"]["verifierResultRef"] = "artifacts/runs/all_passed/run.json"
    expect_delivery_manifest_validation_failure(
        "channel_evidence_ref_mismatch",
        tampered,
        "evidenceContract.verifierResultRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["payloadContract"]["rendering"] = "external_publish"
    expect_delivery_manifest_validation_failure(
        "channel_payload_rendering_external",
        tampered,
        "payloadContract.rendering must be internal_only",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channels"][0]["schemaVersion"] = "regression-channel-v1"
    expect_delivery_manifest_validation_failure(
        "channel_schema_regression_reuse",
        tampered,
        "schemaVersion must be delivery-channel-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["requiredVerdictForUnlock"] = "needs_human_check"
    expect_delivery_manifest_validation_failure(
        "required_verdict_not_passed",
        tampered,
        "requiredVerdictForUnlock must be passed",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verdictGate"]["unlocked"] = True
    expect_delivery_manifest_validation_failure(
        "verdict_gate_unlocked_when_verdict_failed",
        tampered,
        "verdictGate.unlocked must be true only when currentVerdict equals",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["runTerminalStateGate"]["currentTerminalState"] = "running"
    expect_delivery_manifest_validation_failure(
        "run_terminal_state_gate_drift",
        tampered,
        "runTerminalStateGate.currentTerminalState must equal RunEventLogV1.terminalState",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["approvalGate"]["granted"] = True
    expect_delivery_manifest_validation_failure(
        "approval_gate_granted_when_rejected",
        tampered,
        "approvalGate.granted must equal HumanApprovalDecisionV1.decision.approvalGranted",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["approvalGate"]["unlocked"] = True
    expect_delivery_manifest_validation_failure(
        "approval_gate_unlocked_when_not_granted",
        tampered,
        "approvalGate.unlocked must equal approvalGate.granted",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"].pop("broadcastSubscriptionManifestRef")
    expect_delivery_manifest_validation_failure(
        "coordination_binding_missing_broadcast",
        tampered,
        "coordinationBinding must include",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"]["delegationManifestRef"] = "artifacts/runs/all_passed/run.json"
    expect_delivery_manifest_validation_failure(
        "coordination_binding_wrong_path",
        tampered,
        "coordinationBinding.delegationManifestRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesRegressionEmailDraft"] = True
    expect_delivery_manifest_validation_failure(
        "reuses_regression_email_draft",
        tampered,
        "must not reuse the regression email_draft.md artifact",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesPhase9DeliveryReport"] = True
    expect_delivery_manifest_validation_failure(
        "reuses_phase9_delivery_report",
        tampered,
        "must not reuse phase9_delivery_report.json",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesSendEmailCapability"] = True
    expect_delivery_manifest_validation_failure(
        "reuses_send_email_capability",
        tampered,
        "must not reuse the send_email capability",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_delivery_manifest_validation_failure(
        "non_regression_reuse_path_missing",
        tampered,
        "nonRegressionReusePath must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["channelCount"] = 0
    expect_delivery_manifest_validation_failure(
        "channel_count_drift",
        tampered,
        "channelCount must equal len(channels)",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["anyChannelUnlocked"] = True
    expect_delivery_manifest_validation_failure(
        "any_channel_unlocked_drift",
        tampered,
        "anyChannelUnlocked must reflect channels",
    )

    for hash_role, label in [
        ("test_execution_task_spec", "source_hash_mismatch_task_spec"),
        ("test_execution_capability_manifest", "source_hash_mismatch_capability_manifest"),
        ("test_execution_verifier_result", "source_hash_mismatch_verifier_result"),
        ("test_execution_run_event_log", "source_hash_mismatch_run_event_log"),
        ("broadcast_subscription_manifest", "source_hash_mismatch_broadcast"),
    ]:
        tampered = json.loads(json.dumps(artifact))
        for source in tampered["sourceArtifacts"]:
            if source.get("role") == hash_role:
                source["contentHash"] = "0" * 64
                break
        expect_delivery_manifest_validation_failure(
            label,
            tampered,
            "source hash mismatch",
        )


def run_delivery_manifest_builder(artifact_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/delivery_manifest.py"),
        "--out",
        str(artifact_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "DeliveryManifestV1 builder failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def expect_policy_manifest_validation_failure(
    label: str,
    manifest: dict,
    expected_message_fragment: str,
) -> None:
    try:
        validate_policy_manifest(manifest, ROOT)
    except ValueError as exc:
        message = str(exc)
        if expected_message_fragment not in message:
            raise AssertionError(
                f"PolicyManifestV1 forced-failure case {label} failed for the wrong reason.\n"
                f"Expected message fragment: {expected_message_fragment}\n"
                f"Actual message: {message}"
            ) from exc
        return
    raise AssertionError(
        f"PolicyManifestV1 forced-failure case {label} unexpectedly passed validation"
    )


def _find_policy_rule_index(rules: list, *, rule_kind: str, key: str | None = None, value: str | None = None) -> int:
    for index, rule in enumerate(rules):
        if rule.get("ruleKind") != rule_kind:
            continue
        if key is None:
            return index
        if rule.get(key) == value:
            return index
    raise AssertionError(
        f"PolicyManifestV1 forced-failure case could not locate rule with kind={rule_kind} {key}={value}"
    )


def validate_committed_policy_manifest_artifact() -> None:
    artifact = load_json(POLICY_MANIFEST_PATH)
    try:
        validate_policy_manifest(artifact, ROOT)
    except ValueError as exc:
        raise AssertionError(
            f"Committed PolicyManifestV1 artifact failed validation: {exc}"
        ) from exc

    expected_artifact = build_policy_manifest(ROOT)
    if artifact != expected_artifact:
        raise AssertionError(
            "Committed PolicyManifestV1 artifact differs from deterministic builder output"
        )

    tampered = json.loads(json.dumps(artifact))
    tampered["workloadType"] = "read_only_regression_evidence_demo"
    expect_policy_manifest_validation_failure(
        "workload_type_regression_reuse",
        tampered,
        "workloadType must be test_execution_failure_triage",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["kind"] = "RegressionResultArtifactV1"
    expect_policy_manifest_validation_failure(
        "kind_regression_reuse",
        tampered,
        "kind must be PolicyManifestV1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["schemaVersion"] = "regression-result-artifact-v1"
    expect_policy_manifest_validation_failure(
        "schema_regression_reuse",
        tampered,
        "schemaVersion must be policy-manifest-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["artifactEnvelopeSchemaVersion"] = "regression-result-artifact-v1"
    expect_policy_manifest_validation_failure(
        "envelope_schema_regression_reuse",
        tampered,
        "artifactEnvelopeSchemaVersion must be artifact-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyOwner"] = "creator_agent"
    expect_policy_manifest_validation_failure(
        "policy_owner_creator",
        tampered,
        "policyOwner must be policy-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierVerdictOwner"] = "creator_agent"
    expect_policy_manifest_validation_failure(
        "creator_owns_verdict",
        tampered,
        "verifierVerdictOwner must be verifier-runtime-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierExpectations"]["creatorMustNotOwnVerdict"] = False
    expect_policy_manifest_validation_failure(
        "creator_must_not_own_verdict_disabled",
        tampered,
        "verifierExpectations.creatorMustNotOwnVerdict must be true",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["permissionFlags"]["externalSideEffectsAllowed"] = True
    expect_policy_manifest_validation_failure(
        "permission_flag_external_side_effects_true",
        tampered,
        "permissionFlags.externalSideEffectsAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["permissionFlags"]["repositoryMutationAllowed"] = True
    expect_policy_manifest_validation_failure(
        "permission_flag_repository_mutation_true",
        tampered,
        "permissionFlags.repositoryMutationAllowed must be false",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["permissionFlags"].pop("publicAccessAllowed")
    expect_policy_manifest_validation_failure(
        "permission_flag_missing",
        tampered,
        "permissionFlags must declare every flag",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["permissionFlagDomain"] = ["externalSideEffectsAllowed"]
    expect_policy_manifest_validation_failure(
        "permission_flag_domain_drift",
        tampered,
        "permissionFlagDomain must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["effectClassDomain"] = ["internal_read"]
    expect_policy_manifest_validation_failure(
        "effect_class_domain_drift",
        tampered,
        "effectClassDomain must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["allowEffectClasses"] = []
    expect_policy_manifest_validation_failure(
        "allow_effect_classes_drift",
        tampered,
        "allowEffectClasses must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["denyEffectClasses"] = []
    expect_policy_manifest_validation_failure(
        "deny_effect_classes_drift",
        tampered,
        "denyEffectClasses must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    for entry in tampered["effectClasses"]:
        if entry["className"] == "external_side_effect":
            entry["decision"] = "allow"
            break
    expect_policy_manifest_validation_failure(
        "effect_class_external_side_effect_allow",
        tampered,
        "decision must be deny for class external_side_effect",
    )

    tampered = json.loads(json.dumps(artifact))
    for entry in tampered["effectClasses"]:
        if entry["className"] == "internal_read":
            entry["decision"] = "deny"
            break
    expect_policy_manifest_validation_failure(
        "effect_class_internal_read_deny",
        tampered,
        "decision must be allow for class internal_read",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["effectClasses"] = tampered["effectClasses"][:-1]
    expect_policy_manifest_validation_failure(
        "effect_classes_truncated",
        tampered,
        "effectClasses must be a list of length",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["effectClasses"][0]["schemaVersion"] = "regression-policy-effect-class-v1"
    expect_policy_manifest_validation_failure(
        "effect_class_schema_regression_reuse",
        tampered,
        "schemaVersion must be policy-effect-class-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyRules"] = []
    expect_policy_manifest_validation_failure(
        "policy_rules_empty",
        tampered,
        "policyRules must be a non-empty list",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="capability_allow", key="appliesToCapability", value="write_artifact"
    )
    tampered["policyRules"][idx]["effectClass"] = "internal_read"
    expect_policy_manifest_validation_failure(
        "capability_rule_effect_class_mismatch",
        tampered,
        "for capability write_artifact",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="capability_allow", key="appliesToCapability", value="read_test_execution_result"
    )
    tampered["policyRules"][idx]["decision"] = "deny"
    expect_policy_manifest_validation_failure(
        "capability_rule_decision_deny",
        tampered,
        "capability_allow.decision must be allow",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="capability_allow", key="appliesToCapability", value="read_test_execution_result"
    )
    tampered["policyRules"][idx]["appliesToCapability"] = "send_email_capability"
    expect_policy_manifest_validation_failure(
        "capability_rule_unknown_capability",
        tampered,
        "appliesToCapability must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="capability_allow", key="appliesToCapability", value="classify_test_failure"
    )
    del tampered["policyRules"][idx]
    expect_policy_manifest_validation_failure(
        "capability_rule_missing_for_capability",
        tampered,
        "must declare a capability_allow rule for every CapabilityManifestV1 capability",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="effect_class_deny", key="effectClass", value="external_communication"
    )
    tampered["policyRules"][idx]["decision"] = "allow"
    expect_policy_manifest_validation_failure(
        "effect_class_deny_rule_decision_allow",
        tampered,
        "effect_class_deny.decision must be deny",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="effect_class_deny", key="effectClass", value="public_access"
    )
    tampered["policyRules"][idx]["effectClass"] = "internal_read"
    expect_policy_manifest_validation_failure(
        "effect_class_deny_rule_allow_class",
        tampered,
        "effect_class_deny must be one of",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="effect_class_deny", key="effectClass", value="release_or_deployment"
    )
    del tampered["policyRules"][idx]
    expect_policy_manifest_validation_failure(
        "effect_class_deny_rule_missing",
        tampered,
        "must declare an effect_class_deny rule for every deny effect class",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="permission_flag_deny", key="permissionFlag", value="publicAccessAllowed"
    )
    tampered["policyRules"][idx]["decision"] = "allow"
    expect_policy_manifest_validation_failure(
        "permission_flag_deny_rule_decision_allow",
        tampered,
        "permission_flag_deny.decision must be deny",
    )

    tampered = json.loads(json.dumps(artifact))
    idx = _find_policy_rule_index(
        tampered["policyRules"], rule_kind="permission_flag_deny", key="permissionFlag", value="repositoryMutationAllowed"
    )
    del tampered["policyRules"][idx]
    expect_policy_manifest_validation_failure(
        "permission_flag_deny_rule_missing",
        tampered,
        "must declare a permission_flag_deny rule for every permission flag",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyRuleCount"] = 0
    expect_policy_manifest_validation_failure(
        "policy_rule_count_drift",
        tampered,
        "policyRuleCount must equal len(policyRules)",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["policyRules"][0]["schemaVersion"] = "regression-policy-rule-v1"
    expect_policy_manifest_validation_failure(
        "policy_rule_schema_regression_reuse",
        tampered,
        "schemaVersion must be policy-rule-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["revocationRules"] = []
    expect_policy_manifest_validation_failure(
        "revocation_rules_empty",
        tampered,
        "revocationRules must declare at least five",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["revocationRules"][0]["action"] = "warn"
    expect_policy_manifest_validation_failure(
        "revocation_rule_action_not_revoke",
        tampered,
        "action must be revoke_all_unlocks",
    )

    tampered = json.loads(json.dumps(artifact))
    for rule in tampered["revocationRules"]:
        if rule.get("trigger") == "verifier_result_verdict_not_passed":
            rule["trigger"] = "unknown_workload_specific_trigger"
            break
    expect_policy_manifest_validation_failure(
        "revocation_rule_missing_verdict_trigger",
        tampered,
        "must cover triggers",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["revocationRules"][0]["schemaVersion"] = "regression-policy-revocation-rule-v1"
    expect_policy_manifest_validation_failure(
        "revocation_rule_schema_regression_reuse",
        tampered,
        "schemaVersion must be policy-revocation-rule-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecSchemaVersion"] = "regression-task-spec-v1"
    expect_policy_manifest_validation_failure(
        "task_spec_binding_regression_schema_reuse",
        tampered,
        "taskSpecSchemaVersion must equal test-execution-task-spec-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["taskSpecBinding"]["taskSpecContentHash"] = "0" * 64
    expect_policy_manifest_validation_failure(
        "task_spec_binding_hash_drift",
        tampered,
        "taskSpecContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilityManifestBinding"]["capabilityManifestSchemaVersion"] = "capability-envelope-v1"
    expect_policy_manifest_validation_failure(
        "capability_manifest_binding_regression_schema_reuse",
        tampered,
        "capabilityManifestSchemaVersion must equal capability-manifest-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["capabilityManifestBinding"]["capabilityManifestContentHash"] = "0" * 64
    expect_policy_manifest_validation_failure(
        "capability_manifest_binding_hash_drift",
        tampered,
        "capabilityManifestContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["runEventLogBinding"]["runEventLogSchemaVersion"] = "regression-events-v1"
    expect_policy_manifest_validation_failure(
        "run_event_log_binding_regression_schema_reuse",
        tampered,
        "runEventLogSchemaVersion must equal run-event-log-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["runEventLogBinding"]["runEventLogContentHash"] = "0" * 64
    expect_policy_manifest_validation_failure(
        "run_event_log_binding_hash_drift",
        tampered,
        "runEventLogContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierResultBinding"]["verifierResultSchemaVersion"] = "regression-result-artifact-v1"
    expect_policy_manifest_validation_failure(
        "verifier_result_binding_regression_schema_reuse",
        tampered,
        "verifierResultSchemaVersion must equal verifier-result-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["verifierResultBinding"]["verifierResultContentHash"] = "0" * 64
    expect_policy_manifest_validation_failure(
        "verifier_result_binding_hash_drift",
        tampered,
        "verifierResultContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["deliveryManifestBinding"]["deliveryManifestSchemaVersion"] = "multi-agent-delivery-manifest-v1"
    expect_policy_manifest_validation_failure(
        "delivery_manifest_binding_regression_schema_reuse",
        tampered,
        "deliveryManifestSchemaVersion must equal delivery-manifest-v1",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["deliveryManifestBinding"]["deliveryManifestContentHash"] = "0" * 64
    expect_policy_manifest_validation_failure(
        "delivery_manifest_binding_hash_drift",
        tampered,
        "deliveryManifestContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["approvalRecordBinding"]["approvalRecordContentHash"] = "0" * 64
    expect_policy_manifest_validation_failure(
        "approval_record_binding_hash_drift",
        tampered,
        "approvalRecordContentHash must match",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["unlockConditions"]["requiredVerdict"] = "needs_human_check"
    expect_policy_manifest_validation_failure(
        "unlock_required_verdict_not_passed",
        tampered,
        "unlockConditions.requiredVerdict must be passed",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["unlockConditions"]["unlocked"] = True
    expect_policy_manifest_validation_failure(
        "unlock_unlocked_when_blocked",
        tampered,
        "unlockConditions.unlocked must be true only when verdict",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"].pop("broadcastSubscriptionManifestRef")
    expect_policy_manifest_validation_failure(
        "coordination_binding_missing_broadcast",
        tampered,
        "coordinationBinding must include",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["coordinationBinding"]["delegationManifestRef"] = "artifacts/runs/all_passed/run.json"
    expect_policy_manifest_validation_failure(
        "coordination_binding_wrong_path",
        tampered,
        "coordinationBinding.delegationManifestRef must equal",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesPhase7AdapterPolicyManifest"] = True
    expect_policy_manifest_validation_failure(
        "reuses_phase7_adapter_policy_manifest",
        tampered,
        "must not reuse phase7_adapter_policy_manifest.json",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesPolicyUnlockDenialFixture"] = True
    expect_policy_manifest_validation_failure(
        "reuses_policy_unlock_denial_fixture",
        tampered,
        "must not reuse post_mvp_policy_unlock_request_denied.json",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["regressionWorkloadIsolation"]["reusesSendEmailCapability"] = True
    expect_policy_manifest_validation_failure(
        "reuses_send_email_capability",
        tampered,
        "must not reuse the send_email capability",
    )

    tampered = json.loads(json.dumps(artifact))
    tampered["nonRegressionReusePath"] = ["read_only_regression_evidence_demo"]
    expect_policy_manifest_validation_failure(
        "non_regression_reuse_path_missing",
        tampered,
        "nonRegressionReusePath must equal",
    )

    for hash_role, label in [
        ("test_execution_task_spec", "source_hash_mismatch_task_spec"),
        ("test_execution_capability_manifest", "source_hash_mismatch_capability_manifest"),
        ("test_execution_run_event_log", "source_hash_mismatch_run_event_log"),
        ("test_execution_verifier_result", "source_hash_mismatch_verifier_result"),
        ("test_execution_delivery_manifest", "source_hash_mismatch_delivery_manifest"),
        ("broadcast_subscription_manifest", "source_hash_mismatch_broadcast"),
    ]:
        tampered = json.loads(json.dumps(artifact))
        for source in tampered["sourceArtifacts"]:
            if source.get("role") == hash_role:
                source["contentHash"] = "0" * 64
                break
        expect_policy_manifest_validation_failure(
            label,
            tampered,
            "source hash mismatch",
        )


def run_policy_manifest_builder(artifact_out: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/policy_manifest.py"),
        "--out",
        str(artifact_out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "PolicyManifestV1 builder failed.\n"
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
    validate_committed_replay_query_artifact()
    validate_committed_identity_bound_approval_record_artifact()
    validate_committed_approval_audit_query_artifact()
    validate_committed_approval_revocation_artifact()
    validate_committed_policy_unlock_denial_artifact()
    validate_committed_delegation_manifest_artifact()
    validate_committed_creator_verifier_pairing_artifact()
    validate_committed_agent_message_manifest_artifact()
    validate_committed_negotiation_record_artifact()
    validate_committed_broadcast_subscription_manifest_artifact()
    validate_committed_test_execution_task_spec_artifact()
    validate_committed_test_execution_result_artifact()
    validate_committed_failure_triage_report_artifact()
    validate_committed_verifier_result_artifact()
    validate_committed_capability_manifest_artifact()
    validate_committed_run_event_log_artifact()
    validate_committed_delivery_manifest_artifact()
    validate_committed_policy_manifest_artifact()
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
        generated_replay_query = temp_root / "post_mvp_replay_query.json"
        run_replay_query_builder(generated_replay_query)
        if load_json(generated_replay_query) != load_json(REPLAY_QUERY_PATH):
            raise AssertionError("Committed ReplayQueryV1 artifact differs from deterministic CLI output")
        generated_identity_bound_approval_record = temp_root / "post_mvp_identity_bound_approval_record.json"
        run_identity_bound_approval_record_builder(generated_identity_bound_approval_record)
        if load_json(generated_identity_bound_approval_record) != load_json(IDENTITY_BOUND_APPROVAL_RECORD_PATH):
            raise AssertionError("Committed IdentityBoundApprovalRecordV1 artifact differs from deterministic CLI output")
        generated_approval_audit_query = temp_root / "post_mvp_approval_audit_query.json"
        run_approval_audit_query_builder(generated_approval_audit_query)
        if load_json(generated_approval_audit_query) != load_json(APPROVAL_AUDIT_QUERY_PATH):
            raise AssertionError("Committed ApprovalAuditQueryV1 artifact differs from deterministic CLI output")
        generated_approval_revocation = temp_root / "post_mvp_approval_revocation_or_expiry.json"
        run_approval_revocation_builder(generated_approval_revocation)
        if load_json(generated_approval_revocation) != load_json(APPROVAL_REVOCATION_PATH):
            raise AssertionError("Committed ApprovalRevocationOrExpiryV1 artifact differs from deterministic CLI output")
        generated_policy_unlock_denial = temp_root / "post_mvp_policy_unlock_request_denied.json"
        run_policy_unlock_denial_builder(generated_policy_unlock_denial)
        if load_json(generated_policy_unlock_denial) != load_json(POLICY_UNLOCK_DENIAL_PATH):
            raise AssertionError("Committed PolicyUnlockRequestDeniedV1 artifact differs from deterministic CLI output")
        generated_delegation_manifest = temp_root / "post_mvp_delegation_manifest.json"
        run_delegation_manifest_builder(generated_delegation_manifest)
        if load_json(generated_delegation_manifest) != load_json(DELEGATION_MANIFEST_PATH):
            raise AssertionError("Committed DelegationManifestV1 artifact differs from deterministic CLI output")
        generated_creator_verifier_pairing = temp_root / "post_mvp_creator_verifier_pairing.json"
        run_creator_verifier_pairing_builder(generated_creator_verifier_pairing)
        if load_json(generated_creator_verifier_pairing) != load_json(CREATOR_VERIFIER_PAIRING_PATH):
            raise AssertionError("Committed CreatorVerifierPairingV1 artifact differs from deterministic CLI output")
        generated_agent_message_manifest = temp_root / "post_mvp_agent_message_manifest.json"
        run_agent_message_manifest_builder(generated_agent_message_manifest)
        if load_json(generated_agent_message_manifest) != load_json(AGENT_MESSAGE_MANIFEST_PATH):
            raise AssertionError("Committed AgentMessageManifestV1 artifact differs from deterministic CLI output")
        generated_negotiation_record = temp_root / "post_mvp_negotiation_record.json"
        run_negotiation_record_builder(generated_negotiation_record)
        if load_json(generated_negotiation_record) != load_json(NEGOTIATION_RECORD_PATH):
            raise AssertionError("Committed NegotiationRecordV1 artifact differs from deterministic CLI output")
        generated_broadcast_subscription_manifest = temp_root / "post_mvp_broadcast_subscription_manifest.json"
        run_broadcast_subscription_manifest_builder(generated_broadcast_subscription_manifest)
        if load_json(generated_broadcast_subscription_manifest) != load_json(BROADCAST_SUBSCRIPTION_MANIFEST_PATH):
            raise AssertionError(
                "Committed BroadcastSubscriptionManifestV1 artifact differs from deterministic CLI output"
            )
        generated_test_execution_task_spec = temp_root / "post_mvp_test_execution_task_spec.json"
        run_test_execution_task_spec_builder(generated_test_execution_task_spec)
        if load_json(generated_test_execution_task_spec) != load_json(TEST_EXECUTION_TASK_SPEC_PATH):
            raise AssertionError(
                "Committed TestExecutionTaskSpecV1 artifact differs from deterministic CLI output"
            )
        generated_test_execution_result = temp_root / "post_mvp_test_execution_result.json"
        run_test_execution_result_builder(generated_test_execution_result)
        if load_json(generated_test_execution_result) != load_json(TEST_EXECUTION_RESULT_PATH):
            raise AssertionError(
                "Committed TestExecutionResultV1 artifact differs from deterministic CLI output"
            )
        generated_failure_triage_report = temp_root / "post_mvp_failure_triage_report.json"
        run_failure_triage_report_builder(generated_failure_triage_report)
        if load_json(generated_failure_triage_report) != load_json(FAILURE_TRIAGE_REPORT_PATH):
            raise AssertionError(
                "Committed FailureTriageReportV1 artifact differs from deterministic CLI output"
            )
        generated_verifier_result = temp_root / "post_mvp_verifier_result_test_execution.json"
        run_verifier_result_builder(generated_verifier_result)
        if load_json(generated_verifier_result) != load_json(VERIFIER_RESULT_PATH):
            raise AssertionError(
                "Committed VerifierResultV1 artifact differs from deterministic CLI output"
            )
        generated_capability_manifest = temp_root / "post_mvp_test_execution_capability_manifest.json"
        run_capability_manifest_builder(generated_capability_manifest)
        if load_json(generated_capability_manifest) != load_json(CAPABILITY_MANIFEST_PATH):
            raise AssertionError(
                "Committed CapabilityManifestV1 artifact differs from deterministic CLI output"
            )
        generated_run_event_log = temp_root / "post_mvp_test_execution_run_event_log.json"
        run_run_event_log_builder(generated_run_event_log)
        if load_json(generated_run_event_log) != load_json(RUN_EVENT_LOG_PATH):
            raise AssertionError(
                "Committed RunEventLogV1 artifact differs from deterministic CLI output"
            )
        generated_delivery_manifest = temp_root / "post_mvp_test_execution_delivery_manifest.json"
        run_delivery_manifest_builder(generated_delivery_manifest)
        if load_json(generated_delivery_manifest) != load_json(DELIVERY_MANIFEST_PATH):
            raise AssertionError(
                "Committed DeliveryManifestV1 artifact differs from deterministic CLI output"
            )
        generated_policy_manifest = temp_root / "post_mvp_test_execution_policy_manifest.json"
        run_policy_manifest_builder(generated_policy_manifest)
        if load_json(generated_policy_manifest) != load_json(POLICY_MANIFEST_PATH):
            raise AssertionError(
                "Committed PolicyManifestV1 artifact differs from deterministic CLI output"
            )
        generated_evaluation_report = temp_root / "phase9_mvp_evaluation_report.json"
        run_evaluation_report_builder(generated_evaluation_report)
        if load_json(generated_evaluation_report) != load_json(EVALUATION_REPORT_PATH):
            raise AssertionError("Committed EvaluationReportV1 artifact differs from deterministic CLI output")

    print("Repository validation passed.")


if __name__ == "__main__":
    main()

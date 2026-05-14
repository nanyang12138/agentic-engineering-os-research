from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from multi_agent_delivery import (
    DELIVERY_REPORT_ARTIFACT_PATH,
    MANIFEST_ARTIFACT_PATH as MULTI_AGENT_DELIVERY_MANIFEST_ARTIFACT_PATH,
    validate_delivery_report,
)
from human_approval import DECISION_ARTIFACT_PATH as HUMAN_APPROVAL_DECISION_ARTIFACT_PATH, validate_human_approval_decision
from durable_run_store import STORE_ARTIFACT_PATH as DURABLE_RUN_STORE_ARTIFACT_PATH, validate_durable_run_store
from replay_query import QUERY_ARTIFACT_PATH as REPLAY_QUERY_ARTIFACT_PATH, validate_replay_query
from identity_bound_approval import (
    RECORD_ARTIFACT_PATH as IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH,
    validate_identity_bound_approval_record,
)
from approval_audit_query import (
    AUDIT_ARTIFACT_PATH as APPROVAL_AUDIT_QUERY_ARTIFACT_PATH,
    validate_approval_audit_query,
)
from approval_revocation import (
    REVOCATION_ARTIFACT_PATH as APPROVAL_REVOCATION_ARTIFACT_PATH,
    validate_approval_revocation_or_expiry,
)
from policy_unlock_denial import (
    UNLOCK_DENIAL_ARTIFACT_PATH as POLICY_UNLOCK_DENIAL_ARTIFACT_PATH,
    validate_policy_unlock_request_denied,
)
from coordination_contract import (
    AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
    CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    DELEGATION_MANIFEST_ARTIFACT_PATH,
    NEGOTIATION_RECORD_ARTIFACT_PATH,
    validate_agent_message_manifest,
    validate_broadcast_subscription_manifest,
    validate_creator_verifier_pairing,
    validate_delegation_manifest,
    validate_negotiation_record,
)
from test_execution_task_spec import (
    TASK_SPEC_ARTIFACT_PATH as TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    validate_test_execution_task_spec,
)
from test_execution_result import (
    TEST_EXECUTION_RESULT_ARTIFACT_PATH,
    validate_test_execution_result,
)
from failure_triage_report import (
    FAILURE_TRIAGE_REPORT_ARTIFACT_PATH,
    validate_failure_triage_report,
)
from verifier_result import (
    VERIFIER_RESULT_ARTIFACT_PATH,
    validate_verifier_result,
)
from capability_manifest import (
    CAPABILITY_MANIFEST_ARTIFACT_PATH,
    validate_capability_manifest,
)
from run_event_log import (
    RUN_EVENT_LOG_ARTIFACT_PATH,
    validate_run_event_log,
)
from delivery_manifest import (
    DELIVERY_MANIFEST_ARTIFACT_PATH,
    validate_delivery_manifest,
)
from policy_manifest import (
    POLICY_MANIFEST_ARTIFACT_PATH as POST_MVP_POLICY_MANIFEST_ARTIFACT_PATH,
    validate_policy_manifest,
)
from evidence_artifact import (
    EVIDENCE_LIST_ARTIFACT_PATH as POST_MVP_EVIDENCE_LIST_ARTIFACT_PATH,
    validate_evidence_list_artifact,
)
from observation_artifact import (
    OBSERVATION_LIST_ARTIFACT_PATH as POST_MVP_OBSERVATION_LIST_ARTIFACT_PATH,
    validate_observation_list_artifact,
)
from run_artifact import (
    RUN_ARTIFACT_PATH as POST_MVP_RUN_ARTIFACT_PATH,
    validate_run_artifact,
)
from step_list_artifact import (
    STEP_LIST_ARTIFACT_PATH as POST_MVP_STEP_LIST_ARTIFACT_PATH,
    validate_step_list_artifact,
)
from tool_call_list_artifact import (
    TOOL_CALL_LIST_ARTIFACT_PATH as POST_MVP_TOOL_CALL_LIST_ARTIFACT_PATH,
    validate_tool_call_list_artifact,
)
from intent_artifact import (
    INTENT_ARTIFACT_PATH as POST_MVP_INTENT_ARTIFACT_PATH,
    validate_intent_artifact,
)
from capability_kernel import (
    CAPABILITY_KERNEL_ARTIFACT_PATH as POST_MVP_CAPABILITY_KERNEL_ARTIFACT_PATH,
    validate_capability_kernel_artifact,
)
from policy_kernel import (
    POLICY_KERNEL_ARTIFACT_PATH as POST_MVP_POLICY_KERNEL_ARTIFACT_PATH,
    validate_policy_kernel_artifact,
)


EVALUATION_REPORT_SCHEMA_VERSION = "mvp-evaluation-report-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
REPORT_ID = "read-only-regression-evidence-demo-mvp-evaluation"
REPORT_ARTIFACT_PATH = "artifacts/evaluation/phase9_mvp_evaluation_report.json"

FIXTURE_IDS = [
    "all_passed",
    "failed_tests",
    "incomplete_jobs",
    "passed_with_warning_or_waiver",
    "ambiguous_summary",
]

EXPECTED_PHASES = [
    "phase1a",
    "phase1b",
    "phase2",
    "phase3",
    "phase4",
    "phase5",
    "phase6",
    "phase7",
    "phase8",
    "phase9",
]

REQUIRED_BLOCKER_IDS = {
    "human_approval_missing",
    "external_delivery_disabled_by_mvp_policy",
    "real_provider_execution_out_of_scope",
    "full_product_runtime_out_of_scope",
}

REQUIRED_OUT_OF_SCOPE_IDS = {
    "real_cua_provider_integration",
    "real_ide_execution",
    "external_delivery_adapters",
    "durable_multi_agent_scheduler",
    "full_evidence_graph_database",
    "learning_evaluation_analytics_loop",
}


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_fields(label: str, payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing}")


def _validate_relative_posix_path(path: str) -> None:
    if Path(path).is_absolute() or "\\" in path or path.startswith("../") or "/../" in path:
        raise ValueError(f"EvaluationReport paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"EvaluationReport source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _source_specs() -> list[tuple[str, str]]:
    specs = [
        ("validation_script", "scripts/validate_repo.py"),
        ("phase1a_fixture_runner_script", "scripts/fixture_runner.py"),
        ("phase1b_local_readonly_runner_script", "scripts/local_readonly_runner.py"),
        ("phase2_task_spec_script", "scripts/task_spec.py"),
        ("post_mvp_durable_run_store_script", "scripts/durable_run_store.py"),
        ("post_mvp_replay_query_script", "scripts/replay_query.py"),
        ("post_mvp_identity_bound_approval_script", "scripts/identity_bound_approval.py"),
        ("post_mvp_approval_audit_query_script", "scripts/approval_audit_query.py"),
        ("post_mvp_approval_revocation_script", "scripts/approval_revocation.py"),
        ("post_mvp_policy_unlock_denial_script", "scripts/policy_unlock_denial.py"),
        ("phase3_capability_catalog", "artifacts/capabilities/phase3_capability_catalog.json"),
        ("phase5_verifier_rule_catalog", "artifacts/verifier/phase5_verifier_rule_catalog.json"),
        ("phase6_recovery_run", "artifacts/recovery/interrupted_after_extract/run.json"),
        ("phase6_recovery_events", "artifacts/recovery/interrupted_after_extract/events.jsonl"),
        ("phase7_computer_runtime_contract", "artifacts/computer_runtime/phase7_computer_runtime_contract.json"),
        ("phase7_trajectory_observation", "artifacts/computer_runtime/phase7_trajectory_observation.json"),
        ("phase7_adapter_policy_manifest", "artifacts/computer_runtime/phase7_adapter_policy_manifest.json"),
        ("phase7_observation_redaction_policy", "artifacts/computer_runtime/phase7_observation_redaction_policy.json"),
        ("phase8_ide_adapter_contract", "artifacts/ide_adapter/phase8_ide_adapter_contract.json"),
        ("phase8_workspace_observation", "artifacts/ide_adapter/phase8_workspace_observation.json"),
        ("phase8_ide_approval_handoff", "artifacts/ide_adapter/phase8_ide_approval_handoff_manifest.json"),
        ("phase9_multi_agent_delivery_manifest", MULTI_AGENT_DELIVERY_MANIFEST_ARTIFACT_PATH),
        ("phase9_delivery_report", DELIVERY_REPORT_ARTIFACT_PATH),
        ("post_mvp_human_approval_decision", HUMAN_APPROVAL_DECISION_ARTIFACT_PATH),
        ("post_mvp_durable_run_store", DURABLE_RUN_STORE_ARTIFACT_PATH),
        ("post_mvp_replay_query", REPLAY_QUERY_ARTIFACT_PATH),
        ("post_mvp_identity_bound_approval_record", IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH),
        ("post_mvp_approval_audit_query", APPROVAL_AUDIT_QUERY_ARTIFACT_PATH),
        ("post_mvp_approval_revocation_or_expiry", APPROVAL_REVOCATION_ARTIFACT_PATH),
        ("post_mvp_policy_unlock_request_denied", POLICY_UNLOCK_DENIAL_ARTIFACT_PATH),
        ("post_mvp_delegation_manifest", DELEGATION_MANIFEST_ARTIFACT_PATH),
        ("post_mvp_creator_verifier_pairing", CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH),
        ("post_mvp_agent_message_manifest", AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH),
        ("post_mvp_negotiation_record", NEGOTIATION_RECORD_ARTIFACT_PATH),
        ("post_mvp_broadcast_subscription_manifest", BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH),
        ("post_mvp_test_execution_task_spec", TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH),
        ("post_mvp_test_execution_result", TEST_EXECUTION_RESULT_ARTIFACT_PATH),
        ("post_mvp_failure_triage_report", FAILURE_TRIAGE_REPORT_ARTIFACT_PATH),
        ("post_mvp_verifier_result_test_execution", VERIFIER_RESULT_ARTIFACT_PATH),
        ("post_mvp_test_execution_capability_manifest", CAPABILITY_MANIFEST_ARTIFACT_PATH),
        ("post_mvp_test_execution_run_event_log", RUN_EVENT_LOG_ARTIFACT_PATH),
        ("post_mvp_test_execution_delivery_manifest", DELIVERY_MANIFEST_ARTIFACT_PATH),
        ("post_mvp_test_execution_policy_manifest", POST_MVP_POLICY_MANIFEST_ARTIFACT_PATH),
        ("post_mvp_test_execution_evidence_list", POST_MVP_EVIDENCE_LIST_ARTIFACT_PATH),
        ("post_mvp_test_execution_observation_list", POST_MVP_OBSERVATION_LIST_ARTIFACT_PATH),
        ("post_mvp_test_execution_run", POST_MVP_RUN_ARTIFACT_PATH),
        ("post_mvp_test_execution_step_list", POST_MVP_STEP_LIST_ARTIFACT_PATH),
        ("post_mvp_test_execution_tool_call_list", POST_MVP_TOOL_CALL_LIST_ARTIFACT_PATH),
        ("post_mvp_test_execution_intent", POST_MVP_INTENT_ARTIFACT_PATH),
        ("post_mvp_capability_v1_catalog", POST_MVP_CAPABILITY_KERNEL_ARTIFACT_PATH),
        ("post_mvp_policy_v1_catalog", POST_MVP_POLICY_KERNEL_ARTIFACT_PATH),
    ]
    for fixture_id in FIXTURE_IDS:
        specs.append((f"phase1a_{fixture_id}_run", f"artifacts/runs/{fixture_id}/run.json"))
        specs.append((f"phase1a_{fixture_id}_verifier_report", f"artifacts/runs/{fixture_id}/verifier_report.json"))
        specs.append((f"phase4_{fixture_id}_context_pack", f"artifacts/context/{fixture_id}/context_pack.json"))
    return specs


def _phase_coverage() -> list[dict[str, Any]]:
    return [
        {
            "phase": "phase1a",
            "title": "Static Fixture Contract / Read-only Regression Evidence Demo foundation",
            "status": "mvp_gate_satisfied",
            "gate": "Committed regression fixtures and artifact packets validate deterministic evidence, result, email draft, and verifier outputs.",
            "artifactRoles": [
                "phase1a_fixture_runner_script",
                *[f"phase1a_{fixture_id}_run" for fixture_id in FIXTURE_IDS],
                *[f"phase1a_{fixture_id}_verifier_report" for fixture_id in FIXTURE_IDS],
            ],
            "contractRefs": ["Run", "Step", "Observation", "Evidence", "Artifact", "Verifier"],
        },
        {
            "phase": "phase1b",
            "title": "Local Read-only Runner",
            "status": "mvp_gate_satisfied",
            "gate": "Local one-shot runner consumes a log, TaskSpec, and ContextPack without external side effects.",
            "artifactRoles": ["phase1b_local_readonly_runner_script", "phase1a_all_passed_run"],
            "contractRefs": ["Run", "Step", "ToolCall", "Observation", "Artifact"],
        },
        {
            "phase": "phase2",
            "title": "Intent-to-Spec and task specification",
            "status": "mvp_gate_satisfied",
            "gate": "RegressionTaskSpecV1 builder and runner intake validate allowed actions, forbidden actions, required evidence, success criteria, and approval points.",
            "artifactRoles": ["phase2_task_spec_script", "phase1a_all_passed_run"],
            "contractRefs": ["Intent", "TaskSpec", "Policy"],
        },
        {
            "phase": "phase3",
            "title": "Capability interface standardization",
            "status": "mvp_gate_satisfied",
            "gate": "Capability envelope and committed catalogue define read_log, extract_regression_result, write_artifact, and rule_verifier contracts.",
            "artifactRoles": ["phase3_capability_catalog"],
            "contractRefs": ["Capability", "ToolCall", "Policy"],
        },
        {
            "phase": "phase4",
            "title": "Context Broker",
            "status": "mvp_gate_satisfied",
            "gate": "ContextPackV1 artifacts bind selected log excerpts to source paths, line ranges, hashes, and context budget policy.",
            "artifactRoles": [f"phase4_{fixture_id}_context_pack" for fixture_id in FIXTURE_IDS],
            "contractRefs": ["ContextPack", "Observation", "Evidence"],
        },
        {
            "phase": "phase5",
            "title": "Evidence List and MVP Verifier Runtime",
            "status": "mvp_gate_satisfied",
            "gate": "EvidenceListV1 and VerifierRuntimeV1 replay committed artifacts with rule catalog and forced-failure cases.",
            "artifactRoles": ["phase5_verifier_rule_catalog", "phase1a_all_passed_verifier_report"],
            "contractRefs": ["Evidence", "Verifier", "Artifact"],
        },
        {
            "phase": "phase6",
            "title": "State, permission, and recovery",
            "status": "mvp_gate_satisfied",
            "gate": "RunControlV1, permission-policy-v1, recovery-snapshot-v1, and interrupted recovery fixture cover terminal replay and resume action contract.",
            "artifactRoles": ["phase6_recovery_run", "phase6_recovery_events", "phase1a_all_passed_run"],
            "contractRefs": ["Run", "Policy", "Recovery"],
        },
        {
            "phase": "phase7",
            "title": "Computer Runtime and CUA Adapter",
            "status": "mvp_gate_satisfied",
            "gate": "Contract-only ComputerRuntimeAdapterV1, trajectory observation, adapter policy, and redaction policy define CUA boundary without real provider execution.",
            "artifactRoles": [
                "phase7_computer_runtime_contract",
                "phase7_trajectory_observation",
                "phase7_adapter_policy_manifest",
                "phase7_observation_redaction_policy",
            ],
            "contractRefs": ["Capability", "Observation", "Policy"],
        },
        {
            "phase": "phase8",
            "title": "IDE Adapter",
            "status": "mvp_gate_satisfied",
            "gate": "IDEAdapterContractV1, WorkspaceObservationV1, and approval handoff manifest define IDE boundary without workspace mutation or terminal execution.",
            "artifactRoles": [
                "phase8_ide_adapter_contract",
                "phase8_workspace_observation",
                "phase8_ide_approval_handoff",
            ],
            "contractRefs": ["Capability", "Observation", "Policy", "HumanGate"],
        },
        {
            "phase": "phase9",
            "title": "Multi-agent and delivery loop",
            "status": "mvp_gate_satisfied",
            "gate": "MultiAgentDeliveryManifestV1 and DeliveryReportV1 prove source-bound handoffs, verifier-owned verdicts, draft delivery readiness, and external delivery blockers.",
            "artifactRoles": ["phase9_multi_agent_delivery_manifest", "phase9_delivery_report"],
            "contractRefs": ["Plan", "DAG", "Evidence", "Verifier", "Delivery"],
        },
    ]


def build_evaluation_report(root: Path) -> dict[str, Any]:
    source_artifacts = [_artifact_source(role, path, root) for role, path in _source_specs()]
    delivery_report = _load_json(root / DELIVERY_REPORT_ARTIFACT_PATH)
    validate_delivery_report(delivery_report, root)
    human_approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    validate_human_approval_decision(human_approval_decision, root)
    durable_run_store = _load_json(root / DURABLE_RUN_STORE_ARTIFACT_PATH)
    validate_durable_run_store(durable_run_store, root)
    replay_query = _load_json(root / REPLAY_QUERY_ARTIFACT_PATH)
    validate_replay_query(replay_query, root)
    identity_bound_approval_record = _load_json(root / IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH)
    validate_identity_bound_approval_record(identity_bound_approval_record, root)
    approval_audit_query = _load_json(root / APPROVAL_AUDIT_QUERY_ARTIFACT_PATH)
    validate_approval_audit_query(approval_audit_query, root)
    approval_revocation = _load_json(root / APPROVAL_REVOCATION_ARTIFACT_PATH)
    validate_approval_revocation_or_expiry(approval_revocation, root)
    policy_unlock_denial = _load_json(root / POLICY_UNLOCK_DENIAL_ARTIFACT_PATH)
    validate_policy_unlock_request_denied(policy_unlock_denial, root)
    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    creator_verifier_pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(creator_verifier_pairing, root)
    agent_message_manifest = _load_json(root / AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH)
    validate_agent_message_manifest(agent_message_manifest, root)
    negotiation_record = _load_json(root / NEGOTIATION_RECORD_ARTIFACT_PATH)
    validate_negotiation_record(negotiation_record, root)
    broadcast_subscription_manifest = _load_json(root / BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH)
    validate_broadcast_subscription_manifest(broadcast_subscription_manifest, root)
    test_execution_task_spec = _load_json(root / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH)
    validate_test_execution_task_spec(test_execution_task_spec, root)
    test_execution_result = _load_json(root / TEST_EXECUTION_RESULT_ARTIFACT_PATH)
    validate_test_execution_result(test_execution_result, root)
    failure_triage_report = _load_json(root / FAILURE_TRIAGE_REPORT_ARTIFACT_PATH)
    validate_failure_triage_report(failure_triage_report, root)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    validate_verifier_result(verifier_result, root)
    capability_manifest = _load_json(root / CAPABILITY_MANIFEST_ARTIFACT_PATH)
    validate_capability_manifest(capability_manifest, root)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    validate_run_event_log(run_event_log, root)
    delivery_manifest = _load_json(root / DELIVERY_MANIFEST_ARTIFACT_PATH)
    validate_delivery_manifest(delivery_manifest, root)
    policy_manifest = _load_json(root / POST_MVP_POLICY_MANIFEST_ARTIFACT_PATH)
    validate_policy_manifest(policy_manifest, root)
    evidence_list_artifact = _load_json(root / POST_MVP_EVIDENCE_LIST_ARTIFACT_PATH)
    validate_evidence_list_artifact(evidence_list_artifact, root)
    observation_list_artifact = _load_json(root / POST_MVP_OBSERVATION_LIST_ARTIFACT_PATH)
    validate_observation_list_artifact(observation_list_artifact, root)
    run_artifact = _load_json(root / POST_MVP_RUN_ARTIFACT_PATH)
    validate_run_artifact(run_artifact, root)
    step_list_artifact = _load_json(root / POST_MVP_STEP_LIST_ARTIFACT_PATH)
    validate_step_list_artifact(step_list_artifact, root)
    tool_call_list_artifact = _load_json(root / POST_MVP_TOOL_CALL_LIST_ARTIFACT_PATH)
    validate_tool_call_list_artifact(tool_call_list_artifact, root)
    intent_artifact = _load_json(root / POST_MVP_INTENT_ARTIFACT_PATH)
    validate_intent_artifact(intent_artifact, root)
    capability_kernel_artifact = _load_json(root / POST_MVP_CAPABILITY_KERNEL_ARTIFACT_PATH)
    validate_capability_kernel_artifact(capability_kernel_artifact, root)
    policy_kernel_artifact = _load_json(root / POST_MVP_POLICY_KERNEL_ARTIFACT_PATH)
    validate_policy_kernel_artifact(policy_kernel_artifact, root)
    delivery_readiness = delivery_report["readiness"]
    delivery_blocker_ids = [blocker["id"] for blocker in delivery_report["blockers"]]
    phase_coverage = _phase_coverage()
    return {
        "schemaVersion": EVALUATION_REPORT_SCHEMA_VERSION,
        "id": REPORT_ID,
        "generatedAt": GENERATED_AT,
        "scope": "read_only_regression_evidence_demo_mvp_completion",
        "mode": "static_contract_only",
        "sourceArtifacts": source_artifacts,
        "phaseCoverage": phase_coverage,
        "coverageSummary": {
            "totalGates": len(EXPECTED_PHASES),
            "satisfiedGates": len(phase_coverage),
            "earliestIncompleteGate": None,
            "machineVerificationCommand": "/usr/bin/python3 scripts/validate_repo.py",
        },
        "mvpCompletionDecision": {
            "mvpName": "Read-only Regression Evidence Demo",
            "contractOnlyMvpComplete": True,
            "fullAgenticEngineeringOsComplete": False,
            "machineVerifiable": True,
            "readyForHumanReview": delivery_readiness["readyForHumanReview"],
            "readyForExternalDelivery": delivery_readiness["readyForExternalDelivery"],
            "readyForExternalSideEffects": False,
            "decision": "contract_only_mvp_complete_full_product_in_progress",
        },
        "knownBlockers": [
            {
                "id": "human_approval_missing",
                "owner": "permission-policy-v1",
                "sourceRef": DELIVERY_REPORT_ARTIFACT_PATH,
                "status": "blocked_by_mvp_policy",
            },
            {
                "id": "external_delivery_disabled_by_mvp_policy",
                "owner": "multi-agent-delivery-policy",
                "sourceRef": DELIVERY_REPORT_ARTIFACT_PATH,
                "status": "blocked_by_mvp_policy",
            },
            {
                "id": "real_provider_execution_out_of_scope",
                "owner": "adapter-policy-manifest-v1",
                "sourceRef": "artifacts/computer_runtime/phase7_adapter_policy_manifest.json",
                "status": "post_mvp",
            },
            {
                "id": "full_product_runtime_out_of_scope",
                "owner": "agentic-engineering-os-roadmap",
                "sourceRef": ".cursor/plans/agentic-control-plane.plan.md#parking-lot",
                "status": "post_mvp",
            },
        ],
        "deliveryReportBlockers": delivery_blocker_ids,
        "outOfScope": [
            {
                "id": "real_cua_provider_integration",
                "reason": "Phase 7 MVP defines adapter contracts and policies only; no GUI, desktop, browser, sandbox, or CUA provider is executed.",
            },
            {
                "id": "real_ide_execution",
                "reason": "Phase 8 MVP defines IDE observation and approval handoff contracts only; no workspace mutation, terminal execution, or UI operation is performed.",
            },
            {
                "id": "external_delivery_adapters",
                "reason": "Phase 9 MVP produces a verified delivery draft and readiness report only; no email, PR, ticket, Slack, or web delivery adapter is invoked.",
            },
            {
                "id": "durable_multi_agent_scheduler",
                "reason": "Phase 9 MVP records handoff ownership contracts; it does not run LangGraph, AutoGen, CrewAI, queues, workers, or concurrent agent scheduling.",
            },
            {
                "id": "full_evidence_graph_database",
                "reason": "The MVP uses committed EvidenceListV1 JSON artifacts instead of a graph database or long-lived artifact registry.",
            },
            {
                "id": "learning_evaluation_analytics_loop",
                "reason": "This report is a deterministic milestone evaluation artifact, not a production learning system with longitudinal metrics or user preference updates.",
            },
        ],
        "nextRecommendedSlice": {
            "phase": "post_mvp",
            "slice": "Add a workload-independent RunEventV1 ArtifactV1 subtype contract artifact at artifacts/state/post_mvp_run_event_v1_catalog.json that defines the canonical OS-kernel RunEvent primitive distinct from the workload-specific RunEventLogV1: each runEventItem must declare runEventId / runEventClass (run_lifecycle / step_lifecycle / tool_call_lifecycle / verifier_lifecycle / artifact_lifecycle / approval_lifecycle / policy_lifecycle / coordination_lifecycle) / runEventScope (workload_independent_kernel / workload_specific / coordination_layer) / runEventLifecycleState (drafted / emitted / replayed / deprecated) / requiredFlag / verifierVerdictOwner / sourceEventRef using only workload-independent vocabulary; the envelope must bind TestExecutionTaskSpecV1 / IntentV1 / RunV1 / StepListV1 / ToolCallListV1 / CapabilityV1 / CapabilityManifestV1 / RunEventLogV1 / ObservationListV1 / EvidenceListV1 / VerifierResultV1 / DeliveryManifestV1 / PolicyV1 / PolicyManifestV1 / HumanApprovalDecisionV1 by content hash plus the five Agent Coordination Layer manifests; declare verifier-runtime-v1 as the verdict owner with creatorMustNotOwnVerdict=true; force the six workload-independent permission flags to false; RunEventV1 must explicitly forbid every regression/email forbidden token and set reusesRegressionRunEventLog=false; ensure the artifact reuses ArtifactV1 envelope (artifactEnvelopeSchemaVersion=artifact-v1) and every RunEventLogV1.events[*].type resolves into RunEventV1.runEventItems[*].sourceEventRef.",
            "mustRemainMachineVerifiable": True,
        },
        "invariants": [
            "EvaluationReportV1 summarizes existing committed artifacts; it does not create new evidence or override verifier verdicts.",
            "The contract-only MVP can be complete while the full Agentic Engineering OS product remains in progress.",
            "External delivery, real provider execution, workspace mutation, and human approval synthesis remain blocked.",
        ],
    }


def _validate_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("EvaluationReportV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(_source_specs())
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("EvaluationReportV1 sourceArtifacts must be objects")
        _require_fields("EvaluationReportV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected EvaluationReportV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"EvaluationReportV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"EvaluationReportV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"EvaluationReportV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"EvaluationReportV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def validate_evaluation_report(report: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvaluationReportV1",
        report,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "scope",
            "mode",
            "sourceArtifacts",
            "phaseCoverage",
            "coverageSummary",
            "mvpCompletionDecision",
            "knownBlockers",
            "deliveryReportBlockers",
            "outOfScope",
            "nextRecommendedSlice",
            "invariants",
        ],
    )
    if report["schemaVersion"] != EVALUATION_REPORT_SCHEMA_VERSION:
        raise ValueError(f"EvaluationReportV1 schemaVersion must be {EVALUATION_REPORT_SCHEMA_VERSION}")
    if report["id"] != REPORT_ID:
        raise ValueError(f"EvaluationReportV1 id must be {REPORT_ID}")
    if report["mode"] != "static_contract_only":
        raise ValueError("EvaluationReportV1 mode must be static_contract_only")

    sources = _validate_source_artifacts(report["sourceArtifacts"], root)
    source_roles = set(sources)

    phase_coverage = report["phaseCoverage"]
    if not isinstance(phase_coverage, list):
        raise ValueError("EvaluationReportV1 phaseCoverage must be a list")
    phases = [phase.get("phase") for phase in phase_coverage if isinstance(phase, dict)]
    if phases != EXPECTED_PHASES:
        raise ValueError(f"EvaluationReportV1 phaseCoverage must cover phases in order: {EXPECTED_PHASES}")
    for phase in phase_coverage:
        if not isinstance(phase, dict):
            raise ValueError("EvaluationReportV1 phaseCoverage entries must be objects")
        _require_fields("EvaluationReportV1 phase coverage", phase, ["phase", "title", "status", "gate", "artifactRoles", "contractRefs"])
        if phase["status"] != "mvp_gate_satisfied":
            raise ValueError(f"EvaluationReportV1 {phase['phase']} must be marked mvp_gate_satisfied")
        artifact_roles = phase["artifactRoles"]
        if not isinstance(artifact_roles, list) or not artifact_roles:
            raise ValueError(f"EvaluationReportV1 {phase['phase']} must reference at least one artifact role")
        missing_roles = [role for role in artifact_roles if role not in source_roles]
        if missing_roles:
            raise ValueError(f"EvaluationReportV1 {phase['phase']} references unknown source roles: {missing_roles}")

    summary = report["coverageSummary"]
    _require_fields(
        "EvaluationReportV1 coverageSummary",
        summary,
        ["totalGates", "satisfiedGates", "earliestIncompleteGate", "machineVerificationCommand"],
    )
    if summary["totalGates"] != len(EXPECTED_PHASES):
        raise ValueError("EvaluationReportV1 totalGates must match phaseCoverage")
    if summary["satisfiedGates"] != len(EXPECTED_PHASES):
        raise ValueError("EvaluationReportV1 satisfiedGates must match completed MVP gates")
    if summary["earliestIncompleteGate"] is not None:
        raise ValueError("EvaluationReportV1 earliestIncompleteGate must be null for the contract-only MVP")
    if "scripts/validate_repo.py" not in summary["machineVerificationCommand"]:
        raise ValueError("EvaluationReportV1 must name scripts/validate_repo.py as the machine verification command")

    delivery_report = _load_json(root / sources["phase9_delivery_report"]["path"])
    validate_delivery_report(delivery_report, root)
    decision = report["mvpCompletionDecision"]
    _require_fields(
        "EvaluationReportV1 mvpCompletionDecision",
        decision,
        [
            "mvpName",
            "contractOnlyMvpComplete",
            "fullAgenticEngineeringOsComplete",
            "machineVerifiable",
            "readyForHumanReview",
            "readyForExternalDelivery",
            "readyForExternalSideEffects",
            "decision",
        ],
    )
    if decision["contractOnlyMvpComplete"] is not True:
        raise ValueError("EvaluationReportV1 contract-only MVP must be marked complete")
    if decision["fullAgenticEngineeringOsComplete"] is not False:
        raise ValueError("EvaluationReportV1 must not claim the full Agentic Engineering OS product is complete")
    if decision["machineVerifiable"] is not True:
        raise ValueError("EvaluationReportV1 MVP completion decision must be machine verifiable")
    if decision["readyForExternalDelivery"] != delivery_report["readiness"]["readyForExternalDelivery"]:
        raise ValueError("EvaluationReportV1 external delivery readiness must match DeliveryReportV1")
    if decision["readyForExternalDelivery"] is not False:
        raise ValueError("EvaluationReportV1 must not mark external delivery ready")
    if decision["readyForExternalSideEffects"] is not False:
        raise ValueError("EvaluationReportV1 must not allow external side effects")

    blocker_ids = {blocker.get("id") for blocker in report["knownBlockers"] if isinstance(blocker, dict)}
    missing_blockers = REQUIRED_BLOCKER_IDS - blocker_ids
    if missing_blockers:
        raise ValueError(f"EvaluationReportV1 knownBlockers must include {sorted(missing_blockers)}")
    delivery_blockers = set(report["deliveryReportBlockers"])
    for required_delivery_blocker in ["human_approval_missing", "external_delivery_disabled_by_mvp_policy"]:
        if required_delivery_blocker not in delivery_blockers:
            raise ValueError(f"EvaluationReportV1 deliveryReportBlockers must include {required_delivery_blocker}")

    out_of_scope_ids = {item.get("id") for item in report["outOfScope"] if isinstance(item, dict)}
    missing_out_of_scope = REQUIRED_OUT_OF_SCOPE_IDS - out_of_scope_ids
    if missing_out_of_scope:
        raise ValueError(f"EvaluationReportV1 outOfScope must include {sorted(missing_out_of_scope)}")

    next_slice = report["nextRecommendedSlice"]
    _require_fields("EvaluationReportV1 nextRecommendedSlice", next_slice, ["phase", "slice", "mustRemainMachineVerifiable"])
    if next_slice["mustRemainMachineVerifiable"] is not True:
        raise ValueError("EvaluationReportV1 next slice must remain machine verifiable")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or validate the MVP EvaluationReportV1 artifact.")
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--validate-report", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if args.report_out is None and args.validate_report is None:
        parser.error("At least one of --report-out or --validate-report is required")
    if args.report_out is not None:
        _write_json(args.report_out, build_evaluation_report(root))
    if args.validate_report is not None:
        validate_evaluation_report(_load_json(args.validate_report), root)


if __name__ == "__main__":
    main()

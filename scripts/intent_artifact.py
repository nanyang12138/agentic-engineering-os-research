"""IntentV1 / intent-v1 ArtifactV1 subtype contract.

This module defines a workload-independent ``IntentV1`` ArtifactV1 subtype
that captures the canonical OS-kernel ``Intent`` primitive for any
engineering workload. The artifact is a static, machine-verifiable
contract: no Intent runtime is invoked, no TaskSpec is generated at
inspection time, no external communication is sent.

IntentV1 sits *above* TaskSpecV1: every workload run originates from a
declared intent that names the workload type, the requested capability
classes, the expected artifact kinds, the requested verifier / delivery
/ policy classes, and the lifecycle state that takes the intent into
an accepted TaskSpec. The intent envelope explicitly forbids any
regression/email reuse so that the same schema can host more than one
workload.

Invariants:

- ``IntentV1`` is an ArtifactV1 subtype (``artifactEnvelopeSchemaVersion
  = artifact-v1``) joining the existing thirteen subtypes
  (``regression-result-artifact-v1``, ``test-execution-result-v1``,
  ``failure-triage-report-v1``, ``verifier-result-v1``,
  ``capability-manifest-v1``, ``run-event-log-v1``,
  ``delivery-manifest-v1``, ``policy-manifest-v1``,
  ``evidence-list-artifact-v1``, ``observation-list-artifact-v1``,
  ``run-artifact-v1``, ``step-list-artifact-v1``,
  ``tool-call-list-artifact-v1``).
- ``intentLifecycleState`` must lie in
  ``[drafted, refined, accepted_into_task_spec, rejected, withdrawn]``.
- ``requestedCapabilityClasses`` must be a subset of
  ``[read_only_inspection, evidence_collection, artifact_writing,
  verifier_check, human_approval_request]``; the forbidden capability
  classes ``external_communication``, ``repository_mutation``,
  ``release_or_deploy``, ``gui_or_browser_or_desktop_call`` and
  ``public_access`` are rejected outright.
- ``acceptedTaskSpecRef`` must resolve to a workload-independent
  ``TaskSpecV1`` envelope; the test-execution variant must equal
  ``TestExecutionTaskSpecV1.id`` with
  ``workloadType=test_execution_failure_triage``.
- ``verifierVerdictOwner`` must equal ``verifier-runtime-v1`` and
  ``creatorMustNotOwnVerdict`` must be true.
- The six workload-independent permission flags are forced to false.
- ``IntentV1`` binds the upstream 12 workload artifacts plus the five
  Agent Coordination Layer contracts by content hash, so any upstream
  drift invalidates the intent.
- Regression-workload isolation forbids ``regression_result``,
  ``email_draft``, ``send_email``, ``regression-task-spec-v1`` and
  ``regression-result-artifact-v1`` reuse and tracks
  ``reusesRegressionIntentArtifact=false``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from capability_manifest import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as CAPABILITY_MANIFEST_ARTIFACT_ID,
    CAPABILITY_MANIFEST_ARTIFACT_PATH,
    CAPABILITY_MANIFEST_SCHEMA_VERSION,
    validate_capability_manifest,
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
from delivery_manifest import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as DELIVERY_MANIFEST_ARTIFACT_ID,
    DELIVERY_MANIFEST_ARTIFACT_PATH,
    DELIVERY_MANIFEST_SCHEMA_VERSION,
    validate_delivery_manifest,
)
from evidence_artifact import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as EVIDENCE_LIST_ARTIFACT_ID,
    EVIDENCE_LIST_ARTIFACT_PATH,
    EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION,
    validate_evidence_list_artifact,
)
from human_approval import (
    DECISION_ARTIFACT_PATH as HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    HUMAN_APPROVAL_DECISION_SCHEMA_VERSION,
    validate_human_approval_decision,
)
from observation_artifact import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as OBSERVATION_LIST_ARTIFACT_ID,
    OBSERVATION_LIST_ARTIFACT_PATH,
    OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION,
    validate_observation_list_artifact,
)
from policy_manifest import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as POLICY_MANIFEST_ARTIFACT_ID,
    POLICY_MANIFEST_ARTIFACT_PATH,
    POLICY_MANIFEST_SCHEMA_VERSION,
    validate_policy_manifest,
)
from run_artifact import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as RUN_ARTIFACT_ID,
    RUN_ARTIFACT_PATH,
    RUN_ARTIFACT_SCHEMA_VERSION,
    validate_run_artifact,
)
from run_event_log import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as RUN_EVENT_LOG_ARTIFACT_ID,
    RUN_EVENT_LOG_ARTIFACT_PATH,
    RUN_EVENT_LOG_SCHEMA_VERSION,
    validate_run_event_log,
)
from step_list_artifact import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as STEP_LIST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as STEP_LIST_ARTIFACT_ID,
    STEP_LIST_ARTIFACT_PATH,
    STEP_LIST_ARTIFACT_SCHEMA_VERSION,
    validate_step_list_artifact,
)
from test_execution_task_spec import (
    TASK_SPEC_ARTIFACT_PATH as TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
    TASK_SPEC_ID as TEST_EXECUTION_TASK_SPEC_ID,
    TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
    WORKLOAD_TYPE as TASK_SPEC_WORKLOAD_TYPE,
    validate_test_execution_task_spec,
)
from tool_call_list_artifact import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as TOOL_CALL_LIST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as TOOL_CALL_LIST_ARTIFACT_ID,
    TOOL_CALL_LIST_ARTIFACT_PATH,
    TOOL_CALL_LIST_ARTIFACT_SCHEMA_VERSION,
    validate_tool_call_list_artifact,
)
from verifier_result import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as VERIFIER_RESULT_ARTIFACT_ID,
    VERIFIER_RESULT_ARTIFACT_PATH,
    VERIFIER_RESULT_SCHEMA_VERSION,
    validate_verifier_result,
)


INTENT_ARTIFACT_SCHEMA_VERSION = "intent-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "IntentV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-intent-kernel-contract"
INTENT_ARTIFACT_PATH = "artifacts/intents/post_mvp_test_execution_intent.json"

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_intent_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

INTENT_ID = "intent-post-mvp-test-execution-failure-triage-0001"
INTENT_NARRATIVE = (
    "Triage a recorded test execution result for the post-MVP "
    "test_execution_failure_triage workload: classify failures, attach "
    "evidence-backed verdicts, and produce workload-independent artifacts "
    "without modifying any repository, sending any external "
    "communication, or invoking any GUI/desktop/browser capability."
)
INTENT_ORIGIN_AGENT = "human_principal_agent"
INTENT_ORIGIN_CHANNEL = "human_review"

REQUESTED_WORKLOAD_TYPE = "test_execution_failure_triage"
REQUESTED_CAPABILITY_CLASSES = [
    "read_only_inspection",
    "evidence_collection",
    "artifact_writing",
    "verifier_check",
    "human_approval_request",
]
REQUESTED_ARTIFACT_KINDS = [
    "TestExecutionResultV1",
    "FailureTriageReportV1",
    "EvidenceListV1",
    "VerifierResultV1",
]
REQUESTED_VERIFIER_CLASS = "verifier-runtime-v1"
REQUESTED_DELIVERY_CLASS = "workload_independent_delivery_manifest"
REQUESTED_POLICY_CLASS = "workload_independent_policy_manifest"

INTENT_LIFECYCLE_STATE = "accepted_into_task_spec"
ACCEPTED_TASK_SPEC_REF = TEST_EXECUTION_TASK_SPEC_ID

INTENT_LIFECYCLE_STATE_DOMAIN = [
    "drafted",
    "refined",
    "accepted_into_task_spec",
    "rejected",
    "withdrawn",
]
REQUESTED_CAPABILITY_CLASS_DOMAIN = [
    "read_only_inspection",
    "evidence_collection",
    "artifact_writing",
    "verifier_check",
    "human_approval_request",
]
FORBIDDEN_REQUESTED_CAPABILITY_CLASSES = [
    "external_communication",
    "repository_mutation",
    "release_or_deploy",
    "gui_or_browser_or_desktop_call",
    "public_access",
]
INTENT_ORIGIN_AGENT_DOMAIN = [
    "human_principal_agent",
    "creator_agent",
    "verifier-runtime-v1",
]
INTENT_ORIGIN_CHANNEL_DOMAIN = [
    "human_review",
    "automation_run",
    "delegation_protocol",
    "broadcast_topic",
]
REQUESTED_ARTIFACT_KIND_DOMAIN = [
    "TestExecutionResultV1",
    "FailureTriageReportV1",
    "EvidenceListV1",
    "VerifierResultV1",
    "ObservationListV1",
    "RunV1",
    "StepListV1",
    "ToolCallListV1",
    "CapabilityManifestV1",
    "RunEventLogV1",
    "DeliveryManifestV1",
    "PolicyManifestV1",
    "HumanApprovalDecisionV1",
]

PERMISSION_FLAG_DOMAIN = [
    "externalSideEffectsAllowed",
    "repositoryMutationAllowed",
    "externalCommunicationAllowed",
    "releaseOrDeploymentAllowed",
    "guiOrBrowserOrDesktopCallAllowed",
    "publicAccessAllowed",
]

REQUIRED_VERDICT_FOR_PROMOTION = "passed"
REQUIRED_TERMINAL_RUN_STATE = "completed"
REQUIRED_POLICY_UNLOCKED = True
REQUIRED_LIFECYCLE_STATE_FOR_PROMOTION = "accepted_into_task_spec"

NON_REGRESSION_REUSE_PATH = [
    "test_execution_failure_triage",
    "code_patch_review_loop",
    "pr_review",
]

FORBIDDEN_REGRESSION_FIELDS = [
    "regression_result",
    "regression_result.json",
    "email_draft",
    "email_draft.md",
    "send_email",
    "regression-task-spec-v1",
    "regression-result-artifact-v1",
]

COORDINATION_BINDING_PATHS: dict[str, str] = {
    "delegationManifestRef": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creatorVerifierPairingRef": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agentMessageManifestRef": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiationRecordRef": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcastSubscriptionManifestRef": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

SOURCE_ROLE_TO_PATH: dict[str, str] = {
    "test_execution_task_spec": TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    "test_execution_capability_manifest": CAPABILITY_MANIFEST_ARTIFACT_PATH,
    "test_execution_run_event_log": RUN_EVENT_LOG_ARTIFACT_PATH,
    "test_execution_observation_list": OBSERVATION_LIST_ARTIFACT_PATH,
    "test_execution_evidence_list": EVIDENCE_LIST_ARTIFACT_PATH,
    "test_execution_verifier_result": VERIFIER_RESULT_ARTIFACT_PATH,
    "test_execution_delivery_manifest": DELIVERY_MANIFEST_ARTIFACT_PATH,
    "test_execution_policy_manifest": POLICY_MANIFEST_ARTIFACT_PATH,
    "test_execution_run_artifact": RUN_ARTIFACT_PATH,
    "test_execution_step_list": STEP_LIST_ARTIFACT_PATH,
    "test_execution_tool_call_list": TOOL_CALL_LIST_ARTIFACT_PATH,
    "human_approval_decision": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

REQUIRED_VERIFIER_FLAGS = [
    "mustValidateSchema",
    "mustValidateIntentLifecycleState",
    "mustValidateRequestedCapabilityClasses",
    "mustValidateAcceptedTaskSpecBinding",
    "mustValidateRunBinding",
    "mustValidateStepListBinding",
    "mustValidateToolCallListBinding",
    "mustValidateCapabilityManifestBinding",
    "mustValidateRunEventLogBinding",
    "mustValidateObservationListBinding",
    "mustValidateEvidenceListBinding",
    "mustValidateVerifierResultBinding",
    "mustValidateDeliveryManifestBinding",
    "mustValidatePolicyManifestBinding",
    "mustValidateApprovalDecisionBinding",
    "mustValidatePermissionFlags",
    "mustValidatePromotionConditions",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "IntentV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype and from any first-workload regression intent.",
    "IntentV1.acceptedTaskSpecRef must resolve to TestExecutionTaskSpecV1.id with workloadType=test_execution_failure_triage; regression-task-spec-v1 reuse is forbidden.",
    "IntentV1.requestedCapabilityClasses must be a non-empty subset of [read_only_inspection, evidence_collection, artifact_writing, verifier_check, human_approval_request].",
    "IntentV1.forbiddenRequestedCapabilityClasses must enumerate [external_communication, repository_mutation, release_or_deploy, gui_or_browser_or_desktop_call, public_access] and intersect requestedCapabilityClasses with the empty set.",
    "IntentV1.intentLifecycleState must lie in [drafted, refined, accepted_into_task_spec, rejected, withdrawn]; promotionConditions require accepted_into_task_spec, verifier verdict=passed, terminal run state=completed and policy unlocked=true.",
    "IntentV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and the creator agent may only stage drafts.",
    "IntentV1 must bind TestExecutionTaskSpecV1, RunV1, StepListV1, ToolCallListV1, CapabilityManifestV1, RunEventLogV1, ObservationListV1, EvidenceListV1, VerifierResultV1, DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1, and all five Agent Coordination Layer contracts by content hash.",
    "IntentV1 must not reuse regression-task-spec-v1, regression-result-artifact-v1, the send_email capability, or any regression_result / email_draft / send_email field outside the declarative forbiddenFields list.",
]


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
    if (
        not isinstance(path, str)
        or not path
        or Path(path).is_absolute()
        or "\\" in path
        or path.startswith("../")
        or "/../" in path
    ):
        raise ValueError(
            f"IntentV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(f"IntentV1 source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(full_path),
    }


def _coordination_binding(root: Path) -> dict[str, str]:
    binding: dict[str, str] = {}
    for field, relative_path in COORDINATION_BINDING_PATHS.items():
        _validate_relative_posix_path(relative_path)
        full_path = root / relative_path
        if not full_path.is_file():
            raise ValueError(
                f"IntentV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    delegation = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation, root)
    pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(pairing, root)
    agent_message = _load_json(root / AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH)
    validate_agent_message_manifest(agent_message, root)
    negotiation = _load_json(root / NEGOTIATION_RECORD_ARTIFACT_PATH)
    validate_negotiation_record(negotiation, root)
    broadcast = _load_json(root / BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH)
    validate_broadcast_subscription_manifest(broadcast, root)
    task_spec = _load_json(root / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH)
    validate_test_execution_task_spec(task_spec, root)
    capability_manifest = _load_json(root / CAPABILITY_MANIFEST_ARTIFACT_PATH)
    validate_capability_manifest(capability_manifest, root)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    validate_run_event_log(run_event_log, root)
    observation_list = _load_json(root / OBSERVATION_LIST_ARTIFACT_PATH)
    validate_observation_list_artifact(observation_list, root)
    evidence_list = _load_json(root / EVIDENCE_LIST_ARTIFACT_PATH)
    validate_evidence_list_artifact(evidence_list, root)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    validate_verifier_result(verifier_result, root)
    delivery_manifest = _load_json(root / DELIVERY_MANIFEST_ARTIFACT_PATH)
    validate_delivery_manifest(delivery_manifest, root)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    validate_policy_manifest(policy_manifest, root)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    validate_human_approval_decision(approval_decision, root)
    run_artifact = _load_json(root / RUN_ARTIFACT_PATH)
    validate_run_artifact(run_artifact, root)
    step_list = _load_json(root / STEP_LIST_ARTIFACT_PATH)
    validate_step_list_artifact(step_list, root)
    tool_call_list = _load_json(root / TOOL_CALL_LIST_ARTIFACT_PATH)
    validate_tool_call_list_artifact(tool_call_list, root)
    return (
        task_spec,
        run_event_log,
        observation_list,
        evidence_list,
        verifier_result,
        policy_manifest,
        run_artifact,
        step_list,
        tool_call_list,
        approval_decision,
    )


def _build_task_spec_binding(root: Path, task_spec: dict[str, Any]) -> dict[str, Any]:
    full_path = root / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    return {
        "taskSpecRef": TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecWorkloadType": task_spec["workloadType"],
        "taskSpecContentHash": _stable_file_hash(full_path),
    }


def _build_run_binding(root: Path, run_artifact: dict[str, Any]) -> dict[str, Any]:
    full_path = root / RUN_ARTIFACT_PATH
    return {
        "runRef": RUN_ARTIFACT_PATH,
        "runSchemaVersion": RUN_ARTIFACT_SCHEMA_VERSION,
        "runEnvelopeSchemaVersion": RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "runId": RUN_ARTIFACT_ID,
        "runIdentifier": run_artifact["runId"],
        "runState": run_artifact["runState"],
        "runContentHash": _stable_file_hash(full_path),
    }


def _build_step_list_binding(root: Path, step_list: dict[str, Any]) -> dict[str, Any]:
    full_path = root / STEP_LIST_ARTIFACT_PATH
    return {
        "stepListRef": STEP_LIST_ARTIFACT_PATH,
        "stepListSchemaVersion": STEP_LIST_ARTIFACT_SCHEMA_VERSION,
        "stepListEnvelopeSchemaVersion": STEP_LIST_ENVELOPE_SCHEMA_VERSION,
        "stepListId": STEP_LIST_ARTIFACT_ID,
        "stepCount": step_list["stepCount"],
        "stepListContentHash": _stable_file_hash(full_path),
    }


def _build_tool_call_list_binding(
    root: Path, tool_call_list: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / TOOL_CALL_LIST_ARTIFACT_PATH
    return {
        "toolCallListRef": TOOL_CALL_LIST_ARTIFACT_PATH,
        "toolCallListSchemaVersion": TOOL_CALL_LIST_ARTIFACT_SCHEMA_VERSION,
        "toolCallListEnvelopeSchemaVersion": TOOL_CALL_LIST_ENVELOPE_SCHEMA_VERSION,
        "toolCallListId": TOOL_CALL_LIST_ARTIFACT_ID,
        "toolCallCount": tool_call_list["toolCallCount"],
        "toolCallListContentHash": _stable_file_hash(full_path),
    }


def _build_capability_manifest_binding(root: Path) -> dict[str, Any]:
    full_path = root / CAPABILITY_MANIFEST_ARTIFACT_PATH
    return {
        "capabilityManifestRef": CAPABILITY_MANIFEST_ARTIFACT_PATH,
        "capabilityManifestSchemaVersion": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "capabilityManifestEnvelopeSchemaVersion": CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "capabilityManifestId": CAPABILITY_MANIFEST_ARTIFACT_ID,
        "capabilityManifestContentHash": _stable_file_hash(full_path),
    }


def _build_run_event_log_binding(
    root: Path, run_event_log: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / RUN_EVENT_LOG_ARTIFACT_PATH
    return {
        "runEventLogRef": RUN_EVENT_LOG_ARTIFACT_PATH,
        "runEventLogSchemaVersion": RUN_EVENT_LOG_SCHEMA_VERSION,
        "runEventLogEnvelopeSchemaVersion": RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION,
        "runEventLogId": RUN_EVENT_LOG_ARTIFACT_ID,
        "eventCount": run_event_log["eventCount"],
        "terminalState": run_event_log["terminalState"],
        "runEventLogContentHash": _stable_file_hash(full_path),
    }


def _build_observation_list_binding(
    root: Path, observation_list: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / OBSERVATION_LIST_ARTIFACT_PATH
    return {
        "observationListRef": OBSERVATION_LIST_ARTIFACT_PATH,
        "observationListSchemaVersion": OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION,
        "observationListEnvelopeSchemaVersion": OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION,
        "observationListId": OBSERVATION_LIST_ARTIFACT_ID,
        "observationItemCount": observation_list["observationItemCount"],
        "observationListContentHash": _stable_file_hash(full_path),
    }


def _build_evidence_list_binding(
    root: Path, evidence_list: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / EVIDENCE_LIST_ARTIFACT_PATH
    return {
        "evidenceListRef": EVIDENCE_LIST_ARTIFACT_PATH,
        "evidenceListSchemaVersion": EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION,
        "evidenceListEnvelopeSchemaVersion": EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION,
        "evidenceListId": EVIDENCE_LIST_ARTIFACT_ID,
        "evidenceItemCount": evidence_list["evidenceItemCount"],
        "evidenceListContentHash": _stable_file_hash(full_path),
    }


def _build_verifier_result_binding(
    root: Path, verifier_result: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / VERIFIER_RESULT_ARTIFACT_PATH
    return {
        "verifierResultRef": VERIFIER_RESULT_ARTIFACT_PATH,
        "verifierResultSchemaVersion": VERIFIER_RESULT_SCHEMA_VERSION,
        "verifierResultEnvelopeSchemaVersion": VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION,
        "verifierResultId": VERIFIER_RESULT_ARTIFACT_ID,
        "verdict": verifier_result["verdict"],
        "verifierResultContentHash": _stable_file_hash(full_path),
    }


def _build_delivery_manifest_binding(root: Path) -> dict[str, Any]:
    full_path = root / DELIVERY_MANIFEST_ARTIFACT_PATH
    return {
        "deliveryManifestRef": DELIVERY_MANIFEST_ARTIFACT_PATH,
        "deliveryManifestSchemaVersion": DELIVERY_MANIFEST_SCHEMA_VERSION,
        "deliveryManifestEnvelopeSchemaVersion": DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "deliveryManifestId": DELIVERY_MANIFEST_ARTIFACT_ID,
        "deliveryManifestContentHash": _stable_file_hash(full_path),
    }


def _build_policy_manifest_binding(
    root: Path, policy_manifest: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / POLICY_MANIFEST_ARTIFACT_PATH
    unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    return {
        "policyManifestRef": POLICY_MANIFEST_ARTIFACT_PATH,
        "policyManifestSchemaVersion": POLICY_MANIFEST_SCHEMA_VERSION,
        "policyManifestEnvelopeSchemaVersion": POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "policyManifestId": POLICY_MANIFEST_ARTIFACT_ID,
        "unlocked": unlocked,
        "policyManifestContentHash": _stable_file_hash(full_path),
    }


def _build_approval_decision_binding(
    root: Path, approval_decision: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH
    decision_block = approval_decision.get("decision", {})
    return {
        "approvalDecisionRef": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
        "approvalDecisionSchemaVersion": HUMAN_APPROVAL_DECISION_SCHEMA_VERSION,
        "approvalDecisionId": approval_decision["id"],
        "approvalGranted": bool(decision_block.get("approvalGranted", False)),
        "approvalDecisionContentHash": _stable_file_hash(full_path),
    }


def _build_promotion_conditions(
    intent_lifecycle_state: str,
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> dict[str, Any]:
    verdict = verifier_result["verdict"]
    terminal_state = run_event_log["terminalState"]
    unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    promoted = (
        intent_lifecycle_state == REQUIRED_LIFECYCLE_STATE_FOR_PROMOTION
        and verdict == REQUIRED_VERDICT_FOR_PROMOTION
        and terminal_state == REQUIRED_TERMINAL_RUN_STATE
        and unlocked is True
    )
    return {
        "requiredLifecycleState": REQUIRED_LIFECYCLE_STATE_FOR_PROMOTION,
        "currentLifecycleState": intent_lifecycle_state,
        "requiredVerdict": REQUIRED_VERDICT_FOR_PROMOTION,
        "currentVerdict": verdict,
        "verdictOwner": VERIFIER_VERDICT_OWNER,
        "requiredTerminalRunState": REQUIRED_TERMINAL_RUN_STATE,
        "currentTerminalRunState": terminal_state,
        "requiredPolicyUnlocked": REQUIRED_POLICY_UNLOCKED,
        "currentPolicyUnlocked": unlocked,
        "promoted": promoted,
    }


def build_intent_artifact(root: Path) -> dict[str, Any]:
    (
        task_spec,
        run_event_log,
        observation_list,
        evidence_list,
        verifier_result,
        policy_manifest,
        run_artifact,
        step_list,
        tool_call_list,
        approval_decision,
    ) = _validate_referenced_artifacts(root)

    payload: dict[str, Any] = {
        "schemaVersion": INTENT_ARTIFACT_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "intentId": INTENT_ID,
        "intentNarrative": INTENT_NARRATIVE,
        "intentOriginAgent": INTENT_ORIGIN_AGENT,
        "intentOriginChannel": INTENT_ORIGIN_CHANNEL,
        "intentLifecycleState": INTENT_LIFECYCLE_STATE,
        "acceptedTaskSpecRef": ACCEPTED_TASK_SPEC_REF,
        "requestedWorkloadType": REQUESTED_WORKLOAD_TYPE,
        "requestedCapabilityClasses": list(REQUESTED_CAPABILITY_CLASSES),
        "requestedArtifactKinds": list(REQUESTED_ARTIFACT_KINDS),
        "requestedVerifierClass": REQUESTED_VERIFIER_CLASS,
        "requestedDeliveryClass": REQUESTED_DELIVERY_CLASS,
        "requestedPolicyClass": REQUESTED_POLICY_CLASS,
        "intentLifecycleStateDomain": list(INTENT_LIFECYCLE_STATE_DOMAIN),
        "requestedCapabilityClassDomain": list(REQUESTED_CAPABILITY_CLASS_DOMAIN),
        "forbiddenRequestedCapabilityClasses": list(FORBIDDEN_REQUESTED_CAPABILITY_CLASSES),
        "intentOriginAgentDomain": list(INTENT_ORIGIN_AGENT_DOMAIN),
        "intentOriginChannelDomain": list(INTENT_ORIGIN_CHANNEL_DOMAIN),
        "requestedArtifactKindDomain": list(REQUESTED_ARTIFACT_KIND_DOMAIN),
        "verdictDomain": list(VERDICT_DOMAIN),
        "permissionFlagDomain": list(PERMISSION_FLAG_DOMAIN),
        "permissionFlags": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
        "taskSpecBinding": _build_task_spec_binding(root, task_spec),
        "runBinding": _build_run_binding(root, run_artifact),
        "stepListBinding": _build_step_list_binding(root, step_list),
        "toolCallListBinding": _build_tool_call_list_binding(root, tool_call_list),
        "capabilityManifestBinding": _build_capability_manifest_binding(root),
        "runEventLogBinding": _build_run_event_log_binding(root, run_event_log),
        "observationListBinding": _build_observation_list_binding(root, observation_list),
        "evidenceListBinding": _build_evidence_list_binding(root, evidence_list),
        "verifierResultBinding": _build_verifier_result_binding(root, verifier_result),
        "deliveryManifestBinding": _build_delivery_manifest_binding(root),
        "policyManifestBinding": _build_policy_manifest_binding(root, policy_manifest),
        "approvalDecisionBinding": _build_approval_decision_binding(root, approval_decision),
        "promotionConditions": _build_promotion_conditions(
            INTENT_LIFECYCLE_STATE, verifier_result, run_event_log, policy_manifest
        ),
        "verifierExpectations": {
            **{flag: True for flag in REQUIRED_VERIFIER_FLAGS},
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERDICT_DOMAIN),
        },
        "regressionWorkloadIsolation": {
            "reusesRegressionIntentArtifact": False,
            "reusesRegressionTaskSpec": False,
            "reusesRegressionResultArtifact": False,
            "reusesSendEmailCapability": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "coordinationBinding": _coordination_binding(root),
        "sourceArtifacts": [
            _artifact_source(role, relative_path, root)
            for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
        ],
        "invariants": list(INVARIANTS),
    }
    validate_intent_artifact(payload, root)
    return payload


def _validate_binding_common(
    label: str,
    binding: Any,
    required_fields: list[str],
    *,
    ref_field: str,
    expected_ref: str,
    hash_field: str,
    root: Path,
) -> None:
    if not isinstance(binding, dict):
        raise ValueError(f"IntentV1 {label} must be an object")
    _require_fields(f"IntentV1 {label}", binding, required_fields)
    if binding[ref_field] != expected_ref:
        raise ValueError(f"IntentV1 {label}.{ref_field} must equal {expected_ref}")
    full_path = root / binding[ref_field]
    if binding[hash_field] != _stable_file_hash(full_path):
        raise ValueError(
            f"IntentV1 {label}.{hash_field} must match the on-disk artifact"
        )


def _validate_task_spec_binding(
    binding: dict[str, Any], root: Path, task_spec: dict[str, Any]
) -> None:
    _validate_binding_common(
        "taskSpecBinding",
        binding,
        [
            "taskSpecRef",
            "taskSpecSchemaVersion",
            "taskSpecEnvelopeSchemaVersion",
            "taskSpecId",
            "taskSpecWorkloadType",
            "taskSpecContentHash",
        ],
        ref_field="taskSpecRef",
        expected_ref=TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
        hash_field="taskSpecContentHash",
        root=root,
    )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 taskSpecBinding.taskSpecSchemaVersion must equal "
            f"{TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression-task-spec-v1 reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal "
            f"{TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"IntentV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    if binding["taskSpecWorkloadType"] != TASK_SPEC_WORKLOAD_TYPE:
        raise ValueError(
            f"IntentV1 taskSpecBinding.taskSpecWorkloadType must equal {TASK_SPEC_WORKLOAD_TYPE}"
        )
    if binding["taskSpecWorkloadType"] != task_spec["workloadType"]:
        raise ValueError(
            "IntentV1 taskSpecBinding.taskSpecWorkloadType must equal TestExecutionTaskSpecV1.workloadType"
        )


def _validate_run_binding(
    binding: dict[str, Any], root: Path, run_artifact: dict[str, Any]
) -> None:
    _validate_binding_common(
        "runBinding",
        binding,
        [
            "runRef",
            "runSchemaVersion",
            "runEnvelopeSchemaVersion",
            "runId",
            "runIdentifier",
            "runState",
            "runContentHash",
        ],
        ref_field="runRef",
        expected_ref=RUN_ARTIFACT_PATH,
        hash_field="runContentHash",
        root=root,
    )
    if binding["runSchemaVersion"] != RUN_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 runBinding.runSchemaVersion must equal {RUN_ARTIFACT_SCHEMA_VERSION}; "
            "regression run.json reuse is forbidden"
        )
    if binding["runEnvelopeSchemaVersion"] != RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 runBinding.runEnvelopeSchemaVersion must equal {RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runId"] != RUN_ARTIFACT_ID:
        raise ValueError(f"IntentV1 runBinding.runId must equal {RUN_ARTIFACT_ID}")
    if binding["runIdentifier"] != run_artifact["runId"]:
        raise ValueError("IntentV1 runBinding.runIdentifier must equal RunV1.runId")
    if binding["runState"] != run_artifact["runState"]:
        raise ValueError("IntentV1 runBinding.runState must equal RunV1.runState")


def _validate_step_list_binding(
    binding: dict[str, Any], root: Path, step_list: dict[str, Any]
) -> None:
    _validate_binding_common(
        "stepListBinding",
        binding,
        [
            "stepListRef",
            "stepListSchemaVersion",
            "stepListEnvelopeSchemaVersion",
            "stepListId",
            "stepCount",
            "stepListContentHash",
        ],
        ref_field="stepListRef",
        expected_ref=STEP_LIST_ARTIFACT_PATH,
        hash_field="stepListContentHash",
        root=root,
    )
    if binding["stepListSchemaVersion"] != STEP_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 stepListBinding.stepListSchemaVersion must equal {STEP_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression run.json steps array reuse is forbidden"
        )
    if binding["stepListEnvelopeSchemaVersion"] != STEP_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 stepListBinding.stepListEnvelopeSchemaVersion must equal {STEP_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["stepListId"] != STEP_LIST_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 stepListBinding.stepListId must equal {STEP_LIST_ARTIFACT_ID}"
        )
    if binding["stepCount"] != step_list["stepCount"]:
        raise ValueError(
            "IntentV1 stepListBinding.stepCount must equal StepListV1.stepCount"
        )


def _validate_tool_call_list_binding(
    binding: dict[str, Any], root: Path, tool_call_list: dict[str, Any]
) -> None:
    _validate_binding_common(
        "toolCallListBinding",
        binding,
        [
            "toolCallListRef",
            "toolCallListSchemaVersion",
            "toolCallListEnvelopeSchemaVersion",
            "toolCallListId",
            "toolCallCount",
            "toolCallListContentHash",
        ],
        ref_field="toolCallListRef",
        expected_ref=TOOL_CALL_LIST_ARTIFACT_PATH,
        hash_field="toolCallListContentHash",
        root=root,
    )
    if binding["toolCallListSchemaVersion"] != TOOL_CALL_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 toolCallListBinding.toolCallListSchemaVersion must equal {TOOL_CALL_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression tool-call artifact reuse is forbidden"
        )
    if binding["toolCallListEnvelopeSchemaVersion"] != TOOL_CALL_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 toolCallListBinding.toolCallListEnvelopeSchemaVersion must equal {TOOL_CALL_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["toolCallListId"] != TOOL_CALL_LIST_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 toolCallListBinding.toolCallListId must equal {TOOL_CALL_LIST_ARTIFACT_ID}"
        )
    if binding["toolCallCount"] != tool_call_list["toolCallCount"]:
        raise ValueError(
            "IntentV1 toolCallListBinding.toolCallCount must equal ToolCallListV1.toolCallCount"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _validate_binding_common(
        "capabilityManifestBinding",
        binding,
        [
            "capabilityManifestRef",
            "capabilityManifestSchemaVersion",
            "capabilityManifestEnvelopeSchemaVersion",
            "capabilityManifestId",
            "capabilityManifestContentHash",
        ],
        ref_field="capabilityManifestRef",
        expected_ref=CAPABILITY_MANIFEST_ARTIFACT_PATH,
        hash_field="capabilityManifestContentHash",
        root=root,
    )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal {CAPABILITY_MANIFEST_SCHEMA_VERSION}; "
            "regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal {CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 capabilityManifestBinding.capabilityManifestId must equal {CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )


def _validate_run_event_log_binding(
    binding: dict[str, Any], root: Path, run_event_log: dict[str, Any]
) -> None:
    _validate_binding_common(
        "runEventLogBinding",
        binding,
        [
            "runEventLogRef",
            "runEventLogSchemaVersion",
            "runEventLogEnvelopeSchemaVersion",
            "runEventLogId",
            "eventCount",
            "terminalState",
            "runEventLogContentHash",
        ],
        ref_field="runEventLogRef",
        expected_ref=RUN_EVENT_LOG_ARTIFACT_PATH,
        hash_field="runEventLogContentHash",
        root=root,
    )
    if binding["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 runEventLogBinding.runEventLogSchemaVersion must equal {RUN_EVENT_LOG_SCHEMA_VERSION}; "
            "regression events.jsonl reuse is forbidden"
        )
    if binding["runEventLogEnvelopeSchemaVersion"] != RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 runEventLogBinding.runEventLogEnvelopeSchemaVersion must equal {RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runEventLogId"] != RUN_EVENT_LOG_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 runEventLogBinding.runEventLogId must equal {RUN_EVENT_LOG_ARTIFACT_ID}"
        )
    if binding["eventCount"] != run_event_log["eventCount"]:
        raise ValueError(
            "IntentV1 runEventLogBinding.eventCount must equal RunEventLogV1.eventCount"
        )
    if binding["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "IntentV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )


def _validate_observation_list_binding(
    binding: dict[str, Any], root: Path, observation_list: dict[str, Any]
) -> None:
    _validate_binding_common(
        "observationListBinding",
        binding,
        [
            "observationListRef",
            "observationListSchemaVersion",
            "observationListEnvelopeSchemaVersion",
            "observationListId",
            "observationItemCount",
            "observationListContentHash",
        ],
        ref_field="observationListRef",
        expected_ref=OBSERVATION_LIST_ARTIFACT_PATH,
        hash_field="observationListContentHash",
        root=root,
    )
    if binding["observationListSchemaVersion"] != OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 observationListBinding.observationListSchemaVersion must equal {OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression observation reuse is forbidden"
        )
    if binding["observationListEnvelopeSchemaVersion"] != OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 observationListBinding.observationListEnvelopeSchemaVersion must equal {OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["observationListId"] != OBSERVATION_LIST_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 observationListBinding.observationListId must equal {OBSERVATION_LIST_ARTIFACT_ID}"
        )
    if binding["observationItemCount"] != observation_list["observationItemCount"]:
        raise ValueError(
            "IntentV1 observationListBinding.observationItemCount must equal ObservationListV1.observationItemCount"
        )


def _validate_evidence_list_binding(
    binding: dict[str, Any], root: Path, evidence_list: dict[str, Any]
) -> None:
    _validate_binding_common(
        "evidenceListBinding",
        binding,
        [
            "evidenceListRef",
            "evidenceListSchemaVersion",
            "evidenceListEnvelopeSchemaVersion",
            "evidenceListId",
            "evidenceItemCount",
            "evidenceListContentHash",
        ],
        ref_field="evidenceListRef",
        expected_ref=EVIDENCE_LIST_ARTIFACT_PATH,
        hash_field="evidenceListContentHash",
        root=root,
    )
    if binding["evidenceListSchemaVersion"] != EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 evidenceListBinding.evidenceListSchemaVersion must equal {EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression evidence-list-v1 reuse is forbidden"
        )
    if binding["evidenceListEnvelopeSchemaVersion"] != EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 evidenceListBinding.evidenceListEnvelopeSchemaVersion must equal {EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["evidenceListId"] != EVIDENCE_LIST_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 evidenceListBinding.evidenceListId must equal {EVIDENCE_LIST_ARTIFACT_ID}"
        )
    if binding["evidenceItemCount"] != evidence_list["evidenceItemCount"]:
        raise ValueError(
            "IntentV1 evidenceListBinding.evidenceItemCount must equal EvidenceListV1.evidenceItemCount"
        )


def _validate_verifier_result_binding(
    binding: dict[str, Any], root: Path, verifier_result: dict[str, Any]
) -> None:
    _validate_binding_common(
        "verifierResultBinding",
        binding,
        [
            "verifierResultRef",
            "verifierResultSchemaVersion",
            "verifierResultEnvelopeSchemaVersion",
            "verifierResultId",
            "verdict",
            "verifierResultContentHash",
        ],
        ref_field="verifierResultRef",
        expected_ref=VERIFIER_RESULT_ARTIFACT_PATH,
        hash_field="verifierResultContentHash",
        root=root,
    )
    if binding["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 verifierResultBinding.verifierResultSchemaVersion must equal {VERIFIER_RESULT_SCHEMA_VERSION}; "
            "regression result artifact reuse is forbidden"
        )
    if binding["verifierResultEnvelopeSchemaVersion"] != VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 verifierResultBinding.verifierResultEnvelopeSchemaVersion must equal {VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["verifierResultId"] != VERIFIER_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 verifierResultBinding.verifierResultId must equal {VERIFIER_RESULT_ARTIFACT_ID}"
        )
    if binding["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"IntentV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}"
        )
    if binding["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "IntentV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )


def _validate_delivery_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _validate_binding_common(
        "deliveryManifestBinding",
        binding,
        [
            "deliveryManifestRef",
            "deliveryManifestSchemaVersion",
            "deliveryManifestEnvelopeSchemaVersion",
            "deliveryManifestId",
            "deliveryManifestContentHash",
        ],
        ref_field="deliveryManifestRef",
        expected_ref=DELIVERY_MANIFEST_ARTIFACT_PATH,
        hash_field="deliveryManifestContentHash",
        root=root,
    )
    if binding["deliveryManifestSchemaVersion"] != DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 deliveryManifestBinding.deliveryManifestSchemaVersion must equal {DELIVERY_MANIFEST_SCHEMA_VERSION}; "
            "multi-agent-delivery-manifest reuse is forbidden"
        )
    if binding["deliveryManifestEnvelopeSchemaVersion"] != DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 deliveryManifestBinding.deliveryManifestEnvelopeSchemaVersion must equal {DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["deliveryManifestId"] != DELIVERY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 deliveryManifestBinding.deliveryManifestId must equal {DELIVERY_MANIFEST_ARTIFACT_ID}"
        )


def _validate_policy_manifest_binding(
    binding: dict[str, Any], root: Path, policy_manifest: dict[str, Any]
) -> None:
    _validate_binding_common(
        "policyManifestBinding",
        binding,
        [
            "policyManifestRef",
            "policyManifestSchemaVersion",
            "policyManifestEnvelopeSchemaVersion",
            "policyManifestId",
            "unlocked",
            "policyManifestContentHash",
        ],
        ref_field="policyManifestRef",
        expected_ref=POLICY_MANIFEST_ARTIFACT_PATH,
        hash_field="policyManifestContentHash",
        root=root,
    )
    if binding["policyManifestSchemaVersion"] != POLICY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 policyManifestBinding.policyManifestSchemaVersion must equal {POLICY_MANIFEST_SCHEMA_VERSION}; "
            "regression / adapter policy reuse is forbidden"
        )
    if binding["policyManifestEnvelopeSchemaVersion"] != POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 policyManifestBinding.policyManifestEnvelopeSchemaVersion must equal {POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["policyManifestId"] != POLICY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"IntentV1 policyManifestBinding.policyManifestId must equal {POLICY_MANIFEST_ARTIFACT_ID}"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if binding["unlocked"] is not expected_unlocked:
        raise ValueError(
            "IntentV1 policyManifestBinding.unlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )


def _validate_approval_decision_binding(
    binding: dict[str, Any], root: Path, approval_decision: dict[str, Any]
) -> None:
    _validate_binding_common(
        "approvalDecisionBinding",
        binding,
        [
            "approvalDecisionRef",
            "approvalDecisionSchemaVersion",
            "approvalDecisionId",
            "approvalGranted",
            "approvalDecisionContentHash",
        ],
        ref_field="approvalDecisionRef",
        expected_ref=HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
        hash_field="approvalDecisionContentHash",
        root=root,
    )
    if binding["approvalDecisionSchemaVersion"] != HUMAN_APPROVAL_DECISION_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 approvalDecisionBinding.approvalDecisionSchemaVersion must equal {HUMAN_APPROVAL_DECISION_SCHEMA_VERSION}"
        )
    if binding["approvalDecisionId"] != approval_decision["id"]:
        raise ValueError(
            "IntentV1 approvalDecisionBinding.approvalDecisionId must equal HumanApprovalDecisionV1.id"
        )
    expected_granted = bool(approval_decision.get("decision", {}).get("approvalGranted", False))
    if binding["approvalGranted"] is not expected_granted:
        raise ValueError(
            "IntentV1 approvalDecisionBinding.approvalGranted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )


def _validate_promotion_conditions(
    promotion: dict[str, Any],
    intent_lifecycle_state: str,
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> None:
    _require_fields(
        "IntentV1 promotionConditions",
        promotion,
        [
            "requiredLifecycleState",
            "currentLifecycleState",
            "requiredVerdict",
            "currentVerdict",
            "verdictOwner",
            "requiredTerminalRunState",
            "currentTerminalRunState",
            "requiredPolicyUnlocked",
            "currentPolicyUnlocked",
            "promoted",
        ],
    )
    if promotion["requiredLifecycleState"] != REQUIRED_LIFECYCLE_STATE_FOR_PROMOTION:
        raise ValueError(
            f"IntentV1 promotionConditions.requiredLifecycleState must be {REQUIRED_LIFECYCLE_STATE_FOR_PROMOTION}"
        )
    if promotion["currentLifecycleState"] != intent_lifecycle_state:
        raise ValueError(
            "IntentV1 promotionConditions.currentLifecycleState must equal IntentV1.intentLifecycleState"
        )
    if promotion["requiredVerdict"] != REQUIRED_VERDICT_FOR_PROMOTION:
        raise ValueError(
            f"IntentV1 promotionConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_PROMOTION}"
        )
    if promotion["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "IntentV1 promotionConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if promotion["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"IntentV1 promotionConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if promotion["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"IntentV1 promotionConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if promotion["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "IntentV1 promotionConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if promotion["requiredPolicyUnlocked"] is not REQUIRED_POLICY_UNLOCKED:
        raise ValueError("IntentV1 promotionConditions.requiredPolicyUnlocked must be true")
    if promotion["currentPolicyUnlocked"] is not expected_unlocked:
        raise ValueError(
            "IntentV1 promotionConditions.currentPolicyUnlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_promoted = (
        promotion["currentLifecycleState"] == REQUIRED_LIFECYCLE_STATE_FOR_PROMOTION
        and promotion["currentVerdict"] == REQUIRED_VERDICT_FOR_PROMOTION
        and promotion["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and promotion["currentPolicyUnlocked"] is True
    )
    if promotion["promoted"] is not expected_promoted:
        raise ValueError(
            "IntentV1 promotionConditions.promoted must be true only when lifecycle, verdict, run terminal state and policy unlock all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("IntentV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("IntentV1 sourceArtifacts entries must be objects")
        _require_fields(
            "IntentV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(f"IntentV1 sourceArtifacts contains unexpected role: {role}")
        if role in seen_roles:
            raise ValueError(f"IntentV1 sourceArtifacts contains duplicate role: {role}")
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"IntentV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(f"IntentV1 source artifact does not exist: {path}")
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(f"IntentV1 source hash mismatch for {path}")
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"IntentV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_intent_artifact(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "IntentV1",
        manifest,
        [
            "schemaVersion",
            "artifactEnvelopeSchemaVersion",
            "id",
            "generatedAt",
            "kind",
            "scope",
            "workloadType",
            "workloadCategory",
            "creatorAgent",
            "verifierVerdictOwner",
            "intentId",
            "intentNarrative",
            "intentOriginAgent",
            "intentOriginChannel",
            "intentLifecycleState",
            "acceptedTaskSpecRef",
            "requestedWorkloadType",
            "requestedCapabilityClasses",
            "requestedArtifactKinds",
            "requestedVerifierClass",
            "requestedDeliveryClass",
            "requestedPolicyClass",
            "intentLifecycleStateDomain",
            "requestedCapabilityClassDomain",
            "forbiddenRequestedCapabilityClasses",
            "intentOriginAgentDomain",
            "intentOriginChannelDomain",
            "requestedArtifactKindDomain",
            "verdictDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "taskSpecBinding",
            "runBinding",
            "stepListBinding",
            "toolCallListBinding",
            "capabilityManifestBinding",
            "runEventLogBinding",
            "observationListBinding",
            "evidenceListBinding",
            "verifierResultBinding",
            "deliveryManifestBinding",
            "policyManifestBinding",
            "approvalDecisionBinding",
            "promotionConditions",
            "verifierExpectations",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != INTENT_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 schemaVersion must be {INTENT_ARTIFACT_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"IntentV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"IntentV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"IntentV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"IntentV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"IntentV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"IntentV1 workloadType must be {WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(f"IntentV1 workloadCategory must be {WORKLOAD_CATEGORY}")
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"IntentV1 creatorAgent must be {CREATOR_AGENT}")
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"IntentV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; creator must not own the verdict"
        )

    if manifest["intentId"] != INTENT_ID:
        raise ValueError(f"IntentV1 intentId must equal {INTENT_ID}")
    narrative = manifest["intentNarrative"]
    if not isinstance(narrative, str) or not narrative.strip():
        raise ValueError("IntentV1 intentNarrative must be a non-empty string")

    if manifest["intentOriginAgent"] not in INTENT_ORIGIN_AGENT_DOMAIN:
        raise ValueError(
            f"IntentV1 intentOriginAgent must be one of {INTENT_ORIGIN_AGENT_DOMAIN}"
        )
    if manifest["intentOriginAgent"] != INTENT_ORIGIN_AGENT:
        raise ValueError(f"IntentV1 intentOriginAgent must equal {INTENT_ORIGIN_AGENT}")
    if manifest["intentOriginChannel"] not in INTENT_ORIGIN_CHANNEL_DOMAIN:
        raise ValueError(
            f"IntentV1 intentOriginChannel must be one of {INTENT_ORIGIN_CHANNEL_DOMAIN}"
        )
    if manifest["intentOriginChannel"] != INTENT_ORIGIN_CHANNEL:
        raise ValueError(
            f"IntentV1 intentOriginChannel must equal {INTENT_ORIGIN_CHANNEL}"
        )

    if manifest["intentLifecycleState"] not in INTENT_LIFECYCLE_STATE_DOMAIN:
        raise ValueError(
            f"IntentV1 intentLifecycleState must be one of {INTENT_LIFECYCLE_STATE_DOMAIN}"
        )
    if manifest["intentLifecycleState"] != INTENT_LIFECYCLE_STATE:
        raise ValueError(
            f"IntentV1 intentLifecycleState must equal {INTENT_LIFECYCLE_STATE}"
        )

    if manifest["acceptedTaskSpecRef"] != ACCEPTED_TASK_SPEC_REF:
        raise ValueError(
            f"IntentV1 acceptedTaskSpecRef must equal {ACCEPTED_TASK_SPEC_REF}"
        )

    if manifest["requestedWorkloadType"] != REQUESTED_WORKLOAD_TYPE:
        raise ValueError(
            f"IntentV1 requestedWorkloadType must equal {REQUESTED_WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )

    requested_capabilities = manifest["requestedCapabilityClasses"]
    if not isinstance(requested_capabilities, list) or not requested_capabilities:
        raise ValueError(
            "IntentV1 requestedCapabilityClasses must be a non-empty list"
        )
    for capability_class in requested_capabilities:
        if capability_class in FORBIDDEN_REQUESTED_CAPABILITY_CLASSES:
            raise ValueError(
                f"IntentV1 requestedCapabilityClasses contains forbidden class: {capability_class}"
            )
        if capability_class not in REQUESTED_CAPABILITY_CLASS_DOMAIN:
            raise ValueError(
                f"IntentV1 requestedCapabilityClasses contains class outside the workload-independent domain: {capability_class}"
            )
    if requested_capabilities != list(REQUESTED_CAPABILITY_CLASSES):
        raise ValueError(
            f"IntentV1 requestedCapabilityClasses must equal {REQUESTED_CAPABILITY_CLASSES}"
        )

    requested_kinds = manifest["requestedArtifactKinds"]
    if not isinstance(requested_kinds, list) or not requested_kinds:
        raise ValueError("IntentV1 requestedArtifactKinds must be a non-empty list")
    for kind in requested_kinds:
        if kind not in REQUESTED_ARTIFACT_KIND_DOMAIN:
            raise ValueError(
                f"IntentV1 requestedArtifactKinds contains kind outside the workload-independent domain: {kind}"
            )
    if requested_kinds != list(REQUESTED_ARTIFACT_KINDS):
        raise ValueError(
            f"IntentV1 requestedArtifactKinds must equal {REQUESTED_ARTIFACT_KINDS}"
        )

    if manifest["requestedVerifierClass"] != REQUESTED_VERIFIER_CLASS:
        raise ValueError(
            f"IntentV1 requestedVerifierClass must equal {REQUESTED_VERIFIER_CLASS}"
        )
    if manifest["requestedDeliveryClass"] != REQUESTED_DELIVERY_CLASS:
        raise ValueError(
            f"IntentV1 requestedDeliveryClass must equal {REQUESTED_DELIVERY_CLASS}"
        )
    if manifest["requestedPolicyClass"] != REQUESTED_POLICY_CLASS:
        raise ValueError(
            f"IntentV1 requestedPolicyClass must equal {REQUESTED_POLICY_CLASS}"
        )

    if manifest["intentLifecycleStateDomain"] != list(INTENT_LIFECYCLE_STATE_DOMAIN):
        raise ValueError(
            f"IntentV1 intentLifecycleStateDomain must equal {INTENT_LIFECYCLE_STATE_DOMAIN}"
        )
    if manifest["requestedCapabilityClassDomain"] != list(REQUESTED_CAPABILITY_CLASS_DOMAIN):
        raise ValueError(
            f"IntentV1 requestedCapabilityClassDomain must equal {REQUESTED_CAPABILITY_CLASS_DOMAIN}"
        )
    if manifest["forbiddenRequestedCapabilityClasses"] != list(FORBIDDEN_REQUESTED_CAPABILITY_CLASSES):
        raise ValueError(
            f"IntentV1 forbiddenRequestedCapabilityClasses must equal {FORBIDDEN_REQUESTED_CAPABILITY_CLASSES}"
        )
    overlap = set(manifest["forbiddenRequestedCapabilityClasses"]).intersection(
        manifest["requestedCapabilityClasses"]
    )
    if overlap:
        raise ValueError(
            f"IntentV1 forbiddenRequestedCapabilityClasses must not intersect requestedCapabilityClasses: {sorted(overlap)}"
        )
    if manifest["intentOriginAgentDomain"] != list(INTENT_ORIGIN_AGENT_DOMAIN):
        raise ValueError(
            f"IntentV1 intentOriginAgentDomain must equal {INTENT_ORIGIN_AGENT_DOMAIN}"
        )
    if manifest["intentOriginChannelDomain"] != list(INTENT_ORIGIN_CHANNEL_DOMAIN):
        raise ValueError(
            f"IntentV1 intentOriginChannelDomain must equal {INTENT_ORIGIN_CHANNEL_DOMAIN}"
        )
    if manifest["requestedArtifactKindDomain"] != list(REQUESTED_ARTIFACT_KIND_DOMAIN):
        raise ValueError(
            f"IntentV1 requestedArtifactKindDomain must equal {REQUESTED_ARTIFACT_KIND_DOMAIN}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(f"IntentV1 verdictDomain must equal {VERDICT_DOMAIN}")
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"IntentV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )
    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"IntentV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(f"IntentV1 permissionFlags.{flag} must be false")

    task_spec = _load_json(root / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    observation_list = _load_json(root / OBSERVATION_LIST_ARTIFACT_PATH)
    evidence_list = _load_json(root / EVIDENCE_LIST_ARTIFACT_PATH)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    run_artifact = _load_json(root / RUN_ARTIFACT_PATH)
    step_list = _load_json(root / STEP_LIST_ARTIFACT_PATH)
    tool_call_list = _load_json(root / TOOL_CALL_LIST_ARTIFACT_PATH)

    if task_spec["id"] != ACCEPTED_TASK_SPEC_REF:
        raise ValueError(
            f"IntentV1 acceptedTaskSpecRef must resolve to TestExecutionTaskSpecV1.id={task_spec['id']}"
        )

    _validate_task_spec_binding(manifest["taskSpecBinding"], root, task_spec)
    _validate_run_binding(manifest["runBinding"], root, run_artifact)
    _validate_step_list_binding(manifest["stepListBinding"], root, step_list)
    _validate_tool_call_list_binding(manifest["toolCallListBinding"], root, tool_call_list)
    _validate_capability_manifest_binding(manifest["capabilityManifestBinding"], root)
    _validate_run_event_log_binding(manifest["runEventLogBinding"], root, run_event_log)
    _validate_observation_list_binding(manifest["observationListBinding"], root, observation_list)
    _validate_evidence_list_binding(manifest["evidenceListBinding"], root, evidence_list)
    _validate_verifier_result_binding(manifest["verifierResultBinding"], root, verifier_result)
    _validate_delivery_manifest_binding(manifest["deliveryManifestBinding"], root)
    _validate_policy_manifest_binding(manifest["policyManifestBinding"], root, policy_manifest)
    _validate_approval_decision_binding(manifest["approvalDecisionBinding"], root, approval_decision)
    _validate_promotion_conditions(
        manifest["promotionConditions"],
        manifest["intentLifecycleState"],
        verifier_result,
        run_event_log,
        policy_manifest,
    )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "IntentV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(f"IntentV1 verifierExpectations.{flag} must be true")
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"IntentV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"IntentV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "IntentV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionIntentArtifact",
            "reusesRegressionTaskSpec",
            "reusesRegressionResultArtifact",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionIntentArtifact"] is not False:
        raise ValueError(
            "IntentV1 must not reuse any first-workload regression intent artifact"
        )
    if isolation["reusesRegressionTaskSpec"] is not False:
        raise ValueError("IntentV1 must not reuse the regression-task-spec-v1 schema")
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError("IntentV1 must not reuse RegressionResultArtifactV1")
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError("IntentV1 must not reuse the send_email capability")
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"IntentV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"IntentV1 must not embed regression/email field {term} outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"IntentV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            f"IntentV1 coordinationBinding must include {sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"IntentV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 6:
        raise ValueError(
            "IntentV1 invariants must declare at least six workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="intent-artifact")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_intent_artifact(root)
        _write_json(args.out, manifest)
        print(f"Wrote IntentV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_intent_artifact(manifest, root)
        print(f"Validated IntentV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

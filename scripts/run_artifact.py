"""RunV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``RunV1`` ArtifactV1 subtype.
It captures the canonical OS-kernel ``Run`` primitive for any engineering
workload by tying together every previously committed kernel primitive into
a single, machine-verifiable run record:

- a workload-independent ``RunV1`` envelope (``run-artifact-v1``) reusing the
  shared ``ArtifactV1`` envelope (``artifact-v1``);
- workload-independent ``runId`` / ``runState`` / ``startedAt`` /
  ``terminalAt`` / ``runControlStateMachineRef`` /
  ``runControlStateMachineSchemaVersion`` / ``runControlStates`` /
  ``terminalRunControlStates`` / ``allowedRunControlTransitions`` /
  ``initialRunControlState`` fields, all anchored on the kernel-level
  ``run-state-machine-v1`` state machine declared by ``RunEventLogV1``;
- bindings to every previously committed primitive
  (``TestExecutionTaskSpecV1``, ``CapabilityManifestV1``, ``RunEventLogV1``,
  ``ObservationListV1``, ``EvidenceListV1``, ``VerifierResultV1``,
  ``DeliveryManifestV1``, ``PolicyManifestV1`` and
  ``HumanApprovalDecisionV1``) by ref + content hash plus the five Agent
  Coordination Layer manifests;
- cross-artifact consistency: ``runState`` must equal
  ``RunEventLogV1.terminalState``; ``startedAt`` and ``terminalAt`` must
  equal the first and last ``RunEventLogV1.events`` timestamps;
  ``eventCount`` / ``observationCount`` / ``evidenceCount`` must equal the
  upstream counts; every ``runControlStateAfter`` transition observed in
  ``RunEventLogV1.events`` must be a member of
  ``allowedRunControlTransitions``; ``promotionConditions`` requires
  ``VerifierResultV1.verdict==passed``,
  ``RunEventLogV1.terminalState==completed`` and
  ``PolicyManifestV1.unlockConditions.unlocked==true``;
- verifier-runtime-v1 owns acceptance: ``creatorMustNotOwnVerdict=true``;
- six workload-independent permission flags forced to ``false``.

The artifact answers four OS-kernel invariants at once:

- ``Run`` primitive: the manifest declares a workload-independent
  ``Run`` envelope independent of the first-workload regression
  ``artifacts/runs/<fixture>/run.json`` artifact, and reuses the
  ``run-state-machine-v1`` state machine across workloads.
- ``Artifact`` envelope reuse: the manifest is an ``ArtifactV1`` subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) joining the existing
  ``CapabilityManifestV1`` / ``TestExecutionResultV1`` /
  ``FailureTriageReportV1`` / ``VerifierResultV1`` / ``RunEventLogV1`` /
  ``DeliveryManifestV1`` / ``PolicyManifestV1`` / ``EvidenceListV1`` /
  ``ObservationListV1`` subtypes, and it is the first ArtifactV1 subtype
  that wires every other primitive together by content hash.
- ``Verifier`` / ``Policy`` consistency: the manifest pins the
  ``VerifierResultV1`` verdict, ``RunEventLogV1.terminalState`` and
  ``PolicyManifestV1`` unlock as prerequisites for any creator-side run
  promotion, and declares ``verifier-runtime-v1`` as the verdict owner
  while forcing ``creatorMustNotOwnVerdict=true``.
- ``Coordination`` boundary: the manifest binds all five Agent Coordination
  Layer contracts by ref + content hash, so every coordination decision
  over the run is constrained by the same envelope.
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
from run_event_log import (
    ALLOWED_RUN_CONTROL_TRANSITIONS,
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as RUN_EVENT_LOG_ARTIFACT_ID,
    INITIAL_RUN_CONTROL_STATE,
    RUN_CONTROL_STATES,
    RUN_EVENT_LOG_ARTIFACT_PATH,
    RUN_EVENT_LOG_SCHEMA_VERSION,
    RUN_IDENTIFIER,
    RUN_STATE_MACHINE_SCHEMA_VERSION,
    TERMINAL_RUN_CONTROL_STATES,
    validate_run_event_log,
)
from test_execution_task_spec import (
    TASK_SPEC_ARTIFACT_PATH as TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
    TASK_SPEC_ID as TEST_EXECUTION_TASK_SPEC_ID,
    TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
    validate_test_execution_task_spec,
)
from verifier_result import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as VERIFIER_RESULT_ARTIFACT_ID,
    VERIFIER_RESULT_ARTIFACT_PATH,
    VERIFIER_RESULT_SCHEMA_VERSION,
    validate_verifier_result,
)


RUN_ARTIFACT_SCHEMA_VERSION = "run-artifact-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "RunV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-run-kernel-contract"
RUN_ARTIFACT_PATH = "artifacts/runs/post_mvp_test_execution_run.json"

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_run_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

REQUIRED_VERDICT_FOR_PROMOTION = "passed"
REQUIRED_TERMINAL_RUN_STATE = "completed"
REQUIRED_POLICY_UNLOCKED = True
REQUIRED_RUN_CONTROL_STATE_MACHINE_SCHEMA_VERSION = RUN_STATE_MACHINE_SCHEMA_VERSION

PERMISSION_FLAG_DOMAIN = [
    "externalSideEffectsAllowed",
    "repositoryMutationAllowed",
    "externalCommunicationAllowed",
    "releaseOrDeploymentAllowed",
    "guiOrBrowserOrDesktopCallAllowed",
    "publicAccessAllowed",
]

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
    "human_approval_decision": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

REQUIRED_VERIFIER_FLAGS = [
    "mustValidateSchema",
    "mustValidateTaskSpecBinding",
    "mustValidateCapabilityManifestBinding",
    "mustValidateRunEventLogBinding",
    "mustValidateObservationListBinding",
    "mustValidateEvidenceListBinding",
    "mustValidateVerifierResultBinding",
    "mustValidateDeliveryManifestBinding",
    "mustValidatePolicyManifestBinding",
    "mustValidateApprovalDecisionBinding",
    "mustValidateRunStateMachine",
    "mustValidatePermissionFlags",
    "mustValidatePromotionConditions",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "RunV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype and from the first-workload regression run.json artifact.",
    "RunV1 must bind TestExecutionTaskSpecV1, CapabilityManifestV1, RunEventLogV1, ObservationListV1, EvidenceListV1, VerifierResultV1, DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1, and all five coordination contracts by content hash.",
    "RunV1.runState must equal RunEventLogV1.terminalState; runState transitions observed in RunEventLogV1.events must all live inside allowedRunControlTransitions.",
    "RunV1.startedAt must equal the timestamp of RunEventLogV1.events[0]; RunV1.terminalAt must equal the timestamp of RunEventLogV1.events[-1].",
    "RunV1.eventCount must equal RunEventLogV1.eventCount; RunV1.observationCount must equal ObservationListV1.observationItemCount; RunV1.evidenceCount must equal EvidenceListV1.evidenceItemCount.",
    "RunV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and creator agents may only stage drafts.",
    "RunV1 promotionConditions require verdict=passed, terminal run state=completed and PolicyManifestV1 unlock=true.",
    "RunV1 must not reuse regression-task-spec-v1, regression-result-artifact-v1, or any regression result / email_draft / send_email field, and must not reuse the first-workload regression run.json artifact.",
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
            f"RunV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"RunV1 source artifact does not exist: {relative_path}"
        )
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
                f"RunV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> tuple[
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
    return (
        run_event_log,
        observation_list,
        evidence_list,
        verifier_result,
        policy_manifest,
    )


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "taskSpecRef": relative_path,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecContentHash": _stable_file_hash(full_path),
    }


def _build_capability_manifest_binding(root: Path) -> dict[str, Any]:
    relative_path = CAPABILITY_MANIFEST_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "capabilityManifestRef": relative_path,
        "capabilityManifestSchemaVersion": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "capabilityManifestEnvelopeSchemaVersion": CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "capabilityManifestId": CAPABILITY_MANIFEST_ARTIFACT_ID,
        "capabilityManifestContentHash": _stable_file_hash(full_path),
    }


def _build_run_event_log_binding(
    root: Path, run_event_log: dict[str, Any]
) -> dict[str, Any]:
    relative_path = RUN_EVENT_LOG_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "runEventLogRef": relative_path,
        "runEventLogSchemaVersion": RUN_EVENT_LOG_SCHEMA_VERSION,
        "runEventLogEnvelopeSchemaVersion": RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION,
        "runEventLogId": RUN_EVENT_LOG_ARTIFACT_ID,
        "runEventLogContentHash": _stable_file_hash(full_path),
        "terminalState": run_event_log["terminalState"],
        "eventCount": run_event_log["eventCount"],
    }


def _build_observation_list_binding(
    root: Path, observation_list: dict[str, Any]
) -> dict[str, Any]:
    relative_path = OBSERVATION_LIST_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "observationListRef": relative_path,
        "observationListSchemaVersion": OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION,
        "observationListEnvelopeSchemaVersion": OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION,
        "observationListId": OBSERVATION_LIST_ARTIFACT_ID,
        "observationListContentHash": _stable_file_hash(full_path),
        "observationItemCount": observation_list["observationItemCount"],
    }


def _build_evidence_list_binding(
    root: Path, evidence_list: dict[str, Any]
) -> dict[str, Any]:
    relative_path = EVIDENCE_LIST_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "evidenceListRef": relative_path,
        "evidenceListSchemaVersion": EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION,
        "evidenceListEnvelopeSchemaVersion": EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION,
        "evidenceListId": EVIDENCE_LIST_ARTIFACT_ID,
        "evidenceListContentHash": _stable_file_hash(full_path),
        "evidenceItemCount": evidence_list["evidenceItemCount"],
    }


def _build_verifier_result_binding(
    root: Path, verifier_result: dict[str, Any]
) -> dict[str, Any]:
    relative_path = VERIFIER_RESULT_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "verifierResultRef": relative_path,
        "verifierResultSchemaVersion": VERIFIER_RESULT_SCHEMA_VERSION,
        "verifierResultEnvelopeSchemaVersion": VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION,
        "verifierResultId": VERIFIER_RESULT_ARTIFACT_ID,
        "verifierResultContentHash": _stable_file_hash(full_path),
        "verdict": verifier_result["verdict"],
    }


def _build_delivery_manifest_binding(root: Path) -> dict[str, Any]:
    relative_path = DELIVERY_MANIFEST_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "deliveryManifestRef": relative_path,
        "deliveryManifestSchemaVersion": DELIVERY_MANIFEST_SCHEMA_VERSION,
        "deliveryManifestEnvelopeSchemaVersion": DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "deliveryManifestId": DELIVERY_MANIFEST_ARTIFACT_ID,
        "deliveryManifestContentHash": _stable_file_hash(full_path),
    }


def _build_policy_manifest_binding(
    root: Path, policy_manifest: dict[str, Any]
) -> dict[str, Any]:
    relative_path = POLICY_MANIFEST_ARTIFACT_PATH
    full_path = root / relative_path
    unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    return {
        "policyManifestRef": relative_path,
        "policyManifestSchemaVersion": POLICY_MANIFEST_SCHEMA_VERSION,
        "policyManifestEnvelopeSchemaVersion": POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "policyManifestId": POLICY_MANIFEST_ARTIFACT_ID,
        "policyManifestContentHash": _stable_file_hash(full_path),
        "unlocked": unlocked,
    }


def _build_approval_decision_binding(
    root: Path, approval_decision: dict[str, Any]
) -> dict[str, Any]:
    relative_path = HUMAN_APPROVAL_DECISION_ARTIFACT_PATH
    full_path = root / relative_path
    decision_block = approval_decision.get("decision", {})
    return {
        "approvalDecisionRef": relative_path,
        "approvalDecisionSchemaVersion": HUMAN_APPROVAL_DECISION_SCHEMA_VERSION,
        "approvalDecisionId": approval_decision["id"],
        "approvalDecisionContentHash": _stable_file_hash(full_path),
        "approvalGranted": bool(decision_block.get("approvalGranted", False)),
    }


def _build_run_control_state_machine(run_event_log: dict[str, Any]) -> dict[str, Any]:
    observed_transitions: list[list[str]] = []
    seen_transitions: set[tuple[str, str]] = set()
    previous_state: str | None = None
    for event in run_event_log["events"]:
        current_state = event["runControlStateAfter"]
        if previous_state is None:
            transition = (INITIAL_RUN_CONTROL_STATE, current_state)
        else:
            transition = (previous_state, current_state)
        if transition not in seen_transitions and transition[0] != transition[1]:
            seen_transitions.add(transition)
            observed_transitions.append([transition[0], transition[1]])
        previous_state = current_state
    return {
        "runControlStateMachineSchemaVersion": RUN_STATE_MACHINE_SCHEMA_VERSION,
        "runControlStates": list(RUN_CONTROL_STATES),
        "initialRunControlState": INITIAL_RUN_CONTROL_STATE,
        "terminalRunControlStates": list(TERMINAL_RUN_CONTROL_STATES),
        "allowedRunControlTransitions": [list(pair) for pair in ALLOWED_RUN_CONTROL_TRANSITIONS],
        "observedRunControlTransitions": observed_transitions,
    }


def _build_promotion_conditions(
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> dict[str, Any]:
    verdict = verifier_result["verdict"]
    terminal_state = run_event_log["terminalState"]
    unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    promoted = (
        verdict == REQUIRED_VERDICT_FOR_PROMOTION
        and terminal_state == REQUIRED_TERMINAL_RUN_STATE
        and unlocked is True
    )
    return {
        "requiredVerdict": REQUIRED_VERDICT_FOR_PROMOTION,
        "currentVerdict": verdict,
        "verdictOwner": VERIFIER_VERDICT_OWNER,
        "requiredTerminalRunState": REQUIRED_TERMINAL_RUN_STATE,
        "currentTerminalRunState": terminal_state,
        "requiredPolicyUnlocked": REQUIRED_POLICY_UNLOCKED,
        "currentPolicyUnlocked": unlocked,
        "promoted": promoted,
    }


def build_run_artifact(root: Path) -> dict[str, Any]:
    (
        run_event_log,
        observation_list,
        evidence_list,
        verifier_result,
        policy_manifest,
    ) = _validate_referenced_artifacts(root)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)

    events = run_event_log["events"]
    if not events:
        raise ValueError("RunV1 cannot be built from an empty RunEventLogV1.events")
    started_at = events[0]["timestampMs"]
    terminal_at = events[-1]["timestampMs"]
    payload: dict[str, Any] = {
        "schemaVersion": RUN_ARTIFACT_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "runId": RUN_IDENTIFIER,
        "runState": run_event_log["terminalState"],
        "startedAt": started_at,
        "terminalAt": terminal_at,
        "eventCount": run_event_log["eventCount"],
        "observationCount": observation_list["observationItemCount"],
        "evidenceCount": evidence_list["evidenceItemCount"],
        "verdictDomain": list(VERDICT_DOMAIN),
        "permissionFlagDomain": list(PERMISSION_FLAG_DOMAIN),
        "permissionFlags": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
        "runControlStateMachine": _build_run_control_state_machine(run_event_log),
        "taskSpecBinding": _build_task_spec_binding(root),
        "capabilityManifestBinding": _build_capability_manifest_binding(root),
        "runEventLogBinding": _build_run_event_log_binding(root, run_event_log),
        "observationListBinding": _build_observation_list_binding(root, observation_list),
        "evidenceListBinding": _build_evidence_list_binding(root, evidence_list),
        "verifierResultBinding": _build_verifier_result_binding(root, verifier_result),
        "deliveryManifestBinding": _build_delivery_manifest_binding(root),
        "policyManifestBinding": _build_policy_manifest_binding(root, policy_manifest),
        "approvalDecisionBinding": _build_approval_decision_binding(root, approval_decision),
        "promotionConditions": _build_promotion_conditions(
            verifier_result, run_event_log, policy_manifest
        ),
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateTaskSpecBinding": True,
            "mustValidateCapabilityManifestBinding": True,
            "mustValidateRunEventLogBinding": True,
            "mustValidateObservationListBinding": True,
            "mustValidateEvidenceListBinding": True,
            "mustValidateVerifierResultBinding": True,
            "mustValidateDeliveryManifestBinding": True,
            "mustValidatePolicyManifestBinding": True,
            "mustValidateApprovalDecisionBinding": True,
            "mustValidateRunStateMachine": True,
            "mustValidatePermissionFlags": True,
            "mustValidatePromotionConditions": True,
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERDICT_DOMAIN),
            "creatorMustNotOwnVerdict": True,
        },
        "regressionWorkloadIsolation": {
            "reusesRegressionRunArtifact": False,
            "reusesRegressionResultArtifact": False,
            "reusesRegressionEventsArtifact": False,
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
    validate_run_artifact(payload, root)
    return payload


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "RunV1 taskSpecBinding",
        binding,
        [
            "taskSpecRef",
            "taskSpecSchemaVersion",
            "taskSpecEnvelopeSchemaVersion",
            "taskSpecId",
            "taskSpecContentHash",
        ],
    )
    if binding["taskSpecRef"] != TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 taskSpecBinding.taskSpecRef must equal {TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 taskSpecBinding.taskSpecSchemaVersion must equal {TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; "
            "regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal {TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"RunV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if binding["taskSpecContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "RunV1 capabilityManifestBinding",
        binding,
        [
            "capabilityManifestRef",
            "capabilityManifestSchemaVersion",
            "capabilityManifestEnvelopeSchemaVersion",
            "capabilityManifestId",
            "capabilityManifestContentHash",
        ],
    )
    if binding["capabilityManifestRef"] != CAPABILITY_MANIFEST_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 capabilityManifestBinding.capabilityManifestRef must equal {CAPABILITY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal {CAPABILITY_MANIFEST_SCHEMA_VERSION}; "
            "regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal {CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"RunV1 capabilityManifestBinding.capabilityManifestId must equal {CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["capabilityManifestRef"]
    if binding["capabilityManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 capabilityManifestBinding.capabilityManifestContentHash must match the on-disk capability manifest"
        )


def _validate_run_event_log_binding(
    binding: dict[str, Any], root: Path, run_event_log: dict[str, Any]
) -> None:
    _require_fields(
        "RunV1 runEventLogBinding",
        binding,
        [
            "runEventLogRef",
            "runEventLogSchemaVersion",
            "runEventLogEnvelopeSchemaVersion",
            "runEventLogId",
            "runEventLogContentHash",
            "terminalState",
            "eventCount",
        ],
    )
    if binding["runEventLogRef"] != RUN_EVENT_LOG_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 runEventLogBinding.runEventLogRef must equal {RUN_EVENT_LOG_ARTIFACT_PATH}"
        )
    if binding["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 runEventLogBinding.runEventLogSchemaVersion must equal {RUN_EVENT_LOG_SCHEMA_VERSION}; "
            "regression events.jsonl reuse is forbidden"
        )
    if binding["runEventLogEnvelopeSchemaVersion"] != RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 runEventLogBinding.runEventLogEnvelopeSchemaVersion must equal {RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runEventLogId"] != RUN_EVENT_LOG_ARTIFACT_ID:
        raise ValueError(
            f"RunV1 runEventLogBinding.runEventLogId must equal {RUN_EVENT_LOG_ARTIFACT_ID}"
        )
    full_path = root / binding["runEventLogRef"]
    if binding["runEventLogContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 runEventLogBinding.runEventLogContentHash must match the on-disk run event log"
        )
    if binding["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "RunV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )
    if binding["eventCount"] != run_event_log["eventCount"]:
        raise ValueError(
            "RunV1 runEventLogBinding.eventCount must equal RunEventLogV1.eventCount"
        )


def _validate_observation_list_binding(
    binding: dict[str, Any], root: Path, observation_list: dict[str, Any]
) -> None:
    _require_fields(
        "RunV1 observationListBinding",
        binding,
        [
            "observationListRef",
            "observationListSchemaVersion",
            "observationListEnvelopeSchemaVersion",
            "observationListId",
            "observationListContentHash",
            "observationItemCount",
        ],
    )
    if binding["observationListRef"] != OBSERVATION_LIST_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 observationListBinding.observationListRef must equal {OBSERVATION_LIST_ARTIFACT_PATH}"
        )
    if binding["observationListSchemaVersion"] != OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 observationListBinding.observationListSchemaVersion must equal {OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression observation reuse is forbidden"
        )
    if binding["observationListEnvelopeSchemaVersion"] != OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 observationListBinding.observationListEnvelopeSchemaVersion must equal {OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["observationListId"] != OBSERVATION_LIST_ARTIFACT_ID:
        raise ValueError(
            f"RunV1 observationListBinding.observationListId must equal {OBSERVATION_LIST_ARTIFACT_ID}"
        )
    full_path = root / binding["observationListRef"]
    if binding["observationListContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 observationListBinding.observationListContentHash must match the on-disk observation list"
        )
    if binding["observationItemCount"] != observation_list["observationItemCount"]:
        raise ValueError(
            "RunV1 observationListBinding.observationItemCount must equal ObservationListV1.observationItemCount"
        )


def _validate_evidence_list_binding(
    binding: dict[str, Any], root: Path, evidence_list: dict[str, Any]
) -> None:
    _require_fields(
        "RunV1 evidenceListBinding",
        binding,
        [
            "evidenceListRef",
            "evidenceListSchemaVersion",
            "evidenceListEnvelopeSchemaVersion",
            "evidenceListId",
            "evidenceListContentHash",
            "evidenceItemCount",
        ],
    )
    if binding["evidenceListRef"] != EVIDENCE_LIST_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 evidenceListBinding.evidenceListRef must equal {EVIDENCE_LIST_ARTIFACT_PATH}"
        )
    if binding["evidenceListSchemaVersion"] != EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 evidenceListBinding.evidenceListSchemaVersion must equal {EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression evidence-list-v1 reuse is forbidden"
        )
    if binding["evidenceListEnvelopeSchemaVersion"] != EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 evidenceListBinding.evidenceListEnvelopeSchemaVersion must equal {EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["evidenceListId"] != EVIDENCE_LIST_ARTIFACT_ID:
        raise ValueError(
            f"RunV1 evidenceListBinding.evidenceListId must equal {EVIDENCE_LIST_ARTIFACT_ID}"
        )
    full_path = root / binding["evidenceListRef"]
    if binding["evidenceListContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 evidenceListBinding.evidenceListContentHash must match the on-disk evidence list artifact"
        )
    if binding["evidenceItemCount"] != evidence_list["evidenceItemCount"]:
        raise ValueError(
            "RunV1 evidenceListBinding.evidenceItemCount must equal EvidenceListV1.evidenceItemCount"
        )


def _validate_verifier_result_binding(
    binding: dict[str, Any], root: Path, verifier_result: dict[str, Any]
) -> None:
    _require_fields(
        "RunV1 verifierResultBinding",
        binding,
        [
            "verifierResultRef",
            "verifierResultSchemaVersion",
            "verifierResultEnvelopeSchemaVersion",
            "verifierResultId",
            "verifierResultContentHash",
            "verdict",
        ],
    )
    if binding["verifierResultRef"] != VERIFIER_RESULT_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 verifierResultBinding.verifierResultRef must equal {VERIFIER_RESULT_ARTIFACT_PATH}"
        )
    if binding["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 verifierResultBinding.verifierResultSchemaVersion must equal {VERIFIER_RESULT_SCHEMA_VERSION}; "
            "regression result artifact reuse is forbidden"
        )
    if binding["verifierResultEnvelopeSchemaVersion"] != VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 verifierResultBinding.verifierResultEnvelopeSchemaVersion must equal {VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["verifierResultId"] != VERIFIER_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"RunV1 verifierResultBinding.verifierResultId must equal {VERIFIER_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["verifierResultRef"]
    if binding["verifierResultContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 verifierResultBinding.verifierResultContentHash must match the on-disk verifier result"
        )
    if binding["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"RunV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}; got {binding['verdict']}"
        )
    if binding["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "RunV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )


def _validate_delivery_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "RunV1 deliveryManifestBinding",
        binding,
        [
            "deliveryManifestRef",
            "deliveryManifestSchemaVersion",
            "deliveryManifestEnvelopeSchemaVersion",
            "deliveryManifestId",
            "deliveryManifestContentHash",
        ],
    )
    if binding["deliveryManifestRef"] != DELIVERY_MANIFEST_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 deliveryManifestBinding.deliveryManifestRef must equal {DELIVERY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["deliveryManifestSchemaVersion"] != DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 deliveryManifestBinding.deliveryManifestSchemaVersion must equal {DELIVERY_MANIFEST_SCHEMA_VERSION}; "
            "multi-agent-delivery-manifest reuse is forbidden"
        )
    if binding["deliveryManifestEnvelopeSchemaVersion"] != DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 deliveryManifestBinding.deliveryManifestEnvelopeSchemaVersion must equal {DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["deliveryManifestId"] != DELIVERY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"RunV1 deliveryManifestBinding.deliveryManifestId must equal {DELIVERY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["deliveryManifestRef"]
    if binding["deliveryManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 deliveryManifestBinding.deliveryManifestContentHash must match the on-disk delivery manifest"
        )


def _validate_policy_manifest_binding(
    binding: dict[str, Any], root: Path, policy_manifest: dict[str, Any]
) -> None:
    _require_fields(
        "RunV1 policyManifestBinding",
        binding,
        [
            "policyManifestRef",
            "policyManifestSchemaVersion",
            "policyManifestEnvelopeSchemaVersion",
            "policyManifestId",
            "policyManifestContentHash",
            "unlocked",
        ],
    )
    if binding["policyManifestRef"] != POLICY_MANIFEST_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 policyManifestBinding.policyManifestRef must equal {POLICY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["policyManifestSchemaVersion"] != POLICY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 policyManifestBinding.policyManifestSchemaVersion must equal {POLICY_MANIFEST_SCHEMA_VERSION}; "
            "regression / adapter policy reuse is forbidden"
        )
    if binding["policyManifestEnvelopeSchemaVersion"] != POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 policyManifestBinding.policyManifestEnvelopeSchemaVersion must equal {POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["policyManifestId"] != POLICY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"RunV1 policyManifestBinding.policyManifestId must equal {POLICY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["policyManifestRef"]
    if binding["policyManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 policyManifestBinding.policyManifestContentHash must match the on-disk policy manifest"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if binding["unlocked"] is not expected_unlocked:
        raise ValueError(
            "RunV1 policyManifestBinding.unlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )


def _validate_approval_decision_binding(
    binding: dict[str, Any], root: Path, approval_decision: dict[str, Any]
) -> None:
    _require_fields(
        "RunV1 approvalDecisionBinding",
        binding,
        [
            "approvalDecisionRef",
            "approvalDecisionSchemaVersion",
            "approvalDecisionId",
            "approvalDecisionContentHash",
            "approvalGranted",
        ],
    )
    if binding["approvalDecisionRef"] != HUMAN_APPROVAL_DECISION_ARTIFACT_PATH:
        raise ValueError(
            f"RunV1 approvalDecisionBinding.approvalDecisionRef must equal {HUMAN_APPROVAL_DECISION_ARTIFACT_PATH}"
        )
    if binding["approvalDecisionSchemaVersion"] != HUMAN_APPROVAL_DECISION_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 approvalDecisionBinding.approvalDecisionSchemaVersion must equal {HUMAN_APPROVAL_DECISION_SCHEMA_VERSION}"
        )
    if binding["approvalDecisionId"] != approval_decision["id"]:
        raise ValueError(
            "RunV1 approvalDecisionBinding.approvalDecisionId must equal HumanApprovalDecisionV1.id"
        )
    full_path = root / binding["approvalDecisionRef"]
    if binding["approvalDecisionContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "RunV1 approvalDecisionBinding.approvalDecisionContentHash must match the on-disk approval decision"
        )
    expected_granted = bool(approval_decision.get("decision", {}).get("approvalGranted", False))
    if binding["approvalGranted"] is not expected_granted:
        raise ValueError(
            "RunV1 approvalDecisionBinding.approvalGranted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )


def _validate_run_control_state_machine(
    machine: dict[str, Any], run_event_log: dict[str, Any]
) -> None:
    _require_fields(
        "RunV1 runControlStateMachine",
        machine,
        [
            "runControlStateMachineSchemaVersion",
            "runControlStates",
            "initialRunControlState",
            "terminalRunControlStates",
            "allowedRunControlTransitions",
            "observedRunControlTransitions",
        ],
    )
    if machine["runControlStateMachineSchemaVersion"] != RUN_STATE_MACHINE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 runControlStateMachine.runControlStateMachineSchemaVersion must equal {RUN_STATE_MACHINE_SCHEMA_VERSION}"
        )
    if machine["runControlStates"] != list(RUN_CONTROL_STATES):
        raise ValueError(
            f"RunV1 runControlStateMachine.runControlStates must equal {RUN_CONTROL_STATES}"
        )
    if machine["initialRunControlState"] != INITIAL_RUN_CONTROL_STATE:
        raise ValueError(
            f"RunV1 runControlStateMachine.initialRunControlState must equal {INITIAL_RUN_CONTROL_STATE}"
        )
    if machine["terminalRunControlStates"] != list(TERMINAL_RUN_CONTROL_STATES):
        raise ValueError(
            f"RunV1 runControlStateMachine.terminalRunControlStates must equal {TERMINAL_RUN_CONTROL_STATES}"
        )
    expected_allowed = [list(pair) for pair in ALLOWED_RUN_CONTROL_TRANSITIONS]
    if machine["allowedRunControlTransitions"] != expected_allowed:
        raise ValueError(
            f"RunV1 runControlStateMachine.allowedRunControlTransitions must equal {expected_allowed}"
        )
    allowed_set = {tuple(pair) for pair in ALLOWED_RUN_CONTROL_TRANSITIONS}
    expected_observed: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    previous_state: str | None = None
    for event in run_event_log["events"]:
        current_state = event["runControlStateAfter"]
        if previous_state is None:
            transition = (INITIAL_RUN_CONTROL_STATE, current_state)
        else:
            transition = (previous_state, current_state)
        if transition not in seen and transition[0] != transition[1]:
            seen.add(transition)
            expected_observed.append([transition[0], transition[1]])
        previous_state = current_state
    if machine["observedRunControlTransitions"] != expected_observed:
        raise ValueError(
            "RunV1 runControlStateMachine.observedRunControlTransitions must enumerate distinct (previous, current) "
            "state transitions inferred from RunEventLogV1.events in order"
        )
    for transition in expected_observed:
        pair = (transition[0], transition[1])
        if pair not in allowed_set:
            raise ValueError(
                f"RunV1 runControlStateMachine observed transition {pair} is not in allowedRunControlTransitions"
            )


def _validate_promotion_conditions(
    promotion: dict[str, Any],
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> None:
    _require_fields(
        "RunV1 promotionConditions",
        promotion,
        [
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
    if promotion["requiredVerdict"] != REQUIRED_VERDICT_FOR_PROMOTION:
        raise ValueError(
            f"RunV1 promotionConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_PROMOTION}"
        )
    if promotion["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "RunV1 promotionConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if promotion["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"RunV1 promotionConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if promotion["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"RunV1 promotionConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if promotion["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "RunV1 promotionConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if promotion["requiredPolicyUnlocked"] is not REQUIRED_POLICY_UNLOCKED:
        raise ValueError(
            "RunV1 promotionConditions.requiredPolicyUnlocked must be true"
        )
    if promotion["currentPolicyUnlocked"] is not expected_unlocked:
        raise ValueError(
            "RunV1 promotionConditions.currentPolicyUnlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_promoted = (
        promotion["currentVerdict"] == REQUIRED_VERDICT_FOR_PROMOTION
        and promotion["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and promotion["currentPolicyUnlocked"] is True
    )
    if promotion["promoted"] is not expected_promoted:
        raise ValueError(
            "RunV1 promotionConditions.promoted must be true only when verdict, run terminal state and policy unlock all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("RunV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("RunV1 sourceArtifacts entries must be objects")
        _require_fields(
            "RunV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"RunV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"RunV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"RunV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"RunV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"RunV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"RunV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_run_artifact(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "RunV1",
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
            "runId",
            "runState",
            "startedAt",
            "terminalAt",
            "eventCount",
            "observationCount",
            "evidenceCount",
            "verdictDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "runControlStateMachine",
            "taskSpecBinding",
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
    if manifest["schemaVersion"] != RUN_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 schemaVersion must be {RUN_ARTIFACT_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"RunV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"RunV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"RunV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"RunV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"RunV1 workloadType must be {WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"RunV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"RunV1 creatorAgent must be {CREATOR_AGENT}")
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"RunV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; creator must not own the verdict"
        )
    if manifest["runId"] != RUN_IDENTIFIER:
        raise ValueError(
            f"RunV1 runId must equal {RUN_IDENTIFIER}; reuse of regression run identifiers is forbidden"
        )

    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(f"RunV1 verdictDomain must equal {VERDICT_DOMAIN}")
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"RunV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )
    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"RunV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(
                f"RunV1 permissionFlags.{flag} must be false"
            )

    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    observation_list = _load_json(root / OBSERVATION_LIST_ARTIFACT_PATH)
    evidence_list = _load_json(root / EVIDENCE_LIST_ARTIFACT_PATH)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)

    events = run_event_log["events"]
    if not events:
        raise ValueError("RunV1 cannot validate against an empty RunEventLogV1.events")
    if manifest["runState"] != run_event_log["terminalState"]:
        raise ValueError(
            "RunV1 runState must equal RunEventLogV1.terminalState"
        )
    if manifest["startedAt"] != events[0]["timestampMs"]:
        raise ValueError(
            "RunV1 startedAt must equal RunEventLogV1.events[0].timestampMs"
        )
    if manifest["terminalAt"] != events[-1]["timestampMs"]:
        raise ValueError(
            "RunV1 terminalAt must equal RunEventLogV1.events[-1].timestampMs"
        )
    if manifest["startedAt"] > manifest["terminalAt"]:
        raise ValueError("RunV1 startedAt must not be greater than terminalAt")
    if manifest["eventCount"] != run_event_log["eventCount"]:
        raise ValueError(
            "RunV1 eventCount must equal RunEventLogV1.eventCount"
        )
    if manifest["observationCount"] != observation_list["observationItemCount"]:
        raise ValueError(
            "RunV1 observationCount must equal ObservationListV1.observationItemCount"
        )
    if manifest["evidenceCount"] != evidence_list["evidenceItemCount"]:
        raise ValueError(
            "RunV1 evidenceCount must equal EvidenceListV1.evidenceItemCount"
        )
    if manifest["observationCount"] != manifest["eventCount"]:
        raise ValueError(
            "RunV1 observationCount must equal eventCount; ObservationListV1 must mirror RunEventLogV1.events"
        )

    _validate_run_control_state_machine(manifest["runControlStateMachine"], run_event_log)
    _validate_task_spec_binding(manifest["taskSpecBinding"], root)
    _validate_capability_manifest_binding(manifest["capabilityManifestBinding"], root)
    _validate_run_event_log_binding(manifest["runEventLogBinding"], root, run_event_log)
    _validate_observation_list_binding(
        manifest["observationListBinding"], root, observation_list
    )
    _validate_evidence_list_binding(
        manifest["evidenceListBinding"], root, evidence_list
    )
    _validate_verifier_result_binding(
        manifest["verifierResultBinding"], root, verifier_result
    )
    _validate_delivery_manifest_binding(manifest["deliveryManifestBinding"], root)
    _validate_policy_manifest_binding(
        manifest["policyManifestBinding"], root, policy_manifest
    )
    _validate_approval_decision_binding(
        manifest["approvalDecisionBinding"], root, approval_decision
    )
    _validate_promotion_conditions(
        manifest["promotionConditions"], verifier_result, run_event_log, policy_manifest
    )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "RunV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"RunV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"RunV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"RunV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "RunV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionRunArtifact",
            "reusesRegressionResultArtifact",
            "reusesRegressionEventsArtifact",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionRunArtifact"] is not False:
        raise ValueError(
            "RunV1 must not reuse the first-workload regression run.json artifact"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "RunV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesRegressionEventsArtifact"] is not False:
        raise ValueError(
            "RunV1 must not reuse the first-workload regression events.jsonl artifact"
        )
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError(
            "RunV1 must not reuse the send_email capability"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"RunV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"RunV1 must not embed regression/email field {term} outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"RunV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            f"RunV1 coordinationBinding must include {sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"RunV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 7:
        raise ValueError(
            "RunV1 invariants must declare at least seven workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run-artifact")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_run_artifact(root)
        _write_json(args.out, manifest)
        print(f"Wrote RunV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_run_artifact(manifest, root)
        print(f"Validated RunV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

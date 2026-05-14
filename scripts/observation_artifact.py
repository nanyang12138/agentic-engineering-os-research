"""ObservationListV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``ObservationListV1`` ArtifactV1
subtype.  It captures the canonical OS-kernel ``Observation`` primitive for any
engineering workload:

- a workload-independent ``ObservationItemV1`` envelope describing every
  observation by stable ``observationId``, workload-independent
  ``observationKind``, ``capturedAt`` timestamp, ``capabilityRef`` (or the
  run-kernel sentinel), ``runEventLogRef`` (resolving to a specific
  ``RunEventLogV1.events`` entry by ``eventId`` and ``sequence``),
  ``evidenceRefs`` (resolving into ``EvidenceListV1.evidenceItems``),
  ``sourceAgent`` and a deterministic ``payloadHash``;
- a workload-independent ``ObservationListV1`` envelope (an ``ArtifactV1``
  subtype) wrapping an ordered list of ``ObservationItemV1`` instances along
  with bindings to every upstream ``test_execution_failure_triage`` primitive,
  the five Agent Coordination Layer contracts, the policy boundary, the
  promotion conditions, and a verifier-owned verdict expectation;
- cross-validation against ``RunEventLogV1.events`` (every event must map to
  exactly one observation through ``runEventLogRef``) and against
  ``EvidenceListV1.evidenceItems`` (every cited ``evidenceRef`` must resolve
  into the kernel evidence envelope).

The artifact answers four OS-kernel invariants at once:

- ``Observation`` primitive: the manifest declares a workload-independent
  ``observationKindDomain`` (``capability_invocation_record`` /
  ``tool_call_record`` / ``artifact_write_record`` /
  ``verifier_rule_evaluation_record`` / ``run_state_transition_record`` /
  ``redaction_overlay_record``), pins each item to a workload-independent
  ``sourceAgent``, and binds every item to a capability and to a run event.
- ``Artifact`` envelope reuse: the manifest is an ``ArtifactV1`` subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) joining the existing
  ``CapabilityManifestV1`` / ``TestExecutionResultV1`` /
  ``FailureTriageReportV1`` / ``VerifierResultV1`` / ``RunEventLogV1`` /
  ``DeliveryManifestV1`` / ``PolicyManifestV1`` / ``EvidenceListV1`` subtypes.
- ``Verifier`` / ``Policy`` consistency: the manifest pins the
  ``VerifierResultV1`` verdict, ``RunEventLogV1.terminalState`` and
  ``PolicyManifestV1`` unlock as prerequisites for any creator-side
  observation promotion, and declares ``verifier-runtime-v1`` as the verdict
  owner while forcing ``creatorMustNotOwnVerdict=true``.
- ``Coordination`` observation boundary: the manifest binds all five Agent
  Coordination Layer contracts by ref + content hash, so every coordination
  decision over observations is constrained by the same envelope.
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
    CAPABILITY_NAMES,
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
    validate_human_approval_decision,
)
from policy_manifest import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as POLICY_MANIFEST_ARTIFACT_ID,
    POLICY_MANIFEST_ARTIFACT_PATH,
    POLICY_MANIFEST_SCHEMA_VERSION,
    validate_policy_manifest,
)
from run_event_log import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as RUN_EVENT_LOG_ARTIFACT_ID,
    RUN_EVENT_LOG_ARTIFACT_PATH,
    RUN_EVENT_LOG_SCHEMA_VERSION,
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


OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION = "observation-list-artifact-v1"
OBSERVATION_ITEM_SCHEMA_VERSION = "observation-item-v1"
OBSERVATION_RUN_EVENT_REF_SCHEMA_VERSION = "observation-run-event-ref-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "ObservationListV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-observation-list-kernel-contract"
OBSERVATION_LIST_ARTIFACT_PATH = (
    "artifacts/observations/post_mvp_test_execution_observation_list.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_observation_list_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

REQUIRED_VERDICT_FOR_PROMOTION = "passed"
REQUIRED_TERMINAL_RUN_STATE = "completed"
REQUIRED_POLICY_UNLOCKED = True

OBSERVATION_REDACTION_POLICY_REF = (
    "artifacts/computer_runtime/phase7_observation_redaction_policy.json"
)
OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION = "observation-redaction-policy-v1"

RUN_KERNEL_CAPABILITY_SENTINEL = "__run_kernel__"

OBSERVATION_KIND_DOMAIN = [
    "capability_invocation_record",
    "tool_call_record",
    "artifact_write_record",
    "verifier_rule_evaluation_record",
    "run_state_transition_record",
    "redaction_overlay_record",
]

SOURCE_AGENT_DOMAIN = [
    "run_kernel",
    "creator_agent",
    "verifier-runtime-v1",
]

PERMISSION_FLAG_DOMAIN = [
    "externalSideEffectsAllowed",
    "repositoryMutationAllowed",
    "externalCommunicationAllowed",
    "releaseOrDeploymentAllowed",
    "guiOrBrowserOrDesktopCallAllowed",
    "publicAccessAllowed",
]

# Workload-independent mapping from RunEventLogV1.eventType to
# ObservationItemV1.observationKind.  This declares which observation kind a
# kernel-level run event is promoted into when it is materialized as an
# Observation primitive, and is reused across non-regression workloads.
EVENT_TYPE_TO_OBSERVATION_KIND: dict[str, str] = {
    "run.created": "run_state_transition_record",
    "task_spec.generated": "run_state_transition_record",
    "capability.invoked": "capability_invocation_record",
    "capability.completed": "tool_call_record",
    "artifact.written": "artifact_write_record",
    "verifier.completed": "verifier_rule_evaluation_record",
    "run.completed": "run_state_transition_record",
    "run.failed": "run_state_transition_record",
}

# Capabilities that promote upstream evidence into observations.  Mapping
# capability name -> ordered evidenceIds expected to be cited when the
# capability completes.  Workload-independent: every entry is keyed on a
# capability name from CapabilityManifestV1, never on a regression artifact.
CAPABILITY_TO_EVIDENCE_REFS: dict[str, list[str]] = {
    "collect_test_failure_evidence": [
        "ev-case-001-outcome",
        "ev-case-002-outcome",
        "ev-case-002-trace",
        "ev-case-003-outcome",
    ],
}

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
    "test_execution_verifier_result": VERIFIER_RESULT_ARTIFACT_PATH,
    "test_execution_delivery_manifest": DELIVERY_MANIFEST_ARTIFACT_PATH,
    "test_execution_policy_manifest": POLICY_MANIFEST_ARTIFACT_PATH,
    "test_execution_evidence_list": EVIDENCE_LIST_ARTIFACT_PATH,
    "human_approval_decision": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    "observation_redaction_policy": OBSERVATION_REDACTION_POLICY_REF,
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
    "mustValidateVerifierResultBinding",
    "mustValidateDeliveryManifestBinding",
    "mustValidatePolicyManifestBinding",
    "mustValidateEvidenceListBinding",
    "mustValidatePermissionFlags",
    "mustValidateObservationItems",
    "mustValidateRunEventCoverage",
    "mustValidateEvidenceCoverage",
    "mustValidatePromotionConditions",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "ObservationListV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype.",
    "ObservationListV1 must bind TestExecutionTaskSpecV1, CapabilityManifestV1, RunEventLogV1, VerifierResultV1, DeliveryManifestV1, PolicyManifestV1, EvidenceListV1, HumanApprovalDecisionV1, and all five coordination contracts by content hash.",
    "ObservationListV1 observationKindDomain and sourceAgentDomain are workload-independent; no workload-specific kind or agent may appear in observationItems.",
    "Every ObservationItemV1.runEventLogRef must resolve into a unique RunEventLogV1.events entry by eventId and sequence.",
    "Every ObservationItemV1.evidenceRefs id must resolve into EvidenceListV1.evidenceItems and reference workload-independent kinds only.",
    "Every RunEventLogV1.events entry must be covered by exactly one ObservationItemV1; ObservationListV1 is the canonical materialization of the run event log.",
    "ObservationListV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and creator agents may only stage drafts.",
    "ObservationListV1 promotionConditions require verdict=passed, terminal run state=completed and PolicyManifestV1 unlock=true.",
    "ObservationListV1 must not reuse regression-task-spec-v1, regression-result-artifact-v1, evidence-list-v1, or any regression result / email_draft / send_email field.",
]


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    normalized = canonical.replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
            f"ObservationListV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"ObservationListV1 source artifact does not exist: {relative_path}"
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
                f"ObservationListV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
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
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    validate_verifier_result(verifier_result, root)
    delivery_manifest = _load_json(root / DELIVERY_MANIFEST_ARTIFACT_PATH)
    validate_delivery_manifest(delivery_manifest, root)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    validate_policy_manifest(policy_manifest, root)
    evidence_list = _load_json(root / EVIDENCE_LIST_ARTIFACT_PATH)
    validate_evidence_list_artifact(evidence_list, root)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    validate_human_approval_decision(approval_decision, root)
    return run_event_log, verifier_result, policy_manifest, evidence_list


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


def _build_evidence_list_binding(root: Path) -> dict[str, Any]:
    relative_path = EVIDENCE_LIST_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "evidenceListRef": relative_path,
        "evidenceListSchemaVersion": EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION,
        "evidenceListEnvelopeSchemaVersion": EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION,
        "evidenceListId": EVIDENCE_LIST_ARTIFACT_ID,
        "evidenceListContentHash": _stable_file_hash(full_path),
    }


def _resolve_capability_for_event(event: dict[str, Any]) -> str:
    capability = event.get("sourceCapability")
    if capability == RUN_KERNEL_CAPABILITY_SENTINEL:
        return RUN_KERNEL_CAPABILITY_SENTINEL
    if capability not in CAPABILITY_NAMES:
        raise ValueError(
            f"ObservationListV1 cannot resolve capability for event {event.get('eventId')}; "
            f"capability {capability} is not in the run-kernel sentinel or CapabilityManifestV1 capabilities"
        )
    return capability


def _resolve_evidence_refs(event: dict[str, Any]) -> list[str]:
    if event["eventType"] != "capability.completed":
        return []
    capability = event.get("sourceCapability")
    return list(CAPABILITY_TO_EVIDENCE_REFS.get(capability, []))


def _build_observation_items(
    run_event_log: dict[str, Any], evidence_list: dict[str, Any]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    evidence_ids = {item["evidenceId"] for item in evidence_list.get("evidenceItems", [])}
    for event in run_event_log["events"]:
        event_type = event["eventType"]
        observation_kind = EVENT_TYPE_TO_OBSERVATION_KIND.get(event_type)
        if observation_kind is None:
            raise ValueError(
                f"ObservationListV1 cannot promote event {event['eventId']}: "
                f"unknown eventType {event_type}"
            )
        capability_ref = _resolve_capability_for_event(event)
        evidence_refs = _resolve_evidence_refs(event)
        for evidence_id in evidence_refs:
            if evidence_id not in evidence_ids:
                raise ValueError(
                    f"ObservationListV1 evidence ref {evidence_id} for event "
                    f"{event['eventId']} is not in EvidenceListV1.evidenceItems"
                )
        source_agent = event["sourceAgent"]
        if source_agent not in SOURCE_AGENT_DOMAIN:
            raise ValueError(
                f"ObservationListV1 sourceAgent {source_agent} is not in workload-independent domain"
            )
        sequence = event["sequence"]
        observation_id = f"obs-{run_event_log['runIdentifier']}-{sequence:04d}"
        observation_payload = {
            "observationId": observation_id,
            "observationKind": observation_kind,
            "capturedAt": event["timestampMs"],
            "capabilityRef": capability_ref,
            "sourceAgent": source_agent,
            "runEventId": event["eventId"],
            "runEventSequence": sequence,
            "evidenceRefs": list(evidence_refs),
        }
        item = {
            "schemaVersion": OBSERVATION_ITEM_SCHEMA_VERSION,
            "observationId": observation_id,
            "observationKind": observation_kind,
            "capturedAt": event["timestampMs"],
            "capabilityRef": capability_ref,
            "sourceAgent": source_agent,
            "runEventLogRef": {
                "schemaVersion": OBSERVATION_RUN_EVENT_REF_SCHEMA_VERSION,
                "runEventLogPath": RUN_EVENT_LOG_ARTIFACT_PATH,
                "runEventId": event["eventId"],
                "runEventSequence": sequence,
                "runEventType": event_type,
                "runEventStatus": event["status"],
            },
            "evidenceRefs": list(evidence_refs),
            "redactionPolicyRef": OBSERVATION_REDACTION_POLICY_REF,
            "redactionPolicySchemaVersion": OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION,
            "redactionApplied": False,
            "payloadHash": _payload_hash(observation_payload),
        }
        items.append(item)
    return items


def _build_run_event_coverage(
    items: list[dict[str, Any]], run_event_log: dict[str, Any]
) -> dict[str, Any]:
    item_event_ids = sorted(item["runEventLogRef"]["runEventId"] for item in items)
    log_event_ids = sorted(event["eventId"] for event in run_event_log["events"])
    return {
        "runEventLogEventIds": log_event_ids,
        "observationEventIds": item_event_ids,
        "missingObservationsForEventIds": sorted(set(log_event_ids) - set(item_event_ids)),
        "extraObservationEventIds": sorted(set(item_event_ids) - set(log_event_ids)),
        "everyEventCovered": set(item_event_ids) == set(log_event_ids),
    }


def _build_evidence_coverage(
    items: list[dict[str, Any]], evidence_list: dict[str, Any]
) -> dict[str, Any]:
    cited: set[str] = set()
    for item in items:
        for evidence_id in item.get("evidenceRefs", []):
            cited.add(evidence_id)
    evidence_ids = {entry["evidenceId"] for entry in evidence_list.get("evidenceItems", [])}
    return {
        "observationEvidenceIds": sorted(cited),
        "resolvedIntoEvidenceList": sorted(cited & evidence_ids),
        "unresolvedObservationEvidenceIds": sorted(cited - evidence_ids),
        "everyEvidenceRefResolved": cited.issubset(evidence_ids),
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


def build_observation_list_artifact(root: Path) -> dict[str, Any]:
    (
        run_event_log,
        verifier_result,
        policy_manifest,
        evidence_list,
    ) = _validate_referenced_artifacts(root)
    observation_items = _build_observation_items(run_event_log, evidence_list)
    run_event_coverage = _build_run_event_coverage(observation_items, run_event_log)
    if not run_event_coverage["everyEventCovered"]:
        raise ValueError(
            "ObservationListV1 must cover every RunEventLogV1.events entry; "
            f"missing: {run_event_coverage['missingObservationsForEventIds']}; "
            f"extra: {run_event_coverage['extraObservationEventIds']}"
        )
    evidence_coverage = _build_evidence_coverage(observation_items, evidence_list)
    if not evidence_coverage["everyEvidenceRefResolved"]:
        raise ValueError(
            "ObservationListV1 evidenceRefs must resolve into EvidenceListV1.evidenceItems; "
            f"unresolved: {evidence_coverage['unresolvedObservationEvidenceIds']}"
        )
    payload: dict[str, Any] = {
        "schemaVersion": OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "observationItemSchemaVersion": OBSERVATION_ITEM_SCHEMA_VERSION,
        "observationRunEventRefSchemaVersion": OBSERVATION_RUN_EVENT_REF_SCHEMA_VERSION,
        "verdictDomain": list(VERDICT_DOMAIN),
        "observationKindDomain": list(OBSERVATION_KIND_DOMAIN),
        "sourceAgentDomain": list(SOURCE_AGENT_DOMAIN),
        "permissionFlagDomain": list(PERMISSION_FLAG_DOMAIN),
        "permissionFlags": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
        "runKernelCapabilitySentinel": RUN_KERNEL_CAPABILITY_SENTINEL,
        "observationItems": observation_items,
        "observationItemCount": len(observation_items),
        "taskSpecBinding": _build_task_spec_binding(root),
        "capabilityManifestBinding": _build_capability_manifest_binding(root),
        "runEventLogBinding": _build_run_event_log_binding(root, run_event_log),
        "verifierResultBinding": _build_verifier_result_binding(root, verifier_result),
        "deliveryManifestBinding": _build_delivery_manifest_binding(root),
        "policyManifestBinding": _build_policy_manifest_binding(root, policy_manifest),
        "evidenceListBinding": _build_evidence_list_binding(root),
        "runEventCoverage": run_event_coverage,
        "evidenceCoverage": evidence_coverage,
        "promotionConditions": _build_promotion_conditions(
            verifier_result, run_event_log, policy_manifest
        ),
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateTaskSpecBinding": True,
            "mustValidateCapabilityManifestBinding": True,
            "mustValidateRunEventLogBinding": True,
            "mustValidateVerifierResultBinding": True,
            "mustValidateDeliveryManifestBinding": True,
            "mustValidatePolicyManifestBinding": True,
            "mustValidateEvidenceListBinding": True,
            "mustValidatePermissionFlags": True,
            "mustValidateObservationItems": True,
            "mustValidateRunEventCoverage": True,
            "mustValidateEvidenceCoverage": True,
            "mustValidatePromotionConditions": True,
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERDICT_DOMAIN),
            "creatorMustNotOwnVerdict": True,
        },
        "regressionWorkloadIsolation": {
            "reusesRegressionRunEventArtifact": False,
            "reusesRegressionResultArtifact": False,
            "reusesRegressionEvidenceList": False,
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
    validate_observation_list_artifact(payload, root)
    return payload


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ObservationListV1 taskSpecBinding",
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
            f"ObservationListV1 taskSpecBinding.taskSpecRef must equal {TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 taskSpecBinding.taskSpecSchemaVersion must equal {TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; "
            "regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal {TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"ObservationListV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"ObservationListV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    if binding["taskSpecContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ObservationListV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ObservationListV1 capabilityManifestBinding",
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
            f"ObservationListV1 capabilityManifestBinding.capabilityManifestRef must equal {CAPABILITY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal {CAPABILITY_MANIFEST_SCHEMA_VERSION}; "
            "regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal {CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"ObservationListV1 capabilityManifestBinding.capabilityManifestId must equal {CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["capabilityManifestRef"]
    if binding["capabilityManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ObservationListV1 capabilityManifestBinding.capabilityManifestContentHash must match the on-disk capability manifest"
        )


def _validate_run_event_log_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ObservationListV1 runEventLogBinding",
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
            f"ObservationListV1 runEventLogBinding.runEventLogRef must equal {RUN_EVENT_LOG_ARTIFACT_PATH}"
        )
    if binding["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 runEventLogBinding.runEventLogSchemaVersion must equal {RUN_EVENT_LOG_SCHEMA_VERSION}; "
            "regression events.jsonl reuse is forbidden"
        )
    if binding["runEventLogEnvelopeSchemaVersion"] != RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 runEventLogBinding.runEventLogEnvelopeSchemaVersion must equal {RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION}"
        )
    full_path = root / binding["runEventLogRef"]
    if binding["runEventLogContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ObservationListV1 runEventLogBinding.runEventLogContentHash must match the on-disk run event log"
        )
    run_event_log = _load_json(full_path)
    if binding["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "ObservationListV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )
    if binding["eventCount"] != run_event_log["eventCount"]:
        raise ValueError(
            "ObservationListV1 runEventLogBinding.eventCount must equal RunEventLogV1.eventCount"
        )


def _validate_verifier_result_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ObservationListV1 verifierResultBinding",
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
            f"ObservationListV1 verifierResultBinding.verifierResultRef must equal {VERIFIER_RESULT_ARTIFACT_PATH}"
        )
    if binding["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 verifierResultBinding.verifierResultSchemaVersion must equal {VERIFIER_RESULT_SCHEMA_VERSION}; "
            "regression result artifact reuse is forbidden"
        )
    if binding["verifierResultEnvelopeSchemaVersion"] != VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 verifierResultBinding.verifierResultEnvelopeSchemaVersion must equal {VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["verifierResultId"] != VERIFIER_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"ObservationListV1 verifierResultBinding.verifierResultId must equal {VERIFIER_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["verifierResultRef"]
    if binding["verifierResultContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ObservationListV1 verifierResultBinding.verifierResultContentHash must match the on-disk verifier result"
        )
    if binding["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"ObservationListV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}; got {binding['verdict']}"
        )
    verifier_result = _load_json(full_path)
    if binding["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "ObservationListV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )


def _validate_delivery_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ObservationListV1 deliveryManifestBinding",
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
            f"ObservationListV1 deliveryManifestBinding.deliveryManifestRef must equal {DELIVERY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["deliveryManifestSchemaVersion"] != DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 deliveryManifestBinding.deliveryManifestSchemaVersion must equal {DELIVERY_MANIFEST_SCHEMA_VERSION}; "
            "multi-agent-delivery-manifest reuse is forbidden"
        )
    if binding["deliveryManifestEnvelopeSchemaVersion"] != DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 deliveryManifestBinding.deliveryManifestEnvelopeSchemaVersion must equal {DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["deliveryManifestId"] != DELIVERY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"ObservationListV1 deliveryManifestBinding.deliveryManifestId must equal {DELIVERY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["deliveryManifestRef"]
    if binding["deliveryManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ObservationListV1 deliveryManifestBinding.deliveryManifestContentHash must match the on-disk delivery manifest"
        )


def _validate_policy_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ObservationListV1 policyManifestBinding",
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
            f"ObservationListV1 policyManifestBinding.policyManifestRef must equal {POLICY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["policyManifestSchemaVersion"] != POLICY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 policyManifestBinding.policyManifestSchemaVersion must equal {POLICY_MANIFEST_SCHEMA_VERSION}; "
            "regression / adapter policy reuse is forbidden"
        )
    if binding["policyManifestEnvelopeSchemaVersion"] != POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 policyManifestBinding.policyManifestEnvelopeSchemaVersion must equal {POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["policyManifestId"] != POLICY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"ObservationListV1 policyManifestBinding.policyManifestId must equal {POLICY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["policyManifestRef"]
    if binding["policyManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ObservationListV1 policyManifestBinding.policyManifestContentHash must match the on-disk policy manifest"
        )
    policy_manifest = _load_json(full_path)
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if binding["unlocked"] is not expected_unlocked:
        raise ValueError(
            "ObservationListV1 policyManifestBinding.unlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )


def _validate_evidence_list_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ObservationListV1 evidenceListBinding",
        binding,
        [
            "evidenceListRef",
            "evidenceListSchemaVersion",
            "evidenceListEnvelopeSchemaVersion",
            "evidenceListId",
            "evidenceListContentHash",
        ],
    )
    if binding["evidenceListRef"] != EVIDENCE_LIST_ARTIFACT_PATH:
        raise ValueError(
            f"ObservationListV1 evidenceListBinding.evidenceListRef must equal {EVIDENCE_LIST_ARTIFACT_PATH}"
        )
    if binding["evidenceListSchemaVersion"] != EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 evidenceListBinding.evidenceListSchemaVersion must equal {EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression evidence-list-v1 reuse is forbidden"
        )
    if binding["evidenceListEnvelopeSchemaVersion"] != EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 evidenceListBinding.evidenceListEnvelopeSchemaVersion must equal {EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["evidenceListId"] != EVIDENCE_LIST_ARTIFACT_ID:
        raise ValueError(
            f"ObservationListV1 evidenceListBinding.evidenceListId must equal {EVIDENCE_LIST_ARTIFACT_ID}"
        )
    full_path = root / binding["evidenceListRef"]
    if binding["evidenceListContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ObservationListV1 evidenceListBinding.evidenceListContentHash must match the on-disk evidence list artifact"
        )


def _validate_observation_items(
    items: list[Any],
    root: Path,
    run_event_log: dict[str, Any],
    evidence_list: dict[str, Any],
) -> None:
    if not isinstance(items, list) or not items:
        raise ValueError("ObservationListV1 observationItems must be a non-empty list")
    events_by_id = {event["eventId"]: event for event in run_event_log["events"]}
    evidence_ids = {entry["evidenceId"] for entry in evidence_list.get("evidenceItems", [])}
    seen_observation_ids: set[str] = set()
    seen_event_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("ObservationListV1 observationItems entries must be objects")
        label = f"ObservationListV1 observationItems[{index}]"
        _require_fields(
            label,
            item,
            [
                "schemaVersion",
                "observationId",
                "observationKind",
                "capturedAt",
                "capabilityRef",
                "sourceAgent",
                "runEventLogRef",
                "evidenceRefs",
                "redactionPolicyRef",
                "redactionPolicySchemaVersion",
                "redactionApplied",
                "payloadHash",
            ],
        )
        if item["schemaVersion"] != OBSERVATION_ITEM_SCHEMA_VERSION:
            raise ValueError(
                f"{label}.schemaVersion must be {OBSERVATION_ITEM_SCHEMA_VERSION}"
            )
        if item["observationId"] in seen_observation_ids:
            raise ValueError(
                f"ObservationListV1 duplicate observationItems.observationId: {item['observationId']}"
            )
        seen_observation_ids.add(item["observationId"])
        if item["observationKind"] not in OBSERVATION_KIND_DOMAIN:
            raise ValueError(
                f"{label}.observationKind must be one of {OBSERVATION_KIND_DOMAIN}; got {item['observationKind']}"
            )
        if item["sourceAgent"] not in SOURCE_AGENT_DOMAIN:
            raise ValueError(
                f"{label}.sourceAgent must be one of {SOURCE_AGENT_DOMAIN}; got {item['sourceAgent']}"
            )
        capability_ref = item["capabilityRef"]
        if (
            capability_ref != RUN_KERNEL_CAPABILITY_SENTINEL
            and capability_ref not in CAPABILITY_NAMES
        ):
            raise ValueError(
                f"{label}.capabilityRef must be the run-kernel sentinel or one of {CAPABILITY_NAMES}; got {capability_ref}"
            )
        if item["redactionPolicyRef"] != OBSERVATION_REDACTION_POLICY_REF:
            raise ValueError(
                f"{label}.redactionPolicyRef must equal {OBSERVATION_REDACTION_POLICY_REF}"
            )
        if item["redactionPolicySchemaVersion"] != OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION:
            raise ValueError(
                f"{label}.redactionPolicySchemaVersion must equal {OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION}"
            )
        if item["redactionApplied"] is not False:
            raise ValueError(
                f"{label}.redactionApplied must be false (no redaction is applied at the contract layer)"
            )
        ref = item["runEventLogRef"]
        if not isinstance(ref, dict):
            raise ValueError(f"{label}.runEventLogRef must be an object")
        _require_fields(
            f"{label}.runEventLogRef",
            ref,
            [
                "schemaVersion",
                "runEventLogPath",
                "runEventId",
                "runEventSequence",
                "runEventType",
                "runEventStatus",
            ],
        )
        if ref["schemaVersion"] != OBSERVATION_RUN_EVENT_REF_SCHEMA_VERSION:
            raise ValueError(
                f"{label}.runEventLogRef.schemaVersion must be {OBSERVATION_RUN_EVENT_REF_SCHEMA_VERSION}"
            )
        if ref["runEventLogPath"] != RUN_EVENT_LOG_ARTIFACT_PATH:
            raise ValueError(
                f"{label}.runEventLogRef.runEventLogPath must equal {RUN_EVENT_LOG_ARTIFACT_PATH}"
            )
        run_event = events_by_id.get(ref["runEventId"])
        if run_event is None:
            raise ValueError(
                f"{label}.runEventLogRef.runEventId {ref['runEventId']} is not present in RunEventLogV1.events"
            )
        if ref["runEventId"] in seen_event_ids:
            raise ValueError(
                f"ObservationListV1 duplicate runEventLogRef.runEventId: {ref['runEventId']}"
            )
        seen_event_ids.add(ref["runEventId"])
        if ref["runEventSequence"] != run_event["sequence"]:
            raise ValueError(
                f"{label}.runEventLogRef.runEventSequence must equal RunEventLogV1.events sequence for {ref['runEventId']}"
            )
        if ref["runEventType"] != run_event["eventType"]:
            raise ValueError(
                f"{label}.runEventLogRef.runEventType must equal RunEventLogV1.events eventType for {ref['runEventId']}"
            )
        if ref["runEventStatus"] != run_event["status"]:
            raise ValueError(
                f"{label}.runEventLogRef.runEventStatus must equal RunEventLogV1.events status for {ref['runEventId']}"
            )
        expected_kind = EVENT_TYPE_TO_OBSERVATION_KIND.get(run_event["eventType"])
        if expected_kind is None or item["observationKind"] != expected_kind:
            raise ValueError(
                f"{label}.observationKind for runEventType {run_event['eventType']} must be {expected_kind}; got {item['observationKind']}"
            )
        if item["capturedAt"] != run_event["timestampMs"]:
            raise ValueError(
                f"{label}.capturedAt must equal RunEventLogV1.events timestampMs for {ref['runEventId']}"
            )
        if item["sourceAgent"] != run_event["sourceAgent"]:
            raise ValueError(
                f"{label}.sourceAgent must equal RunEventLogV1.events sourceAgent for {ref['runEventId']}"
            )
        if item["capabilityRef"] != run_event["sourceCapability"]:
            raise ValueError(
                f"{label}.capabilityRef must equal RunEventLogV1.events sourceCapability for {ref['runEventId']}"
            )
        evidence_refs = item["evidenceRefs"]
        if not isinstance(evidence_refs, list):
            raise ValueError(f"{label}.evidenceRefs must be a list")
        for evidence_id in evidence_refs:
            if not isinstance(evidence_id, str):
                raise ValueError(f"{label}.evidenceRefs entries must be strings")
            if evidence_id not in evidence_ids:
                raise ValueError(
                    f"{label}.evidenceRefs id {evidence_id} is not present in EvidenceListV1.evidenceItems"
                )
        expected_evidence_refs = []
        if run_event["eventType"] == "capability.completed":
            expected_evidence_refs = list(
                CAPABILITY_TO_EVIDENCE_REFS.get(run_event["sourceCapability"], [])
            )
        if list(evidence_refs) != expected_evidence_refs:
            raise ValueError(
                f"{label}.evidenceRefs for runEventId {ref['runEventId']} must equal {expected_evidence_refs}; got {list(evidence_refs)}"
            )
        observation_payload = {
            "observationId": item["observationId"],
            "observationKind": item["observationKind"],
            "capturedAt": item["capturedAt"],
            "capabilityRef": item["capabilityRef"],
            "sourceAgent": item["sourceAgent"],
            "runEventId": ref["runEventId"],
            "runEventSequence": ref["runEventSequence"],
            "evidenceRefs": list(evidence_refs),
        }
        expected_payload_hash = _payload_hash(observation_payload)
        if item["payloadHash"] != expected_payload_hash:
            raise ValueError(
                f"{label}.payloadHash must equal sha256 of canonical observation payload for {item['observationId']}"
            )


def _validate_run_event_coverage(
    coverage: dict[str, Any],
    items: list[dict[str, Any]],
    run_event_log: dict[str, Any],
) -> None:
    _require_fields(
        "ObservationListV1 runEventCoverage",
        coverage,
        [
            "runEventLogEventIds",
            "observationEventIds",
            "missingObservationsForEventIds",
            "extraObservationEventIds",
            "everyEventCovered",
        ],
    )
    expected_log_ids = sorted(event["eventId"] for event in run_event_log["events"])
    expected_observation_ids = sorted(item["runEventLogRef"]["runEventId"] for item in items)
    if coverage["runEventLogEventIds"] != expected_log_ids:
        raise ValueError(
            "ObservationListV1 runEventCoverage.runEventLogEventIds must equal sorted RunEventLogV1.events ids"
        )
    if coverage["observationEventIds"] != expected_observation_ids:
        raise ValueError(
            "ObservationListV1 runEventCoverage.observationEventIds must equal sorted observationItems runEventIds"
        )
    expected_missing = sorted(set(expected_log_ids) - set(expected_observation_ids))
    expected_extra = sorted(set(expected_observation_ids) - set(expected_log_ids))
    if coverage["missingObservationsForEventIds"] != expected_missing:
        raise ValueError(
            "ObservationListV1 runEventCoverage.missingObservationsForEventIds must equal sorted(runEventIds - observationEventIds)"
        )
    if coverage["extraObservationEventIds"] != expected_extra:
        raise ValueError(
            "ObservationListV1 runEventCoverage.extraObservationEventIds must equal sorted(observationEventIds - runEventIds)"
        )
    expected_covered = set(expected_log_ids) == set(expected_observation_ids)
    if coverage["everyEventCovered"] is not expected_covered:
        raise ValueError(
            "ObservationListV1 runEventCoverage.everyEventCovered must equal runEventIds == observationEventIds"
        )
    if coverage["everyEventCovered"] is not True:
        raise ValueError(
            "ObservationListV1 runEventCoverage.everyEventCovered must be true: every RunEventLogV1.events entry must be covered"
        )


def _validate_evidence_coverage(
    coverage: dict[str, Any],
    items: list[dict[str, Any]],
    evidence_list: dict[str, Any],
) -> None:
    _require_fields(
        "ObservationListV1 evidenceCoverage",
        coverage,
        [
            "observationEvidenceIds",
            "resolvedIntoEvidenceList",
            "unresolvedObservationEvidenceIds",
            "everyEvidenceRefResolved",
        ],
    )
    cited: set[str] = set()
    for item in items:
        for evidence_id in item.get("evidenceRefs", []):
            if isinstance(evidence_id, str):
                cited.add(evidence_id)
    expected_sorted = sorted(cited)
    if coverage["observationEvidenceIds"] != expected_sorted:
        raise ValueError(
            "ObservationListV1 evidenceCoverage.observationEvidenceIds must equal the sorted set of observationItems evidenceRefs"
        )
    evidence_ids = {entry["evidenceId"] for entry in evidence_list.get("evidenceItems", [])}
    expected_resolved = sorted(cited & evidence_ids)
    expected_unresolved = sorted(cited - evidence_ids)
    if coverage["resolvedIntoEvidenceList"] != expected_resolved:
        raise ValueError(
            "ObservationListV1 evidenceCoverage.resolvedIntoEvidenceList must equal sorted(observationEvidenceIds ∩ EvidenceListV1.evidenceItems)"
        )
    if coverage["unresolvedObservationEvidenceIds"] != expected_unresolved:
        raise ValueError(
            "ObservationListV1 evidenceCoverage.unresolvedObservationEvidenceIds must equal sorted(observationEvidenceIds - EvidenceListV1.evidenceItems)"
        )
    expected_resolved_flag = cited.issubset(evidence_ids)
    if coverage["everyEvidenceRefResolved"] is not expected_resolved_flag:
        raise ValueError(
            "ObservationListV1 evidenceCoverage.everyEvidenceRefResolved must equal observationEvidenceIds ⊆ EvidenceListV1.evidenceItems"
        )
    if coverage["everyEvidenceRefResolved"] is not True:
        raise ValueError(
            "ObservationListV1 evidenceCoverage.everyEvidenceRefResolved must be true: "
            f"unresolved: {coverage['unresolvedObservationEvidenceIds']}"
        )


def _validate_promotion_conditions(
    promotion: dict[str, Any],
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> None:
    _require_fields(
        "ObservationListV1 promotionConditions",
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
            f"ObservationListV1 promotionConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_PROMOTION}"
        )
    if promotion["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "ObservationListV1 promotionConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if promotion["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"ObservationListV1 promotionConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if promotion["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"ObservationListV1 promotionConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if promotion["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "ObservationListV1 promotionConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if promotion["requiredPolicyUnlocked"] is not REQUIRED_POLICY_UNLOCKED:
        raise ValueError(
            "ObservationListV1 promotionConditions.requiredPolicyUnlocked must be true"
        )
    if promotion["currentPolicyUnlocked"] is not expected_unlocked:
        raise ValueError(
            "ObservationListV1 promotionConditions.currentPolicyUnlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_promoted = (
        promotion["currentVerdict"] == REQUIRED_VERDICT_FOR_PROMOTION
        and promotion["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and promotion["currentPolicyUnlocked"] is True
    )
    if promotion["promoted"] is not expected_promoted:
        raise ValueError(
            "ObservationListV1 promotionConditions.promoted must be true only when verdict, run terminal state and policy unlock all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("ObservationListV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("ObservationListV1 sourceArtifacts entries must be objects")
        _require_fields(
            "ObservationListV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"ObservationListV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"ObservationListV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"ObservationListV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"ObservationListV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"ObservationListV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"ObservationListV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_observation_list_artifact(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ObservationListV1",
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
            "observationItemSchemaVersion",
            "observationRunEventRefSchemaVersion",
            "verdictDomain",
            "observationKindDomain",
            "sourceAgentDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "runKernelCapabilitySentinel",
            "observationItems",
            "observationItemCount",
            "taskSpecBinding",
            "capabilityManifestBinding",
            "runEventLogBinding",
            "verifierResultBinding",
            "deliveryManifestBinding",
            "policyManifestBinding",
            "evidenceListBinding",
            "runEventCoverage",
            "evidenceCoverage",
            "promotionConditions",
            "verifierExpectations",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 schemaVersion must be {OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"ObservationListV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"ObservationListV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"ObservationListV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"ObservationListV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"ObservationListV1 workloadType must be {WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"ObservationListV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"ObservationListV1 creatorAgent must be {CREATOR_AGENT}")
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"ObservationListV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; creator must not own the verdict"
        )
    if manifest["observationItemSchemaVersion"] != OBSERVATION_ITEM_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 observationItemSchemaVersion must be {OBSERVATION_ITEM_SCHEMA_VERSION}"
        )
    if manifest["observationRunEventRefSchemaVersion"] != OBSERVATION_RUN_EVENT_REF_SCHEMA_VERSION:
        raise ValueError(
            f"ObservationListV1 observationRunEventRefSchemaVersion must be {OBSERVATION_RUN_EVENT_REF_SCHEMA_VERSION}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(f"ObservationListV1 verdictDomain must equal {VERDICT_DOMAIN}")
    if manifest["observationKindDomain"] != list(OBSERVATION_KIND_DOMAIN):
        raise ValueError(
            f"ObservationListV1 observationKindDomain must equal {OBSERVATION_KIND_DOMAIN}"
        )
    if manifest["sourceAgentDomain"] != list(SOURCE_AGENT_DOMAIN):
        raise ValueError(
            f"ObservationListV1 sourceAgentDomain must equal {SOURCE_AGENT_DOMAIN}"
        )
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"ObservationListV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )
    if manifest["runKernelCapabilitySentinel"] != RUN_KERNEL_CAPABILITY_SENTINEL:
        raise ValueError(
            f"ObservationListV1 runKernelCapabilitySentinel must be {RUN_KERNEL_CAPABILITY_SENTINEL}"
        )

    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"ObservationListV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(
                f"ObservationListV1 permissionFlags.{flag} must be false"
            )

    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    evidence_list = _load_json(root / EVIDENCE_LIST_ARTIFACT_PATH)

    _validate_observation_items(
        manifest["observationItems"], root, run_event_log, evidence_list
    )
    if manifest["observationItemCount"] != len(manifest["observationItems"]):
        raise ValueError(
            "ObservationListV1 observationItemCount must equal len(observationItems)"
        )

    _validate_task_spec_binding(manifest["taskSpecBinding"], root)
    _validate_capability_manifest_binding(manifest["capabilityManifestBinding"], root)
    _validate_run_event_log_binding(manifest["runEventLogBinding"], root)
    _validate_verifier_result_binding(manifest["verifierResultBinding"], root)
    _validate_delivery_manifest_binding(manifest["deliveryManifestBinding"], root)
    _validate_policy_manifest_binding(manifest["policyManifestBinding"], root)
    _validate_evidence_list_binding(manifest["evidenceListBinding"], root)
    _validate_run_event_coverage(
        manifest["runEventCoverage"], manifest["observationItems"], run_event_log
    )
    _validate_evidence_coverage(
        manifest["evidenceCoverage"], manifest["observationItems"], evidence_list
    )
    _validate_promotion_conditions(
        manifest["promotionConditions"], verifier_result, run_event_log, policy_manifest
    )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "ObservationListV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"ObservationListV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"ObservationListV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"ObservationListV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "ObservationListV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionRunEventArtifact",
            "reusesRegressionResultArtifact",
            "reusesRegressionEvidenceList",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionRunEventArtifact"] is not False:
        raise ValueError(
            "ObservationListV1 must not reuse the first-workload regression events.jsonl artifact"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "ObservationListV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesRegressionEvidenceList"] is not False:
        raise ValueError(
            "ObservationListV1 must not reuse the first-workload regression evidence-list-v1 artifact"
        )
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError(
            "ObservationListV1 must not reuse the send_email capability"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"ObservationListV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"ObservationListV1 must not embed regression/email field {term} outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"ObservationListV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            f"ObservationListV1 coordinationBinding must include {sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"ObservationListV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 7:
        raise ValueError(
            "ObservationListV1 invariants must declare at least seven workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="observation-artifact")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_observation_list_artifact(root)
        _write_json(args.out, manifest)
        print(f"Wrote ObservationListV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_observation_list_artifact(manifest, root)
        print(f"Validated ObservationListV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

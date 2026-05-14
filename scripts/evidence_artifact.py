"""EvidenceListV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``EvidenceListV1`` ArtifactV1
subtype.  It captures the canonical OS-kernel evidence primitive for any
engineering workload:

- a workload-independent ``EvidenceItemV1`` envelope describing every piece of
  evidence by stable ``evidenceId``, workload-independent ``evidenceKind``,
  payload ``contentHash``, source descriptor, capability provenance and
  redaction policy binding;
- a workload-independent ``EvidenceListV1`` envelope (an ``ArtifactV1``
  subtype) wrapping an ordered list of ``EvidenceItemV1`` instances along
  with bindings to every upstream test_execution_failure_triage primitive,
  the five Agent Coordination Layer contracts, the policy boundary, the
  unlock conditions, and a verifier-owned verdict expectation;
- cross-validation against ``TestExecutionResultV1.evidenceList`` (every
  workload-specific result must appear in the kernel envelope with the same
  ``contentHash``) and against
  ``FailureTriageReportV1.triageFindings[*].supportingEvidenceIds`` (every
  triage citation must resolve into the kernel envelope).

The artifact answers four OS-kernel invariants at once:

- ``Evidence`` primitive: the manifest declares a workload-independent
  evidence kind domain (``test_case_outcome_record`` / ``stack_trace_record``
  / ``log_excerpt`` / ``diff_snippet`` / ``build_log_excerpt`` /
  ``screenshot_redaction_record`` / ``triage_finding_excerpt`` /
  ``evidence_metadata_record``), pins each item to a workload-independent
  source kind, and binds every item to a capability and a redaction policy.
- ``Artifact`` envelope reuse: the manifest is an ``ArtifactV1`` subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) joining the existing
  ``CapabilityManifestV1`` / ``TestExecutionResultV1`` /
  ``FailureTriageReportV1`` / ``VerifierResultV1`` / ``RunEventLogV1`` /
  ``DeliveryManifestV1`` / ``PolicyManifestV1`` subtypes.
- ``Verifier`` / ``Policy`` consistency: the manifest pins the
  ``VerifierResultV1`` verdict and ``PolicyManifestV1`` unlock as
  prerequisites for any creator-side evidence promotion, and declares
  ``verifier-runtime-v1`` as the verdict owner while forcing
  ``creatorMustNotOwnVerdict=true``.
- ``Coordination`` evidence boundary: the manifest binds all five Agent
  Coordination Layer contracts by ref + content hash, so every coordination
  decision over evidence is constrained by the same envelope.
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
from failure_triage_report import (
    FAILURE_TRIAGE_REPORT_ARTIFACT_PATH,
    FAILURE_TRIAGE_REPORT_SCHEMA_VERSION,
    validate_failure_triage_report,
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
from test_execution_result import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION,
    TEST_EXECUTION_RESULT_ARTIFACT_PATH,
    TEST_EXECUTION_RESULT_SCHEMA_VERSION,
    validate_test_execution_result,
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


EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION = "evidence-list-artifact-v1"
EVIDENCE_ITEM_SCHEMA_VERSION = "evidence-item-v1"
EVIDENCE_SOURCE_SCHEMA_VERSION = "evidence-source-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "EvidenceListV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-evidence-list-kernel-contract"
EVIDENCE_LIST_ARTIFACT_PATH = (
    "artifacts/evidence/post_mvp_test_execution_evidence_list.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_evidence_list_contract"

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

EVIDENCE_KIND_DOMAIN = [
    "test_case_outcome_record",
    "stack_trace_record",
    "log_excerpt",
    "diff_snippet",
    "build_log_excerpt",
    "screenshot_redaction_record",
    "triage_finding_excerpt",
    "evidence_metadata_record",
]

EVIDENCE_SOURCE_KIND_DOMAIN = [
    "test_execution_result_v1",
    "failure_triage_report_v1",
    "run_event_log_v1",
    "verifier_result_v1",
    "delivery_manifest_v1",
    "policy_manifest_v1",
    "capability_manifest_v1",
]

PERMISSION_FLAG_DOMAIN = [
    "externalSideEffectsAllowed",
    "repositoryMutationAllowed",
    "externalCommunicationAllowed",
    "releaseOrDeploymentAllowed",
    "guiOrBrowserOrDesktopCallAllowed",
    "publicAccessAllowed",
]

EVIDENCE_KIND_TO_CAPABILITY: dict[str, str] = {
    "test_case_outcome_record": "collect_test_failure_evidence",
    "stack_trace_record": "collect_test_failure_evidence",
    "log_excerpt": "read_test_execution_result",
    "evidence_metadata_record": "read_test_execution_result",
    "triage_finding_excerpt": "classify_test_failure",
    "diff_snippet": "read_test_execution_result",
    "build_log_excerpt": "read_test_execution_result",
    "screenshot_redaction_record": "read_test_execution_result",
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
    "test_execution_result": TEST_EXECUTION_RESULT_ARTIFACT_PATH,
    "test_execution_verifier_result": VERIFIER_RESULT_ARTIFACT_PATH,
    "test_execution_failure_triage_report": FAILURE_TRIAGE_REPORT_ARTIFACT_PATH,
    "test_execution_delivery_manifest": DELIVERY_MANIFEST_ARTIFACT_PATH,
    "test_execution_policy_manifest": POLICY_MANIFEST_ARTIFACT_PATH,
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
    "mustValidateFailureTriageReportBinding",
    "mustValidateTestExecutionResultBinding",
    "mustValidateDeliveryManifestBinding",
    "mustValidatePolicyManifestBinding",
    "mustValidatePermissionFlags",
    "mustValidateEvidenceItems",
    "mustValidateFailureTriageEvidenceCoverage",
    "mustValidatePromotionConditions",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "EvidenceListV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype.",
    "EvidenceListV1 must bind TestExecutionTaskSpecV1, CapabilityManifestV1, RunEventLogV1, TestExecutionResultV1, FailureTriageReportV1, VerifierResultV1, DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1, and all five coordination contracts by content hash.",
    "EvidenceListV1 evidenceKindDomain and evidenceSourceKindDomain are workload-independent; no workload-specific kind may appear in evidenceItems.",
    "Every EvidenceItemV1 must mirror an item in TestExecutionResultV1.evidenceList by evidenceId, evidenceKind and contentHash.",
    "Every FailureTriageReportV1.triageFindings[*].supportingEvidenceIds must resolve into an EvidenceListV1 evidenceItem.",
    "EvidenceListV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and creator agents may only stage drafts.",
    "EvidenceListV1 promotionConditions require verdict=passed, terminal run state=completed and PolicyManifestV1 unlock=true.",
    "EvidenceListV1 must not reuse evidence-list-v1 (the first-workload regression EvidenceListV1) or any regression result / email_draft / send_email field.",
]


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _payload_hash(payload: str) -> str:
    normalized = payload.replace("\r\n", "\n")
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
            f"EvidenceListV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"EvidenceListV1 source artifact does not exist: {relative_path}"
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
                f"EvidenceListV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
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
    test_execution_result = _load_json(root / TEST_EXECUTION_RESULT_ARTIFACT_PATH)
    validate_test_execution_result(test_execution_result, root)
    failure_triage_report = _load_json(root / FAILURE_TRIAGE_REPORT_ARTIFACT_PATH)
    validate_failure_triage_report(failure_triage_report, root)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    validate_verifier_result(verifier_result, root)
    delivery_manifest = _load_json(root / DELIVERY_MANIFEST_ARTIFACT_PATH)
    validate_delivery_manifest(delivery_manifest, root)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    validate_policy_manifest(policy_manifest, root)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    validate_human_approval_decision(approval_decision, root)
    return (
        test_execution_result,
        failure_triage_report,
        verifier_result,
        run_event_log,
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
    }


def _build_test_execution_result_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_RESULT_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "testExecutionResultRef": relative_path,
        "testExecutionResultSchemaVersion": TEST_EXECUTION_RESULT_SCHEMA_VERSION,
        "testExecutionResultEnvelopeSchemaVersion": TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION,
        "testExecutionResultContentHash": _stable_file_hash(full_path),
    }


def _build_failure_triage_report_binding(root: Path) -> dict[str, Any]:
    relative_path = FAILURE_TRIAGE_REPORT_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "failureTriageReportRef": relative_path,
        "failureTriageReportSchemaVersion": FAILURE_TRIAGE_REPORT_SCHEMA_VERSION,
        "failureTriageReportEnvelopeSchemaVersion": "artifact-v1",
        "failureTriageReportContentHash": _stable_file_hash(full_path),
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


def _build_evidence_items(
    root: Path, test_execution_result: dict[str, Any]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    source_artifact = TEST_EXECUTION_RESULT_ARTIFACT_PATH
    source_hash = _stable_file_hash(root / source_artifact)
    for entry in test_execution_result["evidenceList"]:
        evidence_kind = entry["kind"]
        if evidence_kind not in EVIDENCE_KIND_DOMAIN:
            raise ValueError(
                f"EvidenceListV1 cannot promote evidence with workload-specific kind: {evidence_kind}"
            )
        capability_ref = EVIDENCE_KIND_TO_CAPABILITY.get(evidence_kind)
        if capability_ref is None or capability_ref not in CAPABILITY_NAMES:
            raise ValueError(
                f"EvidenceListV1 has no capability binding for evidence kind: {evidence_kind}"
            )
        payload_hash = _payload_hash(entry["payload"])
        if payload_hash != entry["contentHash"]:
            raise ValueError(
                f"EvidenceListV1 source contentHash mismatch for {entry['id']}"
            )
        items.append(
            {
                "schemaVersion": EVIDENCE_ITEM_SCHEMA_VERSION,
                "evidenceId": entry["id"],
                "evidenceKind": evidence_kind,
                "contentHash": entry["contentHash"],
                "source": {
                    "schemaVersion": EVIDENCE_SOURCE_SCHEMA_VERSION,
                    "sourceKind": "test_execution_result_v1",
                    "sourceArtifactRef": source_artifact,
                    "sourceArtifactSchemaVersion": TEST_EXECUTION_RESULT_SCHEMA_VERSION,
                    "sourceArtifactContentHash": source_hash,
                },
                "capabilityRef": capability_ref,
                "redactionPolicyRef": OBSERVATION_REDACTION_POLICY_REF,
                "redactionPolicySchemaVersion": OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION,
                "redactionApplied": False,
            }
        )
    return items


def _build_failure_triage_coverage(
    failure_triage_report: dict[str, Any], evidence_items: list[dict[str, Any]]
) -> dict[str, Any]:
    cited: set[str] = set()
    for finding in failure_triage_report.get("triageFindings", []):
        if not isinstance(finding, dict):
            continue
        for evidence_id in finding.get("supportingEvidenceIds", []) or []:
            if isinstance(evidence_id, str):
                cited.add(evidence_id)
    item_ids = {item["evidenceId"] for item in evidence_items}
    return {
        "triageEvidenceIds": sorted(cited),
        "resolvedIntoEvidenceList": sorted(cited & item_ids),
        "unresolvedTriageEvidenceIds": sorted(cited - item_ids),
        "evidenceListCoversTriage": cited.issubset(item_ids),
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


def build_evidence_list_artifact(root: Path) -> dict[str, Any]:
    (
        test_execution_result,
        failure_triage_report,
        verifier_result,
        run_event_log,
        policy_manifest,
    ) = _validate_referenced_artifacts(root)
    evidence_items = _build_evidence_items(root, test_execution_result)
    coverage = _build_failure_triage_coverage(failure_triage_report, evidence_items)
    if not coverage["evidenceListCoversTriage"]:
        raise ValueError(
            "EvidenceListV1 must cover every FailureTriageReportV1 supporting evidence id; "
            f"unresolved: {coverage['unresolvedTriageEvidenceIds']}"
        )
    payload: dict[str, Any] = {
        "schemaVersion": EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "evidenceItemSchemaVersion": EVIDENCE_ITEM_SCHEMA_VERSION,
        "evidenceSourceSchemaVersion": EVIDENCE_SOURCE_SCHEMA_VERSION,
        "verdictDomain": list(VERDICT_DOMAIN),
        "evidenceKindDomain": list(EVIDENCE_KIND_DOMAIN),
        "evidenceSourceKindDomain": list(EVIDENCE_SOURCE_KIND_DOMAIN),
        "permissionFlagDomain": list(PERMISSION_FLAG_DOMAIN),
        "permissionFlags": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
        "evidenceItems": evidence_items,
        "evidenceItemCount": len(evidence_items),
        "taskSpecBinding": _build_task_spec_binding(root),
        "capabilityManifestBinding": _build_capability_manifest_binding(root),
        "runEventLogBinding": _build_run_event_log_binding(root, run_event_log),
        "testExecutionResultBinding": _build_test_execution_result_binding(root),
        "failureTriageReportBinding": _build_failure_triage_report_binding(root),
        "verifierResultBinding": _build_verifier_result_binding(root, verifier_result),
        "deliveryManifestBinding": _build_delivery_manifest_binding(root),
        "policyManifestBinding": _build_policy_manifest_binding(root, policy_manifest),
        "failureTriageEvidenceCoverage": coverage,
        "promotionConditions": _build_promotion_conditions(
            verifier_result, run_event_log, policy_manifest
        ),
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateTaskSpecBinding": True,
            "mustValidateCapabilityManifestBinding": True,
            "mustValidateRunEventLogBinding": True,
            "mustValidateVerifierResultBinding": True,
            "mustValidateFailureTriageReportBinding": True,
            "mustValidateTestExecutionResultBinding": True,
            "mustValidateDeliveryManifestBinding": True,
            "mustValidatePolicyManifestBinding": True,
            "mustValidatePermissionFlags": True,
            "mustValidateEvidenceItems": True,
            "mustValidateFailureTriageEvidenceCoverage": True,
            "mustValidatePromotionConditions": True,
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERDICT_DOMAIN),
            "creatorMustNotOwnVerdict": True,
        },
        "regressionWorkloadIsolation": {
            "reusesRegressionEvidenceList": False,
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
    validate_evidence_list_artifact(payload, root)
    return payload


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1 taskSpecBinding",
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
            f"EvidenceListV1 taskSpecBinding.taskSpecRef must equal {TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 taskSpecBinding.taskSpecSchemaVersion must equal {TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; "
            "regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal {TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"EvidenceListV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"EvidenceListV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    if binding["taskSpecContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "EvidenceListV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1 capabilityManifestBinding",
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
            f"EvidenceListV1 capabilityManifestBinding.capabilityManifestRef must equal {CAPABILITY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal {CAPABILITY_MANIFEST_SCHEMA_VERSION}; "
            "regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal {CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"EvidenceListV1 capabilityManifestBinding.capabilityManifestId must equal {CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["capabilityManifestRef"]
    if binding["capabilityManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "EvidenceListV1 capabilityManifestBinding.capabilityManifestContentHash must match the on-disk capability manifest"
        )


def _validate_run_event_log_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1 runEventLogBinding",
        binding,
        [
            "runEventLogRef",
            "runEventLogSchemaVersion",
            "runEventLogEnvelopeSchemaVersion",
            "runEventLogId",
            "runEventLogContentHash",
            "terminalState",
        ],
    )
    if binding["runEventLogRef"] != RUN_EVENT_LOG_ARTIFACT_PATH:
        raise ValueError(
            f"EvidenceListV1 runEventLogBinding.runEventLogRef must equal {RUN_EVENT_LOG_ARTIFACT_PATH}"
        )
    if binding["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 runEventLogBinding.runEventLogSchemaVersion must equal {RUN_EVENT_LOG_SCHEMA_VERSION}; "
            "regression events.jsonl reuse is forbidden"
        )
    if binding["runEventLogEnvelopeSchemaVersion"] != RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 runEventLogBinding.runEventLogEnvelopeSchemaVersion must equal {RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION}"
        )
    full_path = root / binding["runEventLogRef"]
    if binding["runEventLogContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "EvidenceListV1 runEventLogBinding.runEventLogContentHash must match the on-disk run event log"
        )
    run_event_log = _load_json(full_path)
    if binding["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "EvidenceListV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )


def _validate_test_execution_result_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1 testExecutionResultBinding",
        binding,
        [
            "testExecutionResultRef",
            "testExecutionResultSchemaVersion",
            "testExecutionResultEnvelopeSchemaVersion",
            "testExecutionResultContentHash",
        ],
    )
    if binding["testExecutionResultRef"] != TEST_EXECUTION_RESULT_ARTIFACT_PATH:
        raise ValueError(
            f"EvidenceListV1 testExecutionResultBinding.testExecutionResultRef must equal {TEST_EXECUTION_RESULT_ARTIFACT_PATH}"
        )
    if binding["testExecutionResultSchemaVersion"] != TEST_EXECUTION_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 testExecutionResultBinding.testExecutionResultSchemaVersion must equal {TEST_EXECUTION_RESULT_SCHEMA_VERSION}; "
            "regression result artifact reuse is forbidden"
        )
    if binding["testExecutionResultEnvelopeSchemaVersion"] != TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 testExecutionResultBinding.testExecutionResultEnvelopeSchemaVersion must equal {TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    full_path = root / binding["testExecutionResultRef"]
    if binding["testExecutionResultContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "EvidenceListV1 testExecutionResultBinding.testExecutionResultContentHash must match the on-disk test execution result"
        )


def _validate_failure_triage_report_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1 failureTriageReportBinding",
        binding,
        [
            "failureTriageReportRef",
            "failureTriageReportSchemaVersion",
            "failureTriageReportEnvelopeSchemaVersion",
            "failureTriageReportContentHash",
        ],
    )
    if binding["failureTriageReportRef"] != FAILURE_TRIAGE_REPORT_ARTIFACT_PATH:
        raise ValueError(
            f"EvidenceListV1 failureTriageReportBinding.failureTriageReportRef must equal {FAILURE_TRIAGE_REPORT_ARTIFACT_PATH}"
        )
    if binding["failureTriageReportSchemaVersion"] != FAILURE_TRIAGE_REPORT_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 failureTriageReportBinding.failureTriageReportSchemaVersion must equal {FAILURE_TRIAGE_REPORT_SCHEMA_VERSION}; "
            "regression result artifact reuse is forbidden"
        )
    if binding["failureTriageReportEnvelopeSchemaVersion"] != "artifact-v1":
        raise ValueError(
            "EvidenceListV1 failureTriageReportBinding.failureTriageReportEnvelopeSchemaVersion must equal artifact-v1"
        )
    full_path = root / binding["failureTriageReportRef"]
    if binding["failureTriageReportContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "EvidenceListV1 failureTriageReportBinding.failureTriageReportContentHash must match the on-disk failure triage report"
        )


def _validate_verifier_result_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1 verifierResultBinding",
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
            f"EvidenceListV1 verifierResultBinding.verifierResultRef must equal {VERIFIER_RESULT_ARTIFACT_PATH}"
        )
    if binding["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 verifierResultBinding.verifierResultSchemaVersion must equal {VERIFIER_RESULT_SCHEMA_VERSION}; "
            "regression result artifact reuse is forbidden"
        )
    if binding["verifierResultEnvelopeSchemaVersion"] != VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 verifierResultBinding.verifierResultEnvelopeSchemaVersion must equal {VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["verifierResultId"] != VERIFIER_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"EvidenceListV1 verifierResultBinding.verifierResultId must equal {VERIFIER_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["verifierResultRef"]
    if binding["verifierResultContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "EvidenceListV1 verifierResultBinding.verifierResultContentHash must match the on-disk verifier result"
        )
    if binding["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"EvidenceListV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}; got {binding['verdict']}"
        )
    verifier_result = _load_json(full_path)
    if binding["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "EvidenceListV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )


def _validate_delivery_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1 deliveryManifestBinding",
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
            f"EvidenceListV1 deliveryManifestBinding.deliveryManifestRef must equal {DELIVERY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["deliveryManifestSchemaVersion"] != DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 deliveryManifestBinding.deliveryManifestSchemaVersion must equal {DELIVERY_MANIFEST_SCHEMA_VERSION}; "
            "multi-agent-delivery-manifest reuse is forbidden"
        )
    if binding["deliveryManifestEnvelopeSchemaVersion"] != DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 deliveryManifestBinding.deliveryManifestEnvelopeSchemaVersion must equal {DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["deliveryManifestId"] != DELIVERY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"EvidenceListV1 deliveryManifestBinding.deliveryManifestId must equal {DELIVERY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["deliveryManifestRef"]
    if binding["deliveryManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "EvidenceListV1 deliveryManifestBinding.deliveryManifestContentHash must match the on-disk delivery manifest"
        )


def _validate_policy_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1 policyManifestBinding",
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
            f"EvidenceListV1 policyManifestBinding.policyManifestRef must equal {POLICY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["policyManifestSchemaVersion"] != POLICY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 policyManifestBinding.policyManifestSchemaVersion must equal {POLICY_MANIFEST_SCHEMA_VERSION}; "
            "regression / adapter policy reuse is forbidden"
        )
    if binding["policyManifestEnvelopeSchemaVersion"] != POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 policyManifestBinding.policyManifestEnvelopeSchemaVersion must equal {POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["policyManifestId"] != POLICY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"EvidenceListV1 policyManifestBinding.policyManifestId must equal {POLICY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["policyManifestRef"]
    if binding["policyManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "EvidenceListV1 policyManifestBinding.policyManifestContentHash must match the on-disk policy manifest"
        )
    policy_manifest = _load_json(full_path)
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if binding["unlocked"] is not expected_unlocked:
        raise ValueError(
            "EvidenceListV1 policyManifestBinding.unlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )


def _validate_evidence_items(
    evidence_items: list[Any], root: Path, test_execution_result: dict[str, Any]
) -> None:
    if not isinstance(evidence_items, list) or not evidence_items:
        raise ValueError("EvidenceListV1 evidenceItems must be a non-empty list")
    source_artifact = TEST_EXECUTION_RESULT_ARTIFACT_PATH
    source_hash = _stable_file_hash(root / source_artifact)
    upstream_items = {
        item["id"]: item for item in test_execution_result.get("evidenceList", [])
    }
    seen_ids: set[str] = set()
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict):
            raise ValueError("EvidenceListV1 evidenceItems entries must be objects")
        label = f"EvidenceListV1 evidenceItems[{index}]"
        _require_fields(
            label,
            item,
            [
                "schemaVersion",
                "evidenceId",
                "evidenceKind",
                "contentHash",
                "source",
                "capabilityRef",
                "redactionPolicyRef",
                "redactionPolicySchemaVersion",
                "redactionApplied",
            ],
        )
        if item["schemaVersion"] != EVIDENCE_ITEM_SCHEMA_VERSION:
            raise ValueError(
                f"{label}.schemaVersion must be {EVIDENCE_ITEM_SCHEMA_VERSION}"
            )
        if item["evidenceId"] in seen_ids:
            raise ValueError(
                f"EvidenceListV1 duplicate evidenceItems.evidenceId: {item['evidenceId']}"
            )
        seen_ids.add(item["evidenceId"])
        if item["evidenceKind"] not in EVIDENCE_KIND_DOMAIN:
            raise ValueError(
                f"{label}.evidenceKind must be one of {EVIDENCE_KIND_DOMAIN}; got {item['evidenceKind']}"
            )
        if item["capabilityRef"] not in CAPABILITY_NAMES:
            raise ValueError(
                f"{label}.capabilityRef must be one of {CAPABILITY_NAMES}; got {item['capabilityRef']}"
            )
        expected_capability = EVIDENCE_KIND_TO_CAPABILITY.get(item["evidenceKind"])
        if expected_capability is None or item["capabilityRef"] != expected_capability:
            raise ValueError(
                f"{label}.capabilityRef for kind {item['evidenceKind']} must be {expected_capability}; got {item['capabilityRef']}"
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
        source = item["source"]
        if not isinstance(source, dict):
            raise ValueError(f"{label}.source must be an object")
        _require_fields(
            f"{label}.source",
            source,
            [
                "schemaVersion",
                "sourceKind",
                "sourceArtifactRef",
                "sourceArtifactSchemaVersion",
                "sourceArtifactContentHash",
            ],
        )
        if source["schemaVersion"] != EVIDENCE_SOURCE_SCHEMA_VERSION:
            raise ValueError(
                f"{label}.source.schemaVersion must be {EVIDENCE_SOURCE_SCHEMA_VERSION}"
            )
        if source["sourceKind"] not in EVIDENCE_SOURCE_KIND_DOMAIN:
            raise ValueError(
                f"{label}.source.sourceKind must be one of {EVIDENCE_SOURCE_KIND_DOMAIN}; got {source['sourceKind']}"
            )
        if source["sourceKind"] != "test_execution_result_v1":
            raise ValueError(
                f"{label}.source.sourceKind must equal test_execution_result_v1 for the first test execution workload"
            )
        if source["sourceArtifactRef"] != source_artifact:
            raise ValueError(
                f"{label}.source.sourceArtifactRef must equal {source_artifact}"
            )
        if source["sourceArtifactSchemaVersion"] != TEST_EXECUTION_RESULT_SCHEMA_VERSION:
            raise ValueError(
                f"{label}.source.sourceArtifactSchemaVersion must equal {TEST_EXECUTION_RESULT_SCHEMA_VERSION}"
            )
        if source["sourceArtifactContentHash"] != source_hash:
            raise ValueError(
                f"{label}.source.sourceArtifactContentHash must match the on-disk test execution result hash"
            )
        upstream = upstream_items.get(item["evidenceId"])
        if upstream is None:
            raise ValueError(
                f"{label}.evidenceId {item['evidenceId']} is not present in TestExecutionResultV1.evidenceList"
            )
        if upstream["kind"] != item["evidenceKind"]:
            raise ValueError(
                f"{label}.evidenceKind {item['evidenceKind']} does not match TestExecutionResultV1.evidenceList kind {upstream['kind']}"
            )
        if upstream["contentHash"] != item["contentHash"]:
            raise ValueError(
                f"{label}.contentHash must equal TestExecutionResultV1.evidenceList contentHash for {item['evidenceId']}"
            )
    expected_ids = set(upstream_items)
    if seen_ids != expected_ids:
        missing = sorted(expected_ids - seen_ids)
        extra = sorted(seen_ids - expected_ids)
        raise ValueError(
            "EvidenceListV1 evidenceItems must mirror TestExecutionResultV1.evidenceList. "
            f"Missing: {missing}; Extra: {extra}"
        )


def _validate_failure_triage_evidence_coverage(
    coverage: dict[str, Any],
    failure_triage_report: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> None:
    _require_fields(
        "EvidenceListV1 failureTriageEvidenceCoverage",
        coverage,
        [
            "triageEvidenceIds",
            "resolvedIntoEvidenceList",
            "unresolvedTriageEvidenceIds",
            "evidenceListCoversTriage",
        ],
    )
    expected_cited: set[str] = set()
    for finding in failure_triage_report.get("triageFindings", []):
        if not isinstance(finding, dict):
            continue
        for evidence_id in finding.get("supportingEvidenceIds", []) or []:
            if isinstance(evidence_id, str):
                expected_cited.add(evidence_id)
    expected_sorted = sorted(expected_cited)
    if coverage["triageEvidenceIds"] != expected_sorted:
        raise ValueError(
            "EvidenceListV1 failureTriageEvidenceCoverage.triageEvidenceIds must equal the sorted set of FailureTriageReportV1 supporting evidence ids"
        )
    item_ids = {item["evidenceId"] for item in evidence_items}
    expected_resolved = sorted(expected_cited & item_ids)
    expected_unresolved = sorted(expected_cited - item_ids)
    if coverage["resolvedIntoEvidenceList"] != expected_resolved:
        raise ValueError(
            "EvidenceListV1 failureTriageEvidenceCoverage.resolvedIntoEvidenceList must equal sorted(triageEvidenceIds ∩ evidenceItems)"
        )
    if coverage["unresolvedTriageEvidenceIds"] != expected_unresolved:
        raise ValueError(
            "EvidenceListV1 failureTriageEvidenceCoverage.unresolvedTriageEvidenceIds must equal sorted(triageEvidenceIds - evidenceItems)"
        )
    expected_covers = expected_cited.issubset(item_ids)
    if coverage["evidenceListCoversTriage"] is not expected_covers:
        raise ValueError(
            "EvidenceListV1 failureTriageEvidenceCoverage.evidenceListCoversTriage must equal triageEvidenceIds ⊆ evidenceItems"
        )
    if coverage["evidenceListCoversTriage"] is not True:
        raise ValueError(
            "EvidenceListV1 failureTriageEvidenceCoverage.evidenceListCoversTriage must be true: "
            f"unresolved: {coverage['unresolvedTriageEvidenceIds']}"
        )


def _validate_promotion_conditions(
    promotion: dict[str, Any],
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> None:
    _require_fields(
        "EvidenceListV1 promotionConditions",
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
            f"EvidenceListV1 promotionConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_PROMOTION}"
        )
    if promotion["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "EvidenceListV1 promotionConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if promotion["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"EvidenceListV1 promotionConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if promotion["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"EvidenceListV1 promotionConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if promotion["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "EvidenceListV1 promotionConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if promotion["requiredPolicyUnlocked"] is not REQUIRED_POLICY_UNLOCKED:
        raise ValueError(
            "EvidenceListV1 promotionConditions.requiredPolicyUnlocked must be true"
        )
    if promotion["currentPolicyUnlocked"] is not expected_unlocked:
        raise ValueError(
            "EvidenceListV1 promotionConditions.currentPolicyUnlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_promoted = (
        promotion["currentVerdict"] == REQUIRED_VERDICT_FOR_PROMOTION
        and promotion["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and promotion["currentPolicyUnlocked"] is True
    )
    if promotion["promoted"] is not expected_promoted:
        raise ValueError(
            "EvidenceListV1 promotionConditions.promoted must be true only when verdict, run terminal state and policy unlock all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("EvidenceListV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("EvidenceListV1 sourceArtifacts entries must be objects")
        _require_fields(
            "EvidenceListV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"EvidenceListV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"EvidenceListV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"EvidenceListV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"EvidenceListV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"EvidenceListV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"EvidenceListV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_evidence_list_artifact(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "EvidenceListV1",
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
            "evidenceItemSchemaVersion",
            "evidenceSourceSchemaVersion",
            "verdictDomain",
            "evidenceKindDomain",
            "evidenceSourceKindDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "evidenceItems",
            "evidenceItemCount",
            "taskSpecBinding",
            "capabilityManifestBinding",
            "runEventLogBinding",
            "testExecutionResultBinding",
            "failureTriageReportBinding",
            "verifierResultBinding",
            "deliveryManifestBinding",
            "policyManifestBinding",
            "failureTriageEvidenceCoverage",
            "promotionConditions",
            "verifierExpectations",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 schemaVersion must be {EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"EvidenceListV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"EvidenceListV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"EvidenceListV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"EvidenceListV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"EvidenceListV1 workloadType must be {WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"EvidenceListV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"EvidenceListV1 creatorAgent must be {CREATOR_AGENT}")
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"EvidenceListV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; creator must not own the verdict"
        )
    if manifest["evidenceItemSchemaVersion"] != EVIDENCE_ITEM_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 evidenceItemSchemaVersion must be {EVIDENCE_ITEM_SCHEMA_VERSION}"
        )
    if manifest["evidenceSourceSchemaVersion"] != EVIDENCE_SOURCE_SCHEMA_VERSION:
        raise ValueError(
            f"EvidenceListV1 evidenceSourceSchemaVersion must be {EVIDENCE_SOURCE_SCHEMA_VERSION}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(f"EvidenceListV1 verdictDomain must equal {VERDICT_DOMAIN}")
    if manifest["evidenceKindDomain"] != list(EVIDENCE_KIND_DOMAIN):
        raise ValueError(f"EvidenceListV1 evidenceKindDomain must equal {EVIDENCE_KIND_DOMAIN}")
    if manifest["evidenceSourceKindDomain"] != list(EVIDENCE_SOURCE_KIND_DOMAIN):
        raise ValueError(
            f"EvidenceListV1 evidenceSourceKindDomain must equal {EVIDENCE_SOURCE_KIND_DOMAIN}"
        )
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"EvidenceListV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )

    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"EvidenceListV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(
                f"EvidenceListV1 permissionFlags.{flag} must be false"
            )

    test_execution_result = _load_json(root / TEST_EXECUTION_RESULT_ARTIFACT_PATH)
    failure_triage_report = _load_json(root / FAILURE_TRIAGE_REPORT_ARTIFACT_PATH)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)

    _validate_evidence_items(manifest["evidenceItems"], root, test_execution_result)
    if manifest["evidenceItemCount"] != len(manifest["evidenceItems"]):
        raise ValueError(
            "EvidenceListV1 evidenceItemCount must equal len(evidenceItems)"
        )

    _validate_task_spec_binding(manifest["taskSpecBinding"], root)
    _validate_capability_manifest_binding(manifest["capabilityManifestBinding"], root)
    _validate_run_event_log_binding(manifest["runEventLogBinding"], root)
    _validate_test_execution_result_binding(manifest["testExecutionResultBinding"], root)
    _validate_failure_triage_report_binding(manifest["failureTriageReportBinding"], root)
    _validate_verifier_result_binding(manifest["verifierResultBinding"], root)
    _validate_delivery_manifest_binding(manifest["deliveryManifestBinding"], root)
    _validate_policy_manifest_binding(manifest["policyManifestBinding"], root)
    _validate_failure_triage_evidence_coverage(
        manifest["failureTriageEvidenceCoverage"],
        failure_triage_report,
        manifest["evidenceItems"],
    )
    _validate_promotion_conditions(
        manifest["promotionConditions"], verifier_result, run_event_log, policy_manifest
    )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "EvidenceListV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"EvidenceListV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"EvidenceListV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"EvidenceListV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "EvidenceListV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionEvidenceList",
            "reusesRegressionResultArtifact",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionEvidenceList"] is not False:
        raise ValueError(
            "EvidenceListV1 must not reuse the first-workload regression evidence-list-v1 artifact"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "EvidenceListV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError(
            "EvidenceListV1 must not reuse the send_email capability"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"EvidenceListV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"EvidenceListV1 must not embed regression/email field {term} outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"EvidenceListV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            f"EvidenceListV1 coordinationBinding must include {sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"EvidenceListV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 7:
        raise ValueError(
            "EvidenceListV1 invariants must declare at least seven workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evidence-artifact")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_evidence_list_artifact(root)
        _write_json(args.out, manifest)
        print(f"Wrote EvidenceListV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_evidence_list_artifact(manifest, root)
        print(f"Validated EvidenceListV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

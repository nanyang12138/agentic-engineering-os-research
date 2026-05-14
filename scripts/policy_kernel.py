"""PolicyV1 / policy-v1 ArtifactV1 subtype contract.

This module defines a workload-independent ``PolicyV1`` ArtifactV1
subtype that captures the canonical OS-kernel ``Policy`` primitive for
any engineering workload. The artifact is a static, machine-verifiable
contract: no policy is enforced at runtime, no decision is dispatched,
no external side effect is triggered.

``PolicyV1`` is intentionally distinct from the workload-specific
``PolicyManifestV1`` (which catalogues the runtime policy rules,
effect-class decisions, unlock conditions and revocation rules for the
Test Execution / Failure Triage workload). Where ``PolicyManifestV1``
answers *what does the policy enforcement look like inside this
workload*, ``PolicyV1`` answers *what is the canonical shape of a
policy primitive that any workload can reuse*: every ``policyItem``
declares ``policyId`` / ``policyClass`` / ``policyScope`` /
``policyLifecycleState`` / ``requiredFlag`` / ``verifierVerdictOwner``
/ ``unlockConditionRef`` from the workload-independent vocabulary.

Invariants enforced by ``validate_policy_kernel_artifact``:

- ``PolicyV1`` is an ArtifactV1 subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) joining the existing
  fifteen subtypes; ``kind`` must be ``PolicyV1`` and ``schemaVersion``
  must be ``policy-v1``.
- ``policyClass`` must lie in ``[permission_policy, approval_policy,
  delivery_policy, external_side_effect_policy,
  regression_isolation_policy, coordination_policy]``;
  ``[regression_result_policy, email_draft_policy, send_email_policy]``
  are explicitly forbidden.
- ``policyScope`` must lie in ``[workload_independent_kernel,
  workload_specific, coordination_layer]``; every committed policy
  item must be ``workload_independent_kernel`` or
  ``coordination_layer``.
- ``policyLifecycleState`` must lie in ``[drafted, active, deprecated,
  withdrawn]``; every committed policy item must be ``active``.
- ``requiredFlag`` must be ``false`` for every workload-independent
  kernel policy item (the contract-only MVP cannot flip any policy on
  at the kernel level).
- Every ``PolicyManifestV1.unlockConditions`` key must resolve into a
  ``PolicyV1.policyItems[*].unlockConditionRef``; the unlock condition
  keys must equal the set of policy item references with no missing
  or extra key.
- ``PolicyV1`` binds the upstream fourteen workload artifacts
  (TestExecutionTaskSpecV1, IntentV1, RunV1, StepListV1,
  ToolCallListV1, CapabilityV1, CapabilityManifestV1, RunEventLogV1,
  ObservationListV1, EvidenceListV1, VerifierResultV1,
  DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1) plus
  the five Agent Coordination Layer contracts by content hash.
- The six workload-independent permission flags are forced to
  ``false`` at the envelope and per policy item.
- Regression-workload isolation forbids ``regression_result`` /
  ``email_draft`` / ``send_email`` / ``regression-task-spec-v1`` /
  ``regression-result-artifact-v1`` reuse and tracks
  ``reusesRegressionPolicyArtifact=false`` /
  ``reusesPhase7AdapterPolicyManifest=false`` /
  ``reusesPolicyUnlockDenialFixture=false`` /
  ``reusesSendEmailCapability=false``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from capability_kernel import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as CAPABILITY_KERNEL_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as CAPABILITY_KERNEL_ARTIFACT_ID,
    CAPABILITY_KERNEL_ARTIFACT_PATH,
    CAPABILITY_KERNEL_SCHEMA_VERSION,
    validate_capability_kernel_artifact,
)
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
from intent_artifact import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as INTENT_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as INTENT_ARTIFACT_ID,
    INTENT_ARTIFACT_PATH,
    INTENT_ARTIFACT_SCHEMA_VERSION,
    validate_intent_artifact,
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


POLICY_KERNEL_SCHEMA_VERSION = "policy-v1"
POLICY_ITEM_SCHEMA_VERSION = "policy-item-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "PolicyV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-policy-v1-kernel-contract"
POLICY_KERNEL_ARTIFACT_PATH = "artifacts/policy/post_mvp_policy_v1_catalog.json"

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "workload_independent_policy_v1_kernel_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

POLICY_CLASS_DOMAIN = [
    "permission_policy",
    "approval_policy",
    "delivery_policy",
    "external_side_effect_policy",
    "regression_isolation_policy",
    "coordination_policy",
]
FORBIDDEN_POLICY_CLASSES = [
    "regression_result_policy",
    "email_draft_policy",
    "send_email_policy",
]

POLICY_SCOPE_DOMAIN = [
    "workload_independent_kernel",
    "workload_specific",
    "coordination_layer",
]
ALLOWED_COMMITTED_POLICY_SCOPES = [
    "workload_independent_kernel",
    "coordination_layer",
]

POLICY_LIFECYCLE_STATE_DOMAIN = [
    "drafted",
    "active",
    "deprecated",
    "withdrawn",
]
REQUIRED_POLICY_LIFECYCLE_STATE = "active"

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
    "test_execution_intent": INTENT_ARTIFACT_PATH,
    "test_execution_capability_kernel": CAPABILITY_KERNEL_ARTIFACT_PATH,
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
    "mustValidatePolicyClassDomain",
    "mustValidateForbiddenPolicyClasses",
    "mustValidatePolicyScopeDomain",
    "mustValidatePolicyLifecycleStateDomain",
    "mustValidateRequiredFlag",
    "mustValidatePermissionFlags",
    "mustValidateTaskSpecBinding",
    "mustValidateIntentBinding",
    "mustValidateRunBinding",
    "mustValidateStepListBinding",
    "mustValidateToolCallListBinding",
    "mustValidateCapabilityV1Binding",
    "mustValidateCapabilityManifestBinding",
    "mustValidateRunEventLogBinding",
    "mustValidateObservationListBinding",
    "mustValidateEvidenceListBinding",
    "mustValidateVerifierResultBinding",
    "mustValidateDeliveryManifestBinding",
    "mustValidatePolicyManifestBinding",
    "mustValidateApprovalDecisionBinding",
    "mustValidateUnlockConditionCoverage",
    "mustValidatePromotionConditions",
    "creatorMustNotOwnVerdict",
]


# Deterministic PolicyV1 blueprint: exactly one entry per unique
# ``PolicyManifestV1.unlockConditions`` key. Every blueprint entry uses
# only workload-independent vocabulary: policyClass, policyScope,
# policyLifecycleState, requiredFlag, verifierVerdictOwner, and
# unlockConditionRef. The eleven entries collectively cover every key
# of ``PolicyManifestV1.unlockConditions`` so that the kernel-level
# Policy primitive owns the unlock contract.
POLICY_BLUEPRINT: list[dict[str, Any]] = [
    {
        "policyId": "permission-flags-locked",
        "policyClass": "permission_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "unlocked",
        "description": (
            "Locks the six workload-independent permission flags to "
            "false; flipping any flag breaks the contract-only MVP "
            "guarantee and revokes the unlock."
        ),
    },
    {
        "policyId": "approval-granted",
        "policyClass": "approval_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "approvalGranted",
        "description": (
            "Binds the policy unlock to the human approval decision "
            "approvalGranted flag; only a granted decision can unlock."
        ),
    },
    {
        "policyId": "approval-record-path",
        "policyClass": "approval_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "approvalRecordRef",
        "description": (
            "Pins the approval record path so the unlock can only "
            "reference the committed HumanApprovalDecisionV1 fixture."
        ),
    },
    {
        "policyId": "approval-record-schema",
        "policyClass": "approval_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "approvalRecordSchemaVersion",
        "description": (
            "Pins the approval record schema version to the canonical "
            "human-approval-decision-v1 contract."
        ),
    },
    {
        "policyId": "approval-decision-current",
        "policyClass": "approval_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "currentApprovalDecision",
        "description": (
            "Mirrors the current human approval decision so the unlock "
            "tracks decision drift."
        ),
    },
    {
        "policyId": "approval-decision-required",
        "policyClass": "approval_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "requiredApprovalDecision",
        "description": (
            "Declares that the required human approval decision is "
            "approved; any other required decision is invalid."
        ),
    },
    {
        "policyId": "run-terminal-state-current",
        "policyClass": "delivery_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "currentTerminalRunState",
        "description": (
            "Mirrors RunEventLogV1.terminalState so the unlock cannot "
            "survive a run that never terminated cleanly."
        ),
    },
    {
        "policyId": "run-terminal-state-required",
        "policyClass": "delivery_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "requiredTerminalRunState",
        "description": (
            "Declares completed as the only acceptable run terminal "
            "state for delivery readiness."
        ),
    },
    {
        "policyId": "verdict-current",
        "policyClass": "external_side_effect_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "currentVerdict",
        "description": (
            "Mirrors VerifierResultV1.verdict so the unlock cannot "
            "fire when the verifier verdict drifts from passed; the "
            "policy primitive must never authorise an external side "
            "effect under a non-passed verdict."
        ),
    },
    {
        "policyId": "verdict-required",
        "policyClass": "regression_isolation_policy",
        "policyScope": "workload_independent_kernel",
        "unlockConditionRef": "requiredVerdict",
        "description": (
            "Declares passed as the only acceptable required verdict "
            "and forbids any first-workload regression verdict reuse."
        ),
    },
    {
        "policyId": "verdict-owner",
        "policyClass": "coordination_policy",
        "policyScope": "coordination_layer",
        "unlockConditionRef": "verdictOwner",
        "description": (
            "Pins the verdict owner to verifier-runtime-v1; the creator "
            "agent must not own the verdict that gates the unlock."
        ),
    },
]

EXPECTED_POLICY_COUNT = len(POLICY_BLUEPRINT)

INVARIANTS = [
    "PolicyV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype and from PolicyManifestV1.",
    "PolicyV1.policyItems[*].policyClass must lie in [permission_policy, approval_policy, delivery_policy, external_side_effect_policy, regression_isolation_policy, coordination_policy].",
    "PolicyV1.forbiddenPolicyClasses must enumerate [regression_result_policy, email_draft_policy, send_email_policy] and never intersect declared policyClasses.",
    "PolicyV1.policyItems[*].policyScope must lie in [workload_independent_kernel, workload_specific, coordination_layer]; every committed item must be workload_independent_kernel or coordination_layer.",
    "PolicyV1.policyItems[*].policyLifecycleState must lie in [drafted, active, deprecated, withdrawn]; every committed policy item must be active.",
    "PolicyV1.policyItems[*].requiredFlag must be false for every workload-independent kernel item; the contract-only MVP cannot flip a kernel-scope policy on.",
    "PolicyV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and the creator agent may only stage drafts.",
    "PolicyV1 must bind TestExecutionTaskSpecV1, IntentV1, RunV1, StepListV1, ToolCallListV1, CapabilityV1, CapabilityManifestV1, RunEventLogV1, ObservationListV1, EvidenceListV1, VerifierResultV1, DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1, and all five Agent Coordination Layer contracts by content hash.",
    "Every PolicyManifestV1.unlockConditions key must resolve into a PolicyV1.policyItems[*].unlockConditionRef; the unlock condition keys must equal the unique set of policy item references.",
    "PolicyV1 must not reuse regression-task-spec-v1, regression-result-artifact-v1, phase7_adapter_policy_manifest.json, post_mvp_policy_unlock_request_denied.json, the send_email capability, or any regression_result / email_draft / send_email field outside the declarative forbiddenFields list.",
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
            f"PolicyV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(f"PolicyV1 source artifact does not exist: {relative_path}")
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
                f"PolicyV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> dict[str, dict[str, Any]]:
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
    capability_kernel = _load_json(root / CAPABILITY_KERNEL_ARTIFACT_PATH)
    validate_capability_kernel_artifact(capability_kernel, root)
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
    intent = _load_json(root / INTENT_ARTIFACT_PATH)
    validate_intent_artifact(intent, root)
    return {
        "task_spec": task_spec,
        "capability_kernel": capability_kernel,
        "run_event_log": run_event_log,
        "observation_list": observation_list,
        "evidence_list": evidence_list,
        "verifier_result": verifier_result,
        "policy_manifest": policy_manifest,
        "run_artifact": run_artifact,
        "step_list": step_list,
        "tool_call_list": tool_call_list,
        "approval_decision": approval_decision,
        "intent": intent,
    }


def _build_policy_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, blueprint in enumerate(POLICY_BLUEPRINT):
        item: dict[str, Any] = {
            "schemaVersion": POLICY_ITEM_SCHEMA_VERSION,
            "sequence": index,
            "policyId": blueprint["policyId"],
            "policyClass": blueprint["policyClass"],
            "policyScope": blueprint["policyScope"],
            "policyLifecycleState": REQUIRED_POLICY_LIFECYCLE_STATE,
            "requiredFlag": False,
            "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
            "unlockConditionRef": blueprint["unlockConditionRef"],
            "permissionFlagOverrides": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
            "description": blueprint["description"],
        }
        items.append(item)
    return items


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


def _build_intent_binding(root: Path, intent: dict[str, Any]) -> dict[str, Any]:
    full_path = root / INTENT_ARTIFACT_PATH
    return {
        "intentRef": INTENT_ARTIFACT_PATH,
        "intentSchemaVersion": INTENT_ARTIFACT_SCHEMA_VERSION,
        "intentEnvelopeSchemaVersion": INTENT_ENVELOPE_SCHEMA_VERSION,
        "intentId": INTENT_ARTIFACT_ID,
        "intentIdentifier": intent["intentId"],
        "intentLifecycleState": intent["intentLifecycleState"],
        "intentContentHash": _stable_file_hash(full_path),
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


def _build_capability_kernel_binding(
    root: Path, capability_kernel: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / CAPABILITY_KERNEL_ARTIFACT_PATH
    return {
        "capabilityKernelRef": CAPABILITY_KERNEL_ARTIFACT_PATH,
        "capabilityKernelSchemaVersion": CAPABILITY_KERNEL_SCHEMA_VERSION,
        "capabilityKernelEnvelopeSchemaVersion": CAPABILITY_KERNEL_ENVELOPE_SCHEMA_VERSION,
        "capabilityKernelId": CAPABILITY_KERNEL_ARTIFACT_ID,
        "capabilityCount": capability_kernel["capabilityCount"],
        "capabilityKernelContentHash": _stable_file_hash(full_path),
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
    unlock = policy_manifest.get("unlockConditions", {})
    unlocked = bool(unlock.get("unlocked", False))
    unlock_condition_keys = sorted(unlock.keys())
    return {
        "policyManifestRef": POLICY_MANIFEST_ARTIFACT_PATH,
        "policyManifestSchemaVersion": POLICY_MANIFEST_SCHEMA_VERSION,
        "policyManifestEnvelopeSchemaVersion": POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "policyManifestId": POLICY_MANIFEST_ARTIFACT_ID,
        "unlocked": unlocked,
        "unlockConditionKeys": unlock_condition_keys,
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


def _build_unlock_condition_coverage(
    policy_items: list[dict[str, Any]], policy_manifest: dict[str, Any]
) -> dict[str, Any]:
    unlock_conditions = policy_manifest.get("unlockConditions", {})
    unlock_keys = sorted(unlock_conditions.keys())
    policy_refs = [item["unlockConditionRef"] for item in policy_items]
    unique_policy_refs = sorted(set(policy_refs))
    every_key_covered = all(key in policy_refs for key in unlock_keys)
    every_ref_resolves = all(ref in unlock_keys for ref in policy_refs)
    return {
        "policyManifestRef": POLICY_MANIFEST_ARTIFACT_PATH,
        "unlockConditionKeyCount": len(unlock_keys),
        "uniquePolicyItemRefCount": len(unique_policy_refs),
        "unlockConditionKeys": unlock_keys,
        "uniquePolicyItemRefs": unique_policy_refs,
        "policyItemRefsCovered": list(policy_refs),
        "everyUnlockConditionKeyCovered": every_key_covered,
        "everyPolicyItemReferencesValidKey": every_ref_resolves,
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


def build_policy_kernel_artifact(root: Path) -> dict[str, Any]:
    refs = _validate_referenced_artifacts(root)
    policy_items = _build_policy_items()

    payload: dict[str, Any] = {
        "schemaVersion": POLICY_KERNEL_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "policyItemSchemaVersion": POLICY_ITEM_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "policyCount": EXPECTED_POLICY_COUNT,
        "policyItems": policy_items,
        "policyClassDomain": list(POLICY_CLASS_DOMAIN),
        "forbiddenPolicyClasses": list(FORBIDDEN_POLICY_CLASSES),
        "policyScopeDomain": list(POLICY_SCOPE_DOMAIN),
        "allowedCommittedPolicyScopes": list(ALLOWED_COMMITTED_POLICY_SCOPES),
        "policyLifecycleStateDomain": list(POLICY_LIFECYCLE_STATE_DOMAIN),
        "requiredPolicyLifecycleState": REQUIRED_POLICY_LIFECYCLE_STATE,
        "verdictDomain": list(VERDICT_DOMAIN),
        "permissionFlagDomain": list(PERMISSION_FLAG_DOMAIN),
        "permissionFlags": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
        "taskSpecBinding": _build_task_spec_binding(root, refs["task_spec"]),
        "intentBinding": _build_intent_binding(root, refs["intent"]),
        "runBinding": _build_run_binding(root, refs["run_artifact"]),
        "stepListBinding": _build_step_list_binding(root, refs["step_list"]),
        "toolCallListBinding": _build_tool_call_list_binding(
            root, refs["tool_call_list"]
        ),
        "capabilityKernelBinding": _build_capability_kernel_binding(
            root, refs["capability_kernel"]
        ),
        "capabilityManifestBinding": _build_capability_manifest_binding(root),
        "runEventLogBinding": _build_run_event_log_binding(root, refs["run_event_log"]),
        "observationListBinding": _build_observation_list_binding(
            root, refs["observation_list"]
        ),
        "evidenceListBinding": _build_evidence_list_binding(
            root, refs["evidence_list"]
        ),
        "verifierResultBinding": _build_verifier_result_binding(
            root, refs["verifier_result"]
        ),
        "deliveryManifestBinding": _build_delivery_manifest_binding(root),
        "policyManifestBinding": _build_policy_manifest_binding(
            root, refs["policy_manifest"]
        ),
        "approvalDecisionBinding": _build_approval_decision_binding(
            root, refs["approval_decision"]
        ),
        "unlockConditionCoverage": _build_unlock_condition_coverage(
            policy_items, refs["policy_manifest"]
        ),
        "promotionConditions": _build_promotion_conditions(
            refs["verifier_result"], refs["run_event_log"], refs["policy_manifest"]
        ),
        "verifierExpectations": {
            **{flag: True for flag in REQUIRED_VERIFIER_FLAGS},
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERDICT_DOMAIN),
        },
        "regressionWorkloadIsolation": {
            "reusesRegressionPolicyArtifact": False,
            "reusesRegressionTaskSpec": False,
            "reusesRegressionResultArtifact": False,
            "reusesPhase7AdapterPolicyManifest": False,
            "reusesPolicyUnlockDenialFixture": False,
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
    validate_policy_kernel_artifact(payload, root)
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
        raise ValueError(f"PolicyV1 {label} must be an object")
    _require_fields(f"PolicyV1 {label}", binding, required_fields)
    if binding[ref_field] != expected_ref:
        raise ValueError(f"PolicyV1 {label}.{ref_field} must equal {expected_ref}")
    full_path = root / binding[ref_field]
    if binding[hash_field] != _stable_file_hash(full_path):
        raise ValueError(
            f"PolicyV1 {label}.{hash_field} must match the on-disk artifact"
        )


def _validate_policy_items(items: Any) -> None:
    if not isinstance(items, list) or len(items) != EXPECTED_POLICY_COUNT:
        raise ValueError(
            f"PolicyV1 policyItems must contain exactly {EXPECTED_POLICY_COUNT} entries"
        )
    seen_policy_ids: set[str] = set()
    seen_sequences: set[int] = set()
    seen_unlock_refs: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"PolicyV1 policyItems[{index}] must be an object")
        _require_fields(
            f"PolicyV1 policyItems[{index}]",
            item,
            [
                "schemaVersion",
                "sequence",
                "policyId",
                "policyClass",
                "policyScope",
                "policyLifecycleState",
                "requiredFlag",
                "verifierVerdictOwner",
                "unlockConditionRef",
                "permissionFlagOverrides",
                "description",
            ],
        )
        if item["schemaVersion"] != POLICY_ITEM_SCHEMA_VERSION:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].schemaVersion must equal {POLICY_ITEM_SCHEMA_VERSION}"
            )
        if item["sequence"] != index:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].sequence must equal {index}"
            )
        if item["sequence"] in seen_sequences:
            raise ValueError(
                f"PolicyV1 policyItems has duplicate sequence {item['sequence']}"
            )
        seen_sequences.add(item["sequence"])
        blueprint = POLICY_BLUEPRINT[index]
        if item["policyId"] != blueprint["policyId"]:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyId must equal {blueprint['policyId']}"
            )
        if item["policyId"] in seen_policy_ids:
            raise ValueError(
                f"PolicyV1 policyItems has duplicate policyId {item['policyId']}"
            )
        seen_policy_ids.add(item["policyId"])
        if item["policyClass"] in FORBIDDEN_POLICY_CLASSES:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyClass is forbidden: {item['policyClass']}"
            )
        if item["policyClass"] not in POLICY_CLASS_DOMAIN:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyClass outside workload-independent domain: {item['policyClass']}"
            )
        if item["policyClass"] != blueprint["policyClass"]:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyClass must equal {blueprint['policyClass']}"
            )
        if item["policyScope"] not in POLICY_SCOPE_DOMAIN:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyScope outside workload-independent domain: {item['policyScope']}"
            )
        if item["policyScope"] not in ALLOWED_COMMITTED_POLICY_SCOPES:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyScope must be one of {ALLOWED_COMMITTED_POLICY_SCOPES}"
            )
        if item["policyScope"] != blueprint["policyScope"]:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyScope must equal {blueprint['policyScope']}"
            )
        if item["policyLifecycleState"] not in POLICY_LIFECYCLE_STATE_DOMAIN:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyLifecycleState must be one of {POLICY_LIFECYCLE_STATE_DOMAIN}"
            )
        if item["policyLifecycleState"] != REQUIRED_POLICY_LIFECYCLE_STATE:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].policyLifecycleState must equal {REQUIRED_POLICY_LIFECYCLE_STATE}"
            )
        if item["requiredFlag"] is not False:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].requiredFlag must be false for workload-independent kernel policy"
            )
        if item["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].verifierVerdictOwner must equal {VERIFIER_VERDICT_OWNER}"
            )
        if item["unlockConditionRef"] != blueprint["unlockConditionRef"]:
            raise ValueError(
                f"PolicyV1 policyItems[{index}].unlockConditionRef must equal {blueprint['unlockConditionRef']}"
            )
        if item["unlockConditionRef"] in seen_unlock_refs:
            raise ValueError(
                f"PolicyV1 policyItems has duplicate unlockConditionRef {item['unlockConditionRef']}"
            )
        seen_unlock_refs.add(item["unlockConditionRef"])
        overrides = item["permissionFlagOverrides"]
        if not isinstance(overrides, dict) or set(overrides) != set(PERMISSION_FLAG_DOMAIN):
            raise ValueError(
                f"PolicyV1 policyItems[{index}].permissionFlagOverrides must declare every flag in {PERMISSION_FLAG_DOMAIN}"
            )
        for flag in PERMISSION_FLAG_DOMAIN:
            if overrides[flag] is not False:
                raise ValueError(
                    f"PolicyV1 policyItems[{index}].permissionFlagOverrides.{flag} must be false"
                )
        description = item["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValueError(
                f"PolicyV1 policyItems[{index}].description must be a non-empty string"
            )


def _validate_unlock_condition_coverage(
    coverage: Any,
    policy_items: list[dict[str, Any]],
    policy_manifest: dict[str, Any],
) -> None:
    if not isinstance(coverage, dict):
        raise ValueError("PolicyV1 unlockConditionCoverage must be an object")
    _require_fields(
        "PolicyV1 unlockConditionCoverage",
        coverage,
        [
            "policyManifestRef",
            "unlockConditionKeyCount",
            "uniquePolicyItemRefCount",
            "unlockConditionKeys",
            "uniquePolicyItemRefs",
            "policyItemRefsCovered",
            "everyUnlockConditionKeyCovered",
            "everyPolicyItemReferencesValidKey",
        ],
    )
    if coverage["policyManifestRef"] != POLICY_MANIFEST_ARTIFACT_PATH:
        raise ValueError(
            f"PolicyV1 unlockConditionCoverage.policyManifestRef must equal {POLICY_MANIFEST_ARTIFACT_PATH}"
        )
    unlock_keys = sorted(policy_manifest.get("unlockConditions", {}).keys())
    if coverage["unlockConditionKeys"] != unlock_keys:
        raise ValueError(
            "PolicyV1 unlockConditionCoverage.unlockConditionKeys must equal sorted PolicyManifestV1.unlockConditions keys"
        )
    if coverage["unlockConditionKeyCount"] != len(unlock_keys):
        raise ValueError(
            "PolicyV1 unlockConditionCoverage.unlockConditionKeyCount must equal the number of PolicyManifestV1.unlockConditions keys"
        )
    policy_refs = [item["unlockConditionRef"] for item in policy_items]
    if coverage["policyItemRefsCovered"] != policy_refs:
        raise ValueError(
            "PolicyV1 unlockConditionCoverage.policyItemRefsCovered must mirror policyItems order"
        )
    unique_refs = sorted(set(policy_refs))
    if coverage["uniquePolicyItemRefs"] != unique_refs:
        raise ValueError(
            "PolicyV1 unlockConditionCoverage.uniquePolicyItemRefs must equal sorted unique policy item refs"
        )
    if coverage["uniquePolicyItemRefCount"] != len(unique_refs):
        raise ValueError(
            "PolicyV1 unlockConditionCoverage.uniquePolicyItemRefCount must equal the unique policy item ref count"
        )
    if coverage["everyUnlockConditionKeyCovered"] is not True:
        raise ValueError(
            "PolicyV1 unlockConditionCoverage.everyUnlockConditionKeyCovered must be true"
        )
    if coverage["everyPolicyItemReferencesValidKey"] is not True:
        raise ValueError(
            "PolicyV1 unlockConditionCoverage.everyPolicyItemReferencesValidKey must be true"
        )
    missing_keys = [key for key in unlock_keys if key not in policy_refs]
    if missing_keys:
        raise ValueError(
            f"PolicyV1 policy items must cover every PolicyManifestV1.unlockConditions key; missing: {missing_keys}"
        )
    extra_refs = [ref for ref in policy_refs if ref not in unlock_keys]
    if extra_refs:
        raise ValueError(
            f"PolicyV1 unlockConditionRef must resolve into PolicyManifestV1.unlockConditions keys; extra: {extra_refs}"
        )


def _validate_promotion_conditions(
    promotion: dict[str, Any],
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> None:
    _require_fields(
        "PolicyV1 promotionConditions",
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
            f"PolicyV1 promotionConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_PROMOTION}"
        )
    if promotion["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "PolicyV1 promotionConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if promotion["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"PolicyV1 promotionConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if promotion["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"PolicyV1 promotionConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if promotion["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "PolicyV1 promotionConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if promotion["requiredPolicyUnlocked"] is not REQUIRED_POLICY_UNLOCKED:
        raise ValueError(
            "PolicyV1 promotionConditions.requiredPolicyUnlocked must be true"
        )
    if promotion["currentPolicyUnlocked"] is not expected_unlocked:
        raise ValueError(
            "PolicyV1 promotionConditions.currentPolicyUnlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_promoted = (
        promotion["currentVerdict"] == REQUIRED_VERDICT_FOR_PROMOTION
        and promotion["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and promotion["currentPolicyUnlocked"] is True
    )
    if promotion["promoted"] is not expected_promoted:
        raise ValueError(
            "PolicyV1 promotionConditions.promoted must be true only when verdict, run terminal state and policy unlock all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("PolicyV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("PolicyV1 sourceArtifacts entries must be objects")
        _require_fields(
            "PolicyV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(f"PolicyV1 sourceArtifacts contains unexpected role: {role}")
        if role in seen_roles:
            raise ValueError(f"PolicyV1 sourceArtifacts contains duplicate role: {role}")
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"PolicyV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(f"PolicyV1 source artifact does not exist: {path}")
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(f"PolicyV1 source hash mismatch for {path}")
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"PolicyV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_policy_kernel_artifact(
    manifest: dict[str, Any], root: Path
) -> None:
    _require_fields(
        "PolicyV1",
        manifest,
        [
            "schemaVersion",
            "artifactEnvelopeSchemaVersion",
            "policyItemSchemaVersion",
            "id",
            "generatedAt",
            "kind",
            "scope",
            "workloadType",
            "workloadCategory",
            "creatorAgent",
            "verifierVerdictOwner",
            "policyCount",
            "policyItems",
            "policyClassDomain",
            "forbiddenPolicyClasses",
            "policyScopeDomain",
            "allowedCommittedPolicyScopes",
            "policyLifecycleStateDomain",
            "requiredPolicyLifecycleState",
            "verdictDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "taskSpecBinding",
            "intentBinding",
            "runBinding",
            "stepListBinding",
            "toolCallListBinding",
            "capabilityKernelBinding",
            "capabilityManifestBinding",
            "runEventLogBinding",
            "observationListBinding",
            "evidenceListBinding",
            "verifierResultBinding",
            "deliveryManifestBinding",
            "policyManifestBinding",
            "approvalDecisionBinding",
            "unlockConditionCoverage",
            "promotionConditions",
            "verifierExpectations",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != POLICY_KERNEL_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyV1 schemaVersion must be {POLICY_KERNEL_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["policyItemSchemaVersion"] != POLICY_ITEM_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyV1 policyItemSchemaVersion must be {POLICY_ITEM_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"PolicyV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"PolicyV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"PolicyV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"PolicyV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"PolicyV1 workloadType must be {WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(f"PolicyV1 workloadCategory must be {WORKLOAD_CATEGORY}")
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"PolicyV1 creatorAgent must be {CREATOR_AGENT}")
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"PolicyV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; creator must not own the verdict"
        )

    if manifest["policyCount"] != EXPECTED_POLICY_COUNT:
        raise ValueError(
            f"PolicyV1 policyCount must equal {EXPECTED_POLICY_COUNT}"
        )
    if manifest["policyClassDomain"] != list(POLICY_CLASS_DOMAIN):
        raise ValueError(
            f"PolicyV1 policyClassDomain must equal {POLICY_CLASS_DOMAIN}"
        )
    if manifest["forbiddenPolicyClasses"] != list(FORBIDDEN_POLICY_CLASSES):
        raise ValueError(
            f"PolicyV1 forbiddenPolicyClasses must equal {FORBIDDEN_POLICY_CLASSES}"
        )
    if manifest["policyScopeDomain"] != list(POLICY_SCOPE_DOMAIN):
        raise ValueError(
            f"PolicyV1 policyScopeDomain must equal {POLICY_SCOPE_DOMAIN}"
        )
    if manifest["allowedCommittedPolicyScopes"] != list(ALLOWED_COMMITTED_POLICY_SCOPES):
        raise ValueError(
            f"PolicyV1 allowedCommittedPolicyScopes must equal {ALLOWED_COMMITTED_POLICY_SCOPES}"
        )
    if manifest["policyLifecycleStateDomain"] != list(POLICY_LIFECYCLE_STATE_DOMAIN):
        raise ValueError(
            f"PolicyV1 policyLifecycleStateDomain must equal {POLICY_LIFECYCLE_STATE_DOMAIN}"
        )
    if manifest["requiredPolicyLifecycleState"] != REQUIRED_POLICY_LIFECYCLE_STATE:
        raise ValueError(
            f"PolicyV1 requiredPolicyLifecycleState must equal {REQUIRED_POLICY_LIFECYCLE_STATE}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(f"PolicyV1 verdictDomain must equal {VERDICT_DOMAIN}")
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"PolicyV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )
    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"PolicyV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(f"PolicyV1 permissionFlags.{flag} must be false")

    overlap = set(manifest["forbiddenPolicyClasses"]).intersection(
        pol["policyClass"] for pol in manifest["policyItems"]
    )
    if overlap:
        raise ValueError(
            f"PolicyV1 forbiddenPolicyClasses must not intersect declared policyItems[*].policyClass: {sorted(overlap)}"
        )

    task_spec = _load_json(root / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH)
    capability_kernel = _load_json(root / CAPABILITY_KERNEL_ARTIFACT_PATH)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    observation_list = _load_json(root / OBSERVATION_LIST_ARTIFACT_PATH)
    evidence_list = _load_json(root / EVIDENCE_LIST_ARTIFACT_PATH)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    run_artifact = _load_json(root / RUN_ARTIFACT_PATH)
    step_list = _load_json(root / STEP_LIST_ARTIFACT_PATH)
    tool_call_list = _load_json(root / TOOL_CALL_LIST_ARTIFACT_PATH)
    intent = _load_json(root / INTENT_ARTIFACT_PATH)

    _validate_policy_items(manifest["policyItems"])

    _validate_binding_common(
        "taskSpecBinding",
        manifest["taskSpecBinding"],
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
    if manifest["taskSpecBinding"]["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyV1 taskSpecBinding.taskSpecSchemaVersion must equal {TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression-task-spec-v1 reuse is forbidden"
        )
    if manifest["taskSpecBinding"]["taskSpecWorkloadType"] != TASK_SPEC_WORKLOAD_TYPE:
        raise ValueError(
            f"PolicyV1 taskSpecBinding.taskSpecWorkloadType must equal {TASK_SPEC_WORKLOAD_TYPE}"
        )
    if manifest["taskSpecBinding"]["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"PolicyV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    if manifest["taskSpecBinding"]["taskSpecWorkloadType"] != task_spec["workloadType"]:
        raise ValueError(
            "PolicyV1 taskSpecBinding.taskSpecWorkloadType must equal TestExecutionTaskSpecV1.workloadType"
        )

    _validate_binding_common(
        "intentBinding",
        manifest["intentBinding"],
        [
            "intentRef",
            "intentSchemaVersion",
            "intentEnvelopeSchemaVersion",
            "intentId",
            "intentIdentifier",
            "intentLifecycleState",
            "intentContentHash",
        ],
        ref_field="intentRef",
        expected_ref=INTENT_ARTIFACT_PATH,
        hash_field="intentContentHash",
        root=root,
    )
    if manifest["intentBinding"]["intentSchemaVersion"] != INTENT_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyV1 intentBinding.intentSchemaVersion must equal {INTENT_ARTIFACT_SCHEMA_VERSION}"
        )
    if manifest["intentBinding"]["intentId"] != INTENT_ARTIFACT_ID:
        raise ValueError(
            f"PolicyV1 intentBinding.intentId must equal {INTENT_ARTIFACT_ID}"
        )
    if manifest["intentBinding"]["intentIdentifier"] != intent["intentId"]:
        raise ValueError(
            "PolicyV1 intentBinding.intentIdentifier must equal IntentV1.intentId"
        )
    if manifest["intentBinding"]["intentLifecycleState"] != intent["intentLifecycleState"]:
        raise ValueError(
            "PolicyV1 intentBinding.intentLifecycleState must equal IntentV1.intentLifecycleState"
        )

    _validate_binding_common(
        "runBinding",
        manifest["runBinding"],
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
    if manifest["runBinding"]["runIdentifier"] != run_artifact["runId"]:
        raise ValueError(
            "PolicyV1 runBinding.runIdentifier must equal RunV1.runId"
        )
    if manifest["runBinding"]["runState"] != run_artifact["runState"]:
        raise ValueError(
            "PolicyV1 runBinding.runState must equal RunV1.runState"
        )

    _validate_binding_common(
        "stepListBinding",
        manifest["stepListBinding"],
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
    if manifest["stepListBinding"]["stepCount"] != step_list["stepCount"]:
        raise ValueError(
            "PolicyV1 stepListBinding.stepCount must equal StepListV1.stepCount"
        )

    _validate_binding_common(
        "toolCallListBinding",
        manifest["toolCallListBinding"],
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
    if manifest["toolCallListBinding"]["toolCallCount"] != tool_call_list["toolCallCount"]:
        raise ValueError(
            "PolicyV1 toolCallListBinding.toolCallCount must equal ToolCallListV1.toolCallCount"
        )

    _validate_binding_common(
        "capabilityKernelBinding",
        manifest["capabilityKernelBinding"],
        [
            "capabilityKernelRef",
            "capabilityKernelSchemaVersion",
            "capabilityKernelEnvelopeSchemaVersion",
            "capabilityKernelId",
            "capabilityCount",
            "capabilityKernelContentHash",
        ],
        ref_field="capabilityKernelRef",
        expected_ref=CAPABILITY_KERNEL_ARTIFACT_PATH,
        hash_field="capabilityKernelContentHash",
        root=root,
    )
    if manifest["capabilityKernelBinding"]["capabilityKernelSchemaVersion"] != CAPABILITY_KERNEL_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyV1 capabilityKernelBinding.capabilityKernelSchemaVersion must equal {CAPABILITY_KERNEL_SCHEMA_VERSION}"
        )
    if manifest["capabilityKernelBinding"]["capabilityKernelId"] != CAPABILITY_KERNEL_ARTIFACT_ID:
        raise ValueError(
            f"PolicyV1 capabilityKernelBinding.capabilityKernelId must equal {CAPABILITY_KERNEL_ARTIFACT_ID}"
        )
    if manifest["capabilityKernelBinding"]["capabilityCount"] != capability_kernel["capabilityCount"]:
        raise ValueError(
            "PolicyV1 capabilityKernelBinding.capabilityCount must equal CapabilityV1.capabilityCount"
        )

    _validate_binding_common(
        "capabilityManifestBinding",
        manifest["capabilityManifestBinding"],
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
    if manifest["capabilityManifestBinding"]["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal {CAPABILITY_MANIFEST_SCHEMA_VERSION}"
        )
    if manifest["capabilityManifestBinding"]["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"PolicyV1 capabilityManifestBinding.capabilityManifestId must equal {CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )

    _validate_binding_common(
        "runEventLogBinding",
        manifest["runEventLogBinding"],
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
    if manifest["runEventLogBinding"]["eventCount"] != run_event_log["eventCount"]:
        raise ValueError(
            "PolicyV1 runEventLogBinding.eventCount must equal RunEventLogV1.eventCount"
        )
    if manifest["runEventLogBinding"]["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "PolicyV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )

    _validate_binding_common(
        "observationListBinding",
        manifest["observationListBinding"],
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
    if manifest["observationListBinding"]["observationItemCount"] != observation_list["observationItemCount"]:
        raise ValueError(
            "PolicyV1 observationListBinding.observationItemCount must equal ObservationListV1.observationItemCount"
        )

    _validate_binding_common(
        "evidenceListBinding",
        manifest["evidenceListBinding"],
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
    if manifest["evidenceListBinding"]["evidenceItemCount"] != evidence_list["evidenceItemCount"]:
        raise ValueError(
            "PolicyV1 evidenceListBinding.evidenceItemCount must equal EvidenceListV1.evidenceItemCount"
        )

    _validate_binding_common(
        "verifierResultBinding",
        manifest["verifierResultBinding"],
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
    if manifest["verifierResultBinding"]["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"PolicyV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}"
        )
    if manifest["verifierResultBinding"]["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "PolicyV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )

    _validate_binding_common(
        "deliveryManifestBinding",
        manifest["deliveryManifestBinding"],
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
    if manifest["deliveryManifestBinding"]["deliveryManifestId"] != DELIVERY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"PolicyV1 deliveryManifestBinding.deliveryManifestId must equal {DELIVERY_MANIFEST_ARTIFACT_ID}"
        )

    _validate_binding_common(
        "policyManifestBinding",
        manifest["policyManifestBinding"],
        [
            "policyManifestRef",
            "policyManifestSchemaVersion",
            "policyManifestEnvelopeSchemaVersion",
            "policyManifestId",
            "unlocked",
            "unlockConditionKeys",
            "policyManifestContentHash",
        ],
        ref_field="policyManifestRef",
        expected_ref=POLICY_MANIFEST_ARTIFACT_PATH,
        hash_field="policyManifestContentHash",
        root=root,
    )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if manifest["policyManifestBinding"]["unlocked"] is not expected_unlocked:
        raise ValueError(
            "PolicyV1 policyManifestBinding.unlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_keys = sorted(policy_manifest.get("unlockConditions", {}).keys())
    if manifest["policyManifestBinding"]["unlockConditionKeys"] != expected_keys:
        raise ValueError(
            "PolicyV1 policyManifestBinding.unlockConditionKeys must equal sorted PolicyManifestV1.unlockConditions keys"
        )

    _validate_binding_common(
        "approvalDecisionBinding",
        manifest["approvalDecisionBinding"],
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
    if manifest["approvalDecisionBinding"]["approvalDecisionSchemaVersion"] != HUMAN_APPROVAL_DECISION_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyV1 approvalDecisionBinding.approvalDecisionSchemaVersion must equal {HUMAN_APPROVAL_DECISION_SCHEMA_VERSION}"
        )
    if manifest["approvalDecisionBinding"]["approvalDecisionId"] != approval_decision["id"]:
        raise ValueError(
            "PolicyV1 approvalDecisionBinding.approvalDecisionId must equal HumanApprovalDecisionV1.id"
        )
    expected_granted = bool(approval_decision.get("decision", {}).get("approvalGranted", False))
    if manifest["approvalDecisionBinding"]["approvalGranted"] is not expected_granted:
        raise ValueError(
            "PolicyV1 approvalDecisionBinding.approvalGranted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )

    _validate_unlock_condition_coverage(
        manifest["unlockConditionCoverage"], manifest["policyItems"], policy_manifest
    )

    _validate_promotion_conditions(
        manifest["promotionConditions"],
        verifier_result,
        run_event_log,
        policy_manifest,
    )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "PolicyV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(f"PolicyV1 verifierExpectations.{flag} must be true")
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"PolicyV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"PolicyV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "PolicyV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionPolicyArtifact",
            "reusesRegressionTaskSpec",
            "reusesRegressionResultArtifact",
            "reusesPhase7AdapterPolicyManifest",
            "reusesPolicyUnlockDenialFixture",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionPolicyArtifact"] is not False:
        raise ValueError(
            "PolicyV1 must not reuse any first-workload regression policy artifact"
        )
    if isolation["reusesRegressionTaskSpec"] is not False:
        raise ValueError("PolicyV1 must not reuse the regression-task-spec-v1 schema")
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError("PolicyV1 must not reuse RegressionResultArtifactV1")
    if isolation["reusesPhase7AdapterPolicyManifest"] is not False:
        raise ValueError("PolicyV1 must not reuse phase7_adapter_policy_manifest.json")
    if isolation["reusesPolicyUnlockDenialFixture"] is not False:
        raise ValueError(
            "PolicyV1 must not reuse post_mvp_policy_unlock_request_denied.json"
        )
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError("PolicyV1 must not reuse the send_email capability")
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"PolicyV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"PolicyV1 must not embed regression/email field {term} outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"PolicyV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            f"PolicyV1 coordinationBinding must include {sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"PolicyV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 6:
        raise ValueError(
            "PolicyV1 invariants must declare at least six workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="policy-kernel")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_policy_kernel_artifact(root)
        _write_json(args.out, manifest)
        print(f"Wrote PolicyV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_policy_kernel_artifact(manifest, root)
        print(f"Validated PolicyV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

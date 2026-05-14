"""CapabilityV1 / capability-v1 ArtifactV1 subtype contract.

This module defines a workload-independent ``CapabilityV1`` ArtifactV1
subtype that captures the canonical OS-kernel ``Capability`` primitive
for any engineering workload. The artifact is a static, machine-
verifiable contract: no capability is invoked, no real runtime is
called, no external side effect is triggered.

``CapabilityV1`` is intentionally distinct from the workload-specific
``CapabilityManifestV1`` (which catalogues the runtime capability
definitions for the Test Execution / Failure Triage workload). Where
``CapabilityManifestV1`` answers *what does each capability look like
inside this workload*, ``CapabilityV1`` answers *what is the canonical
shape of a capability primitive that any workload can reuse*: every
``capabilityItem`` declares ``capabilityId`` /
``capabilityClass`` / ``sideEffectClass`` / ``inputSchemaRef`` /
``outputSchemaRef`` / ``sourceAgentDomain`` /
``permissionFlagOverrides`` / ``verifierVerdictOwner`` /
``capabilityLifecycleState`` from the workload-independent
vocabulary.

Invariants enforced by ``validate_capability_kernel_artifact``:

- ``CapabilityV1`` is an ArtifactV1 subtype
  (``artifactEnvelopeSchemaVersion = artifact-v1``) joining the existing
  fourteen subtypes; ``kind`` must be ``CapabilityV1`` and
  ``schemaVersion`` must be ``capability-v1``.
- ``capabilityClass`` must lie in ``[read_only_inspection,
  evidence_collection, artifact_writing, verifier_check,
  human_approval_request]``; ``[external_communication,
  repository_mutation, release_or_deploy,
  gui_or_browser_or_desktop_call, public_access]`` are explicitly
  forbidden.
- ``sideEffectClass`` must lie in ``[read_only, evidence_writer,
  artifact_writer, verifier_check]``; external / email_send_call /
  release_or_deploy / repository_mutation /
  gui_or_browser_or_desktop_call / public_access are forbidden.
- ``capabilityLifecycleState`` must lie in ``[drafted, registered,
  deprecated, withdrawn]``; every committed capability item must be
  ``registered``.
- Every ``ToolCallListV1.toolCallItems[*].capabilityRef`` must resolve
  into a ``CapabilityV1.capabilityItems[*].capabilityId``; the
  capability ids must equal the unique set of tool-call capability refs
  with no extra or missing capability id.
- ``CapabilityV1`` binds the upstream thirteen workload artifacts
  (TestExecutionTaskSpecV1, IntentV1, RunV1, StepListV1,
  ToolCallListV1, CapabilityManifestV1, RunEventLogV1,
  ObservationListV1, EvidenceListV1, VerifierResultV1,
  DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1) plus
  the five Agent Coordination Layer contracts by content hash.
- The six workload-independent permission flags
  (``externalSideEffectsAllowed`` / ``repositoryMutationAllowed`` /
  ``externalCommunicationAllowed`` / ``releaseOrDeploymentAllowed`` /
  ``guiOrBrowserOrDesktopCallAllowed`` / ``publicAccessAllowed``) are
  forced to ``false``.
- Regression-workload isolation forbids ``regression_result`` /
  ``email_draft`` / ``send_email`` / ``regression-task-spec-v1`` /
  ``regression-result-artifact-v1`` reuse and tracks
  ``reusesRegressionCapabilityArtifact=false``.
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


CAPABILITY_KERNEL_SCHEMA_VERSION = "capability-v1"
CAPABILITY_ITEM_SCHEMA_VERSION = "capability-item-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "CapabilityV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-capability-v1-kernel-contract"
CAPABILITY_KERNEL_ARTIFACT_PATH = (
    "artifacts/capabilities/post_mvp_capability_v1_catalog.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "workload_independent_capability_v1_kernel_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

CAPABILITY_CLASS_DOMAIN = [
    "read_only_inspection",
    "evidence_collection",
    "artifact_writing",
    "verifier_check",
    "human_approval_request",
]
FORBIDDEN_CAPABILITY_CLASSES = [
    "external_communication",
    "repository_mutation",
    "release_or_deploy",
    "gui_or_browser_or_desktop_call",
    "public_access",
]

SIDE_EFFECT_CLASS_DOMAIN = [
    "read_only",
    "evidence_writer",
    "artifact_writer",
    "verifier_check",
]
FORBIDDEN_SIDE_EFFECT_CLASSES = [
    "external",
    "email_send_call",
    "release_or_deploy",
    "repository_mutation",
    "gui_or_browser_or_desktop_call",
    "public_access",
]

SOURCE_AGENT_DOMAIN = ["creator_agent", "verifier-runtime-v1"]

CAPABILITY_LIFECYCLE_STATE_DOMAIN = [
    "drafted",
    "registered",
    "deprecated",
    "withdrawn",
]
REQUIRED_CAPABILITY_LIFECYCLE_STATE = "registered"

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
    "mustValidateCapabilityClassDomain",
    "mustValidateForbiddenCapabilityClasses",
    "mustValidateSideEffectClassDomain",
    "mustValidateForbiddenSideEffectClasses",
    "mustValidateCapabilityLifecycleStateDomain",
    "mustValidateSourceAgentDomain",
    "mustValidatePermissionFlags",
    "mustValidatePermissionFlagOverrides",
    "mustValidateTaskSpecBinding",
    "mustValidateIntentBinding",
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
    "mustValidateToolCallCoverage",
    "mustValidatePromotionConditions",
    "creatorMustNotOwnVerdict",
]


# Deterministic CapabilityV1 blueprint: one entry per unique workload-
# independent capability primitive referenced by
# ``ToolCallListV1.toolCallItems[*].capabilityRef``. Each blueprint
# entry uses only workload-independent vocabulary: capabilityClass,
# sideEffectClass, sourceAgentDomain, capabilityLifecycleState and
# input/output schema refs that point at the workload-specific
# ``CapabilityManifestV1`` definitions through stable schema names.
CAPABILITY_BLUEPRINT: list[dict[str, Any]] = [
    {
        "capabilityId": "read_test_execution_result",
        "capabilityClass": "read_only_inspection",
        "sideEffectClass": "read_only",
        "inputSchemaRef": "ReadTestExecutionResultInputV1",
        "outputSchemaRef": "ReadTestExecutionResultOutputV1",
        "sourceAgentDomain": ["creator_agent"],
        "description": (
            "Read a recorded TestExecutionResultV1 artifact by content "
            "hash without modifying it."
        ),
    },
    {
        "capabilityId": "collect_test_failure_evidence",
        "capabilityClass": "evidence_collection",
        "sideEffectClass": "evidence_writer",
        "inputSchemaRef": "CollectTestFailureEvidenceInputV1",
        "outputSchemaRef": "CollectTestFailureEvidenceOutputV1",
        "sourceAgentDomain": ["creator_agent"],
        "description": (
            "Read referenced diagnostic bundles bound to TestExecution"
            "ResultV1 evidence ids; emits EvidenceListV1 entries only."
        ),
    },
    {
        "capabilityId": "classify_test_failure",
        "capabilityClass": "read_only_inspection",
        "sideEffectClass": "read_only",
        "inputSchemaRef": "ClassifyTestFailureInputV1",
        "outputSchemaRef": "ClassifyTestFailureOutputV1",
        "sourceAgentDomain": ["creator_agent"],
        "description": (
            "Classify a failed test case using only bound evidence; the "
            "verifier owns the final verdict."
        ),
    },
    {
        "capabilityId": "write_artifact",
        "capabilityClass": "artifact_writing",
        "sideEffectClass": "artifact_writer",
        "inputSchemaRef": "WriteArtifactInputV1",
        "outputSchemaRef": "WriteArtifactOutputV1",
        "sourceAgentDomain": ["creator_agent"],
        "description": (
            "Write the workload-independent artifact bundle "
            "(TestExecutionResultV1, FailureTriageReportV1, "
            "VerifierResultV1) to the local artifact directory only."
        ),
    },
    {
        "capabilityId": "__run_kernel__",
        "capabilityClass": "verifier_check",
        "sideEffectClass": "verifier_check",
        "inputSchemaRef": "VerifierRunInputV1",
        "outputSchemaRef": "VerifierRunOutputV1",
        "sourceAgentDomain": ["verifier-runtime-v1"],
        "description": (
            "Run the workload-independent verifier-runtime-v1 verdict "
            "loop over a VerifierResultV1 artifact."
        ),
    },
]

EXPECTED_CAPABILITY_COUNT = len(CAPABILITY_BLUEPRINT)

INVARIANTS = [
    "CapabilityV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype and from CapabilityManifestV1.",
    "CapabilityV1.capabilityItems[*].capabilityClass must lie in [read_only_inspection, evidence_collection, artifact_writing, verifier_check, human_approval_request].",
    "CapabilityV1.forbiddenCapabilityClasses must enumerate [external_communication, repository_mutation, release_or_deploy, gui_or_browser_or_desktop_call, public_access] and never intersect declared capabilityClasses.",
    "CapabilityV1.capabilityItems[*].sideEffectClass must lie in [read_only, evidence_writer, artifact_writer, verifier_check]; external / email_send_call / release_or_deploy / repository_mutation / gui_or_browser_or_desktop_call / public_access are forbidden.",
    "CapabilityV1.capabilityItems[*].capabilityLifecycleState must lie in [drafted, registered, deprecated, withdrawn]; every committed capability item must be registered.",
    "CapabilityV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and the creator agent may only stage drafts.",
    "CapabilityV1 must bind TestExecutionTaskSpecV1, IntentV1, RunV1, StepListV1, ToolCallListV1, CapabilityManifestV1, RunEventLogV1, ObservationListV1, EvidenceListV1, VerifierResultV1, DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1, and all five Agent Coordination Layer contracts by content hash.",
    "Every ToolCallListV1.toolCallItems[*].capabilityRef must resolve into a CapabilityV1.capabilityItems[*].capabilityId; the capability ids must equal the unique tool-call capability ref set.",
    "CapabilityV1 must not reuse regression-task-spec-v1, regression-result-artifact-v1, the send_email capability, or any regression_result / email_draft / send_email field outside the declarative forbiddenFields list.",
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
            f"CapabilityV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(f"CapabilityV1 source artifact does not exist: {relative_path}")
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
                f"CapabilityV1 coordination binding is missing artifact: {relative_path}"
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


def _build_capability_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, blueprint in enumerate(CAPABILITY_BLUEPRINT):
        item: dict[str, Any] = {
            "schemaVersion": CAPABILITY_ITEM_SCHEMA_VERSION,
            "sequence": index,
            "capabilityId": blueprint["capabilityId"],
            "capabilityClass": blueprint["capabilityClass"],
            "sideEffectClass": blueprint["sideEffectClass"],
            "inputSchemaRef": blueprint["inputSchemaRef"],
            "outputSchemaRef": blueprint["outputSchemaRef"],
            "sourceAgentDomain": list(blueprint["sourceAgentDomain"]),
            "permissionFlagOverrides": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
            "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
            "capabilityLifecycleState": REQUIRED_CAPABILITY_LIFECYCLE_STATE,
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


def _build_tool_call_coverage(
    capability_items: list[dict[str, Any]], tool_call_list: dict[str, Any]
) -> dict[str, Any]:
    capability_ids = [item["capabilityId"] for item in capability_items]
    tool_call_refs = [
        item["capabilityRef"] for item in tool_call_list.get("toolCallItems", [])
    ]
    unique_tool_call_refs = sorted(set(tool_call_refs))
    every_ref_resolved = all(ref in capability_ids for ref in tool_call_refs)
    every_capability_used = all(cid in tool_call_refs for cid in capability_ids)
    return {
        "toolCallListRef": TOOL_CALL_LIST_ARTIFACT_PATH,
        "toolCallCount": tool_call_list.get("toolCallCount"),
        "uniqueCapabilityRefCount": len(unique_tool_call_refs),
        "capabilityIdsCovered": list(capability_ids),
        "uniqueToolCallCapabilityRefs": unique_tool_call_refs,
        "everyToolCallRefResolved": every_ref_resolved,
        "everyCapabilityItemUsed": every_capability_used,
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


def build_capability_kernel_artifact(root: Path) -> dict[str, Any]:
    refs = _validate_referenced_artifacts(root)
    capability_items = _build_capability_items()

    payload: dict[str, Any] = {
        "schemaVersion": CAPABILITY_KERNEL_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "capabilityItemSchemaVersion": CAPABILITY_ITEM_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "capabilityCount": EXPECTED_CAPABILITY_COUNT,
        "capabilityItems": capability_items,
        "capabilityClassDomain": list(CAPABILITY_CLASS_DOMAIN),
        "forbiddenCapabilityClasses": list(FORBIDDEN_CAPABILITY_CLASSES),
        "sideEffectClassDomain": list(SIDE_EFFECT_CLASS_DOMAIN),
        "forbiddenSideEffectClasses": list(FORBIDDEN_SIDE_EFFECT_CLASSES),
        "sourceAgentDomain": list(SOURCE_AGENT_DOMAIN),
        "capabilityLifecycleStateDomain": list(CAPABILITY_LIFECYCLE_STATE_DOMAIN),
        "requiredCapabilityLifecycleState": REQUIRED_CAPABILITY_LIFECYCLE_STATE,
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
        "toolCallCoverage": _build_tool_call_coverage(
            capability_items, refs["tool_call_list"]
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
            "reusesRegressionCapabilityArtifact": False,
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
    validate_capability_kernel_artifact(payload, root)
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
        raise ValueError(f"CapabilityV1 {label} must be an object")
    _require_fields(f"CapabilityV1 {label}", binding, required_fields)
    if binding[ref_field] != expected_ref:
        raise ValueError(f"CapabilityV1 {label}.{ref_field} must equal {expected_ref}")
    full_path = root / binding[ref_field]
    if binding[hash_field] != _stable_file_hash(full_path):
        raise ValueError(
            f"CapabilityV1 {label}.{hash_field} must match the on-disk artifact"
        )


def _validate_capability_items(items: Any, tool_call_list: dict[str, Any]) -> None:
    if not isinstance(items, list) or len(items) != EXPECTED_CAPABILITY_COUNT:
        raise ValueError(
            f"CapabilityV1 capabilityItems must contain exactly {EXPECTED_CAPABILITY_COUNT} entries"
        )
    seen_capability_ids: set[str] = set()
    seen_sequences: set[int] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}] must be an object"
            )
        _require_fields(
            f"CapabilityV1 capabilityItems[{index}]",
            item,
            [
                "schemaVersion",
                "sequence",
                "capabilityId",
                "capabilityClass",
                "sideEffectClass",
                "inputSchemaRef",
                "outputSchemaRef",
                "sourceAgentDomain",
                "permissionFlagOverrides",
                "verifierVerdictOwner",
                "capabilityLifecycleState",
                "description",
            ],
        )
        if item["schemaVersion"] != CAPABILITY_ITEM_SCHEMA_VERSION:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].schemaVersion must equal {CAPABILITY_ITEM_SCHEMA_VERSION}"
            )
        if item["sequence"] != index:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].sequence must equal {index}"
            )
        if item["sequence"] in seen_sequences:
            raise ValueError(
                f"CapabilityV1 capabilityItems has duplicate sequence {item['sequence']}"
            )
        seen_sequences.add(item["sequence"])
        blueprint = CAPABILITY_BLUEPRINT[index]
        if item["capabilityId"] != blueprint["capabilityId"]:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].capabilityId must equal {blueprint['capabilityId']}"
            )
        if item["capabilityId"] in seen_capability_ids:
            raise ValueError(
                f"CapabilityV1 capabilityItems has duplicate capabilityId {item['capabilityId']}"
            )
        seen_capability_ids.add(item["capabilityId"])
        if item["capabilityClass"] in FORBIDDEN_CAPABILITY_CLASSES:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].capabilityClass is forbidden: {item['capabilityClass']}"
            )
        if item["capabilityClass"] not in CAPABILITY_CLASS_DOMAIN:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].capabilityClass outside workload-independent domain: {item['capabilityClass']}"
            )
        if item["capabilityClass"] != blueprint["capabilityClass"]:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].capabilityClass must equal {blueprint['capabilityClass']}"
            )
        if item["sideEffectClass"] in FORBIDDEN_SIDE_EFFECT_CLASSES:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].sideEffectClass is forbidden: {item['sideEffectClass']}"
            )
        if item["sideEffectClass"] not in SIDE_EFFECT_CLASS_DOMAIN:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].sideEffectClass outside workload-independent domain: {item['sideEffectClass']}"
            )
        if item["sideEffectClass"] != blueprint["sideEffectClass"]:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].sideEffectClass must equal {blueprint['sideEffectClass']}"
            )
        if item["inputSchemaRef"] != blueprint["inputSchemaRef"]:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].inputSchemaRef must equal {blueprint['inputSchemaRef']}"
            )
        if item["outputSchemaRef"] != blueprint["outputSchemaRef"]:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].outputSchemaRef must equal {blueprint['outputSchemaRef']}"
            )
        source_domain = item["sourceAgentDomain"]
        if not isinstance(source_domain, list) or not source_domain:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].sourceAgentDomain must be a non-empty list"
            )
        for agent in source_domain:
            if agent not in SOURCE_AGENT_DOMAIN:
                raise ValueError(
                    f"CapabilityV1 capabilityItems[{index}].sourceAgentDomain contains agent outside workload-independent domain: {agent}"
                )
        if source_domain != list(blueprint["sourceAgentDomain"]):
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].sourceAgentDomain must equal {blueprint['sourceAgentDomain']}"
            )
        overrides = item["permissionFlagOverrides"]
        if not isinstance(overrides, dict) or set(overrides) != set(PERMISSION_FLAG_DOMAIN):
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].permissionFlagOverrides must declare every flag in {PERMISSION_FLAG_DOMAIN}"
            )
        for flag in PERMISSION_FLAG_DOMAIN:
            if overrides[flag] is not False:
                raise ValueError(
                    f"CapabilityV1 capabilityItems[{index}].permissionFlagOverrides.{flag} must be false"
                )
        if item["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].verifierVerdictOwner must equal {VERIFIER_VERDICT_OWNER}"
            )
        if item["capabilityLifecycleState"] not in CAPABILITY_LIFECYCLE_STATE_DOMAIN:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].capabilityLifecycleState must be one of {CAPABILITY_LIFECYCLE_STATE_DOMAIN}"
            )
        if item["capabilityLifecycleState"] != REQUIRED_CAPABILITY_LIFECYCLE_STATE:
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].capabilityLifecycleState must equal {REQUIRED_CAPABILITY_LIFECYCLE_STATE}"
            )
        description = item["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValueError(
                f"CapabilityV1 capabilityItems[{index}].description must be a non-empty string"
            )

    capability_ids = [item["capabilityId"] for item in items]
    tool_call_refs = [
        tc["capabilityRef"] for tc in tool_call_list.get("toolCallItems", [])
    ]
    unresolved = [ref for ref in tool_call_refs if ref not in capability_ids]
    if unresolved:
        raise ValueError(
            f"CapabilityV1 capabilityItems must resolve every ToolCallListV1 capabilityRef; unresolved: {unresolved}"
        )
    unused = [cid for cid in capability_ids if cid not in tool_call_refs]
    if unused:
        raise ValueError(
            f"CapabilityV1 capabilityItems must equal the unique ToolCallListV1 capabilityRef set; unused: {unused}"
        )


def _validate_tool_call_coverage(
    coverage: Any,
    capability_items: list[dict[str, Any]],
    tool_call_list: dict[str, Any],
) -> None:
    if not isinstance(coverage, dict):
        raise ValueError("CapabilityV1 toolCallCoverage must be an object")
    _require_fields(
        "CapabilityV1 toolCallCoverage",
        coverage,
        [
            "toolCallListRef",
            "toolCallCount",
            "uniqueCapabilityRefCount",
            "capabilityIdsCovered",
            "uniqueToolCallCapabilityRefs",
            "everyToolCallRefResolved",
            "everyCapabilityItemUsed",
        ],
    )
    if coverage["toolCallListRef"] != TOOL_CALL_LIST_ARTIFACT_PATH:
        raise ValueError(
            f"CapabilityV1 toolCallCoverage.toolCallListRef must equal {TOOL_CALL_LIST_ARTIFACT_PATH}"
        )
    if coverage["toolCallCount"] != tool_call_list["toolCallCount"]:
        raise ValueError(
            "CapabilityV1 toolCallCoverage.toolCallCount must equal ToolCallListV1.toolCallCount"
        )
    capability_ids = [item["capabilityId"] for item in capability_items]
    if coverage["capabilityIdsCovered"] != capability_ids:
        raise ValueError(
            "CapabilityV1 toolCallCoverage.capabilityIdsCovered must mirror capabilityItems order"
        )
    tool_call_refs = [
        tc["capabilityRef"] for tc in tool_call_list.get("toolCallItems", [])
    ]
    unique_tool_call_refs = sorted(set(tool_call_refs))
    if coverage["uniqueToolCallCapabilityRefs"] != unique_tool_call_refs:
        raise ValueError(
            "CapabilityV1 toolCallCoverage.uniqueToolCallCapabilityRefs must equal sorted unique ToolCallListV1 capabilityRef set"
        )
    if coverage["uniqueCapabilityRefCount"] != len(unique_tool_call_refs):
        raise ValueError(
            "CapabilityV1 toolCallCoverage.uniqueCapabilityRefCount must equal the unique ToolCallListV1 capabilityRef count"
        )
    if coverage["everyToolCallRefResolved"] is not True:
        raise ValueError(
            "CapabilityV1 toolCallCoverage.everyToolCallRefResolved must be true"
        )
    if coverage["everyCapabilityItemUsed"] is not True:
        raise ValueError(
            "CapabilityV1 toolCallCoverage.everyCapabilityItemUsed must be true"
        )


def _validate_promotion_conditions(
    promotion: dict[str, Any],
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> None:
    _require_fields(
        "CapabilityV1 promotionConditions",
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
            f"CapabilityV1 promotionConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_PROMOTION}"
        )
    if promotion["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "CapabilityV1 promotionConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if promotion["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"CapabilityV1 promotionConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if promotion["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"CapabilityV1 promotionConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if promotion["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "CapabilityV1 promotionConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if promotion["requiredPolicyUnlocked"] is not REQUIRED_POLICY_UNLOCKED:
        raise ValueError(
            "CapabilityV1 promotionConditions.requiredPolicyUnlocked must be true"
        )
    if promotion["currentPolicyUnlocked"] is not expected_unlocked:
        raise ValueError(
            "CapabilityV1 promotionConditions.currentPolicyUnlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_promoted = (
        promotion["currentVerdict"] == REQUIRED_VERDICT_FOR_PROMOTION
        and promotion["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and promotion["currentPolicyUnlocked"] is True
    )
    if promotion["promoted"] is not expected_promoted:
        raise ValueError(
            "CapabilityV1 promotionConditions.promoted must be true only when verdict, run terminal state and policy unlock all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("CapabilityV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("CapabilityV1 sourceArtifacts entries must be objects")
        _require_fields(
            "CapabilityV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(f"CapabilityV1 sourceArtifacts contains unexpected role: {role}")
        if role in seen_roles:
            raise ValueError(f"CapabilityV1 sourceArtifacts contains duplicate role: {role}")
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"CapabilityV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(f"CapabilityV1 source artifact does not exist: {path}")
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(f"CapabilityV1 source hash mismatch for {path}")
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"CapabilityV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_capability_kernel_artifact(
    manifest: dict[str, Any], root: Path
) -> None:
    _require_fields(
        "CapabilityV1",
        manifest,
        [
            "schemaVersion",
            "artifactEnvelopeSchemaVersion",
            "capabilityItemSchemaVersion",
            "id",
            "generatedAt",
            "kind",
            "scope",
            "workloadType",
            "workloadCategory",
            "creatorAgent",
            "verifierVerdictOwner",
            "capabilityCount",
            "capabilityItems",
            "capabilityClassDomain",
            "forbiddenCapabilityClasses",
            "sideEffectClassDomain",
            "forbiddenSideEffectClasses",
            "sourceAgentDomain",
            "capabilityLifecycleStateDomain",
            "requiredCapabilityLifecycleState",
            "verdictDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "taskSpecBinding",
            "intentBinding",
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
            "toolCallCoverage",
            "promotionConditions",
            "verifierExpectations",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != CAPABILITY_KERNEL_SCHEMA_VERSION:
        raise ValueError(
            f"CapabilityV1 schemaVersion must be {CAPABILITY_KERNEL_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"CapabilityV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["capabilityItemSchemaVersion"] != CAPABILITY_ITEM_SCHEMA_VERSION:
        raise ValueError(
            f"CapabilityV1 capabilityItemSchemaVersion must be {CAPABILITY_ITEM_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"CapabilityV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"CapabilityV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"CapabilityV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"CapabilityV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"CapabilityV1 workloadType must be {WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(f"CapabilityV1 workloadCategory must be {WORKLOAD_CATEGORY}")
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"CapabilityV1 creatorAgent must be {CREATOR_AGENT}")
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"CapabilityV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; creator must not own the verdict"
        )

    if manifest["capabilityCount"] != EXPECTED_CAPABILITY_COUNT:
        raise ValueError(
            f"CapabilityV1 capabilityCount must equal {EXPECTED_CAPABILITY_COUNT}"
        )
    if manifest["capabilityClassDomain"] != list(CAPABILITY_CLASS_DOMAIN):
        raise ValueError(
            f"CapabilityV1 capabilityClassDomain must equal {CAPABILITY_CLASS_DOMAIN}"
        )
    if manifest["forbiddenCapabilityClasses"] != list(FORBIDDEN_CAPABILITY_CLASSES):
        raise ValueError(
            f"CapabilityV1 forbiddenCapabilityClasses must equal {FORBIDDEN_CAPABILITY_CLASSES}"
        )
    if manifest["sideEffectClassDomain"] != list(SIDE_EFFECT_CLASS_DOMAIN):
        raise ValueError(
            f"CapabilityV1 sideEffectClassDomain must equal {SIDE_EFFECT_CLASS_DOMAIN}"
        )
    if manifest["forbiddenSideEffectClasses"] != list(FORBIDDEN_SIDE_EFFECT_CLASSES):
        raise ValueError(
            f"CapabilityV1 forbiddenSideEffectClasses must equal {FORBIDDEN_SIDE_EFFECT_CLASSES}"
        )
    if manifest["sourceAgentDomain"] != list(SOURCE_AGENT_DOMAIN):
        raise ValueError(
            f"CapabilityV1 sourceAgentDomain must equal {SOURCE_AGENT_DOMAIN}"
        )
    if manifest["capabilityLifecycleStateDomain"] != list(CAPABILITY_LIFECYCLE_STATE_DOMAIN):
        raise ValueError(
            f"CapabilityV1 capabilityLifecycleStateDomain must equal {CAPABILITY_LIFECYCLE_STATE_DOMAIN}"
        )
    if manifest["requiredCapabilityLifecycleState"] != REQUIRED_CAPABILITY_LIFECYCLE_STATE:
        raise ValueError(
            f"CapabilityV1 requiredCapabilityLifecycleState must equal {REQUIRED_CAPABILITY_LIFECYCLE_STATE}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(f"CapabilityV1 verdictDomain must equal {VERDICT_DOMAIN}")
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"CapabilityV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )
    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"CapabilityV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(f"CapabilityV1 permissionFlags.{flag} must be false")

    overlap = set(manifest["forbiddenCapabilityClasses"]).intersection(
        cap["capabilityClass"] for cap in manifest["capabilityItems"]
    )
    if overlap:
        raise ValueError(
            f"CapabilityV1 forbiddenCapabilityClasses must not intersect declared capabilityItems[*].capabilityClass: {sorted(overlap)}"
        )

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
    intent = _load_json(root / INTENT_ARTIFACT_PATH)

    _validate_capability_items(manifest["capabilityItems"], tool_call_list)

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
            f"CapabilityV1 taskSpecBinding.taskSpecSchemaVersion must equal {TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression-task-spec-v1 reuse is forbidden"
        )
    if manifest["taskSpecBinding"]["taskSpecWorkloadType"] != TASK_SPEC_WORKLOAD_TYPE:
        raise ValueError(
            f"CapabilityV1 taskSpecBinding.taskSpecWorkloadType must equal {TASK_SPEC_WORKLOAD_TYPE}"
        )
    if manifest["taskSpecBinding"]["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"CapabilityV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    if manifest["taskSpecBinding"]["taskSpecWorkloadType"] != task_spec["workloadType"]:
        raise ValueError(
            "CapabilityV1 taskSpecBinding.taskSpecWorkloadType must equal TestExecutionTaskSpecV1.workloadType"
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
            f"CapabilityV1 intentBinding.intentSchemaVersion must equal {INTENT_ARTIFACT_SCHEMA_VERSION}"
        )
    if manifest["intentBinding"]["intentId"] != INTENT_ARTIFACT_ID:
        raise ValueError(
            f"CapabilityV1 intentBinding.intentId must equal {INTENT_ARTIFACT_ID}"
        )
    if manifest["intentBinding"]["intentIdentifier"] != intent["intentId"]:
        raise ValueError(
            "CapabilityV1 intentBinding.intentIdentifier must equal IntentV1.intentId"
        )
    if manifest["intentBinding"]["intentLifecycleState"] != intent["intentLifecycleState"]:
        raise ValueError(
            "CapabilityV1 intentBinding.intentLifecycleState must equal IntentV1.intentLifecycleState"
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
            "CapabilityV1 runBinding.runIdentifier must equal RunV1.runId"
        )
    if manifest["runBinding"]["runState"] != run_artifact["runState"]:
        raise ValueError(
            "CapabilityV1 runBinding.runState must equal RunV1.runState"
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
            "CapabilityV1 stepListBinding.stepCount must equal StepListV1.stepCount"
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
            "CapabilityV1 toolCallListBinding.toolCallCount must equal ToolCallListV1.toolCallCount"
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
            f"CapabilityV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal {CAPABILITY_MANIFEST_SCHEMA_VERSION}; capability-envelope-v1 reuse is forbidden"
        )
    if manifest["capabilityManifestBinding"]["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"CapabilityV1 capabilityManifestBinding.capabilityManifestId must equal {CAPABILITY_MANIFEST_ARTIFACT_ID}"
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
            "CapabilityV1 runEventLogBinding.eventCount must equal RunEventLogV1.eventCount"
        )
    if manifest["runEventLogBinding"]["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "CapabilityV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
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
            "CapabilityV1 observationListBinding.observationItemCount must equal ObservationListV1.observationItemCount"
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
            "CapabilityV1 evidenceListBinding.evidenceItemCount must equal EvidenceListV1.evidenceItemCount"
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
            f"CapabilityV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}"
        )
    if manifest["verifierResultBinding"]["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "CapabilityV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
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
            f"CapabilityV1 deliveryManifestBinding.deliveryManifestId must equal {DELIVERY_MANIFEST_ARTIFACT_ID}"
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
            "CapabilityV1 policyManifestBinding.unlocked must equal PolicyManifestV1.unlockConditions.unlocked"
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
            f"CapabilityV1 approvalDecisionBinding.approvalDecisionSchemaVersion must equal {HUMAN_APPROVAL_DECISION_SCHEMA_VERSION}"
        )
    if manifest["approvalDecisionBinding"]["approvalDecisionId"] != approval_decision["id"]:
        raise ValueError(
            "CapabilityV1 approvalDecisionBinding.approvalDecisionId must equal HumanApprovalDecisionV1.id"
        )
    expected_granted = bool(approval_decision.get("decision", {}).get("approvalGranted", False))
    if manifest["approvalDecisionBinding"]["approvalGranted"] is not expected_granted:
        raise ValueError(
            "CapabilityV1 approvalDecisionBinding.approvalGranted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )

    _validate_tool_call_coverage(
        manifest["toolCallCoverage"], manifest["capabilityItems"], tool_call_list
    )

    _validate_promotion_conditions(
        manifest["promotionConditions"],
        verifier_result,
        run_event_log,
        policy_manifest,
    )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "CapabilityV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(f"CapabilityV1 verifierExpectations.{flag} must be true")
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"CapabilityV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"CapabilityV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "CapabilityV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionCapabilityArtifact",
            "reusesRegressionTaskSpec",
            "reusesRegressionResultArtifact",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionCapabilityArtifact"] is not False:
        raise ValueError(
            "CapabilityV1 must not reuse any first-workload regression capability artifact"
        )
    if isolation["reusesRegressionTaskSpec"] is not False:
        raise ValueError("CapabilityV1 must not reuse the regression-task-spec-v1 schema")
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError("CapabilityV1 must not reuse RegressionResultArtifactV1")
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError("CapabilityV1 must not reuse the send_email capability")
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"CapabilityV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"CapabilityV1 must not embed regression/email field {term} outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"CapabilityV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            f"CapabilityV1 coordinationBinding must include {sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"CapabilityV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 6:
        raise ValueError(
            "CapabilityV1 invariants must declare at least six workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="capability-kernel")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_capability_kernel_artifact(root)
        _write_json(args.out, manifest)
        print(f"Wrote CapabilityV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_capability_kernel_artifact(manifest, root)
        print(f"Validated CapabilityV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

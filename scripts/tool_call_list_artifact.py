"""ToolCallListV1 / ToolCallV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``ToolCallListV1`` ArtifactV1
subtype that captures the canonical OS-kernel ``ToolCall`` primitive for any
engineering workload. Each tool call is a workload-independent
``ToolCallV1`` envelope (``tool-call-v1``) describing a single invocation
of a Capability that the run executed.

ToolCallListV1 sits between StepListV1 (``step-list-artifact-v1``) and the
lower-level RunEventLogV1 (``run-event-log-v1``):

- RunEventLogV1 records every append-only event the run produced
  (``capability.invoked`` / ``capability.completed`` /
  ``artifact.written`` / ``verifier.completed`` ...).
- StepListV1 groups one or more events into a single step
  (``capability_invocation_step`` / ``artifact_write_step`` /
  ``verifier_step`` / ``run_state_transition_step`` /
  ``planning_lifecycle_step``).
- ToolCallListV1 extracts the *tool-bearing* steps (every
  ``capability_invocation_step`` / ``artifact_write_step`` /
  ``verifier_step``) and materializes each one as a single
  ``ToolCallV1`` record with deterministic input/output payload hashes,
  observed-event-id pairs, observation refs and side-effect class.

The artifact answers four OS-kernel invariants at once:

- ``ToolCall`` primitive: each tool call declares ``toolCallId`` /
  ``capabilityRef`` / ``sourceAgent`` / ``status`` / ``startedAt`` /
  ``completedAt`` / ``inputSchemaRef`` / ``outputSchemaRef`` /
  ``inputPayloadHash`` / ``outputPayloadHash`` / ``runEventLogRefs`` /
  ``observationRefs`` / ``stepRef`` / ``sideEffectClass`` using only
  workload-independent vocabulary.
- ``Artifact`` envelope reuse: the manifest is an ArtifactV1 subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) joining the existing
  twelve subtypes (``test-execution-result-v1``,
  ``failure-triage-report-v1``, ``verifier-result-v1``,
  ``capability-manifest-v1``, ``run-event-log-v1``,
  ``delivery-manifest-v1``, ``policy-manifest-v1``,
  ``evidence-list-artifact-v1``, ``observation-list-artifact-v1``,
  ``run-artifact-v1``, ``step-list-artifact-v1``,
  ``regression-result-artifact-v1``).
- ``Verifier`` / ``Policy`` consistency: ``promotionConditions`` ties
  tool-call promotion to ``VerifierResultV1.verdict=passed`` /
  ``RunEventLogV1.terminalState=completed`` /
  ``PolicyManifestV1.unlockConditions.unlocked=true`` and declares
  ``verifier-runtime-v1`` as verdict owner with
  ``creatorMustNotOwnVerdict=true``.
- ``Coordination`` boundary: all five Agent Coordination Layer
  contracts are pinned by ref + content hash, so coordination drift
  invalidates the tool-call list.

Invariants beyond the step / observation envelopes:

- ``toolCallCount`` must equal the number of
  ``capability_invocation_step`` / ``artifact_write_step`` /
  ``verifier_step`` entries in ``StepListV1.stepItems`` (5 for the
  current Test Execution / Failure Triage blueprint: 3 capability
  invocations + 1 artifact write + 1 verifier check).
- Every tool call's ``stepRef`` must resolve to an existing
  ``StepListV1.stepItems[*].stepId`` of a tool-bearing stepKind.
- Every tool call's ``runEventLogRefs`` must equal the step's
  ``runEventLogRefs`` and resolve into ``RunEventLogV1.events`` by
  ``eventId``.
- Every tool call's ``observationRefs`` must equal the step's
  ``observationRefs`` and resolve into
  ``ObservationListV1.observationItems``.
- ``sideEffectClass`` must lie in
  ``[read_only, evidence_writer, artifact_writer, verifier_check]``
  and never equal ``external`` / ``send_email`` /
  ``release_or_deploy``.
- ``inputPayloadHash`` and ``outputPayloadHash`` are deterministic
  sha256 hashes over canonicalized JSON of declared input/output
  payload contracts.
- Six workload-independent permission flags are forced to ``false``.
- Regression-workload isolation forbids ``regression_result``,
  ``email_draft``, ``send_email``, ``regression-task-spec-v1`` and
  ``regression-result-artifact-v1`` reuse.
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
    RUN_IDENTIFIER,
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
    validate_test_execution_task_spec,
)
from verifier_result import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as VERIFIER_RESULT_ARTIFACT_ID,
    VERIFIER_RESULT_ARTIFACT_PATH,
    VERIFIER_RESULT_SCHEMA_VERSION,
    validate_verifier_result,
)


TOOL_CALL_LIST_ARTIFACT_SCHEMA_VERSION = "tool-call-list-artifact-v1"
TOOL_CALL_ITEM_SCHEMA_VERSION = "tool-call-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "ToolCallListV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-tool-call-list-kernel-contract"
TOOL_CALL_LIST_ARTIFACT_PATH = (
    "artifacts/tool_calls/post_mvp_test_execution_tool_call_list.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_tool_call_list_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

REQUIRED_VERDICT_FOR_PROMOTION = "passed"
REQUIRED_TERMINAL_RUN_STATE = "completed"
REQUIRED_POLICY_UNLOCKED = True

TOOL_CALL_STATUS_DOMAIN = ["completed", "failed"]
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
TOOL_BEARING_STEP_KINDS = [
    "capability_invocation_step",
    "artifact_write_step",
    "verifier_step",
]

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


# Deterministic ToolCallV1 blueprint: one entry per tool-bearing step.
# capabilityRef / sourceAgent / sideEffectClass / inputSchemaRef /
# outputSchemaRef / inputPayloadShape / outputPayloadShape are
# workload-independent declarations derived from the run event log
# payloads. The script index aligns to the position inside
# StepListV1.stepItems whose stepKind is tool-bearing.
TOOL_CALL_BLUEPRINT: list[dict[str, Any]] = [
    {
        "stepKindExpected": "capability_invocation_step",
        "capabilityRef": "read_test_execution_result",
        "sourceAgent": "creator_agent",
        "sideEffectClass": "read_only",
        "inputPayloadShape": {
            "type": "ReadTestExecutionResultInputV1",
            "fields": ["taskSpecId", "testExecutionResultRef"],
        },
        "outputPayloadShape": {
            "type": "ReadTestExecutionResultOutputV1",
            "fields": ["testExecutionResultId", "totalCases", "failedCases"],
        },
    },
    {
        "stepKindExpected": "capability_invocation_step",
        "capabilityRef": "collect_test_failure_evidence",
        "sourceAgent": "creator_agent",
        "sideEffectClass": "evidence_writer",
        "inputPayloadShape": {
            "type": "CollectTestFailureEvidenceInputV1",
            "fields": ["taskSpecId", "testExecutionResultRef", "failedCaseIds"],
        },
        "outputPayloadShape": {
            "type": "CollectTestFailureEvidenceOutputV1",
            "fields": ["evidenceListRef", "evidenceItemCount"],
        },
    },
    {
        "stepKindExpected": "capability_invocation_step",
        "capabilityRef": "classify_test_failure",
        "sourceAgent": "creator_agent",
        "sideEffectClass": "read_only",
        "inputPayloadShape": {
            "type": "ClassifyTestFailureInputV1",
            "fields": ["taskSpecId", "evidenceListRef"],
        },
        "outputPayloadShape": {
            "type": "ClassifyTestFailureOutputV1",
            "fields": ["failureTriageReportRef", "perCaseClassifications"],
        },
    },
    {
        "stepKindExpected": "artifact_write_step",
        "capabilityRef": "write_artifact",
        "sourceAgent": "creator_agent",
        "sideEffectClass": "artifact_writer",
        "inputPayloadShape": {
            "type": "WriteArtifactInputV1",
            "fields": ["artifactKinds", "artifactRefs"],
        },
        "outputPayloadShape": {
            "type": "WriteArtifactOutputV1",
            "fields": ["artifactRefs", "artifactContentHashes"],
        },
    },
    {
        "stepKindExpected": "verifier_step",
        "capabilityRef": "__run_kernel__",
        "sourceAgent": "verifier-runtime-v1",
        "sideEffectClass": "verifier_check",
        "inputPayloadShape": {
            "type": "VerifierRunInputV1",
            "fields": ["verifierResultRef", "verdictDomain"],
        },
        "outputPayloadShape": {
            "type": "VerifierRunOutputV1",
            "fields": ["verdict", "verifierAgent"],
        },
    },
]

EXPECTED_TOOL_CALL_COUNT = len(TOOL_CALL_BLUEPRINT)

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
    "human_approval_decision": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

REQUIRED_VERIFIER_FLAGS = [
    "mustValidateSchema",
    "mustValidateToolCallSchema",
    "mustValidateSideEffectClassDomain",
    "mustValidateStepBinding",
    "mustValidateRunEventLogBinding",
    "mustValidateObservationListBinding",
    "mustValidateVerifierResultBinding",
    "mustValidateRunBinding",
    "mustValidatePayloadHashes",
    "mustValidateStepCoverage",
    "mustValidatePermissionFlags",
    "mustValidatePromotionConditions",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "ToolCallListV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype and from any first-workload regression tool-call artifact.",
    "ToolCallListV1 must bind StepListV1, RunV1, TestExecutionTaskSpecV1, CapabilityManifestV1, RunEventLogV1, ObservationListV1, EvidenceListV1, VerifierResultV1, DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1, and all five coordination contracts by content hash.",
    "Every ToolCallV1.stepRef must resolve to a tool-bearing StepListV1.stepItems entry (capability_invocation_step / artifact_write_step / verifier_step); every ToolCallV1.runEventLogRefs entry must resolve to RunEventLogV1.events; every ToolCallV1.observationRefs entry must resolve to ObservationListV1.observationItems.",
    "toolCallCount must equal the number of tool-bearing entries in StepListV1; stepCoverage.everyToolBearingStepCovered must be true.",
    "ToolCallV1.sideEffectClass must lie in [read_only, evidence_writer, artifact_writer, verifier_check]; external / email_send_call / release_or_deploy classes are forbidden.",
    "ToolCallV1.inputPayloadHash and outputPayloadHash must be deterministic sha256 hashes over canonicalized JSON of inputPayloadShape and outputPayloadShape declarations.",
    "ToolCallListV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and creator agents may only stage drafts.",
    "ToolCallListV1 promotionConditions require verdict=passed, terminal run state=completed and PolicyManifestV1 unlock=true.",
    "ToolCallListV1 must not reuse regression-task-spec-v1, regression-result-artifact-v1, regression run.json steps array, regression events.jsonl, the send_email capability, or any regression_result / email_draft / send_email field.",
]


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
            f"ToolCallListV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"ToolCallListV1 source artifact does not exist: {relative_path}"
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
                f"ToolCallListV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _tool_bearing_steps(step_list: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for step in step_list["stepItems"]
        if step["stepKind"] in TOOL_BEARING_STEP_KINDS
    ]


def _input_schema_for_step(step: dict[str, Any], run_event_log: dict[str, Any]) -> str:
    events_by_id = {event["eventId"]: event for event in run_event_log["events"]}
    for event_id in step["runEventLogRefs"]:
        event = events_by_id[event_id]
        payload = event.get("payload") or {}
        if "inputSchema" in payload:
            return payload["inputSchema"]
    return step.get("inputContract") or ""


def _output_schema_for_step(step: dict[str, Any], run_event_log: dict[str, Any]) -> str:
    events_by_id = {event["eventId"]: event for event in run_event_log["events"]}
    last_output: str | None = None
    for event_id in step["runEventLogRefs"]:
        event = events_by_id[event_id]
        payload = event.get("payload") or {}
        if "outputSchema" in payload:
            last_output = payload["outputSchema"]
    return last_output or step.get("outputContract") or ""


def _status_for_step(step: dict[str, Any]) -> str:
    if step["status"] == "failed":
        return "failed"
    return "completed"


def _build_tool_call_items(
    step_list: dict[str, Any], run_event_log: dict[str, Any]
) -> list[dict[str, Any]]:
    tool_steps = _tool_bearing_steps(step_list)
    if len(tool_steps) != EXPECTED_TOOL_CALL_COUNT:
        raise ValueError(
            f"ToolCallListV1 expected {EXPECTED_TOOL_CALL_COUNT} tool-bearing steps "
            f"in StepListV1; got {len(tool_steps)}"
        )
    items: list[dict[str, Any]] = []
    for index, blueprint in enumerate(TOOL_CALL_BLUEPRINT):
        step = tool_steps[index]
        if step["stepKind"] != blueprint["stepKindExpected"]:
            raise ValueError(
                f"ToolCallListV1 blueprint index {index} expected stepKind "
                f"{blueprint['stepKindExpected']}; got {step['stepKind']}"
            )
        if step["capabilityRef"] != blueprint["capabilityRef"]:
            raise ValueError(
                f"ToolCallListV1 blueprint index {index} expected capabilityRef "
                f"{blueprint['capabilityRef']}; got {step['capabilityRef']}"
            )
        if step["sourceAgent"] != blueprint["sourceAgent"]:
            raise ValueError(
                f"ToolCallListV1 blueprint index {index} expected sourceAgent "
                f"{blueprint['sourceAgent']}; got {step['sourceAgent']}"
            )
        tool_call_id = f"toolcall-{RUN_IDENTIFIER}-{index:04d}"
        item: dict[str, Any] = {
            "schemaVersion": TOOL_CALL_ITEM_SCHEMA_VERSION,
            "toolCallId": tool_call_id,
            "sequence": index,
            "stepRef": step["stepId"],
            "stepKind": step["stepKind"],
            "capabilityRef": blueprint["capabilityRef"],
            "sourceAgent": blueprint["sourceAgent"],
            "status": _status_for_step(step),
            "startedAt": step["startedAt"],
            "completedAt": step["completedAt"],
            "inputSchemaRef": _input_schema_for_step(step, run_event_log),
            "outputSchemaRef": _output_schema_for_step(step, run_event_log),
            "inputPayloadShape": blueprint["inputPayloadShape"],
            "outputPayloadShape": blueprint["outputPayloadShape"],
            "inputPayloadHash": _payload_hash(blueprint["inputPayloadShape"]),
            "outputPayloadHash": _payload_hash(blueprint["outputPayloadShape"]),
            "runEventLogRefs": list(step["runEventLogRefs"]),
            "observationRefs": list(step["observationRefs"]),
            "sideEffectClass": blueprint["sideEffectClass"],
        }
        items.append(item)
    return items


def _build_step_coverage(
    tool_call_items: list[dict[str, Any]], step_list: dict[str, Any]
) -> dict[str, Any]:
    expected_step_ids = [step["stepId"] for step in _tool_bearing_steps(step_list)]
    covered_step_ids = [item["stepRef"] for item in tool_call_items]
    missing = [step_id for step_id in expected_step_ids if step_id not in covered_step_ids]
    extra = [step_id for step_id in covered_step_ids if step_id not in expected_step_ids]
    duplicates = [
        step_id
        for step_id in covered_step_ids
        if covered_step_ids.count(step_id) > 1
    ]
    return {
        "toolBearingStepCount": len(expected_step_ids),
        "coveredStepCount": len(covered_step_ids),
        "distinctCoveredStepCount": len(set(covered_step_ids)),
        "everyToolBearingStepCovered": not missing and not extra and not duplicates,
        "missingSteps": missing,
        "duplicateSteps": sorted(set(duplicates)),
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


def _build_step_list_binding(
    root: Path, step_list: dict[str, Any]
) -> dict[str, Any]:
    full_path = root / STEP_LIST_ARTIFACT_PATH
    tool_bearing_count = len(_tool_bearing_steps(step_list))
    return {
        "stepListRef": STEP_LIST_ARTIFACT_PATH,
        "stepListSchemaVersion": STEP_LIST_ARTIFACT_SCHEMA_VERSION,
        "stepListEnvelopeSchemaVersion": STEP_LIST_ENVELOPE_SCHEMA_VERSION,
        "stepListId": STEP_LIST_ARTIFACT_ID,
        "stepListContentHash": _stable_file_hash(full_path),
        "stepCount": step_list["stepCount"],
        "toolBearingStepCount": tool_bearing_count,
    }


def _build_run_binding(root: Path, run_artifact: dict[str, Any]) -> dict[str, Any]:
    full_path = root / RUN_ARTIFACT_PATH
    return {
        "runRef": RUN_ARTIFACT_PATH,
        "runSchemaVersion": RUN_ARTIFACT_SCHEMA_VERSION,
        "runEnvelopeSchemaVersion": RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "runId": RUN_ARTIFACT_ID,
        "runContentHash": _stable_file_hash(full_path),
        "runIdentifier": run_artifact["runId"],
        "runState": run_artifact["runState"],
    }


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    full_path = root / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    return {
        "taskSpecRef": TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecContentHash": _stable_file_hash(full_path),
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
        "runEventLogContentHash": _stable_file_hash(full_path),
        "eventCount": run_event_log["eventCount"],
        "terminalState": run_event_log["terminalState"],
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
        "observationListContentHash": _stable_file_hash(full_path),
        "observationItemCount": observation_list["observationItemCount"],
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
        "evidenceListContentHash": _stable_file_hash(full_path),
        "evidenceItemCount": evidence_list["evidenceItemCount"],
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
        "verifierResultContentHash": _stable_file_hash(full_path),
        "verdict": verifier_result["verdict"],
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
        "policyManifestContentHash": _stable_file_hash(full_path),
        "unlocked": unlocked,
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
        "approvalDecisionContentHash": _stable_file_hash(full_path),
        "approvalGranted": bool(decision_block.get("approvalGranted", False)),
    }


def _validate_referenced_artifacts(root: Path) -> tuple[
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
    return (
        run_event_log,
        observation_list,
        evidence_list,
        verifier_result,
        policy_manifest,
        run_artifact,
        step_list,
    )


def build_tool_call_list_artifact(root: Path) -> dict[str, Any]:
    (
        run_event_log,
        observation_list,
        evidence_list,
        verifier_result,
        policy_manifest,
        run_artifact,
        step_list,
    ) = _validate_referenced_artifacts(root)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)

    tool_call_items = _build_tool_call_items(step_list, run_event_log)

    payload: dict[str, Any] = {
        "schemaVersion": TOOL_CALL_LIST_ARTIFACT_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "toolCallItemSchemaVersion": TOOL_CALL_ITEM_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "runIdentifier": RUN_IDENTIFIER,
        "toolCallCount": len(tool_call_items),
        "toolCallStatusDomain": list(TOOL_CALL_STATUS_DOMAIN),
        "sideEffectClassDomain": list(SIDE_EFFECT_CLASS_DOMAIN),
        "forbiddenSideEffectClasses": list(FORBIDDEN_SIDE_EFFECT_CLASSES),
        "sourceAgentDomain": list(SOURCE_AGENT_DOMAIN),
        "toolBearingStepKinds": list(TOOL_BEARING_STEP_KINDS),
        "verdictDomain": list(VERDICT_DOMAIN),
        "permissionFlagDomain": list(PERMISSION_FLAG_DOMAIN),
        "permissionFlags": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
        "toolCallItems": tool_call_items,
        "stepCoverage": _build_step_coverage(tool_call_items, step_list),
        "stepListBinding": _build_step_list_binding(root, step_list),
        "runBinding": _build_run_binding(root, run_artifact),
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
            "mustValidateToolCallSchema": True,
            "mustValidateSideEffectClassDomain": True,
            "mustValidateStepBinding": True,
            "mustValidateRunEventLogBinding": True,
            "mustValidateObservationListBinding": True,
            "mustValidateVerifierResultBinding": True,
            "mustValidateRunBinding": True,
            "mustValidatePayloadHashes": True,
            "mustValidateStepCoverage": True,
            "mustValidatePermissionFlags": True,
            "mustValidatePromotionConditions": True,
            "creatorMustNotOwnVerdict": True,
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERDICT_DOMAIN),
        },
        "regressionWorkloadIsolation": {
            "reusesRegressionRunArtifact": False,
            "reusesRegressionResultArtifact": False,
            "reusesRegressionEventsArtifact": False,
            "reusesRegressionRunStepArray": False,
            "reusesRegressionToolCallArtifact": False,
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
    validate_tool_call_list_artifact(payload, root)
    return payload


def _validate_tool_call_items(
    tool_call_items: Any,
    step_list: dict[str, Any],
    run_event_log: dict[str, Any],
    observation_list: dict[str, Any],
) -> None:
    if not isinstance(tool_call_items, list) or len(tool_call_items) != EXPECTED_TOOL_CALL_COUNT:
        raise ValueError(
            f"ToolCallListV1 toolCallItems must be a list of length {EXPECTED_TOOL_CALL_COUNT}"
        )
    tool_steps = _tool_bearing_steps(step_list)
    if len(tool_steps) != EXPECTED_TOOL_CALL_COUNT:
        raise ValueError(
            "ToolCallListV1 expected StepListV1 to expose "
            f"{EXPECTED_TOOL_CALL_COUNT} tool-bearing steps"
        )
    events_by_id = {event["eventId"]: event for event in run_event_log["events"]}
    obs_by_id = {item["observationId"]: item for item in observation_list["observationItems"]}
    seen_ids: set[str] = set()
    for index, item in enumerate(tool_call_items):
        if not isinstance(item, dict):
            raise ValueError("ToolCallListV1 toolCallItems entries must be objects")
        _require_fields(
            f"ToolCallListV1 toolCallItems[{index}]",
            item,
            [
                "schemaVersion",
                "toolCallId",
                "sequence",
                "stepRef",
                "stepKind",
                "capabilityRef",
                "sourceAgent",
                "status",
                "startedAt",
                "completedAt",
                "inputSchemaRef",
                "outputSchemaRef",
                "inputPayloadShape",
                "outputPayloadShape",
                "inputPayloadHash",
                "outputPayloadHash",
                "runEventLogRefs",
                "observationRefs",
                "sideEffectClass",
            ],
        )
        blueprint = TOOL_CALL_BLUEPRINT[index]
        if item["schemaVersion"] != TOOL_CALL_ITEM_SCHEMA_VERSION:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].schemaVersion must be {TOOL_CALL_ITEM_SCHEMA_VERSION}"
            )
        if item["sequence"] != index:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].sequence must equal its position {index}"
            )
        expected_id = f"toolcall-{RUN_IDENTIFIER}-{index:04d}"
        if item["toolCallId"] != expected_id:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].toolCallId must equal {expected_id}"
            )
        if item["toolCallId"] in seen_ids:
            raise ValueError(
                f"ToolCallListV1 toolCallItems contains duplicate toolCallId: {item['toolCallId']}"
            )
        seen_ids.add(item["toolCallId"])
        step = tool_steps[index]
        if item["stepRef"] != step["stepId"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].stepRef must equal StepListV1 tool-bearing step {step['stepId']}"
            )
        if item["stepKind"] not in TOOL_BEARING_STEP_KINDS:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].stepKind must be one of {TOOL_BEARING_STEP_KINDS}"
            )
        if item["stepKind"] != step["stepKind"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].stepKind must equal StepListV1 step.stepKind"
            )
        if item["capabilityRef"] != blueprint["capabilityRef"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].capabilityRef must equal {blueprint['capabilityRef']}"
            )
        if item["capabilityRef"] != step["capabilityRef"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].capabilityRef must equal StepListV1 step.capabilityRef"
            )
        if item["sourceAgent"] not in SOURCE_AGENT_DOMAIN:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].sourceAgent must be one of {SOURCE_AGENT_DOMAIN}"
            )
        if item["sourceAgent"] != blueprint["sourceAgent"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].sourceAgent must equal {blueprint['sourceAgent']}"
            )
        if item["sourceAgent"] != step["sourceAgent"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].sourceAgent must equal StepListV1 step.sourceAgent"
            )
        if item["status"] not in TOOL_CALL_STATUS_DOMAIN:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].status must be one of {TOOL_CALL_STATUS_DOMAIN}"
            )
        if item["status"] != _status_for_step(step):
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].status must equal derived step status"
            )
        if item["startedAt"] != step["startedAt"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].startedAt must equal StepListV1 step.startedAt"
            )
        if item["completedAt"] != step["completedAt"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].completedAt must equal StepListV1 step.completedAt"
            )
        if item["startedAt"] > item["completedAt"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].startedAt must not be greater than completedAt"
            )
        if item["sideEffectClass"] in FORBIDDEN_SIDE_EFFECT_CLASSES:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].sideEffectClass must not be one of {FORBIDDEN_SIDE_EFFECT_CLASSES}"
            )
        if item["sideEffectClass"] not in SIDE_EFFECT_CLASS_DOMAIN:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].sideEffectClass must be one of {SIDE_EFFECT_CLASS_DOMAIN}"
            )
        if item["sideEffectClass"] != blueprint["sideEffectClass"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].sideEffectClass must equal {blueprint['sideEffectClass']}"
            )
        if item["inputSchemaRef"] != _input_schema_for_step(step, run_event_log):
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].inputSchemaRef must equal derived run-event input schema"
            )
        if item["outputSchemaRef"] != _output_schema_for_step(step, run_event_log):
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].outputSchemaRef must equal derived run-event output schema"
            )
        if item["inputPayloadShape"] != blueprint["inputPayloadShape"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].inputPayloadShape must equal blueprint inputPayloadShape"
            )
        if item["outputPayloadShape"] != blueprint["outputPayloadShape"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].outputPayloadShape must equal blueprint outputPayloadShape"
            )
        if item["inputPayloadHash"] != _payload_hash(blueprint["inputPayloadShape"]):
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].inputPayloadHash must equal sha256 of canonicalized inputPayloadShape"
            )
        if item["outputPayloadHash"] != _payload_hash(blueprint["outputPayloadShape"]):
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].outputPayloadHash must equal sha256 of canonicalized outputPayloadShape"
            )
        if item["runEventLogRefs"] != step["runEventLogRefs"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].runEventLogRefs must equal StepListV1 step.runEventLogRefs"
            )
        for event_id in item["runEventLogRefs"]:
            if event_id not in events_by_id:
                raise ValueError(
                    f"ToolCallListV1 toolCallItems[{index}] references unknown RunEventLogV1.events eventId: {event_id}"
                )
        if item["observationRefs"] != step["observationRefs"]:
            raise ValueError(
                f"ToolCallListV1 toolCallItems[{index}].observationRefs must equal StepListV1 step.observationRefs"
            )
        for obs_id in item["observationRefs"]:
            if obs_id not in obs_by_id:
                raise ValueError(
                    f"ToolCallListV1 toolCallItems[{index}] references unknown ObservationListV1.observationId: {obs_id}"
                )


def _validate_step_coverage(
    coverage: dict[str, Any], step_list: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 stepCoverage",
        coverage,
        [
            "toolBearingStepCount",
            "coveredStepCount",
            "distinctCoveredStepCount",
            "everyToolBearingStepCovered",
            "missingSteps",
            "duplicateSteps",
        ],
    )
    tool_bearing_count = len(_tool_bearing_steps(step_list))
    if coverage["toolBearingStepCount"] != tool_bearing_count:
        raise ValueError(
            f"ToolCallListV1 stepCoverage.toolBearingStepCount must equal {tool_bearing_count}"
        )
    if coverage["everyToolBearingStepCovered"] is not True:
        raise ValueError(
            "ToolCallListV1 stepCoverage.everyToolBearingStepCovered must be true"
        )
    if coverage["missingSteps"]:
        raise ValueError(
            "ToolCallListV1 stepCoverage.missingSteps must be empty"
        )
    if coverage["duplicateSteps"]:
        raise ValueError(
            "ToolCallListV1 stepCoverage.duplicateSteps must be empty"
        )
    if coverage["distinctCoveredStepCount"] != tool_bearing_count:
        raise ValueError(
            f"ToolCallListV1 stepCoverage.distinctCoveredStepCount must equal {tool_bearing_count}"
        )


def _validate_promotion_conditions(
    promotion: dict[str, Any],
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> None:
    _require_fields(
        "ToolCallListV1 promotionConditions",
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
            f"ToolCallListV1 promotionConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_PROMOTION}"
        )
    if promotion["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "ToolCallListV1 promotionConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if promotion["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"ToolCallListV1 promotionConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if promotion["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"ToolCallListV1 promotionConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if promotion["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "ToolCallListV1 promotionConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if promotion["requiredPolicyUnlocked"] is not REQUIRED_POLICY_UNLOCKED:
        raise ValueError(
            "ToolCallListV1 promotionConditions.requiredPolicyUnlocked must be true"
        )
    if promotion["currentPolicyUnlocked"] is not expected_unlocked:
        raise ValueError(
            "ToolCallListV1 promotionConditions.currentPolicyUnlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_promoted = (
        promotion["currentVerdict"] == REQUIRED_VERDICT_FOR_PROMOTION
        and promotion["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and promotion["currentPolicyUnlocked"] is True
    )
    if promotion["promoted"] is not expected_promoted:
        raise ValueError(
            "ToolCallListV1 promotionConditions.promoted must be true only when verdict, run terminal state and policy unlock all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("ToolCallListV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("ToolCallListV1 sourceArtifacts entries must be objects")
        _require_fields(
            "ToolCallListV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"ToolCallListV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"ToolCallListV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"ToolCallListV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"ToolCallListV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"ToolCallListV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"ToolCallListV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def _validate_step_list_binding(
    binding: dict[str, Any], root: Path, step_list: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 stepListBinding",
        binding,
        [
            "stepListRef",
            "stepListSchemaVersion",
            "stepListEnvelopeSchemaVersion",
            "stepListId",
            "stepListContentHash",
            "stepCount",
            "toolBearingStepCount",
        ],
    )
    if binding["stepListRef"] != STEP_LIST_ARTIFACT_PATH:
        raise ValueError(
            f"ToolCallListV1 stepListBinding.stepListRef must equal {STEP_LIST_ARTIFACT_PATH}"
        )
    if binding["stepListSchemaVersion"] != STEP_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 stepListBinding.stepListSchemaVersion must equal {STEP_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression run.json steps array reuse is forbidden"
        )
    if binding["stepListEnvelopeSchemaVersion"] != STEP_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 stepListBinding.stepListEnvelopeSchemaVersion must equal {STEP_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["stepListId"] != STEP_LIST_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 stepListBinding.stepListId must equal {STEP_LIST_ARTIFACT_ID}"
        )
    full_path = root / binding["stepListRef"]
    if binding["stepListContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 stepListBinding.stepListContentHash must match the on-disk StepListV1 artifact"
        )
    if binding["stepCount"] != step_list["stepCount"]:
        raise ValueError(
            "ToolCallListV1 stepListBinding.stepCount must equal StepListV1.stepCount"
        )
    tool_bearing_count = len(_tool_bearing_steps(step_list))
    if binding["toolBearingStepCount"] != tool_bearing_count:
        raise ValueError(
            "ToolCallListV1 stepListBinding.toolBearingStepCount must equal the StepListV1 tool-bearing step count"
        )


def _validate_run_binding(
    binding: dict[str, Any], root: Path, run_artifact: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 runBinding",
        binding,
        [
            "runRef",
            "runSchemaVersion",
            "runEnvelopeSchemaVersion",
            "runId",
            "runContentHash",
            "runIdentifier",
            "runState",
        ],
    )
    if binding["runRef"] != RUN_ARTIFACT_PATH:
        raise ValueError(
            f"ToolCallListV1 runBinding.runRef must equal {RUN_ARTIFACT_PATH}"
        )
    if binding["runSchemaVersion"] != RUN_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 runBinding.runSchemaVersion must equal {RUN_ARTIFACT_SCHEMA_VERSION}; "
            "regression run.json reuse is forbidden"
        )
    if binding["runEnvelopeSchemaVersion"] != RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 runBinding.runEnvelopeSchemaVersion must equal {RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runId"] != RUN_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 runBinding.runId must equal {RUN_ARTIFACT_ID}"
        )
    full_path = root / binding["runRef"]
    if binding["runContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 runBinding.runContentHash must match the on-disk RunV1 artifact"
        )
    if binding["runIdentifier"] != run_artifact["runId"]:
        raise ValueError(
            "ToolCallListV1 runBinding.runIdentifier must equal RunV1.runId"
        )
    if binding["runState"] != run_artifact["runState"]:
        raise ValueError(
            "ToolCallListV1 runBinding.runState must equal RunV1.runState"
        )


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ToolCallListV1 taskSpecBinding",
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
            f"ToolCallListV1 taskSpecBinding.taskSpecRef must equal {TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 taskSpecBinding.taskSpecSchemaVersion must equal {TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; "
            "regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal {TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"ToolCallListV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if binding["taskSpecContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ToolCallListV1 capabilityManifestBinding",
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
            f"ToolCallListV1 capabilityManifestBinding.capabilityManifestRef must equal {CAPABILITY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal {CAPABILITY_MANIFEST_SCHEMA_VERSION}; "
            "regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal {CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 capabilityManifestBinding.capabilityManifestId must equal {CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["capabilityManifestRef"]
    if binding["capabilityManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 capabilityManifestBinding.capabilityManifestContentHash must match the on-disk capability manifest"
        )


def _validate_run_event_log_binding(
    binding: dict[str, Any], root: Path, run_event_log: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 runEventLogBinding",
        binding,
        [
            "runEventLogRef",
            "runEventLogSchemaVersion",
            "runEventLogEnvelopeSchemaVersion",
            "runEventLogId",
            "runEventLogContentHash",
            "eventCount",
            "terminalState",
        ],
    )
    if binding["runEventLogRef"] != RUN_EVENT_LOG_ARTIFACT_PATH:
        raise ValueError(
            f"ToolCallListV1 runEventLogBinding.runEventLogRef must equal {RUN_EVENT_LOG_ARTIFACT_PATH}"
        )
    if binding["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 runEventLogBinding.runEventLogSchemaVersion must equal {RUN_EVENT_LOG_SCHEMA_VERSION}; "
            "regression events.jsonl reuse is forbidden"
        )
    if binding["runEventLogEnvelopeSchemaVersion"] != RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 runEventLogBinding.runEventLogEnvelopeSchemaVersion must equal {RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runEventLogId"] != RUN_EVENT_LOG_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 runEventLogBinding.runEventLogId must equal {RUN_EVENT_LOG_ARTIFACT_ID}"
        )
    full_path = root / binding["runEventLogRef"]
    if binding["runEventLogContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 runEventLogBinding.runEventLogContentHash must match the on-disk run event log"
        )
    if binding["eventCount"] != run_event_log["eventCount"]:
        raise ValueError(
            "ToolCallListV1 runEventLogBinding.eventCount must equal RunEventLogV1.eventCount"
        )
    if binding["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "ToolCallListV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )


def _validate_observation_list_binding(
    binding: dict[str, Any], root: Path, observation_list: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 observationListBinding",
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
            f"ToolCallListV1 observationListBinding.observationListRef must equal {OBSERVATION_LIST_ARTIFACT_PATH}"
        )
    if binding["observationListSchemaVersion"] != OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 observationListBinding.observationListSchemaVersion must equal {OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression observation reuse is forbidden"
        )
    if binding["observationListEnvelopeSchemaVersion"] != OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 observationListBinding.observationListEnvelopeSchemaVersion must equal {OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["observationListId"] != OBSERVATION_LIST_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 observationListBinding.observationListId must equal {OBSERVATION_LIST_ARTIFACT_ID}"
        )
    full_path = root / binding["observationListRef"]
    if binding["observationListContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 observationListBinding.observationListContentHash must match the on-disk observation list"
        )
    if binding["observationItemCount"] != observation_list["observationItemCount"]:
        raise ValueError(
            "ToolCallListV1 observationListBinding.observationItemCount must equal ObservationListV1.observationItemCount"
        )


def _validate_evidence_list_binding(
    binding: dict[str, Any], root: Path, evidence_list: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 evidenceListBinding",
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
            f"ToolCallListV1 evidenceListBinding.evidenceListRef must equal {EVIDENCE_LIST_ARTIFACT_PATH}"
        )
    if binding["evidenceListSchemaVersion"] != EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 evidenceListBinding.evidenceListSchemaVersion must equal {EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression evidence-list-v1 reuse is forbidden"
        )
    if binding["evidenceListEnvelopeSchemaVersion"] != EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 evidenceListBinding.evidenceListEnvelopeSchemaVersion must equal {EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["evidenceListId"] != EVIDENCE_LIST_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 evidenceListBinding.evidenceListId must equal {EVIDENCE_LIST_ARTIFACT_ID}"
        )
    full_path = root / binding["evidenceListRef"]
    if binding["evidenceListContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 evidenceListBinding.evidenceListContentHash must match the on-disk evidence list artifact"
        )
    if binding["evidenceItemCount"] != evidence_list["evidenceItemCount"]:
        raise ValueError(
            "ToolCallListV1 evidenceListBinding.evidenceItemCount must equal EvidenceListV1.evidenceItemCount"
        )


def _validate_verifier_result_binding(
    binding: dict[str, Any], root: Path, verifier_result: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 verifierResultBinding",
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
            f"ToolCallListV1 verifierResultBinding.verifierResultRef must equal {VERIFIER_RESULT_ARTIFACT_PATH}"
        )
    if binding["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 verifierResultBinding.verifierResultSchemaVersion must equal {VERIFIER_RESULT_SCHEMA_VERSION}; "
            "regression result artifact reuse is forbidden"
        )
    if binding["verifierResultEnvelopeSchemaVersion"] != VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 verifierResultBinding.verifierResultEnvelopeSchemaVersion must equal {VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["verifierResultId"] != VERIFIER_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 verifierResultBinding.verifierResultId must equal {VERIFIER_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["verifierResultRef"]
    if binding["verifierResultContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 verifierResultBinding.verifierResultContentHash must match the on-disk verifier result"
        )
    if binding["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"ToolCallListV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}; got {binding['verdict']}"
        )
    if binding["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "ToolCallListV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )


def _validate_delivery_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ToolCallListV1 deliveryManifestBinding",
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
            f"ToolCallListV1 deliveryManifestBinding.deliveryManifestRef must equal {DELIVERY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["deliveryManifestSchemaVersion"] != DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 deliveryManifestBinding.deliveryManifestSchemaVersion must equal {DELIVERY_MANIFEST_SCHEMA_VERSION}; "
            "multi-agent-delivery-manifest reuse is forbidden"
        )
    if binding["deliveryManifestEnvelopeSchemaVersion"] != DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 deliveryManifestBinding.deliveryManifestEnvelopeSchemaVersion must equal {DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["deliveryManifestId"] != DELIVERY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 deliveryManifestBinding.deliveryManifestId must equal {DELIVERY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["deliveryManifestRef"]
    if binding["deliveryManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 deliveryManifestBinding.deliveryManifestContentHash must match the on-disk delivery manifest"
        )


def _validate_policy_manifest_binding(
    binding: dict[str, Any], root: Path, policy_manifest: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 policyManifestBinding",
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
            f"ToolCallListV1 policyManifestBinding.policyManifestRef must equal {POLICY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["policyManifestSchemaVersion"] != POLICY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 policyManifestBinding.policyManifestSchemaVersion must equal {POLICY_MANIFEST_SCHEMA_VERSION}; "
            "regression / adapter policy reuse is forbidden"
        )
    if binding["policyManifestEnvelopeSchemaVersion"] != POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 policyManifestBinding.policyManifestEnvelopeSchemaVersion must equal {POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["policyManifestId"] != POLICY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"ToolCallListV1 policyManifestBinding.policyManifestId must equal {POLICY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["policyManifestRef"]
    if binding["policyManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 policyManifestBinding.policyManifestContentHash must match the on-disk policy manifest"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if binding["unlocked"] is not expected_unlocked:
        raise ValueError(
            "ToolCallListV1 policyManifestBinding.unlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )


def _validate_approval_decision_binding(
    binding: dict[str, Any], root: Path, approval_decision: dict[str, Any]
) -> None:
    _require_fields(
        "ToolCallListV1 approvalDecisionBinding",
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
            f"ToolCallListV1 approvalDecisionBinding.approvalDecisionRef must equal {HUMAN_APPROVAL_DECISION_ARTIFACT_PATH}"
        )
    if binding["approvalDecisionSchemaVersion"] != HUMAN_APPROVAL_DECISION_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 approvalDecisionBinding.approvalDecisionSchemaVersion must equal {HUMAN_APPROVAL_DECISION_SCHEMA_VERSION}"
        )
    if binding["approvalDecisionId"] != approval_decision["id"]:
        raise ValueError(
            "ToolCallListV1 approvalDecisionBinding.approvalDecisionId must equal HumanApprovalDecisionV1.id"
        )
    full_path = root / binding["approvalDecisionRef"]
    if binding["approvalDecisionContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "ToolCallListV1 approvalDecisionBinding.approvalDecisionContentHash must match the on-disk approval decision"
        )
    expected_granted = bool(approval_decision.get("decision", {}).get("approvalGranted", False))
    if binding["approvalGranted"] is not expected_granted:
        raise ValueError(
            "ToolCallListV1 approvalDecisionBinding.approvalGranted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )


def validate_tool_call_list_artifact(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ToolCallListV1",
        manifest,
        [
            "schemaVersion",
            "artifactEnvelopeSchemaVersion",
            "toolCallItemSchemaVersion",
            "id",
            "generatedAt",
            "kind",
            "scope",
            "workloadType",
            "workloadCategory",
            "creatorAgent",
            "verifierVerdictOwner",
            "runIdentifier",
            "toolCallCount",
            "toolCallStatusDomain",
            "sideEffectClassDomain",
            "forbiddenSideEffectClasses",
            "sourceAgentDomain",
            "toolBearingStepKinds",
            "verdictDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "toolCallItems",
            "stepCoverage",
            "stepListBinding",
            "runBinding",
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
    if manifest["schemaVersion"] != TOOL_CALL_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 schemaVersion must be {TOOL_CALL_LIST_ARTIFACT_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["toolCallItemSchemaVersion"] != TOOL_CALL_ITEM_SCHEMA_VERSION:
        raise ValueError(
            f"ToolCallListV1 toolCallItemSchemaVersion must be {TOOL_CALL_ITEM_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"ToolCallListV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"ToolCallListV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"ToolCallListV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"ToolCallListV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"ToolCallListV1 workloadType must be {WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"ToolCallListV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"ToolCallListV1 creatorAgent must be {CREATOR_AGENT}")
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"ToolCallListV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; creator must not own the verdict"
        )
    if manifest["runIdentifier"] != RUN_IDENTIFIER:
        raise ValueError(
            f"ToolCallListV1 runIdentifier must equal {RUN_IDENTIFIER}; reuse of regression run identifiers is forbidden"
        )
    if manifest["toolCallCount"] != EXPECTED_TOOL_CALL_COUNT:
        raise ValueError(
            f"ToolCallListV1 toolCallCount must equal {EXPECTED_TOOL_CALL_COUNT}"
        )
    if manifest["toolCallStatusDomain"] != list(TOOL_CALL_STATUS_DOMAIN):
        raise ValueError(
            f"ToolCallListV1 toolCallStatusDomain must equal {TOOL_CALL_STATUS_DOMAIN}"
        )
    if manifest["sideEffectClassDomain"] != list(SIDE_EFFECT_CLASS_DOMAIN):
        raise ValueError(
            f"ToolCallListV1 sideEffectClassDomain must equal {SIDE_EFFECT_CLASS_DOMAIN}"
        )
    if manifest["forbiddenSideEffectClasses"] != list(FORBIDDEN_SIDE_EFFECT_CLASSES):
        raise ValueError(
            f"ToolCallListV1 forbiddenSideEffectClasses must equal {FORBIDDEN_SIDE_EFFECT_CLASSES}"
        )
    if manifest["sourceAgentDomain"] != list(SOURCE_AGENT_DOMAIN):
        raise ValueError(
            f"ToolCallListV1 sourceAgentDomain must equal {SOURCE_AGENT_DOMAIN}"
        )
    if manifest["toolBearingStepKinds"] != list(TOOL_BEARING_STEP_KINDS):
        raise ValueError(
            f"ToolCallListV1 toolBearingStepKinds must equal {TOOL_BEARING_STEP_KINDS}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"ToolCallListV1 verdictDomain must equal {VERDICT_DOMAIN}"
        )
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"ToolCallListV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )
    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"ToolCallListV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(
                f"ToolCallListV1 permissionFlags.{flag} must be false"
            )

    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    observation_list = _load_json(root / OBSERVATION_LIST_ARTIFACT_PATH)
    evidence_list = _load_json(root / EVIDENCE_LIST_ARTIFACT_PATH)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    run_artifact = _load_json(root / RUN_ARTIFACT_PATH)
    step_list = _load_json(root / STEP_LIST_ARTIFACT_PATH)

    _validate_tool_call_items(
        manifest["toolCallItems"], step_list, run_event_log, observation_list
    )
    if manifest["toolCallCount"] != len(manifest["toolCallItems"]):
        raise ValueError("ToolCallListV1 toolCallCount must equal len(toolCallItems)")

    _validate_step_coverage(manifest["stepCoverage"], step_list)
    _validate_step_list_binding(manifest["stepListBinding"], root, step_list)
    _validate_run_binding(manifest["runBinding"], root, run_artifact)
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
        "ToolCallListV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"ToolCallListV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"ToolCallListV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"ToolCallListV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "ToolCallListV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionRunArtifact",
            "reusesRegressionResultArtifact",
            "reusesRegressionEventsArtifact",
            "reusesRegressionRunStepArray",
            "reusesRegressionToolCallArtifact",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionRunArtifact"] is not False:
        raise ValueError(
            "ToolCallListV1 must not reuse the first-workload regression run.json artifact"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "ToolCallListV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesRegressionEventsArtifact"] is not False:
        raise ValueError(
            "ToolCallListV1 must not reuse the first-workload regression events.jsonl artifact"
        )
    if isolation["reusesRegressionRunStepArray"] is not False:
        raise ValueError(
            "ToolCallListV1 must not reuse the first-workload regression run.json steps array"
        )
    if isolation["reusesRegressionToolCallArtifact"] is not False:
        raise ValueError(
            "ToolCallListV1 must not reuse any first-workload regression tool-call artifact"
        )
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError(
            "ToolCallListV1 must not reuse the send_email capability"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"ToolCallListV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"ToolCallListV1 must not embed regression/email field {term} outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"ToolCallListV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            f"ToolCallListV1 coordinationBinding must include {sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"ToolCallListV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 7:
        raise ValueError(
            "ToolCallListV1 invariants must declare at least seven workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tool-call-list-artifact")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_tool_call_list_artifact(root)
        _write_json(args.out, manifest)
        print(f"Wrote ToolCallListV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_tool_call_list_artifact(manifest, root)
        print(f"Validated ToolCallListV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

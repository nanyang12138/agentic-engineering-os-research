"""RunEventLogV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``RunEventLogV1`` ArtifactV1 subtype.
It captures the canonical OS-kernel event log for any workload ``Run``: an
ordered sequence of ``RunEventV1`` records with stable ids, monotonically
non-decreasing timestamps, an event-type / status / sourceCapability /
sourceAgent / payloadHash field set, and explicit ``RunControl`` state
transitions.

The artifact answers four OS-kernel invariants at once:

- ``RunEvent`` primitive: every event has a workload-independent ``eventId``,
  ``schemaVersion``, ``sequence``, ``timestampMs``, ``eventType``, ``status``,
  ``sourceCapability``, ``sourceAgent``, ``payloadHash``, ``payload`` and
  ``runControlStateAfter``. The fields do not reference regression or
  email-specific schemas and can be reused by Code Patch / Review Loop,
  PR Review, Documentation Update, Incident / Log Analysis, and other
  engineering workloads.
- ``Artifact`` envelope reuse: the log is an ``ArtifactV1`` subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) that joins the existing
  ``CapabilityManifestV1`` / ``TestExecutionResultV1`` / ``FailureTriageReportV1``
  / ``VerifierResultV1`` subtypes.
- ``TaskSpec`` and ``Capability`` binding: the log pins the upstream
  ``TestExecutionTaskSpecV1`` envelope and the upstream
  ``CapabilityManifestV1`` artifact by content hash. Every event's
  ``sourceCapability`` must be either the workload-independent run-kernel
  sentinel or one of the names in
  ``CapabilityManifestV1.capabilities[*].name``.
- ``RunControl`` state machine: the log embeds the workload-independent run
  state machine; every transition between successive
  ``runControlStateAfter`` values must appear in the artifact's declared
  ``allowedRunControlTransitions``.

Key invariants this module enforces:

- The log is an ``ArtifactV1`` envelope subtype distinct from every existing
  creator-owned or verifier-owned test_execution_failure_triage subtype;
  ``schemaVersion`` is ``run-event-log-v1`` and ``kind`` is ``RunEventLogV1``.
- The log binds the bound ``TestExecutionTaskSpecV1`` envelope, the bound
  ``CapabilityManifestV1`` artifact, and all five coordination contracts by
  content hash, so a drift in any upstream artifact invalidates the log.
- Events are ordered: ``sequence`` starts at 0 and increases by 1; timestamps
  are monotonically non-decreasing; the first event is ``run.created`` and
  the last event is ``run.completed`` (or ``run.failed`` if the run failed).
- Every event id has the format ``evt-<runIdentifier>-<sequence padded>``;
  duplicate event ids are rejected.
- Each event's ``runControlStateAfter`` is in the declared run-state set, and
  each (previous, current) pair appears in ``allowedRunControlTransitions``.
- Each event's ``payloadHash`` equals ``sha256`` over the canonical JSON of
  the embedded ``payload`` (sorted keys, UTF-8, no trailing newline).
- The verifier owns acceptance; ``verifierVerdictOwner`` is
  ``verifier-runtime-v1`` and ``creatorMustNotOwnVerdict`` is ``true``.
- The artifact carries no external side effects, no repository mutation, no
  GUI / browser / desktop call, no public access, and no delivery.

The artifact is fully self-contained (synthetic deterministic events) so it
remains deterministic across Linux / macOS / Windows and requires no real
run kernel to validate.
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
from test_execution_task_spec import (
    TASK_SPEC_ARTIFACT_PATH as TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
    TASK_SPEC_ID as TEST_EXECUTION_TASK_SPEC_ID,
    TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
    validate_test_execution_task_spec,
)


RUN_EVENT_LOG_SCHEMA_VERSION = "run-event-log-v1"
RUN_EVENT_SCHEMA_VERSION = "run-event-v1"
RUN_STATE_MACHINE_SCHEMA_VERSION = "run-state-machine-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "RunEventLogV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-run-event-log-kernel-contract"
RUN_EVENT_LOG_ARTIFACT_PATH = (
    "artifacts/state/post_mvp_test_execution_run_event_log.json"
)
RUN_IDENTIFIER = "run-post-mvp-test-execution-failure-triage"

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_run_event_log_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERIFIER_VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

RUN_KERNEL_CAPABILITY = "__run_kernel__"

RUN_CONTROL_STATES = [
    "created",
    "planning",
    "waiting_context",
    "running",
    "verifying",
    "completed",
    "failed",
]
ALLOWED_RUN_CONTROL_TRANSITIONS: list[list[str]] = [
    ["created", "planning"],
    ["planning", "waiting_context"],
    ["waiting_context", "running"],
    ["running", "running"],
    ["running", "verifying"],
    ["verifying", "completed"],
    ["verifying", "failed"],
]
INITIAL_RUN_CONTROL_STATE = "created"
TERMINAL_RUN_CONTROL_STATES = ["completed", "failed"]

EVENT_TYPE_DOMAIN = [
    "run.created",
    "task_spec.generated",
    "capability.invoked",
    "capability.completed",
    "artifact.written",
    "verifier.completed",
    "run.completed",
    "run.failed",
]
EVENT_STATUS_DOMAIN = ["started", "completed", "failed"]
SOURCE_AGENT_DOMAIN = ["run_kernel", "creator_agent", "verifier-runtime-v1"]

EVENT_BLUEPRINT: list[dict[str, Any]] = [
    {
        "eventType": "run.created",
        "status": "completed",
        "sourceCapability": RUN_KERNEL_CAPABILITY,
        "sourceAgent": "run_kernel",
        "runControlStateAfter": "created",
        "timestampMs": 0,
        "payload": {
            "runIdentifier": RUN_IDENTIFIER,
            "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        },
    },
    {
        "eventType": "task_spec.generated",
        "status": "completed",
        "sourceCapability": RUN_KERNEL_CAPABILITY,
        "sourceAgent": "run_kernel",
        "runControlStateAfter": "planning",
        "timestampMs": 100,
        "payload": {
            "taskSpecRef": TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
            "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        },
    },
    {
        "eventType": "capability.invoked",
        "status": "started",
        "sourceCapability": "read_test_execution_result",
        "sourceAgent": "creator_agent",
        "runControlStateAfter": "waiting_context",
        "timestampMs": 200,
        "payload": {
            "capabilityRef": "capability://post-mvp/test_execution/read_test_execution_result",
            "inputSchema": "ReadTestExecutionResultInputV1",
        },
    },
    {
        "eventType": "capability.completed",
        "status": "completed",
        "sourceCapability": "read_test_execution_result",
        "sourceAgent": "creator_agent",
        "runControlStateAfter": "running",
        "timestampMs": 300,
        "payload": {
            "capabilityRef": "capability://post-mvp/test_execution/read_test_execution_result",
            "outputSchema": "ReadTestExecutionResultOutputV1",
        },
    },
    {
        "eventType": "capability.invoked",
        "status": "started",
        "sourceCapability": "collect_test_failure_evidence",
        "sourceAgent": "creator_agent",
        "runControlStateAfter": "running",
        "timestampMs": 400,
        "payload": {
            "capabilityRef": "capability://post-mvp/test_execution/collect_test_failure_evidence",
            "inputSchema": "CollectTestFailureEvidenceInputV1",
        },
    },
    {
        "eventType": "capability.completed",
        "status": "completed",
        "sourceCapability": "collect_test_failure_evidence",
        "sourceAgent": "creator_agent",
        "runControlStateAfter": "running",
        "timestampMs": 500,
        "payload": {
            "capabilityRef": "capability://post-mvp/test_execution/collect_test_failure_evidence",
            "outputSchema": "CollectTestFailureEvidenceOutputV1",
        },
    },
    {
        "eventType": "capability.invoked",
        "status": "started",
        "sourceCapability": "classify_test_failure",
        "sourceAgent": "creator_agent",
        "runControlStateAfter": "running",
        "timestampMs": 600,
        "payload": {
            "capabilityRef": "capability://post-mvp/test_execution/classify_test_failure",
            "inputSchema": "ClassifyTestFailureInputV1",
        },
    },
    {
        "eventType": "capability.completed",
        "status": "completed",
        "sourceCapability": "classify_test_failure",
        "sourceAgent": "creator_agent",
        "runControlStateAfter": "running",
        "timestampMs": 700,
        "payload": {
            "capabilityRef": "capability://post-mvp/test_execution/classify_test_failure",
            "outputSchema": "ClassifyTestFailureOutputV1",
        },
    },
    {
        "eventType": "capability.invoked",
        "status": "started",
        "sourceCapability": "write_artifact",
        "sourceAgent": "creator_agent",
        "runControlStateAfter": "running",
        "timestampMs": 800,
        "payload": {
            "capabilityRef": "capability://post-mvp/test_execution/write_artifact",
            "inputSchema": "WriteArtifactInputV1",
        },
    },
    {
        "eventType": "artifact.written",
        "status": "completed",
        "sourceCapability": "write_artifact",
        "sourceAgent": "creator_agent",
        "runControlStateAfter": "running",
        "timestampMs": 900,
        "payload": {
            "capabilityRef": "capability://post-mvp/test_execution/write_artifact",
            "outputSchema": "WriteArtifactOutputV1",
            "artifactKinds": [
                "TestExecutionResultV1",
                "FailureTriageReportV1",
            ],
        },
    },
    {
        "eventType": "verifier.completed",
        "status": "completed",
        "sourceCapability": RUN_KERNEL_CAPABILITY,
        "sourceAgent": "verifier-runtime-v1",
        "runControlStateAfter": "verifying",
        "timestampMs": 1000,
        "payload": {
            "verifierAgent": "verifier-runtime-v1",
            "verdictDomain": list(VERIFIER_VERDICT_DOMAIN),
        },
    },
    {
        "eventType": "run.completed",
        "status": "completed",
        "sourceCapability": RUN_KERNEL_CAPABILITY,
        "sourceAgent": "run_kernel",
        "runControlStateAfter": "completed",
        "timestampMs": 1100,
        "payload": {
            "runIdentifier": RUN_IDENTIFIER,
            "terminalState": "completed",
        },
    },
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
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

REQUIRED_POLICY_FLAGS = [
    "externalSideEffectsAllowed",
    "repositoryMutationAllowed",
    "externalCommunicationAllowed",
    "releaseOrDeploymentAllowed",
    "guiOrBrowserOrDesktopCallAllowed",
    "publicAccessAllowed",
]

REQUIRED_VERIFIER_FLAGS = [
    "mustValidateSchema",
    "mustValidateTaskSpecBinding",
    "mustValidateCapabilityManifestBinding",
    "mustValidateEventSequence",
    "mustValidatePayloadHashes",
    "mustValidateRunControlTransitions",
    "mustEnforcePolicyBoundary",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "RunEventLogV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype.",
    "RunEventLogV1 must bind the TestExecutionTaskSpecV1 envelope, the CapabilityManifestV1 artifact, and all five coordination contracts by content hash.",
    "RunEventLogV1 events must be ordered: sequences are contiguous from 0 and timestamps are monotonically non-decreasing.",
    "RunEventLogV1 first event must be run.created and the last event must be run.completed or run.failed.",
    "RunEventLogV1 every event sourceCapability must be the run-kernel sentinel or appear in CapabilityManifestV1.capabilities[*].name.",
    "RunEventLogV1 every event payloadHash must equal sha256 over canonical payload JSON.",
    "RunEventLogV1 every (previous, current) runControlStateAfter pair must appear in allowedRunControlTransitions.",
    "RunEventLogV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance.",
    "RunEventLogV1 must keep external side effects, repository mutation, external communication, GUI/desktop access, public access, and release/deployment disabled.",
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
            f"RunEventLogV1 paths must be POSIX relative repository paths: {path}"
        )


def _canonical_payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_id(sequence: int) -> str:
    return f"evt-{RUN_IDENTIFIER}-{sequence:04d}"


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"RunEventLogV1 source artifact does not exist: {relative_path}"
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
                f"RunEventLogV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> dict[str, Any]:
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
    return capability_manifest


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"RunEventLogV1 taskSpecBinding requires artifact: {relative_path}"
        )
    return {
        "taskSpecRef": relative_path,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecContentHash": _stable_file_hash(full_path),
    }


def _build_capability_manifest_binding(root: Path) -> dict[str, Any]:
    relative_path = CAPABILITY_MANIFEST_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"RunEventLogV1 capabilityManifestBinding requires artifact: {relative_path}"
        )
    return {
        "capabilityManifestRef": relative_path,
        "capabilityManifestSchemaVersion": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "capabilityManifestEnvelopeSchemaVersion": CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "capabilityManifestId": CAPABILITY_MANIFEST_ARTIFACT_ID,
        "capabilityManifestContentHash": _stable_file_hash(full_path),
    }


def _build_events(allowed_capability_names: set[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for sequence, blueprint in enumerate(EVENT_BLUEPRINT):
        payload = blueprint["payload"]
        event = {
            "schemaVersion": RUN_EVENT_SCHEMA_VERSION,
            "eventId": _event_id(sequence),
            "sequence": sequence,
            "timestampMs": blueprint["timestampMs"],
            "eventType": blueprint["eventType"],
            "status": blueprint["status"],
            "sourceCapability": blueprint["sourceCapability"],
            "sourceAgent": blueprint["sourceAgent"],
            "runControlStateAfter": blueprint["runControlStateAfter"],
            "payload": json.loads(json.dumps(payload, sort_keys=True)),
            "payloadHash": _canonical_payload_hash(payload),
        }
        capability_name = event["sourceCapability"]
        if (
            capability_name != RUN_KERNEL_CAPABILITY
            and capability_name not in allowed_capability_names
        ):
            raise ValueError(
                f"RunEventLogV1 event {event['eventId']} references unknown capability: "
                f"{capability_name}"
            )
        events.append(event)
    return events


def build_run_event_log(root: Path) -> dict[str, Any]:
    capability_manifest = _validate_referenced_artifacts(root)
    allowed_capability_names = {
        capability["name"] for capability in capability_manifest["capabilities"]
    }
    events = _build_events(allowed_capability_names)
    source_artifacts = [
        _artifact_source(role, relative_path, root)
        for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
    ]
    payload: dict[str, Any] = {
        "schemaVersion": RUN_EVENT_LOG_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "runIdentifier": RUN_IDENTIFIER,
        "runEventSchemaVersion": RUN_EVENT_SCHEMA_VERSION,
        "runControlStateMachineSchemaVersion": RUN_STATE_MACHINE_SCHEMA_VERSION,
        "runControlStates": list(RUN_CONTROL_STATES),
        "initialRunControlState": INITIAL_RUN_CONTROL_STATE,
        "terminalRunControlStates": list(TERMINAL_RUN_CONTROL_STATES),
        "allowedRunControlTransitions": [list(pair) for pair in ALLOWED_RUN_CONTROL_TRANSITIONS],
        "eventTypeDomain": list(EVENT_TYPE_DOMAIN),
        "eventStatusDomain": list(EVENT_STATUS_DOMAIN),
        "sourceAgentDomain": list(SOURCE_AGENT_DOMAIN),
        "runKernelCapabilitySentinel": RUN_KERNEL_CAPABILITY,
        "taskSpecBinding": _build_task_spec_binding(root),
        "capabilityManifestBinding": _build_capability_manifest_binding(root),
        "events": events,
        "eventCount": len(events),
        "terminalState": events[-1]["runControlStateAfter"] if events else None,
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateTaskSpecBinding": True,
            "mustValidateCapabilityManifestBinding": True,
            "mustValidateEventSequence": True,
            "mustValidatePayloadHashes": True,
            "mustValidateRunControlTransitions": True,
            "mustEnforcePolicyBoundary": True,
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERIFIER_VERDICT_DOMAIN),
            "creatorMustNotOwnVerdict": True,
        },
        "policyBoundary": {
            "externalSideEffectsAllowed": False,
            "repositoryMutationAllowed": False,
            "externalCommunicationAllowed": False,
            "releaseOrDeploymentAllowed": False,
            "guiOrBrowserOrDesktopCallAllowed": False,
            "publicAccessAllowed": False,
        },
        "regressionWorkloadIsolation": {
            "reusesRegressionRunArtifact": False,
            "reusesRegressionEventsArtifact": False,
            "reusesRegressionResultArtifact": False,
            "reusesEmailDraftArtifact": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "coordinationBinding": _coordination_binding(root),
        "sourceArtifacts": source_artifacts,
        "invariants": list(INVARIANTS),
    }
    validate_run_event_log(payload, root)
    return payload


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "RunEventLogV1 taskSpecBinding",
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
            f"RunEventLogV1 taskSpecBinding.taskSpecRef must equal "
            f"{TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"RunEventLogV1 taskSpecBinding.taskSpecSchemaVersion must equal "
            f"{TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunEventLogV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal "
            f"{TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"RunEventLogV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"RunEventLogV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["taskSpecContentHash"] != expected_hash:
        raise ValueError(
            "RunEventLogV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "RunEventLogV1 capabilityManifestBinding",
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
            f"RunEventLogV1 capabilityManifestBinding.capabilityManifestRef must equal "
            f"{CAPABILITY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"RunEventLogV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal "
            f"{CAPABILITY_MANIFEST_SCHEMA_VERSION}; regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunEventLogV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal "
            f"{CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"RunEventLogV1 capabilityManifestBinding.capabilityManifestId must equal "
            f"{CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["capabilityManifestRef"]
    if not full_path.is_file():
        raise ValueError(
            f"RunEventLogV1 capabilityManifestBinding artifact missing: {binding['capabilityManifestRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["capabilityManifestContentHash"] != expected_hash:
        raise ValueError(
            "RunEventLogV1 capabilityManifestBinding.capabilityManifestContentHash must match the on-disk capability manifest"
        )


def _validate_events(
    events: list[Any],
    capability_manifest: dict[str, Any],
    allowed_transitions: list[Any],
    declared_states: list[Any],
    initial_state: str,
    terminal_states: list[Any],
    run_identifier: str,
) -> None:
    if not isinstance(events, list) or not events:
        raise ValueError("RunEventLogV1 events must be a non-empty list")
    transitions_set: set[tuple[str, str]] = set()
    for pair in allowed_transitions:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(
                "RunEventLogV1 allowedRunControlTransitions entries must be [from, to] pairs"
            )
        transitions_set.add((pair[0], pair[1]))
    states_set = set(declared_states)
    terminal_states_set = set(terminal_states)

    allowed_capability_names = {
        capability["name"] for capability in capability_manifest["capabilities"]
    }
    seen_event_ids: set[str] = set()
    previous_state: str | None = None
    previous_timestamp = -1
    expected_event_id_prefix = f"evt-{run_identifier}-"
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError("RunEventLogV1 events entries must be objects")
        _require_fields(
            f"RunEventLogV1 event[{index}]",
            event,
            [
                "schemaVersion",
                "eventId",
                "sequence",
                "timestampMs",
                "eventType",
                "status",
                "sourceCapability",
                "sourceAgent",
                "runControlStateAfter",
                "payload",
                "payloadHash",
            ],
        )
        if event["schemaVersion"] != RUN_EVENT_SCHEMA_VERSION:
            raise ValueError(
                f"RunEventLogV1 event[{index}] schemaVersion must be {RUN_EVENT_SCHEMA_VERSION}; "
                f"regression event schema reuse is forbidden"
            )
        if not isinstance(event["sequence"], int) or isinstance(event["sequence"], bool):
            raise ValueError(
                f"RunEventLogV1 event[{index}] sequence must be an integer"
            )
        if event["sequence"] != index:
            raise ValueError(
                f"RunEventLogV1 event[{index}] sequence must equal {index}; "
                f"sequences must be contiguous from 0"
            )
        if not isinstance(event["eventId"], str) or not event["eventId"]:
            raise ValueError(
                f"RunEventLogV1 event[{index}] eventId must be a non-empty string"
            )
        if not event["eventId"].startswith(expected_event_id_prefix):
            raise ValueError(
                f"RunEventLogV1 event[{index}] eventId must start with {expected_event_id_prefix}; "
                f"got {event['eventId']}"
            )
        if event["eventId"] in seen_event_ids:
            raise ValueError(
                f"RunEventLogV1 duplicate eventId: {event['eventId']}"
            )
        seen_event_ids.add(event["eventId"])
        if (
            not isinstance(event["timestampMs"], int)
            or isinstance(event["timestampMs"], bool)
            or event["timestampMs"] < 0
        ):
            raise ValueError(
                f"RunEventLogV1 event[{index}] timestampMs must be a non-negative integer"
            )
        if event["timestampMs"] < previous_timestamp:
            raise ValueError(
                f"RunEventLogV1 event[{index}] timestampMs must be monotonically non-decreasing"
            )
        previous_timestamp = event["timestampMs"]
        if event["eventType"] not in EVENT_TYPE_DOMAIN:
            raise ValueError(
                f"RunEventLogV1 event[{index}] eventType must be one of {EVENT_TYPE_DOMAIN}; "
                f"got {event['eventType']}"
            )
        if event["status"] not in EVENT_STATUS_DOMAIN:
            raise ValueError(
                f"RunEventLogV1 event[{index}] status must be one of {EVENT_STATUS_DOMAIN}; "
                f"got {event['status']}"
            )
        if event["sourceAgent"] not in SOURCE_AGENT_DOMAIN:
            raise ValueError(
                f"RunEventLogV1 event[{index}] sourceAgent must be one of {SOURCE_AGENT_DOMAIN}; "
                f"got {event['sourceAgent']}"
            )
        capability_name = event["sourceCapability"]
        if (
            capability_name != RUN_KERNEL_CAPABILITY
            and capability_name not in allowed_capability_names
        ):
            raise ValueError(
                f"RunEventLogV1 event[{index}] sourceCapability must be the run-kernel sentinel "
                f"or appear in CapabilityManifestV1.capabilities[*].name; got {capability_name}"
            )
        state_after = event["runControlStateAfter"]
        if state_after not in states_set:
            raise ValueError(
                f"RunEventLogV1 event[{index}] runControlStateAfter must be in declared states; "
                f"got {state_after}"
            )
        if index == 0:
            if state_after != initial_state:
                raise ValueError(
                    f"RunEventLogV1 event[0] runControlStateAfter must equal initialRunControlState "
                    f"{initial_state}; got {state_after}"
                )
            if event["eventType"] != "run.created":
                raise ValueError(
                    "RunEventLogV1 first event eventType must be run.created"
                )
        else:
            transition = (previous_state, state_after)
            if transition not in transitions_set:
                raise ValueError(
                    f"RunEventLogV1 event[{index}] illegal runControlStateAfter transition "
                    f"{previous_state} -> {state_after}"
                )
        previous_state = state_after
        canonical_hash = _canonical_payload_hash(event["payload"])
        if event["payloadHash"] != canonical_hash:
            raise ValueError(
                f"RunEventLogV1 event[{index}] payloadHash must equal sha256 over canonical payload"
            )
        if not isinstance(event["payloadHash"], str) or len(event["payloadHash"]) != 64:
            raise ValueError(
                f"RunEventLogV1 event[{index}] payloadHash must be a 64-character sha256 hex digest"
            )
    if events[-1]["eventType"] not in {"run.completed", "run.failed"}:
        raise ValueError(
            "RunEventLogV1 last event must be run.completed or run.failed"
        )
    if events[-1]["runControlStateAfter"] not in terminal_states_set:
        raise ValueError(
            f"RunEventLogV1 last event runControlStateAfter must be in terminalRunControlStates "
            f"{sorted(terminal_states_set)}"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("RunEventLogV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("RunEventLogV1 sourceArtifacts entries must be objects")
        _require_fields(
            "RunEventLogV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"RunEventLogV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"RunEventLogV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"RunEventLogV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"RunEventLogV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"RunEventLogV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"RunEventLogV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_run_event_log(log: dict[str, Any], root: Path) -> None:
    _require_fields(
        "RunEventLogV1",
        log,
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
            "runIdentifier",
            "runEventSchemaVersion",
            "runControlStateMachineSchemaVersion",
            "runControlStates",
            "initialRunControlState",
            "terminalRunControlStates",
            "allowedRunControlTransitions",
            "eventTypeDomain",
            "eventStatusDomain",
            "sourceAgentDomain",
            "runKernelCapabilitySentinel",
            "taskSpecBinding",
            "capabilityManifestBinding",
            "events",
            "eventCount",
            "terminalState",
            "verifierExpectations",
            "policyBoundary",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if log["schemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"RunEventLogV1 schemaVersion must be {RUN_EVENT_LOG_SCHEMA_VERSION}"
        )
    if log["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"RunEventLogV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if log["id"] != ARTIFACT_ID:
        raise ValueError(f"RunEventLogV1 id must be {ARTIFACT_ID}")
    if log["generatedAt"] != GENERATED_AT:
        raise ValueError(f"RunEventLogV1 generatedAt must be {GENERATED_AT}")
    if log["kind"] != ARTIFACT_KIND:
        raise ValueError(f"RunEventLogV1 kind must be {ARTIFACT_KIND}")
    if log["scope"] != SCOPE:
        raise ValueError(f"RunEventLogV1 scope must be {SCOPE}")
    if log["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"RunEventLogV1 workloadType must be {WORKLOAD_TYPE}; "
            f"regression workload reuse is forbidden"
        )
    if log["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"RunEventLogV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if log["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(
            f"RunEventLogV1 creatorAgent must be {CREATOR_AGENT}"
        )
    if log["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"RunEventLogV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; "
            f"creator must not own the verdict"
        )
    if log["runIdentifier"] != RUN_IDENTIFIER:
        raise ValueError(
            f"RunEventLogV1 runIdentifier must be {RUN_IDENTIFIER}"
        )
    if log["runEventSchemaVersion"] != RUN_EVENT_SCHEMA_VERSION:
        raise ValueError(
            f"RunEventLogV1 runEventSchemaVersion must be {RUN_EVENT_SCHEMA_VERSION}"
        )
    if log["runControlStateMachineSchemaVersion"] != RUN_STATE_MACHINE_SCHEMA_VERSION:
        raise ValueError(
            f"RunEventLogV1 runControlStateMachineSchemaVersion must be {RUN_STATE_MACHINE_SCHEMA_VERSION}"
        )
    if log["runControlStates"] != list(RUN_CONTROL_STATES):
        raise ValueError(
            f"RunEventLogV1 runControlStates must equal {RUN_CONTROL_STATES}"
        )
    if log["initialRunControlState"] != INITIAL_RUN_CONTROL_STATE:
        raise ValueError(
            f"RunEventLogV1 initialRunControlState must equal {INITIAL_RUN_CONTROL_STATE}"
        )
    if log["terminalRunControlStates"] != list(TERMINAL_RUN_CONTROL_STATES):
        raise ValueError(
            f"RunEventLogV1 terminalRunControlStates must equal {TERMINAL_RUN_CONTROL_STATES}"
        )
    if log["allowedRunControlTransitions"] != [list(pair) for pair in ALLOWED_RUN_CONTROL_TRANSITIONS]:
        raise ValueError(
            f"RunEventLogV1 allowedRunControlTransitions must equal {ALLOWED_RUN_CONTROL_TRANSITIONS}"
        )
    if log["eventTypeDomain"] != list(EVENT_TYPE_DOMAIN):
        raise ValueError(
            f"RunEventLogV1 eventTypeDomain must equal {EVENT_TYPE_DOMAIN}"
        )
    if log["eventStatusDomain"] != list(EVENT_STATUS_DOMAIN):
        raise ValueError(
            f"RunEventLogV1 eventStatusDomain must equal {EVENT_STATUS_DOMAIN}"
        )
    if log["sourceAgentDomain"] != list(SOURCE_AGENT_DOMAIN):
        raise ValueError(
            f"RunEventLogV1 sourceAgentDomain must equal {SOURCE_AGENT_DOMAIN}"
        )
    if log["runKernelCapabilitySentinel"] != RUN_KERNEL_CAPABILITY:
        raise ValueError(
            f"RunEventLogV1 runKernelCapabilitySentinel must equal {RUN_KERNEL_CAPABILITY}"
        )

    _validate_task_spec_binding(log["taskSpecBinding"], root)
    _validate_capability_manifest_binding(log["capabilityManifestBinding"], root)
    capability_manifest = _load_json(root / CAPABILITY_MANIFEST_ARTIFACT_PATH)
    validate_capability_manifest(capability_manifest, root)
    _validate_events(
        log["events"],
        capability_manifest,
        log["allowedRunControlTransitions"],
        log["runControlStates"],
        log["initialRunControlState"],
        log["terminalRunControlStates"],
        log["runIdentifier"],
    )
    if log["eventCount"] != len(log["events"]):
        raise ValueError(
            "RunEventLogV1 eventCount must equal len(events)"
        )
    if log["terminalState"] != log["events"][-1]["runControlStateAfter"]:
        raise ValueError(
            "RunEventLogV1 terminalState must equal the last event runControlStateAfter"
        )

    verifier = log["verifierExpectations"]
    _require_fields(
        "RunEventLogV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"RunEventLogV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"RunEventLogV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != VERIFIER_VERDICT_DOMAIN:
        raise ValueError(
            f"RunEventLogV1 verifierExpectations.verdictDomain must equal {VERIFIER_VERDICT_DOMAIN}"
        )

    policy = log["policyBoundary"]
    _require_fields(
        "RunEventLogV1 policyBoundary", policy, REQUIRED_POLICY_FLAGS
    )
    for flag in REQUIRED_POLICY_FLAGS:
        if policy[flag] is not False:
            raise ValueError(
                f"RunEventLogV1 policyBoundary.{flag} must be false"
            )

    isolation = log["regressionWorkloadIsolation"]
    _require_fields(
        "RunEventLogV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionRunArtifact",
            "reusesRegressionEventsArtifact",
            "reusesRegressionResultArtifact",
            "reusesEmailDraftArtifact",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionRunArtifact"] is not False:
        raise ValueError(
            "RunEventLogV1 must not reuse the regression run.json artifact"
        )
    if isolation["reusesRegressionEventsArtifact"] is not False:
        raise ValueError(
            "RunEventLogV1 must not reuse the regression events.jsonl artifact"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "RunEventLogV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesEmailDraftArtifact"] is not False:
        raise ValueError(
            "RunEventLogV1 must not reuse EmailDraftArtifactV1"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"RunEventLogV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(log, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"RunEventLogV1 must not embed regression/email field {term} "
                f"outside forbiddenFields"
            )

    reuse_path = log["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"RunEventLogV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = log["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            "RunEventLogV1 coordinationBinding must include "
            f"{sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"RunEventLogV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(log["sourceArtifacts"], root)

    invariants = log["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 7:
        raise ValueError(
            "RunEventLogV1 invariants must declare at least seven workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run-event-log")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        log = build_run_event_log(root)
        _write_json(args.out, log)
        print(f"Wrote RunEventLogV1 artifact to {args.out}.")
    if args.validate is not None:
        log = _load_json(args.validate)
        validate_run_event_log(log, root)
        print(f"Validated RunEventLogV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

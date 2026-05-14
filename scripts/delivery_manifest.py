"""DeliveryManifestV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``DeliveryManifestV1`` ArtifactV1
subtype.  It captures the canonical OS-kernel delivery primitive for any
engineering workload: an ordered list of channel-agnostic ``delivery-channel-v1``
records, each binding a single delivery surface (internal status card,
verifier verdict record, human review queue entry, triage artifact handoff,
etc.) to (a) the workload's ``VerifierResultV1`` verdict, (b) the workload's
``RunEventLogV1`` terminal state, and (c) a human approval decision record.

The artifact answers four OS-kernel invariants at once:

- ``Delivery`` primitive: every channel has a workload-independent
  ``schemaVersion``, ``channelName``, ``channelKind``, ``channelStatus``,
  ``approvalRef``, ``policyBoundary``, ``evidenceContract``, and
  ``payloadContract``.  The fields do not reference email, regression, IDE,
  PR, or other workload-specific schemas and can be reused by Code Patch /
  Review Loop, PR Review, Documentation Update, and Incident / Log Analysis.
- ``Artifact`` envelope reuse: the manifest is an ``ArtifactV1`` subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) that joins the existing
  ``CapabilityManifestV1`` / ``TestExecutionResultV1`` /
  ``FailureTriageReportV1`` / ``VerifierResultV1`` / ``RunEventLogV1``
  subtypes.
- ``Verifier`` / ``RunEvent`` / ``Approval`` triple gate: the manifest pins
  the upstream ``TestExecutionTaskSpecV1`` envelope, the upstream
  ``CapabilityManifestV1`` artifact, the upstream ``VerifierResultV1``
  verdict, and the upstream ``RunEventLogV1`` terminal state by content
  hash.  A delivery channel can only unlock when ``verdict == passed``,
  the ``RunEventLogV1`` terminal state is ``completed``, and the bound
  human approval decision is granted.
- ``Policy`` boundary: every channel and the artifact itself disable
  external side effects, repository mutation, external communication,
  release/deployment, GUI/desktop access, and public access.  No real email,
  PR, ticket, Slack, or web delivery is performed.

Key invariants this module enforces:

- The manifest is an ``ArtifactV1`` envelope subtype distinct from every
  existing creator-owned or verifier-owned test_execution_failure_triage
  subtype; ``schemaVersion`` is ``delivery-manifest-v1`` and ``kind`` is
  ``DeliveryManifestV1``.
- The manifest binds the bound ``TestExecutionTaskSpecV1`` envelope, the
  ``CapabilityManifestV1`` artifact, the ``VerifierResultV1`` artifact, the
  ``RunEventLogV1`` artifact, and all five coordination contracts by content
  hash, so a drift in any upstream artifact invalidates the manifest.
- Every channel has a unique ``channelName``, a ``channelKind`` from a
  workload-independent domain, a ``channelStatus`` from a closed domain that
  excludes any "delivered" / "sent" / "published" terminal status, and a
  ``payloadContract`` describing the structured payload by reference rather
  than by content.
- The verifier owns acceptance; ``verifierVerdictOwner`` is
  ``verifier-runtime-v1`` and ``creatorMustNotOwnVerdict`` is ``true``.
- ``requiredVerdictForUnlock`` is ``passed``; channels never claim
  ``unlocked == true`` unless the bound verdict equals ``passed``, the
  bound run terminal state is ``completed``, and the bound approval is
  granted.
- The artifact carries no external side effects, no repository mutation,
  no GUI / browser / desktop call, no public access, and no delivery.

The artifact is fully self-contained (synthetic deterministic channels) so
it remains deterministic across Linux / macOS / Windows and requires no real
delivery runtime to validate.
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
from human_approval import (
    DECISION_ARTIFACT_PATH as HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    validate_human_approval_decision,
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


DELIVERY_MANIFEST_SCHEMA_VERSION = "delivery-manifest-v1"
DELIVERY_CHANNEL_SCHEMA_VERSION = "delivery-channel-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "DeliveryManifestV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-delivery-manifest-kernel-contract"
DELIVERY_MANIFEST_ARTIFACT_PATH = (
    "artifacts/delivery/post_mvp_test_execution_delivery_manifest.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_delivery_manifest_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

REQUIRED_VERDICT_FOR_UNLOCK = "passed"
REQUIRED_TERMINAL_RUN_STATE = "completed"

CHANNEL_KIND_DOMAIN = [
    "internal_run_summary_card",
    "verifier_verdict_record",
    "human_review_queue_entry",
    "triage_artifact_handoff",
    "internal_event_log_archive",
]
CHANNEL_STATUS_DOMAIN = [
    "drafted_internal_only",
    "pending_verdict",
    "pending_approval",
    "pending_policy_unlock",
    "blocked_by_verdict",
    "blocked_by_approval",
    "blocked_by_policy",
]

CHANNEL_BLUEPRINT: list[dict[str, Any]] = [
    {
        "channelName": "internal-test-execution-run-summary-card",
        "channelKind": "internal_run_summary_card",
        "payloadContract": {
            "payloadKind": "structured_json",
            "schemaVersion": "test-execution-result-v1",
            "contractRefs": [
                "TestExecutionResultV1",
                "VerifierResultV1",
            ],
            "rendering": "internal_only",
        },
        "description": "Internal dashboard card summarizing the test execution Run for human review only.",
    },
    {
        "channelName": "verifier-verdict-record-archive",
        "channelKind": "verifier_verdict_record",
        "payloadContract": {
            "payloadKind": "structured_json",
            "schemaVersion": VERIFIER_RESULT_SCHEMA_VERSION,
            "contractRefs": [
                "VerifierResultV1",
                "RunEventLogV1",
            ],
            "rendering": "internal_only",
        },
        "description": "Verifier verdict record persisted to internal evidence store; never published externally.",
    },
    {
        "channelName": "human-review-queue-entry",
        "channelKind": "human_review_queue_entry",
        "payloadContract": {
            "payloadKind": "structured_json",
            "schemaVersion": "human-approval-decision-v1",
            "contractRefs": [
                "HumanApprovalDecisionV1",
                "VerifierResultV1",
            ],
            "rendering": "internal_only",
        },
        "description": "Queue entry that asks a human reviewer to approve or reject the workload outcome.",
    },
    {
        "channelName": "failure-triage-artifact-handoff",
        "channelKind": "triage_artifact_handoff",
        "payloadContract": {
            "payloadKind": "structured_json",
            "schemaVersion": "failure-triage-report-v1",
            "contractRefs": [
                "FailureTriageReportV1",
                "VerifierResultV1",
            ],
            "rendering": "internal_only",
        },
        "description": "Internal handoff of the failure triage report to downstream creator or verifier agents.",
    },
    {
        "channelName": "run-event-log-archive",
        "channelKind": "internal_event_log_archive",
        "payloadContract": {
            "payloadKind": "structured_json",
            "schemaVersion": RUN_EVENT_LOG_SCHEMA_VERSION,
            "contractRefs": [
                "RunEventLogV1",
            ],
            "rendering": "internal_only",
        },
        "description": "Internal archive of the workload Run event log for replay; never exposed externally.",
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
    "test_execution_verifier_result": VERIFIER_RESULT_ARTIFACT_PATH,
    "test_execution_run_event_log": RUN_EVENT_LOG_ARTIFACT_PATH,
    "human_approval_decision": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
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
    "mustValidateVerifierResultBinding",
    "mustValidateRunEventLogBinding",
    "mustValidateApprovalGate",
    "mustEnforceVerdictGate",
    "mustEnforcePolicyBoundary",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "DeliveryManifestV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype.",
    "DeliveryManifestV1 must bind TestExecutionTaskSpecV1, CapabilityManifestV1, VerifierResultV1, RunEventLogV1, and all five coordination contracts by content hash.",
    "DeliveryManifestV1 channels must have unique workload-independent names and kinds from a closed domain.",
    "DeliveryManifestV1 channels never declare a terminal external delivery status; only drafted_internal_only / pending_* / blocked_* are allowed.",
    "DeliveryManifestV1 unlock requires verdict=passed, terminal run state=completed, and granted human approval; channels claiming unlocked=true otherwise are rejected.",
    "DeliveryManifestV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance.",
    "DeliveryManifestV1 must keep external side effects, repository mutation, external communication, GUI/desktop access, public access, and release/deployment disabled at the manifest level and on every channel.",
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
            f"DeliveryManifestV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 source artifact does not exist: {relative_path}"
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
                f"DeliveryManifestV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any]
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
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    validate_verifier_result(verifier_result, root)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    validate_run_event_log(run_event_log, root)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    validate_human_approval_decision(approval_decision, root)
    return verifier_result, run_event_log, approval_decision


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 taskSpecBinding requires artifact: {relative_path}"
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
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 capabilityManifestBinding requires artifact: {relative_path}"
        )
    return {
        "capabilityManifestRef": relative_path,
        "capabilityManifestSchemaVersion": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "capabilityManifestEnvelopeSchemaVersion": CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "capabilityManifestId": CAPABILITY_MANIFEST_ARTIFACT_ID,
        "capabilityManifestContentHash": _stable_file_hash(full_path),
    }


def _build_verifier_result_binding(
    root: Path, verifier_result: dict[str, Any]
) -> dict[str, Any]:
    relative_path = VERIFIER_RESULT_ARTIFACT_PATH
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 verifierResultBinding requires artifact: {relative_path}"
        )
    return {
        "verifierResultRef": relative_path,
        "verifierResultSchemaVersion": VERIFIER_RESULT_SCHEMA_VERSION,
        "verifierResultEnvelopeSchemaVersion": VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION,
        "verifierResultId": VERIFIER_RESULT_ARTIFACT_ID,
        "verifierResultContentHash": _stable_file_hash(full_path),
        "verdict": verifier_result["verdict"],
    }


def _build_run_event_log_binding(
    root: Path, run_event_log: dict[str, Any]
) -> dict[str, Any]:
    relative_path = RUN_EVENT_LOG_ARTIFACT_PATH
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 runEventLogBinding requires artifact: {relative_path}"
        )
    return {
        "runEventLogRef": relative_path,
        "runEventLogSchemaVersion": RUN_EVENT_LOG_SCHEMA_VERSION,
        "runEventLogEnvelopeSchemaVersion": RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION,
        "runEventLogId": RUN_EVENT_LOG_ARTIFACT_ID,
        "runEventLogContentHash": _stable_file_hash(full_path),
        "terminalState": run_event_log["terminalState"],
    }


def _build_approval_gate(approval_decision: dict[str, Any]) -> dict[str, Any]:
    decision_block = approval_decision.get("decision", {})
    decision = decision_block.get("decision")
    granted = decision_block.get("approvalGranted") is True
    return {
        "approvalRecordRef": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
        "approvalRecordSchemaVersion": "human-approval-decision-v1",
        "requiredDecision": "approved",
        "currentDecision": decision,
        "granted": granted,
        "unlocked": granted,
    }


def _build_verdict_gate(verifier_result: dict[str, Any]) -> dict[str, Any]:
    verdict = verifier_result["verdict"]
    unlocked = verdict == REQUIRED_VERDICT_FOR_UNLOCK
    return {
        "requiredVerdict": REQUIRED_VERDICT_FOR_UNLOCK,
        "currentVerdict": verdict,
        "verdictOwner": VERIFIER_VERDICT_OWNER,
        "unlocked": unlocked,
    }


def _build_run_terminal_state_gate(run_event_log: dict[str, Any]) -> dict[str, Any]:
    terminal_state = run_event_log["terminalState"]
    unlocked = terminal_state == REQUIRED_TERMINAL_RUN_STATE
    return {
        "requiredTerminalState": REQUIRED_TERMINAL_RUN_STATE,
        "currentTerminalState": terminal_state,
        "unlocked": unlocked,
    }


def _channel_unlock_decision(
    verdict_unlocked: bool, run_state_unlocked: bool, approval_unlocked: bool
) -> tuple[bool, str]:
    if not verdict_unlocked:
        return False, "blocked_by_verdict"
    if not run_state_unlocked:
        return False, "blocked_by_policy"
    if not approval_unlocked:
        return False, "blocked_by_approval"
    return True, "drafted_internal_only"


def _build_channels(
    verdict_gate: dict[str, Any],
    run_terminal_state_gate: dict[str, Any],
    approval_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    unlocked, status = _channel_unlock_decision(
        verdict_gate["unlocked"],
        run_terminal_state_gate["unlocked"],
        approval_gate["unlocked"],
    )
    channels: list[dict[str, Any]] = []
    for blueprint in CHANNEL_BLUEPRINT:
        channel = {
            "schemaVersion": DELIVERY_CHANNEL_SCHEMA_VERSION,
            "channelName": blueprint["channelName"],
            "channelKind": blueprint["channelKind"],
            "channelStatus": status,
            "unlocked": unlocked,
            "description": blueprint["description"],
            "approvalRef": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
            "evidenceContract": {
                "verifierResultRef": VERIFIER_RESULT_ARTIFACT_PATH,
                "verifierResultSchemaVersion": VERIFIER_RESULT_SCHEMA_VERSION,
                "runEventLogRef": RUN_EVENT_LOG_ARTIFACT_PATH,
                "runEventLogSchemaVersion": RUN_EVENT_LOG_SCHEMA_VERSION,
            },
            "payloadContract": dict(blueprint["payloadContract"]),
            "policyBoundary": {
                "externalSideEffectsAllowed": False,
                "repositoryMutationAllowed": False,
                "externalCommunicationAllowed": False,
                "releaseOrDeploymentAllowed": False,
                "guiOrBrowserOrDesktopCallAllowed": False,
                "publicAccessAllowed": False,
            },
        }
        channels.append(channel)
    return channels


def build_delivery_manifest(root: Path) -> dict[str, Any]:
    verifier_result, run_event_log, approval_decision = _validate_referenced_artifacts(
        root
    )
    verdict_gate = _build_verdict_gate(verifier_result)
    run_terminal_state_gate = _build_run_terminal_state_gate(run_event_log)
    approval_gate = _build_approval_gate(approval_decision)
    channels = _build_channels(verdict_gate, run_terminal_state_gate, approval_gate)
    source_artifacts = [
        _artifact_source(role, relative_path, root)
        for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
    ]
    payload: dict[str, Any] = {
        "schemaVersion": DELIVERY_MANIFEST_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "deliveryChannelSchemaVersion": DELIVERY_CHANNEL_SCHEMA_VERSION,
        "requiredVerdictForUnlock": REQUIRED_VERDICT_FOR_UNLOCK,
        "requiredTerminalRunState": REQUIRED_TERMINAL_RUN_STATE,
        "verdictDomain": list(VERDICT_DOMAIN),
        "channelKindDomain": list(CHANNEL_KIND_DOMAIN),
        "channelStatusDomain": list(CHANNEL_STATUS_DOMAIN),
        "taskSpecBinding": _build_task_spec_binding(root),
        "capabilityManifestBinding": _build_capability_manifest_binding(root),
        "verifierResultBinding": _build_verifier_result_binding(root, verifier_result),
        "runEventLogBinding": _build_run_event_log_binding(root, run_event_log),
        "verdictGate": verdict_gate,
        "runTerminalStateGate": run_terminal_state_gate,
        "approvalGate": approval_gate,
        "channels": channels,
        "channelCount": len(channels),
        "anyChannelUnlocked": any(channel["unlocked"] for channel in channels),
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateTaskSpecBinding": True,
            "mustValidateCapabilityManifestBinding": True,
            "mustValidateVerifierResultBinding": True,
            "mustValidateRunEventLogBinding": True,
            "mustValidateApprovalGate": True,
            "mustEnforceVerdictGate": True,
            "mustEnforcePolicyBoundary": True,
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERDICT_DOMAIN),
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
            "reusesRegressionEmailDraft": False,
            "reusesPhase9DeliveryReport": False,
            "reusesRegressionResultArtifact": False,
            "reusesSendEmailCapability": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "coordinationBinding": _coordination_binding(root),
        "sourceArtifacts": source_artifacts,
        "invariants": list(INVARIANTS),
    }
    validate_delivery_manifest(payload, root)
    return payload


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "DeliveryManifestV1 taskSpecBinding",
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
            f"DeliveryManifestV1 taskSpecBinding.taskSpecRef must equal "
            f"{TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 taskSpecBinding.taskSpecSchemaVersion must equal "
            f"{TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal "
            f"{TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"DeliveryManifestV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    if binding["taskSpecContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "DeliveryManifestV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "DeliveryManifestV1 capabilityManifestBinding",
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
            f"DeliveryManifestV1 capabilityManifestBinding.capabilityManifestRef must equal "
            f"{CAPABILITY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal "
            f"{CAPABILITY_MANIFEST_SCHEMA_VERSION}; regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal "
            f"{CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"DeliveryManifestV1 capabilityManifestBinding.capabilityManifestId must equal "
            f"{CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["capabilityManifestRef"]
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 capabilityManifestBinding artifact missing: {binding['capabilityManifestRef']}"
        )
    if binding["capabilityManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "DeliveryManifestV1 capabilityManifestBinding.capabilityManifestContentHash must match the on-disk capability manifest"
        )


def _validate_verifier_result_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "DeliveryManifestV1 verifierResultBinding",
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
            f"DeliveryManifestV1 verifierResultBinding.verifierResultRef must equal "
            f"{VERIFIER_RESULT_ARTIFACT_PATH}"
        )
    if binding["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 verifierResultBinding.verifierResultSchemaVersion must equal "
            f"{VERIFIER_RESULT_SCHEMA_VERSION}; regression result artifact reuse is forbidden"
        )
    if binding["verifierResultEnvelopeSchemaVersion"] != VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 verifierResultBinding.verifierResultEnvelopeSchemaVersion must equal "
            f"{VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["verifierResultId"] != VERIFIER_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"DeliveryManifestV1 verifierResultBinding.verifierResultId must equal "
            f"{VERIFIER_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["verifierResultRef"]
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 verifierResultBinding artifact missing: {binding['verifierResultRef']}"
        )
    if binding["verifierResultContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "DeliveryManifestV1 verifierResultBinding.verifierResultContentHash must match the on-disk verifier result"
        )
    if binding["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"DeliveryManifestV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}; "
            f"got {binding['verdict']}"
        )
    verifier_result = _load_json(full_path)
    if binding["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "DeliveryManifestV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )


def _validate_run_event_log_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "DeliveryManifestV1 runEventLogBinding",
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
            f"DeliveryManifestV1 runEventLogBinding.runEventLogRef must equal "
            f"{RUN_EVENT_LOG_ARTIFACT_PATH}"
        )
    if binding["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 runEventLogBinding.runEventLogSchemaVersion must equal "
            f"{RUN_EVENT_LOG_SCHEMA_VERSION}; regression events.jsonl reuse is forbidden"
        )
    if binding["runEventLogEnvelopeSchemaVersion"] != RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 runEventLogBinding.runEventLogEnvelopeSchemaVersion must equal "
            f"{RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runEventLogId"] != RUN_EVENT_LOG_ARTIFACT_ID:
        raise ValueError(
            f"DeliveryManifestV1 runEventLogBinding.runEventLogId must equal "
            f"{RUN_EVENT_LOG_ARTIFACT_ID}"
        )
    full_path = root / binding["runEventLogRef"]
    if not full_path.is_file():
        raise ValueError(
            f"DeliveryManifestV1 runEventLogBinding artifact missing: {binding['runEventLogRef']}"
        )
    if binding["runEventLogContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "DeliveryManifestV1 runEventLogBinding.runEventLogContentHash must match the on-disk run event log"
        )
    run_event_log = _load_json(full_path)
    if binding["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "DeliveryManifestV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )


def _validate_channels(
    channels: list[Any],
    verdict_unlocked: bool,
    run_state_unlocked: bool,
    approval_unlocked: bool,
) -> None:
    if not isinstance(channels, list) or not channels:
        raise ValueError("DeliveryManifestV1 channels must be a non-empty list")
    seen_names: set[str] = set()
    kind_domain = set(CHANNEL_KIND_DOMAIN)
    status_domain = set(CHANNEL_STATUS_DOMAIN)
    overall_unlocked, expected_status = _channel_unlock_decision(
        verdict_unlocked, run_state_unlocked, approval_unlocked
    )
    for index, channel in enumerate(channels):
        if not isinstance(channel, dict):
            raise ValueError("DeliveryManifestV1 channels entries must be objects")
        _require_fields(
            f"DeliveryManifestV1 channel[{index}]",
            channel,
            [
                "schemaVersion",
                "channelName",
                "channelKind",
                "channelStatus",
                "unlocked",
                "description",
                "approvalRef",
                "evidenceContract",
                "payloadContract",
                "policyBoundary",
            ],
        )
        if channel["schemaVersion"] != DELIVERY_CHANNEL_SCHEMA_VERSION:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].schemaVersion must be "
                f"{DELIVERY_CHANNEL_SCHEMA_VERSION}; regression channel schema reuse is forbidden"
            )
        name = channel["channelName"]
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].channelName must be a non-empty string"
            )
        if name in seen_names:
            raise ValueError(
                f"DeliveryManifestV1 duplicate channelName: {name}"
            )
        seen_names.add(name)
        if channel["channelKind"] not in kind_domain:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].channelKind must be one of {CHANNEL_KIND_DOMAIN}; "
                f"got {channel['channelKind']}"
            )
        if channel["channelStatus"] not in status_domain:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].channelStatus must be one of {CHANNEL_STATUS_DOMAIN}; "
                f"got {channel['channelStatus']}"
            )
        if channel["channelStatus"] != expected_status:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].channelStatus must equal "
                f"{expected_status} derived from verdict/run/approval gates; got {channel['channelStatus']}"
            )
        if channel["unlocked"] is not overall_unlocked:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].unlocked must equal the gate-derived unlocked decision "
                f"({overall_unlocked})"
            )
        if channel["approvalRef"] != HUMAN_APPROVAL_DECISION_ARTIFACT_PATH:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].approvalRef must equal "
                f"{HUMAN_APPROVAL_DECISION_ARTIFACT_PATH}"
            )
        evidence = channel["evidenceContract"]
        _require_fields(
            f"DeliveryManifestV1 channel[{index}] evidenceContract",
            evidence,
            [
                "verifierResultRef",
                "verifierResultSchemaVersion",
                "runEventLogRef",
                "runEventLogSchemaVersion",
            ],
        )
        if evidence["verifierResultRef"] != VERIFIER_RESULT_ARTIFACT_PATH:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].evidenceContract.verifierResultRef must equal "
                f"{VERIFIER_RESULT_ARTIFACT_PATH}"
            )
        if evidence["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].evidenceContract.verifierResultSchemaVersion must equal "
                f"{VERIFIER_RESULT_SCHEMA_VERSION}"
            )
        if evidence["runEventLogRef"] != RUN_EVENT_LOG_ARTIFACT_PATH:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].evidenceContract.runEventLogRef must equal "
                f"{RUN_EVENT_LOG_ARTIFACT_PATH}"
            )
        if evidence["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].evidenceContract.runEventLogSchemaVersion must equal "
                f"{RUN_EVENT_LOG_SCHEMA_VERSION}"
            )
        payload_contract = channel["payloadContract"]
        _require_fields(
            f"DeliveryManifestV1 channel[{index}] payloadContract",
            payload_contract,
            ["payloadKind", "schemaVersion", "contractRefs", "rendering"],
        )
        if payload_contract["payloadKind"] != "structured_json":
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].payloadContract.payloadKind must be structured_json"
            )
        if payload_contract["rendering"] != "internal_only":
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].payloadContract.rendering must be internal_only"
            )
        if not isinstance(payload_contract["contractRefs"], list) or not payload_contract["contractRefs"]:
            raise ValueError(
                f"DeliveryManifestV1 channel[{index}].payloadContract.contractRefs must be a non-empty list"
            )
        policy = channel["policyBoundary"]
        _require_fields(
            f"DeliveryManifestV1 channel[{index}] policyBoundary",
            policy,
            REQUIRED_POLICY_FLAGS,
        )
        for flag in REQUIRED_POLICY_FLAGS:
            if policy[flag] is not False:
                raise ValueError(
                    f"DeliveryManifestV1 channel[{index}].policyBoundary.{flag} must be false"
                )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("DeliveryManifestV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("DeliveryManifestV1 sourceArtifacts entries must be objects")
        _require_fields(
            "DeliveryManifestV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"DeliveryManifestV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"DeliveryManifestV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"DeliveryManifestV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"DeliveryManifestV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"DeliveryManifestV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"DeliveryManifestV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_delivery_manifest(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "DeliveryManifestV1",
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
            "deliveryChannelSchemaVersion",
            "requiredVerdictForUnlock",
            "requiredTerminalRunState",
            "verdictDomain",
            "channelKindDomain",
            "channelStatusDomain",
            "taskSpecBinding",
            "capabilityManifestBinding",
            "verifierResultBinding",
            "runEventLogBinding",
            "verdictGate",
            "runTerminalStateGate",
            "approvalGate",
            "channels",
            "channelCount",
            "anyChannelUnlocked",
            "verifierExpectations",
            "policyBoundary",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 schemaVersion must be {DELIVERY_MANIFEST_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"DeliveryManifestV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"DeliveryManifestV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"DeliveryManifestV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"DeliveryManifestV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"DeliveryManifestV1 workloadType must be {WORKLOAD_TYPE}; "
            f"regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"DeliveryManifestV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(
            f"DeliveryManifestV1 creatorAgent must be {CREATOR_AGENT}"
        )
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"DeliveryManifestV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; "
            f"creator must not own the verdict"
        )
    if manifest["deliveryChannelSchemaVersion"] != DELIVERY_CHANNEL_SCHEMA_VERSION:
        raise ValueError(
            f"DeliveryManifestV1 deliveryChannelSchemaVersion must be {DELIVERY_CHANNEL_SCHEMA_VERSION}"
        )
    if manifest["requiredVerdictForUnlock"] != REQUIRED_VERDICT_FOR_UNLOCK:
        raise ValueError(
            f"DeliveryManifestV1 requiredVerdictForUnlock must be {REQUIRED_VERDICT_FOR_UNLOCK}"
        )
    if manifest["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"DeliveryManifestV1 requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"DeliveryManifestV1 verdictDomain must equal {VERDICT_DOMAIN}"
        )
    if manifest["channelKindDomain"] != list(CHANNEL_KIND_DOMAIN):
        raise ValueError(
            f"DeliveryManifestV1 channelKindDomain must equal {CHANNEL_KIND_DOMAIN}"
        )
    if manifest["channelStatusDomain"] != list(CHANNEL_STATUS_DOMAIN):
        raise ValueError(
            f"DeliveryManifestV1 channelStatusDomain must equal {CHANNEL_STATUS_DOMAIN}"
        )

    _validate_task_spec_binding(manifest["taskSpecBinding"], root)
    _validate_capability_manifest_binding(manifest["capabilityManifestBinding"], root)
    _validate_verifier_result_binding(manifest["verifierResultBinding"], root)
    _validate_run_event_log_binding(manifest["runEventLogBinding"], root)

    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)

    verdict_gate = manifest["verdictGate"]
    _require_fields(
        "DeliveryManifestV1 verdictGate",
        verdict_gate,
        ["requiredVerdict", "currentVerdict", "verdictOwner", "unlocked"],
    )
    if verdict_gate["requiredVerdict"] != REQUIRED_VERDICT_FOR_UNLOCK:
        raise ValueError(
            f"DeliveryManifestV1 verdictGate.requiredVerdict must equal {REQUIRED_VERDICT_FOR_UNLOCK}"
        )
    if verdict_gate["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "DeliveryManifestV1 verdictGate.currentVerdict must equal VerifierResultV1.verdict"
        )
    if verdict_gate["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"DeliveryManifestV1 verdictGate.verdictOwner must equal {VERIFIER_VERDICT_OWNER}"
        )
    expected_verdict_unlocked = verdict_gate["currentVerdict"] == REQUIRED_VERDICT_FOR_UNLOCK
    if verdict_gate["unlocked"] is not expected_verdict_unlocked:
        raise ValueError(
            "DeliveryManifestV1 verdictGate.unlocked must be true only when currentVerdict equals "
            f"{REQUIRED_VERDICT_FOR_UNLOCK}"
        )

    run_gate = manifest["runTerminalStateGate"]
    _require_fields(
        "DeliveryManifestV1 runTerminalStateGate",
        run_gate,
        ["requiredTerminalState", "currentTerminalState", "unlocked"],
    )
    if run_gate["requiredTerminalState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"DeliveryManifestV1 runTerminalStateGate.requiredTerminalState must equal {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if run_gate["currentTerminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "DeliveryManifestV1 runTerminalStateGate.currentTerminalState must equal RunEventLogV1.terminalState"
        )
    expected_run_unlocked = run_gate["currentTerminalState"] == REQUIRED_TERMINAL_RUN_STATE
    if run_gate["unlocked"] is not expected_run_unlocked:
        raise ValueError(
            "DeliveryManifestV1 runTerminalStateGate.unlocked must be true only when currentTerminalState equals "
            f"{REQUIRED_TERMINAL_RUN_STATE}"
        )

    approval_gate = manifest["approvalGate"]
    _require_fields(
        "DeliveryManifestV1 approvalGate",
        approval_gate,
        [
            "approvalRecordRef",
            "approvalRecordSchemaVersion",
            "requiredDecision",
            "currentDecision",
            "granted",
            "unlocked",
        ],
    )
    if approval_gate["approvalRecordRef"] != HUMAN_APPROVAL_DECISION_ARTIFACT_PATH:
        raise ValueError(
            f"DeliveryManifestV1 approvalGate.approvalRecordRef must equal {HUMAN_APPROVAL_DECISION_ARTIFACT_PATH}"
        )
    if approval_gate["approvalRecordSchemaVersion"] != "human-approval-decision-v1":
        raise ValueError(
            "DeliveryManifestV1 approvalGate.approvalRecordSchemaVersion must be human-approval-decision-v1"
        )
    if approval_gate["requiredDecision"] != "approved":
        raise ValueError(
            "DeliveryManifestV1 approvalGate.requiredDecision must be approved"
        )
    decision_block = approval_decision.get("decision", {})
    expected_decision = decision_block.get("decision")
    expected_granted = decision_block.get("approvalGranted") is True
    if approval_gate["currentDecision"] != expected_decision:
        raise ValueError(
            "DeliveryManifestV1 approvalGate.currentDecision must equal HumanApprovalDecisionV1.decision.decision"
        )
    if approval_gate["granted"] is not expected_granted:
        raise ValueError(
            "DeliveryManifestV1 approvalGate.granted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )
    if approval_gate["unlocked"] is not approval_gate["granted"]:
        raise ValueError(
            "DeliveryManifestV1 approvalGate.unlocked must equal approvalGate.granted"
        )

    _validate_channels(
        manifest["channels"],
        verdict_gate["unlocked"],
        run_gate["unlocked"],
        approval_gate["unlocked"],
    )
    if manifest["channelCount"] != len(manifest["channels"]):
        raise ValueError(
            "DeliveryManifestV1 channelCount must equal len(channels)"
        )
    if manifest["anyChannelUnlocked"] is not any(
        channel.get("unlocked") for channel in manifest["channels"]
    ):
        raise ValueError(
            "DeliveryManifestV1 anyChannelUnlocked must reflect channels[*].unlocked"
        )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "DeliveryManifestV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"DeliveryManifestV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"DeliveryManifestV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"DeliveryManifestV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    policy = manifest["policyBoundary"]
    _require_fields(
        "DeliveryManifestV1 policyBoundary", policy, REQUIRED_POLICY_FLAGS
    )
    for flag in REQUIRED_POLICY_FLAGS:
        if policy[flag] is not False:
            raise ValueError(
                f"DeliveryManifestV1 policyBoundary.{flag} must be false"
            )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "DeliveryManifestV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionEmailDraft",
            "reusesPhase9DeliveryReport",
            "reusesRegressionResultArtifact",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionEmailDraft"] is not False:
        raise ValueError(
            "DeliveryManifestV1 must not reuse the regression email_draft.md artifact"
        )
    if isolation["reusesPhase9DeliveryReport"] is not False:
        raise ValueError(
            "DeliveryManifestV1 must not reuse phase9_delivery_report.json"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "DeliveryManifestV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError(
            "DeliveryManifestV1 must not reuse the send_email capability"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"DeliveryManifestV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"DeliveryManifestV1 must not embed regression/email field {term} "
                f"outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"DeliveryManifestV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            "DeliveryManifestV1 coordinationBinding must include "
            f"{sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"DeliveryManifestV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 6:
        raise ValueError(
            "DeliveryManifestV1 invariants must declare at least six workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="delivery-manifest")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_delivery_manifest(root)
        _write_json(args.out, manifest)
        print(f"Wrote DeliveryManifestV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_delivery_manifest(manifest, root)
        print(f"Validated DeliveryManifestV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

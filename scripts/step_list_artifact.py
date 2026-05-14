"""StepListV1 / StepV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``StepListV1`` ArtifactV1
subtype that captures the canonical OS-kernel ``Step`` primitive for any
engineering workload.  Each step is a workload-independent
``StepV1`` envelope (``step-v1``) describing a single discrete unit of
work that the run executed.  StepListV1 sits between RunEventLogV1
(``run-event-log-v1``) and the higher-level RunV1 envelope
(``run-artifact-v1``):

- RunEventLogV1 records every append-only event the run produced.
- ObservationListV1 mirrors each event into a workload-independent
  observation.
- StepListV1 groups one or more events into a single step (capability
  invocation pair, artifact write pair, single verifier event, single
  run lifecycle event) and binds each step to the events,
  observations, and evidence it produced.

The artifact answers four OS-kernel invariants at once:

- ``Step`` primitive: each step declares ``stepId`` / ``stepKind`` /
  ``status`` / ``capabilityRef`` / ``sourceAgent`` / ``startedAt`` /
  ``completedAt`` / ``inputContract`` / ``outputContract`` /
  ``runEventLogRefs`` / ``observationRefs`` / ``evidenceRefs`` using
  only workload-independent vocabulary.
- ``Artifact`` envelope reuse: the manifest is an ArtifactV1 subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) joining the existing
  eleven subtypes (``test-execution-result-v1``,
  ``failure-triage-report-v1``, ``verifier-result-v1``,
  ``capability-manifest-v1``, ``run-event-log-v1``,
  ``delivery-manifest-v1``, ``policy-manifest-v1``,
  ``evidence-list-artifact-v1``, ``observation-list-artifact-v1``,
  ``run-artifact-v1``).
- ``Verifier`` / ``Policy`` consistency: ``promotionConditions`` ties
  step promotion to ``VerifierResultV1.verdict=passed`` /
  ``RunEventLogV1.terminalState=completed`` /
  ``PolicyManifestV1.unlockConditions.unlocked=true`` and declares
  ``verifier-runtime-v1`` as verdict owner with
  ``creatorMustNotOwnVerdict=true``.
- ``Coordination`` boundary: all five Agent Coordination Layer
  contracts are pinned by ref + content hash, so coordination drift
  invalidates the step list.

Invariants beyond the run / observation envelopes:

- ``stepCount`` must equal ``len(stepItems)`` and equal the number of
  derived steps from ``RunEventLogV1.events`` (8 steps for the 12
  committed events: 2 lifecycle, 3 capability-invocation pairs,
  1 artifact-write pair, 1 verifier step, 1 run-completion step).
- Every step's ``runEventLogRefs`` must resolve into
  ``RunEventLogV1.events`` by ``eventId``; every step's
  ``observationRefs`` must resolve into
  ``ObservationListV1.observationItems``; every step's
  ``evidenceRefs`` must resolve into ``EvidenceListV1.evidenceItems``.
- ``runEventCoverage.everyEventCovered`` must be true:
  ``StepListV1`` is the canonical materialization of
  ``RunEventLogV1.events`` grouped by step.
- ``observationCoverage.everyObservationCovered`` must be true.
- ``evidenceCoverage.everyEvidenceItemCovered`` must be true.
- Sum of distinct ``runEventLogRefs`` across steps must equal
  ``RunEventLogV1.eventCount``; same for observations and evidence
  items.
- ``startedAt`` must equal the timestamp of the first event the step
  refers to; ``completedAt`` must equal the timestamp of the last.
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


STEP_LIST_ARTIFACT_SCHEMA_VERSION = "step-list-artifact-v1"
STEP_ITEM_SCHEMA_VERSION = "step-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "StepListV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-step-list-kernel-contract"
STEP_LIST_ARTIFACT_PATH = "artifacts/steps/post_mvp_test_execution_step_list.json"

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_step_list_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

REQUIRED_VERDICT_FOR_PROMOTION = "passed"
REQUIRED_TERMINAL_RUN_STATE = "completed"
REQUIRED_POLICY_UNLOCKED = True

STEP_KIND_DOMAIN = [
    "run_state_transition_step",
    "planning_lifecycle_step",
    "capability_invocation_step",
    "artifact_write_step",
    "verifier_step",
]
STEP_STATUS_DOMAIN = ["started", "completed", "failed"]
SOURCE_AGENT_DOMAIN = ["run_kernel", "creator_agent", "verifier-runtime-v1"]
RUN_KERNEL_CAPABILITY = "__run_kernel__"

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

# Deterministic StepListV1 blueprint: 8 steps cover all 12 events.
# stepKind / capabilityRef / sourceAgent / inputContract / outputContract /
# eventSequences / requiredEvidenceIds derive entirely from event payloads.
STEP_BLUEPRINT: list[dict[str, Any]] = [
    {
        "stepKind": "run_state_transition_step",
        "sourceAgent": "run_kernel",
        "capabilityRef": RUN_KERNEL_CAPABILITY,
        "eventSequences": [0],
        "evidenceIds": [],
    },
    {
        "stepKind": "planning_lifecycle_step",
        "sourceAgent": "run_kernel",
        "capabilityRef": RUN_KERNEL_CAPABILITY,
        "eventSequences": [1],
        "evidenceIds": [],
    },
    {
        "stepKind": "capability_invocation_step",
        "sourceAgent": "creator_agent",
        "capabilityRef": "read_test_execution_result",
        "eventSequences": [2, 3],
        "evidenceIds": [],
    },
    {
        "stepKind": "capability_invocation_step",
        "sourceAgent": "creator_agent",
        "capabilityRef": "collect_test_failure_evidence",
        "eventSequences": [4, 5],
        "evidenceIds": [
            "ev-case-001-outcome",
            "ev-case-002-outcome",
            "ev-case-002-trace",
            "ev-case-003-outcome",
        ],
    },
    {
        "stepKind": "capability_invocation_step",
        "sourceAgent": "creator_agent",
        "capabilityRef": "classify_test_failure",
        "eventSequences": [6, 7],
        "evidenceIds": [],
    },
    {
        "stepKind": "artifact_write_step",
        "sourceAgent": "creator_agent",
        "capabilityRef": "write_artifact",
        "eventSequences": [8, 9],
        "evidenceIds": [],
    },
    {
        "stepKind": "verifier_step",
        "sourceAgent": "verifier-runtime-v1",
        "capabilityRef": RUN_KERNEL_CAPABILITY,
        "eventSequences": [10],
        "evidenceIds": [],
    },
    {
        "stepKind": "run_state_transition_step",
        "sourceAgent": "run_kernel",
        "capabilityRef": RUN_KERNEL_CAPABILITY,
        "eventSequences": [11],
        "evidenceIds": [],
    },
]

EXPECTED_STEP_COUNT = len(STEP_BLUEPRINT)

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
    "human_approval_decision": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

REQUIRED_VERIFIER_FLAGS = [
    "mustValidateSchema",
    "mustValidateStepSchema",
    "mustValidateStepKindDomain",
    "mustValidateRunEventLogBinding",
    "mustValidateObservationListBinding",
    "mustValidateEvidenceListBinding",
    "mustValidateVerifierResultBinding",
    "mustValidateRunBinding",
    "mustValidateRunEventCoverage",
    "mustValidateObservationCoverage",
    "mustValidateEvidenceCoverage",
    "mustValidatePermissionFlags",
    "mustValidatePromotionConditions",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "StepListV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype and from the first-workload regression run.json step array.",
    "StepListV1 must bind RunV1, TestExecutionTaskSpecV1, CapabilityManifestV1, RunEventLogV1, ObservationListV1, EvidenceListV1, VerifierResultV1, DeliveryManifestV1, PolicyManifestV1, HumanApprovalDecisionV1, and all five coordination contracts by content hash.",
    "Every StepV1.runEventLogRefs entry must resolve to an existing RunEventLogV1.events.eventId; every StepV1.observationRefs entry must resolve into ObservationListV1.observationItems; every StepV1.evidenceRefs entry must resolve into EvidenceListV1.evidenceItems.",
    "StepListV1 must cover every event, observation and evidence item exactly once across all steps: runEventCoverage.everyEventCovered, observationCoverage.everyObservationCovered and evidenceCoverage.everyEvidenceItemCovered must all be true.",
    "StepV1.startedAt must equal the timestamp of the first event it references; StepV1.completedAt must equal the timestamp of the last event it references.",
    "StepListV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and creator agents may only stage drafts.",
    "StepListV1 promotionConditions require verdict=passed, terminal run state=completed and PolicyManifestV1 unlock=true.",
    "StepListV1 must not reuse regression-task-spec-v1, regression-result-artifact-v1, regression run.json, regression events.jsonl or any regression_result / email_draft / send_email field.",
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
            f"StepListV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"StepListV1 source artifact does not exist: {relative_path}"
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
                f"StepListV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _step_status_for(events: list[dict[str, Any]]) -> str:
    statuses = {event["status"] for event in events}
    if "failed" in statuses:
        return "failed"
    return "completed"


def _step_input_output_contracts(events: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    input_contract: str | None = None
    output_contract: str | None = None
    for event in events:
        payload = event.get("payload", {})
        if "inputSchema" in payload and input_contract is None:
            input_contract = payload["inputSchema"]
        if "outputSchema" in payload:
            output_contract = payload["outputSchema"]
    return input_contract, output_contract


def _build_step_items(
    run_event_log: dict[str, Any],
    observation_list: dict[str, Any],
) -> list[dict[str, Any]]:
    events_by_sequence = {event["sequence"]: event for event in run_event_log["events"]}
    observations_by_event_id = {
        item["runEventLogRef"]["runEventId"]: item for item in observation_list["observationItems"]
    }
    steps: list[dict[str, Any]] = []
    for index, blueprint in enumerate(STEP_BLUEPRINT):
        events = [events_by_sequence[seq] for seq in blueprint["eventSequences"]]
        run_event_log_refs = [event["eventId"] for event in events]
        observation_refs = [
            observations_by_event_id[event_id]["observationId"]
            for event_id in run_event_log_refs
        ]
        started_at = events[0]["timestampMs"]
        completed_at = events[-1]["timestampMs"]
        input_contract, output_contract = _step_input_output_contracts(events)
        step_id = f"step-{RUN_IDENTIFIER}-{index:04d}"
        steps.append(
            {
                "schemaVersion": STEP_ITEM_SCHEMA_VERSION,
                "stepId": step_id,
                "sequence": index,
                "stepKind": blueprint["stepKind"],
                "status": _step_status_for(events),
                "capabilityRef": blueprint["capabilityRef"],
                "sourceAgent": blueprint["sourceAgent"],
                "startedAt": started_at,
                "completedAt": completed_at,
                "inputContract": input_contract,
                "outputContract": output_contract,
                "runEventLogRefs": run_event_log_refs,
                "observationRefs": observation_refs,
                "evidenceRefs": list(blueprint["evidenceIds"]),
            }
        )
    return steps


def _build_run_event_coverage(
    step_items: list[dict[str, Any]], run_event_log: dict[str, Any]
) -> dict[str, Any]:
    all_event_ids = [event["eventId"] for event in run_event_log["events"]]
    covered_event_ids: list[str] = []
    for step in step_items:
        covered_event_ids.extend(step["runEventLogRefs"])
    missing = [event_id for event_id in all_event_ids if event_id not in covered_event_ids]
    extra = [event_id for event_id in covered_event_ids if event_id not in all_event_ids]
    duplicates = [
        event_id
        for event_id in covered_event_ids
        if covered_event_ids.count(event_id) > 1
    ]
    return {
        "eventCount": run_event_log["eventCount"],
        "coveredEventCount": len(covered_event_ids),
        "distinctCoveredEventCount": len(set(covered_event_ids)),
        "everyEventCovered": not missing and not extra and not duplicates,
        "missingEvents": missing,
        "duplicateEvents": sorted(set(duplicates)),
    }


def _build_observation_coverage(
    step_items: list[dict[str, Any]], observation_list: dict[str, Any]
) -> dict[str, Any]:
    all_obs_ids = [item["observationId"] for item in observation_list["observationItems"]]
    covered_obs_ids: list[str] = []
    for step in step_items:
        covered_obs_ids.extend(step["observationRefs"])
    missing = [obs_id for obs_id in all_obs_ids if obs_id not in covered_obs_ids]
    extra = [obs_id for obs_id in covered_obs_ids if obs_id not in all_obs_ids]
    duplicates = [
        obs_id
        for obs_id in covered_obs_ids
        if covered_obs_ids.count(obs_id) > 1
    ]
    return {
        "observationItemCount": observation_list["observationItemCount"],
        "coveredObservationCount": len(covered_obs_ids),
        "distinctCoveredObservationCount": len(set(covered_obs_ids)),
        "everyObservationCovered": not missing and not extra and not duplicates,
        "missingObservations": missing,
        "duplicateObservations": sorted(set(duplicates)),
    }


def _build_evidence_coverage(
    step_items: list[dict[str, Any]], evidence_list: dict[str, Any]
) -> dict[str, Any]:
    all_evidence_ids = [item["evidenceId"] for item in evidence_list["evidenceItems"]]
    covered_evidence_ids: list[str] = []
    for step in step_items:
        covered_evidence_ids.extend(step["evidenceRefs"])
    missing = [
        evidence_id for evidence_id in all_evidence_ids if evidence_id not in covered_evidence_ids
    ]
    extra = [
        evidence_id for evidence_id in covered_evidence_ids if evidence_id not in all_evidence_ids
    ]
    duplicates = [
        evidence_id
        for evidence_id in covered_evidence_ids
        if covered_evidence_ids.count(evidence_id) > 1
    ]
    return {
        "evidenceItemCount": evidence_list["evidenceItemCount"],
        "coveredEvidenceCount": len(covered_evidence_ids),
        "distinctCoveredEvidenceCount": len(set(covered_evidence_ids)),
        "everyEvidenceItemCovered": not missing and not extra and not duplicates,
        "missingEvidence": missing,
        "duplicateEvidence": sorted(set(duplicates)),
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
        "eventCount": run_artifact["eventCount"],
        "observationCount": run_artifact["observationCount"],
        "evidenceCount": run_artifact["evidenceCount"],
    }


def _validate_referenced_artifacts(root: Path) -> tuple[
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
    return (
        run_event_log,
        observation_list,
        evidence_list,
        verifier_result,
        policy_manifest,
        run_artifact,
    )


def build_step_list_artifact(root: Path) -> dict[str, Any]:
    (
        run_event_log,
        observation_list,
        evidence_list,
        verifier_result,
        policy_manifest,
        run_artifact,
    ) = _validate_referenced_artifacts(root)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)

    step_items = _build_step_items(run_event_log, observation_list)

    payload: dict[str, Any] = {
        "schemaVersion": STEP_LIST_ARTIFACT_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "stepItemSchemaVersion": STEP_ITEM_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "runIdentifier": RUN_IDENTIFIER,
        "stepCount": len(step_items),
        "stepKindDomain": list(STEP_KIND_DOMAIN),
        "stepStatusDomain": list(STEP_STATUS_DOMAIN),
        "sourceAgentDomain": list(SOURCE_AGENT_DOMAIN),
        "runKernelCapabilitySentinel": RUN_KERNEL_CAPABILITY,
        "verdictDomain": list(VERDICT_DOMAIN),
        "permissionFlagDomain": list(PERMISSION_FLAG_DOMAIN),
        "permissionFlags": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
        "stepItems": step_items,
        "runEventCoverage": _build_run_event_coverage(step_items, run_event_log),
        "observationCoverage": _build_observation_coverage(step_items, observation_list),
        "evidenceCoverage": _build_evidence_coverage(step_items, evidence_list),
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
            "mustValidateStepSchema": True,
            "mustValidateStepKindDomain": True,
            "mustValidateRunEventLogBinding": True,
            "mustValidateObservationListBinding": True,
            "mustValidateEvidenceListBinding": True,
            "mustValidateVerifierResultBinding": True,
            "mustValidateRunBinding": True,
            "mustValidateRunEventCoverage": True,
            "mustValidateObservationCoverage": True,
            "mustValidateEvidenceCoverage": True,
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
    validate_step_list_artifact(payload, root)
    return payload


def _validate_step_items(
    step_items: Any,
    run_event_log: dict[str, Any],
    observation_list: dict[str, Any],
    evidence_list: dict[str, Any],
) -> None:
    if not isinstance(step_items, list) or len(step_items) != EXPECTED_STEP_COUNT:
        raise ValueError(
            f"StepListV1 stepItems must be a list of length {EXPECTED_STEP_COUNT}"
        )
    events_by_id = {event["eventId"]: event for event in run_event_log["events"]}
    observations_by_id = {item["observationId"]: item for item in observation_list["observationItems"]}
    evidence_by_id = {item["evidenceId"]: item for item in evidence_list["evidenceItems"]}
    step_id_seen: set[str] = set()
    for index, step in enumerate(step_items):
        if not isinstance(step, dict):
            raise ValueError("StepListV1 stepItems entries must be objects")
        _require_fields(
            f"StepListV1 stepItems[{index}]",
            step,
            [
                "schemaVersion",
                "stepId",
                "sequence",
                "stepKind",
                "status",
                "capabilityRef",
                "sourceAgent",
                "startedAt",
                "completedAt",
                "inputContract",
                "outputContract",
                "runEventLogRefs",
                "observationRefs",
                "evidenceRefs",
            ],
        )
        if step["schemaVersion"] != STEP_ITEM_SCHEMA_VERSION:
            raise ValueError(
                f"StepListV1 stepItems[{index}].schemaVersion must be {STEP_ITEM_SCHEMA_VERSION}"
            )
        if step["stepKind"] not in STEP_KIND_DOMAIN:
            raise ValueError(
                f"StepListV1 stepItems[{index}].stepKind must be one of {STEP_KIND_DOMAIN}"
            )
        if step["status"] not in STEP_STATUS_DOMAIN:
            raise ValueError(
                f"StepListV1 stepItems[{index}].status must be one of {STEP_STATUS_DOMAIN}"
            )
        if step["sourceAgent"] not in SOURCE_AGENT_DOMAIN:
            raise ValueError(
                f"StepListV1 stepItems[{index}].sourceAgent must be one of {SOURCE_AGENT_DOMAIN}"
            )
        if step["sequence"] != index:
            raise ValueError(
                f"StepListV1 stepItems[{index}].sequence must equal its position {index}"
            )
        expected_step_id = f"step-{RUN_IDENTIFIER}-{index:04d}"
        if step["stepId"] != expected_step_id:
            raise ValueError(
                f"StepListV1 stepItems[{index}].stepId must equal {expected_step_id}"
            )
        if step["stepId"] in step_id_seen:
            raise ValueError(
                f"StepListV1 stepItems contains duplicate stepId: {step['stepId']}"
            )
        step_id_seen.add(step["stepId"])
        blueprint = STEP_BLUEPRINT[index]
        if step["stepKind"] != blueprint["stepKind"]:
            raise ValueError(
                f"StepListV1 stepItems[{index}].stepKind must equal blueprint stepKind {blueprint['stepKind']}"
            )
        if step["capabilityRef"] != blueprint["capabilityRef"]:
            raise ValueError(
                f"StepListV1 stepItems[{index}].capabilityRef must equal {blueprint['capabilityRef']}"
            )
        if step["sourceAgent"] != blueprint["sourceAgent"]:
            raise ValueError(
                f"StepListV1 stepItems[{index}].sourceAgent must equal {blueprint['sourceAgent']}"
            )
        if not isinstance(step["runEventLogRefs"], list) or not step["runEventLogRefs"]:
            raise ValueError(
                f"StepListV1 stepItems[{index}].runEventLogRefs must be a non-empty list"
            )
        expected_event_ids = [
            events_by_id_event["eventId"]
            for events_by_id_event in [
                run_event_log["events"][seq] for seq in blueprint["eventSequences"]
            ]
        ]
        if step["runEventLogRefs"] != expected_event_ids:
            raise ValueError(
                f"StepListV1 stepItems[{index}].runEventLogRefs must equal {expected_event_ids}"
            )
        for event_id in step["runEventLogRefs"]:
            if event_id not in events_by_id:
                raise ValueError(
                    f"StepListV1 stepItems[{index}] references unknown RunEventLogV1.events eventId: {event_id}"
                )
        if not isinstance(step["observationRefs"], list) or len(step["observationRefs"]) != len(step["runEventLogRefs"]):
            raise ValueError(
                f"StepListV1 stepItems[{index}].observationRefs must mirror runEventLogRefs length"
            )
        for event_id, obs_id in zip(step["runEventLogRefs"], step["observationRefs"]):
            obs = observations_by_id.get(obs_id)
            if obs is None:
                raise ValueError(
                    f"StepListV1 stepItems[{index}] references unknown ObservationListV1.observationId: {obs_id}"
                )
            if obs["runEventLogRef"]["runEventId"] != event_id:
                raise ValueError(
                    f"StepListV1 stepItems[{index}] observation {obs_id} must reference runEventLog event {event_id}"
                )
        if not isinstance(step["evidenceRefs"], list):
            raise ValueError(
                f"StepListV1 stepItems[{index}].evidenceRefs must be a list"
            )
        if sorted(step["evidenceRefs"]) != sorted(blueprint["evidenceIds"]):
            raise ValueError(
                f"StepListV1 stepItems[{index}].evidenceRefs must equal blueprint evidenceIds {sorted(blueprint['evidenceIds'])}"
            )
        for evidence_id in step["evidenceRefs"]:
            if evidence_id not in evidence_by_id:
                raise ValueError(
                    f"StepListV1 stepItems[{index}] references unknown EvidenceListV1.evidenceId: {evidence_id}"
                )
        first_event = run_event_log["events"][blueprint["eventSequences"][0]]
        last_event = run_event_log["events"][blueprint["eventSequences"][-1]]
        if step["startedAt"] != first_event["timestampMs"]:
            raise ValueError(
                f"StepListV1 stepItems[{index}].startedAt must equal first event timestampMs"
            )
        if step["completedAt"] != last_event["timestampMs"]:
            raise ValueError(
                f"StepListV1 stepItems[{index}].completedAt must equal last event timestampMs"
            )
        if step["startedAt"] > step["completedAt"]:
            raise ValueError(
                f"StepListV1 stepItems[{index}].startedAt must not be greater than completedAt"
            )
        expected_input, expected_output = _step_input_output_contracts(
            [run_event_log["events"][seq] for seq in blueprint["eventSequences"]]
        )
        if step["inputContract"] != expected_input:
            raise ValueError(
                f"StepListV1 stepItems[{index}].inputContract must equal {expected_input}"
            )
        if step["outputContract"] != expected_output:
            raise ValueError(
                f"StepListV1 stepItems[{index}].outputContract must equal {expected_output}"
            )
        expected_status = _step_status_for(
            [run_event_log["events"][seq] for seq in blueprint["eventSequences"]]
        )
        if step["status"] != expected_status:
            raise ValueError(
                f"StepListV1 stepItems[{index}].status must equal {expected_status}"
            )


def _validate_coverage(
    coverage: dict[str, Any],
    label: str,
    expected_total: int,
    every_flag: str,
    missing_field: str,
    duplicate_field: str,
    count_field: str,
    distinct_field: str,
) -> None:
    _require_fields(
        f"StepListV1 {label}",
        coverage,
        [count_field, "coveredEventCount", "distinctCoveredEventCount", every_flag, missing_field, duplicate_field]
        if label == "runEventCoverage"
        else [count_field, "coveredObservationCount", "distinctCoveredObservationCount", every_flag, missing_field, duplicate_field]
        if label == "observationCoverage"
        else [count_field, "coveredEvidenceCount", "distinctCoveredEvidenceCount", every_flag, missing_field, duplicate_field],
    )
    if coverage[count_field] != expected_total:
        raise ValueError(
            f"StepListV1 {label}.{count_field} must equal {expected_total}"
        )
    if coverage[every_flag] is not True:
        raise ValueError(
            f"StepListV1 {label}.{every_flag} must be true"
        )
    if coverage[missing_field]:
        raise ValueError(
            f"StepListV1 {label}.{missing_field} must be empty"
        )
    if coverage[duplicate_field]:
        raise ValueError(
            f"StepListV1 {label}.{duplicate_field} must be empty"
        )
    if coverage[distinct_field] != expected_total:
        raise ValueError(
            f"StepListV1 {label}.{distinct_field} must equal {expected_total}"
        )


def _validate_promotion_conditions(
    promotion: dict[str, Any],
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    policy_manifest: dict[str, Any],
) -> None:
    _require_fields(
        "StepListV1 promotionConditions",
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
            f"StepListV1 promotionConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_PROMOTION}"
        )
    if promotion["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "StepListV1 promotionConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if promotion["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"StepListV1 promotionConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if promotion["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"StepListV1 promotionConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if promotion["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "StepListV1 promotionConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if promotion["requiredPolicyUnlocked"] is not REQUIRED_POLICY_UNLOCKED:
        raise ValueError(
            "StepListV1 promotionConditions.requiredPolicyUnlocked must be true"
        )
    if promotion["currentPolicyUnlocked"] is not expected_unlocked:
        raise ValueError(
            "StepListV1 promotionConditions.currentPolicyUnlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )
    expected_promoted = (
        promotion["currentVerdict"] == REQUIRED_VERDICT_FOR_PROMOTION
        and promotion["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and promotion["currentPolicyUnlocked"] is True
    )
    if promotion["promoted"] is not expected_promoted:
        raise ValueError(
            "StepListV1 promotionConditions.promoted must be true only when verdict, run terminal state and policy unlock all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("StepListV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("StepListV1 sourceArtifacts entries must be objects")
        _require_fields(
            "StepListV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"StepListV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"StepListV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"StepListV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"StepListV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"StepListV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"StepListV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def _validate_run_binding(binding: dict[str, Any], root: Path, run_artifact: dict[str, Any]) -> None:
    _require_fields(
        "StepListV1 runBinding",
        binding,
        [
            "runRef",
            "runSchemaVersion",
            "runEnvelopeSchemaVersion",
            "runId",
            "runContentHash",
            "runIdentifier",
            "runState",
            "eventCount",
            "observationCount",
            "evidenceCount",
        ],
    )
    if binding["runRef"] != RUN_ARTIFACT_PATH:
        raise ValueError(f"StepListV1 runBinding.runRef must equal {RUN_ARTIFACT_PATH}")
    if binding["runSchemaVersion"] != RUN_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 runBinding.runSchemaVersion must equal {RUN_ARTIFACT_SCHEMA_VERSION}; regression run.json reuse is forbidden"
        )
    if binding["runEnvelopeSchemaVersion"] != RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 runBinding.runEnvelopeSchemaVersion must equal {RUN_ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runId"] != RUN_ARTIFACT_ID:
        raise ValueError(f"StepListV1 runBinding.runId must equal {RUN_ARTIFACT_ID}")
    full_path = root / binding["runRef"]
    if binding["runContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 runBinding.runContentHash must match the on-disk RunV1 artifact"
        )
    if binding["runIdentifier"] != run_artifact["runId"]:
        raise ValueError(
            "StepListV1 runBinding.runIdentifier must equal RunV1.runId"
        )
    if binding["runState"] != run_artifact["runState"]:
        raise ValueError(
            "StepListV1 runBinding.runState must equal RunV1.runState"
        )
    if binding["eventCount"] != run_artifact["eventCount"]:
        raise ValueError(
            "StepListV1 runBinding.eventCount must equal RunV1.eventCount"
        )
    if binding["observationCount"] != run_artifact["observationCount"]:
        raise ValueError(
            "StepListV1 runBinding.observationCount must equal RunV1.observationCount"
        )
    if binding["evidenceCount"] != run_artifact["evidenceCount"]:
        raise ValueError(
            "StepListV1 runBinding.evidenceCount must equal RunV1.evidenceCount"
        )


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "StepListV1 taskSpecBinding",
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
            f"StepListV1 taskSpecBinding.taskSpecRef must equal {TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 taskSpecBinding.taskSpecSchemaVersion must equal {TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; "
            "regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal {TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"StepListV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if binding["taskSpecContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "StepListV1 capabilityManifestBinding",
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
            f"StepListV1 capabilityManifestBinding.capabilityManifestRef must equal {CAPABILITY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal {CAPABILITY_MANIFEST_SCHEMA_VERSION}; "
            "regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal {CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"StepListV1 capabilityManifestBinding.capabilityManifestId must equal {CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["capabilityManifestRef"]
    if binding["capabilityManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 capabilityManifestBinding.capabilityManifestContentHash must match the on-disk capability manifest"
        )


def _validate_run_event_log_binding(
    binding: dict[str, Any], root: Path, run_event_log: dict[str, Any]
) -> None:
    _require_fields(
        "StepListV1 runEventLogBinding",
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
            f"StepListV1 runEventLogBinding.runEventLogRef must equal {RUN_EVENT_LOG_ARTIFACT_PATH}"
        )
    if binding["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 runEventLogBinding.runEventLogSchemaVersion must equal {RUN_EVENT_LOG_SCHEMA_VERSION}; "
            "regression events.jsonl reuse is forbidden"
        )
    if binding["runEventLogEnvelopeSchemaVersion"] != RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 runEventLogBinding.runEventLogEnvelopeSchemaVersion must equal {RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runEventLogId"] != RUN_EVENT_LOG_ARTIFACT_ID:
        raise ValueError(
            f"StepListV1 runEventLogBinding.runEventLogId must equal {RUN_EVENT_LOG_ARTIFACT_ID}"
        )
    full_path = root / binding["runEventLogRef"]
    if binding["runEventLogContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 runEventLogBinding.runEventLogContentHash must match the on-disk run event log"
        )
    if binding["eventCount"] != run_event_log["eventCount"]:
        raise ValueError(
            "StepListV1 runEventLogBinding.eventCount must equal RunEventLogV1.eventCount"
        )
    if binding["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "StepListV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )


def _validate_observation_list_binding(
    binding: dict[str, Any], root: Path, observation_list: dict[str, Any]
) -> None:
    _require_fields(
        "StepListV1 observationListBinding",
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
            f"StepListV1 observationListBinding.observationListRef must equal {OBSERVATION_LIST_ARTIFACT_PATH}"
        )
    if binding["observationListSchemaVersion"] != OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 observationListBinding.observationListSchemaVersion must equal {OBSERVATION_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression observation reuse is forbidden"
        )
    if binding["observationListEnvelopeSchemaVersion"] != OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 observationListBinding.observationListEnvelopeSchemaVersion must equal {OBSERVATION_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["observationListId"] != OBSERVATION_LIST_ARTIFACT_ID:
        raise ValueError(
            f"StepListV1 observationListBinding.observationListId must equal {OBSERVATION_LIST_ARTIFACT_ID}"
        )
    full_path = root / binding["observationListRef"]
    if binding["observationListContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 observationListBinding.observationListContentHash must match the on-disk observation list"
        )
    if binding["observationItemCount"] != observation_list["observationItemCount"]:
        raise ValueError(
            "StepListV1 observationListBinding.observationItemCount must equal ObservationListV1.observationItemCount"
        )


def _validate_evidence_list_binding(
    binding: dict[str, Any], root: Path, evidence_list: dict[str, Any]
) -> None:
    _require_fields(
        "StepListV1 evidenceListBinding",
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
            f"StepListV1 evidenceListBinding.evidenceListRef must equal {EVIDENCE_LIST_ARTIFACT_PATH}"
        )
    if binding["evidenceListSchemaVersion"] != EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 evidenceListBinding.evidenceListSchemaVersion must equal {EVIDENCE_LIST_ARTIFACT_SCHEMA_VERSION}; "
            "regression evidence-list-v1 reuse is forbidden"
        )
    if binding["evidenceListEnvelopeSchemaVersion"] != EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 evidenceListBinding.evidenceListEnvelopeSchemaVersion must equal {EVIDENCE_LIST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["evidenceListId"] != EVIDENCE_LIST_ARTIFACT_ID:
        raise ValueError(
            f"StepListV1 evidenceListBinding.evidenceListId must equal {EVIDENCE_LIST_ARTIFACT_ID}"
        )
    full_path = root / binding["evidenceListRef"]
    if binding["evidenceListContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 evidenceListBinding.evidenceListContentHash must match the on-disk evidence list artifact"
        )
    if binding["evidenceItemCount"] != evidence_list["evidenceItemCount"]:
        raise ValueError(
            "StepListV1 evidenceListBinding.evidenceItemCount must equal EvidenceListV1.evidenceItemCount"
        )


def _validate_verifier_result_binding(
    binding: dict[str, Any], root: Path, verifier_result: dict[str, Any]
) -> None:
    _require_fields(
        "StepListV1 verifierResultBinding",
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
            f"StepListV1 verifierResultBinding.verifierResultRef must equal {VERIFIER_RESULT_ARTIFACT_PATH}"
        )
    if binding["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 verifierResultBinding.verifierResultSchemaVersion must equal {VERIFIER_RESULT_SCHEMA_VERSION}; "
            "regression result artifact reuse is forbidden"
        )
    if binding["verifierResultEnvelopeSchemaVersion"] != VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 verifierResultBinding.verifierResultEnvelopeSchemaVersion must equal {VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["verifierResultId"] != VERIFIER_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"StepListV1 verifierResultBinding.verifierResultId must equal {VERIFIER_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["verifierResultRef"]
    if binding["verifierResultContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 verifierResultBinding.verifierResultContentHash must match the on-disk verifier result"
        )
    if binding["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"StepListV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}; got {binding['verdict']}"
        )
    if binding["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "StepListV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )


def _validate_delivery_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "StepListV1 deliveryManifestBinding",
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
            f"StepListV1 deliveryManifestBinding.deliveryManifestRef must equal {DELIVERY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["deliveryManifestSchemaVersion"] != DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 deliveryManifestBinding.deliveryManifestSchemaVersion must equal {DELIVERY_MANIFEST_SCHEMA_VERSION}; "
            "multi-agent-delivery-manifest reuse is forbidden"
        )
    if binding["deliveryManifestEnvelopeSchemaVersion"] != DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 deliveryManifestBinding.deliveryManifestEnvelopeSchemaVersion must equal {DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["deliveryManifestId"] != DELIVERY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"StepListV1 deliveryManifestBinding.deliveryManifestId must equal {DELIVERY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["deliveryManifestRef"]
    if binding["deliveryManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 deliveryManifestBinding.deliveryManifestContentHash must match the on-disk delivery manifest"
        )


def _validate_policy_manifest_binding(
    binding: dict[str, Any], root: Path, policy_manifest: dict[str, Any]
) -> None:
    _require_fields(
        "StepListV1 policyManifestBinding",
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
            f"StepListV1 policyManifestBinding.policyManifestRef must equal {POLICY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["policyManifestSchemaVersion"] != POLICY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 policyManifestBinding.policyManifestSchemaVersion must equal {POLICY_MANIFEST_SCHEMA_VERSION}; "
            "regression / adapter policy reuse is forbidden"
        )
    if binding["policyManifestEnvelopeSchemaVersion"] != POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 policyManifestBinding.policyManifestEnvelopeSchemaVersion must equal {POLICY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["policyManifestId"] != POLICY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"StepListV1 policyManifestBinding.policyManifestId must equal {POLICY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["policyManifestRef"]
    if binding["policyManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 policyManifestBinding.policyManifestContentHash must match the on-disk policy manifest"
        )
    expected_unlocked = bool(policy_manifest.get("unlockConditions", {}).get("unlocked", False))
    if binding["unlocked"] is not expected_unlocked:
        raise ValueError(
            "StepListV1 policyManifestBinding.unlocked must equal PolicyManifestV1.unlockConditions.unlocked"
        )


def _validate_approval_decision_binding(
    binding: dict[str, Any], root: Path, approval_decision: dict[str, Any]
) -> None:
    _require_fields(
        "StepListV1 approvalDecisionBinding",
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
            f"StepListV1 approvalDecisionBinding.approvalDecisionRef must equal {HUMAN_APPROVAL_DECISION_ARTIFACT_PATH}"
        )
    if binding["approvalDecisionSchemaVersion"] != HUMAN_APPROVAL_DECISION_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 approvalDecisionBinding.approvalDecisionSchemaVersion must equal {HUMAN_APPROVAL_DECISION_SCHEMA_VERSION}"
        )
    if binding["approvalDecisionId"] != approval_decision["id"]:
        raise ValueError(
            "StepListV1 approvalDecisionBinding.approvalDecisionId must equal HumanApprovalDecisionV1.id"
        )
    full_path = root / binding["approvalDecisionRef"]
    if binding["approvalDecisionContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "StepListV1 approvalDecisionBinding.approvalDecisionContentHash must match the on-disk approval decision"
        )
    expected_granted = bool(approval_decision.get("decision", {}).get("approvalGranted", False))
    if binding["approvalGranted"] is not expected_granted:
        raise ValueError(
            "StepListV1 approvalDecisionBinding.approvalGranted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )


def validate_step_list_artifact(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "StepListV1",
        manifest,
        [
            "schemaVersion",
            "artifactEnvelopeSchemaVersion",
            "stepItemSchemaVersion",
            "id",
            "generatedAt",
            "kind",
            "scope",
            "workloadType",
            "workloadCategory",
            "creatorAgent",
            "verifierVerdictOwner",
            "runIdentifier",
            "stepCount",
            "stepKindDomain",
            "stepStatusDomain",
            "sourceAgentDomain",
            "runKernelCapabilitySentinel",
            "verdictDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "stepItems",
            "runEventCoverage",
            "observationCoverage",
            "evidenceCoverage",
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
    if manifest["schemaVersion"] != STEP_LIST_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 schemaVersion must be {STEP_LIST_ARTIFACT_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["stepItemSchemaVersion"] != STEP_ITEM_SCHEMA_VERSION:
        raise ValueError(
            f"StepListV1 stepItemSchemaVersion must be {STEP_ITEM_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"StepListV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"StepListV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"StepListV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"StepListV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"StepListV1 workloadType must be {WORKLOAD_TYPE}; regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"StepListV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"StepListV1 creatorAgent must be {CREATOR_AGENT}")
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"StepListV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; creator must not own the verdict"
        )
    if manifest["runIdentifier"] != RUN_IDENTIFIER:
        raise ValueError(
            f"StepListV1 runIdentifier must equal {RUN_IDENTIFIER}; reuse of regression run identifiers is forbidden"
        )
    if manifest["stepCount"] != EXPECTED_STEP_COUNT:
        raise ValueError(
            f"StepListV1 stepCount must equal {EXPECTED_STEP_COUNT}"
        )

    if manifest["stepKindDomain"] != list(STEP_KIND_DOMAIN):
        raise ValueError(
            f"StepListV1 stepKindDomain must equal {STEP_KIND_DOMAIN}"
        )
    if manifest["stepStatusDomain"] != list(STEP_STATUS_DOMAIN):
        raise ValueError(
            f"StepListV1 stepStatusDomain must equal {STEP_STATUS_DOMAIN}"
        )
    if manifest["sourceAgentDomain"] != list(SOURCE_AGENT_DOMAIN):
        raise ValueError(
            f"StepListV1 sourceAgentDomain must equal {SOURCE_AGENT_DOMAIN}"
        )
    if manifest["runKernelCapabilitySentinel"] != RUN_KERNEL_CAPABILITY:
        raise ValueError(
            f"StepListV1 runKernelCapabilitySentinel must equal {RUN_KERNEL_CAPABILITY}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(f"StepListV1 verdictDomain must equal {VERDICT_DOMAIN}")
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"StepListV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )
    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"StepListV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(
                f"StepListV1 permissionFlags.{flag} must be false"
            )

    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    observation_list = _load_json(root / OBSERVATION_LIST_ARTIFACT_PATH)
    evidence_list = _load_json(root / EVIDENCE_LIST_ARTIFACT_PATH)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    policy_manifest = _load_json(root / POLICY_MANIFEST_ARTIFACT_PATH)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    run_artifact = _load_json(root / RUN_ARTIFACT_PATH)

    _validate_step_items(manifest["stepItems"], run_event_log, observation_list, evidence_list)
    if manifest["stepCount"] != len(manifest["stepItems"]):
        raise ValueError("StepListV1 stepCount must equal len(stepItems)")

    _validate_coverage(
        manifest["runEventCoverage"],
        "runEventCoverage",
        run_event_log["eventCount"],
        "everyEventCovered",
        "missingEvents",
        "duplicateEvents",
        "eventCount",
        "distinctCoveredEventCount",
    )
    _validate_coverage(
        manifest["observationCoverage"],
        "observationCoverage",
        observation_list["observationItemCount"],
        "everyObservationCovered",
        "missingObservations",
        "duplicateObservations",
        "observationItemCount",
        "distinctCoveredObservationCount",
    )
    _validate_coverage(
        manifest["evidenceCoverage"],
        "evidenceCoverage",
        evidence_list["evidenceItemCount"],
        "everyEvidenceItemCovered",
        "missingEvidence",
        "duplicateEvidence",
        "evidenceItemCount",
        "distinctCoveredEvidenceCount",
    )

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
        "StepListV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"StepListV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"StepListV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"StepListV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "StepListV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionRunArtifact",
            "reusesRegressionResultArtifact",
            "reusesRegressionEventsArtifact",
            "reusesRegressionRunStepArray",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionRunArtifact"] is not False:
        raise ValueError(
            "StepListV1 must not reuse the first-workload regression run.json artifact"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "StepListV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesRegressionEventsArtifact"] is not False:
        raise ValueError(
            "StepListV1 must not reuse the first-workload regression events.jsonl artifact"
        )
    if isolation["reusesRegressionRunStepArray"] is not False:
        raise ValueError(
            "StepListV1 must not reuse the first-workload regression run.json steps array"
        )
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError(
            "StepListV1 must not reuse the send_email capability"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"StepListV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"StepListV1 must not embed regression/email field {term} outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"StepListV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            f"StepListV1 coordinationBinding must include {sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"StepListV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 7:
        raise ValueError(
            "StepListV1 invariants must declare at least seven workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="step-list-artifact")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_step_list_artifact(root)
        _write_json(args.out, manifest)
        print(f"Wrote StepListV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_step_list_artifact(manifest, root)
        print(f"Validated StepListV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

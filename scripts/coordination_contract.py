from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from capability_contract import PHASE3_CAPABILITY_NAMES, validate_capability_catalog
from verifier_runtime import validate_verifier_rule_catalog


DELEGATION_MANIFEST_SCHEMA_VERSION = "delegation-manifest-v1"
DELEGATION_SCHEMA_VERSION = "delegation-v1"
COORDINATION_EVENT_SCHEMA_VERSION = "coordination-event-v1"
CREATOR_VERIFIER_PAIRING_SCHEMA_VERSION = "creator-verifier-pairing-v1"
AGENT_MESSAGE_MANIFEST_SCHEMA_VERSION = "agent-message-manifest-v1"
AGENT_MESSAGE_SCHEMA_VERSION = "agent-message-v1"
NEGOTIATION_RECORD_SCHEMA_VERSION = "negotiation-record-v1"
NEGOTIATION_PROPOSAL_SCHEMA_VERSION = "negotiation-proposal-v1"
NEGOTIATION_AGREEMENT_SCHEMA_VERSION = "negotiation-agreement-v1"
BROADCAST_SUBSCRIPTION_MANIFEST_SCHEMA_VERSION = "broadcast-subscription-manifest-v1"
BROADCAST_TOPIC_SCHEMA_VERSION = "broadcast-topic-v1"
BROADCAST_SUBSCRIPTION_SCHEMA_VERSION = "broadcast-subscription-v1"
BROADCAST_FAN_OUT_SCHEMA_VERSION = "broadcast-fan-out-v1"
TASK_SPEC_ENVELOPE_SCHEMA_VERSION = "task-spec-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"

DELEGATION_MANIFEST_ID = "post-mvp-delegation-manifest-kernel-contract"
DELEGATION_MANIFEST_ARTIFACT_PATH = "artifacts/coordination/post_mvp_delegation_manifest.json"
CREATOR_VERIFIER_PAIRING_ID = "post-mvp-creator-verifier-pairing-kernel-contract"
CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH = "artifacts/coordination/post_mvp_creator_verifier_pairing.json"
AGENT_MESSAGE_MANIFEST_ID = "post-mvp-agent-message-manifest-kernel-contract"
AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH = "artifacts/coordination/post_mvp_agent_message_manifest.json"
NEGOTIATION_RECORD_ID = "post-mvp-negotiation-record-kernel-contract"
NEGOTIATION_RECORD_ARTIFACT_PATH = "artifacts/coordination/post_mvp_negotiation_record.json"
NEGOTIATION_PROPOSAL_ROOT_ID = "negotiation-proposal-acceptance-criteria-clarification"
NEGOTIATION_PROPOSAL_COUNTER_ID = "negotiation-proposal-acceptance-criteria-counter"
NEGOTIATION_PROPOSAL_AGREEMENT_ID = "negotiation-proposal-acceptance-criteria-agreement"
NEGOTIATION_AGREEMENT_ID = "negotiation-agreement-acceptance-criteria-source-bound"
BROADCAST_SUBSCRIPTION_MANIFEST_ID = "post-mvp-broadcast-subscription-kernel-contract"
BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH = "artifacts/coordination/post_mvp_broadcast_subscription_manifest.json"

BROADCAST_TOPIC_DELEGATION_LIFECYCLE = "coordination.delegation_lifecycle"
BROADCAST_TOPIC_NEGOTIATION_LIFECYCLE = "coordination.negotiation_lifecycle"
BROADCAST_TOPIC_IDS = [
    BROADCAST_TOPIC_DELEGATION_LIFECYCLE,
    BROADCAST_TOPIC_NEGOTIATION_LIFECYCLE,
]
BROADCAST_DELEGATION_LIFECYCLE_EVENT_TYPES = [
    "delegation.created",
    "delegation.accepted",
    "verification.requested",
]
BROADCAST_NEGOTIATION_LIFECYCLE_EVENT_TYPES = [
    "negotiation.proposal",
    "negotiation.counter_proposal",
    "negotiation.agreement",
]
BROADCAST_NEGOTIATION_PROPOSAL_TYPE_TO_EVENT = {
    "proposal": "negotiation.proposal",
    "counter_proposal": "negotiation.counter_proposal",
    "agreement": "negotiation.agreement",
}
BROADCAST_OBSERVER_AGENT_ID = "auditor_agent"
BROADCAST_SUBSCRIBER_ROLES = ["planner", "verifier", "auditor"]
BROADCAST_SUBSCRIBER_AGENT_IDS = ["planner_agent", "verifier_agent", BROADCAST_OBSERVER_AGENT_ID]

NEGOTIATION_TOPICS = ["scope", "risk", "policy", "acceptance_criteria"]
NEGOTIATION_PROPOSAL_TYPES = ["proposal", "counter_proposal", "agreement", "withdrawal"]
NEGOTIATION_PROPOSAL_SEQUENCE_TYPES = ["proposal", "counter_proposal", "agreement"]

AGENT_MESSAGE_CHANNEL_REQUEST_ID = "creator-to-verifier-verification-request-channel"
AGENT_MESSAGE_CHANNEL_RESPONSE_ID = "verifier-to-creator-verification-response-channel"
AGENT_MESSAGE_REQUEST_ID = "agent-message-verification-request"
AGENT_MESSAGE_RESPONSE_ID = "agent-message-verification-response"
AGENT_MESSAGE_TYPE_SEQUENCE = ["verification.request", "verification.response"]
AGENT_MESSAGE_PAYLOAD_KINDS = {"ArtifactV1", "EvidenceListV1", "VerifierResultV1"}

DEFAULT_RUN_PATH = "artifacts/runs/all_passed/run.json"
DEFAULT_CAPABILITY_CATALOG_PATH = "artifacts/capabilities/phase3_capability_catalog.json"
DEFAULT_VERIFIER_RULE_CATALOG_PATH = "artifacts/verifier/phase5_verifier_rule_catalog.json"

AGENT_ROLES = ["planner_agent", "creator_agent", "verifier_agent"]
COORDINATION_EVENT_SEQUENCE = [
    "delegation.created",
    "delegation.accepted",
    "verification.requested",
]
NON_REGRESSION_REUSE_PATHS = [
    "test_execution_failure_triage",
    "code_patch_review_loop",
    "pr_review",
]
WORKLOAD_INDEPENDENT_ARTIFACT_TYPES = {
    "EvidenceListV1",
    "ArtifactV1",
    "VerifierResultV1",
}


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _stable_text_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


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
    if Path(path).is_absolute() or "\\" in path or path.startswith("../") or "/../" in path:
        raise ValueError(f"DelegationManifestV1 paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"DelegationManifestV1 source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _expected_source_paths() -> dict[str, str]:
    return {
        "task_run": DEFAULT_RUN_PATH,
        "capability_catalog": DEFAULT_CAPABILITY_CATALOG_PATH,
        "verifier_rule_catalog": DEFAULT_VERIFIER_RULE_CATALOG_PATH,
    }


def _artifact_ref(relative_path: str, fragment: str | None = None) -> str:
    _validate_relative_posix_path(relative_path)
    if fragment:
        return f"{relative_path}{fragment}"
    return relative_path


def _artifact_paths_by_kind(delegation: dict[str, Any]) -> dict[str, str]:
    artifacts = delegation["expectedArtifacts"]
    paths_by_kind: dict[str, str] = {}
    for artifact in artifacts:
        kind = artifact["artifactKind"]
        artifact_ref = artifact["artifactRef"]
        if "#" in artifact_ref:
            artifact_ref = artifact_ref.split("#", 1)[0]
        paths_by_kind[kind] = artifact_ref
    return paths_by_kind


def _build_task_spec_envelope(run: dict[str, Any]) -> dict[str, Any]:
    task_spec = run["taskSpec"]
    goal_hash = _stable_text_hash(task_spec["goal"])
    return {
        "schemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecRef": _artifact_ref(DEFAULT_RUN_PATH, "#taskSpec"),
        "sourceTaskSpecId": task_spec["id"],
        "sourceTaskSpecSchemaVersion": task_spec["schemaVersion"],
        "workloadType": "read_only_regression_evidence_demo",
        "kernelPrimitive": "TaskSpecV1",
        "goalHash": goal_hash,
        "allowedCapabilityClasses": [
            "observation_reader",
            "structured_result_extractor",
            "local_artifact_writer",
        ],
        "forbiddenEffectClasses": [
            "external_side_effect",
            "workspace_mutation",
            "provider_execution",
            "delivery_send",
        ],
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATHS),
    }


def _build_agent_bindings() -> list[dict[str, Any]]:
    return [
        {
            "agentId": "planner_agent",
            "role": "planner",
            "owns": ["delegation_scope", "acceptance_criteria", "policy_boundary"],
            "mayCreateArtifacts": False,
            "mayVerifyArtifacts": False,
        },
        {
            "agentId": "creator_agent",
            "role": "creator",
            "owns": ["artifact_creation", "evidence_backlink_collection"],
            "mayCreateArtifacts": True,
            "mayVerifyArtifacts": False,
        },
        {
            "agentId": "verifier_agent",
            "role": "verifier",
            "owns": ["independent_verifier_result", "policy_invariant_check"],
            "mayCreateArtifacts": False,
            "mayVerifyArtifacts": True,
        },
    ]


def _build_delegation(run: dict[str, Any]) -> dict[str, Any]:
    run_id = run["id"]
    return {
        "schemaVersion": DELEGATION_SCHEMA_VERSION,
        "id": "delegation-workload-independent-artifact-creation",
        "parentTaskSpecRef": _artifact_ref(DEFAULT_RUN_PATH, "#taskSpec"),
        "parentRunRef": DEFAULT_RUN_PATH,
        "fromAgent": "planner_agent",
        "toAgent": "creator_agent",
        "creatorAgent": "creator_agent",
        "verifierAgent": "verifier_agent",
        "workloadIndependentObjective": "Create source-bound engineering artifacts from a reviewed TaskSpec without owning the task verdict.",
        "runId": run_id,
        "requiredEvidence": [
            "source_bound_observation",
            "artifact_backlink",
            "verifier_result",
        ],
        "acceptanceCriteria": [
            "Every produced ArtifactV1 must reference source-bound Evidence.",
            "Creator output cannot be accepted until an independent VerifierResultV1 is recorded.",
            "Delegated work must stay inside the declared PolicyV1 side-effect boundary.",
        ],
        "expectedArtifacts": [
            {
                "artifactKind": "EvidenceListV1",
                "artifactRef": "artifacts/runs/all_passed/evidence.json",
                "purpose": "source_bound_evidence",
            },
            {
                "artifactKind": "ArtifactV1",
                "artifactRef": "artifacts/runs/all_passed/regression_result.json",
                "purpose": "structured_workload_result_instance",
            },
            {
                "artifactKind": "VerifierResultV1",
                "artifactRef": "artifacts/runs/all_passed/verifier_report.json",
                "purpose": "independent_acceptance_verdict",
            },
        ],
        "policyBoundary": {
            "policySchemaVersion": "policy-v1",
            "externalSideEffectsAllowed": False,
            "workspaceMutationAllowed": False,
            "deliverySendAllowed": False,
            "creatorMaySelfVerify": False,
            "requiresIndependentVerifier": True,
        },
    }


def _build_coordination_events() -> list[dict[str, Any]]:
    delegation_ref = f"{DELEGATION_MANIFEST_ARTIFACT_PATH}#delegations/delegation-workload-independent-artifact-creation"
    return [
        {
            "schemaVersion": COORDINATION_EVENT_SCHEMA_VERSION,
            "id": "coord-event-delegation-created",
            "type": "delegation.created",
            "fromAgent": "planner_agent",
            "toAgent": "creator_agent",
            "delegationRef": delegation_ref,
            "causalRefs": [_artifact_ref(DEFAULT_RUN_PATH, "#taskSpec")],
            "message": "Planner created a source-bound artifact creation delegation with explicit verifier binding.",
        },
        {
            "schemaVersion": COORDINATION_EVENT_SCHEMA_VERSION,
            "id": "coord-event-delegation-accepted",
            "type": "delegation.accepted",
            "fromAgent": "creator_agent",
            "toAgent": "planner_agent",
            "delegationRef": delegation_ref,
            "causalRefs": ["coord-event-delegation-created"],
            "message": "Creator accepted artifact production without verifier ownership.",
        },
        {
            "schemaVersion": COORDINATION_EVENT_SCHEMA_VERSION,
            "id": "coord-event-verification-requested",
            "type": "verification.requested",
            "fromAgent": "creator_agent",
            "toAgent": "verifier_agent",
            "delegationRef": delegation_ref,
            "causalRefs": ["coord-event-delegation-accepted"],
            "message": "Creator requested independent verifier review before acceptance.",
        },
    ]


def build_delegation_manifest(root: Path) -> dict[str, Any]:
    run = _load_json(root / DEFAULT_RUN_PATH)
    capability_catalog = _load_json(root / DEFAULT_CAPABILITY_CATALOG_PATH)
    validate_capability_catalog(capability_catalog, PHASE3_CAPABILITY_NAMES)
    verifier_rule_catalog = _load_json(root / DEFAULT_VERIFIER_RULE_CATALOG_PATH)
    validate_verifier_rule_catalog(verifier_rule_catalog)

    return {
        "schemaVersion": DELEGATION_MANIFEST_SCHEMA_VERSION,
        "id": DELEGATION_MANIFEST_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "agent_coordination_delegation_contract",
        "mode": "static_contract_only",
        "sourceArtifacts": [
            _artifact_source(role, path, root)
            for role, path in _expected_source_paths().items()
        ],
        "kernelPrimitive": "Delegation",
        "coordinationProtocols": ["delegation", "creator_verifier"],
        "taskSpecEnvelope": _build_task_spec_envelope(run),
        "agentBindings": _build_agent_bindings(),
        "delegations": [_build_delegation(run)],
        "coordinationEvents": _build_coordination_events(),
        "creatorVerifierInvariant": {
            "creatorAgent": "creator_agent",
            "verifierAgent": "verifier_agent",
            "independentVerifierRequired": True,
            "creatorCannotSelfVerify": True,
            "verifierResultOwner": "verifier-runtime-v1",
            "weakSelfVerificationAllowed": False,
        },
        "policyBoundary": {
            "policySchemaVersion": "policy-v1",
            "externalSideEffectsAllowed": False,
            "workspaceMutationAllowed": False,
            "deliverySendAllowed": False,
            "realMultiAgentRuntimeAllowed": False,
            "providerExecutionAllowed": False,
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATHS),
        "invariants": [
            "DelegationManifestV1 is workload-independent: it binds TaskSpecV1, ArtifactV1, Evidence, VerifierResultV1, and PolicyV1 without adding regression/email behavior.",
            "Creator and verifier agents must be distinct; creator output cannot self-certify acceptance.",
            "CoordinationEventV1 entries must preserve causal refs from delegation creation to verification request.",
            "The manifest is a static contract artifact and does not run a real multi-agent framework, send email, mutate a workspace, or execute providers.",
        ],
    }


def _build_pairing_source_artifacts(delegation_manifest: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    return [
        _artifact_source("delegation_manifest", DELEGATION_MANIFEST_ARTIFACT_PATH, root),
        _artifact_source("creator_output_artifact", paths_by_kind["ArtifactV1"], root),
        _artifact_source("acceptance_evidence", paths_by_kind["EvidenceListV1"], root),
        _artifact_source("verifier_result", paths_by_kind["VerifierResultV1"], root),
    ]


def _delegation_ref(delegation_id: str) -> str:
    return f"{DELEGATION_MANIFEST_ARTIFACT_PATH}#delegations/{delegation_id}"


def build_creator_verifier_pairing(root: Path) -> dict[str, Any]:
    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])

    return {
        "schemaVersion": CREATOR_VERIFIER_PAIRING_SCHEMA_VERSION,
        "id": CREATOR_VERIFIER_PAIRING_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "agent_coordination_creator_verifier_pairing_contract",
        "mode": "static_contract_only",
        "kernelPrimitive": "CreatorVerifierPairing",
        "coordinationProtocols": ["creator_verifier"],
        "sourceArtifacts": _build_pairing_source_artifacts(delegation_manifest, root),
        "delegationBinding": {
            "delegationManifestRef": DELEGATION_MANIFEST_ARTIFACT_PATH,
            "delegationRef": delegation_ref,
            "parentTaskSpecRef": delegation["parentTaskSpecRef"],
            "parentRunRef": delegation["parentRunRef"],
            "workloadIndependentObjective": delegation["workloadIndependentObjective"],
        },
        "creator": {
            "agentId": delegation["creatorAgent"],
            "role": "creator",
            "assignedDelegationRef": delegation_ref,
            "mayCreateArtifacts": True,
            "mayVerifyArtifacts": False,
            "mayDeclareAcceptance": False,
            "owns": ["artifact_creation", "evidence_backlink_collection"],
        },
        "verifier": {
            "agentId": delegation["verifierAgent"],
            "role": "verifier",
            "assignedDelegationRef": delegation_ref,
            "mayCreateArtifacts": False,
            "mayVerifyArtifacts": True,
            "verifierResultOwner": "verifier-runtime-v1",
            "independentFromCreator": True,
            "owns": ["independent_verifier_result", "policy_invariant_check"],
        },
        "creatorOutput": {
            "artifactKind": "ArtifactV1",
            "artifactRef": paths_by_kind["ArtifactV1"],
            "producedBy": delegation["creatorAgent"],
            "acceptanceVerdictOwner": "verifier-runtime-v1",
            "creatorOutputCanSelfCertify": False,
        },
        "acceptanceEvidence": [
            {
                "artifactKind": "EvidenceListV1",
                "artifactRef": paths_by_kind["EvidenceListV1"],
                "requiredForAcceptance": True,
            },
            {
                "artifactKind": "VerifierResultV1",
                "artifactRef": paths_by_kind["VerifierResultV1"],
                "requiredForAcceptance": True,
            },
        ],
        "verifierResultBinding": {
            "artifactKind": "VerifierResultV1",
            "verifierResultRef": paths_by_kind["VerifierResultV1"],
            "verifierAgent": delegation["verifierAgent"],
            "verifierResultOwner": "verifier-runtime-v1",
            "acceptedOnlyIfVerifierPassed": True,
            "creatorOverrideAllowed": False,
        },
        "independencePolicy": {
            "policySchemaVersion": "policy-v1",
            "verifierMustBeDistinct": True,
            "creatorMaySelfVerify": False,
            "weakSelfVerificationAllowed": False,
            "creatorMayOverrideVerifier": False,
            "externalSideEffectsAllowed": False,
            "workspaceMutationAllowed": False,
            "deliverySendAllowed": False,
            "realMultiAgentRuntimeAllowed": False,
            "providerExecutionAllowed": False,
        },
        "coordinationEventRefs": [
            f"{DELEGATION_MANIFEST_ARTIFACT_PATH}#coordinationEvents/{event['id']}"
            for event in delegation_manifest["coordinationEvents"]
        ],
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATHS),
        "invariants": [
            "CreatorVerifierPairingV1 is workload-independent: it binds creator output, acceptance evidence, and VerifierResultV1 without adding regression/email behavior.",
            "Creator and verifier agents must be distinct; creator output cannot self-certify acceptance.",
            "VerifierResultV1 remains the acceptance source of truth and is owned by verifier-runtime-v1.",
            "The pairing is a static contract artifact and does not run a real multi-agent framework, send email, mutate a workspace, or execute providers.",
        ],
    }


def _validate_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("DelegationManifestV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("DelegationManifestV1 sourceArtifacts must be objects")
        _require_fields("DelegationManifestV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected DelegationManifestV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"DelegationManifestV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"DelegationManifestV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"DelegationManifestV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"DelegationManifestV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def _validate_task_spec_envelope(envelope: dict[str, Any], run: dict[str, Any]) -> None:
    _require_fields(
        "DelegationManifestV1 taskSpecEnvelope",
        envelope,
        [
            "schemaVersion",
            "taskSpecRef",
            "sourceTaskSpecId",
            "sourceTaskSpecSchemaVersion",
            "workloadType",
            "kernelPrimitive",
            "goalHash",
            "allowedCapabilityClasses",
            "forbiddenEffectClasses",
            "nonRegressionReusePath",
        ],
    )
    task_spec = run["taskSpec"]
    if envelope["schemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(f"DelegationManifestV1 taskSpecEnvelope schemaVersion must be {TASK_SPEC_ENVELOPE_SCHEMA_VERSION}")
    if envelope["taskSpecRef"] != _artifact_ref(DEFAULT_RUN_PATH, "#taskSpec"):
        raise ValueError("DelegationManifestV1 taskSpecEnvelope must bind run.json#taskSpec")
    if envelope["sourceTaskSpecId"] != task_spec["id"]:
        raise ValueError("DelegationManifestV1 taskSpecEnvelope sourceTaskSpecId must match source TaskSpec")
    if envelope["sourceTaskSpecSchemaVersion"] != task_spec["schemaVersion"]:
        raise ValueError("DelegationManifestV1 taskSpecEnvelope source schemaVersion must match source TaskSpec")
    if envelope["kernelPrimitive"] != "TaskSpecV1":
        raise ValueError("DelegationManifestV1 taskSpecEnvelope kernelPrimitive must be TaskSpecV1")
    if envelope["goalHash"] != _stable_text_hash(task_spec["goal"]):
        raise ValueError("DelegationManifestV1 taskSpecEnvelope goalHash mismatch")
    if "external_side_effect" not in envelope["forbiddenEffectClasses"]:
        raise ValueError("DelegationManifestV1 taskSpecEnvelope must forbid external_side_effect")
    if not set(NON_REGRESSION_REUSE_PATHS).issubset(set(envelope["nonRegressionReusePath"])):
        raise ValueError("DelegationManifestV1 taskSpecEnvelope must include non-regression reuse paths")


def _validate_agent_bindings(agent_bindings: list[Any]) -> None:
    if not isinstance(agent_bindings, list) or [agent.get("agentId") for agent in agent_bindings if isinstance(agent, dict)] != AGENT_ROLES:
        raise ValueError(f"DelegationManifestV1 agentBindings must equal {AGENT_ROLES}")
    for agent in agent_bindings:
        if not isinstance(agent, dict):
            raise ValueError("DelegationManifestV1 agentBindings must be objects")
        _require_fields(
            "DelegationManifestV1 agent binding",
            agent,
            ["agentId", "role", "owns", "mayCreateArtifacts", "mayVerifyArtifacts"],
        )
        if agent["role"] == "creator" and agent["mayVerifyArtifacts"] is not False:
            raise ValueError("DelegationManifestV1 creator must not verify artifacts")
        if agent["role"] == "verifier" and agent["mayCreateArtifacts"] is not False:
            raise ValueError("DelegationManifestV1 verifier must not create delegated artifacts")


def _validate_delegation(delegation: dict[str, Any], run: dict[str, Any]) -> None:
    _require_fields(
        "DelegationManifestV1 delegation",
        delegation,
        [
            "schemaVersion",
            "id",
            "parentTaskSpecRef",
            "parentRunRef",
            "fromAgent",
            "toAgent",
            "creatorAgent",
            "verifierAgent",
            "workloadIndependentObjective",
            "runId",
            "requiredEvidence",
            "acceptanceCriteria",
            "expectedArtifacts",
            "policyBoundary",
        ],
    )
    if delegation["schemaVersion"] != DELEGATION_SCHEMA_VERSION:
        raise ValueError(f"DelegationManifestV1 delegation schemaVersion must be {DELEGATION_SCHEMA_VERSION}")
    if delegation["parentTaskSpecRef"] != _artifact_ref(DEFAULT_RUN_PATH, "#taskSpec"):
        raise ValueError("DelegationManifestV1 delegation must bind parent TaskSpec")
    if delegation["parentRunRef"] != DEFAULT_RUN_PATH or delegation["runId"] != run["id"]:
        raise ValueError("DelegationManifestV1 delegation must bind parent run")
    if delegation["fromAgent"] != "planner_agent" or delegation["toAgent"] != "creator_agent":
        raise ValueError("DelegationManifestV1 delegation must flow planner_agent -> creator_agent")
    if delegation["creatorAgent"] == delegation["verifierAgent"]:
        raise ValueError("DelegationManifestV1 creator and verifier agents must be distinct")
    if delegation["verifierAgent"] != "verifier_agent":
        raise ValueError("DelegationManifestV1 delegation must bind verifier_agent")
    required_evidence = delegation["requiredEvidence"]
    if not isinstance(required_evidence, list) or not {"source_bound_observation", "artifact_backlink", "verifier_result"}.issubset(set(required_evidence)):
        raise ValueError("DelegationManifestV1 requiredEvidence must include source_bound_observation, artifact_backlink, and verifier_result")
    if not isinstance(delegation["acceptanceCriteria"], list) or len(delegation["acceptanceCriteria"]) < 3:
        raise ValueError("DelegationManifestV1 delegation must include explicit acceptanceCriteria")
    expected_artifacts = delegation["expectedArtifacts"]
    if not isinstance(expected_artifacts, list) or not expected_artifacts:
        raise ValueError("DelegationManifestV1 expectedArtifacts must be a non-empty list")
    artifact_kinds = set()
    for artifact in expected_artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("DelegationManifestV1 expectedArtifacts must be objects")
        _require_fields("DelegationManifestV1 expected artifact", artifact, ["artifactKind", "artifactRef", "purpose"])
        artifact_kind = artifact["artifactKind"]
        artifact_kinds.add(artifact_kind)
        if artifact_kind not in WORKLOAD_INDEPENDENT_ARTIFACT_TYPES:
            raise ValueError("DelegationManifestV1 expectedArtifacts must remain workload-independent ArtifactV1/Evidence/VerifierResult refs")
        artifact_ref = artifact["artifactRef"]
        _validate_relative_posix_path(artifact_ref)
        if "email" in artifact_ref or artifact_kind == "EmailDraftArtifactV1":
            raise ValueError("DelegationManifestV1 expectedArtifacts must not add regression/email delivery artifacts")
    if artifact_kinds != WORKLOAD_INDEPENDENT_ARTIFACT_TYPES:
        raise ValueError("DelegationManifestV1 expectedArtifacts must cover EvidenceListV1, ArtifactV1, and VerifierResultV1")
    policy = delegation["policyBoundary"]
    _require_fields(
        "DelegationManifestV1 delegation policyBoundary",
        policy,
        [
            "policySchemaVersion",
            "externalSideEffectsAllowed",
            "workspaceMutationAllowed",
            "deliverySendAllowed",
            "creatorMaySelfVerify",
            "requiresIndependentVerifier",
        ],
    )
    if policy["policySchemaVersion"] != "policy-v1":
        raise ValueError("DelegationManifestV1 delegation policyBoundary must use policy-v1")
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("DelegationManifestV1 delegation policyBoundary must disallow external side effects")
    if policy["workspaceMutationAllowed"] is not False or policy["deliverySendAllowed"] is not False:
        raise ValueError("DelegationManifestV1 delegation policyBoundary must disallow workspace mutation and delivery send")
    if policy["creatorMaySelfVerify"] is not False or policy["requiresIndependentVerifier"] is not True:
        raise ValueError("DelegationManifestV1 delegation policyBoundary must require independent verifier")


def _validate_coordination_events(events: list[Any]) -> None:
    if not isinstance(events, list) or [event.get("type") for event in events if isinstance(event, dict)] != COORDINATION_EVENT_SEQUENCE:
        raise ValueError(f"DelegationManifestV1 coordinationEvents must follow {COORDINATION_EVENT_SEQUENCE}")
    event_ids: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError("DelegationManifestV1 coordinationEvents must be objects")
        _require_fields(
            "DelegationManifestV1 coordination event",
            event,
            ["schemaVersion", "id", "type", "fromAgent", "toAgent", "delegationRef", "causalRefs", "message"],
        )
        if event["schemaVersion"] != COORDINATION_EVENT_SCHEMA_VERSION:
            raise ValueError(f"DelegationManifestV1 coordination event schemaVersion must be {COORDINATION_EVENT_SCHEMA_VERSION}")
        if not event["delegationRef"].startswith(f"{DELEGATION_MANIFEST_ARTIFACT_PATH}#delegations/"):
            raise ValueError("DelegationManifestV1 coordination event must reference the delegation")
        causal_refs = event["causalRefs"]
        if not isinstance(causal_refs, list) or not causal_refs:
            raise ValueError("DelegationManifestV1 coordination event causalRefs must be non-empty")
        if index == 0 and _artifact_ref(DEFAULT_RUN_PATH, "#taskSpec") not in causal_refs:
            raise ValueError("DelegationManifestV1 first coordination event must causally reference parent TaskSpec")
        if index > 0 and events[index - 1]["id"] not in causal_refs:
            raise ValueError("DelegationManifestV1 coordination event causal chain must link to the previous event")
        event_ids.add(event["id"])
    if len(event_ids) != len(events):
        raise ValueError("DelegationManifestV1 coordination event ids must be unique")


def validate_delegation_manifest(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "DelegationManifestV1",
        manifest,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "sourceArtifacts",
            "kernelPrimitive",
            "coordinationProtocols",
            "taskSpecEnvelope",
            "agentBindings",
            "delegations",
            "coordinationEvents",
            "creatorVerifierInvariant",
            "policyBoundary",
            "nonRegressionReusePath",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != DELEGATION_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"DelegationManifestV1 schemaVersion must be {DELEGATION_MANIFEST_SCHEMA_VERSION}")
    if manifest["id"] != DELEGATION_MANIFEST_ID:
        raise ValueError(f"DelegationManifestV1 id must be {DELEGATION_MANIFEST_ID}")
    if manifest["phase"] != "post_mvp":
        raise ValueError("DelegationManifestV1 phase must be post_mvp")
    if manifest["scope"] != "agent_coordination_delegation_contract":
        raise ValueError("DelegationManifestV1 scope must be agent_coordination_delegation_contract")
    if manifest["mode"] != "static_contract_only":
        raise ValueError("DelegationManifestV1 mode must be static_contract_only")
    if manifest["kernelPrimitive"] != "Delegation":
        raise ValueError("DelegationManifestV1 kernelPrimitive must be Delegation")
    if not {"delegation", "creator_verifier"}.issubset(set(manifest["coordinationProtocols"])):
        raise ValueError("DelegationManifestV1 coordinationProtocols must include delegation and creator_verifier")

    sources = _validate_source_artifacts(manifest["sourceArtifacts"], root)
    run = _load_json(root / sources["task_run"]["path"])
    validate_capability_catalog(_load_json(root / sources["capability_catalog"]["path"]), PHASE3_CAPABILITY_NAMES)
    validate_verifier_rule_catalog(_load_json(root / sources["verifier_rule_catalog"]["path"]))

    _validate_task_spec_envelope(manifest["taskSpecEnvelope"], run)
    _validate_agent_bindings(manifest["agentBindings"])
    delegations = manifest["delegations"]
    if not isinstance(delegations, list) or len(delegations) != 1:
        raise ValueError("DelegationManifestV1 delegations must contain exactly one minimal delegation")
    _validate_delegation(delegations[0], run)
    _validate_coordination_events(manifest["coordinationEvents"])

    invariant = manifest["creatorVerifierInvariant"]
    _require_fields(
        "DelegationManifestV1 creatorVerifierInvariant",
        invariant,
        [
            "creatorAgent",
            "verifierAgent",
            "independentVerifierRequired",
            "creatorCannotSelfVerify",
            "verifierResultOwner",
            "weakSelfVerificationAllowed",
        ],
    )
    if invariant["creatorAgent"] == invariant["verifierAgent"]:
        raise ValueError("DelegationManifestV1 creator and verifier agents must be distinct")
    if invariant["independentVerifierRequired"] is not True or invariant["creatorCannotSelfVerify"] is not True:
        raise ValueError("DelegationManifestV1 must require independent verifier and forbid creator self-verification")
    if invariant["verifierResultOwner"] != "verifier-runtime-v1":
        raise ValueError("DelegationManifestV1 verifierResultOwner must be verifier-runtime-v1")
    if invariant["weakSelfVerificationAllowed"] is not False:
        raise ValueError("DelegationManifestV1 weak self-verification must not be allowed")

    policy = manifest["policyBoundary"]
    _require_fields(
        "DelegationManifestV1 policyBoundary",
        policy,
        [
            "policySchemaVersion",
            "externalSideEffectsAllowed",
            "workspaceMutationAllowed",
            "deliverySendAllowed",
            "realMultiAgentRuntimeAllowed",
            "providerExecutionAllowed",
        ],
    )
    if policy["policySchemaVersion"] != "policy-v1":
        raise ValueError("DelegationManifestV1 policyBoundary must use policy-v1")
    for field in [
        "externalSideEffectsAllowed",
        "workspaceMutationAllowed",
        "deliverySendAllowed",
        "realMultiAgentRuntimeAllowed",
        "providerExecutionAllowed",
    ]:
        if policy[field] is not False:
            raise ValueError(f"DelegationManifestV1 policyBoundary must keep {field} false")
    if not set(NON_REGRESSION_REUSE_PATHS).issubset(set(manifest["nonRegressionReusePath"])):
        raise ValueError("DelegationManifestV1 must include non-regression workload reuse paths")


def _expected_pairing_source_paths(delegation_manifest: dict[str, Any]) -> dict[str, str]:
    paths_by_kind = _artifact_paths_by_kind(delegation_manifest["delegations"][0])
    return {
        "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
        "creator_output_artifact": paths_by_kind["ArtifactV1"],
        "acceptance_evidence": paths_by_kind["EvidenceListV1"],
        "verifier_result": paths_by_kind["VerifierResultV1"],
    }


def _validate_pairing_source_artifacts(
    source_artifacts: list[Any],
    delegation_manifest: dict[str, Any],
    root: Path,
) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("CreatorVerifierPairingV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_pairing_source_paths(delegation_manifest)
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("CreatorVerifierPairingV1 sourceArtifacts must be objects")
        _require_fields("CreatorVerifierPairingV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected CreatorVerifierPairingV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"CreatorVerifierPairingV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"CreatorVerifierPairingV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"CreatorVerifierPairingV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"CreatorVerifierPairingV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def _reject_regression_email_delivery_ref(label: str, artifact_ref: str) -> None:
    lowered = artifact_ref.lower()
    if "email" in lowered or "send_email" in lowered or "delivery_unlock" in lowered:
        raise ValueError(f"{label} must not add regression/email delivery artifacts")
    _validate_relative_posix_path(artifact_ref)


def validate_creator_verifier_pairing(pairing: dict[str, Any], root: Path) -> None:
    _require_fields(
        "CreatorVerifierPairingV1",
        pairing,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "kernelPrimitive",
            "coordinationProtocols",
            "sourceArtifacts",
            "delegationBinding",
            "creator",
            "verifier",
            "creatorOutput",
            "acceptanceEvidence",
            "verifierResultBinding",
            "independencePolicy",
            "coordinationEventRefs",
            "nonRegressionReusePath",
            "invariants",
        ],
    )
    if pairing["schemaVersion"] != CREATOR_VERIFIER_PAIRING_SCHEMA_VERSION:
        raise ValueError(f"CreatorVerifierPairingV1 schemaVersion must be {CREATOR_VERIFIER_PAIRING_SCHEMA_VERSION}")
    if pairing["id"] != CREATOR_VERIFIER_PAIRING_ID:
        raise ValueError(f"CreatorVerifierPairingV1 id must be {CREATOR_VERIFIER_PAIRING_ID}")
    if pairing["phase"] != "post_mvp":
        raise ValueError("CreatorVerifierPairingV1 phase must be post_mvp")
    if pairing["scope"] != "agent_coordination_creator_verifier_pairing_contract":
        raise ValueError("CreatorVerifierPairingV1 scope must be agent_coordination_creator_verifier_pairing_contract")
    if pairing["mode"] != "static_contract_only":
        raise ValueError("CreatorVerifierPairingV1 mode must be static_contract_only")
    if pairing["kernelPrimitive"] != "CreatorVerifierPairing":
        raise ValueError("CreatorVerifierPairingV1 kernelPrimitive must be CreatorVerifierPairing")
    if "creator_verifier" not in pairing["coordinationProtocols"]:
        raise ValueError("CreatorVerifierPairingV1 coordinationProtocols must include creator_verifier")

    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])
    _validate_pairing_source_artifacts(pairing["sourceArtifacts"], delegation_manifest, root)

    binding = pairing["delegationBinding"]
    _require_fields(
        "CreatorVerifierPairingV1 delegationBinding",
        binding,
        [
            "delegationManifestRef",
            "delegationRef",
            "parentTaskSpecRef",
            "parentRunRef",
            "workloadIndependentObjective",
        ],
    )
    if binding["delegationManifestRef"] != DELEGATION_MANIFEST_ARTIFACT_PATH or binding["delegationRef"] != delegation_ref:
        raise ValueError("CreatorVerifierPairingV1 delegationBinding must reference DelegationManifestV1")
    if binding["parentTaskSpecRef"] != delegation["parentTaskSpecRef"] or binding["parentRunRef"] != delegation["parentRunRef"]:
        raise ValueError("CreatorVerifierPairingV1 delegationBinding must inherit parent TaskSpec and Run refs")

    creator = pairing["creator"]
    verifier = pairing["verifier"]
    _require_fields(
        "CreatorVerifierPairingV1 creator",
        creator,
        ["agentId", "role", "assignedDelegationRef", "mayCreateArtifacts", "mayVerifyArtifacts", "mayDeclareAcceptance", "owns"],
    )
    _require_fields(
        "CreatorVerifierPairingV1 verifier",
        verifier,
        [
            "agentId",
            "role",
            "assignedDelegationRef",
            "mayCreateArtifacts",
            "mayVerifyArtifacts",
            "verifierResultOwner",
            "independentFromCreator",
            "owns",
        ],
    )
    if creator["agentId"] != delegation["creatorAgent"] or verifier["agentId"] != delegation["verifierAgent"]:
        raise ValueError("CreatorVerifierPairingV1 agents must match DelegationManifestV1 creator and verifier")
    if creator["agentId"] == verifier["agentId"]:
        raise ValueError("CreatorVerifierPairingV1 creator and verifier agents must be distinct")
    if creator["mayVerifyArtifacts"] is not False or creator["mayDeclareAcceptance"] is not False:
        raise ValueError("CreatorVerifierPairingV1 creator must not verify artifacts or declare acceptance")
    if verifier["mayCreateArtifacts"] is not False or verifier["mayVerifyArtifacts"] is not True:
        raise ValueError("CreatorVerifierPairingV1 verifier must verify without creating delegated artifacts")
    if verifier["verifierResultOwner"] != "verifier-runtime-v1" or verifier["independentFromCreator"] is not True:
        raise ValueError("CreatorVerifierPairingV1 verifier must be independent and owned by verifier-runtime-v1")

    creator_output = pairing["creatorOutput"]
    _require_fields(
        "CreatorVerifierPairingV1 creatorOutput",
        creator_output,
        ["artifactKind", "artifactRef", "producedBy", "acceptanceVerdictOwner", "creatorOutputCanSelfCertify"],
    )
    if creator_output["artifactKind"] != "ArtifactV1":
        raise ValueError("CreatorVerifierPairingV1 creatorOutput must be workload-independent ArtifactV1")
    _reject_regression_email_delivery_ref("CreatorVerifierPairingV1 creatorOutput", creator_output["artifactRef"])
    if creator_output["artifactRef"] != paths_by_kind["ArtifactV1"]:
        raise ValueError("CreatorVerifierPairingV1 creatorOutput must bind DelegationManifestV1 ArtifactV1")
    if creator_output["producedBy"] != creator["agentId"]:
        raise ValueError("CreatorVerifierPairingV1 creatorOutput producedBy must match creator")
    if creator_output["acceptanceVerdictOwner"] != "verifier-runtime-v1" or creator_output["creatorOutputCanSelfCertify"] is not False:
        raise ValueError("CreatorVerifierPairingV1 creator output cannot self-certify acceptance")

    acceptance_evidence = pairing["acceptanceEvidence"]
    if not isinstance(acceptance_evidence, list):
        raise ValueError("CreatorVerifierPairingV1 acceptanceEvidence must be a list")
    evidence_by_kind = {
        evidence.get("artifactKind"): evidence
        for evidence in acceptance_evidence
        if isinstance(evidence, dict)
    }
    if set(evidence_by_kind) != {"EvidenceListV1", "VerifierResultV1"}:
        raise ValueError("CreatorVerifierPairingV1 acceptanceEvidence must include EvidenceListV1 and VerifierResultV1")
    for kind, expected_ref in [("EvidenceListV1", paths_by_kind["EvidenceListV1"]), ("VerifierResultV1", paths_by_kind["VerifierResultV1"])]:
        evidence = evidence_by_kind[kind]
        _require_fields("CreatorVerifierPairingV1 acceptance evidence", evidence, ["artifactKind", "artifactRef", "requiredForAcceptance"])
        if evidence["artifactRef"] != expected_ref or evidence["requiredForAcceptance"] is not True:
            raise ValueError("CreatorVerifierPairingV1 acceptanceEvidence must bind required delegation artifacts")
        _reject_regression_email_delivery_ref("CreatorVerifierPairingV1 acceptanceEvidence", evidence["artifactRef"])

    verifier_binding = pairing["verifierResultBinding"]
    _require_fields(
        "CreatorVerifierPairingV1 verifierResultBinding",
        verifier_binding,
        [
            "artifactKind",
            "verifierResultRef",
            "verifierAgent",
            "verifierResultOwner",
            "acceptedOnlyIfVerifierPassed",
            "creatorOverrideAllowed",
        ],
    )
    if verifier_binding["artifactKind"] != "VerifierResultV1" or verifier_binding["verifierResultRef"] != paths_by_kind["VerifierResultV1"]:
        raise ValueError("CreatorVerifierPairingV1 verifierResultBinding must bind DelegationManifestV1 VerifierResultV1")
    if verifier_binding["verifierAgent"] != verifier["agentId"] or verifier_binding["verifierResultOwner"] != "verifier-runtime-v1":
        raise ValueError("CreatorVerifierPairingV1 verifierResultBinding must match independent verifier")
    if verifier_binding["acceptedOnlyIfVerifierPassed"] is not True or verifier_binding["creatorOverrideAllowed"] is not False:
        raise ValueError("CreatorVerifierPairingV1 verifier result must gate acceptance and forbid creator override")

    policy = pairing["independencePolicy"]
    _require_fields(
        "CreatorVerifierPairingV1 independencePolicy",
        policy,
        [
            "policySchemaVersion",
            "verifierMustBeDistinct",
            "creatorMaySelfVerify",
            "weakSelfVerificationAllowed",
            "creatorMayOverrideVerifier",
            "externalSideEffectsAllowed",
            "workspaceMutationAllowed",
            "deliverySendAllowed",
            "realMultiAgentRuntimeAllowed",
            "providerExecutionAllowed",
        ],
    )
    if policy["policySchemaVersion"] != "policy-v1":
        raise ValueError("CreatorVerifierPairingV1 independencePolicy must use policy-v1")
    if policy["verifierMustBeDistinct"] is not True:
        raise ValueError("CreatorVerifierPairingV1 independencePolicy must require a distinct verifier")
    for field in [
        "creatorMaySelfVerify",
        "weakSelfVerificationAllowed",
        "creatorMayOverrideVerifier",
        "externalSideEffectsAllowed",
        "workspaceMutationAllowed",
        "deliverySendAllowed",
        "realMultiAgentRuntimeAllowed",
        "providerExecutionAllowed",
    ]:
        if policy[field] is not False:
            raise ValueError(f"CreatorVerifierPairingV1 independencePolicy must keep {field} false")

    event_refs = pairing["coordinationEventRefs"]
    expected_event_refs = [
        f"{DELEGATION_MANIFEST_ARTIFACT_PATH}#coordinationEvents/{event['id']}"
        for event in delegation_manifest["coordinationEvents"]
    ]
    if event_refs != expected_event_refs:
        raise ValueError("CreatorVerifierPairingV1 coordinationEventRefs must bind DelegationManifestV1 coordination events")
    if not set(NON_REGRESSION_REUSE_PATHS).issubset(set(pairing["nonRegressionReusePath"])):
        raise ValueError("CreatorVerifierPairingV1 must include non-regression workload reuse paths")


def _pairing_ref() -> str:
    return f"{CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH}#id/{CREATOR_VERIFIER_PAIRING_ID}"


def _build_agent_message_source_artifacts(
    delegation_manifest: dict[str, Any],
    pairing: dict[str, Any],
    root: Path,
) -> list[dict[str, Any]]:
    paths_by_kind = _artifact_paths_by_kind(delegation_manifest["delegations"][0])
    return [
        _artifact_source("delegation_manifest", DELEGATION_MANIFEST_ARTIFACT_PATH, root),
        _artifact_source("creator_verifier_pairing", CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH, root),
        _artifact_source("creator_output_artifact", paths_by_kind["ArtifactV1"], root),
        _artifact_source("acceptance_evidence", paths_by_kind["EvidenceListV1"], root),
        _artifact_source("verifier_result", paths_by_kind["VerifierResultV1"], root),
    ]


def _expected_agent_message_source_paths(delegation_manifest: dict[str, Any]) -> dict[str, str]:
    paths_by_kind = _artifact_paths_by_kind(delegation_manifest["delegations"][0])
    return {
        "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
        "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
        "creator_output_artifact": paths_by_kind["ArtifactV1"],
        "acceptance_evidence": paths_by_kind["EvidenceListV1"],
        "verifier_result": paths_by_kind["VerifierResultV1"],
    }


def _build_agent_message_channels() -> list[dict[str, Any]]:
    return [
        {
            "channelId": AGENT_MESSAGE_CHANNEL_REQUEST_ID,
            "fromAgent": "creator_agent",
            "toAgent": "verifier_agent",
            "purpose": "verification_request",
            "deliveryMode": "direct_point_to_point",
            "ordering": "causal",
            "broadcastAllowed": False,
            "externalSideEffectsAllowed": False,
        },
        {
            "channelId": AGENT_MESSAGE_CHANNEL_RESPONSE_ID,
            "fromAgent": "verifier_agent",
            "toAgent": "creator_agent",
            "purpose": "verification_response",
            "deliveryMode": "direct_point_to_point",
            "ordering": "causal",
            "broadcastAllowed": False,
            "externalSideEffectsAllowed": False,
        },
    ]


def _coord_event_ref(event_id: str) -> str:
    return f"{DELEGATION_MANIFEST_ARTIFACT_PATH}#coordinationEvents/{event_id}"


def _build_agent_messages(delegation_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])
    pairing_ref = _pairing_ref()
    verification_requested_event_id = delegation_manifest["coordinationEvents"][-1]["id"]
    return [
        {
            "schemaVersion": AGENT_MESSAGE_SCHEMA_VERSION,
            "id": AGENT_MESSAGE_REQUEST_ID,
            "type": "verification.request",
            "channelId": AGENT_MESSAGE_CHANNEL_REQUEST_ID,
            "fromAgent": delegation["creatorAgent"],
            "toAgent": delegation["verifierAgent"],
            "delegationRef": delegation_ref,
            "pairingRef": pairing_ref,
            "inReplyToMessageId": None,
            "causalRefs": [_coord_event_ref(verification_requested_event_id)],
            "payloadRefs": [
                {
                    "artifactKind": "ArtifactV1",
                    "artifactRef": paths_by_kind["ArtifactV1"],
                    "role": "creator_output",
                },
                {
                    "artifactKind": "EvidenceListV1",
                    "artifactRef": paths_by_kind["EvidenceListV1"],
                    "role": "acceptance_evidence",
                },
            ],
            "requiresResponse": True,
            "expectedResponseType": "verification.response",
            "carriesSideEffects": False,
            "mayOverrideVerifierResult": False,
            "body": "Creator agent requests independent verification of the source-bound ArtifactV1 and acceptance EvidenceListV1 without declaring acceptance.",
        },
        {
            "schemaVersion": AGENT_MESSAGE_SCHEMA_VERSION,
            "id": AGENT_MESSAGE_RESPONSE_ID,
            "type": "verification.response",
            "channelId": AGENT_MESSAGE_CHANNEL_RESPONSE_ID,
            "fromAgent": delegation["verifierAgent"],
            "toAgent": delegation["creatorAgent"],
            "delegationRef": delegation_ref,
            "pairingRef": pairing_ref,
            "inReplyToMessageId": AGENT_MESSAGE_REQUEST_ID,
            "causalRefs": [AGENT_MESSAGE_REQUEST_ID],
            "payloadRefs": [
                {
                    "artifactKind": "VerifierResultV1",
                    "artifactRef": paths_by_kind["VerifierResultV1"],
                    "role": "verifier_result",
                },
            ],
            "requiresResponse": False,
            "expectedResponseType": None,
            "carriesSideEffects": False,
            "mayOverrideVerifierResult": False,
            "body": "Verifier agent returns the independent VerifierResultV1; creator must not override the verifier verdict.",
        },
    ]


def build_agent_message_manifest(root: Path) -> dict[str, Any]:
    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(pairing, root)
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])

    return {
        "schemaVersion": AGENT_MESSAGE_MANIFEST_SCHEMA_VERSION,
        "id": AGENT_MESSAGE_MANIFEST_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "agent_coordination_direct_communication_contract",
        "mode": "static_contract_only",
        "kernelPrimitive": "AgentMessage",
        "coordinationProtocols": ["direct_communication", "creator_verifier"],
        "sourceArtifacts": _build_agent_message_source_artifacts(delegation_manifest, pairing, root),
        "delegationBinding": {
            "delegationManifestRef": DELEGATION_MANIFEST_ARTIFACT_PATH,
            "delegationRef": delegation_ref,
            "pairingManifestRef": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
            "pairingRef": _pairing_ref(),
            "parentTaskSpecRef": delegation["parentTaskSpecRef"],
            "parentRunRef": delegation["parentRunRef"],
            "workloadIndependentObjective": delegation["workloadIndependentObjective"],
        },
        "agentBindings": [
            {
                "agentId": delegation["creatorAgent"],
                "role": "creator",
                "owns": ["verification_request_origination"],
                "maySendVerificationRequest": True,
                "mayReturnVerifierResult": False,
                "mayBroadcast": False,
                "mayOverrideVerifierResult": False,
            },
            {
                "agentId": delegation["verifierAgent"],
                "role": "verifier",
                "owns": ["verification_response_origination", "verifier_result_authoring"],
                "maySendVerificationRequest": False,
                "mayReturnVerifierResult": True,
                "mayBroadcast": False,
                "mayOverrideVerifierResult": False,
            },
        ],
        "channels": _build_agent_message_channels(),
        "messages": _build_agent_messages(delegation_manifest),
        "messageTypeSequence": list(AGENT_MESSAGE_TYPE_SEQUENCE),
        "communicationInvariant": {
            "creatorAgent": delegation["creatorAgent"],
            "verifierAgent": delegation["verifierAgent"],
            "verifierResultOwner": "verifier-runtime-v1",
            "messagesMayCarrySideEffects": False,
            "messagesMayOverrideVerifierResult": False,
            "verifierMustRespondBeforeAcceptance": True,
            "requestResponseMustBeBound": True,
            "broadcastAllowed": False,
        },
        "policyBoundary": {
            "policySchemaVersion": "policy-v1",
            "externalSideEffectsAllowed": False,
            "workspaceMutationAllowed": False,
            "deliverySendAllowed": False,
            "realMultiAgentRuntimeAllowed": False,
            "providerExecutionAllowed": False,
            "broadcastAllowed": False,
        },
        "coordinationEventRefs": [
            _coord_event_ref(event["id"])
            for event in delegation_manifest["coordinationEvents"]
        ],
        "expectedPayloadArtifactRefs": {
            "ArtifactV1": paths_by_kind["ArtifactV1"],
            "EvidenceListV1": paths_by_kind["EvidenceListV1"],
            "VerifierResultV1": paths_by_kind["VerifierResultV1"],
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATHS),
        "invariants": [
            "AgentMessageManifestV1 is workload-independent: it binds direct creator<->verifier messages without adding regression/email behavior.",
            "Every verification.request must be followed by exactly one verification.response that replies to it; the response carries the VerifierResultV1.",
            "Messages must not carry external side effects, override verifier results, or broadcast to additional subscribers.",
            "AgentMessageV1 payload refs must remain workload-independent ArtifactV1/EvidenceListV1/VerifierResultV1 paths bound to the delegation manifest.",
            "The manifest is a static contract artifact and does not run a real multi-agent framework, send email, mutate a workspace, or execute providers.",
        ],
    }


def _validate_agent_message_source_artifacts(
    source_artifacts: list[Any],
    delegation_manifest: dict[str, Any],
    root: Path,
) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("AgentMessageManifestV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_agent_message_source_paths(delegation_manifest)
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("AgentMessageManifestV1 sourceArtifacts must be objects")
        _require_fields("AgentMessageManifestV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected AgentMessageManifestV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"AgentMessageManifestV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"AgentMessageManifestV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"AgentMessageManifestV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"AgentMessageManifestV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def _validate_agent_message_channel(channel: dict[str, Any]) -> None:
    _require_fields(
        "AgentMessageManifestV1 channel",
        channel,
        [
            "channelId",
            "fromAgent",
            "toAgent",
            "purpose",
            "deliveryMode",
            "ordering",
            "broadcastAllowed",
            "externalSideEffectsAllowed",
        ],
    )
    if channel["fromAgent"] == channel["toAgent"]:
        raise ValueError("AgentMessageManifestV1 channel fromAgent and toAgent must be distinct")
    if channel["deliveryMode"] != "direct_point_to_point":
        raise ValueError("AgentMessageManifestV1 channel deliveryMode must be direct_point_to_point")
    if channel["ordering"] != "causal":
        raise ValueError("AgentMessageManifestV1 channel ordering must be causal")
    if channel["broadcastAllowed"] is not False:
        raise ValueError("AgentMessageManifestV1 channel broadcast must be disallowed")
    if channel["externalSideEffectsAllowed"] is not False:
        raise ValueError("AgentMessageManifestV1 channel must keep externalSideEffectsAllowed false")


def _validate_agent_message_payload(
    label: str,
    payload_refs: list[Any],
    expected_payload_paths: dict[str, str],
    expected_kinds: set[str],
) -> None:
    if not isinstance(payload_refs, list) or not payload_refs:
        raise ValueError(f"{label} payloadRefs must be a non-empty list")
    seen_kinds: set[str] = set()
    for payload in payload_refs:
        if not isinstance(payload, dict):
            raise ValueError(f"{label} payloadRefs must be objects")
        _require_fields(label + " payloadRefs", payload, ["artifactKind", "artifactRef", "role"])
        kind = payload["artifactKind"]
        if kind not in AGENT_MESSAGE_PAYLOAD_KINDS:
            raise ValueError(
                f"{label} payloadRefs must remain workload-independent ArtifactV1/EvidenceListV1/VerifierResultV1 refs"
            )
        if kind not in expected_kinds:
            raise ValueError(f"{label} payloadRefs must not include unexpected artifactKind {kind}")
        _reject_regression_email_delivery_ref(label + " payloadRefs", payload["artifactRef"])
        if payload["artifactRef"] != expected_payload_paths[kind]:
            raise ValueError(
                f"{label} payloadRefs must bind delegation manifest path for {kind}: expected {expected_payload_paths[kind]}"
            )
        seen_kinds.add(kind)
    if seen_kinds != expected_kinds:
        raise ValueError(f"{label} payloadRefs must cover {sorted(expected_kinds)}")


def _validate_agent_messages(
    messages: list[Any],
    delegation_manifest: dict[str, Any],
    channels_by_id: dict[str, dict[str, Any]],
    delegation_ref: str,
    pairing_ref: str,
    expected_payload_paths: dict[str, str],
) -> None:
    if not isinstance(messages, list) or [msg.get("type") for msg in messages if isinstance(msg, dict)] != AGENT_MESSAGE_TYPE_SEQUENCE:
        raise ValueError(
            f"AgentMessageManifestV1 messages must follow messageTypeSequence {AGENT_MESSAGE_TYPE_SEQUENCE}"
        )
    delegation = delegation_manifest["delegations"][0]
    verification_requested_event_id = delegation_manifest["coordinationEvents"][-1]["id"]
    expected_request_causal = _coord_event_ref(verification_requested_event_id)
    message_ids: set[str] = set()
    request_message: dict[str, Any] | None = None
    response_message: dict[str, Any] | None = None
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("AgentMessageManifestV1 messages must be objects")
        _require_fields(
            "AgentMessageManifestV1 message",
            message,
            [
                "schemaVersion",
                "id",
                "type",
                "channelId",
                "fromAgent",
                "toAgent",
                "delegationRef",
                "pairingRef",
                "inReplyToMessageId",
                "causalRefs",
                "payloadRefs",
                "requiresResponse",
                "expectedResponseType",
                "carriesSideEffects",
                "mayOverrideVerifierResult",
                "body",
            ],
        )
        if message["schemaVersion"] != AGENT_MESSAGE_SCHEMA_VERSION:
            raise ValueError(f"AgentMessageManifestV1 message schemaVersion must be {AGENT_MESSAGE_SCHEMA_VERSION}")
        if message["channelId"] not in channels_by_id:
            raise ValueError("AgentMessageManifestV1 message must reference a declared channel")
        channel = channels_by_id[message["channelId"]]
        if message["fromAgent"] != channel["fromAgent"] or message["toAgent"] != channel["toAgent"]:
            raise ValueError("AgentMessageManifestV1 message agents must match channel binding")
        if message["fromAgent"] == message["toAgent"]:
            raise ValueError("AgentMessageManifestV1 message fromAgent and toAgent must be distinct")
        if message["delegationRef"] != delegation_ref:
            raise ValueError("AgentMessageManifestV1 message must bind DelegationManifestV1 delegation")
        if message["pairingRef"] != pairing_ref:
            raise ValueError("AgentMessageManifestV1 message must bind CreatorVerifierPairingV1")
        if message["carriesSideEffects"] is not False:
            raise ValueError("AgentMessageManifestV1 messages must not carry side effects")
        if message["mayOverrideVerifierResult"] is not False:
            raise ValueError("AgentMessageManifestV1 messages must not override verifier results")
        message_ids.add(message["id"])
        if message["type"] == "verification.request":
            request_message = message
            if message["fromAgent"] != delegation["creatorAgent"] or message["toAgent"] != delegation["verifierAgent"]:
                raise ValueError("AgentMessageManifestV1 verification.request must flow creator -> verifier")
            if message["inReplyToMessageId"] is not None:
                raise ValueError("AgentMessageManifestV1 verification.request must not reply to another message")
            if message["requiresResponse"] is not True:
                raise ValueError("AgentMessageManifestV1 verification.request must require a response")
            if message["expectedResponseType"] != "verification.response":
                raise ValueError("AgentMessageManifestV1 verification.request expectedResponseType must be verification.response")
            if expected_request_causal not in message["causalRefs"]:
                raise ValueError(
                    "AgentMessageManifestV1 verification.request causalRefs must reference DelegationManifestV1 verification.requested event"
                )
            _validate_agent_message_payload(
                "AgentMessageManifestV1 verification.request",
                message["payloadRefs"],
                expected_payload_paths,
                {"ArtifactV1", "EvidenceListV1"},
            )
        elif message["type"] == "verification.response":
            response_message = message
            if message["fromAgent"] != delegation["verifierAgent"] or message["toAgent"] != delegation["creatorAgent"]:
                raise ValueError("AgentMessageManifestV1 verification.response must flow verifier -> creator")
            if message["inReplyToMessageId"] != AGENT_MESSAGE_REQUEST_ID:
                raise ValueError("AgentMessageManifestV1 verification.response must reply to verification.request via inReplyToMessageId")
            if message["requiresResponse"] is not False:
                raise ValueError("AgentMessageManifestV1 verification.response must not require a response")
            if message["expectedResponseType"] is not None:
                raise ValueError("AgentMessageManifestV1 verification.response must not declare expectedResponseType")
            if AGENT_MESSAGE_REQUEST_ID not in message["causalRefs"]:
                raise ValueError("AgentMessageManifestV1 verification.response causalRefs must include the verification.request id")
            _validate_agent_message_payload(
                "AgentMessageManifestV1 verification.response",
                message["payloadRefs"],
                expected_payload_paths,
                {"VerifierResultV1"},
            )
        else:
            raise ValueError(f"AgentMessageManifestV1 unsupported message type: {message['type']}")
    if len(message_ids) != len(messages):
        raise ValueError("AgentMessageManifestV1 message ids must be unique")
    if request_message is None or response_message is None:
        raise ValueError("AgentMessageManifestV1 must contain both verification.request and verification.response messages")


def validate_agent_message_manifest(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "AgentMessageManifestV1",
        manifest,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "kernelPrimitive",
            "coordinationProtocols",
            "sourceArtifacts",
            "delegationBinding",
            "agentBindings",
            "channels",
            "messages",
            "messageTypeSequence",
            "communicationInvariant",
            "policyBoundary",
            "coordinationEventRefs",
            "expectedPayloadArtifactRefs",
            "nonRegressionReusePath",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != AGENT_MESSAGE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"AgentMessageManifestV1 schemaVersion must be {AGENT_MESSAGE_MANIFEST_SCHEMA_VERSION}")
    if manifest["id"] != AGENT_MESSAGE_MANIFEST_ID:
        raise ValueError(f"AgentMessageManifestV1 id must be {AGENT_MESSAGE_MANIFEST_ID}")
    if manifest["phase"] != "post_mvp":
        raise ValueError("AgentMessageManifestV1 phase must be post_mvp")
    if manifest["scope"] != "agent_coordination_direct_communication_contract":
        raise ValueError("AgentMessageManifestV1 scope must be agent_coordination_direct_communication_contract")
    if manifest["mode"] != "static_contract_only":
        raise ValueError("AgentMessageManifestV1 mode must be static_contract_only")
    if manifest["kernelPrimitive"] != "AgentMessage":
        raise ValueError("AgentMessageManifestV1 kernelPrimitive must be AgentMessage")
    if "direct_communication" not in manifest["coordinationProtocols"]:
        raise ValueError("AgentMessageManifestV1 coordinationProtocols must include direct_communication")
    if manifest["messageTypeSequence"] != AGENT_MESSAGE_TYPE_SEQUENCE:
        raise ValueError(
            f"AgentMessageManifestV1 messageTypeSequence must equal {AGENT_MESSAGE_TYPE_SEQUENCE}"
        )

    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(pairing, root)
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])
    pairing_ref = _pairing_ref()

    _validate_agent_message_source_artifacts(manifest["sourceArtifacts"], delegation_manifest, root)

    binding = manifest["delegationBinding"]
    _require_fields(
        "AgentMessageManifestV1 delegationBinding",
        binding,
        [
            "delegationManifestRef",
            "delegationRef",
            "pairingManifestRef",
            "pairingRef",
            "parentTaskSpecRef",
            "parentRunRef",
            "workloadIndependentObjective",
        ],
    )
    if binding["delegationManifestRef"] != DELEGATION_MANIFEST_ARTIFACT_PATH or binding["delegationRef"] != delegation_ref:
        raise ValueError("AgentMessageManifestV1 delegationBinding must reference DelegationManifestV1")
    if binding["pairingManifestRef"] != CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH or binding["pairingRef"] != pairing_ref:
        raise ValueError("AgentMessageManifestV1 delegationBinding must reference CreatorVerifierPairingV1")
    if binding["parentTaskSpecRef"] != delegation["parentTaskSpecRef"] or binding["parentRunRef"] != delegation["parentRunRef"]:
        raise ValueError("AgentMessageManifestV1 delegationBinding must inherit parent TaskSpec and Run refs")

    agent_bindings = manifest["agentBindings"]
    if not isinstance(agent_bindings, list) or len(agent_bindings) != 2:
        raise ValueError("AgentMessageManifestV1 agentBindings must contain creator and verifier")
    agents_by_role: dict[str, dict[str, Any]] = {}
    for agent in agent_bindings:
        if not isinstance(agent, dict):
            raise ValueError("AgentMessageManifestV1 agentBindings must be objects")
        _require_fields(
            "AgentMessageManifestV1 agent binding",
            agent,
            [
                "agentId",
                "role",
                "owns",
                "maySendVerificationRequest",
                "mayReturnVerifierResult",
                "mayBroadcast",
                "mayOverrideVerifierResult",
            ],
        )
        if agent["mayBroadcast"] is not False:
            raise ValueError("AgentMessageManifestV1 agentBindings must keep mayBroadcast false")
        if agent["mayOverrideVerifierResult"] is not False:
            raise ValueError("AgentMessageManifestV1 agentBindings must keep mayOverrideVerifierResult false")
        agents_by_role[agent["role"]] = agent
    if set(agents_by_role) != {"creator", "verifier"}:
        raise ValueError("AgentMessageManifestV1 agentBindings must cover creator and verifier roles")
    creator_agent = agents_by_role["creator"]
    verifier_agent = agents_by_role["verifier"]
    if creator_agent["agentId"] != delegation["creatorAgent"] or verifier_agent["agentId"] != delegation["verifierAgent"]:
        raise ValueError("AgentMessageManifestV1 agentBindings must match DelegationManifestV1 creator and verifier agents")
    if creator_agent["agentId"] == verifier_agent["agentId"]:
        raise ValueError("AgentMessageManifestV1 creator and verifier agents must be distinct")
    if creator_agent["maySendVerificationRequest"] is not True or creator_agent["mayReturnVerifierResult"] is not False:
        raise ValueError("AgentMessageManifestV1 creator must originate requests without returning verifier results")
    if verifier_agent["maySendVerificationRequest"] is not False or verifier_agent["mayReturnVerifierResult"] is not True:
        raise ValueError("AgentMessageManifestV1 verifier must return verifier results without originating requests")

    channels = manifest["channels"]
    if not isinstance(channels, list) or len(channels) != 2:
        raise ValueError("AgentMessageManifestV1 channels must declare request and response channels")
    channels_by_id: dict[str, dict[str, Any]] = {}
    expected_channel_ids = {AGENT_MESSAGE_CHANNEL_REQUEST_ID, AGENT_MESSAGE_CHANNEL_RESPONSE_ID}
    for channel in channels:
        if not isinstance(channel, dict):
            raise ValueError("AgentMessageManifestV1 channels must be objects")
        _validate_agent_message_channel(channel)
        channels_by_id[channel["channelId"]] = channel
    if set(channels_by_id) != expected_channel_ids:
        raise ValueError(f"AgentMessageManifestV1 channels must equal {sorted(expected_channel_ids)}")

    expected_payload_paths = {
        "ArtifactV1": paths_by_kind["ArtifactV1"],
        "EvidenceListV1": paths_by_kind["EvidenceListV1"],
        "VerifierResultV1": paths_by_kind["VerifierResultV1"],
    }
    if manifest["expectedPayloadArtifactRefs"] != expected_payload_paths:
        raise ValueError("AgentMessageManifestV1 expectedPayloadArtifactRefs must bind DelegationManifestV1 artifact paths")

    _validate_agent_messages(
        manifest["messages"],
        delegation_manifest,
        channels_by_id,
        delegation_ref,
        pairing_ref,
        expected_payload_paths,
    )

    invariant = manifest["communicationInvariant"]
    _require_fields(
        "AgentMessageManifestV1 communicationInvariant",
        invariant,
        [
            "creatorAgent",
            "verifierAgent",
            "verifierResultOwner",
            "messagesMayCarrySideEffects",
            "messagesMayOverrideVerifierResult",
            "verifierMustRespondBeforeAcceptance",
            "requestResponseMustBeBound",
            "broadcastAllowed",
        ],
    )
    if invariant["creatorAgent"] == invariant["verifierAgent"]:
        raise ValueError("AgentMessageManifestV1 communicationInvariant agents must be distinct")
    if invariant["verifierResultOwner"] != "verifier-runtime-v1":
        raise ValueError("AgentMessageManifestV1 communicationInvariant verifierResultOwner must be verifier-runtime-v1")
    if invariant["messagesMayCarrySideEffects"] is not False:
        raise ValueError("AgentMessageManifestV1 communicationInvariant must keep messagesMayCarrySideEffects false")
    if invariant["messagesMayOverrideVerifierResult"] is not False:
        raise ValueError("AgentMessageManifestV1 communicationInvariant must keep messagesMayOverrideVerifierResult false")
    if invariant["verifierMustRespondBeforeAcceptance"] is not True:
        raise ValueError("AgentMessageManifestV1 communicationInvariant must require verifier response before acceptance")
    if invariant["requestResponseMustBeBound"] is not True:
        raise ValueError("AgentMessageManifestV1 communicationInvariant must bind request and response")
    if invariant["broadcastAllowed"] is not False:
        raise ValueError("AgentMessageManifestV1 communicationInvariant must keep broadcastAllowed false")

    policy = manifest["policyBoundary"]
    _require_fields(
        "AgentMessageManifestV1 policyBoundary",
        policy,
        [
            "policySchemaVersion",
            "externalSideEffectsAllowed",
            "workspaceMutationAllowed",
            "deliverySendAllowed",
            "realMultiAgentRuntimeAllowed",
            "providerExecutionAllowed",
            "broadcastAllowed",
        ],
    )
    if policy["policySchemaVersion"] != "policy-v1":
        raise ValueError("AgentMessageManifestV1 policyBoundary must use policy-v1")
    for field in [
        "externalSideEffectsAllowed",
        "workspaceMutationAllowed",
        "deliverySendAllowed",
        "realMultiAgentRuntimeAllowed",
        "providerExecutionAllowed",
        "broadcastAllowed",
    ]:
        if policy[field] is not False:
            raise ValueError(f"AgentMessageManifestV1 policyBoundary must keep {field} false")

    expected_event_refs = [
        _coord_event_ref(event["id"])
        for event in delegation_manifest["coordinationEvents"]
    ]
    if manifest["coordinationEventRefs"] != expected_event_refs:
        raise ValueError("AgentMessageManifestV1 coordinationEventRefs must bind DelegationManifestV1 coordination events")
    if not set(NON_REGRESSION_REUSE_PATHS).issubset(set(manifest["nonRegressionReusePath"])):
        raise ValueError("AgentMessageManifestV1 must include non-regression workload reuse paths")


def _agent_message_manifest_ref() -> str:
    return f"{AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH}#id/{AGENT_MESSAGE_MANIFEST_ID}"


def _agent_message_ref(message_id: str) -> str:
    return f"{AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH}#messages/{message_id}"


def _build_negotiation_source_artifacts(root: Path) -> list[dict[str, Any]]:
    return [
        _artifact_source("delegation_manifest", DELEGATION_MANIFEST_ARTIFACT_PATH, root),
        _artifact_source("creator_verifier_pairing", CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH, root),
        _artifact_source("agent_message_manifest", AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH, root),
    ]


def _expected_negotiation_source_paths() -> dict[str, str]:
    return {
        "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
        "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
        "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    }


def _build_negotiation_agent_bindings(delegation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "agentId": delegation["creatorAgent"],
            "role": "creator",
            "owns": ["proposal_origination", "agreement_co_authoring"],
            "mayProposeAdjustment": True,
            "mayAcceptProposal": True,
            "mayOverrideVerifierResult": False,
            "mayMutateDelegationArtifacts": False,
            "mayBroadcast": False,
        },
        {
            "agentId": delegation["verifierAgent"],
            "role": "verifier",
            "owns": ["counter_proposal_origination", "agreement_co_authoring"],
            "mayProposeAdjustment": True,
            "mayAcceptProposal": True,
            "mayOverrideVerifierResult": False,
            "mayMutateDelegationArtifacts": False,
            "mayBroadcast": False,
        },
    ]


def _build_negotiation_proposals(delegation: dict[str, Any], delegation_ref: str, pairing_ref: str) -> list[dict[str, Any]]:
    base_payload = {
        "topic": "acceptance_criteria",
        "delegationRef": delegation_ref,
        "pairingRef": pairing_ref,
    }
    return [
        {
            **base_payload,
            "schemaVersion": NEGOTIATION_PROPOSAL_SCHEMA_VERSION,
            "id": NEGOTIATION_PROPOSAL_ROOT_ID,
            "proposalType": "proposal",
            "fromAgent": delegation["creatorAgent"],
            "toAgent": delegation["verifierAgent"],
            "inReplyToProposalId": None,
            "causalRefs": [_agent_message_ref(AGENT_MESSAGE_REQUEST_ID)],
            "proposedDelta": {
                "field": "acceptanceCriteriaClarification",
                "appliesToDelegationRef": delegation_ref,
                "mutatesExpectedArtifacts": False,
                "mutatesPolicyBoundary": False,
                "addedClause": "All required evidence must reference source-bound observation hashes captured before verifier review.",
            },
            "rationale": "Creator proposes a clarifying acceptance-criteria clause that does not mutate expectedArtifacts or policyBoundary.",
            "policyBoundaryHonored": True,
            "mayOverrideVerifierResult": False,
            "carriesSideEffects": False,
            "broadcastAllowed": False,
        },
        {
            **base_payload,
            "schemaVersion": NEGOTIATION_PROPOSAL_SCHEMA_VERSION,
            "id": NEGOTIATION_PROPOSAL_COUNTER_ID,
            "proposalType": "counter_proposal",
            "fromAgent": delegation["verifierAgent"],
            "toAgent": delegation["creatorAgent"],
            "inReplyToProposalId": NEGOTIATION_PROPOSAL_ROOT_ID,
            "causalRefs": [NEGOTIATION_PROPOSAL_ROOT_ID],
            "proposedDelta": {
                "field": "acceptanceCriteriaClarification",
                "appliesToDelegationRef": delegation_ref,
                "mutatesExpectedArtifacts": False,
                "mutatesPolicyBoundary": False,
                "addedClause": "All required evidence must reference source-bound observation hashes captured before verifier review AND must remain independent of creator override.",
            },
            "rationale": "Verifier strengthens the clarifying clause to preserve verifier independence without mutating expectedArtifacts.",
            "policyBoundaryHonored": True,
            "mayOverrideVerifierResult": False,
            "carriesSideEffects": False,
            "broadcastAllowed": False,
        },
        {
            **base_payload,
            "schemaVersion": NEGOTIATION_PROPOSAL_SCHEMA_VERSION,
            "id": NEGOTIATION_PROPOSAL_AGREEMENT_ID,
            "proposalType": "agreement",
            "fromAgent": delegation["creatorAgent"],
            "toAgent": delegation["verifierAgent"],
            "inReplyToProposalId": NEGOTIATION_PROPOSAL_COUNTER_ID,
            "causalRefs": [NEGOTIATION_PROPOSAL_COUNTER_ID],
            "proposedDelta": {
                "field": "acceptanceCriteriaClarification",
                "appliesToDelegationRef": delegation_ref,
                "mutatesExpectedArtifacts": False,
                "mutatesPolicyBoundary": False,
                "addedClause": "All required evidence must reference source-bound observation hashes captured before verifier review AND must remain independent of creator override.",
            },
            "rationale": "Creator agrees to the verifier counter-proposal without overriding VerifierResultV1 or mutating delegation expectedArtifacts.",
            "policyBoundaryHonored": True,
            "mayOverrideVerifierResult": False,
            "carriesSideEffects": False,
            "broadcastAllowed": False,
        },
    ]


def _build_negotiation_agreement(delegation: dict[str, Any], delegation_ref: str, pairing_ref: str) -> dict[str, Any]:
    return {
        "schemaVersion": NEGOTIATION_AGREEMENT_SCHEMA_VERSION,
        "id": NEGOTIATION_AGREEMENT_ID,
        "topic": "acceptance_criteria",
        "agreedBy": [delegation["creatorAgent"], delegation["verifierAgent"]],
        "rootProposalId": NEGOTIATION_PROPOSAL_ROOT_ID,
        "finalProposalId": NEGOTIATION_PROPOSAL_AGREEMENT_ID,
        "appliesToDelegationRef": delegation_ref,
        "appliesToPairingRef": pairing_ref,
        "agreedClause": "All required evidence must reference source-bound observation hashes captured before verifier review AND must remain independent of creator override.",
        "mutatesExpectedArtifacts": False,
        "mutatesPolicyBoundary": False,
        "overridesVerifierResult": False,
        "carriesSideEffects": False,
        "broadcastAllowed": False,
    }


def build_negotiation_record(root: Path) -> dict[str, Any]:
    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(pairing, root)
    agent_message_manifest = _load_json(root / AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH)
    validate_agent_message_manifest(agent_message_manifest, root)
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])
    pairing_ref = _pairing_ref()

    return {
        "schemaVersion": NEGOTIATION_RECORD_SCHEMA_VERSION,
        "id": NEGOTIATION_RECORD_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "agent_coordination_negotiation_contract",
        "mode": "static_contract_only",
        "kernelPrimitive": "NegotiationRecord",
        "coordinationProtocols": ["negotiation", "direct_communication", "creator_verifier"],
        "sourceArtifacts": _build_negotiation_source_artifacts(root),
        "delegationBinding": {
            "delegationManifestRef": DELEGATION_MANIFEST_ARTIFACT_PATH,
            "delegationRef": delegation_ref,
            "pairingManifestRef": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
            "pairingRef": pairing_ref,
            "agentMessageManifestRef": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
            "agentMessageManifestId": _agent_message_manifest_ref(),
            "parentTaskSpecRef": delegation["parentTaskSpecRef"],
            "parentRunRef": delegation["parentRunRef"],
            "workloadIndependentObjective": delegation["workloadIndependentObjective"],
        },
        "agentBindings": _build_negotiation_agent_bindings(delegation),
        "negotiationTopics": list(NEGOTIATION_TOPICS),
        "proposalTypeSequence": list(NEGOTIATION_PROPOSAL_SEQUENCE_TYPES),
        "proposals": _build_negotiation_proposals(delegation, delegation_ref, pairing_ref),
        "agreement": _build_negotiation_agreement(delegation, delegation_ref, pairing_ref),
        "negotiationInvariant": {
            "creatorAgent": delegation["creatorAgent"],
            "verifierAgent": delegation["verifierAgent"],
            "verifierResultOwner": "verifier-runtime-v1",
            "agreementRequiresBothParties": True,
            "agreementMayOverrideVerifierResult": False,
            "agreementMayMutateExpectedArtifacts": False,
            "agreementMayMutatePolicyBoundary": False,
            "proposalsMayCarrySideEffects": False,
            "broadcastAllowed": False,
            "creatorAndVerifierMustBeDistinct": True,
        },
        "policyBoundary": {
            "policySchemaVersion": "policy-v1",
            "externalSideEffectsAllowed": False,
            "workspaceMutationAllowed": False,
            "deliverySendAllowed": False,
            "realMultiAgentRuntimeAllowed": False,
            "providerExecutionAllowed": False,
            "broadcastAllowed": False,
        },
        "coordinationEventRefs": [
            _coord_event_ref(event["id"])
            for event in delegation_manifest["coordinationEvents"]
        ],
        "messageRefs": {
            "verificationRequest": _agent_message_ref(AGENT_MESSAGE_REQUEST_ID),
            "verificationResponse": _agent_message_ref(AGENT_MESSAGE_RESPONSE_ID),
        },
        "expectedDelegationArtifactRefs": {
            "ArtifactV1": paths_by_kind["ArtifactV1"],
            "EvidenceListV1": paths_by_kind["EvidenceListV1"],
            "VerifierResultV1": paths_by_kind["VerifierResultV1"],
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATHS),
        "invariants": [
            "NegotiationRecordV1 is workload-independent: it captures scope/risk/policy/acceptance-criteria negotiation without adding regression/email behavior.",
            "Negotiation proposals form a causal chain that ends with a single agreement signed by both creator and verifier.",
            "Agreements must not override VerifierResultV1, mutate delegation expectedArtifacts, relax policyBoundary, carry side effects, or broadcast.",
            "Proposals and agreements bind DelegationManifestV1, CreatorVerifierPairingV1, and AgentMessageManifestV1 by reference; they do not duplicate or rewrite those contracts.",
            "The record is a static contract artifact and does not run a real negotiation runtime, scheduler, message bus, blackboard, or external delivery channel.",
        ],
    }


def _validate_negotiation_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("NegotiationRecordV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_negotiation_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("NegotiationRecordV1 sourceArtifacts must be objects")
        _require_fields("NegotiationRecordV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected NegotiationRecordV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"NegotiationRecordV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"NegotiationRecordV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"NegotiationRecordV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"NegotiationRecordV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def _validate_negotiation_proposal_delta(label: str, delta: dict[str, Any], delegation_ref: str) -> None:
    _require_fields(
        label + " proposedDelta",
        delta,
        ["field", "appliesToDelegationRef", "mutatesExpectedArtifacts", "mutatesPolicyBoundary", "addedClause"],
    )
    if delta["appliesToDelegationRef"] != delegation_ref:
        raise ValueError(f"{label} proposedDelta must apply to DelegationManifestV1 delegation")
    if delta["mutatesExpectedArtifacts"] is not False:
        raise ValueError(f"{label} proposedDelta must not mutate delegation expectedArtifacts")
    if delta["mutatesPolicyBoundary"] is not False:
        raise ValueError(f"{label} proposedDelta must not mutate delegation policyBoundary")
    added_clause = delta["addedClause"]
    if not isinstance(added_clause, str) or not added_clause.strip():
        raise ValueError(f"{label} proposedDelta.addedClause must be a non-empty string")
    lowered = added_clause.lower()
    for forbidden in ("email", "send_email", "delivery_unlock"):
        if forbidden in lowered:
            raise ValueError(
                f"{label} proposedDelta must not add regression/email delivery artifacts"
            )


def _validate_negotiation_proposal(
    label: str,
    proposal: dict[str, Any],
    delegation: dict[str, Any],
    delegation_ref: str,
    pairing_ref: str,
) -> None:
    _require_fields(
        label,
        proposal,
        [
            "schemaVersion",
            "id",
            "proposalType",
            "topic",
            "delegationRef",
            "pairingRef",
            "fromAgent",
            "toAgent",
            "inReplyToProposalId",
            "causalRefs",
            "proposedDelta",
            "rationale",
            "policyBoundaryHonored",
            "mayOverrideVerifierResult",
            "carriesSideEffects",
            "broadcastAllowed",
        ],
    )
    if proposal["schemaVersion"] != NEGOTIATION_PROPOSAL_SCHEMA_VERSION:
        raise ValueError(f"{label} schemaVersion must be {NEGOTIATION_PROPOSAL_SCHEMA_VERSION}")
    if proposal["proposalType"] not in NEGOTIATION_PROPOSAL_TYPES:
        raise ValueError(f"{label} proposalType must be one of {NEGOTIATION_PROPOSAL_TYPES}")
    if proposal["topic"] not in NEGOTIATION_TOPICS:
        raise ValueError(f"{label} topic must be one of {NEGOTIATION_TOPICS}")
    if proposal["delegationRef"] != delegation_ref:
        raise ValueError(f"{label} delegationRef must bind DelegationManifestV1 delegation")
    if proposal["pairingRef"] != pairing_ref:
        raise ValueError(f"{label} pairingRef must bind CreatorVerifierPairingV1")
    if proposal["fromAgent"] == proposal["toAgent"]:
        raise ValueError(f"{label} fromAgent and toAgent must be distinct")
    allowed_agents = {delegation["creatorAgent"], delegation["verifierAgent"]}
    if proposal["fromAgent"] not in allowed_agents or proposal["toAgent"] not in allowed_agents:
        raise ValueError(f"{label} agents must come from DelegationManifestV1 creator/verifier")
    if not isinstance(proposal["causalRefs"], list) or not proposal["causalRefs"]:
        raise ValueError(f"{label} causalRefs must be a non-empty list")
    if proposal["policyBoundaryHonored"] is not True:
        raise ValueError(f"{label} must honor delegation policyBoundary")
    if proposal["mayOverrideVerifierResult"] is not False:
        raise ValueError(f"{label} must not override verifier results")
    if proposal["carriesSideEffects"] is not False:
        raise ValueError(f"{label} must not carry side effects")
    if proposal["broadcastAllowed"] is not False:
        raise ValueError(f"{label} must not broadcast")
    _validate_negotiation_proposal_delta(label, proposal["proposedDelta"], delegation_ref)


def _validate_negotiation_proposals(
    proposals: list[Any],
    delegation: dict[str, Any],
    delegation_ref: str,
    pairing_ref: str,
    verification_request_ref: str,
) -> list[dict[str, Any]]:
    if not isinstance(proposals, list) or len(proposals) < 2:
        raise ValueError("NegotiationRecordV1 proposals must contain at least a proposal and an agreement")
    types = [proposal.get("proposalType") for proposal in proposals if isinstance(proposal, dict)]
    if types != NEGOTIATION_PROPOSAL_SEQUENCE_TYPES:
        raise ValueError(
            f"NegotiationRecordV1 proposals must follow proposalTypeSequence {NEGOTIATION_PROPOSAL_SEQUENCE_TYPES}"
        )
    proposal_ids: set[str] = set()
    previous: dict[str, Any] | None = None
    for index, proposal in enumerate(proposals):
        if not isinstance(proposal, dict):
            raise ValueError("NegotiationRecordV1 proposals must be objects")
        label = f"NegotiationRecordV1 proposal[{index}]"
        _validate_negotiation_proposal(label, proposal, delegation, delegation_ref, pairing_ref)
        if proposal["id"] in proposal_ids:
            raise ValueError(f"{label} id must be unique within proposals")
        proposal_ids.add(proposal["id"])
        if index == 0:
            if proposal["inReplyToProposalId"] is not None:
                raise ValueError(f"{label} root proposal must not reply to another proposal")
            if verification_request_ref not in proposal["causalRefs"]:
                raise ValueError(
                    f"{label} root proposal causalRefs must reference AgentMessageManifestV1 verification.request"
                )
            if proposal["fromAgent"] != delegation["creatorAgent"]:
                raise ValueError(f"{label} root proposal must originate from the creator agent")
        else:
            assert previous is not None
            if proposal["inReplyToProposalId"] != previous["id"]:
                raise ValueError(f"{label} must reply to the previous proposal via inReplyToProposalId")
            if previous["id"] not in proposal["causalRefs"]:
                raise ValueError(f"{label} causalRefs must include the previous proposal id")
        if index == 1 and proposal["fromAgent"] != delegation["verifierAgent"]:
            raise ValueError(f"{label} counter_proposal must originate from the verifier agent")
        previous = proposal
    if types[-1] != "agreement":
        raise ValueError("NegotiationRecordV1 proposals must end with an agreement proposal")
    return list(proposals)


def _validate_negotiation_agreement(
    agreement: dict[str, Any],
    proposals: list[dict[str, Any]],
    delegation: dict[str, Any],
    delegation_ref: str,
    pairing_ref: str,
) -> None:
    _require_fields(
        "NegotiationRecordV1 agreement",
        agreement,
        [
            "schemaVersion",
            "id",
            "topic",
            "agreedBy",
            "rootProposalId",
            "finalProposalId",
            "appliesToDelegationRef",
            "appliesToPairingRef",
            "agreedClause",
            "mutatesExpectedArtifacts",
            "mutatesPolicyBoundary",
            "overridesVerifierResult",
            "carriesSideEffects",
            "broadcastAllowed",
        ],
    )
    if agreement["schemaVersion"] != NEGOTIATION_AGREEMENT_SCHEMA_VERSION:
        raise ValueError(
            f"NegotiationRecordV1 agreement schemaVersion must be {NEGOTIATION_AGREEMENT_SCHEMA_VERSION}"
        )
    if agreement["topic"] not in NEGOTIATION_TOPICS:
        raise ValueError(f"NegotiationRecordV1 agreement topic must be one of {NEGOTIATION_TOPICS}")
    if agreement["topic"] != proposals[-1]["topic"]:
        raise ValueError("NegotiationRecordV1 agreement topic must match negotiation proposals")
    agreed_by = agreement["agreedBy"]
    if not isinstance(agreed_by, list) or set(agreed_by) != {delegation["creatorAgent"], delegation["verifierAgent"]}:
        raise ValueError("NegotiationRecordV1 agreement must be agreedBy both creator and verifier")
    if agreement["rootProposalId"] != proposals[0]["id"]:
        raise ValueError("NegotiationRecordV1 agreement rootProposalId must bind the first proposal")
    if agreement["finalProposalId"] != proposals[-1]["id"]:
        raise ValueError("NegotiationRecordV1 agreement finalProposalId must bind the final proposal")
    if agreement["appliesToDelegationRef"] != delegation_ref:
        raise ValueError("NegotiationRecordV1 agreement appliesToDelegationRef must bind DelegationManifestV1")
    if agreement["appliesToPairingRef"] != pairing_ref:
        raise ValueError("NegotiationRecordV1 agreement appliesToPairingRef must bind CreatorVerifierPairingV1")
    agreed_clause = agreement["agreedClause"]
    if not isinstance(agreed_clause, str) or not agreed_clause.strip():
        raise ValueError("NegotiationRecordV1 agreement agreedClause must be a non-empty string")
    if agreed_clause != proposals[-1]["proposedDelta"]["addedClause"]:
        raise ValueError("NegotiationRecordV1 agreement agreedClause must match final proposal addedClause")
    lowered = agreed_clause.lower()
    for forbidden in ("email", "send_email", "delivery_unlock"):
        if forbidden in lowered:
            raise ValueError("NegotiationRecordV1 agreement must not add regression/email delivery artifacts")
    if agreement["mutatesExpectedArtifacts"] is not False:
        raise ValueError("NegotiationRecordV1 agreement must not mutate delegation expectedArtifacts")
    if agreement["mutatesPolicyBoundary"] is not False:
        raise ValueError("NegotiationRecordV1 agreement must not mutate delegation policyBoundary")
    if agreement["overridesVerifierResult"] is not False:
        raise ValueError("NegotiationRecordV1 agreement must not override verifier results")
    if agreement["carriesSideEffects"] is not False:
        raise ValueError("NegotiationRecordV1 agreement must not carry side effects")
    if agreement["broadcastAllowed"] is not False:
        raise ValueError("NegotiationRecordV1 agreement must not broadcast")


def validate_negotiation_record(record: dict[str, Any], root: Path) -> None:
    _require_fields(
        "NegotiationRecordV1",
        record,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "kernelPrimitive",
            "coordinationProtocols",
            "sourceArtifacts",
            "delegationBinding",
            "agentBindings",
            "negotiationTopics",
            "proposalTypeSequence",
            "proposals",
            "agreement",
            "negotiationInvariant",
            "policyBoundary",
            "coordinationEventRefs",
            "messageRefs",
            "expectedDelegationArtifactRefs",
            "nonRegressionReusePath",
            "invariants",
        ],
    )
    if record["schemaVersion"] != NEGOTIATION_RECORD_SCHEMA_VERSION:
        raise ValueError(f"NegotiationRecordV1 schemaVersion must be {NEGOTIATION_RECORD_SCHEMA_VERSION}")
    if record["id"] != NEGOTIATION_RECORD_ID:
        raise ValueError(f"NegotiationRecordV1 id must be {NEGOTIATION_RECORD_ID}")
    if record["phase"] != "post_mvp":
        raise ValueError("NegotiationRecordV1 phase must be post_mvp")
    if record["scope"] != "agent_coordination_negotiation_contract":
        raise ValueError("NegotiationRecordV1 scope must be agent_coordination_negotiation_contract")
    if record["mode"] != "static_contract_only":
        raise ValueError("NegotiationRecordV1 mode must be static_contract_only")
    if record["kernelPrimitive"] != "NegotiationRecord":
        raise ValueError("NegotiationRecordV1 kernelPrimitive must be NegotiationRecord")
    if "negotiation" not in record["coordinationProtocols"]:
        raise ValueError("NegotiationRecordV1 coordinationProtocols must include negotiation")
    if list(record["negotiationTopics"]) != NEGOTIATION_TOPICS:
        raise ValueError(f"NegotiationRecordV1 negotiationTopics must equal {NEGOTIATION_TOPICS}")
    if list(record["proposalTypeSequence"]) != NEGOTIATION_PROPOSAL_SEQUENCE_TYPES:
        raise ValueError(
            f"NegotiationRecordV1 proposalTypeSequence must equal {NEGOTIATION_PROPOSAL_SEQUENCE_TYPES}"
        )

    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(pairing, root)
    agent_message_manifest = _load_json(root / AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH)
    validate_agent_message_manifest(agent_message_manifest, root)
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])
    pairing_ref = _pairing_ref()
    verification_request_ref = _agent_message_ref(AGENT_MESSAGE_REQUEST_ID)
    verification_response_ref = _agent_message_ref(AGENT_MESSAGE_RESPONSE_ID)

    _validate_negotiation_source_artifacts(record["sourceArtifacts"], root)

    binding = record["delegationBinding"]
    _require_fields(
        "NegotiationRecordV1 delegationBinding",
        binding,
        [
            "delegationManifestRef",
            "delegationRef",
            "pairingManifestRef",
            "pairingRef",
            "agentMessageManifestRef",
            "agentMessageManifestId",
            "parentTaskSpecRef",
            "parentRunRef",
            "workloadIndependentObjective",
        ],
    )
    if binding["delegationManifestRef"] != DELEGATION_MANIFEST_ARTIFACT_PATH or binding["delegationRef"] != delegation_ref:
        raise ValueError("NegotiationRecordV1 delegationBinding must reference DelegationManifestV1")
    if binding["pairingManifestRef"] != CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH or binding["pairingRef"] != pairing_ref:
        raise ValueError("NegotiationRecordV1 delegationBinding must reference CreatorVerifierPairingV1")
    if binding["agentMessageManifestRef"] != AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH:
        raise ValueError("NegotiationRecordV1 delegationBinding must reference AgentMessageManifestV1")
    if binding["agentMessageManifestId"] != _agent_message_manifest_ref():
        raise ValueError("NegotiationRecordV1 delegationBinding must bind AgentMessageManifestV1 id")
    if binding["parentTaskSpecRef"] != delegation["parentTaskSpecRef"] or binding["parentRunRef"] != delegation["parentRunRef"]:
        raise ValueError("NegotiationRecordV1 delegationBinding must inherit parent TaskSpec and Run refs")

    agent_bindings = record["agentBindings"]
    if not isinstance(agent_bindings, list) or len(agent_bindings) != 2:
        raise ValueError("NegotiationRecordV1 agentBindings must contain creator and verifier")
    agents_by_role: dict[str, dict[str, Any]] = {}
    for agent in agent_bindings:
        if not isinstance(agent, dict):
            raise ValueError("NegotiationRecordV1 agentBindings must be objects")
        _require_fields(
            "NegotiationRecordV1 agent binding",
            agent,
            [
                "agentId",
                "role",
                "owns",
                "mayProposeAdjustment",
                "mayAcceptProposal",
                "mayOverrideVerifierResult",
                "mayMutateDelegationArtifacts",
                "mayBroadcast",
            ],
        )
        if agent["mayOverrideVerifierResult"] is not False:
            raise ValueError("NegotiationRecordV1 agentBindings must keep mayOverrideVerifierResult false")
        if agent["mayMutateDelegationArtifacts"] is not False:
            raise ValueError("NegotiationRecordV1 agentBindings must keep mayMutateDelegationArtifacts false")
        if agent["mayBroadcast"] is not False:
            raise ValueError("NegotiationRecordV1 agentBindings must keep mayBroadcast false")
        agents_by_role[agent["role"]] = agent
    if set(agents_by_role) != {"creator", "verifier"}:
        raise ValueError("NegotiationRecordV1 agentBindings must cover creator and verifier roles")
    if agents_by_role["creator"]["agentId"] != delegation["creatorAgent"]:
        raise ValueError("NegotiationRecordV1 creator agentId must match DelegationManifestV1 creator")
    if agents_by_role["verifier"]["agentId"] != delegation["verifierAgent"]:
        raise ValueError("NegotiationRecordV1 verifier agentId must match DelegationManifestV1 verifier")
    if agents_by_role["creator"]["agentId"] == agents_by_role["verifier"]["agentId"]:
        raise ValueError("NegotiationRecordV1 creator and verifier agents must be distinct")

    proposals = _validate_negotiation_proposals(
        record["proposals"],
        delegation,
        delegation_ref,
        pairing_ref,
        verification_request_ref,
    )
    _validate_negotiation_agreement(record["agreement"], proposals, delegation, delegation_ref, pairing_ref)

    invariant = record["negotiationInvariant"]
    _require_fields(
        "NegotiationRecordV1 negotiationInvariant",
        invariant,
        [
            "creatorAgent",
            "verifierAgent",
            "verifierResultOwner",
            "agreementRequiresBothParties",
            "agreementMayOverrideVerifierResult",
            "agreementMayMutateExpectedArtifacts",
            "agreementMayMutatePolicyBoundary",
            "proposalsMayCarrySideEffects",
            "broadcastAllowed",
            "creatorAndVerifierMustBeDistinct",
        ],
    )
    if invariant["creatorAgent"] == invariant["verifierAgent"]:
        raise ValueError("NegotiationRecordV1 negotiationInvariant agents must be distinct")
    if invariant["verifierResultOwner"] != "verifier-runtime-v1":
        raise ValueError("NegotiationRecordV1 negotiationInvariant verifierResultOwner must be verifier-runtime-v1")
    if invariant["agreementRequiresBothParties"] is not True:
        raise ValueError("NegotiationRecordV1 negotiationInvariant must require both parties for agreement")
    for field in [
        "agreementMayOverrideVerifierResult",
        "agreementMayMutateExpectedArtifacts",
        "agreementMayMutatePolicyBoundary",
        "proposalsMayCarrySideEffects",
        "broadcastAllowed",
    ]:
        if invariant[field] is not False:
            raise ValueError(f"NegotiationRecordV1 negotiationInvariant must keep {field} false")
    if invariant["creatorAndVerifierMustBeDistinct"] is not True:
        raise ValueError("NegotiationRecordV1 negotiationInvariant must keep creatorAndVerifierMustBeDistinct true")

    policy = record["policyBoundary"]
    _require_fields(
        "NegotiationRecordV1 policyBoundary",
        policy,
        [
            "policySchemaVersion",
            "externalSideEffectsAllowed",
            "workspaceMutationAllowed",
            "deliverySendAllowed",
            "realMultiAgentRuntimeAllowed",
            "providerExecutionAllowed",
            "broadcastAllowed",
        ],
    )
    if policy["policySchemaVersion"] != "policy-v1":
        raise ValueError("NegotiationRecordV1 policyBoundary must use policy-v1")
    for field in [
        "externalSideEffectsAllowed",
        "workspaceMutationAllowed",
        "deliverySendAllowed",
        "realMultiAgentRuntimeAllowed",
        "providerExecutionAllowed",
        "broadcastAllowed",
    ]:
        if policy[field] is not False:
            raise ValueError(f"NegotiationRecordV1 policyBoundary must keep {field} false")

    expected_event_refs = [
        _coord_event_ref(event["id"])
        for event in delegation_manifest["coordinationEvents"]
    ]
    if record["coordinationEventRefs"] != expected_event_refs:
        raise ValueError("NegotiationRecordV1 coordinationEventRefs must bind DelegationManifestV1 coordination events")

    message_refs = record["messageRefs"]
    _require_fields(
        "NegotiationRecordV1 messageRefs",
        message_refs,
        ["verificationRequest", "verificationResponse"],
    )
    if message_refs["verificationRequest"] != verification_request_ref:
        raise ValueError("NegotiationRecordV1 messageRefs.verificationRequest must bind AgentMessageManifestV1 verification.request")
    if message_refs["verificationResponse"] != verification_response_ref:
        raise ValueError("NegotiationRecordV1 messageRefs.verificationResponse must bind AgentMessageManifestV1 verification.response")

    expected_artifact_refs = {
        "ArtifactV1": paths_by_kind["ArtifactV1"],
        "EvidenceListV1": paths_by_kind["EvidenceListV1"],
        "VerifierResultV1": paths_by_kind["VerifierResultV1"],
    }
    if record["expectedDelegationArtifactRefs"] != expected_artifact_refs:
        raise ValueError("NegotiationRecordV1 expectedDelegationArtifactRefs must bind DelegationManifestV1 artifact paths")

    if not set(NON_REGRESSION_REUSE_PATHS).issubset(set(record["nonRegressionReusePath"])):
        raise ValueError("NegotiationRecordV1 must include non-regression workload reuse paths")


def _negotiation_record_ref() -> str:
    return f"{NEGOTIATION_RECORD_ARTIFACT_PATH}#id/{NEGOTIATION_RECORD_ID}"


def _negotiation_proposal_ref(proposal_id: str) -> str:
    return f"{NEGOTIATION_RECORD_ARTIFACT_PATH}#proposals/{proposal_id}"


def _negotiation_agreement_ref(agreement_id: str) -> str:
    return f"{NEGOTIATION_RECORD_ARTIFACT_PATH}#agreement/{agreement_id}"


def _build_broadcast_source_artifacts(root: Path) -> list[dict[str, Any]]:
    return [
        _artifact_source("delegation_manifest", DELEGATION_MANIFEST_ARTIFACT_PATH, root),
        _artifact_source("creator_verifier_pairing", CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH, root),
        _artifact_source("agent_message_manifest", AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH, root),
        _artifact_source("negotiation_record", NEGOTIATION_RECORD_ARTIFACT_PATH, root),
    ]


def _expected_broadcast_source_paths() -> dict[str, str]:
    return {
        "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
        "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
        "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
        "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    }


def _build_broadcast_subscriber_bindings(delegation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "agentId": "planner_agent",
            "role": "planner",
            "owns": ["delegation_lifecycle_observation", "negotiation_lifecycle_observation"],
            "mayPublish": False,
            "mayAcknowledgeWithSideEffects": False,
            "mayOverrideVerifierResult": False,
            "mayBroadcastDownstream": False,
            "mayMutateDelegationArtifacts": False,
        },
        {
            "agentId": delegation["verifierAgent"],
            "role": "verifier",
            "owns": ["delegation_lifecycle_observation"],
            "mayPublish": False,
            "mayAcknowledgeWithSideEffects": False,
            "mayOverrideVerifierResult": False,
            "mayBroadcastDownstream": False,
            "mayMutateDelegationArtifacts": False,
        },
        {
            "agentId": BROADCAST_OBSERVER_AGENT_ID,
            "role": "auditor",
            "owns": ["read_only_audit_observation"],
            "mayPublish": False,
            "mayAcknowledgeWithSideEffects": False,
            "mayOverrideVerifierResult": False,
            "mayBroadcastDownstream": False,
            "mayMutateDelegationArtifacts": False,
        },
    ]


def _delegation_topic_subscriber_ids() -> list[str]:
    return ["planner_agent", "verifier_agent", BROADCAST_OBSERVER_AGENT_ID]


def _negotiation_topic_subscriber_ids() -> list[str]:
    return ["planner_agent", BROADCAST_OBSERVER_AGENT_ID]


def _build_broadcast_topics() -> list[dict[str, Any]]:
    return [
        {
            "schemaVersion": BROADCAST_TOPIC_SCHEMA_VERSION,
            "topicId": BROADCAST_TOPIC_DELEGATION_LIFECYCLE,
            "kind": "coordination_event_fan_out",
            "allowedEventTypes": list(BROADCAST_DELEGATION_LIFECYCLE_EVENT_TYPES),
            "subscriberAllowList": _delegation_topic_subscriber_ids(),
            "publicAccessAllowed": False,
            "fanOutMayCarrySideEffects": False,
            "fanOutMayOverrideVerifierResult": False,
            "subscribersMayBroadcastDownstream": False,
            "deliveryMode": "read_only_fan_out",
            "ordering": "causal",
        },
        {
            "schemaVersion": BROADCAST_TOPIC_SCHEMA_VERSION,
            "topicId": BROADCAST_TOPIC_NEGOTIATION_LIFECYCLE,
            "kind": "negotiation_event_fan_out",
            "allowedEventTypes": list(BROADCAST_NEGOTIATION_LIFECYCLE_EVENT_TYPES),
            "subscriberAllowList": _negotiation_topic_subscriber_ids(),
            "publicAccessAllowed": False,
            "fanOutMayCarrySideEffects": False,
            "fanOutMayOverrideVerifierResult": False,
            "subscribersMayBroadcastDownstream": False,
            "deliveryMode": "read_only_fan_out",
            "ordering": "causal",
        },
    ]


def _build_broadcast_subscriptions() -> list[dict[str, Any]]:
    subscriptions: list[dict[str, Any]] = []
    for subscriber in _delegation_topic_subscriber_ids():
        subscriptions.append(
            {
                "schemaVersion": BROADCAST_SUBSCRIPTION_SCHEMA_VERSION,
                "id": f"subscription-{subscriber.replace('_', '-')}-delegation-lifecycle",
                "subscriberAgent": subscriber,
                "topicId": BROADCAST_TOPIC_DELEGATION_LIFECYCLE,
                "deliveryMode": "read_only_fan_out",
                "ordering": "causal",
                "mayPublish": False,
                "mayAcknowledgeWithSideEffects": False,
                "mayOverrideVerifierResult": False,
                "mayBroadcastDownstream": False,
            }
        )
    for subscriber in _negotiation_topic_subscriber_ids():
        subscriptions.append(
            {
                "schemaVersion": BROADCAST_SUBSCRIPTION_SCHEMA_VERSION,
                "id": f"subscription-{subscriber.replace('_', '-')}-negotiation-lifecycle",
                "subscriberAgent": subscriber,
                "topicId": BROADCAST_TOPIC_NEGOTIATION_LIFECYCLE,
                "deliveryMode": "read_only_fan_out",
                "ordering": "causal",
                "mayPublish": False,
                "mayAcknowledgeWithSideEffects": False,
                "mayOverrideVerifierResult": False,
                "mayBroadcastDownstream": False,
            }
        )
    return subscriptions


def _build_broadcast_fan_out_events(
    delegation_manifest: dict[str, Any],
    negotiation_record: dict[str, Any],
) -> list[dict[str, Any]]:
    fan_outs: list[dict[str, Any]] = []
    delegation_events = delegation_manifest["coordinationEvents"]
    previous_event_id: str | None = None
    for event in delegation_events:
        event_id = event["id"]
        causal_refs = [_coord_event_ref(event_id)]
        if previous_event_id is not None:
            causal_refs.append(_broadcast_fan_out_id_for_coord_event(previous_event_id))
        fan_outs.append(
            {
                "schemaVersion": BROADCAST_FAN_OUT_SCHEMA_VERSION,
                "id": _broadcast_fan_out_id_for_coord_event(event_id),
                "topicId": BROADCAST_TOPIC_DELEGATION_LIFECYCLE,
                "eventType": event["type"],
                "eventRef": _coord_event_ref(event_id),
                "subscriberAgentIds": _delegation_topic_subscriber_ids(),
                "causalRefs": causal_refs,
                "carriesSideEffects": False,
                "mayOverrideVerifierResult": False,
                "broadcastTopicMatches": True,
                "broadcastAllowedByTopic": True,
            }
        )
        previous_event_id = event_id

    proposals = negotiation_record["proposals"]
    agreement = negotiation_record["agreement"]
    previous_negotiation_fan_out_id: str | None = None
    for proposal in proposals:
        proposal_type = proposal["proposalType"]
        if proposal_type not in BROADCAST_NEGOTIATION_PROPOSAL_TYPE_TO_EVENT:
            continue
        proposal_id = proposal["id"]
        event_type = BROADCAST_NEGOTIATION_PROPOSAL_TYPE_TO_EVENT[proposal_type]
        fan_out_id = _broadcast_fan_out_id_for_proposal(proposal_id)
        causal_refs = [_negotiation_proposal_ref(proposal_id)]
        if previous_negotiation_fan_out_id is not None:
            causal_refs.append(previous_negotiation_fan_out_id)
        else:
            causal_refs.append(_broadcast_fan_out_id_for_coord_event(delegation_events[-1]["id"]))
        fan_outs.append(
            {
                "schemaVersion": BROADCAST_FAN_OUT_SCHEMA_VERSION,
                "id": fan_out_id,
                "topicId": BROADCAST_TOPIC_NEGOTIATION_LIFECYCLE,
                "eventType": event_type,
                "eventRef": _negotiation_proposal_ref(proposal_id),
                "subscriberAgentIds": _negotiation_topic_subscriber_ids(),
                "causalRefs": causal_refs,
                "carriesSideEffects": False,
                "mayOverrideVerifierResult": False,
                "broadcastTopicMatches": True,
                "broadcastAllowedByTopic": True,
            }
        )
        previous_negotiation_fan_out_id = fan_out_id
    return fan_outs


def _broadcast_fan_out_id_for_coord_event(event_id: str) -> str:
    return f"broadcast-fan-out-{event_id}"


def _broadcast_fan_out_id_for_proposal(proposal_id: str) -> str:
    return f"broadcast-fan-out-{proposal_id}"


def build_broadcast_subscription_manifest(root: Path) -> dict[str, Any]:
    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(pairing, root)
    agent_message_manifest = _load_json(root / AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH)
    validate_agent_message_manifest(agent_message_manifest, root)
    negotiation_record = _load_json(root / NEGOTIATION_RECORD_ARTIFACT_PATH)
    validate_negotiation_record(negotiation_record, root)
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])
    pairing_ref = _pairing_ref()

    return {
        "schemaVersion": BROADCAST_SUBSCRIPTION_MANIFEST_SCHEMA_VERSION,
        "id": BROADCAST_SUBSCRIPTION_MANIFEST_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "agent_coordination_broadcast_contract",
        "mode": "static_contract_only",
        "kernelPrimitive": "BroadcastSubscription",
        "coordinationProtocols": [
            "broadcast",
            "negotiation",
            "direct_communication",
            "creator_verifier",
            "delegation",
        ],
        "sourceArtifacts": _build_broadcast_source_artifacts(root),
        "delegationBinding": {
            "delegationManifestRef": DELEGATION_MANIFEST_ARTIFACT_PATH,
            "delegationRef": delegation_ref,
            "pairingManifestRef": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
            "pairingRef": pairing_ref,
            "agentMessageManifestRef": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
            "agentMessageManifestId": _agent_message_manifest_ref(),
            "negotiationRecordRef": NEGOTIATION_RECORD_ARTIFACT_PATH,
            "negotiationRecordId": _negotiation_record_ref(),
            "parentTaskSpecRef": delegation["parentTaskSpecRef"],
            "parentRunRef": delegation["parentRunRef"],
            "workloadIndependentObjective": delegation["workloadIndependentObjective"],
        },
        "subscriberBindings": _build_broadcast_subscriber_bindings(delegation),
        "topics": _build_broadcast_topics(),
        "subscriptions": _build_broadcast_subscriptions(),
        "fanOutEvents": _build_broadcast_fan_out_events(delegation_manifest, negotiation_record),
        "broadcastInvariant": {
            "verifierResultOwner": "verifier-runtime-v1",
            "publishersMustBeAuthorized": True,
            "subscribersMustBeOnAllowList": True,
            "fanOutMustReferenceDeclaredEvent": True,
            "fanOutMayCarrySideEffects": False,
            "fanOutMayOverrideVerifierResult": False,
            "subscribersMayBroadcastDownstream": False,
            "publicAccessAllowed": False,
            "creatorAndVerifierMustBeDistinct": True,
        },
        "policyBoundary": {
            "policySchemaVersion": "policy-v1",
            "externalSideEffectsAllowed": False,
            "workspaceMutationAllowed": False,
            "deliverySendAllowed": False,
            "realMultiAgentRuntimeAllowed": False,
            "providerExecutionAllowed": False,
            "publicAccessAllowed": False,
            "broadcastAllowed": True,
        },
        "coordinationEventRefs": [
            _coord_event_ref(event["id"])
            for event in delegation_manifest["coordinationEvents"]
        ],
        "messageRefs": {
            "verificationRequest": _agent_message_ref(AGENT_MESSAGE_REQUEST_ID),
            "verificationResponse": _agent_message_ref(AGENT_MESSAGE_RESPONSE_ID),
        },
        "negotiationBinding": {
            "negotiationRecordRef": NEGOTIATION_RECORD_ARTIFACT_PATH,
            "negotiationRecordId": _negotiation_record_ref(),
            "negotiationAgreementRef": _negotiation_agreement_ref(negotiation_record["agreement"]["id"]),
            "negotiationProposalRefs": [
                _negotiation_proposal_ref(proposal["id"])
                for proposal in negotiation_record["proposals"]
            ],
        },
        "expectedDelegationArtifactRefs": {
            "ArtifactV1": paths_by_kind["ArtifactV1"],
            "EvidenceListV1": paths_by_kind["EvidenceListV1"],
            "VerifierResultV1": paths_by_kind["VerifierResultV1"],
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATHS),
        "invariants": [
            "BroadcastSubscriptionManifestV1 is workload-independent: it fans out CoordinationEventV1 and NegotiationRecordV1 events to declared subscribers without adding regression/email behavior.",
            "Subscriber agents must be on the topic allow-list; broadcast must not reach unauthorized agents or public consumers.",
            "Fan-out events must reference declared coordination events or negotiation proposals/agreements and must not carry side effects.",
            "Subscribers must not publish, acknowledge with side effects, override verifier results, or broadcast downstream.",
            "The manifest is a static contract artifact and does not run a real event bus, broker, blackboard, queue, or external delivery channel.",
        ],
    }


def _validate_broadcast_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("BroadcastSubscriptionManifestV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_broadcast_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("BroadcastSubscriptionManifestV1 sourceArtifacts must be objects")
        _require_fields("BroadcastSubscriptionManifestV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected BroadcastSubscriptionManifestV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"BroadcastSubscriptionManifestV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"BroadcastSubscriptionManifestV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"BroadcastSubscriptionManifestV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"BroadcastSubscriptionManifestV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def _validate_broadcast_subscriber_bindings(
    subscriber_bindings: list[Any],
    delegation: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if not isinstance(subscriber_bindings, list) or len(subscriber_bindings) != len(BROADCAST_SUBSCRIBER_AGENT_IDS):
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 subscriberBindings must cover {BROADCAST_SUBSCRIBER_AGENT_IDS}"
        )
    bindings_by_agent: dict[str, dict[str, Any]] = {}
    for binding in subscriber_bindings:
        if not isinstance(binding, dict):
            raise ValueError("BroadcastSubscriptionManifestV1 subscriberBindings must be objects")
        _require_fields(
            "BroadcastSubscriptionManifestV1 subscriber binding",
            binding,
            [
                "agentId",
                "role",
                "owns",
                "mayPublish",
                "mayAcknowledgeWithSideEffects",
                "mayOverrideVerifierResult",
                "mayBroadcastDownstream",
                "mayMutateDelegationArtifacts",
            ],
        )
        if binding["role"] not in BROADCAST_SUBSCRIBER_ROLES:
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 subscriber role must be one of {BROADCAST_SUBSCRIBER_ROLES}"
            )
        for field in (
            "mayPublish",
            "mayAcknowledgeWithSideEffects",
            "mayOverrideVerifierResult",
            "mayBroadcastDownstream",
            "mayMutateDelegationArtifacts",
        ):
            if binding[field] is not False:
                raise ValueError(
                    f"BroadcastSubscriptionManifestV1 subscriber binding must keep {field} false"
                )
        bindings_by_agent[binding["agentId"]] = binding
    if set(bindings_by_agent) != set(BROADCAST_SUBSCRIBER_AGENT_IDS):
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 subscriberBindings must cover agents {BROADCAST_SUBSCRIBER_AGENT_IDS}"
        )
    if delegation["verifierAgent"] not in bindings_by_agent:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 subscriberBindings must include DelegationManifestV1 verifier"
        )
    if "planner_agent" not in bindings_by_agent:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 subscriberBindings must include planner_agent"
        )
    if BROADCAST_OBSERVER_AGENT_ID not in bindings_by_agent:
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 subscriberBindings must include observer agent {BROADCAST_OBSERVER_AGENT_ID}"
        )
    return bindings_by_agent


def _validate_broadcast_topic(topic: dict[str, Any]) -> None:
    _require_fields(
        "BroadcastSubscriptionManifestV1 topic",
        topic,
        [
            "schemaVersion",
            "topicId",
            "kind",
            "allowedEventTypes",
            "subscriberAllowList",
            "publicAccessAllowed",
            "fanOutMayCarrySideEffects",
            "fanOutMayOverrideVerifierResult",
            "subscribersMayBroadcastDownstream",
            "deliveryMode",
            "ordering",
        ],
    )
    if topic["schemaVersion"] != BROADCAST_TOPIC_SCHEMA_VERSION:
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 topic schemaVersion must be {BROADCAST_TOPIC_SCHEMA_VERSION}"
        )
    if topic["topicId"] not in BROADCAST_TOPIC_IDS:
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 topic topicId must be one of {BROADCAST_TOPIC_IDS}"
        )
    if topic["deliveryMode"] != "read_only_fan_out":
        raise ValueError("BroadcastSubscriptionManifestV1 topic deliveryMode must be read_only_fan_out")
    if topic["ordering"] != "causal":
        raise ValueError("BroadcastSubscriptionManifestV1 topic ordering must be causal")
    if topic["publicAccessAllowed"] is not False:
        raise ValueError("BroadcastSubscriptionManifestV1 topic must keep publicAccessAllowed false")
    if topic["fanOutMayCarrySideEffects"] is not False:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 topic must keep fanOutMayCarrySideEffects false"
        )
    if topic["fanOutMayOverrideVerifierResult"] is not False:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 topic must keep fanOutMayOverrideVerifierResult false"
        )
    if topic["subscribersMayBroadcastDownstream"] is not False:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 topic must keep subscribersMayBroadcastDownstream false"
        )
    expected_event_types: list[str]
    expected_subscribers: list[str]
    if topic["topicId"] == BROADCAST_TOPIC_DELEGATION_LIFECYCLE:
        expected_event_types = list(BROADCAST_DELEGATION_LIFECYCLE_EVENT_TYPES)
        expected_subscribers = _delegation_topic_subscriber_ids()
    else:
        expected_event_types = list(BROADCAST_NEGOTIATION_LIFECYCLE_EVENT_TYPES)
        expected_subscribers = _negotiation_topic_subscriber_ids()
    if list(topic["allowedEventTypes"]) != expected_event_types:
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 topic allowedEventTypes for {topic['topicId']} must equal {expected_event_types}"
        )
    if list(topic["subscriberAllowList"]) != expected_subscribers:
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 topic subscriberAllowList for {topic['topicId']} must equal {expected_subscribers}"
        )


def _validate_broadcast_topics(topics: list[Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(topics, list) or len(topics) != len(BROADCAST_TOPIC_IDS):
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 topics must declare exactly {len(BROADCAST_TOPIC_IDS)} topics"
        )
    topics_by_id: dict[str, dict[str, Any]] = {}
    for topic in topics:
        if not isinstance(topic, dict):
            raise ValueError("BroadcastSubscriptionManifestV1 topics must be objects")
        _validate_broadcast_topic(topic)
        topics_by_id[topic["topicId"]] = topic
    if set(topics_by_id) != set(BROADCAST_TOPIC_IDS):
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 topics must equal {BROADCAST_TOPIC_IDS}"
        )
    return topics_by_id


def _validate_broadcast_subscriptions(
    subscriptions: list[Any],
    topics_by_id: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(subscriptions, list) or not subscriptions:
        raise ValueError("BroadcastSubscriptionManifestV1 subscriptions must be a non-empty list")
    seen_ids: set[str] = set()
    expected_pairs: set[tuple[str, str]] = set()
    for topic_id, topic in topics_by_id.items():
        for subscriber in topic["subscriberAllowList"]:
            expected_pairs.add((subscriber, topic_id))
    actual_pairs: set[tuple[str, str]] = set()
    for subscription in subscriptions:
        if not isinstance(subscription, dict):
            raise ValueError("BroadcastSubscriptionManifestV1 subscriptions must be objects")
        _require_fields(
            "BroadcastSubscriptionManifestV1 subscription",
            subscription,
            [
                "schemaVersion",
                "id",
                "subscriberAgent",
                "topicId",
                "deliveryMode",
                "ordering",
                "mayPublish",
                "mayAcknowledgeWithSideEffects",
                "mayOverrideVerifierResult",
                "mayBroadcastDownstream",
            ],
        )
        if subscription["schemaVersion"] != BROADCAST_SUBSCRIPTION_SCHEMA_VERSION:
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 subscription schemaVersion must be {BROADCAST_SUBSCRIPTION_SCHEMA_VERSION}"
            )
        if subscription["id"] in seen_ids:
            raise ValueError("BroadcastSubscriptionManifestV1 subscription ids must be unique")
        seen_ids.add(subscription["id"])
        topic_id = subscription["topicId"]
        if topic_id not in topics_by_id:
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 subscription topicId {topic_id} must reference a declared topic"
            )
        topic = topics_by_id[topic_id]
        subscriber = subscription["subscriberAgent"]
        if subscriber not in topic["subscriberAllowList"]:
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 subscriber {subscriber} must be on topic {topic_id} allow-list"
            )
        if subscription["deliveryMode"] != "read_only_fan_out":
            raise ValueError(
                "BroadcastSubscriptionManifestV1 subscription deliveryMode must be read_only_fan_out"
            )
        if subscription["ordering"] != "causal":
            raise ValueError("BroadcastSubscriptionManifestV1 subscription ordering must be causal")
        for field in (
            "mayPublish",
            "mayAcknowledgeWithSideEffects",
            "mayOverrideVerifierResult",
            "mayBroadcastDownstream",
        ):
            if subscription[field] is not False:
                raise ValueError(
                    f"BroadcastSubscriptionManifestV1 subscription must keep {field} false"
                )
        actual_pairs.add((subscriber, topic_id))
    if actual_pairs != expected_pairs:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 subscriptions must cover every (subscriber, topic) pair from topic allow-lists"
        )


def _validate_broadcast_fan_out_events(
    fan_out_events: list[Any],
    topics_by_id: dict[str, dict[str, Any]],
    delegation_manifest: dict[str, Any],
    negotiation_record: dict[str, Any],
) -> None:
    if not isinstance(fan_out_events, list) or not fan_out_events:
        raise ValueError("BroadcastSubscriptionManifestV1 fanOutEvents must be a non-empty list")
    coord_events = delegation_manifest["coordinationEvents"]
    expected_delegation_event_refs = [_coord_event_ref(event["id"]) for event in coord_events]
    proposals = negotiation_record["proposals"]
    expected_negotiation_event_refs = [_negotiation_proposal_ref(proposal["id"]) for proposal in proposals]
    expected_event_refs = expected_delegation_event_refs + expected_negotiation_event_refs
    actual_event_refs = [event.get("eventRef") if isinstance(event, dict) else None for event in fan_out_events]
    if actual_event_refs != expected_event_refs:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 fanOutEvents must fan out every declared coordination event and negotiation proposal in causal order"
        )
    seen_ids: set[str] = set()
    previous_delegation_fan_out_id: str | None = None
    previous_negotiation_fan_out_id: str | None = None
    for index, fan_out in enumerate(fan_out_events):
        if not isinstance(fan_out, dict):
            raise ValueError("BroadcastSubscriptionManifestV1 fanOutEvents must be objects")
        _require_fields(
            "BroadcastSubscriptionManifestV1 fan-out",
            fan_out,
            [
                "schemaVersion",
                "id",
                "topicId",
                "eventType",
                "eventRef",
                "subscriberAgentIds",
                "causalRefs",
                "carriesSideEffects",
                "mayOverrideVerifierResult",
                "broadcastTopicMatches",
                "broadcastAllowedByTopic",
            ],
        )
        if fan_out["schemaVersion"] != BROADCAST_FAN_OUT_SCHEMA_VERSION:
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 fan-out schemaVersion must be {BROADCAST_FAN_OUT_SCHEMA_VERSION}"
            )
        if fan_out["id"] in seen_ids:
            raise ValueError("BroadcastSubscriptionManifestV1 fan-out ids must be unique")
        seen_ids.add(fan_out["id"])
        if fan_out["carriesSideEffects"] is not False:
            raise ValueError("BroadcastSubscriptionManifestV1 fan-out must not carry side effects")
        if fan_out["mayOverrideVerifierResult"] is not False:
            raise ValueError("BroadcastSubscriptionManifestV1 fan-out must not override verifier results")
        if fan_out["broadcastTopicMatches"] is not True:
            raise ValueError(
                "BroadcastSubscriptionManifestV1 fan-out broadcastTopicMatches must be true"
            )
        if fan_out["broadcastAllowedByTopic"] is not True:
            raise ValueError(
                "BroadcastSubscriptionManifestV1 fan-out broadcastAllowedByTopic must be true"
            )
        topic_id = fan_out["topicId"]
        if topic_id not in topics_by_id:
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 fan-out topicId {topic_id} must reference a declared topic"
            )
        topic = topics_by_id[topic_id]
        if fan_out["eventType"] not in topic["allowedEventTypes"]:
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 fan-out eventType {fan_out['eventType']} must be allowed by topic {topic_id}"
            )
        subscriber_ids = list(fan_out["subscriberAgentIds"])
        if subscriber_ids != list(topic["subscriberAllowList"]):
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 fan-out subscriberAgentIds must equal topic {topic_id} subscriberAllowList"
            )
        causal_refs = fan_out["causalRefs"]
        if not isinstance(causal_refs, list) or not causal_refs:
            raise ValueError("BroadcastSubscriptionManifestV1 fan-out causalRefs must be a non-empty list")
        event_ref = fan_out["eventRef"]
        if event_ref not in causal_refs:
            raise ValueError(
                "BroadcastSubscriptionManifestV1 fan-out causalRefs must include the broadcast eventRef"
            )
        if topic_id == BROADCAST_TOPIC_DELEGATION_LIFECYCLE:
            expected_event_type = coord_events[index]["type"]
            if fan_out["eventType"] != expected_event_type:
                raise ValueError(
                    f"BroadcastSubscriptionManifestV1 fan-out eventType for delegation lifecycle index {index} must equal {expected_event_type}"
                )
            if previous_delegation_fan_out_id is not None and previous_delegation_fan_out_id not in causal_refs:
                raise ValueError(
                    "BroadcastSubscriptionManifestV1 delegation lifecycle fan-out causalRefs must include the previous delegation fan-out id"
                )
            previous_delegation_fan_out_id = fan_out["id"]
        else:
            negotiation_index = index - len(coord_events)
            proposal = proposals[negotiation_index]
            expected_event_type = BROADCAST_NEGOTIATION_PROPOSAL_TYPE_TO_EVENT[proposal["proposalType"]]
            if fan_out["eventType"] != expected_event_type:
                raise ValueError(
                    f"BroadcastSubscriptionManifestV1 fan-out eventType for negotiation index {negotiation_index} must equal {expected_event_type}"
                )
            if previous_negotiation_fan_out_id is None:
                if previous_delegation_fan_out_id is not None and previous_delegation_fan_out_id not in causal_refs:
                    raise ValueError(
                        "BroadcastSubscriptionManifestV1 first negotiation fan-out causalRefs must reference the last delegation fan-out id"
                    )
            else:
                if previous_negotiation_fan_out_id not in causal_refs:
                    raise ValueError(
                        "BroadcastSubscriptionManifestV1 negotiation fan-out causalRefs must include the previous negotiation fan-out id"
                    )
            previous_negotiation_fan_out_id = fan_out["id"]


def validate_broadcast_subscription_manifest(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "BroadcastSubscriptionManifestV1",
        manifest,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "kernelPrimitive",
            "coordinationProtocols",
            "sourceArtifacts",
            "delegationBinding",
            "subscriberBindings",
            "topics",
            "subscriptions",
            "fanOutEvents",
            "broadcastInvariant",
            "policyBoundary",
            "coordinationEventRefs",
            "messageRefs",
            "negotiationBinding",
            "expectedDelegationArtifactRefs",
            "nonRegressionReusePath",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != BROADCAST_SUBSCRIPTION_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"BroadcastSubscriptionManifestV1 schemaVersion must be {BROADCAST_SUBSCRIPTION_MANIFEST_SCHEMA_VERSION}"
        )
    if manifest["id"] != BROADCAST_SUBSCRIPTION_MANIFEST_ID:
        raise ValueError(f"BroadcastSubscriptionManifestV1 id must be {BROADCAST_SUBSCRIPTION_MANIFEST_ID}")
    if manifest["phase"] != "post_mvp":
        raise ValueError("BroadcastSubscriptionManifestV1 phase must be post_mvp")
    if manifest["scope"] != "agent_coordination_broadcast_contract":
        raise ValueError("BroadcastSubscriptionManifestV1 scope must be agent_coordination_broadcast_contract")
    if manifest["mode"] != "static_contract_only":
        raise ValueError("BroadcastSubscriptionManifestV1 mode must be static_contract_only")
    if manifest["kernelPrimitive"] != "BroadcastSubscription":
        raise ValueError("BroadcastSubscriptionManifestV1 kernelPrimitive must be BroadcastSubscription")
    if "broadcast" not in manifest["coordinationProtocols"]:
        raise ValueError("BroadcastSubscriptionManifestV1 coordinationProtocols must include broadcast")

    delegation_manifest = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation_manifest, root)
    pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(pairing, root)
    agent_message_manifest = _load_json(root / AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH)
    validate_agent_message_manifest(agent_message_manifest, root)
    negotiation_record = _load_json(root / NEGOTIATION_RECORD_ARTIFACT_PATH)
    validate_negotiation_record(negotiation_record, root)
    delegation = delegation_manifest["delegations"][0]
    paths_by_kind = _artifact_paths_by_kind(delegation)
    delegation_ref = _delegation_ref(delegation["id"])
    pairing_ref = _pairing_ref()

    _validate_broadcast_source_artifacts(manifest["sourceArtifacts"], root)

    binding = manifest["delegationBinding"]
    _require_fields(
        "BroadcastSubscriptionManifestV1 delegationBinding",
        binding,
        [
            "delegationManifestRef",
            "delegationRef",
            "pairingManifestRef",
            "pairingRef",
            "agentMessageManifestRef",
            "agentMessageManifestId",
            "negotiationRecordRef",
            "negotiationRecordId",
            "parentTaskSpecRef",
            "parentRunRef",
            "workloadIndependentObjective",
        ],
    )
    if binding["delegationManifestRef"] != DELEGATION_MANIFEST_ARTIFACT_PATH or binding["delegationRef"] != delegation_ref:
        raise ValueError("BroadcastSubscriptionManifestV1 delegationBinding must reference DelegationManifestV1")
    if binding["pairingManifestRef"] != CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH or binding["pairingRef"] != pairing_ref:
        raise ValueError("BroadcastSubscriptionManifestV1 delegationBinding must reference CreatorVerifierPairingV1")
    if binding["agentMessageManifestRef"] != AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH:
        raise ValueError("BroadcastSubscriptionManifestV1 delegationBinding must reference AgentMessageManifestV1")
    if binding["agentMessageManifestId"] != _agent_message_manifest_ref():
        raise ValueError("BroadcastSubscriptionManifestV1 delegationBinding must bind AgentMessageManifestV1 id")
    if binding["negotiationRecordRef"] != NEGOTIATION_RECORD_ARTIFACT_PATH:
        raise ValueError("BroadcastSubscriptionManifestV1 delegationBinding must reference NegotiationRecordV1")
    if binding["negotiationRecordId"] != _negotiation_record_ref():
        raise ValueError("BroadcastSubscriptionManifestV1 delegationBinding must bind NegotiationRecordV1 id")
    if binding["parentTaskSpecRef"] != delegation["parentTaskSpecRef"] or binding["parentRunRef"] != delegation["parentRunRef"]:
        raise ValueError("BroadcastSubscriptionManifestV1 delegationBinding must inherit parent TaskSpec and Run refs")

    _validate_broadcast_subscriber_bindings(manifest["subscriberBindings"], delegation)
    topics_by_id = _validate_broadcast_topics(manifest["topics"])
    _validate_broadcast_subscriptions(manifest["subscriptions"], topics_by_id)
    _validate_broadcast_fan_out_events(
        manifest["fanOutEvents"],
        topics_by_id,
        delegation_manifest,
        negotiation_record,
    )

    invariant = manifest["broadcastInvariant"]
    _require_fields(
        "BroadcastSubscriptionManifestV1 broadcastInvariant",
        invariant,
        [
            "verifierResultOwner",
            "publishersMustBeAuthorized",
            "subscribersMustBeOnAllowList",
            "fanOutMustReferenceDeclaredEvent",
            "fanOutMayCarrySideEffects",
            "fanOutMayOverrideVerifierResult",
            "subscribersMayBroadcastDownstream",
            "publicAccessAllowed",
            "creatorAndVerifierMustBeDistinct",
        ],
    )
    if invariant["verifierResultOwner"] != "verifier-runtime-v1":
        raise ValueError(
            "BroadcastSubscriptionManifestV1 broadcastInvariant verifierResultOwner must be verifier-runtime-v1"
        )
    if invariant["publishersMustBeAuthorized"] is not True:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 broadcastInvariant must require authorized publishers"
        )
    if invariant["subscribersMustBeOnAllowList"] is not True:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 broadcastInvariant must keep subscribersMustBeOnAllowList true"
        )
    if invariant["fanOutMustReferenceDeclaredEvent"] is not True:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 broadcastInvariant must keep fanOutMustReferenceDeclaredEvent true"
        )
    for field in (
        "fanOutMayCarrySideEffects",
        "fanOutMayOverrideVerifierResult",
        "subscribersMayBroadcastDownstream",
        "publicAccessAllowed",
    ):
        if invariant[field] is not False:
            raise ValueError(
                f"BroadcastSubscriptionManifestV1 broadcastInvariant must keep {field} false"
            )
    if invariant["creatorAndVerifierMustBeDistinct"] is not True:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 broadcastInvariant must keep creatorAndVerifierMustBeDistinct true"
        )

    policy = manifest["policyBoundary"]
    _require_fields(
        "BroadcastSubscriptionManifestV1 policyBoundary",
        policy,
        [
            "policySchemaVersion",
            "externalSideEffectsAllowed",
            "workspaceMutationAllowed",
            "deliverySendAllowed",
            "realMultiAgentRuntimeAllowed",
            "providerExecutionAllowed",
            "publicAccessAllowed",
            "broadcastAllowed",
        ],
    )
    if policy["policySchemaVersion"] != "policy-v1":
        raise ValueError("BroadcastSubscriptionManifestV1 policyBoundary must use policy-v1")
    for field in (
        "externalSideEffectsAllowed",
        "workspaceMutationAllowed",
        "deliverySendAllowed",
        "realMultiAgentRuntimeAllowed",
        "providerExecutionAllowed",
        "publicAccessAllowed",
    ):
        if policy[field] is not False:
            raise ValueError(f"BroadcastSubscriptionManifestV1 policyBoundary must keep {field} false")
    if policy["broadcastAllowed"] is not True:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 policyBoundary broadcastAllowed must be true within declared topic allow-lists"
        )

    expected_event_refs = [
        _coord_event_ref(event["id"])
        for event in delegation_manifest["coordinationEvents"]
    ]
    if list(manifest["coordinationEventRefs"]) != expected_event_refs:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 coordinationEventRefs must bind DelegationManifestV1 coordination events"
        )

    message_refs = manifest["messageRefs"]
    _require_fields(
        "BroadcastSubscriptionManifestV1 messageRefs",
        message_refs,
        ["verificationRequest", "verificationResponse"],
    )
    if message_refs["verificationRequest"] != _agent_message_ref(AGENT_MESSAGE_REQUEST_ID):
        raise ValueError(
            "BroadcastSubscriptionManifestV1 messageRefs.verificationRequest must bind AgentMessageManifestV1 verification.request"
        )
    if message_refs["verificationResponse"] != _agent_message_ref(AGENT_MESSAGE_RESPONSE_ID):
        raise ValueError(
            "BroadcastSubscriptionManifestV1 messageRefs.verificationResponse must bind AgentMessageManifestV1 verification.response"
        )

    negotiation_binding = manifest["negotiationBinding"]
    _require_fields(
        "BroadcastSubscriptionManifestV1 negotiationBinding",
        negotiation_binding,
        ["negotiationRecordRef", "negotiationRecordId", "negotiationAgreementRef", "negotiationProposalRefs"],
    )
    if negotiation_binding["negotiationRecordRef"] != NEGOTIATION_RECORD_ARTIFACT_PATH:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 negotiationBinding.negotiationRecordRef must bind NegotiationRecordV1"
        )
    if negotiation_binding["negotiationRecordId"] != _negotiation_record_ref():
        raise ValueError(
            "BroadcastSubscriptionManifestV1 negotiationBinding.negotiationRecordId must bind NegotiationRecordV1 id"
        )
    expected_agreement_ref = _negotiation_agreement_ref(negotiation_record["agreement"]["id"])
    if negotiation_binding["negotiationAgreementRef"] != expected_agreement_ref:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 negotiationBinding.negotiationAgreementRef must bind NegotiationRecordV1 agreement"
        )
    expected_proposal_refs = [
        _negotiation_proposal_ref(proposal["id"])
        for proposal in negotiation_record["proposals"]
    ]
    if list(negotiation_binding["negotiationProposalRefs"]) != expected_proposal_refs:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 negotiationBinding.negotiationProposalRefs must bind all NegotiationRecordV1 proposals"
        )

    expected_artifact_refs = {
        "ArtifactV1": paths_by_kind["ArtifactV1"],
        "EvidenceListV1": paths_by_kind["EvidenceListV1"],
        "VerifierResultV1": paths_by_kind["VerifierResultV1"],
    }
    if manifest["expectedDelegationArtifactRefs"] != expected_artifact_refs:
        raise ValueError(
            "BroadcastSubscriptionManifestV1 expectedDelegationArtifactRefs must bind DelegationManifestV1 artifact paths"
        )

    if not set(NON_REGRESSION_REUSE_PATHS).issubset(set(manifest["nonRegressionReusePath"])):
        raise ValueError(
            "BroadcastSubscriptionManifestV1 must include non-regression workload reuse paths"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="coordination-contract")
    parser.add_argument("--delegation-out", type=Path)
    parser.add_argument("--validate-delegation", type=Path)
    parser.add_argument("--pairing-out", type=Path)
    parser.add_argument("--validate-pairing", type=Path)
    parser.add_argument("--agent-message-out", type=Path)
    parser.add_argument("--validate-agent-message", type=Path)
    parser.add_argument("--negotiation-out", type=Path)
    parser.add_argument("--validate-negotiation", type=Path)
    parser.add_argument("--broadcast-subscription-out", type=Path)
    parser.add_argument("--validate-broadcast-subscription", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if (
        args.delegation_out is None
        and args.validate_delegation is None
        and args.pairing_out is None
        and args.validate_pairing is None
        and args.agent_message_out is None
        and args.validate_agent_message is None
        and args.negotiation_out is None
        and args.validate_negotiation is None
        and args.broadcast_subscription_out is None
        and args.validate_broadcast_subscription is None
    ):
        raise ValueError("No action requested")
    if args.delegation_out is not None:
        manifest = build_delegation_manifest(root)
        validate_delegation_manifest(manifest, root)
        _write_json(args.delegation_out, manifest)
        print(f"Wrote DelegationManifestV1 artifact to {args.delegation_out}.")
    if args.validate_delegation is not None:
        manifest = _load_json(args.validate_delegation)
        validate_delegation_manifest(manifest, root)
        print(f"Validated DelegationManifestV1 artifact {args.validate_delegation}.")
    if args.pairing_out is not None:
        pairing = build_creator_verifier_pairing(root)
        validate_creator_verifier_pairing(pairing, root)
        _write_json(args.pairing_out, pairing)
        print(f"Wrote CreatorVerifierPairingV1 artifact to {args.pairing_out}.")
    if args.validate_pairing is not None:
        pairing = _load_json(args.validate_pairing)
        validate_creator_verifier_pairing(pairing, root)
        print(f"Validated CreatorVerifierPairingV1 artifact {args.validate_pairing}.")
    if args.agent_message_out is not None:
        manifest = build_agent_message_manifest(root)
        validate_agent_message_manifest(manifest, root)
        _write_json(args.agent_message_out, manifest)
        print(f"Wrote AgentMessageManifestV1 artifact to {args.agent_message_out}.")
    if args.validate_agent_message is not None:
        manifest = _load_json(args.validate_agent_message)
        validate_agent_message_manifest(manifest, root)
        print(f"Validated AgentMessageManifestV1 artifact {args.validate_agent_message}.")
    if args.negotiation_out is not None:
        record = build_negotiation_record(root)
        validate_negotiation_record(record, root)
        _write_json(args.negotiation_out, record)
        print(f"Wrote NegotiationRecordV1 artifact to {args.negotiation_out}.")
    if args.validate_negotiation is not None:
        record = _load_json(args.validate_negotiation)
        validate_negotiation_record(record, root)
        print(f"Validated NegotiationRecordV1 artifact {args.validate_negotiation}.")
    if args.broadcast_subscription_out is not None:
        manifest = build_broadcast_subscription_manifest(root)
        validate_broadcast_subscription_manifest(manifest, root)
        _write_json(args.broadcast_subscription_out, manifest)
        print(f"Wrote BroadcastSubscriptionManifestV1 artifact to {args.broadcast_subscription_out}.")
    if args.validate_broadcast_subscription is not None:
        manifest = _load_json(args.validate_broadcast_subscription)
        validate_broadcast_subscription_manifest(manifest, root)
        print(f"Validated BroadcastSubscriptionManifestV1 artifact {args.validate_broadcast_subscription}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

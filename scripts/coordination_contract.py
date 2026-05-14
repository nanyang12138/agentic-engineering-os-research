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
TASK_SPEC_ENVELOPE_SCHEMA_VERSION = "task-spec-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"

DELEGATION_MANIFEST_ID = "post-mvp-delegation-manifest-kernel-contract"
DELEGATION_MANIFEST_ARTIFACT_PATH = "artifacts/coordination/post_mvp_delegation_manifest.json"
CREATOR_VERIFIER_PAIRING_ID = "post-mvp-creator-verifier-pairing-kernel-contract"
CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH = "artifacts/coordination/post_mvp_creator_verifier_pairing.json"

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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="coordination-contract")
    parser.add_argument("--delegation-out", type=Path)
    parser.add_argument("--validate-delegation", type=Path)
    parser.add_argument("--pairing-out", type=Path)
    parser.add_argument("--validate-pairing", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if (
        args.delegation_out is None
        and args.validate_delegation is None
        and args.pairing_out is None
        and args.validate_pairing is None
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

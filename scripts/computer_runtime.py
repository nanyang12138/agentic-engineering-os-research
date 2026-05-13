from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


COMPUTER_RUNTIME_CONTRACT_SCHEMA_VERSION = "computer-runtime-adapter-contract-v1"
COMPUTER_RUNTIME_CAPABILITY_SCHEMA_VERSION = "computer-runtime-capability-v1"
TRAJECTORY_OBSERVATION_SCHEMA_VERSION = "trajectory-observation-v1"
ADAPTER_POLICY_MANIFEST_SCHEMA_VERSION = "adapter-policy-manifest-v1"
ADAPTER_POLICY_DECISION_SCHEMA_VERSION = "adapter-policy-decision-v1"
OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION = "observation-redaction-policy-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"

CONTRACT_ID = "phase7-static-computer-runtime-contract"
OBSERVATION_ID = "phase7-static-trajectory-observation-all_passed"
POLICY_MANIFEST_ID = "phase7-computer-runtime-adapter-policy"
REDACTION_POLICY_ID = "phase7-observation-redaction-source-policy"
CONTRACT_ARTIFACT_PATH = "artifacts/computer_runtime/phase7_computer_runtime_contract.json"
OBSERVATION_ARTIFACT_PATH = "artifacts/computer_runtime/phase7_trajectory_observation.json"
POLICY_MANIFEST_ARTIFACT_PATH = "artifacts/computer_runtime/phase7_adapter_policy_manifest.json"
REDACTION_POLICY_ARTIFACT_PATH = "artifacts/computer_runtime/phase7_observation_redaction_policy.json"
PHASE3_CAPABILITY_CATALOG_PATH = "artifacts/capabilities/phase3_capability_catalog.json"
ADAPTER_REF = "computer-runtime://phase7/adapter/cua-placeholder"
CAPABILITY_URI_PREFIX = "computer-runtime://phase7/"

CAPABILITY_NAMES = [
    "computer.screenshot",
    "computer.click",
    "computer.type",
    "computer.run_shell",
    "sandbox.session",
    "trajectory.record",
]

READ_ONLY_CAPABILITIES = {"computer.screenshot", "trajectory.record"}
APPROVAL_REQUIRED_CAPABILITIES = {
    "computer.click",
    "computer.type",
    "computer.run_shell",
    "sandbox.session",
}

CAPABILITY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "computer.screenshot": {
        "category": "computer",
        "permission": "read",
        "sideEffectRisk": "screen_observation",
        "approvalRequired": False,
        "inputContract": {
            "schema": "ComputerScreenshotInputV1",
            "required": ["sessionRef"],
            "properties": {"sessionRef": "string:adapter-session-ref"},
        },
        "observationContract": {
            "schema": "ComputerScreenshotObservationV1",
            "produces": ["screenObservationRef"],
            "properties": {
                "screenObservationRef": "string:observation-ref",
                "redactionPolicy": "string",
            },
        },
    },
    "computer.click": {
        "category": "computer",
        "permission": "dangerous",
        "sideEffectRisk": "gui_state_mutation",
        "approvalRequired": True,
        "inputContract": {
            "schema": "ComputerClickInputV1",
            "required": ["sessionRef", "target"],
            "properties": {
                "sessionRef": "string:adapter-session-ref",
                "target": "object:coordinate-or-accessibility-ref",
            },
        },
        "observationContract": {
            "schema": "ComputerActionObservationV1",
            "produces": ["trajectoryEventRef"],
            "properties": {"trajectoryEventRef": "string:trajectory-event-ref"},
        },
    },
    "computer.type": {
        "category": "computer",
        "permission": "dangerous",
        "sideEffectRisk": "gui_state_mutation",
        "approvalRequired": True,
        "inputContract": {
            "schema": "ComputerTypeInputV1",
            "required": ["sessionRef", "text"],
            "properties": {
                "sessionRef": "string:adapter-session-ref",
                "text": "string:redacted-or-approved-input",
            },
        },
        "observationContract": {
            "schema": "ComputerActionObservationV1",
            "produces": ["trajectoryEventRef"],
            "properties": {"trajectoryEventRef": "string:trajectory-event-ref"},
        },
    },
    "computer.run_shell": {
        "category": "computer",
        "permission": "dangerous",
        "sideEffectRisk": "process_or_filesystem_mutation",
        "approvalRequired": True,
        "inputContract": {
            "schema": "ComputerRunShellInputV1",
            "required": ["sessionRef", "command", "workingDirectory"],
            "properties": {
                "sessionRef": "string:adapter-session-ref",
                "command": "string:approved-command",
                "workingDirectory": "string:path",
            },
        },
        "observationContract": {
            "schema": "ComputerShellObservationV1",
            "produces": ["stdoutRef", "stderrRef", "exitCode"],
            "properties": {
                "stdoutRef": "string:observation-ref",
                "stderrRef": "string:observation-ref",
                "exitCode": "integer",
            },
        },
    },
    "sandbox.session": {
        "category": "sandbox",
        "permission": "dangerous",
        "sideEffectRisk": "isolated_environment_lifecycle",
        "approvalRequired": True,
        "inputContract": {
            "schema": "SandboxSessionInputV1",
            "required": ["imageRef", "networkPolicy", "mountPolicy"],
            "properties": {
                "imageRef": "string:image-ref",
                "networkPolicy": "enum:disabled|restricted|approved",
                "mountPolicy": "enum:readonly|approved-write",
            },
        },
        "observationContract": {
            "schema": "SandboxSessionObservationV1",
            "produces": ["sessionRef", "trajectoryRootRef"],
            "properties": {
                "sessionRef": "string:adapter-session-ref",
                "trajectoryRootRef": "string:trajectory-ref",
            },
        },
    },
    "trajectory.record": {
        "category": "trajectory",
        "permission": "read",
        "sideEffectRisk": "observation_capture_only",
        "approvalRequired": False,
        "inputContract": {
            "schema": "TrajectoryRecordInputV1",
            "required": ["eventRef", "observationRef"],
            "properties": {
                "eventRef": "string:run-event-ref",
                "observationRef": "string:observation-ref",
            },
        },
        "observationContract": {
            "schema": "TrajectoryObservationV1",
            "produces": ["trajectoryObservation"],
            "properties": {"trajectoryObservation": TRAJECTORY_OBSERVATION_SCHEMA_VERSION},
        },
    },
}


def computer_capability_ref(name: str) -> str:
    return f"{CAPABILITY_URI_PREFIX}{name}"


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError(f"{path} must contain JSON object lines")
        events.append(event)
    return events


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_fields(label: str, payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing}")


def _validate_relative_posix_path(path: str) -> None:
    if Path(path).is_absolute() or "\\" in path or path.startswith("../") or "/../" in path:
        raise ValueError(f"ComputerRuntime paths must be POSIX relative repository paths: {path}")


def _capability_catalog_refs(catalog: dict[str, Any]) -> list[str]:
    _require_fields("CapabilityCatalogV1", catalog, ["schemaVersion", "id", "capabilityEnvelope"])
    envelope = catalog["capabilityEnvelope"]
    if not isinstance(envelope, dict):
        raise ValueError("CapabilityCatalogV1 capabilityEnvelope must be an object")
    items = envelope.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("CapabilityCatalogV1 capabilityEnvelope.items must be a non-empty list")
    refs = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("CapabilityCatalogV1 capabilityEnvelope.items must be objects")
        _require_fields("CapabilityCatalogV1 capability", item, ["name", "ref"])
        refs.append(item["ref"])
    return refs


def build_computer_runtime_contract() -> dict[str, Any]:
    capabilities = []
    for name in CAPABILITY_NAMES:
        definition = deepcopy(CAPABILITY_DEFINITIONS[name])
        definition.update(
            {
                "schemaVersion": COMPUTER_RUNTIME_CAPABILITY_SCHEMA_VERSION,
                "name": name,
                "ref": computer_capability_ref(name),
                "executionMode": "contract_only",
                "implemented": False,
                "externalSideEffectAllowed": False,
            }
        )
        capabilities.append(definition)

    return {
        "schemaVersion": COMPUTER_RUNTIME_CONTRACT_SCHEMA_VERSION,
        "id": CONTRACT_ID,
        "phase": "phase7",
        "scope": "computer_runtime_adapter_boundary",
        "mode": "static_contract_only",
        "adapterRef": ADAPTER_REF,
        "buildVsIntegrate": {
            "build": [
                "ComputerRuntimeAdapterV1 contract",
                "TrajectoryObservationV1 artifact contract",
                "machine validation for adapter-only/no-side-effect invariants",
            ],
            "integrateLater": [
                "trycua/cua provider",
                "desktop or browser automation",
                "sandbox lifecycle execution",
                "trajectory replay",
            ],
        },
        "adapterBoundary": {
            "layer": "Computer Runtime / Sandbox / GUI Automation / Trajectory Layer",
            "adapterResponsibilities": [
                "expose low-level computer and sandbox actions behind capability contracts",
                "emit observations and trajectory events with stable refs",
                "avoid judging whether an engineering task is complete",
            ],
            "osResponsibilities": [
                "own TaskSpec, Policy, RunControl, Evidence, Verifier, Artifact, and Delivery semantics",
                "decide whether observations satisfy task success criteria",
                "approve dangerous actions before any real provider executes them",
            ],
            "mvpInvariant": "Phase 7 MVP declares adapter boundaries only; it does not execute GUI, browser, desktop, sandbox, shell, or CUA actions.",
        },
        "capabilities": capabilities,
        "trajectoryContract": {
            "schemaVersion": TRAJECTORY_OBSERVATION_SCHEMA_VERSION,
            "allowedObservationKinds": ["trajectory_event"],
            "requiredBindings": ["runId", "eventRef", "evidenceId", "capabilityRef"],
            "taskVerdictOwner": "verifier-runtime-v1",
        },
        "observationPolicy": {
            "schemaVersion": OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION,
            "policyRef": REDACTION_POLICY_ARTIFACT_PATH,
            "rawScreenPixelsAllowed": False,
            "sensitiveValueCaptureAllowed": False,
            "sourceBindingRequired": True,
        },
        "policy": {
            "externalSideEffectsAllowed": False,
            "realProviderExecutionAllowed": False,
            "dangerousCapabilitiesRequireApproval": True,
        },
    }


def validate_computer_runtime_contract(contract: dict[str, Any]) -> None:
    _require_fields(
        "ComputerRuntimeAdapterV1 contract",
        contract,
        [
            "schemaVersion",
            "id",
            "phase",
            "scope",
            "mode",
            "adapterRef",
            "buildVsIntegrate",
            "adapterBoundary",
            "capabilities",
            "trajectoryContract",
            "observationPolicy",
            "policy",
        ],
    )
    if contract["schemaVersion"] != COMPUTER_RUNTIME_CONTRACT_SCHEMA_VERSION:
        raise ValueError(f"ComputerRuntimeAdapterV1 schemaVersion must be {COMPUTER_RUNTIME_CONTRACT_SCHEMA_VERSION}")
    if contract["id"] != CONTRACT_ID:
        raise ValueError(f"ComputerRuntimeAdapterV1 id must be {CONTRACT_ID}")
    if contract["phase"] != "phase7":
        raise ValueError("ComputerRuntimeAdapterV1 phase must be phase7")
    if contract["mode"] != "static_contract_only":
        raise ValueError("ComputerRuntimeAdapterV1 mode must be static_contract_only")
    if contract["adapterRef"] != ADAPTER_REF:
        raise ValueError(f"ComputerRuntimeAdapterV1 adapterRef must be {ADAPTER_REF}")

    policy = contract["policy"]
    if policy.get("externalSideEffectsAllowed") is not False:
        raise ValueError("ComputerRuntimeAdapterV1 policy must disallow external side effects")
    if policy.get("realProviderExecutionAllowed") is not False:
        raise ValueError("ComputerRuntimeAdapterV1 policy must disallow real provider execution")
    if policy.get("dangerousCapabilitiesRequireApproval") is not True:
        raise ValueError("ComputerRuntimeAdapterV1 policy must require approval for dangerous capabilities")

    trajectory_contract = contract["trajectoryContract"]
    if trajectory_contract.get("schemaVersion") != TRAJECTORY_OBSERVATION_SCHEMA_VERSION:
        raise ValueError(f"trajectoryContract schemaVersion must be {TRAJECTORY_OBSERVATION_SCHEMA_VERSION}")
    if trajectory_contract.get("taskVerdictOwner") != "verifier-runtime-v1":
        raise ValueError("trajectoryContract taskVerdictOwner must remain verifier-runtime-v1")

    observation_policy = contract["observationPolicy"]
    _require_fields(
        "ComputerRuntimeAdapterV1 observationPolicy",
        observation_policy,
        [
            "schemaVersion",
            "policyRef",
            "rawScreenPixelsAllowed",
            "sensitiveValueCaptureAllowed",
            "sourceBindingRequired",
        ],
    )
    if observation_policy["schemaVersion"] != OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION:
        raise ValueError(f"observationPolicy schemaVersion must be {OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION}")
    if observation_policy["policyRef"] != REDACTION_POLICY_ARTIFACT_PATH:
        raise ValueError(f"observationPolicy policyRef must be {REDACTION_POLICY_ARTIFACT_PATH}")
    if observation_policy["rawScreenPixelsAllowed"] is not False:
        raise ValueError("observationPolicy must disallow raw screen pixels")
    if observation_policy["sensitiveValueCaptureAllowed"] is not False:
        raise ValueError("observationPolicy must disallow sensitive value capture")
    if observation_policy["sourceBindingRequired"] is not True:
        raise ValueError("observationPolicy must require source binding")

    capabilities = contract["capabilities"]
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("ComputerRuntimeAdapterV1 capabilities must be a non-empty list")
    names = [item.get("name") for item in capabilities if isinstance(item, dict)]
    if names != CAPABILITY_NAMES:
        raise ValueError(f"ComputerRuntimeAdapterV1 capability names must equal {CAPABILITY_NAMES}")

    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("ComputerRuntimeAdapterV1 capabilities must be objects")
        _require_fields(
            f"computer runtime capability {capability.get('name')}",
            capability,
            [
                "schemaVersion",
                "name",
                "ref",
                "category",
                "permission",
                "sideEffectRisk",
                "approvalRequired",
                "inputContract",
                "observationContract",
                "executionMode",
                "implemented",
                "externalSideEffectAllowed",
            ],
        )
        name = capability["name"]
        if capability["schemaVersion"] != COMPUTER_RUNTIME_CAPABILITY_SCHEMA_VERSION:
            raise ValueError(f"Computer runtime capability {name} schemaVersion must be {COMPUTER_RUNTIME_CAPABILITY_SCHEMA_VERSION}")
        if capability["ref"] != computer_capability_ref(name):
            raise ValueError(f"Computer runtime capability {name} ref must be {computer_capability_ref(name)}")
        if capability["permission"] not in {"read", "dangerous"}:
            raise ValueError(f"Computer runtime capability {name} permission must be read or dangerous")
        if name in READ_ONLY_CAPABILITIES and capability["permission"] != "read":
            raise ValueError(f"Computer runtime capability {name} must be read permission")
        if name in APPROVAL_REQUIRED_CAPABILITIES and capability["permission"] != "dangerous":
            raise ValueError(f"Computer runtime capability {name} must be dangerous permission")
        if name in APPROVAL_REQUIRED_CAPABILITIES and capability["approvalRequired"] is not True:
            raise ValueError(f"Computer runtime capability {name} must require approval")
        if capability["executionMode"] != "contract_only":
            raise ValueError(f"Computer runtime capability {name} executionMode must be contract_only")
        if capability["implemented"] is not False:
            raise ValueError(f"Computer runtime capability {name} must remain contract-only")
        if capability["externalSideEffectAllowed"] is not False:
            raise ValueError(f"Computer runtime capability {name} must not allow external side effects")
        for contract_field in ["inputContract", "observationContract"]:
            nested = capability[contract_field]
            if not isinstance(nested, dict) or "schema" not in nested or "required" not in nested and contract_field == "inputContract":
                raise ValueError(f"Computer runtime capability {name} has invalid {contract_field}")


def _artifact_source(role: str, path: Path, root: Path) -> dict[str, Any]:
    relative_path = path.resolve().relative_to(root.resolve()).as_posix()
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def build_trajectory_observation(run_path: Path, evidence_path: Path, events_path: Path, root: Path) -> dict[str, Any]:
    run = _load_json(run_path)
    evidence = _load_json(evidence_path)
    events = _load_events(events_path)
    evidence_items = evidence.get("items")
    if not isinstance(evidence_items, list) or not evidence_items:
        raise ValueError("TrajectoryObservationV1 requires at least one evidence item")
    first_evidence = evidence_items[0]
    extract_event = next(
        (event for event in events if event.get("type") == "capability.extract_regression_result.completed"),
        None,
    )
    if extract_event is None:
        raise ValueError("TrajectoryObservationV1 requires an extract_regression_result event")

    return {
        "schemaVersion": TRAJECTORY_OBSERVATION_SCHEMA_VERSION,
        "id": OBSERVATION_ID,
        "contractRef": CONTRACT_ARTIFACT_PATH,
        "redactionPolicyRef": REDACTION_POLICY_ARTIFACT_PATH,
        "adapterRef": ADAPTER_REF,
        "provider": "static_fixture",
        "mode": "static_fixture_only",
        "externalSideEffect": False,
        "generatedAt": GENERATED_AT,
        "fixtureId": run["fixtureId"],
        "runId": run["id"],
        "sourceArtifacts": [
            _artifact_source("run", run_path, root),
            _artifact_source("evidence_list", evidence_path, root),
            _artifact_source("events", events_path, root),
        ],
        "observations": [
            {
                "id": "trajectory-observation-001",
                "kind": "trajectory_event",
                "capability": "trajectory.record",
                "capabilityRef": computer_capability_ref("trajectory.record"),
                "eventRef": extract_event["id"],
                "evidenceId": first_evidence["id"],
                "sourceRef": f"{evidence_path.resolve().relative_to(root.resolve()).as_posix()}#items/{first_evidence['id']}",
                "lineRange": first_evidence["lineRange"],
                "excerptHash": first_evidence["excerptHash"],
                "redactionPolicy": "evidence_bound_excerpt_only",
                "timestamp": GENERATED_AT,
                "assertion": "Trajectory observations can cite evidence, but task verdicts remain owned by EvidenceListV1 and VerifierRuntimeV1.",
            }
        ],
        "policy": {
            "noExternalSideEffects": True,
            "noGuiAutomationExecuted": True,
            "rawScreenPixelsCaptured": False,
            "sensitiveValuesCaptured": False,
            "requiresVerifierForTaskVerdict": True,
        },
    }


def validate_trajectory_observation(observation: dict[str, Any], contract: dict[str, Any], root: Path) -> None:
    validate_computer_runtime_contract(contract)
    _require_fields(
        "TrajectoryObservationV1",
        observation,
        [
            "schemaVersion",
            "id",
            "contractRef",
            "redactionPolicyRef",
            "adapterRef",
            "provider",
            "mode",
            "externalSideEffect",
            "fixtureId",
            "runId",
            "sourceArtifacts",
            "observations",
            "policy",
        ],
    )
    if observation["schemaVersion"] != TRAJECTORY_OBSERVATION_SCHEMA_VERSION:
        raise ValueError(f"TrajectoryObservationV1 schemaVersion must be {TRAJECTORY_OBSERVATION_SCHEMA_VERSION}")
    if observation["id"] != OBSERVATION_ID:
        raise ValueError(f"TrajectoryObservationV1 id must be {OBSERVATION_ID}")
    if observation["contractRef"] != CONTRACT_ARTIFACT_PATH:
        raise ValueError(f"TrajectoryObservationV1 contractRef must be {CONTRACT_ARTIFACT_PATH}")
    if observation["redactionPolicyRef"] != REDACTION_POLICY_ARTIFACT_PATH:
        raise ValueError(f"TrajectoryObservationV1 redactionPolicyRef must be {REDACTION_POLICY_ARTIFACT_PATH}")
    if observation["redactionPolicyRef"] != contract["observationPolicy"]["policyRef"]:
        raise ValueError("TrajectoryObservationV1 redactionPolicyRef must match ComputerRuntimeAdapterV1 observationPolicy")
    if observation["adapterRef"] != contract["adapterRef"]:
        raise ValueError("TrajectoryObservationV1 adapterRef must match ComputerRuntimeAdapterV1")
    if observation["mode"] != "static_fixture_only":
        raise ValueError("TrajectoryObservationV1 mode must be static_fixture_only")
    if observation["externalSideEffect"] is not False:
        raise ValueError("TrajectoryObservationV1 must not declare external side effects")

    policy = observation["policy"]
    if policy.get("noExternalSideEffects") is not True:
        raise ValueError("TrajectoryObservationV1 policy must forbid external side effects")
    if policy.get("noGuiAutomationExecuted") is not True:
        raise ValueError("TrajectoryObservationV1 policy must record that no GUI automation was executed")
    if policy.get("rawScreenPixelsCaptured") is not False:
        raise ValueError("TrajectoryObservationV1 must not capture raw screen pixels")
    if policy.get("sensitiveValuesCaptured") is not False:
        raise ValueError("TrajectoryObservationV1 must not capture sensitive values")
    if policy.get("requiresVerifierForTaskVerdict") is not True:
        raise ValueError("TrajectoryObservationV1 must require verifier ownership for task verdicts")

    source_artifacts = observation["sourceArtifacts"]
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("TrajectoryObservationV1 sourceArtifacts must be a non-empty list")
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("TrajectoryObservationV1 sourceArtifacts must be objects")
        _require_fields("TrajectoryObservationV1 source artifact", source, ["role", "path", "contentHash"])
        _validate_relative_posix_path(source["path"])
        source_path = root / source["path"]
        if not source_path.is_file():
            raise ValueError(f"TrajectoryObservationV1 source artifact does not exist: {source['path']}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"TrajectoryObservationV1 source hash mismatch for {source['path']}")
        sources_by_role[source["role"]] = source

    expected_roles = {"run", "evidence_list", "events"}
    if set(sources_by_role) != expected_roles:
        raise ValueError(f"TrajectoryObservationV1 source roles must equal {sorted(expected_roles)}")

    run = _load_json(root / sources_by_role["run"]["path"])
    evidence = _load_json(root / sources_by_role["evidence_list"]["path"])
    events = _load_events(root / sources_by_role["events"]["path"])
    if observation["fixtureId"] != run.get("fixtureId"):
        raise ValueError("TrajectoryObservationV1 fixtureId must match run.json")
    if observation["runId"] != run.get("id"):
        raise ValueError("TrajectoryObservationV1 runId must match run.json")

    evidence_items = evidence.get("items")
    if not isinstance(evidence_items, list) or not evidence_items:
        raise ValueError("TrajectoryObservationV1 requires non-empty EvidenceListV1 items")
    evidence_by_id = {item["id"]: item for item in evidence_items if isinstance(item, dict) and "id" in item}
    event_ids = {event["id"] for event in events if "id" in event}

    observations = observation["observations"]
    if not isinstance(observations, list) or not observations:
        raise ValueError("TrajectoryObservationV1 observations must be a non-empty list")
    for item in observations:
        if not isinstance(item, dict):
            raise ValueError("TrajectoryObservationV1 observations must be objects")
        _require_fields(
            "TrajectoryObservationV1 observation",
            item,
            [
                "id",
                "kind",
                "capability",
                "capabilityRef",
                "eventRef",
                "evidenceId",
                "sourceRef",
                "lineRange",
                "excerptHash",
                "redactionPolicy",
            ],
        )
        if "verdict" in item or "taskVerdict" in item:
            raise ValueError("TrajectoryObservationV1 observations must not declare task verdicts")
        if item["redactionPolicy"] != "evidence_bound_excerpt_only":
            raise ValueError("TrajectoryObservationV1 observations must use evidence_bound_excerpt_only redaction policy")
        if item["kind"] not in contract["trajectoryContract"]["allowedObservationKinds"]:
            raise ValueError(f"TrajectoryObservationV1 observation kind is not allowed: {item['kind']}")
        if item["capability"] != "trajectory.record":
            raise ValueError("TrajectoryObservationV1 observations must use trajectory.record capability")
        if item["capabilityRef"] != computer_capability_ref("trajectory.record"):
            raise ValueError("TrajectoryObservationV1 observation capabilityRef mismatch")
        if item["eventRef"] not in event_ids:
            raise ValueError(f"TrajectoryObservationV1 observation references unknown eventRef: {item['eventRef']}")
        evidence_item = evidence_by_id.get(item["evidenceId"])
        if evidence_item is None:
            raise ValueError(f"TrajectoryObservationV1 observation must bind to existing evidence id: {item['evidenceId']}")
        if item["lineRange"] != evidence_item.get("lineRange"):
            raise ValueError("TrajectoryObservationV1 observation lineRange must match EvidenceListV1")
        if item["excerptHash"] != evidence_item.get("excerptHash"):
            raise ValueError("TrajectoryObservationV1 observation excerptHash must match EvidenceListV1")


def build_observation_redaction_policy(contract_path: Path, root: Path) -> dict[str, Any]:
    contract = _load_json(contract_path)
    validate_computer_runtime_contract(contract)
    return {
        "schemaVersion": OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION,
        "id": REDACTION_POLICY_ID,
        "phase": "phase7",
        "scope": "computer_runtime_observation_redaction_and_source_policy",
        "generatedAt": GENERATED_AT,
        "contractRef": CONTRACT_ARTIFACT_PATH,
        "adapterRef": contract["adapterRef"],
        "sourceArtifacts": [
            _artifact_source("computer_runtime_contract", contract_path, root),
        ],
        "defaults": {
            "rawScreenPixelsAllowed": False,
            "sensitiveValueCaptureAllowed": False,
            "sourceBindingRequired": True,
            "verdictEmissionAllowed": False,
        },
        "observationKinds": [
            {
                "kind": "screen_observation",
                "capability": "computer.screenshot",
                "capabilityRef": computer_capability_ref("computer.screenshot"),
                "rawCaptureAllowed": False,
                "requiredRedaction": "redacted_metadata_or_redacted_image_ref_only",
                "allowedDataClasses": [
                    "redacted_screenshot_ref",
                    "window_title",
                    "visible_text_excerpt",
                    "accessibility_tree_excerpt",
                ],
                "forbiddenDataClasses": [
                    "credential",
                    "personal_data",
                    "raw_screen_pixels",
                    "secret",
                ],
                "sourceBinding": "screenObservationRef_with_redaction_policy",
            },
            {
                "kind": "trajectory_event",
                "capability": "trajectory.record",
                "capabilityRef": computer_capability_ref("trajectory.record"),
                "rawCaptureAllowed": False,
                "requiredRedaction": "evidence_bound_excerpt_only",
                "allowedDataClasses": [
                    "eventRef",
                    "evidenceId",
                    "excerptHash",
                    "lineRange",
                    "sourceRef",
                ],
                "forbiddenDataClasses": [
                    "credential",
                    "raw_screen_pixels",
                    "secret",
                    "task_verdict",
                ],
                "sourceBinding": "run_event_and_evidence_ref",
            },
        ],
        "invariants": [
            "Computer runtime observations must bind to source refs before they can be used as evidence.",
            "Raw screen pixels, credentials, secrets, and task verdicts are forbidden in Phase 7 observation artifacts.",
            "Trajectory observations may cite evidence ids and excerpt hashes but must not decide engineering task success.",
        ],
    }


def validate_observation_redaction_policy(policy: dict[str, Any], contract: dict[str, Any], root: Path) -> None:
    validate_computer_runtime_contract(contract)
    _require_fields(
        "ObservationRedactionPolicyV1",
        policy,
        [
            "schemaVersion",
            "id",
            "phase",
            "scope",
            "contractRef",
            "adapterRef",
            "sourceArtifacts",
            "defaults",
            "observationKinds",
            "invariants",
        ],
    )
    if policy["schemaVersion"] != OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION:
        raise ValueError(f"ObservationRedactionPolicyV1 schemaVersion must be {OBSERVATION_REDACTION_POLICY_SCHEMA_VERSION}")
    if policy["id"] != REDACTION_POLICY_ID:
        raise ValueError(f"ObservationRedactionPolicyV1 id must be {REDACTION_POLICY_ID}")
    if policy["phase"] != "phase7":
        raise ValueError("ObservationRedactionPolicyV1 phase must be phase7")
    if policy["contractRef"] != CONTRACT_ARTIFACT_PATH:
        raise ValueError(f"ObservationRedactionPolicyV1 contractRef must be {CONTRACT_ARTIFACT_PATH}")
    if policy["adapterRef"] != contract["adapterRef"]:
        raise ValueError("ObservationRedactionPolicyV1 adapterRef must match ComputerRuntimeAdapterV1")
    if contract["observationPolicy"]["policyRef"] != REDACTION_POLICY_ARTIFACT_PATH:
        raise ValueError("ComputerRuntimeAdapterV1 must reference the committed ObservationRedactionPolicyV1 artifact")

    source_artifacts = policy["sourceArtifacts"]
    if not isinstance(source_artifacts, list) or len(source_artifacts) != 1:
        raise ValueError("ObservationRedactionPolicyV1 sourceArtifacts must contain the computer runtime contract")
    source = source_artifacts[0]
    _require_fields("ObservationRedactionPolicyV1 source artifact", source, ["role", "path", "contentHash"])
    if source["role"] != "computer_runtime_contract" or source["path"] != CONTRACT_ARTIFACT_PATH:
        raise ValueError("ObservationRedactionPolicyV1 source artifact must be the computer runtime contract")
    _validate_relative_posix_path(source["path"])
    source_path = root / source["path"]
    if not source_path.is_file():
        raise ValueError(f"ObservationRedactionPolicyV1 source artifact does not exist: {source['path']}")
    if _stable_file_hash(source_path) != source["contentHash"]:
        raise ValueError(f"ObservationRedactionPolicyV1 source hash mismatch for {source['path']}")

    defaults = policy["defaults"]
    _require_fields(
        "ObservationRedactionPolicyV1 defaults",
        defaults,
        [
            "rawScreenPixelsAllowed",
            "sensitiveValueCaptureAllowed",
            "sourceBindingRequired",
            "verdictEmissionAllowed",
        ],
    )
    if defaults["rawScreenPixelsAllowed"] is not False:
        raise ValueError("ObservationRedactionPolicyV1 must disallow raw screen pixels")
    if defaults["sensitiveValueCaptureAllowed"] is not False:
        raise ValueError("ObservationRedactionPolicyV1 must disallow sensitive value capture")
    if defaults["sourceBindingRequired"] is not True:
        raise ValueError("ObservationRedactionPolicyV1 must require source binding")
    if defaults["verdictEmissionAllowed"] is not False:
        raise ValueError("ObservationRedactionPolicyV1 must not allow observation verdict emission")

    kinds = policy["observationKinds"]
    if not isinstance(kinds, list) or len(kinds) != 2:
        raise ValueError("ObservationRedactionPolicyV1 must define screen_observation and trajectory_event policies")
    by_kind = {item.get("kind"): item for item in kinds if isinstance(item, dict)}
    if set(by_kind) != {"screen_observation", "trajectory_event"}:
        raise ValueError("ObservationRedactionPolicyV1 kinds must be screen_observation and trajectory_event")
    required = {
        "screen_observation": {
            "capability": "computer.screenshot",
            "requiredRedaction": "redacted_metadata_or_redacted_image_ref_only",
            "sourceBinding": "screenObservationRef_with_redaction_policy",
        },
        "trajectory_event": {
            "capability": "trajectory.record",
            "requiredRedaction": "evidence_bound_excerpt_only",
            "sourceBinding": "run_event_and_evidence_ref",
        },
    }
    contract_capability_refs = {capability["name"]: capability["ref"] for capability in contract["capabilities"]}
    for kind, expectations in required.items():
        item = by_kind[kind]
        _require_fields(
            f"ObservationRedactionPolicyV1 {kind}",
            item,
            [
                "kind",
                "capability",
                "capabilityRef",
                "rawCaptureAllowed",
                "requiredRedaction",
                "allowedDataClasses",
                "forbiddenDataClasses",
                "sourceBinding",
            ],
        )
        if item["capability"] != expectations["capability"]:
            raise ValueError(f"ObservationRedactionPolicyV1 {kind} capability mismatch")
        if item["capabilityRef"] != contract_capability_refs[item["capability"]]:
            raise ValueError(f"ObservationRedactionPolicyV1 {kind} capabilityRef must match ComputerRuntimeAdapterV1")
        if item["rawCaptureAllowed"] is not False:
            raise ValueError(f"ObservationRedactionPolicyV1 {kind} must not allow raw capture")
        if item["requiredRedaction"] != expectations["requiredRedaction"]:
            raise ValueError(f"ObservationRedactionPolicyV1 {kind} requiredRedaction mismatch")
        if item["sourceBinding"] != expectations["sourceBinding"]:
            raise ValueError(f"ObservationRedactionPolicyV1 {kind} sourceBinding mismatch")
        forbidden = item["forbiddenDataClasses"]
        if not isinstance(forbidden, list):
            raise ValueError(f"ObservationRedactionPolicyV1 {kind} forbiddenDataClasses must be a list")
        for value in ["credential", "raw_screen_pixels", "secret"]:
            if value not in forbidden:
                raise ValueError(f"ObservationRedactionPolicyV1 {kind} must forbid {value}")
    if "task_verdict" not in by_kind["trajectory_event"]["forbiddenDataClasses"]:
        raise ValueError("ObservationRedactionPolicyV1 trajectory_event must forbid task_verdict")


def build_adapter_policy_manifest(contract_path: Path, capability_catalog_path: Path, root: Path) -> dict[str, Any]:
    contract = _load_json(contract_path)
    validate_computer_runtime_contract(contract)
    catalog = _load_json(capability_catalog_path)
    phase3_refs = _capability_catalog_refs(catalog)
    adapter_refs_in_catalog = [ref for ref in phase3_refs if ref.startswith(CAPABILITY_URI_PREFIX)]

    decisions = []
    for capability in contract["capabilities"]:
        dangerous = capability["permission"] == "dangerous" or capability["approvalRequired"] is True
        decisions.append(
            {
                "schemaVersion": ADAPTER_POLICY_DECISION_SCHEMA_VERSION,
                "capability": capability["name"],
                "capabilityRef": capability["ref"],
                "permission": capability["permission"],
                "approvalRequired": capability["approvalRequired"],
                "executionMode": capability["executionMode"],
                "scheduleWithoutApproval": not dangerous,
                "scheduledByDefault": False,
                "realProviderExecutionAllowed": False,
                "externalSideEffectAllowed": False,
                "schedulerDecision": "blocked_requires_approval" if dangerous else "contract_only_allowed_without_approval",
            }
        )

    return {
        "schemaVersion": ADAPTER_POLICY_MANIFEST_SCHEMA_VERSION,
        "id": POLICY_MANIFEST_ID,
        "phase": "phase7",
        "scope": "computer_runtime_permission_overlay",
        "generatedAt": GENERATED_AT,
        "sourceArtifacts": [
            _artifact_source("computer_runtime_contract", contract_path, root),
            _artifact_source("phase3_capability_catalog", capability_catalog_path, root),
        ],
        "schedulerPolicy": {
            "schemaVersion": "permission-policy-v1",
            "mode": "phase7_adapter_policy_overlay",
            "externalSideEffectsAllowed": False,
            "realProviderExecutionAllowed": False,
            "dangerousCapabilitiesRequireApproval": True,
            "unapprovedDangerousDecision": "block",
        },
        "phase3CatalogBoundary": {
            "catalogRef": PHASE3_CAPABILITY_CATALOG_PATH,
            "registeredRunnerCapabilityRefs": phase3_refs,
            "adapterCapabilityRefPrefix": CAPABILITY_URI_PREFIX,
            "adapterCapabilitiesInRunnerCatalog": adapter_refs_in_catalog,
        },
        "blockedDangerousCapabilityRefs": [
            capability["ref"]
            for capability in contract["capabilities"]
            if capability["permission"] == "dangerous" or capability["approvalRequired"] is True
        ],
        "decisions": decisions,
        "invariants": [
            "Phase 7 adapter capabilities are not registered in the Phase 3 regression runner catalogue.",
            "Dangerous computer and sandbox capabilities must be blocked unless an approval policy explicitly authorizes them.",
            "Real CUA, GUI, desktop, browser, shell, and sandbox providers remain disabled in this MVP slice.",
        ],
    }


def validate_adapter_policy_manifest(
    manifest: dict[str, Any],
    contract: dict[str, Any],
    capability_catalog: dict[str, Any],
    root: Path,
) -> None:
    validate_computer_runtime_contract(contract)
    phase3_refs = _capability_catalog_refs(capability_catalog)
    _require_fields(
        "AdapterPolicyManifestV1",
        manifest,
        [
            "schemaVersion",
            "id",
            "phase",
            "scope",
            "sourceArtifacts",
            "schedulerPolicy",
            "phase3CatalogBoundary",
            "blockedDangerousCapabilityRefs",
            "decisions",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != ADAPTER_POLICY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"AdapterPolicyManifestV1 schemaVersion must be {ADAPTER_POLICY_MANIFEST_SCHEMA_VERSION}")
    if manifest["id"] != POLICY_MANIFEST_ID:
        raise ValueError(f"AdapterPolicyManifestV1 id must be {POLICY_MANIFEST_ID}")
    if manifest["phase"] != "phase7":
        raise ValueError("AdapterPolicyManifestV1 phase must be phase7")
    if manifest["scope"] != "computer_runtime_permission_overlay":
        raise ValueError("AdapterPolicyManifestV1 scope must be computer_runtime_permission_overlay")

    source_artifacts = manifest["sourceArtifacts"]
    if not isinstance(source_artifacts, list) or len(source_artifacts) != 2:
        raise ValueError("AdapterPolicyManifestV1 sourceArtifacts must contain contract and capability catalog")
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("AdapterPolicyManifestV1 sourceArtifacts must be objects")
        _require_fields("AdapterPolicyManifestV1 source artifact", source, ["role", "path", "contentHash"])
        _validate_relative_posix_path(source["path"])
        source_path = root / source["path"]
        if not source_path.is_file():
            raise ValueError(f"AdapterPolicyManifestV1 source artifact does not exist: {source['path']}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"AdapterPolicyManifestV1 source hash mismatch for {source['path']}")
        sources_by_role[source["role"]] = source
    if set(sources_by_role) != {"computer_runtime_contract", "phase3_capability_catalog"}:
        raise ValueError("AdapterPolicyManifestV1 source roles must be contract and capability catalog")
    if sources_by_role["computer_runtime_contract"]["path"] != CONTRACT_ARTIFACT_PATH:
        raise ValueError(f"AdapterPolicyManifestV1 contract source must be {CONTRACT_ARTIFACT_PATH}")
    if sources_by_role["phase3_capability_catalog"]["path"] != PHASE3_CAPABILITY_CATALOG_PATH:
        raise ValueError(f"AdapterPolicyManifestV1 capability catalog source must be {PHASE3_CAPABILITY_CATALOG_PATH}")

    policy = manifest["schedulerPolicy"]
    _require_fields(
        "AdapterPolicyManifestV1 schedulerPolicy",
        policy,
        [
            "schemaVersion",
            "mode",
            "externalSideEffectsAllowed",
            "realProviderExecutionAllowed",
            "dangerousCapabilitiesRequireApproval",
            "unapprovedDangerousDecision",
        ],
    )
    if policy["schemaVersion"] != "permission-policy-v1":
        raise ValueError("AdapterPolicyManifestV1 schedulerPolicy must reference permission-policy-v1")
    if policy["mode"] != "phase7_adapter_policy_overlay":
        raise ValueError("AdapterPolicyManifestV1 schedulerPolicy mode must be phase7_adapter_policy_overlay")
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("AdapterPolicyManifestV1 schedulerPolicy must disallow external side effects")
    if policy["realProviderExecutionAllowed"] is not False:
        raise ValueError("AdapterPolicyManifestV1 schedulerPolicy must disallow real provider execution")
    if policy["dangerousCapabilitiesRequireApproval"] is not True:
        raise ValueError("AdapterPolicyManifestV1 schedulerPolicy must require dangerous capability approval")
    if policy["unapprovedDangerousDecision"] != "block":
        raise ValueError("AdapterPolicyManifestV1 unapproved dangerous decision must be block")

    boundary = manifest["phase3CatalogBoundary"]
    _require_fields(
        "AdapterPolicyManifestV1 phase3CatalogBoundary",
        boundary,
        [
            "catalogRef",
            "registeredRunnerCapabilityRefs",
            "adapterCapabilityRefPrefix",
            "adapterCapabilitiesInRunnerCatalog",
        ],
    )
    if boundary["catalogRef"] != PHASE3_CAPABILITY_CATALOG_PATH:
        raise ValueError("AdapterPolicyManifestV1 phase3 catalogRef mismatch")
    if boundary["registeredRunnerCapabilityRefs"] != phase3_refs:
        raise ValueError("AdapterPolicyManifestV1 registered runner refs must mirror Phase 3 capability catalog")
    if boundary["adapterCapabilityRefPrefix"] != CAPABILITY_URI_PREFIX:
        raise ValueError("AdapterPolicyManifestV1 adapterCapabilityRefPrefix mismatch")
    adapter_refs_in_catalog = [ref for ref in phase3_refs if ref.startswith(CAPABILITY_URI_PREFIX)]
    if boundary["adapterCapabilitiesInRunnerCatalog"] != adapter_refs_in_catalog:
        raise ValueError("AdapterPolicyManifestV1 adapter catalog overlap must be derived from Phase 3 catalog")
    if adapter_refs_in_catalog:
        raise ValueError("AdapterPolicyManifestV1 must not register Phase 7 adapter capabilities in the Phase 3 runner catalog")

    expected_blocked_refs = [
        capability["ref"]
        for capability in contract["capabilities"]
        if capability["permission"] == "dangerous" or capability["approvalRequired"] is True
    ]
    if manifest["blockedDangerousCapabilityRefs"] != expected_blocked_refs:
        raise ValueError("AdapterPolicyManifestV1 blocked dangerous refs must match ComputerRuntimeAdapterV1")

    decisions = manifest["decisions"]
    if not isinstance(decisions, list) or len(decisions) != len(contract["capabilities"]):
        raise ValueError("AdapterPolicyManifestV1 decisions must mirror ComputerRuntimeAdapterV1 capabilities")
    for decision, capability in zip(decisions, contract["capabilities"]):
        _require_fields(
            "AdapterPolicyManifestV1 decision",
            decision,
            [
                "schemaVersion",
                "capability",
                "capabilityRef",
                "permission",
                "approvalRequired",
                "executionMode",
                "scheduleWithoutApproval",
                "scheduledByDefault",
                "realProviderExecutionAllowed",
                "externalSideEffectAllowed",
                "schedulerDecision",
            ],
        )
        if decision["schemaVersion"] != ADAPTER_POLICY_DECISION_SCHEMA_VERSION:
            raise ValueError("AdapterPolicyManifestV1 decision schemaVersion mismatch")
        for field in ["capability", "capabilityRef", "permission", "approvalRequired", "executionMode"]:
            expected = capability["name"] if field == "capability" else capability["ref"] if field == "capabilityRef" else capability[field]
            if decision[field] != expected:
                raise ValueError(f"AdapterPolicyManifestV1 decision {field} must match ComputerRuntimeAdapterV1")
        if decision["scheduledByDefault"] is not False:
            raise ValueError("AdapterPolicyManifestV1 adapter capabilities must not be scheduled by default")
        if decision["realProviderExecutionAllowed"] is not False:
            raise ValueError("AdapterPolicyManifestV1 decisions must disallow real provider execution")
        if decision["externalSideEffectAllowed"] is not False:
            raise ValueError("AdapterPolicyManifestV1 decisions must disallow external side effects")
        dangerous = capability["permission"] == "dangerous" or capability["approvalRequired"] is True
        if dangerous:
            if decision["scheduleWithoutApproval"] is not False:
                raise ValueError("AdapterPolicyManifestV1 dangerous adapter capabilities must not be schedulable without approval")
            if decision["schedulerDecision"] != "blocked_requires_approval":
                raise ValueError("AdapterPolicyManifestV1 dangerous schedulerDecision must be blocked_requires_approval")
        else:
            if decision["scheduleWithoutApproval"] is not True:
                raise ValueError("AdapterPolicyManifestV1 read-only contract capabilities should be schedulable without approval")
            if decision["schedulerDecision"] != "contract_only_allowed_without_approval":
                raise ValueError("AdapterPolicyManifestV1 read-only schedulerDecision must be contract_only_allowed_without_approval")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="computer-runtime-contract")
    parser.add_argument("--contract-out", type=Path)
    parser.add_argument("--observation-out", type=Path)
    parser.add_argument("--policy-manifest-out", type=Path)
    parser.add_argument("--redaction-policy-out", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--capability-catalog", type=Path, default=Path(PHASE3_CAPABILITY_CATALOG_PATH))
    parser.add_argument("--validate-contract", type=Path)
    parser.add_argument("--validate-observation", type=Path)
    parser.add_argument("--validate-policy-manifest", type=Path)
    parser.add_argument("--validate-redaction-policy", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()

    contract = None
    if args.contract_out:
        contract = build_computer_runtime_contract()
        _write_json(args.contract_out, contract)
        print(f"Wrote ComputerRuntimeAdapterV1 contract to {args.contract_out}.")

    if args.observation_out:
        if not args.run or not args.evidence or not args.events:
            raise ValueError("--observation-out requires --run, --evidence, and --events")
        if contract is None:
            contract = build_computer_runtime_contract()
        observation = build_trajectory_observation(args.run, args.evidence, args.events, root)
        validate_trajectory_observation(observation, contract, root)
        _write_json(args.observation_out, observation)
        print(f"Wrote TrajectoryObservationV1 artifact to {args.observation_out}.")

    if args.policy_manifest_out:
        policy_manifest = build_adapter_policy_manifest(root / CONTRACT_ARTIFACT_PATH, root / args.capability_catalog, root)
        _write_json(args.policy_manifest_out, policy_manifest)
        print(f"Wrote AdapterPolicyManifestV1 artifact to {args.policy_manifest_out}.")

    if args.redaction_policy_out:
        redaction_policy = build_observation_redaction_policy(root / CONTRACT_ARTIFACT_PATH, root)
        _write_json(args.redaction_policy_out, redaction_policy)
        print(f"Wrote ObservationRedactionPolicyV1 artifact to {args.redaction_policy_out}.")

    if args.validate_contract:
        contract = _load_json(args.validate_contract)
        validate_computer_runtime_contract(contract)
        print(f"Validated ComputerRuntimeAdapterV1 contract {args.validate_contract}.")

    if args.validate_observation:
        contract_path = args.validate_contract or (root / CONTRACT_ARTIFACT_PATH)
        contract = _load_json(contract_path)
        observation = _load_json(args.validate_observation)
        validate_trajectory_observation(observation, contract, root)
        print(f"Validated TrajectoryObservationV1 artifact {args.validate_observation}.")

    if args.validate_policy_manifest:
        contract_path = args.validate_contract or (root / CONTRACT_ARTIFACT_PATH)
        contract = _load_json(contract_path)
        catalog = _load_json(root / args.capability_catalog)
        policy_manifest = _load_json(args.validate_policy_manifest)
        validate_adapter_policy_manifest(policy_manifest, contract, catalog, root)
        print(f"Validated AdapterPolicyManifestV1 artifact {args.validate_policy_manifest}.")

    if args.validate_redaction_policy:
        contract_path = args.validate_contract or (root / CONTRACT_ARTIFACT_PATH)
        contract = _load_json(contract_path)
        redaction_policy = _load_json(args.validate_redaction_policy)
        validate_observation_redaction_policy(redaction_policy, contract, root)
        print(f"Validated ObservationRedactionPolicyV1 artifact {args.validate_redaction_policy}.")

    if not any(
        [
            args.contract_out,
            args.observation_out,
            args.policy_manifest_out,
            args.redaction_policy_out,
            args.validate_contract,
            args.validate_observation,
            args.validate_policy_manifest,
            args.validate_redaction_policy,
        ]
    ):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


COMPUTER_RUNTIME_CONTRACT_SCHEMA_VERSION = "computer-runtime-contract-v1"
TRAJECTORY_OBSERVATION_SCHEMA_VERSION = "trajectory-observation-v1"
PHASE7_CONTRACT_ID = "phase7-computer-runtime-contract"
PHASE7_TRAJECTORY_OBSERVATION_ID = "phase7-static-trajectory-observation"
DEFAULT_CONTRACT_REF = "artifacts/computer_runtime/phase7_computer_runtime_contract.json"
CAPABILITY_URI_PREFIX = "capability://phase7/"
GENERATED_AT = "2026-05-13T13:44:00Z"

COMPUTER_RUNTIME_CAPABILITY_NAMES = [
    "computer.screenshot",
    "computer.click",
    "computer.type",
    "computer.run_shell",
    "trajectory.record",
    "sandbox.create",
    "sandbox.destroy",
]

READONLY_CAPABILITIES = {"computer.screenshot", "trajectory.record"}
SIDE_EFFECT_POTENTIAL_CAPABILITIES = {
    "computer.click",
    "computer.type",
    "computer.run_shell",
    "sandbox.create",
    "sandbox.destroy",
}


def capability_ref(name: str) -> str:
    return f"{CAPABILITY_URI_PREFIX}{name}"


def capability_namespace(name: str) -> str:
    return name.split(".", 1)[0]


def build_capability(name: str) -> dict[str, Any]:
    if name not in COMPUTER_RUNTIME_CAPABILITY_NAMES:
        raise ValueError(f"Unknown Phase 7 computer runtime capability: {name}")
    side_effect_potential = name in SIDE_EFFECT_POTENTIAL_CAPABILITIES
    permission = "read" if name in READONLY_CAPABILITIES else "dangerous"
    input_schema = {
        "computer.screenshot": {
            "schema": "ComputerScreenshotInputV1",
            "required": ["displayRef"],
            "properties": {"displayRef": "string"},
        },
        "computer.click": {
            "schema": "ComputerClickInputV1",
            "required": ["x", "y", "button"],
            "properties": {"x": "integer", "y": "integer", "button": "string"},
        },
        "computer.type": {
            "schema": "ComputerTypeInputV1",
            "required": ["text"],
            "properties": {"text": "string:redacted-capable"},
        },
        "computer.run_shell": {
            "schema": "ComputerRunShellInputV1",
            "required": ["command"],
            "properties": {"command": "string", "workingDirectory": "string:path"},
        },
        "trajectory.record": {
            "schema": "TrajectoryRecordInputV1",
            "required": ["sessionRef"],
            "properties": {"sessionRef": "string"},
        },
        "sandbox.create": {
            "schema": "SandboxCreateInputV1",
            "required": ["imageRef", "networkPolicy"],
            "properties": {"imageRef": "string", "networkPolicy": "string"},
        },
        "sandbox.destroy": {
            "schema": "SandboxDestroyInputV1",
            "required": ["sandboxRef"],
            "properties": {"sandboxRef": "string"},
        },
    }[name]
    output_schema = {
        "computer.screenshot": {
            "schema": "ComputerScreenshotObservationV1",
            "produces": ["screenObservation"],
        },
        "computer.click": {
            "schema": "ComputerActionObservationV1",
            "produces": ["trajectoryEvent"],
        },
        "computer.type": {
            "schema": "ComputerActionObservationV1",
            "produces": ["trajectoryEvent"],
        },
        "computer.run_shell": {
            "schema": "ComputerShellObservationV1",
            "produces": ["stdoutRef", "stderrRef", "exitCode"],
        },
        "trajectory.record": {
            "schema": "TrajectoryObservationV1",
            "produces": ["trajectoryObservation"],
        },
        "sandbox.create": {
            "schema": "SandboxObservationV1",
            "produces": ["sandboxRef"],
        },
        "sandbox.destroy": {
            "schema": "SandboxObservationV1",
            "produces": ["sandboxClosedRef"],
        },
    }[name]
    return {
        "executionAllowedInMvp": False,
        "inputContract": input_schema,
        "name": name,
        "namespace": capability_namespace(name),
        "observationRole": "observation_source" if not side_effect_potential else "action_request_source",
        "outputContract": output_schema,
        "permission": permission,
        "ref": capability_ref(name),
        "requiresApproval": side_effect_potential,
        "requiresSandbox": side_effect_potential,
        "sideEffectPotential": side_effect_potential,
        "staticObservationAllowedInMvp": not side_effect_potential,
    }


def build_computer_runtime_contract() -> dict[str, Any]:
    return {
        "adapterBoundary": {
            "adapterRole": "computer_runtime_observation_and_trajectory_provider",
            "evidenceAuthority": "verifier_runtime",
            "executionEnabledInMvp": False,
            "externalSideEffectsAllowed": False,
            "integrateLater": ["trycua/cua", "browser-use", "e2b", "devbox"],
        },
        "capabilities": [build_capability(name) for name in COMPUTER_RUNTIME_CAPABILITY_NAMES],
        "id": PHASE7_CONTRACT_ID,
        "phase": "phase7",
        "schemaVersion": COMPUTER_RUNTIME_CONTRACT_SCHEMA_VERSION,
        "scope": "static_computer_runtime_adapter_contract",
    }


def build_static_trajectory_observation(contract_ref: str = DEFAULT_CONTRACT_REF) -> dict[str, Any]:
    return {
        "contractRef": contract_ref,
        "evidenceBridge": {
            "mayDirectlySatisfyTaskGoal": False,
            "observationToEvidence": "requires_evidence_list_and_verifier",
            "verifierRequired": True,
        },
        "id": PHASE7_TRAJECTORY_OBSERVATION_ID,
        "observationEvents": [
            {
                "capabilityRef": capability_ref("computer.screenshot"),
                "eventId": "trajectory-event-001",
                "executionState": "observed",
                "observation": {
                    "artifactRef": "screen://synthetic/phase7/initial",
                    "kind": "screen_observation",
                    "redacted": False,
                },
                "timestamp": GENERATED_AT,
            },
            {
                "capabilityRef": capability_ref("computer.click"),
                "eventId": "trajectory-event-002",
                "executionState": "planned_not_executed",
                "observation": {
                    "kind": "action_request",
                    "reason": "static contract fixture only; no GUI action executed",
                },
                "timestamp": GENERATED_AT,
            },
            {
                "capabilityRef": capability_ref("trajectory.record"),
                "eventId": "trajectory-event-003",
                "executionState": "observed",
                "observation": {
                    "eventCount": 2,
                    "kind": "trajectory_summary",
                },
                "timestamp": GENERATED_AT,
            },
        ],
        "policy": {
            "externalSideEffectsPerformed": False,
            "guiAutomationPerformed": False,
            "runtimeExecutionPerformed": False,
            "sandboxRequiredForFutureExecution": True,
        },
        "provider": "trycua/cua-static-contract-fixture",
        "schemaVersion": TRAJECTORY_OBSERVATION_SCHEMA_VERSION,
        "source": "synthetic_static_fixture",
    }


def _require_fields(label: str, payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing}")


def validate_computer_runtime_contract(contract: dict[str, Any]) -> None:
    _require_fields("ComputerRuntimeContractV1", contract, ["schemaVersion", "id", "phase", "scope", "adapterBoundary", "capabilities"])
    if contract["schemaVersion"] != COMPUTER_RUNTIME_CONTRACT_SCHEMA_VERSION:
        raise ValueError(f"ComputerRuntimeContractV1 schemaVersion must be {COMPUTER_RUNTIME_CONTRACT_SCHEMA_VERSION}")
    if contract["id"] != PHASE7_CONTRACT_ID:
        raise ValueError(f"ComputerRuntimeContractV1 id must be {PHASE7_CONTRACT_ID}")
    if contract["phase"] != "phase7":
        raise ValueError("ComputerRuntimeContractV1 phase must be phase7")
    if contract["scope"] != "static_computer_runtime_adapter_contract":
        raise ValueError("ComputerRuntimeContractV1 scope must be static_computer_runtime_adapter_contract")

    boundary = contract["adapterBoundary"]
    _require_fields(
        "ComputerRuntimeContractV1 adapterBoundary",
        boundary,
        ["adapterRole", "evidenceAuthority", "executionEnabledInMvp", "externalSideEffectsAllowed", "integrateLater"],
    )
    if boundary["adapterRole"] != "computer_runtime_observation_and_trajectory_provider":
        raise ValueError("ComputerRuntimeContractV1 adapter role must stay below the Engineering OS control plane")
    if boundary["evidenceAuthority"] != "verifier_runtime":
        raise ValueError("ComputerRuntimeContractV1 evidence authority must remain in verifier_runtime")
    if boundary["executionEnabledInMvp"] is not False:
        raise ValueError("ComputerRuntimeContractV1 must not enable real computer runtime execution in the MVP")
    if boundary["externalSideEffectsAllowed"] is not False:
        raise ValueError("ComputerRuntimeContractV1 must disallow external side effects")
    if "trycua/cua" not in boundary["integrateLater"]:
        raise ValueError("ComputerRuntimeContractV1 must record trycua/cua as an integrate-later runtime")

    capabilities = contract["capabilities"]
    if not isinstance(capabilities, list):
        raise ValueError("ComputerRuntimeContractV1 capabilities must be a list")
    names = [item.get("name") for item in capabilities if isinstance(item, dict)]
    if names != COMPUTER_RUNTIME_CAPABILITY_NAMES:
        raise ValueError(f"ComputerRuntimeContractV1 capabilities must equal {COMPUTER_RUNTIME_CAPABILITY_NAMES}")
    for item in capabilities:
        _require_fields(
            "ComputerRuntimeContractV1 capability",
            item,
            [
                "name",
                "namespace",
                "ref",
                "permission",
                "sideEffectPotential",
                "requiresApproval",
                "requiresSandbox",
                "executionAllowedInMvp",
                "staticObservationAllowedInMvp",
                "inputContract",
                "outputContract",
                "observationRole",
            ],
        )
        name = item["name"]
        if item["ref"] != capability_ref(name):
            raise ValueError(f"ComputerRuntimeContractV1 capability {name} ref mismatch")
        if item["namespace"] not in {"computer", "trajectory", "sandbox"}:
            raise ValueError(f"ComputerRuntimeContractV1 capability {name} namespace is invalid")
        expected_side_effect = name in SIDE_EFFECT_POTENTIAL_CAPABILITIES
        if item["sideEffectPotential"] is not expected_side_effect:
            raise ValueError(f"ComputerRuntimeContractV1 capability {name} sideEffectPotential mismatch")
        if expected_side_effect:
            if item["permission"] != "dangerous" or item["requiresApproval"] is not True or item["requiresSandbox"] is not True:
                raise ValueError(f"ComputerRuntimeContractV1 capability {name} must require approval and sandbox")
            if item["executionAllowedInMvp"] is not False:
                raise ValueError(f"ComputerRuntimeContractV1 capability {name} must not be executable in the MVP")
            if item["staticObservationAllowedInMvp"] is not False:
                raise ValueError(f"ComputerRuntimeContractV1 capability {name} must not be allowed as a static observation source")
        else:
            if item["permission"] != "read" or item["requiresApproval"] is not False or item["requiresSandbox"] is not False:
                raise ValueError(f"ComputerRuntimeContractV1 read-only capability {name} has invalid policy")
            if item["executionAllowedInMvp"] is not False or item["staticObservationAllowedInMvp"] is not True:
                raise ValueError(f"ComputerRuntimeContractV1 read-only capability {name} must be static-observation only")


def validate_trajectory_observation(observation: dict[str, Any], contract: dict[str, Any]) -> None:
    validate_computer_runtime_contract(contract)
    _require_fields(
        "TrajectoryObservationV1",
        observation,
        ["schemaVersion", "id", "contractRef", "provider", "source", "policy", "evidenceBridge", "observationEvents"],
    )
    if observation["schemaVersion"] != TRAJECTORY_OBSERVATION_SCHEMA_VERSION:
        raise ValueError(f"TrajectoryObservationV1 schemaVersion must be {TRAJECTORY_OBSERVATION_SCHEMA_VERSION}")
    if observation["id"] != PHASE7_TRAJECTORY_OBSERVATION_ID:
        raise ValueError(f"TrajectoryObservationV1 id must be {PHASE7_TRAJECTORY_OBSERVATION_ID}")
    if observation["contractRef"] != DEFAULT_CONTRACT_REF:
        raise ValueError(f"TrajectoryObservationV1 contractRef must be {DEFAULT_CONTRACT_REF}")

    policy = observation["policy"]
    _require_fields("TrajectoryObservationV1 policy", policy, ["runtimeExecutionPerformed", "guiAutomationPerformed", "externalSideEffectsPerformed", "sandboxRequiredForFutureExecution"])
    if policy["runtimeExecutionPerformed"] is not False:
        raise ValueError("TrajectoryObservationV1 must be a static fixture with no runtime execution")
    if policy["guiAutomationPerformed"] is not False:
        raise ValueError("TrajectoryObservationV1 must not perform GUI automation")
    if policy["externalSideEffectsPerformed"] is not False:
        raise ValueError("TrajectoryObservationV1 must not perform external side effects")
    if policy["sandboxRequiredForFutureExecution"] is not True:
        raise ValueError("TrajectoryObservationV1 must require sandboxing for future execution")

    bridge = observation["evidenceBridge"]
    _require_fields("TrajectoryObservationV1 evidenceBridge", bridge, ["observationToEvidence", "verifierRequired", "mayDirectlySatisfyTaskGoal"])
    if bridge["observationToEvidence"] != "requires_evidence_list_and_verifier":
        raise ValueError("TrajectoryObservationV1 must route observations through evidence/verifier")
    if bridge["verifierRequired"] is not True or bridge["mayDirectlySatisfyTaskGoal"] is not False:
        raise ValueError("TrajectoryObservationV1 cannot directly satisfy an engineering task goal")

    capability_by_ref = {item["ref"]: item for item in contract["capabilities"]}
    events = observation["observationEvents"]
    if not isinstance(events, list) or not events:
        raise ValueError("TrajectoryObservationV1 observationEvents must be a non-empty list")
    event_ids = set()
    for event in events:
        _require_fields("TrajectoryObservationV1 event", event, ["eventId", "capabilityRef", "executionState", "observation", "timestamp"])
        if event["eventId"] in event_ids:
            raise ValueError(f"TrajectoryObservationV1 duplicate eventId: {event['eventId']}")
        event_ids.add(event["eventId"])
        capability = capability_by_ref.get(event["capabilityRef"])
        if capability is None:
            raise ValueError(f"TrajectoryObservationV1 references unknown capabilityRef: {event['capabilityRef']}")
        if event["executionState"] == "executed":
            raise ValueError("TrajectoryObservationV1 must not contain executed computer actions in Phase 7 static fixture")
        if capability["sideEffectPotential"] and event["executionState"] != "planned_not_executed":
            raise ValueError("TrajectoryObservationV1 side-effect-capable events must be planned_not_executed")
        if not capability["sideEffectPotential"] and event["executionState"] not in {"observed", "planned_not_executed"}:
            raise ValueError("TrajectoryObservationV1 read-only events have invalid executionState")
        if not isinstance(event["observation"], dict) or "kind" not in event["observation"]:
            raise ValueError("TrajectoryObservationV1 event observation must include kind")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="computer-runtime-contract")
    parser.add_argument("--contract-out", type=Path)
    parser.add_argument("--trajectory-out", type=Path)
    parser.add_argument("--validate-contract", type=Path)
    parser.add_argument("--validate-trajectory", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    contract = build_computer_runtime_contract()
    validate_computer_runtime_contract(contract)

    if args.validate_contract:
        validate_computer_runtime_contract(load_json(args.validate_contract))
    if args.validate_trajectory:
        validate_trajectory_observation(load_json(args.validate_trajectory), contract)

    wrote = False
    if args.contract_out:
        write_json(args.contract_out, contract)
        wrote = True
    if args.trajectory_out:
        trajectory = build_static_trajectory_observation()
        validate_trajectory_observation(trajectory, contract)
        write_json(args.trajectory_out, trajectory)
        wrote = True
    if not wrote and not args.validate_contract and not args.validate_trajectory:
        print(json.dumps(contract, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

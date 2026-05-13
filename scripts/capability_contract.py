from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any


CAPABILITY_CONTRACT_SCHEMA_VERSION = "capability-contract-v1"
PERMISSIONS = {"read", "write", "dangerous"}
REQUIRED_MVP_CAPABILITY_NAMES = ("read_log", "extract_regression_result", "write_artifact")
SYSTEM_CAPABILITY_NAMES = ("rule_verifier",)
TARGET_CAPABILITY_NAMES = (
    "read_file",
    "search_code",
    "run_command",
    "get_git_status",
    "apply_patch",
    "run_test",
    "summarize_log",
    "request_approval",
)


@dataclass(frozen=True)
class CapabilityContract:
    name: str
    permission: str
    sideEffect: bool
    timeoutMs: int
    inputSchema: dict[str, Any]
    outputSchema: dict[str, Any]
    description: str
    schemaVersion: str = CAPABILITY_CONTRACT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def object_schema(required: list[str], properties: dict[str, dict[str, str]]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "properties": properties,
    }


MVP_CAPABILITY_CATALOG: dict[str, dict[str, Any]] = {
    "read_log": CapabilityContract(
        name="read_log",
        permission="read",
        sideEffect=False,
        timeoutMs=5000,
        inputSchema=object_schema(["path"], {"path": {"type": "string"}}),
        outputSchema=object_schema(
            ["sourcePath", "text"],
            {"sourcePath": {"type": "string"}, "text": {"type": "string"}},
        ),
        description="Read a local regression log without modifying it.",
    ).to_dict(),
    "extract_regression_result": CapabilityContract(
        name="extract_regression_result",
        permission="read",
        sideEffect=False,
        timeoutMs=5000,
        inputSchema=object_schema(
            ["sourcePath", "logText", "taskSpec"],
            {
                "sourcePath": {"type": "string"},
                "logText": {"type": "string"},
                "taskSpec": {"type": "object"},
            },
        ),
        outputSchema=object_schema(
            ["evidence", "verdict", "summary", "evidenceIds"],
            {
                "evidence": {"type": "array"},
                "verdict": {"type": "string"},
                "summary": {"type": "string"},
                "evidenceIds": {"type": "array"},
            },
        ),
        description="Classify regression log markers into evidence and a structured verdict.",
    ).to_dict(),
    "write_artifact": CapabilityContract(
        name="write_artifact",
        permission="write",
        sideEffect=True,
        timeoutMs=5000,
        inputSchema=object_schema(
            ["outDir", "artifacts"],
            {"outDir": {"type": "string"}, "artifacts": {"type": "array"}},
        ),
        outputSchema=object_schema(
            ["writtenArtifacts"],
            {"writtenArtifacts": {"type": "array"}},
        ),
        description="Write local run artifacts under the selected output directory.",
    ).to_dict(),
    "rule_verifier": CapabilityContract(
        name="rule_verifier",
        permission="read",
        sideEffect=False,
        timeoutMs=5000,
        inputSchema=object_schema(
            ["evidence", "regressionResult", "emailDraft"],
            {
                "evidence": {"type": "array"},
                "regressionResult": {"type": "object"},
                "emailDraft": {"type": "string"},
            },
        ),
        outputSchema=object_schema(
            ["verifierReport"],
            {"verifierReport": {"type": "object"}},
        ),
        description="Verify schema, evidence references, classification precedence, and email grounding.",
    ).to_dict(),
}


def capability_contract_for(name: str, catalog: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    active_catalog = catalog or MVP_CAPABILITY_CATALOG
    if name not in active_catalog:
        raise KeyError(f"Unknown capability contract: {name}")
    return deepcopy(active_catalog[name])


def validate_json_object_schema(label: str, schema: Any) -> None:
    if not isinstance(schema, dict):
        raise ValueError(f"{label} must be a JSON object schema")
    if schema.get("type") != "object":
        raise ValueError(f"{label}.type must be object")
    if not isinstance(schema.get("required"), list):
        raise ValueError(f"{label}.required must be a list")
    if not isinstance(schema.get("properties"), dict):
        raise ValueError(f"{label}.properties must be an object")


def validate_capability_contract(contract: dict[str, Any]) -> None:
    required_fields = [
        "schemaVersion",
        "name",
        "permission",
        "sideEffect",
        "timeoutMs",
        "inputSchema",
        "outputSchema",
        "description",
    ]
    missing = [field for field in required_fields if field not in contract]
    if missing:
        raise ValueError(f"Capability contract is missing required fields: {missing}")
    if contract["schemaVersion"] != CAPABILITY_CONTRACT_SCHEMA_VERSION:
        raise ValueError(f"Capability contract schemaVersion must be {CAPABILITY_CONTRACT_SCHEMA_VERSION}")
    if not isinstance(contract["name"], str) or not contract["name"].strip():
        raise ValueError("Capability contract name must be a non-empty string")
    if contract["permission"] not in PERMISSIONS:
        raise ValueError(f"Capability contract permission must be one of {sorted(PERMISSIONS)}")
    if not isinstance(contract["sideEffect"], bool):
        raise ValueError("Capability contract sideEffect must be boolean")
    if not isinstance(contract["timeoutMs"], int) or contract["timeoutMs"] <= 0:
        raise ValueError("Capability contract timeoutMs must be a positive integer")
    if not isinstance(contract["description"], str) or not contract["description"].strip():
        raise ValueError("Capability contract description must be a non-empty string")
    validate_json_object_schema("Capability contract inputSchema", contract["inputSchema"])
    validate_json_object_schema("Capability contract outputSchema", contract["outputSchema"])


def validate_capability_catalog(
    catalog: dict[str, dict[str, Any]],
    required_names: tuple[str, ...] = REQUIRED_MVP_CAPABILITY_NAMES + SYSTEM_CAPABILITY_NAMES,
) -> None:
    missing = [name for name in required_names if name not in catalog]
    if missing:
        raise ValueError(f"Capability catalog is missing required capabilities: {missing}")
    for name, contract in catalog.items():
        validate_capability_contract(contract)
        if contract["name"] != name:
            raise ValueError(f"Capability catalog key {name} must match contract name {contract['name']}")


def validate_task_spec_capabilities(task_spec: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None) -> None:
    active_catalog = catalog or MVP_CAPABILITY_CATALOG
    allowed_actions = task_spec.get("allowedActions")
    if not isinstance(allowed_actions, list) or not allowed_actions:
        raise ValueError("TaskSpec allowedActions must be a non-empty list")
    unresolved = [action for action in allowed_actions if action not in active_catalog]
    if unresolved:
        raise ValueError(f"TaskSpec allowedActions missing capability contracts: {unresolved}")
    dangerous = [action for action in allowed_actions if active_catalog[action]["permission"] == "dangerous"]
    if dangerous:
        raise ValueError(f"Read-only regression TaskSpec cannot allow dangerous capabilities: {dangerous}")
    unexpected_side_effects = [
        action
        for action in allowed_actions
        if active_catalog[action]["sideEffect"] and action != "write_artifact"
    ]
    if unexpected_side_effects:
        raise ValueError(
            "Read-only regression TaskSpec only allows write_artifact as a local artifact side effect: "
            f"{unexpected_side_effects}"
        )


def validate_run_steps_capabilities(steps: list[dict[str, Any]], catalog: dict[str, dict[str, Any]] | None = None) -> None:
    active_catalog = catalog or MVP_CAPABILITY_CATALOG
    if not isinstance(steps, list) or not steps:
        raise ValueError("run.steps must be a non-empty list")
    for index, step in enumerate(steps):
        label = f"run.steps[{index}]"
        name = step.get("capability")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label}.capability must be a non-empty string")
        if name not in active_catalog:
            raise ValueError(f"{label}.capability has no registered contract: {name}")
        embedded = step.get("capabilityContract")
        if embedded != capability_contract_for(name, active_catalog):
            raise ValueError(f"{label}.capabilityContract must match the registered {name} contract")

from __future__ import annotations

from copy import deepcopy
from typing import Any


CAPABILITY_ENVELOPE_SCHEMA_VERSION = "capability-envelope-v1"
CAPABILITY_METADATA_SCHEMA_VERSION = "capability-metadata-v1"
CAPABILITY_NAMES = ["read_log", "extract_regression_result", "write_artifact"]
CAPABILITY_PERMISSIONS = {"read", "write", "dangerous"}

_CAPABILITY_METADATA: dict[str, dict[str, Any]] = {
    "read_log": {
        "schemaVersion": CAPABILITY_METADATA_SCHEMA_VERSION,
        "name": "read_log",
        "permission": "read",
        "sideEffect": False,
        "timeoutMs": 1000,
        "inputSchema": {
            "type": "object",
            "required": ["logPath"],
            "properties": {
                "logPath": "string",
            },
        },
        "outputSchema": {
            "type": "object",
            "required": ["logTextRef", "sourcePath"],
            "properties": {
                "logTextRef": "string",
                "sourcePath": "string",
            },
        },
    },
    "extract_regression_result": {
        "schemaVersion": CAPABILITY_METADATA_SCHEMA_VERSION,
        "name": "extract_regression_result",
        "permission": "read",
        "sideEffect": False,
        "timeoutMs": 1000,
        "inputSchema": {
            "type": "object",
            "required": ["logTextRef", "taskSpecRef"],
            "properties": {
                "logTextRef": "string",
                "taskSpecRef": "string",
            },
        },
        "outputSchema": {
            "type": "object",
            "required": ["evidenceArtifact", "regressionResultArtifact"],
            "properties": {
                "evidenceArtifact": "evidence.json",
                "regressionResultArtifact": "regression_result.json",
            },
        },
    },
    "write_artifact": {
        "schemaVersion": CAPABILITY_METADATA_SCHEMA_VERSION,
        "name": "write_artifact",
        "permission": "write",
        "sideEffect": False,
        "timeoutMs": 1000,
        "inputSchema": {
            "type": "object",
            "required": ["artifactPayloads", "outDir"],
            "properties": {
                "artifactPayloads": "object",
                "outDir": "string",
            },
        },
        "outputSchema": {
            "type": "object",
            "required": ["artifactPaths"],
            "properties": {
                "artifactPaths": "string[]",
            },
        },
    },
}


class CapabilityContractError(ValueError):
    pass


def build_capability_envelope() -> dict[str, Any]:
    return {
        "schemaVersion": CAPABILITY_ENVELOPE_SCHEMA_VERSION,
        "capabilities": [deepcopy(_CAPABILITY_METADATA[name]) for name in CAPABILITY_NAMES],
    }


def capability_ref(name: str) -> str:
    if name not in _CAPABILITY_METADATA:
        raise CapabilityContractError(f"Unknown capability: {name}")
    return f"{CAPABILITY_ENVELOPE_SCHEMA_VERSION}#{name}"


def capability_refs_by_name() -> dict[str, str]:
    return {name: capability_ref(name) for name in CAPABILITY_NAMES}


def validate_capability_metadata(metadata: dict[str, Any]) -> None:
    required = [
        "schemaVersion",
        "name",
        "permission",
        "sideEffect",
        "timeoutMs",
        "inputSchema",
        "outputSchema",
    ]
    missing = [field for field in required if field not in metadata]
    if missing:
        raise CapabilityContractError(f"Capability metadata is missing required fields: {missing}")
    if metadata["schemaVersion"] != CAPABILITY_METADATA_SCHEMA_VERSION:
        raise CapabilityContractError(f"Capability metadata schemaVersion must be {CAPABILITY_METADATA_SCHEMA_VERSION}")
    if metadata["name"] not in CAPABILITY_NAMES:
        raise CapabilityContractError(f"Unknown capability metadata name: {metadata['name']}")
    if metadata["permission"] not in CAPABILITY_PERMISSIONS:
        raise CapabilityContractError(f"Capability {metadata['name']} has invalid permission: {metadata['permission']}")
    if not isinstance(metadata["sideEffect"], bool):
        raise CapabilityContractError(f"Capability {metadata['name']} sideEffect must be boolean")
    if metadata["sideEffect"]:
        raise CapabilityContractError(f"Capability {metadata['name']} must not declare external side effects in Phase 3 MVP")
    if not isinstance(metadata["timeoutMs"], int) or metadata["timeoutMs"] <= 0:
        raise CapabilityContractError(f"Capability {metadata['name']} timeoutMs must be a positive integer")
    for schema_field in ["inputSchema", "outputSchema"]:
        value = metadata[schema_field]
        if not isinstance(value, dict) or not value:
            raise CapabilityContractError(f"Capability {metadata['name']} {schema_field} must be a non-empty object")


def validate_capability_envelope(envelope: dict[str, Any]) -> None:
    if envelope.get("schemaVersion") != CAPABILITY_ENVELOPE_SCHEMA_VERSION:
        raise CapabilityContractError(f"Capability envelope schemaVersion must be {CAPABILITY_ENVELOPE_SCHEMA_VERSION}")
    capabilities = envelope.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise CapabilityContractError("Capability envelope capabilities must be a non-empty list")

    by_name: dict[str, dict[str, Any]] = {}
    for metadata in capabilities:
        if not isinstance(metadata, dict):
            raise CapabilityContractError("Capability envelope entries must be objects")
        validate_capability_metadata(metadata)
        name = metadata["name"]
        if name in by_name:
            raise CapabilityContractError(f"Duplicate capability metadata: {name}")
        by_name[name] = metadata

    expected = set(CAPABILITY_NAMES)
    actual = set(by_name)
    if actual != expected:
        raise CapabilityContractError(f"Capability envelope names must be {sorted(expected)}, got {sorted(actual)}")

    for name, expected_metadata in _CAPABILITY_METADATA.items():
        actual_metadata = by_name[name]
        for field in ["permission", "sideEffect", "timeoutMs", "inputSchema", "outputSchema"]:
            if actual_metadata[field] != expected_metadata[field]:
                raise CapabilityContractError(f"Capability {name} {field} must equal the Phase 3 contract")

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


CAPABILITY_METADATA_SCHEMA_VERSION = "capability-metadata-v1"
CAPABILITY_ENVELOPE_SCHEMA_VERSION = "capability-envelope-v1"
CAPABILITY_CATALOG_SCHEMA_VERSION = "capability-catalog-v1"
CAPABILITY_CATALOG_ID = "phase3-readonly-regression-mvp"
CAPABILITY_URI_PREFIX = "capability://phase3/"

PERMISSIONS = {"read", "write", "dangerous"}
PHASE3_CAPABILITY_NAMES = ["read_log", "extract_regression_result", "write_artifact", "rule_verifier"]

CAPABILITY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "read_log": {
        "schemaVersion": CAPABILITY_METADATA_SCHEMA_VERSION,
        "name": "read_log",
        "permission": "read",
        "sideEffect": False,
        "timeoutMs": 1000,
        "inputContract": {
            "schema": "ReadLogInputV1",
            "required": ["sourcePath"],
            "properties": {"sourcePath": "string:path"},
        },
        "outputContract": {
            "schema": "ReadLogOutputV1",
            "produces": ["logTextRef"],
            "properties": {"logTextRef": "string:memory-ref"},
        },
    },
    "extract_regression_result": {
        "schemaVersion": CAPABILITY_METADATA_SCHEMA_VERSION,
        "name": "extract_regression_result",
        "permission": "read",
        "sideEffect": False,
        "timeoutMs": 1000,
        "inputContract": {
            "schema": "ExtractRegressionResultInputV1",
            "required": ["logTextRef", "taskSpecRef"],
            "properties": {
                "logTextRef": "string:memory-ref",
                "taskSpecRef": "string:run-json-pointer",
            },
        },
        "outputContract": {
            "schema": "ExtractRegressionResultOutputV1",
            "produces": ["evidenceItems", "regressionResultCandidate"],
            "properties": {
                "evidenceItems": "LogEvidenceV1[]",
                "regressionResultCandidate": "RegressionResultArtifactV1",
            },
        },
    },
    "write_artifact": {
        "schemaVersion": CAPABILITY_METADATA_SCHEMA_VERSION,
        "name": "write_artifact",
        "permission": "write",
        "sideEffect": False,
        "timeoutMs": 1000,
        "inputContract": {
            "schema": "WriteArtifactInputV1",
            "required": ["runRef", "evidenceRef", "regressionResultRef", "emailDraftRef"],
            "properties": {
                "runRef": "string:run-json-pointer",
                "evidenceRef": "string:artifact-ref",
                "regressionResultRef": "string:artifact-ref",
                "emailDraftRef": "string:artifact-ref",
            },
        },
        "outputContract": {
            "schema": "WriteArtifactOutputV1",
            "produces": ["artifactPaths"],
            "properties": {"artifactPaths": "string:path[]"},
            "effectBoundary": "local_artifact_output_only",
        },
    },
    "rule_verifier": {
        "schemaVersion": CAPABILITY_METADATA_SCHEMA_VERSION,
        "name": "rule_verifier",
        "permission": "read",
        "sideEffect": False,
        "timeoutMs": 1000,
        "inputContract": {
            "schema": "RuleVerifierInputV1",
            "required": ["taskSpecRef", "evidenceRef", "regressionResultRef", "emailDraftRef"],
            "properties": {
                "taskSpecRef": "string:run-json-pointer",
                "evidenceRef": "string:artifact-ref",
                "regressionResultRef": "string:artifact-ref",
                "emailDraftRef": "string:artifact-ref",
            },
        },
        "outputContract": {
            "schema": "RuleVerifierOutputV1",
            "produces": ["verifierReport"],
            "properties": {"verifierReport": "VerifierReportV1"},
        },
    },
}


def capability_ref(name: str) -> str:
    return f"{CAPABILITY_URI_PREFIX}{name}"


def capability_metadata(name: str) -> dict[str, Any]:
    if name not in CAPABILITY_DEFINITIONS:
        raise ValueError(f"Unknown Phase 3 capability: {name}")
    metadata = deepcopy(CAPABILITY_DEFINITIONS[name])
    metadata["ref"] = capability_ref(name)
    return metadata


def build_capability_envelope(names: list[str] | tuple[str, ...]) -> dict[str, Any]:
    return {
        "schemaVersion": CAPABILITY_ENVELOPE_SCHEMA_VERSION,
        "items": [capability_metadata(name) for name in names],
    }


def build_capability_catalog(names: list[str] | tuple[str, ...] = PHASE3_CAPABILITY_NAMES) -> dict[str, Any]:
    return {
        "schemaVersion": CAPABILITY_CATALOG_SCHEMA_VERSION,
        "id": CAPABILITY_CATALOG_ID,
        "description": "Static Phase 3 capability catalogue for the read-only regression evidence MVP.",
        "capabilities": [capability_metadata(name) for name in names],
    }


def validate_capability_metadata(metadata: dict[str, Any]) -> None:
    required_fields = [
        "schemaVersion",
        "name",
        "ref",
        "permission",
        "sideEffect",
        "timeoutMs",
        "inputContract",
        "outputContract",
    ]
    missing = [field for field in required_fields if field not in metadata]
    if missing:
        raise ValueError(f"Capability metadata is missing required fields: {missing}")

    name = metadata["name"]
    if name not in CAPABILITY_DEFINITIONS:
        raise ValueError(f"Capability metadata has unknown name: {name}")
    if metadata["schemaVersion"] != CAPABILITY_METADATA_SCHEMA_VERSION:
        raise ValueError(f"Capability {name} schemaVersion must be {CAPABILITY_METADATA_SCHEMA_VERSION}")
    if metadata["ref"] != capability_ref(name):
        raise ValueError(f"Capability {name} ref must be {capability_ref(name)}")
    if metadata["permission"] not in PERMISSIONS:
        raise ValueError(f"Capability {name} permission must be one of {sorted(PERMISSIONS)}")
    if metadata["permission"] != CAPABILITY_DEFINITIONS[name]["permission"]:
        raise ValueError(f"Capability {name} permission must be {CAPABILITY_DEFINITIONS[name]['permission']}")
    if not isinstance(metadata["sideEffect"], bool):
        raise ValueError(f"Capability {name} sideEffect must be boolean")
    if metadata["sideEffect"]:
        raise ValueError(f"Capability {name} must not declare external side effects in the read-only MVP")
    if not isinstance(metadata["timeoutMs"], int) or metadata["timeoutMs"] <= 0:
        raise ValueError(f"Capability {name} timeoutMs must be a positive integer")

    for field in ["inputContract", "outputContract"]:
        contract = metadata[field]
        if not isinstance(contract, dict) or not contract:
            raise ValueError(f"Capability {name} {field} must be a non-empty object")
        if "schema" not in contract or "required" not in contract and field == "inputContract":
            raise ValueError(f"Capability {name} {field} is missing schema or required fields")


def validate_capability_envelope(envelope: dict[str, Any], expected_names: list[str] | tuple[str, ...]) -> None:
    if envelope.get("schemaVersion") != CAPABILITY_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(f"Capability envelope schemaVersion must be {CAPABILITY_ENVELOPE_SCHEMA_VERSION}")
    items = envelope.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Capability envelope items must be a non-empty list")

    names = [item.get("name") for item in items if isinstance(item, dict)]
    if names != list(expected_names):
        raise ValueError(f"Capability envelope names must equal {list(expected_names)}")

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Capability envelope items must be objects")
        validate_capability_metadata(item)


def validate_capability_catalog(catalog: dict[str, Any], expected_names: list[str] | tuple[str, ...] = PHASE3_CAPABILITY_NAMES) -> None:
    if catalog.get("schemaVersion") != CAPABILITY_CATALOG_SCHEMA_VERSION:
        raise ValueError(f"Capability catalog schemaVersion must be {CAPABILITY_CATALOG_SCHEMA_VERSION}")
    if catalog.get("id") != CAPABILITY_CATALOG_ID:
        raise ValueError(f"Capability catalog id must be {CAPABILITY_CATALOG_ID}")
    capabilities = catalog.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("Capability catalog capabilities must be a non-empty list")

    names = [item.get("name") for item in capabilities if isinstance(item, dict)]
    if names != list(expected_names):
        raise ValueError(f"Capability catalog names must equal {list(expected_names)}")
    for item in capabilities:
        if not isinstance(item, dict):
            raise ValueError("Capability catalog capabilities must be objects")
        validate_capability_metadata(item)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="capability-catalog")
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    catalog = build_capability_catalog()
    validate_capability_catalog(catalog)
    if args.out:
        write_json(args.out, catalog)
        print(f"Wrote capability catalog {catalog['id']} to {args.out}.")
    else:
        print(json.dumps(catalog, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

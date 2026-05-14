"""TestExecutionTaskSpecV1 envelope contract.

This module defines the second workload-independent ``TaskSpecV1`` subtype,
covering the ``Test Execution / Failure Triage`` workload. The artifact must
remain a static, machine-verifiable contract: no test framework is executed,
no repository is mutated, no external communication is sent.

The envelope is intentionally generic: it must not reuse any
regression/email-specific TaskSpec fields, and it explicitly forbids
``regression_result``, ``email_draft``, ``send_email`` and
``regression-task-spec-v1`` so the Agentic Engineering OS kernel can host more
than one workload on the same coordination contracts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

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


TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION = "test-execution-task-spec-v1"
TASK_SPEC_ENVELOPE_SCHEMA_VERSION = "task-spec-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
TASK_SPEC_ID = "post-mvp-test-execution-failure-triage-task-spec"
TASK_SPEC_ARTIFACT_PATH = "artifacts/task_specs/post_mvp_test_execution_task_spec.json"

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"

INTENT = (
    "Collect deterministic evidence of a test execution outcome and produce "
    "a workload-independent failure triage artifact without modifying the "
    "repository or sending external communication."
)
GOAL = (
    "Given a recorded test execution result, classify the test run, attach "
    "evidence-backed failure triage findings, and write workload-independent "
    "artifacts that downstream coordination contracts can deliver."
)

ALLOWED_CAPABILITY_CLASSES = [
    "read_test_execution_result",
    "collect_test_failure_evidence",
    "classify_test_failure",
    "write_artifact",
]
FORBIDDEN_EFFECT_CLASSES = [
    "modify_repository_or_test_artifact",
    "execute_external_side_effect",
    "send_external_communication",
    "trigger_release_or_deployment",
    "call_gui_desktop_cua_or_browser_capability",
    "claim_passed_without_evidence",
]
REQUIRED_EVIDENCE = [
    "testRunIdentifier",
    "testFrameworkAndVersion",
    "testCaseIdentifier",
    "failureClassification",
    "stackTraceOrDiagnosticReference",
    "evidenceIdReferencedByArtifacts",
]
EXPECTED_ARTIFACT_KINDS = [
    "TestExecutionResultV1",
    "FailureTriageReportV1",
    "EvidenceListV1",
]
SUCCESS_CRITERIA = [
    "Read the recorded test execution result without modifying it.",
    "Extract a structured failure triage verdict bound to evidence ids.",
    "Write workload-independent artifacts without external side effects.",
    "Verify schema, evidence references, capability boundary, and forbidden effect classes.",
]
APPROVAL_POINTS = [
    "external_communication_requires_human_approval",
    "release_or_deployment_requires_human_approval",
]

VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERIFIER_VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

NON_REGRESSION_REUSE_PATH = [
    "test_execution_failure_triage",
    "code_patch_review_loop",
    "pr_review",
]
FORBIDDEN_REGRESSION_TASK_SPEC_FIELDS = [
    "regression_result",
    "regression_result.json",
    "email_draft",
    "email_draft.md",
    "send_email",
    "regression-task-spec-v1",
]

COORDINATION_BINDING_PATHS: dict[str, str] = {
    "delegationManifestRef": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creatorVerifierPairingRef": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agentMessageManifestRef": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiationRecordRef": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcastSubscriptionManifestRef": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

SOURCE_ROLE_TO_PATH: dict[str, str] = {
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}


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
            f"TestExecutionTaskSpecV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"TestExecutionTaskSpecV1 source artifact does not exist: {relative_path}"
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
                f"TestExecutionTaskSpecV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_coordination_artifacts(root: Path) -> None:
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


def build_test_execution_task_spec(root: Path) -> dict[str, Any]:
    _validate_referenced_coordination_artifacts(root)
    source_artifacts = [
        _artifact_source(role, relative_path, root)
        for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
    ]
    payload: dict[str, Any] = {
        "schemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "id": TASK_SPEC_ID,
        "generatedAt": GENERATED_AT,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "intent": INTENT,
        "goal": GOAL,
        "inputs": [
            {
                "id": "test_execution_result",
                "kind": "TestExecutionResultV1",
                "required": True,
                "description": "A recorded test execution result identifying framework, run id, and per-case outcomes.",
            },
            {
                "id": "failure_diagnostics",
                "kind": "DiagnosticBundleV1",
                "required": False,
                "description": "Optional diagnostic bundle (stack traces, logs) bound to the test execution result.",
            },
        ],
        "allowedCapabilityClasses": list(ALLOWED_CAPABILITY_CLASSES),
        "forbiddenEffectClasses": list(FORBIDDEN_EFFECT_CLASSES),
        "requiredEvidence": list(REQUIRED_EVIDENCE),
        "expectedArtifactKinds": list(EXPECTED_ARTIFACT_KINDS),
        "successCriteria": list(SUCCESS_CRITERIA),
        "approvalPoints": list(APPROVAL_POINTS),
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateEvidenceProvenance": True,
            "mustValidateCapabilityBoundary": True,
            "mustValidateForbiddenEffectClasses": True,
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
        "coordinationBinding": _coordination_binding(root),
        "regressionWorkloadIsolation": {
            "reusesRegressionTaskSpecFields": False,
            "reusesRegressionTaskSpecSchemaVersion": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_TASK_SPEC_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "sourceArtifacts": source_artifacts,
        "invariants": [
            "TestExecutionTaskSpecV1 is a TaskSpecV1 subtype distinct from RegressionTaskSpecV1.",
            "The TestExecutionTaskSpecV1 must not reuse regression/email TaskSpec fields.",
            "The TestExecutionTaskSpecV1 must bind all five coordination contracts by ref and content hash.",
            "The TestExecutionTaskSpecV1 must keep the verifier verdict owned by verifier-runtime-v1.",
            "The TestExecutionTaskSpecV1 must keep external side effects, communication, and repository mutation disabled.",
        ],
    }
    validate_test_execution_task_spec(payload, root)
    return payload


def validate_test_execution_task_spec(spec: dict[str, Any], root: Path) -> None:
    _require_fields(
        "TestExecutionTaskSpecV1",
        spec,
        [
            "schemaVersion",
            "taskSpecEnvelopeSchemaVersion",
            "id",
            "generatedAt",
            "workloadType",
            "workloadCategory",
            "intent",
            "goal",
            "inputs",
            "allowedCapabilityClasses",
            "forbiddenEffectClasses",
            "requiredEvidence",
            "expectedArtifactKinds",
            "successCriteria",
            "approvalPoints",
            "verifierExpectations",
            "policyBoundary",
            "coordinationBinding",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if spec["schemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"TestExecutionTaskSpecV1 schemaVersion must be {TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}"
        )
    if spec["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"TestExecutionTaskSpecV1 taskSpecEnvelopeSchemaVersion must be {TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if spec["id"] != TASK_SPEC_ID:
        raise ValueError(f"TestExecutionTaskSpecV1 id must be {TASK_SPEC_ID}")
    if spec["generatedAt"] != GENERATED_AT:
        raise ValueError(f"TestExecutionTaskSpecV1 generatedAt must be {GENERATED_AT}")
    if spec["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"TestExecutionTaskSpecV1 workloadType must be {WORKLOAD_TYPE}; "
            f"regression workload reuse is forbidden"
        )
    if spec["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"TestExecutionTaskSpecV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )

    for field in ["intent", "goal"]:
        value = spec[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"TestExecutionTaskSpecV1 {field} must be a non-empty string")

    inputs = spec["inputs"]
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("TestExecutionTaskSpecV1 inputs must be a non-empty list")
    seen_input_ids: set[str] = set()
    for entry in inputs:
        if not isinstance(entry, dict):
            raise ValueError("TestExecutionTaskSpecV1 inputs entries must be objects")
        _require_fields("TestExecutionTaskSpecV1 input", entry, ["id", "kind", "required", "description"])
        if not isinstance(entry["required"], bool):
            raise ValueError("TestExecutionTaskSpecV1 input.required must be a boolean")
        if entry["id"] in seen_input_ids:
            raise ValueError(f"TestExecutionTaskSpecV1 duplicate input id: {entry['id']}")
        seen_input_ids.add(entry["id"])

    exact_lists = {
        "allowedCapabilityClasses": ALLOWED_CAPABILITY_CLASSES,
        "forbiddenEffectClasses": FORBIDDEN_EFFECT_CLASSES,
        "requiredEvidence": REQUIRED_EVIDENCE,
        "expectedArtifactKinds": EXPECTED_ARTIFACT_KINDS,
        "successCriteria": SUCCESS_CRITERIA,
        "approvalPoints": APPROVAL_POINTS,
    }
    for field, expected in exact_lists.items():
        if spec[field] != expected:
            raise ValueError(f"TestExecutionTaskSpecV1 {field} must equal {expected}")

    verifier = spec["verifierExpectations"]
    _require_fields(
        "TestExecutionTaskSpecV1 verifierExpectations",
        verifier,
        [
            "mustValidateSchema",
            "mustValidateEvidenceProvenance",
            "mustValidateCapabilityBoundary",
            "mustValidateForbiddenEffectClasses",
            "mustEnforcePolicyBoundary",
            "verdictOwner",
            "verdictDomain",
            "creatorMustNotOwnVerdict",
        ],
    )
    for flag in [
        "mustValidateSchema",
        "mustValidateEvidenceProvenance",
        "mustValidateCapabilityBoundary",
        "mustValidateForbiddenEffectClasses",
        "mustEnforcePolicyBoundary",
        "creatorMustNotOwnVerdict",
    ]:
        if verifier[flag] is not True:
            raise ValueError(
                f"TestExecutionTaskSpecV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"TestExecutionTaskSpecV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != VERIFIER_VERDICT_DOMAIN:
        raise ValueError(
            f"TestExecutionTaskSpecV1 verifierExpectations.verdictDomain must equal {VERIFIER_VERDICT_DOMAIN}"
        )

    policy = spec["policyBoundary"]
    required_policy_flags = [
        "externalSideEffectsAllowed",
        "repositoryMutationAllowed",
        "externalCommunicationAllowed",
        "releaseOrDeploymentAllowed",
        "guiOrBrowserOrDesktopCallAllowed",
        "publicAccessAllowed",
    ]
    _require_fields("TestExecutionTaskSpecV1 policyBoundary", policy, required_policy_flags)
    for flag in required_policy_flags:
        if policy[flag] is not False:
            raise ValueError(
                f"TestExecutionTaskSpecV1 policyBoundary.{flag} must be false"
            )

    coordination = spec["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            "TestExecutionTaskSpecV1 coordinationBinding must include "
            f"{sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"TestExecutionTaskSpecV1 coordinationBinding.{field} must equal {expected_path}"
            )

    isolation = spec["regressionWorkloadIsolation"]
    _require_fields(
        "TestExecutionTaskSpecV1 regressionWorkloadIsolation",
        isolation,
        ["reusesRegressionTaskSpecFields", "reusesRegressionTaskSpecSchemaVersion", "forbiddenFields"],
    )
    if isolation["reusesRegressionTaskSpecFields"] is not False:
        raise ValueError(
            "TestExecutionTaskSpecV1 must not reuse regression TaskSpec fields"
        )
    if isolation["reusesRegressionTaskSpecSchemaVersion"] is not False:
        raise ValueError(
            "TestExecutionTaskSpecV1 must not reuse regression-task-spec-v1 schema version"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_TASK_SPEC_FIELDS:
        raise ValueError(
            "TestExecutionTaskSpecV1 forbiddenFields must equal "
            f"{FORBIDDEN_REGRESSION_TASK_SPEC_FIELDS}"
        )

    # Defensive scan: no regression/email-specific markers anywhere in the spec.
    serialized = json.dumps(spec, sort_keys=True)
    isolation_terms = {
        "regression_result",
        "regression_result.json",
        "email_draft",
        "email_draft.md",
        "send_email",
        "regression-task-spec-v1",
    }
    for term in isolation_terms:
        if term in FORBIDDEN_REGRESSION_TASK_SPEC_FIELDS:
            # Allowed only inside the declarative forbiddenFields list.
            allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_TASK_SPEC_FIELDS if value == term)
            if serialized.count(f'"{term}"') > allowed_count:
                raise ValueError(
                    f"TestExecutionTaskSpecV1 must not embed regression/email field {term} outside forbiddenFields"
                )

    reuse_path = spec["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"TestExecutionTaskSpecV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    sources = spec["sourceArtifacts"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("TestExecutionTaskSpecV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("TestExecutionTaskSpecV1 sourceArtifacts entries must be objects")
        _require_fields(
            "TestExecutionTaskSpecV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"TestExecutionTaskSpecV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"TestExecutionTaskSpecV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"TestExecutionTaskSpecV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(
                f"TestExecutionTaskSpecV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(
                f"TestExecutionTaskSpecV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"TestExecutionTaskSpecV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )

    invariants = spec["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 5:
        raise ValueError(
            "TestExecutionTaskSpecV1 invariants must declare at least five workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="test-execution-task-spec")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        spec = build_test_execution_task_spec(root)
        _write_json(args.out, spec)
        print(f"Wrote TestExecutionTaskSpecV1 artifact to {args.out}.")
    if args.validate is not None:
        spec = _load_json(args.validate)
        validate_test_execution_task_spec(spec, root)
        print(f"Validated TestExecutionTaskSpecV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

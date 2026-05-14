"""CapabilityManifestV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``CapabilityManifestV1`` ArtifactV1
subtype. It declares the runtime capability primitives the OS kernel exposes
for the ``Test Execution / Failure Triage`` workload (the second workload of
the Agentic Engineering OS) without executing any real test framework, runner,
classifier, or summarizer.

The artifact answers four OS-kernel invariants at once:

- ``Capability`` primitive: every capability has a workload-independent
  ``name``, ``permission``, ``sideEffect``, ``timeoutMs``,
  ``inputContract``, ``outputContract``, ``allowedEffectClasses``,
  ``forbiddenEffectClasses``, ``evidenceContract`` and
  ``verifierExpectations``. The fields do not reference regression or
  email-specific schemas and can be reused by Code Patch / Review Loop,
  PR Review, Documentation Update, and other engineering workloads.
- ``Artifact`` envelope reuse: the manifest is an ``ArtifactV1`` subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) that joins
  ``RegressionResultArtifactV1`` / ``TestExecutionResultV1`` /
  ``FailureTriageReportV1`` / ``VerifierResultV1`` as a fifth subtype of the
  same envelope.
- ``TaskSpec`` binding: the manifest pins the upstream
  ``TestExecutionTaskSpecV1`` envelope by content hash. Every declared
  capability is cross-checked against
  ``TestExecutionTaskSpecV1.allowedCapabilityClasses`` and
  ``TestExecutionTaskSpecV1.forbiddenEffectClasses`` so the manifest never
  authorizes a capability the task spec does not allow and never declares a
  forbidden effect class.
- ``Verifier`` ownership: the creator must not own the verdict;
  ``verifierVerdictOwner`` is ``verifier-runtime-v1`` and
  ``creatorMustNotOwnVerdict`` is ``true``.

Key invariants this module enforces:

- The manifest is an ``ArtifactV1`` envelope subtype distinct from every
  creator-owned or verifier-owned test_execution_failure_triage subtype;
  ``schemaVersion`` is ``capability-manifest-v1`` and ``kind`` is
  ``CapabilityManifestV1``.
- The manifest binds the bound ``TestExecutionTaskSpecV1`` envelope plus all
  five coordination contracts by content hash, so a drift in any upstream
  artifact invalidates the manifest.
- Each capability declares a workload-independent permission
  (``read`` / ``write`` / ``dangerous``), an explicit ``sideEffect`` boolean,
  a positive ``timeoutMs`` integer, an ``inputContract`` and ``outputContract``
  with stable schema ids, an ``allowedEffectClasses`` list drawn from the
  workload-independent effect catalogue, and a
  ``forbiddenEffectClasses`` list that mirrors the bound task spec.
- Every declared capability name must be present in
  ``TestExecutionTaskSpecV1.allowedCapabilityClasses`` and the set of bound
  capability names must equal that allow-list. No capability may declare an
  effect class that intersects
  ``TestExecutionTaskSpecV1.forbiddenEffectClasses``.
- The artifact carries no external side effects, no repository mutation, no
  GUI / browser / desktop call, no public access, and no delivery.

The artifact is fully self-contained (synthetic capability metadata) so it
remains deterministic across Linux / macOS / Windows and requires no real
runtime to validate.
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
from test_execution_task_spec import (
    TASK_SPEC_ARTIFACT_PATH as TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
    TASK_SPEC_ID as TEST_EXECUTION_TASK_SPEC_ID,
    TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
    validate_test_execution_task_spec,
)


CAPABILITY_MANIFEST_SCHEMA_VERSION = "capability-manifest-v1"
CAPABILITY_DEFINITION_SCHEMA_VERSION = "capability-definition-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "CapabilityManifestV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-capability-manifest-kernel-contract"
CAPABILITY_MANIFEST_ARTIFACT_PATH = (
    "artifacts/capabilities/post_mvp_test_execution_capability_manifest.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_capability_manifest_contract"

CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERIFIER_VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

PERMISSIONS = ["read", "write", "dangerous"]

EFFECT_CLASS_DOMAIN = [
    "read_test_execution_result",
    "collect_test_failure_evidence",
    "classify_test_failure",
    "write_local_artifact",
    "modify_repository_or_test_artifact",
    "execute_external_side_effect",
    "send_external_communication",
    "trigger_release_or_deployment",
    "call_gui_desktop_cua_or_browser_capability",
    "claim_passed_without_evidence",
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
    "mustValidateCapabilityBoundary",
    "mustValidateForbiddenEffectClasses",
    "mustValidatePermissionAndSideEffect",
    "mustEnforcePolicyBoundary",
    "creatorMustNotOwnVerdict",
]

CAPABILITY_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "read_test_execution_result",
        "permission": "read",
        "sideEffect": False,
        "timeoutMs": 1000,
        "description": (
            "Read a recorded TestExecutionResultV1 artifact by content hash "
            "without modifying it."
        ),
        "inputContract": {
            "schema": "ReadTestExecutionResultInputV1",
            "required": ["testExecutionResultRef"],
            "properties": {
                "testExecutionResultRef": "string:artifact-ref",
            },
        },
        "outputContract": {
            "schema": "ReadTestExecutionResultOutputV1",
            "produces": ["testExecutionResultRef", "evidenceListRef"],
            "properties": {
                "testExecutionResultRef": "string:memory-ref",
                "evidenceListRef": "string:memory-ref",
            },
        },
        "allowedEffectClasses": ["read_test_execution_result"],
        "evidenceContract": {
            "producesEvidence": False,
            "consumesEvidenceKinds": [
                "test_case_outcome_record",
                "stack_trace_record",
            ],
        },
    },
    {
        "name": "collect_test_failure_evidence",
        "permission": "read",
        "sideEffect": False,
        "timeoutMs": 2000,
        "description": (
            "Read referenced diagnostic bundles bound to TestExecutionResultV1 "
            "evidence ids without modifying any artifact or repository file."
        ),
        "inputContract": {
            "schema": "CollectTestFailureEvidenceInputV1",
            "required": ["testExecutionResultRef", "caseId"],
            "properties": {
                "testExecutionResultRef": "string:artifact-ref",
                "caseId": "string:test-case-id",
            },
        },
        "outputContract": {
            "schema": "CollectTestFailureEvidenceOutputV1",
            "produces": ["evidenceRefs", "diagnosticRefs"],
            "properties": {
                "evidenceRefs": "string:memory-ref[]",
                "diagnosticRefs": "string:memory-ref[]",
            },
        },
        "allowedEffectClasses": ["collect_test_failure_evidence"],
        "evidenceContract": {
            "producesEvidence": False,
            "consumesEvidenceKinds": [
                "test_case_outcome_record",
                "stack_trace_record",
            ],
        },
    },
    {
        "name": "classify_test_failure",
        "permission": "read",
        "sideEffect": False,
        "timeoutMs": 2000,
        "description": (
            "Classify a failed test case using only its bound evidence and "
            "diagnostic refs. The output is a candidate failure classification; "
            "the verifier owns the final verdict."
        ),
        "inputContract": {
            "schema": "ClassifyTestFailureInputV1",
            "required": ["testExecutionResultRef", "caseId"],
            "properties": {
                "testExecutionResultRef": "string:artifact-ref",
                "caseId": "string:test-case-id",
            },
        },
        "outputContract": {
            "schema": "ClassifyTestFailureOutputV1",
            "produces": ["failureClassificationCandidate", "supportingEvidenceIds"],
            "properties": {
                "failureClassificationCandidate": "string:test-failure-classification",
                "supportingEvidenceIds": "string:evidence-id[]",
            },
        },
        "allowedEffectClasses": [
            "classify_test_failure",
            "collect_test_failure_evidence",
        ],
        "evidenceContract": {
            "producesEvidence": False,
            "consumesEvidenceKinds": [
                "test_case_outcome_record",
                "stack_trace_record",
            ],
        },
    },
    {
        "name": "write_artifact",
        "permission": "write",
        "sideEffect": False,
        "timeoutMs": 1000,
        "description": (
            "Write the workload-independent artifact bundle "
            "(TestExecutionResultV1, FailureTriageReportV1, VerifierResultV1) to "
            "the local artifact directory only. External side effects are not "
            "permitted; the verifier owns the acceptance verdict."
        ),
        "inputContract": {
            "schema": "WriteArtifactInputV1",
            "required": [
                "testExecutionResultRef",
                "failureTriageReportRef",
                "verifierResultRef",
            ],
            "properties": {
                "testExecutionResultRef": "string:artifact-ref",
                "failureTriageReportRef": "string:artifact-ref",
                "verifierResultRef": "string:artifact-ref",
            },
        },
        "outputContract": {
            "schema": "WriteArtifactOutputV1",
            "produces": ["artifactPaths"],
            "properties": {
                "artifactPaths": "string:path[]",
            },
            "effectBoundary": "local_artifact_output_only",
        },
        "allowedEffectClasses": ["write_local_artifact"],
        "evidenceContract": {
            "producesEvidence": False,
            "consumesEvidenceKinds": [],
        },
    },
]

CAPABILITY_NAMES = [definition["name"] for definition in CAPABILITY_DEFINITIONS]

INVARIANTS = [
    "CapabilityManifestV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype.",
    "CapabilityManifestV1 must bind the TestExecutionTaskSpecV1 envelope and all five coordination contracts by content hash.",
    "CapabilityManifestV1 must declare every capability with a workload-independent permission, sideEffect, timeoutMs, input/output contract, and effect class set.",
    "CapabilityManifestV1 capability names must equal TestExecutionTaskSpecV1.allowedCapabilityClasses; no capability may declare a TestExecutionTaskSpecV1 forbidden effect class.",
    "CapabilityManifestV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance.",
    "CapabilityManifestV1 must keep external side effects, repository mutation, external communication, GUI/desktop access, public access, and release/deployment disabled.",
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
            f"CapabilityManifestV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"CapabilityManifestV1 source artifact does not exist: {relative_path}"
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
                f"CapabilityManifestV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> dict[str, Any]:
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
    return task_spec


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"CapabilityManifestV1 taskSpecBinding requires artifact: {relative_path}"
        )
    return {
        "taskSpecRef": relative_path,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecContentHash": _stable_file_hash(full_path),
    }


def _build_capabilities(task_spec: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = list(task_spec["allowedCapabilityClasses"])
    forbidden = set(task_spec["forbiddenEffectClasses"])
    if set(CAPABILITY_NAMES) != set(allowed):
        raise ValueError(
            "CapabilityManifestV1 capability names must equal "
            "TestExecutionTaskSpecV1.allowedCapabilityClasses"
        )
    capabilities: list[dict[str, Any]] = []
    for definition in CAPABILITY_DEFINITIONS:
        if definition["name"] not in allowed:
            raise ValueError(
                f"CapabilityManifestV1 capability {definition['name']} is not in "
                f"TestExecutionTaskSpecV1.allowedCapabilityClasses"
            )
        forbidden_intersection = forbidden & set(definition["allowedEffectClasses"])
        if forbidden_intersection:
            raise ValueError(
                f"CapabilityManifestV1 capability {definition['name']} declares "
                f"forbidden effect classes: {sorted(forbidden_intersection)}"
            )
        capability = {
            "schemaVersion": CAPABILITY_DEFINITION_SCHEMA_VERSION,
            "ref": f"capability://post-mvp/test_execution/{definition['name']}",
            **definition,
            "forbiddenEffectClasses": sorted(forbidden),
            "evidenceContract": dict(definition["evidenceContract"]),
        }
        capabilities.append(capability)
    return capabilities


def build_capability_manifest(root: Path) -> dict[str, Any]:
    task_spec = _validate_referenced_artifacts(root)
    capabilities = _build_capabilities(task_spec)
    source_artifacts = [
        _artifact_source(role, relative_path, root)
        for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
    ]
    payload: dict[str, Any] = {
        "schemaVersion": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "taskSpecBinding": _build_task_spec_binding(root),
        "capabilities": capabilities,
        "permissionDomain": list(PERMISSIONS),
        "effectClassDomain": list(EFFECT_CLASS_DOMAIN),
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateTaskSpecBinding": True,
            "mustValidateCapabilityBoundary": True,
            "mustValidateForbiddenEffectClasses": True,
            "mustValidatePermissionAndSideEffect": True,
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
        "regressionWorkloadIsolation": {
            "reusesRegressionCapabilityCatalog": False,
            "reusesRegressionResultArtifact": False,
            "reusesEmailDraftArtifact": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "coordinationBinding": _coordination_binding(root),
        "sourceArtifacts": source_artifacts,
        "invariants": list(INVARIANTS),
    }
    validate_capability_manifest(payload, root)
    return payload


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "CapabilityManifestV1 taskSpecBinding",
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
            f"CapabilityManifestV1 taskSpecBinding.taskSpecRef must equal "
            f"{TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"CapabilityManifestV1 taskSpecBinding.taskSpecSchemaVersion must equal "
            f"{TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"CapabilityManifestV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal "
            f"{TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"CapabilityManifestV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"CapabilityManifestV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["taskSpecContentHash"] != expected_hash:
        raise ValueError(
            "CapabilityManifestV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capabilities(
    capabilities: list[Any],
    task_spec: dict[str, Any],
) -> None:
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("CapabilityManifestV1 capabilities must be a non-empty list")
    allowed = list(task_spec["allowedCapabilityClasses"])
    forbidden = set(task_spec["forbiddenEffectClasses"])
    seen_names: list[str] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("CapabilityManifestV1 capabilities entries must be objects")
        _require_fields(
            "CapabilityManifestV1 capability",
            capability,
            [
                "schemaVersion",
                "ref",
                "name",
                "permission",
                "sideEffect",
                "timeoutMs",
                "description",
                "inputContract",
                "outputContract",
                "allowedEffectClasses",
                "forbiddenEffectClasses",
                "evidenceContract",
            ],
        )
        if capability["schemaVersion"] != CAPABILITY_DEFINITION_SCHEMA_VERSION:
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} schemaVersion must be "
                f"{CAPABILITY_DEFINITION_SCHEMA_VERSION}"
            )
        if capability["ref"] != f"capability://post-mvp/test_execution/{capability['name']}":
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} ref must be "
                f"capability://post-mvp/test_execution/{capability['name']}"
            )
        if capability["name"] in seen_names:
            raise ValueError(
                f"CapabilityManifestV1 duplicate capability name: {capability['name']}"
            )
        seen_names.append(capability["name"])
        if capability["name"] not in allowed:
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} is not in "
                f"TestExecutionTaskSpecV1.allowedCapabilityClasses"
            )
        if capability["permission"] not in PERMISSIONS:
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} permission must be one of {PERMISSIONS}"
            )
        if capability["sideEffect"] is not True and capability["sideEffect"] is not False:
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} sideEffect must be a boolean"
            )
        if capability["sideEffect"] is True:
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} sideEffect must be false; "
                f"the MVP capability boundary disallows side-effecting capabilities"
            )
        if (
            not isinstance(capability["timeoutMs"], int)
            or isinstance(capability["timeoutMs"], bool)
            or capability["timeoutMs"] <= 0
        ):
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} timeoutMs must be a positive integer"
            )
        if not isinstance(capability["description"], str) or len(capability["description"].strip()) < 16:
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} description must be a substantive string"
            )
        for contract_key in ("inputContract", "outputContract"):
            contract = capability[contract_key]
            if not isinstance(contract, dict):
                raise ValueError(
                    f"CapabilityManifestV1 capability {capability['name']} {contract_key} must be an object"
                )
            _require_fields(
                f"CapabilityManifestV1 capability {capability['name']} {contract_key}",
                contract,
                ["schema", "properties"],
            )
            if not isinstance(contract["schema"], str) or not contract["schema"].strip():
                raise ValueError(
                    f"CapabilityManifestV1 capability {capability['name']} {contract_key}.schema must be a non-empty string"
                )
            if not isinstance(contract["properties"], dict) or not contract["properties"]:
                raise ValueError(
                    f"CapabilityManifestV1 capability {capability['name']} {contract_key}.properties must be a non-empty object"
                )
        allowed_effects = capability["allowedEffectClasses"]
        if not isinstance(allowed_effects, list) or not allowed_effects:
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} allowedEffectClasses must be a non-empty list"
            )
        for effect in allowed_effects:
            if effect not in EFFECT_CLASS_DOMAIN:
                raise ValueError(
                    f"CapabilityManifestV1 capability {capability['name']} allowedEffectClasses contains unknown effect: {effect}"
                )
        intersection = forbidden & set(allowed_effects)
        if intersection:
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} declares "
                f"forbidden effect classes: {sorted(intersection)}"
            )
        forbidden_effects = capability["forbiddenEffectClasses"]
        if not isinstance(forbidden_effects, list) or forbidden_effects != sorted(forbidden):
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} forbiddenEffectClasses must equal "
                f"sorted(TestExecutionTaskSpecV1.forbiddenEffectClasses)"
            )
        evidence_contract = capability["evidenceContract"]
        if not isinstance(evidence_contract, dict):
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} evidenceContract must be an object"
            )
        _require_fields(
            f"CapabilityManifestV1 capability {capability['name']} evidenceContract",
            evidence_contract,
            ["producesEvidence", "consumesEvidenceKinds"],
        )
        if (
            evidence_contract["producesEvidence"] is not True
            and evidence_contract["producesEvidence"] is not False
        ):
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} evidenceContract.producesEvidence must be a boolean"
            )
        if not isinstance(evidence_contract["consumesEvidenceKinds"], list):
            raise ValueError(
                f"CapabilityManifestV1 capability {capability['name']} evidenceContract.consumesEvidenceKinds must be a list"
            )
    if seen_names != allowed:
        raise ValueError(
            "CapabilityManifestV1 capability names must equal "
            f"TestExecutionTaskSpecV1.allowedCapabilityClasses in order: {allowed}"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("CapabilityManifestV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("CapabilityManifestV1 sourceArtifacts entries must be objects")
        _require_fields(
            "CapabilityManifestV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"CapabilityManifestV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"CapabilityManifestV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"CapabilityManifestV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"CapabilityManifestV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"CapabilityManifestV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"CapabilityManifestV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_capability_manifest(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "CapabilityManifestV1",
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
            "taskSpecBinding",
            "capabilities",
            "permissionDomain",
            "effectClassDomain",
            "verifierExpectations",
            "policyBoundary",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"CapabilityManifestV1 schemaVersion must be {CAPABILITY_MANIFEST_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"CapabilityManifestV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"CapabilityManifestV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"CapabilityManifestV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"CapabilityManifestV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"CapabilityManifestV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"CapabilityManifestV1 workloadType must be {WORKLOAD_TYPE}; "
            f"regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"CapabilityManifestV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(
            f"CapabilityManifestV1 creatorAgent must be {CREATOR_AGENT}"
        )
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"CapabilityManifestV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; "
            f"creator must not own the verdict"
        )

    _validate_task_spec_binding(manifest["taskSpecBinding"], root)
    task_spec = _load_json(root / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH)
    validate_test_execution_task_spec(task_spec, root)
    _validate_capabilities(manifest["capabilities"], task_spec)

    if manifest["permissionDomain"] != PERMISSIONS:
        raise ValueError(
            f"CapabilityManifestV1 permissionDomain must equal {PERMISSIONS}"
        )
    if manifest["effectClassDomain"] != EFFECT_CLASS_DOMAIN:
        raise ValueError(
            f"CapabilityManifestV1 effectClassDomain must equal {EFFECT_CLASS_DOMAIN}"
        )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "CapabilityManifestV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"CapabilityManifestV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"CapabilityManifestV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != VERIFIER_VERDICT_DOMAIN:
        raise ValueError(
            f"CapabilityManifestV1 verifierExpectations.verdictDomain must equal {VERIFIER_VERDICT_DOMAIN}"
        )

    policy = manifest["policyBoundary"]
    _require_fields(
        "CapabilityManifestV1 policyBoundary", policy, REQUIRED_POLICY_FLAGS
    )
    for flag in REQUIRED_POLICY_FLAGS:
        if policy[flag] is not False:
            raise ValueError(
                f"CapabilityManifestV1 policyBoundary.{flag} must be false"
            )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "CapabilityManifestV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionCapabilityCatalog",
            "reusesRegressionResultArtifact",
            "reusesEmailDraftArtifact",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionCapabilityCatalog"] is not False:
        raise ValueError(
            "CapabilityManifestV1 must not reuse the phase3 regression capability catalog"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "CapabilityManifestV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesEmailDraftArtifact"] is not False:
        raise ValueError(
            "CapabilityManifestV1 must not reuse EmailDraftArtifactV1"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"CapabilityManifestV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"CapabilityManifestV1 must not embed regression/email field {term} "
                f"outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"CapabilityManifestV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            "CapabilityManifestV1 coordinationBinding must include "
            f"{sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"CapabilityManifestV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 5:
        raise ValueError(
            "CapabilityManifestV1 invariants must declare at least five workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="capability-manifest")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_capability_manifest(root)
        _write_json(args.out, manifest)
        print(f"Wrote CapabilityManifestV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_capability_manifest(manifest, root)
        print(f"Validated CapabilityManifestV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

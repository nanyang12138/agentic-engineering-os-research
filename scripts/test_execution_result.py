"""TestExecutionResultV1 ArtifactV1 subtype contract.

This module defines the first workload-independent ``ArtifactV1`` subtype for the
``Test Execution / Failure Triage`` workload. The artifact is a creator output
that records a deterministic, fixture-style test execution result and binds the
upstream ``TestExecutionTaskSpecV1`` envelope plus the five Agent Coordination
Layer contracts (Delegation / CreatorVerifierPairing / AgentMessageManifest /
NegotiationRecord / BroadcastSubscriptionManifest).

Key invariants this module enforces:

- The artifact is an ``ArtifactV1`` envelope subtype distinct from
  ``RegressionResultArtifactV1``; it must not reuse regression / email-specific
  fields and must keep the verifier verdict owned by ``verifier-runtime-v1``.
- Every test case status must be backed by at least one evidence record bound
  by content hash so verification can replay the result without trusting the
  creator agent.
- All upstream contracts are pinned by content hash so a drift in any
  coordination / task spec contract invalidates this artifact.
- The artifact carries no external side effects, no repository mutation, no
  GUI / browser / desktop call, no public access, and no delivery.

The artifact is fully self-contained (synthetic test execution data is embedded
inline) so it remains deterministic across Linux / macOS / Windows and does not
require any real test framework to run.
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


TEST_EXECUTION_RESULT_SCHEMA_VERSION = "test-execution-result-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "TestExecutionResultV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-result-kernel-contract"
TEST_EXECUTION_RESULT_ARTIFACT_PATH = (
    "artifacts/test_execution/post_mvp_test_execution_result.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_artifact_contract"
CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERIFIER_VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

CASE_STATUSES = ["passed", "failed", "skipped", "error"]

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

SYNTHETIC_FRAMEWORK = {
    "name": "synthetic_workload_independent_test_runner",
    "version": "0.1.0",
}
SYNTHETIC_RUN_ID = "post-mvp-synthetic-test-run-001"

REQUIRED_VERIFIER_FLAGS = [
    "mustValidateSchema",
    "mustValidateEvidenceProvenance",
    "mustValidateCaseEvidenceCoverage",
    "mustValidateCapabilityBoundary",
    "mustValidateForbiddenEffectClasses",
    "mustEnforcePolicyBoundary",
    "creatorMustNotOwnVerdict",
]
REQUIRED_POLICY_FLAGS = [
    "externalSideEffectsAllowed",
    "repositoryMutationAllowed",
    "externalCommunicationAllowed",
    "releaseOrDeploymentAllowed",
    "guiOrBrowserOrDesktopCallAllowed",
    "publicAccessAllowed",
]

INVARIANTS = [
    "TestExecutionResultV1 is an ArtifactV1 subtype distinct from RegressionResultArtifactV1.",
    "TestExecutionResultV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance.",
    "TestExecutionResultV1 must bind the TestExecutionTaskSpecV1 envelope and all five coordination contracts by content hash.",
    "TestExecutionResultV1 must keep external side effects, repository mutation, and external communication disabled.",
    "TestExecutionResultV1 must back every test case status with at least one evidence record bound by content hash.",
]


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
    if (
        not isinstance(path, str)
        or not path
        or Path(path).is_absolute()
        or "\\" in path
        or path.startswith("../")
        or "/../" in path
    ):
        raise ValueError(
            f"TestExecutionResultV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"TestExecutionResultV1 source artifact does not exist: {relative_path}"
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
                f"TestExecutionResultV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> None:
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


def _build_evidence_records() -> list[dict[str, Any]]:
    records = [
        {
            "id": "ev-case-001-outcome",
            "kind": "test_case_outcome_record",
            "caseId": "case-001",
            "payload": "case_id=case-001 name=synthetic.module.test_pass status=passed",
        },
        {
            "id": "ev-case-002-outcome",
            "kind": "test_case_outcome_record",
            "caseId": "case-002",
            "payload": "case_id=case-002 name=synthetic.module.test_fail status=failed",
        },
        {
            "id": "ev-case-002-trace",
            "kind": "stack_trace_record",
            "caseId": "case-002",
            "payload": (
                "AssertionError: expected 1 == 2\n"
                "  at synthetic.module.test_fail (synthetic/module.py:42)"
            ),
        },
        {
            "id": "ev-case-003-outcome",
            "kind": "test_case_outcome_record",
            "caseId": "case-003",
            "payload": "case_id=case-003 name=synthetic.module.test_skipped status=skipped reason=needs_environment",
        },
    ]
    for record in records:
        record["contentHash"] = _stable_text_hash(record["payload"])
    return records


def _build_diagnostics() -> list[dict[str, Any]]:
    return [
        {
            "id": "diag-case-002-stack-trace",
            "caseId": "case-002",
            "kind": "stack_trace_diagnostic",
            "evidenceIds": ["ev-case-002-trace"],
        }
    ]


def _build_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "case-001",
            "name": "synthetic.module.test_pass",
            "status": "passed",
            "durationMs": 12,
            "evidenceIds": ["ev-case-001-outcome"],
            "failureClassification": None,
            "diagnosticRefs": [],
        },
        {
            "id": "case-002",
            "name": "synthetic.module.test_fail",
            "status": "failed",
            "durationMs": 47,
            "evidenceIds": ["ev-case-002-outcome", "ev-case-002-trace"],
            "failureClassification": "assertion_error",
            "diagnosticRefs": ["diag-case-002-stack-trace"],
        },
        {
            "id": "case-003",
            "name": "synthetic.module.test_skipped",
            "status": "skipped",
            "durationMs": 0,
            "evidenceIds": ["ev-case-003-outcome"],
            "failureClassification": None,
            "diagnosticRefs": [],
        },
    ]


def _build_summary(cases: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "totalCases": len(cases),
        "passedCases": sum(1 for case in cases if case["status"] == "passed"),
        "failedCases": sum(1 for case in cases if case["status"] == "failed"),
        "skippedCases": sum(1 for case in cases if case["status"] == "skipped"),
        "errorCases": sum(1 for case in cases if case["status"] == "error"),
    }


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"TestExecutionResultV1 taskSpecBinding requires artifact: {relative_path}"
        )
    return {
        "taskSpecRef": relative_path,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecContentHash": _stable_file_hash(full_path),
    }


def build_test_execution_result(root: Path) -> dict[str, Any]:
    _validate_referenced_artifacts(root)
    cases = _build_cases()
    evidence = _build_evidence_records()
    diagnostics = _build_diagnostics()
    summary = _build_summary(cases)
    source_artifacts = [
        _artifact_source(role, relative_path, root)
        for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
    ]
    payload: dict[str, Any] = {
        "schemaVersion": TEST_EXECUTION_RESULT_SCHEMA_VERSION,
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
        "framework": dict(SYNTHETIC_FRAMEWORK),
        "runIdentifier": SYNTHETIC_RUN_ID,
        "summary": summary,
        "cases": cases,
        "evidenceList": evidence,
        "diagnostics": diagnostics,
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateEvidenceProvenance": True,
            "mustValidateCaseEvidenceCoverage": True,
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
        "regressionWorkloadIsolation": {
            "reusesRegressionResultArtifact": False,
            "reusesEmailDraftArtifact": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "coordinationBinding": _coordination_binding(root),
        "sourceArtifacts": source_artifacts,
        "invariants": list(INVARIANTS),
    }
    validate_test_execution_result(payload, root)
    return payload


def _validate_summary(summary: dict[str, Any], cases: list[dict[str, Any]]) -> None:
    expected = _build_summary(cases)
    if summary != expected:
        raise ValueError(
            f"TestExecutionResultV1 summary must equal computed counts {expected}; got {summary}"
        )
    if summary["totalCases"] != len(cases):
        raise ValueError(
            "TestExecutionResultV1 summary.totalCases must equal len(cases)"
        )


def _validate_cases(cases: list[dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]],
                    diagnostics_by_id: dict[str, dict[str, Any]]) -> None:
    if not isinstance(cases, list) or not cases:
        raise ValueError("TestExecutionResultV1 cases must be a non-empty list")
    seen_case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("TestExecutionResultV1 cases entries must be objects")
        _require_fields(
            "TestExecutionResultV1 case",
            case,
            [
                "id",
                "name",
                "status",
                "durationMs",
                "evidenceIds",
                "failureClassification",
                "diagnosticRefs",
            ],
        )
        case_id = case["id"]
        if case_id in seen_case_ids:
            raise ValueError(f"TestExecutionResultV1 duplicate case id: {case_id}")
        seen_case_ids.add(case_id)
        if case["status"] not in CASE_STATUSES:
            raise ValueError(
                f"TestExecutionResultV1 case {case_id} status must be one of {CASE_STATUSES}"
            )
        if not isinstance(case["durationMs"], int) or case["durationMs"] < 0:
            raise ValueError(
                f"TestExecutionResultV1 case {case_id} durationMs must be a non-negative integer"
            )
        evidence_ids = case["evidenceIds"]
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ValueError(
                f"TestExecutionResultV1 case {case_id} must reference at least one evidence id"
            )
        for evidence_id in evidence_ids:
            if evidence_id not in evidence_by_id:
                raise ValueError(
                    f"TestExecutionResultV1 case {case_id} references unknown evidence id: {evidence_id}"
                )
            if evidence_by_id[evidence_id]["caseId"] != case_id:
                raise ValueError(
                    f"TestExecutionResultV1 case {case_id} references evidence {evidence_id} "
                    f"that belongs to another case"
                )
        diagnostic_refs = case["diagnosticRefs"]
        if not isinstance(diagnostic_refs, list):
            raise ValueError(
                f"TestExecutionResultV1 case {case_id} diagnosticRefs must be a list"
            )
        for diag_ref in diagnostic_refs:
            if diag_ref not in diagnostics_by_id:
                raise ValueError(
                    f"TestExecutionResultV1 case {case_id} references unknown diagnostic: {diag_ref}"
                )
            if diagnostics_by_id[diag_ref]["caseId"] != case_id:
                raise ValueError(
                    f"TestExecutionResultV1 case {case_id} references diagnostic {diag_ref} "
                    f"that belongs to another case"
                )
        if case["status"] == "failed":
            if not case["failureClassification"]:
                raise ValueError(
                    f"TestExecutionResultV1 failed case {case_id} must declare a failureClassification"
                )
        else:
            if case["failureClassification"] not in (None, ""):
                if case["status"] != "error":
                    raise ValueError(
                        f"TestExecutionResultV1 non-failed case {case_id} must not set "
                        f"failureClassification unless status is failed or error"
                    )


def _validate_evidence(evidence_list: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not isinstance(evidence_list, list) or not evidence_list:
        raise ValueError("TestExecutionResultV1 evidenceList must be a non-empty list")
    seen_ids: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for evidence in evidence_list:
        if not isinstance(evidence, dict):
            raise ValueError("TestExecutionResultV1 evidenceList entries must be objects")
        _require_fields(
            "TestExecutionResultV1 evidence",
            evidence,
            ["id", "kind", "caseId", "payload", "contentHash"],
        )
        evidence_id = evidence["id"]
        if evidence_id in seen_ids:
            raise ValueError(f"TestExecutionResultV1 duplicate evidence id: {evidence_id}")
        seen_ids.add(evidence_id)
        if not isinstance(evidence["payload"], str) or not evidence["payload"]:
            raise ValueError(
                f"TestExecutionResultV1 evidence {evidence_id} payload must be a non-empty string"
            )
        expected_hash = _stable_text_hash(evidence["payload"])
        if evidence["contentHash"] != expected_hash:
            raise ValueError(
                f"TestExecutionResultV1 evidence {evidence_id} contentHash must equal "
                f"sha256 of payload"
            )
        by_id[evidence_id] = evidence
    return by_id


def _validate_diagnostics(
    diagnostics: list[dict[str, Any]], evidence_by_id: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if not isinstance(diagnostics, list):
        raise ValueError("TestExecutionResultV1 diagnostics must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            raise ValueError("TestExecutionResultV1 diagnostics entries must be objects")
        _require_fields(
            "TestExecutionResultV1 diagnostic",
            diagnostic,
            ["id", "caseId", "kind", "evidenceIds"],
        )
        diag_id = diagnostic["id"]
        if diag_id in by_id:
            raise ValueError(f"TestExecutionResultV1 duplicate diagnostic id: {diag_id}")
        evidence_ids = diagnostic["evidenceIds"]
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ValueError(
                f"TestExecutionResultV1 diagnostic {diag_id} must reference at least one evidence id"
            )
        for evidence_id in evidence_ids:
            if evidence_id not in evidence_by_id:
                raise ValueError(
                    f"TestExecutionResultV1 diagnostic {diag_id} references unknown evidence id: {evidence_id}"
                )
            if evidence_by_id[evidence_id]["caseId"] != diagnostic["caseId"]:
                raise ValueError(
                    f"TestExecutionResultV1 diagnostic {diag_id} references evidence "
                    f"{evidence_id} that belongs to another case"
                )
        by_id[diag_id] = diagnostic
    return by_id


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "TestExecutionResultV1 taskSpecBinding",
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
            f"TestExecutionResultV1 taskSpecBinding.taskSpecRef must equal "
            f"{TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"TestExecutionResultV1 taskSpecBinding.taskSpecSchemaVersion must equal "
            f"{TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"TestExecutionResultV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal "
            f"{TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"TestExecutionResultV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"TestExecutionResultV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["taskSpecContentHash"] != expected_hash:
        raise ValueError(
            "TestExecutionResultV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("TestExecutionResultV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("TestExecutionResultV1 sourceArtifacts entries must be objects")
        _require_fields(
            "TestExecutionResultV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"TestExecutionResultV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"TestExecutionResultV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"TestExecutionResultV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"TestExecutionResultV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"TestExecutionResultV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"TestExecutionResultV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_test_execution_result(result: dict[str, Any], root: Path) -> None:
    _require_fields(
        "TestExecutionResultV1",
        result,
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
            "framework",
            "runIdentifier",
            "summary",
            "cases",
            "evidenceList",
            "diagnostics",
            "verifierExpectations",
            "policyBoundary",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if result["schemaVersion"] != TEST_EXECUTION_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"TestExecutionResultV1 schemaVersion must be {TEST_EXECUTION_RESULT_SCHEMA_VERSION}"
        )
    if result["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"TestExecutionResultV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if result["id"] != ARTIFACT_ID:
        raise ValueError(f"TestExecutionResultV1 id must be {ARTIFACT_ID}")
    if result["generatedAt"] != GENERATED_AT:
        raise ValueError(f"TestExecutionResultV1 generatedAt must be {GENERATED_AT}")
    if result["kind"] != ARTIFACT_KIND:
        raise ValueError(f"TestExecutionResultV1 kind must be {ARTIFACT_KIND}")
    if result["scope"] != SCOPE:
        raise ValueError(f"TestExecutionResultV1 scope must be {SCOPE}")
    if result["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"TestExecutionResultV1 workloadType must be {WORKLOAD_TYPE}; "
            f"regression workload reuse is forbidden"
        )
    if result["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"TestExecutionResultV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if result["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(f"TestExecutionResultV1 creatorAgent must be {CREATOR_AGENT}")
    if result["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"TestExecutionResultV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; "
            f"creator must not own the verdict"
        )

    framework = result["framework"]
    _require_fields("TestExecutionResultV1 framework", framework, ["name", "version"])
    if not isinstance(framework["name"], str) or not framework["name"].strip():
        raise ValueError("TestExecutionResultV1 framework.name must be a non-empty string")
    if not isinstance(framework["version"], str) or not framework["version"].strip():
        raise ValueError("TestExecutionResultV1 framework.version must be a non-empty string")

    if not isinstance(result["runIdentifier"], str) or not result["runIdentifier"].strip():
        raise ValueError("TestExecutionResultV1 runIdentifier must be a non-empty string")

    _validate_task_spec_binding(result["taskSpecBinding"], root)

    evidence_by_id = _validate_evidence(result["evidenceList"])
    diagnostics_by_id = _validate_diagnostics(result["diagnostics"], evidence_by_id)
    _validate_cases(result["cases"], evidence_by_id, diagnostics_by_id)
    _validate_summary(result["summary"], result["cases"])

    case_evidence_ids: set[str] = set()
    case_diagnostic_ids: set[str] = set()
    for case in result["cases"]:
        case_evidence_ids.update(case["evidenceIds"])
        case_diagnostic_ids.update(case["diagnosticRefs"])
    unreferenced_evidence = set(evidence_by_id) - case_evidence_ids
    if unreferenced_evidence:
        raise ValueError(
            f"TestExecutionResultV1 evidenceList contains unreferenced evidence ids: "
            f"{sorted(unreferenced_evidence)}"
        )
    unreferenced_diagnostics = set(diagnostics_by_id) - case_diagnostic_ids
    if unreferenced_diagnostics:
        raise ValueError(
            f"TestExecutionResultV1 diagnostics contains unreferenced diagnostic ids: "
            f"{sorted(unreferenced_diagnostics)}"
        )

    verifier = result["verifierExpectations"]
    _require_fields(
        "TestExecutionResultV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"TestExecutionResultV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"TestExecutionResultV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != VERIFIER_VERDICT_DOMAIN:
        raise ValueError(
            f"TestExecutionResultV1 verifierExpectations.verdictDomain must equal {VERIFIER_VERDICT_DOMAIN}"
        )

    policy = result["policyBoundary"]
    _require_fields("TestExecutionResultV1 policyBoundary", policy, REQUIRED_POLICY_FLAGS)
    for flag in REQUIRED_POLICY_FLAGS:
        if policy[flag] is not False:
            raise ValueError(
                f"TestExecutionResultV1 policyBoundary.{flag} must be false"
            )

    isolation = result["regressionWorkloadIsolation"]
    _require_fields(
        "TestExecutionResultV1 regressionWorkloadIsolation",
        isolation,
        ["reusesRegressionResultArtifact", "reusesEmailDraftArtifact", "forbiddenFields"],
    )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "TestExecutionResultV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesEmailDraftArtifact"] is not False:
        raise ValueError(
            "TestExecutionResultV1 must not reuse EmailDraftArtifactV1"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"TestExecutionResultV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(result, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"TestExecutionResultV1 must not embed regression/email field {term} "
                f"outside forbiddenFields"
            )

    reuse_path = result["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"TestExecutionResultV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = result["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            "TestExecutionResultV1 coordinationBinding must include "
            f"{sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"TestExecutionResultV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(result["sourceArtifacts"], root)

    invariants = result["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 5:
        raise ValueError(
            "TestExecutionResultV1 invariants must declare at least five workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="test-execution-result")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        result = build_test_execution_result(root)
        _write_json(args.out, result)
        print(f"Wrote TestExecutionResultV1 artifact to {args.out}.")
    if args.validate is not None:
        result = _load_json(args.validate)
        validate_test_execution_result(result, root)
        print(f"Validated TestExecutionResultV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

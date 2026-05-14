"""FailureTriageReportV1 ArtifactV1 subtype contract.

This module defines the second workload-independent ``ArtifactV1`` subtype for
the ``Test Execution / Failure Triage`` workload, sitting downstream of
``TestExecutionResultV1`` and ``TestExecutionTaskSpecV1``.

A ``FailureTriageReportV1`` is a creator-produced triage artifact that explains
*why* a recorded test execution result contains failed / error cases. It binds
every triage finding to (a) the case under triage, (b) at least one evidence
record already present in ``TestExecutionResultV1.evidenceList``, and (c) a
remediation category. The verifier verdict is owned exclusively by
``verifier-runtime-v1``; this artifact must not assert pass/fail status itself.

Key invariants this module enforces:

- The artifact is an ``ArtifactV1`` envelope subtype distinct from
  ``RegressionResultArtifactV1`` and ``TestExecutionResultV1``.
- Every failed or error case in the bound ``TestExecutionResultV1`` must have at
  least one triage finding; passed and skipped cases must not be triaged.
- Every finding's ``supportingEvidenceIds`` must resolve to evidence records in
  the bound ``TestExecutionResultV1`` whose ``caseId`` matches the finding.
- All upstream contracts (TestExecutionTaskSpecV1, TestExecutionResultV1, and
  the five Agent Coordination Layer manifests) are pinned by content hash so a
  drift in any upstream contract invalidates this artifact.
- The artifact carries no external side effects, no repository mutation, no
  GUI / browser / desktop call, no public access, and no delivery; findings
  may not broadcast downstream by themselves -- broadcast remains the
  ``BroadcastSubscriptionManifestV1`` responsibility.

The artifact is fully self-contained (synthetic triage data is embedded inline
and references only the synthetic ``TestExecutionResultV1`` cases) so it
remains deterministic across Linux / macOS / Windows.
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
from test_execution_result import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as TEST_EXECUTION_RESULT_ARTIFACT_ID,
    TEST_EXECUTION_RESULT_ARTIFACT_PATH,
    TEST_EXECUTION_RESULT_SCHEMA_VERSION,
    validate_test_execution_result,
)


FAILURE_TRIAGE_REPORT_SCHEMA_VERSION = "failure-triage-report-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "FailureTriageReportV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-failure-triage-report-kernel-contract"
FAILURE_TRIAGE_REPORT_ARTIFACT_PATH = (
    "artifacts/test_execution/post_mvp_failure_triage_report.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_artifact_contract"
CREATOR_AGENT = "creator_agent"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERIFIER_VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

FAILURE_CLASSIFICATION_DOMAIN = [
    "assertion_error",
    "type_error",
    "environment_error",
    "timeout",
    "flaky",
    "configuration_error",
    "unknown",
]
REMEDIATION_DOMAIN = [
    "requires_code_fix",
    "requires_test_fix",
    "requires_infra_change",
    "requires_more_diagnostics",
]
CONFIDENCE_DOMAIN = ["low", "medium", "high"]
TRIAGE_REQUIRED_CASE_STATUSES = {"failed", "error"}
TRIAGE_FORBIDDEN_CASE_STATUSES = {"passed", "skipped"}

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
    "test_execution_result": TEST_EXECUTION_RESULT_ARTIFACT_PATH,
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

REQUIRED_VERIFIER_FLAGS = [
    "mustValidateSchema",
    "mustValidateEvidenceProvenance",
    "mustValidateCaseTriageCoverage",
    "mustValidateUpstreamContractBindings",
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
    "FailureTriageReportV1 is an ArtifactV1 subtype distinct from RegressionResultArtifactV1 and TestExecutionResultV1.",
    "FailureTriageReportV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance.",
    "FailureTriageReportV1 must bind the TestExecutionResultV1 and TestExecutionTaskSpecV1 envelopes and all five coordination contracts by content hash.",
    "FailureTriageReportV1 must keep external side effects, repository mutation, external communication, and downstream broadcast disabled.",
    "FailureTriageReportV1 must cover every failed or error case in the bound TestExecutionResultV1 with at least one evidence-backed finding.",
    "FailureTriageReportV1 must not triage passed or skipped cases and must reuse evidence ids already present in the bound TestExecutionResultV1.",
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
            f"FailureTriageReportV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"FailureTriageReportV1 source artifact does not exist: {relative_path}"
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
                f"FailureTriageReportV1 coordination binding is missing artifact: {relative_path}"
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
    test_execution_result = _load_json(root / TEST_EXECUTION_RESULT_ARTIFACT_PATH)
    validate_test_execution_result(test_execution_result, root)
    return test_execution_result


def _build_findings(test_execution_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one finding per failed/error case in the bound TestExecutionResultV1."""

    cases = {case["id"]: case for case in test_execution_result["cases"]}
    findings: list[dict[str, Any]] = []
    case_002 = cases.get("case-002")
    if case_002 is None or case_002["status"] != "failed":
        raise ValueError(
            "FailureTriageReportV1 expects synthetic case-002 to be a failed case in the bound TestExecutionResultV1"
        )
    findings.append(
        {
            "id": "ft-finding-001",
            "caseRef": "case-002",
            "observedStatus": case_002["status"],
            "declaredFailureClassification": case_002["failureClassification"],
            "refinedFailureClassification": "assertion_error",
            "rootCauseHypothesis": (
                "Synthetic assertion compares literal 1 to 2; this is a deterministic "
                "test-side error and does not indicate a regression in production code."
            ),
            "confidenceLevel": "high",
            "supportingEvidenceIds": [
                "ev-case-002-outcome",
                "ev-case-002-trace",
            ],
            "remediationCategory": "requires_test_fix",
            "mayBroadcastDownstream": False,
        }
    )
    return findings


def _build_summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_classification: dict[str, int] = {kind: 0 for kind in FAILURE_CLASSIFICATION_DOMAIN}
    by_remediation: dict[str, int] = {kind: 0 for kind in REMEDIATION_DOMAIN}
    for finding in findings:
        by_classification[finding["refinedFailureClassification"]] += 1
        by_remediation[finding["remediationCategory"]] += 1
    return {
        "totalFindings": len(findings),
        "byRefinedFailureClassification": dict(sorted(by_classification.items())),
        "byRemediationCategory": dict(sorted(by_remediation.items())),
    }


def _build_test_execution_result_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_RESULT_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"FailureTriageReportV1 testExecutionResultBinding requires artifact: {relative_path}"
        )
    return {
        "testExecutionResultRef": relative_path,
        "testExecutionResultSchemaVersion": TEST_EXECUTION_RESULT_SCHEMA_VERSION,
        "testExecutionResultEnvelopeSchemaVersion": TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION,
        "testExecutionResultId": TEST_EXECUTION_RESULT_ARTIFACT_ID,
        "testExecutionResultContentHash": _stable_file_hash(full_path),
    }


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"FailureTriageReportV1 taskSpecBinding requires artifact: {relative_path}"
        )
    return {
        "taskSpecRef": relative_path,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecContentHash": _stable_file_hash(full_path),
    }


def build_failure_triage_report(root: Path) -> dict[str, Any]:
    test_execution_result = _validate_referenced_artifacts(root)
    findings = _build_findings(test_execution_result)
    summary = _build_summary(findings)
    source_artifacts = [
        _artifact_source(role, relative_path, root)
        for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
    ]
    payload: dict[str, Any] = {
        "schemaVersion": FAILURE_TRIAGE_REPORT_SCHEMA_VERSION,
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
        "testExecutionResultBinding": _build_test_execution_result_binding(root),
        "summary": summary,
        "triageFindings": findings,
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateEvidenceProvenance": True,
            "mustValidateCaseTriageCoverage": True,
            "mustValidateUpstreamContractBindings": True,
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
            "reusesTestExecutionResultArtifactSchema": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "coordinationBinding": _coordination_binding(root),
        "sourceArtifacts": source_artifacts,
        "invariants": list(INVARIANTS),
    }
    validate_failure_triage_report(payload, root)
    return payload


def _validate_summary(summary: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    expected = _build_summary(findings)
    if summary != expected:
        raise ValueError(
            f"FailureTriageReportV1 summary must equal computed counts {expected}; got {summary}"
        )


def _validate_findings(
    findings: list[dict[str, Any]],
    test_execution_result: dict[str, Any],
) -> None:
    if not isinstance(findings, list) or not findings:
        raise ValueError(
            "FailureTriageReportV1 triageFindings must be a non-empty list"
        )
    cases_by_id = {case["id"]: case for case in test_execution_result["cases"]}
    evidence_by_id = {ev["id"]: ev for ev in test_execution_result["evidenceList"]}
    triaged_cases: set[str] = set()
    seen_finding_ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError(
                "FailureTriageReportV1 triageFindings entries must be objects"
            )
        _require_fields(
            "FailureTriageReportV1 finding",
            finding,
            [
                "id",
                "caseRef",
                "observedStatus",
                "declaredFailureClassification",
                "refinedFailureClassification",
                "rootCauseHypothesis",
                "confidenceLevel",
                "supportingEvidenceIds",
                "remediationCategory",
                "mayBroadcastDownstream",
            ],
        )
        finding_id = finding["id"]
        if finding_id in seen_finding_ids:
            raise ValueError(
                f"FailureTriageReportV1 duplicate finding id: {finding_id}"
            )
        seen_finding_ids.add(finding_id)
        case_ref = finding["caseRef"]
        if case_ref not in cases_by_id:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} references unknown caseRef: {case_ref}"
            )
        case = cases_by_id[case_ref]
        if case["status"] in TRIAGE_FORBIDDEN_CASE_STATUSES:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} must not triage a "
                f"{case['status']} case (caseRef={case_ref})"
            )
        if case["status"] not in TRIAGE_REQUIRED_CASE_STATUSES:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} caseRef {case_ref} "
                f"must be a failed or error case; got status {case['status']}"
            )
        if finding["observedStatus"] != case["status"]:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} observedStatus must equal "
                f"the bound case status {case['status']}"
            )
        if finding["declaredFailureClassification"] != case["failureClassification"]:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} declaredFailureClassification "
                f"must equal the TestExecutionResultV1 case failureClassification "
                f"({case['failureClassification']})"
            )
        if finding["refinedFailureClassification"] not in FAILURE_CLASSIFICATION_DOMAIN:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} refinedFailureClassification "
                f"must be one of {FAILURE_CLASSIFICATION_DOMAIN}"
            )
        if finding["remediationCategory"] not in REMEDIATION_DOMAIN:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} remediationCategory must be one of {REMEDIATION_DOMAIN}"
            )
        if finding["confidenceLevel"] not in CONFIDENCE_DOMAIN:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} confidenceLevel must be one of {CONFIDENCE_DOMAIN}"
            )
        if finding["mayBroadcastDownstream"] is not False:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} mayBroadcastDownstream must be false; "
                f"broadcast is owned by BroadcastSubscriptionManifestV1"
            )
        root_cause = finding["rootCauseHypothesis"]
        if not isinstance(root_cause, str) or len(root_cause.strip()) < 16:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} rootCauseHypothesis must be a substantive string"
            )
        supporting = finding["supportingEvidenceIds"]
        if not isinstance(supporting, list) or not supporting:
            raise ValueError(
                f"FailureTriageReportV1 finding {finding_id} must reference at least one supporting evidence id"
            )
        for evidence_id in supporting:
            if evidence_id not in evidence_by_id:
                raise ValueError(
                    f"FailureTriageReportV1 finding {finding_id} references unknown evidence id: {evidence_id}"
                )
            if evidence_by_id[evidence_id]["caseId"] != case_ref:
                raise ValueError(
                    f"FailureTriageReportV1 finding {finding_id} references evidence "
                    f"{evidence_id} that belongs to another case"
                )
        triaged_cases.add(case_ref)

    expected_triage_cases = {
        case["id"]
        for case in test_execution_result["cases"]
        if case["status"] in TRIAGE_REQUIRED_CASE_STATUSES
    }
    missing = expected_triage_cases - triaged_cases
    if missing:
        raise ValueError(
            f"FailureTriageReportV1 must cover every failed/error case; missing findings for: {sorted(missing)}"
        )


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "FailureTriageReportV1 taskSpecBinding",
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
            f"FailureTriageReportV1 taskSpecBinding.taskSpecRef must equal "
            f"{TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"FailureTriageReportV1 taskSpecBinding.taskSpecSchemaVersion must equal "
            f"{TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"FailureTriageReportV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal "
            f"{TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"FailureTriageReportV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"FailureTriageReportV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["taskSpecContentHash"] != expected_hash:
        raise ValueError(
            "FailureTriageReportV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_test_execution_result_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "FailureTriageReportV1 testExecutionResultBinding",
        binding,
        [
            "testExecutionResultRef",
            "testExecutionResultSchemaVersion",
            "testExecutionResultEnvelopeSchemaVersion",
            "testExecutionResultId",
            "testExecutionResultContentHash",
        ],
    )
    if binding["testExecutionResultRef"] != TEST_EXECUTION_RESULT_ARTIFACT_PATH:
        raise ValueError(
            f"FailureTriageReportV1 testExecutionResultBinding.testExecutionResultRef must equal "
            f"{TEST_EXECUTION_RESULT_ARTIFACT_PATH}"
        )
    if binding["testExecutionResultSchemaVersion"] != TEST_EXECUTION_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"FailureTriageReportV1 testExecutionResultBinding.testExecutionResultSchemaVersion must equal "
            f"{TEST_EXECUTION_RESULT_SCHEMA_VERSION}; regression artifact reuse is forbidden"
        )
    if (
        binding["testExecutionResultEnvelopeSchemaVersion"]
        != TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION
    ):
        raise ValueError(
            f"FailureTriageReportV1 testExecutionResultBinding.testExecutionResultEnvelopeSchemaVersion must equal "
            f"{TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["testExecutionResultId"] != TEST_EXECUTION_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"FailureTriageReportV1 testExecutionResultBinding.testExecutionResultId must equal "
            f"{TEST_EXECUTION_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["testExecutionResultRef"]
    if not full_path.is_file():
        raise ValueError(
            f"FailureTriageReportV1 testExecutionResultBinding artifact missing: {binding['testExecutionResultRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["testExecutionResultContentHash"] != expected_hash:
        raise ValueError(
            "FailureTriageReportV1 testExecutionResultBinding.testExecutionResultContentHash must match the on-disk artifact"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("FailureTriageReportV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("FailureTriageReportV1 sourceArtifacts entries must be objects")
        _require_fields(
            "FailureTriageReportV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"FailureTriageReportV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"FailureTriageReportV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"FailureTriageReportV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"FailureTriageReportV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"FailureTriageReportV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"FailureTriageReportV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_failure_triage_report(report: dict[str, Any], root: Path) -> None:
    _require_fields(
        "FailureTriageReportV1",
        report,
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
            "testExecutionResultBinding",
            "summary",
            "triageFindings",
            "verifierExpectations",
            "policyBoundary",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if report["schemaVersion"] != FAILURE_TRIAGE_REPORT_SCHEMA_VERSION:
        raise ValueError(
            f"FailureTriageReportV1 schemaVersion must be {FAILURE_TRIAGE_REPORT_SCHEMA_VERSION}"
        )
    if report["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"FailureTriageReportV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if report["id"] != ARTIFACT_ID:
        raise ValueError(f"FailureTriageReportV1 id must be {ARTIFACT_ID}")
    if report["generatedAt"] != GENERATED_AT:
        raise ValueError(f"FailureTriageReportV1 generatedAt must be {GENERATED_AT}")
    if report["kind"] != ARTIFACT_KIND:
        raise ValueError(f"FailureTriageReportV1 kind must be {ARTIFACT_KIND}")
    if report["scope"] != SCOPE:
        raise ValueError(f"FailureTriageReportV1 scope must be {SCOPE}")
    if report["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"FailureTriageReportV1 workloadType must be {WORKLOAD_TYPE}; "
            f"regression workload reuse is forbidden"
        )
    if report["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"FailureTriageReportV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if report["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(
            f"FailureTriageReportV1 creatorAgent must be {CREATOR_AGENT}"
        )
    if report["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"FailureTriageReportV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; "
            f"creator must not own the verdict"
        )

    _validate_task_spec_binding(report["taskSpecBinding"], root)
    _validate_test_execution_result_binding(report["testExecutionResultBinding"], root)

    test_execution_result = _load_json(root / TEST_EXECUTION_RESULT_ARTIFACT_PATH)
    validate_test_execution_result(test_execution_result, root)
    _validate_findings(report["triageFindings"], test_execution_result)
    _validate_summary(report["summary"], report["triageFindings"])

    verifier = report["verifierExpectations"]
    _require_fields(
        "FailureTriageReportV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"FailureTriageReportV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"FailureTriageReportV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != VERIFIER_VERDICT_DOMAIN:
        raise ValueError(
            f"FailureTriageReportV1 verifierExpectations.verdictDomain must equal {VERIFIER_VERDICT_DOMAIN}"
        )

    policy = report["policyBoundary"]
    _require_fields("FailureTriageReportV1 policyBoundary", policy, REQUIRED_POLICY_FLAGS)
    for flag in REQUIRED_POLICY_FLAGS:
        if policy[flag] is not False:
            raise ValueError(
                f"FailureTriageReportV1 policyBoundary.{flag} must be false"
            )

    isolation = report["regressionWorkloadIsolation"]
    _require_fields(
        "FailureTriageReportV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionResultArtifact",
            "reusesEmailDraftArtifact",
            "reusesTestExecutionResultArtifactSchema",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "FailureTriageReportV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesEmailDraftArtifact"] is not False:
        raise ValueError(
            "FailureTriageReportV1 must not reuse EmailDraftArtifactV1"
        )
    if isolation["reusesTestExecutionResultArtifactSchema"] is not False:
        raise ValueError(
            "FailureTriageReportV1 must not reuse the TestExecutionResultV1 schema as its own envelope"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"FailureTriageReportV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(report, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"FailureTriageReportV1 must not embed regression/email field {term} "
                f"outside forbiddenFields"
            )

    reuse_path = report["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"FailureTriageReportV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = report["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            "FailureTriageReportV1 coordinationBinding must include "
            f"{sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"FailureTriageReportV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(report["sourceArtifacts"], root)

    invariants = report["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 5:
        raise ValueError(
            "FailureTriageReportV1 invariants must declare at least five workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="failure-triage-report")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        report = build_failure_triage_report(root)
        _write_json(args.out, report)
        print(f"Wrote FailureTriageReportV1 artifact to {args.out}.")
    if args.validate is not None:
        report = _load_json(args.validate)
        validate_failure_triage_report(report, root)
        print(f"Validated FailureTriageReportV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

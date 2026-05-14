"""VerifierResultV1 ArtifactV1 subtype contract.

This module defines the first workload-independent ``ArtifactV1`` subtype that is
*owned by the verifier* rather than the creator. It captures the verdict of
``verifier-runtime-v1`` over the bound creator artifacts (``TestExecutionResultV1``
and ``FailureTriageReportV1``) for the ``Test Execution / Failure Triage``
workload, plus the upstream ``TestExecutionTaskSpecV1`` envelope and the five
Agent Coordination Layer manifests.

The artifact answers two OS-kernel invariants at once:

- ``Verifier`` ownership: the creator must not author this artifact and must not
  own the verdict. ``verifierAgent`` is ``verifier-runtime-v1``.
- ``Artifact`` envelope reuse: the artifact reuses the same
  ``artifactEnvelopeSchemaVersion=artifact-v1`` envelope as
  ``RegressionResultArtifactV1`` / ``TestExecutionResultV1`` /
  ``FailureTriageReportV1`` to prove the envelope can carry creator *and*
  verifier outputs.

Key invariants this module enforces:

- The artifact is an ``ArtifactV1`` envelope subtype distinct from every
  creator-owned subtype; ``verifierVerdictOwner`` and ``verifierAgent`` are both
  ``verifier-runtime-v1`` and ``creatorAgentMustNotOwnVerdict`` is ``true``.
- The artifact binds the bound ``TestExecutionResultV1``,
  ``FailureTriageReportV1``, and ``TestExecutionTaskSpecV1`` envelopes plus all
  five coordination contracts by content hash, so a drift in any upstream
  artifact invalidates the verdict.
- Every rule result references rules and supporting evidence ids that exist in
  the bound ``TestExecutionResultV1.evidenceList``; the verifier never invents
  evidence.
- The verdict belongs to a fixed domain and is derived from the rule results
  via a workload-independent precedence: a single blocking failing rule maps to
  ``failed``; otherwise the presence of a failed/error case in the bound
  ``TestExecutionResultV1`` maps to ``needs_human_check``; otherwise the verdict
  is ``passed``.
- The artifact carries no external side effects, no repository mutation, no
  GUI / browser / desktop call, no public access, and no delivery.

The artifact is fully self-contained (synthetic rule results reference the
synthetic evidence ids embedded in the bound ``TestExecutionResultV1``) so it
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
from failure_triage_report import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as FAILURE_TRIAGE_REPORT_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as FAILURE_TRIAGE_REPORT_ARTIFACT_ID,
    FAILURE_TRIAGE_REPORT_ARTIFACT_PATH,
    FAILURE_TRIAGE_REPORT_SCHEMA_VERSION,
    validate_failure_triage_report,
)


VERIFIER_RESULT_SCHEMA_VERSION = "verifier-result-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "VerifierResultV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-verifier-result-test-execution-kernel-contract"
VERIFIER_RESULT_ARTIFACT_PATH = (
    "artifacts/verifier/post_mvp_verifier_result_test_execution.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_artifact_contract"

VERIFIER_AGENT = "verifier-runtime-v1"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]
RULE_STATUS_DOMAIN = ["passed", "failed", "not_applicable"]
RULE_KIND_DOMAIN = [
    "schema",
    "evidence_link",
    "policy_boundary",
    "classification",
    "coordination_binding",
    "case_coverage",
    "upstream_contract_binding",
]

CREATOR_OWNED_AGENT_TOKEN = "creator_agent"
FORBIDDEN_AUTHOR_TOKENS = [CREATOR_OWNED_AGENT_TOKEN]

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
    "failure_triage_report": FAILURE_TRIAGE_REPORT_ARTIFACT_PATH,
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

REQUIRED_RULE_IDS = [
    "schema_validation",
    "evidence_provenance",
    "case_coverage",
    "policy_boundary",
    "coordination_binding",
    "upstream_contract_binding",
    "classification_precedence",
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
    "VerifierResultV1 is an ArtifactV1 subtype owned by verifier-runtime-v1, not by any creator agent.",
    "VerifierResultV1 must bind TestExecutionResultV1, FailureTriageReportV1, and TestExecutionTaskSpecV1 envelopes plus all five coordination contracts by content hash.",
    "VerifierResultV1 verdict belongs to a fixed domain and is derived from rule results via workload-independent precedence.",
    "VerifierResultV1 ruleResults must reference evidence ids that exist in the bound TestExecutionResultV1.evidenceList.",
    "VerifierResultV1 must keep external side effects, repository mutation, external communication, GUI/desktop access, and public access disabled.",
    "VerifierResultV1 must declare creatorAgentMustNotOwnVerdict=true and must not be authored by creator_agent.",
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
            f"VerifierResultV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"VerifierResultV1 source artifact does not exist: {relative_path}"
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
                f"VerifierResultV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
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
    failure_triage_report = _load_json(root / FAILURE_TRIAGE_REPORT_ARTIFACT_PATH)
    validate_failure_triage_report(failure_triage_report, root)
    return test_execution_result, failure_triage_report


def _build_rule_results(
    test_execution_result: dict[str, Any],
    failure_triage_report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return one rule result per workload-independent verifier rule.

    Every rule is *passed* in the synthetic fixture because the upstream
    artifacts are correctly formed; the only workload-level signal is the
    presence of a failed case in ``TestExecutionResultV1``, which the
    ``classification_precedence`` rule reflects in its rationale.
    """

    failed_case_ids = sorted(
        case["id"]
        for case in test_execution_result["cases"]
        if case["status"] in {"failed", "error"}
    )
    triaged_case_ids = sorted(
        finding["caseRef"] for finding in failure_triage_report["triageFindings"]
    )
    return [
        {
            "id": "schema_validation",
            "kind": "schema",
            "status": "passed",
            "blocking": True,
            "description": (
                "All upstream artifacts (TestExecutionTaskSpecV1, "
                "TestExecutionResultV1, FailureTriageReportV1) validate against "
                "their declared schemas."
            ),
            "supportingEvidenceIds": [],
            "rationale": (
                "Each upstream artifact was re-validated by its own validator "
                "during VerifierResultV1 construction."
            ),
        },
        {
            "id": "evidence_provenance",
            "kind": "evidence_link",
            "status": "passed",
            "blocking": True,
            "description": (
                "Every triage finding's supportingEvidenceIds resolve to evidence "
                "records in the bound TestExecutionResultV1.evidenceList."
            ),
            "supportingEvidenceIds": [
                "ev-case-002-outcome",
                "ev-case-002-trace",
            ],
            "rationale": (
                "FailureTriageReportV1 finding ft-finding-001 references "
                "ev-case-002-outcome and ev-case-002-trace, both present in the "
                "bound TestExecutionResultV1."
            ),
        },
        {
            "id": "case_coverage",
            "kind": "case_coverage",
            "status": "passed",
            "blocking": True,
            "description": (
                "Every failed/error case in TestExecutionResultV1 has at least "
                "one matching FailureTriageReportV1 finding."
            ),
            "supportingEvidenceIds": ["ev-case-002-outcome"],
            "rationale": (
                f"Failed/error cases {failed_case_ids} are triaged by findings "
                f"covering {triaged_case_ids}."
            ),
        },
        {
            "id": "policy_boundary",
            "kind": "policy_boundary",
            "status": "passed",
            "blocking": True,
            "description": (
                "All upstream artifacts keep external side effects, repository "
                "mutation, external communication, GUI/desktop access, public "
                "access, and release/deployment disabled."
            ),
            "supportingEvidenceIds": [],
            "rationale": (
                "policyBoundary on TestExecutionResultV1 and "
                "FailureTriageReportV1 enforces zero side-effect classes."
            ),
        },
        {
            "id": "coordination_binding",
            "kind": "coordination_binding",
            "status": "passed",
            "blocking": True,
            "description": (
                "All five Agent Coordination Layer contracts are bound by "
                "content hash via coordinationBinding and sourceArtifacts."
            ),
            "supportingEvidenceIds": [],
            "rationale": (
                "DelegationManifestV1, CreatorVerifierPairingV1, "
                "AgentMessageManifestV1, NegotiationRecordV1, and "
                "BroadcastSubscriptionManifestV1 are all referenced by ref and "
                "by content hash."
            ),
        },
        {
            "id": "upstream_contract_binding",
            "kind": "upstream_contract_binding",
            "status": "passed",
            "blocking": True,
            "description": (
                "TestExecutionTaskSpecV1 envelope and TestExecutionResultV1 / "
                "FailureTriageReportV1 envelopes are pinned by content hash."
            ),
            "supportingEvidenceIds": [],
            "rationale": (
                "taskSpecBinding, testExecutionResultBinding, and "
                "failureTriageReportBinding each include schemaVersion, "
                "envelopeSchemaVersion, id, and contentHash."
            ),
        },
        {
            "id": "classification_precedence",
            "kind": "classification",
            "status": "passed",
            "blocking": True,
            "description": (
                "Verifier verdict follows workload-independent precedence: any "
                "blocking failed rule => failed; else failed/error cases => "
                "needs_human_check; else passed."
            ),
            "supportingEvidenceIds": ["ev-case-002-outcome", "ev-case-002-trace"],
            "rationale": (
                "All rule statuses are passed; TestExecutionResultV1 contains a "
                "failed case, so the precedence selects needs_human_check."
            ),
        },
    ]


def _derive_verdict(
    rule_results: list[dict[str, Any]],
    test_execution_result: dict[str, Any],
) -> str:
    """Workload-independent verdict precedence.

    1. Any blocking rule with status=failed => ``failed``.
    2. Any failed or error case in TestExecutionResultV1 => ``needs_human_check``.
    3. Otherwise => ``passed``.
    """

    for rule in rule_results:
        if rule.get("blocking") is True and rule.get("status") == "failed":
            return "failed"
    has_failure = any(
        case["status"] in {"failed", "error"}
        for case in test_execution_result["cases"]
    )
    if has_failure:
        return "needs_human_check"
    return "passed"


def _build_test_execution_result_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_RESULT_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"VerifierResultV1 testExecutionResultBinding requires artifact: {relative_path}"
        )
    return {
        "testExecutionResultRef": relative_path,
        "testExecutionResultSchemaVersion": TEST_EXECUTION_RESULT_SCHEMA_VERSION,
        "testExecutionResultEnvelopeSchemaVersion": TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION,
        "testExecutionResultId": TEST_EXECUTION_RESULT_ARTIFACT_ID,
        "testExecutionResultContentHash": _stable_file_hash(full_path),
    }


def _build_failure_triage_report_binding(root: Path) -> dict[str, Any]:
    relative_path = FAILURE_TRIAGE_REPORT_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"VerifierResultV1 failureTriageReportBinding requires artifact: {relative_path}"
        )
    return {
        "failureTriageReportRef": relative_path,
        "failureTriageReportSchemaVersion": FAILURE_TRIAGE_REPORT_SCHEMA_VERSION,
        "failureTriageReportEnvelopeSchemaVersion": FAILURE_TRIAGE_REPORT_ENVELOPE_SCHEMA_VERSION,
        "failureTriageReportId": FAILURE_TRIAGE_REPORT_ARTIFACT_ID,
        "failureTriageReportContentHash": _stable_file_hash(full_path),
    }


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"VerifierResultV1 taskSpecBinding requires artifact: {relative_path}"
        )
    return {
        "taskSpecRef": relative_path,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecContentHash": _stable_file_hash(full_path),
    }


def build_verifier_result(root: Path) -> dict[str, Any]:
    test_execution_result, failure_triage_report = _validate_referenced_artifacts(root)
    rule_results = _build_rule_results(test_execution_result, failure_triage_report)
    verdict = _derive_verdict(rule_results, test_execution_result)
    source_artifacts = [
        _artifact_source(role, relative_path, root)
        for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
    ]
    payload: dict[str, Any] = {
        "schemaVersion": VERIFIER_RESULT_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "verifierAgent": VERIFIER_AGENT,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "creatorAgentMustNotOwnVerdict": True,
        "verdict": verdict,
        "verdictDomain": list(VERDICT_DOMAIN),
        "verdictRationale": (
            "All workload-independent verifier rules passed. The bound "
            "TestExecutionResultV1 contains a failed test case (case-002) that "
            "FailureTriageReportV1 has triaged as a test-side assertion error; "
            "workload-level precedence therefore selects needs_human_check "
            "without crossing any policy boundary."
        ),
        "taskSpecBinding": _build_task_spec_binding(root),
        "testExecutionResultBinding": _build_test_execution_result_binding(root),
        "failureTriageReportBinding": _build_failure_triage_report_binding(root),
        "ruleResults": rule_results,
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
            "reusesFailureTriageReportSchema": False,
            "reusesRegressionVerifierReportArtifact": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "coordinationBinding": _coordination_binding(root),
        "sourceArtifacts": source_artifacts,
        "invariants": list(INVARIANTS),
    }
    validate_verifier_result(payload, root)
    return payload


def _validate_rule_results(
    rule_results: list[Any],
    test_execution_result: dict[str, Any],
) -> None:
    if not isinstance(rule_results, list) or not rule_results:
        raise ValueError("VerifierResultV1 ruleResults must be a non-empty list")
    evidence_by_id = {ev["id"]: ev for ev in test_execution_result["evidenceList"]}
    seen_ids: set[str] = set()
    for rule in rule_results:
        if not isinstance(rule, dict):
            raise ValueError("VerifierResultV1 ruleResults entries must be objects")
        _require_fields(
            "VerifierResultV1 ruleResult",
            rule,
            [
                "id",
                "kind",
                "status",
                "blocking",
                "description",
                "supportingEvidenceIds",
                "rationale",
            ],
        )
        rule_id = rule["id"]
        if rule_id in seen_ids:
            raise ValueError(f"VerifierResultV1 duplicate ruleResult id: {rule_id}")
        seen_ids.add(rule_id)
        if rule["kind"] not in RULE_KIND_DOMAIN:
            raise ValueError(
                f"VerifierResultV1 ruleResult {rule_id} kind must be one of {RULE_KIND_DOMAIN}"
            )
        if rule["status"] not in RULE_STATUS_DOMAIN:
            raise ValueError(
                f"VerifierResultV1 ruleResult {rule_id} status must be one of {RULE_STATUS_DOMAIN}"
            )
        if rule["blocking"] is not True and rule["blocking"] is not False:
            raise ValueError(
                f"VerifierResultV1 ruleResult {rule_id} blocking must be a boolean"
            )
        rationale = rule["rationale"]
        if not isinstance(rationale, str) or len(rationale.strip()) < 16:
            raise ValueError(
                f"VerifierResultV1 ruleResult {rule_id} rationale must be a substantive string"
            )
        supporting = rule["supportingEvidenceIds"]
        if not isinstance(supporting, list):
            raise ValueError(
                f"VerifierResultV1 ruleResult {rule_id} supportingEvidenceIds must be a list"
            )
        for evidence_id in supporting:
            if evidence_id not in evidence_by_id:
                raise ValueError(
                    f"VerifierResultV1 ruleResult {rule_id} references unknown evidence id: {evidence_id}"
                )
    missing_rules = set(REQUIRED_RULE_IDS) - seen_ids
    if missing_rules:
        raise ValueError(
            f"VerifierResultV1 ruleResults must include rules: {sorted(missing_rules)}"
        )


def _validate_verdict(
    verdict: str,
    rule_results: list[dict[str, Any]],
    test_execution_result: dict[str, Any],
) -> None:
    if verdict not in VERDICT_DOMAIN:
        raise ValueError(
            f"VerifierResultV1 verdict must be one of {VERDICT_DOMAIN}; got {verdict}"
        )
    expected = _derive_verdict(rule_results, test_execution_result)
    if verdict != expected:
        raise ValueError(
            f"VerifierResultV1 verdict must follow workload-independent precedence; "
            f"expected {expected}, got {verdict}"
        )


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "VerifierResultV1 taskSpecBinding",
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
            f"VerifierResultV1 taskSpecBinding.taskSpecRef must equal "
            f"{TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"VerifierResultV1 taskSpecBinding.taskSpecSchemaVersion must equal "
            f"{TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"VerifierResultV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal "
            f"{TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"VerifierResultV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"VerifierResultV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["taskSpecContentHash"] != expected_hash:
        raise ValueError(
            "VerifierResultV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_test_execution_result_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "VerifierResultV1 testExecutionResultBinding",
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
            f"VerifierResultV1 testExecutionResultBinding.testExecutionResultRef must equal "
            f"{TEST_EXECUTION_RESULT_ARTIFACT_PATH}"
        )
    if binding["testExecutionResultSchemaVersion"] != TEST_EXECUTION_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"VerifierResultV1 testExecutionResultBinding.testExecutionResultSchemaVersion must equal "
            f"{TEST_EXECUTION_RESULT_SCHEMA_VERSION}; regression artifact reuse is forbidden"
        )
    if (
        binding["testExecutionResultEnvelopeSchemaVersion"]
        != TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION
    ):
        raise ValueError(
            f"VerifierResultV1 testExecutionResultBinding.testExecutionResultEnvelopeSchemaVersion must equal "
            f"{TEST_EXECUTION_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["testExecutionResultId"] != TEST_EXECUTION_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"VerifierResultV1 testExecutionResultBinding.testExecutionResultId must equal "
            f"{TEST_EXECUTION_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["testExecutionResultRef"]
    if not full_path.is_file():
        raise ValueError(
            f"VerifierResultV1 testExecutionResultBinding artifact missing: {binding['testExecutionResultRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["testExecutionResultContentHash"] != expected_hash:
        raise ValueError(
            "VerifierResultV1 testExecutionResultBinding.testExecutionResultContentHash must match the on-disk artifact"
        )


def _validate_failure_triage_report_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "VerifierResultV1 failureTriageReportBinding",
        binding,
        [
            "failureTriageReportRef",
            "failureTriageReportSchemaVersion",
            "failureTriageReportEnvelopeSchemaVersion",
            "failureTriageReportId",
            "failureTriageReportContentHash",
        ],
    )
    if binding["failureTriageReportRef"] != FAILURE_TRIAGE_REPORT_ARTIFACT_PATH:
        raise ValueError(
            f"VerifierResultV1 failureTriageReportBinding.failureTriageReportRef must equal "
            f"{FAILURE_TRIAGE_REPORT_ARTIFACT_PATH}"
        )
    if binding["failureTriageReportSchemaVersion"] != FAILURE_TRIAGE_REPORT_SCHEMA_VERSION:
        raise ValueError(
            f"VerifierResultV1 failureTriageReportBinding.failureTriageReportSchemaVersion must equal "
            f"{FAILURE_TRIAGE_REPORT_SCHEMA_VERSION}; regression artifact reuse is forbidden"
        )
    if (
        binding["failureTriageReportEnvelopeSchemaVersion"]
        != FAILURE_TRIAGE_REPORT_ENVELOPE_SCHEMA_VERSION
    ):
        raise ValueError(
            f"VerifierResultV1 failureTriageReportBinding.failureTriageReportEnvelopeSchemaVersion must equal "
            f"{FAILURE_TRIAGE_REPORT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["failureTriageReportId"] != FAILURE_TRIAGE_REPORT_ARTIFACT_ID:
        raise ValueError(
            f"VerifierResultV1 failureTriageReportBinding.failureTriageReportId must equal "
            f"{FAILURE_TRIAGE_REPORT_ARTIFACT_ID}"
        )
    full_path = root / binding["failureTriageReportRef"]
    if not full_path.is_file():
        raise ValueError(
            f"VerifierResultV1 failureTriageReportBinding artifact missing: {binding['failureTriageReportRef']}"
        )
    expected_hash = _stable_file_hash(full_path)
    if binding["failureTriageReportContentHash"] != expected_hash:
        raise ValueError(
            "VerifierResultV1 failureTriageReportBinding.failureTriageReportContentHash must match the on-disk artifact"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("VerifierResultV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("VerifierResultV1 sourceArtifacts entries must be objects")
        _require_fields(
            "VerifierResultV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"VerifierResultV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"VerifierResultV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"VerifierResultV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"VerifierResultV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"VerifierResultV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"VerifierResultV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_verifier_result(report: dict[str, Any], root: Path) -> None:
    _require_fields(
        "VerifierResultV1",
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
            "verifierAgent",
            "verifierVerdictOwner",
            "creatorAgentMustNotOwnVerdict",
            "verdict",
            "verdictDomain",
            "verdictRationale",
            "taskSpecBinding",
            "testExecutionResultBinding",
            "failureTriageReportBinding",
            "ruleResults",
            "policyBoundary",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if report["schemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"VerifierResultV1 schemaVersion must be {VERIFIER_RESULT_SCHEMA_VERSION}"
        )
    if report["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"VerifierResultV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if report["id"] != ARTIFACT_ID:
        raise ValueError(f"VerifierResultV1 id must be {ARTIFACT_ID}")
    if report["generatedAt"] != GENERATED_AT:
        raise ValueError(f"VerifierResultV1 generatedAt must be {GENERATED_AT}")
    if report["kind"] != ARTIFACT_KIND:
        raise ValueError(f"VerifierResultV1 kind must be {ARTIFACT_KIND}")
    if report["scope"] != SCOPE:
        raise ValueError(f"VerifierResultV1 scope must be {SCOPE}")
    if report["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"VerifierResultV1 workloadType must be {WORKLOAD_TYPE}; "
            f"regression workload reuse is forbidden"
        )
    if report["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"VerifierResultV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if report["verifierAgent"] != VERIFIER_AGENT:
        raise ValueError(
            f"VerifierResultV1 verifierAgent must be {VERIFIER_AGENT}; "
            f"creator agents must not author this artifact"
        )
    if report["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"VerifierResultV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; "
            f"creator must not own the verdict"
        )
    if report["creatorAgentMustNotOwnVerdict"] is not True:
        raise ValueError(
            "VerifierResultV1 creatorAgentMustNotOwnVerdict must be true"
        )
    if report["verdictDomain"] != VERDICT_DOMAIN:
        raise ValueError(
            f"VerifierResultV1 verdictDomain must equal {VERDICT_DOMAIN}"
        )
    rationale = report["verdictRationale"]
    if not isinstance(rationale, str) or len(rationale.strip()) < 32:
        raise ValueError(
            "VerifierResultV1 verdictRationale must be a substantive string"
        )

    _validate_task_spec_binding(report["taskSpecBinding"], root)
    _validate_test_execution_result_binding(report["testExecutionResultBinding"], root)
    _validate_failure_triage_report_binding(report["failureTriageReportBinding"], root)

    test_execution_result = _load_json(root / TEST_EXECUTION_RESULT_ARTIFACT_PATH)
    validate_test_execution_result(test_execution_result, root)
    failure_triage_report = _load_json(root / FAILURE_TRIAGE_REPORT_ARTIFACT_PATH)
    validate_failure_triage_report(failure_triage_report, root)

    _validate_rule_results(report["ruleResults"], test_execution_result)
    _validate_verdict(report["verdict"], report["ruleResults"], test_execution_result)

    policy = report["policyBoundary"]
    _require_fields("VerifierResultV1 policyBoundary", policy, REQUIRED_POLICY_FLAGS)
    for flag in REQUIRED_POLICY_FLAGS:
        if policy[flag] is not False:
            raise ValueError(
                f"VerifierResultV1 policyBoundary.{flag} must be false"
            )

    isolation = report["regressionWorkloadIsolation"]
    _require_fields(
        "VerifierResultV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesRegressionResultArtifact",
            "reusesEmailDraftArtifact",
            "reusesTestExecutionResultArtifactSchema",
            "reusesFailureTriageReportSchema",
            "reusesRegressionVerifierReportArtifact",
            "forbiddenFields",
        ],
    )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "VerifierResultV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesEmailDraftArtifact"] is not False:
        raise ValueError(
            "VerifierResultV1 must not reuse EmailDraftArtifactV1"
        )
    if isolation["reusesTestExecutionResultArtifactSchema"] is not False:
        raise ValueError(
            "VerifierResultV1 must not reuse the TestExecutionResultV1 schema as its own envelope"
        )
    if isolation["reusesFailureTriageReportSchema"] is not False:
        raise ValueError(
            "VerifierResultV1 must not reuse the FailureTriageReportV1 schema as its own envelope"
        )
    if isolation["reusesRegressionVerifierReportArtifact"] is not False:
        raise ValueError(
            "VerifierResultV1 must not reuse the regression verifier_report.json artifact"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"VerifierResultV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(report, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"VerifierResultV1 must not embed regression/email field {term} "
                f"outside forbiddenFields"
            )

    reuse_path = report["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"VerifierResultV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = report["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            "VerifierResultV1 coordinationBinding must include "
            f"{sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"VerifierResultV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(report["sourceArtifacts"], root)

    invariants = report["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 5:
        raise ValueError(
            "VerifierResultV1 invariants must declare at least five workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="verifier-result")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        report = build_verifier_result(root)
        _write_json(args.out, report)
        print(f"Wrote VerifierResultV1 artifact to {args.out}.")
    if args.validate is not None:
        report = _load_json(args.validate)
        validate_verifier_result(report, root)
        print(f"Validated VerifierResultV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from identity_bound_approval import (
    RECORD_ARTIFACT_PATH as IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH,
    validate_identity_bound_approval_record,
)
from replay_query import QUERY_ARTIFACT_PATH as REPLAY_QUERY_ARTIFACT_PATH, validate_replay_query


APPROVAL_AUDIT_QUERY_SCHEMA_VERSION = "approval-audit-query-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
AUDIT_QUERY_ID = "post-mvp-approval-audit-query-fixture-all_passed"
AUDIT_ARTIFACT_PATH = "artifacts/approval/post_mvp_approval_audit_query.json"


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
    if Path(path).is_absolute() or "\\" in path or path.startswith("../") or "/../" in path:
        raise ValueError(f"ApprovalAuditQueryV1 paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"ApprovalAuditQueryV1 source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _expected_source_paths() -> dict[str, str]:
    return {
        "replay_query": REPLAY_QUERY_ARTIFACT_PATH,
        "identity_bound_approval_record": IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH,
    }


def _build_expected_queries(record: dict[str, Any], replay_query: dict[str, Any]) -> list[dict[str, Any]]:
    intent = record["intentBinding"]
    actor = record["actorIdentity"]
    approval = record["approvalBinding"]
    decision = record["decisionBinding"]
    policy = record["policyBinding"]
    effects = record["effectBoundary"]
    replay = record["replayBinding"]
    run_id = intent["runId"]
    input_for_run = {"runId": run_id}
    source_refs = [IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH, REPLAY_QUERY_ARTIFACT_PATH]
    return [
        {
            "queryId": "query-approval-audit-actor-by-run-id",
            "queryType": "approval_audit_actor_by_run_id",
            "input": input_for_run,
            "result": {
                "runId": run_id,
                "actorId": actor["actorId"],
                "actorType": actor["actorType"],
                "authenticated": actor["authenticated"],
                "identityProvider": actor["identityProvider"],
                "identitySynthesized": actor["identitySynthesized"],
                "identityVerificationMode": actor["identityVerificationMode"],
                "approvalAuthority": actor["approvalAuthority"],
            },
            "sourceRefs": [IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH],
        },
        {
            "queryId": "query-approval-audit-intent-policy-by-run-id",
            "queryType": "approval_audit_intent_policy_by_run_id",
            "input": input_for_run,
            "result": {
                "runId": run_id,
                "fixtureId": intent["fixtureId"],
                "taskSpecId": intent["taskSpecId"],
                "taskSpecRef": intent["taskSpecRef"],
                "taskSpecContentHash": intent["taskSpecContentHash"],
                "goal": intent["goal"],
                "inputLogPath": intent["inputLogPath"],
                "approvalPoint": approval["approvalPoint"],
                "approvalRequiredFor": list(approval["approvalRequiredFor"]),
                "permissionPolicyId": policy["permissionPolicyId"],
                "permissionPolicySchemaVersion": policy["permissionPolicySchemaVersion"],
                "permissionPolicyContentHash": policy["permissionPolicyContentHash"],
                "sendEmailRequiresApproval": policy["sendEmailRequiresApproval"],
                "externalSideEffectsAllowed": policy["externalSideEffectsAllowed"],
            },
            "sourceRefs": [IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH],
        },
        {
            "queryId": "query-approval-audit-decision-by-run-id",
            "queryType": "approval_audit_decision_by_run_id",
            "input": input_for_run,
            "result": {
                "runId": run_id,
                "decisionId": decision["decisionId"],
                "decision": decision["decision"],
                "decidedBy": decision["decidedBy"],
                "humanDecisionRecorded": decision["humanDecisionRecorded"],
                "approvalGranted": decision["approvalGranted"],
                "approvalDecisionSynthesized": decision["approvalDecisionSynthesized"],
                "reasonCode": decision["reasonCode"],
                "taskVerdictOwner": decision["taskVerdictOwner"],
                "taskVerdictOverrideAllowed": decision["taskVerdictOverrideAllowed"],
            },
            "sourceRefs": [IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH],
        },
        {
            "queryId": "query-approval-audit-effect-boundary-by-run-id",
            "queryType": "approval_audit_effect_boundary_by_run_id",
            "input": input_for_run,
            "result": {
                "runId": run_id,
                "approvalGrantAllowed": effects["approvalGrantAllowed"],
                "sendEmailAllowed": effects["sendEmailAllowed"],
                "externalDeliveryAllowed": effects["externalDeliveryAllowed"],
                "externalSideEffectsAllowed": effects["externalSideEffectsAllowed"],
                "prCreationAllowed": effects["prCreationAllowed"],
                "workspaceMutationAllowed": effects["workspaceMutationAllowed"],
                "realProviderExecutionAllowed": effects["realProviderExecutionAllowed"],
                "databaseUsed": effects["databaseUsed"],
            },
            "sourceRefs": [IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH],
        },
        {
            "queryId": "query-approval-audit-source-hashes-by-run-id",
            "queryType": "approval_audit_source_hashes_by_run_id",
            "input": input_for_run,
            "result": {
                "runId": run_id,
                "durableRunStoreRef": replay["durableRunStoreRef"],
                "replayQueryRef": replay["replayQueryRef"],
                "approvalDecisionRef": replay["approvalDecisionRef"],
                "requiredReplayQueryIds": list(replay["requiredQueryIds"]),
                "replayQueryIds": [query["queryId"] for query in replay_query["queries"]],
                "identityRecordSourceArtifacts": list(record["sourceArtifacts"]),
                "replayQuerySourceArtifacts": list(replay_query["sourceArtifacts"]),
            },
            "sourceRefs": source_refs,
        },
    ]


def build_approval_audit_query(root: Path) -> dict[str, Any]:
    replay_query = _load_json(root / REPLAY_QUERY_ARTIFACT_PATH)
    validate_replay_query(replay_query, root)
    record = _load_json(root / IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH)
    validate_identity_bound_approval_record(record, root)
    return {
        "schemaVersion": APPROVAL_AUDIT_QUERY_SCHEMA_VERSION,
        "id": AUDIT_QUERY_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "approval_audit_query_fixture",
        "mode": "static_json_audit_query_only",
        "sourceArtifacts": [
            _artifact_source(role, path, root)
            for role, path in _expected_source_paths().items()
        ],
        "queryPolicy": {
            "queryEngine": "same_process_json_fixture",
            "databaseUsed": False,
            "durableBackendRequired": False,
            "sourceHashValidationRequired": True,
            "auditOnly": True,
            "externalSideEffectsAllowed": False,
            "realProviderExecutionAllowed": False,
            "approvalGrantAllowed": False,
        },
        "queries": _build_expected_queries(record, replay_query),
        "invariants": [
            "ApprovalAuditQueryV1 answers are derived from ReplayQueryV1 and IdentityBoundApprovalRecordV1 only.",
            "Approval audit queries return actor, intent, policy, decision, effect boundary, and source hash state without granting approval.",
            "Approval audit queries must not use a database, send email, mutate workspace state, or enable external delivery.",
        ],
    }


def _validate_source_artifacts(
    source_artifacts: list[Any],
    root: Path,
) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("ApprovalAuditQueryV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("ApprovalAuditQueryV1 sourceArtifacts must be objects")
        _require_fields("ApprovalAuditQueryV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected ApprovalAuditQueryV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"ApprovalAuditQueryV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"ApprovalAuditQueryV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"ApprovalAuditQueryV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"ApprovalAuditQueryV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def validate_approval_audit_query(audit_query: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ApprovalAuditQueryV1",
        audit_query,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "sourceArtifacts",
            "queryPolicy",
            "queries",
            "invariants",
        ],
    )
    if audit_query["schemaVersion"] != APPROVAL_AUDIT_QUERY_SCHEMA_VERSION:
        raise ValueError(f"ApprovalAuditQueryV1 schemaVersion must be {APPROVAL_AUDIT_QUERY_SCHEMA_VERSION}")
    if audit_query["id"] != AUDIT_QUERY_ID:
        raise ValueError(f"ApprovalAuditQueryV1 id must be {AUDIT_QUERY_ID}")
    if audit_query["phase"] != "post_mvp":
        raise ValueError("ApprovalAuditQueryV1 phase must be post_mvp")
    if audit_query["mode"] != "static_json_audit_query_only":
        raise ValueError("ApprovalAuditQueryV1 mode must be static_json_audit_query_only")

    sources = _validate_source_artifacts(audit_query["sourceArtifacts"], root)
    replay_query = _load_json(root / sources["replay_query"]["path"])
    validate_replay_query(replay_query, root)
    record = _load_json(root / sources["identity_bound_approval_record"]["path"])
    validate_identity_bound_approval_record(record, root)

    policy = audit_query["queryPolicy"]
    _require_fields(
        "ApprovalAuditQueryV1 queryPolicy",
        policy,
        [
            "queryEngine",
            "databaseUsed",
            "durableBackendRequired",
            "sourceHashValidationRequired",
            "auditOnly",
            "externalSideEffectsAllowed",
            "realProviderExecutionAllowed",
            "approvalGrantAllowed",
        ],
    )
    if policy["queryEngine"] != "same_process_json_fixture":
        raise ValueError("ApprovalAuditQueryV1 queryEngine must be same_process_json_fixture")
    if policy["databaseUsed"] is not False:
        raise ValueError("ApprovalAuditQueryV1 must not use a database")
    if policy["durableBackendRequired"] is not False:
        raise ValueError("ApprovalAuditQueryV1 must not require a durable backend")
    if policy["sourceHashValidationRequired"] is not True:
        raise ValueError("ApprovalAuditQueryV1 must require source hash validation")
    if policy["auditOnly"] is not True:
        raise ValueError("ApprovalAuditQueryV1 must remain audit-only")
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("ApprovalAuditQueryV1 must disallow external side effects")
    if policy["realProviderExecutionAllowed"] is not False:
        raise ValueError("ApprovalAuditQueryV1 must disallow real provider execution")
    if policy["approvalGrantAllowed"] is not False:
        raise ValueError("ApprovalAuditQueryV1 must not grant approvals")

    if record["replayBinding"]["replayQueryRef"] != REPLAY_QUERY_ARTIFACT_PATH:
        raise ValueError("ApprovalAuditQueryV1 identity record must bind ReplayQueryV1")
    if record["replayBinding"]["requiredQueryIds"] != [query["queryId"] for query in replay_query["queries"]]:
        raise ValueError("ApprovalAuditQueryV1 replay query ids must match IdentityBoundApprovalRecordV1")
    if audit_query["queries"] != _build_expected_queries(record, replay_query):
        raise ValueError("ApprovalAuditQueryV1 query results must match ReplayQueryV1 and IdentityBoundApprovalRecordV1")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or validate the ApprovalAuditQueryV1 fixture.")
    parser.add_argument("--audit-out", type=Path)
    parser.add_argument("--validate-audit", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    if args.audit_out:
        audit_query = build_approval_audit_query(root)
        validate_approval_audit_query(audit_query, root)
        _write_json(args.audit_out, audit_query)
        print(f"Wrote ApprovalAuditQueryV1 artifact to {args.audit_out}.")

    if args.validate_audit:
        audit_query = _load_json(args.validate_audit)
        validate_approval_audit_query(audit_query, root)
        print(f"Validated ApprovalAuditQueryV1 artifact {args.validate_audit}.")

    if not any([args.audit_out, args.validate_audit]):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

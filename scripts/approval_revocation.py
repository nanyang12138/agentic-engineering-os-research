from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from approval_audit_query import AUDIT_ARTIFACT_PATH, validate_approval_audit_query
from identity_bound_approval import (
    RECORD_ARTIFACT_PATH as IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH,
    validate_identity_bound_approval_record,
)


APPROVAL_REVOCATION_SCHEMA_VERSION = "approval-revocation-or-expiry-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
REVOCATION_ID = "post-mvp-approval-revocation-or-expiry-all_passed"
REVOCATION_ARTIFACT_PATH = "artifacts/approval/post_mvp_approval_revocation_or_expiry.json"


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
        raise ValueError(f"ApprovalRevocationOrExpiryV1 paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"ApprovalRevocationOrExpiryV1 source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _expected_source_paths() -> dict[str, str]:
    return {
        "approval_audit_query": AUDIT_ARTIFACT_PATH,
        "identity_bound_approval_record": IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH,
    }


def _audit_query_ids(audit_query: dict[str, Any]) -> list[str]:
    return [query["queryId"] for query in audit_query["queries"]]


def build_approval_revocation_or_expiry(root: Path) -> dict[str, Any]:
    audit_query = _load_json(root / AUDIT_ARTIFACT_PATH)
    validate_approval_audit_query(audit_query, root)
    record = _load_json(root / IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH)
    validate_identity_bound_approval_record(record, root)

    intent = record["intentBinding"]
    decision = record["decisionBinding"]
    effects = record["effectBoundary"]

    return {
        "schemaVersion": APPROVAL_REVOCATION_SCHEMA_VERSION,
        "id": REVOCATION_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "approval_revocation_or_expiry_fixture",
        "mode": "static_json_lifecycle_fixture_only",
        "sourceArtifacts": [
            _artifact_source(role, path, root)
            for role, path in _expected_source_paths().items()
        ],
        "auditBinding": {
            "approvalAuditQueryRef": AUDIT_ARTIFACT_PATH,
            "approvalAuditQueryId": audit_query["id"],
            "identityBoundApprovalRecordRef": IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH,
            "identityBoundApprovalRecordId": record["id"],
            "requiredAuditQueryIds": _audit_query_ids(audit_query),
            "sourceHashChain": list(audit_query["sourceArtifacts"]) + list(record["sourceArtifacts"]),
        },
        "approvalLifecycle": {
            "runId": intent["runId"],
            "fixtureId": intent["fixtureId"],
            "approvalPoint": record["approvalBinding"]["approvalPoint"],
            "decisionId": decision["decisionId"],
            "originalDecision": decision["decision"],
            "originalApprovalGranted": decision["approvalGranted"],
            "currentState": "expired_and_revoked",
            "expired": True,
            "expiresAt": "2026-05-13T14:39:00Z",
            "expiryReason": "static_fixture_approval_window_elapsed",
            "revoked": True,
            "revokedAt": "2026-05-13T14:40:00Z",
            "revocationReason": "mvp_policy_keeps_external_delivery_disabled",
            "activeApproval": False,
            "approvalUsableForDelivery": False,
        },
        "effectBoundary": {
            "approvalGrantAllowed": False,
            "sendEmailAllowed": effects["sendEmailAllowed"],
            "externalDeliveryAllowed": effects["externalDeliveryAllowed"],
            "externalSideEffectsAllowed": effects["externalSideEffectsAllowed"],
            "prCreationAllowed": effects["prCreationAllowed"],
            "workspaceMutationAllowed": effects["workspaceMutationAllowed"],
            "realProviderExecutionAllowed": effects["realProviderExecutionAllowed"],
            "databaseUsed": effects["databaseUsed"],
        },
        "lifecyclePolicy": {
            "stateMachine": "approval-revocation-or-expiry-v1",
            "lifecycleEventSource": "static_fixture",
            "auditOnly": True,
            "sourceHashValidationRequired": True,
            "approvalGrantAllowed": False,
            "externalSideEffectsAllowed": False,
            "realProviderExecutionAllowed": False,
            "databaseUsed": False,
        },
        "invariants": [
            "ApprovalRevocationOrExpiryV1 is derived from ApprovalAuditQueryV1 and IdentityBoundApprovalRecordV1 only.",
            "Expired or revoked approval lifecycle state cannot unlock send_email, external delivery, workspace mutation, PR creation, or provider execution.",
            "Approval lifecycle audit remains a static JSON fixture; it does not implement an approval backend or database.",
        ],
    }


def _validate_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("ApprovalRevocationOrExpiryV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("ApprovalRevocationOrExpiryV1 sourceArtifacts must be objects")
        _require_fields("ApprovalRevocationOrExpiryV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected ApprovalRevocationOrExpiryV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"ApprovalRevocationOrExpiryV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"ApprovalRevocationOrExpiryV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"ApprovalRevocationOrExpiryV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"ApprovalRevocationOrExpiryV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def validate_approval_revocation_or_expiry(payload: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ApprovalRevocationOrExpiryV1",
        payload,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "sourceArtifacts",
            "auditBinding",
            "approvalLifecycle",
            "effectBoundary",
            "lifecyclePolicy",
            "invariants",
        ],
    )
    if payload["schemaVersion"] != APPROVAL_REVOCATION_SCHEMA_VERSION:
        raise ValueError(f"ApprovalRevocationOrExpiryV1 schemaVersion must be {APPROVAL_REVOCATION_SCHEMA_VERSION}")
    if payload["id"] != REVOCATION_ID:
        raise ValueError(f"ApprovalRevocationOrExpiryV1 id must be {REVOCATION_ID}")
    if payload["phase"] != "post_mvp":
        raise ValueError("ApprovalRevocationOrExpiryV1 phase must be post_mvp")
    if payload["mode"] != "static_json_lifecycle_fixture_only":
        raise ValueError("ApprovalRevocationOrExpiryV1 mode must be static_json_lifecycle_fixture_only")

    sources = _validate_source_artifacts(payload["sourceArtifacts"], root)
    audit_query = _load_json(root / sources["approval_audit_query"]["path"])
    validate_approval_audit_query(audit_query, root)
    record = _load_json(root / sources["identity_bound_approval_record"]["path"])
    validate_identity_bound_approval_record(record, root)

    audit = payload["auditBinding"]
    _require_fields(
        "ApprovalRevocationOrExpiryV1 auditBinding",
        audit,
        [
            "approvalAuditQueryRef",
            "approvalAuditQueryId",
            "identityBoundApprovalRecordRef",
            "identityBoundApprovalRecordId",
            "requiredAuditQueryIds",
            "sourceHashChain",
        ],
    )
    if audit["approvalAuditQueryRef"] != AUDIT_ARTIFACT_PATH or audit["approvalAuditQueryId"] != audit_query["id"]:
        raise ValueError("ApprovalRevocationOrExpiryV1 auditBinding must bind ApprovalAuditQueryV1")
    if audit["identityBoundApprovalRecordRef"] != IDENTITY_BOUND_APPROVAL_RECORD_ARTIFACT_PATH or audit["identityBoundApprovalRecordId"] != record["id"]:
        raise ValueError("ApprovalRevocationOrExpiryV1 auditBinding must bind IdentityBoundApprovalRecordV1")
    if audit["requiredAuditQueryIds"] != _audit_query_ids(audit_query):
        raise ValueError("ApprovalRevocationOrExpiryV1 audit query ids must match ApprovalAuditQueryV1")
    expected_hash_chain = list(audit_query["sourceArtifacts"]) + list(record["sourceArtifacts"])
    if audit["sourceHashChain"] != expected_hash_chain:
        raise ValueError("ApprovalRevocationOrExpiryV1 source hash chain must match audit and identity sources")

    lifecycle = payload["approvalLifecycle"]
    _require_fields(
        "ApprovalRevocationOrExpiryV1 approvalLifecycle",
        lifecycle,
        [
            "runId",
            "fixtureId",
            "approvalPoint",
            "decisionId",
            "originalDecision",
            "originalApprovalGranted",
            "currentState",
            "expired",
            "expiresAt",
            "expiryReason",
            "revoked",
            "revokedAt",
            "revocationReason",
            "activeApproval",
            "approvalUsableForDelivery",
        ],
    )
    intent = record["intentBinding"]
    decision = record["decisionBinding"]
    if lifecycle["runId"] != intent["runId"] or lifecycle["fixtureId"] != intent["fixtureId"]:
        raise ValueError("ApprovalRevocationOrExpiryV1 lifecycle must bind the identity record intent")
    if lifecycle["approvalPoint"] != record["approvalBinding"]["approvalPoint"]:
        raise ValueError("ApprovalRevocationOrExpiryV1 lifecycle approvalPoint must match identity record")
    if lifecycle["decisionId"] != decision["decisionId"] or lifecycle["originalDecision"] != decision["decision"]:
        raise ValueError("ApprovalRevocationOrExpiryV1 lifecycle decision must match identity record")
    if lifecycle["originalApprovalGranted"] != decision["approvalGranted"]:
        raise ValueError("ApprovalRevocationOrExpiryV1 original approval grant must match identity record")
    if lifecycle["originalApprovalGranted"] is not False:
        raise ValueError("ApprovalRevocationOrExpiryV1 must start from a non-granted approval decision")
    if lifecycle["currentState"] != "expired_and_revoked":
        raise ValueError("ApprovalRevocationOrExpiryV1 currentState must be expired_and_revoked")
    if lifecycle["expired"] is not True or lifecycle["revoked"] is not True:
        raise ValueError("ApprovalRevocationOrExpiryV1 must mark the approval lifecycle as expired and revoked")
    if lifecycle["activeApproval"] is not False:
        raise ValueError("ApprovalRevocationOrExpiryV1 activeApproval must be false")
    if lifecycle["approvalUsableForDelivery"] is not False:
        raise ValueError("ApprovalRevocationOrExpiryV1 approvalUsableForDelivery must be false")

    effects = payload["effectBoundary"]
    _require_fields(
        "ApprovalRevocationOrExpiryV1 effectBoundary",
        effects,
        [
            "approvalGrantAllowed",
            "sendEmailAllowed",
            "externalDeliveryAllowed",
            "externalSideEffectsAllowed",
            "prCreationAllowed",
            "workspaceMutationAllowed",
            "realProviderExecutionAllowed",
            "databaseUsed",
        ],
    )
    for field in [
        "approvalGrantAllowed",
        "sendEmailAllowed",
        "externalDeliveryAllowed",
        "externalSideEffectsAllowed",
        "prCreationAllowed",
        "workspaceMutationAllowed",
        "realProviderExecutionAllowed",
        "databaseUsed",
    ]:
        if effects[field] is not False:
            raise ValueError(f"ApprovalRevocationOrExpiryV1 effectBoundary {field} must be false")

    policy = payload["lifecyclePolicy"]
    _require_fields(
        "ApprovalRevocationOrExpiryV1 lifecyclePolicy",
        policy,
        [
            "stateMachine",
            "lifecycleEventSource",
            "auditOnly",
            "sourceHashValidationRequired",
            "approvalGrantAllowed",
            "externalSideEffectsAllowed",
            "realProviderExecutionAllowed",
            "databaseUsed",
        ],
    )
    if policy["stateMachine"] != APPROVAL_REVOCATION_SCHEMA_VERSION:
        raise ValueError("ApprovalRevocationOrExpiryV1 lifecyclePolicy must use approval-revocation-or-expiry-v1")
    if policy["auditOnly"] is not True:
        raise ValueError("ApprovalRevocationOrExpiryV1 lifecyclePolicy must remain audit-only")
    if policy["sourceHashValidationRequired"] is not True:
        raise ValueError("ApprovalRevocationOrExpiryV1 lifecyclePolicy must require source hash validation")
    for field in ["approvalGrantAllowed", "externalSideEffectsAllowed", "realProviderExecutionAllowed", "databaseUsed"]:
        if policy[field] is not False:
            raise ValueError(f"ApprovalRevocationOrExpiryV1 lifecyclePolicy {field} must be false")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or validate the ApprovalRevocationOrExpiryV1 fixture.")
    parser.add_argument("--revocation-out", type=Path)
    parser.add_argument("--validate-revocation", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    if args.revocation_out:
        revocation = build_approval_revocation_or_expiry(root)
        validate_approval_revocation_or_expiry(revocation, root)
        _write_json(args.revocation_out, revocation)
        print(f"Wrote ApprovalRevocationOrExpiryV1 artifact to {args.revocation_out}.")

    if args.validate_revocation:
        revocation = _load_json(args.validate_revocation)
        validate_approval_revocation_or_expiry(revocation, root)
        print(f"Validated ApprovalRevocationOrExpiryV1 artifact {args.validate_revocation}.")

    if not any([args.revocation_out, args.validate_revocation]):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

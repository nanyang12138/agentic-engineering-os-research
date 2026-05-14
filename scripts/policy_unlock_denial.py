from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from approval_revocation import REVOCATION_ARTIFACT_PATH, validate_approval_revocation_or_expiry
from multi_agent_delivery import DELIVERY_REPORT_ARTIFACT_PATH, validate_delivery_report


POLICY_UNLOCK_DENIAL_SCHEMA_VERSION = "policy-unlock-request-denied-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
UNLOCK_DENIAL_ID = "post-mvp-policy-unlock-request-denied-all_passed"
UNLOCK_DENIAL_ARTIFACT_PATH = "artifacts/approval/post_mvp_policy_unlock_request_denied.json"


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
        raise ValueError(f"PolicyUnlockRequestDeniedV1 paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"PolicyUnlockRequestDeniedV1 source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _expected_source_paths() -> dict[str, str]:
    return {
        "approval_revocation_or_expiry": REVOCATION_ARTIFACT_PATH,
        "delivery_report": DELIVERY_REPORT_ARTIFACT_PATH,
    }


def _delivery_blocker_ids(delivery_report: dict[str, Any]) -> list[str]:
    return [blocker["id"] for blocker in delivery_report["blockers"]]


def build_policy_unlock_request_denied(root: Path) -> dict[str, Any]:
    revocation = _load_json(root / REVOCATION_ARTIFACT_PATH)
    validate_approval_revocation_or_expiry(revocation, root)
    delivery_report = _load_json(root / DELIVERY_REPORT_ARTIFACT_PATH)
    validate_delivery_report(delivery_report, root)

    lifecycle = revocation["approvalLifecycle"]
    effects = revocation["effectBoundary"]
    delivery_readiness = delivery_report["readiness"]
    delivery_blockers = _delivery_blocker_ids(delivery_report)

    return {
        "schemaVersion": POLICY_UNLOCK_DENIAL_SCHEMA_VERSION,
        "id": UNLOCK_DENIAL_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "policy_unlock_request_denial_fixture",
        "mode": "static_json_policy_request_fixture_only",
        "sourceArtifacts": [
            _artifact_source(role, path, root)
            for role, path in _expected_source_paths().items()
        ],
        "unlockRequest": {
            "requestId": "unlock-request-all_passed-send-email-delivery",
            "requestType": "delivery_unlock_request",
            "requestedBy": "static_downstream_delivery_adapter_fixture",
            "runId": lifecycle["runId"],
            "fixtureId": lifecycle["fixtureId"],
            "approvalPoint": lifecycle["approvalPoint"],
            "decisionId": lifecycle["decisionId"],
            "requestedEffects": {
                "sendEmail": True,
                "externalDelivery": True,
                "prCreation": True,
                "workspaceMutation": False,
                "realProviderExecution": False,
            },
            "sourceRef": DELIVERY_REPORT_ARTIFACT_PATH,
        },
        "policyInputs": {
            "approvalRevocationRef": REVOCATION_ARTIFACT_PATH,
            "approvalRevocationId": revocation["id"],
            "approvalCurrentState": lifecycle["currentState"],
            "expired": lifecycle["expired"],
            "revoked": lifecycle["revoked"],
            "activeApproval": lifecycle["activeApproval"],
            "approvalUsableForDelivery": lifecycle["approvalUsableForDelivery"],
            "deliveryReportRef": DELIVERY_REPORT_ARTIFACT_PATH,
            "readyForExternalDelivery": delivery_readiness["readyForExternalDelivery"],
            "deliveryBlockerIds": delivery_blockers,
            "sourceHashChain": list(revocation["sourceArtifacts"]) + list(delivery_report["sourceArtifacts"]),
            "effectBoundary": dict(effects),
        },
        "denialDecision": {
            "decision": "denied",
            "unlockAllowed": False,
            "reasonCode": "expired_revoked_approval_and_mvp_no_side_effect_policy",
            "blockingReasons": [
                "approval_expired_or_revoked",
                "mvp_no_external_side_effects_policy",
                "delivery_report_blocks_external_delivery",
            ],
            "policyOwner": "permission-policy-v1",
            "verifierVerdictOwner": "verifier-runtime-v1",
        },
        "effectsAfterDecision": {
            "approvalGrantAllowed": False,
            "sendEmailAllowed": False,
            "externalDeliveryAllowed": False,
            "externalSideEffectsAllowed": False,
            "prCreationAllowed": False,
            "workspaceMutationAllowed": False,
            "realProviderExecutionAllowed": False,
            "databaseUsed": effects["databaseUsed"],
        },
        "requestPolicy": {
            "policySchemaVersion": POLICY_UNLOCK_DENIAL_SCHEMA_VERSION,
            "sourceHashValidationRequired": True,
            "approvalLifecycleRequiredState": "expired_and_revoked",
            "denyWhenApprovalExpiredOrRevoked": True,
            "denyWhenMvpNoSideEffects": True,
            "auditOnly": True,
            "databaseUsed": False,
            "externalSideEffectsAllowed": False,
            "realProviderExecutionAllowed": False,
        },
        "invariants": [
            "PolicyUnlockRequestDeniedV1 records a denied downstream unlock request; it does not grant delivery permission.",
            "Expired or revoked approval state and MVP no-side-effect policy must block send_email, external delivery, PR creation, workspace mutation, and provider execution.",
            "Policy unlock denial remains a static JSON fixture, not a production policy engine, approval backend, or delivery adapter.",
        ],
    }


def _validate_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("PolicyUnlockRequestDeniedV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("PolicyUnlockRequestDeniedV1 sourceArtifacts must be objects")
        _require_fields("PolicyUnlockRequestDeniedV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected PolicyUnlockRequestDeniedV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"PolicyUnlockRequestDeniedV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"PolicyUnlockRequestDeniedV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"PolicyUnlockRequestDeniedV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"PolicyUnlockRequestDeniedV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def validate_policy_unlock_request_denied(payload: dict[str, Any], root: Path) -> None:
    _require_fields(
        "PolicyUnlockRequestDeniedV1",
        payload,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "sourceArtifacts",
            "unlockRequest",
            "policyInputs",
            "denialDecision",
            "effectsAfterDecision",
            "requestPolicy",
            "invariants",
        ],
    )
    if payload["schemaVersion"] != POLICY_UNLOCK_DENIAL_SCHEMA_VERSION:
        raise ValueError(f"PolicyUnlockRequestDeniedV1 schemaVersion must be {POLICY_UNLOCK_DENIAL_SCHEMA_VERSION}")
    if payload["id"] != UNLOCK_DENIAL_ID:
        raise ValueError(f"PolicyUnlockRequestDeniedV1 id must be {UNLOCK_DENIAL_ID}")
    if payload["phase"] != "post_mvp":
        raise ValueError("PolicyUnlockRequestDeniedV1 phase must be post_mvp")
    if payload["mode"] != "static_json_policy_request_fixture_only":
        raise ValueError("PolicyUnlockRequestDeniedV1 mode must be static_json_policy_request_fixture_only")

    sources = _validate_source_artifacts(payload["sourceArtifacts"], root)
    revocation = _load_json(root / sources["approval_revocation_or_expiry"]["path"])
    validate_approval_revocation_or_expiry(revocation, root)
    delivery_report = _load_json(root / sources["delivery_report"]["path"])
    validate_delivery_report(delivery_report, root)
    lifecycle = revocation["approvalLifecycle"]
    effects = revocation["effectBoundary"]
    delivery_readiness = delivery_report["readiness"]
    delivery_blockers = _delivery_blocker_ids(delivery_report)

    request = payload["unlockRequest"]
    _require_fields(
        "PolicyUnlockRequestDeniedV1 unlockRequest",
        request,
        [
            "requestId",
            "requestType",
            "requestedBy",
            "runId",
            "fixtureId",
            "approvalPoint",
            "decisionId",
            "requestedEffects",
            "sourceRef",
        ],
    )
    if request["requestType"] != "delivery_unlock_request":
        raise ValueError("PolicyUnlockRequestDeniedV1 requestType must be delivery_unlock_request")
    if request["runId"] != lifecycle["runId"] or request["fixtureId"] != lifecycle["fixtureId"]:
        raise ValueError("PolicyUnlockRequestDeniedV1 unlock request must bind the revocation lifecycle run")
    if request["approvalPoint"] != lifecycle["approvalPoint"] or request["decisionId"] != lifecycle["decisionId"]:
        raise ValueError("PolicyUnlockRequestDeniedV1 unlock request must bind the revoked approval decision")
    if request["sourceRef"] != DELIVERY_REPORT_ARTIFACT_PATH:
        raise ValueError("PolicyUnlockRequestDeniedV1 unlock request sourceRef must bind DeliveryReportV1")
    requested_effects = request["requestedEffects"]
    _require_fields(
        "PolicyUnlockRequestDeniedV1 requestedEffects",
        requested_effects,
        ["sendEmail", "externalDelivery", "prCreation", "workspaceMutation", "realProviderExecution"],
    )
    if requested_effects["sendEmail"] is not True or requested_effects["externalDelivery"] is not True:
        raise ValueError("PolicyUnlockRequestDeniedV1 fixture must request send_email and external delivery unlock")
    if requested_effects["workspaceMutation"] is not False or requested_effects["realProviderExecution"] is not False:
        raise ValueError("PolicyUnlockRequestDeniedV1 fixture must not request workspace mutation or real provider execution")

    policy_inputs = payload["policyInputs"]
    _require_fields(
        "PolicyUnlockRequestDeniedV1 policyInputs",
        policy_inputs,
        [
            "approvalRevocationRef",
            "approvalRevocationId",
            "approvalCurrentState",
            "expired",
            "revoked",
            "activeApproval",
            "approvalUsableForDelivery",
            "deliveryReportRef",
            "readyForExternalDelivery",
            "deliveryBlockerIds",
            "sourceHashChain",
            "effectBoundary",
        ],
    )
    if policy_inputs["approvalRevocationRef"] != REVOCATION_ARTIFACT_PATH or policy_inputs["approvalRevocationId"] != revocation["id"]:
        raise ValueError("PolicyUnlockRequestDeniedV1 policyInputs must bind ApprovalRevocationOrExpiryV1")
    if policy_inputs["approvalCurrentState"] != "expired_and_revoked":
        raise ValueError("PolicyUnlockRequestDeniedV1 approvalCurrentState must be expired_and_revoked")
    if policy_inputs["expired"] is not True or policy_inputs["revoked"] is not True:
        raise ValueError("PolicyUnlockRequestDeniedV1 approval lifecycle input must be expired and revoked")
    if policy_inputs["activeApproval"] is not False or policy_inputs["approvalUsableForDelivery"] is not False:
        raise ValueError("PolicyUnlockRequestDeniedV1 approval lifecycle input must not be active or usable")
    if policy_inputs["deliveryReportRef"] != DELIVERY_REPORT_ARTIFACT_PATH:
        raise ValueError("PolicyUnlockRequestDeniedV1 policyInputs must bind DeliveryReportV1")
    if policy_inputs["readyForExternalDelivery"] != delivery_readiness["readyForExternalDelivery"]:
        raise ValueError("PolicyUnlockRequestDeniedV1 external delivery readiness must match DeliveryReportV1")
    if policy_inputs["readyForExternalDelivery"] is not False:
        raise ValueError("PolicyUnlockRequestDeniedV1 must start from blocked external delivery readiness")
    if policy_inputs["deliveryBlockerIds"] != delivery_blockers:
        raise ValueError("PolicyUnlockRequestDeniedV1 delivery blockers must match DeliveryReportV1")
    for required_blocker in ["human_approval_missing", "external_delivery_disabled_by_mvp_policy"]:
        if required_blocker not in policy_inputs["deliveryBlockerIds"]:
            raise ValueError(f"PolicyUnlockRequestDeniedV1 delivery blockers must include {required_blocker}")
    expected_hash_chain = list(revocation["sourceArtifacts"]) + list(delivery_report["sourceArtifacts"])
    if policy_inputs["sourceHashChain"] != expected_hash_chain:
        raise ValueError("PolicyUnlockRequestDeniedV1 source hash chain must match revocation and delivery sources")
    if policy_inputs["effectBoundary"] != effects:
        raise ValueError("PolicyUnlockRequestDeniedV1 policyInputs effectBoundary must match ApprovalRevocationOrExpiryV1")

    decision = payload["denialDecision"]
    _require_fields(
        "PolicyUnlockRequestDeniedV1 denialDecision",
        decision,
        ["decision", "unlockAllowed", "reasonCode", "blockingReasons", "policyOwner", "verifierVerdictOwner"],
    )
    if decision["decision"] != "denied":
        raise ValueError("PolicyUnlockRequestDeniedV1 denialDecision must be denied")
    if decision["unlockAllowed"] is not False:
        raise ValueError("PolicyUnlockRequestDeniedV1 unlockAllowed must be false")
    required_reasons = {
        "approval_expired_or_revoked",
        "mvp_no_external_side_effects_policy",
        "delivery_report_blocks_external_delivery",
    }
    reasons = set(decision["blockingReasons"]) if isinstance(decision["blockingReasons"], list) else set()
    missing_reasons = required_reasons - reasons
    if missing_reasons:
        raise ValueError(f"PolicyUnlockRequestDeniedV1 blockingReasons must include {sorted(missing_reasons)}")
    if decision["policyOwner"] != "permission-policy-v1":
        raise ValueError("PolicyUnlockRequestDeniedV1 policyOwner must remain permission-policy-v1")
    if decision["verifierVerdictOwner"] != "verifier-runtime-v1":
        raise ValueError("PolicyUnlockRequestDeniedV1 verifier verdict owner must remain verifier-runtime-v1")

    effects_after = payload["effectsAfterDecision"]
    _require_fields(
        "PolicyUnlockRequestDeniedV1 effectsAfterDecision",
        effects_after,
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
        if effects_after[field] is not False:
            raise ValueError(f"PolicyUnlockRequestDeniedV1 effectsAfterDecision {field} must be false")

    request_policy = payload["requestPolicy"]
    _require_fields(
        "PolicyUnlockRequestDeniedV1 requestPolicy",
        request_policy,
        [
            "policySchemaVersion",
            "sourceHashValidationRequired",
            "approvalLifecycleRequiredState",
            "denyWhenApprovalExpiredOrRevoked",
            "denyWhenMvpNoSideEffects",
            "auditOnly",
            "databaseUsed",
            "externalSideEffectsAllowed",
            "realProviderExecutionAllowed",
        ],
    )
    if request_policy["policySchemaVersion"] != POLICY_UNLOCK_DENIAL_SCHEMA_VERSION:
        raise ValueError("PolicyUnlockRequestDeniedV1 requestPolicy must use policy-unlock-request-denied-v1")
    if request_policy["sourceHashValidationRequired"] is not True:
        raise ValueError("PolicyUnlockRequestDeniedV1 requestPolicy must require source hash validation")
    if request_policy["approvalLifecycleRequiredState"] != "expired_and_revoked":
        raise ValueError("PolicyUnlockRequestDeniedV1 requestPolicy must require expired_and_revoked lifecycle state")
    if request_policy["denyWhenApprovalExpiredOrRevoked"] is not True:
        raise ValueError("PolicyUnlockRequestDeniedV1 requestPolicy must deny expired or revoked approvals")
    if request_policy["denyWhenMvpNoSideEffects"] is not True:
        raise ValueError("PolicyUnlockRequestDeniedV1 requestPolicy must deny MVP external side effects")
    if request_policy["auditOnly"] is not True:
        raise ValueError("PolicyUnlockRequestDeniedV1 requestPolicy must remain audit-only")
    for field in ["databaseUsed", "externalSideEffectsAllowed", "realProviderExecutionAllowed"]:
        if request_policy[field] is not False:
            raise ValueError(f"PolicyUnlockRequestDeniedV1 requestPolicy {field} must be false")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or validate the PolicyUnlockRequestDeniedV1 fixture.")
    parser.add_argument("--denial-out", type=Path)
    parser.add_argument("--validate-denial", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    if args.denial_out:
        denial = build_policy_unlock_request_denied(root)
        validate_policy_unlock_request_denied(denial, root)
        _write_json(args.denial_out, denial)
        print(f"Wrote PolicyUnlockRequestDeniedV1 artifact to {args.denial_out}.")

    if args.validate_denial:
        denial = _load_json(args.validate_denial)
        validate_policy_unlock_request_denied(denial, root)
        print(f"Validated PolicyUnlockRequestDeniedV1 artifact {args.validate_denial}.")

    if not any([args.denial_out, args.validate_denial]):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

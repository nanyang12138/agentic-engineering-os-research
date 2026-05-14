from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from durable_run_store import STORE_ARTIFACT_PATH, validate_durable_run_store
from human_approval import DECISION_ARTIFACT_PATH, validate_human_approval_decision
from replay_query import QUERY_ARTIFACT_PATH, validate_replay_query


IDENTITY_BOUND_APPROVAL_SCHEMA_VERSION = "identity-bound-approval-record-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
RECORD_ID = "post-mvp-identity-bound-approval-record-all_passed"
RECORD_ARTIFACT_PATH = "artifacts/approval/post_mvp_identity_bound_approval_record.json"

DEFAULT_RUN_PATH = "artifacts/runs/all_passed/run.json"
ACTOR_ID = "static-human-approver-fixture"
APPROVAL_AUTHORITY = "permission-policy-v1:send_email_requires_human_approval"


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _stable_json_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
        raise ValueError(f"IdentityBoundApprovalRecord paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"IdentityBoundApprovalRecord source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _expected_source_paths() -> dict[str, str]:
    return {
        "human_approval_decision": DECISION_ARTIFACT_PATH,
        "durable_run_store": STORE_ARTIFACT_PATH,
        "replay_query": QUERY_ARTIFACT_PATH,
        "run": DEFAULT_RUN_PATH,
    }


def _query_ids(replay_query: dict[str, Any]) -> list[str]:
    return [query["queryId"] for query in replay_query["queries"]]


def build_identity_bound_approval_record(root: Path) -> dict[str, Any]:
    decision = _load_json(root / DECISION_ARTIFACT_PATH)
    validate_human_approval_decision(decision, root)
    store = _load_json(root / STORE_ARTIFACT_PATH)
    validate_durable_run_store(store, root)
    replay_query = _load_json(root / QUERY_ARTIFACT_PATH)
    validate_replay_query(replay_query, root)
    run = _load_json(root / DEFAULT_RUN_PATH)

    task_spec = run["taskSpec"]
    permission_policy = run["runControl"]["permissionPolicy"]
    approval_binding = decision["approvalBinding"]
    human_decision = decision["decision"]
    policy_effects = decision["policyEffects"]

    return {
        "schemaVersion": IDENTITY_BOUND_APPROVAL_SCHEMA_VERSION,
        "id": RECORD_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "identity_bound_approval_record_fixture",
        "mode": "static_identity_fixture_only",
        "sourceArtifacts": [
            _artifact_source(role, path, root)
            for role, path in _expected_source_paths().items()
        ],
        "actorIdentity": {
            "actorId": ACTOR_ID,
            "actorType": "human",
            "identityProvider": "static_fixture_identity_provider",
            "authenticated": True,
            "identitySynthesized": False,
            "identityVerificationMode": "source_hash_bound_static_fixture",
            "approvalAuthority": APPROVAL_AUTHORITY,
        },
        "intentBinding": {
            "runId": run["id"],
            "fixtureId": run["fixtureId"],
            "taskSpecRef": approval_binding["taskSpecRef"],
            "taskSpecId": task_spec["id"],
            "taskSpecContentHash": _stable_json_hash(task_spec),
            "goal": task_spec["goal"],
            "inputLogPath": task_spec["inputLogPath"],
        },
        "approvalBinding": {
            "approvalPoint": approval_binding["approvalPoint"],
            "handoffRequestId": approval_binding["handoffRequestId"],
            "handoffCapabilityRef": approval_binding["handoffCapabilityRef"],
            "permissionPolicyRef": approval_binding["permissionPolicyRef"],
            "permissionPolicySchemaVersion": approval_binding["permissionPolicySchemaVersion"],
            "approvalRequiredFor": list(permission_policy["approvalRequiredFor"]),
        },
        "decisionBinding": {
            "decisionId": human_decision["decisionId"],
            "decision": human_decision["decision"],
            "decidedBy": human_decision["decidedBy"],
            "humanDecisionRecorded": human_decision["humanDecisionRecorded"],
            "approvalGranted": human_decision["approvalGranted"],
            "approvalDecisionSynthesized": human_decision["approvalDecisionSynthesized"],
            "reasonCode": human_decision["reasonCode"],
            "taskVerdictOwner": decision["verifierBinding"]["taskVerdictOwner"],
            "taskVerdictOverrideAllowed": decision["verifierBinding"]["taskVerdictOverrideAllowed"],
        },
        "policyBinding": {
            "permissionPolicyId": permission_policy["id"],
            "permissionPolicySchemaVersion": permission_policy["schemaVersion"],
            "permissionPolicyContentHash": _stable_json_hash(permission_policy),
            "externalSideEffectsAllowed": permission_policy["externalSideEffectsAllowed"],
            "sendEmailRequiresApproval": "send_email" in permission_policy["approvalRequiredFor"],
            "localWriteBoundary": permission_policy["localWriteBoundary"],
        },
        "replayBinding": {
            "durableRunStoreRef": STORE_ARTIFACT_PATH,
            "durableRunStoreId": store["id"],
            "replayQueryRef": QUERY_ARTIFACT_PATH,
            "replayQueryId": replay_query["id"],
            "requiredQueryIds": _query_ids(replay_query),
            "approvalDecisionRef": store["runIndex"]["humanApprovalDecisionRef"],
        },
        "effectBoundary": {
            "approvalGrantAllowed": False,
            "sendEmailAllowed": policy_effects["sendEmailAllowed"],
            "externalDeliveryAllowed": policy_effects["externalDeliveryAllowed"],
            "externalSideEffectsAllowed": policy_effects["externalSideEffectsAllowed"],
            "prCreationAllowed": policy_effects["prCreationAllowed"],
            "workspaceMutationAllowed": policy_effects["workspaceMutationAllowed"],
            "realProviderExecutionAllowed": False,
            "databaseUsed": False,
        },
        "invariants": [
            "IdentityBoundApprovalRecordV1 binds a human decision to an actor, intent, policy, replay store, and source hashes.",
            "This fixture records identity provenance only; it does not grant approval or execute an approval backend.",
            "Identity binding cannot override VerifierRuntimeV1 verdicts, permission-policy-v1, or no-side-effect delivery policy.",
        ],
    }


def _validate_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("IdentityBoundApprovalRecordV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("IdentityBoundApprovalRecordV1 sourceArtifacts must be objects")
        _require_fields("IdentityBoundApprovalRecordV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected IdentityBoundApprovalRecordV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"IdentityBoundApprovalRecordV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"IdentityBoundApprovalRecordV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"IdentityBoundApprovalRecordV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"IdentityBoundApprovalRecordV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def validate_identity_bound_approval_record(record: dict[str, Any], root: Path) -> None:
    _require_fields(
        "IdentityBoundApprovalRecordV1",
        record,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "sourceArtifacts",
            "actorIdentity",
            "intentBinding",
            "approvalBinding",
            "decisionBinding",
            "policyBinding",
            "replayBinding",
            "effectBoundary",
            "invariants",
        ],
    )
    if record["schemaVersion"] != IDENTITY_BOUND_APPROVAL_SCHEMA_VERSION:
        raise ValueError(f"IdentityBoundApprovalRecordV1 schemaVersion must be {IDENTITY_BOUND_APPROVAL_SCHEMA_VERSION}")
    if record["id"] != RECORD_ID:
        raise ValueError(f"IdentityBoundApprovalRecordV1 id must be {RECORD_ID}")
    if record["phase"] != "post_mvp":
        raise ValueError("IdentityBoundApprovalRecordV1 phase must be post_mvp")
    if record["mode"] != "static_identity_fixture_only":
        raise ValueError("IdentityBoundApprovalRecordV1 mode must be static_identity_fixture_only")

    sources = _validate_source_artifacts(record["sourceArtifacts"], root)
    decision = _load_json(root / sources["human_approval_decision"]["path"])
    validate_human_approval_decision(decision, root)
    store = _load_json(root / sources["durable_run_store"]["path"])
    validate_durable_run_store(store, root)
    replay_query = _load_json(root / sources["replay_query"]["path"])
    validate_replay_query(replay_query, root)
    run = _load_json(root / sources["run"]["path"])

    actor = record["actorIdentity"]
    _require_fields(
        "IdentityBoundApprovalRecordV1 actorIdentity",
        actor,
        [
            "actorId",
            "actorType",
            "identityProvider",
            "authenticated",
            "identitySynthesized",
            "identityVerificationMode",
            "approvalAuthority",
        ],
    )
    if actor["actorId"] != ACTOR_ID:
        raise ValueError(f"IdentityBoundApprovalRecordV1 actorId must be {ACTOR_ID}")
    if actor["actorType"] != "human":
        raise ValueError("IdentityBoundApprovalRecordV1 actorType must be human")
    if actor["authenticated"] is not True:
        raise ValueError("IdentityBoundApprovalRecordV1 actor must be authenticated")
    if actor["identitySynthesized"] is not False:
        raise ValueError("IdentityBoundApprovalRecordV1 must not synthesize actor identity")
    if actor["approvalAuthority"] != APPROVAL_AUTHORITY:
        raise ValueError("IdentityBoundApprovalRecordV1 approval authority must match permission policy approval point")

    task_spec = run["taskSpec"]
    intent = record["intentBinding"]
    _require_fields(
        "IdentityBoundApprovalRecordV1 intentBinding",
        intent,
        ["runId", "fixtureId", "taskSpecRef", "taskSpecId", "taskSpecContentHash", "goal", "inputLogPath"],
    )
    if intent["runId"] != run["id"] or intent["fixtureId"] != run["fixtureId"]:
        raise ValueError("IdentityBoundApprovalRecordV1 intent must bind the all_passed run")
    if intent["taskSpecRef"] != decision["approvalBinding"]["taskSpecRef"]:
        raise ValueError("IdentityBoundApprovalRecordV1 intent taskSpecRef must match HumanApprovalDecisionV1")
    if intent["taskSpecId"] != task_spec["id"]:
        raise ValueError("IdentityBoundApprovalRecordV1 intent taskSpecId must match Run taskSpec")
    if intent["taskSpecContentHash"] != _stable_json_hash(task_spec):
        raise ValueError("IdentityBoundApprovalRecordV1 intent taskSpecContentHash must match Run taskSpec")
    if intent["goal"] != task_spec["goal"] or intent["inputLogPath"] != task_spec["inputLogPath"]:
        raise ValueError("IdentityBoundApprovalRecordV1 intent goal and input log must match Run taskSpec")

    approval = record["approvalBinding"]
    _require_fields(
        "IdentityBoundApprovalRecordV1 approvalBinding",
        approval,
        [
            "approvalPoint",
            "handoffRequestId",
            "handoffCapabilityRef",
            "permissionPolicyRef",
            "permissionPolicySchemaVersion",
            "approvalRequiredFor",
        ],
    )
    decision_approval = decision["approvalBinding"]
    for field in ["approvalPoint", "handoffRequestId", "handoffCapabilityRef", "permissionPolicyRef", "permissionPolicySchemaVersion"]:
        if approval[field] != decision_approval[field]:
            raise ValueError(f"IdentityBoundApprovalRecordV1 approvalBinding {field} must match HumanApprovalDecisionV1")
    if "send_email" not in approval["approvalRequiredFor"]:
        raise ValueError("IdentityBoundApprovalRecordV1 approvalBinding must require send_email approval")

    decision_binding = record["decisionBinding"]
    _require_fields(
        "IdentityBoundApprovalRecordV1 decisionBinding",
        decision_binding,
        [
            "decisionId",
            "decision",
            "decidedBy",
            "humanDecisionRecorded",
            "approvalGranted",
            "approvalDecisionSynthesized",
            "reasonCode",
            "taskVerdictOwner",
            "taskVerdictOverrideAllowed",
        ],
    )
    human_decision = decision["decision"]
    if decision_binding["humanDecisionRecorded"] is not True:
        raise ValueError("IdentityBoundApprovalRecordV1 must bind a recorded human decision")
    if decision_binding["approvalGranted"] is not False:
        raise ValueError("IdentityBoundApprovalRecordV1 must not grant approval")
    if decision_binding["approvalDecisionSynthesized"] is not False:
        raise ValueError("IdentityBoundApprovalRecordV1 must not synthesize approval decisions")
    for field in ["decisionId", "decision", "decidedBy", "humanDecisionRecorded", "approvalGranted", "approvalDecisionSynthesized", "reasonCode"]:
        if decision_binding[field] != human_decision[field]:
            raise ValueError(f"IdentityBoundApprovalRecordV1 decisionBinding {field} must match HumanApprovalDecisionV1")
    if decision_binding["taskVerdictOwner"] != "verifier-runtime-v1":
        raise ValueError("IdentityBoundApprovalRecordV1 task verdict owner must remain verifier-runtime-v1")
    if decision_binding["taskVerdictOverrideAllowed"] is not False:
        raise ValueError("IdentityBoundApprovalRecordV1 must not override verifier verdicts")

    permission_policy = run["runControl"]["permissionPolicy"]
    policy = record["policyBinding"]
    _require_fields(
        "IdentityBoundApprovalRecordV1 policyBinding",
        policy,
        [
            "permissionPolicyId",
            "permissionPolicySchemaVersion",
            "permissionPolicyContentHash",
            "externalSideEffectsAllowed",
            "sendEmailRequiresApproval",
            "localWriteBoundary",
        ],
    )
    if policy["permissionPolicyId"] != permission_policy["id"]:
        raise ValueError("IdentityBoundApprovalRecordV1 policyBinding must match RunControl permission policy")
    if policy["permissionPolicySchemaVersion"] != "permission-policy-v1":
        raise ValueError("IdentityBoundApprovalRecordV1 must bind permission-policy-v1")
    if policy["permissionPolicyContentHash"] != _stable_json_hash(permission_policy):
        raise ValueError("IdentityBoundApprovalRecordV1 permissionPolicyContentHash must match RunControl permission policy")
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("IdentityBoundApprovalRecordV1 policy must disallow external side effects")
    if policy["sendEmailRequiresApproval"] is not True:
        raise ValueError("IdentityBoundApprovalRecordV1 policy must require approval for send_email")
    if policy["localWriteBoundary"] != permission_policy["localWriteBoundary"]:
        raise ValueError("IdentityBoundApprovalRecordV1 localWriteBoundary must match permission policy")

    replay = record["replayBinding"]
    _require_fields(
        "IdentityBoundApprovalRecordV1 replayBinding",
        replay,
        [
            "durableRunStoreRef",
            "durableRunStoreId",
            "replayQueryRef",
            "replayQueryId",
            "requiredQueryIds",
            "approvalDecisionRef",
        ],
    )
    if replay["durableRunStoreRef"] != STORE_ARTIFACT_PATH or replay["durableRunStoreId"] != store["id"]:
        raise ValueError("IdentityBoundApprovalRecordV1 replayBinding must bind DurableRunStoreV1")
    if replay["replayQueryRef"] != QUERY_ARTIFACT_PATH or replay["replayQueryId"] != replay_query["id"]:
        raise ValueError("IdentityBoundApprovalRecordV1 replayBinding must bind ReplayQueryV1")
    if replay["requiredQueryIds"] != _query_ids(replay_query):
        raise ValueError("IdentityBoundApprovalRecordV1 replayBinding query ids must match ReplayQueryV1")
    if replay["approvalDecisionRef"] != DECISION_ARTIFACT_PATH:
        raise ValueError("IdentityBoundApprovalRecordV1 replayBinding approval decision ref must match HumanApprovalDecisionV1")
    if store["runIndex"]["humanApprovalDecisionRef"] != DECISION_ARTIFACT_PATH:
        raise ValueError("IdentityBoundApprovalRecordV1 DurableRunStoreV1 must index the human approval decision")

    effects = record["effectBoundary"]
    _require_fields(
        "IdentityBoundApprovalRecordV1 effectBoundary",
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
            raise ValueError(f"IdentityBoundApprovalRecordV1 effectBoundary {field} must be false")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or validate the IdentityBoundApprovalRecordV1 fixture.")
    parser.add_argument("--record-out", type=Path)
    parser.add_argument("--validate-record", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    if args.record_out:
        record = build_identity_bound_approval_record(root)
        validate_identity_bound_approval_record(record, root)
        _write_json(args.record_out, record)
        print(f"Wrote IdentityBoundApprovalRecordV1 artifact to {args.record_out}.")

    if args.validate_record:
        record = _load_json(args.validate_record)
        validate_identity_bound_approval_record(record, root)
        print(f"Validated IdentityBoundApprovalRecordV1 artifact {args.validate_record}.")

    if not any([args.record_out, args.validate_record]):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

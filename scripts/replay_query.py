from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from durable_run_store import STORE_ARTIFACT_PATH, validate_durable_run_store


REPLAY_QUERY_SCHEMA_VERSION = "replay-query-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
QUERY_SET_ID = "post-mvp-replay-query-fixture-all_passed"
QUERY_ARTIFACT_PATH = "artifacts/state/post_mvp_replay_query.json"


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
        raise ValueError(f"ReplayQueryV1 paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"ReplayQueryV1 source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _expected_source_paths(store: dict[str, Any]) -> dict[str, str]:
    run_index = store["runIndex"]
    return {
        "durable_run_store": STORE_ARTIFACT_PATH,
        "run": run_index["runRef"],
        "events": run_index["eventsRef"],
        "delivery_report": run_index["deliveryReportRef"],
        "human_approval_decision": run_index["humanApprovalDecisionRef"],
    }


def _build_expected_queries(store: dict[str, Any]) -> list[dict[str, Any]]:
    run_index = store["runIndex"]
    state_index = store["stateIndex"]
    delivery_index = store["deliveryIndex"]
    approval_index = store["approvalIndex"]
    source_refs = {
        "store": STORE_ARTIFACT_PATH,
        "run": run_index["runRef"],
        "events": run_index["eventsRef"],
        "deliveryReport": run_index["deliveryReportRef"],
        "humanApprovalDecision": run_index["humanApprovalDecisionRef"],
    }
    run_id = run_index["runId"]
    tail_event_ids = run_index["appendOnlyEventIds"][-3:]
    return [
        {
            "queryId": "query-run-state-by-id",
            "queryType": "run_state_by_id",
            "input": {"runId": run_id},
            "result": {
                "runId": run_id,
                "fixtureId": run_index["fixtureId"],
                "runStatus": run_index["runStatus"],
                "currentState": state_index["currentState"],
                "terminal": state_index["terminal"],
                "eventCount": run_index["eventCount"],
                "lastEventId": run_index["lastEventId"],
                "recoveryMode": state_index["recoveryMode"],
                "nextAction": state_index["nextAction"],
            },
            "sourceRefs": [source_refs["store"], source_refs["run"], source_refs["events"]],
        },
        {
            "queryId": "query-delivery-readiness-by-run-id",
            "queryType": "delivery_readiness_by_run_id",
            "input": {"runId": run_id},
            "result": {
                "deliveryReportId": delivery_index["deliveryReportId"],
                "readyForHumanReview": delivery_index["readyForHumanReview"],
                "readyForExternalDelivery": delivery_index["readyForExternalDelivery"],
                "sendEmailAllowed": delivery_index["sendEmailAllowed"],
                "externalSideEffectsAllowed": delivery_index["externalSideEffectsAllowed"],
                "blockers": list(delivery_index["blockers"]),
            },
            "sourceRefs": [source_refs["store"], source_refs["deliveryReport"]],
        },
        {
            "queryId": "query-approval-decision-by-run-id",
            "queryType": "approval_decision_by_run_id",
            "input": {"runId": run_id},
            "result": {
                "decisionId": approval_index["decisionId"],
                "humanDecisionRecorded": approval_index["humanDecisionRecorded"],
                "approvalGranted": approval_index["approvalGranted"],
                "approvalDecisionSynthesized": approval_index["approvalDecisionSynthesized"],
                "sendEmailAllowed": approval_index["sendEmailAllowed"],
                "externalDeliveryAllowed": approval_index["externalDeliveryAllowed"],
                "externalSideEffectsAllowed": approval_index["externalSideEffectsAllowed"],
                "taskVerdictOverrideAllowed": approval_index["taskVerdictOverrideAllowed"],
                "postDecisionBlockers": list(approval_index["postDecisionBlockers"]),
            },
            "sourceRefs": [source_refs["store"], source_refs["humanApprovalDecision"]],
        },
        {
            "queryId": "query-event-log-tail-by-run-id",
            "queryType": "event_log_tail_by_run_id",
            "input": {"runId": run_id, "tailCount": len(tail_event_ids)},
            "result": {
                "eventCount": run_index["eventCount"],
                "tailEventIds": tail_event_ids,
                "lastEventId": run_index["lastEventId"],
                "eventLogContentHash": run_index["eventLogContentHash"],
                "appendOnlyEventIds": list(run_index["appendOnlyEventIds"]),
            },
            "sourceRefs": [source_refs["store"], source_refs["events"]],
        },
    ]


def build_replay_query(root: Path) -> dict[str, Any]:
    store = _load_json(root / STORE_ARTIFACT_PATH)
    validate_durable_run_store(store, root)
    expected_source_paths = _expected_source_paths(store)
    return {
        "schemaVersion": REPLAY_QUERY_SCHEMA_VERSION,
        "id": QUERY_SET_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "durable_run_store_replay_query_fixture",
        "mode": "static_json_query_only",
        "sourceArtifacts": [
            _artifact_source(role, path, root)
            for role, path in expected_source_paths.items()
        ],
        "queryPolicy": {
            "queryEngine": "same_process_json_fixture",
            "databaseUsed": False,
            "durableBackendRequired": False,
            "sourceHashValidationRequired": True,
            "replayOnly": True,
            "externalSideEffectsAllowed": False,
            "realProviderExecutionAllowed": False,
            "approvalGrantAllowed": False,
        },
        "queries": _build_expected_queries(store),
        "invariants": [
            "ReplayQueryV1 answers are derived from DurableRunStoreV1 and committed source artifacts only.",
            "Replay queries must not grant approval, send email, mutate workspace state, or enable external delivery.",
            "Event query results preserve append-only event order and source content hashes.",
        ],
    }


def _validate_source_artifacts(
    source_artifacts: list[Any],
    root: Path,
    store: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("ReplayQueryV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_source_paths(store)
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("ReplayQueryV1 sourceArtifacts must be objects")
        _require_fields("ReplayQueryV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected ReplayQueryV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"ReplayQueryV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"ReplayQueryV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"ReplayQueryV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"ReplayQueryV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def validate_replay_query(query_artifact: dict[str, Any], root: Path) -> None:
    _require_fields(
        "ReplayQueryV1",
        query_artifact,
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
    if query_artifact["schemaVersion"] != REPLAY_QUERY_SCHEMA_VERSION:
        raise ValueError(f"ReplayQueryV1 schemaVersion must be {REPLAY_QUERY_SCHEMA_VERSION}")
    if query_artifact["id"] != QUERY_SET_ID:
        raise ValueError(f"ReplayQueryV1 id must be {QUERY_SET_ID}")
    if query_artifact["phase"] != "post_mvp":
        raise ValueError("ReplayQueryV1 phase must be post_mvp")
    if query_artifact["mode"] != "static_json_query_only":
        raise ValueError("ReplayQueryV1 mode must be static_json_query_only")

    durable_source = next(
        (
            source
            for source in query_artifact["sourceArtifacts"]
            if isinstance(source, dict) and source.get("role") == "durable_run_store"
        ),
        None,
    )
    if durable_source is None:
        raise ValueError("ReplayQueryV1 sourceArtifacts must include durable_run_store")
    _validate_relative_posix_path(durable_source["path"])
    store = _load_json(root / durable_source["path"])
    validate_durable_run_store(store, root)
    _validate_source_artifacts(query_artifact["sourceArtifacts"], root, store)

    policy = query_artifact["queryPolicy"]
    _require_fields(
        "ReplayQueryV1 queryPolicy",
        policy,
        [
            "queryEngine",
            "databaseUsed",
            "durableBackendRequired",
            "sourceHashValidationRequired",
            "replayOnly",
            "externalSideEffectsAllowed",
            "realProviderExecutionAllowed",
            "approvalGrantAllowed",
        ],
    )
    if policy["queryEngine"] != "same_process_json_fixture":
        raise ValueError("ReplayQueryV1 queryEngine must be same_process_json_fixture")
    if policy["databaseUsed"] is not False:
        raise ValueError("ReplayQueryV1 must not use a database")
    if policy["durableBackendRequired"] is not False:
        raise ValueError("ReplayQueryV1 must not require a durable backend")
    if policy["sourceHashValidationRequired"] is not True:
        raise ValueError("ReplayQueryV1 must require source hash validation")
    if policy["replayOnly"] is not True:
        raise ValueError("ReplayQueryV1 must remain replay-only")
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("ReplayQueryV1 must disallow external side effects")
    if policy["realProviderExecutionAllowed"] is not False:
        raise ValueError("ReplayQueryV1 must disallow real provider execution")
    if policy["approvalGrantAllowed"] is not False:
        raise ValueError("ReplayQueryV1 must not grant approvals")

    queries = query_artifact["queries"]
    if not isinstance(queries, list):
        raise ValueError("ReplayQueryV1 queries must be a list")
    expected_queries = _build_expected_queries(store)
    if queries != expected_queries:
        raise ValueError("ReplayQueryV1 query results must match DurableRunStoreV1 indexes")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or validate the ReplayQueryV1 fixture.")
    parser.add_argument("--query-out", type=Path)
    parser.add_argument("--validate-query", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    if args.query_out:
        query_artifact = build_replay_query(root)
        validate_replay_query(query_artifact, root)
        _write_json(args.query_out, query_artifact)
        print(f"Wrote ReplayQueryV1 artifact to {args.query_out}.")

    if args.validate_query:
        query_artifact = _load_json(args.validate_query)
        validate_replay_query(query_artifact, root)
        print(f"Validated ReplayQueryV1 artifact {args.validate_query}.")

    if not any([args.query_out, args.validate_query]):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

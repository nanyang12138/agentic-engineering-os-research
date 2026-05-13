from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from human_approval import DECISION_ARTIFACT_PATH as HUMAN_APPROVAL_DECISION_ARTIFACT_PATH, validate_human_approval_decision
from multi_agent_delivery import DELIVERY_REPORT_ARTIFACT_PATH, validate_delivery_report
from run_control import load_events, validate_run_control


DURABLE_RUN_STORE_SCHEMA_VERSION = "durable-run-store-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
STORE_ID = "post-mvp-durable-run-store-fixture-all_passed"
STORE_ARTIFACT_PATH = "artifacts/state/post_mvp_durable_run_store.json"

DEFAULT_RUN_PATH = "artifacts/runs/all_passed/run.json"
DEFAULT_EVENTS_PATH = "artifacts/runs/all_passed/events.jsonl"
DEFAULT_FIXTURE_ID = "all_passed"


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
        raise ValueError(f"DurableRunStore paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"DurableRunStore source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _expected_source_paths() -> dict[str, str]:
    return {
        "run": DEFAULT_RUN_PATH,
        "events": DEFAULT_EVENTS_PATH,
        "delivery_report": DELIVERY_REPORT_ARTIFACT_PATH,
        "human_approval_decision": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    }


def _blocker_ids(delivery_report: dict[str, Any]) -> list[str]:
    return [blocker["id"] for blocker in delivery_report["blockers"]]


def build_durable_run_store(root: Path) -> dict[str, Any]:
    run = _load_json(root / DEFAULT_RUN_PATH)
    events = load_events(root / DEFAULT_EVENTS_PATH)
    validate_run_control(run, events)

    delivery_report = _load_json(root / DELIVERY_REPORT_ARTIFACT_PATH)
    validate_delivery_report(delivery_report, root)
    human_approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    validate_human_approval_decision(human_approval_decision, root)

    recovery = run["runControl"]["recoverySnapshot"]
    readiness = delivery_report["readiness"]
    approval_decision = human_approval_decision["decision"]
    policy_effects = human_approval_decision["policyEffects"]
    event_ids = [event["id"] for event in events]

    return {
        "schemaVersion": DURABLE_RUN_STORE_SCHEMA_VERSION,
        "id": STORE_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "durable_run_store_fixture",
        "mode": "static_json_index_only",
        "sourceArtifacts": [
            _artifact_source(role, path, root)
            for role, path in _expected_source_paths().items()
        ],
        "runIndex": {
            "runId": run["id"],
            "fixtureId": run["fixtureId"],
            "runStatus": run["status"],
            "currentState": run["runControl"]["currentState"],
            "taskSpecRef": f"{DEFAULT_RUN_PATH}#taskSpec",
            "runRef": DEFAULT_RUN_PATH,
            "eventsRef": DEFAULT_EVENTS_PATH,
            "deliveryReportRef": DELIVERY_REPORT_ARTIFACT_PATH,
            "humanApprovalDecisionRef": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
            "permissionPolicyRef": run["runControl"]["permissionPolicy"]["id"],
            "recoverySnapshotRef": f"{DEFAULT_RUN_PATH}#runControl.recoverySnapshot",
            "eventCount": len(events),
            "appendOnlyEventIds": event_ids,
            "lastEventId": events[-1]["id"],
            "eventLogContentHash": _stable_file_hash(root / DEFAULT_EVENTS_PATH),
            "runContentHash": _stable_file_hash(root / DEFAULT_RUN_PATH),
        },
        "stateIndex": {
            "currentState": run["runControl"]["currentState"],
            "terminal": run["runControl"]["currentState"] in ["completed", "failed"],
            "recoveryMode": recovery["resumeMode"],
            "resumeFromEventId": recovery["resumeFromEventId"],
            "nextAction": recovery["nextAction"],
            "replayArtifactCount": len(recovery["replayArtifactRefs"]),
        },
        "deliveryIndex": {
            "deliveryReportId": delivery_report["id"],
            "readyForHumanReview": readiness["readyForHumanReview"],
            "readyForExternalDelivery": readiness["readyForExternalDelivery"],
            "sendEmailAllowed": readiness["sendEmailAllowed"],
            "externalSideEffectsAllowed": readiness["externalSideEffectsAllowed"],
            "blockers": _blocker_ids(delivery_report),
        },
        "approvalIndex": {
            "decisionId": approval_decision["decisionId"],
            "humanDecisionRecorded": approval_decision["humanDecisionRecorded"],
            "approvalGranted": approval_decision["approvalGranted"],
            "approvalDecisionSynthesized": approval_decision["approvalDecisionSynthesized"],
            "sendEmailAllowed": policy_effects["sendEmailAllowed"],
            "externalDeliveryAllowed": policy_effects["externalDeliveryAllowed"],
            "externalSideEffectsAllowed": policy_effects["externalSideEffectsAllowed"],
            "taskVerdictOverrideAllowed": policy_effects["taskVerdictOverrideAllowed"],
            "postDecisionBlockers": list(human_approval_decision["postDecisionBlockers"]),
        },
        "persistencePolicy": {
            "storageMode": "committed_json_fixture",
            "durableBackendImplemented": False,
            "databaseUsed": False,
            "appendOnlyEventsRequired": True,
            "sourceHashValidationRequired": True,
            "replayOnly": True,
            "externalSideEffectsAllowed": False,
            "realProviderExecutionAllowed": False,
        },
        "replayPlan": {
            "replayMode": "source_hash_bound_replay",
            "requiredInputs": [
                DEFAULT_RUN_PATH,
                DEFAULT_EVENTS_PATH,
                DELIVERY_REPORT_ARTIFACT_PATH,
                HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
            ],
            "verificationCommand": "/usr/bin/python3 scripts/validate_repo.py",
        },
        "invariants": [
            "DurableRunStoreV1 is a source-bound replay index, not a database or scheduler.",
            "Events remain append-only and must match the committed events.jsonl order and hash.",
            "Delivery and human approval state remain blocked from external side effects.",
        ],
    }


def _validate_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("DurableRunStoreV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("DurableRunStoreV1 sourceArtifacts must be objects")
        _require_fields("DurableRunStoreV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected DurableRunStoreV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"DurableRunStoreV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"DurableRunStoreV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"DurableRunStoreV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"DurableRunStoreV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def validate_durable_run_store(store: dict[str, Any], root: Path) -> None:
    _require_fields(
        "DurableRunStoreV1",
        store,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "sourceArtifacts",
            "runIndex",
            "stateIndex",
            "deliveryIndex",
            "approvalIndex",
            "persistencePolicy",
            "replayPlan",
            "invariants",
        ],
    )
    if store["schemaVersion"] != DURABLE_RUN_STORE_SCHEMA_VERSION:
        raise ValueError(f"DurableRunStoreV1 schemaVersion must be {DURABLE_RUN_STORE_SCHEMA_VERSION}")
    if store["id"] != STORE_ID:
        raise ValueError(f"DurableRunStoreV1 id must be {STORE_ID}")
    if store["phase"] != "post_mvp":
        raise ValueError("DurableRunStoreV1 phase must be post_mvp")
    if store["mode"] != "static_json_index_only":
        raise ValueError("DurableRunStoreV1 mode must be static_json_index_only")

    sources = _validate_source_artifacts(store["sourceArtifacts"], root)
    run = _load_json(root / sources["run"]["path"])
    events = load_events(root / sources["events"]["path"])
    validate_run_control(run, events)
    delivery_report = _load_json(root / sources["delivery_report"]["path"])
    validate_delivery_report(delivery_report, root)
    human_approval_decision = _load_json(root / sources["human_approval_decision"]["path"])
    validate_human_approval_decision(human_approval_decision, root)

    run_index = store["runIndex"]
    _require_fields(
        "DurableRunStoreV1 runIndex",
        run_index,
        [
            "runId",
            "fixtureId",
            "runStatus",
            "currentState",
            "taskSpecRef",
            "runRef",
            "eventsRef",
            "deliveryReportRef",
            "humanApprovalDecisionRef",
            "permissionPolicyRef",
            "recoverySnapshotRef",
            "eventCount",
            "appendOnlyEventIds",
            "lastEventId",
            "eventLogContentHash",
            "runContentHash",
        ],
    )
    if run_index["runId"] != run["id"]:
        raise ValueError("DurableRunStoreV1 runId must match run.json")
    if run_index["fixtureId"] != DEFAULT_FIXTURE_ID or run_index["fixtureId"] != run["fixtureId"]:
        raise ValueError("DurableRunStoreV1 fixtureId must match the all_passed run")
    if run_index["runStatus"] != run["status"]:
        raise ValueError("DurableRunStoreV1 runStatus must match run.json")
    if run_index["currentState"] != run["runControl"]["currentState"]:
        raise ValueError("DurableRunStoreV1 currentState must match RunControlV1")
    if run_index["runRef"] != sources["run"]["path"]:
        raise ValueError("DurableRunStoreV1 runRef must match sourceArtifacts")
    if run_index["eventsRef"] != sources["events"]["path"]:
        raise ValueError("DurableRunStoreV1 eventsRef must match sourceArtifacts")
    if run_index["deliveryReportRef"] != sources["delivery_report"]["path"]:
        raise ValueError("DurableRunStoreV1 deliveryReportRef must match sourceArtifacts")
    if run_index["humanApprovalDecisionRef"] != sources["human_approval_decision"]["path"]:
        raise ValueError("DurableRunStoreV1 humanApprovalDecisionRef must match sourceArtifacts")
    if run_index["taskSpecRef"] != f"{DEFAULT_RUN_PATH}#taskSpec":
        raise ValueError("DurableRunStoreV1 taskSpecRef must point at run.json#taskSpec")
    if run_index["permissionPolicyRef"] != run["runControl"]["permissionPolicy"]["id"]:
        raise ValueError("DurableRunStoreV1 permissionPolicyRef must match RunControlV1")
    if run_index["recoverySnapshotRef"] != f"{DEFAULT_RUN_PATH}#runControl.recoverySnapshot":
        raise ValueError("DurableRunStoreV1 recoverySnapshotRef must point at RunControlV1 recovery snapshot")

    event_ids = [event["id"] for event in events]
    if run_index["eventCount"] != len(events):
        raise ValueError("DurableRunStoreV1 eventCount must match events.jsonl")
    if run_index["appendOnlyEventIds"] != event_ids or run_index["appendOnlyEventIds"] != run["events"]:
        raise ValueError("DurableRunStoreV1 append-only event ids must match run.json and events.jsonl order")
    if run_index["lastEventId"] != events[-1]["id"]:
        raise ValueError("DurableRunStoreV1 lastEventId must match events.jsonl")
    if run_index["eventLogContentHash"] != _stable_file_hash(root / sources["events"]["path"]):
        raise ValueError("DurableRunStoreV1 event log content hash must match events.jsonl")
    if run_index["runContentHash"] != _stable_file_hash(root / sources["run"]["path"]):
        raise ValueError("DurableRunStoreV1 run content hash must match run.json")

    recovery = run["runControl"]["recoverySnapshot"]
    state_index = store["stateIndex"]
    _require_fields(
        "DurableRunStoreV1 stateIndex",
        state_index,
        ["currentState", "terminal", "recoveryMode", "resumeFromEventId", "nextAction", "replayArtifactCount"],
    )
    if state_index["currentState"] != run["runControl"]["currentState"]:
        raise ValueError("DurableRunStoreV1 stateIndex currentState must match RunControlV1")
    if state_index["terminal"] is not True:
        raise ValueError("DurableRunStoreV1 all_passed fixture must index a terminal run")
    if state_index["recoveryMode"] != recovery["resumeMode"]:
        raise ValueError("DurableRunStoreV1 recoveryMode must match RunControlV1")
    if state_index["resumeFromEventId"] != recovery["resumeFromEventId"]:
        raise ValueError("DurableRunStoreV1 resumeFromEventId must match RunControlV1")
    if state_index["nextAction"] != recovery["nextAction"]:
        raise ValueError("DurableRunStoreV1 nextAction must match RunControlV1")
    if state_index["replayArtifactCount"] != len(recovery["replayArtifactRefs"]):
        raise ValueError("DurableRunStoreV1 replayArtifactCount must match RunControlV1")

    readiness = delivery_report["readiness"]
    delivery_index = store["deliveryIndex"]
    _require_fields(
        "DurableRunStoreV1 deliveryIndex",
        delivery_index,
        [
            "deliveryReportId",
            "readyForHumanReview",
            "readyForExternalDelivery",
            "sendEmailAllowed",
            "externalSideEffectsAllowed",
            "blockers",
        ],
    )
    if delivery_index["deliveryReportId"] != delivery_report["id"]:
        raise ValueError("DurableRunStoreV1 deliveryReportId must match DeliveryReportV1")
    if delivery_index["readyForHumanReview"] != readiness["readyForHumanReview"]:
        raise ValueError("DurableRunStoreV1 readyForHumanReview must match DeliveryReportV1")
    if delivery_index["readyForExternalDelivery"] is not False or delivery_index["readyForExternalDelivery"] != readiness["readyForExternalDelivery"]:
        raise ValueError("DurableRunStoreV1 must not mark external delivery ready")
    if delivery_index["sendEmailAllowed"] is not False or delivery_index["sendEmailAllowed"] != readiness["sendEmailAllowed"]:
        raise ValueError("DurableRunStoreV1 must not allow sending email")
    if delivery_index["externalSideEffectsAllowed"] is not False or delivery_index["externalSideEffectsAllowed"] != readiness["externalSideEffectsAllowed"]:
        raise ValueError("DurableRunStoreV1 must disallow external side effects")
    if delivery_index["blockers"] != _blocker_ids(delivery_report):
        raise ValueError("DurableRunStoreV1 blockers must match DeliveryReportV1")

    approval_decision = human_approval_decision["decision"]
    policy_effects = human_approval_decision["policyEffects"]
    approval_index = store["approvalIndex"]
    _require_fields(
        "DurableRunStoreV1 approvalIndex",
        approval_index,
        [
            "decisionId",
            "humanDecisionRecorded",
            "approvalGranted",
            "approvalDecisionSynthesized",
            "sendEmailAllowed",
            "externalDeliveryAllowed",
            "externalSideEffectsAllowed",
            "taskVerdictOverrideAllowed",
            "postDecisionBlockers",
        ],
    )
    if approval_index["decisionId"] != approval_decision["decisionId"]:
        raise ValueError("DurableRunStoreV1 decisionId must match HumanApprovalDecisionV1")
    if approval_index["humanDecisionRecorded"] != approval_decision["humanDecisionRecorded"]:
        raise ValueError("DurableRunStoreV1 humanDecisionRecorded must match HumanApprovalDecisionV1")
    if approval_index["approvalDecisionSynthesized"] is not False:
        raise ValueError("DurableRunStoreV1 must not synthesize approval decisions")
    if approval_index["approvalGranted"] is not False or approval_index["approvalGranted"] != approval_decision["approvalGranted"]:
        raise ValueError("DurableRunStoreV1 must not grant external delivery approval")
    if approval_index["sendEmailAllowed"] is not False or approval_index["sendEmailAllowed"] != policy_effects["sendEmailAllowed"]:
        raise ValueError("DurableRunStoreV1 must not allow sending email")
    if approval_index["externalDeliveryAllowed"] is not False or approval_index["externalDeliveryAllowed"] != policy_effects["externalDeliveryAllowed"]:
        raise ValueError("DurableRunStoreV1 must not allow external delivery")
    if approval_index["externalSideEffectsAllowed"] is not False or approval_index["externalSideEffectsAllowed"] != policy_effects["externalSideEffectsAllowed"]:
        raise ValueError("DurableRunStoreV1 must disallow external side effects")
    if approval_index["taskVerdictOverrideAllowed"] is not False or approval_index["taskVerdictOverrideAllowed"] != policy_effects["taskVerdictOverrideAllowed"]:
        raise ValueError("DurableRunStoreV1 must not override verifier verdicts")
    if approval_index["postDecisionBlockers"] != human_approval_decision["postDecisionBlockers"]:
        raise ValueError("DurableRunStoreV1 postDecisionBlockers must match HumanApprovalDecisionV1")

    policy = store["persistencePolicy"]
    _require_fields(
        "DurableRunStoreV1 persistencePolicy",
        policy,
        [
            "storageMode",
            "durableBackendImplemented",
            "databaseUsed",
            "appendOnlyEventsRequired",
            "sourceHashValidationRequired",
            "replayOnly",
            "externalSideEffectsAllowed",
            "realProviderExecutionAllowed",
        ],
    )
    if policy["storageMode"] != "committed_json_fixture":
        raise ValueError("DurableRunStoreV1 must remain a static JSON fixture")
    if policy["durableBackendImplemented"] is not False:
        raise ValueError("DurableRunStoreV1 must not claim a durable backend is implemented")
    if policy["databaseUsed"] is not False:
        raise ValueError("DurableRunStoreV1 must remain a static JSON fixture without a database")
    if policy["appendOnlyEventsRequired"] is not True:
        raise ValueError("DurableRunStoreV1 must require append-only events")
    if policy["sourceHashValidationRequired"] is not True:
        raise ValueError("DurableRunStoreV1 must require source hash validation")
    if policy["replayOnly"] is not True:
        raise ValueError("DurableRunStoreV1 must remain replay-only")
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("DurableRunStoreV1 must disallow external side effects")
    if policy["realProviderExecutionAllowed"] is not False:
        raise ValueError("DurableRunStoreV1 must disallow real provider execution")

    replay_plan = store["replayPlan"]
    _require_fields("DurableRunStoreV1 replayPlan", replay_plan, ["replayMode", "requiredInputs", "verificationCommand"])
    if replay_plan["replayMode"] != "source_hash_bound_replay":
        raise ValueError("DurableRunStoreV1 replayMode must be source_hash_bound_replay")
    if replay_plan["requiredInputs"] != list(_expected_source_paths().values()):
        raise ValueError("DurableRunStoreV1 replayPlan requiredInputs must match source artifacts")
    if "scripts/validate_repo.py" not in replay_plan["verificationCommand"]:
        raise ValueError("DurableRunStoreV1 replayPlan must name scripts/validate_repo.py")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or validate the DurableRunStoreV1 fixture.")
    parser.add_argument("--store-out", type=Path)
    parser.add_argument("--validate-store", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    if args.store_out:
        store = build_durable_run_store(root)
        validate_durable_run_store(store, root)
        _write_json(args.store_out, store)
        print(f"Wrote DurableRunStoreV1 artifact to {args.store_out}.")

    if args.validate_store:
        store = _load_json(args.validate_store)
        validate_durable_run_store(store, root)
        print(f"Validated DurableRunStoreV1 artifact {args.validate_store}.")

    if not any([args.store_out, args.validate_store]):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

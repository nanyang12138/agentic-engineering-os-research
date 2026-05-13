from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from capability_contract import capability_ref


RUN_CONTROL_SCHEMA_VERSION = "run-control-v1"
RUN_STATE_MACHINE_SCHEMA_VERSION = "run-state-machine-v1"
PERMISSION_POLICY_SCHEMA_VERSION = "permission-policy-v1"
RECOVERY_SNAPSHOT_SCHEMA_VERSION = "recovery-snapshot-v1"

RUN_STATES = [
    "created",
    "planning",
    "waiting_context",
    "running",
    "verifying",
    "completed",
    "failed",
]
TERMINAL_STATES = ["completed", "failed"]
ALLOWED_TRANSITIONS = [
    ("created", "planning"),
    ("planning", "waiting_context"),
    ("waiting_context", "running"),
    ("running", "running"),
    ("running", "verifying"),
    ("verifying", "completed"),
    ("verifying", "failed"),
]
STATE_BY_EVENT_TYPE = {
    "run.created": "created",
    "task_spec.generated": "planning",
    "capability.read_log.completed": "waiting_context",
    "capability.extract_regression_result.completed": "running",
    "artifact.write.completed": "running",
    "verifier.completed": "verifying",
    "run.completed": "completed",
    "run.failed": "failed",
}
STEP_EVENT_TYPES = {
    "read_log": "capability.read_log.completed",
    "extract_regression_result": "capability.extract_regression_result.completed",
    "write_artifact": "artifact.write.completed",
    "rule_verifier": "verifier.completed",
}
APPROVAL_REQUIRED_FOR = [
    "dangerous",
    "external_side_effect",
    "send_email",
]
DEFAULT_ARTIFACT_ROOT = "artifacts/runs"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError(f"{path} must contain JSON object lines")
        events.append(event)
    return events


def _require_fields(label: str, payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing}")


def _validate_relative_path(path: str) -> None:
    if Path(path).is_absolute() or "\\" in path or path.startswith("../") or "/../" in path:
        raise ValueError(f"RunControl paths must be POSIX relative repository paths: {path}")


def _metadata_by_ref(capability_envelope: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = capability_envelope.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("RunControl requires a non-empty capabilityEnvelope.items list")
    metadata: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("RunControl capabilityEnvelope items must be objects")
        _require_fields("capability metadata", item, ["name", "ref", "permission", "sideEffect", "timeoutMs"])
        metadata[item["ref"]] = item
    return metadata


def build_state_history(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("type")
        if event_type not in STATE_BY_EVENT_TYPE:
            continue
        history.append(
            {
                "eventRef": event["id"],
                "eventType": event_type,
                "state": STATE_BY_EVENT_TYPE[event_type],
            }
        )
    return history


def build_permission_policy(
    fixture_id: str,
    capability_envelope: dict[str, Any],
    artifact_root: str = DEFAULT_ARTIFACT_ROOT,
) -> dict[str, Any]:
    capabilities = []
    for metadata in capability_envelope["items"]:
        output_contract = metadata.get("outputContract", {})
        effect_boundary = output_contract.get("effectBoundary")
        permission = metadata["permission"]
        side_effect = metadata["sideEffect"]
        approval_required = permission == "dangerous" or side_effect
        if metadata["name"] == "write_artifact" and effect_boundary == "local_artifact_output_only" and not side_effect:
            approval_required = False
        capabilities.append(
            {
                "approvalRequired": approval_required,
                "capability": metadata["name"],
                "capabilityRef": metadata["ref"],
                "effectBoundary": effect_boundary or "same_process_readonly",
                "permission": permission,
                "sideEffect": side_effect,
            }
        )
    return {
        "schemaVersion": PERMISSION_POLICY_SCHEMA_VERSION,
        "id": f"permission-policy-{fixture_id}",
        "mode": "readonly_regression_mvp",
        "externalSideEffectsAllowed": False,
        "localWriteBoundary": f"{artifact_root}/{fixture_id}",
        "approvalRequiredFor": list(APPROVAL_REQUIRED_FOR),
        "capabilities": capabilities,
    }


def build_step_attempts(
    steps: list[dict[str, Any]],
    events: list[dict[str, Any]],
    capability_envelope: dict[str, Any],
) -> list[dict[str, Any]]:
    metadata = _metadata_by_ref(capability_envelope)
    events_by_type = {event["type"]: event for event in events if "type" in event}
    attempts = []
    for step in steps:
        capability = step["capability"]
        event = events_by_type.get(STEP_EVENT_TYPES[capability])
        capability_metadata = metadata[step["capabilityRef"]]
        attempts.append(
            {
                "attempt": 1,
                "capability": capability,
                "capabilityRef": step["capabilityRef"],
                "inputRef": event.get("inputRef") if event else None,
                "lastError": None if step["status"] in {"completed", "passed", "pending"} else f"{capability} reported {step['status']}",
                "maxRetries": 0,
                "outputRef": event.get("outputRef") if event else None,
                "permission": capability_metadata["permission"],
                "status": step["status"],
                "stepId": step["id"],
                "timeoutMs": capability_metadata["timeoutMs"],
            }
        )
    return attempts


def next_recovery_action(current_state: str, last_event_type: str) -> str:
    if current_state == "completed":
        return "none_terminal"
    if current_state == "failed":
        return "inspect_verifier_report"
    if last_event_type == "run.created":
        return "resume_task_spec"
    if last_event_type == "task_spec.generated":
        return "resume_read_log"
    if last_event_type == "capability.read_log.completed":
        return "resume_extract_regression_result"
    if last_event_type == "capability.extract_regression_result.completed":
        return "resume_write_artifacts"
    if last_event_type == "artifact.write.completed":
        return "resume_verifier"
    if last_event_type == "verifier.completed":
        return "resume_terminalize_run"
    return "inspect_run_history"


def current_state_for_run_status(run_status: str) -> str:
    if run_status in RUN_STATES:
        return run_status
    raise ValueError(f"RunControlV1 unsupported run status: {run_status}")


def build_recovery_snapshot(
    fixture_id: str,
    run_id: str,
    current_state: str,
    events: list[dict[str, Any]],
    artifacts: list[str],
    artifact_root: str = DEFAULT_ARTIFACT_ROOT,
) -> dict[str, Any]:
    last_event = events[-1]
    return {
        "schemaVersion": RECOVERY_SNAPSHOT_SCHEMA_VERSION,
        "id": f"recovery-snapshot-{fixture_id}",
        "runId": run_id,
        "fixtureId": fixture_id,
        "currentState": current_state,
        "lastEventId": last_event["id"],
        "resumeFromEventId": last_event["id"],
        "resumeMode": "terminal_replay_only" if current_state in TERMINAL_STATES else "from_last_event",
        "nextAction": next_recovery_action(current_state, last_event["type"]),
        "replayArtifactRefs": [
            {
                "path": f"{artifact_root}/{fixture_id}/{artifact}",
                "required": True,
            }
            for artifact in artifacts
        ],
    }


def build_run_control(
    fixture_id: str,
    run_id: str,
    run_status: str,
    capability_envelope: dict[str, Any],
    steps: list[dict[str, Any]],
    events: list[dict[str, Any]],
    artifacts: list[str],
    artifact_root: str = DEFAULT_ARTIFACT_ROOT,
) -> dict[str, Any]:
    state_history = build_state_history(events)
    current_state = current_state_for_run_status(run_status)
    control = {
        "schemaVersion": RUN_CONTROL_SCHEMA_VERSION,
        "currentState": current_state,
        "stateMachine": {
            "schemaVersion": RUN_STATE_MACHINE_SCHEMA_VERSION,
            "states": list(RUN_STATES),
            "initialState": "created",
            "terminalStates": list(TERMINAL_STATES),
            "allowedTransitions": [
                {"from": source, "to": target}
                for source, target in ALLOWED_TRANSITIONS
            ],
        },
        "stateHistory": state_history,
        "permissionPolicy": build_permission_policy(fixture_id, capability_envelope, artifact_root),
        "stepAttempts": build_step_attempts(steps, events, capability_envelope),
        "recoverySnapshot": build_recovery_snapshot(fixture_id, run_id, current_state, events, artifacts, artifact_root),
    }
    validate_run_control(
        {
            "runControl": control,
            "id": run_id,
            "fixtureId": fixture_id,
            "status": run_status,
            "steps": steps,
            "artifacts": artifacts,
            "capabilityEnvelope": capability_envelope,
            "artifactRoot": artifact_root,
        },
        events,
    )
    return control


def validate_run_control(run: dict[str, Any], events: list[dict[str, Any]]) -> None:
    _require_fields("run.json", run, ["id", "fixtureId", "status", "steps", "artifacts", "capabilityEnvelope", "runControl"])
    control = run["runControl"]
    _require_fields(
        "RunControlV1",
        control,
        ["schemaVersion", "currentState", "stateMachine", "stateHistory", "permissionPolicy", "stepAttempts", "recoverySnapshot"],
    )
    if control["schemaVersion"] != RUN_CONTROL_SCHEMA_VERSION:
        raise ValueError(f"RunControlV1 schemaVersion must be {RUN_CONTROL_SCHEMA_VERSION}")
    expected_current_state = current_state_for_run_status(run["status"])
    if control["currentState"] != expected_current_state:
        raise ValueError("RunControlV1 currentState must match run.status")

    validate_state_machine(control["stateMachine"])
    validate_state_history(control["stateHistory"], control["currentState"], events)
    validate_permission_policy(
        run["fixtureId"],
        control["permissionPolicy"],
        run["capabilityEnvelope"],
        run.get("artifactRoot", DEFAULT_ARTIFACT_ROOT),
    )
    validate_step_attempts(control["stepAttempts"], run["steps"], run["capabilityEnvelope"])
    validate_recovery_snapshot(run, control["recoverySnapshot"], control["currentState"], events)


def validate_state_machine(machine: dict[str, Any]) -> None:
    _require_fields("RunStateMachineV1", machine, ["schemaVersion", "states", "initialState", "terminalStates", "allowedTransitions"])
    if machine["schemaVersion"] != RUN_STATE_MACHINE_SCHEMA_VERSION:
        raise ValueError(f"RunStateMachineV1 schemaVersion must be {RUN_STATE_MACHINE_SCHEMA_VERSION}")
    if machine["states"] != RUN_STATES:
        raise ValueError("RunStateMachineV1 states must match Phase 6 contract")
    if machine["initialState"] != "created":
        raise ValueError("RunStateMachineV1 initialState must be created")
    if machine["terminalStates"] != TERMINAL_STATES:
        raise ValueError("RunStateMachineV1 terminalStates must be completed/failed")
    transitions = [(item.get("from"), item.get("to")) for item in machine["allowedTransitions"] if isinstance(item, dict)]
    if transitions != ALLOWED_TRANSITIONS:
        raise ValueError("RunStateMachineV1 allowedTransitions must match Phase 6 contract")


def validate_state_history(history: list[dict[str, Any]], current_state: str, events: list[dict[str, Any]]) -> None:
    if not isinstance(history, list) or not history:
        raise ValueError("RunControlV1 stateHistory must be a non-empty list")
    expected_history = build_state_history(events)
    if history != expected_history:
        raise ValueError("RunControlV1 stateHistory must match events.jsonl")
    if history[0]["state"] != "created":
        raise ValueError("RunControlV1 stateHistory must start at created")
    if history[-1]["state"] != current_state:
        raise ValueError("RunControlV1 stateHistory terminal state must match currentState")
    allowed = set(ALLOWED_TRANSITIONS)
    for previous, current in zip(history, history[1:]):
        transition = (previous["state"], current["state"])
        if transition not in allowed:
            raise ValueError(f"RunControlV1 illegal state transition: {transition[0]} -> {transition[1]}")


def validate_permission_policy(
    fixture_id: str,
    policy: dict[str, Any],
    capability_envelope: dict[str, Any],
    artifact_root: str = DEFAULT_ARTIFACT_ROOT,
) -> None:
    _require_fields(
        "PermissionPolicyV1",
        policy,
        ["schemaVersion", "id", "mode", "externalSideEffectsAllowed", "localWriteBoundary", "approvalRequiredFor", "capabilities"],
    )
    if policy["schemaVersion"] != PERMISSION_POLICY_SCHEMA_VERSION:
        raise ValueError(f"PermissionPolicyV1 schemaVersion must be {PERMISSION_POLICY_SCHEMA_VERSION}")
    if policy["id"] != f"permission-policy-{fixture_id}":
        raise ValueError("PermissionPolicyV1 id must include fixture id")
    if policy["mode"] != "readonly_regression_mvp":
        raise ValueError("PermissionPolicyV1 mode must be readonly_regression_mvp")
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("PermissionPolicyV1 must disallow external side effects")
    if policy["localWriteBoundary"] != f"{artifact_root}/{fixture_id}":
        raise ValueError("PermissionPolicyV1 localWriteBoundary must be the run artifact directory")
    if policy["approvalRequiredFor"] != APPROVAL_REQUIRED_FOR:
        raise ValueError("PermissionPolicyV1 approvalRequiredFor must match Phase 6 contract")

    metadata = _metadata_by_ref(capability_envelope)
    capabilities = policy["capabilities"]
    if not isinstance(capabilities, list) or len(capabilities) != len(metadata):
        raise ValueError("PermissionPolicyV1 capabilities must mirror capabilityEnvelope")
    for item in capabilities:
        _require_fields(
            "PermissionPolicyV1 capability",
            item,
            ["approvalRequired", "capability", "capabilityRef", "effectBoundary", "permission", "sideEffect"],
        )
        ref = item["capabilityRef"]
        if ref not in metadata:
            raise ValueError(f"PermissionPolicyV1 references unknown capabilityRef: {ref}")
        capability = metadata[ref]
        if item["capability"] != capability["name"] or ref != capability_ref(item["capability"]):
            raise ValueError("PermissionPolicyV1 capability identity must match capabilityEnvelope")
        if item["permission"] != capability["permission"]:
            raise ValueError("PermissionPolicyV1 capability permission must match capabilityEnvelope")
        if item["sideEffect"] != capability["sideEffect"]:
            raise ValueError("PermissionPolicyV1 capability sideEffect must match capabilityEnvelope")
        if item["sideEffect"]:
            raise ValueError("PermissionPolicyV1 capabilities must not declare external side effects")
        if item["permission"] == "dangerous" and item["approvalRequired"] is not True:
            raise ValueError("PermissionPolicyV1 dangerous capabilities must require approval")
        if item["permission"] == "write":
            if item["capability"] != "write_artifact":
                raise ValueError("PermissionPolicyV1 only write_artifact may use write permission in the MVP")
            if item["effectBoundary"] != "local_artifact_output_only":
                raise ValueError("PermissionPolicyV1 write_artifact must stay within local artifact output boundary")


def validate_step_attempts(
    attempts: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    capability_envelope: dict[str, Any],
) -> None:
    if not isinstance(attempts, list) or len(attempts) != len(steps):
        raise ValueError("RunControlV1 stepAttempts must mirror run.steps")
    metadata = _metadata_by_ref(capability_envelope)
    for step in steps:
        _require_fields("run step", step, ["id", "capability", "capabilityRef", "status"])
    steps_by_id = {step["id"]: step for step in steps}
    for attempt in attempts:
        _require_fields(
            "RunControlV1 stepAttempt",
            attempt,
            ["attempt", "capability", "capabilityRef", "inputRef", "lastError", "maxRetries", "outputRef", "permission", "status", "stepId", "timeoutMs"],
        )
        if attempt["stepId"] not in steps_by_id:
            raise ValueError(f"RunControlV1 stepAttempt references unknown stepId: {attempt['stepId']}")
        step = steps_by_id[attempt["stepId"]]
        if attempt["capability"] != step["capability"] or attempt["capabilityRef"] != step["capabilityRef"]:
            raise ValueError("RunControlV1 stepAttempt capability must match run.steps")
        if attempt["capabilityRef"] not in metadata:
            raise ValueError(f"RunControlV1 stepAttempt references unknown capabilityRef: {attempt['capabilityRef']}")
        if attempt["permission"] != metadata[attempt["capabilityRef"]]["permission"]:
            raise ValueError("RunControlV1 stepAttempt permission must match capability metadata")
        if attempt["timeoutMs"] != metadata[attempt["capabilityRef"]]["timeoutMs"]:
            raise ValueError("RunControlV1 stepAttempt timeoutMs must match capability metadata")
        if attempt["attempt"] != 1 or attempt["maxRetries"] != 0:
            raise ValueError("RunControlV1 MVP step attempts must be first-attempt/no-retry")
        if attempt["status"] != step["status"]:
            raise ValueError("RunControlV1 stepAttempt status must match run.steps")


def validate_recovery_snapshot(
    run: dict[str, Any],
    snapshot: dict[str, Any],
    current_state: str,
    events: list[dict[str, Any]],
) -> None:
    _require_fields(
        "RecoverySnapshotV1",
        snapshot,
        ["schemaVersion", "id", "runId", "fixtureId", "currentState", "lastEventId", "resumeFromEventId", "resumeMode", "nextAction", "replayArtifactRefs"],
    )
    if snapshot["schemaVersion"] != RECOVERY_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"RecoverySnapshotV1 schemaVersion must be {RECOVERY_SNAPSHOT_SCHEMA_VERSION}")
    if snapshot["id"] != f"recovery-snapshot-{run['fixtureId']}":
        raise ValueError("RecoverySnapshotV1 id must include fixture id")
    if snapshot["runId"] != run["id"] or snapshot["fixtureId"] != run["fixtureId"]:
        raise ValueError("RecoverySnapshotV1 run identity must match run.json")
    last_event_id = events[-1]["id"]
    if snapshot["currentState"] != current_state:
        raise ValueError("RecoverySnapshotV1 currentState must match RunControlV1")
    if snapshot["lastEventId"] != last_event_id or snapshot["resumeFromEventId"] != last_event_id:
        raise ValueError("RecoverySnapshotV1 must point to the last event")
    expected_resume_mode = "terminal_replay_only" if current_state in TERMINAL_STATES else "from_last_event"
    if snapshot["resumeMode"] != expected_resume_mode:
        raise ValueError("RecoverySnapshotV1 resumeMode does not match current state")
    expected_next_action = next_recovery_action(current_state, events[-1]["type"])
    if snapshot["nextAction"] != expected_next_action:
        raise ValueError("RecoverySnapshotV1 nextAction does not match current state")
    artifact_root = run.get("artifactRoot", DEFAULT_ARTIFACT_ROOT)
    expected_paths = [f"{artifact_root}/{run['fixtureId']}/{artifact}" for artifact in run["artifacts"]]
    refs = snapshot["replayArtifactRefs"]
    if not isinstance(refs, list) or [ref.get("path") for ref in refs if isinstance(ref, dict)] != expected_paths:
        raise ValueError("RecoverySnapshotV1 replayArtifactRefs must mirror run.artifacts")
    for ref in refs:
        _require_fields("RecoverySnapshotV1 replayArtifactRef", ref, ["path", "required"])
        _validate_relative_path(ref["path"])
        if ref["required"] is not True:
            raise ValueError("RecoverySnapshotV1 replayArtifactRefs must be required")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run-control")
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_run_control(load_json(args.run), load_events(args.events))
    print(f"RunControlV1 validation passed for {args.run}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

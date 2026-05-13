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
TERMINAL_RUN_STATUS_TO_STATE = {
    "completed": "completed",
    "failed": "failed",
}
NON_TERMINAL_RUN_STATUSES = ["interrupted"]
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
NEXT_ACTION_BY_STATE = {
    "created": "resume_planning",
    "planning": "resume_task_spec_generation",
    "waiting_context": "resume_context_collection",
    "running": "resume_step",
    "verifying": "resume_verifier",
    "completed": "none_terminal",
    "failed": "inspect_verifier_report",
}


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


def build_permission_policy(fixture_id: str, capability_envelope: dict[str, Any], artifact_root: str = "artifacts/runs") -> dict[str, Any]:
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


def build_recovery_snapshot(
    fixture_id: str,
    run_id: str,
    current_state: str,
    events: list[dict[str, Any]],
    artifacts: list[str],
    resume_target: dict[str, Any] | None = None,
    artifact_root: str = "artifacts/runs",
) -> dict[str, Any]:
    last_event = events[-1]
    snapshot = {
        "schemaVersion": RECOVERY_SNAPSHOT_SCHEMA_VERSION,
        "id": f"recovery-snapshot-{fixture_id}",
        "runId": run_id,
        "fixtureId": fixture_id,
        "currentState": current_state,
        "lastEventId": last_event["id"],
        "resumeFromEventId": last_event["id"],
        "resumeMode": "terminal_replay_only" if current_state in TERMINAL_STATES else "from_last_event",
        "nextAction": NEXT_ACTION_BY_STATE[current_state],
        "replayArtifactRefs": [
            {
                "path": f"{artifact_root}/{fixture_id}/{artifact}",
                "required": True,
            }
            for artifact in artifacts
        ],
    }
    if resume_target is not None:
        snapshot["resumeTarget"] = resume_target
    return snapshot


def build_run_control(
    fixture_id: str,
    run_id: str,
    run_status: str,
    capability_envelope: dict[str, Any],
    steps: list[dict[str, Any]],
    events: list[dict[str, Any]],
    artifacts: list[str],
    current_state: str | None = None,
    resume_target: dict[str, Any] | None = None,
    artifact_root: str = "artifacts/runs",
) -> dict[str, Any]:
    state_history = build_state_history(events)
    if current_state is None:
        if run_status not in TERMINAL_RUN_STATUS_TO_STATE:
            raise ValueError("RunControlV1 non-terminal builders must pass current_state explicitly")
        current_state = TERMINAL_RUN_STATUS_TO_STATE[run_status]
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
        "recoverySnapshot": build_recovery_snapshot(fixture_id, run_id, current_state, events, artifacts, resume_target, artifact_root),
    }
    validation_run = {
        "runControl": control,
        "id": run_id,
        "fixtureId": fixture_id,
        "status": run_status,
        "steps": steps,
        "artifacts": artifacts,
        "capabilityEnvelope": capability_envelope,
    }
    if artifact_root != "artifacts/runs":
        validation_run["artifactRoot"] = artifact_root
    validate_run_control(validation_run, events)
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
    if run["status"] in TERMINAL_RUN_STATUS_TO_STATE:
        expected_current_state = TERMINAL_RUN_STATUS_TO_STATE[run["status"]]
        if control["currentState"] != expected_current_state:
            raise ValueError("RunControlV1 currentState must match terminal run.status")
    elif run["status"] in NON_TERMINAL_RUN_STATUSES:
        if control["currentState"] in TERMINAL_STATES:
            raise ValueError("RunControlV1 interrupted runs must use a non-terminal currentState")
        expected_history = build_state_history(events)
        if not expected_history or control["currentState"] != expected_history[-1]["state"]:
            raise ValueError("RunControlV1 interrupted currentState must match the last event-derived state")
    else:
        raise ValueError(f"RunControlV1 unsupported run.status: {run['status']}")

    validate_state_machine(control["stateMachine"])
    validate_state_history(control["stateHistory"], control["currentState"], events)
    validate_permission_policy(run["fixtureId"], control["permissionPolicy"], run["capabilityEnvelope"], run.get("artifactRoot", "artifacts/runs"))
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


def validate_permission_policy(fixture_id: str, policy: dict[str, Any], capability_envelope: dict[str, Any], artifact_root: str = "artifacts/runs") -> None:
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
    if not isinstance(artifact_root, str) or not artifact_root.strip():
        raise ValueError("PermissionPolicyV1 artifact_root must be a non-empty string")
    _validate_relative_path(artifact_root)
    if policy["localWriteBoundary"] != f"{artifact_root}/{fixture_id}":
        raise ValueError("PermissionPolicyV1 localWriteBoundary must be the fixture artifact directory")
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
    expected_next_action = NEXT_ACTION_BY_STATE[current_state]
    if snapshot["nextAction"] != expected_next_action:
        raise ValueError("RecoverySnapshotV1 nextAction does not match current state")
    if current_state in TERMINAL_STATES:
        if "resumeTarget" in snapshot:
            raise ValueError("RecoverySnapshotV1 terminal snapshots must not include resumeTarget")
    else:
        validate_resume_target(run, snapshot.get("resumeTarget"))
    artifact_root = run.get("artifactRoot", "artifacts/runs")
    if not isinstance(artifact_root, str) or not artifact_root.strip():
        raise ValueError("RunControlV1 artifactRoot must be a non-empty string when provided")
    _validate_relative_path(artifact_root)
    expected_paths = [f"{artifact_root}/{run['fixtureId']}/{artifact}" for artifact in run["artifacts"]]
    refs = snapshot["replayArtifactRefs"]
    if not isinstance(refs, list) or [ref.get("path") for ref in refs if isinstance(ref, dict)] != expected_paths:
        raise ValueError("RecoverySnapshotV1 replayArtifactRefs must mirror run.artifacts")
    for ref in refs:
        _require_fields("RecoverySnapshotV1 replayArtifactRef", ref, ["path", "required"])
        _validate_relative_path(ref["path"])
        if ref["required"] is not True:
            raise ValueError("RecoverySnapshotV1 replayArtifactRefs must be required")


def validate_resume_target(run: dict[str, Any], resume_target: Any) -> None:
    if not isinstance(resume_target, dict):
        raise ValueError("RecoverySnapshotV1 non-terminal snapshots must include resumeTarget")
    _require_fields(
        "RecoverySnapshotV1 resumeTarget",
        resume_target,
        ["stepId", "capability", "capabilityRef", "inputRef", "reason"],
    )
    steps_by_id = {step["id"]: step for step in run["steps"] if isinstance(step, dict) and "id" in step}
    step = steps_by_id.get(resume_target["stepId"])
    if step is None:
        raise ValueError(f"RecoverySnapshotV1 resumeTarget references unknown stepId: {resume_target['stepId']}")
    if step.get("status") in {"completed", "passed"}:
        raise ValueError("RecoverySnapshotV1 resumeTarget must reference an incomplete step")
    metadata = _metadata_by_ref(run["capabilityEnvelope"])
    if resume_target["capability"] != step.get("capability"):
        raise ValueError("RecoverySnapshotV1 resumeTarget capability must match run.steps")
    if resume_target["capabilityRef"] != step.get("capabilityRef"):
        raise ValueError("RecoverySnapshotV1 resumeTarget capabilityRef must match run.steps")
    if resume_target["capabilityRef"] not in metadata:
        raise ValueError(f"RecoverySnapshotV1 resumeTarget references unknown capabilityRef: {resume_target['capabilityRef']}")
    for field in ["inputRef", "reason"]:
        if not isinstance(resume_target[field], str) or not resume_target[field].strip():
            raise ValueError(f"RecoverySnapshotV1 resumeTarget {field} must be a non-empty string")


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

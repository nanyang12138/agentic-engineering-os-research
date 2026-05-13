from __future__ import annotations

import argparse
import json
from copy import deepcopy
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
NON_TERMINAL_RUN_STATUSES = {"running"}
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
INTERRUPTED_RECOVERY_FIXTURE_ID = "interrupted_after_read_log"
INTERRUPTED_RECOVERY_LAST_EVENT_ID = "event-all_passed-003"
INTERRUPTED_RECOVERY_ARTIFACT_BASE_PATH = "artifacts/recovery/interrupted_after_read_log"


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n", encoding="utf-8")


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


def build_permission_policy(fixture_id: str, capability_envelope: dict[str, Any]) -> dict[str, Any]:
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
        "localWriteBoundary": f"artifacts/runs/{fixture_id}",
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
                "lastError": None if step["status"] in {"completed", "passed"} else f"{capability} reported {step['status']}",
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
    artifact_base_path: str | None = None,
) -> dict[str, Any]:
    last_event = events[-1]
    base_path = artifact_base_path or f"artifacts/runs/{fixture_id}"
    snapshot = {
        "schemaVersion": RECOVERY_SNAPSHOT_SCHEMA_VERSION,
        "id": f"recovery-snapshot-{fixture_id}",
        "runId": run_id,
        "fixtureId": fixture_id,
        "currentState": current_state,
        "lastEventId": last_event["id"],
        "resumeFromEventId": last_event["id"],
        "resumeMode": "terminal_replay_only" if current_state in TERMINAL_STATES else "from_last_event",
        "nextAction": recovery_next_action(current_state),
        "replayArtifactRefs": [
            {
                "path": f"{base_path}/{artifact}",
                "required": True,
            }
            for artifact in artifacts
        ],
    }
    if artifact_base_path is not None:
        snapshot["artifactBasePath"] = base_path
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
    artifact_base_path: str | None = None,
) -> dict[str, Any]:
    state_history = build_state_history(events)
    if current_state is None:
        current_state = "completed" if run_status == "completed" else "failed"
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
        "permissionPolicy": build_permission_policy(fixture_id, capability_envelope),
        "stepAttempts": build_step_attempts(steps, events, capability_envelope),
        "recoverySnapshot": build_recovery_snapshot(fixture_id, run_id, current_state, events, artifacts, artifact_base_path),
    }
    validate_run_control({"runControl": control, "id": run_id, "fixtureId": fixture_id, "status": run_status, "steps": steps, "artifacts": artifacts, "capabilityEnvelope": capability_envelope}, events)
    return control


def recovery_next_action(current_state: str) -> str:
    actions = {
        "created": "resume_planning",
        "planning": "resume_context_collection",
        "waiting_context": "resume_extract_regression_result",
        "running": "resume_artifact_write_or_verification",
        "verifying": "resume_rule_verifier",
        "completed": "none_terminal",
        "failed": "inspect_verifier_report",
    }
    if current_state not in actions:
        raise ValueError(f"Unknown RunControlV1 current state: {current_state}")
    return actions[current_state]


def expected_current_state_for_run(run: dict[str, Any], events: list[dict[str, Any]]) -> str:
    status = run["status"]
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    if status in NON_TERMINAL_RUN_STATUSES:
        history = build_state_history(events)
        if not history:
            raise ValueError("RunControlV1 non-terminal run must have state-bearing events")
        state = history[-1]["state"]
        if state in TERMINAL_STATES:
            raise ValueError("RunControlV1 running run cannot point at a terminal event")
        return state
    raise ValueError(f"RunControlV1 unsupported run.status: {status}")


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
    expected_current_state = expected_current_state_for_run(run, events)
    if control["currentState"] != expected_current_state:
        raise ValueError("RunControlV1 currentState must match run.status")

    validate_state_machine(control["stateMachine"])
    validate_state_history(control["stateHistory"], control["currentState"], events)
    validate_permission_policy(run["fixtureId"], control["permissionPolicy"], run["capabilityEnvelope"])
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


def validate_permission_policy(fixture_id: str, policy: dict[str, Any], capability_envelope: dict[str, Any]) -> None:
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
    if policy["localWriteBoundary"] != f"artifacts/runs/{fixture_id}":
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
    expected_next_action = recovery_next_action(current_state)
    if snapshot["nextAction"] != expected_next_action:
        raise ValueError("RecoverySnapshotV1 nextAction does not match current state")
    artifact_base_path = snapshot.get("artifactBasePath", f"artifacts/runs/{run['fixtureId']}")
    if not isinstance(artifact_base_path, str):
        raise ValueError("RecoverySnapshotV1 artifactBasePath must be a string when present")
    _validate_relative_path(artifact_base_path)
    expected_paths = [f"{artifact_base_path}/{artifact}" for artifact in run["artifacts"]]
    refs = snapshot["replayArtifactRefs"]
    if not isinstance(refs, list) or [ref.get("path") for ref in refs if isinstance(ref, dict)] != expected_paths:
        raise ValueError("RecoverySnapshotV1 replayArtifactRefs must mirror run.artifacts")
    for ref in refs:
        _require_fields("RecoverySnapshotV1 replayArtifactRef", ref, ["path", "required"])
        _validate_relative_path(ref["path"])
        if ref["required"] is not True:
            raise ValueError("RecoverySnapshotV1 replayArtifactRefs must be required")


def _remap_events_for_interruption(source_events: list[dict[str, Any]], last_event_id: str, fixture_id: str, run_id: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for source_event in source_events:
        selected.append(source_event)
        if source_event.get("id") == last_event_id:
            break
    if not selected or selected[-1].get("id") != last_event_id:
        raise ValueError(f"Could not find interruption event id: {last_event_id}")

    event_id_map = {
        event["id"]: f"event-{fixture_id}-{index:03d}"
        for index, event in enumerate(selected, start=1)
    }
    remapped = []
    for event in selected:
        copied = deepcopy(event)
        copied["id"] = event_id_map[event["id"]]
        copied["fixtureId"] = fixture_id
        copied["runId"] = run_id
        copied["causalRefs"] = [
            event_id_map[ref]
            for ref in copied.get("causalRefs", [])
            if ref in event_id_map
        ]
        remapped.append(copied)
    return remapped


def _steps_attempted_by_events(source_steps: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed_event_types = {event["type"] for event in events}
    attempted_capabilities = {
        capability
        for capability, event_type in STEP_EVENT_TYPES.items()
        if event_type in completed_event_types
    }
    steps = [
        deepcopy(step)
        for step in source_steps
        if step.get("capability") in attempted_capabilities
    ]
    if not steps:
        raise ValueError("Interrupted RunControl fixture must include at least one attempted step")
    return steps


def build_interrupted_run_control_fixture(
    source_run: dict[str, Any],
    source_events: list[dict[str, Any]],
    fixture_id: str = INTERRUPTED_RECOVERY_FIXTURE_ID,
    last_event_id: str = INTERRUPTED_RECOVERY_LAST_EVENT_ID,
    artifact_base_path: str = INTERRUPTED_RECOVERY_ARTIFACT_BASE_PATH,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_id = f"run-{fixture_id}-001"
    events = _remap_events_for_interruption(source_events, last_event_id, fixture_id, run_id)
    state_history = build_state_history(events)
    if not state_history:
        raise ValueError("Interrupted RunControl fixture must contain state-bearing events")
    current_state = state_history[-1]["state"]
    if current_state in TERMINAL_STATES:
        raise ValueError("Interrupted RunControl fixture must stop before a terminal event")

    steps = _steps_attempted_by_events(source_run["steps"], events)
    artifacts = ["run.json", "events.jsonl"]
    run = {
        "schemaVersion": source_run["schemaVersion"],
        "id": run_id,
        "fixtureId": fixture_id,
        "task": source_run["task"],
        "taskSpec": deepcopy(source_run["taskSpec"]),
        "capabilityEnvelope": deepcopy(source_run["capabilityEnvelope"]),
        "steps": steps,
        "events": [event["id"] for event in events],
        "artifacts": artifacts,
        "status": "running",
        "generatedAt": source_run["generatedAt"],
    }
    run["runControl"] = build_run_control(
        fixture_id,
        run_id,
        "running",
        run["capabilityEnvelope"],
        steps,
        events,
        artifacts,
        current_state=current_state,
        artifact_base_path=artifact_base_path,
    )
    return run, events


def write_interrupted_run_control_fixture(
    source_run_path: Path,
    source_events_path: Path,
    out_dir: Path,
    fixture_id: str = INTERRUPTED_RECOVERY_FIXTURE_ID,
    last_event_id: str = INTERRUPTED_RECOVERY_LAST_EVENT_ID,
    artifact_base_path: str = INTERRUPTED_RECOVERY_ARTIFACT_BASE_PATH,
) -> tuple[Path, Path]:
    run, events = build_interrupted_run_control_fixture(
        load_json(source_run_path),
        load_events(source_events_path),
        fixture_id,
        last_event_id,
        artifact_base_path,
    )
    run_path = out_dir / "run.json"
    events_path = out_dir / "events.jsonl"
    write_json(run_path, run)
    write_events(events_path, events)
    validate_run_control(run, events)
    return run_path, events_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run-control")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--build-interrupted", action="store_true")
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--source-events", type=Path)
    parser.add_argument("--last-event-id", default=INTERRUPTED_RECOVERY_LAST_EVENT_ID)
    parser.add_argument("--out-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.build_interrupted:
        if not args.source_run or not args.source_events or not args.out_dir:
            raise SystemExit("--build-interrupted requires --source-run, --source-events, and --out-dir")
        run_path, events_path = write_interrupted_run_control_fixture(
            args.source_run,
            args.source_events,
            args.out_dir,
            last_event_id=args.last_event_id,
        )
        print(f"Wrote interrupted RunControlV1 fixture to {run_path.parent}.")
        print(f"RunControlV1 validation passed for {run_path}.")
        return 0

    if not args.run or not args.events:
        raise SystemExit("RunControlV1 validation requires --run and --events")
    validate_run_control(load_json(args.run), load_events(args.events))
    print(f"RunControlV1 validation passed for {args.run}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

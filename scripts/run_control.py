from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from capability_contract import PHASE3_CAPABILITY_NAMES


RUN_CONTROL_SCHEMA_VERSION = "run-control-v1"
RUN_STATE_SCHEMA_VERSION = "run-state-v1"
PERMISSION_POLICY_SCHEMA_VERSION = "permission-policy-v1"
RECOVERY_SNAPSHOT_SCHEMA_VERSION = "recovery-snapshot-v1"

RUN_STATES = ["created", "planning", "waiting_context", "running", "verifying", "completed", "failed"]
TERMINAL_STATES = {"completed", "failed"}
CAPABILITY_PERMISSIONS = {
    "read_log": "read",
    "extract_regression_result": "read",
    "write_artifact": "write",
    "rule_verifier": "read",
}
FORBIDDEN_ACTIONS = [
    "modify_repo_or_log",
    "execute_external_side_effect",
    "send_email",
    "call_gui_desktop_cua_or_browser_capability",
    "claim_all_passed_without_sufficient_evidence",
]
APPROVAL_POINTS = ["send_email_requires_human_approval"]
RECOVERY_INPUT_REFS = ["fixture.json", "input.log", "taskSpec", "context_pack.json"]


def step_io(capability: str, report_status: str) -> tuple[list[str], list[str]]:
    if capability == "read_log":
        return ["taskSpec.inputLogPath"], ["log_text"]
    if capability == "extract_regression_result":
        return ["log_text", "run.json#/taskSpec"], ["evidence.json", "regression_result.json"]
    if capability == "write_artifact":
        return ["evidence.json", "regression_result.json"], ["email_draft.md", "run.json", "events.jsonl"]
    if capability == "rule_verifier":
        return ["run.json#/taskSpec", "evidence.json", "regression_result.json", "email_draft.md"], ["verifier_report.json"]
    raise ValueError(f"Unknown capability for step IO: {capability}")


def enrich_step(step_id: str, capability: str, status: str, report_status: str) -> dict[str, Any]:
    input_refs, output_refs = step_io(capability, report_status)
    return {
        "error": None if status in {"completed", "passed"} else "Verifier reported blocking failures.",
        "id": step_id,
        "inputRefs": input_refs,
        "outputRefs": output_refs,
        "permission": CAPABILITY_PERMISSIONS[capability],
        "retryPolicy": {
            "maxAttempts": 1,
            "mode": "deterministic_no_retry",
        },
        "timeoutMs": 1000,
    }


def build_run_state(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    verifier_failed = any(event["type"] == "verifier.completed" and event["status"] == "failed" for event in events)
    terminal_state = "failed" if verifier_failed or run.get("status") == "failed" else "completed"
    transition_states = ["created", "planning", "waiting_context", "running", "verifying", terminal_state]
    transitions = []
    for index, state in enumerate(transition_states):
        event = events[min(index, len(events) - 1)]
        transitions.append(
            {
                "eventId": event["id"],
                "from": transition_states[index - 1] if index else None,
                "to": state,
            }
        )
    return {
        "currentState": terminal_state,
        "schemaVersion": RUN_STATE_SCHEMA_VERSION,
        "terminal": terminal_state in TERMINAL_STATES,
        "transitions": transitions,
    }


def build_permission_policy(task_spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "approvalPoints": list(APPROVAL_POINTS),
        "capabilityPermissions": dict(CAPABILITY_PERMISSIONS),
        "externalSideEffectsAllowed": False,
        "forbiddenActions": list(FORBIDDEN_ACTIONS),
        "schemaVersion": PERMISSION_POLICY_SCHEMA_VERSION,
        "writeBoundary": "local_artifact_output_only",
    }


def build_recovery_snapshot(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifactRefs": list(run["artifacts"]),
        "inputRefs": list(RECOVERY_INPUT_REFS),
        "lastEventId": events[-1]["id"],
        "mode": "deterministic_replay_from_inputs",
        "resumeFromState": run["status"],
        "runId": run["id"],
        "schemaVersion": RECOVERY_SNAPSHOT_SCHEMA_VERSION,
    }


def build_run_control(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "permissionPolicy": build_permission_policy(run["taskSpec"]),
        "recoverySnapshot": build_recovery_snapshot(run, events),
        "runState": build_run_state(run, events),
        "schemaVersion": RUN_CONTROL_SCHEMA_VERSION,
    }


def _require_fields(label: str, payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing}")


def validate_step_control(step: dict[str, Any]) -> None:
    _require_fields(
        "Run step",
        step,
        ["id", "capability", "status", "inputRefs", "outputRefs", "error", "timeoutMs", "retryPolicy", "permission"],
    )
    capability = step["capability"]
    if capability not in CAPABILITY_PERMISSIONS:
        raise ValueError(f"Run step has unknown capability: {capability}")
    if step["permission"] != CAPABILITY_PERMISSIONS[capability]:
        raise ValueError(f"Run step {step['id']} permission must be {CAPABILITY_PERMISSIONS[capability]}")
    for field in ["inputRefs", "outputRefs"]:
        if not isinstance(step[field], list) or not all(isinstance(item, str) and item for item in step[field]):
            raise ValueError(f"Run step {step['id']} {field} must be a non-empty string list")
    if not isinstance(step["timeoutMs"], int) or step["timeoutMs"] <= 0:
        raise ValueError(f"Run step {step['id']} timeoutMs must be a positive integer")
    retry_policy = step["retryPolicy"]
    if not isinstance(retry_policy, dict) or retry_policy.get("mode") != "deterministic_no_retry" or retry_policy.get("maxAttempts") != 1:
        raise ValueError(f"Run step {step['id']} retryPolicy must be deterministic_no_retry with one attempt")
    if step["status"] in {"completed", "passed"} and step["error"] is not None:
        raise ValueError(f"Run step {step['id']} completed/passed status must not carry an error")


def validate_run_state(run_state: dict[str, Any], run: dict[str, Any], event_ids: set[str]) -> None:
    _require_fields("RunStateV1", run_state, ["schemaVersion", "currentState", "terminal", "transitions"])
    if run_state["schemaVersion"] != RUN_STATE_SCHEMA_VERSION:
        raise ValueError(f"RunStateV1 schemaVersion must be {RUN_STATE_SCHEMA_VERSION}")
    if run_state["currentState"] not in TERMINAL_STATES:
        raise ValueError("RunStateV1 currentState must be a terminal state for committed fixture runs")
    expected_current = "completed" if run["status"] == "completed" else "failed"
    if run_state["currentState"] != expected_current:
        raise ValueError(f"RunStateV1 currentState must match run.status terminal mapping: {expected_current}")
    if run_state["terminal"] is not True:
        raise ValueError("RunStateV1 terminal must be true for committed fixture runs")

    transitions = run_state["transitions"]
    if not isinstance(transitions, list) or len(transitions) < 2:
        raise ValueError("RunStateV1 transitions must contain the state path")
    previous = None
    allowed_order = RUN_STATES
    for transition in transitions:
        _require_fields("RunStateV1 transition", transition, ["eventId", "from", "to"])
        if transition["eventId"] not in event_ids:
            raise ValueError(f"RunStateV1 transition references unknown eventId: {transition['eventId']}")
        if transition["from"] != previous:
            raise ValueError("RunStateV1 transitions must form a contiguous chain")
        state = transition["to"]
        if state not in RUN_STATES:
            raise ValueError(f"RunStateV1 transition has invalid state: {state}")
        if previous is not None and allowed_order.index(state) <= allowed_order.index(previous):
            raise ValueError("RunStateV1 transitions must move forward through the state machine")
        previous = state
    if previous != run_state["currentState"]:
        raise ValueError("RunStateV1 final transition must equal currentState")


def validate_permission_policy(policy: dict[str, Any], task_spec: dict[str, Any]) -> None:
    _require_fields(
        "PermissionPolicyV1",
        policy,
        [
            "schemaVersion",
            "capabilityPermissions",
            "forbiddenActions",
            "approvalPoints",
            "externalSideEffectsAllowed",
            "writeBoundary",
        ],
    )
    if policy["schemaVersion"] != PERMISSION_POLICY_SCHEMA_VERSION:
        raise ValueError(f"PermissionPolicyV1 schemaVersion must be {PERMISSION_POLICY_SCHEMA_VERSION}")
    if policy["capabilityPermissions"] != CAPABILITY_PERMISSIONS:
        raise ValueError("PermissionPolicyV1 capabilityPermissions must match Phase 6 read-only MVP policy")
    if policy["forbiddenActions"] != task_spec["forbiddenActions"] or policy["forbiddenActions"] != FORBIDDEN_ACTIONS:
        raise ValueError("PermissionPolicyV1 forbiddenActions must match TaskSpec forbidden actions")
    if policy["approvalPoints"] != task_spec["approvalPoints"] or policy["approvalPoints"] != APPROVAL_POINTS:
        raise ValueError("PermissionPolicyV1 approvalPoints must match TaskSpec approval points")
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("PermissionPolicyV1 must forbid external side effects")
    if policy["writeBoundary"] != "local_artifact_output_only":
        raise ValueError("PermissionPolicyV1 writeBoundary must be local_artifact_output_only")


def validate_recovery_snapshot(snapshot: dict[str, Any], run: dict[str, Any], event_ids: set[str]) -> None:
    _require_fields(
        "RecoverySnapshotV1",
        snapshot,
        ["schemaVersion", "runId", "mode", "resumeFromState", "lastEventId", "inputRefs", "artifactRefs"],
    )
    if snapshot["schemaVersion"] != RECOVERY_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"RecoverySnapshotV1 schemaVersion must be {RECOVERY_SNAPSHOT_SCHEMA_VERSION}")
    if snapshot["runId"] != run["id"]:
        raise ValueError("RecoverySnapshotV1 runId must match run.id")
    if snapshot["mode"] != "deterministic_replay_from_inputs":
        raise ValueError("RecoverySnapshotV1 mode must be deterministic_replay_from_inputs")
    if snapshot["resumeFromState"] != run["status"]:
        raise ValueError("RecoverySnapshotV1 resumeFromState must match run.status")
    if snapshot["lastEventId"] not in event_ids:
        raise ValueError("RecoverySnapshotV1 lastEventId must reference events.jsonl")
    if snapshot["inputRefs"] != RECOVERY_INPUT_REFS:
        raise ValueError("RecoverySnapshotV1 inputRefs must include the deterministic replay inputs")
    if snapshot["artifactRefs"] != run["artifacts"]:
        raise ValueError("RecoverySnapshotV1 artifactRefs must match run.artifacts")


def validate_run_control(run_control: dict[str, Any], run: dict[str, Any], events: list[dict[str, Any]]) -> None:
    _require_fields("RunControlV1", run_control, ["schemaVersion", "runState", "permissionPolicy", "recoverySnapshot"])
    if run_control["schemaVersion"] != RUN_CONTROL_SCHEMA_VERSION:
        raise ValueError(f"RunControlV1 schemaVersion must be {RUN_CONTROL_SCHEMA_VERSION}")
    event_ids = {event["id"] for event in events}
    for step in run["steps"]:
        validate_step_control(step)
    validate_run_state(run_control["runState"], run, event_ids)
    validate_permission_policy(run_control["permissionPolicy"], run["taskSpec"])
    validate_recovery_snapshot(run_control["recoverySnapshot"], run, event_ids)

    capability_names = [step["capability"] for step in run["steps"]]
    if capability_names != PHASE3_CAPABILITY_NAMES:
        raise ValueError(f"RunControlV1 step capabilities must equal {PHASE3_CAPABILITY_NAMES}")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError(f"{path} must contain JSON object lines")
            events.append(event)
    return events


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run-control")
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run = load_json(args.run)
    events = load_events(args.events)
    validate_run_control(run["runControl"], run, events)
    print(f"RunControlV1 validation passed for {args.run}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

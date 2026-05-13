from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TASK_SPEC_SCHEMA_VERSION = "regression-task-spec-v1"
ALLOWED_ACTIONS = ["read_log", "extract_regression_result", "write_artifact"]
EXPECTED_ARTIFACTS = ["evidence.json", "regression_result.json", "email_draft.md"]
APPROVAL_POINTS = ["send_email_requires_human_approval"]
FORBIDDEN_ACTIONS = [
    "modify_repo_or_log",
    "execute_external_side_effect",
    "send_email",
    "call_gui_desktop_cua_or_browser_capability",
    "claim_all_passed_without_sufficient_evidence",
]
SUCCESS_CRITERIA = [
    "Read the regression log path without modifying it.",
    "Extract a safe structured verdict from log markers.",
    "Write evidence-linked artifacts without external side effects.",
    "Verify schema, evidence references, classification precedence, and email grounding.",
]
REQUIRED_EVIDENCE = [
    "sourcePath",
    "exact log excerpt",
    "classification",
    "evidence id referenced by artifacts",
]


class TaskSpecValidationError(ValueError):
    pass


def normalize_spec_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_").lower()
    return normalized or "local_regression"


def derive_task_spec_id(input_log_path: str | Path) -> str:
    path = Path(input_log_path)
    source = path.parent.name if path.name == "input.log" and path.parent.name else path.stem
    return f"task-spec-{normalize_spec_id(source)}"


def build_regression_task_spec(goal: str, input_log_path: str | Path, spec_id: str | None = None) -> dict[str, Any]:
    goal_text = goal.strip()
    input_path = str(input_log_path).strip()
    if not goal_text:
        raise TaskSpecValidationError("TaskSpec goal must be a non-empty string")
    if not input_path:
        raise TaskSpecValidationError("TaskSpec inputLogPath must be a non-empty string")

    task_spec = {
        "schemaVersion": TASK_SPEC_SCHEMA_VERSION,
        "id": spec_id or derive_task_spec_id(input_path),
        "goal": goal_text,
        "inputLogPath": input_path,
        "allowedActions": list(ALLOWED_ACTIONS),
        "forbiddenActions": list(FORBIDDEN_ACTIONS),
        "successCriteria": list(SUCCESS_CRITERIA),
        "requiredEvidence": list(REQUIRED_EVIDENCE),
        "expectedArtifacts": list(EXPECTED_ARTIFACTS),
        "approvalPoints": list(APPROVAL_POINTS),
    }
    validate_regression_task_spec(task_spec)
    return task_spec


def validate_regression_task_spec(task_spec: dict[str, Any]) -> None:
    required_fields = [
        "schemaVersion",
        "id",
        "goal",
        "inputLogPath",
        "allowedActions",
        "forbiddenActions",
        "successCriteria",
        "requiredEvidence",
        "expectedArtifacts",
        "approvalPoints",
    ]
    missing = [field for field in required_fields if field not in task_spec]
    if missing:
        raise TaskSpecValidationError(f"TaskSpec is missing required fields: {missing}")
    if task_spec["schemaVersion"] != TASK_SPEC_SCHEMA_VERSION:
        raise TaskSpecValidationError(f"TaskSpec schemaVersion must be {TASK_SPEC_SCHEMA_VERSION}")
    for field in ["id", "goal", "inputLogPath"]:
        if not isinstance(task_spec[field], str) or not task_spec[field].strip():
            raise TaskSpecValidationError(f"TaskSpec {field} must be a non-empty string")

    exact_lists = {
        "allowedActions": ALLOWED_ACTIONS,
        "forbiddenActions": FORBIDDEN_ACTIONS,
        "expectedArtifacts": EXPECTED_ARTIFACTS,
        "approvalPoints": APPROVAL_POINTS,
    }
    for field, expected in exact_lists.items():
        if task_spec[field] != expected:
            raise TaskSpecValidationError(f"TaskSpec {field} must equal {expected}")

    for field in ["successCriteria", "requiredEvidence"]:
        value = task_spec[field]
        if not isinstance(value, list) or not value:
            raise TaskSpecValidationError(f"TaskSpec {field} must be a non-empty list")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise TaskSpecValidationError(f"TaskSpec {field} must contain only non-empty strings")


def load_regression_task_spec(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        task_spec = json.load(file)
    if not isinstance(task_spec, dict):
        raise TaskSpecValidationError("TaskSpec file must contain a JSON object")
    validate_regression_task_spec(task_spec)
    return task_spec


def paths_match(left: str | Path, right: str | Path, base_dir: Path | None = None) -> bool:
    base = base_dir or Path.cwd()

    def normalized(value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = base / path
        return path.resolve(strict=False)

    return normalized(left) == normalized(right)


def validate_task_spec_for_request(task_spec: dict[str, Any], goal: str, input_log_path: str | Path, base_dir: Path | None = None) -> None:
    validate_regression_task_spec(task_spec)
    if task_spec["goal"].strip() != goal.strip():
        raise TaskSpecValidationError("TaskSpec goal must match requested --goal")
    if not paths_match(task_spec["inputLogPath"], input_log_path, base_dir):
        raise TaskSpecValidationError("TaskSpec inputLogPath must match requested --log-path")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="task-spec-builder")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--input-log-path", required=True, type=Path)
    parser.add_argument("--id")
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    task_spec = build_regression_task_spec(args.goal, args.input_log_path, args.id)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, task_spec)
        print(f"Wrote TaskSpec {task_spec['id']} to {args.out}.")
    else:
        print(json.dumps(task_spec, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

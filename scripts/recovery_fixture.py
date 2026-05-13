from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from capability_contract import build_capability_envelope, capability_ref
from fixture_runner import (
    GENERATED_AT,
    Fixture,
    build_run_steps,
    display_path,
    extract_evidence,
    stable_hash,
    task_spec_for,
)
from run_control import build_run_control


RECOVERY_FIXTURE_ID = "interrupted_after_extract"
RECOVERY_ARTIFACT_ROOT = "artifacts/recovery"
DEFAULT_SOURCE_FIXTURE = Path("fixtures/regression/all_passed")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_interrupted_fixture(source_fixture_dir: Path = DEFAULT_SOURCE_FIXTURE) -> tuple[dict, list[dict]]:
    log_path = source_fixture_dir / "input.log"
    if not log_path.is_file():
        raise FileNotFoundError(f"Missing source regression log: {log_path}")

    fixture = Fixture(
        id=RECOVERY_FIXTURE_ID,
        goal="Confirm whether the m2b_lec_regr regression passed and draft a grounded English status email.",
        input_log_file="input.log",
        expected_verdict="unknown",
        allow_all_passed_email=False,
        directory=source_fixture_dir,
    )
    task_spec = task_spec_for(fixture)
    evidence = extract_evidence(fixture)
    evidence_ids = [item["id"] for item in evidence]
    fixture_hash = stable_hash([log_path])
    run_id = f"run-{RECOVERY_FIXTURE_ID}-{fixture_hash[:8]}"
    capability_envelope = build_capability_envelope(task_spec["allowedActions"] + ["rule_verifier"])
    completed_steps = build_run_steps("passed")[:2]
    events = build_interrupted_events(fixture, run_id, evidence_ids)
    artifacts = ["run.json", "events.jsonl"]
    resume_target = {
        "capability": "write_artifact",
        "capabilityRef": capability_ref("write_artifact"),
        "inputRef": "regression_result_candidate",
        "outputRef": "evidence.json,regression_result.json,email_draft.md,run.json",
        "stepId": "step-write-artifact",
    }
    run = {
        "schemaVersion": "run-v1",
        "id": run_id,
        "fixtureId": RECOVERY_FIXTURE_ID,
        "task": fixture.goal,
        "taskSpec": task_spec,
        "capabilityEnvelope": capability_envelope,
        "steps": completed_steps,
        "events": [event["id"] for event in events],
        "artifacts": artifacts,
        "artifactRoot": RECOVERY_ARTIFACT_ROOT,
        "status": "running",
        "generatedAt": GENERATED_AT,
    }
    run["runControl"] = build_run_control(
        RECOVERY_FIXTURE_ID,
        run_id,
        "running",
        capability_envelope,
        completed_steps,
        events,
        artifacts,
        RECOVERY_ARTIFACT_ROOT,
        resume_target,
    )
    return run, events


def build_interrupted_events(fixture: Fixture, run_id: str, evidence_ids: list[str]) -> list[dict]:
    event_specs = [
        ("run.created", "completed", None, "run.json", [], None),
        ("task_spec.generated", "completed", "fixture.json", "run.json#taskSpec", [], None),
        ("capability.read_log.completed", "completed", display_path(fixture.log_path), "log_text", [], "read_log"),
        (
            "capability.extract_regression_result.completed",
            "completed",
            "log_text",
            "regression_result_candidate",
            evidence_ids,
            "extract_regression_result",
        ),
    ]
    events: list[dict] = []
    for index, (event_type, status, input_ref, output_ref, ids, capability) in enumerate(event_specs, start=1):
        event = {
            "id": f"event-{RECOVERY_FIXTURE_ID}-{index:03d}",
            "runId": run_id,
            "fixtureId": RECOVERY_FIXTURE_ID,
            "type": event_type,
            "status": status,
            "timestamp": GENERATED_AT,
            "causalRefs": [events[-1]["id"]] if events else [],
        }
        if input_ref:
            event["inputRef"] = input_ref
        if output_ref:
            event["outputRef"] = output_ref
        if ids:
            event["evidenceIds"] = ids
        if capability:
            event["capability"] = capability
            event["capabilityRef"] = capability_ref(capability)
        events.append(event)
    return events


def write_interrupted_fixture(out_dir: Path, source_fixture_dir: Path = DEFAULT_SOURCE_FIXTURE) -> dict:
    run, events = build_interrupted_fixture(source_fixture_dir)
    run_dir = out_dir / RECOVERY_FIXTURE_ID
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "run.json", run)
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )
    return run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="recovery-fixture-builder")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--source-fixture-dir", default=DEFAULT_SOURCE_FIXTURE, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run = write_interrupted_fixture(args.out_dir, args.source_fixture_dir)
    print(f"Wrote interrupted recovery fixture {run['fixtureId']} into {args.out_dir / run['fixtureId']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

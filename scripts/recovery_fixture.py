from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from capability_contract import build_capability_envelope, capability_ref
from fixture_runner import (
    GENERATED_AT,
    Fixture,
    capability_step,
    classify,
    display_path,
    extract_evidence,
    stable_hash,
    task_spec_for,
    write_json,
)
from run_control import build_run_control


INTERRUPTED_FIXTURE_ID = "interrupted_after_extract"
ARTIFACT_ROOT = "artifacts/recovery"


def build_interrupted_events(fixture: Fixture, run_id: str, evidence_ids: list[str]) -> list[dict]:
    event_specs = [
        ("run.created", "completed", None, "run.json", [], None),
        ("task_spec.generated", "completed", "fixture.json", "run.json#taskSpec", [], None),
        ("capability.read_log.completed", "completed", display_path(fixture.log_path), "log_text", [], "read_log"),
        ("capability.extract_regression_result.completed", "completed", "log_text", "regression_result_candidate", evidence_ids, "extract_regression_result"),
    ]
    events: list[dict] = []
    for index, (event_type, status, input_ref, output_ref, ids, capability) in enumerate(event_specs, start=1):
        event = {
            "causalRefs": [events[-1]["id"]] if events else [],
            "fixtureId": fixture.id,
            "id": f"event-{fixture.id}-{index:03d}",
            "runId": run_id,
            "status": status,
            "timestamp": GENERATED_AT,
            "type": event_type,
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


def build_interrupted_steps() -> list[dict]:
    return [
        capability_step("step-read-log", "read_log", "completed"),
        capability_step("step-extract-regression-result", "extract_regression_result", "completed"),
        capability_step("step-write-artifact", "write_artifact", "pending"),
        capability_step("step-verify", "rule_verifier", "pending"),
    ]


def write_interrupted_recovery_fixture(source_fixture_dir: Path, out_dir: Path) -> dict:
    if not (source_fixture_dir / "input.log").is_file():
        raise FileNotFoundError(f"Missing recovery source input log: {source_fixture_dir / 'input.log'}")

    fixture = Fixture(
        id=INTERRUPTED_FIXTURE_ID,
        goal="Resume an interrupted read-only regression run after result extraction.",
        input_log_file="input.log",
        expected_verdict="unknown",
        allow_all_passed_email=False,
        directory=source_fixture_dir,
    )
    run_hash = stable_hash([source_fixture_dir / "fixture.json", fixture.log_path])
    run_id = f"run-{fixture.id}-{run_hash[:8]}"
    task_spec = task_spec_for(fixture)
    evidence = extract_evidence(fixture)
    _, _, evidence_ids = classify(evidence)
    events = build_interrupted_events(fixture, run_id, evidence_ids)
    capability_envelope = build_capability_envelope(task_spec["allowedActions"] + ["rule_verifier"])
    steps = build_interrupted_steps()
    artifacts = ["run.json", "events.jsonl"]
    resume_target = {
        "capability": "write_artifact",
        "capabilityRef": capability_ref("write_artifact"),
        "inputRef": "regression_result_candidate",
        "reason": "resume_after_last_completed_event",
        "stepId": "step-write-artifact",
    }
    run = {
        "artifactRoot": ARTIFACT_ROOT,
        "artifacts": artifacts,
        "capabilityEnvelope": capability_envelope,
        "events": [event["id"] for event in events],
        "fixtureId": fixture.id,
        "generatedAt": GENERATED_AT,
        "id": run_id,
        "schemaVersion": "run-v1",
        "status": "interrupted",
        "steps": steps,
        "task": fixture.goal,
        "taskSpec": task_spec,
    }
    run["runControl"] = build_run_control(
        fixture.id,
        run_id,
        "interrupted",
        capability_envelope,
        steps,
        events,
        artifacts,
        current_state="running",
        resume_target=resume_target,
        artifact_root=ARTIFACT_ROOT,
    )

    run_dir = out_dir / fixture.id
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
    parser = argparse.ArgumentParser(prog="recovery-fixture")
    parser.add_argument("--source-fixture-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run = write_interrupted_recovery_fixture(args.source_fixture_dir, args.out_dir)
    print(f"Wrote interrupted recovery fixture {run['id']} into {args.out_dir / run['fixtureId']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

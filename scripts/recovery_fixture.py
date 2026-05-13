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
    classify,
    extract_evidence,
    load_fixture,
    stable_hash,
    task_spec_for,
    write_json,
)
from run_control import build_run_control


RECOVERY_FIXTURE_ID = "interrupted_after_extract"
RECOVERY_ARTIFACTS = ["run.json", "events.jsonl"]


def interrupted_event(
    fixture_id: str,
    run_id: str,
    index: int,
    event_type: str,
    status: str,
    causal_refs: list[str],
    input_ref: str,
    output_ref: str,
    evidence_ids: list[str] | None = None,
    capability: str | None = None,
) -> dict:
    event = {
        "causalRefs": causal_refs,
        "fixtureId": fixture_id,
        "id": f"event-{fixture_id}-{index:03d}",
        "inputRef": input_ref,
        "outputRef": output_ref,
        "runId": run_id,
        "status": status,
        "timestamp": GENERATED_AT,
        "type": event_type,
    }
    if evidence_ids is not None:
        event["evidenceIds"] = evidence_ids
    if capability is not None:
        event["capability"] = capability
        event["capabilityRef"] = capability_ref(capability)
    return event


def build_interrupted_recovery_fixture(out_dir: Path) -> Path:
    source_fixture = load_fixture(Path("fixtures/regression/all_passed"))
    fixture = Fixture(
        id=RECOVERY_FIXTURE_ID,
        goal=source_fixture.goal,
        input_log_file=source_fixture.input_log_file,
        expected_verdict="passed",
        allow_all_passed_email=True,
        directory=source_fixture.directory,
    )
    task_spec = task_spec_for(fixture)
    evidence = extract_evidence(fixture)
    verdict, summary, evidence_ids = classify(evidence)
    fixture_hash = stable_hash([fixture.log_path])
    run_id = f"run-{fixture.id}-{fixture_hash[:8]}"
    run_dir = out_dir / fixture.id
    artifact_root = f"artifacts/recovery/{fixture.id}"

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    capability_envelope = build_capability_envelope(task_spec["allowedActions"] + ["rule_verifier"])
    steps = build_run_steps("pending")
    steps[0]["status"] = "completed"
    steps[1]["status"] = "completed"
    steps[2]["status"] = "pending"

    events = [
        {
            "causalRefs": [],
            "fixtureId": fixture.id,
            "id": f"event-{fixture.id}-001",
            "outputRef": "run.json",
            "runId": run_id,
            "status": "completed",
            "timestamp": GENERATED_AT,
            "type": "run.created",
        },
        interrupted_event(
            fixture.id,
            run_id,
            2,
            "task_spec.generated",
            "completed",
            [f"event-{fixture.id}-001"],
            "fixture.json",
            "run.json#taskSpec",
        ),
        interrupted_event(
            fixture.id,
            run_id,
            3,
            "capability.read_log.completed",
            "completed",
            [f"event-{fixture.id}-002"],
            str(fixture.log_path),
            "log_text",
            capability="read_log",
        ),
        interrupted_event(
            fixture.id,
            run_id,
            4,
            "capability.extract_regression_result.completed",
            "completed",
            [f"event-{fixture.id}-003"],
            "log_text",
            "regression_result_candidate",
            evidence_ids,
            "extract_regression_result",
        ),
    ]
    resume_target = {
        "capability": "write_artifact",
        "capabilityRef": capability_ref("write_artifact"),
        "inputRef": "regression_result_candidate",
        "outputRef": "evidence.json,regression_result.json,email_draft.md,run.json",
        "stepId": "step-write-artifact",
    }
    run = {
        "artifactRoot": artifact_root,
        "artifacts": list(RECOVERY_ARTIFACTS),
        "capabilityEnvelope": capability_envelope,
        "events": [event["id"] for event in events],
        "fixtureId": fixture.id,
        "generatedAt": GENERATED_AT,
        "id": run_id,
        "interruption": {
            "afterEventId": f"event-{fixture.id}-004",
            "candidateSummary": summary,
            "candidateVerdict": verdict,
            "schemaVersion": "interrupted-recovery-fixture-v1",
        },
        "schemaVersion": "run-v1",
        "status": "running",
        "steps": steps,
        "task": fixture.goal,
        "taskSpec": task_spec,
    }
    run["runControl"] = build_run_control(
        fixture_id=fixture.id,
        run_id=run_id,
        run_status="running",
        capability_envelope=capability_envelope,
        steps=steps,
        events=events,
        artifacts=run["artifacts"],
        current_state="running",
        artifact_root=artifact_root,
        resume_target=resume_target,
    )

    write_json(run_dir / "run.json", run)
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )
    return run_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="recovery-fixture-builder")
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = build_interrupted_recovery_fixture(args.out_dir)
    print(f"Wrote interrupted recovery fixture to {run_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from fixture_runner import (
    EXPECTED_ARTIFACTS,
    GENERATED_AT,
    Fixture,
    build_email,
    build_events,
    classify,
    extract_evidence,
    stable_hash,
    task_spec_for,
    verify_artifacts,
    write_json,
)


def derive_run_case_id(log_path: Path) -> str:
    source = log_path.parent.name if log_path.name == "input.log" and log_path.parent.name else log_path.stem
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", source).strip("_").lower()
    return normalized or "local_regression"


def write_local_run(log_path: Path, goal: str, out_dir: Path) -> dict:
    if not log_path.is_file():
        raise FileNotFoundError(f"Log path does not exist or is not a file: {log_path}")
    if not goal.strip():
        raise ValueError("--goal must be a non-empty string")

    case_id = derive_run_case_id(log_path)
    initial_fixture = Fixture(
        id=case_id,
        goal=goal,
        input_log_file=log_path.name,
        expected_verdict="unknown",
        allow_all_passed_email=True,
        directory=log_path.parent,
    )
    # Phase 2 gate: build and validate the executable spec before reading or classifying the log.
    task_spec = task_spec_for(initial_fixture)
    evidence = extract_evidence(initial_fixture)
    verdict, summary, verdict_evidence_ids = classify(evidence)
    fixture = Fixture(
        id=case_id,
        goal=goal,
        input_log_file=log_path.name,
        expected_verdict=verdict,
        allow_all_passed_email=verdict == "passed",
        directory=log_path.parent,
    )

    fixture_hash = stable_hash([log_path])
    run_id = f"run-{case_id}-{fixture_hash[:8]}"
    run_dir = out_dir / case_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "schemaVersion": "regression-result-v1",
        "id": f"regression-result-{case_id}",
        "fixtureId": case_id,
        "verdict": verdict,
        "summary": summary,
        "evidenceIds": verdict_evidence_ids,
        "ruleResults": [],
        "generatedAt": GENERATED_AT,
    }
    email = build_email(fixture, result)
    verifier_report = verify_artifacts(fixture, run_id, fixture_hash, task_spec, evidence, result, email)
    report_status = verifier_report["status"]
    events = build_events(fixture, run_id, verdict_evidence_ids, "completed" if report_status == "passed" else "failed")
    run = {
        "schemaVersion": "run-v1",
        "id": run_id,
        "fixtureId": case_id,
        "task": goal,
        "taskSpec": task_spec,
        "steps": [
            {"id": "step-read-log", "capability": "read_log", "status": "completed"},
            {"id": "step-extract-regression-result", "capability": "extract_regression_result", "status": "completed"},
            {"id": "step-write-artifact", "capability": "write_artifact", "status": "completed"},
            {"id": "step-verify", "capability": "rule_verifier", "status": report_status},
        ],
        "events": [event["id"] for event in events],
        "artifacts": EXPECTED_ARTIFACTS + ["run.json", "events.jsonl", "verifier_report.json"],
        "status": "completed" if report_status == "passed" else "failed",
        "generatedAt": GENERATED_AT,
    }

    write_json(run_dir / "run.json", run)
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n", encoding="utf-8")
    write_json(run_dir / "evidence.json", {"schemaVersion": "evidence-list-v1", "fixtureId": case_id, "items": evidence})
    write_json(run_dir / "regression_result.json", result)
    (run_dir / "email_draft.md").write_text(email, encoding="utf-8")
    write_json(run_dir / "verifier_report.json", verifier_report)
    return verifier_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="local-readonly-runner")
    parser.add_argument("--log-path", required=True, type=Path)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_local_run(args.log_path, args.goal, args.out_dir)
    print(f"Wrote local read-only run for {report['fixtureId']} into {args.out_dir / report['fixtureId']}.")
    if report["status"] != "passed":
        print(report["summary"])
        return 1
    print("Local read-only runner validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from capability_contract import build_capability_envelope
from context_pack import (
    ROOT,
    load_json as load_context_pack_json,
    validate_context_pack,
    validate_context_pack_for_request,
    validate_evidence_with_context_pack,
)
from evidence_list import build_evidence_list
from fixture_runner import (
    EXPECTED_ARTIFACTS,
    GENERATED_AT,
    Fixture,
    build_email,
    build_events,
    build_run_steps,
    classify,
    extract_evidence,
    stable_hash,
    task_spec_for,
    verify_artifacts,
    write_json,
)
from task_spec import load_regression_task_spec, validate_task_spec_for_request


def derive_run_case_id(log_path: Path) -> str:
    source = log_path.parent.name if log_path.name == "input.log" and log_path.parent.name else log_path.stem
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", source).strip("_").lower()
    return normalized or "local_regression"


def write_local_run(
    log_path: Path,
    goal: str,
    out_dir: Path,
    task_spec_path: Path | None = None,
    context_pack_path: Path | None = None,
) -> dict:
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
    # Phase 2 gate: use a reviewed TaskSpec when provided, before reading or classifying the log.
    if task_spec_path:
        task_spec = load_regression_task_spec(task_spec_path)
        validate_task_spec_for_request(task_spec, goal, log_path)
    else:
        task_spec = task_spec_for(initial_fixture)
    context_pack = None
    if context_pack_path:
        context_pack = load_context_pack_json(context_pack_path)
        validate_context_pack(context_pack, ROOT)
        validate_context_pack_for_request(context_pack, log_path, goal, ROOT)
    evidence_payload = build_evidence_list(case_id, extract_evidence(initial_fixture))
    evidence = evidence_payload["items"]
    if context_pack:
        validate_evidence_with_context_pack(evidence, context_pack, ROOT)
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
        "capabilityEnvelope": build_capability_envelope(task_spec["allowedActions"] + ["rule_verifier"]),
        "steps": build_run_steps(report_status),
        "events": [event["id"] for event in events],
        "artifacts": EXPECTED_ARTIFACTS + ["run.json", "events.jsonl", "verifier_report.json"],
        "status": "completed" if report_status == "passed" else "failed",
        "generatedAt": GENERATED_AT,
    }

    write_json(run_dir / "run.json", run)
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n", encoding="utf-8")
    write_json(run_dir / "evidence.json", evidence_payload)
    write_json(run_dir / "regression_result.json", result)
    (run_dir / "email_draft.md").write_text(email, encoding="utf-8")
    write_json(run_dir / "verifier_report.json", verifier_report)
    return verifier_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="local-readonly-runner")
    parser.add_argument("--log-path", required=True, type=Path)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--task-spec-path", type=Path)
    parser.add_argument("--context-pack-path", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_local_run(args.log_path, args.goal, args.out_dir, args.task_spec_path, args.context_pack_path)
    print(f"Wrote local read-only run for {report['fixtureId']} into {args.out_dir / report['fixtureId']}.")
    if report["status"] != "passed":
        print(report["summary"])
        return 1
    print("Local read-only runner validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

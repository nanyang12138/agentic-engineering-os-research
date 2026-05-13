from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from capability_contract import build_capability_envelope, capability_ref
from task_spec import EXPECTED_ARTIFACTS, build_regression_task_spec
from verifier_runtime import verify_artifacts


GENERATED_AT = "2026-05-12T14:39:00Z"


@dataclass(frozen=True)
class Fixture:
    id: str
    goal: str
    input_log_file: str
    expected_verdict: str
    allow_all_passed_email: bool
    directory: Path

    @property
    def log_path(self) -> Path:
        return self.directory / self.input_log_file


@dataclass(frozen=True)
class Marker:
    classification: str
    confidence: str
    pattern: re.Pattern[str]


MARKERS = [
    Marker("failure_marker", "high", re.compile(r"\b(status:\s*failed|failed_tests\s*:\s*[1-9]\d*|failures\s*:\s*[1-9]\d*|error:\s*test)\b", re.I)),
    Marker("incomplete_marker", "high", re.compile(r"\b(status:\s*incomplete|incomplete_jobs\s*:\s*[1-9]\d*|still_running\s*:\s*[1-9]\d*|missing\s+final\s+summary|timeout\s+waiting)\b", re.I)),
    Marker("warning_marker", "medium", re.compile(r"\b(warning|warnings\s*:\s*[1-9]\d*)\b", re.I)),
    Marker("waiver_marker", "medium", re.compile(r"\b(waiver|waived\s+error|waived_errors\s*:\s*[1-9]\d*)\b", re.I)),
    Marker("all_passed_marker", "high", re.compile(r"\b(all\s+tests\s+passed|status:\s*passed|failed_tests\s*:\s*0|incomplete_jobs\s*:\s*0)\b", re.I)),
    Marker("ambiguous", "low", re.compile(r"\b(ambiguous|unable\s+to\s+determine|summary\s+unavailable|no\s+final\s+verdict)\b", re.I)),
]

VERDICTS = {"passed", "failed", "incomplete", "warning_or_waiver", "unknown", "needs_human_check"}


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stable_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def load_fixture(directory: Path) -> Fixture:
    payload = read_json(directory / "fixture.json")
    required = ["id", "goal", "inputLogFile", "expectedVerdict", "allowAllPassedEmail"]
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"{directory}/fixture.json is missing required fields: {missing}")
    if payload["expectedVerdict"] not in VERDICTS:
        raise ValueError(f"{directory}/fixture.json has invalid expectedVerdict: {payload['expectedVerdict']}")
    fixture = Fixture(
        id=payload["id"],
        goal=payload["goal"],
        input_log_file=payload["inputLogFile"],
        expected_verdict=payload["expectedVerdict"],
        allow_all_passed_email=bool(payload["allowAllPassedEmail"]),
        directory=directory,
    )
    if fixture.input_log_file != "input.log":
        raise ValueError(f"{directory}/fixture.json must use inputLogFile='input.log'")
    if not fixture.log_path.is_file():
        raise ValueError(f"Missing input log for fixture {fixture.id}: {fixture.log_path}")
    return fixture


def task_spec_for(fixture: Fixture) -> dict:
    return build_regression_task_spec(fixture.goal, display_path(fixture.log_path), f"task-spec-{fixture.id}")


def extract_evidence(fixture: Fixture) -> list[dict]:
    evidence: list[dict] = []
    lines = fixture.log_path.read_text(encoding="utf-8").splitlines()
    seen: set[tuple[str, str]] = set()
    for line_number, line in enumerate(lines, start=1):
        for marker in MARKERS:
            if marker.pattern.search(line):
                key = (marker.classification, line.strip())
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    {
                        "id": f"ev-{fixture.id}-{len(evidence) + 1:03d}",
                        "type": "log",
                        "sourcePath": display_path(fixture.log_path),
                        "lineRange": [line_number, line_number],
                        "excerpt": line.strip(),
                        "observedAt": GENERATED_AT,
                        "classification": marker.classification,
                        "confidence": marker.confidence,
                    }
                )
    if not evidence:
        evidence.append(
            {
                "id": f"ev-{fixture.id}-001",
                "type": "log",
                "sourcePath": display_path(fixture.log_path),
                "lineRange": [1, min(len(lines), 3) if lines else 1],
                "excerpt": "\n".join(lines[:3]) if lines else "",
                "observedAt": GENERATED_AT,
                "classification": "ambiguous",
                "confidence": "low",
            }
        )
    return evidence


def classify(evidence: list[dict]) -> tuple[str, str, list[str]]:
    classes = {item["classification"] for item in evidence}
    ids_by_class = {
        classification: [item["id"] for item in evidence if item["classification"] == classification]
        for classification in classes
    }
    has_pass = "all_passed_marker" in classes
    has_failure = "failure_marker" in classes
    has_incomplete = "incomplete_marker" in classes
    has_warning = "warning_marker" in classes or "waiver_marker" in classes
    has_ambiguous = "ambiguous" in classes

    if has_pass and (has_failure or has_incomplete):
        ids = ids_by_class.get("all_passed_marker", []) + ids_by_class.get("failure_marker", []) + ids_by_class.get("incomplete_marker", [])
        return "needs_human_check", "Conflicting pass and blocking markers require human review.", ids
    if has_failure:
        return "failed", "Failure markers were found in the regression log.", ids_by_class["failure_marker"]
    if has_incomplete:
        return "incomplete", "Incomplete or still-running markers were found in the regression log.", ids_by_class["incomplete_marker"]
    if has_warning:
        ids = ids_by_class.get("warning_marker", []) + ids_by_class.get("waiver_marker", [])
        return "warning_or_waiver", "Warning or waiver markers were found and require review before a clean pass can be claimed.", ids
    if has_pass and not has_ambiguous:
        return "passed", "All-pass markers were found with no conflicting markers.", ids_by_class["all_passed_marker"]
    ids = ids_by_class.get("ambiguous", [item["id"] for item in evidence[:1]])
    return "unknown", "No sufficient pass/fail/incomplete marker was found.", ids


def build_email(fixture: Fixture, result: dict) -> str:
    evidence_line = ", ".join(result["evidenceIds"]) if result["evidenceIds"] else "none"
    header = [
        f"Subject: Regression status for {fixture.id}",
        "",
        "Hello,",
        "",
        f"The structured regression result artifact `{result['id']}` reports verdict `{result['verdict']}`.",
        f"Referenced evidence ids: {evidence_line}.",
        "",
    ]
    if result["verdict"] == "passed":
        body = [
            "Based only on the structured result and referenced evidence, the regression is a clean pass.",
            "Please review the attached artifacts before sending any external notification.",
        ]
    elif result["verdict"] == "failed":
        body = [
            "The regression has failure markers in the referenced log evidence.",
            "Please review the failure evidence before deciding the next action.",
        ]
    elif result["verdict"] == "incomplete":
        body = [
            "The regression is not complete according to the referenced log evidence.",
            "Please wait for a final summary or review the run manually.",
        ]
    elif result["verdict"] == "warning_or_waiver":
        body = [
            "The regression includes warning or waiver markers that require review.",
            "Please confirm whether the warning or waiver is acceptable before sending a pass-style update.",
        ]
    elif result["verdict"] == "needs_human_check":
        body = [
            "The regression needs human review before any status can be confirmed.",
            "Please inspect the cited evidence and decide the final communication.",
        ]
    else:
        body = [
            "The runner cannot confirm the regression status yet.",
            "Please inspect the cited evidence and provide a human decision.",
        ]
    footer = ["", "Regards,", "Agentic Engineering OS Fixture Runner", ""]
    return "\n".join(header + body + footer)


def capability_step(step_id: str, capability: str, status: str) -> dict:
    return {
        "id": step_id,
        "capability": capability,
        "capabilityRef": capability_ref(capability),
        "status": status,
    }


def build_run_steps(report_status: str) -> list[dict]:
    return [
        capability_step("step-read-log", "read_log", "completed"),
        capability_step("step-extract-regression-result", "extract_regression_result", "completed"),
        capability_step("step-write-artifact", "write_artifact", "completed"),
        capability_step("step-verify", "rule_verifier", report_status),
    ]


def build_events(fixture: Fixture, run_id: str, evidence_ids: list[str], verifier_status: str) -> list[dict]:
    event_specs = [
        ("run.created", "completed", None, "run.json", [], None),
        ("task_spec.generated", "completed", "fixture.json", "run.json#taskSpec", [], None),
        ("capability.read_log.completed", "completed", display_path(fixture.log_path), "log_text", [], "read_log"),
        ("capability.extract_regression_result.completed", "completed", "log_text", "regression_result.json", evidence_ids, "extract_regression_result"),
        ("artifact.write.completed", "completed", "regression_result.json", "evidence.json,email_draft.md,run.json", evidence_ids, "write_artifact"),
        ("verifier.completed", verifier_status, "evidence.json,regression_result.json,email_draft.md", "verifier_report.json", evidence_ids, "rule_verifier"),
        ("run.completed" if verifier_status == "completed" else "run.failed", verifier_status, "verifier_report.json", "run.json", evidence_ids, None),
    ]
    events: list[dict] = []
    for index, (event_type, status, input_ref, output_ref, ids, capability) in enumerate(event_specs, start=1):
        event = {
            "id": f"event-{fixture.id}-{index:03d}",
            "runId": run_id,
            "fixtureId": fixture.id,
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


def run_fixture(fixture: Fixture, out_dir: Path) -> dict:
    fixture_hash = stable_hash([fixture.directory / "fixture.json", fixture.log_path])
    run_id = f"run-{fixture.id}-{fixture_hash[:8]}"
    run_dir = out_dir / fixture.id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    task_spec = task_spec_for(fixture)
    evidence = extract_evidence(fixture)
    verdict, summary, verdict_evidence_ids = classify(evidence)
    result = {
        "schemaVersion": "regression-result-v1",
        "id": f"regression-result-{fixture.id}",
        "fixtureId": fixture.id,
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
        "fixtureId": fixture.id,
        "task": fixture.goal,
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
    write_json(run_dir / "evidence.json", {"schemaVersion": "evidence-list-v1", "fixtureId": fixture.id, "items": evidence})
    write_json(run_dir / "regression_result.json", result)
    (run_dir / "email_draft.md").write_text(email, encoding="utf-8")
    write_json(run_dir / "verifier_report.json", verifier_report)
    return verifier_report


def run_all(fixture_dir: Path, out_dir: Path) -> list[dict]:
    if not fixture_dir.is_dir():
        raise ValueError(f"Fixture directory does not exist: {fixture_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for case_dir in sorted(path for path in fixture_dir.iterdir() if path.is_dir()):
        reports.append(run_fixture(load_fixture(case_dir), out_dir))
    if not reports:
        raise ValueError(f"No fixture cases found under {fixture_dir}")
    return reports


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fixture-runner")
    parser.add_argument("--fixture-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    reports = run_all(args.fixture_dir, args.out_dir)
    failed = [report for report in reports if report["status"] != "passed"]
    print(f"Processed {len(reports)} fixtures into {args.out_dir}.")
    if failed:
        for report in failed:
            print(f"FAILED {report['fixtureId']}: {report['summary']}")
        return 1
    print("Fixture runner validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

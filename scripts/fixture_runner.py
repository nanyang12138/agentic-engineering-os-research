from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


GENERATED_AT = "2026-05-12T00:00:00Z"

EXPECTED_FIXTURES = [
    "all_passed",
    "failed_tests",
    "incomplete_jobs",
    "passed_with_warning_or_waiver",
    "ambiguous_summary",
]

VALID_VERDICTS = {
    "passed",
    "failed",
    "incomplete",
    "warning_or_waiver",
    "unknown",
    "needs_human_check",
}

VALID_EVIDENCE_CLASSIFICATIONS = {
    "all_passed_marker",
    "failure_marker",
    "incomplete_marker",
    "warning_marker",
    "waiver_marker",
    "metadata",
    "ambiguous",
}

UNSAFE_ALL_PASSED_PHRASES = (
    "all tests passed",
    "regression passed",
    "clean pass",
    "all passed",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )


def path_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_fixture(fixture_json_path: Path, input_log_path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(fixture_json_path.read_bytes())
    digest.update(b"\n")
    digest.update(input_log_path.read_bytes())
    return digest.hexdigest()


def count_marker(line: str, marker: str) -> int | None:
    match = re.search(rf"\b{re.escape(marker)}=(\d+)\b", line)
    if not match:
        return None
    return int(match.group(1))


def classify_line(line: str) -> tuple[str, str] | None:
    normalized = line.strip()
    upper = normalized.upper()

    if upper.startswith("RUN_ID=") or upper.startswith("STARTED_AT=") or upper.startswith("OWNER="):
        return ("metadata", "high")

    failed_count = count_marker(upper, "FAILED_TESTS")
    if failed_count is not None and failed_count > 0:
        return ("failure_marker", "high")
    if "TEST_FAILURE:" in upper or "REGRESSION_RESULT=FAILED" in upper:
        return ("failure_marker", "high")

    incomplete_count = count_marker(upper, "INCOMPLETE_JOBS")
    if incomplete_count is not None and incomplete_count > 0:
        return ("incomplete_marker", "high")
    if "RUN_STATUS=INCOMPLETE" in upper or "JOB_STATE=RUNNING" in upper:
        return ("incomplete_marker", "high")

    warning_count = count_marker(upper, "WARNING_COUNT")
    if warning_count is not None and warning_count > 0:
        return ("warning_marker", "medium")
    if upper.startswith("WARNING:"):
        return ("warning_marker", "medium")

    waiver_count = count_marker(upper, "WAIVER_COUNT")
    if waiver_count is not None and waiver_count > 0:
        return ("waiver_marker", "medium")
    if upper.startswith("WAIVER:"):
        return ("waiver_marker", "medium")

    if "REGRESSION_RESULT=PASSED" in upper or "ALL_TESTS_PASSED" in upper:
        return ("all_passed_marker", "high")

    if "SUMMARY_UNCLEAR" in upper or "RESULT=UNKNOWN" in upper or "MAYBE PASSED" in upper:
        return ("ambiguous", "low")

    return None


def build_evidence(fixture_id: str, source_path: Path, log_text: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    source_ref = path_ref(source_path)

    for line_number, line in enumerate(log_text.splitlines(), start=1):
        classification = classify_line(line)
        if not classification:
            continue
        evidence.append(
            {
                "id": f"ev:{fixture_id}:{len(evidence) + 1:03d}",
                "type": "log",
                "sourcePath": source_ref,
                "lineRange": [line_number, line_number],
                "excerpt": line.strip(),
                "observedAt": GENERATED_AT,
                "classification": classification[0],
                "confidence": classification[1],
            }
        )

    if not evidence:
        evidence.append(
            {
                "id": f"ev:{fixture_id}:001",
                "type": "log",
                "sourcePath": source_ref,
                "lineRange": None,
                "excerpt": "No supported regression verdict marker found.",
                "observedAt": GENERATED_AT,
                "classification": "ambiguous",
                "confidence": "low",
            }
        )

    return evidence


def ids_for(evidence: list[dict[str, Any]], classifications: set[str]) -> list[str]:
    return [item["id"] for item in evidence if item["classification"] in classifications]


def extract_regression_result(fixture_id: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    failure_ids = ids_for(evidence, {"failure_marker"})
    incomplete_ids = ids_for(evidence, {"incomplete_marker"})
    warning_ids = ids_for(evidence, {"warning_marker", "waiver_marker"})
    passed_ids = ids_for(evidence, {"all_passed_marker"})
    ambiguous_ids = ids_for(evidence, {"ambiguous"})

    if failure_ids and (passed_ids or incomplete_ids):
        verdict = "needs_human_check"
        evidence_ids = sorted(set(failure_ids + passed_ids + incomplete_ids))
        summary = "Conflicting regression markers require human review."
    elif failure_ids:
        verdict = "failed"
        evidence_ids = failure_ids
        summary = "Failure markers were found in the regression log."
    elif incomplete_ids:
        verdict = "incomplete"
        evidence_ids = incomplete_ids
        summary = "Incomplete or still-running job markers were found."
    elif warning_ids:
        verdict = "warning_or_waiver"
        evidence_ids = warning_ids + passed_ids
        summary = "Warning or waiver markers prevent a clean passed verdict."
    elif passed_ids and not ambiguous_ids:
        verdict = "passed"
        evidence_ids = passed_ids
        summary = "The log contains an explicit all-passed marker and no conflict markers."
    else:
        verdict = "unknown"
        evidence_ids = ambiguous_ids or [evidence[0]["id"]]
        summary = "The log does not contain enough unambiguous evidence for a safe verdict."

    return {
        "id": f"regression_result:{fixture_id}",
        "verdict": verdict,
        "summary": summary,
        "evidenceIds": evidence_ids,
        "ruleResults": [],
        "generatedAt": GENERATED_AT,
    }


def build_task_spec(fixture: dict[str, Any], input_log_path: Path) -> dict[str, Any]:
    fixture_id = fixture["id"]
    return {
        "id": f"task_spec:{fixture_id}",
        "goal": fixture["goal"],
        "inputLogPath": path_ref(input_log_path),
        "allowedActions": ["read_log", "extract_regression_result", "write_artifact"],
        "forbiddenActions": [
            "modify_repo_or_log",
            "execute_external_side_effects",
            "send_email",
            "call_gui_desktop_cua_or_browser_capability",
            "assert_all_passed_without_sufficient_evidence",
        ],
        "successCriteria": [
            "read the fixed regression log",
            "extract a structured regression verdict",
            "write evidence, result, email draft, and verifier artifacts",
        ],
        "requiredEvidence": [
            "log excerpt for each non-unknown verdict",
            "fixture hash",
            "evidence id references in generated artifacts",
        ],
        "expectedArtifacts": ["evidence.json", "regression_result.json", "email_draft.md"],
        "approvalPoints": ["send_email_requires_human_approval"],
    }


def build_email_draft(fixture: dict[str, Any], result: dict[str, Any]) -> str:
    fixture_id = fixture["id"]
    evidence_refs = ", ".join(result["evidenceIds"])
    header = [
        f"Subject: Regression status for {fixture_id}",
        "",
        "Hello,",
        "",
        f"Structured result artifact: {result['id']}",
        f"Structured verdict: {result['verdict']}",
        f"Evidence ids: {evidence_refs}",
        "",
    ]

    verdict = result["verdict"]
    if verdict == "passed":
        body = [
            "All tests passed based on the structured regression result.",
            "No failure, incomplete, warning, or waiver markers were found by the verifier.",
        ]
    elif verdict == "failed":
        body = [
            "The regression cannot be reported as successful.",
            "Failure evidence is present in the structured result and should be investigated.",
        ]
    elif verdict == "incomplete":
        body = [
            "The regression cannot be confirmed yet.",
            "Incomplete or running job evidence is present in the structured result.",
        ]
    elif verdict == "warning_or_waiver":
        body = [
            "The regression requires human review before any success update.",
            "Warning or waiver evidence is present in the structured result.",
        ]
    else:
        body = [
            "The regression cannot be confirmed yet and needs human check.",
            "The structured result does not contain enough unambiguous evidence.",
        ]

    footer = [
        "",
        "This draft is grounded only in regression_result.json and the referenced evidence ids.",
        "",
        "Regards,",
        "Agentic Engineering OS",
        "",
    ]
    return "\n".join(header + body + footer)


def result_rule(
    rule_id: str,
    status: str,
    message: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ruleId": rule_id,
        "status": status,
        "message": message,
        "evidenceIds": evidence_ids or [],
    }


def build_verifier_report(
    fixture: dict[str, Any],
    fixture_hash: str,
    evidence: list[dict[str, Any]],
    result: dict[str, Any],
    email_draft: str,
) -> dict[str, Any]:
    fixture_id = fixture["id"]
    evidence_ids = {item["id"] for item in evidence}
    result_evidence_ids = set(result["evidenceIds"])
    verdict = result["verdict"]

    rule_results: list[dict[str, Any]] = []
    blocking_failures: list[dict[str, Any]] = []

    def add_rule(rule: dict[str, Any]) -> None:
        rule_results.append(rule)
        if rule["status"] == "failed":
            blocking_failures.append(
                {
                    "ruleId": rule["ruleId"],
                    "message": rule["message"],
                    "evidenceIds": rule["evidenceIds"],
                }
            )

    required_evidence_fields = {"id", "type", "sourcePath", "excerpt", "observedAt", "classification", "confidence"}
    evidence_schema_ok = all(required_evidence_fields.issubset(item) for item in evidence)
    evidence_enum_ok = all(item.get("classification") in VALID_EVIDENCE_CLASSIFICATIONS for item in evidence)
    add_rule(
        result_rule(
            "schema.validation",
            "passed" if evidence_schema_ok and evidence_enum_ok and verdict in VALID_VERDICTS else "failed",
            "Required artifact fields and enum values are valid."
            if evidence_schema_ok and evidence_enum_ok and verdict in VALID_VERDICTS
            else "A required artifact field or enum value is invalid.",
            list(result_evidence_ids),
        )
    )

    refs_ok = bool(result_evidence_ids) and result_evidence_ids.issubset(evidence_ids)
    add_rule(
        result_rule(
            "evidence.refs",
            "passed" if refs_ok else "failed",
            "Regression result evidence refs point to evidence.json."
            if refs_ok
            else "Regression result has missing or invalid evidence refs.",
            list(result_evidence_ids),
        )
    )

    failure_ids = ids_for(evidence, {"failure_marker"})
    incomplete_ids = ids_for(evidence, {"incomplete_marker"})
    warning_ids = ids_for(evidence, {"warning_marker", "waiver_marker"})
    passed_ids = ids_for(evidence, {"all_passed_marker"})
    ambiguous_ids = ids_for(evidence, {"ambiguous"})
    expected = fixture["expectedVerdict"]

    classification_ok = (
        (failure_ids and verdict in {"failed", "needs_human_check"})
        or (not failure_ids and incomplete_ids and verdict in {"incomplete", "needs_human_check"})
        or (not failure_ids and not incomplete_ids and warning_ids and verdict in {"warning_or_waiver", "needs_human_check"})
        or (not failure_ids and not incomplete_ids and not warning_ids and passed_ids and not ambiguous_ids and verdict == "passed")
        or (not failure_ids and not incomplete_ids and not warning_ids and not passed_ids and verdict in {"unknown", "needs_human_check"})
    )
    add_rule(
        result_rule(
            "classification.consistency",
            "passed" if classification_ok else "failed",
            "Verdict follows marker precedence rules."
            if classification_ok
            else "Verdict does not follow marker precedence rules.",
            list(result_evidence_ids),
        )
    )

    add_rule(
        result_rule(
            "fixture.expected_verdict",
            "passed" if verdict == expected else "failed",
            f"Verdict matches expected fixture verdict {expected}."
            if verdict == expected
            else f"Verdict {verdict} does not match expected fixture verdict {expected}.",
            list(result_evidence_ids),
        )
    )

    email_lower = email_draft.lower()
    email_refs_ok = result["id"].lower() in email_lower and verdict in email_lower
    email_refs_ok = email_refs_ok and all(evidence_id.lower() in email_lower for evidence_id in result["evidenceIds"])
    unsafe_pass_claim = any(phrase in email_lower for phrase in UNSAFE_ALL_PASSED_PHRASES)
    all_passed_allowed = bool(fixture["allowAllPassedEmail"])
    grounding_ok = email_refs_ok and (all_passed_allowed or not unsafe_pass_claim)
    add_rule(
        result_rule(
            "email_draft.uses_structured_facts",
            "passed" if grounding_ok else "failed",
            "Email draft cites the result artifact, verdict, and evidence ids without unsafe new claims."
            if grounding_ok
            else "Email draft is missing grounding refs or contains an unsafe pass claim.",
            list(result_evidence_ids),
        )
    )

    artifact_checks = [
        {
            "artifactId": "evidence.json",
            "artifactType": "evidence",
            "status": "passed" if evidence_schema_ok else "failed",
            "message": "Evidence artifact has required fields." if evidence_schema_ok else "Evidence artifact is missing required fields.",
        },
        {
            "artifactId": result["id"],
            "artifactType": "regression_result",
            "status": "passed" if refs_ok and verdict in VALID_VERDICTS else "failed",
            "message": "Regression result artifact has a valid verdict and evidence refs."
            if refs_ok and verdict in VALID_VERDICTS
            else "Regression result artifact is invalid.",
        },
        {
            "artifactId": "email_draft.md",
            "artifactType": "email_draft",
            "status": "passed" if grounding_ok else "failed",
            "message": "Email draft is grounded in structured facts."
            if grounding_ok
            else "Email draft is not grounded in structured facts.",
        },
    ]

    for check in artifact_checks:
        if check["status"] == "failed":
            blocking_failures.append(
                {
                    "ruleId": f"artifact.{check['artifactId']}",
                    "message": check["message"],
                    "evidenceIds": list(result_evidence_ids),
                }
            )

    status = "failed" if blocking_failures else "passed"
    result["ruleResults"] = rule_results

    return {
        "id": f"verifier_report:{fixture_id}",
        "runId": f"run:{fixture_id}",
        "fixtureId": fixture_id,
        "status": status,
        "generatedAt": GENERATED_AT,
        "fixtureHash": fixture_hash,
        "ruleResults": rule_results,
        "artifactChecks": artifact_checks,
        "blockingFailures": blocking_failures,
        "summary": "Phase 1a fixture gate passed." if status == "passed" else "Phase 1a fixture gate failed.",
    }


def build_events(
    fixture_id: str,
    task_spec: dict[str, Any],
    result: dict[str, Any],
    verifier_report: dict[str, Any],
) -> list[dict[str, Any]]:
    run_id = f"run:{fixture_id}"
    base = {"runId": run_id, "fixtureId": fixture_id, "timestamp": GENERATED_AT}
    return [
        {
            **base,
            "id": f"event:{fixture_id}:001",
            "type": "run.created",
            "status": "completed",
            "inputRef": fixture_id,
        },
        {
            **base,
            "id": f"event:{fixture_id}:002",
            "type": "task_spec.generated",
            "status": "completed",
            "outputRef": task_spec["id"],
        },
        {
            **base,
            "id": f"event:{fixture_id}:003",
            "type": "capability.read_log.completed",
            "status": "completed",
            "outputRef": task_spec["inputLogPath"],
        },
        {
            **base,
            "id": f"event:{fixture_id}:004",
            "type": "capability.extract_regression_result.completed",
            "status": "completed",
            "outputRef": result["id"],
            "evidenceIds": result["evidenceIds"],
        },
        {
            **base,
            "id": f"event:{fixture_id}:005",
            "type": "artifact.write.completed",
            "status": "completed",
            "outputRef": "evidence.json,regression_result.json,email_draft.md",
            "evidenceIds": result["evidenceIds"],
        },
        {
            **base,
            "id": f"event:{fixture_id}:006",
            "type": "verifier.completed",
            "status": verifier_report["status"],
            "outputRef": verifier_report["id"],
            "evidenceIds": result["evidenceIds"],
        },
        {
            **base,
            "id": f"event:{fixture_id}:007",
            "type": "run.completed" if verifier_report["status"] == "passed" else "run.failed",
            "status": "completed" if verifier_report["status"] == "passed" else "failed",
            "outputRef": "verifier_report.json",
            "evidenceIds": result["evidenceIds"],
        },
    ]


def build_run_json(
    fixture: dict[str, Any],
    task_spec: dict[str, Any],
    result: dict[str, Any],
    verifier_report: dict[str, Any],
) -> dict[str, Any]:
    fixture_id = fixture["id"]
    return {
        "id": f"run:{fixture_id}",
        "fixtureId": fixture_id,
        "task": fixture["goal"],
        "status": "completed" if verifier_report["status"] == "passed" else "failed",
        "taskSpec": task_spec,
        "steps": [
            {"id": "step:read_log", "status": "completed", "capability": "read_log"},
            {"id": "step:extract_regression_result", "status": "completed", "capability": "extract_regression_result"},
            {"id": "step:write_artifact", "status": "completed", "capability": "write_artifact"},
            {"id": "step:verify", "status": verifier_report["status"], "capability": "rule_verifier"},
        ],
        "artifacts": [
            {"type": "evidence", "path": "evidence.json"},
            {"type": "regression_result", "path": "regression_result.json", "id": result["id"]},
            {"type": "email_draft", "path": "email_draft.md"},
            {"type": "verifier_report", "path": "verifier_report.json", "id": verifier_report["id"]},
        ],
        "createdAt": GENERATED_AT,
        "completedAt": GENERATED_AT,
    }


def validate_fixture(fixture: dict[str, Any], fixture_dir: Path) -> None:
    required = {"id", "goal", "inputLogFile", "expectedVerdict", "allowAllPassedEmail"}
    missing = required.difference(fixture)
    if missing:
        raise ValueError(f"{fixture_dir}/fixture.json is missing required keys: {sorted(missing)}")
    if fixture["expectedVerdict"] not in VALID_VERDICTS:
        raise ValueError(f"{fixture_dir}/fixture.json has invalid expectedVerdict: {fixture['expectedVerdict']}")
    if fixture["inputLogFile"] != "input.log":
        raise ValueError(f"{fixture_dir}/fixture.json must use inputLogFile='input.log'")


def run_fixture(fixture_case_dir: Path, out_dir: Path) -> dict[str, Any]:
    fixture_json_path = fixture_case_dir / "fixture.json"
    fixture = read_json(fixture_json_path)
    validate_fixture(fixture, fixture_case_dir)

    fixture_id = fixture["id"]
    input_log_path = fixture_case_dir / fixture["inputLogFile"]
    if not input_log_path.is_file():
        raise FileNotFoundError(f"Missing input log for fixture {fixture_id}: {input_log_path}")

    log_text = input_log_path.read_text(encoding="utf-8")
    fixture_hash = sha256_fixture(fixture_json_path, input_log_path)
    task_spec = build_task_spec(fixture, input_log_path)
    evidence = build_evidence(fixture_id, input_log_path, log_text)
    result = extract_regression_result(fixture_id, evidence)
    email_draft = build_email_draft(fixture, result)
    verifier_report = build_verifier_report(fixture, fixture_hash, evidence, result, email_draft)
    run_json = build_run_json(fixture, task_spec, result, verifier_report)
    events = build_events(fixture_id, task_spec, result, verifier_report)

    run_dir = out_dir / fixture_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "run.json", run_json)
    write_jsonl(run_dir / "events.jsonl", events)
    write_json(run_dir / "evidence.json", evidence)
    write_json(run_dir / "regression_result.json", result)
    (run_dir / "email_draft.md").write_text(email_draft, encoding="utf-8")
    write_json(run_dir / "verifier_report.json", verifier_report)
    return verifier_report


def discover_fixture_dirs(fixture_dir: Path) -> list[Path]:
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"Fixture directory does not exist: {fixture_dir}")
    return sorted(path for path in fixture_dir.iterdir() if (path / "fixture.json").is_file())


def run_fixture_dir(fixture_dir: Path, out_dir: Path) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = [run_fixture(case_dir, out_dir) for case_dir in discover_fixture_dirs(fixture_dir)]
    failed = [report for report in reports if report["status"] != "passed"]
    if failed:
        failed_ids = ", ".join(report["fixtureId"] for report in failed)
        raise RuntimeError(f"Fixture verification failed for: {failed_ids}")
    return reports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 1a regression fixture contract gate.")
    parser.add_argument("--fixture-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reports = run_fixture_dir(args.fixture_dir, args.out_dir)
    print(f"Generated {len(reports)} fixture artifact packet(s) in {args.out_dir}")


if __name__ == "__main__":
    main()

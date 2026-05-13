from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from task_spec import validate_regression_task_spec


GENERATED_AT = "2026-05-12T14:39:00Z"
VERIFIER_RUNTIME_SCHEMA_VERSION = "verifier-runtime-v1"
VERIFIER_RULE_CATALOG_SCHEMA_VERSION = "verifier-rule-catalog-v1"
PHASE5_VERIFIER_RULE_CATALOG_ID = "phase5-regression-verifier-rules"
PHASE5_VERIFIER_RUNTIME_ID = "phase5-regression-verifier-runtime"
DEFAULT_RULE_CATALOG_REF = "artifacts/verifier/phase5_verifier_rule_catalog.json"

VERDICTS = {"passed", "failed", "incomplete", "warning_or_waiver", "unknown", "needs_human_check"}
RULE_STATUSES = {"passed", "failed", "not_applicable"}
ARTIFACT_STATUSES = {"passed", "failed"}
ARTIFACT_TYPES = {"regression_result", "email_draft", "evidence"}

VERIFIER_RULE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "schema_validation",
        "kind": "schema",
        "description": "TaskSpec, evidence, and regression result required fields must be present.",
        "blocking": True,
    },
    {
        "id": "evidence_refs",
        "kind": "evidence_link",
        "description": "Non-unknown verdicts must reference evidence ids that exist in evidence.json.",
        "blocking": True,
    },
    {
        "id": "classification_consistency",
        "kind": "classification",
        "description": "Regression verdict must match marker precedence rules.",
        "blocking": True,
    },
    {
        "id": "verdict.failed_precedence",
        "kind": "classification",
        "description": "Failure markers cannot be overridden by a passed verdict.",
        "blocking": True,
    },
    {
        "id": "verdict.incomplete_precedence",
        "kind": "classification",
        "description": "Incomplete markers cannot be converted into a passed verdict.",
        "blocking": True,
    },
    {
        "id": "verdict.warning_guard",
        "kind": "classification",
        "description": "Warnings or waivers require a review-oriented verdict.",
        "blocking": True,
    },
    {
        "id": "verdict.passed_sufficiency",
        "kind": "classification",
        "description": "Passed verdicts require explicit all-pass evidence with no conflicts.",
        "blocking": True,
    },
    {
        "id": "email_draft_uses_structured_facts",
        "kind": "artifact_grounding",
        "description": "Email drafts must cite the structured result, verdict, and evidence ids.",
        "blocking": True,
    },
]

VERIFIER_ARTIFACT_CHECK_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "artifact.evidence_present",
        "artifactType": "evidence",
        "description": "Evidence artifact must contain at least one item.",
        "blocking": True,
    },
    {
        "id": "artifact.regression_result_valid",
        "artifactType": "regression_result",
        "description": "Regression result artifact must contain a supported verdict and evidence ids.",
        "blocking": True,
    },
    {
        "id": "artifact.email_draft_grounded",
        "artifactType": "email_draft",
        "description": "Email draft artifact must be grounded in structured verifier inputs.",
        "blocking": True,
    },
]

REQUIRED_VERIFIER_RULE_IDS = {rule["id"] for rule in VERIFIER_RULE_DEFINITIONS}
REQUIRED_ARTIFACT_CHECK_IDS = {check["id"] for check in VERIFIER_ARTIFACT_CHECK_DEFINITIONS}


def build_verifier_rule_catalog() -> dict[str, Any]:
    return {
        "schemaVersion": VERIFIER_RULE_CATALOG_SCHEMA_VERSION,
        "id": PHASE5_VERIFIER_RULE_CATALOG_ID,
        "phase": "phase5",
        "scope": "regression_readonly_mvp",
        "runtime": {
            "schemaVersion": VERIFIER_RUNTIME_SCHEMA_VERSION,
            "id": PHASE5_VERIFIER_RUNTIME_ID,
            "mode": "same_process_readonly",
            "sideEffect": False,
        },
        "rules": deepcopy(VERIFIER_RULE_DEFINITIONS),
        "artifactChecks": deepcopy(VERIFIER_ARTIFACT_CHECK_DEFINITIONS),
    }


def validate_verifier_rule_catalog(catalog: dict[str, Any]) -> None:
    required = ["schemaVersion", "id", "phase", "scope", "runtime", "rules", "artifactChecks"]
    missing = [field for field in required if field not in catalog]
    if missing:
        raise ValueError(f"Verifier rule catalog is missing required fields: {missing}")
    if catalog["schemaVersion"] != VERIFIER_RULE_CATALOG_SCHEMA_VERSION:
        raise ValueError(f"Verifier rule catalog schemaVersion must be {VERIFIER_RULE_CATALOG_SCHEMA_VERSION}")
    if catalog["id"] != PHASE5_VERIFIER_RULE_CATALOG_ID:
        raise ValueError(f"Verifier rule catalog id must be {PHASE5_VERIFIER_RULE_CATALOG_ID}")
    if catalog["phase"] != "phase5":
        raise ValueError("Verifier rule catalog phase must be phase5")
    if catalog["scope"] != "regression_readonly_mvp":
        raise ValueError("Verifier rule catalog scope must be regression_readonly_mvp")

    runtime = catalog["runtime"]
    if not isinstance(runtime, dict):
        raise ValueError("Verifier rule catalog runtime must be an object")
    if runtime.get("schemaVersion") != VERIFIER_RUNTIME_SCHEMA_VERSION:
        raise ValueError(f"Verifier runtime schemaVersion must be {VERIFIER_RUNTIME_SCHEMA_VERSION}")
    if runtime.get("id") != PHASE5_VERIFIER_RUNTIME_ID:
        raise ValueError(f"Verifier runtime id must be {PHASE5_VERIFIER_RUNTIME_ID}")
    if runtime.get("mode") != "same_process_readonly":
        raise ValueError("Verifier runtime mode must be same_process_readonly")
    if runtime.get("sideEffect") is not False:
        raise ValueError("Verifier runtime must not declare side effects in the read-only MVP")

    rules = catalog["rules"]
    if not isinstance(rules, list) or not rules:
        raise ValueError("Verifier rule catalog rules must be a non-empty list")
    rule_ids = [rule.get("id") for rule in rules if isinstance(rule, dict)]
    if set(rule_ids) != REQUIRED_VERIFIER_RULE_IDS:
        raise ValueError(f"Verifier rule ids must equal {sorted(REQUIRED_VERIFIER_RULE_IDS)}")
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("Verifier rule ids must be unique")
    for rule in rules:
        for field in ["id", "kind", "description", "blocking"]:
            if field not in rule:
                raise ValueError(f"Verifier rule is missing required field: {field}")
        if rule["id"] not in REQUIRED_VERIFIER_RULE_IDS:
            raise ValueError(f"Unknown verifier rule id: {rule['id']}")
        if rule["blocking"] is not True:
            raise ValueError(f"Verifier rule {rule['id']} must be blocking in the MVP")

    artifact_checks = catalog["artifactChecks"]
    if not isinstance(artifact_checks, list) or not artifact_checks:
        raise ValueError("Verifier rule catalog artifactChecks must be a non-empty list")
    check_ids = [check.get("id") for check in artifact_checks if isinstance(check, dict)]
    if set(check_ids) != REQUIRED_ARTIFACT_CHECK_IDS:
        raise ValueError(f"Verifier artifact check ids must equal {sorted(REQUIRED_ARTIFACT_CHECK_IDS)}")
    if len(check_ids) != len(set(check_ids)):
        raise ValueError("Verifier artifact check ids must be unique")
    for check in artifact_checks:
        for field in ["id", "artifactType", "description", "blocking"]:
            if field not in check:
                raise ValueError(f"Verifier artifact check is missing required field: {field}")
        if check["artifactType"] not in ARTIFACT_TYPES:
            raise ValueError(f"Verifier artifact check has invalid artifactType: {check['artifactType']}")
        if check["blocking"] is not True:
            raise ValueError(f"Verifier artifact check {check['id']} must be blocking in the MVP")


def verifier_runtime_ref(rule_catalog_ref: str = DEFAULT_RULE_CATALOG_REF) -> dict[str, Any]:
    return {
        "schemaVersion": VERIFIER_RUNTIME_SCHEMA_VERSION,
        "id": PHASE5_VERIFIER_RUNTIME_ID,
        "ruleCatalogRef": rule_catalog_ref,
        "mode": "same_process_readonly",
        "sideEffect": False,
    }


def validate_verifier_runtime_ref(runtime: dict[str, Any]) -> None:
    required = ["schemaVersion", "id", "ruleCatalogRef", "mode", "sideEffect"]
    missing = [field for field in required if field not in runtime]
    if missing:
        raise ValueError(f"Verifier runtime ref is missing required fields: {missing}")
    if runtime["schemaVersion"] != VERIFIER_RUNTIME_SCHEMA_VERSION:
        raise ValueError(f"Verifier runtime ref schemaVersion must be {VERIFIER_RUNTIME_SCHEMA_VERSION}")
    if runtime["id"] != PHASE5_VERIFIER_RUNTIME_ID:
        raise ValueError(f"Verifier runtime ref id must be {PHASE5_VERIFIER_RUNTIME_ID}")
    if runtime["ruleCatalogRef"] != DEFAULT_RULE_CATALOG_REF:
        raise ValueError(f"Verifier runtime ref ruleCatalogRef must be {DEFAULT_RULE_CATALOG_REF}")
    if runtime["mode"] != "same_process_readonly":
        raise ValueError("Verifier runtime ref mode must be same_process_readonly")
    if runtime["sideEffect"] is not False:
        raise ValueError("Verifier runtime ref must not declare side effects")


def rule_result(rule_id: str, status: str, message: str, evidence_ids: list[str]) -> dict[str, Any]:
    if rule_id not in REQUIRED_VERIFIER_RULE_IDS:
        raise ValueError(f"Unknown verifier rule id: {rule_id}")
    if status not in RULE_STATUSES:
        raise ValueError(f"Verifier rule status must be one of {sorted(RULE_STATUSES)}")
    return {
        "ruleId": rule_id,
        "status": status,
        "message": message,
        "evidenceIds": evidence_ids,
    }


def artifact_check(check_id: str, artifact_id: str, artifact_type: str, status: str, message: str) -> dict[str, Any]:
    if check_id not in REQUIRED_ARTIFACT_CHECK_IDS:
        raise ValueError(f"Unknown verifier artifact check id: {check_id}")
    if artifact_type not in ARTIFACT_TYPES:
        raise ValueError(f"Verifier artifact type must be one of {sorted(ARTIFACT_TYPES)}")
    if status not in ARTIFACT_STATUSES:
        raise ValueError(f"Verifier artifact status must be one of {sorted(ARTIFACT_STATUSES)}")
    return {
        "checkId": check_id,
        "artifactId": artifact_id,
        "artifactType": artifact_type,
        "status": status,
        "message": message,
    }


def verdict_matches_classes(verdict: str, classes: set[str]) -> bool:
    if "failure_marker" in classes:
        return verdict in {"failed", "needs_human_check"}
    if "incomplete_marker" in classes:
        return verdict in {"incomplete", "unknown", "needs_human_check"}
    if {"warning_marker", "waiver_marker"} & classes:
        return verdict in {"warning_or_waiver", "needs_human_check"}
    if "all_passed_marker" in classes and "ambiguous" not in classes:
        return verdict == "passed"
    return verdict in {"unknown", "needs_human_check"}


def build_rule_results(task_spec: dict[str, Any], evidence: list[dict[str, Any]], verdict: str, verdict_evidence_ids: list[str]) -> list[dict[str, Any]]:
    ids = {item["id"] for item in evidence}
    classes = {item["classification"] for item in evidence}
    task_spec_error = ""
    try:
        validate_regression_task_spec(task_spec)
    except ValueError as exc:
        task_spec_error = str(exc)
    required_evidence_fields = {
        "id",
        "type",
        "sourcePath",
        "sourceRef",
        "lineRange",
        "excerpt",
        "excerptHash",
        "observedAt",
        "classification",
        "confidence",
    }
    bad_evidence = [item.get("id", "<missing-id>") for item in evidence if not required_evidence_fields.issubset(item)]
    referenced = [evidence_id for evidence_id in verdict_evidence_ids if evidence_id in ids]
    evidence_status = "passed" if verdict == "unknown" or bool(referenced) else "failed"

    return [
        rule_result(
            "schema_validation",
            "passed" if not task_spec_error and not bad_evidence and verdict in VERDICTS else "failed",
            "TaskSpec, evidence, and regression result required fields are present."
            if not task_spec_error and not bad_evidence and verdict in VERDICTS
            else f"TaskSpec error={task_spec_error}; bad evidence={bad_evidence}; verdict={verdict}",
            referenced,
        ),
        rule_result(
            "evidence_refs",
            evidence_status,
            "Verdict evidence ids resolve to evidence.json items."
            if evidence_status == "passed"
            else "Non-unknown verdict must reference at least one evidence id.",
            verdict_evidence_ids,
        ),
        rule_result(
            "classification_consistency",
            "passed" if verdict_matches_classes(verdict, classes) else "failed",
            "Verdict is consistent with marker precedence rules."
            if verdict_matches_classes(verdict, classes)
            else f"Verdict {verdict} conflicts with classifications {sorted(classes)}.",
            verdict_evidence_ids,
        ),
        rule_result(
            "verdict.failed_precedence",
            "passed" if "failure_marker" not in classes or verdict in {"failed", "needs_human_check"} else "failed",
            "Failure markers are not overridden by a passed verdict.",
            [item["id"] for item in evidence if item["classification"] == "failure_marker"],
        ),
        rule_result(
            "verdict.incomplete_precedence",
            "passed" if "incomplete_marker" not in classes or verdict in {"incomplete", "unknown", "needs_human_check"} else "failed",
            "Incomplete markers are not converted into a passed verdict.",
            [item["id"] for item in evidence if item["classification"] == "incomplete_marker"],
        ),
        rule_result(
            "verdict.warning_guard",
            "passed" if not ({"warning_marker", "waiver_marker"} & classes) or verdict in {"warning_or_waiver", "needs_human_check"} else "failed",
            "Warning or waiver markers require review-oriented verdicts.",
            [item["id"] for item in evidence if item["classification"] in {"warning_marker", "waiver_marker"}],
        ),
        rule_result(
            "verdict.passed_sufficiency",
            "passed" if verdict != "passed" or classes == {"all_passed_marker"} else "failed",
            "Passed verdict is only allowed for explicit all-pass evidence with no conflicts.",
            verdict_evidence_ids,
        ),
    ]


def email_grounding_status(allow_all_passed_email: bool, email: str, result: dict[str, Any]) -> tuple[str, str]:
    lower_email = email.lower()
    references_result = result["id"].lower() in lower_email and f"`{result['verdict']}`" in email
    references_evidence = all(evidence_id.lower() in lower_email for evidence_id in result["evidenceIds"])
    forbidden_pass_style = any(
        phrase in lower_email
        for phrase in ["all passed", "clean pass", "passed successfully", "no failures"]
    )
    if not references_result or not references_evidence:
        return "failed", "Email draft must reference the structured result id, verdict, and evidence ids."
    if not allow_all_passed_email and forbidden_pass_style:
        return "failed", "Negative or uncertain fixtures must not generate a pass-style email."
    return "passed", "Email draft is grounded in regression_result.json and evidence ids."


def run_verifier_runtime(
    fixture_id: str,
    allow_all_passed_email: bool,
    run_id: str,
    fixture_hash: str,
    task_spec: dict[str, Any],
    evidence: list[dict[str, Any]],
    result: dict[str, Any],
    email: str,
) -> dict[str, Any]:
    verdict = result["verdict"]
    verdict_evidence_ids = result["evidenceIds"]
    rule_results = build_rule_results(task_spec, evidence, verdict, verdict_evidence_ids)
    email_status, email_message = email_grounding_status(allow_all_passed_email, email, result)
    rule_results.append(
        rule_result("email_draft_uses_structured_facts", email_status, email_message, verdict_evidence_ids)
    )
    result["ruleResults"] = rule_results

    artifact_checks = [
        artifact_check(
            "artifact.evidence_present",
            "evidence.json",
            "evidence",
            "passed" if evidence else "failed",
            "Evidence artifact contains at least one item.",
        ),
        artifact_check(
            "artifact.regression_result_valid",
            result["id"],
            "regression_result",
            "passed" if verdict in VERDICTS and bool(result["evidenceIds"]) else "failed",
            "Regression result has a valid verdict and evidence ids.",
        ),
        artifact_check(
            "artifact.email_draft_grounded",
            "email_draft.md",
            "email_draft",
            email_status,
            email_message,
        ),
    ]
    blocking_failures = [
        {"ruleId": item["ruleId"], "message": item["message"], "evidenceIds": item["evidenceIds"]}
        for item in rule_results
        if item["status"] == "failed"
    ] + [
        {"ruleId": item["checkId"], "message": item["message"], "evidenceIds": verdict_evidence_ids}
        for item in artifact_checks
        if item["status"] == "failed"
    ]
    report_status = "passed" if not blocking_failures else "failed"
    return {
        "schemaVersion": "verifier-report-v1",
        "id": f"verifier-report-{fixture_id}",
        "runId": run_id,
        "fixtureId": fixture_id,
        "status": report_status,
        "generatedAt": GENERATED_AT,
        "fixtureHash": fixture_hash,
        "verifierRuntime": verifier_runtime_ref(),
        "ruleResults": rule_results,
        "artifactChecks": artifact_checks,
        "blockingFailures": blocking_failures,
        "summary": f"Fixture {fixture_id} produced verdict {verdict}; verifier status {report_status}.",
    }


def verify_artifacts(
    fixture: Any,
    run_id: str,
    fixture_hash: str,
    task_spec: dict[str, Any],
    evidence: list[dict[str, Any]],
    result: dict[str, Any],
    email: str,
) -> dict[str, Any]:
    return run_verifier_runtime(
        fixture_id=fixture.id,
        allow_all_passed_email=fixture.allow_all_passed_email,
        run_id=run_id,
        fixture_hash=fixture_hash,
        task_spec=task_spec,
        evidence=evidence,
        result=result,
        email=email,
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_task_spec_payload(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if "taskSpec" in payload and isinstance(payload["taskSpec"], dict):
        return payload["taskSpec"]
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="verifier-runtime")
    parser.add_argument("--catalog-out", type=Path)
    parser.add_argument("--task-spec", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--email", type=Path)
    parser.add_argument("--fixture-id")
    parser.add_argument("--run-id")
    parser.add_argument("--fixture-hash")
    parser.add_argument("--allow-all-passed-email", action="store_true")
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    catalog = build_verifier_rule_catalog()
    validate_verifier_rule_catalog(catalog)
    if args.catalog_out:
        write_json(args.catalog_out, catalog)
        print(f"Wrote verifier rule catalog {catalog['id']} to {args.catalog_out}.")

    verify_args = [args.task_spec, args.evidence, args.result, args.email, args.fixture_id, args.run_id, args.fixture_hash]
    if any(value is not None for value in verify_args):
        if not all(value is not None for value in verify_args):
            raise SystemExit("Verifier replay requires --task-spec, --evidence, --result, --email, --fixture-id, --run-id, and --fixture-hash")
        result = load_json(args.result)
        report = run_verifier_runtime(
            fixture_id=args.fixture_id,
            allow_all_passed_email=args.allow_all_passed_email,
            run_id=args.run_id,
            fixture_hash=args.fixture_hash,
            task_spec=load_task_spec_payload(args.task_spec),
            evidence=load_json(args.evidence)["items"],
            result=result,
            email=args.email.read_text(encoding="utf-8"),
        )
        if args.out:
            write_json(args.out, report)
            print(f"Wrote verifier report {report['id']} to {args.out}.")
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

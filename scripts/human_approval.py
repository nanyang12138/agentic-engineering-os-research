from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ide_adapter import APPROVAL_HANDOFF_ARTIFACT_PATH, CONTRACT_ARTIFACT_PATH, validate_approval_handoff_manifest
from multi_agent_delivery import DELIVERY_REPORT_ARTIFACT_PATH, validate_delivery_report


HUMAN_APPROVAL_DECISION_SCHEMA_VERSION = "human-approval-decision-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"
DECISION_ID = "phase9-human-approval-decision-fixture-all_passed"
DECISION_ARTIFACT_PATH = "artifacts/approval/phase9_human_approval_decision_fixture.json"

DEFAULT_RUN_PATH = "artifacts/runs/all_passed/run.json"
DEFAULT_VERIFIER_REPORT_PATH = "artifacts/runs/all_passed/verifier_report.json"
DEFAULT_APPROVAL_POINT = "send_email_requires_human_approval"


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_fields(label: str, payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing}")


def _validate_relative_posix_path(path: str) -> None:
    if Path(path).is_absolute() or "\\" in path or path.startswith("../") or "/../" in path:
        raise ValueError(f"HumanApprovalDecision paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"HumanApprovalDecision source artifact does not exist: {relative_path}")
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _expected_source_paths() -> dict[str, str]:
    return {
        "ide_adapter_contract": CONTRACT_ARTIFACT_PATH,
        "delivery_report": DELIVERY_REPORT_ARTIFACT_PATH,
        "ide_approval_handoff": APPROVAL_HANDOFF_ARTIFACT_PATH,
        "run": DEFAULT_RUN_PATH,
        "verifier_report": DEFAULT_VERIFIER_REPORT_PATH,
    }


def _matching_delivery_request(handoff: dict[str, Any], approval_point: str) -> dict[str, Any]:
    matches = [
        request
        for request in handoff.get("handoffRequests", [])
        if isinstance(request, dict) and request.get("approvalPoint") == approval_point
    ]
    if len(matches) != 1:
        raise ValueError("HumanApprovalDecisionV1 must bind exactly one IDE approval handoff request")
    return matches[0]


def build_human_approval_decision(root: Path) -> dict[str, Any]:
    delivery_report = _load_json(root / DELIVERY_REPORT_ARTIFACT_PATH)
    validate_delivery_report(delivery_report, root)
    ide_adapter_contract = _load_json(root / CONTRACT_ARTIFACT_PATH)
    ide_approval_handoff = _load_json(root / APPROVAL_HANDOFF_ARTIFACT_PATH)
    validate_approval_handoff_manifest(ide_approval_handoff, ide_adapter_contract, root)
    run = _load_json(root / DEFAULT_RUN_PATH)
    verifier_report = _load_json(root / DEFAULT_VERIFIER_REPORT_PATH)

    approval_point = delivery_report["approvalBinding"]["approvalPoint"]
    request = _matching_delivery_request(ide_approval_handoff, approval_point)
    permission_policy = run["runControl"]["permissionPolicy"]
    delivery_blocker_ids = [blocker["id"] for blocker in delivery_report["blockers"]]

    return {
        "schemaVersion": HUMAN_APPROVAL_DECISION_SCHEMA_VERSION,
        "id": DECISION_ID,
        "generatedAt": GENERATED_AT,
        "phase": "post_mvp",
        "scope": "human_approval_decision_fixture",
        "mode": "static_fixture_only",
        "sourceArtifacts": [
            _artifact_source(role, path, root)
            for role, path in _expected_source_paths().items()
        ],
        "approvalBinding": {
            "approvalPoint": approval_point,
            "handoffRequestId": request["id"],
            "handoffCapabilityRef": request["capabilityRef"],
            "taskSpecRef": delivery_report["deliveryRefs"]["taskSpecRef"],
            "deliveryReportRef": DELIVERY_REPORT_ARTIFACT_PATH,
            "permissionPolicyRef": permission_policy["id"],
            "permissionPolicySchemaVersion": permission_policy["schemaVersion"],
        },
        "decision": {
            "decisionId": "human-decision-all_passed-send-email-rejected",
            "decision": "rejected",
            "humanDecisionRecorded": True,
            "approvalGranted": False,
            "approvalDecisionSynthesized": False,
            "decidedBy": "static-human-approval-fixture",
            "decidedAt": GENERATED_AT,
            "reasonCode": "mvp_external_delivery_not_allowed",
            "rationale": "The verified draft can be reviewed, but this fixture withholds approval for external email delivery.",
        },
        "policyEffects": {
            "humanApprovalSatisfiedAfterDecision": False,
            "readyForExternalDeliveryAfterDecision": False,
            "sendEmailAllowed": False,
            "externalDeliveryAllowed": False,
            "externalSideEffectsAllowed": False,
            "prCreationAllowed": False,
            "workspaceMutationAllowed": False,
            "taskVerdictOverrideAllowed": False,
            "deliveryStateAfterDecision": "blocked_by_human_rejection_and_mvp_policy",
        },
        "verifierBinding": {
            "verifierReportRef": DEFAULT_VERIFIER_REPORT_PATH,
            "verifierStatus": verifier_report["status"],
            "taskVerdictOwner": "verifier-runtime-v1",
            "taskVerdictOverrideAllowed": False,
        },
        "deliveryReportBlockers": delivery_blocker_ids,
        "postDecisionBlockers": [
            "human_approval_not_granted",
            "external_delivery_disabled_by_mvp_policy",
        ],
        "invariants": [
            "HumanApprovalDecisionV1 records a decision artifact; it does not send email, create PRs, or mutate a workspace.",
            "A human decision cannot override VerifierRuntimeV1 task verdicts or source evidence.",
            "This static fixture withholds external delivery approval, so MVP no-side-effect policy remains intact.",
        ],
    }


def _validate_source_artifacts(source_artifacts: list[Any], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("HumanApprovalDecisionV1 sourceArtifacts must be a non-empty list")
    expected_paths = _expected_source_paths()
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("HumanApprovalDecisionV1 sourceArtifacts must be objects")
        _require_fields("HumanApprovalDecisionV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected HumanApprovalDecisionV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"HumanApprovalDecisionV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"HumanApprovalDecisionV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"HumanApprovalDecisionV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"HumanApprovalDecisionV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def validate_human_approval_decision(decision_artifact: dict[str, Any], root: Path) -> None:
    _require_fields(
        "HumanApprovalDecisionV1",
        decision_artifact,
        [
            "schemaVersion",
            "id",
            "generatedAt",
            "phase",
            "scope",
            "mode",
            "sourceArtifacts",
            "approvalBinding",
            "decision",
            "policyEffects",
            "verifierBinding",
            "deliveryReportBlockers",
            "postDecisionBlockers",
            "invariants",
        ],
    )
    if decision_artifact["schemaVersion"] != HUMAN_APPROVAL_DECISION_SCHEMA_VERSION:
        raise ValueError(f"HumanApprovalDecisionV1 schemaVersion must be {HUMAN_APPROVAL_DECISION_SCHEMA_VERSION}")
    if decision_artifact["id"] != DECISION_ID:
        raise ValueError(f"HumanApprovalDecisionV1 id must be {DECISION_ID}")
    if decision_artifact["phase"] != "post_mvp":
        raise ValueError("HumanApprovalDecisionV1 phase must be post_mvp")
    if decision_artifact["mode"] != "static_fixture_only":
        raise ValueError("HumanApprovalDecisionV1 mode must be static_fixture_only")

    sources = _validate_source_artifacts(decision_artifact["sourceArtifacts"], root)
    delivery_report = _load_json(root / sources["delivery_report"]["path"])
    validate_delivery_report(delivery_report, root)
    ide_adapter_contract = _load_json(root / sources["ide_adapter_contract"]["path"])
    ide_approval_handoff = _load_json(root / sources["ide_approval_handoff"]["path"])
    validate_approval_handoff_manifest(ide_approval_handoff, ide_adapter_contract, root)
    run = _load_json(root / sources["run"]["path"])
    verifier_report = _load_json(root / sources["verifier_report"]["path"])

    approval = decision_artifact["approvalBinding"]
    _require_fields(
        "HumanApprovalDecisionV1 approvalBinding",
        approval,
        [
            "approvalPoint",
            "handoffRequestId",
            "handoffCapabilityRef",
            "taskSpecRef",
            "deliveryReportRef",
            "permissionPolicyRef",
            "permissionPolicySchemaVersion",
        ],
    )
    if approval["approvalPoint"] != DEFAULT_APPROVAL_POINT:
        raise ValueError("HumanApprovalDecisionV1 approvalPoint must be send_email_requires_human_approval")
    if approval["approvalPoint"] != delivery_report["approvalBinding"]["approvalPoint"]:
        raise ValueError("HumanApprovalDecisionV1 approvalPoint must match DeliveryReportV1")
    request = _matching_delivery_request(ide_approval_handoff, approval["approvalPoint"])
    if approval["handoffRequestId"] != request["id"]:
        raise ValueError("HumanApprovalDecisionV1 handoffRequestId must match IDEApprovalHandoffManifestV1")
    if approval["handoffCapabilityRef"] != request["capabilityRef"]:
        raise ValueError("HumanApprovalDecisionV1 handoffCapabilityRef must match IDEApprovalHandoffManifestV1")
    if request["executionAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 IDE approval request must remain execution blocked")
    if request["approvalDecisionSynthesized"] is not False:
        raise ValueError("HumanApprovalDecisionV1 handoff must not synthesize approval decisions")
    if approval["taskSpecRef"] != delivery_report["deliveryRefs"]["taskSpecRef"]:
        raise ValueError("HumanApprovalDecisionV1 taskSpecRef must match DeliveryReportV1")
    permission_policy = run["runControl"]["permissionPolicy"]
    if approval["permissionPolicyRef"] != permission_policy["id"]:
        raise ValueError("HumanApprovalDecisionV1 permissionPolicyRef must match RunControlV1")
    if approval["permissionPolicySchemaVersion"] != "permission-policy-v1":
        raise ValueError("HumanApprovalDecisionV1 must bind permission-policy-v1")
    if permission_policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 permission policy must disallow external side effects")

    decision = decision_artifact["decision"]
    _require_fields(
        "HumanApprovalDecisionV1 decision",
        decision,
        [
            "decisionId",
            "decision",
            "humanDecisionRecorded",
            "approvalGranted",
            "approvalDecisionSynthesized",
            "decidedBy",
            "decidedAt",
            "reasonCode",
            "rationale",
        ],
    )
    if decision["humanDecisionRecorded"] is not True:
        raise ValueError("HumanApprovalDecisionV1 static fixture must record the human gate decision state")
    if decision["approvalDecisionSynthesized"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not synthesize approval decisions")
    if decision["approvalGranted"] is not False:
        raise ValueError("HumanApprovalDecisionV1 static fixture must not grant external delivery approval")
    if decision["decision"] != "rejected":
        raise ValueError("HumanApprovalDecisionV1 static fixture decision must be rejected")

    effects = decision_artifact["policyEffects"]
    _require_fields(
        "HumanApprovalDecisionV1 policyEffects",
        effects,
        [
            "humanApprovalSatisfiedAfterDecision",
            "readyForExternalDeliveryAfterDecision",
            "sendEmailAllowed",
            "externalDeliveryAllowed",
            "externalSideEffectsAllowed",
            "prCreationAllowed",
            "workspaceMutationAllowed",
            "taskVerdictOverrideAllowed",
            "deliveryStateAfterDecision",
        ],
    )
    if effects["humanApprovalSatisfiedAfterDecision"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not mark human approval satisfied after rejection")
    if effects["readyForExternalDeliveryAfterDecision"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not allow external delivery")
    if effects["sendEmailAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not allow sending email")
    if effects["externalDeliveryAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not allow external delivery")
    if effects["externalSideEffectsAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not allow external side effects")
    if effects["prCreationAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not allow PR creation")
    if effects["workspaceMutationAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not allow workspace mutation")
    if effects["taskVerdictOverrideAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not override verifier verdicts")

    verifier = decision_artifact["verifierBinding"]
    _require_fields(
        "HumanApprovalDecisionV1 verifierBinding",
        verifier,
        ["verifierReportRef", "verifierStatus", "taskVerdictOwner", "taskVerdictOverrideAllowed"],
    )
    if verifier["verifierReportRef"] != DEFAULT_VERIFIER_REPORT_PATH:
        raise ValueError("HumanApprovalDecisionV1 verifierReportRef mismatch")
    if verifier["verifierStatus"] != verifier_report["status"]:
        raise ValueError("HumanApprovalDecisionV1 verifierStatus must match verifier_report")
    if verifier["taskVerdictOwner"] != "verifier-runtime-v1":
        raise ValueError("HumanApprovalDecisionV1 task verdict owner must remain verifier-runtime-v1")
    if verifier["taskVerdictOverrideAllowed"] is not False:
        raise ValueError("HumanApprovalDecisionV1 must not override verifier verdicts")

    delivery_blockers = set(decision_artifact["deliveryReportBlockers"])
    for required in ["human_approval_missing", "external_delivery_disabled_by_mvp_policy"]:
        if required not in delivery_blockers:
            raise ValueError("HumanApprovalDecisionV1 must preserve DeliveryReportV1 blockers")
    report_blockers = {blocker["id"] for blocker in delivery_report["blockers"]}
    if not delivery_blockers.issubset(report_blockers):
        raise ValueError("HumanApprovalDecisionV1 deliveryReportBlockers must come from DeliveryReportV1")
    post_decision_blockers = set(decision_artifact["postDecisionBlockers"])
    for required in ["human_approval_not_granted", "external_delivery_disabled_by_mvp_policy"]:
        if required not in post_decision_blockers:
            raise ValueError("HumanApprovalDecisionV1 postDecisionBlockers must keep delivery blocked")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or validate the HumanApprovalDecisionV1 fixture.")
    parser.add_argument("--decision-out", type=Path)
    parser.add_argument("--validate-decision", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    if args.decision_out:
        decision = build_human_approval_decision(root)
        validate_human_approval_decision(decision, root)
        _write_json(args.decision_out, decision)
        print(f"Wrote HumanApprovalDecisionV1 artifact to {args.decision_out}.")

    if args.validate_decision:
        decision = _load_json(args.validate_decision)
        validate_human_approval_decision(decision, root)
        print(f"Validated HumanApprovalDecisionV1 artifact {args.validate_decision}.")

    if not any([args.decision_out, args.validate_decision]):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

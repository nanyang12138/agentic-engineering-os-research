from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


MULTI_AGENT_DELIVERY_MANIFEST_SCHEMA_VERSION = "multi-agent-delivery-manifest-v1"
AGENT_HANDOFF_SCHEMA_VERSION = "agent-handoff-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"

MANIFEST_ID = "phase9-static-multi-agent-delivery-all_passed"
MANIFEST_ARTIFACT_PATH = "artifacts/delivery/phase9_multi_agent_delivery_manifest.json"

DEFAULT_RUN_PATH = "artifacts/runs/all_passed/run.json"
DEFAULT_CONTEXT_PACK_PATH = "artifacts/context/all_passed/context_pack.json"
DEFAULT_EVIDENCE_PATH = "artifacts/runs/all_passed/evidence.json"
DEFAULT_REGRESSION_RESULT_PATH = "artifacts/runs/all_passed/regression_result.json"
DEFAULT_VERIFIER_REPORT_PATH = "artifacts/runs/all_passed/verifier_report.json"
DEFAULT_EMAIL_DRAFT_PATH = "artifacts/runs/all_passed/email_draft.md"
DEFAULT_IDE_APPROVAL_HANDOFF_PATH = "artifacts/ide_adapter/phase8_ide_approval_handoff_manifest.json"

AGENT_SEQUENCE = [
    "planner_agent",
    "context_agent",
    "executor_agent",
    "reviewer_agent",
    "reporter_agent",
]
HANDOFF_SEQUENCE = [
    ("planner_to_context", "planner_agent", "context_agent"),
    ("context_to_executor", "context_agent", "executor_agent"),
    ("executor_to_reviewer", "executor_agent", "reviewer_agent"),
    ("reviewer_to_reporter", "reviewer_agent", "reporter_agent"),
    ("reporter_to_delivery_gate", "reporter_agent", "delivery_gate"),
]


def _stable_file_hash(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _stable_text_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


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
        raise ValueError(f"MultiAgentDelivery paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, path: Path, root: Path) -> dict[str, Any]:
    relative_path = path.resolve().relative_to(root.resolve()).as_posix()
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _artifact_ref(path: Path, root: Path, fragment: str | None = None) -> str:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    if fragment:
        return f"{relative}{fragment}"
    return relative


def _validate_source_artifacts(source_artifacts: list[Any], expected_paths: dict[str, str], root: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("MultiAgentDeliveryManifestV1 sourceArtifacts must be a non-empty list")
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("MultiAgentDeliveryManifestV1 sourceArtifacts must be objects")
        _require_fields("MultiAgentDeliveryManifestV1 source artifact", source, ["role", "path", "contentHash"])
        role = source["role"]
        path = source["path"]
        _validate_relative_posix_path(path)
        if role not in expected_paths:
            raise ValueError(f"Unexpected MultiAgentDeliveryManifestV1 source role: {role}")
        if path != expected_paths[role]:
            raise ValueError(f"MultiAgentDeliveryManifestV1 source role {role} must point to {expected_paths[role]}")
        source_path = root / path
        if not source_path.is_file():
            raise ValueError(f"MultiAgentDeliveryManifestV1 source artifact does not exist: {path}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"MultiAgentDeliveryManifestV1 source hash mismatch for {path}")
        sources_by_role[role] = source
    if set(sources_by_role) != set(expected_paths):
        raise ValueError(f"MultiAgentDeliveryManifestV1 source roles must equal {sorted(expected_paths)}")
    return sources_by_role


def _build_agent_roles(
    run_path: Path,
    context_pack_path: Path,
    evidence_path: Path,
    regression_result_path: Path,
    verifier_report_path: Path,
    email_draft_path: Path,
    root: Path,
) -> list[dict[str, Any]]:
    task_spec_ref = _artifact_ref(run_path, root, "#taskSpec")
    return [
        {
            "name": "planner_agent",
            "role": "planner",
            "owns": ["task_decomposition", "step_strategy"],
            "inputRefs": [task_spec_ref],
            "outputRefs": [f"{MANIFEST_ARTIFACT_PATH}#handoffs/planner_to_context"],
            "allowedActions": ["read_task_spec", "propose_handoff_plan"],
            "forbiddenActions": ["call_tools", "emit_task_verdict", "send_email", "mutate_workspace"],
        },
        {
            "name": "context_agent",
            "role": "context",
            "owns": ["context_selection"],
            "inputRefs": [task_spec_ref],
            "outputRefs": [_artifact_ref(context_pack_path, root)],
            "allowedActions": ["read_context_pack", "select_source_bound_context"],
            "forbiddenActions": ["call_write_tools", "emit_task_verdict", "send_email", "mutate_workspace"],
        },
        {
            "name": "executor_agent",
            "role": "executor",
            "owns": ["capability_invocation_record"],
            "inputRefs": [task_spec_ref, _artifact_ref(context_pack_path, root)],
            "outputRefs": [
                _artifact_ref(run_path, root),
                _artifact_ref(evidence_path, root),
                _artifact_ref(regression_result_path, root),
                _artifact_ref(email_draft_path, root),
            ],
            "allowedActions": ["read_log", "extract_regression_result", "write_local_artifact"],
            "forbiddenActions": ["run_terminal", "call_ide", "call_cua", "send_email", "mutate_workspace"],
        },
        {
            "name": "reviewer_agent",
            "role": "reviewer",
            "owns": ["risk_review", "verifier_result_interpretation"],
            "inputRefs": [
                _artifact_ref(evidence_path, root),
                _artifact_ref(regression_result_path, root),
                _artifact_ref(verifier_report_path, root),
            ],
            "outputRefs": [f"{MANIFEST_ARTIFACT_PATH}#deliveryReview"],
            "allowedActions": ["read_verifier_report", "read_evidence", "flag_risks"],
            "forbiddenActions": ["override_verifier", "emit_unverified_task_verdict", "send_email", "mutate_workspace"],
        },
        {
            "name": "reporter_agent",
            "role": "reporter",
            "owns": ["delivery_summary", "artifact_packaging"],
            "inputRefs": [
                _artifact_ref(verifier_report_path, root),
                _artifact_ref(email_draft_path, root),
            ],
            "outputRefs": [f"{MANIFEST_ARTIFACT_PATH}#deliveryArtifact"],
            "allowedActions": ["summarize_verified_artifacts", "prepare_delivery_draft"],
            "forbiddenActions": ["synthesize_new_facts", "send_email", "mark_human_approval_complete", "mutate_workspace"],
        },
    ]


def _build_handoffs(
    run_path: Path,
    context_pack_path: Path,
    evidence_path: Path,
    regression_result_path: Path,
    verifier_report_path: Path,
    email_draft_path: Path,
    root: Path,
) -> list[dict[str, Any]]:
    refs = {
        "task_spec": _artifact_ref(run_path, root, "#taskSpec"),
        "context_pack": _artifact_ref(context_pack_path, root),
        "run": _artifact_ref(run_path, root),
        "evidence": _artifact_ref(evidence_path, root),
        "regression_result": _artifact_ref(regression_result_path, root),
        "verifier_report": _artifact_ref(verifier_report_path, root),
        "email_draft": _artifact_ref(email_draft_path, root),
    }
    handoff_payloads = {
        "planner_to_context": {
            "inputRefs": [refs["task_spec"]],
            "outputRefs": [refs["context_pack"]],
            "evidenceRefs": [],
            "verifierRefs": [],
            "deliveryRefs": [],
            "policyDecision": "contract_only_plan_ready",
        },
        "context_to_executor": {
            "inputRefs": [refs["task_spec"], refs["context_pack"]],
            "outputRefs": [refs["run"], refs["evidence"], refs["regression_result"], refs["email_draft"]],
            "evidenceRefs": [refs["evidence"]],
            "verifierRefs": [],
            "deliveryRefs": [refs["email_draft"]],
            "policyDecision": "readonly_execution_artifacts_ready",
        },
        "executor_to_reviewer": {
            "inputRefs": [refs["run"], refs["evidence"], refs["regression_result"], refs["email_draft"]],
            "outputRefs": [refs["verifier_report"]],
            "evidenceRefs": [refs["evidence"]],
            "verifierRefs": [refs["verifier_report"]],
            "deliveryRefs": [refs["email_draft"]],
            "policyDecision": "requires_verifier_review",
        },
        "reviewer_to_reporter": {
            "inputRefs": [refs["evidence"], refs["regression_result"], refs["verifier_report"]],
            "outputRefs": [f"{MANIFEST_ARTIFACT_PATH}#deliveryReview"],
            "evidenceRefs": [refs["evidence"]],
            "verifierRefs": [refs["verifier_report"]],
            "deliveryRefs": [refs["email_draft"]],
            "policyDecision": "verified_artifacts_can_be_reported_as_draft",
        },
        "reporter_to_delivery_gate": {
            "inputRefs": [refs["verifier_report"], refs["email_draft"]],
            "outputRefs": [f"{MANIFEST_ARTIFACT_PATH}#deliveryArtifact"],
            "evidenceRefs": [refs["evidence"]],
            "verifierRefs": [refs["verifier_report"]],
            "deliveryRefs": [refs["email_draft"]],
            "policyDecision": "blocked_until_human_approval",
        },
    }
    handoffs = []
    for handoff_id, from_agent, to_agent in HANDOFF_SEQUENCE:
        payload = handoff_payloads[handoff_id]
        handoffs.append(
            {
                "schemaVersion": AGENT_HANDOFF_SCHEMA_VERSION,
                "id": handoff_id,
                "fromAgent": from_agent,
                "toAgent": to_agent,
                "inputRefs": payload["inputRefs"],
                "outputRefs": payload["outputRefs"],
                "evidenceRefs": payload["evidenceRefs"],
                "verifierRefs": payload["verifierRefs"],
                "deliveryRefs": payload["deliveryRefs"],
                "sideEffectAllowed": False,
                "executionAllowed": False,
                "taskVerdictOwner": "verifier-runtime-v1",
                "policyDecision": payload["policyDecision"],
            }
        )
    return handoffs


def build_multi_agent_delivery_manifest(
    run_path: Path,
    context_pack_path: Path,
    evidence_path: Path,
    regression_result_path: Path,
    verifier_report_path: Path,
    email_draft_path: Path,
    ide_approval_handoff_path: Path,
    root: Path,
) -> dict[str, Any]:
    run = _load_json(run_path)
    evidence = _load_json(evidence_path)
    regression_result = _load_json(regression_result_path)
    verifier_report = _load_json(verifier_report_path)
    ide_approval_handoff = _load_json(ide_approval_handoff_path)
    email_text = email_draft_path.read_text(encoding="utf-8")

    task_spec = run["taskSpec"]
    permission_policy = run["runControl"]["permissionPolicy"]
    delivery_approval_point = "send_email_requires_human_approval"
    return {
        "schemaVersion": MULTI_AGENT_DELIVERY_MANIFEST_SCHEMA_VERSION,
        "id": MANIFEST_ID,
        "phase": "phase9",
        "scope": "multi_agent_delivery_loop_contract",
        "mode": "static_contract_only",
        "generatedAt": GENERATED_AT,
        "sourceArtifacts": [
            _artifact_source("run", run_path, root),
            _artifact_source("context_pack", context_pack_path, root),
            _artifact_source("evidence_list", evidence_path, root),
            _artifact_source("regression_result", regression_result_path, root),
            _artifact_source("verifier_report", verifier_report_path, root),
            _artifact_source("email_draft", email_draft_path, root),
            _artifact_source("ide_approval_handoff", ide_approval_handoff_path, root),
        ],
        "taskSpecBinding": {
            "taskSpecId": task_spec["id"],
            "runId": run["id"],
            "goal": task_spec["goal"],
            "approvalPoints": task_spec["approvalPoints"],
            "requiredDeliveryApprovalPoint": delivery_approval_point,
        },
        "agentRoles": _build_agent_roles(
            run_path,
            context_pack_path,
            evidence_path,
            regression_result_path,
            verifier_report_path,
            email_draft_path,
            root,
        ),
        "handoffs": _build_handoffs(
            run_path,
            context_pack_path,
            evidence_path,
            regression_result_path,
            verifier_report_path,
            email_draft_path,
            root,
        ),
        "ownership": {
            "taskSpecOwner": "planner_agent",
            "contextOwner": "context_agent",
            "executionRecordOwner": "executor_agent",
            "evidenceOwner": "evidence-list-v1",
            "taskVerdictOwner": "verifier-runtime-v1",
            "riskReviewOwner": "reviewer_agent",
            "deliveryOwner": "reporter_agent",
            "humanApprovalOwner": "permission-policy-v1",
        },
        "deliveryReview": {
            "verifierReportRef": _artifact_ref(verifier_report_path, root),
            "verifierStatus": verifier_report["status"],
            "blockingFailures": verifier_report["blockingFailures"],
            "evidenceIds": regression_result["evidenceIds"],
            "evidenceItemCount": len(evidence["items"]),
            "reviewerDecision": "delivery_draft_allowed" if verifier_report["status"] == "passed" else "blocked_by_verifier",
        },
        "deliveryArtifact": {
            "artifactType": "email_draft",
            "artifactRef": _artifact_ref(email_draft_path, root),
            "artifactHash": _stable_file_hash(email_draft_path),
            "artifactTextHash": _stable_text_hash(email_text),
            "regressionResultRef": _artifact_ref(regression_result_path, root),
            "evidenceListRef": _artifact_ref(evidence_path, root),
            "verifierReportRef": _artifact_ref(verifier_report_path, root),
            "ideApprovalHandoffRef": _artifact_ref(ide_approval_handoff_path, root),
            "approvalPoint": delivery_approval_point,
            "humanApprovalRequired": True,
            "humanApprovalSatisfied": False,
            "sendEmailAllowed": False,
            "deliveryState": "draft_only_blocked_until_human_approval",
        },
        "policy": {
            "externalSideEffectsAllowed": False,
            "realMultiAgentRuntimeAllowed": False,
            "workspaceMutationAllowed": False,
            "sendEmailAllowed": False,
            "prCreationAllowed": False,
            "requiresVerifierPassed": True,
            "requiresHumanApprovalForDelivery": True,
            "permissionPolicyRef": permission_policy["id"],
            "ideApprovalHandoffMode": ide_approval_handoff["mode"],
        },
        "invariants": [
            "Planner, Context, Executor, Reviewer, and Reporter communicate through source-bound handoff refs.",
            "Agents may package verified artifacts, but task verdicts remain owned by VerifierRuntimeV1.",
            "Delivery remains a draft until the permission policy records explicit human approval.",
            "Phase 9 MVP does not run a real multi-agent framework, mutate a workspace, open a PR, or send email.",
        ],
    }


def validate_multi_agent_delivery_manifest(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "MultiAgentDeliveryManifestV1",
        manifest,
        [
            "schemaVersion",
            "id",
            "phase",
            "scope",
            "mode",
            "sourceArtifacts",
            "taskSpecBinding",
            "agentRoles",
            "handoffs",
            "ownership",
            "deliveryReview",
            "deliveryArtifact",
            "policy",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != MULTI_AGENT_DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"MultiAgentDeliveryManifestV1 schemaVersion must be {MULTI_AGENT_DELIVERY_MANIFEST_SCHEMA_VERSION}"
        )
    if manifest["id"] != MANIFEST_ID:
        raise ValueError(f"MultiAgentDeliveryManifestV1 id must be {MANIFEST_ID}")
    if manifest["phase"] != "phase9":
        raise ValueError("MultiAgentDeliveryManifestV1 phase must be phase9")
    if manifest["mode"] != "static_contract_only":
        raise ValueError("MultiAgentDeliveryManifestV1 mode must be static_contract_only")

    expected_paths = {
        "run": DEFAULT_RUN_PATH,
        "context_pack": DEFAULT_CONTEXT_PACK_PATH,
        "evidence_list": DEFAULT_EVIDENCE_PATH,
        "regression_result": DEFAULT_REGRESSION_RESULT_PATH,
        "verifier_report": DEFAULT_VERIFIER_REPORT_PATH,
        "email_draft": DEFAULT_EMAIL_DRAFT_PATH,
        "ide_approval_handoff": DEFAULT_IDE_APPROVAL_HANDOFF_PATH,
    }
    sources = _validate_source_artifacts(manifest["sourceArtifacts"], expected_paths, root)
    run = _load_json(root / sources["run"]["path"])
    evidence = _load_json(root / sources["evidence_list"]["path"])
    regression_result = _load_json(root / sources["regression_result"]["path"])
    verifier_report = _load_json(root / sources["verifier_report"]["path"])
    ide_approval_handoff = _load_json(root / sources["ide_approval_handoff"]["path"])

    task_spec = run["taskSpec"]
    task_binding = manifest["taskSpecBinding"]
    _require_fields(
        "MultiAgentDeliveryManifestV1 taskSpecBinding",
        task_binding,
        ["taskSpecId", "runId", "goal", "approvalPoints", "requiredDeliveryApprovalPoint"],
    )
    if task_binding["taskSpecId"] != task_spec["id"]:
        raise ValueError("MultiAgentDeliveryManifestV1 taskSpecBinding must match run TaskSpec id")
    if task_binding["runId"] != run["id"]:
        raise ValueError("MultiAgentDeliveryManifestV1 taskSpecBinding runId must match run.json")
    if task_binding["goal"] != task_spec["goal"]:
        raise ValueError("MultiAgentDeliveryManifestV1 taskSpecBinding goal must match TaskSpec")
    if task_binding["approvalPoints"] != task_spec["approvalPoints"]:
        raise ValueError("MultiAgentDeliveryManifestV1 taskSpecBinding approvalPoints must match TaskSpec")
    delivery_approval = task_binding["requiredDeliveryApprovalPoint"]
    if delivery_approval != "send_email_requires_human_approval":
        raise ValueError("MultiAgentDeliveryManifestV1 delivery approval point must be send_email_requires_human_approval")
    if delivery_approval not in task_spec["approvalPoints"]:
        raise ValueError("MultiAgentDeliveryManifestV1 delivery approval point must be present in TaskSpec")

    agent_roles = manifest["agentRoles"]
    if not isinstance(agent_roles, list) or [agent.get("name") for agent in agent_roles if isinstance(agent, dict)] != AGENT_SEQUENCE:
        raise ValueError(f"MultiAgentDeliveryManifestV1 agentRoles must equal {AGENT_SEQUENCE}")
    for agent in agent_roles:
        if not isinstance(agent, dict):
            raise ValueError("MultiAgentDeliveryManifestV1 agentRoles must be objects")
        _require_fields(
            "MultiAgentDeliveryManifestV1 agent role",
            agent,
            ["name", "role", "owns", "inputRefs", "outputRefs", "allowedActions", "forbiddenActions"],
        )
        if "send_email" not in agent["forbiddenActions"]:
            raise ValueError(f"MultiAgentDeliveryManifestV1 {agent['name']} must forbid send_email")
        if agent["name"] != "executor_agent" and "mutate_workspace" not in agent["forbiddenActions"]:
            raise ValueError(f"MultiAgentDeliveryManifestV1 {agent['name']} must forbid workspace mutation")
        if agent["name"] == "reporter_agent" and "synthesize_new_facts" not in agent["forbiddenActions"]:
            raise ValueError("MultiAgentDeliveryManifestV1 reporter_agent must forbid synthesizing new facts")

    ownership = manifest["ownership"]
    _require_fields(
        "MultiAgentDeliveryManifestV1 ownership",
        ownership,
        [
            "taskSpecOwner",
            "contextOwner",
            "executionRecordOwner",
            "evidenceOwner",
            "taskVerdictOwner",
            "riskReviewOwner",
            "deliveryOwner",
            "humanApprovalOwner",
        ],
    )
    if ownership["taskVerdictOwner"] != "verifier-runtime-v1":
        raise ValueError("MultiAgentDeliveryManifestV1 task verdict owner must remain verifier-runtime-v1")
    if ownership["evidenceOwner"] != "evidence-list-v1":
        raise ValueError("MultiAgentDeliveryManifestV1 evidence owner must remain evidence-list-v1")
    if ownership["humanApprovalOwner"] != "permission-policy-v1":
        raise ValueError("MultiAgentDeliveryManifestV1 human approval owner must remain permission-policy-v1")

    handoffs = manifest["handoffs"]
    if not isinstance(handoffs, list) or len(handoffs) != len(HANDOFF_SEQUENCE):
        raise ValueError("MultiAgentDeliveryManifestV1 handoffs must cover the complete planner/context/executor/reviewer/reporter sequence")
    for handoff, expected in zip(handoffs, HANDOFF_SEQUENCE):
        if not isinstance(handoff, dict):
            raise ValueError("MultiAgentDeliveryManifestV1 handoffs must be objects")
        _require_fields(
            "MultiAgentDeliveryManifestV1 handoff",
            handoff,
            [
                "schemaVersion",
                "id",
                "fromAgent",
                "toAgent",
                "inputRefs",
                "outputRefs",
                "evidenceRefs",
                "verifierRefs",
                "deliveryRefs",
                "sideEffectAllowed",
                "executionAllowed",
                "taskVerdictOwner",
                "policyDecision",
            ],
        )
        expected_id, expected_from, expected_to = expected
        if handoff["schemaVersion"] != AGENT_HANDOFF_SCHEMA_VERSION:
            raise ValueError("MultiAgentDeliveryManifestV1 handoff schemaVersion mismatch")
        if (handoff["id"], handoff["fromAgent"], handoff["toAgent"]) != expected:
            raise ValueError(f"MultiAgentDeliveryManifestV1 handoff sequence must include {expected_id} {expected_from}->{expected_to}")
        if handoff["sideEffectAllowed"] is not False:
            raise ValueError("MultiAgentDeliveryManifestV1 handoffs must not allow side effects")
        if handoff["executionAllowed"] is not False:
            raise ValueError("MultiAgentDeliveryManifestV1 handoffs must not allow runtime execution")
        if handoff["taskVerdictOwner"] != "verifier-runtime-v1":
            raise ValueError("MultiAgentDeliveryManifestV1 handoff task verdict owner must remain verifier-runtime-v1")
        for ref_list_name in ["inputRefs", "outputRefs", "evidenceRefs", "verifierRefs", "deliveryRefs"]:
            refs = handoff[ref_list_name]
            if not isinstance(refs, list):
                raise ValueError(f"MultiAgentDeliveryManifestV1 handoff {ref_list_name} must be a list")

    evidence_items = evidence.get("items")
    if not isinstance(evidence_items, list) or not evidence_items:
        raise ValueError("MultiAgentDeliveryManifestV1 requires non-empty EvidenceListV1 items")
    evidence_ids = {item["id"] for item in evidence_items if isinstance(item, dict) and "id" in item}
    if not set(regression_result.get("evidenceIds", [])).issubset(evidence_ids):
        raise ValueError("MultiAgentDeliveryManifestV1 regression result evidence ids must resolve to EvidenceListV1")

    delivery_review = manifest["deliveryReview"]
    _require_fields(
        "MultiAgentDeliveryManifestV1 deliveryReview",
        delivery_review,
        ["verifierReportRef", "verifierStatus", "blockingFailures", "evidenceIds", "evidenceItemCount", "reviewerDecision"],
    )
    if delivery_review["verifierReportRef"] != DEFAULT_VERIFIER_REPORT_PATH:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryReview verifierReportRef mismatch")
    if delivery_review["verifierStatus"] != verifier_report["status"]:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryReview verifierStatus must match verifier_report")
    if delivery_review["verifierStatus"] != "passed":
        raise ValueError("MultiAgentDeliveryManifestV1 requires verifier status passed before delivery draft")
    if delivery_review["blockingFailures"] != verifier_report["blockingFailures"] or delivery_review["blockingFailures"]:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryReview must have no blocking verifier failures")
    if delivery_review["evidenceIds"] != regression_result["evidenceIds"]:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryReview evidenceIds must match regression_result")
    if delivery_review["evidenceItemCount"] != len(evidence_items):
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryReview evidenceItemCount mismatch")
    if delivery_review["reviewerDecision"] != "delivery_draft_allowed":
        raise ValueError("MultiAgentDeliveryManifestV1 reviewerDecision must be delivery_draft_allowed")

    delivery = manifest["deliveryArtifact"]
    _require_fields(
        "MultiAgentDeliveryManifestV1 deliveryArtifact",
        delivery,
        [
            "artifactType",
            "artifactRef",
            "artifactHash",
            "artifactTextHash",
            "regressionResultRef",
            "evidenceListRef",
            "verifierReportRef",
            "ideApprovalHandoffRef",
            "approvalPoint",
            "humanApprovalRequired",
            "humanApprovalSatisfied",
            "sendEmailAllowed",
            "deliveryState",
        ],
    )
    if delivery["artifactType"] != "email_draft":
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact must be an email_draft")
    if delivery["artifactRef"] != DEFAULT_EMAIL_DRAFT_PATH:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact artifactRef mismatch")
    email_path = root / DEFAULT_EMAIL_DRAFT_PATH
    if delivery["artifactHash"] != _stable_file_hash(email_path):
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact hash mismatch")
    if delivery["artifactTextHash"] != _stable_text_hash(email_path.read_text(encoding="utf-8")):
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact text hash mismatch")
    if delivery["regressionResultRef"] != DEFAULT_REGRESSION_RESULT_PATH:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact regressionResultRef mismatch")
    if delivery["evidenceListRef"] != DEFAULT_EVIDENCE_PATH:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact evidenceListRef mismatch")
    if delivery["verifierReportRef"] != DEFAULT_VERIFIER_REPORT_PATH:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact verifierReportRef mismatch")
    if delivery["ideApprovalHandoffRef"] != DEFAULT_IDE_APPROVAL_HANDOFF_PATH:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact ideApprovalHandoffRef mismatch")
    if delivery["approvalPoint"] != delivery_approval:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact approvalPoint must match TaskSpec binding")
    if delivery["humanApprovalRequired"] is not True:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact must require human approval")
    if delivery["humanApprovalSatisfied"] is not False:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact must not synthesize human approval")
    if delivery["sendEmailAllowed"] is not False:
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact must not send email")
    if delivery["deliveryState"] != "draft_only_blocked_until_human_approval":
        raise ValueError("MultiAgentDeliveryManifestV1 deliveryArtifact must remain blocked until human approval")

    handoff_requests = ide_approval_handoff.get("handoffRequests", [])
    matching_approval = [
        request
        for request in handoff_requests
        if isinstance(request, dict) and request.get("approvalPoint") == delivery_approval
    ]
    if not matching_approval:
        raise ValueError("MultiAgentDeliveryManifestV1 must bind delivery approval to IDEApprovalHandoffManifestV1")
    if any(request.get("executionAllowed") is not False for request in matching_approval):
        raise ValueError("MultiAgentDeliveryManifestV1 IDE approval handoff must remain execution blocked")

    policy = manifest["policy"]
    _require_fields(
        "MultiAgentDeliveryManifestV1 policy",
        policy,
        [
            "externalSideEffectsAllowed",
            "realMultiAgentRuntimeAllowed",
            "workspaceMutationAllowed",
            "sendEmailAllowed",
            "prCreationAllowed",
            "requiresVerifierPassed",
            "requiresHumanApprovalForDelivery",
            "permissionPolicyRef",
            "ideApprovalHandoffMode",
        ],
    )
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("MultiAgentDeliveryManifestV1 policy must disallow external side effects")
    if policy["realMultiAgentRuntimeAllowed"] is not False:
        raise ValueError("MultiAgentDeliveryManifestV1 policy must disallow real multi-agent runtime execution")
    if policy["workspaceMutationAllowed"] is not False:
        raise ValueError("MultiAgentDeliveryManifestV1 policy must disallow workspace mutation")
    if policy["sendEmailAllowed"] is not False:
        raise ValueError("MultiAgentDeliveryManifestV1 policy must not send email")
    if policy["prCreationAllowed"] is not False:
        raise ValueError("MultiAgentDeliveryManifestV1 policy must disallow PR creation")
    if policy["requiresVerifierPassed"] is not True:
        raise ValueError("MultiAgentDeliveryManifestV1 policy must require verifier passed status")
    if policy["requiresHumanApprovalForDelivery"] is not True:
        raise ValueError("MultiAgentDeliveryManifestV1 policy must require human approval for delivery")
    if policy["permissionPolicyRef"] != run["runControl"]["permissionPolicy"]["id"]:
        raise ValueError("MultiAgentDeliveryManifestV1 policy permissionPolicyRef must match RunControlV1")
    if policy["ideApprovalHandoffMode"] != "static_fixture_only":
        raise ValueError("MultiAgentDeliveryManifestV1 policy must bind static IDE approval handoff mode")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="multi-agent-delivery")
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--run", type=Path, default=Path(DEFAULT_RUN_PATH))
    parser.add_argument("--context-pack", type=Path, default=Path(DEFAULT_CONTEXT_PACK_PATH))
    parser.add_argument("--evidence", type=Path, default=Path(DEFAULT_EVIDENCE_PATH))
    parser.add_argument("--regression-result", type=Path, default=Path(DEFAULT_REGRESSION_RESULT_PATH))
    parser.add_argument("--verifier-report", type=Path, default=Path(DEFAULT_VERIFIER_REPORT_PATH))
    parser.add_argument("--email-draft", type=Path, default=Path(DEFAULT_EMAIL_DRAFT_PATH))
    parser.add_argument("--ide-approval-handoff", type=Path, default=Path(DEFAULT_IDE_APPROVAL_HANDOFF_PATH))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--validate-manifest", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()

    if args.manifest_out:
        manifest = build_multi_agent_delivery_manifest(
            root / args.run,
            root / args.context_pack,
            root / args.evidence,
            root / args.regression_result,
            root / args.verifier_report,
            root / args.email_draft,
            root / args.ide_approval_handoff,
            root,
        )
        validate_multi_agent_delivery_manifest(manifest, root)
        _write_json(args.manifest_out, manifest)
        print(f"Wrote MultiAgentDeliveryManifestV1 artifact to {args.manifest_out}.")

    if args.validate_manifest:
        manifest = _load_json(args.validate_manifest)
        validate_multi_agent_delivery_manifest(manifest, root)
        print(f"Validated MultiAgentDeliveryManifestV1 artifact {args.validate_manifest}.")

    if not any([args.manifest_out, args.validate_manifest]):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

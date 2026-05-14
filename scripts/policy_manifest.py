"""PolicyManifestV1 ArtifactV1 subtype contract.

This module defines a workload-independent ``PolicyManifestV1`` ArtifactV1
subtype.  It captures the canonical OS-kernel policy primitive for any
engineering workload: an explicit declaration of (a) the workload-independent
permission flag set, (b) a closed effect-class domain with allow/deny
decisions, (c) per-capability ``policy-rule-v1`` bindings, (d) unlock
conditions tying the policy to verdict / run terminal state / approval, and
(e) revocation rules that revert any unlock the moment one of the upstream
invariants drifts.

The artifact answers four OS-kernel invariants at once:

- ``Policy`` primitive: the manifest declares the canonical permission flags
  (``externalSideEffectsAllowed`` / ``repositoryMutationAllowed`` /
  ``externalCommunicationAllowed`` / ``releaseOrDeploymentAllowed`` /
  ``guiOrBrowserOrDesktopCallAllowed`` / ``publicAccessAllowed``) and forces
  every flag to ``false`` at the manifest level.  Per-effect-class allow/deny
  decisions and per-capability policy rules express the runtime contract
  that the policy runtime is expected to enforce.
- ``Artifact`` envelope reuse: the manifest is an ``ArtifactV1`` subtype
  (``artifactEnvelopeSchemaVersion=artifact-v1``) joining the existing
  ``CapabilityManifestV1`` / ``TestExecutionResultV1`` /
  ``FailureTriageReportV1`` / ``VerifierResultV1`` / ``RunEventLogV1`` /
  ``DeliveryManifestV1`` subtypes.
- ``Verifier`` / ``RunEvent`` / ``Delivery`` / ``Approval`` consistency: the
  manifest pins the upstream ``TestExecutionTaskSpecV1`` envelope, the
  upstream ``CapabilityManifestV1`` artifact, the upstream
  ``RunEventLogV1`` artifact, the upstream ``VerifierResultV1`` artifact,
  the upstream ``DeliveryManifestV1`` artifact, and the upstream
  ``HumanApprovalDecisionV1`` record by content hash.  A policy unlock can
  only fire when ``verdict == passed``, ``RunEventLogV1`` terminal state
  is ``completed``, and the bound human approval decision is granted.
- ``Coordination`` policy boundary: the manifest binds all five Agent
  Coordination Layer contracts by ref + content hash, so every coordination
  decision is constrained by the same policy primitive.

Key invariants this module enforces:

- The manifest is an ``ArtifactV1`` envelope subtype distinct from every
  existing creator-owned or verifier-owned test_execution_failure_triage
  subtype; ``schemaVersion`` is ``policy-manifest-v1`` and ``kind`` is
  ``PolicyManifestV1``.
- Every permission flag in ``permissionFlags`` is ``false`` and the
  ``permissionFlagDomain`` enumerates the six canonical permission flags.
- Every effect class in ``effectClasses`` has a workload-independent
  ``className``, a ``decision`` from {``allow``, ``deny``}, and the
  decisions partition the effect-class domain into the canonical allow set
  (``internal_read`` / ``internal_compute`` / ``internal_artifact_write``)
  and deny set (``external_side_effect`` / ``repository_mutation`` /
  ``external_communication`` / ``release_or_deployment`` /
  ``gui_or_browser_or_desktop_call`` / ``public_access``).
- Every capability in ``CapabilityManifestV1.capabilities[*].name`` is bound
  to one allow effect-class via a ``policy-rule-v1`` rule with
  ``ruleKind=capability_allow``; every deny effect-class is bound to a
  ``policy-rule-v1`` rule with ``ruleKind=effect_class_deny``; and every
  permission flag is bound to a ``policy-rule-v1`` rule with
  ``ruleKind=permission_flag_deny`` whose enforcement is ``deny``.
- ``policyOwner`` is ``policy-runtime-v1`` and ``verifierVerdictOwner`` is
  ``verifier-runtime-v1``; ``creatorMustNotOwnVerdict`` is ``true``.
- ``unlockConditions.requiredVerdict`` is ``passed``,
  ``requiredTerminalRunState`` is ``completed``,
  ``requiredApprovalDecision`` is ``approved``, and
  ``unlocked`` is ``true`` only when the bound verdict, run terminal state
  and approval all match the required values.
- ``revocationRules`` declare at least five workload-independent triggers
  (verdict drift, run terminal state drift, approval revocation, permission
  flag flipped, source artifact drift); every rule revokes all unlocks.
- The artifact carries no external side effects, no repository mutation,
  no GUI / browser / desktop call, no public access, and no delivery.

The artifact is fully self-contained (synthetic deterministic effect
classes, capability rules and revocation rules) so it remains deterministic
across Linux / macOS / Windows and requires no real policy runtime to
validate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from capability_manifest import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as CAPABILITY_MANIFEST_ARTIFACT_ID,
    CAPABILITY_MANIFEST_ARTIFACT_PATH,
    CAPABILITY_MANIFEST_SCHEMA_VERSION,
    CAPABILITY_NAMES,
    validate_capability_manifest,
)
from coordination_contract import (
    AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
    CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    DELEGATION_MANIFEST_ARTIFACT_PATH,
    NEGOTIATION_RECORD_ARTIFACT_PATH,
    validate_agent_message_manifest,
    validate_broadcast_subscription_manifest,
    validate_creator_verifier_pairing,
    validate_delegation_manifest,
    validate_negotiation_record,
)
from delivery_manifest import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as DELIVERY_MANIFEST_ARTIFACT_ID,
    DELIVERY_MANIFEST_ARTIFACT_PATH,
    DELIVERY_MANIFEST_SCHEMA_VERSION,
    validate_delivery_manifest,
)
from human_approval import (
    DECISION_ARTIFACT_PATH as HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    validate_human_approval_decision,
)
from run_event_log import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as RUN_EVENT_LOG_ARTIFACT_ID,
    RUN_EVENT_LOG_ARTIFACT_PATH,
    RUN_EVENT_LOG_SCHEMA_VERSION,
    validate_run_event_log,
)
from test_execution_task_spec import (
    TASK_SPEC_ARTIFACT_PATH as TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
    TASK_SPEC_ID as TEST_EXECUTION_TASK_SPEC_ID,
    TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
    validate_test_execution_task_spec,
)
from verifier_result import (
    ARTIFACT_ENVELOPE_SCHEMA_VERSION as VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION,
    ARTIFACT_ID as VERIFIER_RESULT_ARTIFACT_ID,
    VERIFIER_RESULT_ARTIFACT_PATH,
    VERIFIER_RESULT_SCHEMA_VERSION,
    validate_verifier_result,
)


POLICY_MANIFEST_SCHEMA_VERSION = "policy-manifest-v1"
POLICY_RULE_SCHEMA_VERSION = "policy-rule-v1"
POLICY_EFFECT_CLASS_SCHEMA_VERSION = "policy-effect-class-v1"
POLICY_REVOCATION_RULE_SCHEMA_VERSION = "policy-revocation-rule-v1"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "artifact-v1"
ARTIFACT_KIND = "PolicyManifestV1"
GENERATED_AT = "2026-05-12T14:39:00Z"
ARTIFACT_ID = "post-mvp-test-execution-policy-manifest-kernel-contract"
POLICY_MANIFEST_ARTIFACT_PATH = (
    "artifacts/policy/post_mvp_test_execution_policy_manifest.json"
)

WORKLOAD_TYPE = "test_execution_failure_triage"
WORKLOAD_CATEGORY = "engineering_workload"
SCOPE = "test_execution_failure_triage_policy_manifest_contract"

CREATOR_AGENT = "creator_agent"
POLICY_OWNER = "policy-runtime-v1"
VERIFIER_VERDICT_OWNER = "verifier-runtime-v1"
VERDICT_DOMAIN = ["passed", "failed", "incomplete", "needs_human_check"]

REQUIRED_VERDICT_FOR_UNLOCK = "passed"
REQUIRED_TERMINAL_RUN_STATE = "completed"
REQUIRED_APPROVAL_DECISION = "approved"

PERMISSION_FLAG_DOMAIN = [
    "externalSideEffectsAllowed",
    "repositoryMutationAllowed",
    "externalCommunicationAllowed",
    "releaseOrDeploymentAllowed",
    "guiOrBrowserOrDesktopCallAllowed",
    "publicAccessAllowed",
]

EFFECT_CLASS_DOMAIN = [
    "internal_read",
    "internal_compute",
    "internal_artifact_write",
    "external_side_effect",
    "repository_mutation",
    "external_communication",
    "release_or_deployment",
    "gui_or_browser_or_desktop_call",
    "public_access",
]

ALLOW_EFFECT_CLASSES = [
    "internal_read",
    "internal_compute",
    "internal_artifact_write",
]
DENY_EFFECT_CLASSES = [
    "external_side_effect",
    "repository_mutation",
    "external_communication",
    "release_or_deployment",
    "gui_or_browser_or_desktop_call",
    "public_access",
]

DECISION_DOMAIN = ["allow", "deny"]

EFFECT_CLASS_BLUEPRINT: list[dict[str, Any]] = [
    {
        "className": "internal_read",
        "decision": "allow",
        "reason": "Reading internal evidence and artifact records is required for any verifier-owned acceptance flow and never crosses a workload boundary.",
    },
    {
        "className": "internal_compute",
        "decision": "allow",
        "reason": "Pure deterministic computation over internal evidence is required for failure classification and verifier rule evaluation.",
    },
    {
        "className": "internal_artifact_write",
        "decision": "allow",
        "reason": "Writing the workload-independent artifact bundle to the local artifact directory is the only sanctioned creator-side write path.",
    },
    {
        "className": "external_side_effect",
        "decision": "deny",
        "reason": "External side effects (real email, ticketing, web requests, deployment) are out of scope for the contract-only MVP and must not be triggered by any workload.",
    },
    {
        "className": "repository_mutation",
        "decision": "deny",
        "reason": "Repository mutation (commits, branches, tags, deletes) requires explicit human authorization that is not granted by the contract-only MVP.",
    },
    {
        "className": "external_communication",
        "decision": "deny",
        "reason": "External communication (email, Slack, PR comments, webhooks) crosses a delivery boundary and is owned by the future delivery runtime, not the policy primitive.",
    },
    {
        "className": "release_or_deployment",
        "decision": "deny",
        "reason": "Release or deployment is a release-engineering concern outside the policy primitive's authority.",
    },
    {
        "className": "gui_or_browser_or_desktop_call",
        "decision": "deny",
        "reason": "GUI / browser / desktop calls require a real Computer Runtime adapter; the policy primitive denies them by default and defers to AdapterPolicyManifestV1 for any future overlay.",
    },
    {
        "className": "public_access",
        "decision": "deny",
        "reason": "Public access (publishing artifacts, exposing endpoints) is outside the policy primitive's authority.",
    },
]

CAPABILITY_TO_EFFECT_CLASS: dict[str, str] = {
    "read_test_execution_result": "internal_read",
    "collect_test_failure_evidence": "internal_read",
    "classify_test_failure": "internal_compute",
    "write_artifact": "internal_artifact_write",
}

REVOCATION_RULE_BLUEPRINT: list[dict[str, Any]] = [
    {
        "ruleId": "revoke-on-verdict-not-passed",
        "trigger": "verifier_result_verdict_not_passed",
        "watchedField": "VerifierResultV1.verdict",
        "action": "revoke_all_unlocks",
        "reason": "Any verdict other than passed must immediately revoke every unlock granted under this policy.",
    },
    {
        "ruleId": "revoke-on-run-not-completed",
        "trigger": "run_event_log_terminal_state_not_completed",
        "watchedField": "RunEventLogV1.terminalState",
        "action": "revoke_all_unlocks",
        "reason": "If the run never reaches a completed terminal state the policy unlock must be revoked even if the verdict was provisionally passed.",
    },
    {
        "ruleId": "revoke-on-approval-revocation",
        "trigger": "human_approval_decision_revoked_or_not_granted",
        "watchedField": "HumanApprovalDecisionV1.decision.approvalGranted",
        "action": "revoke_all_unlocks",
        "reason": "Loss of human approval (rejection, expiry, revocation) must immediately revoke every unlock granted under this policy.",
    },
    {
        "ruleId": "revoke-on-permission-flag-flipped-true",
        "trigger": "permission_flag_flipped_true",
        "watchedField": "PolicyManifestV1.permissionFlags",
        "action": "revoke_all_unlocks",
        "reason": "Any permission flag flipping to true breaks the contract-only MVP guarantee and must revoke every unlock.",
    },
    {
        "ruleId": "revoke-on-source-artifact-drift",
        "trigger": "source_artifact_content_hash_drift",
        "watchedField": "PolicyManifestV1.sourceArtifacts[*].contentHash",
        "action": "revoke_all_unlocks",
        "reason": "Drift in any pinned source artifact invalidates the policy decision and must revoke every unlock.",
    },
]

NON_REGRESSION_REUSE_PATH = [
    "test_execution_failure_triage",
    "code_patch_review_loop",
    "pr_review",
]

FORBIDDEN_REGRESSION_FIELDS = [
    "regression_result",
    "regression_result.json",
    "email_draft",
    "email_draft.md",
    "send_email",
    "regression-task-spec-v1",
    "regression-result-artifact-v1",
]

COORDINATION_BINDING_PATHS: dict[str, str] = {
    "delegationManifestRef": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creatorVerifierPairingRef": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agentMessageManifestRef": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiationRecordRef": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcastSubscriptionManifestRef": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

SOURCE_ROLE_TO_PATH: dict[str, str] = {
    "test_execution_task_spec": TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH,
    "test_execution_capability_manifest": CAPABILITY_MANIFEST_ARTIFACT_PATH,
    "test_execution_run_event_log": RUN_EVENT_LOG_ARTIFACT_PATH,
    "test_execution_verifier_result": VERIFIER_RESULT_ARTIFACT_PATH,
    "test_execution_delivery_manifest": DELIVERY_MANIFEST_ARTIFACT_PATH,
    "human_approval_decision": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
    "delegation_manifest": DELEGATION_MANIFEST_ARTIFACT_PATH,
    "creator_verifier_pairing": CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH,
    "agent_message_manifest": AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH,
    "negotiation_record": NEGOTIATION_RECORD_ARTIFACT_PATH,
    "broadcast_subscription_manifest": BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH,
}

REQUIRED_VERIFIER_FLAGS = [
    "mustValidateSchema",
    "mustValidateTaskSpecBinding",
    "mustValidateCapabilityManifestBinding",
    "mustValidateRunEventLogBinding",
    "mustValidateVerifierResultBinding",
    "mustValidateDeliveryManifestBinding",
    "mustValidateApprovalRecordBinding",
    "mustValidatePermissionFlags",
    "mustEnforceEffectClassDecisions",
    "mustEnforceCapabilityRules",
    "mustEnforceUnlockConditions",
    "mustEnforceRevocationRules",
    "creatorMustNotOwnVerdict",
]

INVARIANTS = [
    "PolicyManifestV1 is an ArtifactV1 subtype distinct from every workload-specific result subtype.",
    "PolicyManifestV1 must bind TestExecutionTaskSpecV1, CapabilityManifestV1, RunEventLogV1, VerifierResultV1, DeliveryManifestV1, HumanApprovalDecisionV1, and all five coordination contracts by content hash.",
    "PolicyManifestV1 declares the canonical workload-independent permission flag set; every flag is forced to false at the manifest level.",
    "PolicyManifestV1 partitions the effect-class domain into a fixed allow set and deny set; deny effect classes can never be allowed.",
    "PolicyManifestV1 binds every capability in CapabilityManifestV1 to exactly one allow effect class through a policy-rule-v1 rule.",
    "PolicyManifestV1 must not own the verifier verdict; verifier-runtime-v1 owns acceptance and policy-runtime-v1 owns enforcement.",
    "PolicyManifestV1 unlock requires verdict=passed, terminal run state=completed, and granted human approval; revocation rules revert the unlock the moment any of those conditions drifts.",
    "PolicyManifestV1 must not reuse phase7_adapter_policy_manifest.json or post_mvp_policy_unlock_request_denied.json; both remain workload-specific overlays.",
]


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
    if (
        not isinstance(path, str)
        or not path
        or Path(path).is_absolute()
        or "\\" in path
        or path.startswith("../")
        or "/../" in path
    ):
        raise ValueError(
            f"PolicyManifestV1 paths must be POSIX relative repository paths: {path}"
        )


def _artifact_source(role: str, relative_path: str, root: Path) -> dict[str, Any]:
    _validate_relative_posix_path(relative_path)
    full_path = root / relative_path
    if not full_path.is_file():
        raise ValueError(
            f"PolicyManifestV1 source artifact does not exist: {relative_path}"
        )
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(full_path),
    }


def _coordination_binding(root: Path) -> dict[str, str]:
    binding: dict[str, str] = {}
    for field, relative_path in COORDINATION_BINDING_PATHS.items():
        _validate_relative_posix_path(relative_path)
        full_path = root / relative_path
        if not full_path.is_file():
            raise ValueError(
                f"PolicyManifestV1 coordination binding is missing artifact: {relative_path}"
            )
        binding[field] = relative_path
    return dict(sorted(binding.items()))


def _validate_referenced_artifacts(root: Path) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any]
]:
    delegation = _load_json(root / DELEGATION_MANIFEST_ARTIFACT_PATH)
    validate_delegation_manifest(delegation, root)
    pairing = _load_json(root / CREATOR_VERIFIER_PAIRING_ARTIFACT_PATH)
    validate_creator_verifier_pairing(pairing, root)
    agent_message = _load_json(root / AGENT_MESSAGE_MANIFEST_ARTIFACT_PATH)
    validate_agent_message_manifest(agent_message, root)
    negotiation = _load_json(root / NEGOTIATION_RECORD_ARTIFACT_PATH)
    validate_negotiation_record(negotiation, root)
    broadcast = _load_json(root / BROADCAST_SUBSCRIPTION_MANIFEST_ARTIFACT_PATH)
    validate_broadcast_subscription_manifest(broadcast, root)
    task_spec = _load_json(root / TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH)
    validate_test_execution_task_spec(task_spec, root)
    capability_manifest = _load_json(root / CAPABILITY_MANIFEST_ARTIFACT_PATH)
    validate_capability_manifest(capability_manifest, root)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    validate_run_event_log(run_event_log, root)
    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    validate_verifier_result(verifier_result, root)
    delivery_manifest = _load_json(root / DELIVERY_MANIFEST_ARTIFACT_PATH)
    validate_delivery_manifest(delivery_manifest, root)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    validate_human_approval_decision(approval_decision, root)
    return verifier_result, run_event_log, approval_decision


def _build_task_spec_binding(root: Path) -> dict[str, Any]:
    relative_path = TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "taskSpecRef": relative_path,
        "taskSpecSchemaVersion": TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION,
        "taskSpecEnvelopeSchemaVersion": TASK_SPEC_ENVELOPE_SCHEMA_VERSION,
        "taskSpecId": TEST_EXECUTION_TASK_SPEC_ID,
        "taskSpecContentHash": _stable_file_hash(full_path),
    }


def _build_capability_manifest_binding(root: Path) -> dict[str, Any]:
    relative_path = CAPABILITY_MANIFEST_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "capabilityManifestRef": relative_path,
        "capabilityManifestSchemaVersion": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "capabilityManifestEnvelopeSchemaVersion": CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "capabilityManifestId": CAPABILITY_MANIFEST_ARTIFACT_ID,
        "capabilityManifestContentHash": _stable_file_hash(full_path),
    }


def _build_run_event_log_binding(
    root: Path, run_event_log: dict[str, Any]
) -> dict[str, Any]:
    relative_path = RUN_EVENT_LOG_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "runEventLogRef": relative_path,
        "runEventLogSchemaVersion": RUN_EVENT_LOG_SCHEMA_VERSION,
        "runEventLogEnvelopeSchemaVersion": RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION,
        "runEventLogId": RUN_EVENT_LOG_ARTIFACT_ID,
        "runEventLogContentHash": _stable_file_hash(full_path),
        "terminalState": run_event_log["terminalState"],
    }


def _build_verifier_result_binding(
    root: Path, verifier_result: dict[str, Any]
) -> dict[str, Any]:
    relative_path = VERIFIER_RESULT_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "verifierResultRef": relative_path,
        "verifierResultSchemaVersion": VERIFIER_RESULT_SCHEMA_VERSION,
        "verifierResultEnvelopeSchemaVersion": VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION,
        "verifierResultId": VERIFIER_RESULT_ARTIFACT_ID,
        "verifierResultContentHash": _stable_file_hash(full_path),
        "verdict": verifier_result["verdict"],
    }


def _build_delivery_manifest_binding(root: Path) -> dict[str, Any]:
    relative_path = DELIVERY_MANIFEST_ARTIFACT_PATH
    full_path = root / relative_path
    return {
        "deliveryManifestRef": relative_path,
        "deliveryManifestSchemaVersion": DELIVERY_MANIFEST_SCHEMA_VERSION,
        "deliveryManifestEnvelopeSchemaVersion": DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION,
        "deliveryManifestId": DELIVERY_MANIFEST_ARTIFACT_ID,
        "deliveryManifestContentHash": _stable_file_hash(full_path),
    }


def _build_approval_record_binding(
    root: Path, approval_decision: dict[str, Any]
) -> dict[str, Any]:
    relative_path = HUMAN_APPROVAL_DECISION_ARTIFACT_PATH
    full_path = root / relative_path
    decision_block = approval_decision.get("decision", {})
    return {
        "approvalRecordRef": relative_path,
        "approvalRecordSchemaVersion": "human-approval-decision-v1",
        "approvalRecordContentHash": _stable_file_hash(full_path),
        "currentDecision": decision_block.get("decision"),
        "approvalGranted": decision_block.get("approvalGranted") is True,
    }


def _build_unlock_conditions(
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    approval_decision: dict[str, Any],
) -> dict[str, Any]:
    decision_block = approval_decision.get("decision", {})
    verdict = verifier_result["verdict"]
    terminal_state = run_event_log["terminalState"]
    granted = decision_block.get("approvalGranted") is True
    unlocked = (
        verdict == REQUIRED_VERDICT_FOR_UNLOCK
        and terminal_state == REQUIRED_TERMINAL_RUN_STATE
        and granted
    )
    return {
        "requiredVerdict": REQUIRED_VERDICT_FOR_UNLOCK,
        "currentVerdict": verdict,
        "verdictOwner": VERIFIER_VERDICT_OWNER,
        "requiredTerminalRunState": REQUIRED_TERMINAL_RUN_STATE,
        "currentTerminalRunState": terminal_state,
        "requiredApprovalDecision": REQUIRED_APPROVAL_DECISION,
        "currentApprovalDecision": decision_block.get("decision"),
        "approvalGranted": granted,
        "approvalRecordRef": HUMAN_APPROVAL_DECISION_ARTIFACT_PATH,
        "approvalRecordSchemaVersion": "human-approval-decision-v1",
        "unlocked": unlocked,
    }


def _build_effect_classes() -> list[dict[str, Any]]:
    classes: list[dict[str, Any]] = []
    for blueprint in EFFECT_CLASS_BLUEPRINT:
        entry = {
            "schemaVersion": POLICY_EFFECT_CLASS_SCHEMA_VERSION,
            "className": blueprint["className"],
            "decision": blueprint["decision"],
            "reason": blueprint["reason"],
        }
        classes.append(entry)
    return classes


def _build_capability_rules() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for capability_name in CAPABILITY_NAMES:
        if capability_name not in CAPABILITY_TO_EFFECT_CLASS:
            raise ValueError(
                f"PolicyManifestV1 capability rule blueprint missing capability: {capability_name}"
            )
        effect_class = CAPABILITY_TO_EFFECT_CLASS[capability_name]
        rules.append(
            {
                "schemaVersion": POLICY_RULE_SCHEMA_VERSION,
                "ruleId": f"capability-allow-{capability_name.replace('_', '-')}",
                "ruleKind": "capability_allow",
                "decision": "allow",
                "appliesToCapability": capability_name,
                "effectClass": effect_class,
                "reason": (
                    f"Capability {capability_name} is bound to allow effect class {effect_class}; "
                    "no other effect class is permitted for this capability."
                ),
            }
        )
    return rules


def _build_effect_class_deny_rules() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for class_name in DENY_EFFECT_CLASSES:
        rules.append(
            {
                "schemaVersion": POLICY_RULE_SCHEMA_VERSION,
                "ruleId": f"effect-class-deny-{class_name.replace('_', '-')}",
                "ruleKind": "effect_class_deny",
                "decision": "deny",
                "effectClass": class_name,
                "reason": f"Effect class {class_name} is denied for every workload covered by this policy primitive.",
            }
        )
    return rules


def _build_permission_flag_deny_rules() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for flag in PERMISSION_FLAG_DOMAIN:
        rules.append(
            {
                "schemaVersion": POLICY_RULE_SCHEMA_VERSION,
                "ruleId": f"permission-flag-deny-{flag}",
                "ruleKind": "permission_flag_deny",
                "decision": "deny",
                "permissionFlag": flag,
                "reason": f"Permission flag {flag} is forced to false; flipping it to true revokes every unlock granted under this policy.",
            }
        )
    return rules


def _build_revocation_rules() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for blueprint in REVOCATION_RULE_BLUEPRINT:
        rules.append(
            {
                "schemaVersion": POLICY_REVOCATION_RULE_SCHEMA_VERSION,
                "ruleId": blueprint["ruleId"],
                "trigger": blueprint["trigger"],
                "watchedField": blueprint["watchedField"],
                "action": blueprint["action"],
                "reason": blueprint["reason"],
            }
        )
    return rules


def build_policy_manifest(root: Path) -> dict[str, Any]:
    verifier_result, run_event_log, approval_decision = _validate_referenced_artifacts(
        root
    )
    capability_rules = _build_capability_rules()
    effect_class_deny_rules = _build_effect_class_deny_rules()
    permission_flag_deny_rules = _build_permission_flag_deny_rules()
    policy_rules = capability_rules + effect_class_deny_rules + permission_flag_deny_rules
    payload: dict[str, Any] = {
        "schemaVersion": POLICY_MANIFEST_SCHEMA_VERSION,
        "artifactEnvelopeSchemaVersion": ARTIFACT_ENVELOPE_SCHEMA_VERSION,
        "id": ARTIFACT_ID,
        "generatedAt": GENERATED_AT,
        "kind": ARTIFACT_KIND,
        "scope": SCOPE,
        "workloadType": WORKLOAD_TYPE,
        "workloadCategory": WORKLOAD_CATEGORY,
        "creatorAgent": CREATOR_AGENT,
        "policyOwner": POLICY_OWNER,
        "verifierVerdictOwner": VERIFIER_VERDICT_OWNER,
        "policyRuleSchemaVersion": POLICY_RULE_SCHEMA_VERSION,
        "policyEffectClassSchemaVersion": POLICY_EFFECT_CLASS_SCHEMA_VERSION,
        "policyRevocationRuleSchemaVersion": POLICY_REVOCATION_RULE_SCHEMA_VERSION,
        "verdictDomain": list(VERDICT_DOMAIN),
        "decisionDomain": list(DECISION_DOMAIN),
        "permissionFlagDomain": list(PERMISSION_FLAG_DOMAIN),
        "permissionFlags": {flag: False for flag in PERMISSION_FLAG_DOMAIN},
        "effectClassDomain": list(EFFECT_CLASS_DOMAIN),
        "allowEffectClasses": list(ALLOW_EFFECT_CLASSES),
        "denyEffectClasses": list(DENY_EFFECT_CLASSES),
        "effectClasses": _build_effect_classes(),
        "policyRules": policy_rules,
        "policyRuleCount": len(policy_rules),
        "revocationRules": _build_revocation_rules(),
        "taskSpecBinding": _build_task_spec_binding(root),
        "capabilityManifestBinding": _build_capability_manifest_binding(root),
        "runEventLogBinding": _build_run_event_log_binding(root, run_event_log),
        "verifierResultBinding": _build_verifier_result_binding(root, verifier_result),
        "deliveryManifestBinding": _build_delivery_manifest_binding(root),
        "approvalRecordBinding": _build_approval_record_binding(root, approval_decision),
        "unlockConditions": _build_unlock_conditions(
            verifier_result, run_event_log, approval_decision
        ),
        "verifierExpectations": {
            "mustValidateSchema": True,
            "mustValidateTaskSpecBinding": True,
            "mustValidateCapabilityManifestBinding": True,
            "mustValidateRunEventLogBinding": True,
            "mustValidateVerifierResultBinding": True,
            "mustValidateDeliveryManifestBinding": True,
            "mustValidateApprovalRecordBinding": True,
            "mustValidatePermissionFlags": True,
            "mustEnforceEffectClassDecisions": True,
            "mustEnforceCapabilityRules": True,
            "mustEnforceUnlockConditions": True,
            "mustEnforceRevocationRules": True,
            "verdictOwner": VERIFIER_VERDICT_OWNER,
            "verdictDomain": list(VERDICT_DOMAIN),
            "creatorMustNotOwnVerdict": True,
        },
        "regressionWorkloadIsolation": {
            "reusesPhase7AdapterPolicyManifest": False,
            "reusesPolicyUnlockDenialFixture": False,
            "reusesRegressionResultArtifact": False,
            "reusesSendEmailCapability": False,
            "forbiddenFields": list(FORBIDDEN_REGRESSION_FIELDS),
        },
        "nonRegressionReusePath": list(NON_REGRESSION_REUSE_PATH),
        "coordinationBinding": _coordination_binding(root),
        "sourceArtifacts": [
            _artifact_source(role, relative_path, root)
            for role, relative_path in sorted(SOURCE_ROLE_TO_PATH.items())
        ],
        "invariants": list(INVARIANTS),
    }
    validate_policy_manifest(payload, root)
    return payload


def _validate_task_spec_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "PolicyManifestV1 taskSpecBinding",
        binding,
        [
            "taskSpecRef",
            "taskSpecSchemaVersion",
            "taskSpecEnvelopeSchemaVersion",
            "taskSpecId",
            "taskSpecContentHash",
        ],
    )
    if binding["taskSpecRef"] != TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH:
        raise ValueError(
            f"PolicyManifestV1 taskSpecBinding.taskSpecRef must equal "
            f"{TEST_EXECUTION_TASK_SPEC_ARTIFACT_PATH}"
        )
    if binding["taskSpecSchemaVersion"] != TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 taskSpecBinding.taskSpecSchemaVersion must equal "
            f"{TEST_EXECUTION_TASK_SPEC_SCHEMA_VERSION}; regression task spec reuse is forbidden"
        )
    if binding["taskSpecEnvelopeSchemaVersion"] != TASK_SPEC_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 taskSpecBinding.taskSpecEnvelopeSchemaVersion must equal "
            f"{TASK_SPEC_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["taskSpecId"] != TEST_EXECUTION_TASK_SPEC_ID:
        raise ValueError(
            f"PolicyManifestV1 taskSpecBinding.taskSpecId must equal {TEST_EXECUTION_TASK_SPEC_ID}"
        )
    full_path = root / binding["taskSpecRef"]
    if not full_path.is_file():
        raise ValueError(
            f"PolicyManifestV1 taskSpecBinding artifact missing: {binding['taskSpecRef']}"
        )
    if binding["taskSpecContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "PolicyManifestV1 taskSpecBinding.taskSpecContentHash must match the on-disk task spec"
        )


def _validate_capability_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "PolicyManifestV1 capabilityManifestBinding",
        binding,
        [
            "capabilityManifestRef",
            "capabilityManifestSchemaVersion",
            "capabilityManifestEnvelopeSchemaVersion",
            "capabilityManifestId",
            "capabilityManifestContentHash",
        ],
    )
    if binding["capabilityManifestRef"] != CAPABILITY_MANIFEST_ARTIFACT_PATH:
        raise ValueError(
            f"PolicyManifestV1 capabilityManifestBinding.capabilityManifestRef must equal "
            f"{CAPABILITY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["capabilityManifestSchemaVersion"] != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 capabilityManifestBinding.capabilityManifestSchemaVersion must equal "
            f"{CAPABILITY_MANIFEST_SCHEMA_VERSION}; regression capability catalog reuse is forbidden"
        )
    if binding["capabilityManifestEnvelopeSchemaVersion"] != CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 capabilityManifestBinding.capabilityManifestEnvelopeSchemaVersion must equal "
            f"{CAPABILITY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["capabilityManifestId"] != CAPABILITY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"PolicyManifestV1 capabilityManifestBinding.capabilityManifestId must equal "
            f"{CAPABILITY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["capabilityManifestRef"]
    if not full_path.is_file():
        raise ValueError(
            f"PolicyManifestV1 capabilityManifestBinding artifact missing: {binding['capabilityManifestRef']}"
        )
    if binding["capabilityManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "PolicyManifestV1 capabilityManifestBinding.capabilityManifestContentHash must match the on-disk capability manifest"
        )


def _validate_run_event_log_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "PolicyManifestV1 runEventLogBinding",
        binding,
        [
            "runEventLogRef",
            "runEventLogSchemaVersion",
            "runEventLogEnvelopeSchemaVersion",
            "runEventLogId",
            "runEventLogContentHash",
            "terminalState",
        ],
    )
    if binding["runEventLogRef"] != RUN_EVENT_LOG_ARTIFACT_PATH:
        raise ValueError(
            f"PolicyManifestV1 runEventLogBinding.runEventLogRef must equal "
            f"{RUN_EVENT_LOG_ARTIFACT_PATH}"
        )
    if binding["runEventLogSchemaVersion"] != RUN_EVENT_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 runEventLogBinding.runEventLogSchemaVersion must equal "
            f"{RUN_EVENT_LOG_SCHEMA_VERSION}; regression events.jsonl reuse is forbidden"
        )
    if binding["runEventLogEnvelopeSchemaVersion"] != RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 runEventLogBinding.runEventLogEnvelopeSchemaVersion must equal "
            f"{RUN_EVENT_LOG_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["runEventLogId"] != RUN_EVENT_LOG_ARTIFACT_ID:
        raise ValueError(
            f"PolicyManifestV1 runEventLogBinding.runEventLogId must equal "
            f"{RUN_EVENT_LOG_ARTIFACT_ID}"
        )
    full_path = root / binding["runEventLogRef"]
    if not full_path.is_file():
        raise ValueError(
            f"PolicyManifestV1 runEventLogBinding artifact missing: {binding['runEventLogRef']}"
        )
    if binding["runEventLogContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "PolicyManifestV1 runEventLogBinding.runEventLogContentHash must match the on-disk run event log"
        )
    run_event_log = _load_json(full_path)
    if binding["terminalState"] != run_event_log["terminalState"]:
        raise ValueError(
            "PolicyManifestV1 runEventLogBinding.terminalState must equal RunEventLogV1.terminalState"
        )


def _validate_verifier_result_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "PolicyManifestV1 verifierResultBinding",
        binding,
        [
            "verifierResultRef",
            "verifierResultSchemaVersion",
            "verifierResultEnvelopeSchemaVersion",
            "verifierResultId",
            "verifierResultContentHash",
            "verdict",
        ],
    )
    if binding["verifierResultRef"] != VERIFIER_RESULT_ARTIFACT_PATH:
        raise ValueError(
            f"PolicyManifestV1 verifierResultBinding.verifierResultRef must equal "
            f"{VERIFIER_RESULT_ARTIFACT_PATH}"
        )
    if binding["verifierResultSchemaVersion"] != VERIFIER_RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 verifierResultBinding.verifierResultSchemaVersion must equal "
            f"{VERIFIER_RESULT_SCHEMA_VERSION}; regression result artifact reuse is forbidden"
        )
    if binding["verifierResultEnvelopeSchemaVersion"] != VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 verifierResultBinding.verifierResultEnvelopeSchemaVersion must equal "
            f"{VERIFIER_RESULT_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["verifierResultId"] != VERIFIER_RESULT_ARTIFACT_ID:
        raise ValueError(
            f"PolicyManifestV1 verifierResultBinding.verifierResultId must equal "
            f"{VERIFIER_RESULT_ARTIFACT_ID}"
        )
    full_path = root / binding["verifierResultRef"]
    if not full_path.is_file():
        raise ValueError(
            f"PolicyManifestV1 verifierResultBinding artifact missing: {binding['verifierResultRef']}"
        )
    if binding["verifierResultContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "PolicyManifestV1 verifierResultBinding.verifierResultContentHash must match the on-disk verifier result"
        )
    if binding["verdict"] not in VERDICT_DOMAIN:
        raise ValueError(
            f"PolicyManifestV1 verifierResultBinding.verdict must be one of {VERDICT_DOMAIN}; "
            f"got {binding['verdict']}"
        )
    verifier_result = _load_json(full_path)
    if binding["verdict"] != verifier_result["verdict"]:
        raise ValueError(
            "PolicyManifestV1 verifierResultBinding.verdict must equal VerifierResultV1.verdict"
        )


def _validate_delivery_manifest_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "PolicyManifestV1 deliveryManifestBinding",
        binding,
        [
            "deliveryManifestRef",
            "deliveryManifestSchemaVersion",
            "deliveryManifestEnvelopeSchemaVersion",
            "deliveryManifestId",
            "deliveryManifestContentHash",
        ],
    )
    if binding["deliveryManifestRef"] != DELIVERY_MANIFEST_ARTIFACT_PATH:
        raise ValueError(
            f"PolicyManifestV1 deliveryManifestBinding.deliveryManifestRef must equal "
            f"{DELIVERY_MANIFEST_ARTIFACT_PATH}"
        )
    if binding["deliveryManifestSchemaVersion"] != DELIVERY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 deliveryManifestBinding.deliveryManifestSchemaVersion must equal "
            f"{DELIVERY_MANIFEST_SCHEMA_VERSION}; multi-agent-delivery-manifest reuse is forbidden"
        )
    if binding["deliveryManifestEnvelopeSchemaVersion"] != DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 deliveryManifestBinding.deliveryManifestEnvelopeSchemaVersion must equal "
            f"{DELIVERY_MANIFEST_ENVELOPE_SCHEMA_VERSION}"
        )
    if binding["deliveryManifestId"] != DELIVERY_MANIFEST_ARTIFACT_ID:
        raise ValueError(
            f"PolicyManifestV1 deliveryManifestBinding.deliveryManifestId must equal "
            f"{DELIVERY_MANIFEST_ARTIFACT_ID}"
        )
    full_path = root / binding["deliveryManifestRef"]
    if not full_path.is_file():
        raise ValueError(
            f"PolicyManifestV1 deliveryManifestBinding artifact missing: {binding['deliveryManifestRef']}"
        )
    if binding["deliveryManifestContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "PolicyManifestV1 deliveryManifestBinding.deliveryManifestContentHash must match the on-disk delivery manifest"
        )


def _validate_approval_record_binding(binding: dict[str, Any], root: Path) -> None:
    _require_fields(
        "PolicyManifestV1 approvalRecordBinding",
        binding,
        [
            "approvalRecordRef",
            "approvalRecordSchemaVersion",
            "approvalRecordContentHash",
            "currentDecision",
            "approvalGranted",
        ],
    )
    if binding["approvalRecordRef"] != HUMAN_APPROVAL_DECISION_ARTIFACT_PATH:
        raise ValueError(
            f"PolicyManifestV1 approvalRecordBinding.approvalRecordRef must equal "
            f"{HUMAN_APPROVAL_DECISION_ARTIFACT_PATH}"
        )
    if binding["approvalRecordSchemaVersion"] != "human-approval-decision-v1":
        raise ValueError(
            "PolicyManifestV1 approvalRecordBinding.approvalRecordSchemaVersion must be human-approval-decision-v1"
        )
    full_path = root / binding["approvalRecordRef"]
    if not full_path.is_file():
        raise ValueError(
            f"PolicyManifestV1 approvalRecordBinding artifact missing: {binding['approvalRecordRef']}"
        )
    if binding["approvalRecordContentHash"] != _stable_file_hash(full_path):
        raise ValueError(
            "PolicyManifestV1 approvalRecordBinding.approvalRecordContentHash must match the on-disk approval record"
        )
    decision = _load_json(full_path)
    decision_block = decision.get("decision", {})
    if binding["currentDecision"] != decision_block.get("decision"):
        raise ValueError(
            "PolicyManifestV1 approvalRecordBinding.currentDecision must equal HumanApprovalDecisionV1.decision.decision"
        )
    if binding["approvalGranted"] is not (decision_block.get("approvalGranted") is True):
        raise ValueError(
            "PolicyManifestV1 approvalRecordBinding.approvalGranted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )


def _validate_effect_classes(effect_classes: list[Any]) -> None:
    if not isinstance(effect_classes, list) or len(effect_classes) != len(EFFECT_CLASS_DOMAIN):
        raise ValueError(
            f"PolicyManifestV1 effectClasses must be a list of length {len(EFFECT_CLASS_DOMAIN)}"
        )
    seen: set[str] = set()
    for index, entry in enumerate(effect_classes):
        if not isinstance(entry, dict):
            raise ValueError("PolicyManifestV1 effectClasses entries must be objects")
        _require_fields(
            f"PolicyManifestV1 effectClass[{index}]",
            entry,
            ["schemaVersion", "className", "decision", "reason"],
        )
        if entry["schemaVersion"] != POLICY_EFFECT_CLASS_SCHEMA_VERSION:
            raise ValueError(
                f"PolicyManifestV1 effectClass[{index}].schemaVersion must be "
                f"{POLICY_EFFECT_CLASS_SCHEMA_VERSION}"
            )
        if entry["className"] not in EFFECT_CLASS_DOMAIN:
            raise ValueError(
                f"PolicyManifestV1 effectClass[{index}].className must be one of {EFFECT_CLASS_DOMAIN}"
            )
        if entry["className"] in seen:
            raise ValueError(
                f"PolicyManifestV1 duplicate effectClass.className: {entry['className']}"
            )
        seen.add(entry["className"])
        if entry["decision"] not in DECISION_DOMAIN:
            raise ValueError(
                f"PolicyManifestV1 effectClass[{index}].decision must be one of {DECISION_DOMAIN}"
            )
        expected_decision = (
            "allow" if entry["className"] in ALLOW_EFFECT_CLASSES else "deny"
        )
        if entry["decision"] != expected_decision:
            raise ValueError(
                f"PolicyManifestV1 effectClass[{index}].decision must be {expected_decision} "
                f"for class {entry['className']}"
            )
    if seen != set(EFFECT_CLASS_DOMAIN):
        raise ValueError(
            f"PolicyManifestV1 effectClasses must cover the full effect-class domain {sorted(EFFECT_CLASS_DOMAIN)}"
        )


def _validate_policy_rules(policy_rules: list[Any]) -> None:
    if not isinstance(policy_rules, list) or not policy_rules:
        raise ValueError("PolicyManifestV1 policyRules must be a non-empty list")
    capability_seen: set[str] = set()
    deny_class_seen: set[str] = set()
    permission_flag_seen: set[str] = set()
    rule_ids: set[str] = set()
    for index, rule in enumerate(policy_rules):
        if not isinstance(rule, dict):
            raise ValueError("PolicyManifestV1 policyRules entries must be objects")
        _require_fields(
            f"PolicyManifestV1 policyRule[{index}]",
            rule,
            ["schemaVersion", "ruleId", "ruleKind", "decision", "reason"],
        )
        if rule["schemaVersion"] != POLICY_RULE_SCHEMA_VERSION:
            raise ValueError(
                f"PolicyManifestV1 policyRule[{index}].schemaVersion must be "
                f"{POLICY_RULE_SCHEMA_VERSION}"
            )
        rule_id = rule["ruleId"]
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError(
                f"PolicyManifestV1 policyRule[{index}].ruleId must be a non-empty string"
            )
        if rule_id in rule_ids:
            raise ValueError(f"PolicyManifestV1 duplicate policyRule.ruleId: {rule_id}")
        rule_ids.add(rule_id)
        kind = rule["ruleKind"]
        if kind not in {"capability_allow", "effect_class_deny", "permission_flag_deny"}:
            raise ValueError(
                f"PolicyManifestV1 policyRule[{index}].ruleKind must be one of "
                "capability_allow / effect_class_deny / permission_flag_deny"
            )
        if kind == "capability_allow":
            _require_fields(
                f"PolicyManifestV1 policyRule[{index}]",
                rule,
                ["appliesToCapability", "effectClass"],
            )
            if rule["decision"] != "allow":
                raise ValueError(
                    f"PolicyManifestV1 policyRule[{index}] capability_allow.decision must be allow"
                )
            cap_name = rule["appliesToCapability"]
            if cap_name not in CAPABILITY_NAMES:
                raise ValueError(
                    f"PolicyManifestV1 policyRule[{index}].appliesToCapability must be one of {CAPABILITY_NAMES}; "
                    f"got {cap_name}"
                )
            if cap_name in capability_seen:
                raise ValueError(
                    f"PolicyManifestV1 duplicate capability_allow rule for capability: {cap_name}"
                )
            capability_seen.add(cap_name)
            expected_class = CAPABILITY_TO_EFFECT_CLASS.get(cap_name)
            if rule["effectClass"] != expected_class:
                raise ValueError(
                    f"PolicyManifestV1 policyRule[{index}].effectClass for capability {cap_name} "
                    f"must be {expected_class}; got {rule['effectClass']}"
                )
            if rule["effectClass"] not in ALLOW_EFFECT_CLASSES:
                raise ValueError(
                    f"PolicyManifestV1 policyRule[{index}].effectClass must be one of {ALLOW_EFFECT_CLASSES}"
                )
        elif kind == "effect_class_deny":
            _require_fields(
                f"PolicyManifestV1 policyRule[{index}]",
                rule,
                ["effectClass"],
            )
            if rule["decision"] != "deny":
                raise ValueError(
                    f"PolicyManifestV1 policyRule[{index}] effect_class_deny.decision must be deny"
                )
            class_name = rule["effectClass"]
            if class_name not in DENY_EFFECT_CLASSES:
                raise ValueError(
                    f"PolicyManifestV1 policyRule[{index}].effectClass for effect_class_deny must be one of "
                    f"{DENY_EFFECT_CLASSES}; got {class_name}"
                )
            if class_name in deny_class_seen:
                raise ValueError(
                    f"PolicyManifestV1 duplicate effect_class_deny rule for class: {class_name}"
                )
            deny_class_seen.add(class_name)
        else:
            _require_fields(
                f"PolicyManifestV1 policyRule[{index}]",
                rule,
                ["permissionFlag"],
            )
            if rule["decision"] != "deny":
                raise ValueError(
                    f"PolicyManifestV1 policyRule[{index}] permission_flag_deny.decision must be deny"
                )
            flag = rule["permissionFlag"]
            if flag not in PERMISSION_FLAG_DOMAIN:
                raise ValueError(
                    f"PolicyManifestV1 policyRule[{index}].permissionFlag must be one of "
                    f"{PERMISSION_FLAG_DOMAIN}; got {flag}"
                )
            if flag in permission_flag_seen:
                raise ValueError(
                    f"PolicyManifestV1 duplicate permission_flag_deny rule for flag: {flag}"
                )
            permission_flag_seen.add(flag)
    if capability_seen != set(CAPABILITY_NAMES):
        missing = sorted(set(CAPABILITY_NAMES) - capability_seen)
        raise ValueError(
            f"PolicyManifestV1 policyRules must declare a capability_allow rule for every CapabilityManifestV1 capability; "
            f"missing: {missing}"
        )
    if deny_class_seen != set(DENY_EFFECT_CLASSES):
        missing = sorted(set(DENY_EFFECT_CLASSES) - deny_class_seen)
        raise ValueError(
            f"PolicyManifestV1 policyRules must declare an effect_class_deny rule for every deny effect class; "
            f"missing: {missing}"
        )
    if permission_flag_seen != set(PERMISSION_FLAG_DOMAIN):
        missing = sorted(set(PERMISSION_FLAG_DOMAIN) - permission_flag_seen)
        raise ValueError(
            f"PolicyManifestV1 policyRules must declare a permission_flag_deny rule for every permission flag; "
            f"missing: {missing}"
        )


def _validate_revocation_rules(revocation_rules: list[Any]) -> None:
    if not isinstance(revocation_rules, list) or len(revocation_rules) < 5:
        raise ValueError(
            "PolicyManifestV1 revocationRules must declare at least five workload-independent triggers"
        )
    seen_ids: set[str] = set()
    seen_triggers: set[str] = set()
    expected_triggers = {entry["trigger"] for entry in REVOCATION_RULE_BLUEPRINT}
    for index, rule in enumerate(revocation_rules):
        if not isinstance(rule, dict):
            raise ValueError("PolicyManifestV1 revocationRules entries must be objects")
        _require_fields(
            f"PolicyManifestV1 revocationRule[{index}]",
            rule,
            ["schemaVersion", "ruleId", "trigger", "watchedField", "action", "reason"],
        )
        if rule["schemaVersion"] != POLICY_REVOCATION_RULE_SCHEMA_VERSION:
            raise ValueError(
                f"PolicyManifestV1 revocationRule[{index}].schemaVersion must be "
                f"{POLICY_REVOCATION_RULE_SCHEMA_VERSION}"
            )
        if rule["action"] != "revoke_all_unlocks":
            raise ValueError(
                f"PolicyManifestV1 revocationRule[{index}].action must be revoke_all_unlocks"
            )
        rule_id = rule["ruleId"]
        if rule_id in seen_ids:
            raise ValueError(f"PolicyManifestV1 duplicate revocationRule.ruleId: {rule_id}")
        seen_ids.add(rule_id)
        seen_triggers.add(rule["trigger"])
    missing_triggers = expected_triggers - seen_triggers
    if missing_triggers:
        raise ValueError(
            f"PolicyManifestV1 revocationRules must cover triggers {sorted(expected_triggers)}; "
            f"missing: {sorted(missing_triggers)}"
        )


def _validate_unlock_conditions(
    unlock: dict[str, Any],
    verifier_result: dict[str, Any],
    run_event_log: dict[str, Any],
    approval_decision: dict[str, Any],
) -> None:
    _require_fields(
        "PolicyManifestV1 unlockConditions",
        unlock,
        [
            "requiredVerdict",
            "currentVerdict",
            "verdictOwner",
            "requiredTerminalRunState",
            "currentTerminalRunState",
            "requiredApprovalDecision",
            "currentApprovalDecision",
            "approvalGranted",
            "approvalRecordRef",
            "approvalRecordSchemaVersion",
            "unlocked",
        ],
    )
    if unlock["requiredVerdict"] != REQUIRED_VERDICT_FOR_UNLOCK:
        raise ValueError(
            f"PolicyManifestV1 unlockConditions.requiredVerdict must be {REQUIRED_VERDICT_FOR_UNLOCK}"
        )
    if unlock["currentVerdict"] != verifier_result["verdict"]:
        raise ValueError(
            "PolicyManifestV1 unlockConditions.currentVerdict must equal VerifierResultV1.verdict"
        )
    if unlock["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"PolicyManifestV1 unlockConditions.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if unlock["requiredTerminalRunState"] != REQUIRED_TERMINAL_RUN_STATE:
        raise ValueError(
            f"PolicyManifestV1 unlockConditions.requiredTerminalRunState must be {REQUIRED_TERMINAL_RUN_STATE}"
        )
    if unlock["currentTerminalRunState"] != run_event_log["terminalState"]:
        raise ValueError(
            "PolicyManifestV1 unlockConditions.currentTerminalRunState must equal RunEventLogV1.terminalState"
        )
    if unlock["requiredApprovalDecision"] != REQUIRED_APPROVAL_DECISION:
        raise ValueError(
            f"PolicyManifestV1 unlockConditions.requiredApprovalDecision must be {REQUIRED_APPROVAL_DECISION}"
        )
    decision_block = approval_decision.get("decision", {})
    expected_decision = decision_block.get("decision")
    expected_granted = decision_block.get("approvalGranted") is True
    if unlock["currentApprovalDecision"] != expected_decision:
        raise ValueError(
            "PolicyManifestV1 unlockConditions.currentApprovalDecision must equal HumanApprovalDecisionV1.decision.decision"
        )
    if unlock["approvalGranted"] is not expected_granted:
        raise ValueError(
            "PolicyManifestV1 unlockConditions.approvalGranted must equal HumanApprovalDecisionV1.decision.approvalGranted"
        )
    if unlock["approvalRecordRef"] != HUMAN_APPROVAL_DECISION_ARTIFACT_PATH:
        raise ValueError(
            f"PolicyManifestV1 unlockConditions.approvalRecordRef must equal {HUMAN_APPROVAL_DECISION_ARTIFACT_PATH}"
        )
    expected_unlocked = (
        unlock["currentVerdict"] == REQUIRED_VERDICT_FOR_UNLOCK
        and unlock["currentTerminalRunState"] == REQUIRED_TERMINAL_RUN_STATE
        and unlock["approvalGranted"] is True
    )
    if unlock["unlocked"] is not expected_unlocked:
        raise ValueError(
            "PolicyManifestV1 unlockConditions.unlocked must be true only when verdict, run terminal state, and approval all match"
        )


def _validate_source_artifacts(sources: list[Any], root: Path) -> None:
    if not isinstance(sources, list) or not sources:
        raise ValueError("PolicyManifestV1 sourceArtifacts must be a non-empty list")
    expected_paths = dict(SOURCE_ROLE_TO_PATH)
    seen_roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("PolicyManifestV1 sourceArtifacts entries must be objects")
        _require_fields(
            "PolicyManifestV1 source artifact",
            source,
            ["role", "path", "contentHash"],
        )
        role = source["role"]
        path = source["path"]
        if role not in expected_paths:
            raise ValueError(
                f"PolicyManifestV1 sourceArtifacts contains unexpected role: {role}"
            )
        if role in seen_roles:
            raise ValueError(
                f"PolicyManifestV1 sourceArtifacts contains duplicate role: {role}"
            )
        seen_roles.add(role)
        if path != expected_paths[role]:
            raise ValueError(
                f"PolicyManifestV1 sourceArtifacts role {role} must point to {expected_paths[role]}"
            )
        _validate_relative_posix_path(path)
        full_path = root / path
        if not full_path.is_file():
            raise ValueError(
                f"PolicyManifestV1 source artifact does not exist: {path}"
            )
        if _stable_file_hash(full_path) != source["contentHash"]:
            raise ValueError(
                f"PolicyManifestV1 source hash mismatch for {path}"
            )
    if seen_roles != set(expected_paths):
        raise ValueError(
            f"PolicyManifestV1 sourceArtifacts must cover roles {sorted(expected_paths)}"
        )


def validate_policy_manifest(manifest: dict[str, Any], root: Path) -> None:
    _require_fields(
        "PolicyManifestV1",
        manifest,
        [
            "schemaVersion",
            "artifactEnvelopeSchemaVersion",
            "id",
            "generatedAt",
            "kind",
            "scope",
            "workloadType",
            "workloadCategory",
            "creatorAgent",
            "policyOwner",
            "verifierVerdictOwner",
            "policyRuleSchemaVersion",
            "policyEffectClassSchemaVersion",
            "policyRevocationRuleSchemaVersion",
            "verdictDomain",
            "decisionDomain",
            "permissionFlagDomain",
            "permissionFlags",
            "effectClassDomain",
            "allowEffectClasses",
            "denyEffectClasses",
            "effectClasses",
            "policyRules",
            "policyRuleCount",
            "revocationRules",
            "taskSpecBinding",
            "capabilityManifestBinding",
            "runEventLogBinding",
            "verifierResultBinding",
            "deliveryManifestBinding",
            "approvalRecordBinding",
            "unlockConditions",
            "verifierExpectations",
            "regressionWorkloadIsolation",
            "nonRegressionReusePath",
            "coordinationBinding",
            "sourceArtifacts",
            "invariants",
        ],
    )
    if manifest["schemaVersion"] != POLICY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 schemaVersion must be {POLICY_MANIFEST_SCHEMA_VERSION}"
        )
    if manifest["artifactEnvelopeSchemaVersion"] != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 artifactEnvelopeSchemaVersion must be {ARTIFACT_ENVELOPE_SCHEMA_VERSION}"
        )
    if manifest["id"] != ARTIFACT_ID:
        raise ValueError(f"PolicyManifestV1 id must be {ARTIFACT_ID}")
    if manifest["generatedAt"] != GENERATED_AT:
        raise ValueError(f"PolicyManifestV1 generatedAt must be {GENERATED_AT}")
    if manifest["kind"] != ARTIFACT_KIND:
        raise ValueError(f"PolicyManifestV1 kind must be {ARTIFACT_KIND}")
    if manifest["scope"] != SCOPE:
        raise ValueError(f"PolicyManifestV1 scope must be {SCOPE}")
    if manifest["workloadType"] != WORKLOAD_TYPE:
        raise ValueError(
            f"PolicyManifestV1 workloadType must be {WORKLOAD_TYPE}; "
            f"regression workload reuse is forbidden"
        )
    if manifest["workloadCategory"] != WORKLOAD_CATEGORY:
        raise ValueError(
            f"PolicyManifestV1 workloadCategory must be {WORKLOAD_CATEGORY}"
        )
    if manifest["creatorAgent"] != CREATOR_AGENT:
        raise ValueError(
            f"PolicyManifestV1 creatorAgent must be {CREATOR_AGENT}"
        )
    if manifest["policyOwner"] != POLICY_OWNER:
        raise ValueError(
            f"PolicyManifestV1 policyOwner must be {POLICY_OWNER}"
        )
    if manifest["verifierVerdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"PolicyManifestV1 verifierVerdictOwner must be {VERIFIER_VERDICT_OWNER}; "
            f"creator must not own the verdict"
        )
    if manifest["policyRuleSchemaVersion"] != POLICY_RULE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 policyRuleSchemaVersion must be {POLICY_RULE_SCHEMA_VERSION}"
        )
    if manifest["policyEffectClassSchemaVersion"] != POLICY_EFFECT_CLASS_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 policyEffectClassSchemaVersion must be {POLICY_EFFECT_CLASS_SCHEMA_VERSION}"
        )
    if manifest["policyRevocationRuleSchemaVersion"] != POLICY_REVOCATION_RULE_SCHEMA_VERSION:
        raise ValueError(
            f"PolicyManifestV1 policyRevocationRuleSchemaVersion must be {POLICY_REVOCATION_RULE_SCHEMA_VERSION}"
        )
    if manifest["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"PolicyManifestV1 verdictDomain must equal {VERDICT_DOMAIN}"
        )
    if manifest["decisionDomain"] != list(DECISION_DOMAIN):
        raise ValueError(
            f"PolicyManifestV1 decisionDomain must equal {DECISION_DOMAIN}"
        )
    if manifest["permissionFlagDomain"] != list(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"PolicyManifestV1 permissionFlagDomain must equal {PERMISSION_FLAG_DOMAIN}"
        )
    if manifest["effectClassDomain"] != list(EFFECT_CLASS_DOMAIN):
        raise ValueError(
            f"PolicyManifestV1 effectClassDomain must equal {EFFECT_CLASS_DOMAIN}"
        )
    if manifest["allowEffectClasses"] != list(ALLOW_EFFECT_CLASSES):
        raise ValueError(
            f"PolicyManifestV1 allowEffectClasses must equal {ALLOW_EFFECT_CLASSES}"
        )
    if manifest["denyEffectClasses"] != list(DENY_EFFECT_CLASSES):
        raise ValueError(
            f"PolicyManifestV1 denyEffectClasses must equal {DENY_EFFECT_CLASSES}"
        )

    flags = manifest["permissionFlags"]
    if not isinstance(flags, dict) or set(flags) != set(PERMISSION_FLAG_DOMAIN):
        raise ValueError(
            f"PolicyManifestV1 permissionFlags must declare every flag in {PERMISSION_FLAG_DOMAIN}"
        )
    for flag in PERMISSION_FLAG_DOMAIN:
        if flags[flag] is not False:
            raise ValueError(
                f"PolicyManifestV1 permissionFlags.{flag} must be false"
            )

    _validate_effect_classes(manifest["effectClasses"])
    _validate_policy_rules(manifest["policyRules"])
    if manifest["policyRuleCount"] != len(manifest["policyRules"]):
        raise ValueError(
            "PolicyManifestV1 policyRuleCount must equal len(policyRules)"
        )
    _validate_revocation_rules(manifest["revocationRules"])

    _validate_task_spec_binding(manifest["taskSpecBinding"], root)
    _validate_capability_manifest_binding(manifest["capabilityManifestBinding"], root)
    _validate_run_event_log_binding(manifest["runEventLogBinding"], root)
    _validate_verifier_result_binding(manifest["verifierResultBinding"], root)
    _validate_delivery_manifest_binding(manifest["deliveryManifestBinding"], root)
    _validate_approval_record_binding(manifest["approvalRecordBinding"], root)

    verifier_result = _load_json(root / VERIFIER_RESULT_ARTIFACT_PATH)
    run_event_log = _load_json(root / RUN_EVENT_LOG_ARTIFACT_PATH)
    approval_decision = _load_json(root / HUMAN_APPROVAL_DECISION_ARTIFACT_PATH)
    _validate_unlock_conditions(
        manifest["unlockConditions"], verifier_result, run_event_log, approval_decision
    )

    verifier = manifest["verifierExpectations"]
    _require_fields(
        "PolicyManifestV1 verifierExpectations",
        verifier,
        [*REQUIRED_VERIFIER_FLAGS, "verdictOwner", "verdictDomain"],
    )
    for flag in REQUIRED_VERIFIER_FLAGS:
        if verifier[flag] is not True:
            raise ValueError(
                f"PolicyManifestV1 verifierExpectations.{flag} must be true"
            )
    if verifier["verdictOwner"] != VERIFIER_VERDICT_OWNER:
        raise ValueError(
            f"PolicyManifestV1 verifierExpectations.verdictOwner must be {VERIFIER_VERDICT_OWNER}"
        )
    if verifier["verdictDomain"] != list(VERDICT_DOMAIN):
        raise ValueError(
            f"PolicyManifestV1 verifierExpectations.verdictDomain must equal {VERDICT_DOMAIN}"
        )

    isolation = manifest["regressionWorkloadIsolation"]
    _require_fields(
        "PolicyManifestV1 regressionWorkloadIsolation",
        isolation,
        [
            "reusesPhase7AdapterPolicyManifest",
            "reusesPolicyUnlockDenialFixture",
            "reusesRegressionResultArtifact",
            "reusesSendEmailCapability",
            "forbiddenFields",
        ],
    )
    if isolation["reusesPhase7AdapterPolicyManifest"] is not False:
        raise ValueError(
            "PolicyManifestV1 must not reuse phase7_adapter_policy_manifest.json"
        )
    if isolation["reusesPolicyUnlockDenialFixture"] is not False:
        raise ValueError(
            "PolicyManifestV1 must not reuse post_mvp_policy_unlock_request_denied.json"
        )
    if isolation["reusesRegressionResultArtifact"] is not False:
        raise ValueError(
            "PolicyManifestV1 must not reuse RegressionResultArtifactV1"
        )
    if isolation["reusesSendEmailCapability"] is not False:
        raise ValueError(
            "PolicyManifestV1 must not reuse the send_email capability"
        )
    if isolation["forbiddenFields"] != FORBIDDEN_REGRESSION_FIELDS:
        raise ValueError(
            f"PolicyManifestV1 forbiddenFields must equal {FORBIDDEN_REGRESSION_FIELDS}"
        )

    serialized = json.dumps(manifest, sort_keys=True)
    for term in FORBIDDEN_REGRESSION_FIELDS:
        allowed_count = sum(1 for value in FORBIDDEN_REGRESSION_FIELDS if value == term)
        if serialized.count(f'"{term}"') > allowed_count:
            raise ValueError(
                f"PolicyManifestV1 must not embed regression/email field {term} "
                f"outside forbiddenFields"
            )

    reuse_path = manifest["nonRegressionReusePath"]
    if not isinstance(reuse_path, list) or set(reuse_path) != set(NON_REGRESSION_REUSE_PATH):
        raise ValueError(
            f"PolicyManifestV1 nonRegressionReusePath must equal {NON_REGRESSION_REUSE_PATH}"
        )

    coordination = manifest["coordinationBinding"]
    if not isinstance(coordination, dict) or set(coordination) != set(COORDINATION_BINDING_PATHS):
        raise ValueError(
            "PolicyManifestV1 coordinationBinding must include "
            f"{sorted(COORDINATION_BINDING_PATHS)}"
        )
    for field, expected_path in COORDINATION_BINDING_PATHS.items():
        if coordination[field] != expected_path:
            raise ValueError(
                f"PolicyManifestV1 coordinationBinding.{field} must equal {expected_path}"
            )

    _validate_source_artifacts(manifest["sourceArtifacts"], root)

    invariants = manifest["invariants"]
    if not isinstance(invariants, list) or len(invariants) < 7:
        raise ValueError(
            "PolicyManifestV1 invariants must declare at least seven workload-independent statements"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="policy-manifest")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.out is None and args.validate is None:
        raise ValueError("No action requested: pass --out and/or --validate")
    if args.out is not None:
        manifest = build_policy_manifest(root)
        _write_json(args.out, manifest)
        print(f"Wrote PolicyManifestV1 artifact to {args.out}.")
    if args.validate is not None:
        manifest = _load_json(args.validate)
        validate_policy_manifest(manifest, root)
        print(f"Validated PolicyManifestV1 artifact {args.validate}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

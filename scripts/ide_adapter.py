from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


IDE_ADAPTER_CONTRACT_SCHEMA_VERSION = "ide-adapter-contract-v1"
IDE_ADAPTER_CAPABILITY_SCHEMA_VERSION = "ide-adapter-capability-v1"
WORKSPACE_OBSERVATION_SCHEMA_VERSION = "workspace-observation-v1"
IDE_APPROVAL_HANDOFF_MANIFEST_SCHEMA_VERSION = "ide-approval-handoff-manifest-v1"
GENERATED_AT = "2026-05-12T14:39:00Z"

CONTRACT_ID = "phase8-static-ide-adapter-contract"
OBSERVATION_ID = "phase8-static-workspace-observation-all_passed"
APPROVAL_HANDOFF_MANIFEST_ID = "phase8-static-ide-approval-handoff-all_passed"
CONTRACT_ARTIFACT_PATH = "artifacts/ide_adapter/phase8_ide_adapter_contract.json"
OBSERVATION_ARTIFACT_PATH = "artifacts/ide_adapter/phase8_workspace_observation.json"
APPROVAL_HANDOFF_ARTIFACT_PATH = "artifacts/ide_adapter/phase8_ide_approval_handoff_manifest.json"
ADAPTER_REF = "ide-adapter://phase8/cursor-placeholder"
CAPABILITY_URI_PREFIX = "ide-adapter://phase8/"

CAPABILITY_NAMES = [
    "ide.workspace.inspect",
    "ide.current_file.read",
    "ide.diagnostics.read",
    "ide.open_file",
    "ide.diff_view.open",
    "ide.terminal.request",
    "ide.approval.request",
]

READ_ONLY_CAPABILITIES = {
    "ide.workspace.inspect",
    "ide.current_file.read",
    "ide.diagnostics.read",
    "ide.approval.request",
}
APPROVAL_REQUIRED_CAPABILITIES = {
    "ide.open_file",
    "ide.diff_view.open",
    "ide.terminal.request",
}

CAPABILITY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "ide.workspace.inspect": {
        "category": "workspace",
        "permission": "read",
        "sideEffectRisk": "workspace_metadata_observation",
        "approvalRequired": False,
        "inputContract": {
            "schema": "IdeWorkspaceInspectInputV1",
            "required": ["workspaceRef"],
            "properties": {"workspaceRef": "string:workspace-ref"},
        },
        "observationContract": {
            "schema": "WorkspaceObservationV1",
            "produces": ["workspaceObservation"],
            "properties": {"workspaceObservation": WORKSPACE_OBSERVATION_SCHEMA_VERSION},
        },
    },
    "ide.current_file.read": {
        "category": "workspace",
        "permission": "read",
        "sideEffectRisk": "current_editor_metadata_observation",
        "approvalRequired": False,
        "inputContract": {
            "schema": "IdeCurrentFileReadInputV1",
            "required": ["workspaceRef"],
            "properties": {"workspaceRef": "string:workspace-ref"},
        },
        "observationContract": {
            "schema": "IdeCurrentFileObservationV1",
            "produces": ["currentFileRef"],
            "properties": {"currentFileRef": "string:path"},
        },
    },
    "ide.diagnostics.read": {
        "category": "diagnostics",
        "permission": "read",
        "sideEffectRisk": "diagnostics_observation",
        "approvalRequired": False,
        "inputContract": {
            "schema": "IdeDiagnosticsReadInputV1",
            "required": ["workspaceRef"],
            "properties": {"workspaceRef": "string:workspace-ref"},
        },
        "observationContract": {
            "schema": "IdeDiagnosticsObservationV1",
            "produces": ["diagnosticsRef"],
            "properties": {"diagnosticsRef": "string:observation-ref"},
        },
    },
    "ide.open_file": {
        "category": "editor",
        "permission": "write",
        "sideEffectRisk": "ide_ui_state_change",
        "approvalRequired": True,
        "inputContract": {
            "schema": "IdeOpenFileInputV1",
            "required": ["workspaceRef", "path"],
            "properties": {
                "workspaceRef": "string:workspace-ref",
                "path": "string:repo-relative-path",
            },
        },
        "observationContract": {
            "schema": "IdeUiActionObservationV1",
            "produces": ["editorStateRef"],
            "properties": {"editorStateRef": "string:observation-ref"},
        },
    },
    "ide.diff_view.open": {
        "category": "diff",
        "permission": "write",
        "sideEffectRisk": "ide_ui_state_change",
        "approvalRequired": True,
        "inputContract": {
            "schema": "IdeDiffViewOpenInputV1",
            "required": ["workspaceRef", "artifactRef"],
            "properties": {
                "workspaceRef": "string:workspace-ref",
                "artifactRef": "string:artifact-ref",
            },
        },
        "observationContract": {
            "schema": "IdeUiActionObservationV1",
            "produces": ["diffViewRef"],
            "properties": {"diffViewRef": "string:observation-ref"},
        },
    },
    "ide.terminal.request": {
        "category": "terminal",
        "permission": "dangerous",
        "sideEffectRisk": "process_or_filesystem_mutation",
        "approvalRequired": True,
        "inputContract": {
            "schema": "IdeTerminalRequestInputV1",
            "required": ["workspaceRef", "command"],
            "properties": {
                "workspaceRef": "string:workspace-ref",
                "command": "string:approved-command",
            },
        },
        "observationContract": {
            "schema": "IdeTerminalRequestObservationV1",
            "produces": ["approvalRequestRef"],
            "properties": {"approvalRequestRef": "string:human-gate-ref"},
        },
    },
    "ide.approval.request": {
        "category": "human_gate",
        "permission": "read",
        "sideEffectRisk": "approval_prompt_only",
        "approvalRequired": False,
        "inputContract": {
            "schema": "IdeApprovalRequestInputV1",
            "required": ["runRef", "approvalPoint"],
            "properties": {
                "runRef": "string:run-ref",
                "approvalPoint": "string:approval-point",
            },
        },
        "observationContract": {
            "schema": "IdeApprovalObservationV1",
            "produces": ["approvalDecisionRef"],
            "properties": {"approvalDecisionRef": "string:human-decision-ref"},
        },
    },
}


def ide_capability_ref(name: str) -> str:
    return f"{CAPABILITY_URI_PREFIX}{name}"


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
        raise ValueError(f"IDEAdapter paths must be POSIX relative repository paths: {path}")


def _artifact_source(role: str, path: Path, root: Path) -> dict[str, Any]:
    relative_path = path.resolve().relative_to(root.resolve()).as_posix()
    return {
        "role": role,
        "path": relative_path,
        "contentHash": _stable_file_hash(path),
    }


def _capabilities_by_name(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        capability["name"]: capability
        for capability in contract.get("capabilities", [])
        if isinstance(capability, dict) and "name" in capability
    }


def build_ide_adapter_contract() -> dict[str, Any]:
    capabilities = []
    for name in CAPABILITY_NAMES:
        definition = deepcopy(CAPABILITY_DEFINITIONS[name])
        definition.update(
            {
                "schemaVersion": IDE_ADAPTER_CAPABILITY_SCHEMA_VERSION,
                "name": name,
                "ref": ide_capability_ref(name),
                "executionMode": "contract_only",
                "implemented": False,
                "externalSideEffectAllowed": False,
            }
        )
        capabilities.append(definition)

    return {
        "schemaVersion": IDE_ADAPTER_CONTRACT_SCHEMA_VERSION,
        "id": CONTRACT_ID,
        "phase": "phase8",
        "scope": "ide_adapter_boundary",
        "mode": "static_contract_only",
        "adapterRef": ADAPTER_REF,
        "buildVsIntegrate": {
            "build": [
                "IDEAdapterContractV1 schema",
                "WorkspaceObservationV1 artifact contract",
                "machine validation for read-only workspace observation and no IDE side effects",
            ],
            "integrateLater": [
                "real Cursor/IDE extension bridge",
                "diagnostics streaming",
                "terminal execution",
                "diff view and approval UI",
                "workspace registry service",
            ],
        },
        "adapterBoundary": {
            "layer": "Interaction Plane / IDE Adapter",
            "adapterResponsibilities": [
                "expose IDE workspace, current file, diagnostics, diff view, terminal request, and approval surfaces behind capability contracts",
                "emit workspace observations with stable repository-relative source refs",
                "avoid deciding whether an engineering task is complete",
            ],
            "osResponsibilities": [
                "own TaskSpec, RunControl, ContextPack, Evidence, Verifier, Policy, and Delivery semantics",
                "decide whether IDE observations are sufficient evidence for a task",
                "require approval before any real IDE UI, terminal, or workspace side effect executes",
            ],
            "mvpInvariant": "Phase 8 MVP declares IDE adapter boundaries only; it does not open files, run terminals, mutate workspace state, or call a real IDE provider.",
        },
        "capabilities": capabilities,
        "workspaceObservationContract": {
            "schemaVersion": WORKSPACE_OBSERVATION_SCHEMA_VERSION,
            "allowedObservationKinds": ["workspace_snapshot"],
            "requiredBindings": ["workspaceRef", "sourceArtifacts", "capabilityRef"],
            "taskVerdictOwner": "verifier-runtime-v1",
        },
        "policy": {
            "externalSideEffectsAllowed": False,
            "realIdeExecutionAllowed": False,
            "workspaceMutationAllowed": False,
            "terminalExecutionAllowed": False,
            "dangerousCapabilitiesRequireApproval": True,
        },
    }


def validate_ide_adapter_contract(contract: dict[str, Any]) -> None:
    _require_fields(
        "IDEAdapterContractV1",
        contract,
        [
            "schemaVersion",
            "id",
            "phase",
            "scope",
            "mode",
            "adapterRef",
            "buildVsIntegrate",
            "adapterBoundary",
            "capabilities",
            "workspaceObservationContract",
            "policy",
        ],
    )
    if contract["schemaVersion"] != IDE_ADAPTER_CONTRACT_SCHEMA_VERSION:
        raise ValueError(f"IDEAdapterContractV1 schemaVersion must be {IDE_ADAPTER_CONTRACT_SCHEMA_VERSION}")
    if contract["id"] != CONTRACT_ID:
        raise ValueError(f"IDEAdapterContractV1 id must be {CONTRACT_ID}")
    if contract["phase"] != "phase8":
        raise ValueError("IDEAdapterContractV1 phase must be phase8")
    if contract["mode"] != "static_contract_only":
        raise ValueError("IDEAdapterContractV1 mode must be static_contract_only")
    if contract["adapterRef"] != ADAPTER_REF:
        raise ValueError(f"IDEAdapterContractV1 adapterRef must be {ADAPTER_REF}")

    policy = contract["policy"]
    _require_fields(
        "IDEAdapterContractV1 policy",
        policy,
        [
            "externalSideEffectsAllowed",
            "realIdeExecutionAllowed",
            "workspaceMutationAllowed",
            "terminalExecutionAllowed",
            "dangerousCapabilitiesRequireApproval",
        ],
    )
    if policy["externalSideEffectsAllowed"] is not False:
        raise ValueError("IDEAdapterContractV1 policy must disallow external side effects")
    if policy["realIdeExecutionAllowed"] is not False:
        raise ValueError("IDEAdapterContractV1 policy must disallow real IDE execution")
    if policy["workspaceMutationAllowed"] is not False:
        raise ValueError("IDEAdapterContractV1 policy must disallow workspace mutation")
    if policy["terminalExecutionAllowed"] is not False:
        raise ValueError("IDEAdapterContractV1 policy must disallow terminal execution")
    if policy["dangerousCapabilitiesRequireApproval"] is not True:
        raise ValueError("IDEAdapterContractV1 policy must require approval for dangerous capabilities")

    workspace_contract = contract["workspaceObservationContract"]
    if workspace_contract.get("schemaVersion") != WORKSPACE_OBSERVATION_SCHEMA_VERSION:
        raise ValueError(f"workspaceObservationContract schemaVersion must be {WORKSPACE_OBSERVATION_SCHEMA_VERSION}")
    if workspace_contract.get("taskVerdictOwner") != "verifier-runtime-v1":
        raise ValueError("workspaceObservationContract taskVerdictOwner must remain verifier-runtime-v1")

    capabilities = contract["capabilities"]
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("IDEAdapterContractV1 capabilities must be a non-empty list")
    names = [item.get("name") for item in capabilities if isinstance(item, dict)]
    if names != CAPABILITY_NAMES:
        raise ValueError(f"IDEAdapterContractV1 capability names must equal {CAPABILITY_NAMES}")

    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("IDEAdapterContractV1 capabilities must be objects")
        _require_fields(
            f"IDE adapter capability {capability.get('name')}",
            capability,
            [
                "schemaVersion",
                "name",
                "ref",
                "category",
                "permission",
                "sideEffectRisk",
                "approvalRequired",
                "inputContract",
                "observationContract",
                "executionMode",
                "implemented",
                "externalSideEffectAllowed",
            ],
        )
        name = capability["name"]
        if capability["schemaVersion"] != IDE_ADAPTER_CAPABILITY_SCHEMA_VERSION:
            raise ValueError(f"IDE adapter capability {name} schemaVersion must be {IDE_ADAPTER_CAPABILITY_SCHEMA_VERSION}")
        if capability["ref"] != ide_capability_ref(name):
            raise ValueError(f"IDE adapter capability {name} ref must be {ide_capability_ref(name)}")
        if capability["permission"] not in {"read", "write", "dangerous"}:
            raise ValueError(f"IDE adapter capability {name} permission must be read, write, or dangerous")
        if name in READ_ONLY_CAPABILITIES and capability["permission"] != "read":
            raise ValueError(f"IDE adapter capability {name} must be read permission")
        if name in APPROVAL_REQUIRED_CAPABILITIES and capability["approvalRequired"] is not True:
            raise ValueError(f"IDE adapter capability {name} must require approval")
        if capability["executionMode"] != "contract_only":
            raise ValueError(f"IDE adapter capability {name} executionMode must be contract_only")
        if capability["implemented"] is not False:
            raise ValueError(f"IDE adapter capability {name} must remain contract-only")
        if capability["externalSideEffectAllowed"] is not False:
            raise ValueError(f"IDE adapter capability {name} must not allow external side effects")
        for contract_field in ["inputContract", "observationContract"]:
            nested = capability[contract_field]
            if not isinstance(nested, dict) or "schema" not in nested or "required" not in nested and contract_field == "inputContract":
                raise ValueError(f"IDE adapter capability {name} has invalid {contract_field}")


def _context_pack_log_source(context_pack: dict[str, Any]) -> dict[str, Any]:
    sources = context_pack.get("sources")
    if not isinstance(sources, list):
        raise ValueError("ContextPack sources must be a list")
    for source in sources:
        if isinstance(source, dict) and source.get("role") == "regression_log":
            _require_fields("ContextPack regression_log source", source, ["path", "contentHash"])
            return source
    raise ValueError("ContextPack must contain a regression_log source")


def _context_pack_log_excerpt(context_pack: dict[str, Any]) -> dict[str, Any]:
    items = context_pack.get("contextItems")
    if not isinstance(items, list):
        raise ValueError("ContextPack contextItems must be a list")
    sources = {
        source.get("id"): source
        for source in context_pack.get("sources", [])
        if isinstance(source, dict) and "id" in source
    }
    for item in items:
        if isinstance(item, dict) and item.get("kind") == "log_excerpt":
            _require_fields("ContextPack log_excerpt item", item, ["id", "sourceId", "lineRange", "text"])
            source = sources.get(item["sourceId"])
            if not isinstance(source, dict):
                raise ValueError("ContextPack log_excerpt sourceId must reference a source")
            _require_fields("ContextPack log_excerpt source", source, ["path"])
            enriched = dict(item)
            enriched["sourcePath"] = source["path"]
            enriched["textHash"] = _stable_text_hash(item["text"])
            return enriched
    raise ValueError("ContextPack must contain a log_excerpt item")


def build_workspace_observation(
    contract_path: Path,
    context_pack_path: Path,
    run_path: Path,
    root: Path,
) -> dict[str, Any]:
    contract = _load_json(contract_path)
    validate_ide_adapter_contract(contract)
    context_pack = _load_json(context_pack_path)
    run = _load_json(run_path)
    log_source = _context_pack_log_source(context_pack)
    log_excerpt = _context_pack_log_excerpt(context_pack)
    log_path = root / log_source["path"]
    if not log_path.is_file():
        raise ValueError(f"WorkspaceObservationV1 currentFile source does not exist: {log_source['path']}")
    if _stable_file_hash(log_path) != log_source["contentHash"]:
        raise ValueError(f"WorkspaceObservationV1 currentFile source hash mismatch for {log_source['path']}")

    capability_ref = ide_capability_ref("ide.workspace.inspect")
    return {
        "schemaVersion": WORKSPACE_OBSERVATION_SCHEMA_VERSION,
        "id": OBSERVATION_ID,
        "contractRef": CONTRACT_ARTIFACT_PATH,
        "adapterRef": ADAPTER_REF,
        "provider": "static_fixture",
        "mode": "static_fixture_only",
        "externalSideEffect": False,
        "generatedAt": GENERATED_AT,
        "fixtureId": run["fixtureId"],
        "runId": run["id"],
        "workspace": {
            "workspaceRef": "workspace://repo/agentic-engineering-os-research",
            "repository": "nanyang12138/agentic-engineering-os-research",
            "root": ".",
            "currentFile": log_source["path"],
            "currentFileHash": log_source["contentHash"],
            "visibleFiles": [
                "README.md",
                ".cursor/plans/agentic-control-plane.plan.md",
                "scripts/local_readonly_runner.py",
                log_source["path"],
            ],
        },
        "sourceArtifacts": [
            _artifact_source("ide_adapter_contract", contract_path, root),
            _artifact_source("context_pack", context_pack_path, root),
            _artifact_source("run", run_path, root),
        ],
        "observations": [
            {
                "id": "workspace-observation-001",
                "kind": "workspace_snapshot",
                "capability": "ide.workspace.inspect",
                "capabilityRef": capability_ref,
                "workspaceRef": "workspace://repo/agentic-engineering-os-research",
                "sourceRef": f"{context_pack_path.resolve().relative_to(root.resolve()).as_posix()}#contextItems/{log_excerpt['id']}",
                "sourcePath": log_excerpt["sourcePath"],
                "lineRange": log_excerpt["lineRange"],
                "textHash": log_excerpt["textHash"],
                "assertion": "IDE workspace observations can provide context refs, but task verdicts remain owned by EvidenceListV1 and VerifierRuntimeV1.",
            }
        ],
        "policy": {
            "noExternalSideEffects": True,
            "noIdeUiAutomationExecuted": True,
            "noTerminalExecuted": True,
            "workspaceMutationAllowed": False,
            "requiresVerifierForTaskVerdict": True,
        },
    }


def build_approval_handoff_manifest(
    contract_path: Path,
    observation_path: Path,
    run_path: Path,
    root: Path,
) -> dict[str, Any]:
    contract = _load_json(contract_path)
    validate_ide_adapter_contract(contract)
    observation = _load_json(observation_path)
    validate_workspace_observation(observation, contract, root)
    run = _load_json(run_path)
    permission_policy = run["runControl"]["permissionPolicy"]
    task_spec = run["taskSpec"]
    capabilities = _capabilities_by_name(contract)
    workspace_ref = observation["workspace"]["workspaceRef"]
    current_file = observation["workspace"]["currentFile"]
    run_relative_path = run_path.resolve().relative_to(root.resolve()).as_posix()

    side_effect_requests = [
        {
            "capability": "ide.open_file",
            "approvalPoint": "ide_open_file_requires_human_approval",
            "policyBindings": ["external_side_effect"],
            "inputPreview": {
                "workspaceRef": workspace_ref,
                "path": current_file,
            },
            "reason": "Opening a file changes IDE UI state and requires an explicit TaskSpec approval point before scheduling.",
        },
        {
            "capability": "ide.diff_view.open",
            "approvalPoint": "ide_diff_view_requires_human_approval",
            "policyBindings": ["external_side_effect"],
            "inputPreview": {
                "workspaceRef": workspace_ref,
                "artifactRef": "artifacts/runs/all_passed/regression_result.json",
            },
            "reason": "Opening a diff view changes IDE UI state and remains blocked until the TaskSpec names the approval point.",
        },
        {
            "capability": "ide.terminal.request",
            "approvalPoint": "ide_terminal_execution_requires_human_approval",
            "policyBindings": ["dangerous", "external_side_effect"],
            "inputPreview": {
                "workspaceRef": workspace_ref,
                "commandDigest": _stable_text_hash("echo contract-only-terminal-request"),
                "commandRedacted": True,
            },
            "reason": "Terminal execution is dangerous and cannot be scheduled without both policy and TaskSpec approval.",
        },
    ]

    requests = []
    task_spec_approval_points = task_spec["approvalPoints"]
    for request in side_effect_requests:
        capability = capabilities[request["capability"]]
        requests.append(
            {
                "id": f"approval-handoff-{request['capability'].replace('.', '-')}",
                "capability": request["capability"],
                "capabilityRef": capability["ref"],
                "permission": capability["permission"],
                "approvalPoint": request["approvalPoint"],
                "requiresHumanApproval": True,
                "permissionPolicyBound": True,
                "policyBindings": request["policyBindings"],
                "taskSpecApprovalBound": request["approvalPoint"] in task_spec_approval_points,
                "schedulerDecision": "blocked_missing_task_spec_approval",
                "executionAllowed": False,
                "approvalDecisionSynthesized": False,
                "inputPreview": request["inputPreview"],
                "reason": request["reason"],
            }
        )

    approval_capability = capabilities["ide.approval.request"]
    requests.append(
        {
            "id": "approval-handoff-task-spec-send-email",
            "capability": "ide.approval.request",
            "capabilityRef": approval_capability["ref"],
            "permission": approval_capability["permission"],
            "approvalPoint": "send_email_requires_human_approval",
            "requiresHumanApproval": True,
            "permissionPolicyBound": True,
            "policyBindings": ["send_email"],
            "taskSpecApprovalBound": "send_email_requires_human_approval" in task_spec_approval_points,
            "schedulerDecision": "contract_only_handoff_ready",
            "executionAllowed": False,
            "approvalDecisionSynthesized": False,
            "inputPreview": {
                "runRef": f"{run_relative_path}#taskSpec",
                "approvalPoint": "send_email_requires_human_approval",
            },
            "reason": "The IDE may surface a human approval prompt for TaskSpec approval points, but Phase 8 does not synthesize decisions or send email.",
        }
    )

    return {
        "schemaVersion": IDE_APPROVAL_HANDOFF_MANIFEST_SCHEMA_VERSION,
        "id": APPROVAL_HANDOFF_MANIFEST_ID,
        "contractRef": CONTRACT_ARTIFACT_PATH,
        "workspaceObservationRef": OBSERVATION_ARTIFACT_PATH,
        "runRef": run_relative_path,
        "adapterRef": ADAPTER_REF,
        "provider": "static_fixture",
        "mode": "static_fixture_only",
        "externalSideEffect": False,
        "generatedAt": GENERATED_AT,
        "taskSpecBinding": {
            "taskSpecId": task_spec["id"],
            "approvalPoints": task_spec_approval_points,
            "requiredApprovalPoints": ["send_email_requires_human_approval"],
        },
        "permissionPolicyBinding": {
            "schemaVersion": permission_policy["schemaVersion"],
            "id": permission_policy["id"],
            "externalSideEffectsAllowed": permission_policy["externalSideEffectsAllowed"],
            "approvalRequiredFor": permission_policy["approvalRequiredFor"],
            "localWriteBoundary": permission_policy["localWriteBoundary"],
        },
        "sourceArtifacts": [
            _artifact_source("ide_adapter_contract", contract_path, root),
            _artifact_source("workspace_observation", observation_path, root),
            _artifact_source("run", run_path, root),
        ],
        "handoffRequests": requests,
        "policy": {
            "noRealIdeExecution": True,
            "noTerminalExecution": True,
            "noWorkspaceMutation": True,
            "autoApprovalAllowed": False,
            "approvalDecisionSynthesisAllowed": False,
        },
    }


def validate_workspace_observation(observation: dict[str, Any], contract: dict[str, Any], root: Path) -> None:
    validate_ide_adapter_contract(contract)
    _require_fields(
        "WorkspaceObservationV1",
        observation,
        [
            "schemaVersion",
            "id",
            "contractRef",
            "adapterRef",
            "provider",
            "mode",
            "externalSideEffect",
            "fixtureId",
            "runId",
            "workspace",
            "sourceArtifacts",
            "observations",
            "policy",
        ],
    )
    if observation["schemaVersion"] != WORKSPACE_OBSERVATION_SCHEMA_VERSION:
        raise ValueError(f"WorkspaceObservationV1 schemaVersion must be {WORKSPACE_OBSERVATION_SCHEMA_VERSION}")
    if observation["id"] != OBSERVATION_ID:
        raise ValueError(f"WorkspaceObservationV1 id must be {OBSERVATION_ID}")
    if observation["contractRef"] != CONTRACT_ARTIFACT_PATH:
        raise ValueError(f"WorkspaceObservationV1 contractRef must be {CONTRACT_ARTIFACT_PATH}")
    if observation["adapterRef"] != contract["adapterRef"]:
        raise ValueError("WorkspaceObservationV1 adapterRef must match IDEAdapterContractV1")
    if observation["mode"] != "static_fixture_only":
        raise ValueError("WorkspaceObservationV1 mode must be static_fixture_only")
    if observation["externalSideEffect"] is not False:
        raise ValueError("WorkspaceObservationV1 must not declare external side effects")
    if "verdict" in observation or "taskVerdict" in observation:
        raise ValueError("WorkspaceObservationV1 must not declare task verdicts")

    policy = observation["policy"]
    _require_fields(
        "WorkspaceObservationV1 policy",
        policy,
        [
            "noExternalSideEffects",
            "noIdeUiAutomationExecuted",
            "noTerminalExecuted",
            "workspaceMutationAllowed",
            "requiresVerifierForTaskVerdict",
        ],
    )
    if policy["noExternalSideEffects"] is not True:
        raise ValueError("WorkspaceObservationV1 policy must forbid external side effects")
    if policy["noIdeUiAutomationExecuted"] is not True:
        raise ValueError("WorkspaceObservationV1 policy must record that no IDE UI automation was executed")
    if policy["noTerminalExecuted"] is not True:
        raise ValueError("WorkspaceObservationV1 policy must record that no terminal was executed")
    if policy["workspaceMutationAllowed"] is not False:
        raise ValueError("WorkspaceObservationV1 policy must disallow workspace mutation")
    if policy["requiresVerifierForTaskVerdict"] is not True:
        raise ValueError("WorkspaceObservationV1 must require verifier ownership for task verdicts")

    source_artifacts = observation["sourceArtifacts"]
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("WorkspaceObservationV1 sourceArtifacts must be a non-empty list")
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("WorkspaceObservationV1 sourceArtifacts must be objects")
        _require_fields("WorkspaceObservationV1 source artifact", source, ["role", "path", "contentHash"])
        _validate_relative_posix_path(source["path"])
        source_path = root / source["path"]
        if not source_path.is_file():
            raise ValueError(f"WorkspaceObservationV1 source artifact does not exist: {source['path']}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"WorkspaceObservationV1 source hash mismatch for {source['path']}")
        sources_by_role[source["role"]] = source
    expected_roles = {"ide_adapter_contract", "context_pack", "run"}
    if set(sources_by_role) != expected_roles:
        raise ValueError(f"WorkspaceObservationV1 source roles must equal {sorted(expected_roles)}")
    if sources_by_role["ide_adapter_contract"]["path"] != CONTRACT_ARTIFACT_PATH:
        raise ValueError(f"WorkspaceObservationV1 contract source must be {CONTRACT_ARTIFACT_PATH}")

    workspace = observation["workspace"]
    _require_fields(
        "WorkspaceObservationV1 workspace",
        workspace,
        ["workspaceRef", "repository", "root", "currentFile", "currentFileHash", "visibleFiles"],
    )
    if workspace["root"] != ".":
        raise ValueError("WorkspaceObservationV1 workspace.root must be repository-relative '.'")
    _validate_relative_posix_path(workspace["currentFile"])
    current_file_path = root / workspace["currentFile"]
    if not current_file_path.is_file():
        raise ValueError(f"WorkspaceObservationV1 currentFile does not exist: {workspace['currentFile']}")
    if _stable_file_hash(current_file_path) != workspace["currentFileHash"]:
        raise ValueError(f"WorkspaceObservationV1 currentFile source hash mismatch for {workspace['currentFile']}")
    visible_files = workspace["visibleFiles"]
    if not isinstance(visible_files, list) or not visible_files:
        raise ValueError("WorkspaceObservationV1 visibleFiles must be a non-empty list")
    for path in visible_files:
        _validate_relative_posix_path(path)
        if not (root / path).is_file():
            raise ValueError(f"WorkspaceObservationV1 visibleFile does not exist: {path}")

    context_pack = _load_json(root / sources_by_role["context_pack"]["path"])
    run = _load_json(root / sources_by_role["run"]["path"])
    log_excerpt = _context_pack_log_excerpt(context_pack)
    if observation["fixtureId"] != run.get("fixtureId"):
        raise ValueError("WorkspaceObservationV1 fixtureId must match run.json")
    if observation["runId"] != run.get("id"):
        raise ValueError("WorkspaceObservationV1 runId must match run.json")

    observations = observation["observations"]
    if not isinstance(observations, list) or not observations:
        raise ValueError("WorkspaceObservationV1 observations must be a non-empty list")
    contract_capability_refs = {capability["name"]: capability["ref"] for capability in contract["capabilities"]}
    for item in observations:
        if not isinstance(item, dict):
            raise ValueError("WorkspaceObservationV1 observations must be objects")
        _require_fields(
            "WorkspaceObservationV1 observation",
            item,
            [
                "id",
                "kind",
                "capability",
                "capabilityRef",
                "workspaceRef",
                "sourceRef",
                "sourcePath",
                "lineRange",
                "textHash",
            ],
        )
        if "verdict" in item or "taskVerdict" in item:
            raise ValueError("WorkspaceObservationV1 observations must not declare task verdicts")
        if item["kind"] not in contract["workspaceObservationContract"]["allowedObservationKinds"]:
            raise ValueError(f"WorkspaceObservationV1 observation kind is not allowed: {item['kind']}")
        if item["capability"] != "ide.workspace.inspect":
            raise ValueError("WorkspaceObservationV1 observations must use ide.workspace.inspect capability")
        if item["capabilityRef"] != contract_capability_refs["ide.workspace.inspect"]:
            raise ValueError("WorkspaceObservationV1 observation capabilityRef mismatch")
        if item["workspaceRef"] != workspace["workspaceRef"]:
            raise ValueError("WorkspaceObservationV1 observation workspaceRef must match workspace")
        if item["sourcePath"] != log_excerpt["sourcePath"]:
            raise ValueError("WorkspaceObservationV1 observation sourcePath must match ContextPack log_excerpt")
        if item["lineRange"] != log_excerpt["lineRange"]:
            raise ValueError("WorkspaceObservationV1 observation lineRange must match ContextPack log_excerpt")
        if item["textHash"] != log_excerpt["textHash"]:
            raise ValueError("WorkspaceObservationV1 observation textHash must match ContextPack log_excerpt")
        expected_ref = f"{sources_by_role['context_pack']['path']}#contextItems/{log_excerpt['id']}"
        if item["sourceRef"] != expected_ref:
            raise ValueError("WorkspaceObservationV1 observation sourceRef must bind to ContextPack log_excerpt")


def validate_approval_handoff_manifest(manifest: dict[str, Any], contract: dict[str, Any], root: Path) -> None:
    validate_ide_adapter_contract(contract)
    _require_fields(
        "IDEApprovalHandoffManifestV1",
        manifest,
        [
            "schemaVersion",
            "id",
            "contractRef",
            "workspaceObservationRef",
            "runRef",
            "adapterRef",
            "provider",
            "mode",
            "externalSideEffect",
            "taskSpecBinding",
            "permissionPolicyBinding",
            "sourceArtifacts",
            "handoffRequests",
            "policy",
        ],
    )
    if manifest["schemaVersion"] != IDE_APPROVAL_HANDOFF_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"IDEApprovalHandoffManifestV1 schemaVersion must be {IDE_APPROVAL_HANDOFF_MANIFEST_SCHEMA_VERSION}")
    if manifest["id"] != APPROVAL_HANDOFF_MANIFEST_ID:
        raise ValueError(f"IDEApprovalHandoffManifestV1 id must be {APPROVAL_HANDOFF_MANIFEST_ID}")
    if manifest["contractRef"] != CONTRACT_ARTIFACT_PATH:
        raise ValueError(f"IDEApprovalHandoffManifestV1 contractRef must be {CONTRACT_ARTIFACT_PATH}")
    if manifest["workspaceObservationRef"] != OBSERVATION_ARTIFACT_PATH:
        raise ValueError(f"IDEApprovalHandoffManifestV1 workspaceObservationRef must be {OBSERVATION_ARTIFACT_PATH}")
    _validate_relative_posix_path(manifest["runRef"])
    if manifest["adapterRef"] != contract["adapterRef"]:
        raise ValueError("IDEApprovalHandoffManifestV1 adapterRef must match IDEAdapterContractV1")
    if manifest["mode"] != "static_fixture_only":
        raise ValueError("IDEApprovalHandoffManifestV1 mode must be static_fixture_only")
    if manifest["externalSideEffect"] is not False:
        raise ValueError("IDEApprovalHandoffManifestV1 must not declare external side effects")

    policy = manifest["policy"]
    _require_fields(
        "IDEApprovalHandoffManifestV1 policy",
        policy,
        [
            "noRealIdeExecution",
            "noTerminalExecution",
            "noWorkspaceMutation",
            "autoApprovalAllowed",
            "approvalDecisionSynthesisAllowed",
        ],
    )
    if policy["noRealIdeExecution"] is not True:
        raise ValueError("IDEApprovalHandoffManifestV1 must record that no real IDE execution occurred")
    if policy["noTerminalExecution"] is not True:
        raise ValueError("IDEApprovalHandoffManifestV1 must record that no terminal execution occurred")
    if policy["noWorkspaceMutation"] is not True:
        raise ValueError("IDEApprovalHandoffManifestV1 must disallow workspace mutation")
    if policy["autoApprovalAllowed"] is not False:
        raise ValueError("IDEApprovalHandoffManifestV1 must disallow auto approval")
    if policy["approvalDecisionSynthesisAllowed"] is not False:
        raise ValueError("IDEApprovalHandoffManifestV1 must not synthesize approval decisions")

    source_artifacts = manifest["sourceArtifacts"]
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise ValueError("IDEApprovalHandoffManifestV1 sourceArtifacts must be a non-empty list")
    sources_by_role: dict[str, dict[str, Any]] = {}
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise ValueError("IDEApprovalHandoffManifestV1 sourceArtifacts must be objects")
        _require_fields("IDEApprovalHandoffManifestV1 source artifact", source, ["role", "path", "contentHash"])
        _validate_relative_posix_path(source["path"])
        source_path = root / source["path"]
        if not source_path.is_file():
            raise ValueError(f"IDEApprovalHandoffManifestV1 source artifact does not exist: {source['path']}")
        if _stable_file_hash(source_path) != source["contentHash"]:
            raise ValueError(f"IDEApprovalHandoffManifestV1 source hash mismatch for {source['path']}")
        sources_by_role[source["role"]] = source
    expected_roles = {"ide_adapter_contract", "workspace_observation", "run"}
    if set(sources_by_role) != expected_roles:
        raise ValueError(f"IDEApprovalHandoffManifestV1 source roles must equal {sorted(expected_roles)}")
    if sources_by_role["ide_adapter_contract"]["path"] != CONTRACT_ARTIFACT_PATH:
        raise ValueError(f"IDEApprovalHandoffManifestV1 contract source must be {CONTRACT_ARTIFACT_PATH}")
    if sources_by_role["workspace_observation"]["path"] != OBSERVATION_ARTIFACT_PATH:
        raise ValueError(f"IDEApprovalHandoffManifestV1 observation source must be {OBSERVATION_ARTIFACT_PATH}")
    if sources_by_role["run"]["path"] != manifest["runRef"]:
        raise ValueError("IDEApprovalHandoffManifestV1 run source must match runRef")

    observation = _load_json(root / sources_by_role["workspace_observation"]["path"])
    validate_workspace_observation(observation, contract, root)
    run = _load_json(root / sources_by_role["run"]["path"])
    task_spec = run["taskSpec"]
    permission_policy = run["runControl"]["permissionPolicy"]

    task_spec_binding = manifest["taskSpecBinding"]
    _require_fields("IDEApprovalHandoffManifestV1 taskSpecBinding", task_spec_binding, ["taskSpecId", "approvalPoints", "requiredApprovalPoints"])
    if task_spec_binding["taskSpecId"] != task_spec["id"]:
        raise ValueError("IDEApprovalHandoffManifestV1 taskSpecBinding must match run TaskSpec id")
    if task_spec_binding["approvalPoints"] != task_spec["approvalPoints"]:
        raise ValueError("IDEApprovalHandoffManifestV1 taskSpecBinding approvalPoints must match run TaskSpec")
    required_task_points = task_spec_binding["requiredApprovalPoints"]
    if not isinstance(required_task_points, list) or "send_email_requires_human_approval" not in required_task_points:
        raise ValueError("IDEApprovalHandoffManifestV1 must require TaskSpec send_email approval point")
    for point in required_task_points:
        if point not in task_spec_binding["approvalPoints"]:
            raise ValueError(f"IDEApprovalHandoffManifestV1 required approval point is missing from TaskSpec: {point}")

    policy_binding = manifest["permissionPolicyBinding"]
    _require_fields(
        "IDEApprovalHandoffManifestV1 permissionPolicyBinding",
        policy_binding,
        ["schemaVersion", "id", "externalSideEffectsAllowed", "approvalRequiredFor", "localWriteBoundary"],
    )
    if policy_binding["schemaVersion"] != permission_policy["schemaVersion"]:
        raise ValueError("IDEApprovalHandoffManifestV1 permission policy schemaVersion must match RunControlV1")
    if policy_binding["id"] != permission_policy["id"]:
        raise ValueError("IDEApprovalHandoffManifestV1 permission policy id must match RunControlV1")
    if policy_binding["externalSideEffectsAllowed"] is not False:
        raise ValueError("IDEApprovalHandoffManifestV1 permission policy must disallow external side effects")
    if policy_binding["approvalRequiredFor"] != permission_policy["approvalRequiredFor"]:
        raise ValueError("IDEApprovalHandoffManifestV1 approvalRequiredFor must match RunControlV1 permission policy")
    if policy_binding["localWriteBoundary"] != permission_policy["localWriteBoundary"]:
        raise ValueError("IDEApprovalHandoffManifestV1 localWriteBoundary must match RunControlV1 permission policy")

    capabilities = _capabilities_by_name(contract)
    required_requests = {
        "ide.open_file",
        "ide.diff_view.open",
        "ide.terminal.request",
        "ide.approval.request",
    }
    requests = manifest["handoffRequests"]
    if not isinstance(requests, list) or not requests:
        raise ValueError("IDEApprovalHandoffManifestV1 handoffRequests must be a non-empty list")
    request_names = {request.get("capability") for request in requests if isinstance(request, dict)}
    if request_names != required_requests:
        raise ValueError(f"IDEApprovalHandoffManifestV1 handoffRequests must cover {sorted(required_requests)}")

    approval_required_for = set(policy_binding["approvalRequiredFor"])
    task_approval_points = set(task_spec_binding["approvalPoints"])
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("IDEApprovalHandoffManifestV1 handoffRequests must be objects")
        _require_fields(
            "IDEApprovalHandoffManifestV1 handoff request",
            request,
            [
                "id",
                "capability",
                "capabilityRef",
                "permission",
                "approvalPoint",
                "requiresHumanApproval",
                "permissionPolicyBound",
                "policyBindings",
                "taskSpecApprovalBound",
                "schedulerDecision",
                "executionAllowed",
                "approvalDecisionSynthesized",
                "inputPreview",
                "reason",
            ],
        )
        capability = capabilities[request["capability"]]
        if request["capabilityRef"] != capability["ref"]:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} capabilityRef mismatch")
        if request["permission"] != capability["permission"]:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} permission mismatch")
        if request["requiresHumanApproval"] is not True:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} must require human approval")
        if request["permissionPolicyBound"] is not True:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} must bind to permission policy")
        if request["executionAllowed"] is not False:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} must not allow execution")
        if request["approvalDecisionSynthesized"] is not False:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} must not synthesize approval decisions")
        policy_bindings = request["policyBindings"]
        if not isinstance(policy_bindings, list) or not policy_bindings:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} policyBindings must be non-empty")
        missing_policy_bindings = [binding for binding in policy_bindings if binding not in approval_required_for]
        if missing_policy_bindings:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} has policy bindings missing from RunControlV1: {missing_policy_bindings}")
        expected_task_bound = request["approvalPoint"] in task_approval_points
        if request["taskSpecApprovalBound"] is not expected_task_bound:
            raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} taskSpecApprovalBound must reflect TaskSpec approval points")

        if request["capability"] in {"ide.open_file", "ide.diff_view.open", "ide.terminal.request"}:
            if capability["approvalRequired"] is not True:
                raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} contract capability must require approval")
            if request["taskSpecApprovalBound"] is not False:
                raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} must remain blocked until TaskSpec grants an IDE approval point")
            if request["schedulerDecision"] != "blocked_missing_task_spec_approval":
                raise ValueError(f"IDEApprovalHandoffManifestV1 {request['capability']} must be blocked by missing TaskSpec approval")
        else:
            if request["approvalPoint"] != "send_email_requires_human_approval":
                raise ValueError("IDEApprovalHandoffManifestV1 ide.approval.request must bind to TaskSpec send_email approval point")
            if request["taskSpecApprovalBound"] is not True:
                raise ValueError("IDEApprovalHandoffManifestV1 ide.approval.request must be bound to a TaskSpec approval point")
            if request["schedulerDecision"] != "contract_only_handoff_ready":
                raise ValueError("IDEApprovalHandoffManifestV1 ide.approval.request must remain contract-only handoff ready")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ide-adapter-contract")
    parser.add_argument("--contract-out", type=Path)
    parser.add_argument("--observation-out", type=Path)
    parser.add_argument("--approval-handoff-out", type=Path)
    parser.add_argument("--context-pack", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--validate-contract", type=Path)
    parser.add_argument("--validate-observation", type=Path)
    parser.add_argument("--validate-approval-handoff", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()

    contract = None
    if args.contract_out:
        contract = build_ide_adapter_contract()
        _write_json(args.contract_out, contract)
        print(f"Wrote IDEAdapterContractV1 contract to {args.contract_out}.")

    if args.observation_out:
        if not args.context_pack or not args.run:
            raise ValueError("--observation-out requires --context-pack and --run")
        if contract is None:
            contract = build_ide_adapter_contract()
        observation = build_workspace_observation(root / CONTRACT_ARTIFACT_PATH, args.context_pack, args.run, root)
        validate_workspace_observation(observation, contract, root)
        _write_json(args.observation_out, observation)
        print(f"Wrote WorkspaceObservationV1 artifact to {args.observation_out}.")

    if args.approval_handoff_out:
        if not args.run:
            raise ValueError("--approval-handoff-out requires --run")
        if contract is None:
            contract = build_ide_adapter_contract()
        manifest = build_approval_handoff_manifest(
            root / CONTRACT_ARTIFACT_PATH,
            root / OBSERVATION_ARTIFACT_PATH,
            args.run,
            root,
        )
        validate_approval_handoff_manifest(manifest, contract, root)
        _write_json(args.approval_handoff_out, manifest)
        print(f"Wrote IDEApprovalHandoffManifestV1 artifact to {args.approval_handoff_out}.")

    if args.validate_contract:
        contract = _load_json(args.validate_contract)
        validate_ide_adapter_contract(contract)
        print(f"Validated IDEAdapterContractV1 contract {args.validate_contract}.")

    if args.validate_observation:
        contract_path = args.validate_contract or (root / CONTRACT_ARTIFACT_PATH)
        contract = _load_json(contract_path)
        observation = _load_json(args.validate_observation)
        validate_workspace_observation(observation, contract, root)
        print(f"Validated WorkspaceObservationV1 artifact {args.validate_observation}.")

    if args.validate_approval_handoff:
        contract_path = args.validate_contract or (root / CONTRACT_ARTIFACT_PATH)
        contract = _load_json(contract_path)
        manifest = _load_json(args.validate_approval_handoff)
        validate_approval_handoff_manifest(manifest, contract, root)
        print(f"Validated IDEApprovalHandoffManifestV1 artifact {args.validate_approval_handoff}.")

    if not any(
        [
            args.contract_out,
            args.observation_out,
            args.approval_handoff_out,
            args.validate_contract,
            args.validate_observation,
            args.validate_approval_handoff,
        ]
    ):
        raise ValueError("No action requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from capability_contract import PHASE3_CAPABILITY_NAMES, validate_capability_catalog


ROOT = Path(__file__).resolve().parents[1]
CONTEXT_PACK_SCHEMA_VERSION = "context-pack-v1"
DEFAULT_CONTEXT_PURPOSE = "Bounded regression context for evidence extraction and verification."
REQUIRED_ARTIFACTS = [
    "run.json",
    "events.jsonl",
    "evidence.json",
    "regression_result.json",
    "email_draft.md",
    "verifier_report.json",
]
REQUIRED_SOURCE_ROLES = {
    "task_spec",
    "regression_log",
    "capability_catalog",
    "run_artifact",
    "events_artifact",
    "evidence_artifact",
    "regression_result_artifact",
    "email_draft_artifact",
    "verifier_report_artifact",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return text_hash(normalized_text(path))


def json_hash(payload: Any) -> str:
    return text_hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def repo_path(path: Path, root: Path = ROOT) -> str:
    resolved = path.resolve(strict=False)
    try:
        relative = resolved.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError(f"ContextPack paths must stay under repository root: {path}") from exc
    return relative.as_posix()


def resolve_repo_path(path: str | Path, root: Path = ROOT) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
    else:
        resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError(f"ContextPack path escapes repository root: {path}") from exc
    return resolved


def source(
    source_id: str,
    source_type: str,
    role: str,
    path: Path,
    content_hash: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "contentHash": content_hash,
        "id": source_id,
        "path": repo_path(path),
        "role": role,
        "type": source_type,
        **extra,
    }


def artifact_source_id(filename: str) -> str:
    return f"source-{filename.replace('.', '-').replace('_', '-')}"


def artifact_role(filename: str) -> str:
    return {
        "run.json": "run_artifact",
        "events.jsonl": "events_artifact",
        "evidence.json": "evidence_artifact",
        "regression_result.json": "regression_result_artifact",
        "email_draft.md": "email_draft_artifact",
        "verifier_report.json": "verifier_report_artifact",
    }[filename]


def log_excerpt_text(log_path: Path, line_range: list[int]) -> str:
    lines = normalized_text(log_path).splitlines()
    start, end = line_range
    return "\n".join(lines[start - 1 : end])


def build_context_pack(
    run_dir: Path,
    fixture_dir: Path,
    capability_catalog_path: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    run_path = run_dir / "run.json"
    evidence_path = run_dir / "evidence.json"
    result_path = run_dir / "regression_result.json"
    catalog_path = capability_catalog_path

    run = load_json(run_path)
    evidence = load_json(evidence_path)
    result = load_json(result_path)
    catalog = load_json(catalog_path)
    validate_capability_catalog(catalog, PHASE3_CAPABILITY_NAMES)

    fixture_id = run["fixtureId"]
    task_spec = run["taskSpec"]
    log_path = resolve_repo_path(task_spec["inputLogPath"], root)
    if not log_path.is_file():
        fallback = fixture_dir / "input.log"
        if fallback.is_file():
            log_path = fallback
        else:
            raise ValueError(f"Missing regression log for fixture {fixture_id}: {task_spec['inputLogPath']}")

    artifact_refs = []
    sources = [
        source(
            "source-task-spec",
            "artifact",
            "task_spec",
            run_path,
            json_hash(task_spec),
            jsonPointer="/taskSpec",
        ),
        source(
            "source-regression-log",
            "log",
            "regression_log",
            log_path,
            file_hash(log_path),
            lineCount=len(normalized_text(log_path).splitlines()),
        ),
        source(
            "source-capability-catalog",
            "artifact",
            "capability_catalog",
            catalog_path,
            file_hash(catalog_path),
        ),
    ]

    for filename in REQUIRED_ARTIFACTS:
        path = run_dir / filename
        artifact_refs.append(
            {
                "contentHash": file_hash(path),
                "path": repo_path(path),
                "type": artifact_role(filename).removesuffix("_artifact"),
            }
        )
        sources.append(
            source(
                artifact_source_id(filename),
                "artifact",
                artifact_role(filename),
                path,
                file_hash(path),
            )
        )

    capability_refs = [
        item["ref"]
        for item in catalog["capabilityEnvelope"]["items"]
    ]
    context_items = [
        {
            "id": "ctx-task-goal",
            "kind": "task_goal",
            "sourceId": "source-task-spec",
            "text": task_spec["goal"],
        },
        {
            "allowedActions": task_spec["allowedActions"],
            "approvalPoints": task_spec["approvalPoints"],
            "forbiddenActions": task_spec["forbiddenActions"],
            "id": "ctx-task-boundaries",
            "kind": "task_boundaries",
            "sourceId": "source-task-spec",
        },
        {
            "capabilityRefs": capability_refs,
            "id": "ctx-capability-refs",
            "kind": "capability_refs",
            "sourceId": "source-capability-catalog",
        },
    ]

    for index, item in enumerate(evidence["items"], start=1):
        line_range = item.get("lineRange")
        excerpt = item["excerpt"]
        if isinstance(line_range, list) and len(line_range) == 2:
            excerpt = log_excerpt_text(log_path, line_range)
        context_items.append(
            {
                "classification": item["classification"],
                "confidence": item["confidence"],
                "evidenceId": item["id"],
                "id": f"ctx-log-evidence-{index:03d}",
                "kind": "log_excerpt",
                "lineRange": line_range,
                "sourceId": "source-regression-log",
                "text": excerpt,
            }
        )

    context_items.append(
        {
            "evidenceIds": result["evidenceIds"],
            "id": "ctx-regression-verdict",
            "kind": "regression_verdict",
            "sourceId": "source-regression-result-json",
            "summary": result["summary"],
            "verdict": result["verdict"],
        }
    )

    pack = {
        "artifactRefs": artifact_refs,
        "capabilityCatalogRef": repo_path(catalog_path),
        "contextItems": context_items,
        "fixtureId": fixture_id,
        "id": f"context-pack-{fixture_id}",
        "purpose": DEFAULT_CONTEXT_PURPOSE,
        "runRef": repo_path(run_path),
        "schemaVersion": CONTEXT_PACK_SCHEMA_VERSION,
        "sources": sources,
        "taskSpecRef": f"{repo_path(run_path)}#/taskSpec",
    }
    validate_context_pack(pack, root)
    return pack


def validate_context_pack(pack: dict[str, Any], root: Path = ROOT) -> None:
    required_fields = [
        "schemaVersion",
        "id",
        "fixtureId",
        "purpose",
        "runRef",
        "taskSpecRef",
        "capabilityCatalogRef",
        "sources",
        "contextItems",
        "artifactRefs",
    ]
    missing = [field for field in required_fields if field not in pack]
    if missing:
        raise ValueError(f"ContextPack is missing required fields: {missing}")
    if pack["schemaVersion"] != CONTEXT_PACK_SCHEMA_VERSION:
        raise ValueError(f"ContextPack schemaVersion must be {CONTEXT_PACK_SCHEMA_VERSION}")
    if not isinstance(pack["sources"], list) or not pack["sources"]:
        raise ValueError("ContextPack sources must be a non-empty list")
    if not isinstance(pack["contextItems"], list) or not pack["contextItems"]:
        raise ValueError("ContextPack contextItems must be a non-empty list")
    if not isinstance(pack["artifactRefs"], list) or not pack["artifactRefs"]:
        raise ValueError("ContextPack artifactRefs must be a non-empty list")

    source_ids: set[str] = set()
    source_roles: set[str] = set()
    for source_item in pack["sources"]:
        for field in ["id", "type", "role", "path", "contentHash"]:
            if field not in source_item:
                raise ValueError(f"ContextPack source is missing required field: {field}")
        if source_item["id"] in source_ids:
            raise ValueError(f"ContextPack source id is duplicated: {source_item['id']}")
        source_ids.add(source_item["id"])
        source_roles.add(source_item["role"])
        if source_item["type"] not in {"artifact", "log"}:
            raise ValueError(f"ContextPack source type is invalid: {source_item['type']}")
        validate_relative_path(source_item["path"])
        source_path = resolve_repo_path(source_item["path"], root)
        if not source_path.is_file():
            raise ValueError(f"ContextPack source path does not exist: {source_item['path']}")
        expected_hash = source_item["contentHash"]
        if source_item.get("jsonPointer") == "/taskSpec":
            run = load_json(source_path)
            actual_hash = json_hash(run["taskSpec"])
        else:
            actual_hash = file_hash(source_path)
        if expected_hash != actual_hash:
            raise ValueError(f"ContextPack source hash mismatch for {source_item['id']}")

    missing_roles = sorted(REQUIRED_SOURCE_ROLES - source_roles)
    if missing_roles:
        raise ValueError(f"ContextPack is missing required source roles: {missing_roles}")

    catalog_path = resolve_repo_path(pack["capabilityCatalogRef"], root)
    catalog = load_json(catalog_path)
    validate_capability_catalog(catalog, PHASE3_CAPABILITY_NAMES)

    for artifact_ref in pack["artifactRefs"]:
        for field in ["type", "path", "contentHash"]:
            if field not in artifact_ref:
                raise ValueError(f"ContextPack artifactRef is missing required field: {field}")
        validate_relative_path(artifact_ref["path"])
        artifact_path = resolve_repo_path(artifact_ref["path"], root)
        if artifact_ref["contentHash"] != file_hash(artifact_path):
            raise ValueError(f"ContextPack artifactRef hash mismatch for {artifact_ref['path']}")

    log_source_ids = {
        source_item["id"]
        for source_item in pack["sources"]
        if source_item["role"] == "regression_log"
    }
    for context_item in pack["contextItems"]:
        for field in ["id", "kind", "sourceId"]:
            if field not in context_item:
                raise ValueError(f"ContextPack contextItem is missing required field: {field}")
        if context_item["sourceId"] not in source_ids:
            raise ValueError(f"ContextPack contextItem has unknown sourceId: {context_item['sourceId']}")
        if context_item["kind"] == "log_excerpt":
            if context_item["sourceId"] not in log_source_ids:
                raise ValueError("ContextPack log_excerpt must reference the regression log source")
            line_range = context_item.get("lineRange")
            if (
                not isinstance(line_range, list)
                or len(line_range) != 2
                or not all(isinstance(number, int) and number >= 1 for number in line_range)
                or line_range[0] > line_range[1]
            ):
                raise ValueError("ContextPack log_excerpt lineRange must be [start, end] positive integers")
            log_source = next(source_item for source_item in pack["sources"] if source_item["id"] == context_item["sourceId"])
            expected_text = log_excerpt_text(resolve_repo_path(log_source["path"], root), line_range)
            if context_item.get("text") != expected_text:
                raise ValueError("ContextPack log_excerpt text must match source log lines")


def validate_relative_path(path: str) -> None:
    if Path(path).is_absolute() or "\\" in path or path.startswith("../") or "/../" in path:
        raise ValueError(f"ContextPack paths must be POSIX relative paths under the repository: {path}")


def build_all_context_packs(
    run_root: Path,
    fixture_root: Path,
    capability_catalog_path: Path,
    out_dir: Path,
    root: Path = ROOT,
) -> list[Path]:
    written: list[Path] = []
    for run_dir in sorted(path for path in run_root.iterdir() if path.is_dir()):
        fixture_dir = fixture_root / run_dir.name
        pack = build_context_pack(run_dir, fixture_dir, capability_catalog_path, root)
        out_path = out_dir / run_dir.name / "context_pack.json"
        write_json(out_path, pack)
        written.append(out_path)
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="context-pack-builder")
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--fixture-root", required=True, type=Path)
    parser.add_argument("--capability-catalog", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    written = build_all_context_packs(args.run_root, args.fixture_root, args.capability_catalog, args.out_dir)
    print(f"Wrote {len(written)} ContextPack artifact(s) into {args.out_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from context_pack import (
    ROOT,
    log_excerpt_text,
    repo_path,
    resolve_repo_path,
    validate_context_pack,
    validate_relative_path,
)


EVIDENCE_LIST_SCHEMA_VERSION = "evidence-list-v1"
DEFAULT_LOG_SOURCE_REF = "source-regression-log"
EVIDENCE_CLASSES = {
    "all_passed_marker",
    "failure_marker",
    "incomplete_marker",
    "warning_marker",
    "waiver_marker",
    "metadata",
    "ambiguous",
}
EVIDENCE_CONFIDENCE = {"high", "medium", "low"}
REQUIRED_ARTIFACT_BACKLINKS = [
    {
        "artifact": "regression_result.json",
        "jsonPointer": "/evidenceIds",
        "relation": "supports_regression_result",
    },
    {
        "artifact": "verifier_report.json",
        "jsonPointer": "/ruleResults/*/evidenceIds",
        "relation": "checked_by_verifier",
    },
    {
        "artifact": "events.jsonl",
        "jsonPointer": "/*.evidenceIds",
        "relation": "audited_by_events",
    },
    {
        "artifact": "email_draft.md",
        "jsonPointer": "/text",
        "relation": "cited_by_delivery_draft",
    },
]


def normalized_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def text_hash(text: str) -> str:
    return hashlib.sha256(normalized_text(text).encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def enrich_evidence_item(item: dict[str, Any], source_ref: str = DEFAULT_LOG_SOURCE_REF) -> dict[str, Any]:
    enriched = dict(item)
    excerpt = str(enriched.get("excerpt", ""))
    enriched["sourceRef"] = source_ref
    enriched["excerptHash"] = text_hash(excerpt)
    return enriched


def build_evidence_list(fixture_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifactBacklinks": list(REQUIRED_ARTIFACT_BACKLINKS),
        "fixtureId": fixture_id,
        "id": f"evidence-list-{fixture_id}",
        "items": [enrich_evidence_item(item) for item in items],
        "schemaVersion": EVIDENCE_LIST_SCHEMA_VERSION,
    }


def _require_fields(label: str, payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing}")


def _validate_line_range(label: str, line_range: Any) -> list[int]:
    if (
        not isinstance(line_range, list)
        or len(line_range) != 2
        or not all(isinstance(number, int) and number >= 1 for number in line_range)
        or line_range[0] > line_range[1]
    ):
        raise ValueError(f"{label}.lineRange must be [start, end] positive integers")
    return line_range


def validate_evidence_list_schema(evidence_list: dict[str, Any], root: Path = ROOT) -> None:
    _require_fields(
        "EvidenceListV1",
        evidence_list,
        ["schemaVersion", "id", "fixtureId", "artifactBacklinks", "items"],
    )
    if evidence_list["schemaVersion"] != EVIDENCE_LIST_SCHEMA_VERSION:
        raise ValueError(f"EvidenceListV1 schemaVersion must be {EVIDENCE_LIST_SCHEMA_VERSION}")
    expected_id = f"evidence-list-{evidence_list['fixtureId']}"
    if evidence_list["id"] != expected_id:
        raise ValueError(f"EvidenceListV1 id must be {expected_id}")
    if evidence_list["artifactBacklinks"] != REQUIRED_ARTIFACT_BACKLINKS:
        raise ValueError("EvidenceListV1 artifactBacklinks must match the Phase 5 contract")

    items = evidence_list["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("EvidenceListV1 items must be a non-empty list")
    ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"EvidenceListV1 item {index} must be an object")
        label = f"EvidenceListV1 items[{index}]"
        _require_fields(
            label,
            item,
            [
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
            ],
        )
        if item["id"] in ids:
            raise ValueError(f"EvidenceListV1 evidence id is duplicated: {item['id']}")
        ids.add(item["id"])
        if item["type"] != "log":
            raise ValueError(f"{label}.type must be log")
        if item["classification"] not in EVIDENCE_CLASSES:
            raise ValueError(f"{label}.classification is invalid: {item['classification']}")
        if item["confidence"] not in EVIDENCE_CONFIDENCE:
            raise ValueError(f"{label}.confidence is invalid: {item['confidence']}")
        if item["sourceRef"] != DEFAULT_LOG_SOURCE_REF:
            raise ValueError(f"{label}.sourceRef must be {DEFAULT_LOG_SOURCE_REF}")
        if not isinstance(item["sourcePath"], str):
            raise ValueError(f"{label}.sourcePath must be a string")
        validate_relative_path(item["sourcePath"])
        line_range = _validate_line_range(label, item["lineRange"])
        source_path = resolve_repo_path(item["sourcePath"], root)
        if not source_path.is_file():
            raise ValueError(f"{label}.sourcePath does not exist: {item['sourcePath']}")
        expected_excerpt = log_excerpt_text(source_path, line_range)
        if item["excerpt"] != expected_excerpt:
            raise ValueError(f"{label}.excerpt must match sourcePath lineRange")
        if item["excerptHash"] != text_hash(item["excerpt"]):
            raise ValueError(f"{label}.excerptHash must equal sha256(normalized excerpt)")


def _collect_json_evidence_ids(payload: Any) -> list[str]:
    collected: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "evidenceIds" and isinstance(value, list):
                collected.extend(item for item in value if isinstance(item, str))
            else:
                collected.extend(_collect_json_evidence_ids(value))
    elif isinstance(payload, list):
        for item in payload:
            collected.extend(_collect_json_evidence_ids(item))
    return collected


def _load_events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError(f"{path} must contain JSON object lines")
            events.append(event)
    return events


def validate_artifact_backlinks(evidence_list: dict[str, Any], run_dir: Path) -> None:
    evidence_ids = {item["id"] for item in evidence_list["items"]}
    paths = {
        "regression_result.json": run_dir / "regression_result.json",
        "verifier_report.json": run_dir / "verifier_report.json",
        "events.jsonl": run_dir / "events.jsonl",
        "email_draft.md": run_dir / "email_draft.md",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ValueError(f"EvidenceListV1 artifactBacklinks point to missing artifacts: {missing}")

    result = load_json(paths["regression_result.json"])
    report = load_json(paths["verifier_report.json"])
    events = _load_events(paths["events.jsonl"])
    email = paths["email_draft.md"].read_text(encoding="utf-8")

    referenced = {
        "regression_result.json": _collect_json_evidence_ids(result),
        "verifier_report.json": _collect_json_evidence_ids(report),
        "events.jsonl": _collect_json_evidence_ids(events),
    }
    for artifact, ids in referenced.items():
        unknown = sorted(set(ids) - evidence_ids)
        if unknown:
            raise ValueError(f"{artifact} references unknown EvidenceListV1 ids: {unknown}")

    result_ids = result.get("evidenceIds")
    if not isinstance(result_ids, list) or not result_ids:
        raise ValueError("regression_result.json must backlink to at least one EvidenceListV1 id")
    email_lower = email.lower()
    missing_email_refs = [evidence_id for evidence_id in result_ids if evidence_id.lower() not in email_lower]
    if missing_email_refs:
        raise ValueError(f"email_draft.md does not cite regression result evidence ids: {missing_email_refs}")


def validate_context_pack_provenance(evidence_list: dict[str, Any], context_pack: dict[str, Any], root: Path = ROOT) -> None:
    validate_context_pack(context_pack, root)
    log_sources = {
        source["id"]: source
        for source in context_pack["sources"]
        if source.get("role") == "regression_log"
    }
    context_items_by_evidence_id = {
        item["evidenceId"]: item
        for item in context_pack["contextItems"]
        if item.get("kind") == "log_excerpt" and "evidenceId" in item
    }
    evidence_ids = {item["id"] for item in evidence_list["items"]}
    missing_context = sorted(evidence_ids - set(context_items_by_evidence_id))
    if missing_context:
        raise ValueError(f"ContextPack is missing log_excerpt provenance for evidence ids: {missing_context}")

    for evidence in evidence_list["items"]:
        context_item = context_items_by_evidence_id[evidence["id"]]
        if context_item["sourceId"] != evidence["sourceRef"]:
            raise ValueError(f"Evidence item {evidence['id']} sourceRef does not match ContextPack sourceId")
        if context_item["sourceId"] not in log_sources:
            raise ValueError(f"Evidence item {evidence['id']} does not reference a ContextPack regression log source")
        context_source_path = repo_path(resolve_repo_path(log_sources[context_item["sourceId"]]["path"], root), root)
        evidence_source_path = repo_path(resolve_repo_path(evidence["sourcePath"], root), root)
        if context_source_path != evidence_source_path:
            raise ValueError(f"Evidence item {evidence['id']} sourcePath does not match ContextPack regression log source")
        if context_item.get("lineRange") != evidence["lineRange"]:
            raise ValueError(f"Evidence item {evidence['id']} lineRange does not match ContextPack provenance")
        if context_item.get("text") != evidence["excerpt"]:
            raise ValueError(f"Evidence item {evidence['id']} excerpt does not match ContextPack provenance")
        if context_item.get("classification") != evidence["classification"]:
            raise ValueError(f"Evidence item {evidence['id']} classification does not match ContextPack provenance")
        if context_item.get("confidence") != evidence["confidence"]:
            raise ValueError(f"Evidence item {evidence['id']} confidence does not match ContextPack provenance")

    evidence_artifact_refs = [
        ref
        for ref in context_pack["artifactRefs"]
        if ref.get("type") == "evidence"
    ]
    if len(evidence_artifact_refs) != 1:
        raise ValueError("ContextPack must contain exactly one evidence artifactRef")


def validate_evidence_list(
    evidence_list: dict[str, Any],
    root: Path = ROOT,
    run_dir: Path | None = None,
    context_pack: dict[str, Any] | None = None,
) -> None:
    validate_evidence_list_schema(evidence_list, root)
    if run_dir is not None:
        validate_artifact_backlinks(evidence_list, run_dir)
    if context_pack is not None:
        validate_context_pack_provenance(evidence_list, context_pack, root)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evidence-list")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--context-pack", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    context_pack = load_json(args.context_pack) if args.context_pack else None
    validate_evidence_list(load_json(args.evidence), ROOT, args.run_dir, context_pack)
    print(f"EvidenceListV1 validation passed for {args.evidence}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(REPO_ROOT, "runtime", "scripts"))

from runtime_io import load_jsonl, load_schema, validate_object, write_jsonl  # noqa: E402


CANONICAL_FIELDS = (
    "id",
    "candidate_id",
    "topic",
    "content",
    "timestamp",
    "category",
    "maturity",
    "source",
    "source_file",
    "source_section",
    "approved_at",
    "ingested_at",
    "schema_version",
)


def audit_memory_nodes(nodes, *, schema=None):
    schema = schema or load_schema("memory-node.v2", REPO_ROOT)
    candidate_groups = defaultdict(list)
    fingerprint_groups = defaultdict(list)
    field_counter = Counter()
    records = []

    for index, node in enumerate(nodes, start=1):
        node = dict(node)
        for key in node:
            field_counter[key] += 1

        candidate_id = node.get("candidate_id")
        fingerprint = content_fingerprint(node)
        if candidate_id:
            candidate_groups[candidate_id].append(index)
        if fingerprint:
            fingerprint_groups[fingerprint].append(index)

        schema_errors = validate_object(node, schema, location=f"memory[{index}]")
        unknown_fields = sorted(key for key in node if key not in CANONICAL_FIELDS)
        missing_fields = [key for key in schema.get("required", []) if key not in node]
        records.append(
            {
                "index": index,
                "id": node.get("id"),
                "candidate_id": candidate_id,
                "topic": node.get("topic"),
                "schema_version": node.get("schema_version"),
                "content_fingerprint": fingerprint,
                "unknown_fields": unknown_fields,
                "missing_required_fields": missing_fields,
                "schema_errors": schema_errors,
                "migration_action": classify_node(node, schema_errors, unknown_fields, candidate_groups[candidate_id] if candidate_id else []),
            }
        )

    duplicate_candidate_ids = {key: indexes for key, indexes in candidate_groups.items() if len(indexes) > 1}
    duplicate_content = {key: indexes for key, indexes in fingerprint_groups.items() if len(indexes) > 1}
    for record in records:
        cid = record.get("candidate_id")
        fp = record.get("content_fingerprint")
        if cid in duplicate_candidate_ids:
            record["migration_action"] = "dedupe_candidate_id"
            record["duplicate_group"] = {"type": "candidate_id", "key": cid, "indexes": duplicate_candidate_ids[cid]}
        elif fp in duplicate_content:
            record["migration_action"] = "review_content_duplicate"
            record["duplicate_group"] = {"type": "content_fingerprint", "key": fp, "indexes": duplicate_content[fp]}

    return {
        "summary": {
            "total_memory_nodes": len(records),
            "schema_valid": sum(1 for record in records if not record["schema_errors"] and not record["unknown_fields"]),
            "needs_field_cleanup": sum(1 for record in records if record["unknown_fields"]),
            "missing_candidate_id": sum(1 for record in records if not record.get("candidate_id")),
            "duplicate_candidate_id_groups": len(duplicate_candidate_ids),
            "duplicate_content_groups": len(duplicate_content),
            "fields_seen": dict(sorted(field_counter.items())),
        },
        "duplicates": {
            "candidate_id": duplicate_candidate_ids,
            "content_fingerprint": duplicate_content,
        },
        "records": records,
    }


def build_migration_plan(nodes, audit):
    by_index = {record["index"]: record for record in audit["records"]}
    plan = []
    rollback = []
    for index, node in enumerate(nodes, start=1):
        record = by_index[index]
        action = record["migration_action"]
        canonical = {key: node[key] for key in CANONICAL_FIELDS if key in node}

        if action == "keep":
            continue
        if action in {"strip_unknown_fields", "normalize_schema_version"}:
            if canonical.get("schema_version") in (None, "Memory", "memory-node"):
                canonical["schema_version"] = "memory-node.v2"
            plan.append({"action": "update_properties", "match": match_key(node, index), "set": canonical, "remove_unknown_fields": record["unknown_fields"]})
        elif action == "dedupe_candidate_id":
            plan.append({"action": "manual_dedupe", "match": match_key(node, index), "reason": "candidate_id is not unique", "group": record["duplicate_group"]})
        elif action == "review_content_duplicate":
            plan.append({"action": "manual_review", "match": match_key(node, index), "reason": "content fingerprint appears on multiple Memory nodes", "group": record["duplicate_group"]})
        else:
            plan.append({"action": "quarantine", "match": match_key(node, index), "reason": action, "node": node})
        rollback.append({"match": match_key(node, index), "restore": node})
    return plan, rollback


def classify_node(node, schema_errors, unknown_fields, candidate_group):
    if not node.get("candidate_id"):
        return "quarantine_missing_candidate_id"
    if node.get("id") == node.get("candidate_id"):
        return "quarantine_candidate_id_reused_as_id"
    if len(candidate_group) > 1:
        return "dedupe_candidate_id"
    if unknown_fields:
        return "strip_unknown_fields"
    if node.get("schema_version") in (None, "Memory", "memory-node"):
        return "normalize_schema_version"
    if schema_errors:
        return "quarantine_schema_violation"
    return "keep"


def content_fingerprint(node):
    topic = normalized_text(node.get("topic"))
    content = normalized_text(node.get("content"))
    if not topic and not content:
        return None
    return hashlib.sha256(f"{topic}\n{content}".encode("utf-8")).hexdigest()[:16]


def normalized_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def match_key(node, index):
    if node.get("id"):
        return {"id": node["id"]}
    if node.get("candidate_id"):
        return {"candidate_id": node["candidate_id"]}
    return {"export_index": index}


def load_export(path):
    return [record.data for record in load_jsonl(path, allow_missing=False)]


def maintenance_main():
    parser = argparse.ArgumentParser(description="Audit exported FalkorDB Memory nodes and generate a cleanup migration plan.")
    parser.add_argument("--export-jsonl", required=True, help="JSONL export where each line is one Memory node properties object.")
    parser.add_argument("--report-json", help="Write inventory/audit report JSON.")
    parser.add_argument("--plan-jsonl", help="Write proposed migration actions JSONL.")
    parser.add_argument("--rollback-jsonl", help="Write rollback restore records JSONL.")
    args = parser.parse_args()

    nodes = load_export(args.export_jsonl)
    audit = audit_memory_nodes(nodes)
    plan, rollback = build_migration_plan(nodes, audit)

    if args.report_json:
        os.makedirs(os.path.dirname(args.report_json) or ".", exist_ok=True)
        with open(args.report_json, "w", encoding="utf-8") as handle:
            json.dump(audit, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    if args.plan_jsonl:
        write_jsonl(args.plan_jsonl, plan)
    if args.rollback_jsonl:
        write_jsonl(args.rollback_jsonl, rollback)

    print(json.dumps({**audit["summary"], "migration_actions": len(plan)}, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    maintenance_main()

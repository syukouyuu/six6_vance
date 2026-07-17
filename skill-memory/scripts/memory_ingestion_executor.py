import argparse
import datetime
import json
import os
import sys

from falkordb import FalkorDB
from redis.exceptions import RedisError


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(REPO_ROOT, "runtime", "scripts"))

from runtime_io import (  # noqa: E402
    SchemaValidationError,
    generate_memory_id,
    load_jsonl,
    load_schema,
    validate_object,
    write_jsonl,
)


MEMORY_SCHEMA_VERSION = "memory-node.v2"
MUTABLE_FIELDS = (
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
)
RETURN_FIELDS = ("id", "candidate_id", "schema_version") + MUTABLE_FIELDS


class IngestionConflictError(RuntimeError):
    pass


class FalkorGraphBackend:
    def __init__(self, *, graph, host="localhost", port=6379, username=None, password=None):
        db = FalkorDB(host=host, port=port, username=username, password=password)
        self._graph = db.select_graph(graph)

    def find_by_candidate_id(self, candidate_id):
        returned = ", ".join(f"m.{key}" for key in RETURN_FIELDS)
        result = self._query(
            f"MATCH (m:Memory {{candidate_id: $candidate_id}}) RETURN {returned} LIMIT 2",
            {"candidate_id": candidate_id},
        )
        rows = result.result_set
        if len(rows) > 1:
            raise IngestionConflictError(f"multiple Memory nodes found for candidate_id {candidate_id!r}")
        if not rows:
            return None
        return {key: value for key, value in zip(RETURN_FIELDS, rows[0])}

    def create_memory(self, memory):
        fields = ", ".join(f"{key}: ${key}" for key in memory)
        self._query(f"CREATE (:Memory {{{fields}}})", memory)

    def update_memory(self, memory):
        assignments = ", ".join(f"m.{key} = ${key}" for key in MUTABLE_FIELDS if key in memory)
        self._query(
            f"MATCH (m:Memory {{candidate_id: $candidate_id}}) SET {assignments}",
            memory,
        )

    def _query(self, query, params):
        try:
            return self._graph.query(query, params=params)
        except RedisError as exc:
            raise RuntimeError(f"FalkorDB query failed: {exc}") from exc


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ingest_approved_decisions(input_path, backend, *, ingested_at=None):
    ingested_at = ingested_at or utc_now()
    approved_schema = load_schema("approved-decision.v2", REPO_ROOT)
    memory_schema = load_schema("memory-node.v2", REPO_ROOT)
    report = {
        "input_path": input_path,
        "ingested_at": ingested_at,
        "summary": {"created": 0, "updated": 0, "skipped": 0, "failed": 0},
        "results": [],
    }

    try:
        records = load_jsonl(input_path, schema=approved_schema, allow_missing=False)
    except Exception as exc:
        report["summary"]["failed"] += 1
        report["results"].append(_result("fail", None, input_path, None, str(exc)))
        return report

    seen = set()
    for record in records:
        candidate_id = record.data["candidate_id"]
        if candidate_id in seen:
            report["summary"]["failed"] += 1
            report["results"].append(_result("fail", candidate_id, record.path, record.line_no, "duplicate candidate_id in input batch"))
            continue
        seen.add(candidate_id)

        try:
            memory = approved_to_memory_node(record.data, ingested_at=ingested_at)
            errors = validate_object(memory, memory_schema, location=f"{record.path}:{record.line_no}")
            if errors:
                raise SchemaValidationError(errors)
            existing = backend.find_by_candidate_id(candidate_id)
            if existing is None:
                backend.create_memory(memory)
                action = "created"
            else:
                _assert_existing_is_compatible(existing, memory)
                if _mutable_fields_match(existing, memory):
                    action = "skipped"
                else:
                    merged = dict(memory)
                    merged["id"] = existing["id"]
                    backend.update_memory(merged)
                    action = "updated"
                    memory = merged
            report["summary"][action] += 1
            report["results"].append(_result(action, candidate_id, record.path, record.line_no, None, memory["id"]))
        except Exception as exc:
            report["summary"]["failed"] += 1
            report["results"].append(_result("fail", candidate_id, record.path, record.line_no, str(exc)))
    return report


def approved_to_memory_node(approved, *, ingested_at):
    node = {
        "id": generate_memory_id(approved["candidate_id"], timestamp=approved["timestamp"]),
        "candidate_id": approved["candidate_id"],
        "topic": approved["topic"],
        "content": approved["content"],
        "timestamp": approved["timestamp"],
        "category": approved["category"],
        "maturity": approved["maturity"],
        "source": approved["source"],
        "schema_version": MEMORY_SCHEMA_VERSION,
    }
    for key in ("source_file", "source_section", "approved_at"):
        if key in approved:
            node[key] = approved[key]
    node["ingested_at"] = ingested_at
    return node


def write_ingestion_report(base_dir, report):
    safe_time = report["ingested_at"].replace(":", "").replace("-", "")
    path = os.path.join(base_dir, "memory", "ingestion", f"{safe_time}-ingestion-report.jsonl")
    latest_path = os.path.join(base_dir, "memory", "ingestion", "latest-ingestion-report.jsonl")
    write_jsonl(path, report["results"])
    write_jsonl(latest_path, report["results"])
    return path, latest_path


def default_approved_path(base_dir):
    return os.path.join(base_dir, "memory", "approved_decisions", "latest-approved-seeds.jsonl")


def _assert_existing_is_compatible(existing, memory):
    if existing.get("candidate_id") != memory["candidate_id"]:
        raise IngestionConflictError("lookup returned a Memory node with a different candidate_id")
    if existing.get("schema_version") not in (None, MEMORY_SCHEMA_VERSION):
        raise IngestionConflictError(
            f"existing Memory schema_version is {existing.get('schema_version')!r}, expected {MEMORY_SCHEMA_VERSION!r}"
        )
    if existing.get("id") == memory["candidate_id"]:
        raise IngestionConflictError("existing Memory.id reuses candidate_id and violates memory-node.v2")


def _mutable_fields_match(existing, memory):
    return all(existing.get(key) == memory.get(key) for key in MUTABLE_FIELDS if key in existing or key in memory)


def _result(action, candidate_id, path, line_no, error=None, memory_id=None):
    result = {
        "action": action,
        "candidate_id": candidate_id,
        "memory_id": memory_id,
        "source_path": path,
        "source_line": line_no,
    }
    if error:
        result["error"] = error
    return result


def ingestion_executor_main():
    parser = argparse.ArgumentParser(description="Ingest approved-decision.v2 JSONL into FalkorDB Memory nodes.")
    parser.add_argument("--base-dir", default=".", help="Base directory containing memory/approved_decisions/.")
    parser.add_argument("--input", help="Approved JSONL path. Defaults to memory/approved_decisions/latest-approved-seeds.jsonl.")
    parser.add_argument("--graph", default=os.environ.get("SIX6_FALKOR_GRAPH", "FreyaGraph"), help="FalkorDB graph name.")
    parser.add_argument("--redis-host", default=os.environ.get("FALKORDB_HOST", "localhost"), help="FalkorDB host. Defaults to $FALKORDB_HOST.")
    parser.add_argument("--redis-port", type=int, default=int(os.environ.get("FALKORDB_PORT", "6379")), help="FalkorDB port. Defaults to $FALKORDB_PORT.")
    parser.add_argument("--redis-user", default=os.environ.get("FALKORDB_USER"), help="FalkorDB ACL username. Defaults to $FALKORDB_USER.")
    parser.add_argument("--redis-password", default=os.environ.get("FALKORDB_PASS"), help="FalkorDB password. Defaults to $FALKORDB_PASS.")
    parser.add_argument("--ingested-at", help="UTC ingestion timestamp, useful for reproducible tests.")
    args = parser.parse_args()

    input_path = args.input or default_approved_path(args.base_dir)
    backend = FalkorGraphBackend(
        graph=args.graph,
        host=args.redis_host,
        port=args.redis_port,
        username=args.redis_user,
        password=args.redis_password,
    )
    report = ingest_approved_decisions(input_path, backend, ingested_at=args.ingested_at)
    paths = write_ingestion_report(args.base_dir, report)
    print(json.dumps(report["summary"], ensure_ascii=False, separators=(",", ":")))
    for path in paths:
        print(path)
    if report["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    ingestion_executor_main()

import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "runtime", "scripts"))
sys.path.append(os.path.join(ROOT, "skill-memory", "scripts"))

from runtime_io import generate_memory_id, load_jsonl, write_jsonl  # noqa: E402
from memory_ingestion_executor import (  # noqa: E402
    approved_to_memory_node,
    ingest_approved_decisions,
    write_ingestion_report,
)


class FakeMemoryBackend:
    def __init__(self):
        self.nodes = {}

    def find_by_candidate_id(self, candidate_id):
        node = self.nodes.get(candidate_id)
        return dict(node) if node else None

    def create_memory(self, memory):
        self.nodes[memory["candidate_id"]] = dict(memory)

    def update_memory(self, memory):
        self.nodes[memory["candidate_id"]] = dict(memory)


class FailingMemoryBackend(FakeMemoryBackend):
    def create_memory(self, memory):
        raise RuntimeError("FalkorDB unavailable")


class MemoryIngestionExecutorTests(unittest.TestCase):
    def test_maps_approved_decision_to_memory_node_v2(self):
        approved = self._approved_record()
        node = approved_to_memory_node(approved, ingested_at="2026-05-20T14:00:00Z")

        self.assertEqual(node["id"], generate_memory_id(approved["candidate_id"], timestamp=approved["timestamp"]))
        self.assertNotEqual(node["id"], approved["candidate_id"])
        self.assertEqual(node["candidate_id"], approved["candidate_id"])
        self.assertEqual(node["schema_version"], "memory-node.v2")

    def test_repeated_ingestion_updates_existing_node_without_duplicate_create(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "approved.jsonl")
            approved = self._approved_record()
            write_jsonl(input_path, [approved])
            backend = FakeMemoryBackend()

            first = ingest_approved_decisions(input_path, backend, ingested_at="2026-05-20T14:00:00Z")
            approved["content"] = "更新后的核准内容会覆盖同 candidate_id 的 Memory 节点。"
            write_jsonl(input_path, [approved])
            second = ingest_approved_decisions(input_path, backend, ingested_at="2026-05-20T15:00:00Z")

            self.assertEqual(first["summary"], {"created": 1, "updated": 0, "skipped": 0, "failed": 0})
            self.assertEqual(second["summary"], {"created": 0, "updated": 1, "skipped": 0, "failed": 0})
            self.assertEqual(len(backend.nodes), 1)
            node = backend.nodes[approved["candidate_id"]]
            self.assertEqual(node["content"], "更新后的核准内容会覆盖同 candidate_id 的 Memory 节点。")
            self.assertEqual(node["id"], first["results"][0]["memory_id"])
            self.assertEqual(second["results"][0]["candidate_id"], approved["candidate_id"])

    def test_exact_repeat_with_same_ingestion_clock_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "approved.jsonl")
            write_jsonl(input_path, [self._approved_record()])
            backend = FakeMemoryBackend()

            ingest_approved_decisions(input_path, backend, ingested_at="2026-05-20T14:00:00Z")
            report = ingest_approved_decisions(input_path, backend, ingested_at="2026-05-20T14:00:00Z")

            self.assertEqual(report["summary"], {"created": 0, "updated": 0, "skipped": 1, "failed": 0})
            self.assertEqual(report["results"][0]["action"], "skipped")

    def test_invalid_schema_is_reported_before_db_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "approved.jsonl")
            invalid = self._approved_record()
            invalid.pop("approved_at")
            write_jsonl(input_path, [invalid])
            backend = FakeMemoryBackend()

            report = ingest_approved_decisions(input_path, backend, ingested_at="2026-05-20T14:00:00Z")

            self.assertEqual(report["summary"], {"created": 0, "updated": 0, "skipped": 0, "failed": 1})
            self.assertEqual(backend.nodes, {})
            self.assertIn("approved_at", report["results"][0]["error"])

    def test_duplicate_candidate_id_in_batch_is_audited_as_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "approved.jsonl")
            write_jsonl(input_path, [self._approved_record(), self._approved_record()])

            report = ingest_approved_decisions(input_path, FakeMemoryBackend(), ingested_at="2026-05-20T14:00:00Z")

            self.assertEqual(report["summary"], {"created": 1, "updated": 0, "skipped": 0, "failed": 1})
            self.assertEqual(report["results"][1]["candidate_id"], "pro-260520-123456abcdef")
            self.assertIn("duplicate candidate_id", report["results"][1]["error"])

    def test_db_errors_are_reported_per_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "approved.jsonl")
            write_jsonl(input_path, [self._approved_record()])

            report = ingest_approved_decisions(input_path, FailingMemoryBackend(), ingested_at="2026-05-20T14:00:00Z")

            self.assertEqual(report["summary"], {"created": 0, "updated": 0, "skipped": 0, "failed": 1})
            self.assertEqual(report["results"][0]["candidate_id"], "pro-260520-123456abcdef")
            self.assertIn("FalkorDB unavailable", report["results"][0]["error"])

    def test_writes_auditable_report_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = {
                "ingested_at": "2026-05-20T14:00:00Z",
                "results": [
                    {
                        "action": "created",
                        "candidate_id": "pro-260520-123456abcdef",
                        "memory_id": "memnode-260520-1234567890abcdef",
                        "source_path": "approved.jsonl",
                        "source_line": 1,
                    }
                ],
            }

            path, latest_path = write_ingestion_report(tmpdir, report)

            self.assertEqual(load_jsonl(path)[0].data["candidate_id"], "pro-260520-123456abcdef")
            self.assertEqual(load_jsonl(latest_path)[0].data["action"], "created")

    def _approved_record(self):
        return {
            "candidate_id": "pro-260520-123456abcdef",
            "topic": "Memory ingestion executor",
            "content": "approved-decision.v2 只由 ingestion executor 写入 FalkorDB Memory。",
            "timestamp": "2026-05-20T13:00:00Z",
            "category": "protocol",
            "maturity": 1,
            "source": "docs/MEMORY_V1_PROTOCOL.md",
            "source_file": "docs/MEMORY_V1_PROTOCOL.md",
            "source_section": "FalkorDB Memory",
            "approved_at": "2026-05-20T13:30:00Z",
            "schema_version": "approved-decision.v2",
        }


if __name__ == "__main__":
    unittest.main()

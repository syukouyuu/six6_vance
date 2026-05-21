import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "runtime", "scripts"))
sys.path.append(os.path.join(ROOT, "skill-memory", "scripts"))

from runtime_io import load_jsonl, write_jsonl  # noqa: E402
from memory_graph_maintenance import audit_memory_nodes, build_migration_plan, maintenance_main  # noqa: E402


class MemoryGraphMaintenanceTests(unittest.TestCase):
    def test_audit_separates_valid_nodes_field_cleanup_and_quarantine(self):
        nodes = [
            self._memory_node(),
            {**self._memory_node(candidate_id="les-260520-abcdef123456", topic="Legacy field", content="Legacy field should be stripped."), "legacy_field": "old"},
            {**self._memory_node(candidate_id="fac-260520-abcdef123456", topic="Bad id", content="Candidate id cannot be reused as node id."), "id": "fac-260520-abcdef123456"},
            {**self._memory_node(candidate_id=None, topic="Missing candidate", content="Missing candidate id requires quarantine."), "candidate_id": None},
        ]

        audit = audit_memory_nodes(nodes)

        self.assertEqual(audit["summary"]["total_memory_nodes"], 4)
        self.assertEqual(audit["summary"]["schema_valid"], 1)
        self.assertEqual(audit["records"][1]["migration_action"], "strip_unknown_fields")
        self.assertEqual(audit["records"][2]["migration_action"], "quarantine_candidate_id_reused_as_id")
        self.assertEqual(audit["records"][3]["migration_action"], "quarantine_missing_candidate_id")

    def test_duplicate_strategy_prefers_candidate_id_then_content_fingerprint(self):
        duplicate_candidate = self._memory_node(candidate_id="pro-260520-aaaaaaaaaaaa")
        content_duplicate = self._memory_node(candidate_id="les-260520-bbbbbbbbbbbb", topic="Same", content="Same content")
        nodes = [
            duplicate_candidate,
            {**duplicate_candidate, "id": "memnode-260520-2222222222222222"},
            content_duplicate,
            {**content_duplicate, "id": "memnode-260520-3333333333333333", "candidate_id": "fac-260520-cccccccccccc"},
        ]

        audit = audit_memory_nodes(nodes)

        self.assertEqual(audit["summary"]["duplicate_candidate_id_groups"], 1)
        self.assertEqual(audit["summary"]["duplicate_content_groups"], 2)
        self.assertEqual(audit["records"][0]["migration_action"], "dedupe_candidate_id")
        self.assertEqual(audit["records"][2]["migration_action"], "review_content_duplicate")

    def test_migration_plan_keeps_valid_nodes_and_writes_rollback(self):
        nodes = [
            self._memory_node(),
            {**self._memory_node(candidate_id="les-260520-abcdef123456", topic="Legacy field", content="Legacy field should be stripped."), "legacy_field": "old"},
            {**self._memory_node(candidate_id=None, topic="Missing candidate", content="Missing candidate id requires quarantine."), "candidate_id": None},
        ]
        audit = audit_memory_nodes(nodes)

        plan, rollback = build_migration_plan(nodes, audit)

        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["action"], "update_properties")
        self.assertEqual(plan[0]["remove_unknown_fields"], ["legacy_field"])
        self.assertEqual(plan[1]["action"], "quarantine")
        self.assertEqual(len(rollback), 2)
        self.assertEqual(rollback[0]["restore"]["legacy_field"], "old")

    def test_cli_writes_report_plan_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = os.path.join(tmpdir, "memory-export.jsonl")
            report_path = os.path.join(tmpdir, "report.json")
            plan_path = os.path.join(tmpdir, "plan.jsonl")
            rollback_path = os.path.join(tmpdir, "rollback.jsonl")
            write_jsonl(export_path, [{**self._memory_node(), "legacy_field": "old"}])

            old_argv = sys.argv
            try:
                sys.argv = [
                    "memory-graph-maintenance",
                    "--export-jsonl",
                    export_path,
                    "--report-json",
                    report_path,
                    "--plan-jsonl",
                    plan_path,
                    "--rollback-jsonl",
                    rollback_path,
                ]
                maintenance_main()
            finally:
                sys.argv = old_argv

            self.assertTrue(os.path.exists(report_path))
            self.assertEqual(load_jsonl(plan_path)[0].data["action"], "update_properties")
            self.assertEqual(load_jsonl(rollback_path)[0].data["restore"]["legacy_field"], "old")

    def _memory_node(self, *, candidate_id="pro-260520-123456abcdef", topic="Memory cleanup", content="Clean Memory nodes keep V2 fields only."):
        return {
            "id": "memnode-260520-1234567890abcdef",
            "candidate_id": candidate_id,
            "topic": topic,
            "content": content,
            "timestamp": "2026-05-20T13:00:00Z",
            "category": "protocol",
            "maturity": 1,
            "source": "docs/MEMORY_V1_PROTOCOL.md",
            "schema_version": "memory-node.v2",
        }


if __name__ == "__main__":
    unittest.main()

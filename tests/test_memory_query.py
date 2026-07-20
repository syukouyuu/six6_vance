import os
import sys
import unittest
from unittest.mock import MagicMock, patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "skill-memory", "scripts"))

import memory_query  # noqa: E402
from memory_query import QUERY_FIELDS, ReadOnlyMemoryBackend, format_markdown  # noqa: E402


def make_backend(rows):
    backend = ReadOnlyMemoryBackend.__new__(ReadOnlyMemoryBackend)
    result = MagicMock()
    result.result_set = rows
    backend._query = MagicMock(return_value=result)
    return backend


class ReadOnlyMemoryBackendTests(unittest.TestCase):
    def test_keyword_search_builds_case_insensitive_contains_query(self):
        backend = make_backend([])
        backend.search(keyword="falkor")
        query, params = backend._query.call_args.args
        self.assertIn("toLower(m.topic) CONTAINS toLower($keyword)", query)
        self.assertIn("toLower(m.content) CONTAINS toLower($keyword)", query)
        self.assertEqual(params["keyword"], "falkor")

    def test_category_and_maturity_filters_are_combined_with_and(self):
        backend = make_backend([])
        backend.search(category="preference", maturity="stable")
        query, params = backend._query.call_args.args
        self.assertIn("m.category = $category AND m.maturity = $maturity", query)
        self.assertEqual(params["category"], "preference")
        self.assertEqual(params["maturity"], "stable")

    def test_no_filters_matches_all_memories_ordered_by_timestamp(self):
        backend = make_backend([])
        backend.search()
        query, params = backend._query.call_args.args
        self.assertNotIn("WHERE", query)
        self.assertIn("ORDER BY m.timestamp DESC", query)
        self.assertEqual(params["limit"], 10)

    def test_query_is_read_only(self):
        backend = make_backend([])
        backend.search(keyword="x", category="y", maturity="z", order_by="ingested_at", limit=3)
        query, _ = backend._query.call_args.args
        for verb in ("CREATE", "SET", "DELETE", "MERGE", "REMOVE"):
            self.assertNotIn(verb, query.upper().replace("MATCH", ""))

    def test_rows_are_mapped_to_field_dicts(self):
        row = ["topic-1", "content-1", "decision", "stable", "2026-03-31T00:00:00Z", "fac-1", "2026-07-18T00:00:00Z"]
        backend = make_backend([row])
        memories = backend.search(keyword="topic")
        self.assertEqual(memories, [dict(zip(QUERY_FIELDS, row))])


class MemoryQueryMainTests(unittest.TestCase):
    def test_errors_out_when_graph_env_is_unset(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", ["memory_query.py", "--keyword", "x"]):
            with self.assertRaises(SystemExit) as ctx:
                memory_query.memory_query_main()
            self.assertEqual(ctx.exception.code, 2)

    def test_recent_orders_by_ingested_at_and_overrides_limit(self):
        backend = make_backend([])
        with patch.dict(os.environ, {"SIX6_FALKOR_GRAPH": "TestGraph"}, clear=True), \
                patch.object(memory_query, "ReadOnlyMemoryBackend", return_value=backend) as backend_cls, \
                patch.object(sys, "argv", ["memory_query.py", "--recent", "5", "--limit", "99"]):
            memory_query.memory_query_main()
        self.assertEqual(backend_cls.call_args.kwargs["graph"], "TestGraph")
        query, params = backend._query.call_args.args
        self.assertIn("ORDER BY m.ingested_at DESC", query)
        self.assertEqual(params["limit"], 5)


class FormatMarkdownTests(unittest.TestCase):
    def test_empty_result_reports_no_matches(self):
        self.assertEqual(format_markdown([]), "(no matching memories)")

    def test_memory_is_rendered_with_topic_and_content(self):
        rendered = format_markdown([
            {"topic": "t", "content": "c", "category": "decision", "maturity": "stable", "timestamp": "2026-03-31", "candidate_id": "fac-1"}
        ])
        self.assertIn("### t", rendered)
        self.assertIn("c", rendered)
        self.assertIn("candidate_id: fac-1", rendered)


if __name__ == "__main__":
    unittest.main()

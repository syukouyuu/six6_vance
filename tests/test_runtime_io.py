import os
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "runtime", "scripts"))

from runtime_io import (  # noqa: E402
    JsonlError,
    SchemaValidationError,
    apply_env_defaults,
    generate_candidate_id,
    generate_memory_id,
    load_jsonl,
    load_schema,
    validate_records,
    write_jsonl,
)


class RuntimeIoTests(unittest.TestCase):
    def test_jsonl_reports_bad_line_number(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "items.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"ok":true}\n')
                handle.write("{bad json}\n")

            with self.assertRaises(JsonlError) as ctx:
                load_jsonl(path)

            self.assertIn(":2: invalid JSON", str(ctx.exception))

    def test_atomic_jsonl_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "items.jsonl")
            write_jsonl(path, [{"type": "x", "ts": 1}])

            records = load_jsonl(path, schema=load_schema("inbox-item", ROOT))

            self.assertEqual(records[0].data, {"type": "x", "ts": 1})

    def test_schema_validation_reports_field_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "items.jsonl")
            write_jsonl(path, [{"type": "", "ts": "bad"}])
            records = load_jsonl(path)

            with self.assertRaises(SchemaValidationError) as ctx:
                validate_records(records, load_schema("inbox-item", ROOT))

            message = str(ctx.exception)
            self.assertIn("items.jsonl:1.type", message)
            self.assertIn("items.jsonl:1.ts", message)

    def test_candidate_and_memory_ids_follow_protocol(self):
        candidate_id = generate_candidate_id(
            "protocol",
            "docs/MEMORY_V1_PROTOCOL.md",
            "字段定义 / Candidates JSONL",
            "Memory V1 候选层保留 candidate_id",
            "候选文件必须保留稳定的 candidate_id，供 review、approve、discard 与入库幂等更新使用，不得直接作为 FalkorDB Memory.id。",
            timestamp="2026-05-16T12:21:26Z",
        )

        self.assertEqual(candidate_id, "pro-260516-b152e6818eb2")
        self.assertEqual(
            generate_memory_id(candidate_id, timestamp="2026-05-16T13:20:00Z"),
            "memnode-260516-8bd038a64d3476ca",
        )

    def test_apply_env_defaults_loads_unset_values_without_overriding_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write("LLM_API_KEY='from-file'\nLLM_MODEL=from-file-model\n")

            with patch.dict(os.environ, {"LLM_MODEL": "from-environment"}, clear=True):
                applied = apply_env_defaults(env_path)
                self.assertEqual(os.environ["LLM_API_KEY"], "from-file")
                self.assertEqual(os.environ["LLM_MODEL"], "from-environment")
                self.assertEqual(applied, {"LLM_API_KEY"})


if __name__ == "__main__":
    unittest.main()

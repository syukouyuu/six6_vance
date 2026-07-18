import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "runtime", "scripts"))
sys.path.append(os.path.join(ROOT, "skill-memory", "scripts"))

from runtime_io import load_jsonl, write_jsonl  # noqa: E402
from memory_pipeline import (  # noqa: E402
    generate_candidates,
    parse_discord_review_command,
    render_review_report,
    render_discord_review,
    review_reply_main,
    route_decisions,
    split_rule_deprecations,
    write_candidate_batch,
    write_decision_batches,
    write_review_report,
)


class MemoryPipelineTests(unittest.TestCase):
    def test_folded_item_is_merged_and_long_item_uses_marked_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            text = "第一句完整陈述。" * 30
            with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as handle:
                handle.write("- **主题**: " + text + "\n  折行续写必须合并。\n")
            candidates = generate_candidates(tmpdir, source_files=("MEMORY.md",), created_at="2026-05-20T12:00:00Z")
            self.assertEqual(len(candidates), 1)
            self.assertTrue(candidates[0]["truncated"])
            self.assertLessEqual(len(candidates[0]["content"]), 200)

    def test_chinese_fallback_truncates_at_sentence_boundary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as handle:
                handle.write("- **主题**: " + "这是一句没有空格分隔的中文完整陈述。" * 20 + "\n")
            candidates = generate_candidates(tmpdir, source_files=("MEMORY.md",), created_at="2026-05-20T12:00:00Z")
            self.assertEqual(len(candidates), 1)
            self.assertTrue(candidates[0]["truncated"])
            self.assertLessEqual(len(candidates[0]["content"]), 200)
            self.assertTrue(candidates[0]["content"].endswith("。"))

    def test_long_item_is_marked_summarized_when_llm_returns_a_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as handle:
                handle.write("- **主题**: " + ("项目 Alpha 于 2026-03-18 保留 42 条记录。" * 12))
            with patch("memory_pipeline.call_llm_detailed", return_value=("项目 Alpha 于 2026-03-18 保留 42 条记录。", None)):
                candidates = generate_candidates(tmpdir, source_files=("MEMORY.md",), created_at="2026-05-20T12:00:00Z", llm_config={"api_base": "http://mock", "api_key": "test", "model": "mock"})
            self.assertTrue(candidates[0]["summarized"])
    def test_candidate_generation_is_stable_and_schema_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_sources(tmpdir)

            first = generate_candidates(tmpdir, created_at="2026-05-20T12:00:00Z")
            second = generate_candidates(tmpdir, created_at="2026-05-20T12:00:00Z")

            self.assertEqual(first, second)
            self.assertEqual([item["review_id"] for item in first], ["01", "02"])
            self.assertTrue(all(item["schema_version"] == "memory-candidate.v1" for item in first))
            self.assertTrue(all(item["candidate_id"] != item["review_id"] for item in first))

            batch_path, latest_path = write_candidate_batch(tmpdir, first, created_at="2026-05-20T12:00:00Z")
            self.assertEqual(batch_path, os.path.join(tmpdir, "memory", "candidates", "2026-05-20-memory-candidates.jsonl"))
            self.assertEqual(load_jsonl(latest_path)[0].data, first[0])

    def test_isolated_batch_does_not_write_a_latest_pointer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates = self._review_candidates()
            output_dir = os.path.join(tmpdir, "monthly-review", "2026-02", "candidates")

            (batch_path,) = write_candidate_batch(
                tmpdir,
                candidates,
                created_at="2026-02-28T23:59:59Z",
                output_dir=output_dir,
                batch_label="2026-02",
                write_latest=False,
            )

            self.assertEqual(batch_path, os.path.join(output_dir, "2026-02-memory-candidates.jsonl"))
            self.assertTrue(os.path.isfile(batch_path))
            self.assertFalse(os.path.exists(os.path.join(output_dir, "latest-memory-candidates.jsonl")))

    def test_review_report_shows_review_id_and_candidate_id(self):
        candidates = [
            {
                "review_id": "01",
                "candidate_id": "pro-260520-123456abcdef",
                "topic": "候选层 ID 分离",
                "content": "review_id 只用于阅读，candidate_id 才用于分流。",
                "timestamp": "2026-05-20T12:00:00Z",
                "category": "protocol",
                "maturity": 1,
                "source": "MEMORY.md",
                "source_file": "MEMORY.md",
                "source_section": "root",
                "created_at": "2026-05-20T12:00:00Z",
                "schema_version": "memory-candidate.v1",
                "hash_input": "MEMORY.md\nroot\n候选层 ID 分离\nreview_id 只用于阅读，candidate_id 才用于分流。",
            }
        ]

        report = render_review_report(candidates)

        self.assertIn("## 01 | pro-260520-123456abcdef", report)
        self.assertIn("decision: pending", report)

    def test_decision_router_uses_candidate_id_for_stable_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_sources(tmpdir)
            candidates = generate_candidates(tmpdir, created_at="2026-05-20T12:00:00Z")
            _, latest_candidates = write_candidate_batch(tmpdir, candidates, created_at="2026-05-20T12:00:00Z")
            write_review_report(tmpdir, candidates, created_at="2026-05-20T12:00:00Z")
            review_path = os.path.join(tmpdir, "reviewed.jsonl")
            write_jsonl(
                review_path,
                [
                    {"candidate_id": candidates[0]["candidate_id"], "decision": "approved"},
                    {
                        "candidate_id": candidates[1]["candidate_id"],
                        "decision": "deprecated",
                        "deprecation_reason": "运维细节，不入正式记忆",
                    },
                ],
            )

            approved, deprecated = route_decisions(
                tmpdir,
                latest_candidates,
                review_path,
                decided_at="2026-05-20T13:00:00Z",
            )
            write_decision_batches(tmpdir, approved, deprecated, decided_at="2026-05-20T13:00:00Z")

            self.assertEqual(approved[0]["candidate_id"], candidates[0]["candidate_id"])
            self.assertNotIn("review_id", approved[0])
            self.assertEqual(approved[0]["schema_version"], "approved-decision.v2")
            self.assertEqual(deprecated[0]["candidate_id"], candidates[1]["candidate_id"])
            self.assertEqual(deprecated[0]["schema_version"], "deprecated-decision.v2")
            self.assertEqual(approved[0]["decided_by"], "human")
            self.assertEqual(deprecated[0]["decided_by"], "human")

    def test_rule_auto_deprecations_do_not_enter_pending_review(self):
        candidates = self._review_candidates()
        candidates[1]["content"] = "Homebrew 路径调整属于运维琐事。"

        pending, deprecated = split_rule_deprecations(candidates, decided_at="2026-05-20T12:00:00Z")

        self.assertEqual([item["review_id"] for item in pending], ["01"])
        self.assertEqual(deprecated[0]["decided_by"], "rule")
        self.assertIn("运维琐事", deprecated[0]["deprecation_reason"])

        pending, deprecated = split_rule_deprecations(candidates, enabled=False)
        self.assertEqual(len(pending), 2)
        self.assertEqual(deprecated, [])

    def test_discord_cards_and_commands_keep_candidate_ids_as_routing_keys(self):
        candidates = self._review_candidates()
        pages = render_discord_review(candidates, date="2026-05-20")

        self.assertEqual(len(pages), 1)
        self.assertIn("01 📜 候选层 ID 分离", pages[0])
        self.assertIn("(protocol · pro-260520-123456abcdef)", pages[0])
        self.assertLessEqual(len(pages[0]), 2000)

        decisions = parse_discord_review_command("收 01，其余弃", candidates)
        self.assertEqual(decisions[0], {"candidate_id": "pro-260520-123456abcdef", "decision": "approved"})
        self.assertEqual(decisions[1]["candidate_id"], "fac-260520-abcdef123456")
        with self.assertRaises(ValueError):
            parse_discord_review_command("收 99，其余弃", candidates)
        with self.assertRaises(ValueError):
            parse_discord_review_command("收 01", candidates)

    def test_review_reply_cli_writes_decisions_and_prints_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates = self._review_candidates()
            candidates_path = os.path.join(tmpdir, "candidates.jsonl")
            out_path = os.path.join(tmpdir, "review-decisions.jsonl")
            write_jsonl(candidates_path, candidates)

            output = self._run_review_reply(
                "--base-dir", tmpdir, "--candidates", candidates_path,
                "--command", "收 01，其余弃", "--out", out_path,
            )

            self.assertIn(f"approved 1 / deprecated 1 / {out_path}", output)
            self.assertEqual(
                [record.data for record in load_jsonl(out_path)],
                [
                    {"candidate_id": candidates[0]["candidate_id"], "decision": "approved"},
                    {"candidate_id": candidates[1]["candidate_id"], "decision": "deprecated", "reason": "Discord 其余弃"},
                ],
            )

    def test_review_reply_cli_rejects_ambiguous_command_without_writing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates_path = os.path.join(tmpdir, "candidates.jsonl")
            out_path = os.path.join(tmpdir, "review-decisions.jsonl")
            write_jsonl(candidates_path, self._review_candidates())

            with self.assertRaises(SystemExit) as caught, redirect_stderr(StringIO()):
                self._run_review_reply(
                    "--base-dir", tmpdir, "--candidates", candidates_path,
                    "--command", "收 01", "--out", out_path,
                )

            self.assertNotEqual(caught.exception.code, 0)
            self.assertFalse(os.path.exists(out_path))

    def _run_review_reply(self, *arguments):
        original_argv = sys.argv
        output = StringIO()
        try:
            sys.argv = ["memory-review-reply.py", *arguments]
            with redirect_stdout(output):
                review_reply_main()
        finally:
            sys.argv = original_argv
        return output.getvalue()

    def _review_candidates(self):
        return [
            {
                "review_id": "01", "candidate_id": "pro-260520-123456abcdef", "topic": "候选层 ID 分离",
                "content": "review_id 只用于阅读，candidate_id 才用于分流。", "timestamp": "2026-05-20T12:00:00Z",
                "category": "protocol", "maturity": 1, "source": "MEMORY.md", "source_file": "MEMORY.md",
                "source_section": "root", "created_at": "2026-05-20T12:00:00Z", "schema_version": "memory-candidate.v1", "hash_input": "x",
            },
            {
                "review_id": "02", "candidate_id": "fac-260520-abcdef123456", "topic": "普通事实",
                "content": "保留给人工审核。", "timestamp": "2026-05-20T12:00:00Z",
                "category": "fact", "maturity": 1, "source": "MEMORY.md", "source_file": "MEMORY.md",
                "source_section": "root", "created_at": "2026-05-20T12:00:00Z", "schema_version": "memory-candidate.v1", "hash_input": "y",
            },
        ]

    def _write_sources(self, tmpdir):
        with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as handle:
            handle.write(
                "# MEMORY\n\n"
                "## 关键协议\n"
                "- **候选层 ID 分离**: review_id 只用于阅读，candidate_id 才用于分流。\n"
            )
        os.makedirs(os.path.join(tmpdir, "data"), exist_ok=True)
        with open(os.path.join(tmpdir, "data", "evolution.md"), "w", encoding="utf-8") as handle:
            handle.write(
                "## 系统自我进化记录\n"
                "- **运行环境迁移记录**: Homebrew 路径调整属于运维细节，不进入正式记忆。\n"
            )


if __name__ == "__main__":
    unittest.main()

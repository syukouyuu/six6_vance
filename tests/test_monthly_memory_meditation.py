import os
import sys
import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "skill-memory", "scripts"))

import monthly_memory_meditation as monthly  # noqa: E402


class MonthlyMemoryMeditationTests(unittest.TestCase):
    def test_config_source_marks_env_file_with_environment_variable_name(self):
        self.assertEqual(monthly.config_source("LLM_API_BASE", {"LLM_API_BASE"}, [], "--api-base"), ".env")

    def test_preflight_only_accepts_canonical_daily_files_in_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = os.path.join(tmpdir, "memory")
            os.makedirs(memory_dir)
            for name in ("2026-02-02.md", "2026-02-01.md", "2026-02-01-note.md"):
                with open(os.path.join(memory_dir, name), "w", encoding="utf-8") as handle:
                    handle.write(name)

            present, missing = monthly.preflight(tmpdir, monthly.parse_month("2026-02"))

            self.assertEqual(present, ["2026-02-01", "2026-02-02"])
            self.assertEqual(missing[0], "2026-02-03")
            self.assertEqual(missing[-1], "2026-02-28")

    def test_dry_run_writes_no_monthly_package(self):
        parser = monthly.build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = os.path.join(tmpdir, "memory")
            os.makedirs(memory_dir)
            with open(os.path.join(memory_dir, "2026-02-01.md"), "w", encoding="utf-8") as handle:
                handle.write("- daily note\n")
            args = parser.parse_args(["--month", "2026-02", "--source-dir", tmpdir, "--dry-run"])

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(monthly.run_month(args), 0)

            self.assertIn("2026-02-01", output.getvalue())
            self.assertIn("2026-02-28", output.getvalue())
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "monthly-review")))

    def test_incomplete_month_refuses_before_creating_output(self):
        parser = monthly.build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            args = parser.parse_args(["--month", "2026-02", "--source-dir", tmpdir, "--api-base", "http://mock", "--model", "mock", "--api-key", "test-key"])

            with self.assertRaisesRegex(ValueError, "incomplete month"):
                monthly.run_month(args)

            self.assertFalse(os.path.exists(os.path.join(tmpdir, "monthly-review")))

    def test_missing_llm_config_fails_before_month_processing(self):
        parser = monthly.build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            args = parser.parse_args(["--month", "2026-02", "--source-dir", tmpdir])
            with self.assertRaisesRegex(ValueError, "Missing LLM_API_BASE, LLM_MODEL, LLM_API_KEY"):
                monthly.run_month(args)

    def test_resume_skips_dates_already_recorded_in_staged_evolution(self):
        parser = monthly.build_parser()
        original_run_meditation = monthly.run_meditation
        calls = []

        def fake_run_meditation(base_dir, date, *unused):
            calls.append(date)
            evolution = os.path.join(base_dir, "data", "evolution.md")
            os.makedirs(os.path.dirname(evolution), exist_ok=True)
            with open(evolution, "a", encoding="utf-8") as handle:
                handle.write(f"- **{date}**: reflection\\n")
            with open(os.path.join(base_dir, "MEMORY.md"), "a", encoding="utf-8") as handle:
                handle.write(f"- **{date}**: durable lesson\\n")

        monthly.run_meditation = fake_run_meditation
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                source_memory = os.path.join(tmpdir, "memory")
                os.makedirs(source_memory)
                for date_value in monthly.month_dates(monthly.parse_month("2026-02")):
                    with open(os.path.join(source_memory, f"{date_value.isoformat()}.md"), "w", encoding="utf-8") as handle:
                        handle.write("- daily note\\n")
                package = os.path.join(tmpdir, "monthly-review", "2026-02")
                staging = os.path.join(package, "staging")
                os.makedirs(os.path.join(staging, "data"), exist_ok=True)
                for date_value in monthly.month_dates(monthly.parse_month("2026-02")):
                    target = os.path.join(staging, "memory", f"{date_value.isoformat()}.md")
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "w", encoding="utf-8") as handle:
                        handle.write("- daily note\\n")
                with open(os.path.join(staging, "data", "evolution.md"), "w", encoding="utf-8") as handle:
                    handle.write("- **2026-02-01**: reflection\\n")
                with open(os.path.join(staging, "MEMORY.md"), "w", encoding="utf-8") as handle:
                    handle.write("- **2026-02-01**: durable lesson\\n")

                args = parser.parse_args(["--month", "2026-02", "--source-dir", tmpdir, "--api-base", "http://mock", "--model", "mock", "--api-key", "test-key", "--resume"])
                self.assertEqual(monthly.run_month(args, logger=DummyLogger()), 0)
                self.assertNotIn("2026-02-01", calls)
                self.assertEqual(calls[0], "2026-02-02")
        finally:
            monthly.run_meditation = original_run_meditation

    def test_complete_month_replays_in_order_and_keeps_live_latest_untouched(self):
        parser = monthly.build_parser()
        original_run_meditation = monthly.run_meditation
        calls = []

        def fake_run_meditation(base_dir, date, *unused):
            calls.append(date)
            with open(os.path.join(base_dir, "MEMORY.md"), "a", encoding="utf-8") as handle:
                handle.write(f"- **Durable lesson**: {date}\n")
            evolution = os.path.join(base_dir, "data", "evolution.md")
            os.makedirs(os.path.dirname(evolution), exist_ok=True)
            with open(evolution, "a", encoding="utf-8") as handle:
                handle.write(f"- **{date}**: reflection\n")

        monthly.run_meditation = fake_run_meditation
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                memory_dir = os.path.join(tmpdir, "memory")
                os.makedirs(memory_dir)
                for date_value in monthly.month_dates(monthly.parse_month("2026-02")):
                    with open(os.path.join(memory_dir, f"{date_value.isoformat()}.md"), "w", encoding="utf-8") as handle:
                        handle.write("- daily note\n")
                args = parser.parse_args(["--month", "2026-02", "--source-dir", tmpdir, "--api-base", "http://mock", "--model", "mock", "--api-key", "test-key"])

                self.assertEqual(monthly.run_month(args, logger=DummyLogger()), 0)

                package = os.path.join(tmpdir, "monthly-review", "2026-02")
                self.assertEqual(calls, [date.isoformat() for date in monthly.month_dates(monthly.parse_month("2026-02"))])
                self.assertTrue(os.path.isfile(os.path.join(package, "candidates", "2026-02-memory-candidates.jsonl")))
                self.assertTrue(os.path.isfile(os.path.join(package, "review", "2026-02-memory-review.md")))
                self.assertFalse(os.path.exists(os.path.join(tmpdir, "memory", "candidates", "latest-memory-candidates.jsonl")))
        finally:
            monthly.run_meditation = original_run_meditation

    def test_recoverable_failure_is_isolated_then_resume_completes(self):
        parser = monthly.build_parser()
        original_run_meditation = monthly.run_meditation
        calls = []
        fail_once = {"2026-02-02"}

        def fake_run_meditation(base_dir, date, *unused):
            calls.append(date)
            if date in fail_once:
                fail_once.remove(date)
                raise monthly.RecoverableMeditationError("bad tags")
            evolution = os.path.join(base_dir, "data", "evolution.md")
            os.makedirs(os.path.dirname(evolution), exist_ok=True)
            with open(evolution, "a", encoding="utf-8") as handle:
                handle.write(f"- **{date}**: reflection\n")

        monthly.run_meditation = fake_run_meditation
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                memory_dir = os.path.join(tmpdir, "memory")
                os.makedirs(memory_dir)
                for date_value in monthly.month_dates(monthly.parse_month("2026-02")):
                    with open(os.path.join(memory_dir, f"{date_value.isoformat()}.md"), "w", encoding="utf-8") as handle:
                        handle.write("daily note\n")
                first = parser.parse_args(["--month", "2026-02", "--source-dir", tmpdir, "--api-base", "http://mock", "--model", "mock", "--api-key", "test-key"])
                self.assertEqual(monthly.run_month(first, logger=DummyLogger()), 75)
                self.assertIn("2026-02-03", calls)
                package = os.path.join(tmpdir, "monthly-review", "2026-02")
                with open(os.path.join(package, "manifest.json"), encoding="utf-8") as handle:
                    self.assertEqual(json.load(handle)["failed_dates"], ["2026-02-02"])
                self.assertFalse(os.path.exists(os.path.join(package, "candidates")))

                resumed = parser.parse_args(["--month", "2026-02", "--source-dir", tmpdir, "--api-base", "http://mock", "--model", "mock", "--api-key", "test-key", "--resume"])
                self.assertEqual(monthly.run_month(resumed, logger=DummyLogger()), 0)
                with open(os.path.join(package, "manifest.json"), encoding="utf-8") as handle:
                    self.assertEqual(json.load(handle)["failed_dates"], [])
                self.assertTrue(os.path.exists(os.path.join(package, "candidates", "2026-02-memory-candidates.jsonl")))
        finally:
            monthly.run_meditation = original_run_meditation


class DummyLogger:
    def info(self, *unused):
        pass

    def warning(self, *unused):
        pass

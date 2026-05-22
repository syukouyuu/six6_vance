import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "skill-memory", "scripts"))

import backfill_memory  # noqa: E402


class DummyLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append(message % args if args else message)

    def warning(self, message, *args):
        self.messages.append(message % args if args else message)

    def error(self, message, *args):
        self.messages.append(message % args if args else message)

    def exception(self, message, *args):
        self.messages.append(message % args if args else message)


class BackfillMemoryTests(unittest.TestCase):
    def test_requires_from_and_to_together(self):
        parser = backfill_memory.build_parser()

        with self.assertRaises(SystemExit) as ctx:
            args = parser.parse_args(["--from", "2026-05-01"])
            args.parser = parser
            backfill_memory.run_backfill(args, DummyLogger())

        self.assertNotEqual(ctx.exception.code, 0)

    def test_rejects_reversed_range(self):
        parser = backfill_memory.build_parser()

        with self.assertRaises(SystemExit) as ctx:
            args = parser.parse_args(["--from", "2026-05-03", "--to", "2026-05-01"])
            args.parser = parser
            backfill_memory.run_backfill(args, DummyLogger())

        self.assertNotEqual(ctx.exception.code, 0)

    def test_rebuild_processes_existing_dates_and_logs_missing_dates(self):
        parser = backfill_memory.build_parser()
        original_run_meditation = backfill_memory.run_meditation
        calls = []

        def fake_run_meditation(base_dir, date, api_base, api_key, model, temperature, api_type):
            calls.append(date)

        backfill_memory.run_meditation = fake_run_meditation
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "memory"), exist_ok=True)
                os.makedirs(os.path.join(tmpdir, "data"), exist_ok=True)
                with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as handle:
                    handle.write("old memory")
                with open(os.path.join(tmpdir, "data", "evolution.md"), "w", encoding="utf-8") as handle:
                    handle.write("old evolution")
                with open(os.path.join(tmpdir, "memory", "2026-05-01.md"), "w", encoding="utf-8") as handle:
                    handle.write("day one")
                with open(os.path.join(tmpdir, "memory", "2026-05-03.md"), "w", encoding="utf-8") as handle:
                    handle.write("day three")
                with open(os.path.join(tmpdir, "memory", "notes.md"), "w", encoding="utf-8") as handle:
                    handle.write("ignored")

                args = parser.parse_args(
                    [
                        "--base-dir",
                        tmpdir,
                        "--from",
                        "2026-05-01",
                        "--to",
                        "2026-05-03",
                        "--api-key",
                        "test-key",
                    ]
                )
                args.parser = parser
                logger = DummyLogger()

                processed, skipped, failed = backfill_memory.run_backfill(args, logger)

                self.assertEqual(processed, ["2026-05-01", "2026-05-03"])
                self.assertEqual(skipped, ["2026-05-02"])
                self.assertEqual(failed, [])
                self.assertEqual(calls, ["2026-05-01", "2026-05-03"])
                self.assertIn("Skipping missing daily memory", "\n".join(logger.messages))
                self.assertIn("REBUILD MODE", "\n".join(logger.messages))
                with open(os.path.join(tmpdir, "MEMORY.md"), "r", encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "")
                with open(os.path.join(tmpdir, "data", "evolution.md"), "r", encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "")
        finally:
            backfill_memory.run_meditation = original_run_meditation

    def test_meditation_failure_is_recorded_and_later_dates_continue(self):
        parser = backfill_memory.build_parser()
        original_run_meditation = backfill_memory.run_meditation
        calls = []

        def fake_run_meditation(base_dir, date, api_base, api_key, model, temperature, api_type):
            calls.append(date)
            if date == "2026-05-02":
                raise backfill_memory.MeditationError("bad response")

        backfill_memory.run_meditation = fake_run_meditation
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "memory"), exist_ok=True)
                for date in ("2026-05-01", "2026-05-02", "2026-05-03"):
                    with open(os.path.join(tmpdir, "memory", f"{date}.md"), "w", encoding="utf-8") as handle:
                        handle.write(date)

                args = parser.parse_args(
                    [
                        "--base-dir",
                        tmpdir,
                        "--from",
                        "2026-05-01",
                        "--to",
                        "2026-05-03",
                        "--api-key",
                        "test-key",
                    ]
                )
                args.parser = parser
                logger = DummyLogger()

                processed, skipped, failed = backfill_memory.run_backfill(args, logger)

                self.assertEqual(processed, ["2026-05-01", "2026-05-03"])
                self.assertEqual(skipped, [])
                self.assertEqual(failed, [{"date": "2026-05-02", "error": "bad response"}])
                self.assertEqual(calls, ["2026-05-01", "2026-05-02", "2026-05-03"])
                self.assertIn("Failed dates: 2026-05-02", "\n".join(logger.messages))
        finally:
            backfill_memory.run_meditation = original_run_meditation


if __name__ == "__main__":
    unittest.main()

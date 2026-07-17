import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "skill-meditation", "scripts"))

import meditate  # noqa: E402


class MeditateTests(unittest.TestCase):
    def test_run_meditation_raises_error_without_exiting(self):
        original_call_llm = meditate.call_llm
        meditate.call_llm = lambda *args, **kwargs: "missing tags"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "memory"), exist_ok=True)
                with open(os.path.join(tmpdir, "memory", "2026-05-01.md"), "w", encoding="utf-8") as handle:
                    handle.write("daily memory")

                with self.assertRaises(meditate.MeditationError):
                    meditate.run_meditation(
                        tmpdir,
                        "2026-05-01",
                        "https://api.example.com/v1",
                        "test-key",
                        "test-model",
                    )
        finally:
            meditate.call_llm = original_call_llm

    def test_invalid_output_retries_then_writes_memory_backup_atomically(self):
        original_call_llm = meditate.call_llm
        responses = iter(["invalid", "<new_memory>new memory</new_memory><evolution>learned</evolution>"])
        meditate.call_llm = lambda *args, **kwargs: next(responses)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "memory"), exist_ok=True)
                os.makedirs(os.path.join(tmpdir, "data"), exist_ok=True)
                with open(os.path.join(tmpdir, "memory", "2026-05-01.md"), "w", encoding="utf-8") as handle:
                    handle.write("daily memory")
                with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as handle:
                    handle.write("old memory")

                meditate.run_meditation(tmpdir, "2026-05-01", "https://api.example.com/v1", "test-key", "test-model")

                with open(os.path.join(tmpdir, "MEMORY.md"), "r", encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "new memory")
                backups = [name for name in os.listdir(tmpdir) if name.startswith("MEMORY.md.bak-")]
                self.assertEqual(len(backups), 1)
                with open(os.path.join(tmpdir, backups[0]), "r", encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "old memory")
        finally:
            meditate.call_llm = original_call_llm

    def test_invalid_output_is_saved_for_retry_after_second_failure(self):
        original_call_llm = meditate.call_llm
        meditate.call_llm = lambda *args, **kwargs: "invalid output"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "memory"), exist_ok=True)
                with open(os.path.join(tmpdir, "memory", "2026-05-01.md"), "w", encoding="utf-8") as handle:
                    handle.write("daily memory")

                with self.assertRaises(meditate.RecoverableMeditationError):
                    meditate.run_meditation(tmpdir, "2026-05-01", "https://api.example.com/v1", "test-key", "test-model")

                failed_path = os.path.join(tmpdir, "log", "failed-meditations", "2026-05-01.txt")
                with open(failed_path, "r", encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "invalid output")
        finally:
            meditate.call_llm = original_call_llm


if __name__ == "__main__":
    unittest.main()

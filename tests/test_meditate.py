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


if __name__ == "__main__":
    unittest.main()

import os
import sys
import tempfile
import unittest
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "skill-meditation", "scripts"))

import meditate  # noqa: E402
from runtime_io import apply_env_defaults  # noqa: E402


class MeditateTests(unittest.TestCase):
    def test_env_file_config_reaches_mock_endpoint_and_updates_memory(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                body = json.dumps({"choices": [{"message": {"content": "<new_memory>from mock</new_memory><evolution>tested</evolution>"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *unused):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {}, clear=True):
                with open(os.path.join(tmpdir, ".env"), "w", encoding="utf-8") as handle:
                    handle.write(f"LLM_API_BASE=http://127.0.0.1:{server.server_port}/v1\nLLM_MODEL=mock-model\nLLM_API_KEY=test-only\n")
                apply_env_defaults(os.path.join(tmpdir, ".env"))
                os.makedirs(os.path.join(tmpdir, "memory"))
                with open(os.path.join(tmpdir, "memory", "2026-05-01.md"), "w", encoding="utf-8") as handle:
                    handle.write("daily memory")
                meditate.run_meditation(tmpdir, "2026-05-01", os.environ["LLM_API_BASE"], os.environ["LLM_API_KEY"], os.environ["LLM_MODEL"])
                with open(os.path.join(tmpdir, "MEMORY.md"), encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "from mock")
                self.assertEqual(requests[0]["model"], "mock-model")
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_config_source_precedence_is_cli_then_env_then_env_file(self):
        self.assertEqual(meditate._config_source("LLM_MODEL", {"LLM_MODEL"}, ["--model", "cli"], "--model"), "cli")
        self.assertEqual(meditate._config_source("LLM_MODEL", set(), [], "--model"), "env")
        self.assertEqual(meditate._config_source("LLM_MODEL", {"LLM_MODEL"}, [], "--model"), ".env")

    def test_main_logs_env_file_as_config_source(self):
        messages = []

        class Logger:
            def info(self, message, *args):
                messages.append(message % args if args else message)

            def error(self, *unused):
                pass

        def apply_defaults():
            os.environ.update({"LLM_API_BASE": "http://mock", "LLM_MODEL": "mock", "LLM_API_KEY": "test"})
            return {"LLM_API_BASE", "LLM_MODEL", "LLM_API_KEY"}

        with patch.dict(os.environ, {}, clear=True), patch.object(meditate, "apply_env_defaults", side_effect=apply_defaults), patch.object(meditate, "setup_six6_logging", return_value=Logger()), patch.object(meditate, "run_meditation"), patch.object(sys, "argv", ["meditate.py", "--base-dir", ".", "--date", "2026-05-01"]):
            meditate.main()

        self.assertIn("config_source=api_base:.env,model:.env,api_key:.env", "\n".join(messages))

    def test_main_fails_fast_without_llm_configuration(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {}, clear=True), patch.object(meditate, "apply_env_defaults", return_value=set()), patch.object(sys, "argv", ["meditate.py", "--base-dir", tmpdir]):
            with self.assertRaises(SystemExit) as ctx:
                meditate.main()
            self.assertEqual(ctx.exception.code, 1)

    def test_auth_error_category_is_in_meditation_error(self):
        class Error:
            category = "auth_error"

        original_call_llm = meditate.call_llm
        meditate.call_llm = lambda *args, **kwargs: (None, Error())
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "memory"))
                with open(os.path.join(tmpdir, "memory", "2026-05-01.md"), "w", encoding="utf-8") as handle:
                    handle.write("daily memory")
                with self.assertRaisesRegex(meditate.MeditationError, "auth_error"):
                    meditate.run_meditation(tmpdir, "2026-05-01", "http://mock", "test", "mock", tag_retries=1)
        finally:
            meditate.call_llm = original_call_llm
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

    def test_tag_retries_accepts_a_later_valid_response(self):
        original_call_llm = meditate.call_llm
        responses = iter(["invalid", "still invalid", "<new_memory>new</new_memory><evolution>learned</evolution>"])
        meditate.call_llm = lambda *args, **kwargs: next(responses)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "memory"), exist_ok=True)
                with open(os.path.join(tmpdir, "memory", "2026-05-01.md"), "w", encoding="utf-8") as handle:
                    handle.write("daily memory")
                meditate.run_meditation(tmpdir, "2026-05-01", "https://api.example.com/v1", "test-key", "test-model", tag_retries=3)
                with open(os.path.join(tmpdir, "MEMORY.md"), encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "new")
        finally:
            meditate.call_llm = original_call_llm

    def test_lenient_parse_accepts_unclosed_case_insensitive_tags(self):
        original_call_llm = meditate.call_llm
        meditate.call_llm = lambda *args, **kwargs: "<NEW MEMORY>new memory<Evolution>learned"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.makedirs(os.path.join(tmpdir, "memory"), exist_ok=True)
                with open(os.path.join(tmpdir, "memory", "2026-05-01.md"), "w", encoding="utf-8") as handle:
                    handle.write("daily memory")
                meditate.run_meditation(tmpdir, "2026-05-01", "https://api.example.com/v1", "test-key", "test-model", tag_retries=1)
                with open(os.path.join(tmpdir, "MEMORY.md"), encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "new memory")
        finally:
            meditate.call_llm = original_call_llm


if __name__ == "__main__":
    unittest.main()

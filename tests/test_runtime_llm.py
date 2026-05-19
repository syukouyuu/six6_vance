import io
import json
import os
import sys
import unittest
import urllib.error


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "runtime", "scripts"))

from runtime_llm import (  # noqa: E402
    LlmClient,
    LlmProviderError,
    LlmRequest,
    build_provider_request,
    call_llm,
    parse_provider_response,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RuntimeLlmTests(unittest.TestCase):
    def test_openai_request_shape_and_response_cleanup(self):
        request = LlmRequest(
            api_base="https://api.example.com/v1",
            api_key="secret",
            model="model-a",
            prompt="hello",
            api_type="openai",
            temperature=0.2,
        )

        url, headers, payload = build_provider_request(request, "openai")
        content = parse_provider_response(
            {"choices": [{"message": {"content": "<think>private</think> public"}}]},
            "openai",
        )

        self.assertEqual(url, "https://api.example.com/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(payload["messages"][0]["content"], "hello")
        self.assertEqual(content, "<think>private</think> public")

    def test_anthropic_request_shape_and_response_parse(self):
        request = LlmRequest(
            api_base="https://api.example.com/anthropic",
            api_key="secret",
            model="claude-compatible",
            prompt="hello",
            api_type="anthropic",
            temperature=0.4,
        )

        url, _, payload = build_provider_request(request, "anthropic")
        content = parse_provider_response(
            {"content": [{"type": "text", "text": "one"}, {"type": "text", "text": " two"}]},
            "anthropic",
        )

        self.assertEqual(url, "https://api.example.com/anthropic/v1/messages")
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertEqual(content, "one two")

    def test_transport_retry_then_success(self):
        calls = []

        def opener(req, timeout):
            calls.append((req, timeout))
            if len(calls) == 1:
                raise TimeoutError("slow")
            return FakeResponse({"choices": [{"message": {"content": "<think>x</think>done"}}]})

        client = LlmClient(opener=opener, sleep=lambda seconds: None)
        response = client.complete(
            LlmRequest(
                api_base="https://api.example.com/v1",
                api_key="secret",
                model="model-a",
                prompt="hello",
                max_retries=1,
            )
        )

        self.assertEqual(response, "done")
        self.assertEqual(len(calls), 2)

    def test_http_error_metadata_classification(self):
        def opener(req, timeout):
            raise urllib.error.HTTPError(
                req.full_url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=io.BytesIO(b'{"error":"bad key"}'),
            )

        client = LlmClient(opener=opener, sleep=lambda seconds: None)

        with self.assertRaises(LlmProviderError) as ctx:
            client.complete(
                LlmRequest(
                    api_base="https://api.example.com/v1",
                    api_key="secret",
                    model="model-a",
                    prompt="hello",
                )
            )

        self.assertEqual(ctx.exception.category, "auth_error")
        self.assertEqual(ctx.exception.metadata["http_status"], 401)
        self.assertEqual(ctx.exception.metadata["model"], "model-a")
        self.assertIn("bad key", ctx.exception.metadata["response_summary"])

    def test_retryable_http_error_retries_then_success(self):
        calls = []

        def opener(req, timeout):
            calls.append(req)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    req.full_url,
                    500,
                    "Server Error",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":"temporary"}'),
                )
            return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

        client = LlmClient(opener=opener, sleep=lambda seconds: None)
        response = client.complete(
            LlmRequest(
                api_base="https://api.example.com/v1",
                api_key="secret",
                model="model-a",
                prompt="hello",
                max_retries=1,
            )
        )

        self.assertEqual(response, "ok")
        self.assertEqual(len(calls), 2)

    def test_compat_call_returns_none_on_runtime_error(self):
        self.assertIsNone(call_llm("https://api.example.com/v1", "secret", "model-a", "hello", api_type="bogus"))


if __name__ == "__main__":
    unittest.main()

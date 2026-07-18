import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class LlmRuntimeError(Exception):
    def __init__(self, message, *, category, metadata=None):
        super().__init__(message)
        self.category = category
        self.metadata = metadata or {}


class LlmProviderError(LlmRuntimeError):
    pass


class LlmResponseError(LlmRuntimeError):
    pass


class LlmTransportError(LlmRuntimeError):
    pass


@dataclass(frozen=True)
class LlmRequest:
    api_base: str
    api_key: str
    model: str
    prompt: str
    api_type: str = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 180
    max_retries: int = 3


def call_llm_detailed(api_base, api_key, model, prompt, api_type=None, temperature=0.7, max_retries=3, logger=None, raise_on_error=False):
    """Return ``(content, error)`` so callers can retain failure categories."""
    client = LlmClient(logger=logger)
    request = LlmRequest(
        api_base=api_base,
        api_key=api_key,
        model=model,
        prompt=prompt,
        api_type=api_type or None,
        temperature=temperature,
        max_retries=max_retries,
    )
    try:
        return client.complete(request), None
    except LlmRuntimeError as exc:
        _log(logger, "error", f"LLM request failed [{exc.category}]: {exc}", exc.metadata)
        if raise_on_error:
            raise
        return None, exc


def call_llm(api_base, api_key, model, prompt, api_type=None, temperature=0.7, max_retries=3, logger=None, raise_on_error=False):
    content, error = call_llm_detailed(
        api_base, api_key, model, prompt, api_type=api_type,
        temperature=temperature, max_retries=max_retries, logger=logger,
        raise_on_error=raise_on_error,
    )
    return content


class LlmClient:
    def __init__(self, *, logger=None, opener=None, sleep=None):
        self.logger = logger
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep or time.sleep

    def complete(self, request):
        provider = normalize_api_type(request.api_type, request.api_base)
        url, headers, payload = build_provider_request(request, provider)
        body = json.dumps(payload).encode("utf-8")

        attempts = request.max_retries + 1
        for attempt in range(1, attempts + 1):
            metadata = request_metadata(request, provider, url, attempt)
            try:
                _log(self.logger, "info", "LLM request attempt", metadata)
                req = urllib.request.Request(url, data=body, headers=headers)
                with self.opener(req, timeout=request.timeout) as response:
                    raw = response.read().decode("utf-8")
                result = json.loads(raw)
                content = parse_provider_response(result, provider)
                content = strip_think_blocks(content)
                _log(self.logger, "info", "LLM request succeeded", {**metadata, "response_summary": summarize_text(content)})
                return content
            except urllib.error.HTTPError as exc:
                detail = _read_http_error(exc)
                category = classify_http_status(exc.code)
                error_metadata = {**metadata, "error_category": category, "http_status": exc.code, "response_summary": summarize_text(detail)}
                if category == "provider_retryable_error" and attempt < attempts:
                    wait_seconds = backoff_seconds(attempt)
                    _log(self.logger, "warning", f"LLM provider error; retrying in {wait_seconds}s", error_metadata)
                    self.sleep(wait_seconds)
                    continue
                raise LlmProviderError(f"HTTP {exc.code} from {provider}: {exc.reason}", category=category, metadata=error_metadata) from exc
            except json.JSONDecodeError as exc:
                error_metadata = {**metadata, "error_category": "invalid_json", "response_summary": str(exc)}
                raise LlmResponseError("Provider response was not valid JSON", category="invalid_json", metadata=error_metadata) from exc
            except LlmResponseError as exc:
                exc.metadata = {**metadata, **exc.metadata}
                raise
            except Exception as exc:
                category = "transport_error"
                metadata = {**metadata, "error_category": category, "error_type": type(exc).__name__, "response_summary": str(exc)}
                if attempt < attempts:
                    wait_seconds = backoff_seconds(attempt)
                    _log(self.logger, "warning", f"LLM attempt failed; retrying in {wait_seconds}s", metadata)
                    self.sleep(wait_seconds)
                    continue
                raise LlmTransportError(f"All {attempts} LLM attempts failed: {type(exc).__name__}: {exc}", category=category, metadata=metadata) from exc


def normalize_api_type(api_type, api_base):
    if api_type:
        normalized = api_type.lower().strip()
        if normalized not in {"openai", "anthropic"}:
            raise LlmProviderError(f"Unsupported LLM API type: {api_type}", category="configuration_error")
        return normalized
    if api_base and "anthropic" in api_base.lower():
        return "anthropic"
    return "openai"


def build_provider_request(request, provider):
    if provider == "anthropic":
        headers = {
            "Content-Type": "application/json",
            "x-api-key": request.api_key,
            "anthropic-version": "2023-06-01",
        }
        return (
            f"{request.api_base.rstrip('/')}/v1/messages",
            headers,
            {
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "max_tokens": request.max_tokens,
                "temperature": float(request.temperature),
            },
        )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {request.api_key}",
    }
    return (
        f"{request.api_base.rstrip('/')}/chat/completions",
        headers,
        {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": float(request.temperature),
        },
    )


def parse_provider_response(result, provider):
    if provider == "anthropic":
        parts = result.get("content")
        if not isinstance(parts, list):
            raise LlmResponseError("Anthropic response missing content list", category="response_schema_error", metadata={"response_summary": summarize_json(result)})
        return "".join(part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text")

    choices = result.get("choices")
    if not choices:
        raise LlmResponseError("OpenAI response missing choices", category="response_schema_error", metadata={"response_summary": summarize_json(result)})
    return choices[0].get("message", {}).get("content", "")


def strip_think_blocks(content):
    if not content:
        return content
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()


def classify_http_status(status):
    if status in {408, 409, 425, 429} or status >= 500:
        return "provider_retryable_error"
    if status in {401, 403}:
        return "auth_error"
    if 400 <= status < 500:
        return "provider_request_error"
    return "provider_error"


def backoff_seconds(attempt):
    return min(60, attempt * 5)


def request_metadata(request, provider, url, attempt):
    return {
        "model": request.model,
        "api_base": request.api_base,
        "api_type": provider,
        "url": url,
        "attempt": attempt,
    }


def summarize_text(text, limit=500):
    if text is None:
        return ""
    collapsed = re.sub(r"\s+", " ", str(text)).strip()
    return collapsed[:limit]


def summarize_json(value):
    return summarize_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _read_http_error(exc):
    try:
        return exc.read().decode("utf-8")
    except Exception:
        return ""


def _log(logger, level, message, metadata=None):
    if not logger:
        return
    suffix = f" | metadata={json.dumps(metadata, ensure_ascii=False, sort_keys=True)}" if metadata else ""
    getattr(logger, level)(f"{message}{suffix}")

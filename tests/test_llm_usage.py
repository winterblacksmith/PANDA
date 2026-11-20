import pytest

import llm_client
import llm_usage


class FakeHTTPResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("PANDA_STORAGE_DIR", str(tmp_path))
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "PANDA_LLM_PROVIDERS", "PANDA_INFERENCE_URL",
                 "PANDA_GEMINI_DAILY_REQUESTS", "PANDA_GROQ_DAILY_TOKENS",
                 "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID"):
        monkeypatch.delenv(name, raising=False)
    llm_client.reset_cooldowns()


def test_normalize_openai_and_ollama_usage():
    assert llm_usage.normalize_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}) == {
        "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert llm_usage.normalize_usage({"prompt_eval_count": 7, "eval_count": 3})["total_tokens"] == 10
    assert llm_usage.normalize_usage(None)["total_tokens"] == 0


def test_gemini_usage_is_counted_against_configured_daily_limit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.setenv("PANDA_LLM_PROVIDERS", "gemini")
    monkeypatch.setenv("PANDA_GEMINI_DAILY_REQUESTS", "500")
    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: FakeHTTPResponse(200, {
        "model": "gemini-3.5-flash-lite",
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
    }))
    for _ in range(3):
        result = llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])
    assert result["usage"]["total_tokens"] == 140

    row = llm_usage.provider_rows(providers=["gemini"])["rows"][0]
    assert row["requests_used"] == 3 and row["tokens_used"] == 420
    assert row["requests_limit"] == 500 and row["requests_remaining"] == 497
    assert row["source"] == "counted by PANDA"


def test_groq_live_quota_headers_override_counts(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("PANDA_LLM_PROVIDERS", "groq")
    headers = {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "940",
               "x-ratelimit-reset-requests": "2h1m", "x-ratelimit-limit-tokens": "8000",
               "x-ratelimit-remaining-tokens": "7300", "x-ratelimit-reset-tokens": "5.2s"}
    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: FakeHTTPResponse(200, {
        "model": "openai/gpt-oss-120b", "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 600, "completion_tokens": 100, "total_tokens": 700},
    }, headers))
    llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])

    row = llm_usage.provider_rows(providers=["groq"])["rows"][0]
    assert row["source"] == "reported by provider"
    assert row["requests_limit"] == 1000 and row["requests_remaining"] == 940
    assert row["live"]["remaining_tokens"] == 7300 and row["live"]["limit_tokens"] == 8000
    assert row["tokens_used"] == 700 and row["tokens_limit"] == 200_000
    assert row["tokens_remaining"] == 199_300


def test_local_usage_from_ollama_counts(monkeypatch):
    monkeypatch.setattr(llm_client, "_local_chat", lambda *a, **k: {
        "model": "qwen2.5:3b", "message": {"content": "hi"}, "prompt_eval_count": 50, "eval_count": 20})
    result = llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])
    assert result["usage"]["total_tokens"] == 70
    row = llm_usage.provider_rows(providers=["local"])["rows"][0]
    assert row["tokens_used"] == 70 and row["requests_limit"] == 0


def test_usage_database_never_stores_text_or_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "secret-key-123")
    monkeypatch.setenv("PANDA_LLM_PROVIDERS", "groq")
    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: FakeHTTPResponse(200, {
        "choices": [{"message": {"content": "private answer"}}]}))
    llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "private question"}])
    raw = (tmp_path / "llm_usage.sqlite").read_bytes()
    for text in (b"secret-key-123", b"private answer", b"private question"):
        assert text not in raw

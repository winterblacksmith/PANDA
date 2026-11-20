import httpx
import pytest

import llm_client


class FakeHTTPResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)


def openai_reply(text, model="hosted-model"):
    return FakeHTTPResponse(200, {"model": model, "choices": [{"message": {"content": text}}]})


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PANDA_STORAGE_DIR", str(tmp_path))
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "PANDA_LLM_PROVIDERS",
                 "PANDA_INFERENCE_URL", "PANDA_INFERENCE_TOKEN",
                 "PANDA_GROQ_MODEL", "PANDA_GEMINI_MODEL",
                 "PANDA_GROQ_FALLBACK_MODELS", "PANDA_GEMINI_FALLBACK_MODELS",
                 "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID", "OLLAMA_HOST"):
        monkeypatch.delenv(name, raising=False)
    llm_client.reset_cooldowns()
    yield
    llm_client.reset_cooldowns()


def install_local(monkeypatch, text="local answer", calls=None):
    def fake_local(model, messages, options=None, timeout=180):
        if calls is not None:
            calls.append("local")
        return {"model": model, "message": {"role": "assistant", "content": text}}
    monkeypatch.setattr(llm_client, "_local_chat", fake_local)


def test_chain_skips_hosted_providers_without_keys():
    assert llm_client.provider_chain() == ["local"]
    assert llm_client.local_only()


def test_default_chain_orders_hosted_first(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    assert llm_client.provider_chain() == ["groq", "gemini", "local"]
    assert not llm_client.local_only()


def test_explicit_order_and_unknown_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.setenv("PANDA_LLM_PROVIDERS", "gemini, local")
    assert llm_client.provider_chain() == ["gemini", "local"]
    monkeypatch.setenv("PANDA_LLM_PROVIDERS", "groq,openai")
    with pytest.raises(llm_client.LLMConnectionError):
        llm_client.provider_chain()


def test_groq_answers_first_and_maps_options(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json)
        return openai_reply("hello from groq", model="openai/gpt-oss-120b")

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    install_local(monkeypatch)
    result = llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}],
                             options={"num_predict": 50, "num_ctx": 4096, "num_gpu": 0, "temperature": 0.1})
    assert result["provider"] == "groq"
    assert result["message"]["content"] == "hello from groq"
    assert result["fallback_errors"] == []
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer g"
    assert seen["json"]["model"] == "openai/gpt-oss-120b"
    # gpt-oss reasons first: effort low and a cap big enough to leave room for the answer.
    assert seen["json"]["reasoning_effort"] == "low"
    assert seen["json"]["max_tokens"] == llm_client.REASONING_MIN_TOKENS
    assert seen["json"]["temperature"] == 0.1
    assert "num_ctx" not in seen["json"] and "num_gpu" not in seen["json"]


def test_rate_limit_falls_through_to_gemini_then_cools_down(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    urls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        urls.append(url)
        if "groq" in url:
            return FakeHTTPResponse(429, headers={"retry-after": "30"})
        return openai_reply("hello from gemini", model="gemini-2.5-flash")

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    install_local(monkeypatch)
    first = llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])
    assert first["provider"] == "gemini"
    assert "HTTP 429" in first["fallback_errors"][0]

    second = llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "again"}])
    assert second["provider"] == "gemini"
    groq_calls = sum("groq" in u for u in urls)
    assert groq_calls == len(llm_client.hosted_models("groq"))  # each Groq model tried once
    second_groq = sum("groq" in u for u in urls) - groq_calls
    assert second_groq == 0  # whole provider skipped while cooling down


def test_falls_back_to_local_when_all_hosted_fail(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")

    def fake_post(url, headers=None, json=None, timeout=None):
        if "groq" in url:
            raise httpx.ConnectTimeout("timeout")
        return FakeHTTPResponse(503)

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    install_local(monkeypatch, text="qwen says hi")
    result = llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])
    assert result["provider"] == "local"
    assert result["message"]["content"] == "qwen says hi"
    assert len(result["fallback_errors"]) == 2


def test_empty_hosted_answer_falls_back(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: openai_reply("   "))
    install_local(monkeypatch)
    assert llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])["provider"] == "local"


def test_all_providers_failing_raises_with_every_reason(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: FakeHTTPResponse(401))

    def broken_local(*args, **kwargs):
        raise llm_client.LLMConnectionError("Direct Ollama chat failed: refused")

    monkeypatch.setattr(llm_client, "_local_chat", broken_local)
    with pytest.raises(llm_client.LLMConnectionError) as exc:
        llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])
    assert "Groq" in str(exc.value) and "HTTP 401" in str(exc.value)
    assert "Direct Ollama" in str(exc.value)


def test_api_key_is_not_in_error_messages(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "super-secret-key")
    monkeypatch.setenv("PANDA_LLM_PROVIDERS", "groq")
    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: FakeHTTPResponse(500))
    with pytest.raises(llm_client.LLMConnectionError) as exc:
        llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])
    assert "super-secret-key" not in str(exc.value)


def test_gemini_retired_model_falls_to_next_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.setenv("PANDA_LLM_PROVIDERS", "gemini")
    tried = []

    def fake_post(url, headers=None, json=None, timeout=None):
        tried.append(json["model"])
        if len(tried) == 1:
            return FakeHTTPResponse(404)
        return openai_reply("ok", model=json["model"])

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    result = llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "hi"}])
    assert result["provider"] == "gemini"
    assert tried == llm_client.hosted_models("gemini")[:2]


def test_short_connection_test_still_gets_room_to_answer():
    payload = llm_client._openai_payload("openai/gpt-oss-120b", [{"role": "user", "content": "x"}],
                                         {"num_predict": 24})
    assert payload["max_tokens"] >= 1024
    plain = llm_client._openai_payload("some-plain-model", [{"role": "user", "content": "x"}],
                                       {"num_predict": 24})
    assert plain["max_tokens"] == 24 and "reasoning_effort" not in plain


def test_railway_without_gateway_skips_local(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    assert llm_client.provider_chain() == ["groq"]
    monkeypatch.setenv("PANDA_INFERENCE_URL", "https://irene.example")
    assert llm_client.provider_chain() == ["groq", "local"]

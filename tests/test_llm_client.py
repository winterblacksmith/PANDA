import llm_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_gateway_lists_models_and_chats(monkeypatch):
    monkeypatch.setenv("PANDA_INFERENCE_URL", "https://inference.example")
    monkeypatch.setenv("PANDA_INFERENCE_TOKEN", "test-token")

    monkeypatch.setattr(
        llm_client.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({"models": [{"model": "qwen2.5:3b"}]}),
    )
    monkeypatch.setattr(
        llm_client.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {"message": {"role": "assistant", "content": "connected"}}
        ),
    )

    assert llm_client.list_models() == ["qwen2.5:3b"]
    result = llm_client.chat("qwen2.5:3b", [{"role": "user", "content": "test"}])
    assert result["message"]["content"] == "connected"


def test_gateway_requires_token(monkeypatch):
    monkeypatch.setenv("PANDA_INFERENCE_URL", "https://inference.example")
    monkeypatch.delenv("PANDA_INFERENCE_TOKEN", raising=False)

    try:
        llm_client.list_models()
    except llm_client.LLMConnectionError as exc:
        assert "PANDA_INFERENCE_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected missing-token failure")

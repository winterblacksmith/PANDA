import httpx
from fastapi.testclient import TestClient

from inference_gateway.main import create_app


class FakeAsyncOllama:
    def __init__(self):
        self.last_chat_body = None

    async def get(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"models": [{"model": "qwen2.5:3b"}]},
            request=httpx.Request("GET", url),
        )

    async def post(self, url, json, **kwargs):
        self.last_chat_body = json
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "PANDA model connected."}},
            request=httpx.Request("POST", url),
        )


def test_gateway_authentication_and_generation(monkeypatch):
    monkeypatch.setenv("PANDA_INFERENCE_TOKEN", "secret-token")
    monkeypatch.setenv("PANDA_ALLOWED_MODELS", "qwen2.5:3b")
    ollama = FakeAsyncOllama()
    with TestClient(create_app(ollama)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/models").status_code == 401
        assert client.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/docs").status_code == 404

        headers = {"Authorization": "Bearer secret-token"}
        models = client.get("/v1/models", headers=headers)
        assert models.status_code == 200
        assert models.json() == {"models": [{"model": "qwen2.5:3b"}]}

        response = client.post(
            "/v1/chat",
            headers=headers,
            json={
                "model": "qwen2.5:3b",
                "messages": [{"role": "user", "content": "test"}],
                "options": {"num_predict": 99_999, "num_ctx": 12, "num_gpu": 99},
            },
        )
        assert response.status_code == 200
        assert response.json()["message"]["content"] == "PANDA model connected."
        assert ollama.last_chat_body["options"] == {"num_predict": 2_048, "num_ctx": 512}
        assert ollama.last_chat_body["stream"] is False


def test_gateway_rejects_unapproved_model(monkeypatch):
    monkeypatch.setenv("PANDA_INFERENCE_TOKEN", "secret-token")
    monkeypatch.setenv("PANDA_ALLOWED_MODELS", "qwen2.5:3b")
    with TestClient(create_app(FakeAsyncOllama())) as client:
        response = client.post(
            "/v1/chat",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "model": "unapproved:latest",
                "messages": [{"role": "user", "content": "test"}],
            },
        )
        assert response.status_code == 422

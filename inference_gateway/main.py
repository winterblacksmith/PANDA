"""FastAPI boundary between the public PANDA app and private Ollama."""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator


security = HTTPBearer(auto_error=False)
ALLOWED_OPTION_KEYS = {
    "temperature", "top_k", "top_p", "num_ctx", "num_predict", "seed", "stop"
}


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")


def allowed_models() -> set[str]:
    raw = os.environ.get("PANDA_ALLOWED_MODELS", "qwen2.5:3b")
    return {item.strip() for item in raw.split(",") if item.strip()}


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=100)
    messages: List[Message] = Field(min_length=1, max_length=32)
    options: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if value not in allowed_models():
            raise ValueError("Model is not allowed by this gateway")
        return value

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        clean = {key: item for key, item in value.items() if key in ALLOWED_OPTION_KEYS}
        if "num_predict" in clean:
            clean["num_predict"] = min(max(int(clean["num_predict"]), 1), 2_048)
        if "num_ctx" in clean:
            clean["num_ctx"] = min(max(int(clean["num_ctx"]), 512), 32_768)
        return clean


def require_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> None:
    expected = os.environ.get("PANDA_INFERENCE_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Inference authentication is not configured")
    supplied = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def create_app(client: Optional[httpx.AsyncClient] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.owns_client = client is None
        app.state.ollama = client or httpx.AsyncClient(timeout=httpx.Timeout(180, connect=10))
        yield
        if app.state.owns_client:
            await app.state.ollama.aclose()

    app = FastAPI(
        title="PANDA Inference Gateway",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health(request: Request):
        try:
            response = await request.app.state.ollama.get(f"{ollama_base_url()}/api/tags", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(status_code=503, detail="Ollama is unavailable")
        return {"status": "ok"}

    @app.get("/v1/models", dependencies=[Depends(require_token)])
    async def models(request: Request):
        try:
            response = await request.app.state.ollama.get(f"{ollama_base_url()}/api/tags")
            response.raise_for_status()
            installed = response.json().get("models", [])
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="Ollama model listing failed") from exc
        permitted = allowed_models()
        models = []
        for item in installed:
            name = (item.get("model") or item.get("name")) if isinstance(item, dict) else None
            if name in permitted:
                models.append({"model": name})
        return {"models": models}

    @app.post("/v1/chat", dependencies=[Depends(require_token)])
    async def chat(payload: ChatRequest, request: Request):
        body = {
            "model": payload.model,
            "messages": [message.model_dump() for message in payload.messages],
            "options": payload.options,
            "stream": False,
        }
        try:
            response = await request.app.state.ollama.post(f"{ollama_base_url()}/api/chat", json=body)
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="Ollama generation failed") from exc
        content = result.get("message", {}).get("content", "") if isinstance(result, dict) else ""
        if not content:
            raise HTTPException(status_code=502, detail="Ollama returned an empty response")
        return {
            "model": payload.model,
            "message": {"role": "assistant", "content": content},
            "done": True,
        }

    return app


app = create_app()

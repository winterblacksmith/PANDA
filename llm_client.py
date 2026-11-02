"""Shared PANDA model client for authenticated gateways and direct local Ollama."""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

import httpx
import ollama


DEFAULT_MODEL = "qwen2.5:3b"


class LLMConnectionError(RuntimeError):
    """Raised when PANDA cannot reach or use its configured model service."""


def inference_url() -> str:
    return os.environ.get("PANDA_INFERENCE_URL", "").strip().rstrip("/")


def inference_token() -> str:
    return os.environ.get("PANDA_INFERENCE_TOKEN", "").strip()


def ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip()


def using_gateway() -> bool:
    return bool(inference_url())


def connection_label() -> str:
    return inference_url() or ollama_host()


def _gateway_headers() -> Dict[str, str]:
    token = inference_token()
    if not token:
        raise LLMConnectionError(
            "PANDA_INFERENCE_URL is configured, but PANDA_INFERENCE_TOKEN is missing."
        )
    return {"Authorization": f"Bearer {token}"}


def _model_names(raw_models: Iterable[Any]) -> List[str]:
    names: List[str] = []
    for model in raw_models:
        if isinstance(model, dict):
            name = model.get("model") or model.get("name")
        else:
            name = getattr(model, "model", None) or getattr(model, "name", None)
        if name:
            names.append(str(name))
    return sorted(set(names))


def list_models(timeout: float = 30) -> List[str]:
    """Return installed/allowed model names from the configured service."""
    if using_gateway():
        try:
            response = httpx.get(
                f"{inference_url()}/v1/models",
                headers=_gateway_headers(),
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            return _model_names(payload.get("models", []))
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise LLMConnectionError(f"Inference gateway model listing failed: {exc}") from exc

    try:
        response = ollama.Client(host=ollama_host(), timeout=timeout).list()
        raw = response.get("models", []) if isinstance(response, dict) else response.models
        return _model_names(raw)
    except Exception as exc:
        raise LLMConnectionError(f"Direct Ollama model listing failed: {exc}") from exc


def chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Optional[Dict[str, Any]] = None,
    timeout: float = 180,
) -> Dict[str, Any]:
    """Return an Ollama-compatible non-streaming chat response."""
    if using_gateway():
        try:
            response = httpx.post(
                f"{inference_url()}/v1/chat",
                headers=_gateway_headers(),
                json={"model": model, "messages": messages, "options": options or {}},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("Gateway returned a non-object response")
            return payload
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise LLMConnectionError(f"Inference gateway chat failed: {exc}") from exc

    try:
        return ollama.Client(host=ollama_host(), timeout=timeout).chat(
            model=model,
            messages=messages,
            options=options or {},
        )
    except Exception as exc:
        raise LLMConnectionError(f"Direct Ollama chat failed: {exc}") from exc

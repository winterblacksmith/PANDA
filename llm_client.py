"""Shared PANDA model client.

Routes chat requests through an ordered provider chain. By default the hosted
free-tier providers are tried first (Groq, then Gemini, each only when its API
key is set) and the local route is the fallback: the authenticated Irene
gateway when PANDA_INFERENCE_URL is set, otherwise direct Ollama.

Override the order with PANDA_LLM_PROVIDERS, e.g. "groq,gemini,local" or
"local" to disable hosted providers entirely.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

import httpx
import ollama

import llm_usage


DEFAULT_MODEL = "qwen2.5:3b"

# Hosted providers speak the OpenAI chat-completions format.
HOSTED_PROVIDERS: Dict[str, Dict[str, str]] = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model_env": "PANDA_GROQ_MODEL",
        "default_model": "openai/gpt-oss-120b",
        "fallback_env": "PANDA_GROQ_FALLBACK_MODELS",
        "default_fallbacks": "openai/gpt-oss-20b",
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "model_env": "PANDA_GEMINI_MODEL",
        # Same defaults as KTPI, which works on the free tier.
        "default_model": "gemini-3.5-flash-lite",
        "fallback_env": "PANDA_GEMINI_FALLBACK_MODELS",
        "default_fallbacks": "gemini-3.1-flash-lite,gemini-3.5-flash",
    },
}
# Reasoning models think before answering, and those thinking tokens count
# against max_tokens. A small cap (e.g. 24 for the connection test) leaves no
# room for the answer, which comes back empty. Keep effort low and a generous cap.
REASONING_EFFORT = os.environ.get("PANDA_REASONING_EFFORT", "low").strip()
REASONING_MIN_TOKENS = 2048
KNOWN_PROVIDERS = tuple(HOSTED_PROVIDERS) + ("local",)

# Errors worth moving to the next provider for (rate limit, overload, outage,
# payload too large for a free-tier token budget, bad/expired key).
FALLBACK_STATUS_CODES = {401, 403, 404, 408, 409, 413, 422, 429, 500, 502, 503, 504}
DEFAULT_COOLDOWN_SECONDS = 60.0
MAX_COOLDOWN_SECONDS = 600.0

_cooldowns: Dict[str, float] = {}
_cooldown_lock = threading.Lock()


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


def _hosted_key(name: str) -> str:
    return os.environ.get(HOSTED_PROVIDERS[name]["key_env"], "").strip()


def hosted_model(name: str) -> str:
    spec = HOSTED_PROVIDERS[name]
    return os.environ.get(spec["model_env"], "").strip() or spec["default_model"]


def hosted_models(name: str) -> List[str]:
    """Primary model then fallbacks, de-duplicated, in order."""
    spec = HOSTED_PROVIDERS[name]
    raw = os.environ.get(spec["fallback_env"], spec["default_fallbacks"])
    models = [hosted_model(name)] + [m.strip() for m in raw.split(",") if m.strip()]
    return list(dict.fromkeys(models))


def _is_reasoning_model(model: str) -> bool:
    return model.startswith("gemini") or "gpt-oss" in model


def _local_unreachable_on_railway() -> bool:
    """On Railway with no Irene gateway, 127.0.0.1:11434 has no Ollama behind it."""
    on_railway = any(os.environ.get(k) for k in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID"))
    return on_railway and not using_gateway() and not os.environ.get("OLLAMA_HOST", "").strip()


def provider_chain() -> List[str]:
    """Ordered providers to try. Hosted providers without a key are skipped."""
    raw = os.environ.get("PANDA_LLM_PROVIDERS", "").strip()
    if raw:
        requested = [part.strip().lower() for part in raw.split(",") if part.strip()]
        unknown = [name for name in requested if name not in KNOWN_PROVIDERS]
        if unknown:
            raise LLMConnectionError(
                f"Unknown provider(s) in PANDA_LLM_PROVIDERS: {', '.join(unknown)}. "
                f"Use any of: {', '.join(KNOWN_PROVIDERS)}."
            )
    else:
        requested = list(KNOWN_PROVIDERS)
        if _local_unreachable_on_railway():
            requested.remove("local")
    chain: List[str] = []
    for name in requested:
        if name in chain:
            continue
        if name in HOSTED_PROVIDERS and not _hosted_key(name):
            continue
        chain.append(name)
    return chain


def local_label() -> str:
    return "Irene gateway" if using_gateway() else "Local Ollama"


def provider_label(name: str) -> str:
    return HOSTED_PROVIDERS[name]["label"] if name in HOSTED_PROVIDERS else local_label()


def local_only() -> bool:
    try:
        return provider_chain() == ["local"]
    except LLMConnectionError:
        return False


def _cooling_down(name: str) -> bool:
    with _cooldown_lock:
        until = _cooldowns.get(name, 0.0)
        if until and until <= time.monotonic():
            _cooldowns.pop(name, None)
            return False
        return bool(until)


def _start_cooldown(name: str, seconds: float) -> None:
    seconds = max(1.0, min(seconds, MAX_COOLDOWN_SECONDS))
    with _cooldown_lock:
        _cooldowns[name] = time.monotonic() + seconds


def reset_cooldowns() -> None:
    with _cooldown_lock:
        _cooldowns.clear()


def _retry_after_seconds(response: httpx.Response) -> float:
    value = response.headers.get("retry-after", "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_SECONDS


def _openai_payload(model: str, messages: List[Dict[str, str]], options: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in messages
        ],
        "stream": False,
    }
    # Translate the Ollama options PANDA uses; GPU/context options do not apply.
    if "temperature" in options:
        payload["temperature"] = options["temperature"]
    if "top_p" in options:
        payload["top_p"] = options["top_p"]
    requested = int(options["num_predict"]) if options.get("num_predict") else 0
    if _is_reasoning_model(model):
        if REASONING_EFFORT:
            payload["reasoning_effort"] = REASONING_EFFORT
        payload["max_tokens"] = max(requested, REASONING_MIN_TOKENS)
    elif requested:
        payload["max_tokens"] = requested
    return payload


class _ModelFailure(Exception):
    def __init__(self, message: str, status: Optional[int] = None, retry_after: float = 0.0):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _hosted_model_chat(
    name: str,
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
    timeout: float,
) -> Dict[str, Any]:
    spec = HOSTED_PROVIDERS[name]
    try:
        response = httpx.post(
            f"{spec['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {_hosted_key(name)}"},
            json=_openai_payload(model, messages, options),
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise _ModelFailure(f"{model}: request failed ({type(exc).__name__})") from exc
    if response.status_code >= 400:
        reason = {401: "API key rejected", 403: "API key not allowed for this model",
                  404: "model not found or retired", 429: "rate limited",
                  503: "overloaded"}.get(response.status_code, "error")
        retry = _retry_after_seconds(response) if response.status_code == 429 else 0.0
        raise _ModelFailure(f"{model}: HTTP {response.status_code} {reason}", response.status_code, retry)
    llm_usage.record_quota_headers(name, response.headers)
    try:
        payload = response.json()
        content = payload["choices"][0]["message"].get("content") or ""
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise _ModelFailure(f"{model}: unexpected response shape") from exc
    if not str(content).strip():
        raise _ModelFailure(f"{model}: empty answer")
    return {
        "model": payload.get("model") or model,
        "message": {"role": "assistant", "content": str(content)},
        "usage": llm_usage.normalize_usage(payload.get("usage")),
        "done": True,
    }


def _hosted_chat(
    name: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
    timeout: float,
) -> Dict[str, Any]:
    """Try the provider's primary model, then its fallback models."""
    label = HOSTED_PROVIDERS[name]["label"]
    failures: List[str] = []
    rate_limited = 0.0
    for model in hosted_models(name):
        try:
            return _hosted_model_chat(name, model, messages, options, timeout)
        except _ModelFailure as exc:
            failures.append(str(exc))
            if exc.status == 401:
                # A rejected key fails for every model; stop and skip this provider for a while.
                _start_cooldown(name, MAX_COOLDOWN_SECONDS)
                raise LLMConnectionError(f"{label}: {exc}") from exc
            if exc.status == 429:
                rate_limited = max(rate_limited, exc.retry_after)
    _start_cooldown(name, rate_limited or DEFAULT_COOLDOWN_SECONDS)
    raise LLMConnectionError(f"{label} failed ({'; '.join(failures)})")


def _local_chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Optional[Dict[str, Any]] = None,
    timeout: float = 180,
) -> Dict[str, Any]:
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


def chat(
    model: str,
    messages: List[Dict[str, str]],
    options: Optional[Dict[str, Any]] = None,
    timeout: float = 180,
) -> Dict[str, Any]:
    """Return an Ollama-compatible non-streaming chat response.

    `model` names the local model (the UI selector); hosted providers use their
    own configured model. The response carries `provider`, `provider_label`
    and `fallback_errors` so the UI can show which service actually answered.
    """
    chain = provider_chain()
    if not chain:
        raise LLMConnectionError("No model providers are configured.")
    opts = dict(options or {})
    errors: List[str] = []
    for index, name in enumerate(chain):
        is_last = index == len(chain) - 1
        # Skip a hosted provider that recently failed, unless nothing is left.
        if name in HOSTED_PROVIDERS and _cooling_down(name) and not is_last:
            errors.append(f"{provider_label(name)} skipped (recent rate limit or error)")
            continue
        try:
            if name in HOSTED_PROVIDERS:
                result = _hosted_chat(name, messages, opts, timeout=min(timeout, 90))
            else:
                result = _local_chat(model, messages, opts, timeout=timeout)
        except LLMConnectionError as exc:
            errors.append(str(exc))
            continue
        if not isinstance(result, dict):
            # ollama.ChatResponse objects support dict-style access via model_dump.
            dump = getattr(result, "model_dump", None)
            result = dump() if callable(dump) else {"message": {"content": str(result)}}
        if "usage" not in result:
            # Ollama (direct or via the Irene gateway) reports prompt_eval_count/eval_count.
            result["usage"] = llm_usage.normalize_usage(result)
        result["provider"] = name
        result["provider_label"] = provider_label(name)
        result["fallback_errors"] = errors
        llm_usage.record(name, str(result.get("model") or model), result["usage"])
        return result
    raise LLMConnectionError("All model providers failed: " + "; ".join(errors))

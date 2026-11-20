"""Explicit diagnostics for PANDA's gateway or direct local Ollama connection."""
import os
from urllib.parse import urlsplit

import streamlit as st

from llm_client import (
    HOSTED_PROVIDERS,
    LLMConnectionError,
    chat,
    connection_label,
    hosted_models,
    provider_chain,
    provider_label,
    using_gateway,
)


def connection_test(model, client=None):
    if client is not None:
        response = client.list()
        raw = response.get("models", []) if isinstance(response, dict) else response.models
        names = [
            (item.get("model") or item.get("name"))
            if isinstance(item, dict)
            else (getattr(item, "model", None) or getattr(item, "name", None))
            for item in raw
        ]
    else:
        return chain_connection_test(model)
    if model not in names:
        return False, f"The model service is reachable, but {model} is not available."
    request = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the words PANDA model connected."}],
        "options": {"num_predict": 24, "num_ctx": 2048, "temperature": 0},
    }
    result = client.chat(**request) if client is not None else chat(**request)
    content = result["message"]["content"].strip()
    if not content:
        return False, "The model is installed, but returned an empty answer. Check Ollama logs and available memory."
    return True, f"{model} generated a response: {content}"


def chain_connection_test(model):
    """Send one short request through the provider chain and report who answered."""
    request = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the words PANDA model connected."}],
        "options": {"num_predict": 24, "num_ctx": 2048, "temperature": 0},
    }
    try:
        result = chat(**request)
    except LLMConnectionError as exc:
        return False, str(exc)
    content = str(result.get("message", {}).get("content", "")).strip()
    if not content:
        return False, "The model service answered with an empty response."
    answered = f"{result.get('provider_label', 'Model')} ({result.get('model') or model})"
    note = ""
    if result.get("fallback_errors"):
        note = " Earlier providers failed: " + "; ".join(result["fallback_errors"]) + "."
    return True, f"{answered} generated a response: {content}.{note}"


def _chain_summary(local_model):
    try:
        chain = provider_chain()
    except LLMConnectionError as exc:
        return f"Provider configuration error: {exc}"
    if not chain:
        return "No providers configured."
    parts = []
    for name in chain:
        model = " / ".join(hosted_models(name)) if name in HOSTED_PROVIDERS else local_model
        parts.append(f"{provider_label(name)} ({model})")
    return "Order: " + " -> ".join(parts)


@st.fragment
def render_model_connection():
    with st.expander("Model connection", expanded=False):
        model = st.session_state.get("question_model", os.environ.get("PANDA_OLLAMA_MODEL", "qwen2.5:3b"))
        raw_host = connection_label()
        parsed = urlsplit(raw_host if "://" in raw_host else "http://" + raw_host)
        mode = "Authenticated FastAPI gateway" if using_gateway() else "Direct local Ollama"
        st.caption(_chain_summary(model))
        st.caption(f"Local fallback: {parsed.hostname or 'not configured'} | Model: {model} | Mode: {mode}")
        st.caption("A model appearing in the dropdown does not confirm it is installed. Test a real response here.")
        if st.button("Test model connection", key="test_model_connection"):
            try:
                with st.spinner("Checking the model and requesting a short response..."):
                    ok, message = connection_test(model)
            except Exception as exc:
                ok = False
                message = (f"Connection test failed ({type(exc).__name__}). Check the configured gateway URL/token "
                           "or the local OLLAMA_HOST, plus the service logs and available memory.")
            st.session_state["panda_model_test"] = (raw_host, model, ok, message)
        result = st.session_state.get("panda_model_test")
        if result and result[:2] == (raw_host, model):
            (st.success if result[2] else st.error)(result[3])
        st.caption("Provider keys and the Irene gateway URL are set as Railway variables; see README.")

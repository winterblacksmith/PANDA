"""Explicit diagnostics for PANDA's gateway or direct local Ollama connection."""
import os
from urllib.parse import urlsplit

import streamlit as st

from llm_client import chat, connection_label, list_models, using_gateway


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
        names = list_models()
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


@st.fragment
def render_model_connection():
    with st.expander("Model connection", expanded=False):
        model = st.session_state.get("question_model", os.environ.get("PANDA_OLLAMA_MODEL", "qwen2.5:3b"))
        raw_host = connection_label()
        parsed = urlsplit(raw_host if "://" in raw_host else "http://" + raw_host)
        mode = "Authenticated FastAPI gateway" if using_gateway() else "Direct local Ollama"
        st.caption(f"Server: {parsed.hostname or 'not configured'} | Model: {model} | Mode: {mode}")
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
        st.markdown("**Railway to Irene setup**")
        st.code("PANDA_INFERENCE_URL=https://your-approved-gateway.example.edu\nPANDA_INFERENCE_TOKEN=<Railway secret>\nPANDA_OLLAMA_MODEL=qwen2.5:3b", language="text")
        st.caption("Only the authenticated FastAPI gateway should be public. Keep Ollama private on Irene.")

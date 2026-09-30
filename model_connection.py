"""Explicit connection/inference diagnostics for local and Railway Ollama."""
import os
from urllib.parse import urlsplit

import ollama
import streamlit as st


def ollama_host():
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def connection_test(model, client=None):
    client = client or ollama.Client(host=ollama_host(), timeout=180)
    response = client.list()
    raw = response.get("models", []) if isinstance(response, dict) else response.models
    names = [(r.get("model") or r.get("name")) if isinstance(r, dict) else r.model for r in raw]
    if model not in names:
        return False, f"Ollama is reachable, but {model} is not installed. Run ollama pull {model} inside the Ollama service."
    result = client.chat(model=model, messages=[{"role": "user", "content": "Reply with the words PANDA model connected."}],
                         options={"num_predict": 24, "num_ctx": 2048, "temperature": 0})
    content = result["message"]["content"].strip()
    if not content:
        return False, "The model is installed, but returned an empty answer. Check Ollama logs and available memory."
    return True, f"{model} generated a response: {content}"


@st.fragment
def render_model_connection():
    with st.expander("Model connection", expanded=False):
        model = st.session_state.get("question_model", os.environ.get("PANDA_OLLAMA_MODEL", "qwen2.5:3b"))
        raw_host = ollama_host()
        parsed = urlsplit(raw_host if "://" in raw_host else "http://" + raw_host)
        st.caption(f"Server: {parsed.hostname or 'not configured'} | Model: {model}")
        st.caption("A model appearing in the dropdown does not confirm it is installed. Test a real response here.")
        if st.button("Test model connection", key="test_model_connection"):
            try:
                with st.spinner("Checking the model and requesting a short response..."):
                    ok, message = connection_test(model)
            except Exception as exc:
                ok = False
                message = (f"Connection test failed ({type(exc).__name__}). Check OLLAMA_HOST, the Ollama service logs, "
                           "and available memory. On Railway, localhost points to PANDA itself.")
            st.session_state["panda_model_test"] = (raw_host, model, ok, message)
        result = st.session_state.get("panda_model_test")
        if result and result[:2] == (raw_host, model):
            (st.success if result[2] else st.error)(result[3])
        st.markdown("**Railway setup**")
        st.code("# PANDA service variables\nOLLAMA_HOST=http://${{ollama.RAILWAY_PRIVATE_DOMAIN}}:11434\nPANDA_OLLAMA_MODEL=qwen2.5:3b", language="text")
        st.caption("Ollama needs its own volume at /root/.ollama. Install qwen2.5:3b inside that service, "
                   "then enable model answers in Advanced options. Keep Ollama on Railway's private network.")

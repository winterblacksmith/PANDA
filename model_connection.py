"""Explicit diagnostics for PANDA's gateway or direct local Ollama connection."""
import os
from urllib.parse import urlsplit

import streamlit as st

import llm_usage

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


def _fmt(value):
    return f"{value:,}" if isinstance(value, int) else "?"


def _usage_bar(label, used, limit, remaining):
    if limit:
        left = remaining if remaining is not None else max(0, limit - used)
        st.caption(f"{label}: **{_fmt(used)}** of {_fmt(limit)} used, **{_fmt(left)} left**")
        st.progress(min(1.0, used / limit) if limit else 0.0)
    else:
        st.caption(f"{label}: **{_fmt(used)}** used (no daily limit set)")


def render_model_usage():
    """Tokens and requests used today per provider, with limits and what is left."""
    with st.expander("Model usage today", expanded=False):
        try:
            chain = provider_chain()
        except LLMConnectionError:
            chain = []
        data = llm_usage.provider_rows(providers=chain or None)
        if not data["rows"]:
            st.caption("No model providers configured.")
            return
        last = st.session_state.get("last_llm_usage")
        if last:
            st.caption(f"Last answer: **{_fmt(last.get('total_tokens', 0))} tokens** "
                       f"({_fmt(last.get('prompt_tokens', 0))} in, {_fmt(last.get('completion_tokens', 0))} out) "
                       f"via {last.get('label', 'model')}")
        for row in data["rows"]:
            name = row["provider"]
            st.markdown(f"**{provider_label(name)}**")
            if name == "local":
                st.caption(f"Requests: **{_fmt(row['requests_used'])}**, tokens: **{_fmt(row['tokens_used'])}** "
                           "(self-hosted, no provider quota)")
                continue
            _usage_bar("Requests", row["requests_used"] if row["live"] is None
                       else row["requests_limit"] - (row["requests_remaining"] or 0),
                       row["requests_limit"], row["requests_remaining"])
            _usage_bar("Tokens", row["tokens_used"], row["tokens_limit"], row["tokens_remaining"])
            live = row["live"]
            if live and live.get("limit_tokens"):
                st.caption(f"Per-minute tokens: {_fmt(live['remaining_tokens'])} of "
                           f"{_fmt(live['limit_tokens'])} left (resets in {live.get('reset_tokens') or '?'})")
            source = ("Requests reported live by Groq; tokens counted by PANDA."
                      if row["source"] == "reported by provider"
                      else "Counted by PANDA (this provider does not report its quota).")
            st.caption(source)
            if len(row["models"]) > 1:
                st.caption(" · ".join(f"{m['model']}: {_fmt(m['requests'])} req, {_fmt(m['tokens'])} tok"
                                      for m in row["models"]))
        st.caption(f"Day {data['day']} (Pacific). Daily quotas reset at midnight Pacific / 3 AM Eastern. "
                   "Exact account limits: console.groq.com/settings/limits and aistudio.google.com/rate-limit.")


def _ring_color(fraction):
    if fraction >= 0.85:
        return "#F07167"
    if fraction >= 0.6:
        return "#F2C14E"
    return "#5CC285"


def usage_ring_html(rows, last=None):
    """Circle showing the highest share of today's quota used; hover/focus reveals exact numbers."""
    from html import escape as esc

    fractions = []
    sections = []
    for row in rows:
        name = row["provider"]
        label = esc(provider_label(name))
        if name == "local":
            sections.append(f'<div class="prov">{label}</div>'
                            f'<div class="row"><span>Requests</span><b>{_fmt(row["requests_used"])}</b></div>'
                            f'<div class="row"><span>Tokens</span><b>{_fmt(row["tokens_used"])}</b></div>'
                            '<div class="row"><span>Limit</span><b>none (self-hosted)</b></div>')
            continue
        live = row["live"]
        req_used = (row["requests_limit"] - (row["requests_remaining"] or 0)) if live else row["requests_used"]
        parts = [f'<div class="prov">{label}</div>']
        for title, used, limit, left in (("Requests", req_used, row["requests_limit"], row["requests_remaining"]),
                                         ("Tokens", row["tokens_used"], row["tokens_limit"], row["tokens_remaining"])):
            if limit:
                frac = min(1.0, used / limit)
                fractions.append(frac)
                left = left if left is not None else max(0, limit - used)
                parts.append(f'<div class="row"><span>{title}</span><b>{_fmt(used)} / {_fmt(limit)}</b></div>'
                             f'<div class="bar"><span style="width:{frac * 100:.1f}%;background:{_ring_color(frac)}"></span></div>'
                             f'<div class="row"><span></span><span>{_fmt(left)} left</span></div>')
            else:
                parts.append(f'<div class="row"><span>{title}</span><b>{_fmt(used)}</b></div>')
        if live and live.get("limit_tokens"):
            parts.append(f'<div class="row"><span>This minute</span><b>{_fmt(live["remaining_tokens"])} / '
                         f'{_fmt(live["limit_tokens"])} tokens left</b></div>')
        parts.append('<div class="row"><span>Source</span><span>' +
                     ("live from Groq" if live else "counted by PANDA") + '</span></div>')
        sections.append("".join(parts))
    peak = max(fractions) if fractions else 0.0
    circumference = 2 * 3.14159 * 13
    dash = circumference * peak
    last_line = ""
    if last:
        last_line = (f'<div class="row" style="margin-top:6px"><span>Last answer</span><b>{_fmt(last.get("total_tokens", 0))} tokens</b></div>'
                     f'<div class="row"><span></span><span>{esc(str(last.get("label", "")))}</span></div>')
    card = ('<div class="panda-usage-card" role="tooltip"><h4>Model usage today</h4>' + last_line + "".join(sections) +
            '<div class="foot">Daily quotas reset at midnight Pacific (3 AM Eastern).</div></div>')
    svg = ('<svg viewBox="0 0 32 32" aria-hidden="true">'
           '<circle cx="16" cy="16" r="13" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="3.2"/>'
           f'<circle cx="16" cy="16" r="13" fill="none" stroke="{_ring_color(peak)}" stroke-width="3.2" '
           f'stroke-linecap="round" stroke-dasharray="{dash:.2f} {circumference:.2f}"/></svg>')
    pct = f"{peak * 100:.0f}%" if fractions else "–"
    return (f'<div class="panda-usage" tabindex="0" aria-label="Model usage today: {pct} of the tightest daily limit used">'
            f'{svg}<span class="pct">{pct}</span>{card}</div>')


def render_usage_ring():
    try:
        chain = provider_chain()
    except LLMConnectionError:
        chain = []
    data = llm_usage.provider_rows(providers=chain or None)
    with st.container(key="panda-topbar-usage"):
        st.markdown(usage_ring_html(data["rows"], st.session_state.get("last_llm_usage")), unsafe_allow_html=True)

from io import BytesIO
import pandas as pd
from pypdf import PdfReader
import pytest

from conversation_report import (conversation_entries, generate_report, report_fingerprint,
                                 transcript_text, report_filename)
from model_connection import connection_test


def sample_messages():
    return [
        {"role": "user", "content": "Show stands older than 60 <please> & explain."},
        {"role": "assistant", "results": [{"type": "fvs_query", "content": "4,222 matching stands.",
            "sql_query": "SELECT * FROM stands WHERE Age > ?", "sql_parameters": [60],
            "spec": {"min_age": 60}, "data_backend": "SQLite"}]},
        {"role": "user", "content": "What is the raster CRS?"},
        {"role": "assistant", "content": "The raster uses EPSG:5070."},
        {"role": "assistant", "results": [{"type": "data", "explanation": "Two sample species.",
            "payload": {"rows": 2}, "table_df": pd.DataFrame({"Species": ["Oak", "Pine"]}),
            "filtered_df": pd.DataFrame({"private_raw": ["DO_NOT_INCLUDE"]})}]},
    ]


def test_pdf_preserves_all_message_shapes_and_escapes_markup():
    messages = sample_messages()
    calls = []
    def chat(model, prompt, **kwargs):
        calls.append(prompt)
        return "The discussion covered older stands and raster coordinates."
    result = generate_report(messages, "test.csv", "Forest <report>", "qwen2.5:3b", chat)
    assert result.ai_generated
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(result.pdf)).pages)
    for expected in ("4,222", "EPSG:5070", "<please>", "SQL", "Oak", "Pine", "5. Assistant"):
        assert expected in text
    assert "DO_NOT_INCLUDE" not in text
    assert "DO_NOT_INCLUDE" not in calls[0]
    assert "ai summary" in text.lower()


def test_long_chat_covers_tail_and_fails_honestly():
    messages = [{"role": "user", "content": "a" * 20000 + "IMPORTANT_TAIL"}]
    calls = []
    def chat(model, prompt, **kwargs):
        calls.append(prompt)
        return "Covered section."
    result = generate_report(messages, "dataset", "Long chat", "qwen", chat)
    assert result.ai_generated and len(calls) == 3
    assert "IMPORTANT_TAIL" in calls[-1]
    assert "Part 3" in result.summary
    result = generate_report(messages, "dataset", "Long chat", "qwen", lambda *a, **kw: "")
    assert not result.ai_generated
    assert "AI summary unavailable" in result.notice
    assert "IMPORTANT_TAIL" in "".join(p.extract_text() for p in PdfReader(BytesIO(result.pdf)).pages)


def test_disabled_summary_never_calls_model_and_empty_chat_is_rejected():
    def fail(*args, **kwargs):
        pytest.fail("Model should not be called")
    result = generate_report(sample_messages(), "a", "b", "c", fail, use_llm=False)
    assert not result.ai_generated
    with pytest.raises(ValueError):
        generate_report([], "a", "b", "c", fail)


def test_report_invalidates_when_conversation_settings_or_dataset_change():
    messages = sample_messages()
    original = report_fingerprint(messages, "d", "t", "m", True)
    assert original != report_fingerprint(messages, "different", "t", "m", True)
    assert original != report_fingerprint(messages, "d", "t", "m", False)
    messages.append({"role": "user", "content": "New question"})
    assert original != report_fingerprint(messages, "d", "t", "m", True)
    assert report_filename("../../Forest <report>") == "PANDA-Forest-report.pdf"


def test_connection_test_requires_installed_model_and_generated_response():
    class FakeClient:
        def list(self):
            return {"models": [{"model": "qwen2.5:3b"}]}
        def chat(self, **kwargs):
            return {"message": {"content": "PANDA model connected"}}
    client = FakeClient()
    assert connection_test("qwen2.5:3b", client)[0]
    assert not connection_test("missing", client)[0]


def test_report_fragment_download_and_stale_state():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import streamlit as st
from report_ui import render_report_panel
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "user", "content": "Summarize the forest"}]
if st.button("Append question"):
    st.session_state.messages.append({"role": "user", "content": "And its age?"})
render_report_panel(st.session_state.messages, "test", "one", "Example", "qwen2.5:3b",
                    lambda *a, **kw: "The conversation asked about the forest.")
''').run()
    assert not app.exception
    next(b for b in app.button if b.label == "Generate PDF report").click().run()
    assert not app.exception
    assert app.session_state["panda_report"][2].pdf.startswith(b"%PDF")
    assert len(app.get("download_button")) == 1
    next(b for b in app.button if b.label == "Append question").click().run()
    assert not app.exception
    assert any("changed" in msg.value for msg in app.info)
    assert not app.get("download_button")

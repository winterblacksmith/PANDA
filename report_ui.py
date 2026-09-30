"""A fragment keeps report actions from rerunning maps and the whole app."""
import streamlit as st
from conversation_report import generate_report, report_filename, report_fingerprint


@st.fragment
def render_report_panel(messages, dataset, chat_id, title, model, chat):
    if not messages:
        return
    with st.expander("Download conversation report", expanded=False):
        st.caption("Summarize this chat and download a PDF with the full conversation and recorded results. "
                   "Maps are described, not embedded as images.")
        key = f"report::{dataset}::{chat_id}"
        use_llm = st.checkbox("Use AI to summarize the discussion", value=True, key=key + "::ai")
        fingerprint = report_fingerprint(messages, dataset, title, model, use_llm)
        if st.button("Generate PDF report", disabled=not messages, key=key + "::generate"):
            try:
                with st.spinner("Preparing your conversation report..."):
                    report = generate_report(messages, dataset, title, model, chat, use_llm)
                # Keep only the most recent report per browser session, never share
                # private conversation PDFs through Streamlit's global data cache.
                st.session_state["panda_report"] = (key, fingerprint, report)
            except Exception as exc:
                st.error(f"Could not create the PDF report: {exc}")
        cached = st.session_state.get("panda_report")
        if cached and cached[0] == key:
            if cached[1] != fingerprint:
                st.info("This conversation or report setting changed. Generate a new report to include the latest messages.")
            else:
                report = cached[2]
                if report.ai_generated:
                    st.success("AI summary and conversation report ready.")
                else:
                    st.warning(report.notice)
                st.download_button("Download PDF", report.pdf, file_name=report_filename(title),
                                   mime="application/pdf", on_click="ignore", key=key + "::download")
                st.markdown(report.summary)

"""A restrained shared chat shell for CSV, FVS, and raster modes."""
from pathlib import Path
import streamlit as st

MARK_PATH = Path(__file__).parent / "assets" / "panda-mark.svg"
PLACEHOLDER = "Ask a forestry question, or branch out..."


def apply_chat_shell():
    st.markdown("""<style>
    [data-testid="stMainBlockContainer"] {max-width:1120px;padding-top:2.5rem;padding-bottom:3rem;}
    [data-testid="stSidebar"] {min-width:260px;max-width:300px;}
    [data-testid="stSidebarUserContent"] {padding:1.5rem 1.25rem;}
    [data-testid="stSidebar"] button p {font-size:14px;}
    .panda-wordmark {font-size:24px;font-weight:650;letter-spacing:5px;margin:0 0 22px 2px;}
    .panda-welcome {text-align:center;padding:clamp(32px,10vh,110px) 0 24px;}
    .panda-welcome > svg {width:230px;max-width:52vw;height:auto;color:var(--canopy-text);opacity:.92;}
    .panda-welcome h1 {font-size:clamp(24px,2.4vw,32px);font-weight:500;letter-spacing:-.6px;margin:24px 0 0;padding:0;justify-content:center;}
    .panda-welcome [data-testid="stHeaderActionElements"] {display:none;}
    .st-key-panda-welcome-composer {max-width:760px;margin:0 auto;}
    [data-testid="stChatInput"] {border-radius:20px;min-height:72px;box-shadow:none;}
    [data-testid="stChatInput"] textarea {font-size:16px;}
    [data-testid="stChatMessage"] {border:0;box-shadow:none;background:transparent;padding:1.2rem 0;}
    [data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] {display:none;}
    [data-testid="stChatMessageContent"] {min-width:0;}
    [data-testid="stMetric"], [data-testid="stExpander"], [data-testid="stAlert"] {box-shadow:none;}
    [data-testid="stSidebar"] [data-testid="stExpander"] {border:0;}
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {background:transparent!important;}
    [data-testid="stDecoration"] {display:none;}
    @media(max-width:760px) {
      [data-testid="stMainBlockContainer"] {padding:1.5rem 1rem 3rem;}
      .panda-welcome {padding-top:8vh;}
      .panda-welcome > svg {width:180px;}
      .panda-welcome h1 {margin-top:20px;}
    }
    </style>""", unsafe_allow_html=True)
    st.sidebar.markdown('<div class="panda-wordmark">PANDA</div>', unsafe_allow_html=True)


def chat_composer(messages, key):
    if not messages and not st.session_state.get("show_dataset_details", False):
        # A placeholder can be removed immediately after submission, avoiding
        # a second full app rerun merely to hide the welcome illustration.
        welcome = st.empty()
        welcome.markdown('<div class="panda-welcome">' + MARK_PATH.read_text() +
                         '<h1>What would you like to explore?</h1></div>', unsafe_allow_html=True)
        with st.container(key="panda-welcome-composer"):
            prompt = st.chat_input(PLACEHOLDER, key=key)
        if prompt:
            welcome.empty()
        return prompt
    return st.chat_input(PLACEHOLDER, key=key)

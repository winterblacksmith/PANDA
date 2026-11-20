"""A restrained shared chat shell for CSV, FVS, and raster modes."""
from pathlib import Path
import streamlit as st

from version import RELEASE_DATE, short_version

MARK_PATH = Path(__file__).parent / "assets" / "panda-mark.svg"
PLACEHOLDER = "Ask a forestry question, or branch out..."


def apply_chat_shell():
    st.markdown("""<style>
    [data-testid="stMainBlockContainer"] {max-width:1120px;padding-top:2.5rem;padding-bottom:3rem;}
    [data-testid="stSidebar"][aria-expanded="true"] {min-width:260px;max-width:300px;}
    [data-testid="stSidebar"][aria-expanded="false"] {min-width:0!important;max-width:0!important;width:0!important;}
    /* Depth: a soft canopy glow behind the conversation instead of a flat fill. */
    [data-testid="stAppViewContainer"] {background:
        radial-gradient(1200px 600px at 50% -10%, var(--canopy-accent-soft), transparent 70%), var(--canopy-bg)!important;}
    [data-testid="stHeader"] {background:transparent!important;}
    [data-testid="stSidebar"] {box-shadow: 1px 0 0 var(--canopy-border);}

    /* Sidebar: wordmark at the very top, centered. */
    [data-testid="stSidebarHeader"] {height:3.25rem;padding-top:.75rem;}
    [data-testid="stSidebarUserContent"] {padding:0 1.25rem 1.5rem;}
    .panda-wordmark {font-size:24px;font-weight:700;letter-spacing:6px;text-align:center;
        margin:-2.85rem 0 1.4rem;padding-left:6px;color:var(--canopy-text);}
    [data-testid="stSidebar"] button p {font-size:14px;}
    /* Sidebar collapse / expand arrows: always visible, readable on dark themes, above the wordmark. */
    .panda-wordmark {pointer-events:none;position:relative;z-index:0;}
    [data-testid="stSidebarCollapseButton"] {visibility:visible!important;display:block!important;position:relative;z-index:5;}
    [data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"] {
        border-radius:8px!important;border:1px solid var(--canopy-border)!important;background:var(--canopy-surface)!important;}
    [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"], [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapseButton"] span, [data-testid="stExpandSidebarButton"] span {color:var(--canopy-text)!important;}
    [data-testid="stSidebarCollapseButton"] button:hover, [data-testid="stExpandSidebarButton"]:hover {
        border-color:var(--canopy-accent)!important;background:var(--canopy-accent-soft)!important;}
    [data-testid="stSidebar"] [data-testid="stExpander"] {border:0;}
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {background:transparent!important;}
    .st-key-panda-docs-footer a {background:transparent!important;border:1px solid var(--canopy-border)!important;
        color:var(--canopy-text)!important;border-radius:10px;}
    .st-key-panda-docs-footer a p, .st-key-panda-docs-footer a span {color:var(--canopy-text)!important;}
    /* New chat: the primary action, so it stands out in white. */
    .st-key-panda-chat-actions button {background:var(--panda-cta-bg)!important;color:var(--panda-cta-fg)!important;border:0!important;
        border-radius:10px;font-weight:600;box-shadow:0 6px 18px rgba(0,0,0,.30);transition:transform .15s, box-shadow .15s;}
    .st-key-panda-chat-actions button p {color:var(--panda-cta-fg)!important;font-weight:600;}
    .st-key-panda-chat-actions button:hover {transform:translateY(-1px);box-shadow:0 10px 24px rgba(0,0,0,.38);}
    .st-key-panda-active-dataset {background:var(--canopy-surface);border:1px solid var(--canopy-border);
        border-radius:12px;padding:.7rem .8rem .8rem;gap:.35rem;}
    .panda-ds .label {font-size:12px;color:var(--canopy-muted);text-transform:uppercase;letter-spacing:.8px;}
    .panda-ds .name {font-weight:650;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .panda-ds .kind {font-size:12.5px;color:var(--canopy-muted);margin-top:2px;}

    /* Welcome state and composer position. */
    [data-testid="stBottom"] {transition:bottom .55s cubic-bezier(.22,1,.36,1);}
    [data-testid="stBottom"] > div {background:transparent!important;}
    [data-testid="stAppViewContainer"]:has(.panda-welcome) [data-testid="stBottom"] {bottom:max(24px,calc(50dvh - 270px))!important;}
    [data-testid="stBottomBlockContainer"] {max-width:840px;margin-inline:auto;padding-bottom:28px;}
    @media(prefers-reduced-motion:reduce) {[data-testid="stBottom"] {transition:none;}}
    .panda-welcome {text-align:center;padding:clamp(32px,10vh,110px) 0 24px;}
    .panda-welcome > svg {width:230px;max-width:52vw;height:auto;color:var(--canopy-text);opacity:.92;}
    .panda-welcome h1 {font-size:clamp(24px,2.4vw,32px);font-weight:500;letter-spacing:-.6px;margin:24px 0 0;padding:0;justify-content:center;}
    .panda-welcome [data-testid="stHeaderActionElements"] {display:none;}

    /* Prompt bar: rounded, floating, text and send button vertically centered. */
    .stApp [data-testid="stBottom"] > div, .stApp [data-testid="stBottomBlockContainer"] {
        background:linear-gradient(to top, var(--canopy-bg) 55%, transparent)!important;}
    .stApp [data-testid="stChatInput"] {border-radius:30px!important;border:1px solid var(--canopy-border)!important;
        background:var(--canopy-surface-strong)!important;
        box-shadow:0 22px 50px rgba(0,0,0,.50), inset 0 1px 0 rgba(255,255,255,.05)!important;
        padding:9px 9px 9px 20px!important;transition:box-shadow .2s, border-color .2s;}
    .stApp [data-testid="stChatInput"]:focus-within {border-color:var(--canopy-accent)!important;
        box-shadow:0 22px 50px rgba(0,0,0,.50), 0 0 0 3px var(--canopy-accent-soft)!important;}
    .stApp [data-testid="stChatInput"] > div, .stApp [data-testid="stChatInput"] > div > div,
    .stApp [data-testid="stChatInput"] [data-baseweb="textarea"], .stApp [data-testid="stChatInput"] [data-baseweb="base-input"] {
        background:transparent!important;border:0!important;box-shadow:none!important;}
    .stApp [data-testid="stChatInput"] > div > div {align-items:center!important;}
    .stApp [data-testid="stChatInput"] textarea {background:transparent!important;font-size:16px;line-height:24px;
        padding:9px 4px!important;min-height:42px!important;}
    .stApp [data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"] {width:42px!important;height:42px!important;
        min-width:42px;border-radius:50%!important;background:var(--panda-cta-bg)!important;color:var(--panda-cta-fg)!important;border:0!important;
        box-shadow:0 6px 16px rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;}
    .stApp [data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"] svg {color:var(--panda-cta-fg)!important;
        fill:var(--panda-cta-fg)!important;width:22px;height:22px;}
    .stApp [data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"]:hover:not(:disabled) {
        background:var(--canopy-accent-hover)!important;}
    .stApp [data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"]:disabled {opacity:.6!important;}
    .stApp [data-testid="stChatInput"] > div > div > div:has(> button) {align-self:center!important;display:flex;align-items:center;}

    /* Messages: avatars back, user turns as bubbles, assistant turns open. */
    [data-testid="stChatMessage"] {border:0;box-shadow:none;background:transparent!important;padding:1rem 0;gap:.9rem;}
    [data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] {width:34px;height:34px;
        border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
    [data-testid="stChatMessageAvatarUser"] {background:#2F6FA8!important;color:#fff!important;}
    [data-testid="stChatMessageAvatarAssistant"] {background:var(--canopy-accent)!important;color:#04120D!important;}
    [data-testid="stChatMessageAvatarUser"] svg, [data-testid="stChatMessageAvatarAssistant"] svg {color:inherit!important;}
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
        background:var(--canopy-surface-strong);border:1px solid var(--canopy-border);border-radius:16px;
        padding:.65rem 1rem;flex:0 1 auto!important;width:fit-content;max-width:100%;}
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {align-items:center;}
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {margin-right:auto!important;margin-left:0!important;}
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] p {margin:0!important;}

    /* Popovers and dialogs follow the theme instead of Streamlit's white defaults. */
    [data-testid="stPopoverBody"], div[role="dialog"] {background:var(--canopy-surface-strong)!important;
        color:var(--canopy-text)!important;border:1px solid var(--canopy-border)!important;border-radius:16px!important;
        box-shadow:0 28px 70px rgba(0,0,0,.55)!important;}
    [data-testid="stPopoverBody"] *, div[role="dialog"] h2, div[role="dialog"] label, div[role="dialog"] p {color:var(--canopy-text);}
    div[role="dialog"] [data-testid="stCaptionContainer"], [data-testid="stPopoverBody"] [data-testid="stCaptionContainer"] {color:var(--canopy-muted)!important;}
    .material-symbols-rounded {font-family:"Material Symbols Rounded";font-weight:normal;font-style:normal;line-height:1;
        letter-spacing:normal;text-transform:none;display:inline-block;white-space:nowrap;font-feature-settings:'liga';
        -webkit-font-smoothing:antialiased;}
    /* Dataset library dialog. */
    div[role="dialog"] {padding-top:4px;color:var(--canopy-text)!important;}
    .panda-lib-text .name, .panda-lib-section, .panda-lib-note {color:var(--canopy-text)!important;}
    div[role="dialog"] [data-testid="stButtonGroup"] button {background:var(--canopy-surface)!important;
        border:1px solid var(--canopy-border)!important;color:var(--canopy-muted)!important;}
    div[role="dialog"] [data-testid="stButtonGroup"] button p {color:inherit!important;}
    div[role="dialog"] [data-testid="stButtonGroup"] button[kind$="Active"] {background:var(--canopy-accent-soft)!important;
        border-color:var(--canopy-accent)!important;color:var(--canopy-text)!important;}
    div[role="dialog"] [data-testid="stButtonGroup"] button:first-child {border-radius:999px 0 0 999px!important;}
    div[role="dialog"] [data-testid="stButtonGroup"] button:last-child {border-radius:0 999px 999px 0!important;}
    [data-testid="stPopoverBody"] [data-testid="stButtonGroup"] button {background:var(--canopy-surface)!important;
        border:1px solid var(--canopy-border)!important;color:var(--canopy-text)!important;border-radius:999px!important;}
    [data-testid="stPopoverBody"] [data-testid="stButtonGroup"] button p {color:inherit!important;}
    [data-testid="stPopoverBody"] [data-testid="stButtonGroup"] button[kind$="Active"] {background:var(--canopy-accent-soft)!important;
        border-color:var(--canopy-accent)!important;}
    [data-testid="stPopoverBody"] [data-baseweb="textarea"], [data-testid="stPopoverBody"] textarea,
    div[role="dialog"] [data-baseweb="textarea"], div[role="dialog"] textarea {background:var(--canopy-surface)!important;
        color:var(--canopy-text)!important;border-color:var(--canopy-border)!important;}
    [data-testid="stPopoverBody"] textarea::placeholder {color:var(--canopy-muted)!important;opacity:1;}
    .panda-lib-note div, .panda-lib-note b {color:var(--canopy-text)!important;}
    .panda-lib-note code {color:var(--canopy-text)!important;}
    .panda-lib-help, .panda-lib-count, .panda-lib-text .meta {color:var(--canopy-muted)!important;}
    /* Answer actions: small icon buttons under each answer. */
    [class*="st-key-panda-actions-"] {margin-top:2px;gap:4px!important;}
    [class*="st-key-panda-actions-"] [data-testid="stPopover"] {width:auto!important;}
    [class*="st-key-panda-actions-"] [data-testid="stPopover"] button {width:32px;height:32px;min-height:32px;padding:0!important;
        border-radius:8px!important;background:transparent!important;border:1px solid transparent!important;
        color:var(--canopy-muted)!important;box-shadow:none!important;transform:none!important;}
    [class*="st-key-panda-actions-"] [data-testid="stPopover"] button:hover {background:var(--canopy-accent-soft)!important;
        border-color:var(--canopy-border)!important;color:var(--canopy-text)!important;}
    [class*="st-key-panda-actions-"] [data-testid="stPopover"] button div[aria-hidden="true"] {display:none!important;}
    [class*="st-key-panda-actions-"] [data-testid="stPopover"] button > div,
    [class*="st-key-panda-actions-"] [data-testid="stPopover"] button > div > div {justify-content:center;width:100%;margin:0!important;gap:0!important;}
    [class*="st-key-panda-actions-"] [data-testid="stIconMaterial"] {font-size:19px;color:inherit;}
    [class*="st-key-panda-actions-"][class*="-flagged"] [data-testid="stPopover"]:first-child button {color:#F07167!important;}
    div[role="dialog"] button[aria-label="Close"] {width:34px;height:34px;border-radius:50%;display:flex;align-items:center;
        justify-content:center;background:var(--canopy-surface)!important;border:1px solid var(--canopy-border)!important;
        color:var(--canopy-text)!important;opacity:1!important;}
    div[role="dialog"] button[aria-label="Close"]:hover {border-color:var(--canopy-accent)!important;background:var(--canopy-accent-soft)!important;}
    div[role="dialog"] button[aria-label="Close"] svg {width:12px;height:12px;stroke:var(--canopy-text)!important;}
    .panda-lib-note {display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:12px;font-size:13.5px;line-height:1.45;}
    .panda-lib-note .material-symbols-rounded {font-size:19px;margin-top:1px;}
    .panda-lib-note.warn {background:rgba(242,193,78,.10);border:1px solid rgba(242,193,78,.35);}
    .panda-lib-note.warn .material-symbols-rounded {color:#F2C14E;}
    .panda-lib-note.ok {background:var(--canopy-accent-soft);border:1px solid var(--canopy-border);}
    .panda-lib-note.ok .material-symbols-rounded {color:var(--canopy-accent);}
    .panda-lib-note code {font-size:12px;background:rgba(255,255,255,.07)!important;padding:1px 5px;border-radius:5px;}
    div[role="dialog"] [data-testid="stTextInputRootElement"] {border-radius:999px!important;background:var(--canopy-surface)!important;}
    .panda-lib-count {font-size:12px;letter-spacing:.6px;text-transform:uppercase;color:var(--canopy-muted);margin:4px 2px -4px;}
    [class*="st-key-library-row-"] {border:1px solid var(--canopy-border);border-radius:14px;padding:10px 12px 10px 12px;
        background:var(--canopy-surface);transition:border-color .15s, background .15s;gap:0!important;}
    [class*="st-key-library-row-"]:hover {border-color:rgba(92,194,133,.45);}
    [class*="st-key-library-row-"][class*="-active"] {border-color:var(--canopy-accent);background:var(--canopy-accent-soft);}
    [class*="st-key-library-row-"] [data-testid="stMarkdownContainer"] {margin-bottom:0!important;}
    .panda-lib-item {display:flex;align-items:center;gap:14px;min-width:0;}
    .panda-lib-icon {flex:0 0 40px;height:40px;border-radius:11px;display:flex;align-items:center;justify-content:center;}
    .panda-lib-icon .material-symbols-rounded {font-size:22px;}
    .panda-lib-icon.fvs {background:rgba(92,194,133,.16);color:#7AD69F;}
    .panda-lib-icon.csv {background:rgba(98,160,234,.16);color:#8DBBF2;}
    .panda-lib-icon.raster {background:rgba(242,193,78,.14);color:#F2C14E;}
    .panda-lib-text {min-width:0;}
    .panda-lib-text .name {font-weight:600;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .panda-lib-text .meta {font-size:12.5px;color:var(--canopy-muted);margin-top:2px;}
    .panda-lib-badge {display:flex;align-items:center;justify-content:center;gap:7px;height:36px;border-radius:999px;
        font-size:13.5px;font-weight:600;color:var(--canopy-accent-hover);}
    .panda-lib-badge span {width:8px;height:8px;border-radius:50%;background:var(--canopy-accent);
        box-shadow:0 0 0 4px var(--canopy-accent-soft);}
    [class*="st-key-library-pick-"] button {border-radius:999px!important;height:36px;min-height:36px;
        background:transparent!important;border:1px solid var(--canopy-accent)!important;color:var(--canopy-accent-hover)!important;}
    [class*="st-key-library-pick-"] button p {color:var(--canopy-accent-hover)!important;font-weight:600;}
    [class*="st-key-library-pick-"] button:hover {background:var(--canopy-accent)!important;}
    [class*="st-key-library-pick-"] button:hover p {color:#04120D!important;}
    [class*="st-key-library-row-"] [data-testid="stPopover"] button {border-radius:999px!important;height:30px;min-height:30px;
        margin-top:6px;font-size:12px;background:transparent!important;border-color:transparent!important;color:var(--canopy-muted)!important;}
    .st-key-library-upload-section {margin-top:10px;padding-top:16px;border-top:1px solid var(--canopy-border);}
    .panda-lib-section {font-weight:650;font-size:15px;}
    .panda-lib-help {font-size:12.5px;color:var(--canopy-muted);margin-top:2px;}
    div[role="dialog"] [data-testid="stFileUploaderDropzone"] {border-radius:14px!important;}
    [data-testid="stFileUploaderDropzone"] {background:var(--canopy-surface)!important;border:1px dashed var(--canopy-border)!important;}
    button[kind="primary"][data-testid="stBaseButton-primary"] {background:var(--canopy-accent)!important;
        color:#04120D!important;border:0!important;}
    button[kind="primary"][data-testid="stBaseButton-primary"]:hover {background:var(--canopy-accent-hover)!important;}
    button[kind="primary"][data-testid="stBaseButton-primary"] p {color:#04120D!important;font-weight:600;}
    button[kind="primary"][data-testid="stBaseButton-primary"]:disabled {opacity:.45;}
    [data-testid="stPopoverBody"] > div {background:transparent!important;}
    div[role="dialog"] input {color:var(--canopy-text)!important;}
    div[role="dialog"] input::placeholder {color:var(--canopy-muted)!important;opacity:1;}
    [data-testid="stFileUploaderDropzone"] small, [data-testid="stFileUploaderDropzone"] span {color:var(--canopy-muted)!important;}
    /* Streamlit pulls markdown blocks up by 1rem to absorb paragraph margins; undo where we control margins. */
    .st-key-panda-active-dataset [data-testid="stMarkdownContainer"],
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] {margin-bottom:0!important;}
    [data-testid="stChatMessageContent"] {min-width:0;}
    [data-testid="stMetric"], [data-testid="stExpander"], [data-testid="stAlert"] {box-shadow:none;}
    [data-testid="stDecoration"] {display:none;}

    /* Top-right tools: usage ring and report download, left of Streamlit's menu. */
    .st-key-panda-topbar-usage, .st-key-panda-topbar-download {position:fixed;top:12px;z-index:999991;width:auto!important;}
    .st-key-panda-topbar-usage {right:120px;}
    .st-key-panda-topbar-download {right:68px;}
    .st-key-panda-topbar-download button {width:40px;height:40px;min-height:40px;padding:0!important;border-radius:50%!important;
        background:var(--canopy-surface-strong)!important;border:1px solid var(--canopy-border)!important;
        box-shadow:0 8px 22px rgba(0,0,0,.40);}
    .st-key-panda-topbar-download button:hover {border-color:var(--canopy-accent)!important;}
    .st-key-panda-topbar-download button [data-testid="stIconMaterial"] {font-size:21px;color:var(--canopy-text);}
    .st-key-panda-topbar-download button div[aria-hidden="true"] {display:none!important;}
    .st-key-panda-topbar-download button > div, .st-key-panda-topbar-download button > div > div {justify-content:center;
        width:100%;margin:0!important;gap:0!important;}
    .panda-usage {position:relative;width:40px;height:40px;border-radius:50%;cursor:default;outline:none;
        background:var(--canopy-surface-strong);border:1px solid var(--canopy-border);box-shadow:0 8px 22px rgba(0,0,0,.40);}
    .panda-usage svg {position:absolute;inset:3px;width:32px;height:32px;transform:rotate(-90deg);}
    .panda-usage .pct {position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
        font-size:10.5px;font-weight:700;color:var(--canopy-text);letter-spacing:-.2px;}
    .panda-usage-card {display:none;position:absolute;top:48px;right:-52px;width:300px;padding:14px 16px;border-radius:14px;
        background:var(--canopy-surface-strong);border:1px solid var(--canopy-border);box-shadow:0 24px 60px rgba(0,0,0,.55);
        color:var(--canopy-text);font-size:13px;line-height:1.45;text-align:left;}
    .panda-usage:hover .panda-usage-card, .panda-usage:focus .panda-usage-card, .panda-usage:focus-within .panda-usage-card {display:block;}
    .panda-usage-card h4 {margin:0 0 8px;font-size:13px;font-weight:700;letter-spacing:.2px;color:var(--canopy-text);padding:0;}
    .panda-usage-card .prov {margin:10px 0 2px;font-weight:600;}
    .panda-usage-card .row {display:flex;justify-content:space-between;gap:12px;color:var(--canopy-muted);}
    .panda-usage-card .row b {color:var(--canopy-text);font-weight:600;}
    .panda-usage-card .bar {height:5px;border-radius:3px;background:rgba(255,255,255,.08);margin:3px 0 4px;overflow:hidden;}
    .panda-usage-card .bar span {display:block;height:100%;border-radius:3px;}
    .panda-usage-card .foot {margin-top:10px;font-size:11.5px;color:var(--canopy-muted);}

    /* Version stamp, bottom right. */
    .panda-version {position:fixed;right:18px;bottom:12px;z-index:999990;font-size:12px;letter-spacing:.4px;
        color:var(--canopy-muted);opacity:.85;pointer-events:none;}

    @media(max-width:760px) {
      [data-testid="stMainBlockContainer"] {padding:1.5rem 1rem 3rem;}
      .panda-welcome {padding-top:8vh;}
      .panda-welcome > svg {width:180px;}
      .panda-welcome h1 {margin-top:20px;}
      .panda-version {display:none;}
      .panda-usage-card {right:-40px;width:260px;}
    }
    </style>""", unsafe_allow_html=True)
    st.sidebar.markdown('<div class="panda-wordmark">PANDA</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="panda-version" title="Released {RELEASE_DATE}">PANDA {short_version()}</div>',
                unsafe_allow_html=True)
    with st.sidebar.container(key="panda-docs-footer"):
        st.link_button("Documentation & FAQ", "https://panda-docs.up.railway.app/", icon=":material/menu_book:", width="stretch")


def chat_composer(messages, key):
    submitted = st.session_state.pop(f"{key}-submitted", False)
    if not messages and not submitted and not st.session_state.get("show_dataset_details", False):
        st.markdown('<div class="panda-welcome">' + MARK_PATH.read_text() +
                         '<h1>What would you like to explore?</h1></div>', unsafe_allow_html=True)

    def mark_submitted():
        st.session_state[f"{key}-submitted"] = True

    # Keep the same native bottom input mounted in both states; moving its
    # container lets CSS animate it without duplicating or losing input focus.
    return st.chat_input(PLACEHOLDER, key=key, on_submit=mark_submitted)

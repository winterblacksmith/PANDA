"""Small action row under each PANDA answer: flag a bad output, and a "more" menu.

Flags are stored in `<PANDA_STORAGE_DIR>/canopy.sqlite`, table `response_flags`, so
reviewers can export them (Model connection panel) and see which answers looked
wrong, with the question, answer, reason, note and the model that was active.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import streamlit as st

FLAG_REASONS = ["Wrong numbers", "Made something up", "Doesn't answer", "Strange or off-topic", "Formatting", "Other"]


def _db_path() -> Path:
    return Path(os.environ.get("PANDA_STORAGE_DIR", "storage")) / "canopy.sqlite"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS response_flags (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               created_at TEXT NOT NULL,
               flag_key TEXT NOT NULL UNIQUE,
               dataset TEXT, chat_id TEXT, message_index INTEGER,
               model TEXT, reason TEXT NOT NULL, note TEXT,
               question TEXT, answer TEXT)"""
    )
    return conn


def save_flag(flag_key: str, *, dataset: str, chat_id: str, message_index: int, model: str,
              reason: str, note: str, question: str, answer: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO response_flags
                 (created_at, flag_key, dataset, chat_id, message_index, model, reason, note, question, answer)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(flag_key) DO UPDATE SET reason = excluded.reason, note = excluded.note,
                 created_at = excluded.created_at""",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), flag_key, dataset, chat_id,
             int(message_index), model, reason, note[:2000], question[:4000], answer[:12000]),
        )


def remove_flag(flag_key: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM response_flags WHERE flag_key = ?", (flag_key,))


def flagged_keys() -> set:
    try:
        with _connect() as conn:
            return {row[0] for row in conn.execute("SELECT flag_key FROM response_flags")}
    except sqlite3.Error:
        return set()


def flags_csv() -> tuple[int, bytes]:
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT created_at, dataset, chat_id, message_index, model, reason, note, question, answer "
            "FROM response_flags ORDER BY created_at DESC")
        rows = cursor.fetchall()
        header = [c[0] for c in cursor.description]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return len(rows), buffer.getvalue().encode("utf-8")


def message_text(message: Dict[str, Any]) -> str:
    parts = [str(message.get("content") or "")]
    for result in message.get("results", []) or []:
        for key in ("content", "explanation"):
            if result.get(key):
                parts.append(str(result[key]))
        verified = result.get("verified_summary") or (result.get("payload") or {}).get("verified_summary")
        if verified:
            parts.append("Verified result: " + str(verified))
    return "\n\n".join(p for p in parts if p).strip()


def preceding_question(messages: Sequence[Dict[str, Any]], index: int) -> str:
    for message in reversed(list(messages)[:index]):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _key(*parts: Any) -> str:
    return hashlib.sha1("::".join(str(p) for p in parts).encode()).hexdigest()[:16]


def render_response_actions(*, dataset: str, chat_id: str, message_index: int, question: str, answer: str,
                            part: Any = 0, extras_key: Optional[str] = None,
                            extras_label: str = "Show data result and developer details") -> None:
    """Flag button and, when there is something to show, a three-dots menu."""
    flag_key = _key(dataset, chat_id, message_index, part)
    flagged = flag_key in st.session_state.setdefault("panda_flagged_keys", flagged_keys())
    row_key = f"panda-actions-{flag_key}{'-flagged' if flagged else ''}"
    with st.container(key=row_key, horizontal=True, gap="small"):
        with st.popover("", icon=":material/flag:" if flagged else ":material/outlined_flag:",
                        help="Flagged — thanks" if flagged else "Flag a wrong or strange answer"):
            if flagged:
                st.markdown("**You flagged this answer.**")
                st.caption("Reviewers can export flagged answers from the Model connection panel.")
                if st.button("Remove flag", key=f"unflag-{flag_key}"):
                    remove_flag(flag_key)
                    st.session_state["panda_flagged_keys"].discard(flag_key)
                    st.rerun()
            else:
                st.markdown("**What looks off?**")
                reason = st.pills("Reason", FLAG_REASONS, key=f"flag-reason-{flag_key}", label_visibility="collapsed")
                note = st.text_area("Details (optional)", key=f"flag-note-{flag_key}", height=80,
                                    placeholder="e.g. the stand count doesn't match the table")
                if st.button("Submit flag", key=f"flag-submit-{flag_key}", type="primary", disabled=not reason):
                    try:
                        save_flag(flag_key, dataset=dataset, chat_id=str(chat_id), message_index=message_index,
                                  model=str(st.session_state.get("ollama_runtime") or ""), reason=reason,
                                  note=note or "", question=question, answer=answer)
                        st.session_state["panda_flagged_keys"].add(flag_key)
                        st.rerun()
                    except sqlite3.Error as exc:
                        st.error(f"Could not save the flag: {exc}")
        if extras_key is not None:
            with st.popover("", icon=":material/more_horiz:", help="More options"):
                st.session_state[extras_key] = st.toggle(extras_label, value=st.session_state.get(extras_key, False),
                                                         key=f"toggle-{extras_key}")

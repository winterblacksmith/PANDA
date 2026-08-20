"""Adapter between the PERSEUS app's existing chat storage and FVS UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import streamlit as st

from fvs_streamlit import render_fvs_mode


def render_fvs_drive_mode(app: Dict[str, Any], dataset_path: Path) -> None:
    """Render FVS mode while reusing the drive app's established helpers."""

    def persist_current_chat(dataset_key: str, chats_key: str, active_chat_id: str) -> None:
        app["save_chat"](
            dataset_key,
            active_chat_id,
            st.session_state[chats_key][active_chat_id],
        )

    def get_chat_storage_summary(dataset_key: str) -> Tuple[int, int]:
        app["ensure_chat_tables"]()
        with app["get_sql_connection"]() as connection:
            row = connection.execute(
                """
                SELECT COUNT(DISTINCT conversations.id), COUNT(messages.position)
                FROM chat_conversations AS conversations
                LEFT JOIN chat_messages AS messages
                  ON messages.conversation_id = conversations.id
                WHERE conversations.dataset_key = ?
                """,
                (dataset_key,),
            ).fetchone()
        return (int(row[0]), int(row[1])) if row else (0, 0)

    render_fvs_mode(
        csv_path=dataset_path,
        database_path=app["SQLITE_DB_PATH"],
        raster_dir=app["RASTER_DIR"],
        model_name=app["model_name"],
        use_model_explanation=app["use_model_explanation"],
        load_csv=app["load_csv"],
        sync_dataframe_to_sqlite=app["sync_dataframe_to_sqlite"],
        init_chat_state=app["init_chat_state"],
        create_new_chat=app["create_new_chat"],
        persist_current_chat=persist_current_chat,
        get_chat_storage_summary=get_chat_storage_summary,
        normalize_prompt=app["normalize_prompt"],
        safe_ollama_chat=app["safe_ollama_chat"],
        render_suggested_question_buttons=app["render_suggested_question_buttons"],
    )

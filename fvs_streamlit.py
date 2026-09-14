"""Streamlit presentation layer for Canopy's FVS integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
from safe_streamlit_render import render_html_bar_chart, render_html_table

from fvs_integration import (
    DISPLAY_COLUMNS,
    build_fvs_chart,
    execute_fvs_sql,
    format_fvs_filters,
    fvs_bundle_paths,
    make_fvs_map,
    make_selected_raster_overlay,
    parse_fvs_question,
    selected_stand_geojson,
    summarize_fvs_result,
)


def _preferred_raster(raster_dir: Path) -> Optional[Path]:
    for candidate in [
        raster_dir / "TreeMap_2022" / "TreeMap_2022.tif",
        raster_dir / "TreeMap_2022.tif",
    ]:
        if candidate.exists():
            return candidate
    return None


def _explain(
    question: str,
    result_df: pd.DataFrame,
    spec: Dict[str, Any],
    model_name: str,
    use_model: bool,
    safe_ollama_chat: Callable[..., str],
) -> str:
    verified_summary = summarize_fvs_result(result_df, spec)
    if result_df.empty or not use_model:
        return verified_summary
    prompt = f"""
You are Canopy, a local forestry data assistant. Use only the verified facts below.
Question: {question}
Applied filters: {format_fvs_filters(spec)}
Verified result: {verified_summary}
Composition counts: {json.dumps(result_df['COMPOSITIO'].value_counts().to_dict())}

Answer in 2-4 clear sentences. Do not invent causes, units, trends, or model assumptions.
Mention that the figures come from the local FVS stand-results table when useful.
"""
    answer = safe_ollama_chat(model_name, prompt, options={"temperature": 0.1})
    return answer or verified_summary


def _render_result(
    result: Dict[str, Any],
    csv_path: Path,
    database_path: Path,
    raster_dir: Path,
    table_name: str,
    active_chat_id: str,
    message_index: int,
) -> None:
    spec = result.get("spec") or parse_fvs_question(str(result.get("question", "")))
    result_df, sql_text, sql_parameters = execute_fvs_sql(database_path, table_name, spec)
    st.write(result.get("content") or summarize_fvs_result(result_df, spec))

    if not result_df.empty:
        metrics = st.columns(4)
        metrics[0].metric("Matching stands", f"{len(result_df):,}")
        metrics[1].metric("Total acres", f"{result_df['Acres'].sum():,.1f}")
        metrics[2].metric("Mean age", f"{result_df['Age'].mean():,.1f} years")
        total_volume = (result_df["TCuFt"] * result_df["Acres"]).sum()
        metrics[3].metric("Estimated volume", f"{total_volume:,.0f} cu ft")

    if spec.get("intent") == "chart" and not result_df.empty:
        group_column = spec.get("chart_group") or "Age"
        chart_data = build_fvs_chart(result_df, group_column)
        st.write(f"Sum of acres by {group_column.replace('_', ' ')}")
        render_html_bar_chart(chart_data, group_column, "Sum of Acres")
        render_html_table(chart_data, maximum_rows=500)

    if (spec.get("make_map") or spec.get("make_raster")) and not result_df.empty:
        maximum_polygons = 500
        bundle = fvs_bundle_paths(csv_path)
        geojson = selected_stand_geojson(
            bundle["shapefile"],
            result_df["MU_ID"].astype(int).head(maximum_polygons).tolist(),
            maximum=maximum_polygons,
        )
        raster_overlay = None
        if spec.get("make_raster"):
            raster_path = _preferred_raster(raster_dir)
            if raster_path is not None:
                selected_values = tuple(
                    sorted(result_df["TM_Value"].dropna().astype(int).unique().tolist())
                )
                raster_overlay = make_selected_raster_overlay(
                    str(raster_path.resolve()),
                    raster_path.stat().st_mtime,
                    selected_values,
                )
        result_map = make_fvs_map(geojson, raster_overlay)
        if result_map is not None:
            st_folium(
                result_map,
                use_container_width=True,
                height=600,
                key=f"fvs-map::{active_chat_id}::{message_index}",
            )
        if len(result_df) > maximum_polygons:
            st.caption(
                f"The map draws the first {maximum_polygons:,} matching polygons for responsiveness; "
                f"the totals and table use all {len(result_df):,} SQL rows."
            )
        if spec.get("make_raster"):
            st.caption(
                "Green cells are TreeMap pixels whose Band 1 value matches a selected FVS `TM_Value`. "
                "Stand polygons are selected independently through `MU_ID`."
            )

    if not result_df.empty:
        visible = [column for column in DISPLAY_COLUMNS if column in result_df.columns]
        render_html_table(
            result_df[visible],
            maximum_rows=int(spec.get("limit", 200)),
        )

    with st.expander("SQL and data proof", expanded=False):
        st.write(f"SQLite file: `{database_path.resolve()}`")
        st.write(f"SQL table: `{table_name}`")
        st.code(sql_text, language="sql")
        st.write("Bound parameters")
        st.json(sql_parameters)
        st.write(f"Returned rows: `{len(result_df):,}`")


def render_fvs_mode(
    *,
    csv_path: Path,
    database_path: Path,
    raster_dir: Path,
    model_name: str,
    use_model_explanation: bool,
    load_csv: Callable[[Path], pd.DataFrame],
    sync_dataframe_to_sqlite: Callable[[str, pd.DataFrame], str],
    init_chat_state: Callable[..., Any],
    create_new_chat: Callable[[str], None],
    persist_current_chat: Callable[..., None],
    get_chat_storage_summary: Callable[[str], Any],
    normalize_prompt: Callable[[str], str],
    safe_ollama_chat: Callable[..., str],
    render_suggested_question_buttons: Callable[..., Optional[str]],
) -> None:
    fvs_df = load_csv(csv_path)
    dataset_key = f"fvs::{csv_path.name}"
    source_key = f"fvs/{csv_path.name}"
    table_name = sync_dataframe_to_sqlite(source_key, fvs_df)
    chats_key, chats, active_chat_id = init_chat_state(dataset_key)

    if st.sidebar.button("New chat", width="stretch", key="new_fvs_chat"):
        create_new_chat(dataset_key)
        st.rerun()
    if st.sidebar.button("Clear current chat", width="stretch", key="clear_fvs_chat"):
        st.session_state[chats_key][active_chat_id]["messages"] = []
        st.session_state[chats_key][active_chat_id]["title"] = "New chat"
        persist_current_chat(dataset_key, chats_key, active_chat_id)
        st.rerun()

    chat_ids = list(st.session_state[chats_key])
    active_index = chat_ids.index(st.session_state[f"active_chat::{dataset_key}"])
    selected_chat_id = st.sidebar.selectbox(
        "Chat history",
        chat_ids,
        index=active_index,
        format_func=lambda chat_id: chats[chat_id]["title"],
        key="fvs_chat_history",
    )
    if selected_chat_id != st.session_state[f"active_chat::{dataset_key}"]:
        st.session_state[f"active_chat::{dataset_key}"] = selected_chat_id
        st.rerun()
    active_chat_id = st.session_state[f"active_chat::{dataset_key}"]
    messages = st.session_state[chats_key][active_chat_id]["messages"]
    suggested_key = f"suggested_prompt::{dataset_key}::{active_chat_id}"

    chat_count, message_count = get_chat_storage_summary(dataset_key)
    st.sidebar.caption(f"Saved in SQLite: {chat_count:,} chat(s), {message_count:,} message(s)")
    with st.sidebar.expander("FVS settings", expanded=False):
        st.caption(f"Local answer model: `{model_name}`")
        st.caption("Filtering backend: `SQLite` (parameterized)")
        st.caption("Geometry join: `MU_ID`")
        st.caption("TreeMap raster join: `TM_Value`")

    st.subheader("FVS stand simulation results")
    overview = st.columns(4)
    overview[0].metric("Stands", f"{len(fvs_df):,}")
    overview[1].metric("Unique MU_ID", f"{fvs_df['MU_ID'].nunique():,}")
    overview[2].metric("Total acres", f"{fvs_df['Acres'].sum():,.1f}")
    overview[3].metric("TreeMap profiles", f"{fvs_df['TM_Value'].nunique():,}")
    st.info(
        "Each SQLite row is one FVS stand. `MU_ID` selects its shapefile polygon; `TM_Value` selects "
        "the linked TreeMap raster cells. The raster attribute DBF explains the TreeMap plot profiles."
    )

    bundle = fvs_bundle_paths(csv_path)
    with st.expander("Dataset package and SQL proof", expanded=False):
        st.write(f"Source CSV: `{csv_path.resolve()}`")
        st.write(f"SQLite database: `{database_path.resolve()}`")
        st.write(f"SQLite table: `{table_name}`")
        st.write(f"Synchronized rows: `{len(fvs_df):,}`")
        st.write("Shapefile package")
        st.json({key: str(path.resolve()) for key, path in bundle.items() if key != "csv"})
        raster_path = _preferred_raster(raster_dir)
        if raster_path is not None:
            st.write("TreeMap raster package")
            st.json([str(path.resolve()) for path in sorted(raster_path.parent.glob("TreeMap_2022.*"))])

    for message_index, message in enumerate(messages):
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.write(message.get("content", ""))
            else:
                if message.get("content"):
                    st.write(message["content"])
                for result in message.get("results", []):
                    if result.get("type") == "fvs_query":
                        _render_result(
                            result, csv_path, database_path, raster_dir, table_name,
                            active_chat_id, message_index,
                        )

    suggested_prompt = st.session_state.pop(suggested_key, None)
    prompt = st.chat_input("Ask about FVS stands, charts, polygons, or the TreeMap raster...")
    active_prompt = suggested_prompt or prompt
    if active_prompt:
        cleaned_prompt = normalize_prompt(active_prompt)
        messages.append({"role": "user", "content": cleaned_prompt})
        current_title = st.session_state[chats_key][active_chat_id]["title"]
        if current_title.startswith("New chat") or current_title.startswith("Chat "):
            st.session_state[chats_key][active_chat_id]["title"] = (
                cleaned_prompt if len(cleaned_prompt) <= 40 else cleaned_prompt[:37] + "..."
            )
        persist_current_chat(dataset_key, chats_key, active_chat_id)
        with st.chat_message("user"):
            st.write(cleaned_prompt)
        with st.chat_message("assistant"):
            with st.spinner("Querying local FVS data..."):
                spec = parse_fvs_question(cleaned_prompt)
                filtered_df, sql_text, sql_parameters = execute_fvs_sql(
                    database_path, table_name, spec
                )
                content = _explain(
                    cleaned_prompt, filtered_df, spec, model_name,
                    use_model_explanation, safe_ollama_chat,
                )
                result = {
                    "type": "fvs_query",
                    "question": cleaned_prompt,
                    "spec": spec,
                    "content": content,
                    "data_backend": "SQLite",
                    "sql_query": sql_text,
                    "sql_parameters": sql_parameters,
                }
                _render_result(
                    result, csv_path, database_path, raster_dir, table_name,
                    active_chat_id, len(messages),
                )
        messages.append({"role": "assistant", "results": [result]})
        persist_current_chat(dataset_key, chats_key, active_chat_id)

    suggestions = [
        "Chart the sum of acres by age",
        "Show stands older than 60 with TCuFt above 3000",
        "Map old hardwood stands",
        "Visualize the TreeMap raster for stands older than 60",
        "Chart acres by composition",
        "How many mature coniferous stands are there?",
    ]
    next_prompt = render_suggested_question_buttons(
        suggestions,
        f"suggested::{dataset_key}::{active_chat_id}",
    )
    if next_prompt:
        st.session_state[suggested_key] = next_prompt
        st.rerun()

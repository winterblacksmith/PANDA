from pathlib import Path
import importlib

# Streamlit reruns in the same interpreter. Refresh directory caches when new
# project modules are added, including on external drives with coarse mtimes.
importlib.invalidate_caches()

import base64
from io import BytesIO
import json
import pickle
import re
import sqlite3
import struct
import zlib
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import folium
import numpy as np
import ollama
import pandas as pd
import streamlit as st
from PIL import Image
from folium.plugins import Draw
from streamlit_folium import st_folium
from fvs_integration import discover_fvs_csvs
from map_basemaps import carto_basemap

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


DATA_DIR = Path("data")
RASTER_DIR = Path("rasters")
STORAGE_DIR = Path("storage")
SQLITE_DB_PATH = STORAGE_DIR / "canopy.sqlite"
APP_STATE_VERSION = "stable_chat_tree_ai_2026_06_04_v1"
APP_NAME = "Canopy"
APP_DESCRIPTION = (
    "an AI knowledge base for forestry, tree inventory, and spatial datasets. "
    "It can summarize existing datasets, answer natural-language questions, filter records, "
    "and map usable location data."
)

MAP_TILE_OPTIONS = {
    "Standard": {
        "tiles": "OpenStreetMap",
        "attr": None,
    },
    "Light": carto_basemap("light_all"),
    "Dark": carto_basemap("dark_all"),
    "Terrain": {
        "tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "attr": "Map data: OpenStreetMap contributors, SRTM | Map style: OpenTopoMap",
    },
    "Satellite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    },
}

RASTER_EXTENSIONS = {".tif", ".tiff", ".img", ".vrt", ".jp2"}
RASTER_SEARCH_DIRS = [RASTER_DIR, DATA_DIR]
CSV_EXTENSIONS = {".csv"}
SUPPORTED_UPLOAD_EXTENSIONS = CSV_EXTENSIONS | RASTER_EXTENSIONS


THEME_PALETTES = {
    "Light": {
        "color_scheme": "light",
        "background": "#F5FAF6",
        "sidebar": "#EDF5EF",
        "surface": "rgba(255, 255, 255, 0.92)",
        "surface_strong": "#FFFFFF",
        "text": "#143024",
        "muted": "#4B6858",
        "border": "rgba(25, 76, 52, 0.20)",
        "accent": "#24764B",
        "accent_hover": "#195D39",
        "accent_soft": "rgba(36, 118, 75, 0.12)",
        "shadow": "0 12px 34px rgba(23, 63, 43, 0.08)",
    },
    "Dark": {
        "color_scheme": "dark",
        "background": "#0D1210",
        "sidebar": "#141B17",
        "surface": "rgba(27, 36, 31, 0.92)",
        "surface_strong": "#202A24",
        "text": "#F1F5F2",
        "muted": "#AAB9AF",
        "border": "rgba(232, 242, 235, 0.16)",
        "accent": "#61BD83",
        "accent_hover": "#7DD39B",
        "accent_soft": "rgba(97, 189, 131, 0.15)",
        "shadow": "0 14px 40px rgba(0, 0, 0, 0.24)",
    },
    "Forest": {
        "color_scheme": "dark",
        "background": "#071D15",
        "sidebar": "#0B271D",
        "surface": "rgba(17, 53, 40, 0.90)",
        "surface_strong": "#123B2C",
        "text": "#F2F7F3",
        "muted": "#B8CBBF",
        "border": "rgba(216, 239, 224, 0.18)",
        "accent": "#55B67A",
        "accent_hover": "#72CB92",
        "accent_soft": "rgba(85, 182, 122, 0.17)",
        "shadow": "0 16px 44px rgba(0, 8, 5, 0.30)",
    },
}


def apply_app_theme(theme_name: str) -> None:
    """Apply a local three-mode theme without depending on remote assets."""
    palette = THEME_PALETTES.get(theme_name, THEME_PALETTES["Forest"])

    st.markdown(
        f"""
        <style>
          :root {{
            color-scheme: {palette['color_scheme']};
            --canopy-bg: {palette['background']};
            --canopy-sidebar: {palette['sidebar']};
            --canopy-surface: {palette['surface']};
            --canopy-surface-strong: {palette['surface_strong']};
            --canopy-text: {palette['text']};
            --canopy-muted: {palette['muted']};
            --canopy-border: {palette['border']};
            --canopy-accent: {palette['accent']};
            --canopy-accent-hover: {palette['accent_hover']};
            --canopy-accent-soft: {palette['accent_soft']};
            --canopy-shadow: {palette['shadow']};
          }}

          .stApp,
          [data-testid="stAppViewContainer"] {{
            background: var(--canopy-bg);
            color: var(--canopy-text);
          }}

          [data-testid="stAppViewContainer"] > section,
          [data-testid="stSidebar"] > div {{
            position: relative;
            z-index: 1;
          }}

          [data-testid="stHeader"] {{
            background: var(--canopy-bg);
          }}

          [data-testid="stDecoration"] {{
            background: var(--canopy-accent);
          }}

          [data-testid="stSidebar"] {{
            position: relative;
            overflow: hidden;
            background: var(--canopy-sidebar);
            border-right: 1px solid var(--canopy-border);
          }}

          .stApp h1, .stApp h2, .stApp h3, .stApp h4,
          .stApp p, .stApp label, .stApp li,
          .stApp [data-testid="stMarkdownContainer"],
          .stApp [data-testid="stCaptionContainer"],
          .stApp [data-testid="stMetricValue"],
          .stApp [data-testid="stMetricLabel"] {{
            color: var(--canopy-text);
          }}

          .stApp [data-testid="stCaptionContainer"],
          .stApp small {{
            color: var(--canopy-muted);
          }}

          [data-testid="stMetric"] {{
            min-height: 108px;
            padding: 1rem 1.05rem;
            background: var(--canopy-surface);
            border: 1px solid var(--canopy-border);
            border-left: 3px solid var(--canopy-accent);
            border-radius: 10px;
            box-shadow: var(--canopy-shadow);
          }}

          [data-testid="stAlert"],
          [data-testid="stExpander"],
          [data-testid="stChatMessage"] {{
            background: var(--canopy-surface);
            color: var(--canopy-text);
            border: 1px solid var(--canopy-border);
            border-radius: 10px;
            box-shadow: var(--canopy-shadow);
          }}

          [data-testid="stExpander"] details,
          [data-testid="stExpander"] summary {{
            background: var(--canopy-surface-strong) !important;
            color: var(--canopy-text) !important;
          }}

          [data-testid="stExpander"] summary:hover,
          [data-testid="stExpander"] summary:focus-visible {{
            background: var(--canopy-accent-soft) !important;
            color: var(--canopy-text) !important;
          }}

          [data-testid="stExpander"] summary svg {{
            color: var(--canopy-text) !important;
            fill: currentColor;
          }}

          .stApp code {{
            background: var(--canopy-accent-soft) !important;
          }}

          .stButton > button,
          [data-testid="stSidebar"] button,
          [data-testid="stPopover"] button,
          button[data-testid="stBaseButton-secondary"] {{
            background: var(--canopy-surface) !important;
            color: var(--canopy-text) !important;
            border: 1px solid var(--canopy-border) !important;
            border-radius: 8px;
            transition: background-color 150ms ease, border-color 150ms ease, transform 150ms ease;
          }}

          .stButton > button:hover,
          [data-testid="stSidebar"] button:hover,
          [data-testid="stPopover"] button:hover,
          button[data-testid="stBaseButton-secondary"]:hover {{
            background: var(--canopy-accent-soft) !important;
            color: var(--canopy-text) !important;
            border-color: var(--canopy-accent) !important;
            transform: translateY(-1px);
          }}

          .stButton button p,
          [data-testid="stPopover"] button p,
          .stButton button span,
          [data-testid="stPopover"] button span {{
            color: inherit !important;
          }}

          [data-baseweb="select"] > div,
          [data-baseweb="input"] > div,
          [data-testid="stTextInputRootElement"],
          [data-testid="stChatInput"],
          [data-testid="stChatInput"] > div,
          [data-testid="stChatInput"] [data-baseweb="textarea"] {{
            background: var(--canopy-surface-strong) !important;
            color: var(--canopy-text) !important;
            border-color: var(--canopy-border) !important;
          }}

          [data-testid="stBottom"],
          [data-testid="stBottom"] > div,
          [data-testid="stBottomBlockContainer"] {{
            background: var(--canopy-bg) !important;
          }}

          [data-baseweb="select"] *,
          [data-baseweb="input"] * {{
            color: var(--canopy-text);
          }}

          [data-testid="stChatInput"] textarea {{
            background: var(--canopy-surface-strong) !important;
            color: var(--canopy-text) !important;
            -webkit-text-fill-color: var(--canopy-text) !important;
            caret-color: var(--canopy-accent-hover);
          }}

          [data-testid="stChatInput"] textarea::placeholder {{
            color: var(--canopy-muted) !important;
            -webkit-text-fill-color: var(--canopy-muted) !important;
            opacity: 1;
          }}

          [data-testid="stChatInput"] button {{
            color: var(--canopy-text) !important;
            background: var(--canopy-accent-soft) !important;
          }}

          [data-testid="stChatInput"] button:disabled {{
            color: var(--canopy-muted) !important;
            opacity: 0.65;
          }}

          [data-testid="stChatInput"] button svg {{
            fill: currentColor;
          }}

          [data-testid="stSegmentedControl"] [role="group"] {{
            display: flex;
            width: 100%;
          }}

          [data-testid="stSegmentedControl"] button {{
            flex: 1 1 0;
            min-width: 0;
            white-space: nowrap;
            justify-content: center;
          }}

          .stApp a,
          .stApp code {{
            color: var(--canopy-accent-hover);
          }}

          .stApp hr {{
            border-color: var(--canopy-border);
          }}

          @media (max-width: 760px) {{
            [data-testid="stMetric"] {{
              min-height: 92px;
              padding: 0.8rem;
            }}

          }}

          @media (prefers-reduced-motion: reduce) {{
            .stButton > button,
            .stPopover > button,
            [data-testid="stBaseButton-secondary"] {{
              transition: none;
            }}
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# File and model helpers
# -----------------------------

def get_tree_csv_files() -> List[Path]:
    return sorted([
        file for file in DATA_DIR.glob("*.csv")
        if not file.name.startswith("._") and "Column_Headers" not in file.name
    ])


def get_raster_files() -> List[Path]:
    files: List[Path] = []
    seen_paths = set()

    for raster_dir in RASTER_SEARCH_DIRS:
        if not raster_dir.exists():
            continue

        for file in sorted(raster_dir.rglob("*")):
            if (
                not file.is_file()
                or file.name.startswith("._")
                or file.suffix.lower() not in RASTER_EXTENSIONS
            ):
                continue

            resolved_path = file.resolve()
            if resolved_path in seen_paths:
                continue

            seen_paths.add(resolved_path)
            files.append(file)

    preferred_files: Dict[Tuple[str, int, int], Path] = {}
    for file in files:
        signature = (
            file.name.lower(),
            file.stat().st_size,
            file.stat().st_mtime_ns,
        )
        current = preferred_files.get(signature)
        direct_companion_count = sum(
            (file.parent / companion_name).exists()
            for companion_name in [
                file.name + ".vat.dbf",
                file.name + ".xml",
                file.name + ".aux.xml",
                file.with_suffix(".tfw").name,
            ]
        )
        current_companion_count = -1
        if current is not None:
            current_companion_count = sum(
                (current.parent / companion_name).exists()
                for companion_name in [
                    current.name + ".vat.dbf",
                    current.name + ".xml",
                    current.name + ".aux.xml",
                    current.with_suffix(".tfw").name,
                ]
            )
        if current is None or direct_companion_count > current_companion_count:
            preferred_files[signature] = file

    return sorted(preferred_files.values())


def get_dataset_options() -> List[Tuple[str, Path]]:
    fvs_options = [("fvs", path) for path in discover_fvs_csvs(DATA_DIR)]
    csv_options = [("csv", path) for path in get_tree_csv_files()]
    raster_options = [("raster", path) for path in get_raster_files()]
    return fvs_options + csv_options + raster_options


def format_dataset_option(option: Tuple[str, Path]) -> str:
    dataset_kind, path = option
    if dataset_kind == "fvs":
        label = "FVS stands + shapefile"
    elif dataset_kind == "raster":
        label = "Raster"
    else:
        label = "CSV"
    if dataset_kind == "raster" and path.parent != RASTER_DIR:
        try:
            folder = path.parent.relative_to(RASTER_DIR)
            return f"{path.name} ({label} - {folder})"
        except ValueError:
            pass
    return f"{path.name} ({label})"


def save_uploaded_dataset(uploaded_file: Any) -> Tuple[Optional[Path], Optional[str]]:
    safe_name = Path(str(uploaded_file.name)).name
    extension = Path(safe_name).suffix.lower()
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        return None, f"Unsupported file type: `{extension or 'none'}`."

    file_bytes = uploaded_file.getvalue()
    if not file_bytes:
        return None, "The uploaded file is empty."

    if extension in CSV_EXTENSIONS:
        try:
            pd.read_csv(BytesIO(file_bytes), nrows=5)
        except Exception as exc:
            return None, f"The CSV could not be read: {exc}"
        target_dir = DATA_DIR
    else:
        target_dir = RASTER_DIR

    target_dir.mkdir(exist_ok=True)
    target_path = target_dir / safe_name
    if target_path.exists():
        return None, f"A dataset named `{safe_name}` already exists. Rename the file before importing it again."

    target_path.write_bytes(file_bytes)
    return target_path, None


def get_installed_ollama_models() -> List[str]:
    try:
        response = ollama.list()
        raw_models = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])

        names = []
        for model in raw_models:
            if isinstance(model, dict):
                name = model.get("model") or model.get("name")
            else:
                name = getattr(model, "model", None) or getattr(model, "name", None)
            if name:
                names.append(name)

        return sorted(set(names)) if names else ["qwen2.5:3b", "qwen3.5:9b", "gpt-oss:20b"]
    except Exception:
        return ["qwen2.5:3b", "qwen3.5:9b", "gpt-oss:20b"]


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def ensure_storage_dirs() -> None:
    STORAGE_DIR.mkdir(exist_ok=True)
    RASTER_DIR.mkdir(exist_ok=True)


def safe_sql_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()
    return cleaned or "dataset"


def quote_sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def get_sql_table_name(csv_name: str) -> str:
    stem = Path(csv_name).stem
    return "dataset_" + safe_sql_identifier(stem)


def get_sql_connection() -> sqlite3.Connection:
    ensure_storage_dirs()
    return sqlite3.connect(SQLITE_DB_PATH)


def ensure_chat_tables() -> None:
    with get_sql_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id TEXT PRIMARY KEY,
                dataset_key TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_chat_conversations_dataset
            ON chat_conversations(dataset_key, updated_at DESC);

            CREATE TABLE IF NOT EXISTS chat_messages (
                conversation_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                message_blob BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (conversation_id, position),
                FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
            );
            """
        )


def encode_chat_message(message: Dict[str, Any]) -> bytes:
    return zlib.compress(pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL))


def decode_chat_message(message_blob: bytes) -> Dict[str, Any]:
    return pickle.loads(zlib.decompress(message_blob))


def load_saved_chats(dataset_key: str) -> Dict[str, Any]:
    ensure_chat_tables()
    chats: Dict[str, Any] = {}

    with get_sql_connection() as conn:
        conversations = conn.execute(
            """
            SELECT id, title
            FROM chat_conversations
            WHERE dataset_key = ?
            ORDER BY updated_at DESC, created_at DESC
            """,
            (dataset_key,),
        ).fetchall()

        for conversation_id, title in conversations:
            message_rows = conn.execute(
                """
                SELECT message_blob
                FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY position
                """,
                (conversation_id,),
            ).fetchall()
            messages = []
            for (message_blob,) in message_rows:
                try:
                    messages.append(decode_chat_message(message_blob))
                except Exception:
                    continue
            chats[conversation_id] = {"title": title, "messages": messages}

    return chats


def save_chat(dataset_key: str, conversation_id: str, chat: Dict[str, Any]) -> None:
    ensure_chat_tables()
    with get_sql_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_conversations (id, dataset_key, title)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                dataset_key = excluded.dataset_key,
                title = excluded.title,
                updated_at = CURRENT_TIMESTAMP
            """,
            (conversation_id, dataset_key, chat.get("title", "New chat")),
        )
        conn.execute(
            "DELETE FROM chat_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        conn.executemany(
            """
            INSERT INTO chat_messages (conversation_id, position, message_blob)
            VALUES (?, ?, ?)
            """,
            [
                (conversation_id, position, encode_chat_message(message))
                for position, message in enumerate(chat.get("messages", []))
            ],
        )


def sync_dataframe_to_sqlite(csv_name: str, df: pd.DataFrame) -> str:
    table_name = get_sql_table_name(csv_name)

    with get_sql_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_registry (
                csv_name TEXT PRIMARY KEY,
                table_name TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                column_count INTEGER NOT NULL,
                synced_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        existing = conn.execute(
            "SELECT row_count, column_count FROM dataset_registry WHERE csv_name = ?",
            (csv_name,),
        ).fetchone()

        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone() is not None

        if not table_exists or existing != (len(df), len(df.columns)):
            df.to_sql(table_name, conn, if_exists="replace", index=True, index_label="__rowid")
            conn.execute(
                """
                INSERT INTO dataset_registry (csv_name, table_name, row_count, column_count, synced_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(csv_name) DO UPDATE SET
                    table_name = excluded.table_name,
                    row_count = excluded.row_count,
                    column_count = excluded.column_count,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (csv_name, table_name, len(df), len(df.columns)),
            )

    return table_name


def get_sqlite_database_overview() -> pd.DataFrame:
    rows = []
    with get_sql_connection() as conn:
        table_names = [
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]
        for table_name in table_names:
            row_count = conn.execute(
                f"SELECT COUNT(*) FROM {quote_sql_identifier(table_name)}"
            ).fetchone()[0]
            if table_name.startswith("dataset_"):
                purpose = "Imported CSV data"
            elif table_name == "dataset_registry":
                purpose = "CSV import registry"
            elif table_name == "chat_conversations":
                purpose = "Saved chats"
            elif table_name == "chat_messages":
                purpose = "Saved chat messages"
            else:
                purpose = "Application data"
            rows.append({"Table": table_name, "Purpose": purpose, "Rows": int(row_count)})
    return pd.DataFrame(rows)


def get_sqlite_table_columns(table_name: str) -> pd.DataFrame:
    with get_sql_connection() as conn:
        rows = conn.execute(
            f"PRAGMA table_info({quote_sql_identifier(table_name)})"
        ).fetchall()
    return pd.DataFrame(
        rows,
        columns=["Position", "Column", "SQL type", "Required", "Default", "Primary key"],
    )


def preview_sqlite_table(table_name: str, limit: int = 25) -> pd.DataFrame:
    sql = f"SELECT * FROM {quote_sql_identifier(table_name)} LIMIT ?"
    with get_sql_connection() as conn:
        return pd.read_sql_query(sql, conn, params=[int(limit)])


def build_sql_where_clause(schema: Dict[str, Any], instructions: Dict[str, Any]) -> Tuple[List[str], List[Any], List[str], List[str]]:
    roles = schema["roles"]
    where_parts: List[str] = []
    params: List[Any] = []
    filters: List[str] = []
    warnings: List[str] = []

    species_cols = [roles.get("species_common"), roles.get("scientific_name")]
    species_cols = [col for col in species_cols if col]

    if instructions.get("species_text"):
        if species_cols:
            species_parts = []

            for col in species_cols:
                species_parts.append(f"LOWER(CAST({quote_sql_identifier(col)} AS TEXT)) LIKE ?")
                params.append("%" + str(instructions["species_text"]).lower() + "%")

            where_parts.append("(" + " OR ".join(species_parts) + ")")
            filters.append("species fields contain '" + str(instructions["species_text"]) + "'")
        else:
            warnings.append("I could not find a species/common-name column in this CSV.")

    if instructions.get("native_text"):
        native_col = roles.get("native_status")

        if native_col:
            where_parts.append(f"LOWER(CAST({quote_sql_identifier(native_col)} AS TEXT)) LIKE ?")
            params.append("%" + str(instructions["native_text"]).lower() + "%")
            filters.append(native_col + " contains '" + str(instructions["native_text"]) + "'")
        else:
            warnings.append("This CSV does not appear to contain a native-status column, so native-tree questions cannot be answered from this file.")

    diameter_col = roles.get("diameter_numeric")

    if diameter_col and (instructions.get("min_diameter") is not None or instructions.get("max_diameter") is not None):
        if instructions.get("min_diameter") is not None:
            where_parts.append(f"CAST({quote_sql_identifier(diameter_col)} AS REAL) >= ?")
            params.append(float(instructions["min_diameter"]))
            filters.append(diameter_col + " >= " + str(instructions["min_diameter"]))

        if instructions.get("max_diameter") is not None:
            where_parts.append(f"CAST({quote_sql_identifier(diameter_col)} AS REAL) <= ?")
            params.append(float(instructions["max_diameter"]))
            filters.append(diameter_col + " <= " + str(instructions["max_diameter"]))
    elif not diameter_col and (instructions.get("min_diameter") is not None or instructions.get("max_diameter") is not None):
        warnings.append("I could not find a numeric diameter/DBH column in this CSV.")

    danger_col = roles.get("danger_flag")

    if instructions.get("danger_value") is not None:
        if danger_col:
            where_parts.append(f"CAST({quote_sql_identifier(danger_col)} AS REAL) = ?")
            params.append(float(instructions["danger_value"]))
            filters.append(danger_col + " = " + str(instructions["danger_value"]))
        else:
            warnings.append("I could not find a danger/hazard flag column in this CSV.")

    if not filters:
        filters.append("No filters applied")

    return where_parts, params, filters, warnings


def run_filtered_query_sql(
    csv_name: str,
    df: pd.DataFrame,
    schema: Dict[str, Any],
    instructions: Dict[str, Any],
) -> Tuple[pd.DataFrame, List[str], List[str], str, List[Any]]:
    table_name = sync_dataframe_to_sqlite(csv_name, df)
    where_parts, params, filters, warnings = build_sql_where_clause(schema, instructions)
    sql = f"SELECT * FROM {quote_sql_identifier(table_name)}"

    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    with get_sql_connection() as conn:
        result = pd.read_sql_query(sql, conn, params=params)

    if "__rowid" in result.columns:
        result = result.set_index("__rowid", drop=True)
        result.index.name = None

    return result, filters, warnings, sql, params


def find_raster_companion(path: Path, companion_name: str) -> Optional[Path]:
    direct_candidate = path.parent / companion_name
    if direct_candidate.exists():
        return direct_candidate

    matches = []
    for raster_dir in RASTER_SEARCH_DIRS:
        if raster_dir.exists():
            matches.extend(raster_dir.rglob(companion_name))

    if not matches:
        return None

    matching_package = [
        match
        for match in matches
        if match.parent.name.lower() == path.stem.lower()
    ]
    return sorted(matching_package or matches)[0]


def get_raster_companion_paths(path: Path) -> Dict[str, Path]:
    return {
        key: companion
        for key, companion in {
            "attribute_table": find_raster_companion(path, path.name + ".vat.dbf"),
            "metadata": find_raster_companion(path, path.name + ".xml"),
            "auxiliary_metadata": find_raster_companion(path, path.name + ".aux.xml"),
            "world_file": find_raster_companion(path, path.with_suffix(".tfw").name),
        }.items()
        if companion is not None
    }


def get_raster_companion_signature(path: Path) -> Tuple[Tuple[str, float], ...]:
    return tuple(
        sorted(
            (key, companion.stat().st_mtime)
            for key, companion in get_raster_companion_paths(path).items()
        )
    )


@st.cache_data(show_spinner=False)
def read_dbf_table(path_text: str, modified_time: float) -> pd.DataFrame:
    del modified_time
    with open(path_text, "rb") as dbf_file:
        header = dbf_file.read(32)
        if len(header) < 32:
            raise ValueError("The DBF header is incomplete.")

        record_count = struct.unpack("<I", header[4:8])[0]
        header_length = struct.unpack("<H", header[8:10])[0]
        record_length = struct.unpack("<H", header[10:12])[0]
        fields = []

        while True:
            descriptor = dbf_file.read(32)
            if not descriptor or descriptor[0] == 0x0D:
                break
            fields.append({
                "name": descriptor[:11].split(b"\x00", 1)[0].decode("latin-1"),
                "type": chr(descriptor[11]),
                "length": descriptor[16],
                "decimals": descriptor[17],
            })

        dbf_file.seek(header_length)
        records = []
        for _ in range(record_count):
            record = dbf_file.read(record_length)
            if len(record) < record_length:
                break
            if record[0] == 0x2A:
                continue

            offset = 1
            parsed = {}
            for field in fields:
                raw_value = record[offset:offset + field["length"]].decode(
                    "latin-1",
                    errors="replace",
                ).strip()
                offset += field["length"]
                parsed[field["name"]] = raw_value or None
            records.append(parsed)

    table = pd.DataFrame(records)
    for field in fields:
        column = field["name"]
        if column not in table.columns or field["type"] not in {"N", "F"}:
            continue
        if column == "PLT_CN":
            table[column] = table[column].astype("string").str.replace(r"\.0+$", "", regex=True)
            continue
        table[column] = pd.to_numeric(table[column], errors="coerce")
        if field["decimals"] == 0:
            table[column] = table[column].astype("Int64")

    return table


@st.cache_data(show_spinner=False)
def read_raster_product_metadata(path_text: str, modified_time: float) -> Dict[str, Any]:
    import xml.etree.ElementTree as ET

    del modified_time
    root = ET.parse(path_text).getroot()
    title = root.findtext(".//resTitle")
    abstract = root.findtext(".//idAbs")
    entity_overview = root.findtext(".//eaover") or ""
    value_match = re.search(
        r"(?:^|\n)Value\s*=\s*(.+?)(?=\n[A-Za-z][A-Za-z0-9_]*\s*=|\Z)",
        entity_overview,
        flags=re.DOTALL,
    )

    value_definition = value_match.group(1).strip() if value_match else None
    band_role = "TM_ID" if "Equivalent to “TM_ID”" in entity_overview or "Equivalent to \"TM_ID\"" in entity_overview else None
    resolution = "30 x 30 meters" if re.search(r"30[×x]30\s*(?:meter|m)", entity_overview + "\n" + (abstract or ""), re.I) else None

    return {
        "title": title,
        "abstract": abstract,
        "value_definition": value_definition,
        "band_role": band_role,
        "resolution_description": resolution,
    }


def attach_raster_companion_data(path: Path, summary: Dict[str, Any]) -> Dict[str, Any]:
    companions = get_raster_companion_paths(path)
    summary["companion_files"] = {
        key: str(companion)
        for key, companion in companions.items()
    }

    metadata_path = companions.get("metadata")
    if metadata_path:
        try:
            summary["product_metadata"] = read_raster_product_metadata(
                str(metadata_path.resolve()),
                metadata_path.stat().st_mtime,
            )
        except Exception as exc:
            summary["metadata_warning"] = str(exc)

    attribute_path = companions.get("attribute_table")
    if not attribute_path:
        return summary

    try:
        attribute_table = read_dbf_table(
            str(attribute_path.resolve()),
            attribute_path.stat().st_mtime,
        )
    except Exception as exc:
        summary["attribute_table_warning"] = str(exc)
        return summary

    summary["attribute_table"] = attribute_table
    summary["attribute_rows"] = len(attribute_table)
    summary["attribute_fields"] = list(attribute_table.columns)

    if {"Value", "Count"}.issubset(attribute_table.columns):
        lookup_columns = [
            column
            for column in [
                "Value",
                "TM_ID",
                "ForTypName",
                "FldTypName",
                "BALIVE",
                "CANOPYPCT",
                "STANDHT",
                "TPA_LIVE",
            ]
            if column in attribute_table.columns
        ]
        lookup = attribute_table[lookup_columns].copy()
        top_table = pd.DataFrame(summary.get("top_values", []))
        if not top_table.empty:
            top_table = top_table.merge(lookup, on="Value", how="left")
            summary["top_values"] = top_table.to_dict("records")

    if {"ForTypName", "Count"}.issubset(attribute_table.columns):
        forest_types = (
            attribute_table.dropna(subset=["ForTypName"])
            .groupby("ForTypName", as_index=False)["Count"]
            .sum()
            .sort_values("Count", ascending=False)
        )
        total_pixels = float(forest_types["Count"].sum())
        forest_types = forest_types.rename(
            columns={"ForTypName": "Forest type", "Count": "Pixels"}
        )
        forest_types["Pixels"] = forest_types["Pixels"].round().astype("Int64")
        forest_types["Percent of mapped pixels"] = (
            forest_types["Pixels"].astype(float) / total_pixels * 100
        ).round(2)
        summary["forest_type_summary"] = forest_types.to_dict("records")

    return summary


def discover_raster_layers() -> List[Dict[str, Any]]:
    layers: List[Dict[str, Any]] = []
    seen_paths = set()

    for raster_dir in RASTER_SEARCH_DIRS:
        if not raster_dir.exists():
            continue

        for path in sorted(raster_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in RASTER_EXTENSIONS:
                continue

            resolved_path = path.resolve()
            if resolved_path in seen_paths:
                continue

            seen_paths.add(resolved_path)

            layer = {
                "name": path.name,
                "folder": str(path.parent),
                "path": str(path),
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
                "driver": "Unknown",
                "crs": "Unknown",
                "width": None,
                "height": None,
                "bands": None,
                "bounds": None,
                "rasterio_available": False,
            }

            try:
                import rasterio

                with rasterio.open(path) as src:
                    layer.update({
                        "driver": src.driver,
                        "crs": str(src.crs) if src.crs else "Unknown",
                        "width": src.width,
                        "height": src.height,
                        "bands": src.count,
                        "bounds": tuple(round(value, 6) for value in src.bounds),
                        "resolution": tuple(round(value, 6) for value in src.res),
                        "band_descriptions": list(src.descriptions),
                        "units": list(src.units),
                        "rasterio_available": True,
                    })

                    if src.crs:
                        try:
                            from rasterio.warp import transform_bounds

                            west, south, east, north = transform_bounds(
                                src.crs,
                                "EPSG:4326",
                                *src.bounds,
                                densify_pts=21,
                            )
                            layer["bounds_wgs84"] = (
                                round(west, 6),
                                round(south, 6),
                                round(east, 6),
                                round(north, 6),
                            )
                        except Exception as bounds_exc:
                            layer["bounds_transform_error"] = str(bounds_exc)
            except Exception as exc:
                layer["metadata_error"] = str(exc)

            layers.append(layer)

    return layers


@st.cache_data(show_spinner=False)
def read_raster_data_summary(
    path_text: str,
    modified_time: float,
    companion_signature: Tuple[Tuple[str, float], ...] = (),
) -> Dict[str, Any]:
    import rasterio

    del modified_time
    del companion_signature
    with rasterio.open(path_text) as src:
        band = src.read(1, masked=True)
        valid_values = band.compressed()
        if valid_values.size == 0:
            return {"valid_pixels": 0, "unique_values": 0, "top_values": []}

        values, counts = np.unique(valid_values, return_counts=True)
        top_indexes = np.argsort(counts)[::-1][:20]
        top_values = [
            {
                "Value": int(values[index]) if float(values[index]).is_integer() else float(values[index]),
                "Pixels": int(counts[index]),
                "Percent of valid pixels": round(float(counts[index] / valid_values.size * 100), 2),
            }
            for index in top_indexes
        ]

        summary = {
            "valid_pixels": int(valid_values.size),
            "nodata_pixels": int(band.size - valid_values.size),
            "minimum": float(valid_values.min()),
            "maximum": float(valid_values.max()),
            "mean": float(valid_values.mean()),
            "median": float(np.median(valid_values)),
            "unique_values": int(values.size),
            "top_values": top_values,
            "band_name": src.descriptions[0] if src.descriptions else None,
            "unit": src.units[0] if src.units else None,
            "has_color_table": False,
        }
        return attach_raster_companion_data(Path(path_text), summary)


@st.cache_data(show_spinner=False)
def make_raster_overlay(path_text: str, modified_time: float, max_width: int = 900) -> Dict[str, Any]:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import calculate_default_transform, reproject, transform_bounds

    del modified_time
    with rasterio.open(path_text) as src:
        if not src.crs:
            return {}

        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        transform, projected_width, projected_height = calculate_default_transform(
            src.crs,
            "EPSG:4326",
            src.width,
            src.height,
            *src.bounds,
        )
        scale = min(1.0, max_width / max(projected_width, 1))
        width = max(1, int(projected_width * scale))
        height = max(1, int(projected_height * scale))
        transform = transform * transform.scale(projected_width / width, projected_height / height)
        destination = np.full((height, width), np.nan, dtype="float32")

        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )

    valid = np.isfinite(destination)
    if not valid.any():
        return {}

    low, high = np.percentile(destination[valid], [2, 98])
    if high <= low:
        high = low + 1
    normalized = np.clip((destination - low) / (high - low), 0, 1)
    normalized = np.nan_to_num(normalized, nan=0.0)

    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[..., 0] = (35 + normalized * 205).astype(np.uint8)
    rgba[..., 1] = (75 + normalized * 155).astype(np.uint8)
    rgba[..., 2] = (110 - normalized * 65).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 205, 0).astype(np.uint8)

    image_buffer = BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(image_buffer, format="PNG")
    image_data = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    return {
        "data_url": f"data:image/png;base64,{image_data}",
        "bounds": [[south, west], [north, east]],
        "stretch_minimum": float(low),
        "stretch_maximum": float(high),
    }


def add_raster_data_overlay(m: folium.Map, layer: Dict[str, Any]) -> bool:
    path = Path(layer["path"])
    if not path.exists() or not layer.get("rasterio_available"):
        return False

    overlay = make_raster_overlay(str(path.resolve()), path.stat().st_mtime)
    if not overlay:
        return False

    folium.raster_layers.ImageOverlay(
        image=overlay["data_url"],
        bounds=overlay["bounds"],
        name=f"{layer.get('name', 'Raster')} values",
        opacity=0.8,
        interactive=True,
        cross_origin=False,
        zindex=2,
    ).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return True


def make_raster_footprint_map(raster_layers: List[Dict[str, Any]]) -> Optional[folium.Map]:
    footprint_layers = [
        layer
        for layer in raster_layers
        if layer.get("bounds_wgs84") and len(layer.get("bounds_wgs84")) == 4
    ]

    if not footprint_layers:
        return None

    first_bounds = footprint_layers[0]["bounds_wgs84"]
    west, south, east, north = first_bounds
    center_lat = (south + north) / 2
    center_lon = (west + east) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles=MAP_TILE_OPTIONS["Light"]["tiles"],
        attr=MAP_TILE_OPTIONS["Light"]["attr"],
        control_scale=True,
    )

    all_bounds = []

    for layer in footprint_layers:
        west, south, east, north = layer["bounds_wgs84"]
        rectangle_bounds = [[south, west], [north, east]]
        all_bounds.extend(rectangle_bounds)

        popup_parts = [
            f"Name: {layer.get('name', 'Raster')}",
            f"CRS: {layer.get('crs', 'Unknown')}",
            f"Size: {layer.get('width')} x {layer.get('height')}",
            f"Bands: {layer.get('bands')}",
        ]

        folium.Rectangle(
            bounds=rectangle_bounds,
            color="#2f80ed",
            weight=2,
            fill=True,
            fill_opacity=0.12,
            popup="<br>".join(popup_parts),
        ).add_to(m)

        if len(footprint_layers) == 1:
            add_raster_data_overlay(m, layer)

    if all_bounds:
        m.fit_bounds(all_bounds)

    return m


def get_raster_layer_for_path(path: Path) -> Dict[str, Any]:
    selected_path = path.resolve()

    for layer in discover_raster_layers():
        if Path(layer["path"]).resolve() == selected_path:
            return layer

    return {
        "name": path.name,
        "folder": str(path.parent),
        "path": str(path),
        "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else 0,
        "driver": "Unknown",
        "crs": "Unknown",
        "width": None,
        "height": None,
        "bands": None,
        "bounds": None,
        "rasterio_available": False,
        "metadata_error": "Raster metadata has not been read yet.",
    }


def format_raster_context(layer: Dict[str, Any]) -> str:
    data_summary = layer.get("data_summary", {})
    product_metadata = data_summary.get("product_metadata", {})
    dominant_forest_types = data_summary.get("forest_type_summary", [])[:10]
    return "\n".join([
        f"Name: {layer.get('name', 'Unknown')}",
        f"Folder: {layer.get('folder', 'Unknown')}",
        f"Size MB: {layer.get('size_mb', 'Unknown')}",
        f"Driver: {layer.get('driver', 'Unknown')}",
        f"CRS: {layer.get('crs', 'Unknown')}",
        f"Width: {layer.get('width', 'Unknown')}",
        f"Height: {layer.get('height', 'Unknown')}",
        f"Bands: {layer.get('bands', 'Unknown')}",
        f"Native bounds: {layer.get('bounds', 'Unknown')}",
        f"Geographic bounds: {layer.get('bounds_wgs84', 'Unknown')}",
        f"Valid pixels: {data_summary.get('valid_pixels', 'Unknown')}",
        f"NoData pixels: {data_summary.get('nodata_pixels', 'Unknown')}",
        f"Minimum value: {data_summary.get('minimum', 'Unknown')}",
        f"Maximum value: {data_summary.get('maximum', 'Unknown')}",
        f"Mean value: {data_summary.get('mean', 'Unknown')}",
        f"Median value: {data_summary.get('median', 'Unknown')}",
        f"Distinct values: {data_summary.get('unique_values', 'Unknown')}",
        f"Band description: {data_summary.get('band_name') or 'Not embedded in the file'}",
        f"Unit: {data_summary.get('unit') or 'Not embedded in the file'}",
        f"Product title: {product_metadata.get('title', 'Not available')}",
        f"Pixel value meaning: {product_metadata.get('value_definition') or 'Not documented'}",
        f"Band role: {product_metadata.get('band_role') or 'Not documented'}",
        f"Resolution description: {product_metadata.get('resolution_description') or layer.get('resolution', 'Unknown')}",
        f"Raster attribute rows: {data_summary.get('attribute_rows', 0)}",
        f"Raster attribute fields: {data_summary.get('attribute_fields', [])}",
        f"Dominant forest types weighted by mapped pixels: {dominant_forest_types}",
        f"Product abstract: {(product_metadata.get('abstract') or 'Not available')[:1600]}",
    ])


def summarize_raster_layer(layer: Dict[str, Any]) -> str:
    if not layer.get("rasterio_available"):
        error = layer.get("metadata_error")
        if error:
            return f"I found `{layer.get('name', 'this raster')}`, but I could not read its raster metadata yet: {error}"
        return f"I found `{layer.get('name', 'this raster')}`, but Rasterio is not available, so I can only see basic file information."

    width = layer.get("width")
    height = layer.get("height")
    bands = layer.get("bands")
    crs = layer.get("crs", "Unknown")
    bounds = layer.get("bounds_wgs84")
    data_summary = layer.get("data_summary", {})
    product_metadata = data_summary.get("product_metadata", {})
    location_text = f" Its geographic footprint is approximately {bounds}." if bounds else ""
    value_text = ""
    if data_summary.get("valid_pixels"):
        value_text = (
            f" Band 1 contains {data_summary['valid_pixels']:,} valid pixels and "
            f"{data_summary['unique_values']:,} distinct values, ranging from "
            f"{data_summary['minimum']:,.0f} to {data_summary['maximum']:,.0f}."
        )

    if product_metadata.get("band_role") == "TM_ID" and data_summary.get("attribute_rows"):
        dominant_types = data_summary.get("forest_type_summary", [])[:3]
        dominant_text = ", ".join(
            f"{row['Forest type']} ({row['Percent of mapped pixels']:.1f}%)"
            for row in dominant_types
        )
        return (
            f"`{layer.get('name')}` is a {layer.get('driver', 'raster')} TreeMap 2022 plot-identifier raster "
            f"with {bands} band, {width:,} columns by {height:,} rows, using CRS {crs}."
            f"{location_text}{value_text} Each valid pixel represents a 30 x 30 meter modeled forest cell "
            f"whose value is a `TM_ID`, linking it to one of {data_summary['attribute_rows']:,} forest plot "
            f"profiles in the accompanying attribute table. The dominant mapped forest types are {dominant_text}."
        )

    return (
        f"`{layer.get('name')}` is a {layer.get('driver', 'raster')} raster with {bands} band(s), "
        f"{width:,} columns by {height:,} rows, using CRS {crs}."
        f"{location_text}{value_text} The file does not include a band description, units, or a class legend, "
        "so its numeric codes cannot be named reliably without accompanying documentation."
    )


def interpret_raster_question(question: str, model_name: str, use_model: bool) -> str:
    valid_intents = {
        "summary",
        "crs",
        "location",
        "dimensions",
        "value_summary",
        "current_capabilities",
        "point_sampling",
        "polygon_analysis",
        "inventory_connection",
        "attribute_meaning",
        "forest_types",
        "general_chat",
        "other",
    }

    if use_model:
        prompt = f"""
Classify the user's question about Canopy or its selected raster dataset.
Return JSON only in this exact shape: {{"intent": "one_label"}}

Allowed labels:
- summary: asks for an overall raster summary
- crs: asks about projection or coordinate reference system
- location: asks where the raster is, its coverage, bounds, or extent
- dimensions: asks about width, height, bands, file size, or resolution
- value_summary: asks about pixels, values, statistics, minimum, maximum, mean, median, or distinct values
- current_capabilities: asks what Canopy can currently do with the raster
- point_sampling: asks what is needed to sample raster values at points
- polygon_analysis: asks about drawn polygons, zonal analysis, or values inside an area
- inventory_connection: asks how the raster connects or joins to a tree inventory or CSV
- attribute_meaning: asks what Band 1, pixel codes, TM_ID, plot IDs, or raster values represent
- forest_types: asks which forest types occur, are dominant, or cover the most area
- general_chat: casual conversation not asking about data or capabilities
- other: a raster-related question that does not fit another label

User question: {question}
"""
        parsed = extract_json(
            safe_ollama_chat(
                model_name,
                prompt,
                options={"temperature": 0, "num_predict": 40},
            )
        )
        if parsed and parsed.get("intent") in valid_intents:
            return str(parsed["intent"])

    lowered = question.lower()
    if "polygon" in lowered or "drawn" in lowered:
        return "polygon_analysis"
    if "tree inventory" in lowered or "connect" in lowered or "join" in lowered:
        return "inventory_connection"
    if "sample" in lowered or "tree point" in lowered:
        return "point_sampling"
    if "forest type" in lowered:
        return "forest_types"
    if any(term in lowered for term in ["tm_id", "plot id", "pixel code", "band 1 represent", "values represent"]):
        return "attribute_meaning"
    if "canopy" in lowered and any(term in lowered for term in ["do", "support", "right now"]):
        return "current_capabilities"
    if "crs" in lowered or "projection" in lowered:
        return "crs"
    if any(term in lowered for term in ["where", "located", "location", "extent", "bounds"]):
        return "location"
    if any(term in lowered for term in ["dimension", "width", "height", "resolution"]):
        return "dimensions"
    if any(term in lowered for term in ["value", "pixel", "minimum", "maximum", "mean", "median", "data"]):
        return "value_summary"
    if classify_prompt_type(question) == "general_chat":
        return "general_chat"
    return "other"


def answer_raster_question(question: str, layer: Dict[str, Any], model_name: str, use_model: bool) -> str:
    fallback = summarize_raster_layer(layer)
    lowered = question.lower().strip()
    data_summary = layer.get("data_summary", {})
    product_metadata = data_summary.get("product_metadata", {})
    bounds = layer.get("bounds_wgs84")
    intent = interpret_raster_question(question, model_name, use_model)
    has_attribute_table = bool(data_summary.get("attribute_rows"))
    attribute_capability = (
        "The accompanying raster attribute table is available, so Canopy can translate TM_ID pixel values into "
        "forest type, live basal area, canopy percentage, stand height, live trees per acre, biomass, and carbon attributes."
        if has_attribute_table
        else "No accompanying raster attribute table is available, so numeric codes cannot be translated into named attributes."
    )

    focus_contexts = {
        "current_capabilities": (
            "Canopy currently reads GeoTIFF metadata, displays the actual Band 1 cells as a color-stretched map "
            "layer, calculates whole-raster statistics and common numeric values, and reads an accompanying ArcGIS "
            f"raster attribute table when present. {attribute_capability} It does not yet sample CSV tree points, "
            "calculate statistics inside drawn polygons, or join raster values to inventory rows."
        ),
        "point_sampling": (
            "Point sampling is not implemented yet. The implementation requires reading tree coordinates from the "
            "selected CSV, transforming them from their source CRS into this raster's EPSG:5070 CRS, sampling Band 1 "
            "at each transformed coordinate with Rasterio, and attaching the sampled TM_ID and its linked forest "
            "attributes to the tree record."
        ),
        "polygon_analysis": (
            "The raster can be analyzed with polygons in principle, but the raster view does not perform this yet. "
            "The implementation must transform the drawn polygon into EPSG:5070, mask Band 1 to that geometry, and "
            "calculate pixel counts, percentages, dominant values, and area inside the polygon."
        ),
        "inventory_connection": (
            "The raster and CSV inventory are currently separate selectable datasets. Connecting them requires a "
            "spatial join: read each tree coordinate, transform it to EPSG:5070, sample Band 1 at that point, and add "
            "the sampled TM_ID and its linked forest-profile attributes to the corresponding tree row."
        ),
        "attribute_meaning": format_raster_context(layer),
        "forest_types": format_raster_context(layer),
        "general_chat": (
            "Canopy is an AI knowledge base for forestry, tree inventory, raster, and spatial datasets. Respond "
            "naturally to casual conversation and do not force dataset facts into the response."
        ),
    }
    focus_context = focus_contexts.get(intent, format_raster_context(layer))

    prompt = f"""
You are Canopy, an AI knowledge base for forestry, tree inventory, and spatial datasets.
The question has already been interpreted as: {intent}

Use only this relevant, verified context:
{focus_context}

USER QUESTION
{question}

Answer the exact question directly in 2-5 clear sentences. Do not discuss unrelated capabilities.
Do not restate the question or begin with "The question asks," "To clarify," or "It is unclear."
Never invent raster meanings, class names, units, or implemented features.
"""
    if use_model:
        answer = safe_ollama_chat(model_name, prompt, options={"temperature": 0.15})
        if answer:
            return answer

    if intent == "polygon_analysis":
        return (
            "The raster is already displayed on the map, but analysis inside a drawn polygon is not implemented yet. "
            "The next step is to mask Band 1 with the polygon and calculate value counts, percentages, and dominant values inside it."
        )
    if intent in {"point_sampling", "inventory_connection"}:
        return (
            "Connecting this raster to a tree inventory requires transforming each tree coordinate into EPSG:5070, "
            "sampling the raster cell at that location, and joining the sampled value back to the tree record. "
            "That point-sampling workflow is not implemented yet."
        )
    if intent == "current_capabilities":
        if has_attribute_table:
            return (
                "Canopy can read and map this GeoTIFF, summarize its pixels, interpret Band 1 as TreeMap `TM_ID` values, "
                "and use the accompanying attribute table to report forest type and structural attributes. Point "
                "sampling and polygon statistics are not implemented yet."
            )
        return (
            "Canopy can currently read this GeoTIFF, display its actual Band 1 cells, and summarize its metadata and "
            "whole-raster values. Point sampling, polygon statistics, and code translation are the next steps."
        )
    if intent == "general_chat":
        return explain_general_chat(question, model_name, False)
    if intent == "crs":
        return f"This raster uses `{layer.get('crs', 'an unknown CRS')}`."
    if bounds and intent == "location":
        west, south, east, north = bounds
        return f"The raster extends from approximately ({west:.4f}, {south:.4f}) to ({east:.4f}, {north:.4f}) in geographic coordinates."
    if data_summary.get("valid_pixels") and intent == "value_summary":
        return (
            f"Band 1 contains {data_summary['valid_pixels']:,} valid pixels and "
            f"{data_summary['unique_values']:,} distinct values, ranging from "
            f"{data_summary['minimum']:,.0f} to {data_summary['maximum']:,.0f}."
        )
    if intent == "attribute_meaning" and product_metadata.get("band_role") == "TM_ID":
        return (
            "Band 1 stores a TreeMap `TM_ID`, not a measured environmental unit. Each 30 x 30 meter forest pixel "
            "links to a modeled FIA plot profile in the accompanying attribute table."
        )
    if intent == "forest_types" and data_summary.get("forest_type_summary"):
        top_types = data_summary["forest_type_summary"][:5]
        readable = ", ".join(
            f"{row['Forest type']} ({row['Percent of mapped pixels']:.1f}%)"
            for row in top_types
        )
        return f"The dominant mapped forest types are {readable}."
    return fallback


def make_raster_suggested_questions(layer: Dict[str, Any]) -> List[str]:
    name = layer.get("name", "this raster")
    return [
        f"Summarize {name}",
        "What CRS does this raster use?",
        "Where is this raster located?",
        "What are the raster dimensions?",
        "What can Canopy do with this raster right now?",
        "What do the Band 1 pixel values represent?",
        "What are the dominant forest types in this raster?",
        "What is needed to sample raster values at tree points?",
        "Can this raster be used with drawn polygons?",
        "How would this raster connect to the tree inventory?",
    ]


def get_ollama_content(response: Any) -> str:
    try:
        if isinstance(response, dict):
            message = response.get("message", {})
            if isinstance(message, dict):
                return str(message.get("content", "") or "")
            return str(getattr(message, "content", "") or "")

        message = getattr(response, "message", None)
        if isinstance(message, dict):
            return str(message.get("content", "") or "")

        return str(getattr(message, "content", "") or "")
    except Exception:
        return ""


def safe_ollama_chat(model_name: str, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
    request_options = dict(options or {})
    try:
        force_cpu = bool(st.session_state.get("ollama_force_cpu", False))
    except Exception:
        force_cpu = False

    if force_cpu:
        request_options["num_gpu"] = 0

    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            options=request_options,
        )
        try:
            st.session_state["ollama_runtime"] = "CPU" if request_options.get("num_gpu") == 0 else "GPU"
            st.session_state.pop("last_ollama_error", None)
        except Exception:
            pass
        return get_ollama_content(response).strip()
    except Exception as first_error:
        if request_options.get("num_gpu") == 0:
            try:
                st.session_state["last_ollama_error"] = str(first_error)
            except Exception:
                pass
            return ""

        cpu_options = dict(request_options)
        cpu_options["num_gpu"] = 0
        try:
            response = ollama.chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                options=cpu_options,
            )
            try:
                st.session_state["ollama_force_cpu"] = True
                st.session_state["ollama_runtime"] = "CPU fallback"
                st.session_state.pop("last_ollama_error", None)
            except Exception:
                pass
            return get_ollama_content(response).strip()
        except Exception as cpu_error:
            try:
                st.session_state["last_ollama_error"] = (
                    f"GPU call failed: {first_error}; CPU retry failed: {cpu_error}"
                )
            except Exception:
                pass
            return ""


# -----------------------------
# Generic helpers
# -----------------------------

def safe_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_prompt(text: str) -> str:
    return str(text).strip().rstrip("\\").strip()


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    return None


def split_questions(text: str) -> List[str]:
    text = normalize_prompt(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[?.!;])\s+|\s+(?:and\s+also|also)\s+|\s+and\s+(?=(?:what|what's|whats|who|which|where|when|why|how|can|could|would|show|list|map|count)\b)",
        text,
        flags=re.IGNORECASE,
    )

    cleaned = []
    for part in parts:
        part = normalize_prompt(part)
        if part:
            cleaned.append(part)

    return cleaned


def column_exists(df: pd.DataFrame, options: List[str]) -> Optional[str]:
    lower_to_original = {col.lower(): col for col in df.columns}

    for option in options:
        if option.lower() in lower_to_original:
            return lower_to_original[option.lower()]

    return None


def get_coordinate_display_label(coordinate_kind: str, selected_projected_crs: Optional[str]) -> str:
    if coordinate_kind == "none":
        return "N/A"

    if coordinate_kind == "decimal_degrees":
        return "Ready"

    if coordinate_kind == "projected_crs_required":
        if selected_projected_crs:
            return "Ready"
        return "Needs CRS"

    return "N/A"


def get_coordinate_note(coordinate_kind: str, selected_projected_crs: Optional[str]) -> Optional[str]:
    if coordinate_kind == "none":
        return None

    if coordinate_kind == "decimal_degrees":
        return "Coordinates are ready for mapping."

    if coordinate_kind == "projected_crs_required" and selected_projected_crs:
        return "Coordinates are ready for mapping."

    if coordinate_kind == "projected_crs_required":
        return "Coordinates need a CRS before mapping."

    return None


# -----------------------------
# Intent routing
# -----------------------------

SPECIES_WORDS = [
    "live oak", "water oak", "willow oak", "overcup oak", "laurel oak",
    "loblolly pine", "flowering dogwood", "crape myrtle", "southern magnolia",
    "oak", "pine", "palm", "maple", "elm", "magnolia", "crapemyrtle",
    "cypress", "cedar", "holly", "palmetto", "dogwood", "poplar", "birch",
]

DATA_ACTION_WORDS = [
    "map", "plot", "where", "location", "locations", "geographic",
    "show", "list", "find", "filter", "count", "how many", "number of",
    "top", "most common", "common species", "diameter", "dbh", "height",
    "native", "introduced", "non-native", "condition", "danger", "hazard",
    "risk", "tree", "trees", "species", "dataset", "csv", "row", "rows",
    "column", "columns", "records",
]

FOLLOWUP_WORDS = [
    "those", "these", "them", "that", "same", "previous", "last result",
    "last results", "that group", "those trees", "these trees",
]


def classify_prompt_type(prompt: str) -> str:
    q = prompt.lower().strip()

    if not q:
        return "empty"

    if any(term in q for term in DATA_ACTION_WORDS):
        return "data"

    if any(species in q for species in SPECIES_WORDS):
        return "data"

    return "general_chat"


def question_is_map_request(question: str) -> bool:
    q = question.lower()
    return any(word in q for word in ["map", "plot", "where", "location", "locations", "geographic"])


def question_is_species_list_request(question: str) -> bool:
    q = question.lower()

    if "species" not in q:
        return False

    species_list_phrases = [
        "what are",
        "list",
        "show",
        "all",
        "which species",
        "tree species",
        "species in the dataset",
        "how many different",
        "how many unique",
        "different tree species",
        "unique tree species",
        "different species",
        "unique species",
    ]

    return any(phrase in q for phrase in species_list_phrases)


def make_suggested_questions(df: pd.DataFrame, schema: Dict[str, Any], coord_rows: int) -> List[str]:
    roles = schema.get("roles", {})
    suggestions: List[str] = ["Summarize this dataset"]

    species_col = roles.get("species_common")
    top_species: Optional[str] = None

    if species_col and species_col in df.columns:
        species_counts = df[species_col].dropna().astype(str).str.strip()
        species_counts = species_counts[species_counts != ""]

        if len(species_counts) > 0:
            top_species = str(species_counts.value_counts().index[0])

        suggestions.extend([
            "What are the most common species?",
            "List every species in the dataset",
        ])

        if top_species:
            suggestions.append(f"How many {top_species} trees are there?")

    if roles.get("danger_flag"):
        suggestions.append("Which trees are marked hazardous?")

    if roles.get("diameter_numeric") or roles.get("diameter_bin"):
        suggestions.append("Summarize tree diameter classes")

    if roles.get("native_status"):
        suggestions.append("Summarize native and introduced trees")

    if coord_rows > 0:
        suggestions.append("Map all trees")

        if top_species:
            suggestions.append(f"Map {top_species} trees")

    deduped: List[str] = []
    for suggestion in suggestions:
        if suggestion not in deduped:
            deduped.append(suggestion)

    return deduped[:8]


def is_followup_prompt(question: str) -> bool:
    q = question.lower()
    return any(word in q for word in FOLLOWUP_WORDS)


def has_filter_values(instructions: Dict[str, Any]) -> bool:
    return any([
        instructions.get("species_text") is not None,
        instructions.get("native_text") is not None,
        instructions.get("min_diameter") is not None,
        instructions.get("max_diameter") is not None,
        instructions.get("danger_value") is not None,
    ])


def merge_followup_filters(
    current_instructions: Dict[str, Any],
    previous_filter_instructions: Optional[Dict[str, Any]],
    question: str,
) -> Dict[str, Any]:
    if not previous_filter_instructions:
        return current_instructions

    if has_filter_values(current_instructions):
        return current_instructions

    if "all" in question.lower():
        return current_instructions

    if not is_followup_prompt(question):
        return current_instructions

    merged = dict(current_instructions)

    for key in ["species_text", "native_text", "min_diameter", "max_diameter", "danger_value"]:
        merged[key] = previous_filter_instructions.get(key)

    return merged


# -----------------------------
# Schema detection
# -----------------------------

def score_column_name(col: str, positive_terms: List[str], negative_terms: Optional[List[str]] = None) -> int:
    name = col.lower().replace(" ", "_")
    score = 0

    for term in positive_terms:
        if term.lower() in name:
            score += 10

    for term in negative_terms or []:
        if term.lower() in name:
            score -= 20

    return score


def best_text_column(df: pd.DataFrame, candidates: List[str], negative_terms: Optional[List[str]] = None) -> Optional[str]:
    scored: List[Tuple[int, str]] = []

    for col in df.columns:
        score = score_column_name(col, candidates, negative_terms)

        if score <= 0:
            continue

        non_null = int(df[col].notna().sum())
        unique = int(df[col].nunique(dropna=True))

        score += min(non_null, 1000) // 100
        score += min(unique, 200) // 20

        scored.append((score, col))

    return sorted(scored, reverse=True)[0][1] if scored else None


def best_numeric_column(df: pd.DataFrame, candidates: List[str], negative_terms: Optional[List[str]] = None) -> Optional[str]:
    scored: List[Tuple[int, str]] = []

    for col in df.columns:
        score = score_column_name(col, candidates, negative_terms)

        if score <= 0:
            continue

        numeric = pd.to_numeric(df[col], errors="coerce")
        numeric_count = int(numeric.notna().sum())

        if numeric_count == 0:
            continue

        name = col.lower()
        score += min(numeric_count, 1000) // 100

        if name.endswith("_1") or name.endswith("1"):
            score += 5

        if name.endswith("_2") or name.endswith("2"):
            score -= 2

        scored.append((score, col))

    return sorted(scored, reverse=True)[0][1] if scored else None


@st.cache_data(show_spinner=False)
def infer_schema_rules_only(csv_name: str, df: pd.DataFrame) -> Dict[str, Any]:
    roles: Dict[str, Optional[str]] = {
        "species_common": None,
        "scientific_name": None,
        "native_status": None,
        "diameter_numeric": None,
        "diameter_bin": None,
        "height_numeric": None,
        "latitude": None,
        "longitude": None,
        "condition": None,
        "danger_flag": None,
        "id": None,
    }

    roles["species_common"] = column_exists(df, ["common_name", "COMMON1", "COMMON", "species", "spc_common"])
    if not roles["species_common"]:
        roles["species_common"] = best_text_column(df, ["common", "species"], ["scientific", "sci"])

    roles["scientific_name"] = column_exists(df, ["scientific_name", "SCINAME1", "SCINAME", "latin_name"])
    if not roles["scientific_name"]:
        roles["scientific_name"] = best_text_column(df, ["scientific", "sciname", "sci", "latin"])

    roles["native_status"] = best_text_column(df, ["native", "origin", "introduced"])

    roles["diameter_bin"] = best_text_column(df, ["diameter", "dbh", "breast_height", "bin", "class", "range"])
    if roles["diameter_bin"]:
        name = roles["diameter_bin"].lower()
        if not any(term in name for term in ["bin", "class", "range"]):
            roles["diameter_bin"] = None

    roles["diameter_numeric"] = column_exists(df, ["DBH_1", "DBH", "diameter_breast_height_CM", "diameter"])
    if roles["diameter_numeric"]:
        if pd.to_numeric(df[roles["diameter_numeric"]], errors="coerce").notna().sum() == 0:
            roles["diameter_numeric"] = None

    if not roles["diameter_numeric"]:
        roles["diameter_numeric"] = best_numeric_column(
            df,
            ["dbh", "diameter", "breast_height", "diam"],
            ["bin", "class", "range"],
        )

    roles["height_numeric"] = column_exists(df, ["TOTALHT1", "TOTALHT", "height_M", "height"])
    if roles["height_numeric"]:
        if pd.to_numeric(df[roles["height_numeric"]], errors="coerce").notna().sum() == 0:
            roles["height_numeric"] = None

    if not roles["height_numeric"]:
        roles["height_numeric"] = best_numeric_column(df, ["height", "totalht", "total_ht", "ht"])

    roles["latitude"] = column_exists(df, ["latitude_coordinate", "latitude", "LAT", "lat", "y"])
    roles["longitude"] = column_exists(df, ["longitude_coordinate", "longitude", "LONG", "long", "lon", "lng", "x"])

    if not roles["latitude"]:
        roles["latitude"] = best_numeric_column(df, ["latitude", "lat", "northing", "y"])

    if not roles["longitude"]:
        roles["longitude"] = best_numeric_column(df, ["longitude", "long", "lon", "lng", "easting", "x"])

    roles["condition"] = best_text_column(df, ["condition", "health", "status"])

    roles["danger_flag"] = column_exists(df, ["IsDANGER", "danger", "hazard", "risk"])
    if not roles["danger_flag"]:
        roles["danger_flag"] = best_numeric_column(df, ["danger", "hazard", "risk"])

    roles["id"] = best_text_column(df, ["tree_id", "objectid", "fid", "id"])

    coordinate_kind = classify_coordinates(df, roles.get("latitude"), roles.get("longitude"))

    return {
        "roles": roles,
        "coordinate_kind": coordinate_kind,
        "schema_method": "rules_only",
    }


def build_column_profile(df: pd.DataFrame, max_examples: int = 6, max_columns: int = 80) -> List[Dict[str, Any]]:
    profile: List[Dict[str, Any]] = []
    total = len(df)

    for col in list(df.columns)[:max_columns]:
        series = df[col]
        numeric = pd.to_numeric(series, errors="coerce")
        non_null = int(series.notna().sum())
        numeric_non_null = int(numeric.notna().sum())
        examples = [safe_string(x) for x in series.dropna().head(max_examples).tolist()]

        item: Dict[str, Any] = {
            "name": col,
            "dtype": str(series.dtype),
            "non_null_count": non_null,
            "non_null_ratio": round(non_null / total, 3) if total else 0,
            "numeric_ratio": round(numeric_non_null / total, 3) if total else 0,
            "sample_values": examples,
        }

        if numeric_non_null > 0:
            item["numeric_min"] = float(numeric.min())
            item["numeric_max"] = float(numeric.max())
            item["numeric_median"] = float(numeric.median())
        else:
            value_counts = series.dropna().astype(str).value_counts().head(5)
            item["top_values"] = value_counts.to_dict()

        profile.append(item)

    return profile


def validate_ai_role(df: pd.DataFrame, role: str, col: Any) -> Optional[str]:
    if col is None:
        return None

    col = str(col).strip()

    if col.lower() in ["", "none", "null"]:
        return None

    if col not in df.columns:
        return None

    series = df[col]
    name = col.lower()

    if role in ["diameter_numeric", "height_numeric", "latitude", "longitude"]:
        numeric_count = int(pd.to_numeric(series, errors="coerce").notna().sum())
        return col if numeric_count > 0 else None

    if role == "native_status":
        values = " ".join(series.dropna().astype(str).head(300).str.lower().tolist())
        name_ok = any(term in name for term in ["native", "origin", "introduced"])
        value_ok = any(term in values for term in ["native", "introduced", "naturally", "occurring", "non-native"])
        return col if name_ok or value_ok else None

    if role == "danger_flag":
        name_ok = any(term in name for term in ["danger", "hazard", "risk"])
        values = set(series.dropna().astype(str).str.lower().head(50).tolist())
        flag_like = values.issubset({"0", "1", "0.0", "1.0", "true", "false", "yes", "no"}) if values else False
        return col if name_ok or flag_like else None

    if role in ["species_common", "scientific_name", "condition", "id", "diameter_bin"]:
        return col if int(series.notna().sum()) > 0 else None

    return col


def ask_ai_to_refine_schema(csv_name: str, profile_json: str, rule_roles_json: str, model_name: str) -> Dict[str, Any]:
    prompt = f"""
You are reviewing a tree inventory CSV schema.

CSV file: {csv_name}

Rule-based schema guess:
{rule_roles_json}

Column profile:
{profile_json}

Return only valid JSON. Do not include markdown, reasoning, or extra text.
Use this exact structure:
{{
  "species_common": null,
  "scientific_name": null,
  "native_status": null,
  "diameter_numeric": null,
  "diameter_bin": null,
  "height_numeric": null,
  "latitude": null,
  "longitude": null,
  "condition": null,
  "danger_flag": null,
  "id": null
}}

Rules:
- Use exact column names from the profile.
- Return null if a role is not present.
- Do not guess native_status unless a column clearly stores native/origin/introduced values.
- COMMON/common_name/species-like columns usually mean common species name.
- SCINAME/scientific/latin-like columns usually mean scientific name.
- DBH/diameter-like numeric columns usually mean diameter.
- TOTALHT/height-like numeric columns usually mean height.
- LAT/LONG/X/Y/northing/easting-like numeric columns can be coordinate fields.
- IsDANGER/danger/hazard/risk-like fields can be danger flags.
"""
    text = safe_ollama_chat(
        model_name,
        prompt,
        options={"temperature": 0, "num_predict": 350},
    )
    parsed = extract_json(text)
    return parsed if isinstance(parsed, dict) else {}


def merge_ai_schema(df: pd.DataFrame, base_schema: Dict[str, Any], ai_guess: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    roles = dict(base_schema["roles"])

    for role in roles.keys():
        proposed = validate_ai_role(df, role, ai_guess.get(role)) if isinstance(ai_guess, dict) else None
        if proposed:
            roles[role] = proposed

    coordinate_kind = classify_coordinates(df, roles.get("latitude"), roles.get("longitude"))

    return {
        "roles": roles,
        "coordinate_kind": coordinate_kind,
        "schema_method": f"ai_refined_with_{model_name}",
        "ai_schema_guess": ai_guess,
        "rule_schema_guess": base_schema["roles"],
    }


def refine_schema_job(
    df: pd.DataFrame,
    csv_name: str,
    base_schema: Dict[str, Any],
    schema_model_name: str,
) -> Dict[str, Any]:
    profile = build_column_profile(df)

    ai_guess = ask_ai_to_refine_schema(
        csv_name,
        json.dumps(profile, indent=2),
        json.dumps(base_schema["roles"], indent=2),
        schema_model_name,
    )

    return merge_ai_schema(
        df,
        base_schema,
        ai_guess,
        schema_model_name,
    )


def classify_coordinates(df: pd.DataFrame, lat_col: Optional[str], lon_col: Optional[str]) -> str:
    if not lat_col or not lon_col:
        return "none"

    lat = pd.to_numeric(df[lat_col], errors="coerce")
    lon = pd.to_numeric(df[lon_col], errors="coerce")
    valid = lat.notna() & lon.notna()

    if int(valid.sum()) == 0:
        return "none"

    lat_med = float(lat[valid].median())
    lon_med = float(lon[valid].median())

    if -90 <= lat_med <= 90 and -180 <= lon_med <= 180:
        return "decimal_degrees"

    return "projected_crs_required"


def get_map_coordinates(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str,
    coordinate_kind: str,
    selected_projected_crs: Optional[str],
) -> Tuple[Optional[pd.Series], Optional[pd.Series], Optional[str]]:
    raw_lat = pd.to_numeric(df[lat_col], errors="coerce")
    raw_lon = pd.to_numeric(df[lon_col], errors="coerce")

    if coordinate_kind == "decimal_degrees":
        return raw_lat, raw_lon, None

    if coordinate_kind == "projected_crs_required":
        if not selected_projected_crs:
            return None, None, (
                "Coordinate fields were found, but they need a coordinate system before mapping. "
                "Choose a projected CRS in Advanced options."
            )

        try:
            from pyproj import Transformer
        except Exception:
            return None, None, "Install pyproj first: python -m pip install pyproj"

        try:
            transformer = Transformer.from_crs(selected_projected_crs, "EPSG:4326", always_xy=True)

            lon_values, lat_values = transformer.transform(
                raw_lon.to_numpy(),
                raw_lat.to_numpy(),
            )

            return pd.Series(lat_values, index=df.index), pd.Series(lon_values, index=df.index), None

        except Exception as exc:
            return None, None, f"Coordinate transformation failed: {exc}"

    return None, None, "No usable coordinates were found."


def get_map_status(
    df: pd.DataFrame,
    schema: Dict[str, Any],
    selected_projected_crs: Optional[str],
) -> Dict[str, Any]:
    roles = schema.get("roles", {})
    lat_col = roles.get("latitude")
    lon_col = roles.get("longitude")
    coordinate_kind = schema.get("coordinate_kind", "none")

    status = {
        "map_available": False,
        "coordinate_rows": 0,
        "message": None,
        "coordinate_kind": coordinate_kind,
    }

    if not lat_col or not lon_col or coordinate_kind == "none":
        status["message"] = "No usable coordinate columns were detected in this CSV."
        return status

    map_df = df.dropna(subset=[lat_col, lon_col]).copy()

    if len(map_df) == 0:
        status["message"] = "No rows have usable coordinate values."
        return status

    lat_values, lon_values, error = get_map_coordinates(
        map_df,
        lat_col,
        lon_col,
        coordinate_kind,
        selected_projected_crs,
    )

    if error:
        status["message"] = error
        return status

    if lat_values is None or lon_values is None:
        status["message"] = "Could not prepare coordinates for mapping."
        return status

    valid = (
        lat_values.notna()
        & lon_values.notna()
        & lat_values.between(-90, 90)
        & lon_values.between(-180, 180)
    )
    coordinate_rows = int(valid.sum())

    if coordinate_rows == 0:
        status["message"] = "No valid latitude/longitude values remained after conversion."
        return status

    status["map_available"] = True
    status["coordinate_rows"] = coordinate_rows
    return status


# -----------------------------
# Question interpretation
# -----------------------------

def blank_instructions() -> Dict[str, Any]:
    return {
        "intent": "summary",
        "species_text": None,
        "native_text": None,
        "min_diameter": None,
        "max_diameter": None,
        "danger_value": None,
        "make_map": False,
        "limit": 1000,
    }


def parse_with_rules(question: str) -> Dict[str, Any]:
    q = question.lower()
    instructions = blank_instructions()

    if question_is_species_list_request(question):
        instructions["intent"] = "species_list"
    elif any(word in q for word in ["map", "plot", "geographic", "where", "location", "locations"]):
        instructions["intent"] = "map"
        instructions["make_map"] = True
    elif any(phrase in q for phrase in ["top species", "most common species", "common species"]):
        instructions["intent"] = "top_species"
    elif any(word in q for word in ["diameter", "dbh", "size class", "size classes", "diameter bins", "diameter bin"]):
        instructions["intent"] = "diameter_summary"
    elif any(word in q for word in ["native", "introduced", "non-native", "non native"]):
        instructions["intent"] = "native_summary"
    elif any(word in q for word in ["danger", "dangerous", "hazard", "hazardous", "risk"]):
        instructions["intent"] = "danger_summary"
    elif any(phrase in q for phrase in ["how many", "count", "number of"]):
        instructions["intent"] = "count"
    elif any(word in q for word in ["show", "list", "find", "filter"]):
        instructions["intent"] = "filter"

    for word in sorted(SPECIES_WORDS, key=len, reverse=True):
        if word in q:
            instructions["species_text"] = word
            if instructions["intent"] == "summary":
                instructions["intent"] = "filter"
            break

    if "naturally occurring" in q:
        instructions["native_text"] = "naturally_occurring"
    elif "introduced" in q or "non-native" in q or "non native" in q:
        instructions["native_text"] = "introduced"
    elif "native" in q and not any(phrase in q for phrase in ["native vs", "native versus", "native and introduced"]):
        instructions["native_text"] = "naturally_occurring"

    if any(word in q for word in ["danger", "dangerous", "hazard", "hazardous"]):
        instructions["danger_value"] = 1

    greater_than = re.search(r"(?:greater than|over|above|more than)\s+(\d+(?:\.\d+)?)", q)
    less_than = re.search(r"(?:less than|under|below|fewer than)\s+(\d+(?:\.\d+)?)", q)

    if greater_than:
        instructions["min_diameter"] = float(greater_than.group(1))
        if instructions["intent"] == "summary":
            instructions["intent"] = "filter"

    if less_than:
        instructions["max_diameter"] = float(less_than.group(1))
        if instructions["intent"] == "summary":
            instructions["intent"] = "filter"

    return instructions


def ask_model_for_parse(question: str, schema: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    prompt = f"""
Return only valid JSON. Do not include reasoning, markdown, or extra text.
If you have a thinking mode, do not use it.

Detected tree dataset roles:
{json.dumps(schema["roles"], indent=2)}

Convert the question into this exact JSON structure:
{{
  "intent": "summary",
  "species_text": null,
  "native_text": null,
  "min_diameter": null,
  "max_diameter": null,
  "danger_value": null,
  "make_map": false,
  "limit": 1000
}}

Intent must be one of: summary, count, top_species, species_list, native_summary, diameter_summary, danger_summary, filter, map.
Use species_list when the user asks what species are in the dataset or asks to list all tree species.
Use intent count for "how many" questions.
Use intent top_species for most common species.
Use intent native_summary for native/introduced questions.
Use intent diameter_summary for diameter/DBH/bin questions.
Use intent danger_summary and danger_value 1 for danger/hazard questions.
Use intent map and make_map true for map/location questions.
For species groups like oak, pine, dogwood, poplar, maple, magnolia, etc., put the word in species_text.
For native trees, set native_text to naturally_occurring.

Question: {question}
"""
    text = safe_ollama_chat(
        model_name,
        prompt,
        options={"temperature": 0, "num_predict": 180},
    )
    parsed = extract_json(text)
    return parsed if isinstance(parsed, dict) else blank_instructions()


def clean_instruction_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str) and value.strip().lower() in ["", "none", "null"]:
        return None

    return value


def interpret_question(question: str, schema: Dict[str, Any], model_name: str, use_model_parse: bool) -> Dict[str, Any]:
    rule_instructions = parse_with_rules(question)
    model_instructions = ask_model_for_parse(question, schema, model_name) if use_model_parse else blank_instructions()

    allowed_intents = {
        "summary", "count", "top_species", "species_list", "native_summary",
        "diameter_summary", "danger_summary", "filter", "map"
    }

    merged = blank_instructions()
    merged.update(model_instructions or {})

    if merged.get("intent") not in allowed_intents:
        merged["intent"] = "summary"

    for key in ["species_text", "native_text", "min_diameter", "max_diameter", "danger_value"]:
        merged[key] = clean_instruction_value(merged.get(key))

    try:
        merged["limit"] = int(merged.get("limit") or 1000)
    except Exception:
        merged["limit"] = 1000

    for key in ["species_text", "native_text", "min_diameter", "max_diameter", "danger_value"]:
        if rule_instructions.get(key) is not None:
            merged[key] = rule_instructions[key]

    if rule_instructions.get("intent") != "summary":
        merged["intent"] = rule_instructions["intent"]

    if rule_instructions.get("make_map"):
        merged["make_map"] = True

    return merged


# -----------------------------
# Query execution, caching, summaries
# -----------------------------

def make_query_cache_key(
    csv_name: str,
    df: pd.DataFrame,
    schema: Dict[str, Any],
    instructions: Dict[str, Any],
) -> str:
    roles = schema.get("roles", {})

    cache_payload = {
        "csv_name": csv_name,
        "row_count": len(df),
        "schema_method": schema.get("schema_method", "unknown"),
        "roles": {
            "species_common": roles.get("species_common"),
            "scientific_name": roles.get("scientific_name"),
            "native_status": roles.get("native_status"),
            "diameter_numeric": roles.get("diameter_numeric"),
            "danger_flag": roles.get("danger_flag"),
        },
        "filters": {
            "species_text": instructions.get("species_text"),
            "native_text": instructions.get("native_text"),
            "min_diameter": instructions.get("min_diameter"),
            "max_diameter": instructions.get("max_diameter"),
            "danger_value": instructions.get("danger_value"),
        },
    }

    return json.dumps(cache_payload, sort_keys=True)


def apply_filters(df: pd.DataFrame, schema: Dict[str, Any], instructions: Dict[str, Any]) -> Tuple[pd.DataFrame, List[str], List[str]]:
    roles = schema["roles"]
    filtered = df.copy()
    filters: List[str] = []
    warnings: List[str] = []

    species_cols = [roles.get("species_common"), roles.get("scientific_name")]
    species_cols = [col for col in species_cols if col]

    if instructions.get("species_text"):
        if species_cols:
            mask = pd.Series(False, index=filtered.index)

            for col in species_cols:
                mask = mask | filtered[col].astype(str).str.contains(str(instructions["species_text"]), case=False, na=False)

            filtered = filtered[mask]
            filters.append("species fields contain '" + str(instructions["species_text"]) + "'")
        else:
            warnings.append("I could not find a species/common-name column in this CSV.")

    if instructions.get("native_text"):
        native_col = roles.get("native_status")

        if native_col:
            filtered = filtered[filtered[native_col].astype(str).str.contains(str(instructions["native_text"]), case=False, na=False)]
            filters.append(native_col + " contains '" + str(instructions["native_text"]) + "'")
        else:
            warnings.append("This CSV does not appear to contain a native-status column, so native-tree questions cannot be answered from this file.")

    diameter_col = roles.get("diameter_numeric")

    if diameter_col and (instructions.get("min_diameter") is not None or instructions.get("max_diameter") is not None):
        numeric = pd.to_numeric(filtered[diameter_col], errors="coerce")

        if instructions.get("min_diameter") is not None:
            filtered = filtered[numeric >= float(instructions["min_diameter"])]
            filters.append(diameter_col + " >= " + str(instructions["min_diameter"]))

        if instructions.get("max_diameter") is not None:
            numeric = pd.to_numeric(filtered[diameter_col], errors="coerce")
            filtered = filtered[numeric <= float(instructions["max_diameter"])]
            filters.append(diameter_col + " <= " + str(instructions["max_diameter"]))
    elif not diameter_col and (instructions.get("min_diameter") is not None or instructions.get("max_diameter") is not None):
        warnings.append("I could not find a numeric diameter/DBH column in this CSV.")

    danger_col = roles.get("danger_flag")

    if instructions.get("danger_value") is not None:
        if danger_col:
            numeric = pd.to_numeric(filtered[danger_col], errors="coerce")
            filtered = filtered[numeric == float(instructions["danger_value"])]
            filters.append(danger_col + " = " + str(instructions["danger_value"]))
        else:
            warnings.append("I could not find a danger/hazard flag column in this CSV.")

    if not filters:
        filters.append("No filters applied")

    return filtered, filters, warnings


def get_or_run_filtered_query(
    csv_name: str,
    df: pd.DataFrame,
    schema: Dict[str, Any],
    instructions: Dict[str, Any],
) -> Tuple[pd.DataFrame, List[str], List[str], bool, str]:
    if "query_cache" not in st.session_state:
        st.session_state["query_cache"] = {}

    cache = st.session_state["query_cache"]
    cache_key = make_query_cache_key(csv_name, df, schema, instructions)

    if cache_key in cache:
        cached = cache[cache_key]
        try:
            filtered_df = df.loc[cached["indices"]].copy()
        except Exception:
            filtered_df, filters, warnings = apply_filters(df, schema, instructions)
            cache[cache_key] = {
                "indices": filtered_df.index.tolist(),
                "filters": filters,
                "warnings": warnings,
            }
            return filtered_df, filters, warnings, False, cache_key

        return filtered_df, cached["filters"], cached["warnings"], True, cache_key

    filtered_df, filters, warnings = apply_filters(df, schema, instructions)

    cache[cache_key] = {
        "indices": filtered_df.index.tolist(),
        "filters": filters,
        "warnings": warnings,
    }

    return filtered_df, filters, warnings, False, cache_key


def make_diameter_table(df: pd.DataFrame, schema: Dict[str, Any]) -> Tuple[Optional[pd.DataFrame], str]:
    roles = schema["roles"]
    bin_col = roles.get("diameter_bin")
    numeric_col = roles.get("diameter_numeric")

    if bin_col:
        table = df[bin_col].astype(str).value_counts().reset_index()
        table.columns = ["Diameter bin", "Count"]

        if len(table) > 0:
            summary = f"The most common diameter bin is '{table.iloc[0]['Diameter bin']}', with {int(table.iloc[0]['Count']):,} records."
        else:
            summary = "No diameter-bin values were found."

        return table, summary

    if numeric_col:
        values = pd.to_numeric(df[numeric_col], errors="coerce").dropna()

        if len(values) == 0:
            return None, "The detected diameter column has no numeric values."

        bins = [-0.001, 5, 10, 20, 30, 40, 50, float("inf")]
        labels = ["0 to 5", "5 to 10", "10 to 20", "20 to 30", "30 to 40", "40 to 50", "more than 50"]
        cut = pd.cut(values, bins=bins, labels=labels, include_lowest=True)

        table = cut.value_counts().sort_index().reset_index()
        table.columns = ["Diameter/DBH range", "Count"]
        table["Diameter/DBH range"] = table["Diameter/DBH range"].astype(str)

        summary = (
            f"This CSV does not have a pre-binned diameter field, so I binned the numeric {numeric_col} field. "
            f"The median {numeric_col} value is {values.median():.1f}, and the maximum is {values.max():.1f}."
        )

        return table, summary

    return None, "I could not find a diameter/DBH column in this CSV."


def describe_top_values(df: pd.DataFrame, col: Optional[str], label: str, limit: int = 5) -> Tuple[Optional[str], Optional[pd.DataFrame]]:
    if not col or col not in df.columns:
        return None, None

    values = df[col].dropna().astype(str).str.strip()
    values = values[values != ""]

    if len(values) == 0:
        return None, None

    table = values.value_counts().head(limit).reset_index()
    table.columns = [label, "Count"]

    parts = [
        f"{row[label]} ({int(row['Count']):,})"
        for _, row in table.iterrows()
    ]

    return ", ".join(parts), table


def humanize_text(value: Any) -> str:
    text = safe_string(value)

    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def describe_query_subject(instructions: Dict[str, Any], filters: List[str]) -> str:
    species_text = humanize_text(instructions.get("species_text"))
    native_text = humanize_text(instructions.get("native_text"))

    if instructions.get("danger_value") is not None:
        return "hazardous trees"

    if species_text:
        return f"{species_text} trees"

    if native_text:
        native_label = native_text.replace("_", " ").replace("-", " ")
        if native_label == "naturally occurring":
            return "naturally occurring trees"
        return f"{native_label} trees"

    diameter_parts = []
    if instructions.get("min_diameter") is not None:
        diameter_parts.append(f"at least {instructions['min_diameter']} DBH")
    if instructions.get("max_diameter") is not None:
        diameter_parts.append(f"at most {instructions['max_diameter']} DBH")

    if diameter_parts:
        return "trees with " + " and ".join(diameter_parts)

    meaningful_filters = [item for item in filters if item != "No filters applied"]

    if not meaningful_filters:
        return "tree records in the full dataset"

    return "trees matching " + "; ".join(meaningful_filters)


def build_result(
    df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    question: str,
    instructions: Dict[str, Any],
    schema: Dict[str, Any],
    filters: List[str],
    warnings: List[str],
    coord_rows: int,
    map_status: Dict[str, Any],
    cache_hit: bool,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    roles = schema["roles"]
    total_rows = len(df)
    matching_rows = len(filtered_df)
    percent = round((matching_rows / total_rows) * 100, 1) if total_rows else 0.0
    intent = instructions.get("intent", "summary")

    table_df: Optional[pd.DataFrame] = None
    preview_df: Optional[pd.DataFrame] = None
    result_available = True

    display_count_label = "Matching records"
    display_count_value = int(matching_rows)

    if intent == "species_list" and roles.get("species_common"):
        species_col = roles["species_common"]

        table_df = (
            filtered_df[species_col]
            .dropna()
            .astype(str)
            .value_counts()
            .reset_index()
        )
        table_df.columns = ["Species", "Count"]

        unique_species = int(len(table_df))
        display_count_label = "Unique species"
        display_count_value = unique_species

        if unique_species > 0:
            top_rows = table_df.head(5)
            top_parts = [
                f"{row['Species']} ({int(row['Count']):,})"
                for _, row in top_rows.iterrows()
            ]

            verified_summary = (
                f"The dataset contains {unique_species:,} unique tree species/common names "
                f"across {matching_rows:,} tree records. "
                f"The most common species are {', '.join(top_parts)}. "
                "The full species list is shown below."
            )
        else:
            verified_summary = "I could not find any species/common-name values in this dataset."

    elif warnings and any("native-status" in w for w in warnings) and intent == "native_summary":
        result_available = False
        table_df = pd.DataFrame([
            {"Item": "Native-status column", "Result": "Not found in this CSV"},
            {"Item": "Rows in dataset", "Result": f"{total_rows:,}"},
        ])
        verified_summary = "This CSV does not contain a recognized native-status column, so I cannot determine which records are native trees from this file."

    elif intent == "top_species" and roles.get("species_common"):
        species_col = roles["species_common"]
        table_df = filtered_df[species_col].astype(str).value_counts().head(10).reset_index()
        table_df.columns = ["Species", "Count"]

        if len(table_df) > 0:
            verified_summary = (
                f"The most common species in the matching records is {table_df.iloc[0]['Species']}, "
                f"with {int(table_df.iloc[0]['Count']):,} records. "
                f"This summary is based on {matching_rows:,} matching records out of {total_rows:,} total records."
            )
        else:
            verified_summary = "No matching species records were found."

    elif intent == "native_summary" and roles.get("native_status"):
        native_col = roles["native_status"]
        table_df = filtered_df[native_col].astype(str).value_counts().reset_index()
        table_df.columns = ["Native status", "Count"]
        status_parts = [
            f"{row['Native status']} ({int(row['Count']):,})"
            for _, row in table_df.head(5).iterrows()
        ]
        verified_summary = (
            f"The native-status field is {native_col}. For {describe_query_subject(instructions, filters)}, "
            f"the breakdown is {', '.join(status_parts)} across {matching_rows:,} records."
        )

    elif intent == "diameter_summary":
        table_df, diameter_summary = make_diameter_table(filtered_df, schema)

        if table_df is None:
            result_available = False
            table_df = pd.DataFrame([{"Item": "Diameter/DBH column", "Result": "Not found or not usable"}])

        verified_summary = diameter_summary + f" The summary is based on {matching_rows:,} matching records out of {total_rows:,} total records."

    elif intent == "danger_summary" and roles.get("danger_flag"):
        danger_col = roles["danger_flag"]
        table_df = filtered_df[danger_col].astype(str).value_counts().reset_index()
        table_df.columns = ["Danger flag", "Count"]
        preview_df = filtered_df.head(int(instructions.get("limit", 1000))) if matching_rows > 0 else None
        verified_summary = (
            f"There are {matching_rows:,} trees marked hazardous/danger in the {danger_col} field, "
            f"which is {percent}% of the full dataset. The matching records are available below."
        )

    elif intent == "summary":
        summary_rows = [
            {"Metric": "Rows", "Value": f"{total_rows:,}"},
            {"Metric": "Columns", "Value": f"{len(df.columns):,}"},
        ]
        summary_parts = [
            f"This dataset contains {total_rows:,} tree records across {len(df.columns):,} columns."
        ]

        species_text, species_table = describe_top_values(filtered_df, roles.get("species_common"), "Species")
        if species_table is not None:
            unique_species = int(filtered_df[roles["species_common"]].dropna().astype(str).str.strip().nunique())
            summary_rows.append({"Metric": "Unique species/common names", "Value": f"{unique_species:,}"})
            summary_rows.append({"Metric": "Most common species", "Value": species_text or "Not available"})
            summary_parts.append(f"It includes {unique_species:,} unique species/common names; the most common are {species_text}.")

        scientific_text, _ = describe_top_values(filtered_df, roles.get("scientific_name"), "Scientific name", limit=3)
        if scientific_text:
            summary_rows.append({"Metric": "Top scientific names", "Value": scientific_text})

        diameter_col = roles.get("diameter_numeric")
        if diameter_col and diameter_col in filtered_df.columns:
            diameter_values = pd.to_numeric(filtered_df[diameter_col], errors="coerce").dropna()
            if len(diameter_values) > 0:
                summary_rows.append({"Metric": f"Median {diameter_col}", "Value": f"{diameter_values.median():.1f}"})
                summary_rows.append({"Metric": f"Maximum {diameter_col}", "Value": f"{diameter_values.max():.1f}"})
                summary_parts.append(f"The median {diameter_col} is {diameter_values.median():.1f}, with a maximum of {diameter_values.max():.1f}.")

        native_text, _ = describe_top_values(filtered_df, roles.get("native_status"), "Native status", limit=4)
        if native_text:
            summary_rows.append({"Metric": "Native status values", "Value": native_text})

        danger_col = roles.get("danger_flag")
        if danger_col and danger_col in filtered_df.columns:
            danger_values = pd.to_numeric(filtered_df[danger_col], errors="coerce")
            danger_count = int((danger_values == 1).sum())
            summary_rows.append({"Metric": "Marked hazardous/danger", "Value": f"{danger_count:,}"})
            if danger_count > 0:
                summary_parts.append(f"{danger_count:,} records are marked as hazardous/danger.")

        if coord_rows > 0:
            summary_rows.append({"Metric": "Rows with usable coordinates", "Value": f"{coord_rows:,}"})
            summary_parts.append(f"{coord_rows:,} records have usable coordinates for mapping.")
        else:
            summary_rows.append({"Metric": "Rows with usable coordinates", "Value": "0"})
            summary_parts.append("No usable coordinate fields were detected for mapping in this dataset.")

        table_df = pd.DataFrame(summary_rows)
        verified_summary = " ".join(summary_parts)

    else:
        table_df = pd.DataFrame([
            {"Metric": "Matching records", "Value": f"{matching_rows:,}"},
            {"Metric": "Total records in dataset", "Value": f"{total_rows:,}"},
            {"Metric": "Percent of dataset", "Value": f"{percent}%"},
            {"Metric": "Filters used", "Value": "; ".join(filters)},
        ])

        preview_df = filtered_df.head(int(instructions.get("limit", 1000))) if matching_rows > 0 else None

        if intent == "count":
            verified_summary = (
                f"There are {matching_rows:,} {describe_query_subject(instructions, filters)}, "
                f"which is {percent}% of the full dataset."
            )
        elif intent == "filter":
            verified_summary = (
                f"I found {matching_rows:,} {describe_query_subject(instructions, filters)}, "
                f"which is {percent}% of the full dataset. A preview of the matching rows is available below."
            )
        else:
            verified_summary = (
                f"I found {matching_rows:,} {describe_query_subject(instructions, filters)}, "
                f"which is {percent}% of the full dataset."
            )

    if warnings:
        verified_summary += " " + " ".join(warnings)

    map_requested = bool(instructions.get("make_map"))
    map_available = bool(map_status.get("map_available"))
    map_status_message = map_status.get("message")

    if map_requested and not map_available:
        if map_status_message:
            verified_summary += " A map was requested, but it was not created: " + str(map_status_message)
        else:
            verified_summary += " A map was requested, but it was not created because no usable coordinates were found."

    payload = {
        "question": question,
        "intent": intent,
        "result_available": result_available,
        "matching_record_count": int(matching_rows),
        "total_dataset_rows": int(total_rows),
        "percent_of_dataset": percent,
        "answer_subject": describe_query_subject(instructions, filters),
        "display_count_label": display_count_label,
        "display_count_value": display_count_value,
        "filters_used": filters,
        "warnings": warnings,
        "verified_summary": verified_summary,
        "important_table": table_df.to_dict(orient="records") if table_df is not None else [],
        "map_requested": map_requested,
        "map_available": map_available,
        "map_status_message": map_status_message,
        "coordinate_rows_in_result": int(map_status.get("coordinate_rows", 0)),
        "coordinate_rows_in_dataset": int(coord_rows),
        "coordinate_kind": schema.get("coordinate_kind"),
        "cache_hit": cache_hit,
    }

    return table_df, preview_df, payload


# -----------------------------
# AI responses
# -----------------------------

def explain_general_chat(prompt: str, model_name: str, use_model_explanation: bool) -> str:
    q = prompt.lower().strip()

    if any(word in q for word in ["hi", "hello", "hey"]) and len(q.split()) <= 4:
        return f"Hi. What would you like to explore in {APP_NAME}?"

    if "how is your day" in q or "how are you" in q:
        return "I’m doing well. I’m ready to help with the tree dataset whenever you are."

    if any(phrase in q for phrase in ["who are you", "what are you", "what is this", "what app is this"]):
        return (
            f"I'm the chat assistant for {APP_NAME}, {APP_DESCRIPTION} "
            "I can answer casual questions too, but my main job is helping you work with forestry and tree-related data."
        )

    if any(phrase in q for phrase in ["what can you do", "what do you do", "help me", "everything i can do", "tell me everything"]):
        return (
            "You can ask me to summarize datasets, count trees, list species, filter records by species or traits, "
            "preview matching rows, and map tree or forestry data when usable coordinates are available."
        )

    if "favorite pokemon" in q or "favourite pokemon" in q:
        return "I do not have personal favorites, but Pikachu is probably the classic answer."

    fallback = "I can answer normally too, but I’m mainly set up to help you explore, summarize, filter, and map this tree dataset."

    fallback = f"I can answer normally too, but I am mainly set up to help you explore, summarize, filter, and map forestry and tree datasets in {APP_NAME}."

    if not use_model_explanation:
        return fallback

    system_prompt = f"""
You are a helpful assistant inside {APP_NAME}, {APP_DESCRIPTION}
The user is casually chatting, not asking for data analysis.
Answer naturally in 1 to 2 short sentences.
Do not mention querying the CSV unless the user asks about the dataset.
Do not describe the app as a programming, binary-tree, heap, or data-structures tool.
Do not pretend to have personal experiences.

User message:
{prompt}
"""

    text = safe_ollama_chat(
        model_name,
        system_prompt,
        options={"temperature": 0.4, "num_predict": 140},
    )

    return text if text else fallback


def explain_result(
    payload: Dict[str, Any],
    model_name: str,
    use_model_explanation: bool,
    selected_projected_crs: Optional[str],
) -> str:
    if payload.get("intent") == "species_list":
        return payload["verified_summary"]

    map_requested = bool(payload.get("map_requested"))
    map_available = bool(payload.get("map_available"))

    if map_requested and not map_available:
        return payload["verified_summary"]

    if not use_model_explanation:
        if map_requested:
            return "Here's your map. " + payload["verified_summary"]
        return payload["verified_summary"]

    if not use_model_explanation:
        if payload.get("map_requested"):
            return "Here’s your map. " + payload["verified_summary"]
        return payload["verified_summary"]

    user_facing_payload = {
        "question": payload["question"],
        "intent": payload["intent"],
        "result_available": payload["result_available"],
        "matching_record_count": payload["matching_record_count"],
        "total_dataset_rows": payload["total_dataset_rows"],
        "percent_of_dataset": payload["percent_of_dataset"],
        "answer_subject": payload.get("answer_subject"),
        "display_count_label": payload.get("display_count_label"),
        "display_count_value": payload.get("display_count_value"),
        "filters_used": payload["filters_used"],
        "warnings": payload["warnings"],
        "verified_summary": payload["verified_summary"],
        "important_table": payload["important_table"][:10],
    }

    if payload.get("map_requested"):
        if selected_projected_crs:
            user_facing_payload["map_note"] = (
                f"A map was requested. Coordinate rows available: {payload['coordinate_rows_in_dataset']}. "
                f"The app transformed the coordinate values using {selected_projected_crs} so they can be displayed on the map."
            )
        else:
            user_facing_payload["map_note"] = (
                f"A map was requested. Coordinate rows available: {payload['coordinate_rows_in_dataset']}. "
                "A coordinate system must be selected before these coordinates can be mapped."
            )

    if map_requested and map_available:
        if payload.get("coordinate_kind") == "projected_crs_required" and selected_projected_crs:
            user_facing_payload["map_note"] = (
                f"A map was created for {payload.get('coordinate_rows_in_result', 0)} matching rows. "
                f"The app transformed the coordinate values using {selected_projected_crs} so they can be displayed on the map."
            )
        else:
            user_facing_payload["map_note"] = (
                f"A map was created for {payload.get('coordinate_rows_in_result', 0)} matching rows with usable coordinates."
            )

    if payload.get("map_requested"):
        instruction = """
Write a friendly, direct answer that starts with "Here’s your map."
Then mention the key count and percent if available.
Do not repeat the user's question.
"""
    else:
        instruction = """
Write a friendly, direct answer.
Answer the user's question first, then briefly explain what the matched records mean.
Mention the key count and percent if available.
Do not repeat the user's question.
"""

    prompt = f"""
Use only the verified facts below. Write 2 to 4 plain-English sentences.
Do not invent facts. Do not recalculate numbers. Do not mention JSON or internal fields.
If a map note is present, explain it in simple terms.
If matching records are present, describe them as the answer to the question rather than merely saying records matched.
If answer_subject is present, use that human phrase instead of internal filter wording.
{instruction}

Verified facts:
{json.dumps(user_facing_payload, indent=2)}
"""

    text = safe_ollama_chat(
        model_name,
        prompt,
        options={"temperature": 0.2, "num_predict": 220},
    )

    if not text:
        if payload.get("map_requested"):
            return "Here’s your map. " + payload["verified_summary"]
        return payload["verified_summary"]

    lowered = text.lower()

    forbidden = [
        "over 99%",
        "almost all",
        "forest surveyed",
        "map_requested",
        "json",
        "coordinate information is not available",
        "coordinates are not available",
        "coordinate data is not available",
    ]

    if not payload.get("map_requested"):
        forbidden.extend(["coordinate data", "coordinate rows", "missing coordinate"])

    if any(term in lowered for term in forbidden):
        if payload.get("map_requested"):
            return "Here’s your map. " + payload["verified_summary"]
        return payload["verified_summary"]

    if payload.get("map_requested") and "map" not in lowered:
        return "Here’s your map. " + text

    return text


# -----------------------------
# Map creation
# -----------------------------

def add_map_tile_layers(m: folium.Map, selected_map_style: str) -> None:
    if selected_map_style not in MAP_TILE_OPTIONS:
        selected_map_style = "Standard"

    for style_name, config in MAP_TILE_OPTIONS.items():
        tile_kwargs = {
            "tiles": config["tiles"],
            "name": style_name,
            "show": style_name == selected_map_style,
            "control": True,
        }

        if config.get("attr"):
            tile_kwargs["attr"] = config["attr"]

        folium.TileLayer(**tile_kwargs).add_to(m)

    folium.LayerControl(position="topright", collapsed=False).add_to(m)


def add_polygon_draw_control(m: folium.Map) -> None:
    Draw(
        export=False,
        draw_options={
            "polyline": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
            "polygon": True,
            "rectangle": True,
        },
        edit_options={
            "edit": True,
            "remove": True,
        },
    ).add_to(m)


def point_in_polygon(lat: float, lon: float, ring: List[List[float]]) -> bool:
    x = lon
    y = lat
    inside = False
    j = len(ring) - 1

    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]

        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )

        if intersects:
            inside = not inside

        j = i

    return inside


def polygon_rings_from_drawings(drawings: Any) -> List[List[List[float]]]:
    rings: List[List[List[float]]] = []

    for feature in drawings or []:
        geometry = feature.get("geometry", {}) if isinstance(feature, dict) else {}
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])

        if geometry_type == "Polygon" and coordinates:
            rings.append(coordinates[0])
        elif geometry_type == "MultiPolygon":
            for polygon in coordinates:
                if polygon:
                    rings.append(polygon[0])

    return rings


def select_rows_inside_drawings(map_df: pd.DataFrame, drawings: Any) -> Optional[pd.DataFrame]:
    rings = polygon_rings_from_drawings(drawings)

    if not rings:
        return None

    selected_mask = pd.Series(False, index=map_df.index)

    for ring in rings:
        if len(ring) < 3:
            continue

        selected_mask = selected_mask | map_df.apply(
            lambda row: point_in_polygon(float(row["__map_lat"]), float(row["__map_lon"]), ring),
            axis=1,
        )

    return map_df[selected_mask].copy()


def prepare_map_dataframe(
    df: pd.DataFrame,
    schema: Dict[str, Any],
    selected_projected_crs: Optional[str],
    sample_limit: Optional[int] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    roles = schema["roles"]
    lat_col = roles.get("latitude")
    lon_col = roles.get("longitude")

    if not lat_col or not lon_col:
        return None, "No coordinate columns were detected."

    map_df = df.dropna(subset=[lat_col, lon_col]).copy()

    if len(map_df) == 0:
        return None, "No rows have usable coordinate values."

    lat_values, lon_values, error = get_map_coordinates(
        map_df,
        lat_col,
        lon_col,
        schema.get("coordinate_kind", "none"),
        selected_projected_crs,
    )

    if error:
        return None, error

    if lat_values is None or lon_values is None:
        return None, "Could not prepare coordinates for mapping."

    map_df = map_df.copy()
    map_df["__map_lat"] = lat_values
    map_df["__map_lon"] = lon_values
    map_df = map_df.dropna(subset=["__map_lat", "__map_lon"])
    map_df = map_df[
        map_df["__map_lat"].between(-90, 90)
        & map_df["__map_lon"].between(-180, 180)
    ]

    if len(map_df) == 0:
        return None, "No valid coordinates remained after conversion."

    if sample_limit is not None and len(map_df) > sample_limit:
        map_df = map_df.sample(sample_limit, random_state=42)

    return map_df, None


def make_map(
    df: pd.DataFrame,
    schema: Dict[str, Any],
    popup_cols: List[Optional[str]],
    selected_projected_crs: Optional[str],
    selected_map_style: str,
) -> Tuple[Optional[folium.Map], Optional[str]]:
    map_df, error = prepare_map_dataframe(
        df,
        schema,
        selected_projected_crs,
        sample_limit=1000,
    )

    if error:
        return None, error

    if map_df is None:
        return None, "Could not prepare coordinates for mapping."

    m = folium.Map(
        location=[map_df["__map_lat"].mean(), map_df["__map_lon"].mean()],
        zoom_start=16,
        tiles=None,
        control_scale=True,
    )
    add_map_tile_layers(m, selected_map_style)
    add_polygon_draw_control(m)

    for _, row in map_df.iterrows():
        popup_text = []

        for col in popup_cols:
            if col and col in row:
                popup_text.append(f"{col}: {row[col]}")

        folium.CircleMarker(
            location=[row["__map_lat"], row["__map_lon"]],
            radius=3,
            popup="<br>".join(popup_text),
            fill=True,
        ).add_to(m)

    return m, None


# -----------------------------
# Chat helpers
# -----------------------------

def init_chat_state(csv_name: str) -> Tuple[str, Dict[str, Any], str]:
    chats_key = f"chats::{csv_name}"
    active_key = f"active_chat::{csv_name}"

    if chats_key not in st.session_state:
        st.session_state[chats_key] = load_saved_chats(csv_name)
        if not st.session_state[chats_key]:
            first_id = str(uuid4())
            st.session_state[chats_key] = {
                first_id: {
                    "title": "New chat",
                    "messages": [],
                }
            }
            save_chat(csv_name, first_id, st.session_state[chats_key][first_id])
        else:
            first_id = next(iter(st.session_state[chats_key]))
        st.session_state[active_key] = first_id

    if active_key not in st.session_state or st.session_state[active_key] not in st.session_state[chats_key]:
        st.session_state[active_key] = next(iter(st.session_state[chats_key]))

    return chats_key, st.session_state[chats_key], st.session_state[active_key]


def create_new_chat(csv_name: str) -> None:
    chats_key = f"chats::{csv_name}"
    active_key = f"active_chat::{csv_name}"

    new_id = str(uuid4())
    count = len(st.session_state.get(chats_key, {})) + 1

    st.session_state[chats_key][new_id] = {
        "title": f"Chat {count}",
        "messages": [],
    }
    st.session_state[active_key] = new_id
    save_chat(csv_name, new_id, st.session_state[chats_key][new_id])


def render_suggested_question_buttons(suggestions: List[str], key_prefix: str) -> Optional[str]:
    if not suggestions:
        return None

    visible_suggestions = suggestions[:4]
    more_suggestions = suggestions[4:8]
    show_more_key = f"{key_prefix}::show_more"

    if show_more_key not in st.session_state:
        st.session_state[show_more_key] = False

    if st.session_state[show_more_key]:
        visible_suggestions = visible_suggestions + more_suggestions

    st.caption("Suggested questions")
    selected_question = None
    columns = st.columns(2)

    for index, suggestion in enumerate(visible_suggestions):
        with columns[index % 2]:
            if st.button(suggestion, key=f"{key_prefix}::{index}", width="stretch"):
                selected_question = suggestion

    if more_suggestions:
        toggle_label = "Show fewer questions ^" if st.session_state[show_more_key] else "More suggested questions v"
        if st.button(toggle_label, key=f"{key_prefix}::toggle_more", width="stretch"):
            st.session_state[show_more_key] = not st.session_state[show_more_key]
            st.rerun()

    return selected_question


def render_assistant_results(
    results: List[Dict[str, Any]],
    csv_name: str,
    active_chat_id: str,
    message_index: int,
    selected_projected_crs: Optional[str],
    selected_map_style: str,
) -> None:
    for result_index, result in enumerate(results):
        if result_index > 0:
            st.divider()

        if result.get("type") == "general_chat":
            st.write(result["content"])
            continue

        instructions = result["instructions"]
        filtered_df = result["filtered_df"]
        table_df = result["table_df"]
        preview_df = result["preview_df"]
        payload = result["payload"]
        explanation = result["explanation"]
        result_roles = result["roles"]
        coordinate_kind = result.get("coordinate_kind", "none")

        extras_key = f"show-extras::{csv_name}::{active_chat_id}::{message_index}::{result_index}"
        if extras_key not in st.session_state:
            st.session_state[extras_key] = False

        answer_col, menu_col = st.columns([0.94, 0.06], vertical_alignment="center")

        with answer_col:
            st.write(explanation)

        with menu_col:
            menu_key = f"extras-menu::{csv_name}::{active_chat_id}::{message_index}::{result_index}"
            checkbox_key = f"extras-checkbox::{csv_name}::{active_chat_id}::{message_index}::{result_index}"

            if hasattr(st, "popover"):
                with st.popover("...", help="Response options", width="stretch", key=menu_key):
                    st.session_state[extras_key] = st.checkbox(
                        "Show data result and developer details",
                        value=st.session_state[extras_key],
                        key=checkbox_key,
                    )
            elif st.button("...", key=menu_key, help="Show or hide data and developer details"):
                st.session_state[extras_key] = not st.session_state[extras_key]
                st.rerun()

        show_extras = st.session_state[extras_key]

        if payload.get("intent") == "species_list" and table_df is not None:
            st.caption(f"Showing all {len(table_df):,} species/common names. Scroll the table or filter it below.")
            species_filter = st.text_input(
                "Filter species list",
                key=f"species-filter::{csv_name}::{active_chat_id}::{message_index}::{result_index}",
                placeholder="Type part of a species name...",
            )
            visible_species_df = table_df

            if species_filter:
                visible_species_df = table_df[
                    table_df["Species"].astype(str).str.contains(species_filter, case=False, na=False)
                ]
                st.caption(f"{len(visible_species_df):,} species match this filter.")

            st.dataframe(
                visible_species_df,
                width="stretch",
                height=650,
                hide_index=True,
            )
            st.download_button(
                "Download species list",
                data=table_df.to_csv(index=False).encode("utf-8"),
                file_name=f"{csv_name}_species_list.csv",
                mime="text/csv",
                key=f"species-download::{csv_name}::{active_chat_id}::{message_index}::{result_index}",
            )

        if instructions.get("make_map") or instructions.get("intent") == "map":
            popup_cols = [
                result_roles.get("species_common"),
                result_roles.get("scientific_name"),
                result_roles.get("diameter_numeric"),
                result_roles.get("height_numeric"),
            ]

            if not payload.get("map_available"):
                st.warning(payload.get("map_status_message") or "No usable coordinates were found.")
            else:
                map_schema = {
                    "roles": result_roles,
                    "coordinate_kind": coordinate_kind,
                }

                m, error = make_map(
                    filtered_df,
                    map_schema,
                    popup_cols,
                    selected_projected_crs,
                    selected_map_style,
                )

                if error:
                    st.warning(error)
                elif m is not None:
                    map_output = st_folium(
                        m,
                        use_container_width=True,
                        height=600,
                        key=f"map::{csv_name}::{active_chat_id}::{message_index}::{result_index}",
                        returned_objects=["all_drawings"],
                    )

                    selected_df = None
                    if map_output and map_output.get("all_drawings"):
                        full_map_df, selection_error = prepare_map_dataframe(
                            filtered_df,
                            map_schema,
                            selected_projected_crs,
                        )

                        if selection_error:
                            st.warning(selection_error)
                        elif full_map_df is not None:
                            selected_df = select_rows_inside_drawings(
                                full_map_df,
                                map_output.get("all_drawings"),
                            )

                    if selected_df is not None:
                        st.write(f"Records inside drawn area: {len(selected_df):,}")

                        species_col = result_roles.get("species_common")
                        if species_col and species_col in selected_df.columns and len(selected_df) > 0:
                            species_summary = (
                                selected_df[species_col]
                                .dropna()
                                .astype(str)
                                .value_counts()
                                .head(20)
                                .reset_index()
                            )
                            species_summary.columns = ["Species", "Count"]

                            with st.expander("Species inside drawn area", expanded=False):
                                st.dataframe(species_summary, width="stretch")

                        display_cols = [
                            col for col in [
                                result_roles.get("species_common"),
                                result_roles.get("scientific_name"),
                                result_roles.get("diameter_numeric"),
                                result_roles.get("height_numeric"),
                                result_roles.get("latitude"),
                                result_roles.get("longitude"),
                            ]
                            if col and col in selected_df.columns
                        ]

                        with st.expander("Rows inside drawn area", expanded=False):
                            if display_cols:
                                st.dataframe(selected_df[display_cols].head(1000), width="stretch")
                            else:
                                st.dataframe(selected_df.head(1000), width="stretch")

        if show_extras:
            with st.expander("Data result", expanded=False):
                if payload.get("result_available"):
                    label = payload.get("display_count_label", "Matching records")
                    value = payload.get("display_count_value", len(filtered_df))

                    st.write(f"{label}: {value:,}")

                    if payload.get("intent") == "species_list":
                        st.caption(f"Tree records checked: {len(filtered_df):,}")
                else:
                    st.write("Matching records: not applicable")

                if payload.get("cache_hit"):
                    st.caption("Reused cached query result.")

                if table_df is not None and payload.get("intent") != "species_list":
                    st.dataframe(table_df, width="stretch")

                if preview_df is not None:
                    with st.expander("Preview matching rows", expanded=False):
                        st.dataframe(preview_df, width="stretch")

            with st.expander("Developer details", expanded=False):
                st.write("Question interpretation")
                st.json(instructions)
                st.write("Detected dataset roles")
                st.json(result_roles)
                st.write(f"Cache hit: {payload.get('cache_hit', False)}")
                st.write(f"Data backend: {result.get('data_backend', 'pandas')}")
                if result.get("sql_query"):
                    st.write("Executed SQL query")
                    st.code(result["sql_query"], language="sql")
                    st.write("SQL parameters")
                    st.json(result.get("sql_parameters", []))
                    st.caption("The question interpretation above is JSON; the command above is the SQL SQLite actually executed.")
                else:
                    st.caption("No SQL command was executed for this response.")


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(page_title=APP_NAME, layout="wide")

if st.session_state.get("app_state_version") != APP_STATE_VERSION:
    for key in list(st.session_state.keys()):
        if (
            key.startswith("pending_chat::")
            or key.startswith("pending_schema_question::")
            or key.startswith("last_filter::")
            or key == "last_general_chat_error"
        ):
            del st.session_state[key]
    st.session_state["app_state_version"] = APP_STATE_VERSION

if st.session_state.get("app_theme") not in THEME_PALETTES:
    st.session_state["app_theme"] = "Forest"

apply_app_theme(st.session_state["app_theme"])

st.title(APP_NAME)
st.write("Ask questions across forestry, tree inventory, and spatial datasets. The app answers from the selected data and maps results when coordinates are usable.")

with st.sidebar.popover("Import dataset", width="stretch"):
    st.caption("Supported: CSV, GeoTIFF, TIFF, ERDAS IMG, GDAL VRT, and JPEG 2000.")
    uploaded_dataset = st.file_uploader(
        "Choose a dataset",
        type=["csv", "tif", "tiff", "img", "vrt", "jp2"],
        accept_multiple_files=False,
        help="CSV files are stored in data. Raster files are stored in rasters.",
    )
    if st.button("Add dataset", disabled=uploaded_dataset is None, width="stretch"):
        imported_path, import_error = save_uploaded_dataset(uploaded_dataset)
        if import_error:
            st.error(import_error)
        elif imported_path is not None:
            imported_kind = "CSV" if imported_path.suffix.lower() == ".csv" else "Raster"
            st.session_state["dataset_selector"] = f"{imported_path.name} ({imported_kind})"
            st.success(f"Imported `{imported_path.name}`.")
            st.rerun()

    st.caption("A VRT may reference other raster files; those referenced files must also be available to Canopy.")

dataset_options = get_dataset_options()

if not dataset_options:
    st.error("No datasets found. Put CSV files in the data folder or raster files in the data or rasters folder.")
    st.stop()

dataset_labels = [format_dataset_option(option) for option in dataset_options]
if st.session_state.get("dataset_selector") not in dataset_labels:
    st.session_state["dataset_selector"] = dataset_labels[0]
selected_dataset_label = st.sidebar.selectbox(
    "Dataset",
    dataset_labels,
    key="dataset_selector",
)
dataset_kind, dataset_path = dataset_options[dataset_labels.index(selected_dataset_label)]

st.sidebar.segmented_control(
    "Theme",
    list(THEME_PALETTES),
    selection_mode="single",
    key="app_theme",
    width="stretch",
    help="Choose the interface palette used throughout the application.",
)

models = get_installed_ollama_models()
question_preferred_order = ["qwen2.5:3b", "qwen3.5:9b", "qwen3:14b", "gemma3:12b", "gpt-oss:20b"]
schema_preferred_order = ["qwen3.5:9b", "qwen3:14b", "gemma3:12b", "gpt-oss:20b", "qwen2.5:3b"]

question_default_model = models[0] if models else "qwen2.5:3b"
for preferred in question_preferred_order:
    if preferred in models:
        question_default_model = preferred
        break

schema_default_model = models[0] if models else "qwen2.5:3b"
for preferred in schema_preferred_order:
    if preferred in models:
        schema_default_model = preferred
        break

if "question_model" not in st.session_state or st.session_state["question_model"] not in models:
    st.session_state["question_model"] = question_default_model

if "schema_model" not in st.session_state or st.session_state["schema_model"] not in models:
    st.session_state["schema_model"] = schema_default_model

if "use_model_parse" not in st.session_state:
    st.session_state["use_model_parse"] = True

if "use_model_explanation" not in st.session_state:
    st.session_state["use_model_explanation"] = True

if "use_sql_backend" not in st.session_state:
    st.session_state["use_sql_backend"] = True

model_name = st.session_state["question_model"]
schema_model_name = st.session_state["schema_model"]
use_model_parse = st.session_state["use_model_parse"]
use_model_explanation = st.session_state["use_model_explanation"]
use_sql_backend = st.session_state["use_sql_backend"]

if dataset_kind == "fvs":
    from fvs_drive_bridge import render_fvs_drive_mode

    render_fvs_drive_mode(globals(), dataset_path)
    st.stop()

if dataset_kind == "raster":
    raster_key = f"raster::{dataset_path.name}"
    chats_key, chats, active_chat_id = init_chat_state(raster_key)

    if st.sidebar.button("New chat", width="stretch"):
        create_new_chat(raster_key)
        st.rerun()

    if st.sidebar.button("Clear current chat", width="stretch"):
        st.session_state[chats_key][active_chat_id]["messages"] = []
        st.session_state[chats_key][active_chat_id]["title"] = "New chat"
        save_chat(raster_key, active_chat_id, st.session_state[chats_key][active_chat_id])
        st.rerun()

    chat_ids = list(st.session_state[chats_key].keys())
    active_index = chat_ids.index(st.session_state[f"active_chat::{raster_key}"])
    chat_labels = [st.session_state[chats_key][cid]["title"] for cid in chat_ids]

    selected_chat_label = st.sidebar.selectbox(
        "Chat history",
        chat_labels,
        index=active_index,
    )
    selected_chat_id = chat_ids[chat_labels.index(selected_chat_label)]

    if selected_chat_id != st.session_state[f"active_chat::{raster_key}"]:
        st.session_state[f"active_chat::{raster_key}"] = selected_chat_id
        st.rerun()

    active_chat_id = st.session_state[f"active_chat::{raster_key}"]
    messages = st.session_state[chats_key][active_chat_id]["messages"]
    suggested_prompt_key = f"suggested_prompt::{raster_key}::{active_chat_id}"

    with st.sidebar.expander("Advanced options", expanded=False):
        with st.form("raster_settings_form"):
            question_model_choice = st.selectbox(
                "Question model",
                models,
                index=models.index(st.session_state["question_model"]) if st.session_state["question_model"] in models else 0,
            )
            explanation_choice = st.checkbox(
                "Use model for raster answers",
                value=st.session_state["use_model_explanation"],
            )
            settings_submitted = st.form_submit_button("Apply settings")

        if settings_submitted:
            st.session_state["question_model"] = question_model_choice
            st.session_state["use_model_explanation"] = explanation_choice
            st.rerun()

        st.caption(f"Question model: `{st.session_state['question_model']}`")
        if st.session_state.get("ollama_runtime"):
            st.caption(f"Model runtime: `{st.session_state['ollama_runtime']}`")
        if st.session_state.get("last_ollama_error"):
            st.warning("The local model is unavailable; Canopy is using a fallback answer.")
        st.caption("Data backend: raster metadata")

    raster_layer = get_raster_layer_for_path(dataset_path)
    if raster_layer.get("rasterio_available"):
        raster_layer["data_summary"] = read_raster_data_summary(
            str(dataset_path.resolve()),
            dataset_path.stat().st_mtime,
            get_raster_companion_signature(dataset_path),
        )

    st.subheader("Raster overview")
    if raster_layer.get("rasterio_available"):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Driver", raster_layer.get("driver", "Unknown"))
        c2.metric("Bands", raster_layer.get("bands", "Unknown"))
        c3.metric("Width", f"{raster_layer.get('width', 0):,}")
        c4.metric("Height", f"{raster_layer.get('height', 0):,}")
        st.info(summarize_raster_layer(raster_layer))
    else:
        st.warning(summarize_raster_layer(raster_layer))

    raster_table = pd.DataFrame([{
        "Name": raster_layer.get("name"),
        "Folder": raster_layer.get("folder"),
        "Size MB": raster_layer.get("size_mb"),
        "Driver": raster_layer.get("driver"),
        "CRS": raster_layer.get("crs"),
        "Width": raster_layer.get("width"),
        "Height": raster_layer.get("height"),
        "Bands": raster_layer.get("bands"),
        "Bounds": raster_layer.get("bounds"),
        "Geographic bounds": raster_layer.get("bounds_wgs84"),
    }])
    st.dataframe(raster_table, width="stretch", hide_index=True)

    data_summary = raster_layer.get("data_summary", {})
    if data_summary.get("valid_pixels"):
        product_metadata = data_summary.get("product_metadata", {})
        value_label = "TM_ID" if product_metadata.get("band_role") == "TM_ID" else "value"
        st.write("Raster value summary")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Valid pixels", f"{data_summary['valid_pixels']:,}")
        s2.metric("Distinct values", f"{data_summary['unique_values']:,}")
        s3.metric(f"Minimum {value_label}", f"{data_summary['minimum']:,.0f}")
        s4.metric(f"Maximum {value_label}", f"{data_summary['maximum']:,.0f}")
        with st.expander("Most common mapped plot profiles", expanded=False):
            st.dataframe(pd.DataFrame(data_summary["top_values"]), width="stretch", hide_index=True)
            if data_summary.get("attribute_rows"):
                st.caption(
                    "Each pixel value is a TreeMap TM_ID. The accompanying raster attribute table supplies the "
                    "linked forest type and structural attributes shown here."
                )
            else:
                st.caption("These are numeric codes; no accompanying attribute table was found to interpret them.")

        if data_summary.get("forest_type_summary"):
            with st.expander("Mapped forest types", expanded=False):
                st.dataframe(
                    pd.DataFrame(data_summary["forest_type_summary"]),
                    width="stretch",
                    height=360,
                    hide_index=True,
                )
                st.caption(
                    "Percentages are weighted by the number of 30 x 30 meter raster pixels assigned to each forest type."
                )

        if data_summary.get("attribute_rows"):
            with st.expander("Raster attribute table", expanded=False):
                st.caption(
                    f"{data_summary['attribute_rows']:,} modeled plot profiles from "
                    f"`{Path(data_summary['companion_files']['attribute_table']).name}`."
                )
                st.dataframe(
                    data_summary["attribute_table"],
                    width="stretch",
                    height=420,
                    hide_index=True,
                )

        if product_metadata:
            with st.expander("Raster product documentation", expanded=False):
                if product_metadata.get("title"):
                    st.write(product_metadata["title"])
                if product_metadata.get("value_definition"):
                    st.write(f"**Pixel value:** {product_metadata['value_definition']}")
                if product_metadata.get("abstract"):
                    st.write(product_metadata["abstract"])

    raster_footprint_map = make_raster_footprint_map([raster_layer])
    if raster_footprint_map is not None:
        st.write("Raster data preview")
        if data_summary.get("product_metadata", {}).get("band_role") == "TM_ID":
            st.caption(
                "The colored layer shows the spatial pattern of TM_ID values. Colors distinguish identifier values "
                "for previewing the raster; they do not represent an ordered forest measurement."
            )
        else:
            st.caption("The colored layer shows actual Band 1 pixel values using a display stretch; it is not a class legend.")
        st_folium(
            raster_footprint_map,
            use_container_width=True,
            height=500,
            key=f"selected-raster-footprint::{dataset_path.name}",
        )

    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    suggested_prompt = st.session_state.pop(suggested_prompt_key, None)
    prompt = st.chat_input("Ask about this raster dataset...")
    active_prompt = suggested_prompt or prompt

    if active_prompt:
        cleaned_prompt = normalize_prompt(active_prompt)
        messages.append({
            "role": "user",
            "content": cleaned_prompt,
        })

        current_title = st.session_state[chats_key][active_chat_id]["title"]
        if current_title.startswith("New chat") or current_title.startswith("Chat "):
            title = cleaned_prompt
            if len(title) > 40:
                title = title[:37] + "..."
            st.session_state[chats_key][active_chat_id]["title"] = title

        with st.chat_message("user"):
            st.write(cleaned_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = answer_raster_question(
                    cleaned_prompt,
                    raster_layer,
                    model_name,
                    use_model_explanation,
                )
            st.write(answer)

        messages.append({
            "role": "assistant",
            "content": answer,
        })
        save_chat(raster_key, active_chat_id, st.session_state[chats_key][active_chat_id])

    next_suggested_prompt = render_suggested_question_buttons(
        make_raster_suggested_questions(raster_layer),
        f"suggested::{raster_key}::{active_chat_id}",
    )

    if next_suggested_prompt:
        st.session_state[suggested_prompt_key] = next_suggested_prompt
        st.rerun()

    st.stop()

csv_choice = dataset_path
df = load_csv(csv_choice)

base_schema = infer_schema_rules_only(csv_choice.name, df)
schema_key = f"schema::{csv_choice.name}"

if schema_key not in st.session_state:
    st.session_state[schema_key] = base_schema

schema = st.session_state[schema_key]
roles = schema["roles"]

coord_rows = 0
if roles.get("latitude") and roles.get("longitude"):
    coord_rows = df[[roles["latitude"], roles["longitude"]]].dropna().shape[0]

crs_options = [
    "Unknown / do not map",
    "EPSG:32617 - WGS 84 / UTM Zone 17N",
    "EPSG:26917 - NAD83 / UTM Zone 17N",
]

crs_key = f"crs_choice::{csv_choice.name}"
if crs_key not in st.session_state:
    st.session_state[crs_key] = crs_options[1]

selected_projected_crs = None
if st.session_state[crs_key].startswith("EPSG:32617"):
    selected_projected_crs = "EPSG:32617"
elif st.session_state[crs_key].startswith("EPSG:26917"):
    selected_projected_crs = "EPSG:26917"

selected_map_style = "Standard"

chats_key, chats, active_chat_id = init_chat_state(csv_choice.name)

if st.sidebar.button("New chat", width="stretch"):
    create_new_chat(csv_choice.name)
    st.rerun()

if st.sidebar.button("Clear current chat", width="stretch"):
    st.session_state[chats_key][active_chat_id]["messages"] = []
    st.session_state[chats_key][active_chat_id]["title"] = "New chat"
    save_chat(csv_choice.name, active_chat_id, st.session_state[chats_key][active_chat_id])
    st.rerun()

chat_ids = list(st.session_state[chats_key].keys())
active_index = chat_ids.index(st.session_state[f"active_chat::{csv_choice.name}"])
chat_labels = [st.session_state[chats_key][cid]["title"] for cid in chat_ids]

selected_chat_label = st.sidebar.selectbox(
    "Chat history",
    chat_labels,
    index=active_index,
)
selected_chat_id = chat_ids[chat_labels.index(selected_chat_label)]

if selected_chat_id != st.session_state[f"active_chat::{csv_choice.name}"]:
    st.session_state[f"active_chat::{csv_choice.name}"] = selected_chat_id
    st.rerun()

active_chat_id = st.session_state[f"active_chat::{csv_choice.name}"]
messages = st.session_state[chats_key][active_chat_id]["messages"]

last_filter_key = f"last_filter::{csv_choice.name}::{active_chat_id}"
suggested_prompt_key = f"suggested_prompt::{csv_choice.name}::{active_chat_id}"

if "schema_refine_executor" not in st.session_state:
    st.session_state["schema_refine_executor"] = ThreadPoolExecutor(max_workers=1)

refine_future_key = f"schema_refine_future::{csv_choice.name}"
refine_model_key = f"schema_refine_model::{csv_choice.name}"
refine_error_key = f"schema_refine_error::{csv_choice.name}"
pending_schema_question_key = f"pending_schema_question::{csv_choice.name}"

refine_running = (
    refine_future_key in st.session_state
    and not st.session_state[refine_future_key].done()
)

if refine_future_key in st.session_state:
    future = st.session_state[refine_future_key]

    if future.done():
        try:
            refined_schema = future.result()
            st.session_state[schema_key] = refined_schema

            if refine_error_key in st.session_state:
                del st.session_state[refine_error_key]

        except Exception as exc:
            st.session_state[refine_error_key] = str(exc)

        del st.session_state[refine_future_key]

        if refine_model_key in st.session_state:
            del st.session_state[refine_model_key]

        st.rerun()

refine_running = (
    refine_future_key in st.session_state
    and not st.session_state[refine_future_key].done()
)

schema = st.session_state[schema_key]
roles = schema["roles"]
schema_method = schema.get("schema_method", "rules_only")
dataset_map_status = get_map_status(df, schema, selected_projected_crs)
coord_rows = int(dataset_map_status.get("coordinate_rows", 0))

if refine_running and st_autorefresh is not None:
    st_autorefresh(interval=2000, key=f"schema_refine_poll::{csv_choice.name}")

with st.sidebar.expander("Advanced options", expanded=False):
    st.markdown("### Question answering")

    with st.form("model_settings_form"):
        question_model_choice = st.selectbox(
            "Question/explanation model",
            models,
            index=models.index(st.session_state["question_model"]) if st.session_state["question_model"] in models else 0,
        )

        parse_choice = st.checkbox(
            "Use model for question interpretation",
            value=st.session_state["use_model_parse"],
        )

        explanation_choice = st.checkbox(
            "Use model for data explanation",
            value=st.session_state["use_model_explanation"],
        )

        sql_backend_choice = st.checkbox(
            "Use SQL backend for filtering",
            value=st.session_state["use_sql_backend"],
            help="Syncs the selected CSV into a local SQLite database and uses SQL for deterministic filtering. Turn off to use the pandas fallback.",
        )

        st.markdown("### Dataset setup")

        schema_model_choice = st.selectbox(
            "Schema refinement model",
            models,
            index=models.index(st.session_state["schema_model"]) if st.session_state["schema_model"] in models else 0,
        )

        settings_submitted = st.form_submit_button("Apply settings")

    if settings_submitted:
        st.session_state["question_model"] = question_model_choice
        st.session_state["schema_model"] = schema_model_choice
        st.session_state["use_model_parse"] = parse_choice
        st.session_state["use_model_explanation"] = explanation_choice
        st.session_state["use_sql_backend"] = sql_backend_choice
        st.rerun()

    st.caption(f"Question model: `{st.session_state['question_model']}`")
    st.caption(f"Schema model: `{st.session_state['schema_model']}`")
    if st.session_state.get("ollama_runtime"):
        st.caption(f"Model runtime: `{st.session_state['ollama_runtime']}`")
    if st.session_state.get("last_ollama_error"):
        st.warning("The local model is unavailable; Canopy is using deterministic interpretation or fallback text.")
    st.caption(f"Data backend: `{'SQLite' if st.session_state['use_sql_backend'] else 'pandas'}`")

    st.markdown("### Mapping")

    st.selectbox(
        "Coordinate system",
        crs_options,
        key=crs_key,
        help=(
            "Only needed when coordinate values are not already normal latitude/longitude. "
            "For UGA campus data, EPSG:32617 is the default."
        ),
    )

    st.markdown("### Dataset setup status")

    if refine_running:
        running_model = st.session_state.get(refine_model_key, "selected model")
        st.markdown(f"🟠 **Schema refinement running**  \nModel: `{running_model}`")

        if st_autorefresh is None:
            st.warning("Auto-refresh is not installed. Run: python -m pip install streamlit-autorefresh")

    elif refine_error_key in st.session_state:
        st.markdown("🔴 **Schema refinement failed**")
        st.caption(st.session_state[refine_error_key])

    elif str(schema_method).startswith("ai_refined"):
        st.markdown("🟢 **Dataset setup refined with AI**")

    else:
        st.markdown("🔴 **Using automatic setup**")

    if st.button("Refine dataset setup with AI", disabled=refine_running, width="stretch"):
        st.session_state[refine_model_key] = st.session_state["schema_model"]

        st.session_state[refine_future_key] = st.session_state["schema_refine_executor"].submit(
            refine_schema_job,
            df.copy(),
            csv_choice.name,
            base_schema,
            st.session_state["schema_model"],
        )

        if refine_error_key in st.session_state:
            del st.session_state[refine_error_key]

        st.rerun()

    if st.button("Reset dataset setup", disabled=refine_running, width="stretch"):
        st.session_state[schema_key] = base_schema

        if refine_error_key in st.session_state:
            del st.session_state[refine_error_key]

        st.rerun()

    with st.expander("Detected dataset roles"):
        st.write(f"Schema method: {schema.get('schema_method', 'unknown')}")
        st.json(roles)

        if schema.get("ai_schema_guess"):
            st.write("AI schema guess before validation")
            st.json(schema.get("ai_schema_guess"))

        if schema.get("rule_schema_guess"):
            st.write("Rule-based schema guess")
            st.json(schema.get("rule_schema_guess"))

    if st.button("Clear query cache", width="stretch"):
        st.session_state["query_cache"] = {}
        st.success("Query cache cleared.")

st.subheader("Dataset overview")

coordinate_label = get_coordinate_display_label(
    schema.get("coordinate_kind", "none"),
    selected_projected_crs,
)

if coord_rows > 0:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Columns", len(df.columns))
    c3.metric("Rows with coordinates", f"{coord_rows:,}")
    c4.metric("Coordinate status", coordinate_label)
else:
    c1, c2 = st.columns(2)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Columns", len(df.columns))

coordinate_note = get_coordinate_note(schema.get("coordinate_kind", "none"), selected_projected_crs)
if coordinate_note:
    st.info(coordinate_note)

with st.expander("Preview data"):
    st.dataframe(df.head(25), width="stretch")

if use_sql_backend:
    selected_sql_table = sync_dataframe_to_sqlite(csv_choice.name, df)
    with st.expander("SQLite database preview", expanded=False):
        database_size_mb = SQLITE_DB_PATH.stat().st_size / (1024 * 1024) if SQLITE_DB_PATH.exists() else 0
        st.caption(
            f"Database: `{SQLITE_DB_PATH}` | Size: {database_size_mb:,.2f} MB | "
            f"Selected table: `{selected_sql_table}`"
        )
        tables_tab, data_tab, columns_tab = st.tabs(["Tables", "Selected data", "Columns"])

        with tables_tab:
            st.dataframe(get_sqlite_database_overview(), width="stretch", hide_index=True)

        with data_tab:
            st.code(
                f"SELECT * FROM {quote_sql_identifier(selected_sql_table)} LIMIT 25",
                language="sql",
            )
            st.dataframe(
                preview_sqlite_table(selected_sql_table, 25),
                width="stretch",
                hide_index=True,
            )

        with columns_tab:
            st.dataframe(
                get_sqlite_table_columns(selected_sql_table),
                width="stretch",
                hide_index=True,
            )


def compute_results_for_query(query_text: str) -> List[Dict[str, Any]]:
    questions = split_questions(query_text)

    if not questions:
        return []

    computed_results = []

    for question in questions:
        route = classify_prompt_type(question)

        if route == "general_chat":
            computed_results.append({
                "type": "general_chat",
                "content": explain_general_chat(question, model_name, use_model_explanation),
            })
            continue

        instructions = interpret_question(question, schema, model_name, use_model_parse)

        if question_is_species_list_request(question):
            instructions["intent"] = "species_list"

        if question_is_map_request(question):
            instructions["intent"] = "map"
            instructions["make_map"] = True

        previous_filter_instructions = st.session_state.get(last_filter_key)
        instructions = merge_followup_filters(
            instructions,
            previous_filter_instructions,
            question,
        )

        if use_sql_backend:
            try:
                filtered_df, filters, warnings, sql_text, sql_params = run_filtered_query_sql(
                    csv_choice.name,
                    df,
                    schema,
                    instructions,
                )
                cache_hit = False
                query_cache_key = f"sql::{sql_text}"
                data_backend = "SQLite"
            except Exception as exc:
                filtered_df, filters, warnings, cache_hit, query_cache_key = get_or_run_filtered_query(
                    csv_choice.name,
                    df,
                    schema,
                    instructions,
                )
                warnings.append(f"SQLite query failed, so Canopy used the pandas fallback for this answer: {exc}")
                data_backend = "pandas fallback"
                sql_text = None
                sql_params = []
        else:
            filtered_df, filters, warnings, cache_hit, query_cache_key = get_or_run_filtered_query(
                csv_choice.name,
                df,
                schema,
                instructions,
            )
            data_backend = "pandas"
            sql_text = None
            sql_params = []

        if instructions.get("make_map"):
            result_map_status = get_map_status(
                filtered_df,
                schema,
                selected_projected_crs,
            )
        else:
            result_map_status = {
                "map_available": False,
                "coordinate_rows": 0,
                "message": None,
                "coordinate_kind": schema.get("coordinate_kind", "none"),
            }

        table_df, preview_df, payload = build_result(
            df=df,
            filtered_df=filtered_df,
            question=question,
            instructions=instructions,
            schema=schema,
            filters=filters,
            warnings=warnings,
            coord_rows=coord_rows,
            map_status=result_map_status,
            cache_hit=cache_hit,
        )

        explanation = explain_result(
            payload,
            model_name,
            use_model_explanation,
            selected_projected_crs,
        )

        if has_filter_values(instructions):
            st.session_state[last_filter_key] = {
                "species_text": instructions.get("species_text"),
                "native_text": instructions.get("native_text"),
                "min_diameter": instructions.get("min_diameter"),
                "max_diameter": instructions.get("max_diameter"),
                "danger_value": instructions.get("danger_value"),
                "query_cache_key": query_cache_key,
            }

        computed_results.append({
            "type": "data",
            "question": question,
            "instructions": instructions,
            "filtered_df": filtered_df,
            "table_df": table_df,
            "preview_df": preview_df,
            "payload": payload,
            "explanation": explanation,
            "roles": dict(roles),
            "coordinate_kind": schema.get("coordinate_kind", "none"),
            "query_cache_key": query_cache_key,
            "data_backend": data_backend,
            "sql_query": sql_text,
            "sql_parameters": sql_params,
        })

    return computed_results


for message_index, message in enumerate(messages):
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["content"])
        else:
            if message.get("content"):
                st.write(message["content"])

            if message.get("results"):
                render_assistant_results(
                    message["results"],
                    csv_choice.name,
                    active_chat_id,
                    message_index,
                    selected_projected_crs,
                    selected_map_style,
                )

if not refine_running and pending_schema_question_key in st.session_state:
    queued_question = st.session_state[pending_schema_question_key]
    del st.session_state[pending_schema_question_key]

    with st.chat_message("assistant"):
        with st.spinner("Dataset setup finished. Answering your queued question..."):
            results = compute_results_for_query(queued_question)
            render_assistant_results(
                results,
                csv_choice.name,
                active_chat_id,
                len(messages),
                selected_projected_crs,
                selected_map_style,
            )

    messages.append({
        "role": "assistant",
        "results": results,
    })
    save_chat(csv_choice.name, active_chat_id, st.session_state[chats_key][active_chat_id])

suggested_prompt = st.session_state.pop(suggested_prompt_key, None)
prompt = st.chat_input("Ask about your forestry or spatial data...")

active_prompt = suggested_prompt or prompt

if active_prompt:
    cleaned_prompt = normalize_prompt(active_prompt)

    messages.append({
        "role": "user",
        "content": cleaned_prompt,
    })

    current_title = st.session_state[chats_key][active_chat_id]["title"]
    if current_title.startswith("New chat") or current_title.startswith("Chat "):
        title = cleaned_prompt
        if len(title) > 40:
            title = title[:37] + "..."
        st.session_state[chats_key][active_chat_id]["title"] = title

    with st.chat_message("user"):
        st.write(cleaned_prompt)

    if refine_running:
        queued_message = "Dataset setup is still running. I queued your question and will answer it when setup finishes."
        st.session_state[pending_schema_question_key] = cleaned_prompt

        messages.append({
            "role": "assistant",
            "content": queued_message,
        })

        with st.chat_message("assistant"):
            st.write(queued_message)

        save_chat(csv_choice.name, active_chat_id, st.session_state[chats_key][active_chat_id])

    else:
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                results = compute_results_for_query(cleaned_prompt)

            render_assistant_results(
                results,
                csv_choice.name,
                active_chat_id,
                len(messages),
                selected_projected_crs,
                selected_map_style,
            )

        messages.append({
            "role": "assistant",
            "results": results,
        })
        save_chat(csv_choice.name, active_chat_id, st.session_state[chats_key][active_chat_id])

next_suggested_prompt = render_suggested_question_buttons(
    make_suggested_questions(df, schema, coord_rows),
    f"suggested::{csv_choice.name}::{active_chat_id}",
)

if next_suggested_prompt:
    st.session_state[suggested_prompt_key] = next_suggested_prompt
    st.rerun()

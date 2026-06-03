from pathlib import Path
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import folium
import ollama
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

DATA_DIR = Path("data")


# -----------------------------
# File and model helpers
# -----------------------------

def get_tree_csv_files() -> List[Path]:
    return sorted([
        file for file in DATA_DIR.glob("*.csv")
        if "Column_Headers" not in file.name
    ])


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


# -----------------------------
# Generic helpers
# -----------------------------

def safe_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_prompt(text: str) -> str:
    return text.strip().rstrip("\\").strip()


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

    parts = re.split(r"(?<=[?.!])\s+", text)
    return [normalize_prompt(part) for part in parts if normalize_prompt(part)]


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
    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0, "num_predict": 350},
        )
        parsed = extract_json(response["message"]["content"].strip())
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


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

    if any(word in q for word in ["map", "plot", "geographic", "where", "location", "locations"]):
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

Intent must be one of: summary, count, top_species, native_summary, diameter_summary, danger_summary, filter, map.
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
    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0, "num_predict": 180},
        )
        parsed = extract_json(response["message"]["content"].strip())
        return parsed if isinstance(parsed, dict) else blank_instructions()
    except Exception:
        return blank_instructions()


def clean_instruction_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str) and value.strip().lower() in ["", "none", "null"]:
        return None

    return value


def interpret_question(question: str, schema: Dict[str, Any], model_name: str, use_model_parse: bool) -> Dict[str, Any]:
    rule_instructions = parse_with_rules(question)
    model_instructions = ask_model_for_parse(question, schema, model_name) if use_model_parse else blank_instructions()

    allowed_intents = {"summary", "count", "top_species", "native_summary", "diameter_summary", "danger_summary", "filter", "map"}
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


def build_result(
    df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    question: str,
    instructions: Dict[str, Any],
    schema: Dict[str, Any],
    filters: List[str],
    warnings: List[str],
    coord_rows: int,
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

    if warnings and any("native-status" in w for w in warnings) and intent == "native_summary":
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
        verified_summary = f"There are {matching_rows:,} matching tree records, which is {percent}% of the full dataset. The filters used were: {'; '.join(filters)}."

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
        verified_summary = f"The danger/hazard summary used the {danger_col} field. There are {matching_rows:,} matching records out of {total_rows:,} total records."

    else:
        table_df = pd.DataFrame([
            {"Metric": "Matching records", "Value": f"{matching_rows:,}"},
            {"Metric": "Total records in dataset", "Value": f"{total_rows:,}"},
            {"Metric": "Percent of dataset", "Value": f"{percent}%"},
            {"Metric": "Filters used", "Value": "; ".join(filters)},
        ])

        preview_df = filtered_df.head(int(instructions.get("limit", 1000))) if matching_rows > 0 else None

        verified_summary = f"There are {matching_rows:,} matching tree records, which is {percent}% of the full dataset. The filters used were: {'; '.join(filters)}."

    if warnings:
        verified_summary += " " + " ".join(warnings)

    if instructions.get("make_map") and coord_rows == 0:
        verified_summary += " A map was requested, but this CSV has no usable coordinate values."

    payload = {
        "question": question,
        "intent": intent,
        "result_available": result_available,
        "matching_record_count": int(matching_rows),
        "total_dataset_rows": int(total_rows),
        "percent_of_dataset": percent,
        "filters_used": filters,
        "warnings": warnings,
        "verified_summary": verified_summary,
        "important_table": table_df.to_dict(orient="records") if table_df is not None else [],
        "map_requested": bool(instructions.get("make_map")),
        "coordinate_rows_in_dataset": int(coord_rows),
        "coordinate_kind": schema.get("coordinate_kind"),
        "cache_hit": cache_hit,
    }

    return table_df, preview_df, payload


# -----------------------------
# AI responses
# -----------------------------

def explain_general_chat(prompt: str, model_name: str, use_model_explanation: bool) -> str:
    fallback = "I’m ready to help with the tree dataset. You can ask me to count, summarize, filter, or map trees."

    if not use_model_explanation:
        return fallback

    system_prompt = f"""
You are a helpful assistant inside a local tree-data demo app.
The user may casually chat with you, but you should not pretend to analyze the CSV unless they ask a data question.
Answer in 1 to 2 sentences.
If useful, mention that you can help count, summarize, filter, or map trees.
User message: {prompt}
"""
    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": system_prompt}],
            options={"temperature": 0.3, "num_predict": 120},
        )
        text = response["message"]["content"].strip()
        return text if text else fallback
    except Exception:
        return fallback


def explain_result(
    payload: Dict[str, Any],
    model_name: str,
    use_model_explanation: bool,
    selected_projected_crs: Optional[str],
) -> str:
    if not use_model_explanation:
        if payload.get("map_requested"):
            return "Here’s your map. " + payload["verified_summary"]
        return payload["verified_summary"]

    user_facing_payload = {
        "question": payload["question"],
        "result_available": payload["result_available"],
        "matching_record_count": payload["matching_record_count"],
        "total_dataset_rows": payload["total_dataset_rows"],
        "percent_of_dataset": payload["percent_of_dataset"],
        "filters_used": payload["filters_used"],
        "warnings": payload["warnings"],
        "verified_summary": payload["verified_summary"],
        "important_table": payload["important_table"],
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

    if payload.get("map_requested"):
        instruction = """
Write a friendly, direct answer that starts with "Here’s your map."
Then mention the key count and percent if available.
Do not repeat the user's question.
"""
    else:
        instruction = """
Write a friendly, direct answer.
Mention the key count and percent if available.
Do not repeat the user's question.
"""

    prompt = f"""
Use only the verified facts below. Write 2 to 4 plain-English sentences for a nontechnical supervisor.
Do not invent facts. Do not recalculate numbers. Do not mention JSON or internal fields.
If a map note is present, explain it in simple terms.
{instruction}

Verified facts:
{json.dumps(user_facing_payload, indent=2)}
"""
    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_predict": 220},
        )
        text = response["message"]["content"].strip()
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

        if payload.get("result_available"):
            count_text = str(payload["matching_record_count"])
            if count_text not in text.replace(",", ""):
                if payload.get("map_requested"):
                    return "Here’s your map. " + payload["verified_summary"]
                return payload["verified_summary"]

        if payload.get("map_requested") and "map" not in lowered:
            return "Here’s your map. " + text

        return text

    except Exception:
        if payload.get("map_requested"):
            return "Here’s your map. " + payload["verified_summary"]
        return payload["verified_summary"]


# -----------------------------
# Map creation
# -----------------------------

def make_map(
    df: pd.DataFrame,
    schema: Dict[str, Any],
    popup_cols: List[Optional[str]],
    selected_projected_crs: Optional[str],
) -> Tuple[Optional[folium.Map], Optional[str]]:
    roles = schema["roles"]
    lat_col = roles.get("latitude")
    lon_col = roles.get("longitude")

    if not lat_col or not lon_col:
        return None, "No coordinate columns were detected."

    map_df = df.dropna(subset=[lat_col, lon_col]).copy()

    if len(map_df) == 0:
        return None, "No rows have usable coordinate values."

    if len(map_df) > 1000:
        map_df = map_df.sample(1000, random_state=42)

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

    if len(map_df) == 0:
        return None, "No valid coordinates remained after conversion."

    m = folium.Map(location=[map_df["__map_lat"].mean(), map_df["__map_lon"].mean()], zoom_start=16)

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
        first_id = str(uuid4())
        st.session_state[chats_key] = {
            first_id: {
                "title": "New chat",
                "messages": [],
            }
        }
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


def render_assistant_results(
    results: List[Dict[str, Any]],
    csv_name: str,
    active_chat_id: str,
    message_index: int,
    selected_projected_crs: Optional[str],
) -> None:
    for result_index, result in enumerate(results):
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

        st.write(explanation)

        if instructions.get("make_map") or instructions.get("intent") == "map":
            popup_cols = [
                result_roles.get("species_common"),
                result_roles.get("scientific_name"),
                result_roles.get("diameter_numeric"),
                result_roles.get("height_numeric"),
            ]

            map_schema = {
                "roles": result_roles,
                "coordinate_kind": coordinate_kind,
            }

            m, error = make_map(
                filtered_df,
                map_schema,
                popup_cols,
                selected_projected_crs,
            )

            if error:
                st.warning(error)
            elif m is not None:
                st_folium(
                    m,
                    width=1000,
                    height=600,
                    key=f"map::{csv_name}::{active_chat_id}::{message_index}::{result_index}",
                    returned_objects=[],
                )

        with st.expander("Data result", expanded=False):
            if payload.get("result_available"):
                st.write(f"Matching records: {len(filtered_df):,}")
            else:
                st.write("Matching records: not applicable")

            if payload.get("cache_hit"):
                st.caption("Reused cached query result.")

            if table_df is not None:
                st.dataframe(table_df, use_container_width=True)

            if preview_df is not None:
                with st.expander("Preview matching rows", expanded=False):
                    st.dataframe(preview_df, use_container_width=True)

        with st.expander("Developer details", expanded=False):
            st.write("Question interpretation")
            st.json(instructions)
            st.write("Detected dataset roles")
            st.json(result_roles)
            st.write(f"Cache hit: {payload.get('cache_hit', False)}")


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(page_title="Tree AI Demo", layout="wide")

st.title("Tree AI Demo")
st.write("Ask questions about a tree CSV. The app queries the data, explains the answer, and can map results when coordinates are usable.")

csv_files = get_tree_csv_files()

if not csv_files:
    st.error("No tree CSV files found. Put your tree CSV file inside the data folder.")
    st.stop()

csv_choice = st.sidebar.selectbox("Dataset", csv_files, format_func=lambda x: x.name)
df = load_csv(csv_choice)

models = get_installed_ollama_models()
preferred_order = ["qwen3.5:9b", "qwen3:14b", "gemma3:12b", "gpt-oss:20b", "qwen2.5:3b"]

default_model = models[0] if models else "qwen2.5:3b"
for preferred in preferred_order:
    if preferred in models:
        default_model = preferred
        break

if "question_model" not in st.session_state or st.session_state["question_model"] not in models:
    st.session_state["question_model"] = default_model

if "schema_model" not in st.session_state or st.session_state["schema_model"] not in models:
    st.session_state["schema_model"] = default_model

if "use_model_parse" not in st.session_state:
    st.session_state["use_model_parse"] = True

if "use_model_explanation" not in st.session_state:
    st.session_state["use_model_explanation"] = True

model_name = st.session_state["question_model"]
schema_model_name = st.session_state["schema_model"]
use_model_parse = st.session_state["use_model_parse"]
use_model_explanation = st.session_state["use_model_explanation"]

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

chats_key, chats, active_chat_id = init_chat_state(csv_choice.name)

if st.sidebar.button("New chat", use_container_width=True):
    create_new_chat(csv_choice.name)
    st.rerun()

chat_ids = list(st.session_state[chats_key].keys())
active_index = chat_ids.index(st.session_state[f"active_chat::{csv_choice.name}"])

selected_chat_id = st.sidebar.selectbox(
    "Chat history",
    chat_ids,
    index=active_index,
    format_func=lambda cid: st.session_state[chats_key][cid]["title"],
)

if selected_chat_id != st.session_state[f"active_chat::{csv_choice.name}"]:
    st.session_state[f"active_chat::{csv_choice.name}"] = selected_chat_id
    st.rerun()

active_chat_id = st.session_state[f"active_chat::{csv_choice.name}"]
messages = st.session_state[chats_key][active_chat_id]["messages"]

last_filter_key = f"last_filter::{csv_choice.name}::{active_chat_id}"

if "schema_refine_executor" not in st.session_state:
    st.session_state["schema_refine_executor"] = ThreadPoolExecutor(max_workers=1)

refine_future_key = f"schema_refine_future::{csv_choice.name}"
refine_model_key = f"schema_refine_model::{csv_choice.name}"
refine_error_key = f"schema_refine_error::{csv_choice.name}"
pending_schema_question_key = f"pending_schema_question::{csv_choice.name}"
pending_chat_key = f"pending_chat::{csv_choice.name}::{active_chat_id}"

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

if refine_running and st_autorefresh is not None:
    st_autorefresh(interval=2000, key=f"schema_refine_poll::{csv_choice.name}")

with st.sidebar.expander("Advanced options", expanded=False):
    st.markdown("### AI model")

    with st.form("model_settings_form"):
        question_model_choice = st.selectbox(
            "Question/explanation model",
            models,
            index=models.index(st.session_state["question_model"]) if st.session_state["question_model"] in models else 0,
        )

        schema_model_choice = st.selectbox(
            "Schema refinement model",
            models,
            index=models.index(st.session_state["schema_model"]) if st.session_state["schema_model"] in models else 0,
        )

        parse_choice = st.checkbox(
            "Use model for question interpretation",
            value=st.session_state["use_model_parse"],
        )

        explanation_choice = st.checkbox(
            "Use model for explanation",
            value=st.session_state["use_model_explanation"],
        )

        settings_submitted = st.form_submit_button("Apply model settings")

    if settings_submitted:
        st.session_state["question_model"] = question_model_choice
        st.session_state["schema_model"] = schema_model_choice
        st.session_state["use_model_parse"] = parse_choice
        st.session_state["use_model_explanation"] = explanation_choice
        st.rerun()

    st.caption(f"Question model: `{st.session_state['question_model']}`")
    st.caption(f"Schema model: `{st.session_state['schema_model']}`")

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

    st.markdown("### Dataset setup")

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

    if st.button("Refine dataset setup with AI", disabled=refine_running, use_container_width=True):
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

    if st.button("Reset dataset setup", disabled=refine_running, use_container_width=True):
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

    if st.button("Clear query cache", use_container_width=True):
        st.session_state["query_cache"] = {}
        st.success("Query cache cleared.")

st.subheader("Dataset overview")

coordinate_label = get_coordinate_display_label(
    schema.get("coordinate_kind", "none"),
    selected_projected_crs,
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows", f"{len(df):,}")
c2.metric("Columns", len(df.columns))
c3.metric("Rows with coordinates", f"{coord_rows:,}")
c4.metric("Coordinate status", coordinate_label)

coordinate_note = get_coordinate_note(schema.get("coordinate_kind", "none"), selected_projected_crs)
if coordinate_note:
    st.info(coordinate_note)

with st.expander("Preview data"):
    st.dataframe(df.head(25), use_container_width=True)


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

        if question_is_map_request(question):
            instructions["intent"] = "map"
            instructions["make_map"] = True

        previous_filter_instructions = st.session_state.get(last_filter_key)
        instructions = merge_followup_filters(
            instructions,
            previous_filter_instructions,
            question,
        )

        filtered_df, filters, warnings, cache_hit, query_cache_key = get_or_run_filtered_query(
            csv_choice.name,
            df,
            schema,
            instructions,
        )

        table_df, preview_df, payload = build_result(
            df=df,
            filtered_df=filtered_df,
            question=question,
            instructions=instructions,
            schema=schema,
            filters=filters,
            warnings=warnings,
            coord_rows=coord_rows,
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
                )

if not refine_running and pending_schema_question_key in st.session_state:
    queued_question = st.session_state[pending_schema_question_key]
    del st.session_state[pending_schema_question_key]

    with st.spinner("Dataset setup finished. Answering your queued question..."):
        messages.append({
            "role": "assistant",
            "results": compute_results_for_query(queued_question),
        })

    st.rerun()

if pending_chat_key in st.session_state and not refine_running:
    pending_prompt = st.session_state[pending_chat_key]
    del st.session_state[pending_chat_key]

    with st.spinner("Thinking..."):
        results = compute_results_for_query(pending_prompt)

    messages.append({
        "role": "assistant",
        "results": results,
    })

    st.rerun()

prompt = st.chat_input("Ask about the tree dataset...")

if prompt:
    cleaned_prompt = normalize_prompt(prompt)

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

    if refine_running:
        st.session_state[pending_schema_question_key] = cleaned_prompt
        messages.append({
            "role": "assistant",
            "content": "Dataset setup is still running. I queued your question and will answer it when setup finishes.",
        })
        st.rerun()

    st.session_state[pending_chat_key] = cleaned_prompt
    st.rerun()
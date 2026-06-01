from pathlib import Path
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import folium
import ollama
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

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

        return sorted(names) if names else ["qwen2.5:3b", "llama3.1:8b"]
    except Exception:
        return ["qwen2.5:3b", "llama3.1:8b"]


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


# -----------------------------
# JSON and text helpers
# -----------------------------

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
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[?.!])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def safe_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


# -----------------------------
# Dataset schema profiling
# -----------------------------

def build_column_profile(df: pd.DataFrame, max_examples: int = 5) -> List[Dict[str, Any]]:
    profile = []
    total = len(df)

    for col in df.columns:
        series = df[col]
        non_null = int(series.notna().sum())
        examples = [safe_string(x) for x in series.dropna().head(max_examples).tolist()]

        numeric_series = pd.to_numeric(series, errors="coerce")
        numeric_non_null = int(numeric_series.notna().sum())
        numeric_ratio = round(numeric_non_null / total, 3) if total else 0

        item = {
            "name": col,
            "dtype": str(series.dtype),
            "non_null_count": non_null,
            "non_null_ratio": round(non_null / total, 3) if total else 0,
            "numeric_ratio": numeric_ratio,
            "sample_values": examples,
        }

        if numeric_non_null > 0:
            item["numeric_min"] = float(numeric_series.min())
            item["numeric_max"] = float(numeric_series.max())
            item["numeric_median"] = float(numeric_series.median())

        profile.append(item)

    return profile


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


def best_text_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    scored: List[Tuple[int, str]] = []
    for col in df.columns:
        score = score_column_name(col, candidates)
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
        score += min(numeric_count, 1000) // 100
        # Prefer primary fields such as DBH_1 over DBH_2.
        name = col.lower()
        if name.endswith("_1") or name.endswith("1"):
            score += 5
        if name.endswith("_2") or name.endswith("2"):
            score -= 2
        scored.append((score, col))
    return sorted(scored, reverse=True)[0][1] if scored else None


def validate_role_column(df: pd.DataFrame, role: str, col: Any) -> Optional[str]:
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
        values = " ".join(series.dropna().astype(str).head(200).str.lower().tolist())
        name_ok = any(term in name for term in ["native", "origin", "introduced"])
        value_ok = any(term in values for term in ["native", "introduced", "naturally", "occurring"])
        return col if name_ok or value_ok else None

    if role in ["species_common", "scientific_name", "condition", "danger_flag"]:
        return col if int(series.notna().sum()) > 0 else None

    return col


def infer_schema_with_rules(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    columns = list(df.columns)
    lower_to_original = {col.lower(): col for col in columns}

    schema: Dict[str, Optional[str]] = {
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

    # Direct exact-name wins.
    exact_species = ["common_name", "common1", "common", "species", "spc_common"]
    for name in exact_species:
        if name in lower_to_original:
            schema["species_common"] = lower_to_original[name]
            break

    if schema["species_common"] is None:
        schema["species_common"] = best_text_column(df, ["common", "species"])

    exact_sci = ["scientific_name", "sciname", "sciname1", "latin_name"]
    for name in exact_sci:
        if name in lower_to_original:
            schema["scientific_name"] = lower_to_original[name]
            break

    if schema["scientific_name"] is None:
        schema["scientific_name"] = best_text_column(df, ["scientific", "sci", "latin"])

    schema["native_status"] = best_text_column(df, ["native", "origin", "introduced"])

    # Prefer binned diameter columns for binned summaries.
    schema["diameter_bin"] = best_text_column(df, ["diameter", "dbh", "breast_height", "bin", "class"])
    if schema["diameter_bin"] is not None:
        bin_name = schema["diameter_bin"].lower()
        if not any(term in bin_name for term in ["bin", "class", "range"]):
            schema["diameter_bin"] = None

    schema["diameter_numeric"] = best_numeric_column(
        df,
        ["dbh", "diameter", "breast_height", "diam"],
        negative_terms=["bin", "class", "range"],
    )

    schema["height_numeric"] = best_numeric_column(df, ["height", "totalht", "total_ht", "ht"])

    # Latitude/longitude. This supports both decimal degrees and projected x/y mislabeled as lat/long.
    lat_exact = ["latitude_coordinate", "latitude", "lat", "y"]
    lon_exact = ["longitude_coordinate", "longitude", "long", "lon", "lng", "x"]

    for name in lat_exact:
        if name in lower_to_original:
            schema["latitude"] = lower_to_original[name]
            break
    for name in lon_exact:
        if name in lower_to_original:
            schema["longitude"] = lower_to_original[name]
            break

    if schema["latitude"] is None:
        schema["latitude"] = best_numeric_column(df, ["latitude", "lat", "northing", "y"])
    if schema["longitude"] is None:
        schema["longitude"] = best_numeric_column(df, ["longitude", "long", "lon", "lng", "easting", "x"])

    schema["condition"] = best_text_column(df, ["condition", "health", "status"])
    schema["danger_flag"] = best_numeric_column(df, ["danger", "hazard", "risk"])
    schema["id"] = best_text_column(df, ["tree_id", "objectid", "fid", "id"])

    # Final validation.
    for role, col in list(schema.items()):
        schema[role] = validate_role_column(df, role, col)

    return schema


@st.cache_data(show_spinner=False)
def ask_model_to_infer_schema(csv_name: str, profile_json: str, model_name: str) -> Dict[str, Optional[str]]:
    prompt = f"""
You are identifying the semantic roles of columns in a tree inventory CSV.

CSV file name: {csv_name}

Column profile JSON:
{profile_json}

Return only valid JSON with this exact structure:
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
- Use column names exactly as shown in the profile.
- COMMON1, COMMON2, common_name, or similar usually mean common species name.
- SCINAME1, scientific_name, or similar usually mean scientific species name.
- DBH, diameter, or diameter_breast_height usually means tree diameter.
- TOTALHT or height usually means tree height.
- LAT/LONG, latitude/longitude, northing/easting, x/y can be coordinate fields.
- If a role is not present in the CSV, return null for that role.
- Do not guess native_status unless a column clearly stores native/origin/introduced values.
"""
    try:
        response = ollama.chat(model=model_name, messages=[{"role": "user", "content": prompt}])
        parsed = extract_json(response["message"]["content"].strip())
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def infer_schema(df: pd.DataFrame, csv_name: str, model_name: str) -> Dict[str, Any]:
    rules = infer_schema_with_rules(df)
    profile = build_column_profile(df)
    compact_profile = json.dumps(profile[:80], indent=2)
    model_guess = ask_model_to_infer_schema(csv_name, compact_profile, model_name)

    merged = dict(rules)
    for role in merged.keys():
        model_col = validate_role_column(df, role, model_guess.get(role)) if isinstance(model_guess, dict) else None
        if model_col:
            merged[role] = model_col

    coordinate_kind = classify_coordinates(df, merged.get("latitude"), merged.get("longitude"))

    return {
        "roles": merged,
        "coordinate_kind": coordinate_kind,
        "model_guess": model_guess,
        "rule_guess": rules,
    }


# -----------------------------
# Coordinate handling
# -----------------------------

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

    # UGA example: LAT around 3,759,000 and LONG around 280,500.
    # Those values look like UTM Zone 17N northing/easting, not decimal lat/lon.
    if 100000 <= lon_med <= 900000 and 0 <= lat_med <= 10000000:
        return "projected_possible_utm17n"

    return "projected_unknown"


def get_map_coordinates(df: pd.DataFrame, lat_col: str, lon_col: str, coordinate_kind: str) -> Tuple[Optional[pd.Series], Optional[pd.Series], Optional[str]]:
    raw_lat = pd.to_numeric(df[lat_col], errors="coerce")
    raw_lon = pd.to_numeric(df[lon_col], errors="coerce")

    if coordinate_kind == "decimal_degrees":
        return raw_lat, raw_lon, None

    if coordinate_kind == "projected_possible_utm17n":
        try:
            from pyproj import Transformer
        except Exception:
            return None, None, "Coordinates are present, but they look projected rather than decimal latitude/longitude. Install pyproj with: pip install pyproj"

        try:
            transformer = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)
            # LONG is the easting/x field, LAT is the northing/y field in the UGA-style file.
            lon_values, lat_values = transformer.transform(raw_lon.to_numpy(), raw_lat.to_numpy())
            return pd.Series(lat_values, index=df.index), pd.Series(lon_values, index=df.index), None
        except Exception as exc:
            return None, None, f"Coordinate transformation failed: {exc}"

    if coordinate_kind == "projected_unknown":
        return None, None, "Coordinates are present, but they are not decimal degrees and the coordinate reference system is unknown."

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

    species_words = [
        "live oak", "water oak", "willow oak", "overcup oak", "laurel oak",
        "loblolly pine", "flowering dogwood", "crape myrtle", "southern magnolia",
        "oak", "pine", "palm", "maple", "elm", "magnolia", "crapemyrtle",
        "cypress", "cedar", "holly", "palmetto", "dogwood", "poplar", "birch",
    ]

    for word in sorted(species_words, key=len, reverse=True):
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
You are converting a tree-data question into structured JSON instructions.

Detected dataset schema:
{json.dumps(schema["roles"], indent=2)}

Return only valid JSON. Do not include markdown.

Use this exact structure:
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

Intent must be one of:
summary, count, top_species, native_summary, diameter_summary, danger_summary, filter, map

Rules:
- For "how many", use intent "count".
- For top or most common species, use intent "top_species".
- For native/introduced questions, use intent "native_summary".
- For diameter/DBH/size/bin questions, use intent "diameter_summary".
- For danger/hazard questions, use intent "danger_summary" and danger_value 1.
- For map/plot/geographic/location questions, use intent "map" and make_map true.
- If the user asks about a species group like oak, pine, dogwood, maple, magnolia, etc., put that word in species_text.
- If the user asks for native trees, set native_text to "naturally_occurring".
- Do not invent data fields.

Question:
{question}
"""
    try:
        response = ollama.chat(model=model_name, messages=[{"role": "user", "content": prompt}])
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


def interpret_question(question: str, schema: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    model_instructions = ask_model_for_parse(question, schema, model_name)
    rule_instructions = parse_with_rules(question)

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

    # Deterministic parsing fixes obvious misses from small local models.
    for key in ["species_text", "native_text", "min_diameter", "max_diameter", "danger_value"]:
        if rule_instructions.get(key) is not None:
            merged[key] = rule_instructions[key]

    if rule_instructions.get("intent") != "summary":
        merged["intent"] = rule_instructions["intent"]
    if rule_instructions.get("make_map"):
        merged["make_map"] = True

    return merged


# -----------------------------
# Query execution and summaries
# -----------------------------

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

        max_value = float(values.max())
        if max_value <= 100:
            bins = [-0.001, 5, 10, 20, 30, 40, 50, float("inf")]
            labels = ["0 to 5", "5 to 10", "10 to 20", "20 to 30", "30 to 40", "40 to 50", "more than 50"]
        else:
            bins = 6
            labels = None

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
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    roles = schema["roles"]
    total_rows = len(df)
    matching_rows = len(filtered_df)
    percent = round((matching_rows / total_rows) * 100, 1) if total_rows else 0.0
    intent = instructions.get("intent", "summary")

    table_df: Optional[pd.DataFrame] = None
    preview_df: Optional[pd.DataFrame] = None
    verified_summary = ""
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
        verified_summary = (
            f"There are {matching_rows:,} matching tree records, which is {percent}% of the full dataset. "
            f"The filters used were: {'; '.join(filters)}."
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
        verified_summary = (
            f"The danger/hazard summary used the {danger_col} field. "
            f"There are {matching_rows:,} matching records out of {total_rows:,} total records."
        )

    else:
        table_df = pd.DataFrame([
            {"Metric": "Matching records", "Value": f"{matching_rows:,}"},
            {"Metric": "Total records in dataset", "Value": f"{total_rows:,}"},
            {"Metric": "Percent of dataset", "Value": f"{percent}%"},
            {"Metric": "Filters used", "Value": "; ".join(filters)},
        ])
        preview_df = filtered_df.head(int(instructions.get("limit", 1000))) if matching_rows > 0 else None
        verified_summary = (
            f"There are {matching_rows:,} matching tree records, which is {percent}% of the full dataset. "
            f"The filters used were: {'; '.join(filters)}."
        )

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
    }

    return table_df, preview_df, payload


def explain_result(payload: Dict[str, Any], model_name: str) -> str:
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
        user_facing_payload["map_note"] = (
            f"A map was requested. Coordinate rows available: {payload['coordinate_rows_in_dataset']}. "
            f"Coordinate type: {payload.get('coordinate_kind')}."
        )

    prompt = f"""
You are explaining a tree CSV analysis result to a nontechnical supervisor.

Use only the verified facts below.
Do not invent facts.
Do not recalculate numbers.
Do not mention JSON, internal fields, map_requested, or coordinate details unless map_note is present.
Do not say "forest surveyed"; say "CSV dataset" or "tree dataset".
Write 2 to 4 plain-English sentences.

Verified facts:
{json.dumps(user_facing_payload, indent=2)}
"""
    try:
        response = ollama.chat(model=model_name, messages=[{"role": "user", "content": prompt}])
        text = response["message"]["content"].strip()
        lowered = text.lower()

        forbidden = ["over 99%", "almost all", "forest surveyed", "map_requested", "json"]
        if not payload.get("map_requested"):
            forbidden.extend(["coordinate data", "coordinate rows", "missing coordinate"])

        if any(term in lowered for term in forbidden):
            return payload["verified_summary"]

        if payload.get("result_available"):
            count_text = str(payload["matching_record_count"])
            if count_text not in text.replace(",", ""):
                return payload["verified_summary"]

        return text
    except Exception:
        return payload["verified_summary"]


# -----------------------------
# Map creation
# -----------------------------

def make_map(df: pd.DataFrame, schema: Dict[str, Any], popup_cols: List[Optional[str]]) -> Tuple[Optional[folium.Map], Optional[str]]:
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

    lat_values, lon_values, error = get_map_coordinates(map_df, lat_col, lon_col, schema.get("coordinate_kind", "none"))
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
# Streamlit UI
# -----------------------------

st.set_page_config(page_title="Tree AI Demo", layout="wide")
st.title("Tree AI Demo")
st.write("This demo uses a local AI model to interpret questions, query a tree CSV, and explain the results.")

csv_files = get_tree_csv_files()
if not csv_files:
    st.error("No tree CSV files found. Put your tree CSV file inside the data folder.")
    st.stop()

csv_choice = st.sidebar.selectbox("Choose tree CSV", csv_files, format_func=lambda x: x.name)
df = load_csv(csv_choice)

models = get_installed_ollama_models()
default_index = models.index("qwen2.5:3b") if "qwen2.5:3b" in models else 0
st.sidebar.header("AI model")
model_name = st.sidebar.selectbox("Ollama model", models, index=default_index)

with st.spinner("Interpreting dataset schema..."):
    schema = infer_schema(df, csv_choice.name, model_name)
roles = schema["roles"]

coord_rows = 0
if roles.get("latitude") and roles.get("longitude"):
    coord_rows = df[[roles["latitude"], roles["longitude"]]].dropna().shape[0]

st.subheader("Dataset overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows", f"{len(df):,}")
c2.metric("Columns", len(df.columns))
c3.metric("Rows with coordinates", f"{coord_rows:,}")
c4.metric("Coordinate type", schema.get("coordinate_kind", "none"))

with st.expander("Preview data"):
    st.dataframe(df.head(25))

st.subheader("Ask a question")
question_text = st.text_area(
    "Ask one or more questions. Separate multiple questions with punctuation.",
    value="How many oak trees are there? Show native trees. What are the diameter bins?",
    height=100,
)

if st.button("Run"):
    questions = split_questions(question_text)
    if not questions:
        st.warning("Please enter a question.")
        st.stop()

    for question in questions:
        st.divider()
        st.subheader(f"Question: {question}")

        instructions = interpret_question(question, schema, model_name)
        filtered_df, filters, warnings = apply_filters(df, schema, instructions)
        table_df, preview_df, payload = build_result(
            df=df,
            filtered_df=filtered_df,
            question=question,
            instructions=instructions,
            schema=schema,
            filters=filters,
            warnings=warnings,
            coord_rows=coord_rows,
        )

        with st.expander("AI interpretation"):
            st.write("Question interpretation")
            st.json(instructions)
            st.write("Automatically detected dataset roles")
            st.json(roles)
            if schema.get("model_guess"):
                st.write("Model schema guess before validation")
                st.json(schema.get("model_guess"))

        st.markdown("### Plain-English answer")
        st.write(explain_result(payload, model_name))

        st.markdown("### Data result")
        if payload.get("result_available"):
            st.write(f"Matching records: {len(filtered_df):,}")
        else:
            st.write("Matching records: not applicable")

        if table_df is not None:
            st.dataframe(table_df)

        if preview_df is not None:
            with st.expander("Preview matching rows"):
                st.dataframe(preview_df)

        if instructions.get("make_map") or instructions.get("intent") == "map":
            st.markdown("### Map")
            popup_cols = [roles.get("species_common"), roles.get("scientific_name"), roles.get("diameter_numeric"), roles.get("height_numeric")]
            m, error = make_map(filtered_df, schema, popup_cols)
            if error:
                st.warning(error)
            elif m is not None:
                st_folium(m, width=1000, height=600)

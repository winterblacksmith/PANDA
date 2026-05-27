from pathlib import Path
import json
import re
import pandas as pd
import streamlit as st
import ollama
import folium
from streamlit_folium import st_folium

DATA_DIR = Path("data")


def get_tree_csv_files():
    return sorted([
        file for file in DATA_DIR.glob("*.csv")
        if "Column_Headers" not in file.name
    ])


def get_installed_ollama_models():
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
def load_csv(path):
    return pd.read_csv(path)


def find_column(columns, possible_names):
    for possible in possible_names:
        for col in columns:
            if col.lower() == possible.lower():
                return col

    for possible in possible_names:
        for col in columns:
            if possible.lower() in col.lower():
                return col

    return None


def split_questions(text):
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[?.!])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None

    return None


def blank_instructions():
    return {
        "intent": "summary",
        "species_text": None,
        "native_text": None,
        "diameter_bin_text": None,
        "make_map": False,
        "limit": 1000,
    }


def parse_with_rules(question):
    q = question.lower()
    instructions = blank_instructions()

    if any(word in q for word in ["map", "plot", "geographic", "where"]):
        instructions["intent"] = "map"
        instructions["make_map"] = True
    elif any(phrase in q for phrase in ["top species", "most common species", "common species"]):
        instructions["intent"] = "top_species"
    elif any(word in q for word in ["diameter", "dbh", "size class", "size classes", "diameter bins"]):
        instructions["intent"] = "diameter_summary"
    elif any(word in q for word in ["native", "introduced", "non-native", "non native"]):
        instructions["intent"] = "native_summary"
    elif any(phrase in q for phrase in ["how many", "count", "number of"]):
        instructions["intent"] = "count"
    elif any(word in q for word in ["show", "list", "find", "filter"]):
        instructions["intent"] = "filter"

    species_words = [
        "oak", "pine", "palm", "maple", "elm", "magnolia", "crapemyrtle",
        "cypress", "cedar", "holly", "palmetto", "laurel", "live oak"
    ]

    # Check longer names first so "live oak" is not reduced to just "oak".
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

    return instructions


def ask_model_for_parse(question, columns, model_name):
    prompt = f"""
You are converting a tree-dataset question into JSON instructions.

CSV columns:
{columns}

Return only valid JSON. Do not include markdown.

Use this exact structure:
{{
  "intent": "summary",
  "species_text": null,
  "native_text": null,
  "diameter_bin_text": null,
  "make_map": false,
  "limit": 1000
}}

Intent must be one of:
summary, count, top_species, native_summary, diameter_summary, filter, map

Rules:
- For "how many", use intent "count".
- For top or most common species, use intent "top_species".
- For native/introduced questions, use intent "native_summary".
- For diameter/DBH/size bins, use intent "diameter_summary".
- For map/plot/geographic questions, use intent "map" and make_map true.
- If the user asks about a species group like oak, pine, palm, maple, elm, magnolia, etc., put that word in species_text.
- If the user asks for native trees, set native_text to "naturally_occurring".
- If the user asks for introduced or non-native trees, set native_text to "introduced".
- Do not put column names into species_text, native_text, or diameter_bin_text.

Question:
{question}
"""
    try:
        response = ollama.chat(model=model_name, messages=[{"role": "user", "content": prompt}])
        text = response["message"]["content"].strip()
        parsed = extract_json(text)
        return parsed if isinstance(parsed, dict) else blank_instructions()
    except Exception:
        return blank_instructions()


def clean_value(value, columns):
    if value is None:
        return None

    value = str(value).strip()
    if value.lower() in ["", "none", "null"]:
        return None

    column_names = {str(col).lower() for col in columns}
    if value.lower() in column_names:
        return None

    return value


def merge_instructions(model_instructions, rule_instructions, columns):
    allowed_intents = {"summary", "count", "top_species", "native_summary", "diameter_summary", "filter", "map"}

    merged = blank_instructions()
    merged.update(model_instructions or {})

    if merged.get("intent") not in allowed_intents:
        merged["intent"] = "summary"

    for key in ["species_text", "native_text", "diameter_bin_text"]:
        merged[key] = clean_value(merged.get(key), columns)

    try:
        merged["limit"] = int(merged.get("limit") or 1000)
    except Exception:
        merged["limit"] = 1000

    # Rule-based parsing overrides obvious model misses.
    if rule_instructions["intent"] != "summary":
        merged["intent"] = rule_instructions["intent"]
    if rule_instructions["species_text"]:
        merged["species_text"] = rule_instructions["species_text"]
    if rule_instructions["native_text"]:
        merged["native_text"] = rule_instructions["native_text"]
    if rule_instructions["diameter_bin_text"]:
        merged["diameter_bin_text"] = rule_instructions["diameter_bin_text"]
    if rule_instructions["make_map"]:
        merged["make_map"] = True

    return merged


def interpret_question(question, columns, model_name):
    model_instructions = ask_model_for_parse(question, columns, model_name)
    rule_instructions = parse_with_rules(question)
    return merge_instructions(model_instructions, rule_instructions, columns)


def apply_filters(df, species_col, native_col, diameter_bin_col, instructions):
    filtered = df.copy()

    if instructions.get("species_text") and species_col:
        filtered = filtered[
            filtered[species_col]
            .astype(str)
            .str.contains(str(instructions["species_text"]), case=False, na=False)
        ]

    if instructions.get("native_text") and native_col:
        filtered = filtered[
            filtered[native_col]
            .astype(str)
            .str.contains(str(instructions["native_text"]), case=False, na=False)
        ]

    if instructions.get("diameter_bin_text") and diameter_bin_col:
        filtered = filtered[
            filtered[diameter_bin_col]
            .astype(str)
            .str.contains(str(instructions["diameter_bin_text"]), case=False, na=False)
        ]

    return filtered


def filter_description(instructions, species_col, native_col, diameter_bin_col):
    filters = []
    if instructions.get("species_text") and species_col:
        filters.append(f"{species_col} contains '{instructions['species_text']}'")
    if instructions.get("native_text") and native_col:
        filters.append(f"{native_col} contains '{instructions['native_text']}'")
    if instructions.get("diameter_bin_text") and diameter_bin_col:
        filters.append(f"{diameter_bin_col} contains '{instructions['diameter_bin_text']}'")
    return filters if filters else ["No filters applied"]


def build_result(df, filtered_df, question, instructions, species_col, native_col, diameter_bin_col, coord_rows):
    total_rows = len(df)
    matching_rows = len(filtered_df)
    percent = round((matching_rows / total_rows) * 100, 1) if total_rows else 0.0
    intent = instructions.get("intent", "summary")
    filters = filter_description(instructions, species_col, native_col, diameter_bin_col)

    table_df = None
    preview_df = None

    if intent == "top_species" and species_col:
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

    elif intent == "native_summary" and native_col:
        table_df = filtered_df[native_col].astype(str).value_counts().reset_index()
        table_df.columns = ["Native status", "Count"]
        verified_summary = (
            f"There are {matching_rows:,} matching tree records, which is {percent}% of the full dataset. "
            f"The filters used were: {'; '.join(filters)}."
        )

    elif intent == "diameter_summary" and diameter_bin_col:
        table_df = filtered_df[diameter_bin_col].astype(str).value_counts().reset_index()
        table_df.columns = ["Diameter bin", "Count"]
        if len(table_df) > 0:
            verified_summary = (
                f"The most common diameter bin is '{table_df.iloc[0]['Diameter bin']}', "
                f"with {int(table_df.iloc[0]['Count']):,} records. "
                f"The diameter-bin summary is based on {matching_rows:,} matching records out of {total_rows:,} total records."
            )
        else:
            verified_summary = "No diameter-bin records were found."

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

    if instructions.get("make_map") and coord_rows == 0:
        verified_summary += " A map was requested, but this CSV has no usable latitude/longitude values."

    payload = {
        "question": question,
        "intent": intent,
        "matching_record_count": int(matching_rows),
        "total_dataset_rows": int(total_rows),
        "percent_of_dataset": percent,
        "filters_used": filters,
        "verified_summary": verified_summary,
        "important_table": table_df.to_dict(orient="records") if table_df is not None else [],
        "map_requested": bool(instructions.get("make_map")),
        "coordinate_rows_in_dataset": int(coord_rows),
    }

    return table_df, preview_df, payload


def explain_result(payload, model_name):
    user_facing_payload = {
        "question": payload["question"],
        "matching_record_count": payload["matching_record_count"],
        "total_dataset_rows": payload["total_dataset_rows"],
        "percent_of_dataset": payload["percent_of_dataset"],
        "filters_used": payload["filters_used"],
        "verified_summary": payload["verified_summary"],
        "important_table": payload["important_table"],
    }

    if payload.get("map_requested"):
        user_facing_payload["map_note"] = (
            f"A map was requested. Coordinate rows available: {payload['coordinate_rows_in_dataset']}."
        )

    prompt = f"""
You are explaining a tree CSV analysis result to a nontechnical supervisor.

Use only the verified facts below.
Do not invent facts.
Do not recalculate numbers.
Do not mention JSON, internal fields, map_requested, coordinate rows, or missing coordinates unless map_note is present.
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

        count_text = str(payload["matching_record_count"])
        if count_text not in text.replace(",", ""):
            return payload["verified_summary"]

        return text
    except Exception:
        return payload["verified_summary"]


def make_map(df, lat_col, lon_col, popup_cols):
    map_df = df.dropna(subset=[lat_col, lon_col]).copy()
    if len(map_df) == 0:
        return None

    if len(map_df) > 1000:
        map_df = map_df.sample(1000, random_state=42)

    map_df[lat_col] = pd.to_numeric(map_df[lat_col], errors="coerce")
    map_df[lon_col] = pd.to_numeric(map_df[lon_col], errors="coerce")
    map_df = map_df.dropna(subset=[lat_col, lon_col])

    if len(map_df) == 0:
        return None

    m = folium.Map(location=[map_df[lat_col].mean(), map_df[lon_col].mean()], zoom_start=11)

    for _, row in map_df.iterrows():
        popup_text = []
        for col in popup_cols:
            if col and col in row:
                popup_text.append(f"{col}: {row[col]}")

        folium.CircleMarker(
            location=[row[lat_col], row[lon_col]],
            radius=3,
            popup="<br>".join(popup_text),
            fill=True,
        ).add_to(m)

    return m


st.set_page_config(page_title="Tree AI Demo", layout="wide")
st.title("Tree AI Demo")
st.write("This demo uses a local AI model to interpret questions, query a tree CSV, and explain the results.")

csv_files = get_tree_csv_files()
if not csv_files:
    st.error("No tree CSV files found. Put your tree CSV file inside the data folder.")
    st.stop()

csv_choice = st.sidebar.selectbox("Choose tree CSV", csv_files, format_func=lambda x: x.name)
df = load_csv(csv_choice)
columns = list(df.columns)

species_guess = find_column(columns, ["common_name", "species", "scientific_name"])
native_guess = find_column(columns, ["native"])
diameter_guess = find_column(columns, ["diameter_breast_height_binned_CM"])
lat_guess = find_column(columns, ["latitude_coordinate", "latitude", "lat"])
lon_guess = find_column(columns, ["longitude_coordinate", "longitude", "lon"])

st.sidebar.header("Detected columns")
species_col = st.sidebar.selectbox("Species column", [None] + columns, index=([None] + columns).index(species_guess) if species_guess in columns else 0)
native_col = st.sidebar.selectbox("Native column", [None] + columns, index=([None] + columns).index(native_guess) if native_guess in columns else 0)
diameter_bin_col = st.sidebar.selectbox("Diameter bin column", [None] + columns, index=([None] + columns).index(diameter_guess) if diameter_guess in columns else 0)
lat_col = st.sidebar.selectbox("Latitude column", [None] + columns, index=([None] + columns).index(lat_guess) if lat_guess in columns else 0)
lon_col = st.sidebar.selectbox("Longitude column", [None] + columns, index=([None] + columns).index(lon_guess) if lon_guess in columns else 0)

models = get_installed_ollama_models()
default_index = models.index("qwen2.5:3b") if "qwen2.5:3b" in models else 0
st.sidebar.header("AI model")
model_name = st.sidebar.selectbox("Ollama model", models, index=default_index)

coord_rows = df[[lat_col, lon_col]].dropna().shape[0] if lat_col and lon_col else 0

st.subheader("Dataset overview")
c1, c2, c3 = st.columns(3)
c1.metric("Rows", f"{len(df):,}")
c2.metric("Columns", len(df.columns))
c3.metric("Rows with coordinates", f"{coord_rows:,}")

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

        instructions = interpret_question(question, columns, model_name)

        with st.expander("AI interpretation"):
            st.json(instructions)

        filtered_df = apply_filters(df, species_col, native_col, diameter_bin_col, instructions)
        table_df, preview_df, payload = build_result(
            df=df,
            filtered_df=filtered_df,
            question=question,
            instructions=instructions,
            species_col=species_col,
            native_col=native_col,
            diameter_bin_col=diameter_bin_col,
            coord_rows=coord_rows,
        )

        st.markdown("### Plain-English answer")
        st.write(explain_result(payload, model_name))

        st.markdown("### Data result")
        st.write(f"Matching records: {len(filtered_df):,}")

        if table_df is not None:
            st.dataframe(table_df)

        if preview_df is not None:
            with st.expander("Preview matching rows"):
                st.dataframe(preview_df)

        if instructions.get("make_map") or instructions.get("intent") == "map":
            st.markdown("### Map")
            if not lat_col or not lon_col:
                st.warning("No latitude/longitude columns selected.")
            else:
                m = make_map(filtered_df, lat_col, lon_col, [species_col, native_col, diameter_bin_col])
                if m is None:
                    st.warning("No usable coordinates found for this result. The selected CSV has no usable latitude/longitude values.")
                else:
                    st_folium(m, width=1000, height=600)

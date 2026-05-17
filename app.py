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

        if isinstance(response, dict):
            raw_models = response.get("models", [])
        else:
            raw_models = getattr(response, "models", [])

        model_names = []

        for model in raw_models:
            if isinstance(model, dict):
                name = model.get("model") or model.get("name")
            else:
                name = getattr(model, "model", None) or getattr(model, "name", None)

            if name:
                model_names.append(name)

        if model_names:
            return sorted(model_names)

    except Exception:
        pass

    return ["qwen2.5:3b", "llama3.1:8b"]


@st.cache_data
def load_csv(path):
    return pd.read_csv(path)


def find_column(columns, names):
    for name in names:
        for col in columns:
            if col.lower() == name.lower():
                return col

    for name in names:
        for col in columns:
            if name.lower() in col.lower():
                return col

    return None


def extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass

    return None


def split_questions(text):
    text = text.strip()

    if not text:
        return []

    parts = re.split(r"(?<=[?.!])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def deterministic_parse(question):
    """
    Rule-based backup parser.

    This is important because small local models may return valid JSON
    but still miss obvious words like "oak".
    """
    q = question.lower()

    instructions = {
        "intent": "summary",
        "species_text": None,
        "native_text": None,
        "diameter_bin_text": None,
        "make_map": False,
        "limit": 1000
    }

    if any(word in q for word in ["map", "plot", "geographic", "where are", "display on map"]):
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
        "oak", "pine", "palm", "maple", "elm", "magnolia",
        "crapemyrtle", "cypress", "cedar", "holly", "palmetto"
    ]

    for word in species_words:
        if word in q:
            instructions["species_text"] = word
            if instructions["intent"] == "summary":
                instructions["intent"] = "filter"

    if "naturally occurring" in q:
        instructions["native_text"] = "naturally_occurring"
    elif "introduced" in q or "non-native" in q or "non native" in q:
        instructions["native_text"] = "introduced"
    elif "native" in q:
        instructions["native_text"] = "naturally_occurring"

    return instructions


def clean_and_merge_instructions(model_instructions, columns, question):
    """
    Combines the model's interpretation with deterministic parsing.
    The deterministic parser fixes obvious misses.
    """
    cleaned = {
        "intent": model_instructions.get("intent", "summary"),
        "species_text": model_instructions.get("species_text"),
        "native_text": model_instructions.get("native_text"),
        "diameter_bin_text": model_instructions.get("diameter_bin_text"),
        "make_map": bool(model_instructions.get("make_map", False)),
        "limit": model_instructions.get("limit", 1000)
    }

    try:
        cleaned["limit"] = int(cleaned["limit"])
    except Exception:
        cleaned["limit"] = 1000

    allowed_intents = {
        "summary",
        "count",
        "top_species",
        "native_summary",
        "diameter_summary",
        "filter",
        "map"
    }

    if cleaned["intent"] not in allowed_intents:
        cleaned["intent"] = "summary"

    column_names_lower = {str(col).lower() for col in columns}

    for key in ["species_text", "native_text", "diameter_bin_text"]:
        value = cleaned.get(key)

        if value is None:
            continue

        value_str = str(value).strip()

        if value_str.lower() in ["null", "none", ""]:
            cleaned[key] = None
        elif value_str.lower() in column_names_lower:
            cleaned[key] = None
        else:
            cleaned[key] = value_str

    deterministic = deterministic_parse(question)

    if deterministic["intent"] != "summary":
        cleaned["intent"] = deterministic["intent"]

    if deterministic["species_text"]:
        cleaned["species_text"] = deterministic["species_text"]

    if deterministic["native_text"]:
        cleaned["native_text"] = deterministic["native_text"]

    if deterministic["diameter_bin_text"]:
        cleaned["diameter_bin_text"] = deterministic["diameter_bin_text"]

    if deterministic["make_map"]:
        cleaned["make_map"] = True

    return cleaned


def ask_ai_for_instructions(question, columns, model_name):
    prompt = f"""
You are analyzing a CSV of tree records.

The CSV columns are:
{columns}

Convert the user's question into JSON.

Return only valid JSON. No markdown. No explanation.

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
- For "how many" questions, use intent "count".
- For "top species" or "most common species", use intent "top_species".
- For native/introduced questions, use intent "native_summary".
- For diameter/DBH/size/bin questions, use intent "diameter_summary".
- For map/plot/geographic questions, use intent "map" and make_map true.
- If the user asks about oak, pine, palm, maple, elm, magnolia, etc., put that word in species_text.
- If the user asks about native trees, set native_text to "naturally_occurring".
- If the user asks about introduced or non-native trees, set native_text to "introduced".
- Do not put column names into species_text, native_text, or diameter_bin_text.
- If unsure, use intent "summary".

User question:
{question}
"""

    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response["message"]["content"].strip()
        parsed = extract_json(text)

        if parsed:
            return clean_and_merge_instructions(parsed, columns, question)

        return clean_and_merge_instructions(deterministic_parse(question), columns, question)

    except Exception as e:
        st.warning(f"Ollama failed while interpreting the question. Using backup parser. Error: {e}")
        return clean_and_merge_instructions(deterministic_parse(question), columns, question)


def apply_filters(df, species_col, native_col, diameter_bin_col, instructions):
    filtered = df.copy()

    species_text = instructions.get("species_text")
    native_text = instructions.get("native_text")
    diameter_bin_text = instructions.get("diameter_bin_text")

    if species_text and species_col:
        filtered = filtered[
            filtered[species_col]
            .astype(str)
            .str.contains(str(species_text), case=False, na=False)
        ]

    if native_text and native_col:
        filtered = filtered[
            filtered[native_col]
            .astype(str)
            .str.contains(str(native_text), case=False, na=False)
        ]

    if diameter_bin_text and diameter_bin_col:
        filtered = filtered[
            filtered[diameter_bin_col]
            .astype(str)
            .str.contains(str(diameter_bin_text), case=False, na=False)
        ]

    return filtered


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

    center_lat = map_df[lat_col].mean()
    center_lon = map_df[lon_col].mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=11)

    for _, row in map_df.iterrows():
        popup_text = []

        for col in popup_cols:
            if col and col in row:
                popup_text.append(f"{col}: {row[col]}")

        folium.CircleMarker(
            location=[row[lat_col], row[lon_col]],
            radius=3,
            popup="<br>".join(popup_text),
            fill=True
        ).add_to(m)

    return m


def build_analysis(df, filtered_df, question, instructions, species_col, native_col, diameter_bin_col, coord_rows):
    intent = instructions.get("intent", "summary")
    total_rows = len(df)
    matching_count = len(filtered_df)

    if total_rows > 0:
        percent_of_dataset = round((matching_count / total_rows) * 100, 1)
    else:
        percent_of_dataset = 0.0

    filters = []

    if instructions.get("species_text") and species_col:
        filters.append(f"{species_col} contains '{instructions.get('species_text')}'")

    if instructions.get("native_text") and native_col:
        filters.append(f"{native_col} equals '{instructions.get('native_text')}'")

    if instructions.get("diameter_bin_text") and diameter_bin_col:
        filters.append(f"{diameter_bin_col} contains '{instructions.get('diameter_bin_text')}'")

    if not filters:
        filters.append("No filters applied")

    table_df = None
    preview_df = None

    if intent == "top_species" and species_col:
        table_df = (
            filtered_df[species_col]
            .astype(str)
            .value_counts()
            .head(10)
            .reset_index()
        )
        table_df.columns = ["Species", "Count"]

        if len(table_df) > 0:
            top_species = table_df.iloc[0]["Species"]
            top_count = int(table_df.iloc[0]["Count"])
            verified_summary = (
                f"The most common species in the matching records is {top_species}, "
                f"with {top_count:,} records. The analysis used {matching_count:,} "
                f"matching records out of {total_rows:,} total records."
            )
        else:
            verified_summary = "No matching species records were found."

    elif intent == "native_summary" and native_col:
        table_df = (
            filtered_df[native_col]
            .astype(str)
            .value_counts()
            .reset_index()
        )
        table_df.columns = ["Native status", "Count"]

        verified_summary = (
            f"There are {matching_count:,} matching tree records, which is "
            f"{percent_of_dataset}% of the full dataset. The filters used were: "
            f"{'; '.join(filters)}."
        )

    elif intent == "diameter_summary" and diameter_bin_col:
        table_df = (
            filtered_df[diameter_bin_col]
            .astype(str)
            .value_counts()
            .reset_index()
        )
        table_df.columns = ["Diameter bin", "Count"]

        if len(table_df) > 0:
            top_bin = table_df.iloc[0]["Diameter bin"]
            top_count = int(table_df.iloc[0]["Count"])
            verified_summary = (
                f"The largest diameter group is '{top_bin}', with {top_count:,} records. "
                f"The diameter-bin summary is based on {matching_count:,} matching records."
            )
        else:
            verified_summary = "No diameter-bin records were found."

    else:
        table_df = pd.DataFrame([
            {"Metric": "Matching records", "Value": f"{matching_count:,}"},
            {"Metric": "Total records in dataset", "Value": f"{total_rows:,}"},
            {"Metric": "Percent of dataset", "Value": f"{percent_of_dataset}%"},
            {"Metric": "Filters used", "Value": "; ".join(filters)}
        ])

        verified_summary = (
            f"There are {matching_count:,} matching tree records, which is "
            f"{percent_of_dataset}% of the full dataset. The filters used were: "
            f"{'; '.join(filters)}."
        )

        if matching_count > 0:
            preview_df = filtered_df.head(int(instructions.get("limit", 1000)))

    if instructions.get("make_map"):
        if coord_rows == 0:
            verified_summary += (
                " This CSV does not contain usable latitude and longitude values, "
                "so the matching records cannot be displayed on a map."
            )

    payload = {
        "question": question,
        "intent": intent,
        "matching_record_count": int(matching_count),
        "total_dataset_rows": int(total_rows),
        "percent_of_dataset": percent_of_dataset,
        "filters_used": filters,
        "verified_summary": verified_summary,
        "map_requested": bool(instructions.get("make_map")),
        "coordinate_rows_in_dataset": int(coord_rows),
        "important_table": table_df.head(12).to_dict(orient="records") if table_df is not None else []
    }

    return table_df, preview_df, payload


def ask_ai_to_explain_result(payload, model_name):
    """
    The model explains facts that Python already calculated.
    If the model response looks unreliable, the app uses the verified summary instead.
    """
    prompt = f"""
You are a forestry data assistant explaining CSV analysis results to a nontechnical supervisor.

Use only the verified facts below.
Do not invent facts.
Do not recalculate numbers.
Do not say "forest surveyed"; say "CSV dataset" or "tree dataset."
Mention missing coordinate data only if map_requested is true.

Write 2 to 4 plain-English sentences.

Verified facts:
{json.dumps(payload, indent=2)}
"""

    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response["message"]["content"].strip()

        forbidden_phrases = [
            "over 99%",
            "almost all",
            "forest surveyed"
        ]

        lowered = text.lower()

        if any(phrase in lowered for phrase in forbidden_phrases):
            return payload["verified_summary"]

        expected_count = str(payload["matching_record_count"])
        text_no_commas = text.replace(",", "")

        if expected_count not in text_no_commas:
            return payload["verified_summary"]

        return text

    except Exception:
        return payload["verified_summary"]


st.set_page_config(page_title="Tree AI Demo", layout="wide")

st.title("Tree AI Demo")
st.write("This demo uses a local AI model to interpret questions, query a tree CSV, and explain the results.")

csv_files = get_tree_csv_files()

if not csv_files:
    st.error("No tree CSV files found. Put your tree CSV file inside the data folder.")
    st.stop()

csv_choice = st.sidebar.selectbox(
    "Choose tree CSV",
    csv_files,
    format_func=lambda x: x.name
)

df = load_csv(csv_choice)
columns = list(df.columns)

species_col_guess = find_column(columns, ["common_name", "species", "scientific_name"])
native_col_guess = find_column(columns, ["native"])
diameter_bin_col_guess = find_column(columns, ["diameter_breast_height_binned_CM"])
lat_col_guess = find_column(columns, ["latitude_coordinate", "latitude", "lat"])
lon_col_guess = find_column(columns, ["longitude_coordinate", "longitude", "lon"])

st.sidebar.header("Detected columns")

species_col = st.sidebar.selectbox(
    "Species column",
    [None] + columns,
    index=([None] + columns).index(species_col_guess) if species_col_guess in columns else 0
)

native_col = st.sidebar.selectbox(
    "Native column",
    [None] + columns,
    index=([None] + columns).index(native_col_guess) if native_col_guess in columns else 0
)

diameter_bin_col = st.sidebar.selectbox(
    "Diameter bin column",
    [None] + columns,
    index=([None] + columns).index(diameter_bin_col_guess) if diameter_bin_col_guess in columns else 0
)

lat_col = st.sidebar.selectbox(
    "Latitude column",
    [None] + columns,
    index=([None] + columns).index(lat_col_guess) if lat_col_guess in columns else 0
)

lon_col = st.sidebar.selectbox(
    "Longitude column",
    [None] + columns,
    index=([None] + columns).index(lon_col_guess) if lon_col_guess in columns else 0
)

installed_models = get_installed_ollama_models()

default_model_index = 0
if "qwen2.5:3b" in installed_models:
    default_model_index = installed_models.index("qwen2.5:3b")

st.sidebar.header("AI model")

model_name = st.sidebar.selectbox(
    "Ollama model",
    installed_models,
    index=default_model_index
)

st.subheader("Dataset overview")

if lat_col and lon_col:
    coord_rows = df[[lat_col, lon_col]].dropna().shape[0]
else:
    coord_rows = 0

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Rows", f"{len(df):,}")

with col2:
    st.metric("Columns", len(df.columns))

with col3:
    st.metric("Rows with coordinates", f"{coord_rows:,}")

with st.expander("Preview data"):
    st.dataframe(df.head(25))

st.subheader("Ask a question")

question_text = st.text_area(
    "Ask one or more questions. Separate multiple questions with punctuation.",
    value="How many oak trees are there? Show native trees. What are the diameter bins?",
    height=100
)

if st.button("Run"):
    questions = split_questions(question_text)

    if not questions:
        st.warning("Please enter a question.")
        st.stop()

    for question in questions:
        st.divider()
        st.subheader(f"Question: {question}")

        instructions = ask_ai_for_instructions(question, columns, model_name)

        with st.expander("AI interpretation"):
            st.json(instructions)

        filtered_df = apply_filters(
            df,
            species_col,
            native_col,
            diameter_bin_col,
            instructions
        )

        table_df, preview_df, payload = build_analysis(
            df=df,
            filtered_df=filtered_df,
            question=question,
            instructions=instructions,
            species_col=species_col,
            native_col=native_col,
            diameter_bin_col=diameter_bin_col,
            coord_rows=coord_rows
        )

        explanation = ask_ai_to_explain_result(payload, model_name)

        st.markdown("### Plain-English answer")
        st.write(explanation)

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
                    st.warning(
                        "No usable coordinates found for this result. "
                        "The selected CSV has 0 usable latitude/longitude values, so it cannot be mapped."
                    )
                else:
                    st_folium(m, width=1000, height=600)
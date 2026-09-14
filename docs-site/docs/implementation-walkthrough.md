---
id: implementation-walkthrough
title: 2. Implementation walkthrough
slug: /implementation-walkthrough
description: A supervisor-ready explanation of how Canopy evolved from CSV and JSON files into a local SQL and spatial-data knowledge base.
sidebar_position: 2
---

# 2. Implementation walkthrough

This section explains the changes made to Canopy, why each change was needed, how it was implemented, and how to demonstrate that it works. It is written so it can be used as the basis of a supervisor presentation.

## Short explanation for a supervisor

> I started Canopy as a question-answering interface over CSV and JSON files. That was useful for prototyping, but the data was loaded into memory for each run, query behavior was difficult to prove, and chat history existed only in the current Streamlit session. I changed the architecture so tabular data is synchronized into a local SQLite database and questions are converted into constrained, parameterized SQL queries. I then added persistent SQLite chat tables, imported realistic FVS stand outputs with their complete shapefile, and connected those stands to a packaged TreeMap raster through `TM_Value`. Canopy can now return evidence as SQL results, acreage-weighted charts, stand polygons, and matching raster cells while using a local Qwen model only to interpret or explain verified data.

## Before and after

| Earlier prototype | Current Canopy implementation |
|---|---|
| CSV and JSON read directly for each session | CSV attributes synchronized into local SQLite tables |
| Filtering mainly performed in pandas | Parameterized SQL used for deterministic filtering |
| Answers were difficult to audit | Interface exposes SQL, parameters, table, database path, and returned row count |
| Chat messages lived in Streamlit session state | Chats and structured query specifications persist in SQLite |
| Raster was treated mainly as a standalone TIFF | Complete TreeMap package includes TIFF, VAT DBF, metadata XML, auxiliary XML, and world file |
| No realistic stand-simulation geometry | FVS CSV and complete shapefile package provide one polygon per stand |
| Inventory CSV questions only | FVS age, acreage, composition, density, volume, polygon, and raster questions |
| Model could appear to be the source of an answer | Database and spatial files provide facts; the local model explains verified results |

## Change 1: moving tabular data into SQLite

### Why this was changed

CSV is a useful exchange format, but it is not a query engine. Reading a CSV into memory does not by itself prove that SQL is being used, and repeatedly filtering large tables in application code makes it harder to reproduce an answer.

### How it was implemented

When a CSV dataset is selected, Canopy:

1. reads the source table with pandas;
2. creates a safe SQLite table name from the filename;
3. synchronizes the dataframe into `storage/canopy.sqlite`;
4. records the import in `dataset_registry`; and
5. reruns the synchronization only when the source signature or table dimensions change.

The registry records the source name, SQL table name, row count, column count, file size, modification time, and synchronization time. For the FVS package, the resulting table is `dataset_fvs_output_07222026` with 20,069 rows and 40 source columns.

### How questions become SQL

Canopy does not give the language model unrestricted access to execute arbitrary SQL. The question is converted into a structured specification containing:

- an allow-listed column;
- an allow-listed comparison operator;
- a separately bound value;
- an output intent such as summary, count, chart, stand map, or raster map; and
- a display limit that does not change the calculation totals.

For the question:

```text
Show stands older than 60 with TCuFt above 3000
```

Canopy executes:

```sql
SELECT *
FROM "dataset_fvs_output_07222026"
WHERE "Age" > ? AND "TCuFt" > ?
ORDER BY "MU_ID"
```

with these values bound separately:

```json
[60.0, 3000.0]
```

This separation makes the result deterministic and avoids treating user text as executable SQL.

### How to prove this change

Open **SQL and data proof** under an answer. It shows:

- the absolute `canopy.sqlite` database path;
- the SQLite table name;
- the executed query;
- the bound parameters; and
- the number of SQL rows returned.

The executable checks in `verify_integration.py` and `verify_fvs_integration.py` independently compare source and SQL row counts.

## Change 2: saving chat history permanently

### Earlier behavior

Streamlit session state kept a conversation only while that application session remained active. Closing or restarting the application could lose the visible conversation.

### Current behavior

Canopy stores conversations in two SQLite tables:

```text
chat_conversations
  id                   primary key
  dataset_key          identifies the selected dataset
  title
  created_at
  updated_at

chat_messages
  conversation_id + position   composite primary key
  message_blob         compressed role, text, and query specification
  created_at
```

Each dataset has its own conversation history. An inventory conversation, FVS conversation, and raster conversation do not overwrite one another.

For calculated FVS responses, Canopy stores the small query specification rather than storing a large dataframe or map image. When a saved chat is reopened, the query is executed again and its chart or map is reconstructed from the source data. This makes the history both persistent and reproducible.

### How to prove this change

1. Ask an FVS question.
2. Note the **Saved in SQLite** count in the sidebar.
3. stop and restart Streamlit;
4. select the same dataset and chat title; and
5. show that the previous question and reconstructed result are still present.

This exact reload test was performed with “Chart the sum of acres by age.”

## Change 3: importing the complete FVS output package

### What was imported

The supervisor's ZIP contains both the attribute table and the parts of one ESRI shapefile:

```text
FVS_output_07222026.csv       queryable stand attributes
FVS_output_07222026.shp       polygon geometry
FVS_output_07222026.shx       shape index
FVS_output_07222026.dbf       shapefile attribute records
FVS_output_07222026.prj       coordinate reference system
FVS_output_07222026.cpg       text encoding
FVS_output_07222026.sbn/.sbx  spatial indexes
FVS_output_07222026.*.xml     metadata and lineage
schema.ini                    CSV field interpretation
```

These are not extra TIFF files. They are companion parts of the shapefile and should remain together. Canopy preserves the complete package under `data/fvs/`.

### What the data contains

- 20,069 stand rows;
- 20,069 unique `MU_ID` values;
- 873,483.45 total acres;
- stand ages from 0 to 145;
- Coniferous, Mixed, and Deciduous composition classes;
- Young, Intermediate, Mature, and Old age classes; and
- 315 distinct TreeMap profile codes.

Useful measures include `Age`, `Acres`, `TCuFt`, `Tpa`, `BA`, `SDI`, `TopHt`, ownership, mortality, and growth fields.

### The polygon join

`MU_ID` is the unique stand identifier in both the FVS attribute data and shapefile records:

```text
SQLite result row -- MU_ID --> shapefile stand polygon
```

When a map is requested, Canopy collects the matching `MU_ID` values, reads those shapes, transforms the geometry from `EPSG:5070` to web-map coordinates (`EPSG:4326`), and adds the polygons to a Folium map. Tooltips display the stand identifier and selected attributes.

The table and totals use every matching SQL row. To keep the browser responsive, the interactive map draws at most the first 500 matching polygons and states this limit below the map.

## Change 4: producing the supervisor's age distribution

The requested chart is not a count of stands. It is an area-weighted distribution:

```text
group rows by exact Age
        |
        v
sum Acres within each Age
        |
        v
bar chart: x = Age, y = Sum of Acres
```

This distinction matters because stands have different areas. Counting rows would give every stand equal weight and would not reproduce the supervisor's “Sum of Acres by Age” example.

The result also provides a way to diagnose the reported age bias: unusually tall acreage bars show ages that were assigned to disproportionately large areas. Canopy visualizes that issue; it does not claim to correct the Leto/FIA sampling bias.

## Change 5: using the complete TreeMap raster package

### Files being used

Canopy uses the complete directory under `rasters/TreeMap_2022/`:

```text
TreeMap_2022.tif              actual categorical raster cells
TreeMap_2022.tfw              world file
TreeMap_2022.tif.aux.xml      auxiliary ArcGIS/GDAL metadata
TreeMap_2022.tif.xml          product metadata and lineage
TreeMap_2022.tif.vat.dbf      raster value-attribute table
```

The GeoTIFF is a one-band, 4,381 × 3,596 raster in `EPSG:5070`. It contains 4,918,259 valid pixels and 693 distinct categorical values.

The VAT DBF contains one record per raster value and fields such as forest type, canopy percentage, stand height, live trees per acre, volume, biomass, and carbon.

### The raster join

The FVS-to-raster relationship is:

```text
FVS stand row -- TM_Value --> TreeMap Band 1 Value
```

All 315 `TM_Value` codes in the supplied FVS output occur in the TreeMap raster. The raster has 693 codes overall, so the FVS run represents a subset of the profiles available in the raster.

`MU_ID` should not be used as the raster join. `MU_ID` identifies a stand polygon, while `TM_Value` identifies a modeled TreeMap/FIA plot profile.

### How the raster visualization is created

For a question such as:

```text
Visualize the TreeMap raster for stands older than 60
```

Canopy:

1. runs the age filter in SQLite;
2. collects distinct `TM_Value` codes from the matching rows;
3. creates a categorical mask where raster Band 1 matches those codes;
4. downsamples for browser performance using nearest-neighbor resampling;
5. reprojects the display mask from `EPSG:5070` to `EPSG:4326`;
6. produces a transparent green image overlay; and
7. displays it with matching FVS polygons on a Folium map.

Nearest-neighbor resampling is important because `TM_Value` is a category code. Bilinear interpolation would create codes that do not exist.

### Interpretation limitation

Several stands can share one `TM_Value`. Age is consistent within the supplied profile groups, but composition and volume can vary among stands sharing a profile. The green overlay therefore means “these pixels use a TreeMap profile selected by the SQL result.” It does not mean a raster cell has a unique FVS `MU_ID`.

If a future map colors cells by a varying value such as `TCuFt`, the aggregation must be stated—for example, acreage-weighted mean `TCuFt` for each `TM_Value`.

## Change 6: clarifying the local Qwen model's responsibility

The preferred model is `qwen2.5:3b`, run locally with Ollama. It was selected because it performed well for this project's questions while remaining small enough for local use.

The model is not used as a replacement for the database:

```text
Question -> constrained query -> verified SQL result -> Qwen explanation
```

For FVS data, the deterministic parser and SQLite perform the filter. Qwen receives only the question, applied filters, verified summary figures, and limited composition counts. If Ollama is unavailable, Canopy can still execute SQL and produce a deterministic summary, chart, and map.

### Fixing the command-not-found problem

The original terminal errors occurred because `python`, `pip`, and `streamlit` were not available as global shell commands and the expected `.venv` did not exist in that project directory.

The PERSEUS project now includes its own native macOS virtual environment, project-local Ollama runtime, Qwen model files, and launcher. `run_canopy.sh`:

1. resolves the project directory;
2. uses `.venv/bin/streamlit` and `tools/Ollama.app/Contents/Resources/ollama` explicitly;
3. starts the local Ollama service when it is not already responding;
4. waits until the service is ready; and
5. starts Streamlit with `qwen2.5:3b` available.

The model was tested with a real local generation request, not only by checking its filename.

### Fixes found during the live raster test

The exact question “Visualize the TreeMap raster for stands older than 60” originally produced its map and then terminated Streamlit. The macOS crash report located the native failure in the PyArrow conversion used by Streamlit's dataframe renderer. FVS result tables and acreage charts now use the small `safe_streamlit_render.py` HTML renderer, removing PyArrow from that result-display path while keeping the SQL result unchanged.

The external drive also created hidden AppleDouble files such as `._FVS_output_07222026.csv`. That file is binary metadata, not a CSV, and caused a UTF-8 decoding error when selected. Dataset discovery now rejects every filename beginning with `._`, so future sidecars cannot appear as datasets.

Finally, `starlette==0.49.3` is pinned because Streamlit 1.57's server is incompatible with Starlette 1.4's changed compression constructor. These fixes were verified by submitting the exact raster question: 4,222 stands, 187,021.4 acres, mean age 78.9 years, and estimated volume 381,323,326 cubic feet, with the server still healthy afterward.

## Change 7: adding project documentation

A Docusaurus website was added under `docs-site/`. It contains:

- Section 1: purpose, repository, local LLM, and high-level architecture;
- this implementation walkthrough;
- the FVS and TreeMap data guide;
- SQL and chat-persistence architecture; and
- local setup instructions.

The documentation reuses the supervisor's example maps and age chart as scientific figures. TypeScript checking and a production Docusaurus build are part of verification.

## File-by-file summary

| File or directory | Change |
|---|---|
| `app.py` | Adds the FVS dataset type and routes it to the FVS interface while retaining inventory CSV and raster modes |
| `fvs_integration.py` | Implements safe query specifications, SQL generation, age/acres aggregation, shapefile transformation, raster masking, and Folium map construction |
| `fvs_streamlit.py` | Implements FVS metrics, chat controls, charts, result tables, maps, SQL proof, suggestions, and history reconstruction |
| `safe_streamlit_render.py` | Renders FVS tables and bar charts without the native PyArrow path that caused the macOS segmentation fault |
| `data/fvs/` | Preserves the complete FVS CSV and shapefile package |
| `rasters/TreeMap_2022/` | Preserves the complete raster and companion metadata/VAT package |
| `storage/canopy.sqlite` | Stores synchronized dataset tables, registry records, and persistent chats |
| `run_canopy.sh` | Starts the project-local Ollama and Streamlit executables |
| `requirements.txt` | Adds explicit numerical, image, raster, projection, and shapefile dependencies |
| `verify_integration.py` | Checks general CSV-to-SQL, chat, and raster integration |
| `verify_fvs_integration.py` | Checks FVS rows, SQL queries, shapefile join, raster codes, VAT fields, and saved FVS chat evidence |
| `docs-site/` | Docusaurus documentation source and production build configuration |

## Verification results

The completed checks verify:

- 20,069 source FVS rows equal 20,069 SQLite rows;
- all `MU_ID` values are unique;
- the shapefile also contains 20,069 records;
- the GeoTIFF is readable as `EPSG:5070`, 4,381 × 3,596, one-band `int32` data;
- all 315 FVS raster codes occur in TreeMap Band 1;
- the VAT describes all 693 raster codes;
- example questions produce parameterized SQL results;
- the age/acres chart renders through the live Streamlit interface;
- a saved FVS question remains after reload;
- `qwen2.5:3b` generates a local response; and
- Docusaurus passes TypeScript and production-build checks.

## Suggested supervisor demonstration

### 1. Establish the purpose

Say:

> Canopy is not training a new forestry model. It is a local knowledge and analysis layer over existing inventory, simulation, and spatial data.

### 2. Prove the SQL integration

Ask:

```text
Show stands older than 60 with TCuFt above 3000
```

Open **SQL and data proof** and show the SQL text and separately bound values.

### 3. Reproduce the requested chart

Ask:

```text
Chart the sum of acres by age
```

Explain that the y-axis is summed stand acreage rather than the number of rows.

### 4. Prove the vector join

Ask:

```text
Map old hardwood stands
```

Hover over polygons and point out that `MU_ID` is the stand identity used for the join.

### 5. Prove the raster join

Ask:

```text
Visualize the TreeMap raster for MU_ID 4
```

Explain that the stand is found through `MU_ID`, while its related raster cells are found through `TM_Value`.

### 6. Prove persistence

Open a previous chat, restart Canopy, and show that the question and reconstructed result remain available.

## Concise statement of contribution

> My main contribution was changing Canopy from a temporary CSV demonstration into a reproducible local data system. I added a real SQLite query layer and proof view, persistent chat history, realistic FVS stand and shapefile support, a validated link to the complete TreeMap raster package, natural-language charts and maps, local Qwen integration, automated verification, and maintainable Docusaurus documentation. The result is a system where the language model improves usability, but the forestry data, SQL, and spatial joins remain inspectable and defensible.

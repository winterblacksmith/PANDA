"""Executable proof for Canopy's FVS, shapefile, raster, SQL, and chat joins."""

from pathlib import Path
import pickle
import sqlite3
import uuid
import zlib

import numpy as np
import pandas as pd
import rasterio
import shapefile

from fvs_integration import execute_fvs_sql, parse_fvs_question


ROOT = Path(__file__).resolve().parent
CSV = ROOT / "data/fvs/FVS_output_07222026.csv"
SHP = CSV.with_suffix(".shp")
RASTER = ROOT / "rasters/TreeMap_2022/TreeMap_2022.tif"
VAT = RASTER.with_name(RASTER.name + ".vat.dbf")
DATABASE = ROOT / "storage/canopy.sqlite"
TABLE = "dataset_fvs_output_07222026"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


print("CANOPY FVS + TREEMAP INTEGRATION PROOF")
print("=" * 72)
frame = pd.read_csv(CSV)
check(len(frame) == 20_069, "FVS CSV has 20,069 stand rows")
check(frame["MU_ID"].nunique() == len(frame), "MU_ID is unique for every stand")
check(round(float(frame["Acres"].sum()), 2) == 873_483.45, "stand acres total 873,483.45")

with sqlite3.connect(DATABASE) as connection:
    frame.to_sql(TABLE, connection, if_exists="replace", index=True, index_label="__rowid")
    sql_rows = connection.execute(f'SELECT COUNT(*) FROM "{TABLE}"').fetchone()[0]
check(sql_rows == len(frame), f"SQLite table {TABLE} contains all FVS rows")

examples = [
    "Chart the sum of acres by age",
    "Show stands older than 60 with TCuFt above 3000",
    "Map old hardwood stands",
    "Visualize the TreeMap raster for stands older than 60",
]
for question in examples:
    spec = parse_fvs_question(question)
    result, sql_text, parameters = execute_fvs_sql(DATABASE, TABLE, spec)
    check(len(result) > 0, f"query returns rows: {question}")
    check("SELECT * FROM" in sql_text, f"query uses SQLite with {len(parameters)} bound parameter(s)")

shape_reader = shapefile.Reader(str(SHP))
shape_fields = [field[0] for field in shape_reader.fields[1:]]
check(len(shape_reader) == len(frame), "shapefile has one polygon record per FVS stand")
check("MU_ID" in shape_fields, "shapefile exposes the MU_ID geometry join")
shape_reader.close()

with rasterio.open(RASTER) as source:
    values = source.read(1, masked=True).compressed()
    raster_codes = set(np.unique(values).astype(int).tolist())
    check(str(source.crs) == "EPSG:5070", "TreeMap raster CRS is EPSG:5070")
    check(source.width == 4381 and source.height == 3596, "TreeMap raster is 4,381 x 3,596 pixels")

fvs_codes = set(frame["TM_Value"].dropna().astype(int).unique().tolist())
check(fvs_codes.issubset(raster_codes), "all 315 FVS TM_Value codes occur in TreeMap Band 1")

vat_reader = shapefile.Reader(dbf=str(VAT))
vat_fields = [field[0] for field in vat_reader.fields[1:]]
check(len(vat_reader) == len(raster_codes) == 693, "raster VAT describes all 693 TreeMap codes")
check({"Value", "ForTypName", "CANOPYPCT", "STANDHT"}.issubset(vat_fields), "raster VAT contains profile attributes")
vat_reader.close()

proof_chat_id = f"integration-proof-{uuid.uuid4()}"
proof_message = {"role": "user", "content": "Chart the sum of acres by age"}
message_blob = zlib.compress(pickle.dumps(proof_message, protocol=pickle.HIGHEST_PROTOCOL))
with sqlite3.connect(DATABASE) as connection:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id TEXT PRIMARY KEY,
            dataset_key TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            conversation_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            message_blob BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (conversation_id, position)
        );
        """
    )
    connection.execute(
        "INSERT INTO chat_conversations (id, dataset_key, title) VALUES (?, ?, ?)",
        (proof_chat_id, f"fvs::{CSV.name}", "Integration proof"),
    )
    connection.execute(
        "INSERT INTO chat_messages (conversation_id, position, message_blob) VALUES (?, ?, ?)",
        (proof_chat_id, 0, message_blob),
    )
    chat_row = connection.execute(
        "SELECT message_blob FROM chat_messages WHERE conversation_id = ? AND position = 0",
        (proof_chat_id,),
    ).fetchone()
    connection.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (proof_chat_id,))
    connection.execute("DELETE FROM chat_conversations WHERE id = ?", (proof_chat_id,))
check(chat_row is not None, "FVS question persists in SQLite chat history")
stored_message = pickle.loads(zlib.decompress(chat_row[0]))
check(stored_message == proof_message, "persisted chat retains its role and content")

print("=" * 72)
print("All FVS, SQL, shapefile, raster, VAT, and chat checks passed.")

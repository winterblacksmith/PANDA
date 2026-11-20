---
id: dataset-library
title: Dataset library and storage
description: How datasets are added, chosen for analysis, and where PANDA stores uploads, chats and usage on Railway.
last_update:
  date: 2026-11-20
---

# Dataset library and storage

PANDA keeps every dataset it can analyze in one **library**. Open it from the
sidebar with **Dataset library**, then press **Analyze** on the dataset you want.
The sidebar card shows which dataset is being analyzed.

## Built-in and uploaded datasets

| Source | Where it lives | Can be deleted in the app |
| --- | --- | --- |
| Built-in | `data/` and `rasters/` in the app image | No |
| Uploaded | `<PANDA_STORAGE_DIR>/library/` | Yes (with confirmation) |

Uploads are grouped by file name, so companion files travel with their dataset:

- **CSV table**: `trees.csv`
- **FVS stands with polygons**: `stands.csv` plus `stands.shp`, `stands.shx`, `stands.dbf`
  (and optional `.prj`, `.cpg`). Upload them together; the shapefile enables stand maps.
- **Raster**: `map.tif` plus optional `map.tfw`, `map.tif.aux.xml`, `map.tif.vat.dbf`.

Files keep their original names because shapefile and GDAL readers rely on them.
Uploads are limited to 200 MB per file.

## What the model knows about the selected dataset

When a dataset is selected, PANDA builds a short profile for the model: the
row count, every column with its type, numeric ranges and averages, and the
most common text values. For FVS data it also lists what PANDA's tools can
compute. No raw rows are sent. This lets the model answer "what columns do we
have?" or explain an analysis without asking you to confirm columns that exist.
Counts, charts and maps still come from PANDA's verified SQL and Python tools.

## Where data is stored

Everything PANDA writes goes under `PANDA_STORAGE_DIR` (`/app/storage` in the
Docker image). Nothing is stored on Irene.

| File or folder | Contents |
| --- | --- |
| `canopy.sqlite` | Saved chats and the query tables built from datasets |
| `library/` | Uploaded datasets |
| `llm_usage.sqlite` | Daily model request and token counts (no text) |

On Railway, attach a **volume** to the PANDA service with mount path
`/app/storage`. Without one, the container's disk is replaced on every
redeploy and uploads, chats and usage counts are lost. The library dialog shows
a warning when the storage folder is not on a volume (detected from Railway's
`RAILWAY_VOLUME_MOUNT_PATH`).

## Version

The running version is shown in the bottom-right corner (for example
"PANDA v1.1") and is set in `version.py`.

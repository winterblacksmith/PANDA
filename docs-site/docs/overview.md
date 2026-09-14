---
id: overview
title: 1. Canopy overview
slug: /overview
description: Purpose, repository, local language model, and data flow for Canopy.
sidebar_position: 1
---

# 1. Canopy overview

Canopy is a local-first AI knowledge base for forestry, tree inventory, forest simulation, and spatial data. It turns a natural-language question into an inspectable data operation and returns evidence as text, tables, charts, stand polygons, or raster maps.

## Purpose

Forestry projects often distribute related information across CSV files, JSON, spatial databases, shapefiles, and rasters. Canopy gives those sources one question-and-answer interface while keeping calculations deterministic and visible.

Canopy is designed to:

- answer questions about existing forestry data rather than rely on the model's memory;
- use parameterized SQLite queries for repeatable filtering and aggregation;
- visualize records when point, polygon, or raster geometry is available;
- run the language model locally through Ollama; and
- save conversations in SQLite so they survive a browser refresh or application restart.

Canopy is not the Forest Vegetation Simulator (FVS) itself. It reads and explains results produced by FVS and related stand-creation workflows such as Leto.

## Repository

The source code and project history are in the [Canopy GitHub repository](https://github.com/winterblacksmith/tree_ai_demo).

The Streamlit application starts in `app.py`. Specialized FVS query and visualization logic lives in `fvs_integration.py` and `fvs_streamlit.py`. This documentation website lives in `docs-site/` and is built with Docusaurus.

## Local LLMs

Canopy uses [Ollama](https://ollama.com/) to run models on the same computer as the application. The preferred model in this project is `qwen2.5:3b`, a small Qwen model that balances response quality with local memory and speed.

The model is deliberately not the database. For FVS questions, Canopy first creates a constrained query specification, executes parameterized SQL, and gives Qwen only verified result facts to explain. If Ollama is unavailable, the SQL, charts, maps, and deterministic summary still work.

:::info Local-first boundary
Dataset rows and query results stay on the local machine. Installing packages or downloading an Ollama model requires internet access, but ordinary Canopy questions do not need a hosted model API.
:::

## How data moves

```text
Natural-language question
          |
          v
Constrained intent + filters
          |
          v
Parameterized SQLite query  <---- CSV / FVS attribute table
          |
          +----------------------> result table + chart
          |
          +-- MU_ID -------------> stand polygon in shapefile
          |
          +-- TM_Value ----------> TreeMap Band 1 raster cells
          |
          v
Verified facts --> local qwen2.5:3b explanation
          |
          v
Saved chat + query proof in storage/canopy.sqlite
```

The important separation is between language and evidence: the local LLM makes the interaction conversational, while SQLite and the spatial files provide the answerable facts.

## Current data sources

| Source | Role in Canopy | How it is addressed |
|---|---|---|
| Tree inventory CSVs | Individual inventory records | Inferred column roles and SQLite table |
| FVS output CSV | One row per simulated stand | Unique `MU_ID` and parameterized SQL |
| FVS shapefile package | Stand boundary geometry | Attribute join on `MU_ID` |
| TreeMap GeoTIFF | 30 × 30 m modeled forest pixels | Band 1 code linked through `TM_Value` |
| TreeMap raster VAT DBF | Meaning and attributes of raster codes | Raster `Value` / TreeMap profile lookup |
| SQLite | Query engine, registry, and saved chats | `storage/canopy.sqlite` |

Continue with [FVS and TreeMap data](./data/fvs-treemap) for the exact joins and limitations.

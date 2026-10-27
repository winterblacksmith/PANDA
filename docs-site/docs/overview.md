---
id: overview
title: PANDA overview
slug: /overview
description: Purpose, scope, repository, model, and data flow for PANDA.
sidebar_position: 1
---

# PANDA overview

**PANDA** stands for **PERSEUS AI for Natural-language Data Analysis**. It is a forestry-focused interface for asking natural-language questions about inventory tables, forest simulation results, stand polygons, and raster datasets.

## Project purpose

Forestry data is often distributed across CSV files, databases, shapefiles, and rasters. PANDA brings those sources into one conversational interface while keeping the calculations inspectable.

PANDA is designed to:

- translate natural-language questions into constrained data operations;
- use SQLite for reproducible filtering and aggregation;
- visualize point, polygon, and raster results;
- preserve chat history across application restarts;
- use a local Qwen model for conversational explanations; and
- expose enough evidence to show where every result came from.

PANDA is not FVS and does not train a new forestry model. It reads, filters, visualizes, and explains outputs produced by FVS, TreeMap, tree inventories, and related workflows.

## Repository

The project is maintained in the [PANDA GitHub repository](https://github.com/winterblacksmith/PANDA). The application lives at the repository root and this Docusaurus website lives in `docs-site/`.

## Language model

The preferred model is `qwen2.5:3b`, served by Ollama. It can run locally or on Irene's NVIDIA GPUs behind an authenticated FastAPI gateway. The model explains verified results; SQLite and the spatial files remain the source of factual calculations.

## Data flow

```text
Question
  -> constrained intent and filters
  -> parameterized SQLite query
  -> optional shapefile or TreeMap join
  -> verified table, total, chart, or map
  -> Qwen explanation
  -> persistent saved conversation
```

Continue with the [system architecture](./architecture/system-overview) or the [implementation walkthrough](./implementation-walkthrough).
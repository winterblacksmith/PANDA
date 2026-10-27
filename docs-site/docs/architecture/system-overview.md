---
id: system-overview
title: System architecture
description: How PANDA connects its interface, data layer, spatial tools, and local language model.
---

# System architecture

PANDA stands for **PERSEUS AI for Natural-language Data Analysis**. It is a forestry data assistant that separates conversational reasoning from evidence-producing calculations.

```text
User question
     |
     v
Streamlit interface
     |
     +--> SQLite query layer --> tables, totals, and charts
     |
     +--> spatial layer ------> points, stand polygons, and raster overlays
     |
     +--> model connector ----> authenticated FastAPI gateway
                                      |
                                      v
                              Ollama + qwen2.5:3b
                                      |
                                      v
                              natural-language explanation
```

## Main components

| Component | Responsibility |
|---|---|
| `app.py` | Streamlit application, dataset selection, and chat experience |
| `conversation.py` | Persistent conversations and messages |
| `model_connection.py` | Chooses the configured language-model connection |
| `fvs_integration.py` | FVS filtering, SQL evidence, vector joins, and raster masks |
| `inference_gateway/` | Authenticated FastAPI service in front of Ollama |
| `storage/canopy.sqlite` | Dataset registry, queryable tables, and chat history |
| `docs-site/` | This Docusaurus documentation website |

## Trust boundary

The LLM does not replace the database. PANDA first calculates answers with SQL and spatial code, then gives verified results to the model for explanation. This keeps numeric answers reproducible while preserving a natural conversational interface.

## Deployment shape

Railway hosts the public application. Irene hosts the private inference service and GPUs. Railway should call only the authenticated FastAPI gateway; Ollama itself should never be exposed directly to the public internet.
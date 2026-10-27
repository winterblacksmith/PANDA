---
id: project-handoff
title: Project handoff
description: A checklist for transferring PANDA to its next maintainer.
---

# Project handoff

## What PANDA currently provides

- Natural-language exploration of forestry tables and spatial datasets
- SQLite-backed filtering, aggregation, and persistent chat history
- FVS stand summaries and acreage-weighted charts
- Shapefile mapping through `MU_ID`
- TreeMap raster matching through `TM_Value`
- Local or remote Qwen generation through Ollama
- An authenticated FastAPI inference boundary
- Downloadable conversation reports

## Handoff checklist

- [ ] Confirm the authoritative GitHub branch and deployment branch.
- [ ] Record the Railway project owner and service names.
- [ ] Record the Irene administrator and operational contact.
- [ ] Rotate and transfer secrets through an approved password manager.
- [ ] Verify the current model and model storage volume.
- [ ] Run the automated and manual test checklist.
- [ ] Confirm backups for persistent application data.
- [ ] Review open limitations and the React migration plan.
- [ ] Confirm that no private data or secrets are committed to Git.

## Known architectural limitation

The current UI uses Streamlit, which reruns the Python script after interactions. The planned React migration separates a persistent browser interface from a FastAPI application backend so chat submission, map updates, and file selection can update independently without dimming and rerendering the whole page.

## Suggested next phase

1. Stabilize the Irene inference endpoint.
2. Add structured application monitoring and model latency metrics.
3. Move the chat interface to React while retaining the tested Python data services.
4. Add user authentication before allowing access to non-public datasets.
5. Expand evaluation prompts and regression tests as new forestry datasets are added.
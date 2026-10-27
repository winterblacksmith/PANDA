---
id: testing-troubleshooting
title: Testing and troubleshooting
description: Reproducible checks for PANDA's data, model, documentation, and deployment layers.
---

# Testing and troubleshooting

Test each layer independently before testing the entire application.

## Recommended order

1. Verify Python imports and unit tests.
2. Verify SQLite synchronization and saved chats.
3. Verify the FVS shapefile and TreeMap raster joins.
4. Verify Ollama lists `qwen2.5:3b`.
5. Verify the FastAPI gateway health and authenticated generation endpoints.
6. Verify Railway can reach the gateway.
7. Build the documentation site.

## Documentation checks

```bash
cd docs-site
npm install
npm run typecheck
npm run build
npm run start
```

## Common failures

| Symptom | Likely cause | Response |
|---|---|---|
| `command not found: streamlit` | Virtual environment is missing or inactive | Use the project's launcher or recreate the environment |
| CSV UTF-8 decoding error | A macOS `._` metadata sidecar was selected | Ignore files whose names begin with `._` |
| Ollama healthy, gateway restarting | Gateway application import or permission error | Inspect gateway logs and rebuild only the gateway |
| Model unavailable on Railway | Missing URL/token, blocked network path, or gateway down | Test each connection boundary separately |
| Raster metadata unavailable | Native GDAL/raster dependency missing | Install the system library required by Rasterio |

## Evidence to retain

For handoff, keep the test date, branch or commit, commands used, pass/fail result, and relevant non-secret log excerpt. Never copy access tokens into the test record.
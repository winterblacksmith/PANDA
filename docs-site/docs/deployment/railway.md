---
id: railway
title: Railway application deployment
description: Connect the hosted PANDA interface to its private inference gateway.
---

# Railway application deployment

Railway hosts PANDA's public-facing application. The application can still provide deterministic SQL and spatial results when the model is unavailable, but natural-language generation requires the Irene gateway.

## Required application variables

| Variable | Purpose |
|---|---|
| `PANDA_INFERENCE_URL` | HTTPS address of the FastAPI gateway |
| `PANDA_INFERENCE_TOKEN` | Shared bearer token accepted by the gateway |
| `PANDA_OLLAMA_MODEL` | Model name, currently `qwen2.5:3b` |
| `STREAMLIT_SERVER_ADDRESS` | Normally `0.0.0.0` on Railway |
| `STREAMLIT_SERVER_PORT` | Railway-provided port or application default |

Do not place secret values in screenshots, documentation, source code, or commit history.

## Connection flow

```text
Railway PANDA app
  -> HTTPS request + bearer token
  -> Irene FastAPI gateway
  -> private Ollama container
  -> qwen2.5:3b response
```

## Deployment check

1. Confirm the Railway service is healthy.
2. Confirm the inference variables exist without displaying their values.
3. Confirm the Irene gateway health endpoint responds through HTTPS.
4. Ask a general question that cannot be answered by a canned dataset response.
5. Check that PANDA reports the remote model as available.

## Failure behavior

If the gateway cannot be reached, PANDA should show a clear model-unavailable message and continue offering deterministic dataset summaries, SQL queries, charts, and maps.
---
id: irene-inference-gateway
title: Irene inference gateway
description: How Railway PANDA reaches the private Qwen model hosted on Irene.
---

# Irene inference gateway

PANDA separates the public application from model hosting:

```text
Browser
   |
   v
PANDA on Railway
   |  HTTPS + bearer token
   v
FastAPI gateway on Irene
   |  private Docker network
   v
Ollama + qwen2.5:3b on Irene GPUs
```

Railway stores only the gateway URL and a shared bearer token. Ollama is never
published directly to the internet. The gateway checks the token, accepts only
approved model names, limits message sizes and generation options, and forwards
valid requests to Ollama.

## Repository files

- `llm_client.py` chooses the authenticated gateway when
  `PANDA_INFERENCE_URL` is set and otherwise supports local Ollama.
- `inference_gateway/` contains the FastAPI service and non-root Docker image.
- `docker-compose.llm.yml` defines Ollama, model initialization, and the gateway.
- `docker-compose.irene.yml` enables Irene's NVIDIA GPUs.
- `scripts/local_llm.sh` starts, stops, inspects, and tests the stack.
- `LLM_INTEGRATION_WORKLOG.md` records implementation and verification commands.

## Required secrets

Create `.env.local-llm` on Irene from `.env.local-llm.example`. Use a long,
random `PANDA_INFERENCE_TOKEN`. Store the same value in Railway as a service
variable. Never commit the token, CARTO key, SSH credentials, or other secrets.

Railway requires:

```text
PANDA_INFERENCE_URL=https://your-approved-irene-gateway.example.edu
PANDA_INFERENCE_TOKEN=<secret>
PANDA_OLLAMA_MODEL=qwen2.5:3b
```

## Network boundary

The repository binds FastAPI to `127.0.0.1:8000` on Irene. Before Railway can
reach it, a UGA-approved HTTPS reverse proxy or tunnel must forward public HTTPS
traffic to that loopback address. Do not expose Ollama port `11434`. Coordinate
the hostname, TLS certificate, firewall, and service policy with the Irene
administrator.

## Verification stages

1. Validate the Compose configuration locally without starting Irene.
2. Start the stack on Irene only after each command is approved.
3. Test `/health`, authenticated `/v1/models`, and authenticated `/v1/chat`
   from inside the gateway container.
4. Test the approved HTTPS route from outside Irene.
5. Configure a Railway staging service and run PANDA's **Test model connection**.
6. Ask a multi-turn casual question and a forestry data question through the
   deployed interface before changing production.

The complete command history and observed results live in
`LLM_INTEGRATION_WORKLOG.md`.

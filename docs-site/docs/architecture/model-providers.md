---
id: model-providers
title: Model providers, fallback and usage
description: How PANDA chooses between Groq, Gemini and the local Qwen model, and how token usage and limits are shown.
last_update:
  date: 2026-11-20
---

# Model providers, fallback and usage

PANDA sends every model request (answers, FVS explanations, PDF summaries)
through one shared client, `llm_client.py`. That client tries providers in order
and uses the first one that returns a real answer.

```text
Question -> Groq (gpt-oss-120b, then gpt-oss-20b)
         -> Google Gemini (3.5 Flash-Lite, then 3.1 Flash-Lite, then 3.5 Flash)
         -> Local Qwen2.5:3b (Irene gateway, or Ollama on a developer's Mac)
```

The numbers, tables, charts and maps always come from PANDA's own Python and
SQL code. The model only interprets questions and explains verified results, so
switching providers changes the wording of explanations, not the data.

## Why hosted models first

Irene already runs Qwen2.5:3b, but Railway cannot reach it until UGA approves a
secure HTTPS route (see [Irene inference gateway](./irene-inference-gateway.md)).
Groq and Gemini free tiers keep PANDA working in the meantime. Irene stays in the
chain as the fallback and can become the first choice again with one setting.

## Configuration (Railway variables)

| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Enables Groq. Key from console.groq.com. Seal it in Railway. |
| `GEMINI_API_KEY` | Enables Gemini. Key from aistudio.google.com. Seal it in Railway. |
| `PANDA_LLM_PROVIDERS` | Optional order, e.g. `groq,gemini,local` or `local` only. |
| `PANDA_GROQ_MODEL`, `PANDA_GEMINI_MODEL` | Optional primary model overrides. |
| `PANDA_GROQ_FALLBACK_MODELS`, `PANDA_GEMINI_FALLBACK_MODELS` | Optional comma-separated backup models. |
| `PANDA_GROQ_DAILY_REQUESTS`, `PANDA_GROQ_DAILY_TOKENS` | Daily limits shown in the usage panel (defaults 1,000 and 200,000). |
| `PANDA_GEMINI_DAILY_REQUESTS`, `PANDA_GEMINI_DAILY_TOKENS` | Daily limits shown in the usage panel (default 500 requests, no token limit). |

A provider without a key is skipped. On Railway, the local provider is skipped
automatically until `PANDA_INFERENCE_URL` points at the Irene gateway.

## When PANDA moves on

Within a provider, PANDA tries the next model when a model is retired (HTTP 404),
rate limited (429), overloaded (503), times out, or returns an empty answer. A
rejected key (401) skips the provider's other models. After a provider fails,
it is skipped for its `Retry-After` time (60 seconds by default) so later
questions are not slowed down by the same failure.

Groq's gpt-oss and the Gemini models reason before answering, and that reasoning
counts against the output cap. PANDA therefore sends `reasoning_effort=low` and
allows at least 2,048 output tokens. A small cap produced empty answers in the
first staging test on 2026-11-20.

## Usage indicator

The circle in the top-right corner shows how much of today's tightest quota is
used (green under 60%, amber under 85%, red above). Hover over it, or focus it
with the keyboard, to see per provider:

- requests used today, the daily limit, and how many are left;
- tokens used today, the daily token limit, and how many are left;
- for Groq, the live per-minute token allowance;
- the token count of the most recent answer.

The download circle next to it opens the conversation report menu (PDF).

| Provider | Requests: used / left | Tokens: used / left |
| --- | --- | --- |
| Groq | Reported live by Groq's response headers (covers every app using the key) | Counted by PANDA against the configured daily token limit |
| Gemini | Counted by PANDA against the configured daily limit (Gemini sends no quota headers) | Counted by PANDA |
| Local | Counted by PANDA, no quota | Counted by PANDA, no quota |

Counts are kept per Pacific-time day in `llm_usage.sqlite` inside
`PANDA_STORAGE_DIR`, so they survive redeploys on the Railway storage volume.
Daily quotas reset at midnight Pacific (3 AM Eastern). The database stores
counts only: no prompts, answers or keys.

PANDA's counts include only requests made by PANDA. If the same Gemini key is
used elsewhere, check the exact remaining quota at aistudio.google.com/rate-limit.
For Groq, console.groq.com/settings/limits shows the account limits.

## Data note

Prompts include dataset summaries and query results. On Gemini's free tier,
Google may use prompts and responses to improve its products. For data that must
stay on UGA systems, set `PANDA_LLM_PROVIDERS=local` or remove `gemini`.

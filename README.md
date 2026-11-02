# PANDA

**PANDA** stands for **PERSEUS AI for Natural-language Data Analysis**. It is a
Streamlit chat interface for querying and visualizing forestry, FVS, vector, and
raster datasets from the PERSEUS project with a self-hosted Ollama model.

## Railway deployment

The repository includes a Dockerfile that installs the Linux system library
required by Rasterio and starts Streamlit on Railway's assigned port.

### PANDA service (Railway)

Attach a persistent volume at `/app/storage`, then configure these variables:

```text
PANDA_INFERENCE_URL=https://your-approved-irene-gateway.example.edu
PANDA_INFERENCE_TOKEN=the-same-long-random-secret-used-by-the-gateway
PANDA_OLLAMA_MODEL=qwen2.5:3b
PANDA_STORAGE_DIR=/app/storage
CARTO_API_KEY=your-carto-basemaps-key
```

The storage volume preserves PANDA's SQLite chat database across deployments.
Repository datasets remain part of the deployed image.

### Ollama and FastAPI gateway (Irene)

PANDA does not expose Ollama directly. Irene runs three Docker services:

- private Ollama with a persistent model volume;
- a one-time model initializer that pulls `qwen2.5:3b`; and
- an authenticated FastAPI gateway that permits only configured models and
  bounded request options.

Copy `.env.local-llm.example` to `.env.local-llm`, replace the placeholder token
with a long random value, then use `scripts/local_llm.sh`. The helper validates
health, model discovery, and a real generated response. Do not commit the real
environment file or token.

The Compose configuration binds the gateway to Irene loopback only. A separate,
UGA-approved HTTPS reverse proxy or tunnel must terminate TLS and forward to
`127.0.0.1:8000`; keep port `11434` private. In PANDA, open **Model connection**
and select **Test model connection** to verify a real generated response. An
online container or a successful health check alone does not prove Qwen can answer.

Detailed setup and verification instructions are in the
[Irene inference gateway documentation](docs-site/docs/architecture/irene-inference-gateway.md).

## Download a PDF report

After a conversation, open **Download conversation report** below the messages.
Select **Generate PDF report**, then **Download PDF**. This works for ordinary CSV,
FVS, and raster chats, including previously saved conversations.

The PDF contains a summary from the selected Ollama model, the dataset name,
creation time, and a full text appendix with recorded query details and bounded
table samples. Long conversations are summarized in sections without silently
dropping the end. If model generation fails, the PDF explicitly says that it is
a transcript export and preserves the discussion. It does not embed interactive
map/chart images or re-run queries. Clear/changed chats invalidate old downloads.
PDF bytes stay in the current browser session and are downloaded on request;
they are not written to a shared server report directory.

Install the updated requirements before running locally. Use an explicit Python
path if the virtual environment was moved or renamed:

```sh
cd "/Volumes/PERSEUS 4TB/Visualization/tree_ai_demo/PANDA-report-update"
"/Volumes/PERSEUS 4TB/PERSEUS/PANDA/.venv/bin/python" -m pip install -r requirements.txt
"/Volumes/PERSEUS 4TB/PERSEUS/PANDA/.venv/bin/python" -m streamlit run app.py --server.port 8503
```

Railway installs requirements through the Dockerfile. When
`PANDA_INFERENCE_URL` is unset, local development remains compatible with direct
Ollama through `OLLAMA_HOST=http://127.0.0.1:11434`.

## Dashboard migration

See [the React + FastAPI migration plan](DASHBOARD_MIGRATION_PLAN.md). The plan
covers streamed answers, persistent map state, background report/raster jobs,
chat migration, authentication, tests, deployment, and rollback.

## Chat-first interface and model behavior

New chats open with an original, scalable bamboo-and-leaf SVG mark, the welcome
question, and a single composer. Select/import data in the sidebar. Dataset
metrics, tables, and raster previews are opt-in under **Appearance & data → Show
dataset details**; example questions and diagnostics are collapsed in the sidebar.
Light, Dark, and Forest remain available. This is a Streamlit design improvement,
not the completed React migration; ordinary chat submissions still rerun the app.

The old casual-chat path returned hard-coded greetings/capability statements,
limited answers to 140 generated tokens, and sent no prior chat messages. The
new path uses a system message, up to 16 recent turns bounded to 14,000 characters,
and up to 1,200 output tokens. The assistant can answer everyday questions such
as pizza recipes and optionally invite the user back to forestry. FVS now routes
casual questions to this same path instead of treating them as full-table queries.
Data requests still use the existing bounded Python/SQL tools. The model does
not gain unrestricted database execution or permission to fabricate results.
Routing remains heuristic and may need clarification on ambiguous requests.
An unavailable/disabled model is reported explicitly, not disguised as AI output.

### Model research (September 2026)

Qwen2.5:3b is an instruction-tuned general conversational model, not inherently
a forestry-only bot. Its [official model card](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct)
documents system/user chat messages and a 32,768-token context for the 3B model.
The restricted behavior above was in PANDA's application code and connection
fallbacks; replacing the model alone cannot remove those branches.

Keep **qwen2.5:3b** as the baseline you preferred. As a later controlled experiment,
compare **qwen3:4b** in non-thinking mode, then **qwen2.5:7b** if the hosting memory
and latency budget permit. [Qwen3's release notes](https://qwenlm.github.io/blog/qwen3/)
describe improvements in multi-turn dialogue and a non-thinking mode, while
[Ollama documents explicit thinking controls](https://docs.ollama.com/capabilities/thinking).
This branch does not switch models or claim a benchmark win. A thinking-capable
model needs explicit handling of its separate thinking output before adoption.

Approximate Ollama download sizes are 1.9 GB for Qwen2.5:3b, 2.5 GB for Qwen3:4b,
and 4.7 GB for Qwen2.5:7b ([Qwen2.5 tags](https://ollama.com/library/qwen2.5),
[Qwen3 tags](https://ollama.com/library/qwen3)). Download size is not runtime RAM;
context, parallel requests, and KV cache add memory. CPU-only Railway generation
can still be slow even when the UI becomes responsive.

Evaluate each candidate on the same prompts: a pizza recipe and a follow-up,
a forestry definition, the known FVS age/acre query, a map request, an ambiguous
follow-up, and a report containing verified numbers. Compare correctness,
first-token latency, total time, and memory. Do not select solely by parameter count.

## Railway branch workflow

The Irene gateway changes are staged on `integration/irene-fastapi`, not `main`.
Test locally first. In Railway, select that branch for a staging PANDA service
using the Dockerfile. Give staging a separate storage volume and configure its
gateway URL and token as Railway service variables. Changing production's branch
or public hostname is a separate cutover step.
Never commit API keys, SQLite chat files, Ollama weights, or virtual environments.

## Verification

```sh
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

Report tests use synthetic conversations and mock model responses. A live model
connection test is still required in each deployment.

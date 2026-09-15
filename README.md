# PANDA

**PANDA** stands for **PERSEUS AI for Natural Language Data Analysis**. It is a
Streamlit chat interface for querying and visualizing forestry, FVS, vector, and
raster datasets from the PERSEUS project with a self-hosted Ollama model.

## Railway deployment

The repository includes a Dockerfile that installs the Linux system library
required by Rasterio and starts Streamlit on Railway's assigned port.

### PANDA service

Attach a persistent volume at `/app/storage`, then configure these variables:

```text
OLLAMA_HOST=http://${{ollama.RAILWAY_PRIVATE_DOMAIN}}:11434
PANDA_OLLAMA_MODEL=qwen2.5:3b
PANDA_STORAGE_DIR=/app/storage
CARTO_API_KEY=your-carto-basemaps-key
```

The storage volume preserves PANDA's SQLite chat database across deployments.
Repository datasets remain part of the deployed image.

### Ollama service

Run the `ollama/ollama` image as a private Railway service on port `11434`, set
`OLLAMA_HOST=0.0.0.0:11434`, and attach a separate persistent volume at
`/root/.ollama`. In that service's console, pull the configured model:

```sh
ollama pull qwen2.5:3b
ollama list
```

Deploy Ollama first, wait for the model pull to finish, and then redeploy PANDA.

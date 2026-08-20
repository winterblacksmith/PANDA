---
id: local-setup
title: Run Canopy locally
description: Start Ollama, qwen2.5:3b, Streamlit, and the documentation site.
---

# Run Canopy locally

The supported project location is:

```text
/Volumes/PERSEUS 4TB/PERSEUS/tree_ai_demo
```

From that directory, the launcher starts the bundled Ollama runtime when necessary and then starts Streamlit:

```bash
./run_canopy.sh
```

The preferred local model is `qwen2.5:3b`. Confirm the local runtime and models with:

```bash
OLLAMA_HOST=127.0.0.1:11434 tools/Ollama.app/Contents/Resources/ollama list
```

To run Streamlit directly instead of using the launcher:

```bash
cd "/Volumes/PERSEUS 4TB/PERSEUS/tree_ai_demo"
source .venv/bin/activate
streamlit run app.py
```

The former `.venv` was a Windows environment copied onto the Mac, so it had no usable `.venv/bin/python` or `.venv/bin/streamlit`. It was preserved as `.venv_windows_backup_20260805`, and a native environment was created on the PERSEUS drive.

If a hidden filename beginning with `._` appears on an external drive, it is macOS metadata rather than project data. Canopy now ignores such files automatically.

To run the documentation website:

```bash
cd docs-site
npm install
npm start
```

Docusaurus requires Node.js 20 or newer. A production build is generated with `npm run build`.

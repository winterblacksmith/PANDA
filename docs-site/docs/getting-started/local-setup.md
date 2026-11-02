---
id: local-setup
title: Run PANDA locally
description: Start Ollama, qwen2.5:3b, Streamlit, and the documentation site.
---

# Run PANDA locally

Use the active PANDA repository checkout on the PERSEUS drive. Depending on the
copy being tested, the folder may be named `PANDA` or a staging checkout.

```text
/Volumes/PERSEUS 4TB/PERSEUS/PANDA
```

From that directory, activate the native macOS environment and start Streamlit:

```bash
source .venv/bin/activate
python -m streamlit run app.py
```

The preferred local model is `qwen2.5:3b`. Confirm the local runtime and models with:

```bash
OLLAMA_HOST=127.0.0.1:11434 tools/Ollama.app/Contents/Resources/ollama list
```

If the environment was moved from another computer or `python`/`streamlit` is
missing after activation, recreate it in the current folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Virtual environments are platform-specific and should not be copied between
Windows, macOS, Irene, or Railway.

If a hidden filename beginning with `._` appears on an external drive, it is macOS metadata rather than project data. Canopy now ignores such files automatically.

To run the documentation website:

```bash
cd docs-site
npm install
npm start
```

Docusaurus requires Node.js 20 or newer. A production build is generated with `npm run build`.

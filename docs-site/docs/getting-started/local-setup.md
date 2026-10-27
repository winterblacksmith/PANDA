---
id: local-setup
title: Local development
description: Run PANDA and its Docusaurus documentation locally.
---

# Local development

Clone the repository or open the authoritative PANDA working copy. Do not assume a particular external-drive path; confirm the folder that contains `app.py`, `requirements.txt`, and `docs-site/`.

## Application

When a project virtual environment already exists:

```bash
source .venv/bin/activate
python -m streamlit run app.py
```

Using `python -m streamlit` avoids relying on a globally installed `streamlit` shell command.

## Documentation website

Docusaurus requires Node.js 20 or newer:

```bash
cd docs-site
npm install
npm run start
```

The development site normally opens at `http://localhost:3000/PANDA/`. Changes to Markdown files are reflected automatically.

Before publishing:

```bash
npm run typecheck
npm run build
npm run serve
```

## Online editing

Every documentation page includes an **Edit this page** link. It opens the Markdown file on the `docs/panda-handoff-starter` branch in GitHub, where an authorized maintainer can edit, preview, and commit changes without the PERSEUS drive.
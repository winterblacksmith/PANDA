# PANDA documentation

This Docusaurus site documents PANDA: PERSEUS AI for Natural-language Data Analysis.

## Edit online

Open `docs-site/docs/` on the `docs/panda-handoff-starter` branch. Documentation pages are ordinary Markdown files and can be edited directly through GitHub.

## Run locally

```bash
cd docs-site
npm install
npm run start
```

## Verify a production build

```bash
npm run typecheck
npm run build
npm run serve
```

## Deploy on Railway

Create a separate Railway service connected to the `docs/panda-handoff-starter` branch, then configure:

```text
Root Directory: /docs-site
Build Command: npm ci && npm run build
Start Command: npm run serve:railway
Healthcheck Path: /
```

Under Networking, generate a public domain. The preferred name, if Railway reports it available, is:

```text
https://perseus-panda-docs.up.railway.app
```

The application does not require database credentials or inference secrets. The documentation is static and should be deployed as a separate service from the PANDA application.

## Optional GitHub Pages deployment

The included workflow can also publish to `https://winterblacksmith.github.io/PANDA/` after GitHub Pages is configured to use GitHub Actions.
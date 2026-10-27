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

## Publish

The intended public address is:

```text
https://winterblacksmith.github.io/PANDA/
```

GitHub Pages must be configured to use GitHub Actions before the deployment workflow can publish the site.
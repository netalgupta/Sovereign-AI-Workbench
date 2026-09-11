# Standalone Workbench Internals console

A single self-contained HTML page showing everything inside the
pipeline — the knowledge graph, the embedding space, every chunk, every
image with what was understood from it, and the measured pipeline
health. No server, no build step, no network.

```bash
# Refresh the data (only needed if the corpus or graph changed)
python -m backend.evaluation.export_inspection_data
python -m backend.evaluation.export_image_data

# Build
python frontend/standalone/build_console.py
```

Then open `workbench_console.html` in any browser, or publish it as an
artifact to share a link.

## Why this exists alongside the React pages

| | standalone (`frontend/standalone/`) | in-app (`frontend/src/pages/`) |
|---|---|---|
| Views | Graph, Images, Vectors, Chunks, Health | same, plus Sources |
| Data | inlined at build time | live from the API, snapshot fallback |
| Needs | a browser | the app + backend running |
| For | a judge, a reviewer, a teammate on another machine | daily development |

Both read the **same exports**, so they cannot drift in *what* they
show — only in how they get it. `InstrumentationPage.jsx` is the
in-app version; `GraphExplorerPage.jsx` and `KnowledgeBasePage.jsx` are
focused slices of the same views for the `/graph` and `/sources` routes.

## Files

- `workbench_console.template.html` — the page, with `__INSPECTION_DATA__`
  and `__IMAGE_DATA__` placeholders where the JSON is injected. Edit this,
  never the built output.
- `build_console.py` — substitutes the data and writes the page. Fails
  loudly if a placeholder is left unreplaced, because an unsubstituted
  one renders as a JavaScript syntax error and a blank screen, which is
  a confusing way to discover a typo.
- `workbench_console.html` — the built output. Gitignored: it is ~3.4MB
  of base64 images derived entirely from files already tracked under
  `MRPL_RAG_Test_Corpus/` and `MRPL_Chart_Stress_Corpus/`, so committing
  it would put the same bytes in the repo twice.

## Note on the images

Chart images are inlined as `data:` URIs rather than referenced by path.
That is what makes the page genuinely self-contained — a published
artifact has no access to the local filesystem, and its CSP blocks
loading images from anywhere but the page itself.

Every chart reading shown is labelled **ESTIMATE**, and images where the
vision model stated values that were never printed are flagged by count.
That is not decoration: measured on generated charts carrying no printed
numbers at all, the model produced specific figures and described them
as values "printed as text on the chart"
(`backend/evaluation/CHART_STRESS_REPORT.md`).

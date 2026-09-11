"""Build the standalone Workbench Internals console.

Inlines the exported pipeline data into the HTML template and writes a
single self-contained page — no server, no build step, no network. Open
the output in a browser, or publish it as an artifact.

WHY THIS EXISTS ALONGSIDE THE REACT PAGES. `frontend/src/pages/
InstrumentationPage.jsx` is the same views inside the real app, talking
to the live API. This standalone build is the version you can hand to
someone who has neither the app nor the backend running — a judge, a
reviewer, a teammate on another machine. Both read the same exports, so
they cannot drift in what they show, only in how they get it.

Paths are REPO-RELATIVE. The first version of this script carried the
absolute scratchpad paths of the session that wrote it, which made it
unrunnable by anyone else and was the whole reason it was moved out of a
temp directory and into the repo.

Regenerate the inputs first if the corpus or graph has changed:

    python -m backend.evaluation.export_inspection_data
    python -m backend.evaluation.export_image_data
    python frontend/standalone/build_console.py
"""

import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

TEMPLATE = os.path.join(HERE, "workbench_console.template.html")
OUTPUT = os.path.join(HERE, "workbench_console.html")
INSPECTION = os.path.join(REPO, "backend", "evaluation", "inspection_data.json")
IMAGES = os.path.join(REPO, "backend", "evaluation", "image_data.json")


def build() -> str:
    template = io.open(TEMPLATE, encoding="utf-8").read()

    with io.open(INSPECTION, encoding="utf-8") as handle:
        inspection = json.load(handle)
    with io.open(IMAGES, encoding="utf-8") as handle:
        images = json.load(handle)["images"]

    # Only what the page renders. The raw export also carries per-file
    # stats and an error map that nothing on the page reads, and a 3MB
    # page should not carry a byte it does not use.
    slim = {
        "chunking": inspection["chunking"],
        "embedding_dim": inspection["embedding_dim"],
        "pca_explained_variance": inspection["pca_explained_variance"],
        "chunks": inspection["chunks"],
        # Four decimals is past anything the heatmap can render and
        # roughly halves the matrix.
        "similarity": [[round(v, 4) for v in row] for row in inspection["similarity"]],
        "graph": {
            "nodes": inspection["graph"]["nodes"],
            "relationships": inspection["graph"]["relationships"],
        },
    }

    page = template.replace("__INSPECTION_DATA__", json.dumps(slim, separators=(",", ":")))
    page = page.replace("__IMAGE_DATA__", json.dumps(images, separators=(",", ":")))

    # Fail loudly rather than publishing a page whose data never landed:
    # an unreplaced placeholder renders as a JavaScript syntax error and
    # a blank screen, which is a confusing way to discover a typo.
    for placeholder in ("__INSPECTION_DATA__", "__IMAGE_DATA__"):
        if placeholder in page:
            raise RuntimeError(f"{placeholder} was never substituted — check the template.")

    io.open(OUTPUT, "w", encoding="utf-8").write(page)
    return page


if __name__ == "__main__":
    page = build()
    size_mb = len(page) / 1024 / 1024
    print(f"Wrote {OUTPUT}  ({size_mb:.2f} MB)")
    print("  Open it directly in a browser, or publish it as an artifact.")
    if size_mb > 16:
        print("  WARNING: over the 16MB artifact limit — shrink the image export first.")

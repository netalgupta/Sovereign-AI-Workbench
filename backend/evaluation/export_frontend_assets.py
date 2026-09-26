"""Write the pipeline snapshots the frontend loads from /pipeline/.

The frontend's graph explorer and knowledge-base pages need the real
graph, chunks and image understanding. Those live in Neo4j, a FAISS
store and a set of JSON artifacts respectively — none of which a browser
can read, and none of which have a backend HTTP endpoint yet.

Rather than block the UI on an API that does not exist, this exports
static snapshots into frontend/public/pipeline/. The page fetches them
exactly as it would fetch an endpoint, so swapping to a live route later
is a URL change in one place per page and nothing else.

Split into several files, not one: the graph is ~100KB and the images
are megabytes of base64. A page that only draws the graph should not
have to download every chart image to do it.
"""

import json
import sys
from pathlib import Path

DEFAULT_OUT = Path("frontend/public/pipeline")


def export(out_dir: Path, inspection_path: Path, image_path: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    inspection = json.loads(inspection_path.read_text(encoding="utf-8"))

    graph = {
        "nodes": inspection["graph"]["nodes"],
        "relationships": inspection["graph"]["relationships"],
    }
    (out_dir / "graph.json").write_text(json.dumps(graph, separators=(",", ":")), encoding="utf-8")
    written["graph.json"] = len(graph["nodes"])

    chunks = {
        "chunking": inspection["chunking"],
        "embedding_dim": inspection["embedding_dim"],
        "pca_explained_variance": inspection["pca_explained_variance"],
        "chunks": inspection["chunks"],
        # Rounded: four decimals is well past what any UI renders, and it
        # roughly halves the file.
        "similarity": [[round(v, 4) for v in row] for row in inspection["similarity"]],
    }
    (out_dir / "chunks.json").write_text(json.dumps(chunks, separators=(",", ":")), encoding="utf-8")
    written["chunks.json"] = len(chunks["chunks"])

    if image_path.exists():
        images = json.loads(image_path.read_text(encoding="utf-8"))["images"]
        (out_dir / "images.json").write_text(
            json.dumps(images, separators=(",", ":")), encoding="utf-8"
        )
        written["images.json"] = len(images)

    return written


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    written = export(
        out_dir,
        Path("backend/evaluation/inspection_data.json"),
        Path("backend/evaluation/image_data.json"),
    )
    print(f"Wrote {out_dir}/")
    for name, count in written.items():
        size_kb = (out_dir / name).stat().st_size / 1024
        print(f"  {name:<14} {count:>4} records   {size_kb:>8.0f} KB")

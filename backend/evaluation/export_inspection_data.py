"""Export the whole pipeline in an inspectable form: every chunk, its
metadata, its embedding projected to 2D, the chunk-to-chunk similarity
matrix, and the complete Neo4j knowledge graph (nodes, labels,
properties, relationships).

Purpose is developer inspection, not the product: the RAG pipeline
otherwise only shows you its OUTPUT (an answer plus citations), which
makes it very hard to see WHY a given chunk was retrieved, whether
chunking split a table down the middle, or whether two documents'
embeddings sit on top of each other. Everything here is derived from the
real pipeline — the same ingest_corpus, the same bge-large embeddings,
the same chunker — never a re-implementation, or it would be inspecting
something that isn't what runs.

The 2D projection is PCA, deliberately, not t-SNE/UMAP: PCA is
deterministic (same input, same picture, every run), linear (distances
mean something consistent), and has no perplexity/neighbour parameters
that would let a viewer accidentally tune the plot into showing clusters
that aren't there. It explains less variance than a nonlinear method
would — the explained-variance ratio is exported alongside so the viewer
can see exactly how much is being lost rather than trusting the picture.
"""

import json
import sys
from pathlib import Path

import numpy as np


def _pca_2d(vectors: np.ndarray) -> tuple[np.ndarray, list[float]]:
    """Project to 2D via PCA, returning coords and explained variance.

    Implemented directly rather than pulled from scikit-learn: it is a
    mean-centre plus an SVD, sklearn is not currently a dependency, and
    adding one for six lines of linear algebra is the wrong trade —
    especially under CLAUDE.md's fully-offline constraint, where every
    new dependency is another thing to vendor onto the venue machine.
    """
    centered = vectors - vectors.mean(axis=0, keepdims=True)
    # full_matrices=False: we only need the top components, not the full
    # 1024x1024 basis.
    _u, singular_values, vt = np.linalg.svd(centered, full_matrices=False)
    coords = centered @ vt[:2].T

    total_variance = float((singular_values**2).sum())
    explained = [float(s**2 / total_variance) for s in singular_values[:2]] if total_variance else [0.0, 0.0]
    return coords, explained


def export_graph(uri: str, user: str, password: str) -> dict:
    """Pull the entire graph — every node with all its properties, every
    relationship — for a Neo4j-Browser-style view.

    Exports ALL properties rather than just the key property per label,
    because the whole point of an inspection view is seeing what is
    actually stored, including fields you didn't expect to be there (or
    expected and find missing). Node ids are Neo4j's internal element
    ids, used only to join relationships to endpoints client-side.

    Returns an empty graph rather than raising if Neo4j is unreachable:
    the chunk/embedding half of this export is still useful on its own,
    and a dev inspecting retrieval shouldn't be blocked by the graph
    database being down.
    """
    try:
        from backend.graph.neo4j_client import GraphClient

        client = GraphClient(uri, user, password)
    except Exception as exc:  # noqa: BLE001 — graph is optional for this export
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "nodes": [], "relationships": []}

    try:
        with client._driver.session() as session:
            nodes = [
                {
                    "id": record["id"],
                    "labels": record["labels"],
                    "properties": {k: str(v) for k, v in record["props"].items()},
                }
                for record in session.run(
                    "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props"
                )
            ]
            relationships = [
                {
                    "id": record["id"],
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["type"],
                }
                for record in session.run(
                    "MATCH (a)-[r]->(b) RETURN elementId(r) AS id, elementId(a) AS source, "
                    "elementId(b) AS target, type(r) AS type"
                )
            ]
        return {"available": True, "error": None, "nodes": nodes, "relationships": relationships}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "nodes": [], "relationships": []}
    finally:
        client.close()


def build(corpus_dir: str, include_graph: bool = True) -> dict:
    from backend.evaluation.ingest_corpus import ingest_corpus
    from backend.ingestion.chunking import (
        CHUNK_OVERLAP_TOKENS,
        CHUNK_SIZE_TOKENS,
        TIKTOKEN_ENCODING,
    )
    from backend.ingestion.embeddings import embed_texts

    store, chunks, stats = ingest_corpus(corpus_dir, verbose=False)

    texts = [c.text for c in chunks]
    vectors = np.asarray(embed_texts(texts), dtype=np.float32)
    coords, explained = _pca_2d(vectors)

    # Cosine similarity between every pair — the actual quantity dense
    # retrieval ranks on, so the viewer can see which chunks the
    # embedding model considers near-duplicates. Vectors from
    # embed_texts are already L2-normalized (bge convention), so a dot
    # product IS cosine similarity; normalizing again would be a no-op
    # that hides the assumption. Asserted rather than assumed:
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3), f"expected normalized vectors, got norms {norms[:3]}"
    similarity = (vectors @ vectors.T).tolist()

    graph = (
        export_graph("bolt://localhost:7687", "neo4j", "testpassword123")
        if include_graph
        else {"available": False, "error": "not requested", "nodes": [], "relationships": []}
    )

    return {
        "corpus_dir": corpus_dir,
        "graph": graph,
        "chunking": {
            "chunk_size_tokens": CHUNK_SIZE_TOKENS,
            "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS,
            "encoding": TIKTOKEN_ENCODING,
        },
        "embedding_dim": int(vectors.shape[1]),
        "pca_explained_variance": explained,
        "stats": stats,
        "chunks": [
            {
                "index": i,
                "text": c.text,
                "chars": len(c.text),
                "source_document": c.metadata.source_document,
                "document_type": c.metadata.document_type,
                "page_number": c.metadata.page_number,
                "chunk_index": c.metadata.chunk_index,
                "x": float(coords[i][0]),
                "y": float(coords[i][1]),
            }
            for i, c in enumerate(chunks)
        ],
        "similarity": similarity,
    }


if __name__ == "__main__":
    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/inspection_data.json"

    data = build(corpus_dir)
    Path(out_path).write_text(json.dumps(data), encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"  chunks:     {len(data['chunks'])}")
    print(f"  dim:        {data['embedding_dim']}")
    print(f"  PCA 2D explains {sum(data['pca_explained_variance']):.1%} of variance")
    g = data["graph"]
    if g["available"]:
        print(f"  graph:      {len(g['nodes'])} nodes, {len(g['relationships'])} relationships")
    else:
        print(f"  graph:      UNAVAILABLE ({g['error']})")

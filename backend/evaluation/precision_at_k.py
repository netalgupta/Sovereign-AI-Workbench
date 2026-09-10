"""Precision@K for raw hybrid retrieval, plus a dense-only/sparse-only
breakdown to diagnose whether BM25 is dominating the RRF fusion.

Relevance proxy, stated explicitly because there's no manually-labeled
chunk-level relevance judgment for this corpus: a retrieved chunk counts
as "relevant" if its `source_document` matches the question's
`expected_source` (from mrpl_qa_test_set.json). This is a document-level
proxy standing in for true chunk-level relevance — reasonable given each
question's answer lives in exactly one source document in this corpus's
design, but not a substitute for real relevance judgments.
"""

import json
import sys

from rank_bm25 import BM25Okapi

from backend.ingestion.embeddings import embed_texts
from backend.retrieval.hybrid_search import RRF_K, hybrid_search
from backend.retrieval.vector_store import VectorStore


def _dense_only_top_k(store: VectorStore, query: str, k: int) -> list[str]:
    query_embedding = embed_texts([query])[0]
    hits = store.dense_search(query_embedding, top_k=k)
    return [store.get_by_faiss_id(fid).source_document for fid, _score in hits]


def _sparse_only_top_k(store: VectorStore, query: str, k: int) -> list[str]:
    all_rows = store.all_chunk_texts()
    faiss_ids = [row[0] for row in all_rows]
    corpus_texts = [row[1] for row in all_rows]
    tokenized_corpus = [t.split() for t in corpus_texts]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(query.split())
    ranked = sorted(range(len(faiss_ids)), key=lambda i: scores[i], reverse=True)[:k]
    return [store.get_by_faiss_id(faiss_ids[i]).source_document for i in ranked]


def precision_at_k(sources: list[str], expected_source: str, k: int) -> float:
    top_k = sources[:k]
    hits = sum(1 for s in top_k if s == expected_source)
    return hits / k


def run_precision_analysis(store: VectorStore, questions: list[dict], k: int = 5) -> dict:
    results = []
    for q in questions:
        if q["expected_source"].startswith("None"):
            continue  # Q9, the negative test case, has no expected_source to score against

        question = q["question"]
        expected = q["expected_source"]

        fused_sources = [c.source_document for c in hybrid_search(store, question, top_k=k)]
        dense_sources = _dense_only_top_k(store, question, k)
        sparse_sources = _sparse_only_top_k(store, question, k)

        results.append(
            {
                "question": question,
                "expected_source": expected,
                "fused_sources": fused_sources,
                "precision_at_k_fused": precision_at_k(fused_sources, expected, k),
                "precision_at_k_dense_only": precision_at_k(dense_sources, expected, k),
                "precision_at_k_sparse_only": precision_at_k(sparse_sources, expected, k),
            }
        )

    avg_fused = sum(r["precision_at_k_fused"] for r in results) / len(results)
    avg_dense = sum(r["precision_at_k_dense_only"] for r in results) / len(results)
    avg_sparse = sum(r["precision_at_k_sparse_only"] for r in results) / len(results)

    return {
        "k": k,
        "rrf_k_constant": RRF_K,
        "per_question": results,
        "avg_precision_at_k_fused": avg_fused,
        "avg_precision_at_k_dense_only": avg_dense,
        "avg_precision_at_k_sparse_only": avg_sparse,
    }


if __name__ == "__main__":
    from backend.evaluation.ingest_corpus import ingest_corpus

    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    questions_path = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/mrpl_qa_test_set.json"

    with open(questions_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    store, _, stats = ingest_corpus(corpus_dir, verbose=False)
    print(f"Ingested {stats['total_chunks']} chunks (chunk_size default per chunking.py).")

    analysis = run_precision_analysis(store, questions, k=5)
    print(json.dumps(analysis, indent=2))

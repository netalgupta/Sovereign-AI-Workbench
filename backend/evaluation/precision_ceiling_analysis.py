"""Is precision@5 measuring retrieval quality, or measuring the corpus?

precision@5 always divides by 5, but each question in this test set has
exactly ONE correct source document, and that document contributes only
a handful of chunks to the corpus. If the answer's document produces 2
chunks, then even PERFECT retrieval — both of those chunks ranked 1 and
2, nothing relevant missed — scores 2/5 = 0.40, not 1.00.

So the achievable maximum for a question is min(chunks_in_expected_doc,
5) / 5, and the corpus-wide ceiling is the mean of those. Comparing raw
precision@5 across chunk sizes without accounting for this is a trap:
HALVING the chunk size roughly DOUBLES the chunks each document
contributes, which mechanically RAISES the ceiling. A higher score at a
smaller chunk size can therefore be pure metric inflation rather than
better retrieval.

This module computes, for each chunk size, both the raw score and the
fraction of the achievable maximum that was actually captured. The
second number is the one that compares fairly across chunk sizes.
"""

import json
import sys
from collections import Counter

from backend.evaluation.chunk_size_experiment import ingest_document_with_chunk_size
from backend.evaluation.ingest_corpus import discover_files
from backend.evaluation.precision_at_k import run_precision_analysis
from backend.ingestion.embeddings import embed_texts
from backend.retrieval.vector_store import VectorStore


def ingest_and_count(corpus_dir: str, chunk_size_tokens: int) -> tuple[VectorStore, Counter]:
    """Same ingestion as chunk_size_experiment, but also returns how many
    chunks each source document contributed — the input to the ceiling."""
    store = VectorStore(dim=1024)
    per_document: Counter = Counter()
    for file_path in discover_files(corpus_dir):
        chunks = ingest_document_with_chunk_size(str(file_path), chunk_size_tokens)
        if chunks:
            embeddings = embed_texts([c.text for c in chunks])
            store.add_chunks(chunks, embeddings)
            per_document[chunks[0].metadata.source_document] += len(chunks)
    return store, per_document


def ceiling_for(per_document: Counter, expected_source: str, k: int) -> float:
    return min(per_document.get(expected_source, 0), k) / k


def analyse(corpus_dir: str, questions: list[dict], chunk_size: int, k: int = 5) -> dict:
    store, per_document = ingest_and_count(corpus_dir, chunk_size)
    analysis = run_precision_analysis(store, questions, k=k)

    scored = [q for q in questions if not q["expected_source"].startswith("None")]
    per_question = []
    for q, result in zip(scored, analysis["per_question"]):
        ceiling = ceiling_for(per_document, q["expected_source"], k)
        per_question.append(
            {
                "question": q["question"],
                "expected_source": q["expected_source"],
                "chunks_in_expected_doc": per_document.get(q["expected_source"], 0),
                "ceiling": ceiling,
                "actual_fused": result["precision_at_k_fused"],
                "at_ceiling": abs(result["precision_at_k_fused"] - ceiling) < 1e-9,
            }
        )

    mean_ceiling = sum(p["ceiling"] for p in per_question) / len(per_question)
    return {
        "chunk_size_tokens": chunk_size,
        "total_chunks": len(store),
        "raw_precision_at_k_fused": analysis["avg_precision_at_k_fused"],
        "raw_precision_at_k_dense_only": analysis["avg_precision_at_k_dense_only"],
        "raw_precision_at_k_sparse_only": analysis["avg_precision_at_k_sparse_only"],
        "mean_structural_ceiling": mean_ceiling,
        # THE comparable number across chunk sizes.
        "fraction_of_achievable_fused": analysis["avg_precision_at_k_fused"] / mean_ceiling,
        "fraction_of_achievable_dense_only": analysis["avg_precision_at_k_dense_only"] / mean_ceiling,
        "questions_at_ceiling": sum(1 for p in per_question if p["at_ceiling"]),
        "questions_scored": len(per_question),
        "per_question": per_question,
    }


if __name__ == "__main__":
    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    questions_path = (
        sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/mrpl_qa_test_set.json"
    )
    out_path = (
        sys.argv[3] if len(sys.argv) > 3 else "backend/evaluation/precision_ceiling_analysis.json"
    )

    with open(questions_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    results = [analyse(corpus_dir, questions, size) for size in (512, 256)]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote {out_path}\n")
    header = f"{'chunk':>6} {'chunks':>7} {'raw fused':>10} {'ceiling':>8} {'% achieved':>11} {'at ceiling':>11}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['chunk_size_tokens']:>6} {r['total_chunks']:>7} "
            f"{r['raw_precision_at_k_fused']:>10.3f} {r['mean_structural_ceiling']:>8.3f} "
            f"{r['fraction_of_achievable_fused']:>10.1%} "
            f"{str(r['questions_at_ceiling']) + '/' + str(r['questions_scored']):>11}"
        )

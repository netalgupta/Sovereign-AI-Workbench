"""Retrieval metrics that still have headroom once precision@5 saturates.

THE PROBLEM THIS SOLVES. precision_ceiling_analysis.py established that
at the locked 512-token chunk size, all 8 content questions retrieve
every available relevant chunk inside the top-5 — 100% of the metric's
structural ceiling. A saturated metric cannot report improvement OR
regression: any future retrieval change would measure 0.350 whether it
helped, did nothing, or quietly broke ordering. Tuning against it is
tuning blind.

Recall@k has the same problem here (everything relevant is already
retrieved, so it pins at 1.0). What is NOT saturated is ORDERING:

  MRR (Mean Reciprocal Rank) — 1/rank of the FIRST relevant chunk,
    averaged over questions. Perfect retrieval that ranks the right
    chunk 3rd scores 0.33, not 1.0. Independent of how many chunks the
    answer's document happens to contribute, so it does not inherit
    precision@k's corpus-shape ceiling.

  MAP (Mean Average Precision) — averages precision at each relevant
    hit, rewarding relevant chunks clustered at the top rather than
    scattered through the top-5. Discriminates between two result sets
    that MRR would score identically.

Relevance proxy is unchanged from precision_at_k.py and stated again
here because it bounds every number this module produces: a chunk counts
as relevant if its source_document equals the question's
expected_source. That is a DOCUMENT-level proxy for chunk-level
relevance — appropriate for this corpus (each answer lives in exactly
one document by design) but not a substitute for real per-chunk
judgments, which is the next step if these metrics saturate too.
"""

import json
import sys

from backend.retrieval.hybrid_search import hybrid_search
from backend.retrieval.vector_store import VectorStore


def reciprocal_rank(sources: list[str], expected_source: str) -> float:
    """1/rank of the first relevant result; 0.0 if none are relevant."""
    for rank, source in enumerate(sources, start=1):
        if source == expected_source:
            return 1.0 / rank
    return 0.0


def average_precision(sources: list[str], expected_source: str) -> float:
    """Mean of precision@i taken at each position i holding a relevant
    result. 0.0 if none are relevant.

    Normalized by the number of relevant results ACTUALLY FOUND, not by
    the number that exist in the corpus — so, unlike precision@k, a
    question whose document contributes only one chunk can still score
    1.0 by ranking that chunk first. That is exactly the ceiling
    behaviour this module exists to avoid.
    """
    hits = 0
    precision_sum = 0.0
    for i, source in enumerate(sources, start=1):
        if source == expected_source:
            hits += 1
            precision_sum += hits / i
    return precision_sum / hits if hits else 0.0


def recall_at_k(sources: list[str], expected_source: str, total_relevant: int) -> float:
    if not total_relevant:
        return 0.0
    found = sum(1 for s in sources if s == expected_source)
    return min(found, total_relevant) / total_relevant


def run_metrics(
    store: VectorStore, questions: list[dict], chunks_per_document: dict[str, int], k: int = 5
) -> dict:
    per_question = []
    for q in questions:
        if q["expected_source"].startswith("None"):
            continue  # the negative test case has no relevant document to rank

        sources = [c.source_document for c in hybrid_search(store, q["question"], top_k=k)]
        expected = q["expected_source"]
        total_relevant = min(chunks_per_document.get(expected, 0), k)

        first_rank = next(
            (i for i, s in enumerate(sources, start=1) if s == expected), None
        )
        per_question.append(
            {
                "question": q["question"],
                "expected_source": expected,
                "rank_of_first_relevant": first_rank,
                "reciprocal_rank": reciprocal_rank(sources, expected),
                "average_precision": average_precision(sources, expected),
                "recall_at_k": recall_at_k(sources, expected, total_relevant),
                "retrieved_sources": sources,
            }
        )

    n = len(per_question)
    return {
        "k": k,
        "questions_scored": n,
        "MRR": sum(p["reciprocal_rank"] for p in per_question) / n,
        "MAP": sum(p["average_precision"] for p in per_question) / n,
        "recall_at_k": sum(p["recall_at_k"] for p in per_question) / n,
        "questions_ranked_first": sum(
            1 for p in per_question if p["rank_of_first_relevant"] == 1
        ),
        "per_question": per_question,
    }


if __name__ == "__main__":
    from collections import Counter

    from backend.evaluation.ingest_corpus import ingest_corpus

    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    questions_path = (
        sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/mrpl_qa_test_set.json"
    )
    out_path = sys.argv[3] if len(sys.argv) > 3 else "backend/evaluation/retrieval_metrics.json"

    with open(questions_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    store, all_chunks, _stats = ingest_corpus(corpus_dir, verbose=False)
    chunks_per_document = Counter(c.metadata.source_document for c in all_chunks)

    result = run_metrics(store, questions, chunks_per_document, k=5)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {out_path}\n")
    print(f"questions scored:     {result['questions_scored']}")
    print(f"MRR:                  {result['MRR']:.3f}   (1.0 = correct doc always ranked #1)")
    print(f"MAP:                  {result['MAP']:.3f}")
    print(f"recall@5:             {result['recall_at_k']:.3f}   (saturated if 1.000)")
    print(f"ranked #1:            {result['questions_ranked_first']}/{result['questions_scored']}")
    print("\nrank of first relevant chunk, per question:")
    for p in result["per_question"]:
        print(f"  rank {p['rank_of_first_relevant']}  {p['expected_source'][:50]}")

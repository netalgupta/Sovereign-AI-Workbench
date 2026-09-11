"""Measure what signal can actually separate in-corpus questions from
out-of-corpus ones, so RAG_SPEC.md §3's confidence gate can be built on
something real.

WHY THE SPEC'S OWN METHOD CANNOT WORK. §3 says to normalize the top
fused score across the candidate pool and refuse below 0.35. As
implemented that is `(top - min) / (max - min)` where `top` IS `max`,
so it evaluates to exactly 1.0 for every query — measured across 16
questions spanning in-corpus to Pride and Prejudice, the gate refused 0
and the normalized value was 1.0 every single time.

Fixing the arithmetic does not rescue the approach, because the deeper
problem is the input. Reciprocal Rank Fusion scores on RANK ALONE and
discards similarity magnitude: some chunk is always rank 1, so its fused
score is the same whether the corpus answers the question perfectly or
has nothing to do with it. No function of fused ranks can distinguish
those two cases. The confidence signal has to come from the raw
similarity the fusion threw away.

This script measures three candidate signals per question — best dense
cosine, mean of the top-5 dense cosines, and best BM25 score — over
questions grouped by how far they sit from the corpus, and reports the
separation each achieves. The threshold is then read off measured data
rather than chosen and hoped for.
"""

import json
import sys

import numpy as np

from backend.evaluation.ingest_corpus import ingest_corpus
from backend.evaluation.refusal_at_scale import QUESTIONS
from backend.ingestion.embeddings import embed_texts


def measure(corpus_dir: str) -> dict:
    from rank_bm25 import BM25Okapi

    store, _chunks, _stats = ingest_corpus(corpus_dir, verbose=False)
    rows_all = store.all_chunk_texts()
    corpus_texts = [r[1] for r in rows_all]
    bm25 = BM25Okapi([t.split() for t in corpus_texts])

    rows = []
    for group, question in QUESTIONS:
        q_vec = np.asarray(embed_texts([question])[0], dtype=np.float32)
        hits = store.dense_search(q_vec, top_k=5)
        # bge vectors are L2-normalized, so the stored inner-product
        # score IS cosine similarity — no rescaling needed.
        cosines = [score for _fid, score in hits]
        bm25_scores = bm25.get_scores(question.split())

        rows.append({
            "group": group,
            "question": question,
            "best_cosine": round(float(max(cosines)), 4),
            "mean_top5_cosine": round(float(np.mean(cosines)), 4),
            "best_bm25": round(float(max(bm25_scores)), 4),
        })

    def spread(signal: str) -> dict:
        in_scope = [r[signal] for r in rows if r["group"] == "in_scope"]
        out = [r[signal] for r in rows if r["group"] in ("off_domain", "unrelated")]
        adjacent = [r[signal] for r in rows if r["group"] == "adjacent"]
        # A signal is usable only if the worst in-scope question still
        # scores above the best out-of-scope one; the gap between them is
        # where a threshold can safely sit.
        return {
            "in_scope_min": min(in_scope), "in_scope_max": max(in_scope),
            "adjacent_min": min(adjacent), "adjacent_max": max(adjacent),
            "out_min": min(out), "out_max": max(out),
            "separates": min(in_scope) > max(out),
            "gap": round(min(in_scope) - max(out), 4),
            "suggested_threshold": round((min(in_scope) + max(out)) / 2, 4),
        }

    return {
        "rows": rows,
        "signals": {s: spread(s) for s in ("best_cosine", "mean_top5_cosine", "best_bm25")},
    }


if __name__ == "__main__":
    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/confidence_calibration.json"

    result = measure(corpus_dir)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {out_path}\n")
    for signal, s in result["signals"].items():
        verdict = "SEPARATES" if s["separates"] else "overlaps - unusable"
        print(f"{signal}:  {verdict}")
        print(f"    in_scope  {s['in_scope_min']:.4f} .. {s['in_scope_max']:.4f}")
        print(f"    adjacent  {s['adjacent_min']:.4f} .. {s['adjacent_max']:.4f}")
        print(f"    out       {s['out_min']:.4f} .. {s['out_max']:.4f}")
        if s["separates"]:
            print(f"    gap {s['gap']:.4f}  ->  threshold {s['suggested_threshold']:.4f}")
        print()

    print("per question (best_cosine):")
    for r in sorted(result["rows"], key=lambda r: -r["best_cosine"]):
        print(f"  {r['best_cosine']:.4f}  [{r['group']:<10}] {r['question'][:54]}")

"""Does RAG_SPEC.md §3's confidence gate actually refuse anything?

NFR-4 says the system must say "not found in the provided corpus"
rather than answer from parametric memory when retrieval has nothing
relevant. Q9 of the QA set tests exactly one out-of-scope question,
which is thin evidence for a safety property: one question passing
tells you almost nothing about where the boundary actually sits, or
whether the gate fired at all versus the generation model happening to
refuse on its own.

This runs a balanced set instead — in-scope questions the corpus can
answer, and progressively more out-of-scope ones it cannot, from
adjacent-domain (another refinery's units) through to entirely
unrelated (cooking, astronomy). A working gate should pass the first
group and refuse the last. Anything that refuses NOTHING, or refuses
EVERYTHING, is broken regardless of how Q9 scored.

Retrieval-only by design: the gate lives in retrieve_with_grounding_
check, before any LLM call, so this measures the gate itself rather
than the generation model's willingness to refuse. It also means the
whole sweep runs on embeddings alone, in seconds.
"""

import json
import sys

from backend.evaluation.ingest_corpus import ingest_corpus
from backend.retrieval.grounded_retrieval import (
    CONFIDENCE_THRESHOLD,
    retrieve_with_grounding_check,
)
from backend.retrieval.hybrid_search import rrf_fuse

# Graded by distance from the corpus, so a partial result still says
# WHERE the boundary sits rather than just "it failed".
QUESTIONS = [
    ("in_scope", "What is the WABT end-of-run trigger temperature for HCU-2?"),
    ("in_scope", "What caused the off-spec batch H110F-0847?"),
    ("in_scope", "Which Kero Merox sample exceeded the sulphur spec limit?"),
    ("in_scope", "Why was Tank TK-K-03 at Kasargod held out of service?"),
    ("in_scope", "What is the 8-hour TWA benzene exposure limit?"),
    # Same domain, entities that do not exist anywhere in this corpus.
    ("adjacent", "What is the WABT trigger temperature for hydrocracker HCU-9?"),
    ("adjacent", "What caused the off-spec batch Z999X-0001?"),
    ("adjacent", "Why was Tank TK-Q-88 at Mangalore taken out of service?"),
    ("adjacent", "What is the catalyst changeout procedure for the Coker unit?"),
    # Plausible industrial questions, wrong industry entirely.
    ("off_domain", "What is the recommended torque for a Boeing 737 landing gear bolt?"),
    ("off_domain", "What is the maximum core temperature for a pressurised water reactor?"),
    ("off_domain", "How many megawatts does the Bhakra Nangal dam generate?"),
    # Nothing to do with industry at all.
    ("unrelated", "What is the best way to poach an egg?"),
    ("unrelated", "How far is Proxima Centauri from Earth?"),
    ("unrelated", "Who won the 2018 FIFA World Cup?"),
    ("unrelated", "What is the plot of Pride and Prejudice?"),
]


def run(corpus_dir: str) -> dict:
    store, _chunks, _stats = ingest_corpus(corpus_dir, verbose=False)

    rows = []
    for group, question in QUESTIONS:
        result = retrieve_with_grounding_check(store, question, top_k=5)

        # Recompute the gate's own inputs so the report shows WHY it
        # decided what it decided, not just the verdict.
        fused = rrf_fuse(store, question, 5)
        scores = list(fused.values()) or [0.0]
        top, lo, hi = max(scores), min(scores), max(scores)
        normalized = 1.0 if hi == lo else (top - lo) / (hi - lo)

        rows.append({
            "group": group,
            "question": question,
            "refused": not result.found,
            "reason": result.reason if not result.found else None,
            "top_source": result.chunks[0].source_document if result.found and result.chunks else None,
            "raw_top_score": round(top, 5),
            "raw_min_score": round(lo, 5),
            "normalized_top": round(normalized, 5),
            "candidate_pool": len(scores),
        })

    by_group = {}
    for r in rows:
        g = by_group.setdefault(r["group"], {"n": 0, "refused": 0})
        g["n"] += 1
        g["refused"] += r["refused"]

    return {
        "threshold": CONFIDENCE_THRESHOLD,
        "total": len(rows),
        "total_refused": sum(r["refused"] for r in rows),
        "by_group": by_group,
        "distinct_normalized_values": sorted({r["normalized_top"] for r in rows}),
        "rows": rows,
    }


if __name__ == "__main__":
    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/refusal_at_scale.json"

    result = run(corpus_dir)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {out_path}\n")
    print(f"confidence threshold: {result['threshold']}")
    print(f"refused {result['total_refused']} of {result['total']} questions\n")
    for group in ("in_scope", "adjacent", "off_domain", "unrelated"):
        g = result["by_group"].get(group)
        if g:
            print(f"  {group:<12} refused {g['refused']}/{g['n']}")
    print(f"\ndistinct normalized_top values seen: {result['distinct_normalized_values']}")
    print("\nper question:")
    for r in result["rows"]:
        mark = "REFUSED" if r["refused"] else "answered"
        print(f"  [{r['group']:<10}] norm={r['normalized_top']:<8} {mark:<9} {r['question'][:52]}")

"""Before/after precision@5 measurement for the boilerplate-removal step
(RAG_SPEC.md §2 — see backend/ingestion/boilerplate.py).

Runs the SAME precision analysis (precision_at_k.run_precision_analysis)
twice in ONE process, against two stores built from the same corpus:

  before — ingest_corpus()                        (no boilerplate removal)
  after  — ingest_corpus_with_boilerplate_removal()

Both in one process deliberately: identical embedding model instance,
identical chunking config, identical question set, same machine state.
The only difference between the two measurements is the boilerplate
strip, so any delta is attributable to it and nothing else. (Running
them as two separate script invocations would also work but re-pays the
OCR/embedding model load, and invites exactly the "was anything else
different?" doubt this is meant to settle.)

Writes the full comparison to a JSON file rather than relying on shell
redirection — a real bug earlier in this work was a redirected stdout
file that mixed a status line in with the JSON payload and broke
json.load() downstream.
"""

import json
import sys

from backend.evaluation.ingest_corpus import (
    ingest_corpus,
    ingest_corpus_with_boilerplate_removal,
)
from backend.evaluation.precision_at_k import run_precision_analysis


def compare(corpus_dir: str, questions: list[dict], k: int = 5) -> dict:
    store_before, _, stats_before = ingest_corpus(corpus_dir, verbose=False)
    before = run_precision_analysis(store_before, questions, k=k)

    store_after, _, stats_after = ingest_corpus_with_boilerplate_removal(
        corpus_dir, verbose=False
    )
    after = run_precision_analysis(store_after, questions, k=k)

    metrics = (
        "avg_precision_at_k_fused",
        "avg_precision_at_k_dense_only",
        "avg_precision_at_k_sparse_only",
    )

    return {
        "k": k,
        "corpus_dir": corpus_dir,
        "boilerplate_sentences_detected": stats_after["boilerplate_sentences"],
        "total_chunks_before": stats_before["total_chunks"],
        "total_chunks_after": stats_after["total_chunks"],
        "before": before,
        "after": after,
        "delta": {m: after[m] - before[m] for m in metrics},
        # Per-question deltas matter as much as the average: a fix that
        # improves the mean while breaking a question that previously
        # worked is not an improvement, and the average alone hides it.
        "per_question_delta_fused": [
            {
                "question": b["question"],
                "expected_source": b["expected_source"],
                "before": b["precision_at_k_fused"],
                "after": a["precision_at_k_fused"],
                "delta": a["precision_at_k_fused"] - b["precision_at_k_fused"],
            }
            for b, a in zip(before["per_question"], after["per_question"])
        ],
    }


if __name__ == "__main__":
    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    questions_path = (
        sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/mrpl_qa_test_set.json"
    )
    out_path = (
        sys.argv[3]
        if len(sys.argv) > 3
        else "backend/evaluation/boilerplate_precision_comparison.json"
    )

    with open(questions_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    result = compare(corpus_dir, questions, k=5)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {out_path}")
    print(f"Boilerplate detected: {result['boilerplate_sentences_detected']}")
    print(f"chunks before={result['total_chunks_before']} after={result['total_chunks_after']}")
    for metric, delta in result["delta"].items():
        before_val = result["before"][metric]
        after_val = result["after"][metric]
        print(f"{metric}: {before_val:.3f} -> {after_val:.3f}  (delta {delta:+.3f})")

"""Run a question/expected-answer/expected-source test set against an
ingested corpus, via the real generate_grounded_answer pipeline
(RAG_SPEC.md §4) — no shortcuts, no mocking of retrieval or generation.

This is deliberately generic (question set passed in, not hardcoded to
one corpus) so it's reusable for future accuracy runs, not a throwaway
script for one test.
"""

import json
import sys
from dataclasses import dataclass, field

from backend.retrieval.generation import generate_grounded_answer
from backend.retrieval.vector_store import VectorStore


@dataclass
class QAResult:
    question: str
    expected_answer: str
    expected_source: str
    actual_answer: str
    actual_sources: list[str] = field(default_factory=list)
    found: bool = True


def run_qa_tests(store: VectorStore, questions: list[dict], verbose: bool = True) -> list[QAResult]:
    """`questions` is a list of {"question", "expected_answer", "expected_source"} dicts."""
    results = []
    for i, q in enumerate(questions):
        if verbose:
            print(f"[{i+1}/{len(questions)}] {q['question']}")
        answer = generate_grounded_answer(store, q["question"], top_k=5)
        result = QAResult(
            question=q["question"],
            expected_answer=q["expected_answer"],
            expected_source=q["expected_source"],
            actual_answer=answer.answer_text,
            actual_sources=[c.source_document for c in answer.sources],
            found=answer.found,
        )
        results.append(result)
        if verbose:
            print(f"  -> found={result.found}, sources={result.actual_sources}")
            print(f"  -> answer: {result.actual_answer[:200]}")
    return results


if __name__ == "__main__":
    from backend.evaluation.ingest_corpus import ingest_corpus

    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    questions_file = sys.argv[2] if len(sys.argv) > 2 else "backend/evaluation/mrpl_qa_test_set.json"

    with open(questions_file, "r", encoding="utf-8") as f:
        questions = json.load(f)

    print(f"Ingesting corpus from {corpus_dir}...")
    store, _, ingest_stats = ingest_corpus(corpus_dir, verbose=False)
    print(f"Ingested {ingest_stats['total_chunks']} chunks.\n")

    results = run_qa_tests(store, questions)

    output_path = "qa_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([r.__dict__ for r in results], f, indent=2)
    print(f"\nResults written to {output_path}")

"""Generate a full, untruncated Markdown validation report.

Re-runs RETRIEVAL ONLY (fast, local, no LLM) against a fresh copy of the
corpus to capture the full source passages for each question, then
combines that with already-generated answers from a prior
run_qa_tests.py run (qa_results.json) -- avoids re-paying for the slow
LLM generation step just to get the source text that was already
implicitly used to produce those answers.
"""

import json
import sys

from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check


def _format_chunk(i: int, chunk) -> str:
    page_part = f", page/sheet {chunk.page_number}" if chunk.page_number is not None else ""
    return (
        f"**[{i}] {chunk.source_document}{page_part}** (fused score: {chunk.score:.4f})\n\n"
        f"> {chunk.text}\n"
    )


def generate_report(
    corpus_dir: str,
    qa_results_path: str,
    questions_path: str,
    output_path: str,
    top_k: int = 5,
) -> None:
    from backend.evaluation.ingest_corpus import ingest_corpus

    print(f"Re-ingesting corpus from {corpus_dir} for retrieval-only replay...")
    store, _, ingest_stats = ingest_corpus(corpus_dir, verbose=False)
    print(f"Ingested {ingest_stats['total_chunks']} chunks.\n")

    with open(qa_results_path, "r", encoding="utf-8") as f:
        qa_results = json.load(f)
    with open(questions_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    lines = ["# MRPL RAG/GraphRAG Validation Report\n"]
    lines.append(
        "Full, untruncated question/expected-answer/actual-answer/source-provenance "
        "record for every question in the test set, against the real ingestion -> "
        "retrieval -> generation pipeline (RAG_SPEC.md §2-§4). No summarization "
        "or truncation of any generated text or retrieved passage below.\n"
    )

    for i, (q, result) in enumerate(zip(questions, qa_results), start=1):
        question = q["question"]
        grounding = retrieve_with_grounding_check(store, question, top_k=top_k)

        lines.append(f"\n---\n\n## Q{i}. {question}\n")
        lines.append(f"**Expected answer:** {q['expected_answer']}\n")
        lines.append(f"**Expected source:** {q['expected_source']}\n")
        lines.append(f"\n**Actual answer (full, verbatim):**\n\n{result['actual_answer']}\n")
        lines.append(f"\n**Grounding gate:** `found={grounding.found}`" + (f" — {grounding.reason}" if grounding.reason else "") + "\n")

        if grounding.chunks:
            lines.append(f"\n**Retrieved source passages (top {len(grounding.chunks)}, full text):**\n")
            for j, chunk in enumerate(grounding.chunks, start=1):
                lines.append("\n" + _format_chunk(j, chunk))
        else:
            lines.append("\n**Retrieved source passages:** none (grounding gate did not pass any chunks through)\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_RAG_Test_Corpus"
    qa_results_path = sys.argv[2] if len(sys.argv) > 2 else "qa_results.json"
    questions_path = sys.argv[3] if len(sys.argv) > 3 else "backend/evaluation/mrpl_qa_test_set.json"
    output_path = sys.argv[4] if len(sys.argv) > 4 else "backend/evaluation/VALIDATION_REPORT.md"

    generate_report(corpus_dir, qa_results_path, questions_path, output_path)

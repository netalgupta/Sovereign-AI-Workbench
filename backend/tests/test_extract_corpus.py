"""Tests for extract_corpus.py's durable checkpoint mechanism.

The property being tested throughout: extraction results must survive
independently of whatever happens to the graph database afterward (the
real problem this file exists to solve — see its module docstring).
Mocked extraction, no live Ollama call — this suite is about the
checkpoint file format and resumability, not model behavior.
"""

import json

from backend.evaluation.extract_corpus import extract_corpus, load_extractions
from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk


def _chunk(source: str, index: int, text: str = "chunk text") -> IngestedChunk:
    return IngestedChunk(
        text=text,
        metadata=ChunkMetadata(
            source_document=source, document_type="pdf", page_number=1,
            chunk_index=index, ingestion_date="2026-09-10",
        ),
    )


def test_extractions_round_trip_through_the_checkpoint_file(tmp_path, monkeypatch):
    import backend.evaluation.extract_corpus as extract_corpus_module
    from backend.graph.entity_extraction import ExtractedEntity, ExtractionResult

    def fake_extract(chunk_text, model_id="reasoning-model"):
        return ExtractionResult(
            entities=[ExtractedEntity(type="Equipment", name=f"E-{chunk_text}", attributes={})],
            relationships=[],
        )

    monkeypatch.setattr(extract_corpus_module, "extract_entities_and_relationships", fake_extract)

    output_path = str(tmp_path / "extractions.jsonl")
    chunks = [_chunk("doc1.pdf", 0, "alpha"), _chunk("doc1.pdf", 1, "beta")]

    stats = extract_corpus(chunks, output_path, verbose=False)

    assert stats["chunks_processed"] == 2
    assert stats["errors"] == {}

    loaded = load_extractions(output_path)
    assert len(loaded) == 2
    assert loaded[0][0]["source_document"] == "doc1.pdf"
    assert loaded[0][0]["chunk_index"] == 0
    assert loaded[0][1].entities[0].name == "E-alpha"
    assert loaded[1][1].entities[0].name == "E-beta"


def test_checkpoint_file_is_one_json_object_per_line_not_a_single_array(tmp_path, monkeypatch):
    """This IS the crash-resilience property: each line is independently
    parseable the instant it's written (and flushed), so a crash after
    chunk 2 of 5 still leaves chunks 1-2 fully readable -- a single JSON
    array wouldn't be valid at all until the closing bracket, meaning a
    mid-run crash would corrupt the entire file, losing everything, not
    just the in-flight chunk.
    """
    import backend.evaluation.extract_corpus as extract_corpus_module
    from backend.graph.entity_extraction import ExtractedEntity, ExtractionResult

    def fake_extract(chunk_text, model_id="reasoning-model"):
        return ExtractionResult(
            entities=[ExtractedEntity(type="Equipment", name="X", attributes={})], relationships=[]
        )

    monkeypatch.setattr(extract_corpus_module, "extract_entities_and_relationships", fake_extract)

    output_path = str(tmp_path / "extractions.jsonl")
    extract_corpus([_chunk("doc1.pdf", 0), _chunk("doc1.pdf", 1)], output_path, verbose=False)

    with open(output_path, "r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]

    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # each line independently parses -- not one big array


def test_resume_skips_completed_chunks_and_appends_only_missing_ones(tmp_path, monkeypatch):
    """The exact real scenario this was built for: a first run gets most
    chunks done, then hits transient failures (Ollama 500s, a malformed-
    JSON response) on a few. Resuming must not re-call extraction for
    the chunks that already succeeded, and must not duplicate them in
    the output file -- it should only fill in what's actually missing.
    """
    import backend.evaluation.extract_corpus as extract_corpus_module
    from backend.graph.entity_extraction import ExtractedEntity, ExtractionResult

    call_log = []

    def fake_extract(chunk_text, model_id="reasoning-model"):
        call_log.append(chunk_text)
        return ExtractionResult(
            entities=[ExtractedEntity(type="Equipment", name=f"E-{chunk_text}", attributes={})],
            relationships=[],
        )

    monkeypatch.setattr(extract_corpus_module, "extract_entities_and_relationships", fake_extract)

    output_path = str(tmp_path / "extractions.jsonl")
    all_chunks = [_chunk("doc1.pdf", 0, "alpha"), _chunk("doc1.pdf", 1, "beta"), _chunk("doc1.pdf", 2, "gamma")]

    # First "run": only chunks 0 and 2 succeed (simulating chunk 1 having
    # failed and never been written).
    extract_corpus([all_chunks[0], all_chunks[2]], output_path, verbose=False)
    assert len(call_log) == 2

    # Resume with the FULL chunk list -- must only call extraction for
    # chunk 1 (the missing one), not re-call it for 0 or 2.
    call_log.clear()
    stats = extract_corpus(all_chunks, output_path, verbose=False, resume=True)

    assert call_log == ["beta"]  # only the missing chunk was actually extracted
    assert stats["chunks_processed"] == 1

    loaded = load_extractions(output_path)
    assert len(loaded) == 3  # all three present, none duplicated
    chunk_ids = sorted(f"{meta['source_document']}#{meta['chunk_index']}" for meta, _ in loaded)
    assert chunk_ids == ["doc1.pdf#0", "doc1.pdf#1", "doc1.pdf#2"]


def test_a_failed_chunk_does_not_abort_the_whole_run_or_corrupt_earlier_results(tmp_path, monkeypatch):
    import backend.evaluation.extract_corpus as extract_corpus_module
    from backend.graph.entity_extraction import ExtractedEntity, ExtractionResult

    def flaky_extract(chunk_text, model_id="reasoning-model"):
        if chunk_text == "bad":
            raise ValueError("simulated extraction failure")
        return ExtractionResult(
            entities=[ExtractedEntity(type="Equipment", name="OK", attributes={})], relationships=[]
        )

    monkeypatch.setattr(extract_corpus_module, "extract_entities_and_relationships", flaky_extract)

    output_path = str(tmp_path / "extractions.jsonl")
    chunks = [_chunk("doc1.pdf", 0, "good1"), _chunk("doc1.pdf", 1, "bad"), _chunk("doc1.pdf", 2, "good2")]

    stats = extract_corpus(chunks, output_path, verbose=False)

    assert stats["chunks_processed"] == 2  # the 2 good chunks, not aborted by the bad one
    assert "doc1.pdf#1" in stats["errors"]

    loaded = load_extractions(output_path)
    assert len(loaded) == 2  # only the successful ones were ever written

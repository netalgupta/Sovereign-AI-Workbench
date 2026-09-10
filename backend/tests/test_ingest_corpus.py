"""Tests for the corpus-level two-pass ingestion flow.

The property under test is the ORCHESTRATION, not the pieces: that
boilerplate detection sees one string per DOCUMENT, that extraction
happens exactly once per file (never re-run for pass 2), and that the
detected sentences actually reach the chunker. Each of those was a real
bug at some point while building this — the per-document/per-page mixup
in particular silently measured a disclaimer against the wrong
denominator and reported "no boilerplate found" on a corpus that
visibly had it.

Extraction is faked throughout: this suite is about wiring, and paying
for real OCR/PDF parsing here would make it slow without testing
anything text_extraction.py's own suite doesn't already cover.
"""

import numpy as np

import backend.evaluation.ingest_corpus as ingest_corpus_module
from backend.evaluation.ingest_corpus import ingest_corpus_with_boilerplate_removal
from backend.ingestion.text_extraction import PageText

_DISCLAIMER = "This document is provided for illustrative purposes only."


def _write_corpus(tmp_path, files: dict[str, str]):
    for name, _text in files.items():
        (tmp_path / name).write_text("placeholder", encoding="utf-8")
    return str(tmp_path)


def _patch_pipeline(monkeypatch, pages_by_filename: dict[str, list[PageText]], call_log: list):
    """Fake detect+extract+embed so the test exercises orchestration only."""

    class _TypeInfo:
        detected_type = "pdf"

    monkeypatch.setattr(
        ingest_corpus_module, "detect_document_type", lambda path: _TypeInfo()
    )

    def fake_extract_pages(path, doc_type, ocr_fn=None):
        from pathlib import Path

        name = Path(path).name
        call_log.append(name)
        return pages_by_filename[name]

    monkeypatch.setattr(ingest_corpus_module, "extract_pages", fake_extract_pages)
    # 1024-dim float32 ndarray, matching the real embed_texts' return
    # contract (VectorStore reads .shape) — the values are irrelevant
    # here, the shape is not.
    monkeypatch.setattr(
        ingest_corpus_module,
        "embed_texts",
        lambda texts: np.full((len(texts), 1024), 0.1, dtype=np.float32),
    )


def test_boilerplate_recurring_across_documents_is_stripped_from_every_chunk(
    tmp_path, monkeypatch
):
    pages = {
        "a.pdf": [PageText(page_number=1, text=f"Alpha content about WABT creep. {_DISCLAIMER}")],
        "b.pdf": [PageText(page_number=1, text=f"Beta content about PSA purity. {_DISCLAIMER}")],
        "c.pdf": [PageText(page_number=1, text=f"Gamma content about sulphur spec. {_DISCLAIMER}")],
    }
    corpus_dir = _write_corpus(tmp_path, dict.fromkeys(pages, ""))
    _patch_pipeline(monkeypatch, pages, call_log=[])

    _store, chunks, stats = ingest_corpus_with_boilerplate_removal(corpus_dir, verbose=False)

    assert _DISCLAIMER.lower() in stats["boilerplate_sentences"]
    assert chunks, "expected chunks to be produced"
    for chunk in chunks:
        assert "illustrative purposes" not in chunk.text.lower()
    # The real content must survive the strip, not be collateral damage.
    assert any("WABT creep" in c.text for c in chunks)
    assert any("PSA purity" in c.text for c in chunks)


def test_each_file_is_extracted_exactly_once_across_both_passes(tmp_path, monkeypatch):
    """The whole reason pages_to_chunks was split out of ingest_document:
    a two-pass flow must not re-run extraction (OCR/ASR included) for
    pass 2. If this regresses, every corpus run silently doubles its
    most expensive step."""
    pages = {
        "a.pdf": [PageText(page_number=1, text=f"Alpha content here. {_DISCLAIMER}")],
        "b.pdf": [PageText(page_number=1, text=f"Beta content here. {_DISCLAIMER}")],
    }
    corpus_dir = _write_corpus(tmp_path, dict.fromkeys(pages, ""))
    call_log: list[str] = []
    _patch_pipeline(monkeypatch, pages, call_log)

    ingest_corpus_with_boilerplate_removal(corpus_dir, verbose=False)

    assert sorted(call_log) == ["a.pdf", "b.pdf"]


def test_boilerplate_is_counted_per_document_not_per_page(tmp_path, monkeypatch):
    """Real bug this pins: the first version passed PAGE-level texts to
    detect_boilerplate_sentences, whose contract is one string per
    DOCUMENT. Here the disclaimer sits on only the LAST page of each
    3-page document. Per-page counting sees 2 of 6 "documents" (33%,
    below threshold, undetected); correct per-document counting sees 2
    of 2 (100%)."""
    def _doc(prefix: str) -> list[PageText]:
        return [
            PageText(page_number=1, text=f"{prefix} page one content."),
            PageText(page_number=2, text=f"{prefix} page two content."),
            PageText(page_number=3, text=f"{prefix} page three content. {_DISCLAIMER}"),
        ]

    pages = {"a.pdf": _doc("Alpha"), "b.pdf": _doc("Beta")}
    corpus_dir = _write_corpus(tmp_path, dict.fromkeys(pages, ""))
    _patch_pipeline(monkeypatch, pages, call_log=[])

    _store, chunks, stats = ingest_corpus_with_boilerplate_removal(corpus_dir, verbose=False)

    assert _DISCLAIMER.lower() in stats["boilerplate_sentences"]
    for chunk in chunks:
        assert "illustrative purposes" not in chunk.text.lower()


def test_a_sentence_unique_to_one_document_is_never_stripped(tmp_path, monkeypatch):
    """The inverse guard: boilerplate removal must not delete real
    content that happens to look formulaic in a single document."""
    pages = {
        "a.pdf": [PageText(page_number=1, text="The WABT trigger is 415 degC. Unique closing note here.")],
        "b.pdf": [PageText(page_number=1, text="PSA-3 purity dropped to 99.1 percent on Tuesday.")],
    }
    corpus_dir = _write_corpus(tmp_path, dict.fromkeys(pages, ""))
    _patch_pipeline(monkeypatch, pages, call_log=[])

    _store, chunks, stats = ingest_corpus_with_boilerplate_removal(corpus_dir, verbose=False)

    assert stats["boilerplate_sentences"] == []
    assert any("Unique closing note here." in c.text for c in chunks)
    assert any("99.1 percent" in c.text for c in chunks)

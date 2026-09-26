"""A book is summarised by its own chapters, and every claim is checked.

Model calls are stubbed; what is tested is the part that decides whether
the summary follows the book and says only what the book says: where the
chapters are, which pages each one reads, which sentences are removed,
and what the coverage note tells the reader.
"""

from __future__ import annotations

from collections import Counter

from backend.orchestrator import book_agent as B


# ── where the chapters are ──────────────────────────────────────────────────


def test_chapters_are_placed_by_the_best_non_decreasing_labelling():
    """A greedy first-appearance rule failed on the real book: one early page
    naming chapter 11 in a cross-reference blocked every chapter after it."""
    votes = {p: Counter({1: 3}) for p in range(17, 70)}
    votes[20] = Counter({11: 4})                     # a cross-reference, not a chapter start
    votes.update({p: Counter({2: 3}) for p in range(70, 106)})
    votes.update({p: Counter({3: 2, 1: 1}) for p in range(106, 150)})
    starts = B.locate_chapters(votes, 12)
    assert starts == {1: 17, 2: 70, 3: 106}


def test_a_chapter_the_pages_never_mention_is_not_invented():
    votes = {p: Counter({1: 2}) for p in range(1, 30)}
    votes.update({p: Counter() for p in range(30, 60)})   # blank or unnumbered pages
    starts = B.locate_chapters(votes, 5)
    assert set(starts) == {1}


def test_section_and_figure_numbers_vote_for_their_chapter():
    pages = {20: "4.4.2 Offline Attacks are the next step. See Figure 4.12 and Table 4.3.",
             21: "Nothing numbered here.",
             22: "The rate was 3.4 g/10min."}          # a decimal, not a section number
    votes = B.chapter_votes(pages, after=10, n_chapters=12)
    assert votes[20][4] == 3
    assert not votes[21] and not votes[22]


# ── what each chapter reads ─────────────────────────────────────────────────


def test_every_page_of_a_chapter_is_read_and_blank_pages_are_skipped():
    pages = {p: ("x" * 1500 if p != 25 else "") for p in range(20, 40)}
    wins = B.windows(pages, 20, 39)
    read = {p for first, last, _ in wins for p in range(first, last + 1)}
    assert set(range(20, 40)) - {25} <= read, "every page with text is read"
    assert all("[page 25]" not in text for _, _, text in wins)
    assert all(len(text) < B.WINDOW_CHARS + 2000 for _, _, text in wins)


# ── what survives the checks ────────────────────────────────────────────────


def _chapter(body: str) -> B.Chapter:
    ch = B.Chapter(number=5, title="Phishing and Identity Theft", first_page=210, last_page=250)
    ch.points = [{"point": "Spear phishing targets a specific organisation.", "page": 212}]
    ch.body = body
    return ch


def test_sentences_about_the_task_are_removed(monkeypatch):
    """Measured in an earlier summary: "According to [S1]…", "…as requested
    for this report section", "not provided in the sources, it is known…"."""
    monkeypatch.setattr(B, "_ask_json", lambda *a, **k: {"unsupported": []})
    ch = _chapter("Spear phishing targets a specific organisation. According to [S1], it is common. "
                  "The details are not provided in the sources.")
    B.check_chapter(ch, "Spear phishing targets a specific organisation.", writer="reasoning-model")
    assert ch.body == "Spear phishing targets a specific organisation."
    assert len(ch.removed) == 2


def test_a_figure_the_book_does_not_contain_is_removed(monkeypatch):
    monkeypatch.setattr(B, "_ask_json", lambda *a, **k: {"unsupported": []})
    ch = _chapter("Spear phishing targets a specific organisation. It caused 4200 incidents in 2009.")
    B.check_chapter(ch, "Spear phishing targets a specific organisation. The 2009 report.", writer="w")
    assert "4200" not in ch.body and any("figure not in the book" in r for r in ch.removed)


def test_sentences_the_checker_finds_unsupported_are_removed(monkeypatch):
    monkeypatch.setattr(B, "_ask_json", lambda *a, **k: {"unsupported": [2]})
    ch = _chapter("Spear phishing targets a specific organisation. It is a cognizable offence "
                  "investigated without a warrant.")
    B.check_chapter(ch, "Spear phishing targets a specific organisation.", writer="w")
    assert ch.body == "Spear phishing targets a specific organisation."


def test_a_checker_that_rejects_most_of_a_chapter_is_not_trusted(monkeypatch):
    monkeypatch.setattr(B, "_ask_json", lambda *a, **k: {"unsupported": [1, 2, 3]})
    body = "One claim here. Another claim there. A third claim again."
    ch = _chapter(body)
    B.check_chapter(ch, body, writer="w")
    assert ch.body == body and "not applied" in ch.removed[-1]


# ── the whole pipeline, and what it tells the reader ────────────────────────


def _book_chunks():
    from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk

    texts = {p: f"Front matter page {p}." for p in range(1, 4)}
    texts[4] = "Contents 1 Introduction to Cybercrime 2 Cyberoffenses 3 Mobile Devices"
    for p in range(5, 45):
        texts[p] = f"1.{p % 7 + 1} Cybercrime Basics are described on this page. Figure 1.{p % 5 + 1} shows it."
    for p in range(45, 90):
        texts[p] = f"2.{p % 7 + 1} Attack Planning is described on this page. Figure 2.{p % 5 + 1} shows it."
    return [IngestedChunk(text=t, metadata=ChunkMetadata(
        source_document="Book.pdf", document_type="scanned_pdf", page_number=p, chunk_index=0,
        ingestion_date="2026-09-26")) for p, t in texts.items()]


def _stub_models(monkeypatch):
    def ask(prompt, **_k):
        if "TABLE OF CONTENTS" in prompt:
            return {"title": "Cyber Security", "chapters": [
                {"number": 1, "title": "Introduction to Cybercrime"},
                {"number": 2, "title": "Cyberoffenses"},
                {"number": 3, "title": "Mobile Devices"}]}
        if "List the important points" in prompt:
            return {"points": [{"point": "This stretch explains a mechanism in the book's own terms.",
                                "page": int(prompt.split("pages ")[1].split("-")[0])}]}
        if "Check a summary" in prompt:
            return {"unsupported": []}
        return {"paragraphs": ["The chapter explains a mechanism in the book's own terms."]}

    monkeypatch.setattr(B, "_ask_json", ask)


def test_the_summary_follows_the_chapters_and_says_what_the_file_lacks(monkeypatch):
    _stub_models(monkeypatch)
    result = B.summarise_book("Summarise the book", "Book.pdf", _book_chunks(), writer="w")
    assert [c["number"] for c in result["chapters"]] == [1, 2]
    assert result["chapters"][0]["pages"][0] < result["chapters"][1]["pages"][0]
    assert result["missing_chapters"] == [{"number": 3, "title": "Mobile Devices"}]
    assert "chapter 3, Mobile Devices is listed in its contents but not contained in the file" \
        in result["coverage"]
    assert result["overview"]


def test_a_document_without_contents_falls_back_to_the_generic_path(monkeypatch):
    monkeypatch.setattr(B, "_ask_json", lambda *a, **k: {"title": "", "chapters": []})
    assert B.summarise_book("Summarise it", "Book.pdf", _book_chunks(), writer="w") is None


def test_a_book_becomes_overview_chapters_and_coverage_sections(monkeypatch):
    from backend.orchestrator import document_agent as D

    _stub_models(monkeypatch)
    docs = [{"id": "S1", "document": "Book.pdf", "pages": [1], "truncated": False, "text": "x" * 40000}]
    spec = D._book_spec("Summarise the book", docs, _book_chunks(), writer="w", progress=None)
    headings = [s["heading"] for s in spec["sections"]]
    assert headings[0] == "Overview" and headings[-1] == "What this summary covers"
    assert headings[1] == "Chapter 1: Introduction to Cybercrime"
    assert spec["sections"][1]["note"].startswith("Pages ")

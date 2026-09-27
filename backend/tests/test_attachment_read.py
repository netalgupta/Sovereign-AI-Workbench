"""A document attached to one chat message is READ, and stays out of the corpus.

Reported 27 Sep: "This file, tell me ab tit [Temporary Attachment: x.pdf]"
answered "I see a temporary attachment but no specific question" -- the
frontend sent the file's NAME only; nothing ever read a PDF/DOCX attached
in the chat.
"""

import io

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_a_pdf_attached_in_chat_is_read():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Tutorial 1: shell and tube exchanger duty is 4.2 MW.")
    doc.new_page().insert_text((72, 72), "Second page mentions fouling factor 0.0002.")
    res = client.post("/api/attachments/read",
                      files={"file": ("Tut 1.pdf", io.BytesIO(doc.tobytes()), "application/pdf")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pages"] == 2
    assert "4.2 MW" in body["text"] and "fouling factor" in body["text"]
    assert body["truncated"] is False


def test_a_docx_attached_in_chat_is_read_and_not_added_to_the_corpus():
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("Permit PTW-7781 covers the benzene column entry.")
    buf = io.BytesIO()
    d.save(buf)
    before = client.get("/api/corpus").json().get("count")
    res = client.post("/api/attachments/read",
                      files={"file": ("permit.docx", io.BytesIO(buf.getvalue()),
                                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert res.status_code == 200, res.text
    assert "PTW-7781" in res.json()["text"]
    assert client.get("/api/corpus").json().get("count") == before


def test_an_empty_file_is_refused_with_a_reason():
    res = client.post("/api/attachments/read", files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")})
    assert res.status_code == 400
    assert "empty" in res.json()["detail"]


def test_a_message_with_an_attached_file_is_never_a_shortcut():
    """'List all houses from the document' + a spreadsheet got the corpus inventory."""
    from backend.orchestrator.path_router import decide_path
    from backend.retrieval.corpus_questions import is_corpus_question

    attached = ("\n\nAnswer from the attached file(s) below. They were attached to this message and are "
                "not in the corpus.\n\nATTACHED FILE: Best House 2026.xlsx\n<<<\nHouse | Price\nRosewood | 1.2 Cr\n>>>")
    for question in ("List all houses from the document", "hi", "What documents do you have?"):
        assert not is_corpus_question(question + attached)
        assert decide_path(question + attached).path == "agentic", question
    # without a file, the inventory still answers the collection question
    assert is_corpus_question("What documents do you have?")


def test_a_workbook_reads_as_tables_with_every_tab_named():
    """Best House 2026.xlsx: 11 tabs (one per institute), cells with line breaks,
    26 columns wide. It read as 40 KB of tabs, rows split mid-cell, and "list
    the institutes" got one house from the first sheet."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.active.title = "Sakarwadi"
    for name in ("Laxmiwadi", "CONSOLIDATED"):
        wb.create_sheet(name)
    for ws in wb.worksheets:
        ws["A1"] = "Name of the Institute -"
        ws["B1"] = "Periyar Elephants \n(Purple House)"
        ws["Z1"] = None
        ws["A2"] = "Total (OUT OF 500)"
        ws["B2"] = 420
        ws["AF40"] = ""  # a far, empty corner: width without content
    wb["CONSOLIDATED"]["B1"] = "Somaiya Vidya Mandir Sakarwadi"
    buf = io.BytesIO()
    wb.save(buf)

    res = client.post("/api/attachments/read", files={"file": ("Best House.xlsx", io.BytesIO(buf.getvalue()),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert res.status_code == 200, res.text
    body = res.json()
    text = body["text"]
    assert body["unit"] == "sheet" and body["pages"] == 3
    assert "This workbook has 3 sheets (tabs): Sakarwadi; Laxmiwadi; CONSOLIDATED" in text
    assert "Sheet 2 of 3: Laxmiwadi" in text
    # a row is one line, with its cells in order
    assert "Name of the Institute - | Periyar Elephants (Purple House)" in text
    assert "Total (OUT OF 500) | 420" in text
    assert "--- page" not in text
    assert "\t" not in text and "| |" not in text.split("\n")[-1]
    assert len(text) < 1000


def test_a_request_for_code_files_is_not_a_question_about_the_collection():
    """'...as separate files: app.py, requirements.txt and a Dockerfile. Show
    each file's full contents.' was answered with the corpus inventory."""
    from backend.retrieval.corpus_questions import is_corpus_question

    assert not is_corpus_question("Give me a minimal Flask hello-world project as separate files: app.py, "
                                  "requirements.txt and a Dockerfile. Show each file's full contents.")
    assert not is_corpus_question("Show all files for a docker compose setup")
    assert not is_corpus_question("Write a script that lists the files in a folder")
    # the collection questions still are
    for q in ("What documents do you have?", "List all the files", "How many sources are indexed?",
              "What's in the corpus?"):
        assert is_corpus_question(q), q


# ── folders: locations, not just file names ────────────────────────────────

def test_a_short_question_with_its_own_subject_is_not_a_follow_up():
    """'Find both sop summary and quality' (6 words) was treated as a
    follow-up and had the previous turn's cyber-security book appended."""
    from backend.memory.resolver import needs_resolution

    assert not needs_resolution("Find both sop summary and quality")
    assert needs_resolution("give all of them")
    assert needs_resolution("what about the rest?")


def test_folder_words_match_documents_by_location(tmp_path, monkeypatch):
    """The SOPs live in 01_SOPs_and_Procedures and quality records in
    03_Quality_and_Process_Data; no passage's text says either name."""
    from backend.api import source_config
    from backend.retrieval import catalog as C

    root = tmp_path / "Plant"
    for rel in ("01_SOPs_and_Procedures/SOP-114-Changeout.docx", "03_Quality_and_Process_Data/Batch_QA_Aug.pdf",
                "02_Inspection/Pipeline_Incident.pdf"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x", encoding="utf-8")
    source_config.save([{"id": "p", "name": "Plant", "path": str(root), "enabled": True}])
    monkeypatch.setattr(C, "_cache", {"key": None, "docs": {}})

    class Store:
        def document_names(self):
            return ["SOP-114-Changeout.docx", "Batch_QA_Aug.pdf", "Pipeline_Incident.pdf"]

        def generation(self):
            return 1

    store = Store()
    scores = C.location_scores(store, "Find both sop summary and quality")
    assert set(scores) == {"SOP-114-Changeout.docx", "Batch_QA_Aug.pdf"}
    assert C.location_label(store, "Batch_QA_Aug.pdf") == "Plant / 03_Quality_and_Process_Data / Batch_QA_Aug.pdf"
    listing = dict((k, [d.name for d in v]) for k, v in C.folder_listing(store, "what is in the quality folder"))
    assert listing == {"Plant / 03_Quality_and_Process_Data": ["Batch_QA_Aug.pdf"]}

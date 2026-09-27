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

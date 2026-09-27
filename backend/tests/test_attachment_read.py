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

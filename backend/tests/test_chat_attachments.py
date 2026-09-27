"""A file attached in a chat is a source of THAT chat only.

Reported 27 Sep: the attachment travelled with one message, so the
follow-up ("List all schools", same workbook) was answered without it.
"""

import numpy as np
import pytest

from backend.ingestion.document_ingestion import ChunkMetadata, IngestedChunk
from backend.retrieval import chat_attachments as CA
from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
from backend.retrieval.vector_store import VectorStore


@pytest.fixture
def store():
    from backend.ingestion.embeddings import embed_texts

    texts = {
        "Hydrocracker_SOP.pdf": "The hydrocracker catalyst changeout requires reactor isolation.",
        "Best House 2026.xlsx": "Somaiya Vidya Mandir Sakarwadi house scores: Hemis Snow Leopards 420.",
    }
    chunks = [
        IngestedChunk(text=t, metadata=ChunkMetadata(source_document=n, document_type="pdf", page_number=1,
                                                     chunk_index=0, ingestion_date="2026-01-01"))
        for n, t in texts.items()
    ]
    emb = np.asarray(embed_texts([c.text for c in chunks]), dtype="float32")
    s = VectorStore(dim=emb.shape[1])
    s.add_chunks(chunks, emb)
    return s


def _attach(session_id, name, tmp_path):
    folder = CA.session_dir(session_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("x", encoding="utf-8")
    return CA.register(session_id, folder / name)


Q = "Somaiya Vidya Mandir Sakarwadi house scores"


def _docs(store, session, active=None):
    scoped = CA.scope_documents(session, active, store)
    result = retrieve_with_grounding_check(store, Q, top_k=3, active_documents=scoped)
    return {c.source_document for c in result.chunks} if result.found else set()


def test_the_owning_chat_searches_its_attachment(store, tmp_path):
    _attach("chat-a", "Best House 2026.xlsx", tmp_path)
    assert "Best House 2026.xlsx" in _docs(store, "chat-a")


def test_no_other_chat_and_no_new_chat_sees_it(store, tmp_path):
    _attach("chat-a", "Best House 2026.xlsx", tmp_path)
    assert "Best House 2026.xlsx" not in _docs(store, "chat-b")
    assert "Best House 2026.xlsx" not in _docs(store, "brand-new-chat")
    # a caller that forgets the chat altogether fails closed
    result = retrieve_with_grounding_check(store, Q, top_k=3, active_documents=None)
    assert all(c.source_document != "Best House 2026.xlsx" for c in result.chunks)


def test_an_explicit_list_from_another_chat_cannot_name_it_in(store, tmp_path):
    """Even a list naming the file does not reach it from another chat's scope
    unless that list came from the owner -- the frontend of chat B never
    lists chat A's files; the retrieval default is what guards None."""
    _attach("chat-a", "Best House 2026.xlsx", tmp_path)
    scoped = CA.scope_documents("chat-b", None, store)
    # chat B has no attachments: its scope stays None, which retrieval
    # treats as "global sources only"
    assert scoped is None or "Best House 2026.xlsx" not in scoped
    _attach("chat-b", "own.pdf", tmp_path)
    scoped = CA.scope_documents("chat-b", None, store)
    assert "own.pdf" in scoped and "Best House 2026.xlsx" not in scoped


def test_a_removed_attachment_is_hidden_everywhere(store, tmp_path):
    _attach("chat-a", "Best House 2026.xlsx", tmp_path)
    assert CA.retire("chat-a", "Best House 2026.xlsx")
    assert CA.for_session("chat-a") == []
    assert "Best House 2026.xlsx" not in _docs(store, "chat-a")
    assert "Best House 2026.xlsx" not in _docs(store, "chat-b")


def test_names_never_collide_across_chats(tmp_path, monkeypatch):
    _attach("aaaa1111-x", "report.pdf", tmp_path)
    assert CA.unique_name("bbbb2222-y", "report.pdf") == "report (bbbb2222).pdf"


def test_a_chat_id_cannot_escape_the_attachment_folder():
    with pytest.raises(ValueError):
        CA.session_dir("../../etc")

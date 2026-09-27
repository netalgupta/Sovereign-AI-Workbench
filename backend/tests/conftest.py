"""Suite-wide guards for tests that touch real local services.

TWO THINGS THE SUITE MUST NOT DO TO A DEVELOPER'S MACHINE.

1. Start background graph extraction. Ingesting a file schedules entity
   extraction (backend/graph/auto_extract.py): model calls in a daemon
   thread that outlives the test and writes to the real Neo4j and to the
   COMMITTED extraction cache. MEASURED: a graph test counting Equipment
   nodes saw 2 where it created 1, because an earlier test's extraction
   was still writing. Off for every test.

2. Wipe a graph it did not create. The Neo4j tests clear the database
   before and after (MATCH (n) DETACH DELETE n) -- the SAME database the
   app serves. Running the full suite with Docker up deleted the
   knowledge graph the demo shows. They now skip when the database holds
   data, unless WORKBENCH_TEST_ALLOW_NEO4J_WIPE=1 says wiping is fine.
   Against an empty database they run as before, and clearing it
   afterwards leaves it as they found it.

3. Write to the real audit trail. Any test that approved, refused or
   executed something without naming its own log appended to
   backend/audit/audit.jsonl -- the append-only governance record the
   demo shows. MEASURED: 96 of its 932 entries were pytest runs, with
   temp-directory paths. The default audit log and approval ledger now
   live in each test's tmp directory.

4. Rewrite the operator's source list. configured_sources.json and
   deleted_sources.json are anchored to the repo (backend/api/
   source_config.py); a test that adds and deletes a source rewrote the
   REAL list and dropped a book the operator had added. They point at
   each test's tmp directory too.
"""

from __future__ import annotations

import os

import pytest

os.environ["WORKBENCH_AUTO_EXTRACT_GRAPH"] = "0"


def wipeable_neo4j_client(uri: str, user: str, password: str):
    """A connected client on a database this test may clear, else skip."""
    from backend.graph.neo4j_client import GraphClient

    client = GraphClient(uri, user, password)
    if os.environ.get("WORKBENCH_TEST_ALLOW_NEO4J_WIPE") != "1":
        existing = client.run_cypher("MATCH (n) RETURN count(n) AS c")[0]["c"]
        if existing:
            client.close()
            pytest.skip(
                f"Neo4j at {uri} holds {existing} node(s) this test did not create, and "
                "the test clears the database. Set WORKBENCH_TEST_ALLOW_NEO4J_WIPE=1 to "
                "run it anyway (rebuild afterwards: py -3 -m backend.evaluation.build_graph)."
            )
    return client


@pytest.fixture(autouse=True)
def _audit_trail_in_tmp(tmp_path, monkeypatch):
    """Default AuditLog / ApprovalGate files go to tmp, never to the real trail."""
    import backend.paths

    monkeypatch.setattr(backend.paths, "REPO_ROOT", tmp_path)
    (tmp_path / "backend" / "audit").mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def _source_lists_in_tmp(tmp_path, monkeypatch):
    """The operator's source lists are never touched by a test."""
    from backend.api import source_config

    monkeypatch.setattr(source_config, "CONFIG_PATH", tmp_path / "configured_sources.json")
    monkeypatch.setattr(source_config, "DELETED_PATH", tmp_path / "deleted_sources.json")


@pytest.fixture(autouse=True)
def _chat_attachments_in_tmp(tmp_path, monkeypatch):
    """Chat attachments (files and registry) are never written to real storage by a test."""
    from backend.retrieval import chat_attachments

    monkeypatch.setattr(chat_attachments, "ROOT", tmp_path / "chat_attachments")


@pytest.fixture(autouse=True)
def _corpus_cache_read_only(monkeypatch):
    """Tests READ the real corpus cache (.workbench/) but never WRITE it.

    A test that ingested a file through the live pipeline saved the result
    to the operator's cache: sop_test_procedure_*.txt documents sat in the
    real index and outranked SOP-114 for "a report of SOPs and procedures".
    """
    from backend.api.state import PipelineState

    monkeypatch.setattr(PipelineState, "_write_corpus_cache", lambda self, chunks: None)
    monkeypatch.setattr(PipelineState, "_write_index", lambda self: None)

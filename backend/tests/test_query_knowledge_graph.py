"""query_knowledge_graph answers about the entity asked for, or says it has none.

Called through the registry, the way the agent calls it (Review Rule 1).
Found in review: no match returned nodes[0] as if it were the answer;
`depth` was accepted and ignored; the target could be cut from its own
result; and an unreadable live graph fell back to an exported snapshot.
"""

from __future__ import annotations

import pytest

from backend.tools import netal_tools as NT
from backend.tools.registry import call_tool

GRAPH = {
    "nodes": [
        {"id": 1, "labels": ["Unit"], "properties": {"name": "Hydrocracker HCU-2"}},
        {"id": 2, "labels": ["Equipment"], "properties": {"tag": "R-201"}},
        {"id": 3, "labels": ["Document"], "properties": {"filename": "SOP-114.docx"}},
        {"id": 4, "labels": ["Incident"], "properties": {"summary": "Reactor bed delta-P rise"}},
    ],
    "relationships": [
        {"id": "a", "source": 1, "target": 2, "type": "HAS_EQUIPMENT"},
        {"id": "b", "source": 3, "target": 2, "type": "REFERENCES"},
        {"id": "c", "source": 4, "target": 2, "type": "INVOLVES"},
    ],
}


@pytest.fixture(autouse=True)
def live_graph(monkeypatch):
    monkeypatch.setattr(NT, "_load_graph", lambda: (GRAPH, "live"))


def test_no_match_is_no_answer_not_the_first_entity_in_the_graph():
    out = call_tool("query_knowledge_graph", {"entity_name": "HCU-9"})
    assert out["found"] is False
    assert out["nodes"] == []


def test_the_target_is_always_in_its_own_result():
    out = call_tool("query_knowledge_graph", {"entity_name": "R-201"})
    assert out["found"] and out["target"] == "R-201"
    assert any(n["is_target"] for n in out["nodes"])


def test_depth_reaches_further():
    one = call_tool("query_knowledge_graph", {"entity_name": "Hydrocracker HCU-2", "depth": 1})
    two = call_tool("query_knowledge_graph", {"entity_name": "Hydrocracker HCU-2", "depth": 2})
    names_one = {n["name"] for n in one["nodes"]}
    names_two = {n["name"] for n in two["nodes"]}
    assert names_one == {"Hydrocracker HCU-2", "R-201"}
    assert {"SOP-114.docx", "Reactor bed delta-P rise"} <= names_two


def test_relationship_type_filters():
    out = call_tool("query_knowledge_graph", {"entity_name": "R-201", "relationship_type": "REFERENCES"})
    assert {r["type"] for r in out["relationships"]} == {"REFERENCES"}


def test_an_unreachable_live_graph_is_unavailable_not_a_snapshot(monkeypatch):
    import backend.api.routes as R

    monkeypatch.undo()                       # the real _load_graph
    monkeypatch.setattr(R, "get_graph", lambda: (_ for _ in ()).throw(ConnectionError("neo4j down")))
    graph, source = NT._load_graph()
    assert graph is None and source == "unavailable"

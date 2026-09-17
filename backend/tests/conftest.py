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

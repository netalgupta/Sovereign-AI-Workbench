"""Run GRAPH_SPEC.md §6's signature query against the built graph —
the README's Q10, kept separate from run_qa_tests.py's plain-RAG
questions because this IS a graph query, not plain retrieval (per the
corpus README's own explicit distinction).
"""

import sys

from backend.graph.neo4j_client import GraphClient

if __name__ == "__main__":
    segment_name = sys.argv[1] if len(sys.argv) > 1 else "Mangalore-Hassan"
    neo4j_uri = sys.argv[2] if len(sys.argv) > 2 else "bolt://localhost:7687"
    neo4j_user = sys.argv[3] if len(sys.argv) > 3 else "neo4j"
    neo4j_password = sys.argv[4] if len(sys.argv) > 4 else "testpassword123"

    client = GraphClient(neo4j_uri, neo4j_user, neo4j_password)
    result = client.signature_pipeline_segment_query(segment_name)
    client.close()

    print(f"segment_found: {result.segment_found}")
    print(f"related_documents: {result.related_documents}")
    print(f"related_incidents: {result.related_incidents}")

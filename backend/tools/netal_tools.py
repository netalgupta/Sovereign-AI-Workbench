"""Netal backend tools — provenance, correspondence, and graph analytics.

TOOLS.MD OWNERSHIP
  Row 16 — Version/revision tracking        (category: retrieval)
  Row 18 — Correspondence summarisation      (category: retrieval)
  Row 32 — NetworkX graph analytics          (category: computation)
  Row 60 — Multi-location correspondence    (category: retrieval)
"""

from __future__ import annotations

import json
import pathlib
import re
import urllib.request
from typing import Optional

from backend.tools.registry import tool


# ---------------------------------------------------------------------------
# Row 16 — Version / revision tracking
# ---------------------------------------------------------------------------

@tool(
    name="get_document_revision",
    category="retrieval",
    tools_md_row=16,
    description=(
        "Check whether a procedure document (SOP, circular, standard) is "
        "current, superseded, or has a newer revision. Returns the revision "
        "identifier, effective date, and whether a more recent version exists "
        "in the corpus. Use this before citing an SOP to verify currency — "
        "referencing a superseded revision for a safety-critical procedure is "
        "a compliance failure.\n"
        "Pass the document name or SOP number (e.g. 'SOP-114' or "
        "'Hydrocracker Catalyst Changeout'). If multiple revisions exist in "
        "the corpus they are all returned, newest first."
    ),
)
def get_document_revision(document_name: str) -> dict:
    """Return revision metadata for a procedure document.

    Searches the ingested corpus for any document whose filename or
    extracted title matches document_name, then extracts revision
    identifiers (Rev-N, v1.2, Issue 3, etc.) from the text and metadata.

    Returns:
        found, revisions list with is_latest flag, warning if superseded doc found.
    """
    from backend.retrieval.vector_store import get_vector_store

    store = get_vector_store()
    if store is None or not store.chunks:
        return {
            "found": False,
            "document_name": document_name,
            "revisions": [],
            "latest_revision": None,
            "warning": None,
            "note": "No corpus loaded.",
        }

    query_lower = document_name.lower().replace("-", " ").replace("_", " ")
    matching_chunks = [
        c for c in store.chunks
        if query_lower in (c.get("source_document") or "").lower().replace("-", " ").replace("_", " ")
        or query_lower in (c.get("text") or "")[:300].lower()
    ]

    if not matching_chunks:
        return {
            "found": False,
            "document_name": document_name,
            "revisions": [],
            "latest_revision": None,
            "warning": None,
            "note": "No document matching that name found in the corpus.",
        }

    rev_pattern = re.compile(
        r"(?:Rev(?:ision)?[\s.\-]*)([A-Z]?\d+(?:\.\d+)?)"
        r"|(?:Issue\s+)(\d+)"
        r"|(?:v\.?\s*)(\d+\.\d+)"
        r"|(?:Version\s+)(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    date_pattern = re.compile(
        r"(?:effective|issued|dated?|date)[:\s]+(\d{1,2}[\s\-/]\w+[\s\-/]\d{2,4}"
        r"|\d{4}[\-/]\d{2}[\-/]\d{2})",
        re.IGNORECASE,
    )

    seen_docs: dict[str, dict] = {}
    for chunk in matching_chunks:
        src = chunk.get("source_document") or "unknown"
        text = chunk.get("text") or ""
        rev_str = None
        for groups in rev_pattern.findall(text + " " + src):
            candidate = next((g for g in groups if g), None)
            if candidate:
                rev_str = candidate
                break
        if rev_str is None:
            fn_match = rev_pattern.search(src)
            if fn_match:
                rev_str = next((g for g in fn_match.groups() if g), None)
        date_match = date_pattern.search(text)
        eff_date = date_match.group(1) if date_match else None
        if src not in seen_docs or (rev_str and not seen_docs[src]["revision"]):
            seen_docs[src] = {
                "revision": rev_str or "unknown",
                "effective_date": eff_date,
                "source_document": src,
                "page": chunk.get("page_number") or 1,
                "is_latest": True,
            }

    revisions = sorted(seen_docs.values(), key=lambda r: r["revision"], reverse=True)
    for i, rev in enumerate(revisions):
        rev["is_latest"] = i == 0

    latest = revisions[0]["revision"] if revisions else None
    warning = None
    if len(revisions) > 1:
        warning = (
            f"Multiple revisions of '{document_name}' found. "
            f"Verify you are citing the latest (Rev {latest})."
        )

    return {
        "found": True,
        "document_name": document_name,
        "revisions": revisions,
        "latest_revision": latest,
        "warning": warning,
        "note": f"{len(revisions)} revision(s) found in corpus.",
    }


# ---------------------------------------------------------------------------
# Row 18 — Correspondence / email summarisation
# ---------------------------------------------------------------------------

@tool(
    name="summarise_correspondence",
    category="retrieval",
    tools_md_row=18,
    description=(
        "Summarise a depot-to-HQ or inter-department correspondence thread "
        "from the corpus. Returns: a one-paragraph summary, key action "
        "items, and any items that appear to require HQ approval.\n"
        "Pass the document name or a keyword identifying the thread "
        "(e.g. 'Kasargod depot thread', 'tank TK-K-03'). All content is "
        "grounded in retrieved text — nothing is added."
    ),
)
def summarise_correspondence(
    document_or_query: str,
    focus: Optional[str] = None,
) -> dict:
    """Retrieve and summarise a correspondence thread.

    Returns summary, action_items, approval_required, participants, citations.
    """
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
    from backend.retrieval.vector_store import get_vector_store

    store = get_vector_store()
    if store is None or not store.chunks:
        return {
            "found": False,
            "document": document_or_query,
            "summary": "No corpus loaded.",
            "action_items": [],
            "approval_required": [],
            "participants": [],
            "citations": [],
            "note": "Run ingestion first.",
        }

    query = f"{document_or_query} {focus}" if focus else document_or_query
    result = retrieve_with_grounding_check(store, query)

    if not result.found or not result.chunks:
        return {
            "found": False,
            "document": document_or_query,
            "summary": "No correspondence matching that query found in the corpus.",
            "action_items": [],
            "approval_required": [],
            "participants": [],
            "citations": [],
            "note": result.reason or "Not found.",
        }

    # Concatenate retrieved chunk texts as the grounded summary
    answer_text = "\n\n".join(
        c.text for c in result.chunks if c.text
    )
    citations = result.chunks

    action_items = [
        line.lstrip("-*0123456789. ").strip()
        for line in answer_text.splitlines()
        if re.match(r"^\s*[-*\d]+[\.\)]\s+", line)
        and any(kw in line.lower() for kw in ["action", "require", "submit", "must", "need"])
    ]

    approval_required = [
        line.strip()
        for line in answer_text.splitlines()
        if any(kw in line.lower() for kw in ["hq approval", "formal response", "authoris", "authoriz", "approve"])
    ]

    participant_pattern = re.compile(r"(?:From|To|CC)[:\s]+([A-Z][a-zA-Z\s,]+?)(?:\n|$)")
    participants = list({m.group(1).strip() for m in participant_pattern.finditer(answer_text)})

    return {
        "found": True,
        "document": document_or_query,
        "summary": answer_text[:2000],  # cap for agent context
        "action_items": action_items,
        "approval_required": approval_required,
        "participants": participants,
        "citations": [
            {"source_document": c.source_document, "page": c.page_number}
            for c in citations
        ],
        "note": f"Grounded in {len(citations)} chunk(s). Admitted by: {result.admitted_by}.",
    }



# ---------------------------------------------------------------------------
# Row 32 — NetworkX graph analytics
# ---------------------------------------------------------------------------

@tool(
    name="graph_analytics",
    category="computation",
    tools_md_row=32,
    description=(
        "Run graph-theoretic analysis: centrality measures (degree, "
        "betweenness, closeness), shortest path between two nodes, "
        "and the edge types along it. Returns the top-N most central nodes.\n"
        "Use when the question is about CONNECTIVITY — which document is "
        "most referenced, which segment is the hub of an incident cluster, "
        "or the shortest relationship chain between two entities. "
        "node_a and node_b are optional for path queries."
    ),
)
def graph_analytics(
    node_a: Optional[str] = None,
    node_b: Optional[str] = None,
    top_n: int = 10,
    metric: str = "betweenness",
) -> dict:
    """Compute graph centrality and optional shortest-path. Fully local NetworkX — no model calls."""
    try:
        import networkx as nx
    except ImportError:
        return {
            "source": "unavailable",
            "error": "networkx not installed. Run: pip install networkx",
            "top_nodes": [],
            "shortest_path": None,
            "note": "Install networkx to use this tool.",
        }

    # Load graph — try live backend, fall back to snapshot
    graph_data = None
    source_label = "snapshot"
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/graph",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = json.loads(resp.read())
            if raw.get("nodes"):
                graph_data = raw
                source_label = "live"
    except Exception:
        pass

    if graph_data is None:
        snapshot = pathlib.Path(__file__).resolve().parents[2] / "pipeline" / "graph.json"
        if snapshot.exists():
            graph_data = json.loads(snapshot.read_text())

    if graph_data is None or not graph_data.get("nodes"):
        return {
            "source": "unavailable",
            "node_count": 0,
            "edge_count": 0,
            "metric": metric,
            "top_nodes": [],
            "shortest_path": None,
            "note": "Graph data unavailable. Start Neo4j and run build_graph.",
        }

    G = nx.DiGraph()
    node_name_map: dict[str, str] = {}
    node_label_map: dict[str, str] = {}

    for node in graph_data.get("nodes", []):
        nid = str(node.get("id", ""))
        props = node.get("properties", {})
        label = (node.get("labels") or ["Unknown"])[0]
        display = (
            props.get("segment_name") or props.get("tag") or props.get("name")
            or props.get("summary") or props.get("title") or props.get("filename") or nid
        )
        G.add_node(nid, label=label, name=display)
        node_name_map[nid] = display
        node_label_map[nid] = label

    for rel in graph_data.get("relationships", []):
        src = str(rel.get("source") or rel.get("startNode", ""))
        tgt = str(rel.get("target") or rel.get("endNode", ""))
        rtype = rel.get("type", "RELATED")
        if src and tgt:
            G.add_edge(src, tgt, type=rtype)

    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()

    try:
        m = metric.lower()
        if m == "degree":
            scores = dict(nx.degree_centrality(G))
        elif m == "closeness":
            scores = dict(nx.closeness_centrality(G))
        else:
            m = "betweenness"
            scores = dict(nx.betweenness_centrality(G))
    except Exception as e:
        scores = {n: float(G.degree(n)) / max(node_count - 1, 1) for n in G.nodes()}
        m = f"degree (fallback: {e})"

    top_nodes = sorted(
        [{"name": node_name_map.get(nid, nid), "label": node_label_map.get(nid, "Unknown"),
          "score": round(s, 4)} for nid, s in scores.items()],
        key=lambda x: x["score"], reverse=True,
    )[:top_n]

    shortest_path_result = None
    if node_a and node_b:
        def find_id(name_query: str) -> Optional[str]:
            q = name_query.lower()
            for nid, nm in node_name_map.items():
                if q in nm.lower() or nm.lower() in q:
                    return nid
            return None

        id_a, id_b = find_id(node_a), find_id(node_b)
        if id_a and id_b:
            try:
                path_ids = nx.shortest_path(G.to_undirected(), id_a, id_b)
                path_names = [node_name_map.get(n, n) for n in path_ids]
                edge_types = [
                    G.edges.get((path_ids[i], path_ids[i+1]), {}).get("type")
                    or G.edges.get((path_ids[i+1], path_ids[i]), {}).get("type")
                    or "—"
                    for i in range(len(path_ids) - 1)
                ]
                shortest_path_result = {"found": True, "path": path_names,
                                        "edge_types": edge_types, "length": len(path_ids) - 1}
            except nx.NetworkXNoPath:
                shortest_path_result = {"found": False, "path": [], "edge_types": [], "length": -1}
        else:
            missing = [x for x, i in [(node_a, id_a), (node_b, id_b)] if not i]
            shortest_path_result = {"found": False, "path": [], "edge_types": [], "length": -1,
                                    "note": f"Nodes not found: {', '.join(missing)}"}

    return {
        "source": source_label,
        "node_count": node_count,
        "edge_count": edge_count,
        "metric": m,
        "top_nodes": top_nodes,
        "shortest_path": shortest_path_result,
        "note": f"Analytics on {node_count} nodes, {edge_count} edges ({source_label}).",
    }


# ---------------------------------------------------------------------------
# Row 60 — Multi-location depot correspondence summariser
# ---------------------------------------------------------------------------

MRPL_DEPOTS = {
    "kasargod": "Kasargod depot (KTK pipeline terminal)",
    "hindupur": "Hindupur depot",
    "hosur": "Hosur depot",
    "mangalore": "Mangalore refinery / MRPL HQ",
    "hassan": "Hassan pumping station",
    "neriya": "Neriya booster station",
    "devangonthi": "Devangonthi terminal",
}


@tool(
    name="summarise_depot_correspondence",
    category="retrieval",
    tools_md_row=60,
    description=(
        "Summarise correspondence threads between MRPL named depots and HQ "
        "— Kasargod, Hindupur, Hosur, Hassan, Mangalore, Neriya, Devangonthi. "
        "Groups by location, flags items needing HQ approval, and surfaces "
        "outstanding action items per depot.\n"
        "Pass a location name to focus on one depot, or omit for a "
        "cross-depot summary. All content is grounded in retrieved text."
    ),
)
def summarise_depot_correspondence(
    location: Optional[str] = None,
    focus: Optional[str] = None,
) -> dict:
    """Retrieve and summarise multi-depot correspondence. Specialises tool 18 for MRPL depots."""
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check
    from backend.retrieval.vector_store import get_vector_store

    store = get_vector_store()
    if store is None or not store.chunks:
        return {
            "found": False,
            "locations_covered": [],
            "by_location": {},
            "cross_location_summary": "No corpus loaded.",
            "escalations": [],
            "note": "Run ingestion first.",
        }

    targets = (
        {location.lower(): MRPL_DEPOTS.get(location.lower(), location)}
        if location
        else MRPL_DEPOTS
    )

    by_location: dict = {}
    all_escalations: list[str] = []
    found_locs: list[str] = []

    for loc_key, loc_desc in targets.items():
        query = f"{loc_desc} correspondence {focus or ''}".strip()
        result = retrieve_with_grounding_check(store, query)
        if not result.found or not result.chunks:
            continue
        found_locs.append(loc_key)
        answer = "\n\n".join(c.text for c in result.chunks if c.text)
        citations = result.chunks
        action_items = [
            line.lstrip("-*0123456789. ").strip()
            for line in answer.splitlines()
            if re.match(r"^\s*[-*\d]+[\.\)]\s+", line)
        ]
        approval_items = [
            line.strip()
            for line in answer.splitlines()
            if any(kw in line.lower() for kw in ["hq approval", "approve", "authoris", "escalat"])
        ]
        all_escalations.extend(f"[{loc_key.title()}] {item}" for item in approval_items)
        by_location[loc_key] = {
            "description": loc_desc,
            "summary": answer[:1500],
            "action_items": action_items,
            "approval_required": approval_items,
            "citations": [
                {"source_document": c.source_document, "page": c.page_number}
                for c in citations
            ],
        }

    if not by_location:
        return {
            "found": False,
            "locations_covered": [],
            "by_location": {},
            "cross_location_summary": "No depot correspondence found in the corpus.",
            "escalations": [],
            "note": "Ingest depot correspondence files first.",
        }

    cross = (
        f"Correspondence found for {len(found_locs)} location(s): "
        f"{', '.join(l.title() for l in found_locs)}. "
        f"{len(all_escalations)} item(s) require HQ attention."
    )

    return {
        "found": True,
        "locations_covered": found_locs,
        "by_location": by_location,
        "cross_location_summary": cross,
        "escalations": all_escalations,
        "note": f"Grounded in corpus for: {', '.join(l.title() for l in found_locs)}.",
    }

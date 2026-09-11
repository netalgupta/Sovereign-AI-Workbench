"""HTTP surface for the workbench.

Everything the Instrumentation view needs, plus the retrieval and
preview endpoints the chat surface needs.

TWO RULES THIS MODULE FOLLOWS THROUGHOUT, both from CLAUDE.md:

  * Hard constraint #1 — nothing here reaches the network. Every route
    reads local state: the corpus on disk, Neo4j on localhost, Ollama on
    localhost. There are no upstream calls, no CDN, no telemetry.
  * Hard constraint #4 — no route writes, sends, or modifies a user's
    document. The only mutating endpoints manage OUR OWN config (which
    folders to watch) and OUR OWN queue. Adding a document-writing route
    here later would need the human-approval gate wrapped around it
    first; there is deliberately nowhere for one to hide.

Responses carry provenance (`source: live | snapshot`) wherever the data
can come from either, so a dashboard can say which it is showing rather
than presenting a stale export as the current corpus.
"""

import base64
import io
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from backend.api.state import get_state

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- health

@router.get("/health")
def health() -> dict:
    """Liveness plus what is actually available right now.

    Deliberately reports the state of every dependency rather than a
    bare "ok": on an air-gapped box the interesting failure is not "is
    the API up" but "is Neo4j up, is Ollama up, has anything been
    ingested" — and a UI that knows can explain an empty screen instead
    of just showing one.
    """
    state = get_state()
    graph = state.graph()
    return {
        "status": "ok",
        "corpus_loaded": state.corpus_is_loaded,
        "snapshot_available": state.snapshot() is not None,
        "snapshot_written_at": state.snapshot_age(),
        "graph_available": graph.get("available", False),
        "graph_error": graph.get("error"),
        "images_stored": len(state.image_store.all_records()),
        "documents_registered": len(state.registry.all_refs()),
        "watched_sources": len(state.watcher.sources()),
    }


# ----------------------------------------------------------------- graph

@router.get("/graph")
def get_graph() -> dict:
    """The whole knowledge graph: nodes with all properties, and edges.

    Every property is returned, not a curated subset: the point of an
    inspection view is seeing what is actually stored, including fields
    you did not expect to be there or expected and find missing.
    """
    state = get_state()
    graph = state.graph()

    # "Reachable" and "populated" are different things, and conflating
    # them showed up immediately in practice: Neo4j came back up after a
    # restart with an empty database, so available=True with 0 nodes, and
    # the API cheerfully served an empty graph as live truth. An empty
    # live graph is a symptom (the container was recreated, the volume
    # was lost, the build never ran) and should fall back to the snapshot
    # while SAYING it did, not silently render nothing.
    live_is_populated = graph.get("available") and graph.get("nodes")
    if live_is_populated:
        return {**graph, "source": "live"}

    snapshot = state.snapshot()
    if snapshot and snapshot.get("graph", {}).get("nodes"):
        return {
            **snapshot["graph"],
            "source": "snapshot",
            "written_at": state.snapshot_age(),
            "warning": (
                "Neo4j is empty; showing the last exported snapshot. Rebuild with: "
                "python -m backend.evaluation.build_graph"
                if graph.get("available")
                else f"Neo4j unavailable ({graph.get('error')}); showing the last snapshot."
            ),
        }
    raise HTTPException(503, detail=graph.get("error") or "graph unavailable and no snapshot")


# ---------------------------------------------------------------- chunks

@router.get("/chunks")
def get_chunks(live: bool = Query(False, description="Force a live ingestion (slow)")) -> dict:
    """Every chunk with metadata, plus the chunk-to-chunk similarity matrix.

    Defaults to the snapshot because a live ingestion is minutes; pass
    live=true to pay for the current truth.
    """
    state = get_state()
    if not live:
        snapshot = state.snapshot()
        if snapshot:
            return {
                "source": "snapshot",
                "written_at": state.snapshot_age(),
                "chunking": snapshot["chunking"],
                "embedding_dim": snapshot["embedding_dim"],
                "pca_explained_variance": snapshot["pca_explained_variance"],
                "chunks": snapshot["chunks"],
                "similarity": snapshot["similarity"],
            }

    from backend.ingestion.chunking import (
        CHUNK_OVERLAP_TOKENS,
        CHUNK_SIZE_TOKENS,
        TIKTOKEN_ENCODING,
    )
    from backend.evaluation.export_inspection_data import _pca_2d
    from backend.ingestion.embeddings import embed_texts

    _store, chunks = state.ensure_corpus()
    vectors = np.asarray(embed_texts([c.text for c in chunks]), dtype=np.float32)
    coords, explained = _pca_2d(vectors)
    similarity = (vectors @ vectors.T).tolist()

    return {
        "source": "live",
        "written_at": None,
        "chunking": {
            "chunk_size_tokens": CHUNK_SIZE_TOKENS,
            "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS,
            "encoding": TIKTOKEN_ENCODING,
        },
        "embedding_dim": int(vectors.shape[1]),
        "pca_explained_variance": explained,
        "chunks": [
            {
                "index": i,
                "text": c.text,
                "chars": len(c.text),
                "source_document": c.metadata.source_document,
                "document_type": c.metadata.document_type,
                "page_number": c.metadata.page_number,
                "chunk_index": c.metadata.chunk_index,
                "image_ids": c.metadata.image_ids,
                "x": float(coords[i][0]),
                "y": float(coords[i][1]),
            }
            for i, c in enumerate(chunks)
        ],
        "similarity": [[round(v, 4) for v in row] for row in similarity],
    }


# ---------------------------------------------------------------- images

@router.get("/images")
def list_images() -> dict:
    """Every stored image with its provenance and both understandings.

    Pixels are NOT inlined here — see /api/images/{id}/raw. A list of
    fifteen charts is ~3MB of base64 if inlined, which makes the list
    endpoint slow for a grid that only needs thumbnails on demand.
    """
    state = get_state()
    records = state.image_store.all_records()
    if records:
        return {
            "source": "live",
            "images": [
                {
                    "image_id": r.image_id,
                    "byte_size": r.byte_size,
                    "content_type": r.content_type,
                    "ocr_text": r.ocr_text,
                    "description": r.description,
                    "description_is_estimate": r.description_is_estimate,
                    "occurrences": [o.model_dump() for o in r.occurrences],
                    "url": f"/api/images/{r.image_id}/raw",
                }
                for r in records
            ],
        }

    # Nothing in the store yet: fall back to the evaluation export, which
    # carries the chart-stress images and their scored readings.
    from backend.api.state import IMAGE_SNAPSHOT_PATH
    import json

    if IMAGE_SNAPSHOT_PATH.exists():
        images = json.loads(IMAGE_SNAPSHOT_PATH.read_text(encoding="utf-8"))["images"]
        return {"source": "snapshot", "images": images}
    return {"source": "empty", "images": []}


@router.get("/images/{image_id}/raw")
def get_image_bytes(image_id: str) -> Response:
    """The actual pixels. This is what "show me that image" resolves to."""
    state = get_state()
    record = state.image_store.get(image_id)
    data = state.image_store.read_bytes(image_id) if record else None
    if data is None:
        raise HTTPException(404, detail=f"no stored image {image_id}")
    return Response(content=data, media_type=record.content_type)


class ImageRequest(BaseModel):
    request: str
    image_ids: list[str] = []
    top_k: int = 1


@router.post("/images/select")
def select_image(body: ImageRequest) -> dict:
    """Pick the image a request is asking for, among several candidates.

    A page holds several images, so a chunk references several. Returning
    all of them is not an answer; the request is what disambiguates. May
    return an EMPTY list — putting the wrong diagram in front of an
    engineer is worse than attaching none.
    """
    from backend.retrieval.image_retrieval import select_images_for_request

    state = get_state()
    candidates = body.image_ids or [r.image_id for r in state.image_store.all_records()]
    matches = select_images_for_request(
        body.request, candidates, state.image_store, top_k=body.top_k
    )
    return {
        "matches": [
            {**m.model_dump(), "url": f"/api/images/{m.image_id}/raw"} for m in matches
        ]
    }


# --------------------------------------------------------------- metrics

@router.get("/metrics")
def get_metrics() -> dict:
    """Every measured evaluation result, each with when it was measured.

    The timestamp is not decoration. This project has three times been
    misled by an artifact that outlived the code that produced it, so a
    dashboard must be able to show that a number is older than the change
    it is being used to judge.
    """
    return get_state().metrics()


# --------------------------------------------------------------- sources

@router.get("/sources")
def list_sources() -> dict:
    """Watched folders, registered documents, and the ingestion queue."""
    state = get_state()
    watcher = state.watcher
    return {
        "watched": [s.model_dump() for s in watcher.sources()],
        "documents": [r.model_dump() for r in state.registry.all_refs()],
        "queue": state.queue.stats(),
    }


class AddSourceRequest(BaseModel):
    path: str
    recursive: bool = True
    include_globs: list[str] = []


@router.post("/sources")
def add_source(body: AddSourceRequest) -> dict:
    """Watch a folder from now on.

    Writes only OUR config — it records a path to READ from. It does not
    copy, move or modify anything the user owns, which is why it needs no
    approval gate: there is no user-visible side effect to approve.
    """
    state = get_state()
    try:
        source = state.watcher.add_source(
            body.path, recursive=body.recursive, include_globs=body.include_globs
        )
    except FileNotFoundError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return source.model_dump()


@router.delete("/sources")
def remove_source(path: str = Query(...)) -> dict:
    """Stop watching a folder. Removes nothing from disk."""
    return {"removed": get_state().watcher.remove_source(path)}


@router.post("/sources/scan")
def scan_sources() -> dict:
    """Find what needs ingesting and queue it, newest first."""
    state = get_state()
    pending = state.watcher.scan()
    added = state.queue.enqueue_all(pending)
    return {
        "found": len(pending),
        "queued": added,
        "pending": [p.model_dump() for p in pending[:50]],
        "queue": state.queue.stats(),
    }


# ------------------------------------------------------------------ tools

@router.get("/tools")
def list_tools(category: str | None = Query(None)) -> dict:
    """Every tool the agent can call, with the exact schema it receives.

    Exposed so the UI can show what the system can actually do, and so a
    developer can see the schema a model is being handed rather than
    inferring it from the function. TOOLS.md answers this for humans;
    this answers it for the orchestrator, and the row numbers link them.
    """
    from backend.tools import catalog  # noqa: F401 — import registers everything
    from backend.tools.registry import all_tools

    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "priority": t.priority,
                "requires_approval": t.requires_approval,
                "is_estimate": t.is_estimate,
                "computes_numbers": t.computes_numbers,
                "tools_md_row": t.tools_md_row,
                "schema": t.to_schema(),
            }
            for t in all_tools()
            if category is None or t.category == category
        ]
    }


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}
    approved: bool = False


@router.post("/tools/call")
def call_tool_endpoint(body: ToolCallRequest) -> dict:
    """Dispatch a tool by name.

    `approved` must come from a genuine human approval in the UI, never
    from a model's own output — a model asserting that a human approved
    something is exactly the failure hard constraint #4 prevents. A gated
    tool called without it returns 403, not a silent no-op.
    """
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import ApprovalRequired, call_tool

    try:
        result = call_tool(body.name, body.arguments, approved=body.approved)
    except ApprovalRequired as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    # Pydantic results serialize; bytes (a rendered chart) do not, so they
    # are base64-encoded rather than silently dropped or crashing the
    # response.
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
        for key, value in list(payload.items()):
            if isinstance(value, bytes):
                payload[key] = base64.b64encode(value).decode("ascii")
                payload[f"{key}_encoding"] = "base64"
        return {"result": payload}
    if isinstance(result, bytes):
        return {"result": base64.b64encode(result).decode("ascii"), "encoding": "base64"}
    return {"result": result}


# -------------------------------------------------------------- approvals

def _gate():
    from backend.audit.approval_gate import ApprovalGate

    return ApprovalGate()


class ApprovalRequestBody(BaseModel):
    tool_name: str
    arguments: dict
    effect: str = ""


@router.post("/approvals/request")
def request_approval(body: ApprovalRequestBody) -> dict:
    """Ask a human to approve one specific gated call.

    The `effect` is what the person actually reads. When the tool can
    describe its own effect (draft_docx does), that description is used
    rather than the caller's — a tool knows things the caller does not,
    such as whether the target file already exists and will be
    overwritten, or which sections have no sources.
    """
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import get_tool

    spec = get_tool(body.tool_name)
    if spec is None:
        raise HTTPException(404, detail=f"No tool named {body.tool_name!r}")
    if not spec.requires_approval:
        raise HTTPException(
            400,
            detail=(
                f"{body.tool_name} is not gated — call it directly via /api/tools/call. "
                "Routing an ungated tool through the approval queue trains people to "
                "click yes on things that did not need it."
            ),
        )

    effect = body.effect
    if body.tool_name == "draft_docx":
        from backend.tools.documents.draft_docx import describe_effect

        try:
            effect = describe_effect(
                body.arguments.get("title", ""),
                body.arguments.get("sections", []),
                body.arguments.get("output_path", ""),
            )
        except Exception:  # noqa: BLE001 — a bad payload is the human's to judge
            pass

    request = _gate().request(body.tool_name, body.arguments, effect or "(no description given)")
    return request.model_dump(exclude={"token"})


@router.get("/approvals")
def list_approvals() -> dict:
    """Everything awaiting a human decision. Tokens are never included."""
    return {"pending": [r.model_dump(exclude={"token"}) for r in _gate().pending()]}


class DecisionBody(BaseModel):
    request_id: str
    decided_by: str
    reason: str = ""


@router.post("/approvals/approve")
def approve(body: DecisionBody) -> dict:
    """Grant approval and return the single-use token.

    `decided_by` is recorded in the audit log and must identify a PERSON.
    It is the answer to "who approved this", which is the question the
    whole gate exists to be able to answer months later.
    """
    from backend.audit.approval_gate import ApprovalDenied

    try:
        request = _gate().approve(body.request_id, approved_by=body.decided_by)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ApprovalDenied as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return request.model_dump()


@router.post("/approvals/refuse")
def refuse(body: DecisionBody) -> dict:
    from backend.audit.approval_gate import ApprovalDenied

    try:
        request = _gate().refuse(body.request_id, refused_by=body.decided_by, reason=body.reason)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ApprovalDenied as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return request.model_dump(exclude={"token"})


class ExecuteBody(BaseModel):
    request_id: str
    token: str


@router.post("/approvals/execute")
def execute_approved(body: ExecuteBody) -> dict:
    """Consume an approval and run the tool it authorised.

    The only path from an approval to an effect. Execution and its audit
    entry are bound together in the gate, so there is no way to run a
    gated tool and forget to record it.
    """
    from backend.audit.approval_gate import ApprovalDenied

    try:
        result = _gate().execute_approved(body.request_id, body.token)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ApprovalDenied as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    return {"result": result.model_dump() if hasattr(result, "model_dump") else result}


@router.get("/audit")
def audit_trail(limit: int = Query(100, ge=1, le=1000), request_id: str | None = None) -> dict:
    """The audit log. Read-only by construction — there is no write route,
    and the log itself has no update path."""
    from backend.audit.audit_log import AuditLog

    log = AuditLog()
    entries = log.for_request(request_id) if request_id else log.entries(limit=limit)
    return {"entries": [e.model_dump() for e in entries]}


# ---------------------------------------------------------------- search

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/search")
def search(body: SearchRequest) -> dict:
    """Grounded retrieval: chunks, or an explicit refusal.

    Returns `found: false` when nothing clears the confidence gate, which
    is a real answer (NFR-4) and not an empty-result edge case. Measured:
    before that gate was fixed it refused 0 of 16 questions including
    ones about Pride and Prejudice.
    """
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    state = get_state()
    store, _chunks = state.ensure_corpus()
    result = retrieve_with_grounding_check(store, body.query, top_k=body.top_k)
    return {
        "found": result.found,
        "reason": result.reason,
        "chunks": [
            {
                "text": c.text,
                "source_document": c.source_document,
                "page_number": c.page_number,
                "score": c.score,
            }
            for c in result.chunks
        ],
    }


# --------------------------------------------------------------- preview

@router.get("/preview")
def preview_page(
    document: str = Query(..., description="Source document file name"),
    page: int = Query(..., ge=1),
    highlight: str | None = Query(None, description="Text to highlight on the page"),
    dpi: int = Query(150, ge=72, le=300),
) -> dict:
    """Render one page of the user's own file, with a passage highlighted.

    Reads the live file through the registry — nothing was copied — so
    what is shown is the current document. Returns the PNG base64-inlined
    alongside the highlight rectangles, because the two are useless apart
    and a UI drawing boxes on an image it fetched separately can drift
    out of sync with it.
    """
    from backend.retrieval.document_preview import render_page_preview

    state = get_state()
    preview = render_page_preview(
        document_name=document,
        page_number=page,
        registry=state.registry,
        highlight_text=highlight,
        dpi=dpi,
    )
    if preview is None:
        raise HTTPException(
            404,
            detail=(
                f"No preview for {document} page {page}. The document may not be "
                "registered, may have moved, or may have no such page."
            ),
        )
    return {
        "document_name": preview.document_name,
        "page_number": preview.page_number,
        "page_count": preview.page_count,
        "width_px": preview.width_px,
        "height_px": preview.height_px,
        "highlights": [h.model_dump() for h in preview.highlights],
        "status": preview.status,
        "warning": preview.warning,
        "image_png_base64": base64.b64encode(preview.image_png).decode("ascii"),
    }

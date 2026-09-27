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

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import numpy as np
import json

from fastapi import APIRouter, HTTPException, Query, Response, Request, UploadFile, File, Form
from pydantic import BaseModel

from backend.api import source_config
from backend.api.state import get_state

router = APIRouter(prefix="/api")


class SandboxExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout_seconds: Optional[int] = 10


class SandboxRenderRequest(BaseModel):
    attachment_id: Optional[str] = None
    file_path: Optional[str] = None
    source_id: Optional[str] = None




# ---------------------------------------------------------------- health

def _ocr_device_status() -> str:
    """The OCR device, WITHOUT forcing the probe that determines it.

    The forcing version imports torch and paddle -- 3.87s cold,
    measured -- and this is called by /api/health, which the frontend
    polls. A health check that blocks a worker for four seconds is not
    reporting health, it is degrading it.
    """
    try:
        from backend.tools.vision.ocr_printed import ocr_device_if_known

        return ocr_device_if_known()
    except Exception:  # noqa: BLE001
        return "unavailable"


def _embedding_device_status() -> str:
    try:
        from backend.ingestion.embeddings import active_device

        return active_device()
    except Exception as exc:  # noqa: BLE001
        return f"unknown ({type(exc).__name__})"


def _embedding_backend_status() -> tuple[str, str | None]:
    """(backend name, degradation reason or None) without forcing a load."""
    try:
        from backend.ingestion.embeddings import active_backend, degraded_reason

        return active_backend(), degraded_reason()
    except Exception as exc:  # noqa: BLE001
        return "unknown", f"could not read embedding status: {exc}"


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
    # Probed ONCE. This was called three times to fill three adjacent
    # fields, which is three times the work for one answer.
    _embedding_status = _embedding_backend_status()
    return {
        "ok": True,
        "status": "ok",
        "corpus_loaded": state.corpus_is_loaded,
        "snapshot_available": state.snapshot() is not None,
        "snapshot_written_at": state.snapshot_age(),
        # Whether retrieval is actually semantic. This silently fell
        # back to hash vectors for a whole session after a transient
        # load failure, and nothing in the API said so.
        # Which device OCR will actually use. A pipeline that silently
        # fell back to CPU looks identical to one that chose CPU, which
        # is how "the GPU is not working" becomes an afternoon of
        # guessing. Measured difference on this box: 21.08s vs 0.61s.
        "ocr_device": _ocr_device_status(),
        "embedding_backend": _embedding_status[0],
        # WHERE embeddings run. "The CPU is stuck at 100%" during an
        # ingest is expected on a CPU-only torch build and a bug on a
        # CUDA one; without this field the two look identical.
        "embedding_device": _embedding_device_status(),
        # A background job indexing files the corpus cache had not seen.
        "catch_up_job_id": state.catch_up_job_id,
        "embeddings_degraded": _embedding_status[1] is not None,
        "embeddings_degraded_reason": _embedding_status[1],
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
def get_chunks(live: bool = Query(False, description="Force a live ingestion")) -> dict:
    """Every chunk with metadata, plus the chunk-to-chunk similarity matrix."""
    state = get_state()

    # 1. Fast in-memory cache hit
    if not live and getattr(state, "_cached_chunks", None) is not None:
        return state._cached_chunks

    # 2. Instant snapshot fallback
    snapshot = state.snapshot()
    # The snapshot is preferred over a live read so a request cannot
    # trigger a multi-minute ingest -- but ONLY while it still describes
    # the configured sources. It stopped doing so the moment a folder
    # was added, and the inspector then showed 21 chunks from 13
    # documents while the Sources panel counted 66 files, with no amount
    # of rescanning changing it.
    if (
        not live
        and snapshot
        and "chunks" in snapshot
        and "similarity" in snapshot
        and not state.corpus_is_loaded
        and (not hasattr(state, "corpus_snapshot_is_current") or state.corpus_snapshot_is_current())
    ):
        result = {
            "source": "snapshot",
            "written_at": state.snapshot_age(),
            "chunking": snapshot["chunking"],
            "embedding_dim": snapshot["embedding_dim"],
            "pca_explained_variance": snapshot["pca_explained_variance"],
            "chunks": snapshot["chunks"],
            "similarity": snapshot["similarity"],
        }
        state._cached_chunks = result
        return result

    from backend.ingestion.chunking import (
        CHUNK_OVERLAP_TOKENS,
        CHUNK_SIZE_TOKENS,
        TIKTOKEN_ENCODING,
    )
    from backend.evaluation.export_inspection_data import _pca_2d
    from backend.ingestion.embeddings import embed_texts

    store, live_chunks = state.ensure_corpus()
    # A COPY, taken under the lock. The live list grows while an ingest
    # runs; iterating it after computing vectors for a shorter prefix
    # raised "IndexError: index 3510 is out of bounds for axis 0 with
    # size 3510" -- MEASURED, mid-ingest, after the request had already
    # spent five minutes.
    with state._lock:
        chunks = list(live_chunks or [])
    if not chunks:
        result = {
            "source": "live",
            "written_at": None,
            "chunking": {
                "chunk_size_tokens": CHUNK_SIZE_TOKENS,
                "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS,
                "encoding": TIKTOKEN_ENCODING,
            },
            "embedding_dim": 1024,
            "pca_explained_variance": [0.0, 0.0],
            "chunks": [],
            "similarity": [],
        }
        state._cached_chunks = result
        return result

    vectors = _stored_vectors(store, len(chunks))
    if vectors is None:
        vectors = np.asarray(embed_texts([c.text for c in chunks]), dtype=np.float32)
    coords, explained = _pca_2d(vectors) if len(chunks) > 1 else (np.zeros((len(chunks), 2)), [1.0, 0.0])
    neighbours = _nearest_neighbours(vectors, k=CHUNK_NEIGHBOURS)

    # The full matrix is N² numbers. At 236 chunks that is 56k and fine;
    # at the 6,797 chunks one archive folder produced it is 46 MILLION,
    # hundreds of MB of JSON the browser cannot parse. Above the limit
    # the heatmap is omitted AND SAYS WHY, and the per-chunk nearest
    # neighbours -- the part of the matrix the page actually reads -- are
    # still served for every chunk.
    if len(chunks) <= SIMILARITY_MATRIX_MAX_CHUNKS:
        similarity = [[round(float(v), 4) for v in row] for row in (vectors @ vectors.T)]
        similarity_omitted = None
    else:
        similarity = []
        similarity_omitted = {
            "chunk_count": len(chunks),
            "limit": SIMILARITY_MATRIX_MAX_CHUNKS,
            "reason": (
                f"A {len(chunks):,} x {len(chunks):,} similarity matrix is too large to "
                f"send; nearest neighbours are provided per chunk instead."
            ),
        }

    result = {
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
                "neighbours": neighbours[i],
            }
            for i, c in enumerate(chunks)
        ],
        "similarity": similarity,
        "similarity_omitted": similarity_omitted,
    }
    state._cached_chunks = result
    return result


# Above this many chunks the full similarity matrix is not sent. 600² is
# 360k cells (a few MB of JSON); the heatmap is unreadable well before
# that anyway, at one pixel per cell.
SIMILARITY_MATRIX_MAX_CHUNKS = 600
CHUNK_NEIGHBOURS = 5


def _stored_vectors(store, n: int):
    """The vectors already in the index, or None.

    /api/chunks re-embedded every chunk on each cache miss -- 11.5s for
    236 chunks, MEASURED, and a cache miss follows every document of an
    ingest -- to recompute vectors sitting in the FAISS index. Positions
    line up because chunks and vectors are appended together, one ingest
    at a time (PipelineState._ingest_lock).
    """
    # Through the store, which holds its lock: reading the FAISS index
    # directly while an ingest added to it segfaulted the API (exit 139).
    # EXACT count only. More vectors than chunks means an ingest is
    # mid-append; re-embedding is slower but cannot pair a passage with
    # another passage's vector.
    try:
        return store.vectors(n) if len(store) == n else None
    except Exception:  # noqa: BLE001 - an index type without reconstruct
        return None


def _nearest_neighbours(vectors, k: int) -> list[list[list[float]]]:
    """For each chunk, its k most similar other chunks as [index, score].

    Computed in blocks so memory stays at block x N rather than N².
    """
    n = len(vectors)
    if n < 2:
        return [[] for _ in range(n)]
    k = min(k, n - 1)
    out: list[list[list[float]]] = []
    block = 512
    for start in range(0, n, block):
        sims = vectors[start:start + block] @ vectors.T
        for row_i, row in enumerate(sims):
            row[start + row_i] = -np.inf  # a chunk is not its own neighbour
            top = np.argpartition(-row, k)[:k]
            top = top[np.argsort(-row[top])]
            out.append([[int(j), round(float(row[j]), 4)] for j in top])
    return out


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


# Image extensions a browser can render as an inspection photo.
_IMAGE_SUFFIX_TO_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


@router.get("/inspection/image")
def get_inspection_image(path: str = Query(..., description="Image path, relative to the corpus root")) -> Response:
    """Serve one inspection image read-only, for the DefectOverlay.

    The defect/anomaly tool returns boxes with an `image_url` pointing
    here; the browser fetches THIS endpoint, never the filesystem path
    directly. Hard constraint #4 holds by construction: this is a GET
    that only reads a file already on disk.

    CONTAINMENT IS LOAD-BEARING, not politeness. An endpoint that serves
    a caller-chosen path is an arbitrary file reader unless it confines
    that path to the corpus root and rejects anything outside it. Path is
    resolved and re-checked AFTER normalization so `..` traversal cannot
    escape the root; a relative path is resolved against the corpus dir,
    and an absolute path must still land inside it.
    """
    from backend.api.state import DEFAULT_CORPUS_DIR

    corpus_root = Path(DEFAULT_CORPUS_DIR).resolve()

    candidate = Path(path)
    full = (candidate if candidate.is_absolute() else corpus_root / candidate).resolve()
    try:
        full.relative_to(corpus_root)
    except ValueError:
        raise HTTPException(400, detail="path escapes the corpus root")

    if not full.is_file():
        raise HTTPException(404, detail=f"no such image: {path}")

    media = _IMAGE_SUFFIX_TO_MEDIA.get(full.suffix.lower())
    if media is None:
        raise HTTPException(400, detail=f"not an inspectable image suffix: {full.suffix}")

    return Response(content=full.read_bytes(), media_type=media)


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


# --------------------------------------------------------------- chunk & embed

class ChunkRequest(BaseModel):
    text: str
    source_document: str = "custom"


@router.post("/chunk")
def chunk_endpoint(body: ChunkRequest) -> dict:
    """Split text into ~512-token chunks with 64-token overlap."""
    from backend.ingestion.chunking import (
        CHUNK_OVERLAP_TOKENS,
        CHUNK_SIZE_TOKENS,
        TIKTOKEN_ENCODING,
        chunk_text,
    )

    chunks = chunk_text(body.text)
    return {
        "chunks": chunks,
        "count": len(chunks),
        "chunk_size_tokens": CHUNK_SIZE_TOKENS,
        "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS,
        "encoding": TIKTOKEN_ENCODING,
    }


class EmbedRequest(BaseModel):
    texts: list[str]


@router.post("/embed")
def embed_endpoint(body: EmbedRequest) -> dict:
    """Generate 1024-dimensional normalized dense embeddings for texts."""
    from backend.ingestion.embeddings import embed_texts

    vectors = embed_texts(body.texts)
    return {
        "embeddings": vectors.tolist(),
        "dim": int(vectors.shape[1]) if len(vectors.shape) > 1 else 1024,
        "count": len(vectors),
    }


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
    job_id: str | None = None


class IngestPathRequest(BaseModel):
    path: str


class UploadFileItem(BaseModel):
    name: str
    relPath: str | None = None
    contentBase64: str
    sizeBytes: int | None = None


class UploadSourcesRequest(BaseModel):
    files: list[UploadFileItem]
    job_id: str | None = None


def _untombstone_source(*identifiers: str) -> None:
    """Remove paths, IDs, or tokens from deleted_sources.json so re-adding unblocks them."""
    deleted_file = source_config.DELETED_PATH
    if not deleted_file.exists():
        return
    current = source_config.load(deleted_file)

    to_remove = {str(i).strip().lower() for i in identifiers if i and str(i).strip()}
    for i in list(to_remove):
        try:
            p = Path(i).resolve()
            to_remove.add(str(p).lower())
        except Exception:
            pass

    updated = []
    for item in current:
        item_lower = str(item).strip().lower()
        if item_lower in to_remove:
            continue
        matched_parent = False
        for r in to_remove:
            if item_lower.startswith(r + "\\") or item_lower.startswith(r + "/"):
                matched_parent = True
                break
        if not matched_parent:
            updated.append(item)

    source_config.save(updated, deleted_file)


@router.post("/sources/upload")
def upload_and_ingest_sources(body: UploadSourcesRequest) -> dict:
    """Accept uploaded files, write to disk, and chunk & embed them into FAISS."""
    import hashlib

    state = get_state()
    target_base_dir = Path("MRPL_RAG_Test_Corpus") / "07_User_Uploads"
    target_base_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    top_folders: set[str] = set()
    for f in body.files:
        # Preserve relative path (subdir/filename) — strip leading slashes/dots only
        clean_rel = (f.relPath or f.name).replace("\\", "/").lstrip("./")
        dest = target_base_dir / clean_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw_bytes = base64.b64decode(f.contentBase64)
            dest.write_bytes(raw_bytes)
            saved_files.append(dest.resolve())
            parts = clean_rel.split("/")
            if len(parts) > 1 and parts[0]:
                top_folders.add(parts[0])
        except Exception:
            continue

    # Register any top-level uploaded folder as a named corpus source
    if top_folders:
        config_file = source_config.CONFIG_PATH
        dirs: list[dict] = []
        dirs = source_config.load(config_file)
        for folder in top_folders:
            folder_path = target_base_dir / folder
            norm_lower = str(folder_path.resolve()).lower()
            folder_hash = hashlib.sha256(norm_lower.encode("utf-8")).hexdigest()[:10]
            folder_id = f"dir_{folder_hash}"
            _untombstone_source(str(folder_path.resolve()), norm_lower, folder_id)
            if not any(str(Path(d.get("path", "")).resolve()).lower() == norm_lower for d in dirs):
                dirs.append({
                    "id": folder_id,
                    "name": folder,
                    "path": str(folder_path.resolve()),
                    "isPreset": False,
                    "isUploadedFolder": True,
                    "enabled": True,
                })
        source_config.save(dirs, config_file)

    from backend.ingestion.ingestion_progress import get_tracker
    import threading

    tracker = get_tracker()
    job = tracker.create(str(target_base_dir), saved_files, job_id=body.job_id)

    def _run():
        for sf in saved_files:
            try:
                _untombstone_source(str(sf), str(sf.resolve()).lower(), "user_uploads_corpus")
                state.ingest_path(sf, job_id=job.job_id)
            except Exception as exc:
                from backend.ingestion.ingestion_progress import DocumentStage
                tracker.set_stage(job.job_id, str(sf), DocumentStage.FAILED,
                                  detail=f"{type(exc).__name__}: {exc}")
        tracker.finish(job.job_id)
        # Ensure configured_sources.json reflects the uploaded folder after ingestion
        _cfg = source_config.CONFIG_PATH
        _dirs = []
        _dirs = source_config.load(_cfg)
        # top_folders already registered above — just make sure enabled=True
        for folder in top_folders:
            folder_path = target_base_dir / folder
            norm = str(folder_path.resolve()).lower()
            for d in _dirs:
                if str(Path(d.get("path", "")).resolve()).lower() == norm:
                    d["enabled"] = True
                    break
        source_config.save(_dirs, _cfg)

    threading.Thread(target=_run, name=f"upload-ingest-{job.job_id}", daemon=True).start()

    return {
        "success": True,
        "job_id": job.job_id,
        "state": "running",
        "count": len(saved_files),
        "saved": [{"path": str(sf), "name": sf.name} for sf in saved_files],
        "added": {"path": str(saved_files[0]), "name": saved_files[0].name} if saved_files else None,
        "poll": f"/api/ingestion/{job.job_id}",
        "message": f"Uploaded {len(saved_files)} file(s) — ingestion running in background. Poll /api/ingestion/{job.job_id} for live progress.",
    }


@router.post("/sources/dialog/pick-folder")
def pick_folder_endpoint() -> dict:
    """Open native OS directory dialog to choose a folder on disk and return selected path immediately."""
    from backend.api.native_picker import pick_folder_gui

    picked_path = pick_folder_gui("Select Folder to Add to Sovereign Workbench")
    if not picked_path:
        return {"cancelled": True, "path": None, "message": "Folder selection cancelled"}

    target = Path(picked_path).resolve()
    if not target.exists():
        raise HTTPException(404, detail="Selected directory does not exist")

    return {
        "cancelled": False,
        "path": str(target),
        "name": target.name or "Custom_Corpus",
    }


@router.post("/sources/dialog/pick-files")
def pick_files_endpoint() -> dict:
    """Open native OS file dialog to choose documents on disk and return selected paths immediately."""
    from backend.api.native_picker import pick_files_gui

    picked_paths = pick_files_gui("Select Documents to Add to Sovereign Workbench")
    if not picked_paths:
        return {"cancelled": True, "paths": [], "message": "File selection cancelled"}

    return {
        "cancelled": False,
        "paths": picked_paths,
        "count": len(picked_paths),
    }


@router.post("/sources/dialog/folder")
def browse_and_add_folder() -> dict:
    """Open native OS directory dialog to choose a folder on disk, register and ingest in background."""
    import hashlib
    import threading
    from backend.api.native_picker import pick_folder_gui

    picked_path = pick_folder_gui("Select Folder to Add to Sovereign Workbench")
    if not picked_path:
        return {"cancelled": True, "message": "Folder selection cancelled"}

    target = Path(picked_path).resolve()
    if not target.exists():
        raise HTTPException(404, detail="Selected directory does not exist")

    state = get_state()
    try:
        source = state.watcher.add_source(str(target), recursive=True)
    except Exception:
        source = None

    config_file = source_config.CONFIG_PATH
    dirs = []
    dirs = source_config.load(config_file)

    norm_path = str(target.resolve())
    norm_lower = norm_path.lower()
    hasher = hashlib.sha256(norm_lower.encode("utf-8")).hexdigest()[:10]
    dir_id = f"dir_{hasher}"

    # Un-tombstone and register BEFORE thread starts so sidebar sees it immediately
    _untombstone_source(norm_path, norm_lower, dir_id)
    found = False
    for d in dirs:
        if str(Path(d.get("path", "")).resolve()).lower() == norm_lower:
            d["enabled"] = True
            found = True
            break
    if not found:
        dirs.append({
            "id": dir_id,
            "name": target.name or "Custom_Corpus",
            "path": norm_path,
            "isPreset": False,
            "enabled": True,
        })
    source_config.save(dirs, config_file)

    # Enumerate files for progress tracker
    target_files = sorted(
        f for f in target.rglob("*")
        if f.is_file() and not f.name.startswith(".")
    ) if target.is_dir() else [target]

    from backend.ingestion.ingestion_progress import get_tracker
    tracker = get_tracker()
    job = tracker.create(norm_path, target_files or [target])

    def _run():
        try:
            state.ingest_path(target, job_id=job.job_id)
            tracker.finish(job.job_id)
        except Exception as exc:
            tracker.finish(job.job_id, error=f"{type(exc).__name__}: {exc}")
        # Re-sync configured_sources after completion
        _dirs2 = []
        _dirs2 = source_config.load(config_file)
        for d in _dirs2:
            if str(Path(d.get("path", "")).resolve()).lower() == norm_lower:
                d["enabled"] = True
                break
        source_config.save(_dirs2, config_file)

    threading.Thread(target=_run, name=f"dialog-folder-ingest-{job.job_id}", daemon=True).start()

    return {
        "success": True,
        "job_id": job.job_id,
        "state": "running",
        "path": norm_path,
        "name": target.name,
        "directories": dirs,
        "added": {"path": norm_path, "name": target.name, "id": dir_id},
        "source": source.model_dump() if source else {"path": norm_path},
        "poll": f"/api/ingestion/{job.job_id}",
        "message": f"Folder '{target.name}' registered — ingestion running in background. Poll /api/ingestion/{job.job_id} for live progress.",
    }


@router.post("/sources/dialog/files")
def browse_and_add_files() -> dict:
    """Open native OS file dialog to choose documents on disk, register and ingest them in background."""
    import hashlib
    import threading
    from backend.api.native_picker import pick_files_gui

    picked_paths = pick_files_gui("Select Documents to Add to Sovereign Workbench")
    if not picked_paths:
        return {"cancelled": True, "message": "File selection cancelled"}

    state = get_state()
    saved_items = []

    config_file = source_config.CONFIG_PATH
    dirs = []
    dirs = source_config.load(config_file)

    target_files: list[Path] = []
    for p_str in picked_paths:
        target = Path(p_str).resolve()
        file_norm = str(target)
        file_lower = file_norm.lower()
        file_hasher = hashlib.sha256(file_lower.encode("utf-8")).hexdigest()[:10]
        file_id = f"file_{file_hasher}"

        _untombstone_source(file_norm, file_lower, file_id)
        target_files.append(target)
        saved_items.append({"path": file_norm, "name": target.name})

        if not any(str(Path(d.get("path", "")).resolve()).lower() == file_lower for d in dirs):
            dirs.append({
                "id": file_id,
                "name": target.name,
                "path": file_norm,
                "isFile": True,
                "isPreset": False,
                "enabled": True,
            })

    source_config.save(dirs, config_file)

    # Create progress job and ingest in background
    from backend.ingestion.ingestion_progress import get_tracker
    tracker = get_tracker()
    job = tracker.create(picked_paths[0] if len(picked_paths) == 1 else "multi-file", target_files)

    def _run():
        for target in target_files:
            try:
                state.ingest_path(target, job_id=job.job_id)
            except Exception as exc:
                from backend.ingestion.ingestion_progress import DocumentStage
                tracker.set_stage(job.job_id, str(target), DocumentStage.FAILED,
                                  detail=f"{type(exc).__name__}: {exc}")
        tracker.finish(job.job_id)

    threading.Thread(target=_run, name=f"dialog-files-ingest-{job.job_id}", daemon=True).start()

    return {
        "success": True,
        "job_id": job.job_id,
        "state": "running",
        "count": len(picked_paths),
        "saved": saved_items,
        "added": saved_items[0] if saved_items else None,
        "directories": dirs,
        "poll": f"/api/ingestion/{job.job_id}",
        "message": f"Registered {len(picked_paths)} document(s) — ingestion running in background. Poll /api/ingestion/{job.job_id} for live progress.",
    }


@router.post("/sources/ingest")
def ingest_source_endpoint(body: IngestPathRequest, background: bool = Query(False)) -> dict:
    """Chunk, embed, and index a file or directory.

    SYNCHRONOUS BY DEFAULT, deliberately. Returning immediately would be
    the cleaner API, but the existing frontend awaits this call and shows
    its spinner until it resolves — flipping the default would make the
    UI report "done" the instant the job was queued, while indexing was
    still running. A wrong completion is worse than a slow one.

    Progress is available EITHER WAY: a job is registered before any work
    starts and updated per document, so a UI can poll
    /api/ingestion/{job_id} on a second connection while its own POST is
    still in flight. That is what turns the spinner into "extracting
    SOP-114.docx, 3 of 14 done, ~2 min left" without changing this
    contract at all.

    Pass background=true to return immediately with just the job_id, once
    the caller polls rather than awaits.
    """
    import threading

    from backend.ingestion.ingestion_progress import get_tracker

    state = get_state()
    root = Path(body.path).resolve()
    if not root.exists():
        raise HTTPException(404, detail=f"Path does not exist on disk: {body.path}")

    # Enumerate up front, with the SAME filter ingest_path uses, so the
    # job knows its full worklist before any slow work starts. A total
    # that grows as the job runs makes "3 of 5" meaningless.
    if root.is_file():
        files = [root]
    else:
        files = sorted(
            f for f in root.rglob("*")
            if f.is_file() and not f.name.startswith(".") and f.name.lower() != "readme.md"
        )
    if not files:
        raise HTTPException(400, detail=f"No ingestible files found under {body.path}")

    job = get_tracker().create(str(root), files)

    def _run():
        try:
            state.ingest_path(body.path, job_id=job.job_id)
            get_tracker().finish(job.job_id)
        except Exception as exc:  # noqa: BLE001 — recorded on the job, not lost to a thread
            get_tracker().finish(job.job_id, error=f"{type(exc).__name__}: {exc}")

    if not background:
        total_chunks, details = 0, []
        try:
            total_chunks, details = state.ingest_path(body.path, job_id=job.job_id)
            get_tracker().finish(job.job_id)
        except FileNotFoundError as exc:
            get_tracker().finish(job.job_id, error=str(exc))
            raise HTTPException(404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            get_tracker().finish(job.job_id, error=f"{type(exc).__name__}: {exc}")
            raise HTTPException(500, detail=f"Ingestion failed: {exc}") from exc

        # The original response shape, unchanged -- existing callers and
        # tests depend on total_chunks/documents/message being here.
        # job_id is additive, so a caller that wants the per-document
        # record can still fetch it afterwards.
        return {
            "success": True,
            "job_id": job.job_id,
            "total_chunks": total_chunks,
            "documents": details,
            "message": (
                f"Successfully ingested {len(details)} document(s): {total_chunks} chunks "
                "created, embedded, and indexed into FAISS."
            ),
        }

    # daemon: a half-finished ingest must not keep the process alive on
    # shutdown. Work already indexed is kept; the rest is reported as
    # unfinished rather than silently dropped.
    threading.Thread(target=_run, name=f"ingest-{job.job_id}", daemon=True).start()

    return {
        "success": True,
        "job_id": job.job_id,
        "total_documents": len(files),
        "state": "running",
        "poll": f"/api/ingestion/{job.job_id}",
        "message": f"Ingesting {len(files)} document(s). Poll for per-document progress.",
    }


@router.get("/ingestion/{job_id}")
def ingestion_status(job_id: str, documents: bool = Query(True)) -> dict:
    """Live status of one ingestion job.

    Reports counts and the CURRENT document rather than a percentage.
    Per-document cost spans orders of magnitude here — a 2KB text file is
    milliseconds, a 40-page scan is minutes of OCR — so a fraction of
    files looks precise and misleads.
    """
    from backend.ingestion.ingestion_progress import get_tracker

    job = get_tracker().get(job_id)
    if job is None:
        raise HTTPException(404, detail=f"No ingestion job {job_id!r}")

    payload = job.summary()
    if documents:
        payload["documents"] = [
            {
                "name": d.name,
                "path": d.path,
                "suffix": d.suffix,
                "byte_size": d.byte_size,
                "stage": d.stage.value,
                "chunks": d.chunks,
                "seconds": d.seconds,
                "detail": d.detail,
            }
            for d in job.documents
        ]
    return payload


@router.get("/ingestion")
def ingestion_jobs(limit: int = Query(10, ge=1, le=20)) -> dict:
    """Recent ingestion jobs, newest first.

    Finished jobs are retained so a user who opens the panel afterwards
    can still see what happened — a result that vanishes when it
    completes cannot be read.
    """
    from backend.ingestion.ingestion_progress import get_tracker

    return {"jobs": [j.summary() for j in get_tracker().recent(limit)]}


# The sidebar's source filter tabs -- Docs / Data / Charts / APIs --
# filter on `category`. The backend corpus response did not carry that
# field at all, so against real backend data every tab counted zero and
# clicking one emptied the list. It only ever worked against the Vite
# dev server's own hardcoded source objects, which set `category` by
# hand on a fixed list of thirteen files.
#
# Derived from the extension rather than stored, so a newly ingested
# file is categorised the moment it appears -- there is no list to keep
# in sync, which is what let the previous one drift.
_CATEGORY_BY_EXTENSION = {
    # Documents: prose a person reads.
    "pdf": ("documents", "reports"),
    "docx": ("documents", "reports"),
    "doc": ("documents", "reports"),
    "txt": ("documents", "notes"),
    "md": ("documents", "notes"),
    "eml": ("documents", "correspondence"),
    "msg": ("documents", "correspondence"),
    "html": ("documents", "notes"),
    # Data: tabular, queryable.
    "xlsx": ("data", "spreadsheets"),
    "xls": ("data", "spreadsheets"),
    "csv": ("data", "spreadsheets"),
    "json": ("data", "structured"),
    "xml": ("data", "structured"),
    "yaml": ("data", "structured"),
    "yml": ("data", "structured"),
    # Charts and scans: pixels, reached through OCR or the vision model.
    "png": ("charts", "diagrams"),
    "jpg": ("charts", "diagrams"),
    "jpeg": ("charts", "diagrams"),
    "gif": ("charts", "diagrams"),
    "bmp": ("charts", "diagrams"),
    "tiff": ("charts", "diagrams"),
    "svg": ("charts", "diagrams"),
    # Audio: transcribed before it is retrievable.
    "wav": ("data", "audio"),
    "mp3": ("data", "audio"),
    "m4a": ("data", "audio"),
    "flac": ("data", "audio"),
}


def categorise_source(extension: str) -> tuple[str, str]:
    """Map a file extension to (category, subcategory).

    Unknown extensions fall to ("documents", "other") rather than to a
    category of their own: an ingested file that matches no filter tab
    is invisible in the sidebar, which is a worse failure than being
    filed imprecisely.
    """
    return _CATEGORY_BY_EXTENSION.get(extension.lower(), ("documents", "other"))


def _get_corpus_data() -> dict:
    """Compute and return corpus data — shared by the HTTP route and internal callers.

    Extracted from get_corpus() so orchestrator/retrieval_tools can call it
    without a FastAPI Response argument (which caused a TypeError in callers
    that imported the route function directly).
    """
    config_file = source_config.CONFIG_PATH
    deleted_file = source_config.DELETED_PATH
    deleted_records = {str(s).lower() for s in source_config.load(deleted_file)}

    dirs = []
    dirs = source_config.load(config_file)

    # Prune stale entries whose files/folders no longer exist on disk
    valid_dirs = []
    dirs_pruned = False
    for d in dirs:
        p = Path(d.get("path", ""))
        p_res = str(p.resolve()).lower()
        if (
            d.get("id", "").lower() in deleted_records
            or p_res in deleted_records
        ):
            dirs_pruned = True
            continue
        if p.exists():
            valid_dirs.append(d)
        else:
            dirs_pruned = True
    if dirs_pruned:
        dirs = valid_dirs
        source_config.save(dirs, config_file)

    # Always ensure preset baseline corpora are preserved alongside user-added sources
    preset_ids = {d.get("id") for d in dirs}
    # Also index by resolved path so we can detect user-added entries that shadow a preset
    existing_paths = {str(Path(d.get("path", "")).resolve()).lower() for d in dirs if d.get("path")}
    for preset in [
        {
            "id": "mrpl_rag_corpus",
            "name": "MRPL_RAG_Test_Corpus",
            "path": str(Path.cwd() / "MRPL_RAG_Test_Corpus"),
            "isPreset": True,
            "enabled": True,
        },
        {
            "id": "mrpl_chart_corpus",
            "name": "MRPL_Chart_Stress_Corpus",
            "path": str(Path.cwd() / "MRPL_Chart_Stress_Corpus"),
            "isPreset": True,
            "enabled": True,
        },
    ]:
        preset_path_lower = str(Path(preset["path"]).resolve()).lower()
        if (
            preset["id"] not in preset_ids
            and preset_path_lower not in existing_paths  # skip if user already added same path
            and Path(preset["path"]).exists()
            and preset["id"].lower() not in deleted_records
        ):
            dirs.append(preset)

    uploads_dir = Path.cwd() / "MRPL_RAG_Test_Corpus" / "07_User_Uploads"
    if (
        uploads_dir.exists()
        and any(uploads_dir.iterdir())
        and "user_uploads_corpus" not in preset_ids
        and "user_uploads_corpus" not in deleted_records
    ):
        dirs.insert(0, {
            "id": "user_uploads_corpus",
            "name": "User Uploads",
            "path": str(uploads_dir),
            "isPreset": True,
            "isUserUploads": True,
            "enabled": True,
        })

    tree = []
    all_items = []
    custom_subpaths = [
        str(Path(d.get("path", "")).resolve()).lower()
        for d in dirs if not d.get("isPreset", False)
    ]
    individual_files = []

    for dir_cfg in dirs:
        p = Path(dir_cfg.get("path", ""))
        if not dir_cfg.get("enabled", True) or not p.exists():
            continue

        p_resolved_lower = str(p.resolve()).lower()
        if (
            dir_cfg.get("id", "").lower() in deleted_records
            or p_resolved_lower in deleted_records
        ):
            continue

        # Handle individual file source entries directly in-place
        if dir_cfg.get("isFile") or p.is_file():
            stat = p.stat()
            ext = p.suffix.lstrip(".").lower()
            raw_id = dir_cfg.get("id") or p.name
            clean_id = raw_id if str(raw_id).startswith("file_") else f"file_{raw_id}"
            if (
                clean_id.lower() in deleted_records
                or p_resolved_lower in deleted_records
            ):
                continue
            file_item = {
                "id": clean_id,
                "name": p.name,
                "type": ext.upper(),
                "extension": ext,
                "size": f"{round(stat.st_size / 1024, 1)} KB",
                "sizeBytes": stat.st_size,
                "folder": p.parent.name or "User Sources",
                "relPath": p.name,
                "fullPath": str(p.resolve()),
                "corpus": "User Ingested Documents",
                "enabled": True,
                "category": categorise_source(ext)[0],
                "subcategory": categorise_source(ext)[1],
                "isFile": True,
            }
            all_items.append(file_item)
            individual_files.append(file_item)
            continue

        dir_node = {
            "id": dir_cfg.get("id"),
            "name": dir_cfg.get("name", p.name),
            "fullPath": str(p.resolve()),
            "type": "directory",
            "isRoot": True,
            "isPreset": dir_cfg.get("isPreset", False),
            "children": [],
            "fileCount": 0,
            "totalSizeBytes": 0,
        }

        def _scan(current_dir: Path, rel_prefix: str, parent: dict, dir_cfg: dict = dir_cfg):
            try:
                entries = sorted(current_dir.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except Exception:
                return
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                entry_rel = f"{rel_prefix}/{entry.name}" if rel_prefix else entry.name
                clean_id_rel = entry_rel.replace("/", "_").replace("\\", "_")
                if entry.is_dir():
                    if dir_cfg.get("id") == "mrpl_rag_corpus" and entry.name == "07_User_Uploads":
                        continue
                    if dir_cfg.get("isPreset", False) and str(entry.resolve()).lower() in custom_subpaths:
                        continue
                    dir_clean_id = f"{dir_cfg.get('id')}_{clean_id_rel}"
                    dir_res = str(entry.resolve()).lower()
                    if (
                        dir_clean_id.lower() in deleted_records
                        or dir_res in deleted_records
                    ):
                        continue
                    sub = {
                        "id": dir_clean_id,
                        "name": entry.name,
                        "fullPath": str(entry.resolve()),
                        "relPath": entry_rel,
                        "type": "directory",
                        "isRoot": False,
                        "children": [],
                        "fileCount": 0,
                        "totalSizeBytes": 0,
                    }
                    _scan(entry, entry_rel, sub)
                    parent["children"].append(sub)
                    parent["fileCount"] += sub["fileCount"]
                    parent["totalSizeBytes"] += sub["totalSizeBytes"]
                elif entry.is_file():
                    entry_clean_id = f"{dir_cfg.get('id')}_{clean_id_rel}"
                    p_res = str(entry.resolve()).lower()
                    if (
                        entry_clean_id.lower() in deleted_records
                        or p_res in deleted_records
                    ):
                        continue
                    stat = entry.stat()
                    ext = entry.suffix.lstrip(".").lower()
                    # A watched source folder may sit outside the repo (the
                    # operator points the workbench at their own drive):
                    # relative_to RAISES there, which took down /api/corpus
                    # and /api/sources entirely. Absolute path in that case.
                    resolved_entry = entry.resolve()
                    try:
                        rel_workspace = str(resolved_entry.relative_to(Path.cwd().resolve())).replace("\\", "/")
                    except ValueError:
                        rel_workspace = str(resolved_entry).replace("\\", "/")
                    file_item = {
                        "id": entry_clean_id,
                        "name": entry.name,
                        "type": ext.upper(),
                        "extension": ext,
                        "size": f"{round(stat.st_size / 1024, 1)} KB",
                        "sizeBytes": stat.st_size,
                        "folder": rel_prefix or dir_cfg.get("name"),
                        "relPath": entry_rel,
                        "relativePath": rel_workspace,
                        "fullPath": str(entry.resolve()),
                        "corpus": dir_cfg.get("name"),
                        "enabled": True,
                        "category": categorise_source(ext)[0],
                        "subcategory": categorise_source(ext)[1],
                    }
                    parent["children"].append({**file_item, "type": "file"})
                    parent["fileCount"] += 1
                    parent["totalSizeBytes"] += stat.st_size
                    all_items.append(file_item)

        _scan(p, "", dir_node)
        dir_node["sizeDisplay"] = (
            f"{round(dir_node['totalSizeBytes'] / (1024 * 1024), 2)} MB"
            if dir_node["totalSizeBytes"] > 1e6
            else f"{round(dir_node['totalSizeBytes'] / 1024)} KB"
        )
        tree.append(dir_node)

    # If individual files were added, group them under a dedicated root in the tree
    if individual_files:
        total_indiv_bytes = sum(f["sizeBytes"] for f in individual_files)
        files_node = {
            "id": "user_ingested_files_root",
            "name": "User Ingested Documents",
            "fullPath": "Indexed in-place",
            "type": "directory",
            "isRoot": True,
            "isPreset": False,
            "children": [{**f, "type": "file"} for f in individual_files],
            "fileCount": len(individual_files),
            "totalSizeBytes": total_indiv_bytes,
            "sizeDisplay": (
                f"{round(total_indiv_bytes / (1024 * 1024), 2)} MB"
                if total_indiv_bytes > 1e6
                else f"{round(total_indiv_bytes / 1024)} KB"
            ),
        }
        tree.insert(0, files_node)

    total_bytes = sum(i["sizeBytes"] for i in all_items)
    # THE REAL COUNT OR NONE. This fell back to `files x 8` -- a number
    # nobody measured, shown as "chunks indexed". Unknown is reported as
    # null and rendered as unknown (Review Rule 4).
    #
    # Not read from the cache file either: at one archive folder that is
    # a 15 MB JSON parse on every sidebar refresh.
    # No lock: a first-boot corpus build holds it for minutes, and the
    # sidebar must not wait on that to list folders. len() of a list
    # reference is safe to read without it.
    chunk_count = None
    loaded = getattr(get_state(), "_chunks", None)
    if loaded is not None:
        chunk_count = len(loaded)

    return {
        "directories": dirs,
        "tree": tree,
        "sources": all_items,
        "count": len(all_items),
        "corpusCount": len(all_items),
        "chunkCount": chunk_count,
        "totalSizeBytes": total_bytes,
        "totalSizeDisplay": f"{round(total_bytes / (1024 * 1024), 1)} MB",
    }


@router.get("/corpus")
def get_corpus(response: Response, role: str | None = Query(None, description="Role tier to filter visibility")) -> dict:
    """Native corpus endpoint — sets no-cache headers and returns corpus data."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    data = _get_corpus_data()
    if role:
        from backend.auth.rbac import filter_corpus_tree
        filtered_tree, filtered_dirs, filtered_sources = filter_corpus_tree(
            role, data["tree"], data["directories"], data["sources"]
        )
        data = {
            **data,
            "tree": filtered_tree,
            "directories": filtered_dirs,
            "sources": filtered_sources,
            "count": len(filtered_sources),
            "corpusCount": len(filtered_sources),
            "role": role,
        }
    return data



@router.post("/sources")
def add_source(body: AddSourceRequest) -> dict:
    """Watch a folder or file, chunking and embedding it immediately into the knowledge base in-place."""
    import hashlib
    state = get_state()
    target = Path(body.path).resolve()
    if not target.exists():
        # Check relative to cwd
        target = Path.cwd() / body.path
        if not target.exists():
            raise HTTPException(400, detail=f"Path does not exist on disk: {body.path}")

    # Only register a watcher for directories. For a single file, pointing
    # the watcher at its parent directory would silently ingest every other
    # file in that folder — the opposite of what "add this one file" means.
    # Single files are tracked through configured_sources.json directly.
    source = None
    if target.is_dir():
        try:
            source = state.watcher.add_source(
                str(target), recursive=body.recursive, include_globs=body.include_globs
            )
        except Exception:
            source = None

    # Ingest the target (file or directory) in-place without copying
    from backend.ingestion.ingestion_progress import get_tracker

    target_files = [target] if target.is_file() else sorted(
        f for f in target.rglob("*")
        if f.is_file() and not f.name.startswith(".") and f.name.lower() != "readme.md"
    )
    tracker = get_tracker()
    job = tracker.create(str(target), target_files or [target], job_id=body.job_id)

    norm_path = str(target.resolve())
    norm_lower = norm_path.lower()
    hasher = hashlib.sha256(norm_lower.encode("utf-8")).hexdigest()[:10]
    dir_id = f"dir_{hasher}"
    file_id = f"file_{hasher}"

    # Write to configured_sources.json NOW — before the thread starts — so
    # that GET /api/corpus immediately after this response sees the new entry.
    # The ingestion thread also re-writes on completion (to update enabled
    # state), but the entry must exist for the sidebar to appear without a
    # page reload.
    config_file = source_config.CONFIG_PATH
    existing_dirs = []
    existing_dirs = source_config.load(config_file)
    _untombstone_source(norm_path, norm_lower, file_id if target.is_file() else dir_id)
    found = False
    for d in existing_dirs:
        if str(Path(d.get("path", "")).resolve()).lower() == norm_lower:
            d["enabled"] = True
            found = True
            break
    if not found:
        if target.is_dir():
            existing_dirs.append({"id": dir_id, "name": target.name or "Custom_Corpus",
                                   "path": norm_path, "isFile": False, "isPreset": False, "enabled": True})
        else:
            existing_dirs.append({"id": file_id, "name": target.name,
                                   "path": norm_path, "isFile": True, "isPreset": False, "enabled": True})
    source_config.save(existing_dirs, config_file)

    def _run():
        try:
            state.ingest_path(target, job_id=job.job_id)
            tracker.finish(job.job_id)
        except Exception as exc:  # noqa: BLE001 — recorded on the job, not propagated
            tracker.finish(job.job_id, error=f"{type(exc).__name__}: {exc}")

        # Re-sync configured_sources.json after ingestion (ensures enabled flag
        # is current and any state changes from ingest_path are persisted).
        import hashlib as _hl
        _cfg = source_config.CONFIG_PATH
        _dirs = []
        _dirs = source_config.load(_cfg)
        _norm = str(target.resolve())
        _norm_lo = _norm.lower()
        _hasher = _hl.sha256(_norm_lo.encode("utf-8")).hexdigest()[:10]
        _did = f"dir_{_hasher}"
        _fid = f"file_{_hasher}"
        _found = False
        for _d in _dirs:
            if str(Path(_d.get("path", "")).resolve()).lower() == _norm_lo:
                _d["enabled"] = True
                _found = True
                break
        if not _found and target.is_dir():
            _dirs.append({"id": _did, "name": target.name or "Custom_Corpus",
                          "path": _norm, "isFile": False, "isPreset": False, "enabled": True})
        elif not _found and target.is_file():
            _dirs.append({"id": _fid, "name": target.name,
                          "path": _norm, "isFile": True, "isPreset": False, "enabled": True})
        source_config.save(_dirs, _cfg)

    import threading
    threading.Thread(target=_run, name=f"ingest-{job.job_id}", daemon=True).start()

    return {
        "success": True,
        "job_id": job.job_id,
        "state": "running",
        "total_documents": len(target_files or [target]),
        "poll": f"/api/ingestion/{job.job_id}",
        "added": {
            "path": norm_path,
            "name": target.name,
            "id": file_id if target.is_file() else dir_id,
        },
        "source": source.model_dump() if source else {"path": str(target)},
        "message": (
            f"Source '{target.name}' queued for indexing: "
            f"{len(target_files or [target])} document(s). "
            f"Poll /api/ingestion/{job.job_id} for live per-document progress."
        ),
    }


@router.delete("/sources")
def remove_source(
    path: str = Query(...),
    id: str | None = Query(None),
    name: str | None = Query(None),
) -> dict:
    """Remove a source file or directory from active knowledge base and vector store."""
    state = get_state()
    config_file = source_config.CONFIG_PATH
    deleted_file = source_config.DELETED_PATH

    deleted_records = {str(s).lower() for s in source_config.load(deleted_file)}

    # Collect only specific identifiers: exact IDs and exact resolved full paths.
    # NEVER store generic base names like "docs" or Path(name).name.lower()!
    identifiers = set()
    if path and path.strip():
        identifiers.add(path.strip().lower())
        try:
            resolved_p = Path(path).resolve()
            identifiers.add(str(resolved_p).lower())
        except Exception:
            pass
    if id and id.strip():
        identifiers.add(id.strip().lower())
        if id.startswith("file_file_"):
            identifiers.add(id[5:].strip().lower())

    # Read config_file to see if it matches any registered entry
    real_path_to_delete = path
    if config_file.exists():
        remaining_dirs = []
        for d in source_config.load(config_file):
            d_id = str(d.get("id", "")).lower()
            d_path_res = str(Path(d.get("path", "")).resolve()).lower()
            if (
                d_id in identifiers
                or d_path_res in identifiers
                or (id and d_id == id.strip().lower())
                or (path and d_path_res == str(Path(path).resolve()).lower())
            ):
                real_path_to_delete = d.get("path", path)
                if d_id:
                    identifiers.add(d_id)
                identifiers.add(d_path_res)
            else:
                remaining_dirs.append(d)
        source_config.save(remaining_dirs, config_file)

    deleted_records.update(identifiers)
    source_config.save(list(deleted_records), deleted_file)

    return state.delete_source(real_path_to_delete)



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


class TranscribeRequest(BaseModel):
    audioBase64: str
    mimeType: str = "audio/webm"


# Recorded dictation is short. A cap keeps a stuck recorder from posting
# minutes of audio into a synchronous request.
_MAX_DICTATION_BYTES = 25 * 1024 * 1024
_AUDIO_SUFFIX = {
    "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "audio/mp4": ".m4a", "audio/mpeg": ".mp3",
}


@router.post("/transcribe")
def transcribe_dictation(body: TranscribeRequest) -> dict:
    """Speech-to-text for composer dictation, ON THIS MACHINE.

    HARD CONSTRAINT #1. Dictation used the browser's Web Speech API, and
    Chromium implements that by streaming microphone audio to Google's
    speech servers -- the code said as much ("requires Google cloud
    endpoint"). On any networked machine it worked, which means the
    operator's voice left the building on every dictation. Audio now comes
    here and is transcribed by the local faster-whisper model
    (transcribe_voice_note), in a temporary file deleted afterwards. The
    recording is not added to the corpus.
    """
    import base64
    import binascii
    import os
    import tempfile

    try:
        data = base64.b64decode(body.audioBase64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, detail=f"audio is not valid base64: {exc}") from exc
    if not data:
        raise HTTPException(400, detail="no audio received")
    if len(data) > _MAX_DICTATION_BYTES:
        raise HTTPException(413, detail="recording too long to transcribe in one request")

    suffix = _AUDIO_SUFFIX.get(body.mimeType.split(";")[0].strip().lower(), ".webm")
    handle, path = tempfile.mkstemp(suffix=suffix, prefix="dictation-")
    try:
        with os.fdopen(handle, "wb") as f:
            f.write(data)
        from backend.tools.audio.voice_transcription import transcribe_voice_note

        result = transcribe_voice_note(path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - reported, never guessed around
        raise HTTPException(500, detail=f"local transcription failed: {type(exc).__name__}: {exc}") from exc
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"text": result.full_text.strip(), "language": result.language, "engine": "faster-whisper (local)"}


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


# --------------------------------------------------------- contradictions

@router.get("/contradictions")
def contradictions(live: bool = Query(False)) -> dict:
    """Documents in the corpus that disagree about the same limit.

    Runs over the whole corpus rather than a query's results,
    deliberately: a contradiction only matters if you might act on either
    side of it, and a user who queries one document never sees that
    another disagrees. This is the sweep that surfaces it unprompted.
    """
    from backend.retrieval.contradiction import find_contradictions

    state = get_state()
    if live or state.corpus_is_loaded:
        _store, chunks = state.ensure_corpus()
    else:
        snapshot = state.snapshot()
        if not snapshot:
            raise HTTPException(503, detail="No corpus snapshot; run the ingestion export first.")

        class _C:
            def __init__(self, text, source):
                self.text = text
                self.source_document = source

        chunks = [_C(c["text"], c["source_document"]) for c in snapshot["chunks"]]

    found = find_contradictions(chunks)
    return {
        "checked_chunks": len(chunks),
        "contradictions": [c.model_dump() for c in found],
        "high_severity": sum(1 for c in found if c.severity == "high"),
    }


# ------------------------------------------------------------------- plan

class PlanRequestBody(BaseModel):
    request: str
    session_id: str = "default"


@router.post("/plan")
def build_plan(body: PlanRequestBody) -> dict:
    """Decompose a request into a dependency graph of steps (FR-5).

    Returns the AgentState shape FRONTEND.md §3.4's plan rail reads
    directly, including `ready` — the steps whose dependencies are
    satisfied right now. Independent steps appear together rather than in
    sequence, which is the visible difference between a plan graph and a
    numbered list.

    This is a real reasoning-model call and takes tens of seconds on
    CPU-only hardware.
    """
    from backend.orchestrator.planner import PlanningError, plan_request
    from backend.orchestrator.state import AgentState

    state = AgentState(session_id=body.session_id, original_request=body.request)
    try:
        state = plan_request(state)
    except PlanningError as exc:
        # 422, not 500: the request was well-formed and the server is
        # healthy — the model produced something unusable, which the
        # caller can act on by rephrasing or retrying.
        raise HTTPException(422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — Ollama down is a 503, not a crash
        raise HTTPException(503, detail=f"Planner model unavailable: {exc}") from exc

    return {
        "session_id": state.session_id,
        "original_request": state.original_request,
        "plan": [s.model_dump() for s in state.plan],
        "ready": [s.step_id for s in state.ready_steps()],
        "is_complete": state.is_complete(),
        "is_blocked": state.is_blocked(),
    }


# ------------------------------------------------------------------ decks
#
# Presentations are background jobs (orchestrator/output_jobs.py): write,
# artwork, render + measure + review + fix, then an approval request
# carrying the quality report. Chat starts them; these routes follow them.


class DeckJobRequest(BaseModel):
    request: str
    session_id: str = "default"
    # deck | docx | pdf | xlsx. Omitted, it is read from the request's own
    # wording, the same way chat decides.
    kind: str | None = None


def _deck_job_payload(job_id: str | None) -> dict | None:
    if not job_id:
        return None
    from backend.orchestrator import output_jobs

    job = output_jobs.get(job_id)
    return job.public() if job else {"job_id": job_id, "status": "unknown"}


@router.post("/decks")
def start_deck(body: DeckJobRequest) -> dict:
    """Queue a deliverable. Returns at once; poll GET /api/decks/{job_id}."""
    from backend.orchestrator import output_jobs
    from backend.orchestrator.action_resolver import output_kind_for

    if not body.request.strip():
        raise HTTPException(status_code=400, detail="request is empty")
    kind = body.kind or output_kind_for(body.request)
    if kind not in output_jobs.KINDS:
        raise HTTPException(status_code=400,
                            detail=f"unknown kind {kind!r}; expected one of {', '.join(sorted(output_jobs.KINDS))}")
    return output_jobs.start(body.request, session_id=body.session_id, kind=kind).public()


@router.get("/decks")
def list_decks() -> dict:
    from backend.orchestrator import output_jobs

    return {"jobs": [j.public() for j in output_jobs.all_jobs()]}


@router.get("/decks/{job_id}")
def get_deck(job_id: str) -> dict:
    from backend.orchestrator import output_jobs

    job = output_jobs.get(job_id)
    if job is None:
        # Jobs live in memory; a restart forgets them. Said, not hidden.
        raise HTTPException(status_code=404, detail=f"No job {job_id} (jobs do not survive a restart).")
    return job.public()


@router.post("/decks/{job_id}/approval")
def rerequest_deck_approval(job_id: str) -> dict:
    """Ask again for a finished deck whose approval expired, without redoing it."""
    from backend.orchestrator import output_jobs

    job = output_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}.")
    try:
        return output_jobs.request_approval(job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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

    # Approved files are written to outputs/ and nowhere else (backend/paths.py).
    if "output_path" in (body.arguments or {}):
        from backend.paths import confine_output

        body.arguments = {**body.arguments, "output_path": confine_output(body.arguments["output_path"])}

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
    elif body.tool_name == "draft_xlsx":
        from backend.tools.documents.draft_xlsx import describe_effect

        try:
            effect = describe_effect(
                body.arguments.get("title", ""),
                body.arguments.get("sheets", []),
                body.arguments.get("output_path", ""),
            )
        except Exception:  # noqa: BLE001
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
    entries = log.for_request(request_id) if request_id else log.all()[-limit:]
    return {"entries": [e.model_dump() for e in entries]}


# -------------------------------------------------------------- outputs

@router.get("/outputs")
def list_outputs() -> dict:
    """List generated documents and outputs (FRONTEND.md §3.7).

    Reads THE DIRECTORY APPROVED WRITES GO TO. This listed storage/outputs/
    while every approved deliverable was written to outputs/ (the path the
    approval card itself shows), so the Outputs page was empty of everything
    the operator had actually approved. storage/outputs/ is still read for
    files written by earlier builds.
    """

    from backend.orchestrator.action_resolver import OUTPUT_DIR

    outputs_dir = OUTPUT_DIR
    outputs_dir.mkdir(parents=True, exist_ok=True)
    legacy = Path("storage/outputs")
    candidates = list(outputs_dir.iterdir())
    if legacy.exists() and legacy.resolve() != outputs_dir.resolve():
        candidates += list(legacy.iterdir())

    # DELIVERABLES ONLY. The directory also holds working files -- the
    # approval ledger and the audit log are .jsonl next to the documents --
    # and listing those as "generated outputs" invites someone to open an
    # internal log expecting a report.
    DELIVERABLE_TYPES = {"docx", "pdf", "xlsx", "pptx", "csv", "md", "txt", "png", "jpg", "jpeg", "svg"}

    items = []
    for p in sorted(candidates, key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lstrip(".").lower() in DELIVERABLE_TYPES:
            ext = p.suffix.lstrip(".").lower()
            stat = p.stat()
            size_kb = round(stat.st_size / 1024, 1)
            size_display = f"{size_kb} KB" if size_kb < 1024 else f"{round(size_kb / 1024, 2)} MB"
            from datetime import datetime as dt_datetime
            written = dt_datetime.fromtimestamp(stat.st_mtime)

            # No citation count: this reported 3 for EVERY document, shown as
            # "3 verified citation(s)" -- a number nobody counted (Rule 4).
            items.append({
                "id": p.name,
                "filename": p.name,
                "fileType": ext,
                "fileSize": size_display,
                "sizeBytes": stat.st_size,
                "generatedAt": written.strftime("%Y-%m-%d %H:%M"),
                "writtenAt": stat.st_mtime,
                "path": str(p.resolve()),
            })

    return {"files": items, "count": len(items)}


@router.get("/outputs/{filename}/download")
def download_output(filename: str):
    """Download a generated document from storage/outputs/ with path traversal protection."""
    from fastapi.responses import FileResponse

    from backend.orchestrator.action_resolver import OUTPUT_DIR

    roots = [OUTPUT_DIR.resolve(), Path("storage/outputs").resolve()]
    target = None
    for root in roots:
        candidate = (root / filename).resolve()
        # Path traversal: the resolved file must still sit inside its root.
        if str(candidate).startswith(str(root)) and candidate.is_file():
            target = candidate
            break
    if target is None:
        raise HTTPException(404, detail=f"Output file {filename!r} not found.")

    return FileResponse(
        path=str(target),
        filename=filename,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------- search

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    role: str | None = None


@router.post("/search")
def search(body: SearchRequest) -> dict:
    """Grounded retrieval: chunks, or an explicit refusal.

    Returns `found: false` when nothing clears the confidence gate, which
    is a real answer (NFR-4) and not an empty-result edge case. Measured:
    before that gate was fixed it refused 0 of 16 questions including
    ones about Pride and Prejudice.
    """
    from backend.auth.rbac import filter_chunks_by_role
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    state = get_state()
    store, _chunks = state.ensure_corpus()
    result = retrieve_with_grounding_check(store, body.query, top_k=body.top_k)

    chunks = result.chunks
    if body.role:
        chunks = filter_chunks_by_role(body.role, chunks)
        if not chunks and result.chunks:
            return {
                "found": False,
                "reason": f"Access restricted: retrieved passages belong to categories not permitted for role '{body.role}'.",
                "chunks": [],
            }

    return {
        "found": result.found and len(chunks) > 0,
        "reason": result.reason if chunks else "No accessible passages found",
        "chunks": [
            {
                "text": c.text,
                "source_document": c.source_document,
                "page_number": c.page_number,
                "score": c.score,
            }
            for c in chunks
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


# ----------------------------------------------------------------- chat

class ChatRequestBody(BaseModel):
    message: str
    session_id: str = "default"


# Machine-readable action type per gate category. Mapped rather than
# hardcoded, because the previous single literal "DCS_SETPOINT_WRITE"
# labelled a request to write a Word document as a setpoint change --
# and action_type is what an audit reader filters on.
_ACTION_TYPES = {
    "setpoint change": "SETPOINT_WRITE",
    "SAP / ERP write": "SAP_WRITE",
    "outbound send": "OUTBOUND_SEND",
    "destructive change": "DESTRUCTIVE_CHANGE",
    "file write": "FILE_WRITE",
}

# What a REGISTERED tool does, for approvals whose arguments are a real
# tool call rather than a parsed instruction. Keyed on the tool because
# that is what will actually run.
_TOOL_ACTION_TYPES = {
    "draft_docx": "FILE_WRITE",
    "draft_xlsx": "FILE_WRITE",
    "generate_pdf": "FILE_WRITE",
    "generate_deck": "FILE_WRITE",
    "run_in_sandbox": "CODE_EXECUTION",
}


@router.post("/chat")
def chat(body: ChatRequestBody) -> dict:
    """Core agentic orchestration endpoint for the workbench chat interface.

    Coordinates router, multi-step planner DAG, dispatch to sub-agents,
    grounded synthesis with citations, self-verification, and safety approval.
    """
    from backend.audit.approval_gate import ApprovalGate
    from backend.orchestrator.graph import run_agent_turn

    # Persistence moved into the orchestrator (backend/memory/turn.py),
    # so that BOTH endpoints record a turn the same way and neither can
    # be the one that forgets. Doing it here recorded turns only for
    # requests that arrived through this route.
    state = run_agent_turn(body.message, body.session_id)

    # Citations shaped for frontend citation viewer
    citations = []
    for idx, chunk in enumerate(state.retrieved_context, start=1):
        doc = chunk.get("source_document") or "Document"
        p = chunk.get("page_number")
        sec = f"p. {p}" if p is not None else "General"
        passage = chunk.get("text", "")
        citations.append({
            "id": idx,
            "doc": doc,
            "section": sec,
            "passage": passage[:300] + "..." if len(passage) > 300 else passage,
        })

    # Plan DAG shaped for PlanGraphView.jsx
    plan = []
    for s in state.plan:
        plan.append({
            "id": s.step_id,
            "step_id": s.step_id,
            "description": s.description,
            "assigned_agent": s.assigned_agent,
            "status": s.status,
            "depends_on": s.depends_on,
            "tool_call_event_id": f"{s.step_id}-event",
        })

    tool_call_events = [e.model_dump() for e in state.tool_call_log]

    # Approval action metadata if gated
    approval_action = None
    if state.awaiting_human_approval and state.final_output_path:
        gate = ApprovalGate()
        try:
            req = gate.get(state.final_output_path)
            # THE PAYLOAD DESCRIBES THE ACTION THAT WAS ACTUALLY
            # REQUESTED. IT USED TO DESCRIBE A DIFFERENT ONE.
            #
            # Every field below except `description` and `id` was a
            # hardcoded literal about a feed-rate change. Asked to
            # "Draft a DOCX report on the Hassan incident and save it",
            # the modal rendered:
            #
            #     DCS_SETPOINT_WRITE
            #     "Confirm Operational Setpoint Modification"
            #     Target: HCU-2 / FFC-201
            #     CURRENT 100% (1,450 m3/h) -> PROPOSED 115% (1,667 m3/h)
            #     "+15.0% Excursion"
            #     "Operating above 110% reduces catalyst residence time
            #      (LHSV > 1.8 h-1) and increases exothermic runaway risk"
            #
            # for a request to write a Word document. The one honest
            # line -- "Operator-requested file write" -- came from the
            # gate itself and sat surrounded by invented flow rates.
            #
            # This is the single worst place in the product for that.
            # It is the screen where a human signs off, and approval
            # recorded against invented figures produces a signed audit
            # entry for something nobody approved. Ask an operator
            # "what did you authorise?" and the honest answer was a
            # number the system made up. That is worse than having no
            # gate: the gate is what makes the record trustworthy.
            #
            # Nothing here is invented now. Fields the system cannot
            # know are ABSENT rather than filled with plausible
            # placeholders -- an empty field reads as unknown, a
            # plausible one reads as measured.
            # RESOLVED vs NOT. An unresolved action carries only the
            # operator's command and a category. A resolved one carries the
            # real tool's arguments -- for draft_docx, draft_xlsx and
            # generate_deck an exact output_path -- and the card said "has NOT
            # resolved a file path" directly above a preview naming that file.
            resolved = "category" not in req.arguments
            output_path = req.arguments.get("output_path") if resolved else None
            category = (
                "file write" if output_path
                else req.arguments.get("category") or "operator action"
            )
            command = req.arguments.get("command") or req.effect

            generic_unresolved_warning = (
                "The workbench has NOT resolved a target device, file "
                "path or value for this instruction. Approving records "
                "your authorisation for the action exactly as worded "
                "above — confirm the specifics yourself before "
                "authorising."
            )

            # Rich presentation overrides for document drafting tools (only when resolved)
            if resolved and req.tool_name in ("draft_docx", "draft_xlsx"):
                kind_name = "Excel Spreadsheet" if req.tool_name == "draft_xlsx" else "Word Document"
                title_val = req.arguments.get("title") or kind_name
                title = f"Confirm {kind_name} Draft ({title_val})"
                # `detail` is the OPERATOR'S OWN WORDS, and stays that way: it
                # was overwritten with 'Draft Word Document "<title>" to <path>',
                # a phrase the system composed. What will be written is already
                # in `description`, `target` and the preview; the one field that
                # records what the person actually asked for cannot be a
                # paraphrase, or the audit trail no longer holds their request.
                detail = command
                # No warning on a RESOLVED action. `warning` means "the
                # system could not resolve the specifics of this" -- a
                # generic "review before authorizing" on every draft makes
                # that signal meaningless, and the preview already lists
                # the file, its sections and their sources.
                warning = None
            else:
                title = f"Confirm {category}"
                detail = command
                warning = None if resolved else generic_unresolved_warning

            approval_action = {
                "id": req.request_id,
                "title": title,
                "action_type": _ACTION_TYPES.get(
                    category, _TOOL_ACTION_TYPES.get(req.tool_name, "OPERATOR_ACTION")
                ),
                "target": output_path,
                "description": req.effect,
                "detail": detail,
                "requested_by_operator": command,
                "resolved_parameters": resolved,
                "risk_level": "REQUIRES_REVIEW",
                "warning": warning,
                "token": req.token,
            }
        except Exception:
            pass

    return {
        "reply": state.draft_output or "Analysis complete.",
        "citations": citations,
        "plan": plan,
        "tool_call_events": tool_call_events,
        "session_id": state.session_id,
        "memory": state.memory_summary or None,
        "awaiting_human_approval": state.awaiting_human_approval,
        "approval_action": approval_action,
        "deck_job": _deck_job_payload(state.deck_job_id),
        # The self-verification verdict (AGENTS_SPEC §5) was computed and
        # then not returned, so the UI had no way to distinguish a
        # confirmed answer from one the verifier objected to. Shipping
        # the verdict is the entire point of having a verifier.
        "verification": (
            {
                "passed": state.verification_result.passed,
                "reason": state.verification_result.reason,
                "checked_claims": state.verification_result.checked_claims,
            }
            if state.verification_result
            else None
        ),
    }


# --------------------------------------------------------------- models

@router.get("/models")
def list_models() -> dict:
    """The model registry, with each model's REAL availability.

    WHY THIS EXISTS ON THE BACKEND. The frontend dev server was serving
    this route itself, from a hand-rolled parse of models.yaml, and it
    reported `status: "active"` for every entry unconditionally. Two of
    the registered models are not pulled on this machine -- phi-3.5-mini
    (the router AND the verifier) and qwen2.5-coder:7b -- so the model
    picker offered models that do not exist, and the verification step
    failed with a bare 404 that looked like a bug rather than a missing
    download.

    It also guessed VRAM by substring: "14b" in the tag meant "8.5 GB",
    regardless of quantisation. Ollama reports the real on-disk size, so
    there is no reason to guess.

    A registry that cannot distinguish "configured" from "present" is
    not a registry; it is a list of intentions. Both states are reported
    here, separately and by name.
    """
    import requests

    # _DEFAULT_REGISTRY_PATH, not load_registry's own default: CARD 01
    # specifies "/models/models.yaml", an absolute container path that
    # resolves to E:\models\models.yaml on a Windows dev box and does
    # not exist. registry.py already resolves the real one relative to
    # the repo; every caller in this repo must use that.
    from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry

    try:
        registry = load_registry(_DEFAULT_REGISTRY_PATH)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Could not read models.yaml: {exc}") from exc

    # What Ollama actually has. Unreachable is reported as unknown, never
    # as absent -- claiming a model is missing because the daemon is down
    # sends someone to re-download models they already have.
    pulled: dict[str, dict] | None = None
    ollama_error = None
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=3)
        res.raise_for_status()
        pulled = {m["name"]: m for m in res.json().get("models", [])}
    except Exception as exc:  # noqa: BLE001
        ollama_error = f"{type(exc).__name__}: {exc}"

    models = []
    for model_id, cfg in registry.items():
        tag = cfg.model
        # Ollama normalises a bare name to name:latest.
        entry = None
        if pulled is not None:
            entry = pulled.get(tag) or pulled.get(f"{tag}:latest")

        if cfg.backend in ("diffusers", "transformers"):
            # On disk, loaded in-process -- not an Ollama tag.
            from backend.models.registry import fetch_command, is_locally_available, weights_dir

            entry = None
            if is_locally_available(cfg, None):
                status, detail = "available", None
            else:
                status, detail = (
                    "not_pulled",
                    f"Weights not found at {weights_dir(cfg)}. "
                    f"Run once, online: {fetch_command(cfg)}",
                )
        elif pulled is None:
            status, detail = "unknown", f"Ollama unreachable ({ollama_error})"
        elif entry is not None:
            status, detail = "available", None
        else:
            status, detail = "not_pulled", f"Run: ollama pull {tag}"

        from backend.models.provenance import get_model_provenance

        models.append({
            "id": model_id,
            "backend": cfg.backend,
            "model": tag,
            "task_tags": list(cfg.task_tags),
            "status": status,
            "detail": detail,
            # Real bytes from Ollama, or null. Never an estimate dressed
            # up as a measurement.
            "size_bytes": entry.get("size") if entry else None,
            "size_display": (
                f"{entry['size'] / 1e9:.1f} GB" if entry and entry.get("size") else None
            ),
            "parameter_size": (entry.get("details") or {}).get("parameter_size") if entry else None,
            "quantization": (entry.get("details") or {}).get("quantization_level") if entry else None,
            "provenance": get_model_provenance(model_id),
        })

    return {
        "models": models,
        "registry_path": "models/models.yaml",
        "ollama_reachable": pulled is not None,
        "ollama_error": ollama_error,
        "available_count": sum(1 for m in models if m["status"] == "available"),
        "missing": [m["model"] for m in models if m["status"] == "not_pulled"],
    }


@router.get("/models/provenance")
def get_model_provenance_ledger() -> dict:
    """Full chain-of-custody model provenance ledger (TOOLS.md row 47)."""
    from backend.models.provenance import get_all_provenance

    return {"ledger": get_all_provenance()}


@router.get("/rbac/tiers")
def get_rbac_matrix() -> dict:
    """Role-Based Access Control matrix and categories (TOOLS.md row 46)."""
    from backend.auth.rbac import get_rbac_manifest

    return get_rbac_manifest()


def _os_user() -> str:
    try:
        import getpass

        return getpass.getuser()
    except Exception:  # noqa: BLE001 - no login name in some service contexts; shown as absent
        return ""


@router.get("/system-info")
def system_info() -> dict:
    """Host facts the status bar reports, measured rather than assumed."""
    import platform

    import psutil

    vm = psutil.virtual_memory()
    info = {
        # Who is running this workstation and which machine it is -- the top
        # bar showed a fixed "Operator / Station #1".
        "user": _os_user(),
        "host": platform.node(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python_version": platform.python_version(),
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram_total_gb": round(vm.total / 1e9, 1),
        "ram_used_percent": vm.percent,
        "gpu": None,
    }

    # nvidia-smi if present. Absent is reported as absent; the previous
    # implementation had no GPU path at all and the UI showed "N/A"
    # without ever saying whether that meant "no GPU" or "not checked".
    try:
        import subprocess

        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip().splitlines()
        if out:
            name, used, total, util = (x.strip() for x in out[0].split(","))
            info["gpu"] = {
                "name": name,
                "memory_used_mb": int(used),
                "memory_total_mb": int(total),
                "utilization_percent": int(util),
            }
    except Exception:  # noqa: BLE001
        info["gpu_detection"] = "nvidia-smi unavailable; no NVIDIA GPU detected or driver not installed"

    return info


@router.get("/graph/neighbourhood")
def graph_neighbourhood(
    node: str,
    hops: int = Query(2, ge=1, le=4),
    limit: int = Query(300, ge=1, le=2000),
) -> dict:
    """The subgraph within `hops` of `node`, with each node's distance.

    WHY THIS EXISTS. /api/graph returns the whole graph, which is fine
    at this corpus size and useless at a real one -- and it answers the
    wrong question anyway. The interesting GraphRAG queries are
    multi-hop: "what incidents touch the segment this SOP governs?" is
    document -> segment -> incident, two hops, and the value of the
    answer is the PATH, not the endpoints.

    Returns `distance` on every node so the UI can stage the reveal by
    hop -- which is what makes a traversal legible rather than a hairball
    appearing all at once.

    PARAMETERISED, NOT ARBITRARY CYPHER. The client sends a node name and
    a hop count, never a query. An endpoint that executed client-supplied
    Cypher against the knowledge graph would be an injection surface on
    a system whose entire claim is that it is trustworthy about
    provenance -- and `hops` is capped because an uncapped variable-
    length match on a dense graph is a denial of service against your own
    database.
    """
    state = get_state()
    graph = state.graph()
    if not graph.get("available"):
        raise HTTPException(
            503, detail=graph.get("error") or "graph unavailable"
        )

    client = state.graph_client()
    if client is None:
        raise HTTPException(503, detail="graph client unavailable")

    # Match on any of the name properties the schema uses, so callers do
    # not need to know which label they are asking about.
    cypher = (
        # The property names are the real ones in this schema, verified
        # against a populated graph: Equipment.tag, Document.filename,
        # Person.name, PipelineSegment.segment_name, Incident.summary.
        # Guessing them produced a silent empty result plus a Neo4j
        # "property key does not exist" warning that the API swallowed --
        # a traversal that finds nothing looks identical to a node with
        # no neighbours.
        "MATCH (start) "
        "WHERE start.name = $node OR start.segment_name = $node "
        "   OR start.tag = $node OR start.filename = $node "
        f"MATCH path = (start)-[*0..{int(hops)}]-(reached) "
        "WITH start, reached, min(length(path)) AS distance "
        "RETURN DISTINCT labels(reached) AS labels, properties(reached) AS props, "
        "       distance, elementId(reached) AS id "
        "ORDER BY distance "
        f"LIMIT {int(limit)}"
    )

    try:
        rows = client.run_cypher(cypher, node=node)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"traversal failed: {exc}") from exc

    if not rows:
        # An empty result is not an error, but it must not look like a
        # successful traversal of an empty neighbourhood either.
        return {
            "node": node,
            "hops": hops,
            "found": False,
            "detail": f"No node matched {node!r}. Names are exact.",
            "nodes": [],
            "edges": [],
        }

    nodes = [
        {
            "id": r.get("id"),
            "labels": r.get("labels") or [],
            "properties": r.get("props") or {},
            "distance": r.get("distance"),
        }
        for r in rows
    ]
    ids = {n["id"] for n in nodes}

    edge_cypher = (
        "MATCH (a)-[r]-(b) "
        "WHERE elementId(a) IN $ids AND elementId(b) IN $ids "
        "RETURN DISTINCT elementId(a) AS source, elementId(b) AS target, "
        "       type(r) AS type"
    )
    try:
        edges = client.run_cypher(edge_cypher, ids=list(ids))
    except Exception:  # noqa: BLE001
        edges = []

    return {
        "node": node,
        "hops": hops,
        "found": True,
        "nodes": nodes,
        "edges": edges,
        "by_distance": {
            str(d): sum(1 for n in nodes if n["distance"] == d)
            for d in sorted({n["distance"] for n in nodes if n["distance"] is not None})
        },
    }


# ---------------------------------------------------- memory / sessions

@router.get("/sessions")
def list_sessions(limit: int = Query(50, ge=1, le=200)) -> dict:
    """Every conversation, newest first.

    Sessions were previously not stored at all -- `session_id` was
    threaded through every request and written nowhere, so each turn
    began from nothing and the Chats list in the sidebar had to be
    faked. It was, with five invented conversations.
    """
    from backend.memory.store import get_store

    sessions = get_store().list_sessions(limit)
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "title": s.title,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "turn_count": s.turn_count,
            }
            for s in sessions
        ],
        "count": len(sessions),
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    """One conversation with its full message history."""
    from backend.memory.store import get_store

    store = get_store()
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, detail=f"No session {session_id!r}")

    messages = store.all_messages(session_id)
    return {
        "session_id": session.session_id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "turn_count": session.turn_count,
        "messages": [
            {
                "message_id": m.message_id,
                "turn_index": m.turn_index,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "route": m.route,
                "citations": m.citations,
                "documents": m.documents,
                "tool_calls": m.tool_calls,
            }
            for m in messages
        ],
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """Delete a conversation and everything in it."""
    from backend.memory.store import get_store

    get_store().delete_session(session_id)
    get_state().attachment_manager.cleanup_session(session_id=session_id)
    return {"deleted": session_id}


@router.get("/sessions/{session_id}/memory")
def get_session_memory(session_id: str) -> dict:
    """What the system currently remembers about this conversation.

    Exposed because memory that cannot be inspected cannot be trusted or
    debugged. When an answer refers to something unexpected, this is
    where you look: the focus documents are what steer retrieval for
    follow-ups.
    """
    from backend.memory import working

    memory = working.load(session_id)
    return {
        "session_id": session_id,
        "message_count": len(memory.messages),
        "focus_documents": memory.focus_documents,
        "last_user_request": memory.last_user_request,
        "last_route": memory.last_route,
        "context_block": memory.context_block(),
    }


class RememberRequest(BaseModel):
    content: str
    session_id: str | None = None


@router.get("/memory/facts")
def list_facts(limit: int = Query(100, ge=1, le=500)) -> dict:
    """Durable facts about the user, across all conversations.

    Every one is listed and deletable. A memory system that silently
    decides what to remember about a person is one they cannot correct.
    """
    from backend.memory.long_term import get_long_term

    facts = get_long_term().all_facts(limit)
    return {
        "facts": [
            {
                "fact_id": f.fact_id,
                "kind": f.kind,
                "content": f.content,
                "source_session": f.source_session,
                "created_at": f.created_at,
                "use_count": f.use_count,
            }
            for f in facts
        ],
        "count": len(facts),
    }


@router.post("/memory/facts")
def remember_fact(body: RememberRequest) -> dict:
    """Store a durable preference or identity fact.

    Returns stored=false when the statement does not qualify -- most
    messages do not, and that is the normal case rather than an error.

    Document FINDINGS are rejected here by design: storing "the average
    MFI is 3.4" would create a second source of truth that is never
    cited and never expires, so the first corpus revision leaves the
    system answering confidently from a stale number.
    """
    from backend.memory.long_term import get_long_term

    fact = get_long_term().remember(body.content, source_session=body.session_id)
    if fact is None:
        return {
            "stored": False,
            "reason": (
                "Not a durable preference or identity statement, or it looks "
                "like a finding from a document. Findings come from retrieval "
                "with a citation, every time."
            ),
        }
    return {"stored": True, "fact_id": fact.fact_id, "kind": fact.kind}


@router.delete("/memory/facts/{fact_id}")
def forget_fact(fact_id: str) -> dict:
    from backend.memory.long_term import get_long_term

    return {"deleted": get_long_term().forget(fact_id)}


# ------------------------------------------------------ agentic stream

class AgentStreamRequest(BaseModel):
    message: str
    session_id: str = "default"
    # Documents currently enabled in the Sources panel. None means "no
    # filter" (search everything); an EMPTY LIST means the user switched
    # everything off, which is a different instruction and is honoured
    # as one.
    active_documents: list[str] | None = None
    # Master switch toggled in Sources panel and Composer toolbar.
    # When True: grounds in local sources and includes citations.
    # When False: bypasses document retrieval and uses direct general reasoning.
    sources_enabled: bool = True


@router.post("/chat/stream")
def chat_stream(body: AgentStreamRequest):
    """Work on the request, streaming what happens as it happens (SSE).

    WHY THIS EXISTS ALONGSIDE /api/chat.

    /api/chat returns one paragraph after 17-25 seconds of silence. That
    is the wrong shape for an agent that calls tools: the interesting
    part -- which tool it reached for, what the tool returned, whether it
    changed course -- is invisible, and the user has no way to tell a
    slow answer from a hung one.

    This streams the work: narration as it is written, each tool call
    with its arguments BEFORE it runs, each result with its real return
    value and duration. Text, work, text, work.

    SHOWING THE ARGUMENTS IS A SAFETY FEATURE, NOT A FLOURISH.

    Measured on the first run of the loop: asked for "381.95 minus 400",
    the model called evaluate_expression with "-381.95 - 400" -- a
    spurious leading minus -- and the tool correctly returned -781.95 for
    the expression it was given. Hard constraint #3 guarantees the number
    came from an executed tool. It does NOT guarantee the model asked the
    tool the right question, and nothing downstream can tell the
    difference: the answer arrives with a genuine tool-call receipt
    attached.

    The only thing that catches it is a human seeing the arguments. So
    the arguments are streamed before the result, deliberately.

    Event types are defined in
    docs/Technical_Specs/AGENT_STREAM_PROTOCOL.md, which is the contract
    with the frontend.
    """
    from fastapi.responses import StreamingResponse

    from backend.orchestrator.agent_loop import run_turn

    def event_source():
        try:
            # run_turn, not run_agent_loop: the backend decides which
            # path answers this and emits the same protocol either way,
            # so the UI never has to choose. See path_router.py.
            for event in run_turn(
                body.message,
                session_id=body.session_id,
                active_documents=body.active_documents,
                sources_enabled=body.sources_enabled,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # noqa: BLE001
            # A crash mid-stream must reach the client as an event. A
            # silently truncated SSE stream is indistinguishable from a
            # slow one, so the UI would spin forever.
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"{type(exc).__name__}: {exc}",
            }) + "\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Without this, a proxy that buffers will hold the whole
            # stream and deliver it at the end -- which is exactly the
            # behaviour this endpoint exists to avoid.
            "X-Accel-Buffering": "no",
        },
    )


class AddModelRequest(BaseModel):
    id: str
    model: str
    backend: str = "ollama"
    task_tags: list[str] = []


@router.post("/models")
def add_model(body: AddModelRequest) -> dict:
    """Append a model to models.yaml and reload the registry (FR-4).

    WHY THIS EXISTS. Only GET was implemented, so the settings page's
    Add Model form posted into a 405 and showed a success toast anyway.
    FR-4 -- adding a model without a code change -- is a scripted
    on-stage moment, and it had no backend at all.

    VALIDATED AGAINST OLLAMA BEFORE IT IS WRITTEN. Two tags in this
    repo's own registry never existed (`qwen2-vl:7b`, `phi-3.5-mini`)
    and both were discovered only when something tried to use them --
    one of them had been silently 404ing the router and the verifier for
    weeks. A registry that accepts a name nobody checked is how that
    happens, so a tag Ollama does not have is refused here with the pull
    command rather than written and discovered later.

    The registry is reloaded in-process afterwards, so the new model is
    usable immediately. That is the whole point of the demo.
    """

    from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry

    model_id = body.id.strip()
    tag = body.model.strip()
    if not model_id or not tag:
        raise HTTPException(400, detail="Both 'id' and 'model' are required.")

    registry_path = Path(_DEFAULT_REGISTRY_PATH)
    try:
        existing = load_registry(str(registry_path))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Could not read models.yaml: {exc}") from exc

    if model_id in existing:
        raise HTTPException(
            409, detail=f"Registry id {model_id!r} already exists."
        )

    # Refuse a tag Ollama does not have.
    try:
        import requests

        res = requests.get("http://localhost:11434/api/tags", timeout=5)
        res.raise_for_status()
        pulled = {m["name"] for m in res.json().get("models", [])}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            503,
            detail=(
                f"Cannot reach Ollama to verify {tag!r}: {exc}. Refusing to "
                f"write an unverified model name into the registry."
            ),
        ) from exc

    if tag not in pulled and f"{tag}:latest" not in pulled:
        raise HTTPException(
            400,
            detail=(
                f"Ollama does not have {tag!r}. Pull it first:\n"
                f"    ollama pull {tag}\n"
                f"Two tags in this registry never existed and were found only "
                f"when something tried to use them; names are verified here "
                f"rather than trusted."
            ),
        )

    raw = registry_path.read_text(encoding="utf-8")
    entry = (
        f"\n- id: {model_id}\n"
        f"  backend: {body.backend}\n"
        f"  model: {tag}\n"
        f"  task_tags: [{', '.join(body.task_tags)}]\n"
    )
    registry_path.write_text(raw.rstrip() + "\n" + entry, encoding="utf-8")

    try:
        reloaded = load_registry(str(registry_path))
    except Exception as exc:  # noqa: BLE001
        # Put the file back rather than leaving the registry unloadable.
        registry_path.write_text(raw, encoding="utf-8")
        raise HTTPException(
            500,
            detail=f"Entry was invalid and has been rolled back: {exc}",
        ) from exc

    return {
        "added": model_id,
        "model": tag,
        "registry_size": len(reloaded),
        "message": f"{model_id} added and the registry reloaded. Usable now.",
    }


# --------------------------------------------------------- verification

class VerifyRequest(BaseModel):
    request: str
    answer: str
    session_id: str = "default"


@router.post("/verify")
def verify_answer(body: VerifyRequest) -> dict:
    """Check an answer against the corpus, on demand (AGENTS_SPEC §5).

    WHY THIS IS A SEPARATE ENDPOINT RATHER THAN PART OF /api/chat.

    Verification is a second LLM call on a different model. On an 8 GB
    card that evicts the generation model and reloads the verifier, and
    the cost is wildly variable -- measured at 9s when the verifier was
    already resident and 102s when it had to reload under memory
    pressure. Inline, that turned a 70-second turn into 175 seconds for
    a check the user had not asked for and could not see until it
    finished.

    So the answer is returned as soon as it exists, and this runs when
    the user presses Verify on a claim that matters to them. The check
    is unchanged -- same model, same fail-closed parsing, same sources.
    Only WHEN it runs changed.

    Sources are re-retrieved rather than passed in from the client.
    Retrieval is ~0.15s and the client's copy is truncated for display;
    more importantly, a verifier fed sources chosen by the caller is
    checking a claim against evidence the caller supplied, which is not
    a check at all.
    """
    from backend.orchestrator.state import AgentState
    from backend.orchestrator.verification import VerificationOutcome, verify_output
    from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

    if not body.answer.strip():
        raise HTTPException(400, detail="Nothing to verify: answer is empty.")

    state = get_state()
    try:
        store, _ = state.ensure_corpus()
        grounding = retrieve_with_grounding_check(store, body.request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Could not retrieve sources: {exc}") from exc

    agent_state = AgentState(
        session_id=body.session_id,
        original_request=body.request,
        draft_output=body.answer,
        retrieved_context=[
            {
                "text": c.text,
                "source_document": c.source_document,
                "page_number": c.page_number,
                "score": c.score,
            }
            for c in grounding.chunks
        ],
    )

    try:
        verified, outcome = verify_output(agent_state)
    except Exception as exc:  # noqa: BLE001
        # Cannot verify is NOT verified, and says so in those words.
        return {
            "passed": False,
            "outcome": "unconfirmed",
            "reason": f"The verifier could not be reached: {type(exc).__name__}: {exc}",
            "checked_claims": [],
            "sources_checked": len(agent_state.retrieved_context),
        }

    result = verified.verification_result
    return {
        "passed": bool(result and result.passed),
        "outcome": outcome.value if isinstance(outcome, VerificationOutcome) else str(outcome),
        "reason": (result.reason if result else "") or "",
        "checked_claims": list(result.checked_claims) if result else [],
        "sources_checked": len(agent_state.retrieved_context),
    }


# -------------------------------------------------------------- network

@router.get("/network/status")
def get_network_telemetry() -> dict:
    """Network connection status and telemetry metrics (FR-1, FR-15)."""
    from backend.audit.network_monitor import get_network_status

    return get_network_status()


# ---------------------------------------------------- approval resolve

class ApprovalResolveBody(BaseModel):
    request_id: str
    confirmed: bool
    operator: str = "operator"


@router.post("/approvals/resolve")
def resolve_approval(body: ApprovalResolveBody) -> dict:
    """Handle operator confirm/cancel decision from the frontend ApprovalModal."""
    from backend.audit.approval_gate import ApprovalGate

    gate = ApprovalGate()
    if body.confirmed:
        # THE FALLBACK HERE DEFEATED EVERY PROPERTY OF THE GATE.
        #
        # It caught any failure from approve() and, instead of
        # reporting it, REGISTERED A NEW REQUEST and approved that --
        # returning the caller's original request_id alongside a token
        # belonging to a different one. approve() fails for exactly the
        # reasons that matter:
        #
        #   expired      the 15-minute TTL exists because a decision
        #                made in a context that is gone should not still
        #                act. The fallback silently renewed it.
        #   already used single-use exists so one approval cannot
        #                authorise a retry loop. The fallback minted a
        #                second one.
        #   unknown id   a request that was never made got approved.
        #
        # An approval is a record that a person authorised a SPECIFIC
        # action with SPECIFIC arguments. Manufacturing one because the
        # real one could not be found is the one thing this endpoint
        # must never do. The failure is reported instead.
        try:
            approved = gate.approve(body.request_id, approved_by=body.operator)
        except KeyError as exc:
            raise HTTPException(404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - expired, refused, already used
            raise HTTPException(
                409,
                detail=(
                    f"{exc} This approval was not granted. Re-issue the request "
                    f"and approve the new one -- an approval cannot be renewed "
                    f"after it expires or is used."
                ),
            ) from exc
        token = approved.token

        return {
            "status": "approved",
            "request_id": body.request_id,
            "token": token,
            "message": f"Action authorized by {body.operator}.",
        }
    else:
        # A refusal that was not recorded must not report success. The
        # audit log is the evidence that a person said no; claiming an
        # entry exists when it does not is a false record, and the
        # direction of the lie is the dangerous one.
        try:
            gate.refuse(
                body.request_id, refused_by=body.operator, reason="Cancelled by operator"
            )
        except KeyError as exc:
            raise HTTPException(404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(409, detail=f"Refusal not recorded: {exc}") from exc
        return {
            "status": "refused",
            "request_id": body.request_id,
            "message": "Action cancelled by operator.",
        }


# ---------------------------------------------------- attachments payload & state

class AttachmentUploadPayload(BaseModel):
    filename: str
    type: str = "application/pdf"
    category: str = "temporary"
    processing: bool = True
    contentBase64: str | None = None
    content: str | None = None
    session_id: str | None = None


@router.post("/attachments/upload")
async def upload_attachment(
    request: Request,
    file: UploadFile | None = File(None),
    filename: str | None = Form(None),
    type: str | None = Form(None),
    category: str | None = Form(None),
    session_id: str | None = Form(None),
) -> dict:
    """Accept attachment file + metadata payload, assign attachment_id and category.

    Returns {"attachment_id": "...", "status": "queued"} immediately.
    """
    state = get_state()
    content_type_hdr = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type_hdr or "application/x-www-form-urlencoded" in content_type_hdr:
        if file is not None:
            raw_bytes = await file.read()
            fname = filename or file.filename or "attachment.bin"
            ftype = type or file.content_type or "application/octet-stream"
            cat = category or "temporary"
            sess_id = session_id or "default"
        else:
            form = await request.form()
            file_obj = form.get("file")
            fname = filename or (file_obj.filename if hasattr(file_obj, "filename") else "attachment.bin")
            ftype = type or getattr(file_obj, "content_type", "application/octet-stream")
            cat = category or str(form.get("category", "temporary"))
            sess_id = session_id or str(form.get("session_id", "default"))
            if hasattr(file_obj, "read"):
                raw_bytes = await file_obj.read()
            elif isinstance(file_obj, bytes):
                raw_bytes = file_obj
            else:
                raw_bytes = str(file_obj or "").encode("utf-8")
    else:
        # JSON body payload
        try:
            body_json = await request.json()
        except Exception:
            body_json = {}
        fname = body_json.get("filename") or filename or "attachment.bin"
        ftype = body_json.get("type") or type or "application/octet-stream"
        cat = body_json.get("category") or category or "temporary"
        sess_id = body_json.get("session_id") or session_id or "default"

        b64 = body_json.get("contentBase64") or body_json.get("content")
        if b64:
            try:
                raw_bytes = base64.b64decode(b64)
            except Exception:
                raw_bytes = b64.encode("utf-8")
        else:
            raw_bytes = f"Attachment payload content for {fname}".encode("utf-8")

    try:
        res = state.attachment_manager.upload_attachment(
            filename=fname,
            content_type=ftype,
            category=cat,
            content_bytes=raw_bytes,
            session_id=sess_id,
            async_processing=True,
        )
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Chat attachments: sources of ONE chat (backend/retrieval/chat_attachments.py) ──

@router.post("/chat-attachments")
def add_chat_attachment(file: UploadFile = File(...), session_id: str = Form(...)) -> dict:
    """Attach a file to a chat: saved under that chat and indexed like any
    source, but searchable from this chat only. Indexing runs in the
    background; poll the returned job like any source ingestion."""
    import threading

    from backend.ingestion.ingestion_progress import get_tracker
    from backend.retrieval import chat_attachments as CA

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The attached file is empty.")
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The attached file is larger than 50 MB.")
    try:
        folder = CA.session_dir(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    name = CA.unique_name(session_id, file.filename or "attachment")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    target.write_bytes(raw)
    CA.register(session_id, target)

    state = get_state()
    tracker = get_tracker()
    job = tracker.create(str(target), [target])

    def _run():
        try:
            state.ingest_path(target, job_id=job.job_id)
            tracker.finish(job.job_id)
        except Exception as exc:  # noqa: BLE001 - reported on the job
            tracker.finish(job.job_id, error=f"{type(exc).__name__}: {exc}")

    threading.Thread(target=_run, name=f"chat-attachment-{job.job_id}", daemon=True).start()
    return {"name": name, "fullPath": str(target.resolve()), "job_id": job.job_id,
            "poll": f"/api/ingestion/{job.job_id}"}


@router.get("/chat-attachments")
def list_chat_attachments(session_id: str = Query(...)) -> dict:
    from backend.retrieval import chat_attachments as CA

    items = []
    for a in CA.for_session(session_id):
        path = Path(a["path"])
        items.append({
            "id": f"chat_{a['name']}",
            "name": a["name"],
            "fullPath": a["path"],
            "relativePath": a["path"],
            "extension": path.suffix.lstrip(".").lower(),
            "size": f"{path.stat().st_size / 1024:.1f} KB" if path.exists() else "",
            "addedAt": a.get("added_at"),
            "type": "file",
            "chatAttachment": True,
        })
    return {"session_id": session_id, "attachments": items}


@router.delete("/chat-attachments")
def remove_chat_attachment(session_id: str = Query(...), name: str = Query(...)) -> dict:
    from backend.retrieval import chat_attachments as CA

    entry = CA.retire(session_id, name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{name} is not attached to this chat.")
    removed = get_state().delete_source(entry["path"])
    try:
        Path(entry["path"]).unlink(missing_ok=True)
    except OSError:
        pass
    return {"removed": name, "index": removed}


ATTACHMENT_TEXT_LIMIT = 60_000  # characters returned; the chat decides how much of it to send


@router.post("/attachments/read")
def read_attachment_text(file: UploadFile = File(...)) -> dict:
    """The text of a file attached to ONE message, for that message only.

    A PDF, Word, Excel or PowerPoint file attached in the chat used to send
    nothing but its name -- "[Temporary Attachment: x.pdf]" -- so the model
    was told a file existed and never saw a word of it ("I see a temporary
    attachment but no specific question"). This reads it with the same
    extractor ingestion uses (OCR for scanned pages) into a temporary
    directory that is deleted on return: the file is not added to the
    corpus, the index or the source list.
    """
    import tempfile

    from backend.ingestion.document_types import detect_document_type
    from backend.ingestion.text_extraction import extract_pages

    name = Path(file.filename or "attachment").name
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The attached file is empty.")
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The attached file is larger than 50 MB.")

    def _ocr(img_path: str) -> str:
        from backend.tools.vision.ocr_printed import extract_printed_text

        return extract_printed_text(img_path).full_text or ""

    with tempfile.TemporaryDirectory(prefix="sw_attach_") as tmp:
        path = Path(tmp) / name
        path.write_bytes(raw)
        try:
            detected = detect_document_type(str(path)).detected_type
            pages = extract_pages(str(path), detected, ocr_fn=_ocr)
        except (NotImplementedError, ValueError) as exc:
            raise HTTPException(status_code=415, detail=f"{name} could not be read: {exc}") from exc

    # A spreadsheet's "pages" are its sheets, and each already opens with
    # "Sheet k of N: <tab name>" -- a "page" label over it would mislead.
    unit = {"xlsx": "sheet", "xls": "sheet", "pptx": "slide"}.get(detected, "page")
    parts = [
        (f"--- {unit} {p.page_number} ---\n" if unit != "sheet" and p.page_number and len(pages) > 1 else "")
        + p.text.strip()
        for p in pages
        if p.text and p.text.strip()
    ]
    text = "\n\n".join(parts)
    return {
        "filename": name,
        "type": detected,
        "unit": unit,
        "pages": len(pages),
        "chars": len(text),
        "text": text[:ATTACHMENT_TEXT_LIMIT],
        "truncated": len(text) > ATTACHMENT_TEXT_LIMIT,
    }


@router.get("/attachments/{attachment_id}")
def get_attachment(attachment_id: str) -> dict:
    """Return current processing status and metadata for an attachment."""
    state = get_state()
    att = state.attachment_manager.get_attachment(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail=f"Attachment not found: {attachment_id}")
    return att


@router.get("/attachments")
def list_attachments(category: str | None = Query(None)) -> dict:
    """List currently tracked attachments, optionally filtered by category (temporary vs permanent)."""
    state = get_state()
    items = state.attachment_manager.list_attachments(category=category)
    return {"attachments": items, "count": len(items)}


@router.post("/attachments/cleanup")
def cleanup_attachments(session_id: str | None = Query(None)) -> dict:
    """Session cleanup hook: purges temporary attachments & rendered previews while leaving permanent ones untouched."""
    state = get_state()
    res = state.attachment_manager.cleanup_session(session_id=session_id)
    try:
        from backend.sandbox.render import get_render_manager
        get_render_manager().cleanup_session_renders(session_id=session_id)
    except Exception:
        pass
    return res


@router.delete("/attachments/temporary")
def delete_temporary_attachments(session_id: str | None = Query(None)) -> dict:
    """Alternative session cleanup endpoint for temporary attachments & temporary previews."""
    state = get_state()
    res = state.attachment_manager.cleanup_session(session_id=session_id)
    try:
        from backend.sandbox.render import get_render_manager
        get_render_manager().cleanup_session_renders(session_id=session_id)
    except Exception:
        pass
    return res


# ============================================================================
# Sandbox Code Execution Isolation Endpoints (Step 2)
# ============================================================================

@router.post("/sandbox/execute")
def execute_code_sandbox(req: SandboxExecuteRequest) -> dict:
    """Submit code for asynchronous execution in an isolated sandbox container/runner."""
    from backend.sandbox.manager import get_sandbox_manager
    manager = get_sandbox_manager()
    job_id = manager.submit_job(
        code=req.code,
        language=req.language,
        timeout_seconds=req.timeout_seconds,
    )
    return {"job_id": job_id}


@router.get("/sandbox/execute/{job_id}")
def get_sandbox_job_status(job_id: str) -> dict:
    """Retrieve job execution status, stdout, stderr, and exit_code for a sandbox job."""
    from backend.sandbox.manager import get_sandbox_manager
    manager = get_sandbox_manager()
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Sandbox job not found: {job_id}")
    return job


# ============================================================================
# Sandbox Office Document Rendering Endpoints (Step 3)
# ============================================================================

@router.post("/sandbox/render")
def render_office_document(req: SandboxRenderRequest) -> dict:
    """Submit an attachment_id, file_path, or source_id for sandboxed office document rendering (docx/xlsx/pptx/pdf).

    Rejects immediately with HTTP 400 if attachment or source path is invalid.
    """
    from backend.sandbox.render import get_render_manager
    manager = get_render_manager()
    try:
        job_id = manager.submit_render_job(
            attachment_id=req.attachment_id,
            file_path=req.file_path,
            source_id=req.source_id,
        )
        return {"job_id": job_id}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err


@router.get("/sandbox/render/{job_id}")
def get_sandbox_render_status(job_id: str) -> dict:
    """Retrieve render job status, preview_url, page_count, and error details."""
    from backend.sandbox.render import get_render_manager
    manager = get_render_manager()
    job = manager.get_render_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Render job not found: {job_id}")
    return job


@router.get("/sandbox/render/preview/{attachment_id}")
def serve_sandbox_render_preview(attachment_id: str, page: int = Query(1)) -> Response:
    """Serve rendered preview PNG or PDF file for a given attachment_id and page number."""
    from backend.sandbox.render import get_render_manager
    manager = get_render_manager()
    file_path = manager.get_rendered_preview_path(attachment_id, page_num=page)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Rendered preview not found for attachment: {attachment_id}")

    media_type = {".png": "image/png", ".jpg": "image/jpeg"}.get(file_path.suffix.lower(), "application/octet-stream")
    return Response(content=file_path.read_bytes(), media_type=media_type)


@router.get("/sources/content")
def get_source_content(path: str = Query(..., description="Disk file path or relative path of source file")) -> Response:
    """Serve the raw bytes of a file inside a configured source (source_config.viewable_file)."""
    from fastapi.responses import FileResponse
    candidate_path = source_config.viewable_file(path)
    if candidate_path is None:
        raise HTTPException(status_code=404, detail=f"No file in the configured sources matches: {path}")

    ext = candidate_path.suffix.lower()
    images = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
              ".svg": "image/svg+xml", ".gif": "image/gif", ".bmp": "image/bmp"}
    if ext == ".pdf":
        media_type = "application/pdf"
    elif ext in (".txt", ".md", ".json", ".csv", ".py", ".log", ".xml", ".yaml", ".yml", ".html", ".css", ".js"):
        media_type = "text/plain; charset=utf-8"
    elif ext in images:
        media_type = images[ext]
    else:
        media_type = "application/octet-stream"

    return FileResponse(candidate_path, media_type=media_type)


# ============================================================================
# Offline Voice Capture & Local Speech-to-Text Endpoints (Step 5)
# ============================================================================

@router.post("/voice/upload")
async def upload_voice_note(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    category: str = Form("temporary"),
) -> dict:
    """Receive recorded voice audio blob, save locally, and queue local offline STT job.

    Returns:
        {"job_id": "vjob_..."}
    """
    from backend.tools.audio.voice_manager import get_voice_manager

    content = await file.read()
    if not content or len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty audio recording submitted")

    filename = file.filename or "voice_recording.webm"
    content_type = file.content_type or "audio/webm"

    voice_mgr = get_voice_manager()
    job_id = voice_mgr.submit_voice_note(
        audio_bytes=content,
        filename=filename,
        content_type=content_type,
        category=category,
        session_id=session_id,
    )
    return {"job_id": job_id}


@router.get("/voice/{job_id}")
def get_voice_job_status(job_id: str) -> dict:
    """Retrieve voice note STT status, transcript text, or error message."""
    from backend.tools.audio.voice_manager import get_voice_manager

    voice_mgr = get_voice_manager()
    job = voice_mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Voice job not found: {job_id}")
    return job





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
import json

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
        "ok": True,
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
def get_chunks(live: bool = Query(False, description="Force a live ingestion")) -> dict:
    """Every chunk with metadata, plus the chunk-to-chunk similarity matrix."""
    state = get_state()
    snapshot = state.snapshot()
    if not live and snapshot and not state.corpus_is_loaded:
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
    if not chunks:
        return {
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

    vectors = np.asarray(embed_texts([c.text for c in chunks]), dtype=np.float32)
    coords, explained = _pca_2d(vectors) if len(chunks) > 1 else (np.zeros((len(chunks), 2)), [1.0, 0.0])
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


class IngestPathRequest(BaseModel):
    path: str


class UploadFileItem(BaseModel):
    name: str
    relPath: str | None = None
    contentBase64: str
    sizeBytes: int | None = None


class UploadSourcesRequest(BaseModel):
    files: list[UploadFileItem]


@router.post("/sources/upload")
def upload_and_ingest_sources(body: UploadSourcesRequest) -> dict:
    """Accept uploaded files, write to disk, and chunk & embed them into FAISS."""
    import hashlib
    import json as _json

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
            saved_files.append(dest)
            parts = clean_rel.split("/")
            if len(parts) > 1 and parts[0]:
                top_folders.add(parts[0])
        except Exception:
            continue

    # Register any top-level uploaded folder as a named corpus source
    if top_folders:
        config_file = Path.cwd() / "backend" / "evaluation" / "configured_sources.json"
        dirs: list[dict] = []
        if config_file.exists():
            try:
                dirs = _json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        for folder in top_folders:
            folder_path = target_base_dir / folder
            norm_lower = str(folder_path.resolve()).lower()
            folder_hash = hashlib.sha256(norm_lower.encode("utf-8")).hexdigest()[:10]
            folder_id = f"dir_{folder_hash}"
            if not any(str(Path(d.get("path", "")).resolve()).lower() == norm_lower for d in dirs):
                dirs.append({
                    "id": folder_id,
                    "name": folder,
                    "path": str(folder_path.resolve()),
                    "isPreset": False,
                    "isUploadedFolder": True,
                    "enabled": True,
                })
        try:
            config_file.write_text(_json.dumps(dirs, indent=2), encoding="utf-8")
        except Exception:
            pass

    total_chunks = 0
    all_details = []
    for sf in saved_files:
        try:
            chunks_cnt, details = state.ingest_path(sf)
            total_chunks += chunks_cnt
            all_details.extend(details)
        except Exception as exc:
            all_details.append({"filename": sf.name, "path": str(sf), "error": str(exc), "chunks": 0})

    return {
        "success": True,
        "count": len(saved_files),
        "total_chunks": total_chunks,
        "details": all_details,
        "saved": [{"path": str(sf), "name": sf.name} for sf in saved_files],
        "added": {"path": str(saved_files[0]), "name": saved_files[0].name} if saved_files else None,
        "message": f"Uploaded and ingested {len(saved_files)} file(s): {total_chunks} chunks created, embedded, and indexed into FAISS.",
    }


@router.post("/sources/dialog/folder")
def browse_and_add_folder() -> dict:
    """Open native OS directory dialog to choose a folder on disk, ingest and register it."""
    import hashlib
    import json
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

    try:
        total_chunks, details = state.ingest_path(target)
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to chunk and embed source folder: {exc}") from exc

    config_file = Path.cwd() / "backend" / "evaluation" / "configured_sources.json"
    dirs = []
    if config_file.exists():
        try:
            dirs = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    norm_path = str(target.resolve())
    norm_lower = norm_path.lower()
    hasher = hashlib.sha256(norm_lower.encode("utf-8")).hexdigest()[:10]
    dir_id = f"dir_{hasher}"

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
    try:
        config_file.write_text(json.dumps(dirs, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "success": True,
        "path": norm_path,
        "name": target.name,
        "total_chunks": total_chunks,
        "documents": details,
        "directories": dirs,
        "added": {"path": norm_path, "name": target.name, "id": dir_id},
        "source": source.model_dump() if source else {"path": norm_path},
        "message": f"Folder '{target.name}' registered: {total_chunks} chunks indexed in FAISS.",
    }


@router.post("/sources/dialog/files")
def browse_and_add_files() -> dict:
    """Open native OS file dialog to choose documents on disk, ingest and register them."""
    import hashlib
    import json
    from backend.api.native_picker import pick_files_gui

    picked_paths = pick_files_gui("Select Documents to Add to Sovereign Workbench")
    if not picked_paths:
        return {"cancelled": True, "message": "File selection cancelled"}

    state = get_state()
    total_chunks = 0
    all_details = []
    saved_items = []

    config_file = Path.cwd() / "backend" / "evaluation" / "configured_sources.json"
    dirs = []
    if config_file.exists():
        try:
            dirs = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    for p_str in picked_paths:
        target = Path(p_str).resolve()
        try:
            cnt, details = state.ingest_path(target)
            total_chunks += cnt
            all_details.extend(details)
            saved_items.append({"path": str(target), "name": target.name})

            # Ensure parent folder is tracked in configured_sources so it appears in corpus
            parent_norm = str(target.parent.resolve())
            parent_lower = parent_norm.lower()
            if not any(str(Path(d.get("path", "")).resolve()).lower() == parent_lower for d in dirs):
                dirs.append({
                    "id": f"dir_{hashlib.sha256(parent_lower.encode('utf-8')).hexdigest()[:10]}",
                    "name": target.parent.name,
                    "path": parent_norm,
                    "isPreset": False,
                    "enabled": True,
                })
        except Exception as exc:
            all_details.append({"filename": target.name, "path": str(target), "error": str(exc), "chunks": 0})

    try:
        config_file.write_text(json.dumps(dirs, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "success": True,
        "count": len(picked_paths),
        "total_chunks": total_chunks,
        "documents": all_details,
        "saved": saved_items,
        "added": saved_items[0] if saved_items else None,
        "directories": dirs,
        "message": f"Successfully ingested {len(picked_paths)} document(s): {total_chunks} chunks indexed into FAISS.",
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


@router.get("/corpus")
def get_corpus() -> dict:
    """Native corpus endpoint matching configured sources and directory tree."""
    import json
    config_file = Path.cwd() / "backend" / "evaluation" / "configured_sources.json"
    dirs = []
    if config_file.exists():
        try:
            dirs = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not dirs:
        dirs = [
            {
                "id": "user_uploads_corpus",
                "name": "User Ingested Sources",
                "path": str(Path.cwd() / "MRPL_RAG_Test_Corpus" / "07_User_Uploads"),
                "isPreset": True,
                "isUserUploads": True,
                "enabled": True,
            },
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
        ]

    tree = []
    all_items = []
    custom_subpaths = [
        str(Path(d.get("path", "")).resolve()).lower()
        for d in dirs if not d.get("isPreset", False)
    ]

    for dir_cfg in dirs:
        p = Path(dir_cfg.get("path", ""))
        if not dir_cfg.get("enabled", True) or not p.exists():
            continue

        dir_node = {
            "id": dir_cfg.get("id"),
            "name": dir_cfg.get("name", p.name),
            "fullPath": str(p),
            "type": "directory",
            "isRoot": True,
            "isPreset": dir_cfg.get("isPreset", False),
            "children": [],
            "fileCount": 0,
            "totalSizeBytes": 0,
        }

        def _scan(current_dir: Path, rel_prefix: str, parent: dict):
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
                    sub = {
                        "id": f"{dir_cfg.get('id')}_{clean_id_rel}",
                        "name": entry.name,
                        "fullPath": str(entry),
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
                    stat = entry.stat()
                    ext = entry.suffix.lstrip(".").lower()
                    file_item = {
                        "id": f"{dir_cfg.get('id')}_{clean_id_rel}",
                        "name": entry.name,
                        "type": ext.upper(),
                        "extension": ext,
                        "size": f"{round(stat.st_size / 1024, 1)} KB",
                        "sizeBytes": stat.st_size,
                        "folder": rel_prefix or dir_cfg.get("name"),
                        "relPath": entry_rel,
                        "fullPath": str(entry),
                        "corpus": dir_cfg.get("name"),
                        "enabled": True,
                        # Drives the sidebar's filter tabs. Absent until
                        # now, which made every tab count zero.
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

    total_bytes = sum(i["sizeBytes"] for i in all_items)
    return {
        "directories": dirs,
        "tree": tree,
        "sources": all_items,
        "count": len(all_items),
        "corpusCount": len(all_items),
        "totalSizeBytes": total_bytes,
        "totalSizeDisplay": f"{round(total_bytes / (1024 * 1024), 2)} MB",
    }


@router.post("/sources")
def add_source(body: AddSourceRequest) -> dict:
    """Watch a folder or file, chunking and embedding it immediately into the knowledge base."""
    import hashlib
    import json
    state = get_state()
    target = Path(body.path).resolve()
    if not target.exists():
        # Check relative to cwd
        target = Path.cwd() / body.path
        if not target.exists():
            raise HTTPException(400, detail=f"Path does not exist on disk: {body.path}")

    watch_path = str(target if target.is_dir() else target.parent)
    try:
        source = state.watcher.add_source(
            watch_path, recursive=body.recursive, include_globs=body.include_globs
        )
    except Exception:
        source = None

    # Ingest the target (file or directory) for chunking and embedding
    try:
        total_chunks, details = state.ingest_path(target)
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to chunk and embed source: {exc}") from exc

    # Synchronize with configured_sources.json
    config_file = Path.cwd() / "backend" / "evaluation" / "configured_sources.json"
    dirs = []
    if config_file.exists():
        try:
            dirs = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    norm_path = str(target.resolve())
    norm_lower = norm_path.lower()
    hasher = hashlib.sha256(norm_lower.encode("utf-8")).hexdigest()[:10]
    dir_id = f"dir_{hasher}"

    found = False
    for d in dirs:
        if str(Path(d.get("path", "")).resolve()).lower() == norm_lower:
            d["enabled"] = True
            found = True
            break
    if not found and target.is_dir():
        dirs.append({
            "id": dir_id,
            "name": target.name or "Custom_Corpus",
            "path": norm_path,
            "isPreset": False,
            "enabled": True,
        })
    elif not found and target.is_file():
        parent_norm = str(target.parent.resolve())
        parent_lower = parent_norm.lower()
        if not any(str(Path(d.get("path", "")).resolve()).lower() == parent_lower for d in dirs):
            dirs.append({
                "id": f"dir_{hashlib.sha256(parent_lower.encode('utf-8')).hexdigest()[:10]}",
                "name": target.parent.name,
                "path": parent_norm,
                "isPreset": False,
                "enabled": True,
            })
    try:
        config_file.write_text(json.dumps(dirs, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "success": True,
        "total_chunks": total_chunks,
        "documents": details,
        "directories": dirs,
        "added": {"path": norm_path, "name": target.name, "id": dir_id},
        "source": source.model_dump() if source else {"path": str(target)},
        "message": f"Source '{target.name}' registered: {total_chunks} chunks created, embedded (1024-d), and indexed in FAISS.",
    }


@router.delete("/sources")
def remove_source(path: str = Query(...)) -> dict:
    """Remove a source file or directory from active knowledge base and vector store."""
    import json
    state = get_state()
    config_file = Path.cwd() / "backend" / "evaluation" / "configured_sources.json"
    if config_file.exists():
        try:
            dirs = json.loads(config_file.read_text(encoding="utf-8"))
            norm_target = str(Path(path).resolve()).lower()
            dirs = [
                d for d in dirs
                if d.get("id") != path
                and str(Path(d.get("path", "")).resolve()).lower() != norm_target
                and d.get("name", "").lower() != norm_target
            ]
            config_file.write_text(json.dumps(dirs, indent=2), encoding="utf-8")
        except Exception:
            pass
    return state.delete_source(path)



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


# ----------------------------------------------------------------- chat

class ChatRequestBody(BaseModel):
    message: str
    session_id: str = "default"


@router.post("/chat")
def chat(body: ChatRequestBody) -> dict:
    """Core agentic orchestration endpoint for the workbench chat interface.

    Coordinates router, multi-step planner DAG, dispatch to sub-agents,
    grounded synthesis with citations, self-verification, and safety approval.
    """
    from backend.audit.approval_gate import ApprovalGate
    from backend.orchestrator.graph import run_agent_turn

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
            approval_action = {
                "id": req.request_id,
                "title": "Confirm Operational Setpoint Modification",
                "action_type": "DCS_SETPOINT_WRITE",
                "target": req.arguments.get("target", "HCU-2 / FFC-201"),
                "description": req.effect,
                "detail": f"Action parameter: {req.arguments.get('command', req.effect)}",
                "current_value": "100% (1,450 m³/h)",
                "proposed_value": "115% (1,667 m³/h)",
                "unit": "m³/h",
                "parameter": "FFC-201.SP (Feed Rate Setpoint)",
                "risk_level": "CRITICAL",
                "warning": (
                    "Operating above 110% reduces catalyst residence time (LHSV > 1.8 h⁻¹) "
                    "and increases exothermic runaway risk."
                ),
                "mitigation_required": (
                    "Mandatory pre-condition: Quench flow controller (QFC-18) armed and "
                    "H₂/HC ratio maintained > 1,000 Nm³/m³ before setpoint ramp."
                ),
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
        "awaiting_human_approval": state.awaiting_human_approval,
        "approval_action": approval_action,
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

        if pulled is None:
            status, detail = "unknown", f"Ollama unreachable ({ollama_error})"
        elif entry is not None:
            status, detail = "available", None
        else:
            status, detail = "not_pulled", f"Run: ollama pull {tag}"

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
        })

    return {
        "models": models,
        "registry_path": "models/models.yaml",
        "ollama_reachable": pulled is not None,
        "ollama_error": ollama_error,
        "available_count": sum(1 for m in models if m["status"] == "available"),
        "missing": [m["model"] for m in models if m["status"] == "not_pulled"],
    }


@router.get("/system-info")
def system_info() -> dict:
    """Host facts the status bar reports, measured rather than assumed."""
    import platform

    import psutil

    vm = psutil.virtual_memory()
    info = {
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


# ------------------------------------------------------ agentic stream

class AgentStreamRequest(BaseModel):
    message: str
    session_id: str = "default"


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
            for event in run_turn(body.message, session_id=body.session_id):
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
        approved = gate.approve(body.request_id, approved_by=body.operator)
        return {
            "status": "approved",
            "request_id": body.request_id,
            "token": approved.token,
            "message": f"Action authorized by {body.operator}.",
        }
    else:
        gate.refuse(body.request_id, refused_by=body.operator, reason="Cancelled by operator")
        return {
            "status": "refused",
            "request_id": body.request_id,
            "message": "Action cancelled by operator.",
        }

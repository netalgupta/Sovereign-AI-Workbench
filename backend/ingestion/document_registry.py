"""Remember WHERE each source document lives. Never copy it.

An earlier version of this module copied every ingested file into a
content-addressed store. That was wrong: the user already has the file,
and a refinery's document set is gigabytes of PDFs and scans. Copying
doubles their disk for no benefit — the bytes are already on the machine,
at a path the user chose.

So this registry records the PATH plus enough identity to know whether
that path still holds the same document, and everything downstream
(page previews, "open the source", extracting a figure) reads the
original file in place, on demand.

WHAT IDENTITY MEANS HERE, and why it is not just the path. A path is not
a stable identifier: files get moved, renamed, edited, and replaced by
next year's revision under the same name. A content hash is a stable
identifier but is expensive to recompute on a 500-page PDF every time
someone asks a question. So both are kept, and they answer different
questions:

  * size + mtime — a cheap check, correct almost always, used on every
    access to decide whether anything might have changed;
  * sha256 — computed at registration and only recomputed when the cheap
    check says something moved, used to tell "edited" apart from
    "touched" and to recognise the same document arriving under a new
    name.

WHY STATUS IS EXPLICIT RATHER THAN AN EXCEPTION. Referencing files the
system does not own means they can vanish, and that is normal operation,
not an error condition: a user moves a folder, a share unmounts, someone
edits an SOP after it was indexed. Each of those needs a DIFFERENT thing
said to the user — "the file moved", "the file changed since it was
indexed, this citation may no longer be accurate" — so resolve() returns
a status rather than raising, and the caller can say the true thing.
"""

import hashlib
import json
from datetime import date
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

DEFAULT_REGISTRY_DIR = Path("document_registry")
_HASH_CHUNK_BYTES = 1024 * 1024  # stream; never load a large PDF into memory to hash it


class DocumentStatus(str, Enum):
    AVAILABLE = "available"  # present, and unchanged since indexing
    MODIFIED = "modified"  # present, but the bytes differ from what was indexed
    MISSING = "missing"  # the recorded path no longer holds a file
    UNKNOWN = "unknown"  # never registered


class DocumentRef(BaseModel):
    document_id: str  # sha256 at registration time, hex
    source_path: str  # absolute path on the user's machine
    original_name: str
    byte_size: int
    modified_time: float  # st_mtime at registration
    page_count: int | None = None  # for paginated formats; None otherwise
    registered_on: str
    # Other paths the same content has been seen at. A document copied to
    # a second folder is one document in two places; losing the alternates
    # means losing the ability to fall back when one path breaks.
    known_paths: list[str] = []


class ResolvedDocument(BaseModel):
    status: DocumentStatus
    ref: DocumentRef | None = None
    path: Path | None = None
    detail: str | None = None

    model_config = {"arbitrary_types_allowed": True}


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_HASH_CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def _page_count(path: Path) -> int | None:
    """Page count for paginated formats, so a UI can show "page 7 of 512"
    without opening the document first. None for formats that genuinely
    have no pages — a DOCX is a flow, and its page count depends on the
    renderer, so reporting one would be a guess."""
    if path.suffix.lower() != ".pdf":
        return None
    try:
        import fitz

        with fitz.open(path) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001 — a page count is a nicety, never a reason to fail ingestion
        return None


class DocumentRegistry:
    def __init__(self, root: str | Path = DEFAULT_REGISTRY_DIR):
        self.root = Path(root)

    def _dir_for(self, document_id: str) -> Path:
        return self.root / document_id[:2]

    def _meta_path(self, document_id: str) -> Path:
        return self._dir_for(document_id) / f"{document_id}.json"

    def get(self, document_id: str) -> DocumentRef | None:
        path = self._meta_path(document_id)
        if not path.exists():
            return None
        return DocumentRef.model_validate_json(path.read_text(encoding="utf-8"))

    def register(self, file_path: str | Path) -> DocumentRef:
        """Record where a document lives. Copies nothing."""
        source = Path(file_path).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Cannot register a document that does not exist: {source}")

        document_id = hash_file(source)
        stat = source.stat()

        ref = self.get(document_id)
        if ref is None:
            ref = DocumentRef(
                document_id=document_id,
                source_path=str(source),
                original_name=source.name,
                byte_size=stat.st_size,
                modified_time=stat.st_mtime,
                page_count=_page_count(source),
                registered_on=date.today().isoformat(),
                known_paths=[str(source)],
            )
        else:
            # Same content, new location. Point at the path we were just
            # handed — it is the one the caller knows is live — but keep
            # the others as fallbacks.
            if str(source) not in ref.known_paths:
                ref.known_paths.append(str(source))
            ref.source_path = str(source)
            ref.modified_time = stat.st_mtime

        self._write(ref)
        return ref

    def resolve(self, document_id: str) -> ResolvedDocument:
        """Where is this document now, and is it still what we indexed?

        Tries the recorded path first, then any other path the same
        content has been seen at, so a document copied to two folders
        survives one of them going away.
        """
        ref = self.get(document_id)
        if ref is None:
            return ResolvedDocument(status=DocumentStatus.UNKNOWN, detail="not registered")

        for candidate in [ref.source_path, *ref.known_paths]:
            path = Path(candidate)
            if not path.exists():
                continue

            stat = path.stat()
            # Cheap check first. Only if size or mtime moved do we pay
            # for a hash — on a 500-page PDF that difference is the
            # difference between instant and seconds.
            if stat.st_size == ref.byte_size and stat.st_mtime == ref.modified_time:
                return ResolvedDocument(status=DocumentStatus.AVAILABLE, ref=ref, path=path)

            if hash_file(path) == document_id:
                # Touched but not edited (a copy, a restore, a sync).
                # Same document; update the cheap fingerprint so the next
                # access is fast again.
                ref.modified_time = stat.st_mtime
                ref.byte_size = stat.st_size
                self._write(ref)
                return ResolvedDocument(status=DocumentStatus.AVAILABLE, ref=ref, path=path)

            return ResolvedDocument(
                status=DocumentStatus.MODIFIED,
                ref=ref,
                path=path,
                detail=(
                    f"{path.name} has changed since it was indexed. Anything quoted from it "
                    "may no longer match the current file; re-ingest to update."
                ),
            )

        return ResolvedDocument(
            status=DocumentStatus.MISSING,
            ref=ref,
            detail=(
                f"{ref.original_name} is no longer at {ref.source_path}. It was moved, renamed "
                "or deleted after indexing — re-add it to restore previews and citations."
            ),
        )

    def find_by_name(self, name: str) -> list[DocumentRef]:
        """All registered documents matching a file name.

        Chunk metadata records source_document as a NAME, not an id, so
        this is the bridge from a retrieved chunk back to the file it
        came from. Returns a list because two different documents can
        genuinely share a name.
        """
        return [
            ref for ref in self.all_refs()
            if ref.original_name == name or name in ref.known_paths
        ]

    def all_refs(self) -> list[DocumentRef]:
        if not self.root.exists():
            return []
        return [
            DocumentRef.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self.root.glob("*/*.json"))
        ]

    def _write(self, ref: DocumentRef) -> None:
        self._dir_for(ref.document_id).mkdir(parents=True, exist_ok=True)
        self._meta_path(ref.document_id).write_text(
            ref.model_dump_json(indent=2), encoding="utf-8"
        )

"""Durable store for images extracted from documents, plus everything
the pipeline understands about each one.

WHY THIS EXISTS. Until now an embedded image was rendered to a temp
file, described, and deleted. That is enough to get description text
into a chunk, and not enough for anything else: a user who asks "show me
that P&ID" cannot be shown it, because the pixels are gone and nothing
recorded which document or page they came from. An answer that says
"see the schematic on page 3" without being able to produce the
schematic is a worse answer than one that shows it.

So each image is stored once, permanently, with:

  * the pixels, content-addressed by SHA-256;
  * every PLACE it occurs (document, page, position on that page) — a
    letterhead logo appearing in 40 documents is ONE stored image with
    40 occurrences, not 40 copies;
  * its OCR text — what CARD 05 read off it, which is the text that
    actually enters the retrieval corpus for that image;
  * its vision-model description — what CARD 13 thinks it depicts, which
    is ALWAYS an estimate (see chart_understanding.py) and is stored
    with that flag attached so no downstream caller can lose track of it.

CONTENT-ADDRESSING IS LOAD-BEARING, not a tidiness preference. Real
corpora repeat images constantly — letterheads, standard safety
diagrams, the same equipment photo pasted into six reports. Keying on
content means describing each distinct image once (a vision call is
tens of seconds), and means "the same image" is a fact about the bytes
rather than a guess based on filename or position.

WHY A SIDECAR JSON PER IMAGE rather than one index file: ingestion is
incremental and can be interrupted. One shared index is a file every
writer must read-modify-write, which loses data on a crash and needs
locking to be safe concurrently. A file per image is atomic per image
and survives a half-finished run with exactly the images it finished.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel

DEFAULT_STORE_DIR = Path("image_store")


class ImageOccurrence(BaseModel):
    """One place this image appears. An image can occur many times."""

    source_document: str
    page_number: int | None
    # Position on the page in PDF points (x0, top, x1, bottom), when the
    # extractor knows it. None for formats with no page geometry (DOCX
    # has no coordinates — the image is in document flow, not at a
    # position), which is a real distinction rather than missing data.
    bbox: tuple[float, float, float, float] | None = None
    # Ordinal of this image within its page/document, so two images with
    # no bbox are still distinguishable and orderable.
    index_on_page: int = 0


class ImageRecord(BaseModel):
    image_id: str  # sha256 of the pixels, hex
    file_name: str  # relative to the store root
    content_type: str
    byte_size: int
    occurrences: list[ImageOccurrence]
    ocr_text: str | None = None
    description: str | None = None
    # Mirrors ChartVisualDescription.is_estimate. Stored explicitly, per
    # image, so a consumer reading a record straight off disk cannot
    # treat a vision-model reading as a verified fact — CLAUDE.md hard
    # constraint #3. Measured reason this matters: on charts with no
    # printed numbers at all, the model still emitted specific figures
    # and called them values "printed as text on the chart".
    description_is_estimate: bool = True


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ImageStore:
    """File-backed image store. Cheap to construct; does no I/O until used."""

    def __init__(self, root: str | Path = DEFAULT_STORE_DIR):
        self.root = Path(root)

    # Two-level fan-out on the first two hex characters keeps any single
    # directory from holding tens of thousands of entries, which some
    # filesystems handle badly and every file browser handles badly.
    def _dir_for(self, image_id: str) -> Path:
        return self.root / image_id[:2]

    def image_path(self, image_id: str, suffix: str = ".png") -> Path:
        return self._dir_for(image_id) / f"{image_id}{suffix}"

    def _meta_path(self, image_id: str) -> Path:
        return self._dir_for(image_id) / f"{image_id}.json"

    def get(self, image_id: str) -> ImageRecord | None:
        path = self._meta_path(image_id)
        if not path.exists():
            return None
        return ImageRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def read_bytes(self, image_id: str) -> bytes | None:
        record = self.get(image_id)
        if record is None:
            return None
        path = self.root / record.file_name
        return path.read_bytes() if path.exists() else None

    def add(
        self,
        data: bytes,
        occurrence: ImageOccurrence,
        content_type: str = "image/png",
        suffix: str = ".png",
    ) -> ImageRecord:
        """Store `data` if new, and record this occurrence of it.

        Returns the record either way. Calling this again for an image
        already stored does NOT rewrite the pixels and does NOT
        re-describe it — it appends the occurrence and returns the
        existing understanding, which is the whole point of keying on
        content: the second document containing the same letterhead
        costs a hash, not a vision call.
        """
        image_id = _hash_bytes(data)
        directory = self._dir_for(image_id)
        directory.mkdir(parents=True, exist_ok=True)

        image_path = self.image_path(image_id, suffix)
        if not image_path.exists():
            image_path.write_bytes(data)

        record = self.get(image_id)
        if record is None:
            record = ImageRecord(
                image_id=image_id,
                file_name=str(image_path.relative_to(self.root)).replace("\\", "/"),
                content_type=content_type,
                byte_size=len(data),
                occurrences=[occurrence],
            )
        elif not any(
            o.source_document == occurrence.source_document
            and o.page_number == occurrence.page_number
            and o.index_on_page == occurrence.index_on_page
            for o in record.occurrences
        ):
            # Same image, somewhere new. Re-ingesting the SAME document
            # must not keep appending duplicates, so the check is on the
            # full location, not just the document name.
            record.occurrences.append(occurrence)

        self._write(record)
        return record

    def attach_understanding(
        self,
        image_id: str,
        ocr_text: str | None = None,
        description: str | None = None,
        description_is_estimate: bool = True,
    ) -> ImageRecord | None:
        """Attach OCR text and/or a vision description to a stored image.

        Separate from add() because the two have very different costs:
        storing is a hash and a write, while OCR and a vision call are
        seconds to tens of seconds each. Keeping them apart lets a caller
        store everything cheaply first and decide what is worth
        describing, and lets a re-run skip images that already have an
        understanding.
        """
        record = self.get(image_id)
        if record is None:
            return None
        if ocr_text is not None:
            record.ocr_text = ocr_text
        if description is not None:
            record.description = description
            record.description_is_estimate = description_is_estimate
        self._write(record)
        return record

    def _write(self, record: ImageRecord) -> None:
        self._dir_for(record.image_id).mkdir(parents=True, exist_ok=True)
        self._meta_path(record.image_id).write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )

    def all_records(self) -> list[ImageRecord]:
        if not self.root.exists():
            return []
        return [
            ImageRecord.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self.root.glob("*/*.json"))
        ]


def render_image_block(record: ImageRecord, occurrence: ImageOccurrence) -> str:
    """The text that stands in for this image inside a chunk.

    This text is what gets embedded and BM25-indexed, so it is written as
    prose a question could plausibly match ("diagram", "figure", the OCR'd
    equipment tags, the described trend) rather than as a machine-readable
    blob. The image id is included so that a chunk retrieved later can be
    traced back to the actual pixels — that reference is the whole
    mechanism by which "show me that diagram" can be answered.

    The estimate warning is inline, in the indexed text itself, not only
    in metadata. If a downstream consumer renders chunk text and drops
    the metadata (a plain prompt, a log line, a copy-paste into a
    report), the caveat has to travel with the words or it is lost
    exactly where it matters most.
    """
    where = f"page {occurrence.page_number}" if occurrence.page_number else "this document"
    lines = [f"[Image {occurrence.index_on_page + 1} on {where} — ref image:{record.image_id[:12]}]"]

    if record.ocr_text and record.ocr_text.strip():
        lines.append(f"Text visible in the image: {record.ocr_text.strip()}")
    if record.description and record.description.strip():
        qualifier = (
            "vision-model estimate, not a measurement"
            if record.description_is_estimate
            else "extracted"
        )
        lines.append(f"Description of the image ({qualifier}): {record.description.strip()}")
    if len(lines) == 1:
        lines.append("No text or description could be extracted from this image.")
    return "\n".join(lines)

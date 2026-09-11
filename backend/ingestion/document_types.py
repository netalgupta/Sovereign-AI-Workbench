"""Document type detection — RAG_SPEC.md §2 step 1.

WHY BOTH EXTENSION AND MIME, RECONCILED, NOT MIME ALONE: RAG_SPEC.md
literally specifies "file extension + a MIME check (don't trust
extension alone)" — that phrasing means both signals are used together,
with MIME correcting a wrong/misleading extension, not "compute MIME and
discard the extension." Two concrete cases where MIME alone is wrong:

1. OOXML files (.docx, .xlsx) are zip containers under the hood. Some
   libmagic builds/versions can't fully parse the internal
   [Content_Types].xml and fall back to the generic "application/zip" —
   at that point MIME has become LESS informative than the extension,
   not more.
2. A plain CSV export and a plain TXT file are both byte-for-byte
   "text/plain" as far as content-sniffing is concerned — there is no
   MIME signature that distinguishes them. Only the extension can.

So: MIME wins when it's specific and confidently known (it catches a
genuinely mislabeled/renamed file, which the extension can never catch).
The extension wins only in the specific cases above, where MIME's answer
is provably too generic to be the "ground truth" RAG_SPEC.md wants.
"""

from pathlib import Path
from typing import Literal

import magic
from pydantic import BaseModel

DetectedType = Literal[
    "pdf", "docx", "txt", "csv", "xlsx", "xls", "email", "image", "audio", "unknown"
]

_EXTENSION_TO_TYPE: dict[str, DetectedType] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "txt",
    ".markdown": "txt",
    ".json": "txt",
    ".log": "txt",
    ".yaml": "txt",
    ".yml": "txt",
    ".xml": "txt",
    ".py": "txt",
    ".sql": "txt",
    ".html": "txt",
    ".htm": "txt",
    ".ini": "txt",
    ".env": "txt",
    ".conf": "txt",
    ".tsv": "csv",
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".eml": "email",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".ogg": "audio",
}

_MIME_TO_TYPE: dict[str, DetectedType] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "text/csv": "csv",
    "text/plain": "txt",
    "text/markdown": "txt",
    "text/x-markdown": "txt",
    "application/json": "txt",
    "text/xml": "txt",
    "application/xml": "txt",
    "text/x-python": "txt",
    "message/rfc822": "email",
    "image/png": "image",
    "image/jpeg": "image",
    "image/tiff": "image",
    "audio/x-wav": "audio",
    "audio/wav": "audio",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/ogg": "audio",
}

# MIME results too generic to trust over the extension hint — see the
# two concrete cases in the module docstring. "text/plain" is genuinely
# ambiguous between .txt and .csv (no byte signature distinguishes
# them), and "application/zip" / "application/octet-stream" are what a
# non-fully-parsing libmagic build reports for an OOXML file it couldn't
# look inside.
_AMBIGUOUS_MIME_TYPES = {"text/plain", "application/zip", "application/octet-stream"}


class DocumentTypeInfo(BaseModel):
    file_extension: str
    mime_type: str
    detected_type: DetectedType


def _reconcile(extension_guess: DetectedType, mime_guess: DetectedType, mime_type: str) -> DetectedType:
    if mime_type in _AMBIGUOUS_MIME_TYPES:
        return extension_guess if extension_guess != "unknown" else mime_guess
    if mime_guess != "unknown":
        return mime_guess
    return extension_guess


def detect_document_type(file_path: str) -> DocumentTypeInfo:
    """Detect a document's real type from BOTH its extension and its
    actual byte-content MIME signature, reconciling disagreements per
    the rules in this module's docstring.

    Raises:
        FileNotFoundError: if `file_path` doesn't exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found at {file_path}")

    extension = path.suffix.lower()
    extension_guess = _EXTENSION_TO_TYPE.get(extension, "unknown")

    mime_type = magic.from_file(str(path), mime=True)
    mime_guess = _MIME_TO_TYPE.get(mime_type, "unknown")

    return DocumentTypeInfo(
        file_extension=extension,
        mime_type=mime_type,
        detected_type=_reconcile(extension_guess, mime_guess, mime_type),
    )

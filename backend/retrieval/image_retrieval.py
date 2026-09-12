"""Answer "show me that image" — pick the RIGHT image and hand back the
actual pixels, not a description of them.

THE PROBLEM THIS SOLVES. Retrieval returns chunks. A chunk carries the
ids of every image on its page, and a page routinely holds several: a
P&ID, a trend chart and a letterhead can all sit on one page and all
end up attached to the same chunk. So "show me the schematic" cannot be
answered by returning the chunk's images — that returns three pictures
and makes the user find theirs. The request itself is the signal that
disambiguates, and using it is what turns a pile of attachments into an
answer.

HOW SELECTION WORKS. Each stored image has two independent kinds of
understanding (see image_store.py): OCR text — what is written IN it,
which for a P&ID is the equipment tags an engineer would actually type —
and a vision description of what it DEPICTS. Both are embedded together
and scored against the request with the same bge model used for chunk
retrieval, so "the hydrocracker schematic" matches a description while
"the diagram with V-204 on it" matches OCR text, without the caller
having to say which kind of question they are asking.

WHY NOT JUST REUSE THE CHUNK'S SCORE: the chunk was retrieved for its
prose. An image's relevance to the request is a different question from
its page's relevance, and a page can be exactly right while two of its
three images are irrelevant to what was asked.
"""

import numpy as np
from pydantic import BaseModel

from backend.ingestion.image_store import ImageRecord, ImageStore

# Below this cosine similarity, an image is not returned at all. The
# alternative — always returning the best-scoring image — means a
# question that referenced no image at all still produces a picture,
# which reads as an assertion that the picture is relevant. Refusing to
# attach anything is the honest answer to "there is no matching image
# here", and mirrors the same reasoning as the retrieval confidence gate
# in grounded_retrieval.py. Tuned conservatively: this threshold gates
# an ATTACHMENT, so a miss costs the user a follow-up question while a
# false positive puts a wrong diagram in front of an engineer.
# Same backend-dependence as the confidence gate, and the same history:
# lowered to 0.15 so schematics would match at all on hash vectors. With
# the real model that floor matches almost anything, which turns "show me
# the P&ID" into "here is some image" — and putting the wrong diagram in
# front of an engineer is worse than attaching none.
_MIN_SIMILARITY_BY_BACKEND = {
    "bge-large-en-v1.5": 0.35,
    "deterministic-hash": 0.15,
}

MIN_IMAGE_MATCH_SIMILARITY = 0.35


def min_image_match_similarity() -> float:
    """The match floor for whichever embedder is actually running."""
    from backend.ingestion.embeddings import active_backend

    return _MIN_SIMILARITY_BY_BACKEND.get(active_backend(), MIN_IMAGE_MATCH_SIMILARITY)


class ImageMatch(BaseModel):
    image_id: str
    score: float
    source_document: str
    page_number: int | None
    ocr_text: str | None
    description: str | None
    description_is_estimate: bool
    file_name: str

    @property
    def is_estimate(self) -> bool:
        return self.description_is_estimate


def _searchable_text(record: ImageRecord) -> str:
    """What an image is matched ON.

    Both understandings, plus where it came from. The source document
    name is included deliberately: users refer to images by their
    document ("the diagram in the incident report") at least as often as
    by content, and that phrasing would otherwise match nothing.
    """
    parts: list[str] = []
    if record.occurrences:
        occ = record.occurrences[0]
        parts.append(occ.source_document.replace("_", " ").replace("-", " "))
    if record.description:
        parts.append(record.description)
    if record.ocr_text:
        parts.append(record.ocr_text)
    return "\n".join(parts).strip()


def select_images_for_request(
    request: str,
    image_ids: list[str],
    store: ImageStore,
    top_k: int = 1,
    min_similarity: float | None = None,
) -> list[ImageMatch]:
    """Rank `image_ids` by how well each matches `request`.

    Returns at most `top_k`, and returns EMPTY rather than a weak best
    guess when nothing clears `min_similarity` — see that constant for
    why attaching the wrong diagram is worse than attaching none.

    Deduplicates ids before scoring: every chunk from a page carries
    that page's images, so a multi-chunk answer naturally arrives with
    the same id several times, and the same picture should not be
    offered twice.
    """
    from backend.ingestion.embeddings import embed_texts

    if min_similarity is None:
        min_similarity = min_image_match_similarity()

    unique_ids = list(dict.fromkeys(image_ids))
    records = [(i, store.get(i)) for i in unique_ids]
    candidates = [(i, r) for i, r in records if r is not None and _searchable_text(r)]
    if not candidates:
        return []

    texts = [_searchable_text(r) for _i, r in candidates]
    # One batched call: the query and every candidate together, so this
    # costs a single embedding round trip regardless of image count.
    vectors = np.asarray(embed_texts([request] + texts), dtype=np.float32)
    query_vector, candidate_vectors = vectors[0], vectors[1:]
    # bge vectors are L2-normalized, so a dot product IS cosine similarity.
    scores = candidate_vectors @ query_vector

    matches = []
    for (image_id, record), score in zip(candidates, scores):
        if float(score) < min_similarity:
            continue
        occurrence = record.occurrences[0] if record.occurrences else None
        matches.append(
            ImageMatch(
                image_id=image_id,
                score=round(float(score), 4),
                source_document=occurrence.source_document if occurrence else "",
                page_number=occurrence.page_number if occurrence else None,
                ocr_text=record.ocr_text,
                description=record.description,
                description_is_estimate=record.description_is_estimate,
                file_name=record.file_name,
            )
        )

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:top_k]


def images_referenced_by_chunks(chunks) -> list[str]:
    """Every image id attached to a set of retrieved chunks, in order.

    Accepts anything with `.metadata.image_ids` (an IngestedChunk) or a
    plain `.image_ids`, so it works on both the ingestion-side and
    retrieval-side chunk shapes without either having to know about the
    other.
    """
    ids: list[str] = []
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", None)
        found = getattr(metadata, "image_ids", None) if metadata else None
        if found is None:
            found = getattr(chunk, "image_ids", None)
        ids.extend(found or [])
    return list(dict.fromkeys(ids))


def resolve_image_bytes(match: ImageMatch, store: ImageStore) -> bytes | None:
    """The actual pixels for a match, ready to return to the user."""
    return store.read_bytes(match.image_id)

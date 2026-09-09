"""Chunking — RAG_SPEC.md §2 step 3.

Exact values, not "reasonable defaults": chunk size 512 tokens, overlap
64 tokens, counted via tiktoken's cl100k_base encoding. RAG_SPEC.md is
explicit that these must stay fixed — consistency across the corpus
matters for retrieval-quality comparisons, so an agent (or a developer)
picking its own chunk size later would quietly invalidate any prior
tuning of RAG_SPEC.md §3's 0.35 confidence threshold.

WHY REUSE langchain_text_splitters INSTEAD OF HAND-ROLLING THIS: recursive
splitting-with-overlap has real edge cases (overlap duplicating whole
sentences, off-by-one token counts, splitting mid-word) that are easy to
get subtly wrong. `langchain_text_splitters` is already a transitive
dependency of this project (LangGraph pulls it in), and its
`from_tiktoken_encoder` constructor IS "recursive character splitter,
sized by a named tiktoken encoding" — precisely RAG_SPEC.md's spec,
verbatim, not an approximation of it. Writing a new, less-tested chunker
to replace an already-correct one already in the dependency tree would
be the wrong kind of "simplification."
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
TIKTOKEN_ENCODING = "cl100k_base"

_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name=TIKTOKEN_ENCODING,
    chunk_size=CHUNK_SIZE_TOKENS,
    chunk_overlap=CHUNK_OVERLAP_TOKENS,
)


def chunk_text(text: str) -> list[str]:
    """Split `text` into ~512-token chunks with 64-token overlap.

    Returns an empty list for blank/whitespace-only input rather than a
    single empty chunk — an empty chunk would still get embedded and
    stored, polluting the corpus with a vector that means nothing.
    """
    if not text.strip():
        return []
    return _splitter.split_text(text)

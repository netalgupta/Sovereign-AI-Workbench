# RAG_SPEC.md — Complete Retrieval-Augmented Generation Specification

## 1. Design Principle
Every generated claim in this system must be traceable to a source passage (NFR-4). This document specifies exactly how ingestion, indexing, and retrieval work so that principle is actually enforceable in code, not just aspirational.

## 2. Ingestion Pipeline

**Input types accepted:** PDF (text-native and scanned), DOCX, TXT, email exports (`.eml`/plain text), scanned TIFF/PNG/JPG (routed through OCR first, per CARD 05 in VIBECODING_SPEC.md)

**Exact pipeline steps:**
1. **Document type detection** — file extension + a `python-magic` MIME check (don't trust extension alone)
2. **Text extraction:**
   - Text-native PDF → `pdfplumber` (preserves layout better than `PyPDF2` for table-heavy refinery documents)
   - Scanned PDF/image → CARD 05 OCR pipeline, page by page
   - DOCX → `python-docx`'s paragraph/table iteration
3. **Chunking:** recursive character splitter, **chunk size 512 tokens, overlap 64 tokens** (exact values — do not leave these as "reasonable defaults" the agent picks itself; consistency across the corpus matters for retrieval quality comparisons). Use `tiktoken`'s `cl100k_base` encoding to count tokens for the split, even though inference uses local models — it's a good-enough universal tokenizer for chunk-sizing purposes.
4. **Metadata attached to every chunk (mandatory fields, none optional):**
   ```python
   class ChunkMetadata(BaseModel):
       source_document: str       # original filename
       document_type: str         # sop, inspection_report, correspondence, spec_sheet, etc.
       page_number: int | None    # None only if genuinely unpaginated (e.g. a chat export)
       chunk_index: int           # position within the document
       ingestion_date: str        # ISO 8601
   ```
5. **Embedding:** `BAAI/bge-large-en-v1.5` via `sentence-transformers`, batch size 32, normalize embeddings (`normalize_embeddings=True` — required for cosine similarity via FAISS's inner-product index to behave correctly)
6. **Storage:** embeddings → FAISS `IndexFlatIP` (exact index type — flat is fine at hackathon corpus scale, don't over-engineer with IVF/HNSW for a demo-sized corpus); raw chunk text + metadata → a parallel SQLite table keyed by the same chunk ID as the FAISS vector index position

## 3. Retrieval — Hybrid Search (full detail beyond VIBECODING_SPEC CARD 09)

- Dense: FAISS cosine similarity via normalized inner product
- Sparse: BM25Okapi over whitespace-tokenized chunk text
- Fusion: Reciprocal Rank Fusion, k=60, as specified in CARD 09 — this k value is a well-established default from the original RRF paper, not arbitrary, keep it
- **Retrieval confidence threshold:** if the top fused result's normalized score falls below **0.35** (on a 0-1 scale after min-max normalizing the fused scores across the candidate set), the system must return "not found in the provided corpus" rather than passing a weak match to the generation step — this is the literal implementation of the NotebookLM-style refusal behavior from the MRPL Grounded Dossier §2. This threshold is a starting point for tuning during Day 6 testing, not a permanently fixed constant — document any change to it in this file.

## 4. Grounding Enforcement at Generation Time

- The reasoning sub-agent's prompt template must include an explicit instruction block (verbatim, do not paraphrase when implementing):
```
You must only state facts that are directly supported by the SOURCES section below. For every factual claim, include a citation marker [N] referring to the source number. If the sources do not contain enough information to answer, say so explicitly rather than filling the gap from general knowledge.

SOURCES:
{retrieved_chunks_formatted_with_numbers}

REQUEST:
{user_request}
```
- Post-generation validation: parse all `[N]` markers in the output, confirm each `N` corresponds to an actually-retrieved chunk (catches the LLM inventing a citation number that doesn't exist) — if an invalid citation number is found, either strip that claim or flag it for human review before it reaches the approval-note generator; do not silently pass it through

## 5. Contradiction Detection (🟡 tier)
- When two retrieved chunks from different `source_document` values both address the same entity (matched via the graph layer's entity extraction — see GRAPH_SPEC.md) but contain conflicting numeric values or directives, flag both in the UI's citation panel with a visible "⚠ conflicting sources" marker rather than silently picking one

## 6. Version/Revision Awareness (🟡 tier)
- If ingested SOPs carry a revision number/date in their filename or header (extracted via a regex pattern configured per MRPL's actual SOP naming convention — confirm this convention before hardcoding a regex, since PSU documents vary), retrieval should prefer the highest revision number for a given SOP identifier and warn if a lower-revision document is being cited

## 7. Testing Requirements
- A fixture corpus of ≥10 mixed documents (public sample SOPs/reports, per the PS's own dataset note) with 5 known question/expected-answer/expected-source triples
- Test asserts: correct source retrieved in top-3 for all 5; confidence-threshold refusal correctly triggers on an out-of-corpus question (e.g. asking about something not in any ingested document)

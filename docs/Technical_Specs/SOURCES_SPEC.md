# SOURCES_SPEC.md — source tracking, images, and document preview

**Status:** implemented on `aryan/rag-and-graphrag`. This is the contract every
component that touches source documents must follow. Owner: Aryan.

This spec covers four things RAG_SPEC.md §2 does not: where source files live,
how folders are watched, how images inside documents are stored and retrieved,
and how a cited page is shown back to the user.

---

## 1. Core principle: reference, never copy

**The user's files stay where the user put them. We record the path.**

A refinery's document set is gigabytes of PDFs and scans. Copying every ingested
file into a managed store doubles the user's disk for no benefit — the bytes are
already on the machine. Everything downstream (previews, "open the source",
extracting a figure) reads the original file in place, on demand.

The one exception is **images extracted from inside documents** (§3): those are
stored, because they do not exist as files anywhere and cannot be re-derived
without re-parsing the document every time one is displayed.

### Consequences the whole team must handle

Referencing files we do not own means they can move, change, or vanish. That is
**normal operation, not an error** — a user moves a folder, a share unmounts,
someone edits an SOP after it was indexed. `DocumentRegistry.resolve()` therefore
returns a **status**, never an exception:

| status | meaning | what the UI must say |
|---|---|---|
| `available` | present, unchanged since indexing | nothing special |
| `modified` | present, bytes differ from what was indexed | "this file changed since it was indexed; quoted text may no longer match" |
| `missing` | recorded path holds no file | "moved or deleted after indexing — re-add it to restore previews" |
| `unknown` | never registered | treat as not ingested |

Never silently show nothing. A wrong-but-confident citation is the failure mode
this whole design exists to prevent.

---

## 2. Watched sources — `backend/ingestion/source_watcher.py`

A user adds a **path**, not a file: `Downloads`, a project folder, a mounted
share. Anything ingestible appearing under it becomes searchable without being
added again.

### Scanning, not filesystem events

Deliberate. OS watch APIs (`inotify`, `ReadDirectoryChangesW`) are
platform-specific, silently lossy on network shares, and miss everything that
happened while the app was closed — which for a desktop workbench is most of the
time. Scanning is predictable, testable, identical on every platform, and cannot
miss an overnight change. A watch API may later feed the same queue as an
optimisation, never as a replacement.

### What a scan classifies

| kind | test | action |
|---|---|---|
| new | path not in registry | ingest |
| modified | size **or** mtime differs | **re-ingest** — old chunks describe text that is gone |
| unchanged | size and mtime match | skip, cheaply |

**Scans use size + mtime only — never a hash.** On a Downloads folder with
thousands of files almost everything is unchanged, and hashing every file to
learn that is a scan nobody will leave enabled. Hashing happens once, at
registration. A file touched but not edited costs one wasted re-ingest; that is
the accepted trade.

### Exclusions (`SUPPORTED_SUFFIXES`, `EXCLUDE_PATTERNS`)

Only formats RAG_SPEC §2 can actually read are offered. Also always excluded:
Office lock files (`~$*`), partial downloads (`*.crdownload`, `*.part`), OS
metadata (`Thumbs.db`, `.DS_Store`), and anything under a dot-directory.
**Ingesting a half-written download produces garbage chunks that then have to be
hunted down**, which is worse than ingesting it late.

---

## 3. Priority: newest modification time first

**One ordering key delivers the entire policy.**

A file that just arrived has the newest mtime, so it sorts ahead of everything —
new work preempts the backlog automatically. The backlog then drains
most-recent-first, which is also correct: last quarter's report is likelier to be
asked about than one from four years ago.

There is deliberately **no separate "new vs backlog" bookkeeping**, because a
second ordering is a second thing to fall out of sync with the first.

### Queue — `backend/ingestion/ingestion_queue.py`

Durable, because a Downloads folder can present thousands of files each costing
seconds to minutes (OCR, transcription, figure description). Must survive the app
closing mid-run.

States: `pending → in_progress → done | failed`.

- **Failures are state, not exceptions.** One corrupt PDF must not stall the queue
  behind it, must not retry forever, and must not vanish silently. Retried
  `MAX_ATTEMPTS` (3) times, then parked as `failed` with its error, where a UI can
  show it and `requeue_failed()` can retry after the user fixes the cause.
- **Re-scanning must not reset attempt counts**, or a broken file retries forever.
- **Storage is append-only JSON-Lines with `fsync`**, compacted atomically. Same
  reasoning as `extract_corpus.py`: a rewritten file loses everything if the
  process dies mid-write; one line per state change costs at most that line.

---

## 4. Images inside documents

### 4.1 Every image gets BOTH kinds of understanding

For each image found in any document, the pipeline records:

1. **OCR text** — what is *written in* it (CARD 05). For a P&ID this is
   `V-204, E-201B, K-201` — exactly the tokens an engineer types into search.
2. **Vision description** — what it *depicts* (CARD 13). "Hydrocracker reactor
   loop with recycle gas compressor."

**Both, always — never one chosen by guessing the image type.** They answer
different questions and neither subsumes the other: a description paraphrases
away the tags OCR captures, and OCR can never produce the description. Guessing
drops whichever the guess got wrong.

### 4.2 Both go into the chunk text

`render_image_block()` produces the text that stands in for the image inside the
chunk, so the image is reachable by ordinary retrieval:

```
[Image 1 on page 3 — ref image:a1b2c3d4e5f6]
Text visible in the image: V-204 E-201B K-201 Reactor Stripper
Description of the image (vision-model estimate, not a measurement): A piping and
instrumentation diagram of the hydrocracker reactor loop...
```

**The estimate caveat is inline in the indexed text, not only in metadata.** If a
consumer renders chunk text and drops metadata — a prompt, a log line, a paste
into a report — the caveat must travel with the words or it is lost exactly where
it matters most. See §4.5.

### 4.3 Storage is content-addressed — `backend/ingestion/image_store.py`

Keyed by SHA-256 of the pixels. **This is load-bearing, not tidiness.** Real
corpora repeat images constantly — letterheads, standard safety diagrams, the
same equipment photo in six reports. Content-addressing means:

- each distinct image is described **once** (a vision call is tens of seconds);
- "the same image" is a fact about the bytes, not a guess from filename;
- one image with N **occurrences** (document, page, bbox), not N copies.

Metadata is a **sidecar JSON per image**, not one shared index: ingestion is
incremental and interruptible, and a shared index needs read-modify-write and
locking to be crash-safe. A file per image is atomic per image.

### 4.4 Chunks carry image ids

`ChunkMetadata.image_ids` lists every image on the page the chunk came from.
**Every chunk from a page inherits that page's images** — a chunk is a slice of
text, but the image belongs to the page, and attaching it only to whichever slice
contains the description block makes it unreachable from the others.

### 4.5 Retrieving the right image — `backend/retrieval/image_retrieval.py`

A page holds several images, so a chunk references several. **Returning all of
them is not an answer.** `select_images_for_request()` embeds the user's request
and each image's combined understanding (source name + description + OCR) and
ranks them, so:

- "show me the hydrocracker schematic" → the P&ID, via its description
- "the diagram with V-204 on it" → the P&ID, via its OCR text
- "the downtime chart" → the bar chart

**Returns empty rather than a weak best guess** below `MIN_IMAGE_MATCH_SIMILARITY`.
Always returning the top match means a question that referenced no image still
produces one, which reads as a claim that the picture is relevant. Putting the
wrong diagram in front of an engineer is worse than attaching none.

### 4.6 Hard constraint #3 applies to every chart reading

`description_is_estimate` is `True` on every record and must survive to the point
of display. **This is measured, not theoretical:** on generated charts carrying
*no printed numbers at all*, the vision model emitted specific figures and
described them as values "printed as text on the chart" — 10 invented values
across 2 of 6 charts (`backend/evaluation/CHART_STRESS_REPORT.md`). A UI that
renders one of those like a measurement defeats the constraint.

---

## 5. Document preview — `backend/retrieval/document_preview.py`

An answer citing "SOP-114, page 7" is a claim the user cannot check without going
to find it. In a 500-page document that friction is why people stop trusting
retrieval. **Show the page, with the passage highlighted.**

- `preview_for_chunk(chunk, registry)` → rendered PNG of that page + highlight
  rectangles **in image pixel space**.
- **Only one page is ever rendered.** Rendering is the expensive step; a preview
  needs the page asked about, not the document. One page at 150 DPI is a few
  hundred KB and tens of milliseconds.
- Coordinates are converted from PDF points to pixels **here**, because the
  conversion depends on the DPI this module chose, and a consumer that has to
  know that will eventually get it wrong.

### Highlights are searched for, never stored

Storing character offsets at ingestion would be faster, but they go stale the
moment the document is edited and would then highlight the wrong region **with
total confidence** — worse than no highlight. Searching the live page either
matches what is there now, or honestly finds nothing.

Anchoring tries phrases from several positions in the chunk (start, third,
middle), because a chunk usually spans a page boundary at one end, so any single
anchor position fails often.

### Unpaginated sources return `None`

DOCX, TXT, email and audio have no page. Rendering "page 1" of a flow document
would show something the text may not be on. `page_number is None` is a real
property of the format, not missing data — never fabricate one.

---

## 6. Module map

| module | responsibility |
|---|---|
| `ingestion/document_registry.py` | where each source file lives; identity and change status |
| `ingestion/source_watcher.py` | watched folders; classify new/modified/unchanged |
| `ingestion/ingestion_queue.py` | durable priority queue; failure state |
| `ingestion/image_store.py` | content-addressed image storage + understanding |
| `ingestion/image_extraction.py` | pull images out of PDF/DOCX/standalone, understand them |
| `retrieval/image_retrieval.py` | pick the right image for a request; return pixels |
| `retrieval/document_preview.py` | render the cited page with highlights |

## 7. Invariants — do not break these without updating this file

1. **Never copy a user's source document.** Record the path.
2. **Never fabricate a page number** for an unpaginated format.
3. **Never present a vision description as a measurement.** The estimate flag
   travels to the point of display, including inside indexed chunk text.
4. **Never return a best-guess image** below the similarity floor. Return none.
5. **Never hash every file on a routine scan.** Size + mtime; hash at registration.
6. **Never reset a queue item's attempt count on re-scan.**
7. **Failed ingestions stay visible.** Silent failure means "why is this document
   not searchable?" has no answer.

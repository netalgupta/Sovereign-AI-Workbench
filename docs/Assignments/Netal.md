# Netal.md — Fullstack: Sources, Citations, Graph, and Retrieval Transparency

> **Rewritten.** The previous version listed three items, two of which
> now have working implementations on `aryan/rag-and-graphrag`. That
> made this the lightest assignment on the team by a wide margin, which
> was neither intended nor fair. This version takes those two as
> starting points you own outright, and adds the surfaces that exist in
> the backend today with no UI at all.
>
> Ownership questions are settled by `docs/OWNERSHIP.md`.

## What you own, in one sentence

**Everything that answers "where did this come from?"** — the sources
the system is grounded in, the citations that point into them, the graph
that connects them, and the evidence for why a given answer was
retrieved the way it was.

That is the single most important trust surface in a NotebookLM-style
product. If a judge doubts an answer, every path they take to check it
goes through a screen you built.

---

## Scope of Ownership

### 1. Sources panel + `/sources` page (FRONTEND.md §3.5)
The ingested-document list, type icons, include/exclude toggles, and the
persistent trust line specified verbatim in FRONTEND.md: *"This session
is grounded only in the sources listed here."*

Backend ready: `GET /api/corpus` returns every source with `category`,
`subcategory`, size, folder, and full path. `DELETE /api/sources`
removes one. `POST /api/sources` and `/api/sources/scan` add folders.

**Warning from experience:** the source list is a claim about what the
system can retrieve from. An earlier version of this panel shipped a
230-line hardcoded literal of thirteen filenames as its initial state,
so a failed fetch left invented documents on screen indefinitely with no
way to tell them from real ones. Start empty, always.

### 2. Citation chips + expansion (FRONTEND.md §3.2)
A `[1]` in an answer expands to the exact passage it came from.

Backend ready: `/api/chat` returns `citations` with text, source
document, page number and score. Citation markers are validated
server-side — invalid indices are stripped and reported in
`invalid_citations_stripped`, so anything reaching you resolves.

### 3. Source page preview — **NEW, and the highest-value item here**
Render the user's own PDF or DOCX at the exact page a citation points
to. Claude-app style: the document opens, scrolled to the passage, with
the cited text highlighted.

Backend ready: `GET /api/preview` serves the page image; `SOURCES_SPEC.md`
defines the path registry. Source files are **never copied** — only
their paths are tracked — so you are rendering from the user's real file
on their disk.

Why it matters: the product's core promise is that every claim is
traceable. Right now a citation gets you a passage; this gets you the
page, in the actual document, which is what an engineer needs to sign
off on a number. It is an empty surface today.

### 4. Graph explorer `/graph` (FRONTEND.md §3.6 / GRAPH_SPEC.md §6)
**Take over `frontend/src/pages/GraphExplorerPage.jsx`** — a working
force-directed graph with drag, cursor-anchored zoom, label filtering,
search-and-centre, and a node inspector showing every property and every
edge with its type. It is a reference implementation, not a finished
feature. Extend or replace it; it is yours.

Still missing: the signature query's subgraph-highlight animation
(GRAPH_SPEC.md §6). That is the demo moment.

Backend ready: `GET /api/graph` returns all nodes with every property
and typed edges, and degrades to a snapshot when Neo4j is down rather
than serving an empty graph as live truth.

### 4b. Multi-hop graph traversal visualisation — **NEW, and the demo moment**

The interesting GraphRAG questions are not "show me this node", they are
multi-hop: *"what incidents touch the segment this SOP governs?"* is
Document -> PipelineSegment -> Incident. **The answer is the path, not
the endpoints**, and a path is something you can only really show by
animating it.

Backend ready (built for you): `GET /api/graph/neighbourhood?node=X&hops=N`
returns the subgraph within N hops, and **every node carries its
`distance`** plus a `by_distance` histogram. Verified live:

```
'Mangalore-Hassan' hops=1: 3 nodes,  4 edges, by_distance={'0':1, '1':2}
'Mangalore-Hassan' hops=2: 8 nodes, 18 edges, by_distance={'0':1, '1':2, '2':5}
'P-HS-02'          hops=2: 5 nodes, 10 edges, by_distance={'0':1, '1':1, '2':3}
```

`distance` exists specifically so you can stage the reveal: hop 0, then
hop 1, then hop 2. A traversal that appears all at once is a hairball; a
traversal that unfolds is an explanation, and it is the clearest
possible demonstration that this system reasons over connections rather
than just matching text.

What to build:
- **Hop-by-hop reveal** on query. Ring 0 is the anchor, then each hop
  fades in with its edges. Let the user step forward and back.
- **Path highlight** between two selected nodes — trace the actual
  route, dim everything else.
- **Hop depth control** (1-4, the API caps it) so the user can widen or
  narrow the neighbourhood live.
- **Edge types on the path**, always visible. `REFERENCES` vs
  `REPORTS_INCIDENT_AT` is the difference between "this document
  mentions the segment" and "an incident happened there", and hiding the
  distinction makes the graph decorative.
- **Wire it to the chat**: when an answer cites documents, offer "show
  how these connect" and traverse from them.

Two things to know before you start:
- The graph has been **lost three times** to a container without a named
  volume. If `/api/graph` returns 0 nodes, rebuild it in seconds with
  `py -3 -m backend.evaluation.build_graph` — no LLM calls, it replays a
  committed extraction cache. Don't debug your UI against an empty graph.
- The endpoint is **parameterised, not arbitrary Cypher**. If you need a
  traversal shape it does not support, ask for it rather than adding a
  client-supplied-query endpoint — that would be an injection surface on
  the component whose whole job is being trustworthy about provenance.

### 5. Chunk / vector inspector — **NEW**
**Take over `InstrumentationPage.jsx` and `KnowledgeBasePage.jsx`.**
Both are prototypes. Make them tools:
- filter chunks by document
- show a chunk's embedding neighbourhood
- show, for a given query, which chunks were retrieved **and why** —
  dense similarity, lexical match, or neighbour expansion

Backend ready: `GET /api/chunks`, `POST /api/search`, `POST /api/embed`,
`GET /api/metrics`.

### 6. Retrieval trace UI — **NEW**
The backend prints a complete per-turn trace to the server console
(`backend/observability/turn_log.py`): every retrieved chunk with its
score and source, the confidence threshold, what the query was expanded
to, which signal admitted the answer, and what citation validation
changed. **None of it is visible in the app.**

`/api/chat` already returns `plan` and `tool_call_events`, and
`MessageBubble.jsx` has a `TurnTrace` component rendering the basics.
The retrieval detail is the part that is missing and is the part that
proves the system is grounded rather than guessing.

### 7. Ingestion progress feed — **NEW**
`GET /api/ingestion/{job_id}` reports per-document stage
(queued → extracting → chunking → embedding → indexing → indexed /
failed / skipped), failures with human-readable reasons, and an ETA
averaged over documents that have actually finished. There is no UI, so
ingesting a folder is still an indefinite spinner.

Note the deliberate design: it reports **counts and the current
document, not a percentage**. Per-document cost spans two orders of
magnitude (a 2 KB text file versus a 40-page scan needing OCR), so a
fraction of files looks precise and misleads. Do not add a percentage.

---

## Explicitly Not Your Job
- Retrieval, graph and embedding logic (Aryan) — you visualise its output
- App shell, chat, plan graph, approval modal, settings, Electron (Advay)
- Output library, calculation trace, audit log (Kanishka)
- Network monitor, multimodal upload, defect overlay (Sahil)
- Generating DOCX/XLSX/PPTX (Kanishka — see `OWNERSHIP.md` §2)

---

## Day-by-Day

- **Day 1:** Pull `aryan/rag-and-graphrag`. Run the backend and the
  frontend (commands in `docs/RUNNING.md`). Open `/graph`, `/sources`
  and the instrumentation page and see what already works — do not
  start by writing code.
- **Day 2:** Sources panel against the live `/api/corpus`. Empty state
  first, real data second, no placeholder content at any point.
- **Day 3:** Citation chip + expansion against the real `citations`
  payload.
- **Day 4-5:** Source page preview. Backend API exists; build the
  viewer. Test with a genuinely long PDF, not a 2-page fixture.
- **Day 6:** Graph explorer — take over the existing page, add the
  signature-query subgraph highlight.
- **Day 6-7:** Multi-hop traversal visualisation (§4b). Treat this as
  the highest-value item after the page preview — it is the clearest
  proof that the system reasons over connections, and the backend is
  already done.
- **Day 8:** Retrieval trace UI in the chat.
- **Day 9:** Chunk/vector inspector; ingestion progress feed.
- **Day 10:** Hand to Advay for integration; support his consistency pass.
  Buffer for bugs.

## Dependencies
- Everything you need on the backend **exists today** on
  `aryan/rag-and-graphrag`. You are not blocked on Aryan for any item
  above; if an endpoint's shape is wrong for you, say so and it will be
  changed.
- Report components to Advay for integration by Day 8.

## Acceptance Criteria You Own
FR-10 (citation UI), NFR-4 (citation display and refusal presentation),
GRAPH_SPEC.md §6 (signature query presentation), SOURCES_SPEC.md (page
preview).

# Advay — the ingestion pane, and the graph inside the thinking block

Two pieces, one idea: **the system already knows far more about what it
is doing than it tells anyone.** Both of these are about getting what
the backend already produces onto the screen, at the moment it happens.

Read this before starting. The endpoints and events below exist and
return real data today — none of it needs backend work from you, and
none of it should be mocked.

---

## Why this matters more than it sounds

Everything that went wrong on this project in the last two days was a UI
showing something other than what the system held:

- the chunk inspector showed 21 chunks from a committed export while the
  corpus had 231
- the tab badges read `|| 29`, `|| 101`, `: 15`, `|| 21` — the old
  snapshot's exact numbers, displayed whenever a fetch had not landed
- the graph said "101 nodes **in Neo4j**" with the database empty
- the Images tab crashed to a black page because it was written against
  a field name the live API does not use

None of those were hard bugs. They were all the same bug: **a surface
that renders a plausible number instead of the truth, or nothing at
all.** The two features below are the opposite of that — they exist to
make the machine legible while it works. Build them so that anything
they cannot show honestly, they leave blank.

---

## Piece 1 — Source ingestion, live

**Where:** the Sources pane (`/sources`), and the Add Sources flow.

Ingesting a folder is minutes of silence today. One spinner, then a
number. Behind that spinner the backend is reporting, per document,
exactly which stage it is in — and nothing renders it.

### The data you have

`GET /api/ingestion/log` and the progress tracker in
`backend/ingestion/ingestion_progress.py`. Every document moves through:

```
QUEUED → EXTRACTING → CHUNKING → EMBEDDING → INDEXING → INDEXED
                                                      ↘ FAILED / SKIPPED
```

`EXTRACTING` is where OCR and audio transcription happen, so it is the
slow one for scans — a 12-page scanned PDF sits there for a while and
the user deserves to know that is normal rather than stuck.

Each record carries the filename, the stage, the chunk count once
chunking has happened, and an error when it failed.

### What to build

A per-document feed, not a progress bar:

```
Scanned_Inspection_Checklist_CCR1.png     EXTRACTING   OCR, 1 page
SOP-114-Rev3_Hydrocracker_Changeout.docx  INDEXED      8 chunks
Maintenance_Log_Q3_2026.xlsx              EMBEDDING    14 chunks
Corrupt_File.pdf                          FAILED       could not read page 3
```

- **Show the stage, not a percentage.** A percentage across documents of
  wildly different cost is a lie; "OCR on page 4 of 12" is not.
- **Failures stay on screen**, with the reason, and do not stop the run.
  One unreadable PDF in a folder of 50 must not look like a dead ingest.
- **Chunk counts as they land.** That number is what tells someone their
  document actually made it into the retriever.
- **SKIPPED is not FAILED.** A `.zip` nobody can ingest is a normal
  outcome, and conflating the two makes people hunt for a bug.

### The one that will surprise you

`SKIPPED` also means "unchanged since last run". Re-adding a folder is
cheap and should LOOK cheap: if 49 of 50 documents are skipped because
nothing changed, say so, or people will think it silently did nothing.

---

## Piece 2 — The graph, inside the thinking block

**Where:** the in-chat trace (`MessageBubble.jsx`, the `TurnTrace`
component).

The trace already shows plan steps, memory, tool calls with their
arguments, retrieved sources and calculation working. What it does not
show is the thing that makes this product different from a search box:
**how the documents it used are connected to each other.**

### The data you have

- `GET /api/graph` — every node with all properties, every edge WITH ITS
  TYPE. It declares `source: "live" | "snapshot"`, and you must render
  that distinction (see below).
- `GET /api/graph/neighbourhood?node=X&hops=N` — a subgraph around one
  entity, which is what you want here rather than the whole thing.
- The turn's own `memory` event carries `focus_entities` — equipment and
  document tags this turn actually touched, like `HCU-2`, `FFC-201`,
  `SOP-114-Rev3`. That is your entry point into the graph.

### What to build

Inside the expanded trace, under the sources it used: a small
neighbourhood graph of the entities that turn touched, one hop out.

Not the 101-node hairball — six to ten nodes, the ones relevant to THIS
answer. The question it should answer at a glance is *"what else is
connected to the thing I just asked about?"*

- **Edge types are shown, always.** `REFERENCES` (merely mentioned) and
  `APPLIES_TO` (explicitly in scope) mean different things, and
  GRAPH_SPEC.md §8 makes that distinction load-bearing. An anonymous
  line between two nodes is worse than no line, because a reviewer will
  assume the stronger meaning.
- **Clicking a node shows its stored properties**, the same way the full
  explorer does. Reuse `GraphExplorerPage`'s inspector rather than
  writing a second one.
- **If the graph has nothing for this turn, render nothing.** Not an
  empty box, not a placeholder — the absence is information.

### The trap, and it is a real one

`GET /api/graph` returns `source: "snapshot"` when Neo4j is down, and
that snapshot is somebody's exported graph from another day. The Sources
page used to print `"101 nodes · 115 relationships in Neo4j"` over
exactly that data, with the database empty. **Read `source` and say what
it is.** Same rule for coverage: the graph is built from an entity
extraction cache, so it can legitimately describe fewer documents than
the corpus holds.

---

## What just changed that you need to know

**The graph now follows the corpus automatically.** Adding a source
schedules entity extraction in the background
(`backend/graph/auto_extract.py`), and the graph rebuilds when it
finishes. Extraction is one model call per NEW chunk — 10–25s each — so
for a large folder it runs for a while after ingestion has already
returned.

That is a thing your ingestion pane should show. `auto_extract.status()`
returns:

```python
{"state": "extracting" | "building" | "idle" | "failed",
 "chunks_total": int, "chunks_done": int, "reason": str}
```

It is not exposed over HTTP yet — **adding that endpoint is yours**, and
it is four lines in `backend/api/routes.py` next to the other status
routes. Wire it into the same feed: "graph: extracting 40/210" belongs
right under the document list, because from the user's point of view it
is the same operation still finishing.

**Other things that moved:**

- `/sources` and `/graph` no longer fall back to committed JSON exports.
  Default is an honest empty state; `VITE_ALLOW_SNAPSHOTS=true` restores
  the old behaviour for frontend work with no backend.
- The corpus index is cached in `.workbench/` (gitignored) and rebuilt
  only when the configured sources change. Restart is now 0.0s instead
  of 65s.
- `chatStore.activeDocuments` starts `null`, not `[]`. `null` means "not
  known yet"; `[]` means "the user switched everything off" and the
  backend refuses. Do not collapse them.
- `MessageBubble` renders a `memory` node in the trace. Your graph piece
  goes next to it and reads the same event.

---

## How to know you are done

Not "it renders". These:

1. Ingest a folder of 30+ mixed documents including at least one scan
   and one unreadable file. Every document's stage is visible as it
   happens, the failure is on screen with its reason, and the run
   finishes.
2. Re-add the same folder. It is obviously fast and obviously says why.
3. Ask a question whose answer spans two documents. The trace shows the
   entities it touched and how they connect, with edge types named.
4. Stop Neo4j and repeat 3. Nothing lies. Either the graph is absent, or
   it says where its data came from.
5. `npm run build` is clean, and the page does not blank on any payload —
   the Images tab crashed for a whole session because one field was
   undefined and nothing guarded it.

---

## One request

When something on screen does not match what the backend holds, that is
a bug worth stopping for, even when it looks cosmetic. Every single
defect in the list at the top of this document looked cosmetic first.

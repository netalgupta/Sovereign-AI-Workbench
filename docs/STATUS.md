# STATUS.md — what is done, what is not, who has it

**Generated from the live system, not from intent.** Tool counts come
from `docs/TOOLS.md` (Owner + Status columns); "built" means there is a
registered implementation you can call through `POST /api/tools/call`
today. Endpoint list enumerated from the running server.

Branch: `aryan/rag-and-graphrag` · Suite: **357 passed, 1 skipped**

---

## Headline numbers

| | |
|---|---|
| Tool rows in TOOLS.md | **72**, all now assigned an owner |
| Built | **35** |
| Not started | **37** |
| 🔴 demo-critical built | **23 of 33** |
| Live API endpoints | **40** |
| Registered, callable tools | **19** |

---

## Per person

### Aryan — RAG / AI / ML, team lead
**30 built · 21 pending · 🔴 18 built / 4 pending**

Done: model registry + router, hybrid RAG (dense + BM25 + RRF), query
expansion, neighbour expansion, confidence gate, grounded generation,
citation validation, GraphRAG extraction + graph build, OCR, voice
transcription, chart/vision tools, math + unit + thermophysical tools,
NumPy trend/projection, plotting, MRPL process calculations, tool
registry, planner/dispatch/verification, contradiction detection,
ingestion pipeline + progress, source tracking, turn tracing, `draft_docx`.

Pending: rows 54-60 MRPL-specific retrieval features (56, 57, 59, 60),
semantic-chunking evaluation, retrieval at real corpus scale.

**Known limitation, not yet fixed (1):** answer quality on
`/api/chat/stream` is worse than `/api/chat`. The loop retrieves
correctly and under-extracts — the direct path answers "3.4 g/10min
[1]" consistently where the loop retrieved the right documents and
said it could not find the value. Mechanism is sound; the grounding
scaffolding is missing. `/api/chat` stays the default until this closes.

**Known limitation, not yet fixed (2):** `all_chunk_texts()` loads the whole
corpus per query. Fine at 50 documents, will not hold at 1000-page PDFs.
This is the next thing.

### Aditya — backend infra
**5 built · 6 pending · 🔴 5 built / 3 pending**

Done: FastAPI app, sandbox execution engine (image now builds and
egress isolation is proven), approval gate backend, audit log, network
monitor mechanism.

Pending: SAP connector (row 49, 🔴 — highest-leverage MRPL feature),
Docker Compose + air-gapped packaging, encryption at rest, code agent
(CARD 04 — `code_agent` is the one sub-agent with an empty tool set and
it RAISES by design until you wire it), rows 35-37.

**Blocked on you:** nothing. `qwen2.5-coder:7b` is not pulled — that is
your first command.

### Advay — fullstack lead, frontend
**Frontend surfaces, not TOOLS.md rows — 0 rows is not 0 work**

Done (by others, now yours to own): app shell exists, chat works end to
end, `TurnTrace` renders the real per-turn plan and tool output.

Pending: plan graph visualiser (🔴, highest-impact single visual),
approval modal wired to the live gate, settings + live model-add form
(the on-stage FR-4 moment), **Electron packaging** (mandatory,
FRONTEND.md §4.1), integration pass over everyone's components.

### Netal — sources, citations, graph, retrieval transparency
**Frontend surfaces + 4 registry tools (rows 16, 18, 32, 60) —
scope rebalanced, see `Assignments/Netal.md`**

Ready to take over: `GraphExplorerPage`, `KnowledgeBasePage`,
`InstrumentationPage` — all working prototypes.

Pending and high value: **granular agent thinking UI** (backend
streaming today, `/api/chat/stream`, 173 events per turn — read
`AGENT_STREAM_PROTOCOL.md`), **source page preview** (backend API exists, no
viewer), **multi-hop traversal visualisation** (backend built for you,
`/api/graph/neighbourhood`, returns per-node `distance`), retrieval
trace UI, ingestion progress feed, citation chips, sources panel.

### Kanishka — generated outputs, verification trace, audit
**0 built · 7 pending · 🔴 0 built / 2 pending**

Pending: XLSX generation (row 39, 🔴), PPTX (40), PDF export, MRPL
document generators (54, 55, 58), `/outputs` library, calculation trace
viewer, audit log viewer.

**Reference implementation ready:** `backend/tools/documents/draft_docx.py`
— registered, approval-gated, citations structural, `UNSOURCED` marked
in the file, estimate warnings printed in the document. Copy that shape.

**Blocked on nobody.** Approval gate, audit log and tool registry are
all live.

### Sahil — monitor, multimodal, defect overlay
**0 built · 3 pending · 🔴 0 built / 1 pending**

Pending: network monitor panel (🔴, `/api/network/status` is live and
correct), multimodal upload + preview, defect/annotation overlay.

**Read this before building the monitor panel:** it must report
`externalCount` (this process tree), never `hostExternalCount` (the
whole machine). The old version counted every socket on the host and
displayed *"ALERT: External Traffic — 44 external connections"* on a
zero-egress product; all 44 belonged to the browser, the IDE and
Spotify. A safety indicator that fires on someone else's music stream
trains everyone to ignore it.

---

## What changed recently that affects everyone

| Change | Why it matters to you |
|---|---|
| Verification is **on demand**, not inline | `/api/chat` returns `verification: null`. Use the Verify button / `POST /api/verify` |
| Turn tracing **on by default** | Your server console now explains every answer. `WORKBENCH_TRACE=off` to silence |
| Sandbox image **builds and runs** | `run_in_sandbox` works; egress isolation proven |
| `reasoning-model` → **qwen2.5:7b** | Turns are 17-25s instead of 127s |
| `fast-router` → **phi3.5** | The old tag `phi-3.5-mini` never existed |
| Corpus sources carry **`category`** | Sidebar filter tabs work against real data |
| Vite no longer intercepts API routes | The backend wins whenever it is running. **Start the backend first** |
| `/api/graph/neighbourhood` added | Multi-hop traversal with per-node distance |
| **Agentic tool-calling loop** + `POST /api/chat/stream` | The agent now CHOOSES tools and narrates while working. Netal renders it |
| `search_documents` / `list_documents` registered | The registry had no search tool at all — the agent could not look anything up |

---

## Rules (from `docs/OWNERSHIP.md` §6)

1. Every tool you add gets a row in `TOOLS.md` **with your name**.
2. Anything that writes a file, sends, or touches SAP registers
   `requires_approval=True`.
3. No model names outside `models.yaml`. Two tags in this repo were
   wrong and never worked.
4. **No fabricated data in the UI, ever** — not even as a placeholder.
   Empty states only.
5. Don't measure one thing and report another.

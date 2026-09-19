# OWNERSHIP.md — who owns what, unambiguously

**This document is the tie-breaker.** Where any other document disagrees
with this one about who owns a deliverable, this one wins and the other
should be corrected.

## Why this exists

The assignment documents each describe one person's scope, so a
deliverable that sits between two people could be described twice, or
not at all, and nobody could tell which. Three real gaps were found:

1. **Document generation (DOCX / XLSX / PPTX / PDF) had no owner.**
   `Kanishka.md` said the backend generation belongs to "Aditya/Aryan"
   — a slash, not an assignment — while `Aditya.md` and `Aryan.md` both
   omitted it entirely. `TOOLS.md` rows 38-41 name the tools but the
   table **has no Owner column at all**, despite `CLAUDE.md` instructing
   every new tool to "Add a row to TOOLS.md with owner and priority
   tier". So the single headline demo output (FR-9, FR-12) was owned by
   nobody.

2. **Netal's scope was materially lighter than everyone else's**, and
   two of the three items in it have since been built (see "Already
   built" below), so it was lighter still than it looked.

3. **`docs/` held stale duplicates of the root specs.** `docs/SYSTEM.md`
   still named `Qwen2-VL`, a model tag that does not exist on Ollama and
   was corrected in the root copy in commit `3c94963`. Two copies, one
   fixed, one rotted. Resolved under "Source of truth" below.

---

## 1. Source of truth for documents

| Document | Canonical location | Owner |
|---|---|---|
| `CLAUDE.md` | repo root (tooling reads it there) | Aryan |
| `REQUIREMENTS.md`, `SYSTEM.md`, `SIH26117_MRPL_Grounded_Dossier.md` | repo root | Aryan |
| `DEPENDENCIES.md`, `STAKEHOLDERS.md`, `TOOLS.md` | `docs/` | Aryan (TOOLS.md rows: whoever adds the tool) |
| `Technical_Specs/*.md` | `docs/Technical_Specs/` | spec owner, listed in each file |
| `Assignments/*.md` | `docs/Assignments/` | Aryan |
| This file | `docs/OWNERSHIP.md` | Aryan |
| `docs/STATUS.md` — built vs pending, per person | `docs/` | Aryan |
| `docs/RUNNING.md` — how to start and read the system | `docs/` | Aryan |
| `docs/INTEGRATION.md` — every live endpoint and its shape | `docs/` | Aryan |
| `docs/TEAM_KICKOFF_MESSAGE.md` — kickoff text | `docs/` | Aryan |

There is exactly **one** copy of each. The duplicates under `docs/` that
shadowed root files have been deleted. If you need a file, link to it;
do not copy it.

---

## 2. Document generation — resolved

This was the biggest gap. The split is now by **layer**, not by person's
convenience:

| Deliverable | Backend (produces the file) | Frontend (shows/downloads it) |
|---|---|---|
| DOCX generation (row 38, 🔴) | **Aryan** — `backend/tools/documents/draft_docx.py`, **built**, registered, approval-gated | **Kanishka** |
| XLSX generation with live formulas (row 39, 🔴) | **Kanishka** | **Kanishka** |
| PPTX generation (row 40, 🟡) | **Kanishka** | **Kanishka** |
| PDF export of any of the above (row 40a, 🟡) | **Kanishka** | **Kanishka** |
| Calculation trace documents (row 41, 🔴) | **Aryan** (trace data) | **Kanishka** (viewer) |

**Why Kanishka owns XLSX/PPTX end-to-end rather than only the UI.**
Splitting a single file-generation feature across two people means the
person building the card cannot test it until the person building the
generator finishes, and neither owns the result. `draft_docx` is already
built and is the reference implementation — it shows the required shape:
registered in the tool registry, `requires_approval=True`, citations
structural, `UNSOURCED` marked in the file itself, estimate warnings
printed in the document. Copy that shape for XLSX and PPTX.

**The approval gate is not optional on any of these.** CLAUDE.md hard
constraint #4: no file write without a human-approval-gate check. The
dispatcher enforces it from the registry flag, so it cannot be forgotten
— but a tool registered without `requires_approval=True` bypasses it
silently. `draft_docx` is the example to follow.

---

## 3. Full ownership matrix

Read across: the deliverable, who builds the backend, who builds the UI.
"—" means the layer does not exist for that item.

### Retrieval, models, reasoning
| Deliverable | Backend | Frontend |
|---|---|---|
| Model registry + router | Aryan | Advay (settings) |
| Hybrid RAG (dense + BM25 + RRF) | Aryan | — |
| Confidence gate / refusal | Aryan | Advay (chat) |
| Query expansion | Aryan | — |
| GraphRAG entity + relationship extraction | Aryan | Netal (explorer) |
| Multi-hop graph traversal (`/api/graph/neighbourhood`) | Aryan (built) | **Netal** (hop-by-hop visualisation) |
| Grounded generation + citation validation | Aryan | Netal (citation chips) |
| Self-verification (§5) | Aryan | Kanishka (trace viewer) |
| Contradiction detection | Aryan | Netal |
| **Agentic tool-calling loop** (`agent_loop.py`) | **Aryan** (built; answer quality open) | — |
| **Agent event stream** (`POST /api/chat/stream`) | **Aryan** (built) | **Netal** (granular thinking UI) |
| `search_documents` / `list_documents` tools | Aryan (built) | — |
| NetworkX graph analytics (row 32) | **Netal** | **Netal** |
| Version/revision tracking (row 16) | **Netal** | **Netal** |
| Correspondence summarisation (rows 18, 60) | **Netal** | **Netal** |

### Infrastructure
| Deliverable | Backend | Frontend |
|---|---|---|
| FastAPI app, routing | Aditya | — |
| LangGraph orchestration | Aryan (logic) + Aditya (infra) | Advay (plan graph) |
| Sandboxed execution | Aditya | Sahil (output display) |
| SAP connector (read-only) | Aditya | Kanishka (result cards) |
| Audit log | Aditya | Kanishka (viewer) |
| Approval gate | Aditya (state) + Aryan (registry enforcement) | Advay (modal) |
| Network monitor | Aditya (mechanism) | Sahil (panel) |
| Docker / air-gapped packaging | Aditya | — |
| Encryption at rest | Aditya | — |

### Ingestion and sources
| Deliverable | Backend | Frontend |
|---|---|---|
| Document ingestion pipeline | Aryan | Kanishka (upload UI) |
| Watched folders / priority queue | Aryan | Netal |
| OCR (printed + scanned) | Aryan | Sahil |
| OCR text-region overlay (row 7 — NOT defect detection) | **Sahil** (tool + overlay) | Sahil |
| Voice transcription | Aryan | Sahil |
| Image storage + retrieval | Aryan | Netal |
| Page preview from the user's own file | Aryan (API) | **Netal** |
| Ingestion progress feed | Aryan | **Netal** |

### Frontend surfaces
| Surface | Owner |
|---|---|
| App shell, routing, design tokens | Advay |
| Chat, streaming, tool-call events | Advay |
| Plan graph | Advay |
| Approval modal | Advay |
| Settings + live model add | Advay |
| Electron packaging | Advay |
| Sources panel + `/sources` | Netal |
| Citation chips + expansion | Netal |
| Graph explorer `/graph` | Netal |
| Multi-hop traversal / path visualisation | Netal |
| Granular agent thinking transcript | Netal |
| Source page preview | Netal |
| Chunk / vector inspector | Netal |
| Output library `/outputs` | Kanishka |
| Calculation trace viewer | Kanishka |
| Audit log viewer `/audit` | Kanishka |
| Network monitor `/monitor` | Sahil |
| Multimodal upload + preview | Sahil |
| OCR text-region / annotation overlay (row 7) | Sahil |
| Defect detection MODEL (row 7, YOLOv8) — **NOT STARTED (DESCOPED 2026-09-19)** | **Sahil** (if ever built) |

> **Row 7 moved from Aryan to Sahil, then DESCOPED (2026-09-19).** The
> row claims no defect detection. The tool `detect_defects` returns OCR
> text-region boxes only (`kind: "text_region"`, severity always "low")
> — an annotated-text overlay, never defect findings. Real defect/anomaly
> detection (YOLOv8) is `not started` in TOOLS.md. If it is ever built it
> stays Sahil's end to end. Brief, including the three hazards that make
> this different from an ordinary model integration:
> `docs/Assignments/Sahil_Defect_Detection_Handoff.md`.

---

## 4. Already built — do not rebuild, take over

Work landed on `aryan/rag-and-graphrag` that overlaps other people's
scope. Treat these as **starting points you own from here**, not as
finished work. Each was built to unblock you, not to take the item.

| What | Where | Whose scope it lands in |
|---|---|---|
| `GraphExplorerPage` — force-directed graph, drag, zoom, label filter, search, node inspector with every property and typed edges | `frontend/src/pages/GraphExplorerPage.jsx` | **Netal** |
| `KnowledgeBasePage` — chunks, all images with OCR text, chart readings tagged ESTIMATE | `frontend/src/pages/KnowledgeBasePage.jsx` | **Netal** |
| `InstrumentationPage` — chunk/vector/graph metrics | `frontend/src/pages/InstrumentationPage.jsx` | **Netal** |
| `TurnTrace` — real plan, tool output and verdict rendered under each answer | `frontend/src/components/chat/MessageBubble.jsx` | **Advay** |
| `draft_docx` — the gated-output reference implementation | `backend/tools/documents/draft_docx.py` | **Kanishka** to copy for XLSX/PPTX |
| Approval gate backend + `/api/approvals/*` | `backend/audit/` | **Aditya** |
| Network monitor, scoped to this process tree | `backend/audit/network_monitor.py` | **Sahil** (UI) |
| `GET /api/graph/neighbourhood` — N-hop subgraph with per-node `distance` | `backend/api/routes.py` | **Netal** (hop-by-hop reveal) |

---

## 5. Netal's scope, rebalanced

The original scope was three items, two of which now have working
implementations to take over. That is not a full assignment. Added:

- **Source page preview** (`SOURCES_SPEC.md`) — render the user's own
  PDF/DOCX at the exact page a citation points to, Claude-app style. The
  backend API exists (`GET /api/preview`); the viewer does not. This is
  the single most-requested behaviour in the product and it is currently
  an empty surface.
- **Chunk / vector inspector** — take `InstrumentationPage` and
  `KnowledgeBasePage` from prototypes to real tools: filter by document,
  show the embedding neighbourhood of a chunk, show why a chunk was or
  was not retrieved for a given query.
- **Ingestion progress feed** — `GET /api/ingestion/{job_id}` reports
  per-document stage, failures with reasons, and an ETA averaged over
  completed documents. There is no UI for it, so a folder ingest is
  still a spinner to the user.
- **Retrieval trace UI** — the backend prints a full trace to the
  console (`backend/observability/turn_log.py`): every chunk with score,
  which signal admitted it, what the query was expanded to. None of it
  is visible in the app.

---

## 6. Rules that apply to everyone

1. **Every tool you add gets a row in `TOOLS.md` with your name in the
   Owner column.** The column now exists. A tool with no owner is how
   rows 38-41 ended up unassigned.
2. **Every tool that writes a file, sends anything, or touches SAP must
   register `requires_approval=True`.** The dispatcher enforces it; a
   missing flag bypasses the gate silently.
3. **No hardcoded model names outside `models.yaml`.** Two real bugs
   came from tags that were never verified against Ollama:
   `qwen2-vl:7b` and `phi-3.5-mini`, neither of which exists.
4. **No fabricated data in the UI, ever — not even as a placeholder.**
   484 lines of hardcoded demo chat shipped in `ChatPane.jsx`, including
   six invented thermocouple readings with a green "Normal" status and
   two fake "live" SAP/OPC-UA connectors. On a refinery product that is
   a fabricated safety claim, not a placeholder. Use an empty state.
5. **Do not measure one thing and report another.** This repo has three
   recorded instances of a measurement that was real but was about
   something other than what it claimed. If a number matters, state what
   was measured and under what conditions.

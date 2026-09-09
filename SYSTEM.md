# SYSTEM.md — Architecture Specification, SIH26117

## 1. Architectural Principles

1. **Zero egress, always.** Every component must run fully offline. No component is allowed a default that silently calls out (this rules out several "local-first" libraries that still phone home for telemetry — audit every dependency for this).
2. **Model-agnostic core.** The orchestrator never hardcodes a model name in logic — only in the registry config.
3. **Every claim traceable, every number verified.** Grounding and code-executed math are not optional features, they are load-bearing design constraints.
4. **Human-in-the-loop for anything irreversible.** File writes, external-facing actions, and SAP writes (if ever added) always pause for confirmation.
5. **Portable by construction.** The system must be packageable onto a drive and run on a machine that has never seen it before, without an internet connection at any point.

---

## 2. Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER (React app packaged as a native Electron │
│  desktop app — mandatory, see FRONTEND.md §4.1)               │
│  - Chat interface           - Plan graph visualizer          │
│  - Source/citation viewer   - Network monitor panel          │
│  - Output file viewer       - Audit log viewer                │
│  - Knowledge base manager   - Graph explorer                  │
└──────────────────────────┬──────────────────────────────────┘
                            │ REST/WebSocket (localhost only)
┌──────────────────────────▼──────────────────────────────────┐
│  ORCHESTRATION LAYER (Python — FastAPI backend)               │
│  - Task Router (fast classifier model)                        │
│  - Orchestrator Agent (plan decomposition, sub-agent dispatch)│
│  - Self-Verification Agent                                    │
│  - Human Approval Gate                                        │
│  - Audit Logger (writes every action to an append-only log)  │
└──────┬──────────┬──────────┬──────────┬──────────┬───────────┘
       │          │          │          │          │
┌──────▼───┐ ┌────▼─────┐ ┌──▼──────┐ ┌─▼────────┐ ┌▼─────────┐
│ Vision   │ │ Code     │ │ Reason  │ │ Math Tool│ │ Retrieval│
│ Sub-Agent│ │ Sub-Agent│ │ Sub-    │ │ Layer    │ │ Layer    │
│ (Qwen2-VL│ │ (Qwen2.5-│ │ Agent   │ │ (SymPy/  │ │ (Hybrid  │
│ )        │ │ Coder)   │ │ (Qwen2.5│ │ Maxima/  │ │ RAG +    │
│          │ │          │ │ -14B)   │ │ NumPy/   │ │ GraphRAG)│
│          │ │          │ │         │ │ CoolProp)│ │          │
└──────────┘ └────┬─────┘ └─────────┘ └──────────┘ └────┬─────┘
                   │                                      │
             ┌─────▼─────┐                          ┌─────▼──────┐
             │ Sandbox   │                          │ Vector DB  │
             │ (isolated │                          │ + Graph DB │
             │ Docker,   │                          │ (Chroma/   │
             │ no net)   │                          │ FAISS +    │
             └───────────┘                          │ Neo4j)     │
                                                     └────────────┘
┌────────────────────────────────────────────────────────────┐
│  DATA / INGESTION LAYER                                      │
│  - Document ingestion pipeline (PDF/DOCX/scans/emails)       │
│  - OCR + preprocessing pipeline (PaddleOCR, Real-ESRGAN, CV) │
│  - SAP Connector (read-only, local RFC/BAPI or export-based) │
│  - Entity/relationship extractor (graph construction)        │
└────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE / DEPLOYMENT LAYER                            │
│  - Docker Compose stack, all images pre-baked                │
│  - Model weights bundled (GGUF, quantized)                   │
│  - Bootstrap script (install.sh/.bat) — zero-internet setup  │
│  - Encrypted portable drive packaging (LUKS/VeraCrypt)        │
│  - Network monitor (eBPF/tcpdump-backed) feeding the UI panel│
└────────────────────────────────────────────────────────────┘
```

---

## 3. Component Responsibilities

| Component | Responsibility | Tech |
|---|---|---|
| Task Router | Classifies incoming request(s) into task type(s) | phi-3.5-mini via Ollama |
| Orchestrator Agent | Decomposes multi-step tasks, builds visible plan graph, dispatches to sub-agents | LangGraph (Python) |
| Vision Sub-Agent | OCR, diagram/photo understanding | Qwen2-VL-7B, PaddleOCR, Real-ESRGAN |
| Code Sub-Agent | Writes and iterates on code | Qwen2.5-Coder-7B/14B |
| Reasoning Sub-Agent | Drafting, summarization, planning text | Qwen2.5-14B |
| Math Tool Layer | Verified numeric/symbolic computation, called as a direct tool (not through an LLM) | SymPy, Maxima, NumPy/SciPy, Pint, CoolProp |
| Retrieval Layer | Hybrid dense+sparse search, graph traversal | bge-large embeddings, BM25, FAISS/Chroma, Neo4j |
| Self-Verification Agent | Checks final output against original request before completion | phi-3.5-mini (cheap, fast pass) |
| Human Approval Gate | Confirms before any write/send action | Frontend modal + backend hold state |
| Audit Logger | Append-only log of every action | SQLite (local), exportable to CSV |
| SAP Connector | Read-only structured data retrieval | RFC/BAPI (pysap) for real SAP, or CSV/table export ingestion for the demo mock dataset |
| Sandbox | Isolated code execution | Docker container, `--network none`, resource-limited |
| Network Monitor | Proves zero egress | `psutil`/`tcpdump` polling, piped to a live UI panel |

---

## 4. Data Flow — Worked Example (the PS's own example flow)

1. User uploads a scanned inspection report image → **Vision Sub-Agent** (OCR + layout extraction)
2. Extracted text + structure → **Reasoning Sub-Agent** pulls key findings, drafts approval note text
3. Draft cross-checked against **Retrieval Layer** (relevant SOPs/spec sheets) for grounding — any unsupported claim flagged
4. Any calculation needed (e.g. a verified figure to include) → **Math Tool Layer**, executed, result inserted with the code shown
5. **Self-Verification Agent** checks the draft against the original request ("did we actually produce an approval note with key findings?")
6. **Human Approval Gate** — user reviews, confirms
7. Output generator produces the final **DOCX**
8. **Audit Logger** records every step above with timestamps
9. **Network Monitor** panel shows zero external connections throughout

---

## 5. Deployment Topology

**Dev/demo (single workstation, RTX 4060 8GB):**
- Backend components on one machine via Docker Compose
- Frontend during active development runs via Vite's dev server in a browser for fast iteration (FRONTEND.md §4.1) — the Electron wrapper is built for integration testing and the final demo, not for every dev iteration
- Models: 7B-14B quantized tier (see DEPENDENCIES.md)

**Portable demo drive:**
- Backend stack: `docker save`'d images + model weights on an encrypted external SSD/HDD
- Frontend: the packaged Electron app (`.exe`/AppImage per FRONTEND.md §4.1), not a browser tab
- `install.sh` (Linux/Mac) / `install.bat` (Windows) loads the Docker images, starts the Compose backend stack, then launches the Electron app — Electron's `main.js` itself spawns/health-checks the backend on launch (FRONTEND.md §4.1), so the bootstrap script's job is to get Docker running and hand off to the app icon — no internet required at any step, no browser address bar visible at any point

**Real MRPL deployment (documented, not built in the 10 days):**
- Single on-prem GPU server (org-owned), Docker Compose or Kubernetes for multi-user scaling
- SAP Connector pointed at MRPL's actual SAP instance via RFC/BAPI, still read-only, still on the same physical network segment, no internet egress
- Larger model tier (32B-70B class) if org hardware supports it — registry swap only, per FR-4

---

## 6. Security Model Summary

- All inter-component traffic stays on localhost/internal Docker network
- Documents and vector/graph DB encrypted at rest
- SAP connector is read-only by design — no write scope requested or implemented
- RBAC tiering on knowledge base access (basic role tiers: engineer / HSE / approver / admin)
- Full audit trail, exportable, timestamped
- Portable drive itself encrypted (LUKS/VeraCrypt) since it carries both models and potentially real ingested org data during a real deployment

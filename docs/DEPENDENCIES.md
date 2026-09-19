# DEPENDENCIES.md — SIH26117

## 1. Models (all open-weight, all local inference via Ollama/llama.cpp)

**Confirmed: dual-tier design.** Dev happens on the RTX 4060 (8GB) tier below. Venue hardware is expected to be better, so the registry (per FR-4) must have the upgrade tier pre-configured and tested, not improvised on the day — swapping tiers is a `models.yaml` edit, never a code change.

| Model | Role | **Dev tier (4060, 8GB)** | **Venue tier (better GPU, if confirmed available)** |
|---|---|---|---|
| phi-3.5-mini | Fast router / classifier / verifier | Q4_K_M, ~2GB | Same — this model is cheap enough that upgrading it isn't worth the swap |
| qwen2.5-coder:7b/14b/32b | Code sub-agent | 7b, Q4_K_M, ~5GB | 32b, Q4_K_M or higher precision, if VRAM allows |
| qwen2.5:14b/32b/70b | Reasoning/drafting sub-agent | 14b, Q4_K_M, ~8-9GB (tight, CPU offload a few layers) | 32b or 70b class, per PS's own "use a smaller model if 120B-class hardware isn't available" allowance |
| qwen2.5vl:7b/32b | Vision sub-agent | 7b, Q4_K_M — **measured at ~13GB resident, not the ~5GB the weights alone suggest** (vision encoder + KV cache); does NOT fit an 8GB card whole, see note below | 32b-class VL model if available |

> **Measured VRAM note (dev box, RTX 4060 8GB).** `ollama ps` reports `qwen2.5vl:7b` at **13GB / 100% CPU** at a 4096 context — Ollama's fit check sees it doesn't fit in 8GB and places the *entire* model on CPU, which measured **76-122 seconds per chart image**. The weights-only "~5GB" estimate is what the Q4_K_M file size suggests and is misleading for capacity planning: the vision encoder and KV cache dominate. Mitigation in use: partial layer offload via Ollama's `num_gpu` option (`backend/tools/vision/chart_understanding.py`, tunable per call and via `OLLAMA_NUM_GPU_LAYERS`), which puts the heaviest layers on the GPU and leaves the rest on CPU rather than accepting all-or-nothing. Whoever sizes the venue machine should budget from the 13GB figure, not 5GB.
| bge-large-en | Embeddings for dense retrieval | fp16, <1GB | Same — embedding model doesn't benefit much from upsizing here |

**Two `models.yaml` files should exist and be tested independently before demo day:** `models.dev.yaml` (4060-safe, this is what CI/local dev runs against) and `models.venue.yaml` (upgrade tier). Whoever sets up the venue machine confirms actual available VRAM first, then either uses `models.venue.yaml` as-is or edits it — this is exactly the live "add/upgrade a model" moment FR-4 wants to demonstrate, so treat testing this switch beforehand as a rehearsal requirement, not just an infra nicety.


**VRAM budgeting note for the 4060 (8GB):** don't run reasoning + vision + coder all loaded simultaneously on a single 8GB card during dev — load/unload per active sub-agent call (Ollama handles this reasonably well), or route sequentially rather than in parallel during local testing. At the venue, if better hardware is available, all models can stay resident concurrently — this is a config change, not a code change.

## 2. Core Backend

| Library | Purpose |
|---|---|
| FastAPI | Backend API framework |
| LangGraph | Agent state graph / orchestration |
| Ollama (or llama.cpp bindings) | Local model inference server |
| SQLite | Audit log storage |
| Docker / Docker Compose | Containerization + sandbox isolation |

## 3. Vision / OCR

| Library | Purpose |
|---|---|
| PaddleOCR | Printed-text OCR |
| TrOCR (HuggingFace transformers) | Handwritten OCR fallback |
| Real-ESRGAN | Image super-resolution for degraded scans |
| OpenCV | Deskew, denoise, binarization preprocessing |
| LayoutLMv3 / table-transformer | Layout and table extraction |
| Ultralytics YOLOv8 | Intended for defect/anomaly detection — **NOT started (descoped 2026-09-19, TOOLS.md row 7); not installed today.** Row 7's tool is an OCR text-region overlay only. |
| PyMuPDF (fitz) | Rasterizing a specific PDF page to an image, for routing just that page through OCR (a mixed scanned+text-native PDF must not OCR the whole document) |
| faster-whisper | Local speech-to-text for voice-note transcription — **team addition, not PS-traceable, see REQUIREMENTS.md §6 / TOOLS.md #61 / VIBECODING_SPEC.md CARD 12**. Same fetch-once/offline-forever caching discipline as sentence-transformers (§4) — see `backend/ingestion/model_cache.py` |

## 4. Knowledge / Retrieval

| Library | Purpose |
|---|---|
| FAISS (locked: `IndexFlatIP` — see RAG_SPEC.md §2 step 6; ChromaDB was an earlier either/or option, no longer live now that RAG_SPEC.md pins the exact index type) | Vector store |
| rank_bm25 | Sparse keyword retrieval |
| Neo4j Community Edition (locked — see GRAPH_SPEC.md §2) | Graph store. **Ships with usage telemetry ON by default — verified by actually running the container.** `NEO4J_dbms_usage__report_enabled=false` is mandatory on every deployment (dev, portable drive, real MRPL), not optional hardening. |
| sentence-transformers | Embedding generation |
| python-magic | Document type detection — MIME-sniffing half of RAG_SPEC.md §2 step 1's extension+MIME reconciliation |
| pdfplumber | Text-native PDF extraction, per page (RAG_SPEC.md §2 step 2) |
| python-docx / openpyxl / xlrd | DOCX / XLSX / legacy-XLS reading for ingestion — the same python-docx/openpyxl libraries §6 uses for *generating* output, now doing double duty for *reading* input |
| langchain-text-splitters | `RecursiveCharacterTextSplitter.from_tiktoken_encoder` — RAG_SPEC.md §2 step 3's exact chunking spec (512 tokens/64 overlap, cl100k_base), reused rather than hand-rolled |
| tiktoken | Token counting for chunking (`cl100k_base`, per RAG_SPEC.md §2 step 3) |

## 5. Math / Computation (no Wolfram Alpha, no cloud math API — all local)

| Library | Purpose |
|---|---|
| SymPy | Symbolic algebra, calculus, equation solving |
| Maxima | Heavier CAS operations, shelled out to as needed |
| NumPy / SciPy | Numerical computing, curve fitting, stats |
| Pint | Unit-aware calculations (prevents unit-conversion errors) |
| CoolProp | Thermophysical properties (steam tables, fluid properties) |
| Matplotlib | Plotting for trend charts embedded in outputs |
| NetworkX | Graph math for pipeline/dependency graphs |

## 6. Output Generation

| Library | Purpose |
|---|---|
| python-docx | Word document generation |
| openpyxl | Excel generation with live formulas |
| python-pptx | PowerPoint generation |
| Piper (or similar local TTS) | Audio briefing generation (nice-to-have) |

## 7. Frontend

| Library | Purpose |
|---|---|
| React (via Vite) | UI framework |
| **Electron — mandatory** | Native desktop app shell; see FRONTEND.md §4.1 for the full packaging spec |
| **electron-builder** | Build/distribution tooling — targets Windows (NSIS or portable `.exe`) and Linux (`AppImage`) per FRONTEND.md §4.1 |
| react-flow + dagre | Plan graph visualization (DAG layout) |
| react-force-graph or vis-network | Knowledge graph visualization |
| Tailwind CSS | Styling, with a custom design-tokens file per FRONTEND.md §1 |
| Recharts | Trend charts (PSA purity, catalyst deactivation, etc.) |
| Lucide React | Icon set |

## 7.1 Electron-Specific Packaging Checklist
- [ ] `nodeIntegration: false`, `contextIsolation: true` set in every `BrowserWindow`'s `webPreferences` — verify this explicitly, don't rely on Electron's version defaults
- [ ] `preload.js` contextBridge exposes only the two IPC surfaces named in FRONTEND.md §4.1 (native file dialogs, drive status) — no broader Node access exposed to the renderer
- [ ] `main.js` backend health-check-then-spawn logic tested against both "backend already running" and "backend not running" states
- [ ] Clean child-process teardown on app quit verified (no orphaned Docker/Python processes after closing the window)
- [ ] `electron-builder` produces a working Windows portable/NSIS build AND a Linux AppImage — test both, venue hardware OS is not guaranteed

## 8. SAP Connector

| Library | Purpose |
|---|---|
| pysap or SAP RFC SDK bindings | If connecting to a real on-prem SAP instance (post-hackathon, documented not built) |
| pandas | For the demo's mock SAP-shaped dataset (CSV/table ingestion standing in for real SAP tables) |

## 9. Governance / Security

| Library | Purpose |
|---|---|
| cryptography (Python) or VeraCrypt/LUKS | Encryption at rest |
| psutil / tcpdump (via subprocess) | Network monitor data source |

## 10. Offline Packaging Checklist

- [ ] All Docker images built and `docker save`'d to `.tar` files
- [ ] All model weights (GGUF) copied to the portable drive
- [ ] All Python/Node dependencies vendored or included in Docker images (no `pip install`/`npm install` at deploy time)
- [ ] `install.sh` / `install.bat` tested on a machine with no prior setup and no internet
- [ ] Sample demo corpus (public scanned PDFs, sample P&IDs, mock SAP dataset) bundled on the drive
- [ ] Drive encrypted (VeraCrypt/LUKS), decryption step included in the bootstrap flow

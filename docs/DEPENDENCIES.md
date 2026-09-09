# DEPENDENCIES.md — SIH26117

## 1. Models (all open-weight, all local inference via Ollama/llama.cpp)

**Confirmed: dual-tier design.** Dev happens on the RTX 4060 (8GB) tier below. Venue hardware is expected to be better, so the registry (per FR-4) must have the upgrade tier pre-configured and tested, not improvised on the day — swapping tiers is a `models.yaml` edit, never a code change.

| Model | Role | **Dev tier (4060, 8GB)** | **Venue tier (better GPU, if confirmed available)** |
|---|---|---|---|
| phi-3.5-mini | Fast router / classifier / verifier | Q4_K_M, ~2GB | Same — this model is cheap enough that upgrading it isn't worth the swap |
| qwen2.5-coder:7b/14b/32b | Code sub-agent | 7b, Q4_K_M, ~5GB | 32b, Q4_K_M or higher precision, if VRAM allows |
| qwen2.5:14b/32b/70b | Reasoning/drafting sub-agent | 14b, Q4_K_M, ~8-9GB (tight, CPU offload a few layers) | 32b or 70b class, per PS's own "use a smaller model if 120B-class hardware isn't available" allowance |
| qwen2-vl:7b/32b | Vision sub-agent | 7b, Q4_K_M, ~5GB | 32b-class VL model if available |
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
| Ultralytics YOLOv8 | Defect/anomaly detection (fine-tuned on public corrosion datasets) |

## 4. Knowledge / Retrieval

| Library | Purpose |
|---|---|
| FAISS or ChromaDB | Vector store |
| rank_bm25 | Sparse keyword retrieval |
| Neo4j Community Edition (locked — see GRAPH_SPEC.md §2) | Graph store |
| sentence-transformers | Embedding generation |

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

# TOOLS.md — Master Tool Catalog, SIH26117 (Final, Complete)

This consolidates the full tool/skill catalog into one authoritative, owner-assigned reference. Categories A-G map to SYSTEM.md's sub-agents and DEPENDENCIES.md's libraries. Category H below folds in every MRPL-unit-specific tool that was previously only described in prose in the MRPL-Grounded Dossier — those are now numbered, tiered, and owned like everything else, so nothing MRPL-specific is a paragraph instead of a tracked deliverable.

**Priority tiers:** 🔴 Demo-critical (must work flawlessly) · 🟡 Strong-to-have (build if time allows past Day 8) · ⚪ Registry-listed only (architecture supports it, not necessarily polished for the live demo)

---

## A. Vision & Document Understanding — Owner: Sahil (build), Aryan (model integration)


> **Owner and Status columns added.** The table previously had neither,
> despite `CLAUDE.md` instructing every new tool to "Add a row to
> TOOLS.md with owner and priority tier". The consequence was that rows
> 38-41 — DOCX/XLSX/PPTX generation, the headline demo output under
> FR-9 and FR-12 — were owned by nobody, and the only place ownership
> was discussed was a slash in another person's assignment file
> ("Aditya/Aryan trigger it").
>
> **Status is what is true today**, verified against the live tool
> registry (17 tools registered via `backend/tools/catalog.py`) and the
> running API, not against intent. A row marked `built` has a
> registered implementation you can call through `POST /api/tools/call`
> right now. See `docs/OWNERSHIP.md` for the full matrix and for the
> layer split on file generation.

| # | Tool | Owner | Status | Priority | Notes |
|---|---|---|---|---|---|
| 1 | Printed OCR (PaddleOCR) | Aryan | built | 🔴 | Core to FR-7, FR-12. **Runs on the GPU** — `paddlepaddle-gpu` cu126, no virtualenv. Measured on an RTX 4060: warm OCR of the scanned CCR1 checklist **21.08s → 0.61s (34.8x)**, byte-identical text on both devices. Device is DETECTED, not assumed, so a CPU-only install still works and `WORKBENCH_OCR_DEVICE=cpu` forces it; `/api/health` reports which is in use, because a silent CPU fallback looks exactly like a deliberate CPU choice. The setup is fragile in one specific way and it is pinned: torch bundles cuDNN 9.10.2, paddle pins 9.5.1.17, and Windows loads one DLL per base name per process — see requirements.txt and `backend/utils/cuda_dll_path.py`. |
| 2 | Handwritten OCR (TrOCR/VLM fallback) | Aryan | built | 🔴 | Explicit PS requirement |
| 3 | Image super-resolution (Real-ESRGAN) | Aryan | built | 🟡 | Improves OCR accuracy on poor scans |
| 4 | Denoise/deskew/binarize (OpenCV) | Aryan | built | 🔴 | Cheap, always run before OCR |
| 5 | Layout & table extraction (LayoutLMv3) | Aryan | built | 🟡 | Structures inspection report tables |
| 6 | P&ID symbol/connection extraction (Qwen2.5-VL) | Aryan | not started | 🟡 | Feeds the graph layer (pipeline segment query); tuned on hydrocracker-specific line/valve tagging conventions per H1 |
| 62 | Chart image description (Qwen2.5-VL) | Aryan | built | 🟡 | For chart PICTURES with no underlying data (embedded in a PDF page, or a standalone photo) — output is always a vision-model estimate, never a verified fact; see VIBECODING_SPEC.md CARD 13. Distinct from native XLSX chart extraction (RAG_SPEC.md §2, exact/deterministic, no vision model at all) — different tool for a genuinely different problem, not two names for the same thing |
| 63 | Knowledge graph explorer (UI) | Aryan | built | 🟡 | Full-page force-directed viewer over the real Neo4j graph — drag, zoom, filter by label, search, and click a node to see every property stored on it and every relationship attached. Shows the edge TYPE explicitly, because GRAPH_SPEC.md §8's REFERENCES (merely mentioned) vs APPLIES_TO (explicitly in scope) distinction is exactly what a reviewer needs to see and cannot infer from an anonymous line. Fills the `/graph` route already reserved in FRONTEND.md §2. Owner: Aryan (implementation)/Netal (route + polish) |
| 64 | Knowledge base inspector (UI) | Aryan | built | 🟡 | What the retriever actually holds, at `/sources`: every chunk with its metadata and nearest neighbours in embedding space, and every image with each distinct understanding produced for it — OCR text (what really entered the corpus), the CARD 13 chart reading, and ground truth where the chart was generated for testing. Chart readings are labelled ESTIMATE and invented values are called out by name, because measurement showed the model stating figures for charts with no printed numbers at all (CLAUDE.md hard constraint #3). Owner: Aryan |
| 65 | Agent tool registry | Aryan | built | 🔴 | The list the orchestrator reads. Derives each tool's JSON schema from its own type hints and docstring (a hand-maintained schema drifts silently the first time a parameter is renamed), dispatches by name with validation so a hallucinated tool name is correctable rather than fatal, and enforces the safety properties centrally: `requires_approval` (hard constraint #4) is checked by the DISPATCHER, so the next person to add a file-writing tool cannot forget the gate. `is_estimate` and `computes_numbers` let a caller tell a model's guess from an executed calculation without reading each tool. Owner: Aryan |
| 66 | Trend analysis and threshold projection (NumPy) | Aryan | built | 🔴 | Row 28's numerical tier. Fits a least-squares trend to readings (WABT creep, PSA purity drift, sulphur against spec) and projects to a threshold, returning the assumption the projection rests on — "end-of-run in 47 days" read without that caveat is a maintenance decision made on an unstated assumption. Calls "flat" when the fit is unreliable rather than reporting the sign of a line fitted through noise. Owner: Aryan |
| 67 | Human approval gate (implementation) | Aditya | built | 🔴 | NFR-6 / hard constraint #4, made real. Approval is bound to a HASH OF THE EXACT ARGUMENTS (approving one file write must not authorise the next), is SINGLE-USE (or one approval silently authorises a retry loop), EXPIRES after 15 minutes (a decision made in a context that is gone should not still act), and shows the person a plain-language EFFECT rather than a function call — being shown `draft_docx({...})` is not informed consent. There is deliberately no auto-approve flag and no trusted-tools list. Owner: Aryan |
| 68 | Append-only audit log | Aditya | built | 🔴 | Every approval requested, granted, refused and executed, with who and when, in UTC. No update or delete path exists by construction — an audit log that can be edited is not evidence; a correction is a NEW entry referencing the earlier one. fsync per line, because a log entry lost to a crash during the action it describes implies the action never happened. Owner: Aryan |
| 69 | Task planner (implementation) | Aryan | built | 🔴 | FR-5 / AGENTS_SPEC §3-§4, the judge-facing plan graph. Prompt is §4 VERBATIM. The value is the validation around it: local models emit dependency graphs with dangling references, self-dependencies, duplicate step_ids and cycles, and every one of those produces a plan that LOOKS fine and then hangs at dispatch — indistinguishable from slow inference, the worst failure mode available. Each is repaired rather than dropped (the step is usually sound, only its stated ordering is wrong), so `validate_plan` always returns something that can actually start. Owner: Aryan |
| 70 | Sub-agent dispatch + §6 contracts (implementation) | Aryan | built | 🔴 | AGENTS_SPEC §6's allowed/forbidden table as CODE, not prose: each sub-agent gets a closed tool set and the dispatcher refuses anything outside it, so `vision_agent` cannot write a file because `draft_docx` is not reachable — not because it is trusted not to try. `dispatch` releases ALL ready steps at once (the point of depends_on) and marks them running so the same step is never handed out twice. `code_agent` refuses loudly pending Aditya's sandbox rather than reporting a step done without running it. Owner: Aryan |
| 71 | Self-verification agent (implementation) | Aryan | built | 🟡 | AGENTS_SPEC §5, prompt verbatim. Fails CLOSED: any unreadable verdict is treated as unverified, because defaulting to satisfied means a malformed response silently becomes a pass — the one direction this node must never fail in. After 2 re-plan cycles it produces a THIRD state, UNCONFIRMED, not a pass or a fail: an output that failed verification and is presented identically to one that passed makes verification actively harmful, since it creates confidence it did not earn. Owner: Aryan |
| 15 | Contradiction detection across documents | Aryan | built | 🟡 | **IMPLEMENTED** — `backend/retrieval/contradiction.py`. The hard part is false positives, not detection: a detector that flags legitimate variation gets switched off within a day and then catches nothing. Four non-contradictions are excluded by construction — same limit in different units (compared through Pint, so 10 ppm vs 0.001% does not fire), readings vs limits, dated time-series values, and different equipment sharing a word. Comparison is fully deterministic; no model decides whether two values disagree. Extraction is injectable (LLM for recall) but defaults to patterns, because a safety artifact whose contents change between runs on identical input is not one anybody can act on. Owner: Aryan |
| 7 | Defect/anomaly detection (YOLOv8) | Sahil | built | 🟡 | **IMPLEMENTED (OCR-box stage, fully offline)** — `backend/tools/vision/defect_detection.py`, registered as tool `detect_defects`. Detects defect/anomaly regions on an inspection image and returns overlay contract-shaped boxes (`id, label, confidence, box{xmin,ymin,xmax,ymax}, severity`), rendered by the frontend DefectOverlay. The current detection source is local OCR, not YOLO: every text line becomes a detection box labeled by the recognized text, severity = OCR-confidence band (capped at "high", never "critical" — a sub-threshold OCR reading is a transcription-confidence signal, not a defect classification). Feeding pipeline + detector swap are done: uploaded images flow through ChatPane's `detect_defects` call and the overlay mounts from real backend output; the YOLOv8 detector drops into the same output contract later. THREE CONSTRAINTS that must survive the detector upgrade: (1) hard constraint #1 — ultralytics phones home 4 ways (analytics on import AND predict, weight download from GitHub, Arial.ttf fetch), all four must be disabled or proven absent before the import, offline test pattern in `test_defect_detection.py`; (2) torch/cuDNN are deliberately NOT in requirements.txt — keep it that way, Windows loads ONE cuDNN DLL per name per process, a CUDA-adjacent install can move it and break both frameworks, and extras belong in a venv not the shared env; (3) accuracy claims name their corpus — a public fine-tune number describes THAT dataset, not MRPL photos. Owner: Sahil. |
| 8 | Photo-to-report matching | Aryan | not started | ⚪ | Registry-listed |
| 9 | Document type classifier | Aryan | built | 🔴 | **IMPLEMENTED** — `backend/ingestion/document_classifier.py`. The KIND of document, not its format: a P&ID and a scanned checklist are both PNGs and need opposite handling (one is a diagram whose value is the connections between tags, the other a table whose rows are findings), so format alone cannot route them. Rules rather than a model, for two reasons: a model call per document is the dominant cost of ingesting a corpus of any size, and an operator asking why their document was treated as correspondence would get no answer — every classification here names the phrases that decided it. Returns `unknown` rather than the best of a bad set, because forcing a guess is how a P&ID gets parsed as a spreadsheet. Confidence is the margin over the runner-up, not a probability, and is not presented as one. **Measured 13/13 against MRPL_RAG_Test_Corpus's own folder labels** (`backend/evaluation/classifier_accuracy.py`), which were written before the classifier existed and so cannot have been fitted to it. Owner: Aryan |
| 10 | Image diffing/change detection | Aryan | not started | ⚪ | Registry-listed |
| 11 | Signature/stamp detection | Aryan | not started | ⚪ | Nice MRPL-approval-workflow touch, low priority |
| 59 | Vessel/cargo document processing (VLCC manifests, port paperwork) | Aryan | not started | 🟡 | MRPL-specific — OCR + structured extraction → auto-populated tracking sheet; feeds SPM "Mangala-1" workflow, Owner: Sahil (UI)/Aryan (extraction logic) |
| 61 | Voice note transcription (local speech-to-text) | Aryan | built | 🟡 | **Team addition — not traceable to a PS26117 line.** Extends FR-7's document-modality handling to audio input (depot/HQ voice notes, shift handovers). Fully offline (faster-whisper, fetch-once/offline-forever pattern per `model_cache.py`). VIBECODING_SPEC.md CARD 12, Owner: Aryan. See REQUIREMENTS.md §6 for how this is kept honestly separate from PS-derived scope. |

## B. Knowledge & Retrieval (RAG/GraphRAG) — Owner: Aryan (core), Netal (UI)

| # | Tool | Owner | Status | Priority | Notes |
|---|---|---|---|---|---|
| 12 | Hybrid dense+sparse retrieval | Aryan | built | 🔴 | Core to FR-10 |
| 13 | Entity/relationship extraction for graph | Aryan | built | 🔴 | Needed for the signature graph query |
| 14 | Knowledge graph store + query (Neo4j) | Aryan | built | 🔴 | Pipeline-segment / valve-reference query, demoed against real segment names Mangalore–Hassan–Neriya–Devangonthi |
| 15 | Contradiction detection across documents | Aryan | built | 🟡 | Strong safety-relevant differentiator |
| 16 | Version/revision tracking | Netal | not started | 🟡 | SOP-currency checking |
| 17 | Source-grounded citation on every claim | Aryan | built | 🔴 | Non-negotiable per NFR-4 |
| 18 | Correspondence/email summarization | Netal | not started | 🟡 | Generic depot-to-HQ use case |
| 19 | Cross-reference resolver | Aryan | not started | ⚪ | Registry-listed |
| 57 | Aromatic Complex ↔ refinery cross-document reconciliation | Aryan | not started | ⚪ | MRPL-specific — reconciles refinery-side and MSEZ Aromatic Complex-side documentation on shared feedstock/utilities; non-obvious, genuinely MRPL-specific win, Owner: Aryan |
| 60 | Multi-location correspondence summarizer (Kasargod/Hindupur/Hosur depots) | Netal | not started | 🟡 | Specializes tool 18 for MRPL's named depots — condenses depot-to-HQ threads, flags anything needing HQ approval action, Owner: Aryan (logic)/Netal (UI) |

## C. Reasoning, Planning & Orchestration — Owner: Aryan (logic), Aditya (infra)

| # | Tool | Owner | Status | Priority | Notes |
|---|---|---|---|---|---|
| 20 | Task planner with visible plan graph | Aryan | built | 🔴 | FR-5, judge-facing visual |
| 21 | Multi-model router | Aryan | built | 🔴 | FR-3, FR-11 |
| 22 | Sub-agent spawning per modality | Aryan | built | 🔴 | Core architecture |
| 23 | Self-verification agent | Aryan | built | 🟡 | Same deliverable as row 71 — see there. `backend/orchestrator/verification.py`, AGENTS_SPEC §5, fails CLOSED. |
| 24 | Human approval gate | Aryan | built | 🔴 | Same deliverable as rows 67-68 — see there. `backend/audit/approval_gate.py`: argument-hashed, single-use, expiring, no auto-approve flag. |
| 25 | Long-running task checkpointing | Aryan | not started | ⚪ | Registry-listed |

## D. Computation — Owner: Aryan (tool wiring), Sahil (trace UI)

| # | Tool | Owner | Status | Priority | Notes |
|---|---|---|---|---|---|
| 26 | SymPy symbolic engine | Aryan | built | 🔴 | `backend/tools/math/symbolic_calc.py`, registered as `evaluate_expression`. Never `eval()`. No Wolfram Alpha — fully local. |
| 27 | Maxima CAS | Aryan | not started | 🟡 | Heavier symbolic ops |
| 28 | NumPy/SciPy numerical + stats | Aryan | built | 🔴 | Trend analysis, curve fitting |
| 29 | Pint unit-aware calculations | Aryan | built | 🔴 | `backend/tools/math/unit_calc.py`, registered as `evaluate_unit_expression`. Raises on incompatible dimensions rather than coercing. CARD 10. |
| 30 | CoolProp thermophysical properties | Aryan | built | 🟡 | `backend/tools/math/thermophysical.py`, registered as `lookup_thermophysical_property`. CARD 11. Deliberately excluded from the chat tool set — recorded plant values live in documents, and its description reads as if it would know them (see agent_loop.py's CHAT_TOOLS note). |
| 31 | Matplotlib plotting | Aryan | built | 🔴 | Embedded charts in outputs |
| 32 | NetworkX graph math | Netal | not started | 🟡 | Pipeline dependency graphs |
| 51 | Catalyst deactivation / WABT creep trend model (hydrocracker) | Aryan | built | 🟡 | MRPL-specific — SciPy curve-fitting on historical operating data, flags approaching catalyst change-out, math shown step by step per NFR-5. Owner: Aryan |
| 52 | Hydrogen balance calculator (CCR ↔ hydrotreating units) | Aryan | built | 🟡 | MRPL-specific — Pint-based unit-aware mass balance, prevents unit-conversion errors on H2 byproduct tracking. Owner: Aryan |
| 53 | PSA hydrogen purity trend dashboard | Aryan | built | 🟡 | MRPL-specific — ingests PSA purity logs, plots against the 99.9% target (tool 31), flags drift. Owner: Aryan (data)/Kanishka (chart UI) |

## E. Code & Sandbox — Owner: Aditya

| # | Tool | Owner | Status | Priority | Notes |
|---|---|---|---|---|---|
| 33 | Code generation (routed) | Aditya | built | 🔴 | FR-13 |
| 34 | Sandboxed execution (Docker, no network) | Aditya | built | 🔴 | FR-13, NFR core. **BUILT** — warm Docker pool, `--network none`, memory/CPU limits, read-only root, timeout. Egress isolation is PROVEN by test (`test_sandbox.py` asserts the container cannot reach 1.1.1.1), not merely configured. Now driven end to end by `backend/orchestrator/code_generation.py`: qwen2.5-coder:7b writes the program, the sandbox runs it, and the OUTPUT is checked — a program that exits 0 and prints nothing is reported FAILED, because "ran" is not "verified". Measured: "first 10 Fibonacci numbers" → `[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]`, 9.6s to generate, 4.0s to run warm. |
| 35 | Automated test generation + run | Aditya | not started | 🟡 | Strengthens the verification story |
| 36 | Static analysis/linting pass | Aditya | not started | ⚪ | Registry-listed |
| 37 | Internal tool scaffolding | Aditya | not started | ⚪ | Registry-listed |

## F. Output Generation — Owner: Kanishka

| # | Tool | Owner | Status | Priority | Notes |
|---|---|---|---|---|---|
| 38 | DOCX generation (python-docx) | Aryan | built | 🔴 | FR-9, FR-12 — the headline demo output; pre-tuned with hydrocracker/CCR terminology per H1 |
| 39 | XLSX generation with live formulas | Kanishka | built | 🔴 | FR-9 — `draft_xlsx.py` with live formulas, approval gate, unsourced amber markers, and structural citations. |
| 40 | PPTX generation | Aditya / Aryan | built | 🔴 | FR-9 — `prepare_deck` (grounded storyline, every figure verified against the source) + approval-gated `generate_deck`, rendered by the code-driven deck design system (native charts/tables, text measured to fit, no slide cap). |
| 40a | PDF generation & export | Kanishka | built | 🟡 | FR-9, FR-12 — `generate_pdf.py` via PyMuPDF (fitz) with approval gate, structural citations, unsourced warning banner, and estimate markers. |
| 41 | Calculation trace documents | Aryan | built | 🔴 | NFR-5 |
| 42 | Audio briefing (Piper TTS) | Kanishka | not started | ⚪ | Polish item |
| 43 | Redaction tool | Kanishka | not started | 🟡 | Confidentiality-relevant differentiator |
| 54 | Novolen grade-changeover checklist generator | Kanishka | not started | 🟡 | MRPL-specific — retrieval-grounded checklist for gas-phase Ziegler-Natta grade transitions, sourced from the actual SOP for that transition. Owner: Aryan (retrieval)/Kanishka (checklist UI) |
| 55 | Novolen batch quality report generator | Kanishka | not started | 🟡 | MRPL-specific — auto-drafts a QA summary DOCX from lab data + spec sheet comparison (uses tool 38). Owner: Kanishka |
| 56 | Merox sulphur-spec compliance checker | Aryan | built | 🟡 | **IMPLEMENTED** — `backend/tools/spec_compliance.py`. Compliance is COMPUTED from the reading and the limit, never read from the Status column the corpus sheet already carries: a tool that reports that column adds nothing a reader could not see and inherits every mistake in it. Where the document states a status of its own, the two are compared, and a disagreement is the finding that matters most — a sheet marked OK on a reading that exceeds its limit is a compliance failure that has already passed somebody's review, and it is invisible to everyone reading the status column. Unit-aware through Pint (row 29): 10 ppm and 0.001% are the same limit, and a reading whose units cannot be reconciled is reported UNCOMPARABLE rather than silently compared. "Near limit" is a stated policy (default 10% of the limit), reported in every result, because how near counts as near belongs to the plant. Fully deterministic — no model — so the same sheet gives the same answer every run. Owner: Aryan (logic)/Netal (flagging UI) |
| 58 | Aromatic Complex benzene safety-note drafting | Kanishka | not started | 🔴 | MRPL-specific — combines tool 17 (hard refuse-to-hallucinate grounding) + tool 38 (DOCX drafting), demoed as a dedicated safety-critical scenario, not a generic drafting example. This is the strongest safety USP in the catalog — treat as demo-critical even though its underlying components are shared with other 🔴 tools. Owner: Aryan (grounding)/Kanishka (doc output) |

## G. Governance, Audit & Trust — Owner: Aditya (backend), Kanishka (UI)

| # | Tool | Owner | Status | Priority | Notes |
|---|---|---|---|---|---|
| 44 | Live network monitor panel | Aditya | built | 🔴 | FR-1, FR-15 — single most important judge-facing proof |
| 45 | Full audit log | Aditya | built | 🔴 | NFR-7 |
| 46 | RBAC on knowledge base | Sahil | not started | 🟡 | Basic tiers sufficient for demo |
| 47 | Model provenance tracking | Sahil | not started | ⚪ | Registry-listed |
| 48 | Encrypted-at-rest storage | **Aditya** | not started | 🔴 | NFR-3. Owner corrected from Sahil: `docs/OWNERSHIP.md` line 119 assigns "Encryption at rest" to Aditya and is the tie-breaker per CLAUDE.md, and `Aditya.md`'s own scope lists it. Covers the persisted stores — `backend/memory/*.db`, the FAISS index and its SQLite sidecar, `backend/audit/*.jsonl`, and `outputs/`. AES-256 or equivalent per REQUIREMENTS.md NFR-3. |
| 49 | SAP read-only connector | Aditya | not started | 🔴 | REQUIREMENTS.md §5 — highest-leverage MRPL-specific USP; MRPL has run SAP live since Oct 2010 across Finance, Materials, Maintenance, Projects, Marketing, Production, QA |
| 50 | Portable/air-gapped packaging | Aditya | not started | 🔴 | NFR-2 |

---

## H. MRPL Unit-by-Unit Coverage Map (cross-reference — every unit, every tool touching it)

| MRPL Unit | Tools that cover it |
|---|---|
| Hydrocracker (×2, MRPL's signature differentiator) | 6 (P&ID tuning), 38 (terminology-tuned drafting), 51 (catalyst/WABT trend) |
| CCR (×2, UOP tech) | 52 (H2 balance calculator) |
| LPG/Kero Merox | 56 (sulphur-spec compliance checker) |
| Hydrogen/PSA units (×3) | 53 (purity trend dashboard), 30 (CoolProp steam/fluid properties) |
| Novolen Polypropylene plant | 54 (grade-changeover checklist), 55 (batch quality report) |
| Aromatic Complex (MSEZ, Para-Xylene/Benzene) | 57 (cross-document reconciliation), 58 (benzene safety-note drafting) |
| SPM "Mangala-1" + Petronet MHB pipeline | 59 (vessel/cargo processing), 14 (pipeline-segment graph query, real segment names) |
| Marketing depots (Kasargod/Hindupur/Hosur) | 60 (multi-location correspondence summarizer) |
| SAP ERP (all modules, live since 2010) | 49 (read-only connector) |

If a judge asks "what does this actually do for us, unit by unit" — this table is the answer, and every row traces to a numbered, owned, tiered tool above, not a claim in a slide.

---

## I. Live Demo Script (final, timed)

1. **[0:00-1:00]** Boot from portable drive (Electron app), system live, network monitor panel visible and reading zero from the start
2. **[1:00-3:00]** Flow 1 — scanned inspection report → OCR → findings extraction → DOCX approval note drafted, grounded and cited (tools 1, 12, 17, 38)
3. **[3:00-4:30]** Flow 2 — coding task, written and run in sandbox, test result shown (tools 33, 34)
4. **[4:30-6:00]** Flow 3 — P&ID/photo multimodal understanding, structured extraction shown (tool 6)
5. **[6:00-7:00]** Router demoed switching models across the above 3 flows; live model-add to `models.yaml` (tool 21, FR-4)
6. **[7:00-8:00]** Signature graph query on the Mangalore-Hassan pipeline segment (tool 14); SAP connector query grounding a maintenance summary (tool 49)
7. **[8:00-9:00]** *If time allows:* benzene/Aromatic Complex safety-note drafting (tool 58) — the strongest safety-specific USP, worth a dedicated beat if the schedule has room
8. **[9:00-close]** Network monitor still reading zero; audit log exported live as final proof (tools 44, 45)

---

## J. Design Principle Restated

No Wolfram Alpha, no cloud math API, no cloud anything. Every computational claim (tools 26-32, 51-53) is backed by an open-source library executing locally. MRPL cannot use a tool that phones out to evaluate a hydrocracker mass balance, and neither can this system.
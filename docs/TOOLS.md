# TOOLS.md — Master Tool Catalog, SIH26117 (Final, Complete)

This consolidates the full tool/skill catalog into one authoritative, owner-assigned reference. Categories A-G map to SYSTEM.md's sub-agents and DEPENDENCIES.md's libraries. Category H below folds in every MRPL-unit-specific tool that was previously only described in prose in the MRPL-Grounded Dossier — those are now numbered, tiered, and owned like everything else, so nothing MRPL-specific is a paragraph instead of a tracked deliverable.

**Priority tiers:** 🔴 Demo-critical (must work flawlessly) · 🟡 Strong-to-have (build if time allows past Day 8) · ⚪ Registry-listed only (architecture supports it, not necessarily polished for the live demo)

---

## A. Vision & Document Understanding — Owner: Sahil (build), Aryan (model integration)

| # | Tool | Priority | Notes |
|---|---|---|---|
| 1 | Printed OCR (PaddleOCR) | 🔴 | Core to FR-7, FR-12 |
| 2 | Handwritten OCR (TrOCR/VLM fallback) | 🔴 | Explicit PS requirement |
| 3 | Image super-resolution (Real-ESRGAN) | 🟡 | Improves OCR accuracy on poor scans |
| 4 | Denoise/deskew/binarize (OpenCV) | 🔴 | Cheap, always run before OCR |
| 5 | Layout & table extraction (LayoutLMv3) | 🟡 | Structures inspection report tables |
| 6 | P&ID symbol/connection extraction (Qwen2.5-VL) | 🟡 | Feeds the graph layer (pipeline segment query); tuned on hydrocracker-specific line/valve tagging conventions per H1 |
| 62 | Chart image description (Qwen2.5-VL) | 🟡 | For chart PICTURES with no underlying data (embedded in a PDF page, or a standalone photo) — output is always a vision-model estimate, never a verified fact; see VIBECODING_SPEC.md CARD 13. Distinct from native XLSX chart extraction (RAG_SPEC.md §2, exact/deterministic, no vision model at all) — different tool for a genuinely different problem, not two names for the same thing |
| 63 | Knowledge graph explorer (UI) | 🟡 | Full-page force-directed viewer over the real Neo4j graph — drag, zoom, filter by label, search, and click a node to see every property stored on it and every relationship attached. Shows the edge TYPE explicitly, because GRAPH_SPEC.md §8's REFERENCES (merely mentioned) vs APPLIES_TO (explicitly in scope) distinction is exactly what a reviewer needs to see and cannot infer from an anonymous line. Fills the `/graph` route already reserved in FRONTEND.md §2. Owner: Aryan (implementation)/Netal (route + polish) |
| 64 | Knowledge base inspector (UI) | 🟡 | What the retriever actually holds, at `/sources`: every chunk with its metadata and nearest neighbours in embedding space, and every image with each distinct understanding produced for it — OCR text (what really entered the corpus), the CARD 13 chart reading, and ground truth where the chart was generated for testing. Chart readings are labelled ESTIMATE and invented values are called out by name, because measurement showed the model stating figures for charts with no printed numbers at all (CLAUDE.md hard constraint #3). Owner: Aryan |
| 65 | Agent tool registry | 🔴 | The list the orchestrator reads. Derives each tool's JSON schema from its own type hints and docstring (a hand-maintained schema drifts silently the first time a parameter is renamed), dispatches by name with validation so a hallucinated tool name is correctable rather than fatal, and enforces the safety properties centrally: `requires_approval` (hard constraint #4) is checked by the DISPATCHER, so the next person to add a file-writing tool cannot forget the gate. `is_estimate` and `computes_numbers` let a caller tell a model's guess from an executed calculation without reading each tool. Owner: Aryan |
| 66 | Trend analysis and threshold projection (NumPy) | 🔴 | Row 28's numerical tier. Fits a least-squares trend to readings (WABT creep, PSA purity drift, sulphur against spec) and projects to a threshold, returning the assumption the projection rests on — "end-of-run in 47 days" read without that caveat is a maintenance decision made on an unstated assumption. Calls "flat" when the fit is unreliable rather than reporting the sign of a line fitted through noise. Owner: Aryan |
| 67 | Human approval gate (implementation) | 🔴 | NFR-6 / hard constraint #4, made real. Approval is bound to a HASH OF THE EXACT ARGUMENTS (approving one file write must not authorise the next), is SINGLE-USE (or one approval silently authorises a retry loop), EXPIRES after 15 minutes (a decision made in a context that is gone should not still act), and shows the person a plain-language EFFECT rather than a function call — being shown `draft_docx({...})` is not informed consent. There is deliberately no auto-approve flag and no trusted-tools list. Owner: Aryan |
| 68 | Append-only audit log | 🔴 | Every approval requested, granted, refused and executed, with who and when, in UTC. No update or delete path exists by construction — an audit log that can be edited is not evidence; a correction is a NEW entry referencing the earlier one. fsync per line, because a log entry lost to a crash during the action it describes implies the action never happened. Owner: Aryan |
| 69 | Task planner (implementation) | 🔴 | FR-5 / AGENTS_SPEC §3-§4, the judge-facing plan graph. Prompt is §4 VERBATIM. The value is the validation around it: local models emit dependency graphs with dangling references, self-dependencies, duplicate step_ids and cycles, and every one of those produces a plan that LOOKS fine and then hangs at dispatch — indistinguishable from slow inference, the worst failure mode available. Each is repaired rather than dropped (the step is usually sound, only its stated ordering is wrong), so `validate_plan` always returns something that can actually start. Owner: Aryan |
| 70 | Sub-agent dispatch + §6 contracts (implementation) | 🔴 | AGENTS_SPEC §6's allowed/forbidden table as CODE, not prose: each sub-agent gets a closed tool set and the dispatcher refuses anything outside it, so `vision_agent` cannot write a file because `draft_docx` is not reachable — not because it is trusted not to try. `dispatch` releases ALL ready steps at once (the point of depends_on) and marks them running so the same step is never handed out twice. `code_agent` refuses loudly pending Aditya's sandbox rather than reporting a step done without running it. Owner: Aryan |
| 71 | Self-verification agent (implementation) | 🟡 | AGENTS_SPEC §5, prompt verbatim. Fails CLOSED: any unreadable verdict is treated as unverified, because defaulting to satisfied means a malformed response silently becomes a pass — the one direction this node must never fail in. After 2 re-plan cycles it produces a THIRD state, UNCONFIRMED, not a pass or a fail: an output that failed verification and is presented identically to one that passed makes verification actively harmful, since it creates confidence it did not earn. Owner: Aryan |
| 15 | Contradiction detection across documents | 🟡 | **IMPLEMENTED** — `backend/retrieval/contradiction.py`. The hard part is false positives, not detection: a detector that flags legitimate variation gets switched off within a day and then catches nothing. Four non-contradictions are excluded by construction — same limit in different units (compared through Pint, so 10 ppm vs 0.001% does not fire), readings vs limits, dated time-series values, and different equipment sharing a word. Comparison is fully deterministic; no model decides whether two values disagree. Extraction is injectable (LLM for recall) but defaults to patterns, because a safety artifact whose contents change between runs on identical input is not one anybody can act on. Owner: Aryan |
| 7 | Defect/anomaly detection (YOLOv8) | 🟡 | Public dataset fine-tune |
| 8 | Photo-to-report matching | ⚪ | Registry-listed |
| 9 | Document type classifier | 🔴 | Routes scans to correct pipeline |
| 10 | Image diffing/change detection | ⚪ | Registry-listed |
| 11 | Signature/stamp detection | ⚪ | Nice MRPL-approval-workflow touch, low priority |
| 59 | Vessel/cargo document processing (VLCC manifests, port paperwork) | 🟡 | MRPL-specific — OCR + structured extraction → auto-populated tracking sheet; feeds SPM "Mangala-1" workflow, Owner: Sahil (UI)/Aryan (extraction logic) |
| 61 | Voice note transcription (local speech-to-text) | 🟡 | **Team addition — not traceable to a PS26117 line.** Extends FR-7's document-modality handling to audio input (depot/HQ voice notes, shift handovers). Fully offline (faster-whisper, fetch-once/offline-forever pattern per `model_cache.py`). VIBECODING_SPEC.md CARD 12, Owner: Aryan. See REQUIREMENTS.md §6 for how this is kept honestly separate from PS-derived scope. |

## B. Knowledge & Retrieval (RAG/GraphRAG) — Owner: Aryan (core), Netal (UI)

| # | Tool | Priority | Notes |
|---|---|---|---|
| 12 | Hybrid dense+sparse retrieval | 🔴 | Core to FR-10 |
| 13 | Entity/relationship extraction for graph | 🔴 | Needed for the signature graph query |
| 14 | Knowledge graph store + query (Neo4j) | 🔴 | Pipeline-segment / valve-reference query, demoed against real segment names Mangalore–Hassan–Neriya–Devangonthi |
| 15 | Contradiction detection across documents | 🟡 | Strong safety-relevant differentiator |
| 16 | Version/revision tracking | 🟡 | SOP-currency checking |
| 17 | Source-grounded citation on every claim | 🔴 | Non-negotiable per NFR-4 |
| 18 | Correspondence/email summarization | 🟡 | Generic depot-to-HQ use case |
| 19 | Cross-reference resolver | ⚪ | Registry-listed |
| 57 | Aromatic Complex ↔ refinery cross-document reconciliation | ⚪ | MRPL-specific — reconciles refinery-side and MSEZ Aromatic Complex-side documentation on shared feedstock/utilities; non-obvious, genuinely MRPL-specific win, Owner: Aryan |
| 60 | Multi-location correspondence summarizer (Kasargod/Hindupur/Hosur depots) | 🟡 | Specializes tool 18 for MRPL's named depots — condenses depot-to-HQ threads, flags anything needing HQ approval action, Owner: Aryan (logic)/Netal (UI) |

## C. Reasoning, Planning & Orchestration — Owner: Aryan (logic), Aditya (infra)

| # | Tool | Priority | Notes |
|---|---|---|---|
| 20 | Task planner with visible plan graph | 🔴 | FR-5, judge-facing visual |
| 21 | Multi-model router | 🔴 | FR-3, FR-11 |
| 22 | Sub-agent spawning per modality | 🔴 | Core architecture |
| 23 | Self-verification agent | 🟡 | Quality/trust booster |
| 24 | Human approval gate | 🔴 | NFR-6, safety-critical |
| 25 | Long-running task checkpointing | ⚪ | Registry-listed |

## D. Computation — Owner: Aryan (tool wiring), Sahil (trace UI)

| # | Tool | Priority | Notes |
|---|---|---|---|
| 26 | SymPy symbolic engine | 🔴 | No Wolfram Alpha — fully local |
| 27 | Maxima CAS | 🟡 | Heavier symbolic ops |
| 28 | NumPy/SciPy numerical + stats | 🔴 | Trend analysis, curve fitting |
| 29 | Pint unit-aware calculations | 🔴 | Prevents unit-error class entirely — VIBECODING_SPEC.md CARD 10 |
| 30 | CoolProp thermophysical properties | 🟡 | Refinery-specific steam/fluid properties; backs tool 53's steam-table lookups — VIBECODING_SPEC.md CARD 11 |
| 31 | Matplotlib plotting | 🔴 | Embedded charts in outputs |
| 32 | NetworkX graph math | 🟡 | Pipeline dependency graphs |
| 51 | Catalyst deactivation / WABT creep trend model (hydrocracker) | 🟡 | MRPL-specific — SciPy curve-fitting on historical operating data, flags approaching catalyst change-out, math shown step by step per NFR-5. Owner: Aryan |
| 52 | Hydrogen balance calculator (CCR ↔ hydrotreating units) | 🟡 | MRPL-specific — Pint-based unit-aware mass balance, prevents unit-conversion errors on H2 byproduct tracking. Owner: Aryan |
| 53 | PSA hydrogen purity trend dashboard | 🟡 | MRPL-specific — ingests PSA purity logs, plots against the 99.9% target (tool 31), flags drift. Owner: Aryan (data)/Kanishka (chart UI) |

## E. Code & Sandbox — Owner: Aditya

| # | Tool | Priority | Notes |
|---|---|---|---|
| 33 | Code generation (routed) | 🔴 | FR-13 |
| 34 | Sandboxed execution (Docker, no network) | 🔴 | FR-13, NFR core |
| 35 | Automated test generation + run | 🟡 | Strengthens the verification story |
| 36 | Static analysis/linting pass | ⚪ | Registry-listed |
| 37 | Internal tool scaffolding | ⚪ | Registry-listed |

## F. Output Generation — Owner: Kanishka

| # | Tool | Priority | Notes |
|---|---|---|---|
| 38 | DOCX generation (python-docx) | 🔴 | FR-9, FR-12 — the headline demo output; pre-tuned with hydrocracker/CCR terminology per H1 |
| 39 | XLSX generation with live formulas | 🔴 | FR-9 |
| 40 | PPTX generation | 🟡 | FR-9 |
| 41 | Calculation trace documents | 🔴 | NFR-5 |
| 42 | Audio briefing (Piper TTS) | ⚪ | Polish item |
| 43 | Redaction tool | 🟡 | Confidentiality-relevant differentiator |
| 54 | Novolen grade-changeover checklist generator | 🟡 | MRPL-specific — retrieval-grounded checklist for gas-phase Ziegler-Natta grade transitions, sourced from the actual SOP for that transition. Owner: Aryan (retrieval)/Kanishka (checklist UI) |
| 55 | Novolen batch quality report generator | 🟡 | MRPL-specific — auto-drafts a QA summary DOCX from lab data + spec sheet comparison (uses tool 38). Owner: Kanishka |
| 56 | Merox sulphur-spec compliance checker | 🟡 | MRPL-specific — cross-references lab results against product spec sheets in the KB, flags near-limit readings automatically. Owner: Aryan (logic)/Netal (flagging UI) |
| 58 | Aromatic Complex benzene safety-note drafting | 🔴 | MRPL-specific — combines tool 17 (hard refuse-to-hallucinate grounding) + tool 38 (DOCX drafting), demoed as a dedicated safety-critical scenario, not a generic drafting example. This is the strongest safety USP in the catalog — treat as demo-critical even though its underlying components are shared with other 🔴 tools. Owner: Aryan (grounding)/Kanishka (doc output) |

## G. Governance, Audit & Trust — Owner: Aditya (backend), Kanishka (UI)

| # | Tool | Priority | Notes |
|---|---|---|---|
| 44 | Live network monitor panel | 🔴 | FR-1, FR-15 — single most important judge-facing proof |
| 45 | Full audit log | 🔴 | NFR-7 |
| 46 | RBAC on knowledge base | 🟡 | Basic tiers sufficient for demo |
| 47 | Model provenance tracking | ⚪ | Registry-listed |
| 48 | Encrypted-at-rest storage | 🔴 | NFR-3 |
| 49 | SAP read-only connector | 🔴 | REQUIREMENTS.md §5 — highest-leverage MRPL-specific USP; MRPL has run SAP live since Oct 2010 across Finance, Materials, Maintenance, Projects, Marketing, Production, QA |
| 50 | Portable/air-gapped packaging | 🔴 | NFR-2 |

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
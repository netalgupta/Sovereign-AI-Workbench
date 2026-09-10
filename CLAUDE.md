# CLAUDE.md — Agentic Coding Guide for SIH26117
This file is read by Claude Code / Antigravity (or any coding agent) working in this repository. Keep it accurate as the repo evolves — this is what the AI coding agent uses as ground truth for how to work here.

## Project Summary
Sovereign On-Premise Agentic AI Workbench for MRPL (PS26117). Fully offline, multi-model, agentic system. See REQUIREMENTS.md, SYSTEM.md, TOOLS.md, DEPENDENCIES.md in this same folder for full spec — read those before making architectural changes.

## Repo Structure (target layout)
```
/backend
  /orchestrator      — LangGraph agent graph, router, sub-agent dispatch
  /tools             — one module per tool in TOOLS.md, each with a defined schema
  /connectors        — SAP connector, document ingestion
  /sandbox           — Docker sandbox execution wrapper
  /audit             — audit logging module
  main.py            — FastAPI entrypoint
/frontend
  /electron          — main.js, preload.js (mandatory Electron shell, see FRONTEND.md §4.1)
  /src/components    — chat, plan graph, network monitor, source viewer, etc.
/models
  models.yaml        — model registry config (see DEPENDENCIES.md)
/deploy
  docker-compose.yml
  install.sh / install.bat
/docs                — this documentation set
```

## Hard Constraints (never violate these when generating code)
1. **No outbound network calls, anywhere, ever.** Any library or code path that could phone home (telemetry, update checks, CDN-hosted assets) must be disabled or replaced. If unsure whether a library does this, flag it rather than assume.
2. **No hardcoded model names in orchestration logic.** Only `models.yaml` names a model. The router/orchestrator reads the registry.
3. **No math computed by an LLM without a tool call.** Any numeric result must come from an executed SymPy/NumPy/etc. call, never from the LLM "doing the arithmetic in its head."
4. **No file write, send, or SAP write action without a human-approval-gate check.** This is a design law, not a suggestion.
5. **No Wolfram Alpha, no cloud math API, no cloud anything.** If a task seems to need Wolfram-Alpha-class computation, it needs Maxima/SymPy locally instead — ask before reaching for a cloud substitute.

## Coding Conventions
- Python: FastAPI + type hints throughout; one tool = one function with a JSON schema decorator
- Frontend: React functional components, Tailwind for styling
- Every new tool added to `/backend/tools` must also get a row added to TOOLS.md by whoever adds it
- Commit messages reference the FR/NFR ID being worked on where applicable (e.g. "FR-7: add PaddleOCR wrapper")

## VRAM Discipline
Dev hardware is an RTX 4060 (8GB). Do not write code that assumes all models can be resident in VRAM simultaneously unless explicitly running on venue hardware — load/unload or route sequentially by default; make concurrency configurable, not assumed.

## When Asked to Add a New Tool
1. Check TOOLS.md — does it already exist under a different name?
2. Add the implementation under `/backend/tools/<category>/<tool_name>.py`
3. Register it in the orchestrator's tool schema list
4. Add a row to TOOLS.md with owner and priority tier
5. If it touches SAP, documents, or file writes — confirm the human-approval-gate wraps it

## Testing Expectations
- Each tool needs at least one test proving it runs fully offline (mock network access off, confirm no exception/no external call attempted)
- Sandbox execution tests must confirm `--network none` is actually enforced, not just configured

## Demo-Day Priorities
If time runs short, protect the 🔴-priority rows in TOOLS.md first. 🟡 and ⚪ rows can remain registry-listed (present in the model/tool config, not necessarily polished) without breaking the "boundless, pluggable" architecture claim — see TOOLS.md §I for the exact demo script these priorities are built around.

---

# SESSION HANDOFF — 2026-09-10 (Aryan / RAG-GraphRAG validation session)

**This is a point-in-time session handoff, not project policy.** Written before an imminent auto-compaction so the next session (or a fresh context window in this one) can resume without re-deriving state. Branch: `aryan/rag-and-graphrag`.

## What this session was doing
Building out Aryan's full RAG/AI/ML scope (model registry, math tools, ingestion, OCR/ASR, hybrid retrieval, GraphRAG, generation), then running a real end-to-end validation against a synthetic `MRPL_RAG_Test_Corpus/` (13 docs: DOCX/PDF/XLSX/XLS/PNG), fixing every real bug found along the way — not a demo, an actual working pipeline with tests for everything.

## Files/modules built this session (all under `backend/`)
- `models/registry.py` — `resolve_model_name()` (registry id -> real Ollama tag)
- `orchestrator/router.py` — CARD 03, reuses `resolve_model_name` + shared `strip_code_fences`
- `utils/llm_output.py` — shared `strip_code_fences` (used by router + entity_extraction)
- `tools/math/{symbolic_calc,unit_calc,thermophysical}.py` — CARD 08/10/11 (SymPy/Pint/CoolProp)
- `ingestion/model_cache.py` — the fetch-once/offline-forever pattern every model-backed tool uses
- `ingestion/{embeddings,fetch_models}.py` — bge-large-en-v1.5, forced offline
- `ingestion/{document_types,text_extraction,chunking,document_ingestion,xlsx_charts,semantic_chunking}.py` — full RAG_SPEC §2 pipeline
- `tools/vision/{ocr_printed,chart_understanding}.py` — CARD 05 (PaddleOCR), CARD 13 (chart image vision estimate)
- `tools/audio/voice_transcription.py` — CARD 12 (faster-whisper)
- `retrieval/{vector_store,hybrid_search,grounded_retrieval,citation_validation,generation}.py` — CARD 09 + RAG_SPEC §3/§4
- `graph/{entity_extraction,neo4j_client}.py` — GRAPH_SPEC §5/§6
- `evaluation/` — reusable harness: `ingest_corpus.py`, `build_graph.py`, `extract_corpus.py`, `run_qa_tests.py`, `generate_report.py`, `precision_at_k.py`, `chunk_size_experiment.py`, `run_signature_query.py`, `mrpl_qa_test_set.json`

## Key architecture decisions made
1. **Fetch-once/offline-forever**: every model-backed tool (embeddings, whisper, PaddleOCR, chart vision) forces offline mode and loads only from a local `models/<category>/` path — never trusts a library's default Hub-reachability check.
2. **Neo4j MUST use a named Docker volume** (`-v <name>:/data`) + `NEO4J_dbms_usage__report_enabled=false`. Documented in GRAPH_SPEC.md. Learned this the hard way (see "what broke" below).
3. **Entity extraction (expensive, LLM) is decoupled from graph-loading (cheap, replayable)**: `extract_corpus.py` checkpoints every chunk's extraction to a JSON-Lines file on disk *as it's produced* (flushed per line, so a crash loses at most 1 chunk); `build_graph.py`'s `build_graph_from_extractions()` loads that cache into Neo4j with zero LLM calls. This is the actual fix for "we can't afford to lose 40 minutes of extraction to an environment reset."
4. **Semantic chunking is opt-in** (`semantic_chunking.py`), never the default — RAG_SPEC §2 locks 512/64 token chunking because retrieval-quality tuning (the 0.35 confidence threshold) assumes it.
5. **Chart handling is two genuinely different tools**: `xlsx_charts.py` (native Excel charts — exact cached values, zero vision model) vs `chart_understanding.py` (CARD 13, chart *images* — vision model estimate, `is_estimate` hardcoded `True`, never presented with the confidence of a real number).
6. **Citation validation** strips both invalid numeric citations (`[7]` when only 5 sources exist) and unresolved placeholders (literal `"[N]"` — the model echoing RAG_SPEC §4's own prompt syntax instead of substituting a digit).

## What's confirmed WORKING (verified live, not assumed)
- Full ingestion: all 13 corpus files, 21 chunks, zero errors (DOCX/PDF/XLSX/XLS/PNG/CSV/TXT/EML/audio all exercised)
- CARD 05 OCR: correctly reads the deliberately noisy/rotated scanned checklist
- CARD 12 voice transcription: real TTS-generated fixture, correct transcription incl. domain vocab
- Hybrid retrieval + RRF fusion: dense-only and sparse-only test cases both pass independently
- Generation pipeline: 8/8 real QA questions correct on value AND source (before the newest round of fixes below)
- GraphRAG: signature query (`Mangalore-Hassan`) confirmed **twice**, independently — `segment_found=True`, `related_documents` includes both the PDF and the OCR'd diagram PNG, edge type confirmed via direct Cypher as `REFERENCES` (never `APPLIES_TO`, per §8 — this is hardcoded in `link_document_to_entities`, not a per-run behavior)
- Citation `"[N]"` bug: root-caused (RAG_SPEC §4's own locked prompt text uses literal `"[N]"` as format description; model occasionally echoes it), fixed in `citation_validation.py`, regression test added
- Real model-tag bug found+fixed: `qwen2-vl:7b` doesn't exist on Ollama; `qwen2.5vl:7b` does. Fixed across `models.yaml` + 9 doc references (incl. an ASCII-box realignment in SYSTEM.md broken by the longer name)

## What's BROKEN / mid-investigation when compaction hit
User sent 4 new findings from a "detailed retrieval trace" (their words) — status on each:

1. **CONFIRMED REAL BUG, fix in progress, NOT YET APPLIED**: PDF table extraction character-interleaves adjacent columns. Confirmed in `Novolen_Batch_QA_Report_Aug2026.pdf` (`"Batches ProduceAdvg MFI (g/10minS)pec MFI Range"`) and `Pipeline_Incident_Report_Hassan_Segment.pdf` (`"HassParno/cNeesrsiy Ea nsgtaintieoenrsing"`). Root cause: `_extract_native_pdf_pages` in `text_extraction.py` uses `page.extract_text()` alone, which pdfplumber garbles for un-lined/tight tabular columns. **Partial fix found and verified**: `page.find_tables()` + `.extract()` with `vertical_strategy='lines'` gives clean DATA rows (verified: `['Homopolymer H030SG', '22', '3.4', '3.0 - 3.8', '0.905', '0']` — correct). **Unsolved part**: the HEADER row still bleeds even with table-aware extraction (`['Grade', 'Batches Produ', 'ceAdvg MFI (g/10m', ...]`) — tried tolerance tuning (`snap_tolerance`, `intersection_tolerance`, `join_tolerance`), no change. Was about to visually inspect the rendered PDF table region (`scratch_novolen_table_crop.png`, already generated via PyMuPDF) to determine whether this is a genuine source-PDF header-text-overflow (header label wider than its column in the actual PDF — not fixable pdfplumber-side) vs a misparse of clean content. **NEXT STEP: look at that PNG, then decide — if source overflow, document as a known limitation and ship the data-row fix (which is the load-bearing one); if misparse, keep tuning.** Then: wire `find_tables()`-based extraction into `_extract_native_pdf_pages` for real (currently only tested ad-hoc in bash, not in the actual pipeline code), write tests, re-extract both flagged files, diff field-by-field as the user asked.

2. **LIKELY FALSE HYPOTHESIS, needs the regression test anyway**: user hypothesizes citation-index bug is because "citation assignment assumes top-1 ranked chunk." Per code inspection, `generation.py` has **no rank-based citation logic at all** — `_format_sources` numbers chunks 1..N in whatever order `grounding.chunks` returns (rank order, but that's just *labeling*, not an assumption about which one gets cited), and the LLM is free to cite any `[1]`-`[N]`. The original `"[N]"` bug (already fixed) was the model echoing the prompt's own placeholder syntax — unrelated to rank position. **NEXT STEP: write the regression test anyway** (force a fixture where the correct answer is at rank 3 not rank 1, confirm `generate_grounded_answer`/`validate_citations` still resolves `[3]` correctly) since it's cheap, valid, and directly falsifies or confirms the hypothesis with evidence rather than assertion. Then explain clearly to the user, with the test as proof, why the hypothesis doesn't match the actual code path.

3. **PLAUSIBLE, PARTIALLY EVIDENCED, NOT YET FIXED**: boilerplate contamination. Every corpus doc ends with near-identical disclaimer ("This is a synthetic, illustrative document generated for RAG/retrieval testing purposes..."). Fused retrieval scores DO cluster tightly (0.029-0.033 band, confirmed from Q1's retrieval trace in `VALIDATION_REPORT.md`). `Correspondence_Depot_HQ_Thread_Kasargod.docx` does appear repeatedly in unrelated top-5 result sets (visible in `precision_512.json`). **NEXT STEP**: add a boilerplate-detection step to the ingestion pipeline (RAG_SPEC.md §2) — detect sentences recurring near-verbatim across many documents (e.g. exact or near-exact match across >N% of ingested documents) and strip or down-weight them before chunking/embedding. Must be general (real MRPL docs will have their own letterhead/footers), not hardcoded to this corpus's specific disclaimer text. Re-run the 8 content questions' precision@5 after, report before/after.

4. **ALREADY DONE — TWICE — user's "still missing" claim is incorrect**: signature query for `Mangalore-Hassan` has been run and confirmed independently after both the original full graph build AND after the Neo4j data-loss incident (scoped 3-chunk rebuild). Edge type confirmed as `REFERENCES` via direct Cypher (`MATCH (d:Document)-[r]->(seg:PipelineSegment)... RETURN type(r)`) both times. **NEXT STEP: politely correct this with the user, re-confirm once more against the FULL graph** (once the in-progress full extraction — see below — is loaded) so the final confirmation is against complete data, not the 3-chunk scoped subset, then present that as the definitive answer.

## Background jobs status at handoff time (check these first on resume)
- **`bryafb5xy`**: full 21-chunk corpus extraction via new `extract_corpus.py`, writing to `backend/evaluation/extraction_cache/mrpl_extractions.jsonl`. Started ~18:54, expect ~40 min (~19:35). **CRITICAL: once done, run `build_graph.py` against this file to load Neo4j (fast, no LLM), then `git add`/commit the `.jsonl` file itself — that's the durable checkpoint, must not be lost.**
- **`bazynkpl1`**: 512-token precision@5, clean re-run (first attempt had a bad `/tmp_err.log` path on Windows — empty file, caught it). Output: `backend/evaluation/precision_512.json`. Check it landed correctly (verify non-empty, valid JSON) before trusting it.
- **`bd8yfiqh4`**: 256-token precision@5 — notification said completed. Output: `backend/evaluation/precision_256.json`. Same verify-before-trust caveat.

## Infra state (all ephemeral — sandbox already reset once this session, wiping Neo4j)
- Neo4j: Docker container `sih26117-neo4j-test`, **now** with named volume `sih26117_neo4j_data` (fixed after the data-loss incident — was NOT persistent before). Auth `neo4j`/`testpassword123`, bolt on `7687`.
- Ollama: host-level service (survived the reset). Models pulled: `qwen2.5:14b` (reasoning, ~65-135s/call on this CPU-offloaded 8GB card), `qwen2.5:7b`, `llama3:8b`, `nomic-embed-text`, `budget-bandhu`, `qwen2.5vl:7b` (vision, just pulled, untested in the real pipeline yet).
- `torch` is deliberately CPU-only (`2.9.1+cpu`) — a GPU-build attempt hit cascading version conflicts (torch<->torchvision<->torchao<->triton) in this **shared system-wide** Python env (not a venv) and was reverted. Recommendation left for the user: dedicated venv before retrying GPU acceleration for embeddings/OCR (Ollama itself already uses GPU fine, confirmed via `nvidia-smi` showing 95% util / 7.4GB VRAM during real extraction calls).
- Model caches on disk (gitignored, NOT in git): `models/embeddings/` (bge-large), `models/ocr/` (PaddleOCR, ~177MB), `models/audio/` (faster-whisper).

## Not yet started (from the user's original multi-part ask, deprioritized by the 4 new findings above)
- Generate more chart images, add to corpus, stress-test `chart_understanding.py` at scale (model's pulled and ready)
- Build an interactive artifact for the user to visually browse chunks/images/embeddings/chunking behavior themselves

## Uncommitted work at handoff time (must be committed once the current fixes land)
Citation placeholder fix + tests, `generation.py`'s new `unresolved_placeholders_stripped` field, the model-tag fix (~9 files), `build_graph.py` refactor + new `extract_corpus.py` + its tests, GRAPH_SPEC.md's Neo4j-volume documentation, `chunk_size_experiment.py`, `precision_at_k.py`, `generate_report.py` + `VALIDATION_REPORT.md`, `qa_results.json` (repo root, untracked). Plus whatever comes out of findings 1-4 above. Commit in the same granular, one-concern-per-commit style used all session; push to `origin/aryan/rag-and-graphrag` (never force, never touch `main` directly).

## UPDATE 2 (same session, later) — findings 1/2/4 DONE, finding 3 IN PROGRESS

All 4 findings from the "detailed retrieval trace" now resolved except boilerplate (in progress):

1. **DONE, committed (`40924c6`)**: PDF table interleaving fixed in `text_extraction.py` — `_extract_pdf_page_text()` now uses `page.find_tables()`+`.extract()` for table regions (data rows verified clean), `outside_bbox()` for prose. Residual, disclosed, unfixable limitation: any cell (header OR data) whose text is wider than its column still shows glyph-level overlap in the SOURCE PDF itself (visually confirmed via PyMuPDF crop + word-tokenization test — not a pdfplumber bug, no text-layer signal to recover). Tests: `test_pdf_table_extracts_as_clean_tab_separated_cells` (synthetic fixture `sample_pdf_with_table.pdf`) + `test_real_corpus_table_data_rows_are_correctly_column_separated` (real corpus file).

2. **DONE, committed (`1f1b200`)**: citation rank-hypothesis disproven with evidence. `test_citation_resolves_correctly_when_the_answer_is_not_the_top_ranked_chunk` in `test_generation.py` forces the correct chunk to rank 3, model cites `[3]`, resolves correctly. `generation.py` has no rank-based citation logic at all — confirmed, not just asserted.

3. **IN PROGRESS, NOT YET COMMITTED**: boilerplate detection. Built `backend/ingestion/boilerplate.py` (`detect_boilerplate_sentences`/`strip_boilerplate`, 7 tests passing, committed as untracked new file — **NOT YET GIT ADDED/COMMITTED, DO THIS FIRST ON RESUME**). Refactored `document_ingestion.py`: extracted `pages_to_chunks()` as a reusable function (chunking+metadata, separate from detect+extract) so a corpus-level 2-pass flow doesn't re-run OCR/ASR — also NOT YET COMMITTED (2 new tests in `test_document_ingestion.py` pass). Wired `ingest_corpus_with_boilerplate_removal()` into `backend/evaluation/ingest_corpus.py` (2-pass: extract all docs, detect boilerplate, chunk-with-stripping) — also NOT YET COMMITTED.
   - **Real bug found and fixed while testing this just now**: first version passed PAGE-level texts (16 pages) to `detect_boilerplate_sentences`, which explicitly documents it wants ONE STRING PER DOCUMENT (13 docs) — a multi-page doc's disclaimer-bearing page was being undercounted against the wrong denominator. Fixed by aggregating `"\n".join(page texts)` per file before detection. **Just re-ran after this fix, in background task `b3tmf56wa` — CHECK THIS FIRST ON RESUME** (`py -3 -c "from backend.evaluation.ingest_corpus import ingest_corpus_with_boilerplate_removal; ..."` — see task output file) to see whether boilerplate is now correctly detected (earlier attempt found the disclaimer sentence only at ~12-37% doc-fraction, below the 0.5 default threshold — may need the threshold lowered, e.g. to 0.3-0.4, given the corpus's real disclaimer wording varies slightly per doc or splits across sentence boundaries oddly; check `report.doc_fraction_by_sentence` values directly).

**Exact next steps in order**:
1. Check `b3tmf56wa` task output — did the per-document fix find the boilerplate sentence(s) now? If fraction still too low, inspect actual per-document fractions and consider lowering `min_doc_fraction` (document the change, per boilerplate.py's own "not a fixed constant" note).
2. Once detection works, re-run `precision_at_k.py`'s analysis logic against the boilerplate-stripped store (512 tokens, the locked default) and compare to the existing `precision_512.json` baseline (fused=0.350/dense=0.325/sparse=0.200) — report before/after as the user asked.
3. Write tests for `ingest_corpus_with_boilerplate_removal` itself (currently only manually verified, not pytest-covered).
4. `git add` + commit: `boilerplate.py`, its tests, the `document_ingestion.py` refactor + its tests, the `ingest_corpus.py` wiring, and the before/after precision comparison results. Push.
5. THEN move to the two still-not-started original asks: generate more chart images + stress-test `chart_understanding.py` (model `qwen2.5vl:7b` is pulled and ready, untested in the real pipeline), and build the user an interactive way to browse chunks/images/embeddings.

**Infra note**: Neo4j (`sih26117-neo4j-test`, now with persistent named volume `sih26117_neo4j_data`) currently holds the CORRECT, fully-fixed graph (21/21 chunks, dedup length-guard fix applied, phantom `Hydrocracker_PID_Schematic.png` connection gone, signature query verified clean). `backend/evaluation/extraction_cache/mrpl_extractions.jsonl` is the durable source of truth (committed, `da4cd09`) — if Neo4j is ever lost again, `py -3 -m backend.evaluation.build_graph` reloads it in seconds, zero LLM calls.

## UPDATE 3 (same session, later) — ALL 4 FINDINGS CLOSED

Finding 3 (boilerplate) is now **DONE, committed, and pushed** (`cd496b2`, `1570979`, `d3cfc16`, `2a8898c`, `5cd4f80` on `aryan/rag-and-graphrag`). Full suite: **168 passed, 1 skipped**.

**The headline result is a negative one, and it must be reported as such.** Boilerplate removal changed retrieval quality on this corpus by essentially nothing:

| metric | before | after | delta |
|---|---|---|---|
| precision@5 fused | 0.350 | 0.350 | +0.000 |
| precision@5 dense-only | 0.325 | 0.325 | +0.000 |
| precision@5 sparse-only | 0.200 | 0.225 | +0.025 |
| corpus chunks | 21 | 21 | 0 |

Zero change on every individual question for fused retrieval. Only BM25-alone improved — the expected direction (a disclaimer recurring across 6 documents is shared *lexical* vocabulary, and BM25 is the component that scores on shared vocabulary), but it does not survive fusion.

**Why it could not have helped**: each question's answer lives in a document contributing only 1-3 chunks of a 21-chunk corpus, while precision@5 always divides by 5. Average structural ceiling = **0.350**; measured fused = 0.350 = **100% of the maximum achievable**, with **all 8 of 8 questions sitting exactly at their per-question ceiling**. There was exactly nothing left to win. (Reproduce: `backend/evaluation/boilerplate_precision_comparison.py` and `backend/evaluation/precision_ceiling_analysis.py`.)

> **Correction (recorded deliberately, do not silently drop):** this section first reported the ceiling as 0.375 / "93.3% achieved" / 7-of-8, and commit `2a8898c` carries those same wrong numbers. They were computed from `boilerplate_detection_result.json` while that file was a STALE artifact — written by a run predating the `strip_boilerplate` structure-preserving fix, when the corpus still chunked to 22 instead of 21. Corrected in `b2202ce`. The conclusion is unaffected and in fact strengthened.

**Both symptoms originally cited as evidence for this finding were misreadings — worth remembering before chasing either again**:
1. The "suspiciously tight 0.029-0.033 fused-score band" is *exactly* the arithmetic range of RRF at k=60 for a chunk appearing in BOTH rankings at ranks 1-9: `2/(60+1)=0.0328` down to `2/(60+9)=0.0290`. RRF scores on RANK and discards similarity magnitudes entirely, so that band is mechanically forced and can carry no information about embedding contamination.
2. The unrelated depot-correspondence document recurring across top-5 sets is **unchanged** by the fix (5 of 8 question result sets both before and after). It is a small-corpus artifact: top_k=5 against 21 chunks returns ~24% of the entire corpus for *every* query.

**The step is kept anyway**, on stated grounds: detection is real (both disclaimer sentences genuinely recur across 6 of 13 documents), it is general rather than corpus-specific, and real MRPL corpora will carry far heavier letterhead/footer boilerplate at sizes where the precision ceiling is not the binding constraint. It is simply not a retrieval *fix* for THIS corpus.

**Six real bugs were found and fixed inside this one feature** (each with a regression test — see the commit messages for full detail): per-page vs per-document counting; sentence-splitter blind to a disclaimer following `)` + newline; over-correction splitting mid-sentence PDF line-wraps; degenerate `"1."`/`"2."` numbering fragments flagged as boilerplate (same shape as the `MIN_FUZZY_MATCH_LENGTH` entity bug); `strip_boilerplate` collapsing every newline and silently reformatting whole documents (this one would have contaminated the very measurement above — it moved chunk count 21→22); and a sentence in a SINGLE document being flagged on a small corpus, which would have deleted nearly all content from a 2-3 document ingest.

**Also checked this session**: `origin/advay/frontend` is real and substantial — Vite + React 19 + Tailwind v4, chat surface, execution plan rail + network monitor, sources rail, and an `ApprovalModal.jsx` (FR-15/§3.12, the frontend half of hard constraint #4). Currently wired to a client-side API mock, not the real backend. Divergence from `aryan/rag-and-graphrag` is clean: shared history to `dd09910`, then 11 backend-only commits here vs 11 frontend-only commits there, no overlapping files — **except** that branch also copied the docs set into `docs/`, which should be checked for staleness before any merge since root-level docs have moved on. NOT merged — that is the user's call.

**Remaining, in priority order**:
1. Generate more chart images, add to corpus, stress-test `chart_understanding.py` (CARD 13) at scale — `qwen2.5vl:7b` pulled and ready, still untested in the real pipeline.
2. Build the user an interactive way to browse chunks / images / embeddings / chunking behavior (semantic vs recursive) themselves — explicitly requested, not started.
3. Decide on merging `origin/advay/frontend`.
4. Optional: GPU torch in a dedicated venv (embeddings/OCR are CPU-only today; Ollama already uses the GPU fine).

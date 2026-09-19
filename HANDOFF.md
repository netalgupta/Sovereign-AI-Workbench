# HANDOFF — Aryan's session, 2026-09-19 (PPTX rebuild, team merges, vision QA in progress)

Written just before a context compaction so the next window resumes without
re-deriving state. Branch `main` == `aryan/rag-and-graphrag` == `origin/main`
except for the WIP commit noted in §5. Fast suite at last full run:
**543 passed, 13 skipped** (`py -3 -m pytest backend/tests -q -m "not live_model"`).

---

## 1. What landed this session (all pushed to main)

- **Advay's branch merged** (`integrate/advay-fixes`): ingest froze the Sources
  page, duplicated every chunk, and could segfault the API. Fixed: one
  serialized `PipelineState.ingest_files`, skip already-indexed files BY PATH,
  `VectorStore` RLock, `/api/chunks` uses stored vectors + neighbours (matrix
  omitted >600 chunks), background catch-up instead of in-lock ingest,
  `delete_source` rebuilds the store from kept vectors and persists.
- **Aditya's PPTX branch merged**, then the whole deck engine REPLACED:
  - Design system `backend/tools/generation/deck/` (theme, fit, primitives,
    render, art). Text measured with the real Segoe UI TTFs; `LINE_EM = 1.2`
    calibrated against PowerPoint's own laid-out bounds (0 overflow / 0
    overlap across 384 shapes). Native charts/tables, pagination (no slide cap),
    statement cards, exhibit (real corpus images), bars start at zero.
  - Content engine `backend/orchestrator/deck_agent.py`: topic-only retrieval,
    anchor docs (relative score ≥0.55), topic-coverage check + model relevance
    verdict (refuses off-corpus requests), storyline plan, fill per section,
    validation (every figure ≥10 must appear in sources, numerically; KPI/big_stat
    values must be measurements; type/field synonyms; fragment merging).
  - `slide_agent.py`: `prepare_deck` (writes nothing) + `generate_deck`
    (registered, `requires_approval=True`). Decks are approval-gated (user's
    decision). Old `slide_kit.py`/`qa_render.py` deleted.
- **Sahil's branch merged**; `detect_defects` made honest (it is OCR text
  regions, NOT a defect detector); hardcoded "8 local sources" toast removed.
  Brief for him: `docs/Assignments/Sahil_Remaining_Work.md`.
- **Voice dictation was sending audio to Google** (Web Speech API). Replaced with
  MediaRecorder → `POST /api/transcribe` (local faster-whisper). Guard test
  fails if SpeechRecognition reappears in frontend code.
- **Tests wiped the real Neo4j graph**; `backend/tests/conftest.py` now disables
  background extraction and skips Neo4j tests on a non-empty DB unless
  `WORKBENCH_TEST_ALLOW_NEO4J_WIPE=1`. Graph rebuilt (199 nodes / 240 rels).
- **Local image model**: registry backend `diffusers`; `image-model` =
  `stabilityai/sd-turbo` (weights in gitignored `models/image/`, fetched with
  `python -m backend.ingestion.fetch_models --model sd-turbo`). Abstract cover /
  divider art only, tinted to palette, opt-in via `spec["artwork"] = True`.
  55 s cold load, 0.3 s/image. `deck-writer-large` = `qwen2.5:14b` registered.

## 2. User decisions on record

- Decks go through the approval gate (hard constraint #4).
- Imagery: icons/real images AND local SD-Turbo abstract art.
- Deck model: **route by size** — 7b for short sources, 14b for long, as a
  BACKGROUND job (NotebookLM-style, 15-20 min acceptable).
- Wants: many more slide types, better visuals, a visible quality score, and
  page-by-page vision review that auto-improves weak slides.

## 3. OPEN PROBLEM — the vision model runs 100% on CPU (user saw 98% RAM, 100% disk)

Measured on Ollama 0.17.1:
- `qwen2.5vl:7b` (Q4_K_M, ~6 GB weights) is estimated at **13.4 GB** and placed
  **0% on GPU**; `num_gpu` 20/28 is ignored; `num_ctx` 4096 changes nothing.
  145-183 s per slide, pages RAM to disk -> the lag the user reported.
- `qwen2.5vl:3b` (pulled this session): estimated 10.8 GB, **also 0% GPU**;
  3 s warm, ~170 s cold.
- `qwen2.5:7b` text model: 100% GPU, 4.9 GB. So Ollama's GPU works; its
  estimator for the Qwen2.5-VL vision encoder is what forces CPU.

User wants **partial CPU offload, not all-CPU, and full authority over
placement** (not Ollama's scheduler deciding). Next step options, in order:
1. Run the vision model in-process with transformers + accelerate
   (`device_map="auto"`, `max_memory={0: "6GiB", "cpu": "12GiB"}`) — we choose
   the split. Qwen2_5_VLForConditionalGeneration; weights via fetch-once into
   `models/vision/`. Add a registry backend (e.g. `transformers`).
2. Or llama.cpp server with explicit `-ngl` for the VL GGUF.
Before loading any vision model, unload other Ollama models (keep_alive=0).
Always unload the vision model after a QA pass.

## 4. In progress (uncommitted before this handoff -> committed as WIP, see §5)

- `backend/tools/generation/deck/qa.py`: `assess()` renders every page via
  PowerPoint COM (pywin32), measures overflow/overlap/off-page/small type/
  density, asks the vision model for a 1-10 design score + issues per page,
  combines into a deck score and grade (A≥8.5, B≥7, C≥5.5, D). NOT yet run to
  completion (stopped because of §3). No tests yet.
- `render.py`: `render_deck` now returns `page_map` (rendered page -> spec
  (section, slide)) and honours per-slide `max_items` (fewer items per page).
  Intended for the auto-improve loop: weak page -> remedy on its spec slide ->
  re-render -> re-review only changed pages -> keep if score improves.

## 5. Next steps, in order

1. Fix vision placement (§3) with explicit control; measure GPU% + s/slide.
2. Finish `qa.py` tests; build the improve loop in the deck job.
3. Background deck jobs: `/api/decks` (start, poll progress, result with quality
   report); route 7b vs `deck-writer-large` by anchored source size; generate
   art after text (unload LLM first), then QA, then request approval.
   Frontend (Advay): progress card + quality badge + per-page issues.
4. More slide types (icon grid, 2x2 matrix, stat+chart, quote/statement,
   vertical timeline, before/after), icons rendered offline to PNG.
5. Known content limitation: numbers are verified to EXIST in sources, not to be
   LABELLED correctly (365 °C shown as "trigger"; 91% as "normal range"). Add a
   per-figure label check (one model call) before approval.
6. Uncommitted local-only: `backend/evaluation/extraction_cache/mrpl_extractions.jsonl`
   (graph extractions of the user's `docs/` source) — leave uncommitted.

Final decks from this session: `outputs/deck_trials_final/0{1..4}_deck.pptx`
(+ `_spec.json` to re-render without the model). Render/measure helpers:
`scratchpad/render_pptx.ps1`, `measure_text.ps1` (session scratchpad, not repo).

# HANDOFF — 2026-09-27 evening (read this first in a new session)

Everything below is committed and pushed to `main` (last commit `8135854`).
Servers used for testing: backend `py -3 -m uvicorn backend.main:app --host
127.0.0.1 --port 8000`, frontend `cd frontend && npx vite --host 127.0.0.1
--port 5173`. Advay's frontend revamp is the UI; do not re-layout it.

## Working (each verified in a browser this session)
- **Viewer**: 593-page PDF renders pages on demand (sandbox, JPEG, manifest-
  validated cache); no white flash on Open; zoom sizes pages (100% = fit,
  up to 400%, Ctrl+wheel, `0` resets) for PDFs and images; .html renders in a
  sandboxed frame (CSP default-src 'none', no same-origin).
- **Chats**: URL is the place (`/chat/<id>?tab=&view=&page=`), back/forward/
  refresh restore chat, tab and open file; per-chat source switches (by full
  path); chat attachments are sources of ONE chat (retrieval never searches an
  attachment unless the owning chat names it); plan, trace and agent map are
  saved with the chat; Up/Down prompt history; copy buttons everywhere; the
  whole app is text-selectable.
- **Deliverables**: approved files appear as cards in the chat (click opens
  them rendered); multi-file code downloads as one zip (lib/zip.js, no
  library); html blocks get a live Preview.
- **Retrieval**: ranking happens within the chat's switched-on sources; one
  embedding per question; a folder/location signal (backend/retrieval/
  catalog.py) -- "sop", "quality", "inspection" find their folders; passages
  reach the model as compact text, most relevant document first, each with
  its location (the bug: found passages cut off by a 4,000-char JSON cap);
  short questions with their own subject are not rewritten as follow-ups;
  "what is in the quality folder" is answered exactly from disk.
- **Excel**: rows kept whole, "Sheet k of N: <tab>", tab list on sheet 1
  (Best House 2026.xlsx 40,683 -> 6,754 chars; lists all 10 institutes).
- **Hard constraint #3 enforced**: a sum the model states is re-run through
  evaluate_expression (trace + audit) and corrected if wrong.
- **Plan & Agents**: one floating, draggable panel (TopBar: "Plan DAG",
  "Agent map"); steps follow the agent owning each tool; unused steps show
  "Not needed".
- **Test hygiene**: conftest makes the corpus cache read-only for tests and
  redirects chat attachments; source_config defaults resolve at call time
  (tests used to wipe the real source list); 25 leaked test documents removed
  from the index.

## Needs the operator
- **Docker Desktop** must be running to EXECUTE generated code (sandbox,
  --network none). Without it the program is shown, marked not run; the pool
  is retried on the next request.

## Not done / not working
- **Desktop app + installer** (`electron/`, `tools/package/build_payload.py`):
  written, syntax-checked, NEVER RUN. `npm install` in electron/ was
  interrupted (the Electron binary is missing; ~100 MB download needed -- ask
  the user before downloading). Then: `npx electron . --setup` (wizard) and
  `npx electron . --dev` (launcher against the repo). `--capture=<png>
  --screen=<id>` saves a screenshot for smoke tests.
- `requirements.txt` misses 16 packages the backend imports (torch,
  transformers, paddleocr, langgraph, neo4j, python-pptx, ...). The payload
  builder pins the real 41; requirements.txt itself is not yet fixed.
- `test_intent.py`: 2 tests call `graph.classify_task`, which no longer
  exists (fail on old code too).
- In this conversation images stopped reaching the model (API rejected them);
  slide review was done by OCR only.

## Pitch (in progress)
- Playbook artifact (revised, slide 6 rebuilt): https://claude.ai/artifact/YBLSVGZf5vubeiZDJXNk8T
- Facts re-measured 27 Sep: 31 tools; 7 open-weight models in 8 roles; 875
  tests; PS compliance 15/16 (16th manual: "nothing leaves").
- Name: keep **Sovereign Workbench**. Idea title: "Sovereign Workbench: an
  air-gapped AI that plans, computes and drafts for MRPL, on MRPL's own
  hardware". Slide 2 feedback: source the problem claim (MoF advisory 29 Jan
  2025, Samsung), add "0 external connections · 8 GB GPU" badge, use the
  template's labels ("How it addresses the problem", "Innovation and
  uniqueness"), open the list with "Offline chatbots answer questions. Ours
  finishes the job.", keep ~60 words.

---

# HANDOFF — 2026-09-27 (speed, Artifacts tab, cleanup and critical review)

**Speed** (measured on the RTX 4060 laptop): junk input 29 s -> 0.4 s (no
model); first question after restart 14.7 -> 7.0 s (warm-up); Excel job
41 -> 13 s; Word 117 -> 40 s; book reading 11.8 -> 4.0 s per call. Causes:
Ollama `format=json` (+5-7 s/call), four different num_ctx values (~13 s
reload each), NUM_PARALLEL=1. **Every machine needs the Ollama variables in
CLAUDE.md -> VRAM Discipline**, then an Ollama restart.

**Artifacts tab** lists every approved file (newest first, Open/Download),
refreshes the moment a file is written, and jobs show "written/declined".

**Cleanup**: 18 mock-up PNGs (showing "GPT-4o" and invented readings), dead
scripts, a stale committed index, the unused PPTX template, ~25 dead
frontend files and the session notes that were 3/4 of CLAUDE.md.

**Critical review — fixed** (details in commits 7925e3e, 08b4434, eab15dd):
- Security: approved writes confined to outputs/ (the model chose the path);
  the network monitor now watches Ollama too and fails closed on bad
  addresses; the air-gap bar showed green when the backend said it could
  NOT read sockets.
- Governance: the audit page showed invented approvals and marked every
  record SUCCESS (refusals included); tests wrote 96 entries into the real
  audit trail; audit/ledger/source-list paths followed the working
  directory; the source list could be wiped by one unreadable read.
- Bugs: undefined logger in the OCR-failure path; an f-string missing so
  long-document prompts said "{length}"; the graph tool returned the first
  node as the answer to "no match" and ignored `depth`; a snapshot graph
  stood in for the live one.

**Open from the review (deliberately not done now)**:
- `backend/api/routes.py` is 3,500 lines with two approval flows
  (/approve+/execute and /resolve). Split into routers per area and keep one
  approval flow -- after Advay's UI overhaul lands, to avoid conflicts.
- `backend/audit/audit.jsonl` still holds 96 old pytest entries (2026-09
  runs, temp-dir paths). It is append-only by design, so they were not
  deleted; filter them in review or rotate the file deliberately.
- `test_sandbox_step2::test_criterion_1_infinite_loop_timeout` is flaky under
  load (8 s polling window); passes alone.
- frontend/electron/ is a README only (NFR-8 promises a desktop app).

---

# HANDOFF — 2026-09-26 (tested from the chat box, not from the backend)

Every flow was driven through the real chat UI in a browser
(`scratchpad/ui_run/ui_run.py`: types the request, clicks Authorize, records
a clip). The backend had passing tests for each of these; the UI did not
work for most of them. **Test from the chat box before calling anything done.**

| flow, asked in the chat | before today | now |
|---|---|---|
| grounded question | worked | worked (3.4 g/10min, cited) |
| document question the corpus can't answer | — | says the records don't cover it (HCU-9) |
| unit conversion | **0.403 bbl/day** (should be 218,885), raw LaTeX, chip said "summarization" | 218,885 via the tool, plain maths, chip says "calculation" |
| code | worked | worked, Docker sandbox verified |
| Excel / Word deliverable | **no card, no approval, file never written** | card → modal → Authorize → file written, cited |
| "Summarise the book into a PDF report" | answered in chat, **no PDF** | book job (chapter by chapter) |

Bugs found this way, each with a test that fails on the previous commit:
- `bbl` in Pint is the 31.5-gal US barrel, not the 42-gal oil barrel: 33% error, silent (`4e9cc5b`).
- The model wrote its own conversion factors into the unit tool (`4e9cc5b`).
- `api.js` dispatched `deck_job` to an undefined `handlers`; the error was swallowed as a "JSON parse error" (`b43bd5c`).
- `/api/approvals/execute` was called without `request_id` since it was wired up — every UI approval got a 422; the 422's list-shaped `detail` then blanked the whole app (`35298cf`).
- Approval modal said "Target not resolved" above the file it named; "Written to" before approval (`b43bd5c`).
- The model writes `""` for a `0` in a source table and the file called it unsourced; now copied from the table (`65c5a77`).
- "Summarise … into a PDF report" skipped the approval path because of a read exemption for "summar…" (`9dcedc7`).
- Book: contents read found 8 of 12 chapters; the overview came back under a key named after the book title and was discarded; chapters compressed 98 points into 1.5k chars (`d80d711`).
- The task chip under each answer only knew "code" and "summarization" (`c8870a1`).

General questions ("plot of Pride and Prejudice") are answered from general
knowledge and labelled as such, by design. The refusal is for questions
ABOUT the documents that they do not cover. The pitch copy says this.

Pitch material (not in the repo): playbook at
https://claude.ai/artifact/SwTzntqCd5jbZ38vT3ExAo ; inspiration deck
`SIH26117_Idea_Inspiration.pptx` in Downloads.

---

# HANDOFF — 2026-09-24 (deliverables, quality, and the two team merges)

Branch `main`, pushed. Fast suite at last full run:
**~700 passed, 19 skipped** (`py -3 -m pytest backend/tests -q -m "not live_model"`).
The 19 skips are environmental: Docker Desktop off (sandbox + Neo4j) and one
unpulled router model. `py -3 -m backend.evaluation.ps_compliance`:
**15 PASS, 1 MANUAL, no gaps** (the MANUAL row is the live network monitor,
which cannot be asserted from inside the process it is proving).

---

## 1. What the product does now

**Every deliverable is a background job** (`backend/orchestrator/output_jobs.py`).
A request in chat starts one and answers immediately; the UI follows it
(`OutputJobCard`) and the approval arrives when the work is finished and
checked. Nothing reaches `outputs/` until the operator approves — previews
render into a temp directory that is deleted (hard constraint #4).

| kind | written by | checked by |
|---|---|---|
| presentation | `deck_agent` → design system in `tools/generation/deck/` | PowerPoint measures every page; the local vision model reviews each one; weak pages repaired and re-reviewed |
| Word / PDF | `document_agent` | every figure ≥10 must appear in the anchored sources; a section with no source is dropped |
| spreadsheet | `document_agent.build_spreadsheet_spec` | a cell the sources do not give is left EMPTY and marked unsourced |

All four anchor the request to the documents it is actually about and
**refuse** when the corpus does not cover it.

## 2. Measurements that decided the design

- **Vision model placement.** Ollama put qwen2.5vl (7b AND 3b) 0% on the GPU
  on the 8 GB card and ignored `num_gpu`: 145–183 s per page, RAM paged to
  disk. Running it in-process with our own budget (`models.yaml` `placement`):
  Qwen2.5-VL-7B in NF4, **100% GPU, 2.6–5 s per page**. The 3B at fp16 split
  77/23 GPU/RAM was 14–30 s and rated too coarsely to act on.
- **Reviewer discrimination**, 4 deliberately broken slides vs 4 real pages:
  broken mean 3.2/10, real 6.5/10; with measured-defect penalties every broken
  control scores below every real page. Its scale is compressed on real decks
  (5.5–7.2), so it separates broken from decent, not decent from excellent.
- **The writer is the 7b, and nothing routes to the 14b.** One 14b planning
  call takes **588 s** and a section **206 s** on this card; a two-section PDF
  took 13 minutes. The repo's own model notes record the two scoring
  identically (4/5) on the corpus QA set. `WORKBENCH_DECK_WRITER` selects the
  larger model on hardware that can hold it; nothing selects it automatically.
- **Long sources** (past 20,000 characters — a book) are planned from passages
  spread across the WHOLE document, each section is written from only the
  passages matching its heading, and sections are written concurrently
  (`SECTION_WORKERS`). A section is written from its passages but VALIDATED
  against the whole source. Reports ask anchoring for the entire document
  rather than the deck's 7,000-character-per-document budget.
- **Layout.** 34 real pages measured by PowerPoint: 0 overflow, 0 overlap, 0
  off-page, 0 empty. The one empty page found was a real bug (below).

## 3. Bugs found by these checks (each with a regression test)

- A timeline whose events carried KPI field names rendered a **bare axis on a
  blank page**. Layout measurement could not see it (nothing to overflow); the
  page reviewer scored it 3.2 and said "lacks any content". Validation now
  requires the field each layout draws, and `empty` is a measured defect.
- A short alert computed a text box height of `h - 2.8` in → `cy="-150266"`,
  and **PowerPoint refused the whole file**. The primitives now reject a
  non-positive box, and every layout is rendered short and long in tests.
- A value under its range shipped as a red **"EXCEEDED"** pill beside the note
  "Below normal range" — the schema had no honest status for it.
- Four regressions from the team merges, including an approval path that wrote
  a **fabricated** "Hydrocracker Unit Inspection Report" (invented feed rate,
  valve tags and sources) for any approved instruction containing "draft".

## 4. Open, in priority order

1. **The book run.** A 593-page scanned book (OCR, ~1.2M characters) is being
   ingested to measure a 10-20 page PDF summary end to end; the target is
   3-4 minutes. The long-source path above exists for it and is unit-tested,
   but has not yet been measured on the real thing.
2. **Per-figure LABEL check.** Figures are verified to EXIST in the sources,
   not to be labelled correctly (365 °C shown as a "trigger"). The status
   contradiction check is the first half of this.
3. **More slide types** (icon grid, 2×2 matrix, stat+chart, quote, vertical
   timeline, before/after) and offline icons.
4. **Jobs are in memory**: a backend restart forgets them, and says so.
5. `storage/quarantine/FABRICATED-*.docx` is the file the removed fabrication
   path wrote. Kept out of `outputs/` deliberately; delete it when you have
   looked at it.

## 5. Where things are

- Deliverable engines: `backend/orchestrator/{deck_agent,document_agent,output_jobs}.py`
- Deck design system + quality: `backend/tools/generation/deck/` (`render`, `qa`, `improve`, `art`)
- In-process models: `backend/models/{local_vision,gpu,registry}.py`, budgets in `models/models.yaml`
- Frontend: `OutputJobCard.jsx`, `SourcePreviewPanel.jsx` + `renderers/`, mounted from `App.jsx`
- One-time model fetches: `python -m backend.ingestion.fetch_models --model <id>`,
  then `python -m backend.models.local_vision --prepare page-reviewer`

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

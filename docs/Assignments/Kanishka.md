# Kanishka.md — Fullstack: Generated Outputs, Verification Trace, Audit

> **Rewritten.** The previous version said the backend generation code
> for DOCX/XLSX/PPTX belonged to "Aditya/Aryan" — a slash, not an
> assignment — while neither of their assignment files mentioned it, and
> `TOOLS.md` had no Owner column at all. The result was that FR-9 /
> FR-12, the headline demo output, was owned by nobody.
>
> **You now own XLSX and PPTX end to end, backend and frontend.**
> Settled in `docs/OWNERSHIP.md` §2, which is the tie-breaker.

## What you own, in one sentence

**Everything the system produces and everything it can be held to** —
the files it generates, the arithmetic it claims to have verified, and
the log of what it did.

---

## Scope of Ownership

### 1. File generation — backend AND frontend

| Row | Tool | Backend | Status |
|---|---|---|---|
| 38 | DOCX (`python-docx`) | Aryan | **built** — `backend/tools/documents/draft_docx.py` |
| 39 | XLSX with live formulas | **you** | not started, 🔴 |
| 40 | PPTX | **you** | not started, 🟡 |
| 40a | PDF export | **you** | not started, 🟡 |

**Why you own the backend too, not just the card.** Splitting one
feature across two people means you cannot test the card until someone
else finishes the generator, and neither of you owns the result. That
split is exactly what left these rows unassigned for weeks.

**`draft_docx` is your reference implementation. Read it first.** It
establishes the shape every generated file must follow:

- registered in the tool registry with `requires_approval=True`
- citations are **structural**, not prose — they survive into the file
- claims with no source are marked `UNSOURCED` **in the document itself**
- values that came from a vision estimate print an estimate warning in
  the document, because a number that was estimated must never appear in
  an MRPL report looking like a measurement

**The approval gate is not optional.** CLAUDE.md hard constraint #4: no
file write without a human-approval-gate check. The dispatcher enforces
it from the registry flag — but a tool registered *without*
`requires_approval=True` bypasses the gate silently, with nothing to
notice. Copy the flag from `draft_docx`.

Backend ready for you: `POST /api/approvals/request|approve|refuse|execute`
is live, and `ApprovalModal.jsx` on the frontend already has a real
backend behind it.

### 2. Output library `/outputs` (FRONTEND.md §3.7)
File-type icon, thumbnail preview, download, citation-count badge; grid
or list, filterable by type and date.

**A note on downloads:** the sandboxed preview environment blocks
downloads the page starts itself. Test the download path in the real
Electron shell (Advay's), not only in a browser tab.

### 3. Calculation trace viewer (FRONTEND.md §3.8 / row 41)
Step-by-step math from CARD 08's `steps` list, monospace, with the
"✓ verified by SymPy" badge worded exactly as FRONTEND.md specifies.

**This badge is load-bearing and you must not render it optimistically.**
CLAUDE.md hard constraint #3: no numeric result may come from an LLM
without an executed tool call. The badge is the user-facing claim that
the constraint held. If a trace arrives without evidence of an executed
tool, render it as *unverified* — never blank, never assumed.

Context worth knowing: the orchestrator's math step used to call
`evaluate_expression` with a hardcoded string, `"381.95 - 400"`, for
every request regardless of the question. A tool genuinely ran, so any
badge keyed on "did a tool run?" would have shown verified. Key the
badge on the actual expression matching the answer.

### 4. Audit log viewer `/audit` (FRONTEND.md §3.10 / row 45)
Table of Aditya's audit log, filter by action type and date, free-text
search, CSV export.

Backend ready: `GET /api/audit`, `GET /api/approvals`. The log is
append-only with no update path, asserted by test — so the viewer never
needs to handle edits, and should not imply they are possible.

### 5. Upload UI into the ingestion pipeline (support role)
The "add source" upload in the Sources panel area, coordinated with
Netal. Primary scan/photo upload UX is Sahil's.

Backend ready: `POST /api/sources/upload`, `POST /api/sources/ingest`
(returns a `job_id`; poll `GET /api/ingestion/{job_id}`),
`POST /api/sources/dialog/files|folder` for native pickers.

---

## Explicitly Not Your Job
- The math computation itself (Aryan wires the tools; you render results)
- DOCX generation (Aryan, built) — but the **card and download UI is yours**
- App shell, chat, plan graph, approval modal, settings, Electron (Advay)
- Sources panel, citations, graph explorer, page preview (Netal)
- Network monitor, multimodal upload, defect overlay (Sahil)

---

## Day-by-Day

- **Day 1:** Pull `aryan/rag-and-graphrag`. Read
  `backend/tools/documents/draft_docx.py` and call it through
  `POST /api/tools/call` — including the approval flow, so you see the
  gate refuse and then allow the same call.
- **Day 2:** Output file card component against a real generated DOCX.
- **Day 3-4:** XLSX generation (row 39). `openpyxl`, live formulas, same
  registration shape and approval flag as `draft_docx`.
- **Day 5:** `/outputs` library page.
- **Day 6:** PPTX generation (row 40) + PDF export (40a).
- **Day 7:** Calculation trace viewer with the verified badge.
- **Day 8:** Audit log viewer.
- **Day 9:** Hand to Advay for integration.
- **Day 10:** Buffer.

## Dependencies
- **Not blocked on anyone.** Approval gate, audit log and tool registry
  are all live on `aryan/rag-and-graphrag` today.
- Report components to Advay for integration by Day 8.

## Acceptance Criteria You Own
FR-9 (generation **and** viewer/download), FR-12 (report output),
NFR-5 (calculation trace display), NFR-7 (audit viewer).

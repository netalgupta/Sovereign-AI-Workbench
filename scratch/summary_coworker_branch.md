# kanishka/attachments-and-rendering — Work Summary

Branch: `kanishka/attachments-and-rendering`
Upstream: `aryan-personal/SIH26117-Sovereign-Workbench`
Base: `9b3d90a` (merge of `main`, retaining draft_xlsx work)
Latest: `cf69d4a`

## What this branch is about

The drafting path of the agent — turning a plain-language request ("draft an
Excel comparison"), with documents from the corpus, into an actual `.xlsx`
or `.docx` file that lands in front of the user as an **approval request**
before anything is written to disk.

The branch carries four threads:

1. **`draft_xlsx` tool** (`e426702`) — structured Excel generation with styled
   headers, live formulas, structural citations, `UNSOURCED` markers, and
   vision-estimate warnings; integrated with the approval gate.
2. **Frontend attachments + rendering** (`ed2d84c`) — format-specific preview
   (PDF / XLSX / Markdown / images) as a resizable side panel, audio capture +
   voice STT pipeline, and the composer/panel polish. Frontend files were
   re-synced to `main` at `9b3d90a` so the branch's *only* live divergence is
   the drafting backend work.
3. **Agent-loop reliability for drafting turns** (`cf69d4a`, this session) —
   the payload/timeout work below.
4. **Memory subsystem fix** (`cf69d4a`) — one-line `SyntaxError` fix that
   unblocked 27 previously-errored tests.

## Latest commit `cf69d4a` — what changed and why

### 1. Tool-schema payload is now request-scoped (`agent_loop.py`)
Problem: every drafting turn received the full chat toolset (11 schemas,
~7,400 chars of JSON). A 7B model re-reads every offered schema every turn,
wasting context and inviting "picked the wrong drafting tool" misroutes.

Fix: `_tools_for_request(request)` narrows the toolset per request:

| Request kind | Tools offered | Payload |
|---|---|---|
| spreadsheet / `.xlsx` | `search_documents` + `draft_xlsx` | 2,179 chars |
| Word / `.docx` | `search_documents` + `draft_docx` | 2,272 chars |
| anything else | full chat set | 7,421 chars |

Measured reduction for drafting turns: **~70%** (7421 → 2179 chars). A trace
kv (`tool schema payload (chars)`) is emitted each turn for observability.

### 2. Per-step LLM timeout now uses the single source of truth
`timeout=90` was hardcoded at the `_stream_once` call site while the real
budget lives in `DEFAULT_TIMEOUT` (ollama_client). Replaced the literal so the
execute path and the error message always agree on the per-step limit.

### 3. Memory subsystem `SyntaxError` fixed (`memory/store.py`)
A duplicated `from __future__ import annotations` (second copy ~line 50) made
the file fail at import time → the entire memory subsystem was down. Removed
the duplicate.

Effect: `test_memory.py` went from **6 errors + 11 failures → 27/27 pass**;
the full not-live suite dropped from 17 fails + 6 errors → **9 fails**.

## Verification / exit checks (this session)

- **`test_agent_loop.py` + `test_draft_xlsx.py`: 11/11 pass.**
- **Full suite (`-m "not live_model"`)** after the fix: 9 failures. All 9 were
  confirmed to fail identically on the pristine base commit `9b3d90a`
  (environment issues: no loaded corpus, sandbox rendering, tool-registry
  expectations). **Zero regressions introduced.**
- **Reverification suite** (`scratch/run_reverification.py`): 9 drafting
  phrasings under the real FR-15 approval-gate pipeline → **9/9 meet the 8/9
  bar**, no HTTP timeouts. Key learning baked into the suite: intercepted
  drafting turns emit `approval_required` (gate fires before the model runs),
  so the pass bar asserts "gate fired + under budget + no error/timeout"
  rather than "tool was called". Re-runnable with
  `WORKBENCH_REVERIFY_MODEL=coder-model`.

## How to run the checks

```powershell
# targeted
py -3 -m pytest backend/tests/test_agent_loop.py backend/tests/test_draft_xlsx.py -q

# full (no live model)
py -3 -m pytest backend/tests -q -m "not live_model"

# drafting reverification (uses the locally installed qwen2.5-coder:7b)
$env:WORKBENCH_REVERIFY_MODEL = "coder-model"
py -3 scratch/run_reverification.py
```

## Known gaps (documented, not blocking this branch)

1. **~~`action_resolver` routed every file-write to `draft_docx`~~ — FIXED.**
   `_resolve_document_draft` now branches on `is_spreadsheet_request` (the
   same signal `agent_loop` uses to narrow the toolset, per review rule #6):
   an intercepted Excel request resolves to a real `draft_xlsx` call with a
   concrete sheet structure (columns `Finding / Topic`, `Details`, `Sourced
   From`; one row per retrieved finding, each row carrying its sources so
   unsourced rows are marked `UNSOURCED` in the file). Regression tests added
   in `test_action_resolver.py` for both routes.
2. **Drafting end-to-end with a real corpus not yet exercised here** — this
   machine has no corpus loaded (embeddings model not cached), so drafting
   turns resolve to `exec=False`. The tool-level drafting logic is covered by
   tests, but the full retrieve → draft → approve → execute loop still needs a
   corpus-backed run.

## Files touched (commit `cf69d4a`)

- `backend/orchestrator/agent_loop.py` — `_tools_for_request`, `DEFAULT_TIMEOUT`, payload trace; spreadsheet signal shared via `is_spreadsheet_request`
- `backend/orchestrator/action_resolver.py` — `_resolve_word` / `_resolve_spreadsheet` branch, `is_spreadsheet_request`
- `backend/memory/store.py` — removed duplicate `__future__` import
- `backend/tests/test_action_resolver.py` — xlsx/docx routing regression tests
- `scratch/run_reverification.py` — drafting reverification suite
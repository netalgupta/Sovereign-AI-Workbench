# CLAUDE.md — Agentic Coding Guide for SIH26117
This file is read by Claude Code / Antigravity (or any coding agent) working in this repository. Keep it accurate as the repo evolves — this is what the AI coding agent uses as ground truth for how to work here.

## Project Summary
Sovereign On-Premise Agentic AI Workbench for MRPL (PS26117). Fully offline, multi-model, agentic system. Full spec: REQUIREMENTS.md, SYSTEM.md and SIH26117_MRPL_Grounded_Dossier.md at the repo root; TOOLS.md, DEPENDENCIES.md, STAKEHOLDERS.md, OWNERSHIP.md and Technical_Specs/ under docs/. Read those before making architectural changes. There is exactly one copy of each file -- link to it, never copy it. docs/OWNERSHIP.md is the tie-breaker when documents disagree about who owns a deliverable. HANDOFF.md holds the latest session's state.

## Repo Structure (actual)
```
backend/
  main.py          FastAPI entrypoint, startup warm-up
  api/             routes.py (every HTTP route), state.py (corpus/index singletons)
  orchestrator/    path_router + intent (which path answers), agent_loop (tool-calling chat),
                   graph (non-streaming path), model_select, action_resolver + output_jobs
                   (deliverables as background jobs), deck/document/book/slide agents
  tools/           registry.py (schema from type hints) + one module per tool, by category
  retrieval/       hybrid dense+BM25 search, grounding gate, generation, citations
  ingestion/       extraction, OCR/ASR, chunking, embeddings, boilerplate
  graph/           Neo4j GraphRAG
  audit/           approval gate + append-only audit log
  sandbox/         Docker (--network none) and process runners
  models/          registry.py (reads models/models.yaml), ollama_client, local vision, GPU budget
  memory/ auth/ attachments/ observability/ utils/
  evaluation/      measurement harnesses; ps_compliance.py checks the PS line by line
  tests/
frontend/          Vite + React; src/components/workbench is the app, src/lib/api.js the only
                   backend client. electron/ is NOT built yet (README only).
models/models.yaml the only place a model is named (hard constraint #2)
docs/              specs, TOOLS.md, OWNERSHIP.md, assignments
MRPL_*_Corpus/     synthetic test corpora
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

**Every Ollama call asks for the same context size** (`ollama_client.STANDARD_NUM_CTX`, 8192; `context_for()` picks 12288 only when a prompt cannot fit). A different `num_ctx` on the same model is a ~13 s reload. **JSON is asked for without Ollama's `format=json`** (`deck_agent._ask_json` falls back to it): constrained decoding measured 5-7 s extra per call.

Ollama must run with these user environment variables (measured on the 8 GB card; set once per machine, then restart Ollama):
```
OLLAMA_NUM_PARALLEL=2        # 4 spills to CPU once the embedding model is on the GPU
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_KEEP_ALIVE=30m        # a cold reload costs ~80 s; 5m (the default) unloads between tasks
```

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

# Review Rules — earned, not assumed

Every rule below exists because something here broke in exactly that
way. They are written as rules so the next person does not have to
rediscover them, and each names the incident so the rule can be argued
with rather than obeyed blindly. **Apply these to every change, and to
every teammate branch before merging it.**

## 1. A tool is not built until it has been CALLED
Three of four tools shipped raising `ImportError` on their first line —
they imported a function that does not exist. The registry listed them,
the JSON schemas derived correctly, `/api/tools` showed them; everything
worked except calling them. **Every tool needs a test that invokes it
through the registry**, the way the orchestrator does. Import-time
correctness proves nothing.

## 2. Run a new regression test against the PREVIOUS commit
It has caught something every single time it has been run. Twice it
caught a test that passed against the very code it was written to catch:
once because the request it used never reached the code path, once
because the function it stubbed had its exception swallowed by a
`try/except`. **A test you have not seen fail is not a test.**

## 3. A harness must print its own failures
The document classifier scored 1/13, and the classifier was fine — the
harness called a function that does not exist and swallowed the error,
returning `""` for every document. Sixth instance of the repo's
recurring bug class. **Never `except: pass` in measurement code.** If a
harness cannot do its job, it must say so loudly, and never report the
result as a property of the thing under test.

## 4. No fabricated data, not even labelled
The same invented approval payload (`FFC-201`, `1,450 → 1,667 m³/h`)
was removed three times: from the modal's `||` fallbacks, from the
backend chat handler, then from the streaming path after a merge. The
third copy sat behind a clear "SIMULATED" banner and still had to go —
at a demo with the backend down, it shows a confident refinery safety
interlock over numbers nobody measured. **Fields the system cannot know
are ABSENT.** An empty field reads as unknown; a plausible one reads as
measured.

## 5. Never let stale data stand in for live data
`/sources` and `/graph` silently fell back to committed JSON exports
when the backend was down, labelled `source: 'snapshot'`. The label was
accurate and insufficient: the page rendered a full plausible knowledge
base from another machine. **Default to an honest empty state**;
snapshots are opt-in.

## 6. A capability must exist on EVERY path that can reach it
Three instances: intent triage, the source filter, and memory each
existed on one of two endpoints. The pattern is always two entry points,
one implementation, and nothing forcing them together. **Fix it by
moving the logic somewhere both must call**, not by adding it to the
second place.

## 7. Validate endpoints where they are CONSTRUCTED
`OLLAMA_HOST` was read from the environment unchecked — one variable
away from sending every model call off the premises, silently. The
sovereignty claim was resting on a default value. `backend/utils/loopback.py`
resolves the host and refuses anything non-loopback. **A convention is
not a control.**

## 8. Confidential text is not retained past the thing that needs it
`requests.jsonl` held 191 approval records, the largest 11,344
characters, carrying full document sections — one headed
"Classification: Confidential - Internal Use" — forever, long after the
15-minute approval expired. Terminal requests now redact content and
keep the hash, so the record stays verifiable without being a second
copy of the corpus.

## 9. Numbers are traceable after the fact, not just during
Recording a calculation's working shows what happened while you watch
the trace. Every calculation now also carries a `calculation_id` written
to the append-only audit log, so "where did 162.4 come from" is a lookup
rather than a re-run that may not reproduce the inputs.

## 10. Ownership lives in ONE place and the docs are edited together
Row 7 was split between two owners, which made the output format a
dependency in both directions and left nothing built on either side.
`docs/OWNERSHIP.md` is the tie-breaker. When ownership changes, update
TOOLS.md, OWNERSHIP.md and BOTH assignment docs in the same commit and
**grep for contradictions afterwards**.

## 11. Check the work against the problem statement, repeatedly
```bash
py -3 -m backend.evaluation.ps_compliance
```
Verifies each PS26117 requirement against the live codebase — routes
imported, tools looked up in the registry, models read from
`models.yaml`. A row cannot stay green after the thing it describes is
deleted. Rows that cannot be checked from inside the process report
MANUAL rather than being counted as passes.

## 12. Test discipline
Run **the test files that touch the change**, not the whole suite (the
maintainer's standing instruction: a full run is ~800 tests and minutes of
waiting for no new information):
```bash
py -3 -m pytest backend/tests/test_<area>.py -q -m "not live_model"
cd frontend && npm test
```
The 8 `live_model` tests are two thirds of the wall time and **must not
be deleted or mocked**: they are the only ones that catch a model tag
that does not exist, a prompt the model silently stops parsing, and OCR
falling back to CPU. A mock passes while the real thing is broken.

## 13. Test from the chat box, not only the backend
On 26 Sep every backend test passed while the UI could not write a file
(the approval call never sent `request_id`), never showed a job card (an
undefined `handlers` object), and routed "Summarise … into a PDF report"
to a chat answer. **A capability is done when it works through the chat
box in a browser**: type the request, approve in the modal, find the file
in the Artifacts tab. `scratch`-style Playwright runs of exactly that
found all of the above in one afternoon.

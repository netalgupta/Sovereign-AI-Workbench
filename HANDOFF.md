# HANDOFF — Aryan's session, 2026-09-13

Written so the next context window resumes without re-deriving state.
**Nothing here is blocked or half-applied.**

Branch `aryan/rag-and-graphrag`. `main` is at the same commit.
Suite: **425 passed, 19 skipped.** Working tree clean at handoff.

---

## 1. State of the world

| | |
|---|---|
| `main` | fast-forwarded to the branch — the team pulls from `main` |
| `advay/frontend` | **merged in**, with three safety regressions fixed (§4) |
| Registered tools | 21 |
| TOOLS.md | every Aryan-owned 🔴 row is built |
| Embedding model | `bge-large-en-v1.5` on **cuda:0** |
| Typical turn | 17-25s warm; greetings/closings/capability **under 0.02s** |

### The 19 skips are environmental, not failures
Docker Desktop and Neo4j are stopped on this box, so the sandbox tests,
the graph tests and the unpulled `phi-3.5-mini` router test skip as
designed. Start Docker and they run. All three degrade correctly at
runtime; none is a regression.

### Servers must be restarted after a branch switch
A `git checkout` across many commits rewrites hundreds of files under
`--reload`. Vite keeps serving **stale config** and 404s `/api/chat`
instantly (0.013s) while the backend is healthy. Diagnosed twice; do
not debug it as a code bug.

---

## 2. What this session built

**Routing** — intent triage in `router_node`, the entry point of the
one graph both endpoints share. Greetings, closings, capability
questions and bare arithmetic skip the pipeline. Arithmetic still runs
the registered tool; the fast path skips retrieval, never the
calculation.

**Memory, all six audit gaps** — `backend/memory/turn.py` is the single
`open_turn`/`close_turn` pair both paths call; `digest.py` condenses
turns that fall out of the six-message window (extractive, records what
was ASKED and CONSULTED, never what was ANSWERED); facts supersede on
subject and expire from last use; `episodic.py` reuses answers keyed on
corpus generation; `all_chunk_texts()` is cached (19.6ms → 1.3ms at
2000 chunks, linear).

**Safety** — intercepted actions resolve to a real registered tool call
before approval is requested, so approving runs what was displayed.
Signature blocks are stripped from answers. The file-write gate now
sees requests as people write them.

**Ingestion** — document KIND classifier (row 9), 13/13 against the
corpus's own folder labels.

**Compliance** — spec checker (row 56) that computes status rather than
reading the document's own, and reports disagreements.

---

## 3. Open items, in the order I would take them

### a. The agentic path under-extracts on lookups
The loop retrieves correctly then fails to pull the value out. Routing
hides it for the common case (lookups go to `direct`), but it still
applies to genuinely multi-step requests. The cause is scaffolding:
`/api/chat` has a grounding prompt tuned against measured failures; the
loop hands raw passages to a 7B with a general prompt.

### b. The verifier cannot confirm table values
Measured, not suspected: the value sat at character 513 of a 675-char
chunk it was shown in full. phi3.5 false-negatives; qwen2.5:7b
false-**positives** (passed a pressure with no units). The small model
is kept deliberately — waving through a wrong number is worse than
over-flagging.

### c. PaddleOCR still on CPU
`paddle.device.is_compiled_with_cuda()` is False. `paddlepaddle-gpu`
pulls separate multi-GB NVIDIA libs alongside torch's bundled ones —
the cascading-conflict shape that broke this environment before. Wants
a venv and a deliberate decision.

### d. `models.yaml` carries a stand-in named like the real thing
`verify-coder-7b` maps to `qwen2.5:7b` with `task_tags: [code]`, added
in the frontend branch. CARD 04 wants `qwen2.5-coder:7b`, which is not
pulled. A registry entry whose id says "coder" and whose model is not a
coder will route code tasks to a general model and look correct doing
it. Either pull the real tag or rename the entry.

### e. Tool rows deliberately not built
All of Aryan's 🔴 rows are done. What remains is 🟡/⚪ and needs
something this environment does not have:

| Row | Why not |
|---|---|
| 6 P&ID symbol extraction | needs tagging conventions to tune against |
| 7 Defect detection (YOLOv8) | needs a labelled dataset and a fine-tune |
| 8, 10, 11 | ⚪ registry-listed; no demo depends on them |
| 19 Cross-reference resolver | ⚪ |
| 25 Long-running checkpointing | ⚪ |
| 27 Maxima CAS | SymPy covers the demo's symbolic work |
| 57, 59 | ⚪/🟡 MRPL-specific, no corpus to validate against |

Per CLAUDE.md's demo-day priorities these can stay registry-listed
without weakening the architecture claim.

### f. Not mine, listed so they are not lost
`qwen2.5-coder:7b` unpulled and `code_agent` raises pending CARD 04
(Aditya). Kanishka 0/7 built. Sahil 0/3.

---

## 4. What arrived with the frontend merge, and what I changed

`origin/advay/frontend` merged clean and the suite passed with all
three of these present. Each is now pinned by a test that fails against
the merge commit.

1. **The fabricated approval payload came back, in the backend.**
   `DCS_SETPOINT_WRITE`, `HCU-2 / FFC-201`, `100% (1,450 m³/h)` →
   `115% (1,667 m³/h)`, `risk_level CRITICAL` — hardcoded for every
   intercepted action, so "draft an approval note" asked an operator to
   authorise a feed-rate change. Removed from `ApprovalModal.jsx` and
   moved into the backend, which made a visible fallback an invisible
   claim.
2. **An approval could be manufactured.** `/api/approvals/resolve`
   caught any failure from `approve()` and registered a *new* request
   instead — silently renewing expired approvals, minting a second
   single-use token, and approving ids that never existed.
3. **A refusal that was not recorded reported success.**

**Kept, because they are real fixes:** interception on the streaming
path (it had no action gate at all), a real `ApprovalGate` request from
`run_agent_loop`, and `GET /api/audit` — `log.entries()` does not exist
on `AuditLog`, so every call without a `request_id` was a 500. My bug,
his catch.

---

## 5. Things that will bite you if you do not know them

**The embedding model is gitignored.** 1.3 GB, does not arrive with a
pull. Without it retrieval silently uses hash vectors: searches return
results, answers carry citations, content is wrong. Cost a teammate a
full session. `py -3 -m backend.ingestion.fetch_models`. Startup prints
an unmissable block and `/api/health` reports `embedding_backend`.

**Tests have pinned defects in place five times.** A test asserting a
fabricated value makes the honest fix fail the suite. Found in: the
approval payload, the planner (asserting a tangled plan must RAISE),
the gate (pinning a literal string), and twice this session a test that
passed against the very code it was written to catch — one because the
request it used never reached the code path, one because the function
it stubbed had its exception swallowed. **Run a new regression test
against the previous commit before trusting it.** That check has caught
something every time it was run.

**Self-deceiving measurement is this repo's recurring bug class, six
instances.** A stale JSON artifact outliving its code; a resume path
caching a score instead of model output; `%g` formatting making whole
numbers unmatchable; a GPU benchmark measuring VRAM contention and
reporting it as a property of `num_gpu`; hash embeddings passing every
shape assertion; and a classifier harness that called a function which
does not exist, swallowed the error, and scored the classifier 1/13 for
it. **Check the provenance of anything derived from a stored artifact,
and make harnesses print their own failures.**

**The graph has been lost three times** to a container without a named
volume. Rebuild in seconds, zero LLM calls:
`py -3 -m backend.evaluation.build_graph`.

**Where the data lives** (all gitignored, all local):
`backend/memory/sessions.db`, `backend/memory/long_term.db`,
`backend/audit/audit.jsonl`, `outputs/` for drafted deliverables.

---

## 6. Where the documentation is

| File | What it is |
|---|---|
| `docs/OWNERSHIP.md` | **The tie-breaker** when documents disagree |
| `docs/STATUS.md` | Built vs pending, per person, from live data |
| `docs/RUNNING.md` | How to start it, what is normal, what to expect |
| `docs/INTEGRATION.md` | Every endpoint and its shape |
| `docs/Technical_Specs/AGENT_STREAM_PROTOCOL.md` | The SSE contract |
| `docs/TEAM_KICKOFF_MESSAGE.md` | Group + per-person kickoff text |

---

## 7. Deviations from spec, all deliberate and documented

- **RAG_SPEC §4's verbatim prompt was changed.** Its own wording
  (`include a citation marker [N]`) caused models to emit the literal
  `[N]`. The refusal clause is unchanged; only how the format is
  conveyed. The spec should be updated to match.
- **Self-verification moved off the critical path.** 9s resident, 102s
  when it had to reload. Now `POST /api/verify` behind a button;
  `WORKBENCH_VERIFY_INLINE=1` restores blocking behaviour.
- **The LLM planner is skipped for single-intent lookups**, and for
  instant intents entirely. It cost 10.9s against 4.3s to answer and
  invented steps that failed.
- **The fallback plan no longer calls a model.** It used `classify_task`
  — an LLM call with a retry — to pick a label for a step that does
  nothing. Measured at ~37s of a 47s turn.

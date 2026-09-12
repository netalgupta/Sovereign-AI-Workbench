# HANDOFF — Aryan's session, 2026-09-13

Written before an auto-compaction so the next context window can resume
without re-deriving state. **Nothing here is blocked or half-applied.**

Branch `aryan/rag-and-graphrag`. `main` is at the same commit.
Suite: **389 passed, 1 skipped.** Working tree clean at handoff.

---

## 1. State of the world

| | |
|---|---|
| `main` | fast-forwarded to the branch — the team pulls from `main` |
| Endpoints | 46 |
| Registered tools | 19 |
| TOOLS.md rows | 72, all owned, 35 built |
| Embedding model | `bge-large-en-v1.5` on **cuda:0** |
| Reasoning model | `qwen2.5:7b` (registry id `reasoning-model`) |
| Typical turn | 17-25s warm; greetings/closings/capability **under 0.02s** |

### Servers must be restarted after a branch switch
A `git checkout` across 79 commits rewrites hundreds of files under
`--reload`. Both dev servers end up in a bad state — vite keeps serving
**stale config** and 404s `/api/chat` instantly (0.013s) while the
backend is healthy. Diagnosed once already; do not debug it as a code
bug.

---

## 2. What was built this session

**Retrieval** — hybrid dense+BM25+RRF (BM25 tokenization was broken:
`text.split()` on both sides, so half the retriever never matched),
query expansion, neighbour expansion (procedures were truncated at chunk
boundaries), a hybrid confidence gate, source filtering.

**Agent** — real tool calling via Ollama's native function calling,
`POST /api/chat/stream` (SSE) that **routes itself**, a curated
`CHAT_TOOLS` set (19 tools broke a 7B model's selection), repeat-search
suppression, unverified-arithmetic detection.

**Memory** — sessions with primary ids, working memory with focus
documents, follow-up query resolution, long-term preferences that
**refuse to store document findings**.

**Intent triage** (just landed) — greetings, capability questions,
closings and bare arithmetic skip the pipeline entirely.

**Safety** — approval gate over 5 categories, sandbox with proven egress
isolation, network monitor scoped to this process.

**GPU** — `torch 2.9.1+cu126` (same version, CUDA build, `--no-deps`).
Embeddings 99% CPU → **41%**, 64 embeddings in 0.09s.

---

## 3. Open items, in the order I would take them

### a. ~~Greeting latency~~ — CLOSED, `4ee534f`
Two causes, both found by probing the endpoint instead of the helper:

1. **The triage never ran on the path the product uses.** It was wired
   into `decide_path()`, which only `/api/chat/stream` consults; the
   frontend posts to `/api/chat`, which enters the LangGraph
   orchestrator. "Hola Amigo" still cost **50.80s**. Every intent test
   passed the whole time, because they all tested `classify()` rather
   than an endpoint. Triage now lives in `router_node` — the one graph
   both paths share.
2. **`_emit_plan` ran above the instant-path check.** A greeting is not
   a "simple lookup" (no question opener), so it fell through to the LLM
   planner and spent 10.5s planning a turn about to be answered from a
   constant. Capability looked *faster* only because "what can you do"
   starts with "what" and matched the opener.

Warm, both endpoints: greeting **0.003s / 0.014s**, closing
**0.001s / 0.008s**, capability **0.387s / 0.008s**.

The four graph-level tests were run against the previous commit and all
four fail there — worth repeating, because `_emit_plan` catches
`Exception`, so a raising stub degrades to a one-step plan and every
shape assertion still passes. Asserting the planner was **not called**
is what makes that test real.

### b. Agentic path under-extracts on lookups
The loop retrieves correctly and then fails to pull the value out.
Routing hides it for the common case (lookups go to `direct`), but it
still applies to genuinely multi-step requests. The cause is
scaffolding: `/api/chat` has a grounding prompt tuned against measured
failures; the loop hands raw passages to a 7B with a general prompt.

### c. `all_chunk_texts()` loads the whole corpus per query
Fine at 52 documents, will not hold at 1000-page PDFs. The BM25 index is
cached; this is not.

### d. Verifier cannot confirm table values
Measured, not suspected: the value sat at character 513 of a 675-char
chunk it was shown in full. phi3.5 false-negatives; qwen2.5:7b
false-**positives** (passed a pressure with no units). The small model
is kept deliberately — waving through a wrong number is worse than
over-flagging.

### e. Memory has no summarisation/compaction
At ~40 turns the working window truncates silently. Same failure class
as the context-overflow bug already hit once.

### f. PaddleOCR still on CPU
`paddle.device.is_compiled_with_cuda()` is False. `paddlepaddle-gpu`
pulls separate multi-GB NVIDIA libs alongside torch's bundled ones —
the cascading-conflict shape that broke this environment before. Wants a
venv and a deliberate decision.

### g. Not mine, listed so they are not lost
`qwen2.5-coder:7b` unpulled (Aditya, CARD 04). Kanishka 0/7 built,
Sahil 0/3 — both blocked on nobody.

---

## 4. Things that will bite you if you do not know them

**The embedding model is gitignored.** 1.3 GB, does not arrive with a
pull. Without it retrieval silently uses hash vectors: searches return
results, answers carry citations, content is wrong. This cost a teammate
a full session — he asked for his own assignments and got an answer
about a different person. `py -3 -m backend.ingestion.fetch_models`.
Startup now prints an unmissable block, `/api/health` reports
`embedding_backend`, and every degraded turn says so.

**Tests have pinned defects in place three times.** A test asserting a
fabricated value makes the honest fix fail the suite. Found in: the
approval payload (`DCS_SETPOINT_WRITE`, `FFC-201`, `risk_level
CRITICAL`), the planner (asserting a tangled plan must RAISE), and the
gate (pinning the literal string "Safety Interlock Gate"). When a test
fails after a correctness fix, check which one is wrong.

**Self-deceiving measurement is this repo's recurring bug class.** Now
five instances: a stale JSON artifact outliving its code; a resume path
caching a score instead of the model output; a `%g` formatting bug
making whole numbers unmatchable; a GPU benchmark measuring VRAM
contention and reporting it as a property of `num_gpu`; and hash
embeddings returning correctly-shaped garbage that every shape assertion
passed. **Check the provenance of anything derived from a stored
artifact.**

**The graph has been lost three times** to a container without a named
volume. Rebuild in seconds, zero LLM calls:
`py -3 -m backend.evaluation.build_graph`.

---

## 5. Where the documentation is

| File | What it is |
|---|---|
| `docs/OWNERSHIP.md` | **The tie-breaker** when documents disagree |
| `docs/STATUS.md` | Built vs pending, per person, from live data |
| `docs/RUNNING.md` | How to start it, what is normal, what to expect |
| `docs/INTEGRATION.md` | Every endpoint and its shape |
| `docs/Technical_Specs/AGENT_STREAM_PROTOCOL.md` | The SSE contract with Netal |
| `docs/TEAM_KICKOFF_MESSAGE.md` | Group + per-person kickoff text |
| `TASKS.md` | Older task list, superseded by STATUS.md |

---

## 6. Deviations from spec, all deliberate and documented

- **RAG_SPEC §4's verbatim prompt was changed.** Its own wording
  (`include a citation marker [N]`) caused models to emit the literal
  `[N]`. The refusal clause is unchanged; only how the format is
  conveyed. Flagged at the constant — the spec should be updated to
  match.
- **Self-verification moved off the critical path.** 9s resident, 102s
  when it had to reload. Now `POST /api/verify` behind a button.
  `WORKBENCH_VERIFY_INLINE=1` restores blocking behaviour.
- **The LLM planner is skipped for single-intent lookups.** It cost
  10.9s against 4.3s to answer and invented steps that failed.

# Open task list — chat/retrieval/runtime hardening

Working list for the current session. Every item is either DONE with the
evidence that proves it, or OPEN with what specifically is wrong.
Nothing is marked done on the strength of "the code looks right" — this
codebase has already shipped a synthesize step that never called a
model, a verifier hardcoded to pass, and a GPU measurement that measured
VRAM contention instead of the flag it named.

---

## DONE (committed and pushed)

| # | Problem | Evidence it is fixed |
|---|---|---|
| 1 | Network monitor counted the whole machine — "44 external connections" on a zero-egress product | Scoped to own process tree; `externalCount` 0, `hostExternalCount` reported separately |
| 2 | `synthesize_node` never called a model; templated `[1][2]` onto invented sentences | Calls `generate_grounded_answer`; live answer cites `Novolen_Batch_QA_Report_Aug2026.pdf` |
| 3 | Fabricated safety assurance on zero evidence: "All parameters remain within nominal design thresholds" | Refuses; regression test names the phrase so it cannot return |
| 4 | `verify_node` fed `parse_verification` a hardcoded `satisfied: true` | Real verifier, fails closed, verdict surfaced in the reply and the API |
| 5 | Approval gate matched only "feed rate"; SAP/file/send/delete ran ungated | 5 categories covered, tested; gate quotes the operator's own words |
| 6 | Every math step computed the literal `"381.95 - 400"` | Extracts real arithmetic; `(12+8)*3` balances to 60, not 36 |
| 7 | `fast-router: phi-3.5-mini` — tag does not exist on Ollama | `phi3.5`, pulled, verified `100% GPU` |
| 8 | Vite intercepted 9 API routes; the configured proxy was never reached | Backend wins when `/api/health` answers |
| 9 | Fabricated `SAP_Plant_Sensors_API` / `DCS_SCADA_Telemetry_Feed` "live connectors" | Deleted; corpus reports 50 real files, not 52 |
| 10 | 484 lines of hardcoded demo chat + a permanent "Retrieving sources" timer | Deleted; ChatPane 1360 -> 741 lines |
| 11 | Dev-server startup silently erased tracked folders | Load/save split; `docs` (19 files) restored |
| 12 | Model picker: 4 hardcoded strings, selecting did nothing | Reads `/api/models`, shows real status and "not pulled" |
| 13 | 60s frontend timeout vs 69s backend — live path could never win | 300s; backend errors reported rather than silently simulated |
| 14 | Blank chat bubble | Failsafe: the reveal animation can no longer hide an answer |

## DONE (this session, not yet committed)

| # | Problem | Evidence |
|---|---|---|
| 15 | Turn logger existed but defaulted OFF — invisible unless you knew the env var | Defaults ON (off under pytest); user's console now shows the full trace |
| 16 | Logger crashed on Windows cp1252 and the exception was swallowed, replacing a real answer with "I could not complete this analysis" | ASCII-only output; `_emit` cannot raise |
| 17 | Startup noise (CUDA / absl / oneDNN / tf_keras) buried every real line | `quiet_startup` runs before heavy imports — **needs a full server restart, not a reload** |
| 18 | Bare refusals on topics visibly present in the corpus | Refusal names closest documents + the margin |
| 19 | **BM25 tokenized with `text.split()` on both sides** — case-sensitive, punctuation-attached. `"inspection"` never matched `"Inspection"`. Half the hybrid retriever was inert | Shared `lexical.tokenize`; identifiers like `SOP-114-Rev3` kept whole |
| 20 | BM25 index rebuilt from scratch on **every query** | Cached, keyed on corpus identity |
| 21 | Confidence gate was dense-only; strong keyword evidence could not rescue a bad embedding | Hybrid gate. `"Tell me abt inspection"` now found via lexical; Pride and Prejudice / FIFA / chocolate cake still refused |
| 22 | GPU: earlier conclusion "num_gpu does nothing, always 100% CPU" was **wrong** — it measured VRAM contention | On an idle card: unset -> 26/74 CPU/GPU; `num_gpu=99` -> **100% GPU**. Wired via `ollama_client` |
| 23 | Four modules hand-rolled their own `/api/generate` call, so any shared option missed three of them | Single `ollama_client.generate`; all four wired |
| 24 | Corpus-level questions ("summarise the data you have") went through chunk retrieval, which cannot answer them | Answered from the document registry — real names, counts, sizes, nothing generated |

---

## OPEN

### 31. `qwen2.5-coder:7b` not pulled
CARD 04 / Aditya's `code_agent`. Out of scope here, listed so it is not
mistaken for an oversight.

### 32. Model swap thrash (partially mitigated)
The planner and verifier ran on different models, 9.5 GB total on an
8.2 GB card, so Ollama evicted and reloaded twice per turn. Skipping
the planner for simple lookups removed one swap. The verifier still
runs on `fast-router` while generation runs on `reasoning-model`, so
one swap per turn remains. Keeping the two under 8 GB together, or
shrinking the verifier's context, would remove it -- not yet measured.

### 33. Planner still emits nonsense steps for complex requests
Only simple lookups bypass it. For anything routed to the real planner,
the `code` / `math` step selection is still weak ("create standard
operating procedures" dispatched to the sandbox). Needs the §6 closed
tool sets enforced at plan time, not just at dispatch.

---

## DONE this session (continued)

| # | Problem | Evidence |
|---|---|---|
| 25 | Sandbox auto-PULLED from Docker Hub when the image was absent — an outbound call, constraint #1 | Presence checked locally; raises with the build command. Image built (first time ever): `python 3.11.15`, `numpy 1.26.4 sympy 1.12`, **egress blocked** |
| 25a | Image could never build — `useradd -u 1000` exit 4, UID taken by the base image | Reuses the existing UID-1000 user |
| 25b | `SESSIONS_HOST_DIR = "/tmp/..."` on Windows — Docker made an empty anonymous mount, so every script "did not exist" | `tempfile.gettempdir()` |
| 26 | Thin answers: right document ranked 4th, buried at the end of the sources block | Query expansion put `SOP-114-Rev3` at **rank 1**; answers now carry real procedure steps |
| 27 | Query builder | `query_builder.py` — additive domain expansion, retrieval-only, never rewrites the user's request |
| 28 | Reasoning model too slow | Measured 5 known-answer questions: 7b **4/5 @ 4.6s avg**, 3b 4/5 @ 3.4s, 14b 4/5 @ 32.5s. Chose 7b — 3b misread a spec table row (11.2 for a 3.4 question) |
| 29 | Citation contract broken — literal `[N]`, prose citations, zero markers | Root cause was **RAG_SPEC §4's own verbatim prompt text**. Deviation applied and documented |
| 29a | My first fix made it worse — naming "citation marker" to ban it made 3b answer `'[Citation marker]: [4]'` | Form shown by example, forbidden token never quoted |
| 30 | Pipeline trace absent from the chat UI | `TurnTrace` in MessageBubble — real plan, real tool output, real verdict, collapsed by default |
| 34 | **Verifier reported "no readable verdict" on every answer** — phi3.5 returned valid JSON then appended training boilerplate; `json.loads` choked on the trailing prose | Brace-balanced object extraction. Verdicts now PASS; still fails closed on genuine garbage |
| 35 | Turn took 127s | **17-20s steady state.** Planner skipped for single-intent lookups (it cost 10.9s vs 4.3s to answer, and invented a `code` step that failed) |
| 36 | Model wrapped whole answers in a ` ```markdown ` fence, rendering them as grey code blocks | Unwrapped when the entire answer is one md fence; real code blocks untouched |

---

## Known-unknown, recorded deliberately

The blank-chat-bubble root cause is **still unknown**. I attributed it to
`setDisplayedContent` mishandling an updater function and shipped that
claim in a commit message — but `useTypewriter.js` is dead code and the
live path (`useMessageTypewriter`) passes strings. The store fix was a
real defect; it was not this one. The failsafe is what made answers
appear. Recorded rather than quietly dropped, because an unexplained
fix is a fix that can come undone.

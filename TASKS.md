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

### 25. Sandbox tries to PULL from Docker Hub — constraint #1 violation
`containers.run()` auto-pulls when `mrpl-sandbox:combined` is absent, so
a missing image becomes an **outbound network call** on a product whose
first hard constraint is that it makes none. The 404 in the console is
the symptom; the egress attempt is the actual defect. Image has never
been built. Must fail loudly with the build command instead.

### 26. Answers are thin — retrieval finds the right document, generation under-uses it
"Give sops for Hydrocrackers" put `SOP-114-Rev3` at rank 4 and returned
a 3-row metadata table (document number, effective date, review cycle)
plus one summary sentence. The actual procedure content was in the
chunk and went unused. Two suspected causes, both to be measured rather
than assumed:
  - the right document ranks 4th of 5, so its chunk sits late in the
    sources block
  - nothing in the prompt asks for procedural completeness

### 27. Query builder / query understanding
Raised directly by the user. Short, abbreviated, imperative queries
("Give sops for Hydrocrackers", "Tell me abt inspection") retrieve worse
than their written-out forms. Needs: normalisation, domain synonym
expansion (SOP <-> standard operating procedure, HCU <-> hydrocracker),
and plural/singular handling — applied to the retrieval query only,
never to the text shown to the model as the user's request.

### 28. Reasoning model too slow on this laptop
`qwen2.5:14b` is 9.0 GB and takes 57s for one generation even at 100%
GPU. User asked for a 3-4B model. `qwen2.5:3b` pulling. Must **measure
answer quality before switching**, not just speed — a fast wrong answer
is worse than a slow right one on this product.

### 29. Citation contract is being broken by the model
Trace evidence: 2 literal `[N]` placeholders stripped in one turn, and
an answer that wrote `(Novolen_Batch_QA_Report_Aug2026.pdf, p.1)` inline
instead of `[1]` — final answer had **zero** citation markers. The
validator catches and strips, but the model should not be producing it.

### 30. Retrieval stages not shown in the chat UI
Backend returns `plan` and `tool_call_events`; they are attached to the
message but `MessageBubble` does not render them. The console trace has
this information and the UI does not.

### 31. `qwen2.5-coder:7b` not pulled
CARD 04 / Aditya's `code_agent`. Out of scope here, listed so it is not
mistaken for an oversight.

---

## Known-unknown, recorded deliberately

The blank-chat-bubble root cause is **still unknown**. I attributed it to
`setDisplayedContent` mishandling an updater function and shipped that
claim in a commit message — but `useTypewriter.js` is dead code and the
live path (`useMessageTypewriter`) passes strings. The store fix was a
real defect; it was not this one. The failsafe is what made answers
appear. Recorded rather than quietly dropped, because an unexplained
fix is a fix that can come undone.

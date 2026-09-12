# INTEGRATION.md — what exists today, and how to call it

Written so nobody has to read backend source to find out whether
something is built. Every endpoint below is live on
`aryan/rag-and-graphrag` and was enumerated from the running server, not
from intent.

**37 endpoints. 17 registered tools. 350 tests passing.**

---

## Chat

### `POST /api/chat`
```json
{ "message": "What is the SOP for Hydrocracker", "session_id": "abc" }
```
Returns:
```json
{
  "reply": "markdown string",
  "citations": [{"text": "...", "source_document": "...", "page_number": 2, "score": 0.03}],
  "plan": [{"step_id": "...", "description": "...", "assigned_agent": "retrieval", "status": "done", "depends_on": []}],
  "tool_call_events": [{"tool_name": "hybrid_search", "input_params": {}, "output": {}, "status": "done"}],
  "verification": null,
  "awaiting_human_approval": false,
  "approval_action": null,
  "session_id": "abc"
}
```

Notes that will save you time:
- `reply` is **GitHub-flavoured markdown** — tables, headings, code
  blocks, `[1]` citation markers. Render it as markdown.
- `verification` is `null` on a normal turn. Verification is on demand.
- A refusal is a normal 200 response whose `reply` explains what was
  missed and names the closest documents. It is not an error.
- Typical latency 17-25s warm, 45-80s on the first call after start.
  **Do not set a client timeout below 300s.** One that was set to 60s
  against a 69s backend meant no live answer was ever displayed.

### `POST /api/verify`
```json
{ "request": "the original question", "answer": "the answer text" }
```
Returns `{ "passed": bool, "outcome": "...", "reason": "...", "checked_claims": [], "sources_checked": 7 }`.

Runs the §5 self-check on demand. **Can take 100s** — it loads a second
model. Show a progress state. Sources are re-retrieved server-side; do
not send your own.

---

## Sources and ingestion

| Endpoint | Purpose |
|---|---|
| `GET /api/corpus` | Every source with `category`, `subcategory`, size, folder, full path, plus a `tree` and `directories` |
| `GET /api/sources` | Flat source list |
| `POST /api/sources` | Add a watched folder |
| `DELETE /api/sources?path=...` | Remove a source |
| `POST /api/sources/scan` | Rescan watched folders |
| `POST /api/sources/upload` | Upload a file |
| `POST /api/sources/ingest` | Ingest a path. Returns `job_id` |
| `GET /api/ingestion/{job_id}` | Per-document stage, failures with reasons, ETA |
| `GET /api/ingestion` | Recent jobs |
| `POST /api/sources/dialog/files` / `folder` | Native OS picker |
| `GET /api/preview` | Page image from the user's own file |

`category` is one of `documents` / `data` / `charts`, derived from the
extension — this drives the sidebar filter tabs. It was missing until
recently, which made every filter tab count zero against real data.

---

## Retrieval internals (for inspection UIs)

| Endpoint | Purpose |
|---|---|
| `POST /api/search` | Hybrid search, returns ranked chunks with scores |
| `GET /api/chunks` | All chunks with metadata |
| `POST /api/chunk` | Chunk arbitrary text with the production chunker |
| `POST /api/embed` | Embed text (1024-d, L2-normalised) |
| `GET /api/metrics` | Corpus/index statistics |
| `GET /api/contradictions` | Cross-document contradictions |
| `GET /api/images` | Stored images with OCR text and descriptions |
| `POST /api/images/select` | The right image for a request |
| `GET /api/images/{id}/raw` | Image bytes |

---

## Graph

`GET /api/graph` — all nodes with every property, and typed edges.
Degrades to a committed snapshot when Neo4j is down, with `source`
saying which you got. An empty live graph is reported as a problem, not
served as truth.

---

## Tools

| Endpoint | Purpose |
|---|---|
| `GET /api/tools` | Every registered tool with its JSON schema |
| `POST /api/tools/call` | Call one |

17 registered. Schemas are **derived from type hints and docstrings**,
so they cannot drift from the implementation.

Flags that matter:
- `requires_approval` — enforced **in the dispatcher**, so it cannot be
  forgotten by whoever adds the next tool
- `is_estimate` — the vision tools set this. It is not decorative: the
  chart model was measured inventing 10 numeric values across 2 of 6
  charts and describing them as *"the numeric values printed as text on
  the chart"*. Anything flagged as an estimate must be labelled as one
  wherever it is displayed.

---

## Approvals (hard constraint #4)

| Endpoint | Purpose |
|---|---|
| `POST /api/approvals/request` | Create a pending approval |
| `POST /api/approvals/approve` / `refuse` | Operator decision |
| `POST /api/approvals/execute` | Run the approved call |
| `GET /api/approvals` | Pending + history |
| `POST /api/approvals/resolve` | Frontend modal convenience |

Approval is per-call and argument-hashed, single-use, and expires. It
describes the **effect**, not the call. There is deliberately no
auto-approve flag.

---

## System

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Corpus loaded, graph availability, image and document counts |
| `GET /api/models` | Registry with **real** availability from Ollama, real sizes, and the pull command for anything missing |
| `GET /api/system-info` | CPU, RAM, real GPU via nvidia-smi |
| `GET /api/network/status` | Zero-egress proof |
| `GET /api/audit` | Append-only audit log |
| `POST /api/plan` | Decompose a request into a step DAG |

`GET /api/network/status` returns `externalCount` for **this process
tree** and `hostExternalCount` for the machine, separately. It used to
count every socket on the host, so the UI displayed *"ALERT: External
Traffic — 44 external connections"* on a zero-egress product; all 44
belonged to the browser, the IDE and Spotify. Drive the alarm from
`externalCount` only.

---

## Conventions

1. **Markdown, not plain text.** `reply` is markdown. So are generated
   documents' text fields.
2. **A refusal is a success.** 200 with an explanatory `reply`. Do not
   render it as an error.
3. **Citations are `[n]`,** resolving into the `citations` array by
   1-based index. Invalid markers are stripped server-side.
4. **Never fabricate placeholder content.** Empty states only. Hardcoded
   demo data shipped to production once here; it included six invented
   instrument readings marked "Normal" and two fake live plant
   connectors.
5. **Long operations need progress, not spinners.** Ingestion and
   verification both have progress endpoints; use them.

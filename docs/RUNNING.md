# RUNNING.md — start the system, and read what it is doing

Everything here is verified working on `aryan/rag-and-graphrag` as of
this document. If a command fails, that is a bug — say so rather than
working around it.

---

## 1. Prerequisites

| Thing | Check | If missing |
|---|---|---|
| Python 3.13 | `py -3 --version` | install |
| Ollama running | `ollama list` | start Ollama |
| Models pulled (Ollama) | `curl localhost:8000/api/models` | see §2 |
| **Embedding model on disk** | `curl localhost:8000/api/health` -> `embedding_backend` | **see §2b — gitignored, does not come with a pull** |
| Node + npm | `node -v` | install |
| Docker Desktop | `docker ps` | only needed for the sandbox and Neo4j |

---

## 2. Models

`GET /api/models` tells you the truth about what is present, rather than
what is configured:

```
coder-model        qwen2.5-coder:7b   not_pulled    Run: ollama pull qwen2.5-coder:7b
reasoning-model    qwen2.5:7b         available     4.7 GB
vision-model       qwen2.5vl:7b       available     6.0 GB
fast-router        phi3.5             available     2.2 GB
```

Chat works with `reasoning-model` alone. `coder-model` is only needed
for CARD 04 (Aditya's code agent).

**Two model tags in this repo were wrong and never worked**, so verify
rather than assume: `qwen2-vl:7b` and `phi-3.5-mini` do not exist on
Ollama. `ollama pull <tag>` fails instantly on a bad tag — that is the
cheapest possible check.

---

## 2b. Fetch the local models — DO THIS FIRST ON A NEW MACHINE

```bash
py -3 -m backend.ingestion.fetch_models
```

Needs internet **once**. After that the system is fully offline — every
model-backed tool loads only from `models/<category>/` and never checks
a hub.

**Why this is not optional, and why forgetting it is dangerous.**
`models/embeddings/` is **gitignored** (1.3 GB), so it does NOT arrive
with a `git pull`. Without it, embeddings fall back to hash vectors,
which carry no semantic meaning — and nothing appears broken. Searches
return results. Answers carry citations. The content is simply wrong.

This happened on a teammate's machine. Asked for one person's
assignments, retrieval returned two other people's files and the answer
described a third person entirely. Adding a single backslash to the
query changed the whole result set, because hash vectors have no notion
of meaning for a typo to survive.

**How to tell:**
```bash
curl -s localhost:8000/api/health
```
`embedding_backend` must read `bge-large-en-v1.5`. If it says
`deterministic-hash`, retrieval is meaningless — the backend also logs a
large warning at startup and on every affected turn.

---

## 3. Backend

```bash
cd E:/Hackathons/26117
py -3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Bound to loopback deliberately. This API reads the user's filesystem;
`0.0.0.0` would expose it on every interface of a machine that may sit
on a plant network.

Health check:

```bash
curl -s localhost:8000/api/health
```

### Reading the turn trace

Tracing is **on by default**. Every chat turn prints, in order: the
request, what the search query was expanded to, every retrieved chunk
with its score and source, the confidence threshold, the model called,
what citation validation changed, the final answer's markdown structure,
and a per-stage timing summary.

```bash
# everything, including the full prompt and raw model output
WORKBENCH_TRACE=full py -3 -m uvicorn backend.main:app --port 8000 --reload

# silence it
WORKBENCH_TRACE=off ...
```

It is off automatically under pytest.

**Restart, do not reload, after pulling changes that touch startup.**
`TF_CPP_MIN_LOG_LEVEL` and friends are read by TensorFlow's C++ layer at
import time, so `--reload` cannot apply them — the library noise will
come back until you stop and re-run the process.

---

## 4. Frontend

```bash
cd E:/Hackathons/26117/frontend
npm install     # first time only
npm run dev     # http://localhost:5173
```

The dev server proxies `/api` to `127.0.0.1:8000`.

**Important, and it caused weeks of confusion:** `vite.config.js`
contains a plugin that implements nine `/api` routes itself. It now
steps aside whenever the real backend answers `/api/health`, but if you
start the frontend *without* the backend you are talking to the dev
server's own filesystem scan, not the corpus. Start the backend first.

---

## 5. Optional services

### Neo4j (graph)
```bash
docker run -d --name sih26117-neo4j-test \
  -p 7474:7474 -p 7687:7687 \
  -v sih26117_neo4j_data:/data \
  -e NEO4J_AUTH=neo4j/testpassword123 \
  -e NEO4J_dbms_usage__report_enabled=false \
  neo4j:5
```
The **named volume is mandatory** — the graph has been lost twice to a
container without one. Rebuild from the committed extraction cache in
seconds, no LLM calls:
```bash
py -3 -m backend.evaluation.build_graph
```

### Sandbox
```bash
docker build -t mrpl-sandbox:combined -f backend/sandbox/Dockerfile.sandbox backend/sandbox
```
Without it the backend logs that the sandbox is disabled and continues;
chat, retrieval, graph and tools all work. It will **never pull** the
image — a missing image is an error with the build command, not a
download, because this system makes no outbound network calls.

---

## 6. Tests

```bash
py -3 -m pytest backend/tests -q -p no:randomly
```
Expect **370 passed, 1 skipped**. The skip is Neo4j when Docker is down.

---

## 7. What to expect, in numbers

Measured on an RTX 4060 laptop (8 GB), warm:

| Stage | Time |
|---|---|
| Retrieval (hybrid + gate) | ~0.15s |
| Generation (qwen2.5:7b) | 4-25s depending on answer length |
| **Typical full turn** | **17-25s** |
| First turn after start | 45-80s (models load) |

Self-verification is **not** in this path. It runs on demand via the
Verify button (`POST /api/verify`) because it is a second LLM call on a
different model, and on an 8 GB card that means evicting the generation
model — measured at 9s when the verifier was resident and **102s** when
it had to reload.

**VRAM note:** a 7B generation model and any second model do not both
fit on 8 GB, so Ollama evicts one per turn. That is a hardware limit,
not a bug; it is why the first turn is slow and why running two chats
concurrently will be much slower than twice one chat.

---

## 8. If something looks wrong

| Symptom | Most likely cause |
|---|---|
| Answer is blank, "streaming…" forever | Hard-reload the browser |
| "Not found in the loaded corpus" on a topic you can see in Sources | Read the trace: it prints the best similarity, the threshold, and the closest documents |
| **Answers cite real documents but describe the wrong subject entirely** | **Embedding model missing — `/api/health` will say `deterministic-hash`. Run §2b.** |
| Sources list shows files you do not have | You are on the dev server's fallback — the backend is not running |
| Every answer says "not confirmed" | Expected for table values; the verifier is a 3.8B model and false-negatives on them |
| `Could not start sandbox pool` | Build the image (§5) or ignore it |
| Library warnings flooding the console | Restart the process, do not reload |

## Running the tests without waiting three and a half minutes

Measured: the full suite is 212s, and **8 tests are 127s of that**. They
are the ones that call a real model through Ollama or load a
multi-hundred-megabyte model from disk.

```bash
# Fast loop while iterating -- 443 tests, 85s
py -3 -m pytest backend/tests -q -m "not live_model"

# The 8 slow ones on their own -- 120s
py -3 -m pytest backend/tests -q -m "live_model"

# Everything. Run this before you commit, every time.
py -3 -m pytest backend/tests -q
```

**The slow ones are not optional and must not be deleted.** They are
precisely the tests that catch the failures this repo keeps having:

- a model tag in `models.yaml` that does not exist on Ollama (happened
  twice -- `qwen2-vl:7b` and `phi-3.5-mini`, both found only when
  something tried to use them)
- a prompt the model silently stops parsing (the planner and the
  verifier both did this, and both were fixed after a live trace)
- OCR falling back to CPU without saying so (21.08s vs 0.61s)
- the full graph path dispatching and refusing correctly

A mocked version of any of those passes while the real thing is broken.
That is the whole reason they are slow: they are the only tests touching
the parts that cannot be faked.

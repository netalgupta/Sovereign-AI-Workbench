# VIBECODING_SPEC.md — Zero-Ambiguity Task Cards
Every 🔴 demo-critical tool from TOOLS.md, broken into a task card an AI coding agent (Claude Code / Antigravity) can execute with no invented assumptions. Each card is self-contained: exact file path, exact function signature, exact schema, exact commands, exact definition of done. When prompting the agent, paste the whole card as the instruction — don't summarize it, don't paraphrase it.

**Rule for whoever writes new cards later:** if a card leaves a decision unstated (which port, which field name, which exception type), the agent will guess, and a guess is a hallucination risk. Every blank must be filled before the card is used.

---

## CARD 01 — Model Registry Loader
**Owner:** Aryan | **File:** `/backend/models/registry.py`

**Exact function signature:**
```python
def load_registry(path: str = "/models/models.yaml") -> dict[str, ModelConfig]:
```

**ModelConfig schema (pydantic):**
```python
class ModelConfig(BaseModel):
    id: str
    backend: Literal["ollama"]
    model: str
    task_tags: list[str]
```

**Exact `models.yaml` shape** (already defined in DEPENDENCIES.md §1 — use these exact entries, do not invent additional fields):
```yaml
- id: coder-model
  backend: ollama
  model: qwen2.5-coder:7b
  task_tags: [code_generation, code_review, debugging]
- id: reasoning-model
  backend: ollama
  model: qwen2.5:14b
  task_tags: [summarization, drafting, approval_notes, planning]
- id: vision-model
  backend: ollama
  model: qwen2-vl:7b
  task_tags: [ocr, image_understanding, diagram_reading]
- id: fast-router
  backend: ollama
  model: phi-3.5-mini
  task_tags: [classification, routing]
```

**Install command:** `pip install pydantic pyyaml --break-system-packages`

**Step-by-step:**
1. Read the YAML file at `path` using `yaml.safe_load`
2. Validate each entry against `ModelConfig`
3. Return a dict keyed by `id`
4. Raise `FileNotFoundError` with the exact message `f"Model registry not found at {path}"` if the file is missing — do not silently return an empty dict
5. Raise `pydantic.ValidationError` unmodified if an entry is malformed — do not catch and suppress it

**Test command:** `pytest backend/tests/test_registry.py -v`
**Definition of done:** loading the sample YAML above returns exactly 4 `ModelConfig` entries with the exact `id` values shown; a missing file raises the exact exception above; a malformed entry (e.g. missing `model` field) raises unmodified.

**Anti-hallucination note:** do not invent a 5th default model, do not add a `max_tokens` field unless a later card specifies one, do not assume Ollama is already running — that's CARD 02's job.

---

## CARD 02 — Ollama Health Check + Model Pull Verification
**Owner:** Aryan | **File:** `/backend/models/ollama_client.py`

**Exact function signature:**
```python
def verify_models_available(registry: dict[str, ModelConfig], ollama_host: str = "http://localhost:11434") -> dict[str, bool]:
```

**Step-by-step:**
1. `GET {ollama_host}/api/tags` — this is Ollama's exact documented endpoint for listing locally pulled models, do not use a different path
2. Parse the JSON response's `models` array, extract each entry's `name` field
3. For each `ModelConfig` in the registry, check if `model` (e.g. `"qwen2.5-coder:7b"`) appears in the pulled-models list
4. Return `{model_id: bool}` for every registry entry
5. If the request to `ollama_host` fails (connection refused), raise `ConnectionError` with the exact message `f"Ollama not reachable at {ollama_host} — is it running?"` — do not retry silently, do not fall back to a different host

**Test command:** `pytest backend/tests/test_ollama_client.py -v` (mock the HTTP call with `responses` library — install via `pip install responses --break-system-packages`)
**Definition of done:** function correctly reports `True`/`False` per model against a mocked Ollama response; connection failure raises the exact exception text above, verified in a test with `pytest.raises(ConnectionError, match="Ollama not reachable")`.

---

## CARD 03 — Task Router / Classifier
**Owner:** Aryan | **File:** `/backend/orchestrator/router.py`

**Exact function signature:**
```python
def classify_task(user_input: str, router_model_id: str = "fast-router") -> list[str]:
```

**Exact prompt template (use verbatim, do not paraphrase — consistency matters for the 90% accuracy target in FR-3):**
```
You are a task classifier. Given the user's request, output ONLY a JSON array of task tags from this exact list: ["code_generation", "code_review", "debugging", "summarization", "drafting", "approval_notes", "planning", "ocr", "image_understanding", "diagram_reading"]. Output nothing except the JSON array. If multiple tags apply, include all of them.

User request: {user_input}
```

**Step-by-step:**
1. Format the prompt above with `user_input` inserted at `{user_input}`
2. Call the `fast-router` model via Ollama's `/api/generate` endpoint with `stream: false`
3. Strip any markdown code fences (` ```json ` / ` ``` `) from the response before parsing
4. `json.loads()` the result — if parsing fails, retry once with an appended instruction `"Output ONLY the JSON array, no other text."`; if it fails a second time, raise `ValueError(f"Router could not classify: {user_input!r}")`
5. Validate every returned tag exists in the fixed list above — drop any tag that isn't in the list rather than raising (a router hallucinating an extra tag should degrade gracefully, not crash the pipeline)

**Test command:** `pytest backend/tests/test_router.py -v` — must include the exact 20-prompt mixed test set referenced in REQUIREMENTS.md FR-3, stored at `/backend/tests/fixtures/router_test_set.json`

**Definition of done:** ≥18/20 prompts in the fixture set classified correctly (90% per FR-3's literal acceptance criterion — do not round this down).

**Anti-hallucination note:** the task tag list above is the ONLY valid set. Do not let the agent invent new tags like `"math"` or `"vision"` without updating this card, `models.yaml`, and TOOLS.md all three in the same change.

---

## CARD 04 — Sandboxed Code Execution
**Owner:** Aditya | **File:** `/backend/sandbox/executor.py`

**Exact function signature:**
```python
def run_in_sandbox(code: str, language: Literal["python"], timeout_seconds: int = 30) -> SandboxResult

class SandboxResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
```

**Exact Docker invocation (do not substitute a different base image or flags):**
```bash
docker run --rm \
  --network none \
  --memory=512m \
  --cpus=1 \
  --read-only \
  --tmpfs /tmp \
  -v /tmp/sandbox_input:/sandbox/input:ro \
  python:3.11-slim \
  timeout {timeout_seconds}s python /sandbox/input/script.py
```

**Step-by-step:**
1. Write `code` to a temp file at `/tmp/sandbox_input/script.py` (create the directory if missing)
2. Execute the exact `docker run` command above via `subprocess.run`, capturing stdout/stderr, with `timeout=timeout_seconds + 5` on the subprocess call itself (5s buffer beyond the container's internal timeout)
3. Set `timed_out=True` if the subprocess raises `subprocess.TimeoutExpired`, and set `exit_code=-1` in that case
4. Clean up the temp file after execution regardless of outcome (`finally` block)
5. **Never** run the code outside this container. There is no fallback path that executes user/agent-generated code directly on the host.

**Test command:** `pytest backend/tests/test_sandbox.py -v` — must include a test that attempts a network call from inside the sandboxed code (e.g. `import urllib.request; urllib.request.urlopen('http://example.com')`) and asserts it fails, proving `--network none` is actually enforced, not just configured

**Definition of done:** valid Python code returns correct stdout and `exit_code=0`; code that raises an exception returns the traceback in `stderr` and a non-zero `exit_code`; code that runs longer than `timeout_seconds` returns `timed_out=True`; network-access attempt fails inside the container.

---

## CARD 05 — PaddleOCR Wrapper
**Owner:** Sahil (UI) / Aryan (integration) | **File:** `/backend/tools/vision/ocr_printed.py`

**Exact function signature:**
```python
def extract_printed_text(image_path: str) -> OCRResult

class OCRResult(BaseModel):
    full_text: str
    lines: list[OCRLine]

class OCRLine(BaseModel):
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x_min, y_min, x_max, y_max
```

**Install command:** `pip install paddlepaddle paddleocr --break-system-packages`

**Step-by-step:**
1. Initialize `PaddleOCR(use_angle_cls=True, lang='en')` — cache this instance at module level, do not re-initialize per call (initialization is expensive)
2. Call `.ocr(image_path, cls=True)`
3. PaddleOCR's raw output is `[[[bbox_points], (text, confidence)], ...]` — convert `bbox_points` (4 corner points) into the `(x_min, y_min, x_max, y_max)` tuple format specified above by taking min/max across the 4 points
4. Concatenate all line texts with `"\n"` for `full_text`
5. If `image_path` does not exist, raise `FileNotFoundError` before calling PaddleOCR — do not let PaddleOCR's own (less clear) error surface

**Test command:** `pytest backend/tests/test_ocr_printed.py -v` — fixture image at `/backend/tests/fixtures/sample_printed_doc.png` (a public-domain scanned document image, per the PS's own note that only public datasets are needed for the demo)

**Definition of done:** on the fixture image, `full_text` contains the known expected substring defined in the test; every `OCRLine.confidence` is between 0.0 and 1.0; missing file raises `FileNotFoundError` with a message containing the attempted path.

---

## CARD 06 — DOCX Approval Note Generator
**Owner:** Kanishka (viewer) / Aditya (trigger) | **File:** `/backend/tools/output/docx_approval_note.py`

**Exact function signature:**
```python
def generate_approval_note(
    title: str,
    findings: list[str],
    recommendation: str,
    output_path: str,
    source_citations: list[str],
) -> str:  # returns output_path on success
```

**Install command:** `pip install python-docx --break-system-packages`

**Exact document structure (in this order, no reordering):**
1. Heading (level 1): `title`
2. Paragraph: `"Date: {today's date, format YYYY-MM-DD}"` (use `datetime.date.today().isoformat()`)
3. Heading (level 2): `"Key Findings"`
4. Bulleted list, one bullet per entry in `findings`
5. Heading (level 2): `"Recommendation"`
6. Paragraph: `recommendation`
7. Heading (level 2): `"Sources"`
8. Bulleted list, one bullet per entry in `source_citations` — **this section must never be empty**; if `source_citations` is an empty list, raise `ValueError("Approval note cannot be generated with zero source citations — this violates NFR-4")` rather than silently producing an ungrounded document

**Step-by-step:**
1. Validate `source_citations` is non-empty (raise per above if not)
2. Build the `Document()` object per the structure above using `python-docx`'s `add_heading`, `add_paragraph`, `add_paragraph(style='List Bullet')`
3. Save to `output_path`
4. Return `output_path`

**Test command:** `pytest backend/tests/test_docx_approval_note.py -v`
**Definition of done:** generated file opens correctly with `python-docx`'s own reader in the test (round-trip check); document contains all 7 structural elements listed above in the exact order; empty `source_citations` raises the exact `ValueError` text above.

**Anti-hallucination note:** this is the literal PS example output ("drafting an approval note as a Word file"). Do not let the agent add speculative sections (e.g. "Risk Assessment," "Budget Impact") that weren't in `findings`/`recommendation` — the document must only contain what was actually passed in.

---

## CARD 07 — Network Monitor Poller
**Owner:** Aditya | **File:** `/backend/audit/network_monitor.py`

**Exact function signature:**
```python
def get_active_connections() -> list[ConnectionInfo]

class ConnectionInfo(BaseModel):
    local_address: str
    remote_address: str
    status: str
    is_external: bool
```

**Install command:** `pip install psutil --break-system-packages`

**Step-by-step:**
1. Call `psutil.net_connections(kind='inet')`
2. For each connection, extract `laddr`, `raddr`, `status`
3. `is_external = True` if `raddr` exists AND its IP is not in `127.0.0.0/8`, not in the Docker internal bridge range (`172.16.0.0/12` — confirm against your actual `docker network inspect` subnet, do not assume `172.17.0.0/16` without checking), and not `0.0.0.0`
4. Return the full list, sorted by `is_external` descending (external connections surface first — if any exist during the demo, they must be immediately visible, not buried)

**Test command:** `pytest backend/tests/test_network_monitor.py -v`
**Definition of done:** function correctly flags a known-external test connection (mock a connection with `raddr=("8.8.8.8", 443)`) as `is_external=True`, and a loopback connection as `is_external=False`.

**Anti-hallucination note:** do NOT hardcode "0 external connections, always" anywhere in the UI or backend as a static label. The panel must reflect the actual live `is_external` count from this function every polling cycle (recommend 1-second interval via websocket push from Aditya's API). A hardcoded "0" defeats the entire purpose of NFR-1/FR-15 and would be a fabricated proof, not a real one.

---

## CARD 08 — SymPy Verified Calculation Tool
**Owner:** Aryan | **File:** `/backend/tools/math/symbolic_calc.py`

**Exact function signature:**
```python
def evaluate_expression(expression: str, variables: dict[str, float] | None = None) -> CalcResult

class CalcResult(BaseModel):
    expression: str
    result: str
    steps: list[str]
```

**Install command:** `pip install sympy --break-system-packages`

**Step-by-step:**
1. Parse `expression` with `sympy.parsing.sympy_parser.parse_expr` — **never** use Python's built-in `eval()` on the raw string, this is both a security risk (arbitrary code execution) and the exact class of "LLM did unverified math" problem this tool exists to prevent
2. If `variables` provided, substitute via `.subs(variables)`
3. Simplify step-by-step: capture the expression at each `.simplify()` / `.subs()` stage into the `steps` list as strings
4. Final numeric or symbolic result goes in `result` as a string (use `str(sympy_result)`, not a raw float, to preserve exact fractions/symbolic forms when relevant)
5. If parsing fails, raise `ValueError(f"Could not parse expression: {expression!r}")` — do not attempt a "best guess" fallback

**Test command:** `pytest backend/tests/test_symbolic_calc.py -v`
**Definition of done:** `evaluate_expression("2*x + 3", {"x": 5})` returns `result="13"` with at least 1 entry in `steps`; malformed expression raises the exact `ValueError` above; a call using `eval()` anywhere in this file fails a code-review check (grep the file for `eval(` as a CI/lint step).

---

## CARD 09 — Hybrid Retrieval (Dense + BM25)
**Owner:** Aryan | **File:** `/backend/retrieval/hybrid_search.py`

**Exact function signature:**
```python
def hybrid_search(query: str, top_k: int = 5) -> list[RetrievedChunk]

class RetrievedChunk(BaseModel):
    text: str
    source_document: str
    page_number: int | None
    score: float
```

**Install commands:** `pip install faiss-cpu sentence-transformers rank_bm25 --break-system-packages`

**Step-by-step:**
1. Embed `query` using `sentence-transformers` with model `BAAI/bge-large-en-v1.5` (exact model name, do not substitute a different bge variant without updating DEPENDENCIES.md)
2. Dense search: FAISS index `.search(query_embedding, top_k * 2)` (over-fetch by 2x before fusion)
3. Sparse search: `rank_bm25.BM25Okapi` over the same corpus, tokenized with `.split()` (simple whitespace tokenization — do not add stemming/lemmatization unless a later card specifies it, to keep behavior predictable)
4. Fuse with Reciprocal Rank Fusion: `score = sum(1 / (60 + rank))` across both rankings for each chunk (k=60 is the standard RRF constant — use it exactly, don't tune it without documenting why)
5. Return top `top_k` chunks by fused score, each with its `source_document` and `page_number` populated from the ingestion metadata (never leave these `None` if the source metadata exists — a missing citation is a grounding failure per NFR-4)

**Test command:** `pytest backend/tests/test_hybrid_search.py -v`
**Definition of done:** given a small fixture corpus (`/backend/tests/fixtures/sample_sops/`) and a query with a known correct answer document, that document appears in the top 3 results; every returned `RetrievedChunk` has a non-null `source_document`.

---

## Template for Any New Card (use this exact skeleton — do not deviate)

```
## CARD NN — <Tool Name>
**Owner:** <name> | **File:** `<exact path>`

**Exact function signature:**
```python
<signature>
```

**Exact schema(s):**
```python
<pydantic models>
```

**Install command:** `<exact pip/npm command>`

**Step-by-step:**
1. ...
2. ...

**Test command:** `<exact command>`
**Definition of done:** <measurable, checkable statement — never "works correctly", always a specific assertion>
**Anti-hallucination note:** <what the agent must NOT assume, invent, or fabricate for this specific tool>
```

Every blank in every card must be filled before it's handed to the coding agent. An unfilled blank is where a guess — and therefore a hallucination — enters the codebase.

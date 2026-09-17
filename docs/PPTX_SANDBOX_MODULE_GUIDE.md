# PPTX Generation & Docker Sandbox Module Guide

> **Author**: Aditya (Backend & Sandbox Lead)  
> **Audience**: All Team Members (Aryan, Advay, Sahil, Netal, Kanishka)  
> **Status**: Production-Ready, Tested & Verified (All 8 Test Cases Passing)  
> **Repository Target**: `backend/orchestrator/slide_agent.py`, `backend/tools/generation/slide_kit.py`, `backend/sandbox/`

---

## 1. Executive Summary & Design Philosophy

The **PPTX Generation Module** provides an air-gapped, sovereign capability to automatically generate executive-grade, on-brand PowerPoint presentations (`.pptx`) from technical user queries and the MRPL document corpus.

### The Sovereign Separation Principle:
* **"What to Say" is AI-driven**: The reasoning LLM decomposes the user query into logical sections, retrieves grounded citations from the MRPL corpus, and fills structured JSON data fields adhering to strict schemas.
* **"How it Looks" is Fixed Code**: The LLM **never** writes Python drawing code, coordinates, shapes, or visual styles. All layout, brand typography, geometry, and color tokens are defined by fixed Python XML manipulation in [`backend/tools/generation/slide_kit.py`](../backend/tools/generation/slide_kit.py) using the pre-designed master template [`PPTX/MRPL_Template.pptx`](../PPTX/MRPL_Template.pptx).
* **Network-Isolated Sandbox Rendering**: The actual file generation script executes inside a warm, egress-blocked Docker container (`--network none`) via `run_in_sandbox()`, ensuring total code and resource containment.

---

## 2. The 19 Pre-Granted Slide Molds

Every generated presentation is assembled by duplicating and populating slides from [`PPTX/MRPL_Template.pptx`](../PPTX/MRPL_Template.pptx). The template contains 19 hand-crafted master slides mapping directly to technical industrial use cases:

| Mold ID | Purpose / Layout | Key Data Fields |
|---|---|---|
| `executive_summary` | Deck opening / strategic takeaways | `headline`, `points: list[str]` (up to 4) |
| `title_bullets` | Narrative explanation & findings | `title`, `bullets: list[str]` (up to 5), `citations` |
| `stat_callout` | Single huge metric (e.g. 15.02 MMTPA) | `big_number`, `label`, `supporting_narrative` |
| `multi_stat_row` | 3 to 4 side-by-side KPI metric cards | `stats: list[dict(val, label)]` |
| `comparison_cards` | 2 to 3 comparative cards (units/options) | `cards: list[dict(title, text)]` |
| `chart_commentary` | High-res trend/telemetry chart + notes | `chart_image_path`, `commentary` |
| `process_flow` | Stage-gate sequence of operational steps | `steps: list[str]` (with arrow progression) |
| `timeline` | Milestone phases with dates/durations | `phases: list[dict(date, event)]` |
| `quote_highlight` | Communique or management directive | `quote`, `attribution` |
| `image_caption` | P&ID schematic / CAD diagram view | `image_path`, `caption` |
| `safety_alert` | Urgent warning / interlock trip alert | `severity`, `alert_title`, `description` |
| `table_data` | Structured telemetry/spec table | `headers: list[str]`, `rows: list[list[str]]` |
| `two_column` | Trade-offs / Before vs. After comparison | `left_title`, `left_body`, `right_title`, `right_body` |
| `risk_matrix` | HAZOP risk severity assessment | `risks: list[dict(name, likelihood, impact)]` |
| `org_or_flow_chart` | Approval hierarchy & governance | `nodes: list[str]` |
| `section_divider` | Visual break between operational units | `section_title`, `subtitle` |
| `agenda` | Table of contents & meeting structure | `agenda_items: list[str]` |
| `generic_grid` | Flexible 4-box modular fallback | `boxes: list[dict(title, body)]` |
| `flexible_highlight` | High-priority highlight cards | `headline`, `highlight_points` |

---

## 3. End-to-End Pipeline Workflow

When a user submits a prompt like *"Generate a presentation on crude distillation unit limits"*:

```
User Prompt (Chat)
      │
      ▼
[1. Orchestrator Router & Planner]
      │  - Detects presentation intent (pptx, slides, deck)
      │  - Automatically EXEMPTS from hazardous action approval modal
      │  - Dispatches PlanStep with assigned_agent="slide"
      ▼
[2. Slide Agent: plan_deck_outline()]
      │  - Breaks topic into 5-7 logical slides with provisional mold IDs
      ▼
[3. Content Fetch & Grounding Loop]
      │  - Queries RAG hybrid search for real document citations
      │  - Evaluates plant parameters and telemetry
      ▼
[4. Slide Filler: fill_slide_content()]
      │  - Populates Pydantic mold schemas with factual data & citation IDs
      │  - Writes `context.json` to session workspace
      ▼
[5. Docker Sandbox Render (run_in_sandbox)]
      │  - Docker worker executes in container with `--network none`
      │  - Reads context.json, duplicates template molds, replaces tags
      │  - Writes output `.pptx` to shared session volume
      ▼
[6. Automated QA Engine (qa_render.py)]
      │  - Heuristic QA: checks for text overflow, unreplaced tags, empty tables
      │  - Bounded self-correction: retries up to 2 times on failing slides
      ▼
[7. Presentation Synthesis & Delivery]
      │  - Returns formatted deliverable payload with download button
      ▼
Frontend: RealOutputCards.jsx (Immediate Download Card)
```

---

## 4. The Docker Sandbox Setup ("The Docker Thingy")

### Why Run in the Sandbox?
In a refinery environment, all file generation and script execution must be **strictly air-gapped and sandboxed**:
1. Zero network egress (`--network none`).
2. Hard resource caps (`512MB RAM`, `1 CPU core`, `read-only rootfs`).
3. Isolated filesystem (`tmpfs /tmp` + per-session host mount).

### Are the Template and Generation Code Inside Docker?
**YES! Everything is pre-baked directly into the container image (`mrpl-sandbox:combined`).**

Teammates building the sandbox image have **both** the code and master PowerPoint template already baked inside:
```dockerfile
# From backend/sandbox/Dockerfile.sandbox:

RUN mkdir -p /sandbox/lib && chown -R 1000:1000 /sandbox
COPY backend/tools/generation/slide_kit.py /sandbox/lib/slide_kit.py
COPY PPTX/MRPL_Template.pptx /sandbox/lib/mrpl_template.pptx
ENV PYTHONPATH="/sandbox/lib"
```

* **No download needed**: The template is never downloaded or recreated at runtime.
* **No template path confusion**: Inside the container, `slide_kit.py` automatically resolves the template at `/sandbox/lib/mrpl_template.pptx`.
* **Zero host dependency**: Even if the host machine has no PowerPoint software or Office installed, the container compiles valid, self-contained `.pptx` binaries.

### How Host and Container Communicate:
The sandbox uses a shared directory:
* **Host path**: `os.path.join(tempfile.gettempdir(), "mrpl_sandbox_sessions", session_id)`
* **Container path**: `/sandbox/sessions/<session_id>`

1. The host writes `context.json` containing the slide plan into the session folder.
2. The orchestrator calls `run_in_sandbox()` to execute a small runner script:
   ```python
   import json
   from slide_kit import build_deck
   with open('/sandbox/sessions/<session_id>/context.json', 'r') as f:
       plan = json.load(f)
   build_deck(plan, out_path='/sandbox/sessions/<session_id>/MRPL_Executive_Briefing.pptx')
   ```
3. The container compiles the presentation and saves it directly to the mounted folder.
4. The host reads the resulting `.pptx` file directly from the session folder.

---

## 5. Team Setup & Run Instructions

### Step 1: Build the Sandbox Container (Run Once)
Run this command from the repository root:
```bash
docker build -t mrpl-sandbox:combined -f backend/sandbox/Dockerfile.sandbox .
```
*(This bakes Python 3.11, `python-pptx`, `pydantic`, the scientific stack, `slide_kit.py`, and `MRPL_Template.pptx` into the image.)*

### Step 2: Verify the Sandbox Environment
Run this test one-liner to confirm the container can find `python-pptx` and the template:
```bash
docker run --rm mrpl-sandbox:combined python -c "
import pptx, pydantic
from slide_kit import resolve_template_path
print('pptx version:', pptx.__version__)
print('pydantic version:', pydantic.__version__)
print('Template resolved at:', resolve_template_path())
"
```
**Expected output**:
```text
pptx version: 1.0.2
pydantic version: 2.7.1
Template resolved at: /sandbox/lib/mrpl_template.pptx
```

### Step 3: Run the Automated Unit Tests
Run the dedicated PPTX test suite in your local virtual environment:
```bash
~/venv/bin/pytest backend/tests/test_slide_agent.py -v
```
**All 8 tests should pass**:
* `test_template_exists`
* `test_slide_schemas`
* `test_build_deck_creates_valid_presentation`
* `test_heuristic_qa_defect_detection`
* `test_plan_deck_outline`
* `test_fetch_and_fill_slide`
* `test_slide_pipeline_end_to_end` *(executes genuine Docker sandbox rendering)*
* `test_presentation_safe_deliverable_exemption`

### Step 4: Run an End-to-End Orchestrator Turn
To verify full chat integration from Python:
```bash
~/venv/bin/python -c "
from backend.orchestrator.graph import run_agent_turn
res = run_agent_turn('Generate a presentation on crude distillation unit limits', session_id='team_demo')
print('Turn output:\n', res.draft_output)
"
```
**Output**:
```text
**Presentation generated successfully.**

- **Deliverable:** `MRPL_Generate_a_presentation_on_cru_Briefing.pptx` (37 KB)
- **Slides:** 5 on-brand slides formatted via MRPL master template
- **Grounded Citations:** 5 verified citations [1] [2] [3] [4] [5]

The deliverable is available for immediate download in the **Output Cards** pane.
```

---

## 6. Frontend Hand-Off (Advay, Sahil, Netal, Kanishka)

1. **Prepared, then approved**: `prepare_deck` plans, fills and QA-renders the deck inside the sandbox and writes nothing a user receives. The approval card lists the filename, every slide title, the sources, and any section left out for lack of a source.
2. **Approval gate (hard constraint #4)**: `generate_deck` is registered with `requires_approval=True`, like `draft_docx`. It renders exactly the approved plan, with no model call, into `outputs/`. (An earlier "safe deliverable exemption" let decks be written unapproved; it was removed.)
3. **Download Button**: The deliverable appears in the **Output Cards** panel (`RealOutputCards.jsx`) with:
   * Title / Document Name
   * Slide Count badge (e.g. `5 Slides`)
   * Grounded Citation badges (`[1]`, `[2]`, `[3]`)
   * Direct **Download** button pointing to the generated `.pptx` file.

---

## 7. Air-Gapped Deployment Packaging

When shipping the Sovereign Workbench to an air-gapped facility on a portable drive (per `DEPENDENCIES.md`):

```bash
# 1. Save the pre-baked Docker image to a portable tarball
docker save mrpl-sandbox:combined -o mrpl-sandbox.tar

# 2. On the air-gapped target machine (zero internet required):
docker load -i mrpl-sandbox.tar
```
Because the master template and generation libraries are inside `mrpl-sandbox:combined`, the entire PPTX subsystem is 100% operational immediately upon `docker load`.

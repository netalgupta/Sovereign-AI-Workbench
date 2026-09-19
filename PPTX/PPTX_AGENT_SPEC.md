# PPTX Generation Subsystem — Design Spec for `slide_agent`

> Hand this file to the coding agent alongside the existing `CLAUDE.md`. It assumes the architecture already documented in `backend/orchestrator/`, `backend/retrieval/`, `backend/sandbox/`, `backend/audit/`, and `models/models.yaml`. Nothing here overrides the hard constraints in `CLAUDE.md` — it's an implementation of one new capability inside them.

## 1. Goal
Add a `slide_agent` capability that turns a user request + the existing document corpus into a downloadable, on-brand `.pptx`, fully offline, with every visible fact traceable to a source and every number coming from an executed tool call — never from the LLM "just writing" a number or a layout.

## 2. Core principle
Separate **"what to say"** (LLM's job) from **"how it looks"** (fixed, hand-built, never generated at runtime). The LLM only ever chooses *which* pre-built slide design fits its content and supplies the *content* to fill it — it never writes layout/drawing code, and it never invents a new visual design on the fly.

## 3. The two-agent content pipeline

Both "agents" are the **same LLM** (`reasoning-model` / `qwen2.5:14b` per your registry), called twice with different jobs. No second model needed — cheaper on the 8GB VRAM budget than running two models concurrently.

### 3a. Planner (call 1)
- Input: the user's request + a short description of what document types/sections exist (from `retrieval`).
- Output: a deck outline — list of ~8-12 sections, each with:
  - a working title
  - a **rough** mold guess (see §4) — this is provisional, not final
  - a short note on what content that section needs
- This call should be small (fits comfortably in an 8k context call) and does not yet contain real facts.

### 3b. Content fetch (deterministic, not an LLM call)
- For each section in the outline, in a loop:
  - Call `retrieval_agent` (existing hybrid FAISS+BM25 grounded retrieval) for that section's topic.
  - If the section needs a computed number, call `math_tool` (existing deterministic function, never LLM arithmetic).
  - If the section references a diagram/photo, pull it from `ImageStore` by `image_id`.
- Result: a per-section bundle of real, sourced content (text snippets + citations + numbers + image paths). Nothing invented yet.

### 3c. Filler (call 2, per section)
- Input for one section: the real content bundle from 3b + **the full mold menu** (not just the planner's guess — see §4).
- Job:
  1. Confirm or correct the mold choice now that real content is known (e.g., planner guessed "bullets" but there are actually 3 comparable numbers → switch to comparison mold).
  2. Fill in the exact fields the chosen mold requires (see §4 schema).
  3. If no named mold fits well, fall back to one of the **generic/flexible molds** (§4.3) — never invent a new layout.
- Output: one slide's worth of structured JSON matching the chosen mold's schema, with citation IDs attached to every factual field.
- Use `"format": <MoldSchema>.model_json_schema()` on this call (Ollama supports this per your registry) — do not rely on regex-parsing free text.

### 3d. Assemble `context.json`
- Concatenate all filled slide JSONs into one deck plan file, written to the session's sandbox-mounted directory (`/tmp/sandbox_sessions/<session_id>/context.json`).
- This is the **only** thing that crosses into the sandbox — the sandbox has no DB/network access, so everything must be fully resolved before this point.

## 4. The mold library (`slide_kit`)

A fixed, hand-authored Python module (`backend/tools/generation/slide_kit.py`), copied into `Dockerfile.sandbox` at **build time** (not fetched at runtime — stays fully offline). Contains one render function per mold, each pre-styled with the brand tokens from `graphTheme.js` (amber `#C26A10`/`#F59E0B`, teal `#12798C`/`#06B6D4`, slate `#0F172A`/`#1E293B`, coral `#A63927`/`#F43F5E`, emerald `#2F7A52`/`#10B981`) and the MRPL logo assets.

### 4.1 Named molds — finalized set for MRPL-style decks
| # | Mold ID | Looks like | Key fields | When Filler picks it |
|---|---|---|---|---|
| 1 | `title_bullets` | Title + up to 5 bullets | `title`, `bullets[]` | Fallback default — narrative points, no strong structure |
| 2 | `stat_callout` | One huge number, small label below | `big_number`, `label`, `context_sentence` | A single headline metric — e.g. plant utilization % |
| 3 | `multi_stat_row` | 3-4 small stat cards side by side | `stats[]` (value + label each) | Several related KPIs — throughput, uptime, safety days, yield |
| 4 | `comparison_cards` | 2-3 vertical cards | `items[]` (title + 2-3 points each) | Comparing options/scenarios — vendor A vs B, current vs proposed |
| 5 | `chart_commentary` | Chart on one side, short text on other | `chart_image_path`, `commentary` | Any trend — production volume, cost, downtime hours |
| 6 | `process_flow` | Boxes connected by arrows, left to right | `steps[]` (label + short note each) | Unit operation sequence, workflow, approval chain (dependency, not time) |
| 7 | `timeline` | Horizontal steps with dates/phases | `phases[]` (label + date/duration) | Turnaround schedule, project rollout, SOP sequence with time gates |
| 8 | `quote_highlight` | Large italic pulled line + accent bar | `quote_text`, `attribution` | A notable line from a report, audit finding, exec statement |
| 9 | `image_caption` | Large image/diagram + caption strip | `image_path`, `caption` | P&ID schematic, equipment photo, plant layout |
| 10 | `safety_alert` | Coral/red accent banner, icon, bold text | `alert_title`, `detail`, `severity` | Incident callouts, interlock/safety-critical info — visually distinct on purpose |
| 11 | `table_data` | Clean bordered table | `headers[]`, `rows[][]` | Spec sheets, compliance checklists, tolerance ranges |
| 12 | `two_column` | Even split, header per side | `left`/`right` {title, points} | Before/after, as-is vs to-be, pros/cons |
| 13 | `risk_matrix` | Grid/heat-map, colored cells | `risks[]` (label, likelihood, impact) | Risk assessments — standard in industrial reporting |
| 14 | `org_or_flow_chart` | Boxes in a hierarchy | `nodes[]` (label, parent_id) | Approval chains, reporting structure, escalation paths |
| 15 | `executive_summary` | Headline + 3-4 mini icon+text blocks | `headline`, `points[]` (icon_hint + text) | Deck-opening or closing summary slide |
| 16 | `section_divider` | Big title, minimal else | `section_title` | Between major deck sections |
| 17 | `agenda` | Numbered list, clean | `items[]` | Deck opening — what's covered |

Notes:
- `stat_callout` vs `multi_stat_row`: one big number is *the* headline of a slide; 3-4 smaller stats read as a dashboard snapshot — keep these separate, don't merge.
- `process_flow` vs `timeline`: flow is about *sequence/dependency*, timeline is about *when* things happen — SOPs/workflows vs project schedules are genuinely different content shapes.
- `safety_alert` and `risk_matrix` are MRPL-specific additions (not typical generic-deck molds) — expect these to get real use given the refinery/compliance context.

Each mold's field list is its "menu card" — the *only* thing the Filler agent sees when deciding what to write. It never sees pixel coordinates, fonts, or colors.

### 4.2 Design quality rules (baked in once, inherited by every slide forever)
- Fixed type scale (title/subtitle/body sizes always in the same ratio)
- Fixed margins/spacing — never edge-to-edge
- Brand colors used only as accents (bars, icon backgrounds, highlighted numbers) — never full-slide fills
- A "topping" system: optional small variations within a mold (accent box behind one bullet, icon bullets instead of dots, optional side image) that the Filler can request without it counting as a new layout

### 4.3 Generic fallback molds (the guardrail)
Build 2-3 deliberately flexible, still-hand-designed molds as a safety net:
- `generic_grid` — 1 to 4 content blocks, pixel-safe at any count
- `flexible_highlight` — adjustable number of boxes
These absorb anything that doesn't fit a named mold, so "the agent makes something new" only ever means "falls back to a pre-built stretchy mold," never "writes new layout code."

## 5. Render step (`code_agent`, inside existing warm sandbox)

- Add `python-pptx==1.0.2` to `Dockerfile.sandbox` (one-line addition, confirmed compatible with existing image).
- The LLM-generated script for this step is trivial and the same every time:
  ```python
  from slide_kit import build_deck
  import json
  plan = json.load(open("context.json"))
  build_deck(plan, out_path="deck.pptx")
  ```
- Runs via the existing `pool.acquire(session_id)` warm worker — no new container-lifecycle work needed.
- Output `deck.pptx` lands on host at `/tmp/sandbox_sessions/<session_id>/` automatically (existing zero-copy bind mount).

## 6. QA loop

1. **Heuristic checks (in-process, cheap):** text-overflow via python-pptx's own text-frame/font metrics, shape-overlap detection, contrast checks against the fixed palette. Run these first — most issues are cheap to catch here.
2. **Visual pass (`qwen2.5vl:7b`):** convert `deck.pptx` → PNG per slide, then send to the vision model for a layout/readability critique.
   - **Do this conversion host-side**, not inside the sandbox. `soffice`/`poppler` are heavy for a 512MB/1-CPU sandboxed container and this isn't untrusted code anyway — put it in `backend/tools/generation/qa_render.py`, called directly by `dispatch_node` against the file already sitting on the host filesystem.
3. **Bounded retry:** on any defect, feed the specific issue back into the **Filler** step (3c) for just the affected slide (e.g. "slide 4 bullet list has 9 items, this mold caps at 5"), re-render, re-check. **Max 2 retries.** If still failing, deliver what you have and flag the specific slide for manual review rather than looping indefinitely.

## 7. Orchestrator integration

- Add `"slide"` as a new `assigned_agent` value in `PlanStep`.
- Implement as a dedicated LangGraph subgraph (`slide_agent`), invoked as one step from `dispatch_node`, matching the existing agent-as-worker pattern (same shape as `code_agent`, `vision_agent`, etc.) — not a new dispatch mechanism.
- The retry loop (§6.3) lives **inside** this subgraph, not in the outer DAG — the outer dispatch DAG only sees pass/fail of the whole `slide_agent` step.
- Log every stage to the existing audit log (`APPROVAL_REQUESTED` doesn't apply here — see §8) — at minimum log `TOOL_EXECUTED`/`TOOL_FAILED` per retrieval call, math_tool call, render attempt, and QA verdict, so the full chain from source document → number → slide is traceable.
- Given no LangGraph checkpointer exists yet, don't add one just for this: persist a lightweight `OutputRecord` (job id, session_id, status, current_stage, retry_count, output_path) so `RealOutputCards.jsx` can show progress and survive a reconnect.

## 8. Approval gate — explicit exception

A generated deck is a **safe deliverable**, not a hazardous control action. It does **not** go through the safety-interlock modal (`ApprovalModal.jsx`) used for SAP writes / DCS setpoints. It's delivered via the existing **Output Cards** UI (thumbnail + citation badge + Download button) — the explicit download click is the human gate for this artifact class. Document this exception next to hard constraint #4 in `CLAUDE.md` so it isn't "fixed" into blocking on the safety modal later.

## 9. File/component checklist

| File | Change |
|---|---|
| `backend/tools/generation/slide_kit.py` | **New.** Hand-authored mold render functions + brand tokens. |
| `backend/sandbox/Dockerfile.sandbox` | Add `python-pptx==1.0.2`; `COPY` in `slide_kit.py` + logo/brand assets at build time. |
| `backend/tools/generation/qa_render.py` | **New.** Host-side pptx→PNG conversion (needs `libreoffice`/`poppler` on the *host*, not the sandbox). |
| `backend/orchestrator/state.py` | Add `"slide"` to `assigned_agent` enum on `PlanStep`. |
| `backend/orchestrator/slide_agent.py` | **New.** Subgraph: planner call → fetch loop → filler calls → assemble `context.json` → render → QA → bounded retry. |
| `backend/orchestrator/dispatch.py` | Wire `slide_agent` into `_ALLOWED_TOOLS` / dispatch routing. |
| `models/models.yaml` | No new model needed — reuse `reasoning-model` (planner+filler) and `vision-model` (QA). Add `"format": schema` support to the Ollama call wrapper in `planner.py`. |
| `frontend/src/integrations/output-cards/RealOutputCards.jsx` | Extend to show deck thumbnail + retry/QA status if not already generic enough. |
| `TOOLS.md` | Add row for `slide_agent`, priority 🔴 (demo-critical). |
| `CLAUDE.md` | Add the §8 approval-gate exception explicitly. |

## 10. Non-negotiables carried over from `CLAUDE.md`
- No network calls anywhere in this pipeline — `slide_kit` and brand assets are baked into the image at build time, never fetched at runtime.
- No hardcoded model names in `slide_agent.py` — read `reasoning-model`/`vision-model` IDs from `models.yaml` like every other agent does.
- No number appears on a slide unless it came from `math_tool` or a cited retrieval chunk.
- No layout is ever written by the LLM — only mold IDs + field values.

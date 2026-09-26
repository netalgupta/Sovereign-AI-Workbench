# PPTX Generation — System & Execution Architecture

> Companion to `PPTX_AGENT_SPEC.md` (which covers agent prompts, mold schemas, and file-level changes). This document covers **where each piece actually runs** — LLM call vs. backend logic vs. sandboxed code — and the full end-to-end sequence. Read both before implementing.

## 1. The one rule that decides "sandbox or not"

The sandbox exists for exactly one purpose: **executing code that the LLM generated, safely, with no network access.** If a step is not "run some code," it does not belong in the sandbox. Use this to classify every step:

| Step | What it actually is | Runs where |
|---|---|---|
| Planner call | LLM reasoning, produces JSON | Normal backend LLM call — same path as any chat response |
| Retrieval + math_tool fetch | Existing deterministic backend functions | Normal backend process |
| Filler call (per slide) | LLM reasoning, produces JSON | Normal backend LLM call |
| Assemble `context.json` | Plain backend code, no LLM, no untrusted code | Normal backend process |
| **Render script (open template → duplicate slide → fill placeholders)** | **Code execution** | **Sandbox** — this is the only sandboxed step |
| Heuristic QA (overflow/overlap/contrast checks) | Plain backend code (python-pptx read-back) | Normal backend process — not sandboxed, this isn't LLM-generated code |
| Visual QA (`qwen2.5vl`) | LLM call (vision) + a conversion utility | Conversion utility runs host-side; the vision model call is a normal LLM call |
| Retry — feed defect back to Filler | LLM call | Normal backend LLM call |
| Deliver via Output Cards | Frontend rendering | Frontend, not backend |

**Takeaway:** out of the entire pipeline, only one step ever touches the sandbox. Everything else — both AI calls and the QA logic — is exactly the same kind of process your system already runs for regular chat and tool calls. This is not a separate execution model; it's your existing agent pattern, applied to a new capability.

## 2. Where the 19-slide template file lives

- The `.pptx` template you generated is a **static asset**, not a runtime artifact.
- It's copied into `Dockerfile.sandbox` at **image build time**: `COPY assets/mrpl_template.pptx /sandbox/lib/`.
- It is baked into every sandbox container from the moment the image is built — never downloaded, never regenerated, never modified at request time.
- The render script (the only sandboxed step) opens this baked-in file, duplicates the slide layout named in `context.json`, and fills its placeholders. It never creates a new layout and never edits the template itself — read-and-duplicate only.
- If the template needs to change (e.g. adding an 18th mold later), that's a **rebuild of the sandbox image** by a human — same category of change as updating any other baked-in dependency, not a runtime code path.

## 3. Full end-to-end sequence (one request, start to finish)

1. User asks for a deck (chat message, existing entrypoint).
2. `dispatch_node` routes to the new `slide_agent` subgraph — same pattern as routing to `code_agent` or `vision_agent` today.
3. **Planner call** (LLM, backend) → outline of ~8-12 sections, each with a rough mold guess.
4. **Fetch loop** (backend, deterministic) → for each section: `retrieval_agent` call, `math_tool` call if numeric, `ImageStore` lookup if visual. Produces real, sourced content per section.
5. **Filler call, per section** (LLM, backend) → confirms/corrects the mold, fills in exact field values with citations attached, format-constrained to the mold's JSON schema.
6. **Assemble `context.json`** (backend) → all filled slides combined into one deck plan, written to the session's sandbox-mounted directory.
7. **Render** (sandbox, only sandboxed step) → opens baked-in template, duplicates each named slide, fills placeholders from `context.json`, saves `deck.pptx` to the host-mounted output path.
8. **Heuristic QA** (backend) → overflow/overlap/contrast checks against the rendered file.
9. **Visual QA** (host-side conversion + LLM vision call) → pptx→PNG conversion, then `qwen2.5vl` critiques the rendered slide images.
10. **Bounded retry** (backend orchestration) → on defect, loop back to step 5 for just the affected slide. Max 2 retries total, then proceed with a flagged slide rather than looping.
11. **Deliver** (frontend) → `deck.pptx` shown via Output Cards with thumbnail, citations, and a Download button — this download click is the human approval gate for this artifact class (see `PPTX_AGENT_SPEC.md` §8).

## 4. What's genuinely new vs. what's reused

**Reused as-is, no changes:**
- `retrieval_agent`, `math_tool`, `ImageStore`
- The warm sandbox pool / worker acquisition pattern
- `reasoning-model` and `vision-model` from `models.yaml` — no new model added
- Output Cards UI pattern, audit logging pattern

**New, and this is the entire scope of the build:**
- The 19-slide template `.pptx` (already generated — bake into the sandbox image)
- `slide_kit.py`-equivalent glue: the fixed render script that duplicates/fills slides (trivial, same every run — see `PPTX_AGENT_SPEC.md` §5)
- The `slide_agent` subgraph itself: wiring steps 3–10 above together as one LangGraph subgraph
- Mold JSON schemas (one per mold, matching the field lists in `PPTX_AGENT_SPEC.md` §4.1) for constrained LLM output
- `qa_render.py` — the host-side pptx→PNG conversion utility
- One new `assigned_agent` enum value + one new row in `TOOLS.md`

Nothing about your ingestion, retrieval, model registry, or sandbox *infrastructure* changes. This is additive — one new subgraph plus one new static asset.

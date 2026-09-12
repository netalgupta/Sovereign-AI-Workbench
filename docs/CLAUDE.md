# CLAUDE.md — Agentic Coding Guide for SIH26117
This file is read by Claude Code / Antigravity (or any coding agent) working in this repository. Keep it accurate as the repo evolves — this is what the AI coding agent uses as ground truth for how to work here.

## Project Summary
Sovereign On-Premise Agentic AI Workbench for MRPL (PS26117). Fully offline, multi-model, agentic system. See REQUIREMENTS.md, SYSTEM.md, TOOLS.md, DEPENDENCIES.md in this same folder for full spec — read those before making architectural changes.

## Repo Structure (target layout)
```
/backend
  /orchestrator      — LangGraph agent graph, router, sub-agent dispatch
  /tools             — one module per tool in TOOLS.md, each with a defined schema
  /connectors        — SAP connector, document ingestion
  /sandbox           — Docker sandbox execution wrapper
  /audit             — audit logging module
  main.py            — FastAPI entrypoint
/frontend
  /electron          — main.js, preload.js (mandatory Electron shell, see FRONTEND.md §4.1)
  /src/components    — chat, plan graph, network monitor, source viewer, etc.
/models
  models.yaml        — model registry config (see DEPENDENCIES.md)
/deploy
  docker-compose.yml
  install.sh / install.bat
/docs                — this documentation set
```

## Hard Constraints (never violate these when generating code)
1. **No outbound network calls, anywhere, ever.** Any library or code path that could phone home (telemetry, update checks, CDN-hosted assets) must be disabled or replaced. If unsure whether a library does this, flag it rather than assume.
2. **No hardcoded model names in orchestration logic.** Only `models.yaml` names a model. The router/orchestrator reads the registry.
3. **No math computed by an LLM without a tool call.** Any numeric result must come from an executed SymPy/NumPy/etc. call, never from the LLM "doing the arithmetic in its head."
4. **No file write, send, or SAP write action without a human-approval-gate check.** This is a design law, not a suggestion.
5. **No Wolfram Alpha, no cloud math API, no cloud anything.** If a task seems to need Wolfram-Alpha-class computation, it needs Maxima/SymPy locally instead — ask before reaching for a cloud substitute.

## Coding Conventions
- Python: FastAPI + type hints throughout; one tool = one function with a JSON schema decorator
- Frontend: React functional components, Tailwind for styling
- Every new tool added to `/backend/tools` must also get a row added to TOOLS.md by whoever adds it
- Commit messages reference the FR/NFR ID being worked on where applicable (e.g. "FR-7: add PaddleOCR wrapper")

## VRAM Discipline
Dev hardware is an RTX 4060 (8GB). Do not write code that assumes all models can be resident in VRAM simultaneously unless explicitly running on venue hardware — load/unload or route sequentially by default; make concurrency configurable, not assumed.

## When Asked to Add a New Tool
1. Check TOOLS.md — does it already exist under a different name?
2. Add the implementation under `/backend/tools/<category>/<tool_name>.py`
3. Register it in the orchestrator's tool schema list
4. Add a row to TOOLS.md with owner and priority tier
5. If it touches SAP, documents, or file writes — confirm the human-approval-gate wraps it

## Testing Expectations
- Each tool needs at least one test proving it runs fully offline (mock network access off, confirm no exception/no external call attempted)
- Sandbox execution tests must confirm `--network none` is actually enforced, not just configured

## Demo-Day Priorities
If time runs short, protect the 🔴-priority rows in TOOLS.md first. 🟡 and ⚪ rows can remain registry-listed (present in the model/tool config, not necessarily polished) without breaking the "boundless, pluggable" architecture claim — see TOOLS.md §I for the exact demo script these priorities are built around.

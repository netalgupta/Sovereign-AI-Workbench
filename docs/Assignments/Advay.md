# Advay.md — Fullstack Lead (Maximum Frontend Ownership)

**Note on scope:** Advay does not build AI/ML tools (Aryan) or backend infra (Aditya) — his full 10 days go entirely into frontend breadth and depth. He carries the largest single share of frontend work by design, since he isn't splitting time across tool-building. See FRONTEND.md §5 for the full ownership table this assignment is drawn from.

## Scope of Ownership (per FRONTEND.md §5)
- App shell, routing, design tokens, and the three-pane workbench layout (FRONTEND.md §2) — the foundational structure everyone else's components sit inside
- Chat message component + client-side streaming reveal (FRONTEND.md §3.1)
- Tool call event component (FRONTEND.md §3.3) — the single most reused component in the entire app, every one of the 50 tools in TOOLS.md renders through this one component
- Plan graph visualizer (FRONTEND.md §3.4) — the highest-impact single visual in the whole demo, proving FR-5 live; budget the most design/animation care here
- Human approval gate modal (FRONTEND.md §3.12) — safety-critical UI pattern, needs the most careful UX of any single component
- Settings page including the live model-add form (FRONTEND.md §3.11) — this is the literal on-stage FR-4 demo moment
- **Electron packaging — mandatory** (FRONTEND.md §4.1): `main.js` window/lifecycle management, `preload.js` IPC surface (native file dialogs, drive status only), `electron-builder` config for Windows + Linux targets. This is now a first-class deliverable, not an afterthought — the app ships as a desktop app, not a browser tab.
- Integration/merge authority over Netal's, Kanishka's, and Sahil's components into the single coherent app
- Overall visual/UX consistency pass against FRONTEND.md §6's consistency rules

## Explicitly Not Your Job
- Any backend logic (Aditya/Aryan own it — you consume APIs, you don't reimplement logic client-side)
- AI/ML tool implementation of any kind
- Citation/sources/graph-specific components (Netal builds these; you integrate them into the shell)
- Output file cards, calc trace viewer, audit log viewer (Kanishka builds these; you integrate them)
- Network monitor widget internals, upload/preview, defect overlay (Sahil builds these; you integrate them)

## Day-by-Day
- **Day 1-2:** App shell, routing, design tokens (colors/radii/shadows per FRONTEND.md §1), three-pane workbench layout skeleton. Get a placeholder chat talking to Aditya's FastAPI skeleton end-to-end with dummy responses, proving the integration path early.
- **Day 3-4:** Real chat message component with streaming reveal, markdown rendering, code block syntax highlighting. Tool call event component — build this as the single reusable component per FRONTEND.md §3.3, since every sub-agent's tool calls render through it.
- **Day 5:** Plan graph visualizer — `react-flow` + `dagre`, wired to AGENTS_SPEC.md's `PlanStep` schema, 4-state node styling (pending/running/done/failed), edges from `depends_on`.
- **Day 6:** Human approval gate modal — build to the exact spec in FRONTEND.md §3.12 (can't-dismiss-by-outside-click, explicit Confirm/Cancel, preview of the pending action).
- **Day 7:** Settings page — model registry table rendering `models.yaml` live, plus the live "Add Model" form that actually appends to the YAML and triggers backend reload. Rehearse this specific flow, it's an on-stage moment.
- **Day 8:** Integration pass — pull in Netal's sources/citation/graph components, Kanishka's output/calc-trace/audit components, Sahil's monitor/upload/overlay components into the app shell. Resolve API contract mismatches as they surface.
- **Day 9:** Electron wrapping — build `main.js` (backend health-check/spawn, single BrowserWindow, no default menu bar, `nodeIntegration: false`/`contextIsolation: true`) and `preload.js` (the two IPC surfaces only). First integration test of the full React app running inside Electron rather than a dev-server browser tab. Full consistency pass against FRONTEND.md §6 across every integrated component.
- **Day 10:** `electron-builder` packaging for both Windows and Linux targets (DEPENDENCIES.md §7.1 checklist), cold-boot test on a clean machine with the packaged app, buffer for Electron-specific bugs (these tend to surface late — process teardown, path resolution in a packaged build vs dev mode), full demo-flow rehearsal from the frontend side inside the actual packaged app.

## Dependencies on Others
- Needs Aditya's API contracts frozen as early as possible (push for end of Day 2)
- Needs AGENTS_SPEC.md's `PlanStep`/`ToolCallEvent` schemas stable before Day 5 (Aryan/Aditya jointly own this file)
- Needs Netal/Kanishka/Sahil's component specs finalized by Day 6-7 so your Day 8 integration isn't blocked — chase these actively, don't wait passively

## Acceptance Criteria You Own
NFR-8 (non-technical usability), FRONTEND.md §6 (consistency across the whole app), overall demo-day UI reliability across FR-4, FR-5, FR-9, FR-11, FR-15

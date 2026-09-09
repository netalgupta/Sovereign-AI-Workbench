# FRONTEND.md — Complete Frontend Specification
## Design language: Claude (chatbot) + Claude Code (agentic dev surface) + NotebookLM (source-grounded trust) — fused into one workbench

This is the single most judge-visible layer of the entire submission. The backend can be flawless and still lose if the frontend looks like a generic admin dashboard. Read this whole document before writing a single component.

---

## 1. Design Philosophy

Three reference products, three things borrowed from each, deliberately:

| From | What we borrow | Why |
|---|---|---|
| **Claude (chatbot)** | Calm, uncluttered chat surface. Generous whitespace. Warm neutral palette, not corporate-cold blue-and-white. Messages feel like they're being *composed*, not printed. | This is the primary interaction surface — it needs to feel trustworthy and unhurried, appropriate for drafting an approval note, not like a stock trading terminal |
| **Claude Code** | Visible, inspectable agent reasoning. A plan/task list the user can watch execute step by step. Tool calls shown as discrete, collapsible events, not buried in a wall of text. | This is what proves "agentic," not just "chatbot" — judges need to *see* the plan-execute-verify loop happening |
| **NotebookLM** | A visible "sources" panel — always present, always showing exactly what's grounding the current session. Citations that expand inline to show the exact source passage. A sense of "this notebook only knows what you gave it." | This is the trust mechanism — critical for an approval-note tool in a safety-critical industry |

**Visual tone:** warm off-white/cream background (not stark white), deep charcoal text (not pure black), one confident accent color used sparingly (a muted terracotta/rust or deep amber works well against the industrial/refinery subject matter without being literal "hazard orange"), generous rounded corners (12-16px), soft shadows, no gradients as decoration (gradients only where they communicate something, e.g. a live/active state pulse). Typography: a humanist sans (Inter or similar) for UI chrome, a serif or slab for document previews (DOCX/PPTX previews should look like documents, not like app screens).

**Motion principle:** every state change animates, nothing snaps. Plan graph nodes animate from "pending" → "in progress" (pulsing) → "done" (settle + checkmark). Citations expand with a smooth height transition. The network monitor's live connection count should tick, not jump. This is what makes the demo feel "otherworldly" rather than "functional" — motion communicates that the system is alive and working, not static.

---

## 2. Information Architecture (screens/routes)

```
/                      → Chat / main workbench (default landing)
/plan/:sessionId       → Full-screen plan graph view for a running task
/sources               → Knowledge base / source manager (NotebookLM-style)
/graph                 → Graph explorer (standalone, full-screen)
/outputs               → Generated file library (DOCX/XLSX/PPTX history)
/audit                 → Audit log viewer
/settings              → Model registry view, RBAC tiers, drive/encryption status
/monitor               → Network monitor, full-screen (also embedded as a persistent widget elsewhere)
```

The chat view (`/`) is not just a chat — it's a **three-pane workbench**, this is the single most important layout decision:

```
┌──────────────┬───────────────────────────────┬──────────────┐
│  SOURCES      │        CHAT / CONVERSATION     │  PLAN + TOOLS│
│  (left rail)  │        (center, primary)       │  (right rail)│
│               │                                 │              │
│ - Ingested    │  User + assistant messages      │ - Live plan  │
│   documents   │  Tool-call events (collapsible) │   graph      │
│ - Toggle      │  Generated file cards inline    │ - Active     │
│   sources     │  Citation chips → expand        │   tool trace │
│   in/out of   │                                 │ - Network    │
│   context     │                                 │   monitor    │
│               │                                 │   widget     │
└──────────────┴───────────────────────────────┴──────────────┘
```

This layout alone is the visual proof of "Claude + NotebookLM fused" — left rail is pure NotebookLM, center is pure Claude, right rail is pure Claude Code. State this explicitly in the pitch.

---

## 3. Component Specification (every feature, one entry each)

### 3.1 Chat Message Component
- User messages: right-aligned, accent-colored subtle background
- Assistant messages: left-aligned, no bubble — just text on the cream background (Claude's actual style — bubbles read as "generic chatbot")
- Streaming text renders token-by-token (even if the backend returns it in chunks, animate the reveal client-side for consistency)
- Markdown rendering: headings, bold, code blocks with syntax highlighting, tables
- Every factual claim that came from retrieval gets a small citation chip `[1]` inline, superscript style, clickable

### 3.2 Citation Chip + Expansion Panel
- Clicking `[1]` expands an inline card directly below the sentence (push content down, don't overlay/modal — keeps reading flow intact)
- Card shows: source document name, page/section, the exact retrieved passage (highlighted), a "view full source" link to the Sources panel
- Visual: thin left border in the accent color, muted background, monospace or serif for the quoted passage to visually distinguish "quoted" from "generated"

### 3.3 Tool Call Event (Claude-Code-style)
- Renders inline in the chat stream as a distinct, collapsible block — not a chat message, visually distinct (icon + label + status)
- Collapsed state: `🔧 Extracting text from scanned_report.pdf — done ✓` (single line)
- Expanded state: shows the tool's exact input parameters and output, monospace, scrollable
- Status states: `pending` (grey, spinner), `running` (accent color, pulsing icon), `done` (green check), `failed` (red, with error message and a "retry" affordance)
- This component is reused for every single tool in TOOLS.md — one component, driven entirely by the tool-call event schema from the backend, never a bespoke component per tool

### 3.4 Plan Graph Visualizer (right rail + full-screen `/plan/:sessionId`)
- Node-and-edge graph, top-to-bottom or left-to-right flow (not a force-directed blob — this needs to read as a *sequence*, use a DAG layout library like `dagre` via `react-flow`)
- Each node = one planned step, showing: step description (short), assigned sub-agent icon (vision/code/reasoning/math), status (same 4 states as tool call events)
- Edges show dependency order
- Clicking a node scrolls the chat pane to that step's tool-call event
- This is the single highest-impact visual for proving FR-5 (agentic planning) live — budget real design time here

### 3.5 Sources Panel (NotebookLM-style, left rail + full `/sources` page)
- List of ingested documents, each with: filename, type icon (PDF/DOCX/scan/photo), ingestion date, a toggle switch to include/exclude from the current session's retrieval scope
- "Add source" button — drag-and-drop upload, triggers the ingestion pipeline
- Document count badge, and — important trust signal — a small persistent label: **"This session is grounded only in the sources listed here."** This sentence should appear verbatim somewhere visible; it is the plain-language statement of NFR-4 and should be said, not just implemented invisibly

### 3.6 Graph Explorer (`/graph`, standalone)
- Interactive node-link graph (use `react-force-graph` or `vis-network`) rendering the knowledge graph
- Node types color-coded: SOP (blue), Equipment/Valve (amber), Report (green), Person (grey), Date (light grey, smaller)
- Search bar to jump to a specific entity (e.g. type "V-204" to center the graph on that valve node)
- Clicking a node shows a side panel with every document that references it, each linking back into the Sources panel
- The signature demo query ("show every SOP referencing this pipeline segment") should visibly animate the relevant subgraph highlighting when run, not just filter silently

### 3.7 Output File Card + Library (`/outputs`)
- Inline in chat: a card showing file type icon, filename, a "preview" thumbnail (first page render for DOCX/PPTX, sheet preview for XLSX), download button, and an "Open in [app]" hint text
- `/outputs` page: same cards in a grid/list, filterable by type and date
- Every card also shows its source citations count as a small badge, reinforcing groundedness even for generated deliverables

### 3.8 Calculation Trace Viewer
- A specialized card type: shows the math expression, step-by-step simplification (from CARD 08's `steps` list), and the final verified result, with a small "✓ verified by SymPy" badge — this exact badge language matters, it's the visual proof of NFR-5
- Monospace font for all math content

### 3.9 Network Monitor Widget (persistent, right rail) + Full View (`/monitor`)
- Persistent widget: a single always-visible line, e.g. `● 0 external connections` with a solid green dot when zero, turning red immediately if any external connection appears
- Full `/monitor` view: live-updating table of all active connections (local/remote address, status, flagged external or not), plus a running counter/timestamp of "time since last external connection attempt: N/A (none recorded this session)"
- This must NEVER be a static/hardcoded display — wire it directly to CARD 07's live websocket feed, no exceptions, per that card's anti-hallucination note

### 3.10 Audit Log Viewer (`/audit`)
- Table: timestamp, action type, tool/component involved, user (if applicable), status
- Filter by action type, date range
- Export button → downloads CSV
- Search bar for free-text filtering across the log

### 3.11 Settings Page (`/settings`)
- **Model Registry section**: read-only table rendering `models.yaml` live — id, backend, model name, task tags. Include a visible "Add Model" text area/form that, on submit, actually appends to the YAML and triggers backend reload — this is the literal live demo moment for FR-4, make it feel deliberate and easy, not a hidden dev feature
- **RBAC section**: simple role tier list (engineer / HSE / approver / admin) with which knowledge base sources each tier can see
- **Drive/Encryption status**: shows the portable drive is mounted, encrypted, and its used/free space — reinforces NFR-2/NFR-3 visually

### 3.12 Human Approval Gate Modal
- Appears as a clearly distinct, impossible-to-miss modal (not a toast) whenever the backend requests confirmation before a write/send/SAP action
- Shows exactly what will happen ("This will save `approval_note.docx` to the outputs folder"), a diff/preview where feasible, Confirm and Cancel buttons
- This modal's design should feel deliberately weightier than every other UI element — slight backdrop blur, centered, can't be dismissed by clicking outside (must explicitly Confirm or Cancel) — this is a safety-critical UI pattern, treat it as such

### 3.13 Multimodal Upload + Preview (chat-integrated)
- Drag-and-drop or paperclip-icon upload directly in the chat composer
- Immediately shows a thumbnail preview in the message before processing
- OCR/vision results render as a follow-up tool-call event (per 3.3) showing extracted text/structure

### 3.14 Defect/Annotation Overlay Viewer
- For inspection photos run through YOLOv8: renders the original image with bounding boxes overlaid (canvas or SVG overlay on top of an `<img>`), each box labeled with the detected class and confidence
- Clicking a box highlights the corresponding line in an extracted findings list, if one exists

---

## 4. Tech Stack (final)

| Layer | Choice | Why |
|---|---|---|
| Framework | React (Vite, not CRA) | Fast dev server, no build config fighting |
| Styling | Tailwind CSS + a small custom design-tokens file (colors, radii, shadows per §1) | Speed without losing the custom aesthetic — pure Tailwind defaults would look generic, so tokens are mandatory, not optional |
| Plan graph | `react-flow` + `dagre` layout | Purpose-built for exactly this DAG-visualization need |
| Knowledge graph | `react-force-graph` or `vis-network` | Handles larger node counts than react-flow gracefully |
| Charts (trend lines, PSA purity, etc.) | Recharts | Simple, good defaults, easy to theme to match §1 |
| State management | React Query for server state, lightweight Context/Zustand for UI-only state | Avoid over-engineering with Redux for a 10-day build |
| Realtime | WebSocket (native, or `socket.io-client` if the backend uses socket.io) | For tool-call streaming, plan graph updates, network monitor feed |
| Icons | Lucide React | Clean, consistent line-icon set matching the calm aesthetic |
| Desktop packaging | **Electron — mandatory** | The workbench ships as a native desktop app, not a browser tab. See §4.1 for the exact packaging spec. |

---

## 4.1 Electron Packaging Spec (mandatory, exact)

The frontend is not "a website you happen to open in a browser" — it is a desktop application. This matters for the pitch: a refinery engineer double-clicking an icon on a desktop, with no address bar, no browser chrome, no visible "this is a web server" tell, reads as a finished product rather than a hackathon prototype. Build to this exact spec.

**Package structure:**
```
/frontend
  /electron
    main.js           — Electron main process entry point
    preload.js        — contextBridge-exposed IPC surface (see below)
  /src                — the React app itself (everything in §3), built via Vite
  package.json        — includes electron, electron-builder as devDependencies
```

**Exact `main.js` responsibilities:**
1. On app launch, spawn the FastAPI backend as a child process (`child_process.spawn`) if it isn't already running — check via a health-check ping to `http://localhost:8000/health` first, spawn only if that fails, so a developer running the backend manually during dev isn't fighting a duplicate process
2. Create a single `BrowserWindow` (default size 1440x900, resizable, minimum 1024x768) loading the built React app from `dist/index.html` — **not** loading a remote URL, everything is local
3. **No default Electron menu bar** — set `Menu.setApplicationMenu(null)`. A generic File/Edit/View/Window menu bar reads as unfinished/templated; a clean custom title bar (or none at all, using the OS's native title bar with just the app icon and title) looks deliberate
4. `nodeIntegration: false`, `contextIsolation: true` in `webPreferences` — this is a hard security requirement, not a style choice: the renderer must never have direct Node.js access, all backend communication goes through the existing REST/WebSocket API, IPC is only for OS-level needs (see below)
5. On app quit, terminate the spawned backend child process cleanly (`SIGTERM`, with a `SIGKILL` fallback after a 5-second grace period) — don't leave orphaned Python/Docker processes running after the window closes, since this is exactly the kind of loose end an IT/InfoSec judge would notice

**What IPC (`preload.js` contextBridge) is for, exactly — and only for:**
- Native file-open dialogs (choosing a document to ingest, choosing where to save an exported file) — everything else stays in the browser-standard fetch/WebSocket layer talking to the FastAPI backend, exactly as it would from a browser tab
- Reading the portable drive's mount status/free space for the Settings page's drive-status display (FRONTEND.md §3.11)
- Do NOT use IPC as a shortcut to bypass the backend API for anything else — if a feature needs backend logic, it goes through the same REST/WebSocket contract Aditya's API defines, whether the frontend happens to be running in Electron or (during dev) a plain browser tab. This keeps the two interchangeable, which matters for local development speed.

**Build & distribution:**
- `electron-builder` targets: a portable/unpacked build for Windows (`nsis` target with `oneClick: false` if an installer is preferred, or a fully portable `.exe` if the judging machine shouldn't require an install step) and a Linux `AppImage` — cover both since venue hardware is unknown
- The built Electron app, along with the Docker-packaged backend stack, is what goes on the encrypted portable drive per DEPENDENCIES.md §10 — `install.sh`/`install.bat` now additionally copies/launches the Electron `.exe`/AppImage rather than opening a browser
- Dev workflow stays lightweight: during the 10-day build, run the React app via Vite's dev server and open it in a normal browser for fast iteration; only wrap it in Electron for integration testing (Day 8-9) and the final packaged build (Day 9-10) — don't pay Electron's slower rebuild cycle during active feature development

**Consistency rule:** every component spec in §3 above is written against "the app" — that app is now understood to mean the Electron-packaged desktop application specifically, with the browser-based dev server as an implementation convenience only, not the shipped target.

---

## 5. Ownership & Work Allocation (frontend-heavy rebalance)

Advay is Fullstack Lead and is **not building AI/ML tools** — his full capacity goes into frontend breadth and depth. Rebalanced ownership:

| Component | Owner |
|---|---|
| App shell, routing, design tokens, three-pane workbench layout (§2) | **Advay** |
| Chat message component + streaming (§3.1) | **Advay** |
| Tool call event component (§3.3) — the single most reused component in the app | **Advay** |
| Plan graph visualizer (§3.4) | **Advay** (highest-impact visual, needs the most design care) |
| Human approval gate modal (§3.12) | **Advay** (safety-critical, needs the most careful UX) |
| Settings page incl. live model-add form (§3.11) | **Advay** |
| Citation chip + expansion (§3.2) | Netal, integrated by Advay |
| Sources panel + `/sources` page (§3.5) | Netal |
| Graph explorer (§3.6) | Netal |
| Output file card + library (§3.7) | Kanishka |
| Calculation trace viewer (§3.8) | Kanishka |
| Audit log viewer (§3.10) | Kanishka |
| Network monitor widget + full view (§3.9) | Sahil (backend-adjacent, coordinate closely with Aditya) |
| Multimodal upload + preview (§3.13) | Sahil |
| Defect/annotation overlay viewer (§3.14) | Sahil |
| Electron packaging: main.js, preload.js, IPC surface, electron-builder config (§4.1) | **Advay** (with Aditya on the backend-child-process spawn/teardown contract) |

Advay owns the highest concentration of components because he isn't splitting time with tool-building — this is intentional and should be reflected in his day-by-day plan (see updated Advay.md). Electron packaging is his responsibility specifically because he owns the app shell it wraps — nobody else should be maintaining a second copy of window/process lifecycle logic.

---

## 6. Consistency Rules (apply to every component, no exceptions)

1. Every async action shows a loading state — never a blank screen or frozen button
2. Every error shows a human-readable message, never a raw stack trace or raw JSON error in the UI
3. Every list that can be empty has a designed empty state (not just blank space) — e.g. Sources panel with zero documents shows an illustration + "Add your first source" prompt
4. Color usage is consistent: green = done/safe, amber/accent = active/in-progress, red = failed/external-connection-detected, grey = pending/inactive. Never use red for anything except a genuine failure or the external-connection alert — overuse dilutes its meaning
5. All timestamps display in a single consistent format across the app (`YYYY-MM-DD HH:mm`, local time), defined once in a shared utility, never formatted ad hoc per component

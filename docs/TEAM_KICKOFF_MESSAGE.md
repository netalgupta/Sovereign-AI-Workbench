# WhatsApp message — copy/paste

Short version first, then a per-person follow-up you can send
individually so nobody has to read someone else's block.

---

## Group message

```
Team — backend + RAG pipeline is done and pushed. You can all start.

Take a pull:
  git fetch origin
  git checkout aryan/rag-and-graphrag
  git pull

Read these 3 files first, in this order (15 min total):
  docs/RUNNING.md      — how to start backend + frontend, what's normal
  docs/STATUS.md       — what's built, what's pending, who owns what
  docs/OWNERSHIP.md    — the tie-breaker if any doc contradicts another

Your assignment file has been rewritten:  docs/Assignments/<yourname>.md
Please read it fully — several scopes changed.

What's working right now:
• Chat end to end, grounded answers with real citations
• 40 API endpoints, 19 callable tools — all listed in docs/INTEGRATION.md
• Hybrid retrieval + GraphRAG, knowledge graph (101 nodes)
• Approval gate, audit log, sandbox (egress-isolated, proven)
• NEW: the agent now CHOOSES its own tools and narrates while working —
  POST /api/chat/stream streams it live (text, work, text, work)
• 357 tests passing

Two things that changed and will confuse you if you don't know:
1. START THE BACKEND BEFORE THE FRONTEND. If you don't, the Vite dev
   server serves its own fake data and you'll be building against
   something that isn't the real corpus.
2. Turn tracing is ON by default — your backend console now prints
   every retrieval, score, prompt and timing for each answer. That's
   deliberate. WORKBENCH_TRACE=off if it's too noisy.

Ground rules (all in OWNERSHIP.md §6):
• Every tool you add → a row in TOOLS.md WITH YOUR NAME
• Anything that writes a file / sends / touches SAP → requires_approval=True
• No model names outside models.yaml
• NO fake/placeholder data in the UI, ever. Empty states only.

Nobody is blocked on me. Everything you need on the backend exists
today. If an API shape is wrong for you, tell me and I'll change it —
don't work around it.

Questions in the group, not DMs, so answers are shared.
```

---

## Per-person follow-ups

### Aditya
```
Aditya — backend infra is yours and mostly unblocked.

Your first command: ollama pull qwen2.5-coder:7b
(it's the only model in the registry that isn't pulled — /api/models
will tell you)

Done and working: FastAPI app, approval gate, audit log, network monitor.
The sandbox image now BUILDS and runs — egress isolation is proven, not
just configured (numpy/sympy present, network blocked). Three bugs were
fixed to get there, all in the commit log.

Your pending 🔴 items:
• SAP connector (row 49) — highest-leverage MRPL feature we have
• Code agent / CARD 04 — code_agent is the one sub-agent with an empty
  tool set and it RAISES by design until you wire it to run_code_step
  in dispatch.py
• Docker Compose + air-gapped packaging, encryption at rest

Note: any SAP write must register requires_approval=True. The dispatcher
enforces it from the registry flag, so there's nowhere for a write to
hide — but a tool registered without the flag bypasses the gate silently.
```

### Advay
```
Advay — frontend lead, and there's a lot ready for you.

Chat works end to end now. MessageBubble already renders a TurnTrace
component showing the real plan + tool calls + verdict for each answer.
Take it over and make it yours.

Your pending items are the big visuals:
• Plan graph visualiser — highest-impact single visual in the demo
• Approval modal wired to the live gate (POST /api/approvals/* is real)
• Settings + live model-add form — the on-stage FR-4 moment
• ELECTRON PACKAGING — mandatory, FRONTEND.md §4.1, not optional
• Integration pass over Netal/Kanishka/Sahil's components

Heads up: I deleted 484 lines of hardcoded demo chat from ChatPane.jsx
(fake thermocouple table, fake "live" SAP/OPC-UA connectors, a spinner
that counted forever with no request behind it). Don't put placeholder
content back — empty states only. On a refinery product, invented
instrument readings marked "Normal" are a fabricated safety claim.
```

### Netal
```
Netal — your assignment was genuinely too light and I've rewritten it.
Please read docs/Assignments/Netal.md fully.

You own "where did this come from?" — sources, citations, the graph, and
why an answer was retrieved. That's the most important trust surface in
the whole product.

Three working pages are YOURS to take over, not just extend:
GraphExplorerPage, KnowledgeBasePage, InstrumentationPage.

And four things with a working backend and NO UI at all:
• Source page preview — render the user's own PDF at the exact cited
  page, Claude-app style. GET /api/preview exists. This is the single
  most valuable missing thing in the product.
• MULTI-HOP GRAPH TRAVERSAL — I built the backend for you today:
  GET /api/graph/neighbourhood?node=X&hops=N
  Every node comes back with its `distance` + a by_distance histogram,
  specifically so you can reveal the traversal hop by hop. Verified:
    'Mangalore-Hassan' hops=2 → 8 nodes, 18 edges, {'0':1,'1':2,'2':5}
  A graph that appears all at once is a hairball. One that unfolds hop
  by hop is an explanation — and it's the clearest proof we reason over
  connections instead of matching text. Do this one.
• Retrieval trace UI — the backend prints the full trace to console,
  none of it is visible in the app
• Ingestion progress feed — GET /api/ingestion/{job_id}

AND the big new one — GRANULAR AGENT THINKING UI:
POST /api/chat/stream now streams the agent working, live. Narration
token by token, every tool call WITH ITS ARGUMENTS before it runs, every
result with its real output and duration. Text, work, text, work — the
way a real agent reads. One measured turn = 173 events.
Contract: docs/Technical_Specs/AGENT_STREAM_PROTOCOL.md

Show the tool ARGUMENTS. That is a safety control, not a debug view:
the model once called evaluate_expression("-381.95 - 400") for
"381.95 minus 400" and the tool correctly returned -781.95. The wrong
answer arrives with a real tool-call receipt attached. A human seeing
the arguments is the ONLY thing that catches that.

Read the "Known limitation" section first — answers on the streaming
path are currently worse than /api/chat. Thats mine to fix, not yours.
Build the surface; dont be surprised by the answers.

You also own 4 BACKEND TOOLS now (TOOLS.md rows 16, 18, 32, 60) —
NetworkX graph analytics is the natural partner to your hop
visualisation: the traversal gives you the subgraph, NetworkX tells you
which nodes in it actually matter.

If /api/graph ever returns 0 nodes, the graph container lost its data
(happened 3 times). Rebuild in seconds, no LLM calls:
  py -3 -m backend.evaluation.build_graph
Don't debug your UI against an empty graph.
```

### Kanishka
```
Kanishka — the ownership gap that was leaving your area vague is fixed.

You now own XLSX + PPTX + PDF generation END TO END, backend AND
frontend. TOOLS.md had no Owner column at all, so rows 38-41 (the
headline FR-9/FR-12 output) were owned by nobody — the only mention was
a slash in your file saying "Aditya/Aryan". Settled in OWNERSHIP.md §2.

Read this first: backend/tools/documents/draft_docx.py
It's built and it's your reference. It shows the required shape:
• registered in the tool registry
• requires_approval=True  ← NOT optional, hard constraint #4
• citations structural, not prose
• UNSOURCED marked IN the document
• estimate warnings printed in the document

Your items: XLSX (row 39, 🔴), PPTX (40), PDF export, MRPL generators
(54/55/58), /outputs library, calc trace viewer, audit log viewer.

One warning on the calculation trace viewer: the "✓ verified by SymPy"
badge is a load-bearing safety claim (hard constraint #3). Key it on the
actual expression matching the answer — NOT on "did a tool run?". The
math step used to call evaluate_expression with a hardcoded string for
every request, so a tool genuinely ran and the badge would have lied.

You're blocked on nobody — approval gate, audit log and tool registry
are all live.
```

### Sahil
```
Sahil — three surfaces, all with live backends.

• Network monitor panel (🔴) — /api/network/status is live and correct
• Multimodal upload + preview — feeds the OCR/vision pipeline (both work)
• Defect/annotation overlay

READ THIS BEFORE BUILDING THE MONITOR PANEL:
Drive the alarm from `externalCount` (this process tree) and NEVER from
`hostExternalCount` (the whole machine). The old version counted every
socket on the host and the UI showed "ALERT: External Traffic — 44
external connections" on a zero-egress product. All 44 belonged to
Chrome, the IDE and Spotify. The backend owned zero.

A safety indicator that fires on someone else's music stream trains
everyone to ignore it — and on demo day it reads as the product
disproving its own core claim in its own UI. Both numbers are in the
response; show the host one as context only, clearly labelled.

Also: the vision tools set is_estimate=True and that's not decorative.
The chart model was measured inventing 10 numeric values across 2 of 6
charts while describing them as "the numeric values printed as text on
the chart". Anything flagged as an estimate must be visibly labelled.
```

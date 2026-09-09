# Aditya.md — Backend Lead (Heavy Tools)

## Scope of Ownership
- Orchestrator backend infra (FastAPI, LangGraph state graph execution — logic co-owned with Aryan, infra fully yours)
- Sandboxed code execution engine (TOOLS.md §E, items 33-34) — this is the heaviest single piece of infra in the system
- SAP connector, read-only (TOOLS.md item 49 / REQUIREMENTS.md §5) — highest-leverage MRPL-specific feature, treat it accordingly
- Network monitor backend (TOOLS.md item 44) — the actual mechanism proving zero egress, not just the UI panel
- Human approval gate backend logic (holds state until confirmed)
- Audit logging module (TOOLS.md item 45)
- Docker Compose stack + portable/air-gapped packaging (DEPENDENCIES.md §10, SYSTEM.md §5)
- Encryption at rest (NFR-3)

## Explicitly Not Your Job
- Model selection/routing logic (Aryan)
- Any frontend component (Advay's team) — you expose clean APIs, they consume them
- Output file generation (Kanishka) — you provide the trigger/data, they build the DOCX/XLSX/PPTX

## Day-by-Day
- **Day 1-2:** FastAPI skeleton, LangGraph orchestrator scaffold wired to Aryan's router. Basic file read/write tool.
- **Day 3-4:** Sandbox execution engine — Docker container with `--network none`, resource limits, stdout/stderr capture, feedback loop to the code sub-agent for self-correction. Test this hard; it's demo flow #2 in its entirety.
- **Day 5:** SAP connector — build against a mock dataset shaped like real SAP Maintenance/Materials tables (coordinate with Aryan on what fields the grounding layer needs). Document the real-SAP RFC/BAPI interface even though you won't wire it to a live instance.
- **Day 6:** Network monitor backend — poll active connections (psutil/tcpdump), expose via a websocket the frontend can subscribe to. This must be rock-solid; it's the single most judge-scrutinized feature in the whole system.
- **Day 7:** Audit logging — every tool call, every document access, every output generation event, timestamped, exportable. Human approval gate wired into every write/send/SAP-write path.
- **Day 8:** Docker Compose finalization, `docker save` all images, build `install.sh`/`install.bat`, test cold-boot on a machine with no prior setup and no internet.
- **Day 9:** Encryption at rest on vector DB + document store + the portable drive itself. Full-stack rehearsal from the infra side.
- **Day 10:** Buffer, infra bug triage.

## Dependencies on Others
- Needs Aryan's tool schema format finalized by Day 2 to build the orchestrator dispatch layer against it
- Needs Kanishka's output-generation trigger contract by Day 4 so approval-gate → file-write flow is correct
- Netal/Sahil/Kanishka all consume your APIs — freeze API contracts as early as possible (ideally end of Day 2) so frontend work isn't blocked

## Acceptance Criteria You Own
FR-1, FR-4 (infra side), FR-6, FR-9 (trigger/backend side), FR-13, FR-15, NFR-1, NFR-2, NFR-3, NFR-6, NFR-7, REQUIREMENTS.md §5 (SAP)

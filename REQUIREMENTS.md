# REQUIREMENTS.md — SIH26117 Sovereign On-Premise Agentic AI Workbench
**Team:** Ctrl Alt Defeat | **PS Owner:** Mangalore Refinery and Petrochemicals Limited (MRPL) | **Category:** Software | **Theme:** Smart Automation
**Document version:** 1.0 — Final | **Last updated:** as of build kickoff

---

## 1. Purpose

This document is the single source of truth for what must be built, why, and how we know it's done. Every requirement below traces back to a literal sentence in the PS26117 description or expected solution. Nothing is included that isn't traceable, and nothing from the PS is left uncovered.

---

## 2. Functional Requirements (FR)

| ID | Requirement | Source (PS line) | Acceptance Criteria | Owner |
|---|---|---|---|---|
| FR-1 | System runs fully self-hosted, air-gapped, on the org's own GPU server | "self-hosted, air gapped AI workbench running entirely on the organization's own GPU server" | Zero outbound network calls during any operation, verified live via network monitor panel | Aditya |
| FR-2 | Backend supports multiple open-weight models simultaneously | "not locked to one model... support multiple open weight models at once" | Model registry lists ≥4 models across ≥3 task categories, all loadable concurrently within VRAM budget | Aryan |
| FR-3 | System auto-selects the right model per task | "automatically pick the right one for a given task" | Router correctly classifies and routes ≥90% of a 20-prompt mixed test set (code / summarization / vision / math) | Aryan |
| FR-4 | New models addable without redesign | "New open weight models should be addable later without redesigning the system" | Adding a model = editing `models.yaml` + reload, zero code changes, demoed live in <2 minutes | Aryan / Aditya |
| FR-5 | Agent plans multi-step work and executes autonomously | "Plan out multi step work... iterate on a task instead of answering once and stopping" | Given a multi-part request, agent produces a visible plan graph, executes each step, and reports completion status per step | Aryan / Aditya |
| FR-6 | Agent can call local tools: file I/O, code execution, spreadsheet work, document search | "call local tools such as file read and write, code execution in a sandbox, spreadsheet work, internal document search" | Each tool category has ≥1 working, callable implementation with a defined schema | Aditya / Sahil |
| FR-7 | System handles scanned PDFs, handwritten notes, engineering drawings, photographs | "handle more than text too: scanned PDFs, handwritten notes, engineering drawings, photographs" | Demo corpus includes ≥1 sample of each type, each successfully processed end-to-end | Sahil / Aryan |
| FR-8 | On-device OCR and vision models, no external calls | "read through on device OCR and vision models" | OCR + VLM both run as local inference processes, verified against network monitor | Aryan |
| FR-9 | Real deliverables generated: approval notes, PPT/Word/Excel, working code, calculations with steps shown | "Output should be real deliverables... not just chat replies" | Each output type has a working generator producing a valid, openable file | Kanishka / Aditya |
| FR-10 | Local knowledge base grounded in org's own manuals/SOPs/correspondence | "ground itself in the organization's own manuals, SOPs and past correspondence through a local knowledge base connector" | Ingestion pipeline accepts a folder of mixed documents, indexes them, answers are traceable to source passages | Aryan / Netal |
| FR-11 | Demonstrable model auto-selection across ≥2 task types | Expected Solution | Live demo shows router picking different models for ≥2 distinct task types in one session | Aryan |
| FR-12 | Agentic task carried end-to-end: scanned inspection report → key findings → DOCX approval note | Expected Solution (explicit example) | Full pipeline run live, producing an openable, correctly formatted DOCX | Sahil / Kanishka |
| FR-13 | Coding task run and verified in a sandbox | Expected Solution | Agent writes code, executes it in an isolated container, reports pass/fail of a verification step | Aditya |
| FR-14 | Multimodal task: image or scanned document understanding | Expected Solution | Live demo of VLM correctly interpreting an image/diagram input | Aryan / Sahil |
| FR-15 | Visible proof of zero external calls throughout | Expected Solution ("that's the actual proof of the sovereign claim") | Network monitor UI panel visible and reading zero external connections throughout the entire demo | Aditya / Advay |

---

## 3. Non-Functional Requirements (NFR)

| ID | Requirement | Rationale | Target |
|---|---|---|---|
| NFR-1 | Must run on an 8GB VRAM consumer GPU (RTX 4060) for development | Actual dev hardware constraint | All demo-critical models fit in ≤8GB via Q4/Q5 quantization |
| NFR-2 | Fully portable — deployable from a single external drive with no internet | Air-gapped facility deployment reality | Bootstrap script installs and starts the full stack in <10 minutes from a cold machine |
| NFR-3 | Data at rest encrypted (documents, vector DB, portable drive) | Confidential industrial data ("financials, vendor negotiations, unreleased designs") | AES-256 or equivalent on all persisted stores |
| NFR-4 | Every generated claim traceable to a source document | Trust requirement for approval-note drafting in a safety-critical industry | 100% of generated factual claims in the demo carry a visible source citation |
| NFR-5 | Every numeric/calculation output is code-verified, not LLM-guessed | Accuracy requirement for engineering calculations | All demoed calculations show the executed code alongside the result |
| NFR-6 | Human confirmation required before any file write/send action | Safety/governance requirement appropriate to approval workflows | No destructive or external-facing action executes without an explicit UI confirmation step |
| NFR-7 | Full audit trail of tool calls, documents accessed, outputs generated | Governance/compliance expectation for a PSU/defence-linked context | Exportable, timestamped audit log covering the entire demo session |
| NFR-8 | System usable by a non-technical refinery/office user | End-user is not a developer | Ships as a native Electron desktop app (FRONTEND.md §4.1) launched by double-clicking an icon; bootstrap script is the only CLI touchpoint, and only at first-time setup |

---

## 4. Explicit Out-of-Scope (for the 10-day build — stated so nobody wastes time)

- Write-back to MRPL's live SAP system (read-only connector only, per Requirements §5)
- Full production-grade RBAC / SSO integration (a basic permission-tier demo suffices)
- Training or fine-tuning any model from scratch (use existing open-weight checkpoints, optionally light fine-tuning for the defect-detection YOLO model only, using public datasets)
- Multi-GPU distributed inference
- Mobile app version

---

## 5. SAP Integration Requirement (called out separately — highest-leverage item)

- MRPL has run SAP ERP live since 15 Oct 2010 across Finance, Materials, Maintenance, Projects, Marketing, Production, Quality Assurance
- Requirement: a **local, read-only** connector tool that can query on-prem SAP data (maintenance records, materials data, QA data) and surface it as grounding context for agent outputs
- For the demo: since we will not have live access to MRPL's actual SAP instance, this ships as (a) a fully working connector against a **local mock SAP-shaped dataset** (structured to match real SAP table/report shapes — e.g. maintenance notifications, material master records) and (b) a documented, ready-to-point-at-real-SAP interface (RFC/BAPI or scheduled local export ingestion) that MRPL's IT team could wire up post-hackathon
- This must be presented honestly as "demo against a representative local dataset, architecture ready for their real SAP" — not overclaimed as already connected to MRPL's live system

---

## 6. Traceability Statement

Every requirement in §2 and §3 was derived directly from the PS26117 text (Background, Description, Expected Solution) with no invented scope beyond what category H of TOOLS.md adds as differentiators. This table is the artifact judges can be shown to prove full PS coverage line by line.

**Addendum, 2026-09-09 — team-added, non-PS-traceable capabilities:** a small number of tools go beyond both the PS text and category H's MRPL-specific differentiators (e.g. TOOLS.md #61, local voice-note transcription). These are deliberate, explicitly-tracked scope decisions — never presented to judges as PS-derived — made when they extend the general robustness of an already-in-scope requirement (here, FR-7's document-modality handling) using the same offline-first, no-invented-scope discipline as everything else in this catalog. Every such tool is marked "Team addition" in TOOLS.md's notes column so this traceability statement stays honest rather than being quietly broadened.

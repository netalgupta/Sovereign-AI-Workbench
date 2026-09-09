# Kanishka.md — Fullstack (Foundational Tools)

## Scope of Ownership (per FRONTEND.md §5)
- Output file card + library, `/outputs` page (FRONTEND.md §3.7 / TOOLS.md items 38-40)
- Calculation trace viewer (FRONTEND.md §3.8 / TOOLS.md item 41) — including the "✓ verified by SymPy" badge language specified exactly in FRONTEND.md
- Audit log viewer, `/audit` page (FRONTEND.md §3.10 / TOOLS.md item 45)
- File upload UI feeding Aryan's ingestion pipeline (support role — primary upload UX for scans lives with Sahil, but the settings-side "add source" upload in the Sources panel area is yours to coordinate with Netal on)

## Explicitly Not Your Job
- The math computation itself (Aryan wires the tools; you render the result)
- The DOCX/XLSX/PPTX generation code on the backend (Aditya/Aryan trigger it; you build the card/preview/download UI)
- App shell, chat, plan graph, approval modal, settings (Advay owns all of these per FRONTEND.md §5)
- Sources panel, citations, graph explorer (Netal)
- Network monitor, multimodal upload/preview, defect overlay (Sahil)

## Day-by-Day
- **Day 1-2:** Output file card component — file type icon, thumbnail preview, download button, per FRONTEND.md §3.7 spec exactly.
- **Day 3-4:** `/outputs` library page — grid/list view, filterable by type and date, citation-count badge on each card.
- **Day 5-6:** Calculation trace viewer — step-by-step math display from CARD 08's `steps` list, monospace styling, the verified badge.
- **Day 7-8:** Audit log viewer — table view of Aditya's audit log, filter by action type/date, CSV export button, free-text search.
- **Day 9:** Hand off all components to Advay for integration; support his consistency pass with fixes to your own components as issues surface.
- **Day 10:** Buffer, bug fixes.

## Dependencies on Others
- Needs Aditya's file-generation and audit-log API contracts by Day 2
- Reports finished components to Advay for integration into the main app shell by Day 8

## Acceptance Criteria You Own
FR-9 (viewer/download side), NFR-5 (trace display), NFR-7 (audit viewer side)

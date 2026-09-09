# Netal.md — Fullstack (Mid-Complexity Tools)

## Scope of Ownership (per FRONTEND.md §5)
- Citation chip + expansion panel (FRONTEND.md §3.2) — inline expandable source-passage cards, integrated by Advay into the chat stream
- Sources panel (left rail) + full `/sources` page (FRONTEND.md §3.5) — the NotebookLM-style ingested-document list, include/exclude toggles, and the persistent trust-statement line specified exactly in FRONTEND.md ("This session is grounded only in the sources listed here.")
- Graph explorer, `/graph` standalone page (FRONTEND.md §3.6 / GRAPH_SPEC.md §6) — this is the second-highest-impact visual in the whole demo after the plan graph; the signature query's subgraph-highlight animation is your responsibility to get right

## Explicitly Not Your Job
- The retrieval/graph backend logic (Aryan owns RAG_SPEC.md and GRAPH_SPEC.md's implementation) — you visualize its output
- App shell, chat, plan graph, approval modal, settings (Advay)
- Output cards, calc trace, audit log (Kanishka)
- Network monitor, multimodal upload, defect overlay (Sahil)

## Day-by-Day
- **Day 1-2:** Sources panel — basic ingested-document list UI, type icons, ingestion date, include/exclude toggle switches.
- **Day 3-4:** Citation chip + expansion component — given a citation reference from a generated output, fetch and display the exact source passage per RAG_SPEC.md's chunk metadata.
- **Day 5-6:** Graph explorer — `react-force-graph`/`vis-network` rendering GRAPH_SPEC.md's node/relationship schema, color-coded by node type, search bar to jump to a specific entity (e.g. "V-204").
- **Day 7:** Wire the signature demo query (GRAPH_SPEC.md §6) — implement the subgraph-highlight animation on query execution, this is a genuinely important demo visual, prioritize it over polish elsewhere.
- **Day 8:** `/sources` full page, side panel on graph node click showing every referencing document, linked back to the Sources panel.
- **Day 9:** Hand off to Advay for integration; support his consistency pass.
- **Day 10:** Buffer, bug fixes.

## Dependencies on Others
- Needs Aryan's chunk metadata / citation format finalized by Day 3
- Needs Aryan's graph query result format (matching GRAPH_SPEC.md §6's Cypher return shape) by Day 5
- Reports components to Advay for integration by Day 8

## Acceptance Criteria You Own
FR-10 (citation UI side), NFR-4 (citation display), GRAPH_SPEC.md §6's signature query presentation

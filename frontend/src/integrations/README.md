# Sovereign Workbench — Plug-and-Play Integration Architecture

The `/src/integrations/` directory provides an isolated adapter layer and strict folder convention for collaborative frontend development. Each teammate component lives in a designated subfolder featuring: (1) a `contract.js` documenting the exact JSDoc interface, canonical mock data, and runtime prop validation, (2) a `Placeholder.jsx` stub presenting the expected layout and handoff status, and (3) an `index.js` single-export boundary with dev-only prop validation. When Netal, Kanishka, or Sahil delivers their real component, dropping their file into the folder and editing **exactly one line** in `index.js` (`import Component from './RealComponent'`) immediately activates their feature across the entire workbench with zero wiring, routing, or prop-mapping required.

---

## Component Integration Matrix

| Subfolder | Component | Owner | Route / Mount Point | Current Status | Description & Spec |
|---|---|---|---|---|---|
| [`citations/`](file:///c:/SIH/SIH26117-Sovereign-Workbench/frontend/src/integrations/citations) | `CitationCard` / `SourcesUsedList` | **Netal** | Inline Chat Stream & Thinking Block | `stub` | Expandable grounded source passage citation (§3.2) |
| [`sources-panel/`](file:///c:/SIH/SIH26117-Sovereign-Workbench/frontend/src/integrations/sources-panel) | `SourcesPanel` | **Netal** | `/sources` route & Left Sidebar Rail | `stub` | NotebookLM-style grounded knowledge base manager (§3.5) |
| [`graph-explorer/`](file:///c:/SIH/SIH26117-Sovereign-Workbench/frontend/src/integrations/graph-explorer) | `GraphExplorer` | **Netal** | `/graph` route | `stub` | Interactive Neo4j knowledge graph entity canvas (§3.6) |
| [`output-cards/`](file:///c:/SIH/SIH26117-Sovereign-Workbench/frontend/src/integrations/output-cards) | `OutputCards` | **Kanishka** | `/outputs` route & Inline File Cards | `integrated` | Deliverable file library (DOCX, XLSX, PPTX) with citation badges (§3.7) |
| [`calc-trace/`](file:///c:/SIH/SIH26117-Sovereign-Workbench/frontend/src/integrations/calc-trace) | `CalcTraceCard` | **Kanishka** | Inline Chat Tool Call Results | `stub` | Symbolic derivation trace with `✓ verified by SymPy` badge (§3.8) |
| [`audit-log/`](file:///c:/SIH/SIH26117-Sovereign-Workbench/frontend/src/integrations/audit-log) | `AuditLog` | **Kanishka** | `/audit` route | `stub` | Tamper-evident operational event stream with CSV export (§3.10) |
| [`network-monitor/`](./network-monitor) | `NetworkMonitor` / `NetworkMonitorBar` | **Sahil** | `/monitor` route & Chat Bottom Bar | `integrated` | Real-time air-gap security & socket monitor (§3.9); 1s polling of `GET /api/network/status` IS the live feed — there is no network-telemetry websocket to subscribe to |
| [`multimodal-upload/`](./multimodal-upload) | `MultimodalUpload` | **Sahil** | Chat Composer Paperclip & Dropzone | `integrated` | Drag-and-drop ingestion for scans, photos, PDFs + thumbnails; images → `detect_defects`, audio → `transcribe_voice_note` (§3.13) |
| [`defect-overlay/`](./defect-overlay) | `DefectOverlay` | **Sahil** | Chat Findings & Image Viewer | `integrated` | OCR-box detection overlay on plant inspection photos (§3.14); YOLOv8 detector swap planned behind the same contract |

---

## The One-Line Swap Procedure

To integrate a teammate's real component:
1. Drop the component file into the corresponding integration folder (e.g. `frontend/src/integrations/output-cards/RealOutputCards.jsx`).
2. Open `index.js` in that folder and edit **only line 3**:
   ```diff
   - import Component from './Placeholder'
   + import Component from './RealOutputCards'
   ```
3. Done! All routes, parent containers, and props immediately connect to the real component with zero app-wide code edits.

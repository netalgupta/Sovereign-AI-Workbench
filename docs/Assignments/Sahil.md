# Sahil.md — Fullstack (Mid-Complexity Tools)

## Scope of Ownership (per FRONTEND.md §5)
- Network monitor widget (persistent, right rail) + full `/monitor` view (FRONTEND.md §3.9 / TOOLS.md item 44) — coordinate closely with Aditya, this must be wired to the live websocket feed from CARD 07, never hardcoded, per that card's explicit anti-hallucination note
- Multimodal upload + preview, chat-integrated (FRONTEND.md §3.13) — drag-and-drop/paperclip upload, thumbnail preview, feeding the OCR/vision pipeline
- Defect/anomaly detection + annotation overlay (FRONTEND.md §3.14 / TOOLS.md row 7) — **the whole stack is yours: model AND overlay.** Implemented stage 1 = OCR-box detections via the registered `detect_defects` tool (offline, proven), rendered by DefectOverlay; the YOLOv8 detector swaps into the same output contract later. The three constraints that govern the detector upgrade (ultralytics phone-home ×4, cuDNN pin, corpus-naming accuracy) are recorded in TOOLS.md row 7 and the tool module docstring.

## Explicitly Not Your Job
- Handwritten OCR / TrOCR fallback and the vision-language model integration itself (Aryan) — the `detect_defects` tool calls the printed-OCR pipeline but its detection-source swap is yours
- The network monitor's actual detection mechanism (CARD 07, Aditya) — you render the feed, you do not compute connection status yourself
- App shell, chat, plan graph, approval modal, settings (Advay)
- Sources panel, citations, graph explorer (Netal)
- Output cards, calc trace, audit log (Kanishka)

## Day-by-Day
- **Day 1-2:** Multimodal upload component — drag-and-drop or paperclip icon in the chat composer, immediate thumbnail preview before processing.
- **Day 3-4:** Wire the upload component to the OCR/vision pipeline and add the read-only `/api/inspection/image` serving route — this is the critical hand-off, push for it early.
- **Day 5-6:** Defect detection + annotation overlay — bounding boxes over inspection photos, labeled with class + confidence, produced by the `detect_defects` tool and rendered by DefectOverlay.
- **Day 7:** Network monitor widget (persistent) — single always-visible line per FRONTEND.md §3.9 exact spec, green/red dot logic, wired to Aditya's live websocket.
- **Day 8:** Full `/monitor` view — live connection table, external-connection alert behavior. Rehearse that this is visibly live, not static, since it will be scrutinized directly.
- **Day 9:** Hand off to Advay for integration; support his consistency pass.
- **Day 10:** Buffer, bug fixes — prioritize the network monitor above the other two components if time runs short, it's the single most judge-scrutinized UI element in the app.

## Dependencies on Others
- Needs the printed-OCR pipeline output format finalized by Day 3 (push for this early) — the `detect_defects` tool consumes `extract_printed_text`'s OCR lines.
- Needs Aditya's network monitor websocket contract by Day 6 — this is one of the two or three most important integration points in the whole build
- Reports components to Advay for integration by Day 8

## Acceptance Criteria You Own
FR-7, FR-14 (UI side), FR-15 (UI side), TOOLS.md row 7 (detect_defects tool registered, offline-proven, overlay mounting from real detections), demo flow #3 in TOOLS.md §I
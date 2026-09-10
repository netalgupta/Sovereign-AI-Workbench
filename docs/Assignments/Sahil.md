# Sahil.md — Fullstack (Mid-Complexity Tools)

## Scope of Ownership (per FRONTEND.md §5)
- Network monitor widget (persistent, right rail) + full `/monitor` view (FRONTEND.md §3.9 / TOOLS.md item 44) — coordinate closely with Aditya, this must be wired to the live websocket feed from CARD 07, never hardcoded, per that card's explicit anti-hallucination note
- Multimodal upload + preview, chat-integrated (FRONTEND.md §3.13) — drag-and-drop/paperclip upload, thumbnail preview, feeding Aryan's OCR/vision pipeline
- Defect/annotation overlay viewer (FRONTEND.md §3.14) — bounding-box rendering over inspection photos from YOLOv8 output

## Explicitly Not Your Job
- The OCR/vision models themselves (Aryan integrates PaddleOCR/TrOCR/Qwen2.5-VL) — you build the UI that displays their output
- The network monitor's actual detection mechanism (CARD 07, Aditya) — you render the feed, you do not compute connection status yourself
- App shell, chat, plan graph, approval modal, settings (Advay)
- Sources panel, citations, graph explorer (Netal)
- Output cards, calc trace, audit log (Kanishka)

## Day-by-Day
- **Day 1-2:** Multimodal upload component — drag-and-drop or paperclip icon in the chat composer, immediate thumbnail preview before processing.
- **Day 3-4:** Wire the upload component to Aryan's ingestion/OCR pipeline once the output format is finalized — this is the critical hand-off, push for it early.
- **Day 5-6:** Defect/annotation overlay viewer — bounding boxes over inspection photos using YOLOv8 output coordinates, labeled with class + confidence.
- **Day 7:** Network monitor widget (persistent) — single always-visible line per FRONTEND.md §3.9 exact spec, green/red dot logic, wired to Aditya's live websocket.
- **Day 8:** Full `/monitor` view — live connection table, external-connection alert behavior. Rehearse that this is visibly live, not static, since it will be scrutinized directly.
- **Day 9:** Hand off to Advay for integration; support his consistency pass.
- **Day 10:** Buffer, bug fixes — prioritize the network monitor above the other two components if time runs short, it's the single most judge-scrutinized UI element in the app.

## Dependencies on Others
- Needs Aryan's OCR/vision output format finalized by Day 3 (push for this early)
- Needs Aryan's YOLOv8 bounding-box output format by Day 5
- Needs Aditya's network monitor websocket contract by Day 6 — this is one of the two or three most important integration points in the whole build
- Reports components to Advay for integration by Day 8

## Acceptance Criteria You Own
FR-7, FR-14 (UI side), FR-15 (UI side), demo flow #3 in TOOLS.md §I

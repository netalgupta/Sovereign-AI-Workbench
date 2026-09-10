# Aryan.md — RAG / AI / ML / LLM Engineering, Team Lead

## Scope of Ownership
- Model registry design + router/classifier logic (TOOLS.md §C, items 20-22)
- Hybrid RAG + GraphRAG pipeline, entity/relationship extraction (TOOLS.md §B, items 12-14, 17)
- Vision model integration (Qwen2.5-VL wiring, not the UI around it — that's Sahil's)
- Math tool wiring into the agent's tool-call layer (TOOLS.md §D)
- Overall technical direction and architecture sign-off (SYSTEM.md is your document to keep accurate)
- Final say on model selection/quantization tradeoffs given the RTX 4060 constraint (DEPENDENCIES.md §1)

## Explicitly Not Your Job (delegate, don't absorb)
- Frontend of any kind (Advay's team)
- Sandbox execution mechanics (Aditya)
- Output file generation code (Kanishka)
- SAP connector implementation (Aditya, with your input on what grounding data it should surface)

## Day-by-Day
- **Day 1-2:** Stand up model registry (`models.yaml`), get Ollama serving phi-3.5-mini + qwen2.5-coder:7b + qwen2.5:14b + qwen2.5vl:7b concurrently-or-sequentially within 8GB budget. Build the router classifier and test against a 20-prompt mixed set (FR-3 acceptance target: ≥90%).
- **Day 3-4:** Build the ingestion pipeline (chunking, embeddings via bge-large), hybrid retrieval (dense+BM25+RRF). Hand off document-type-classifier output to Sahil's OCR pipeline as an input contract.
- **Day 5-6:** Entity/relationship extraction + graph construction (Neo4j — locked choice, see GRAPH_SPEC.md §2). Get the signature graph query working: "show every SOP referencing Valve/segment X." Wire source citations into every retrieval-grounded output.
- **Day 7:** Wire the math tool layer (SymPy/Maxima/NumPy/Pint/CoolProp) as callable agent tools with schemas. Confirm no LLM is doing arithmetic unverified anywhere in the pipeline.
- **Day 8:** Self-verification agent pass. Contradiction detection across documents if time allows (🟡 tier).
- **Day 9:** End-to-end rehearsal of all 3 non-negotiable demo flows from your side — router correctness, retrieval grounding, math verification.
- **Day 10:** Buffer, bug triage across the whole AI/ML stack.

## Dependencies on Others
- Needs Sahil's OCR output format finalized by Day 3 to build the ingestion pipeline against real extracted text
- Needs Aditya's sandbox interface spec by Day 5 to wire code-sub-agent tool calls correctly
- Needs Netal's graph visualization component spec by Day 6 so the graph query returns data in the shape the UI expects

## Acceptance Criteria You Own
FR-2, FR-3, FR-4, FR-8, FR-10, FR-11, FR-14, NFR-4, NFR-5 (see REQUIREMENTS.md for full text)

# Aryan.md — RAG / AI / ML / LLM Engineering, Team Lead

## Scope of Ownership
- Model registry design + router/classifier logic (TOOLS.md §C, items 20-22)
- Hybrid RAG + GraphRAG pipeline, entity/relationship extraction (TOOLS.md §B, items 12-14, 17)
- Vision model integration (Qwen2.5-VL wiring, not the UI around it — that's Sahil's)
- Math tool wiring into the agent's tool-call layer (TOOLS.md §D)
- Overall technical direction and architecture sign-off (SYSTEM.md is your document to keep accurate)
- Final say on model selection/quantization tradeoffs given the RTX 4060 constraint (DEPENDENCIES.md §1)

## Agentic tool calling — NEW, and the current quality gap is mine

**Built:** `backend/orchestrator/agent_loop.py` + `POST /api/chat/stream`.
A real tool-calling loop using Ollama's native function calling
(verified with qwen2.5:7b): the model sees the registry, chooses a tool,
gets the result back in the conversation, and continues — narrating
throughout. Every step is an event; the protocol is
`docs/Technical_Specs/AGENT_STREAM_PROTOCOL.md`.

This closed a real hole. `dispatch_node` chose tools with a hardcoded
if/elif on agent type, so 17 registered tools with derived schemas were
unreachable — the model never CHOSE anything. Hard constraint #3 ("no
math without a tool call") held only for the one arithmetic path wired
by hand.

**And it exposed a bigger one:** there was no search tool. The registry's
"retrieval" category held `find_contradictions` and
`select_images_for_request`, so it looked populated, while hybrid search
— the thing the whole product rests on — was reachable only from inside
`dispatch_node`. Given the full registry and asked for a value printed
in the corpus, the model called `find_contradictions`, got `[]`, and
reported that no document contained it. Fixed:
`backend/tools/retrieval_tools.py` registers `search_documents` and
`list_documents`.

**MY OPEN ITEM, stated plainly:** answer quality on the streaming path
is currently WORSE than `/api/chat`. The loop retrieves correctly and
then under-extracts — the direct path answers "3.4 g/10min [1]"
consistently where the loop retrieved the right documents and said it
could not find the value. The difference is scaffolding, not mechanism:
`/api/chat` applies a grounding prompt tuned against measured failures
(citation form, answer depth, refusal wording) and the loop hands raw
passages to a 7B with a general system prompt.

Until that closes: `/api/chat` is the default answering path,
`/api/chat/stream` is the agentic one, and Netal builds the thinking UI
against the stream knowing this.

Also mine: tool-selection reliability. Offering all 19 tools to a 7B
produced `lookup_thermophysical_property` called five times drifting
into the density of methane. Curating `CHAT_TOOLS` fixed it; that
curation is a workaround for a model-size limit and should be revisited
on venue hardware.

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

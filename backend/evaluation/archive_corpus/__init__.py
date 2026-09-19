"""Synthetic MRPL company archive, 2020-2026 — a SEPARATE corpus.

WHY A NEW TOP-LEVEL FOLDER, NOT MORE FILES IN MRPL_RAG_Test_Corpus.

That corpus is the validated retrieval baseline: the 0.60 confidence
threshold was calibrated against it (calibrate_confidence.py), the
precision ceiling analysis is measured against its exact 21-chunk shape,
and half a dozen tests assert specific chunk ranks and document names
from it by name (SOP-114-Rev3, the Hassan segment, H030SG). Dropping
hundreds of new chunks into that folder would silently invalidate every
one of those measurements. generate_chart_corpus.py already established
this convention for the same reason; this follows it.

WHY TWO GENERATION ENGINES.

"Crazy amounts of rows and columns" and "an LLM writes every cell" are
opposite ideas. A spreadsheet of six years of daily instrument readings
is not narrative content -- it is generated the way a real one would be,
programmatically, with realistic trend/noise/excursion structure. An
LLM asked to author thousands of numeric rows would be slower by three
orders of magnitude AND less realistic than numpy with a seeded RNG.

So bulk_tables.py (numpy + openpyxl, no model calls, effectively free)
produces the huge tabular files, and narrative_docs.py (real local
model, one call per document) produces SOPs, inspection reports,
incident reports, and correspondence -- the documents that are
supposed to read like something a person wrote.

WHY THE VOCABULARY IS SHARED AND FIXED, NOT GENERATED PER DOCUMENT.

Every generator draws unit names, equipment tags, depot names and
personnel from vocab.py, which reuses the EXACT strings already in
MRPL_RAG_Test_Corpus and in this repo's own tests (Hydrocracker-2,
CCR-1, TK-K-01, FFC-201, the Kasargod/Hindupur/Hosur depots Netal's row
60 already names). A generator free to invent a new equipment tag per
document would produce thousands of entities that each appear once --
which is a graph with no edges. Reusing the same fixed set across years
is what lets an incident in 2022 and a maintenance log in 2024
reference the same pump and actually connect.

NO NETWORK CALLS DURING GENERATION EITHER. bulk_tables.py touches
nothing but numpy/openpyxl. narrative_docs.py calls Ollama on localhost
through the same resolve_model_name() + generate() path every other
tool in this repo uses -- CLAUDE.md hard constraint #2 (no hardcoded
model names in orchestration logic) applies here too, even though this
is a one-off generation script and not the live orchestrator, because
the alternative is a script that silently breaks the first time
models.yaml changes.
"""

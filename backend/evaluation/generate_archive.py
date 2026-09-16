"""Generate the full synthetic MRPL archive corpus, 2020-2026.

    py -3 -m backend.evaluation.generate_archive
    py -3 -m backend.evaluation.generate_archive --narrative-only
    py -3 -m backend.evaluation.generate_archive --bulk-only
    py -3 -m backend.evaluation.generate_archive --sops 40 --inspections 50 \\
        --incidents 40 --correspondence 40 --board-reviews 28

RESUMABLE. Narrative generation checkpoints every document to
MRPL_Archive_Corpus/.manifest.json as it is produced. Killing this
script and re-running it skips everything already done -- see
archive_corpus/narrative_docs.py for why that matters at LLM-call cost.

Bulk tables (huge spreadsheets) are cheap enough to just regenerate;
they are not checkpointed.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

ARCHIVE_ROOT = Path("MRPL_Archive_Corpus")


def _write_readme(root: Path) -> None:
    from .archive_corpus import vocab

    readme = f"""# MRPL_Archive_Corpus — synthetic company archive, 2020-2026

{vocab.synthetic_disclaimer()}

A SEPARATE corpus from MRPL_RAG_Test_Corpus, deliberately. That corpus
is the validated retrieval baseline the confidence threshold and
precision measurements are calibrated against; this one exists to
stress-test retrieval, GraphRAG and ingestion at real archive scale
without disturbing those measurements.

## What is in here

| Folder | Format | Content |
|---|---|---|
| 01_SOPs_and_Procedures | .docx | Procedures per unit, spanning 2020-2026 |
| 02_Inspection_and_Maintenance | .pdf | Inspection and incident reports per unit/year |
| 03_Quality_and_Process_Data | .xlsx | Daily instrument readings, EVERY unit, EVERY day, 2020-2026 |
| 04_SAP_Mock_Exports | .xlsx | Material master + maintenance work-order history, thousands of rows |
| 05_Correspondence | .docx | Depot-HQ correspondence threads (Kasargod/Hindupur/Hosur) |
| 06_Board_and_Quarterly_Reviews | .docx | Quarterly operations review memos |

## Entities

Every unit, equipment tag, depot and person name reused across every
document and every year is the SAME fixed set (backend/evaluation/
archive_corpus/vocab.py) — reused deliberately, not invented per
document, so the knowledge graph has edges: an equipment tag mentioned
in a 2022 incident report is the same tag mentioned in a 2024
maintenance log.

## Regenerating / extending

    py -3 -m backend.evaluation.generate_archive

Resumable — already-generated narrative documents are skipped via
.manifest.json. Increase any --count flag and re-run to grow the corpus
further; nothing already done is regenerated or duplicated.
"""
    (root / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sops", type=int, default=40)
    parser.add_argument("--inspections", type=int, default=50)
    parser.add_argument("--incidents", type=int, default=40)
    parser.add_argument("--correspondence", type=int, default=40)
    parser.add_argument("--board-reviews", type=int, default=28)
    parser.add_argument("--narrative-only", action="store_true")
    parser.add_argument("--bulk-only", action="store_true")
    parser.add_argument("--diagrams", type=int, default=12)
    args = parser.parse_args()

    from .archive_corpus import bulk_tables, diagrams, narrative_docs

    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    _write_readme(ARCHIVE_ROOT)

    if not args.narrative_only:
        print("=== Bulk tabular data (numpy, no model calls) ===")
        t0 = time.perf_counter()
        s1 = bulk_tables.generate_process_readings_log(
            ARCHIVE_ROOT / "03_Quality_and_Process_Data" / "Process_Readings_All_Units_2020_2026.xlsx"
        )
        total_rows = sum(v["rows"] for v in s1.values())
        print(f"  process readings: {total_rows} rows across {len(s1)} unit sheets")
        s2 = bulk_tables.generate_sap_material_master(
            ARCHIVE_ROOT / "04_SAP_Mock_Exports" / "SAP_Material_Master_Full_Export.xlsx"
        )
        print(f"  SAP material master: {s2['rows']} line items")
        s3 = bulk_tables.generate_maintenance_work_orders(
            ARCHIVE_ROOT / "04_SAP_Mock_Exports" / "Work_Order_History_2020_2026.xlsx"
        )
        print(f"  work orders: {s3['rows']} rows")
        print(f"  done in {time.perf_counter() - t0:.1f}s\n")

        print(f"=== Diagrams and scans ({args.diagrams}) ===")
        t0 = time.perf_counter()
        diag_stats = diagrams.generate_batch(args.diagrams, ARCHIVE_ROOT / "06_Diagrams_and_Scans")
        print(f"  {diag_stats['generated']} image(s) in {time.perf_counter() - t0:.1f}s\n")

    if not args.bulk_only:
        specs = (
            narrative_docs.plan_sops(args.sops)
            + narrative_docs.plan_inspection_reports(args.inspections)
            + narrative_docs.plan_incident_reports(args.incidents)
            + narrative_docs.plan_correspondence(args.correspondence)
            + narrative_docs.plan_board_reviews(args.board_reviews)
        )
        print(f"=== Narrative documents: {len(specs)} planned ===")
        print("    (resumable — rerun after an interruption to continue)")
        t0 = time.perf_counter()
        result = narrative_docs.generate_batch(specs, ARCHIVE_ROOT, verbose=True, progress_every=3)
        elapsed = time.perf_counter() - t0
        print(
            f"\n  generated={result['generated']} skipped={result['skipped']} "
            f"failed={len(result['failed'])} in {elapsed:.1f}s"
        )
        if result["failed"]:
            print(f"  FAILED doc_ids: {result['failed'][:10]}")

    print("\nDone. Add MRPL_Archive_Corpus as a source in the Sources panel to ingest it.")


if __name__ == "__main__":
    main()

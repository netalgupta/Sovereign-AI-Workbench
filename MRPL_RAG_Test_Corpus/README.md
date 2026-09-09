# MRPL Synthetic RAG Test Corpus

**Everything in this folder is synthetic, illustrative test data** generated for RAG/GraphRAG accuracy testing on SIH26117. It is grounded in MRPL's real unit names, terminology, and pipeline geography (per the MRPL-Grounded Dossier) but no figures, incidents, batch numbers, or personnel names are real MRPL data. Safe to ingest, safe to share, safe to include in a public repo.

## Folder Structure

```
01_SOPs_and_Procedures/       — DOCX: SOP + safety circular
02_Inspection_and_Maintenance/ — PDF + XLSX: inspection reports, maintenance log, incident report
03_Quality_and_Process_Data/   — PDF + XLSX: QA reports, trend logs, compliance sheets
04_SAP_Mock_Exports/           — XLSX: mock SAP-shaped materials master data
05_Correspondence/             — DOCX: depot-to-HQ email thread
06_Diagrams_and_Scans/         — PNG: P&ID schematic, pipeline map, simulated scanned checklist
```

## File Inventory

| File | Type | Contains |
|---|---|---|
| SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx | DOCX | Tables, revision history table |
| Aromatic_Complex_Benzene_Safety_Circular.docx | DOCX | Exposure limit table |
| Inspection_Report_CCR1_Regeneration_Cycle.pdf | PDF | Table + embedded bar chart |
| Maintenance_Log_Q3_2026.xlsx | XLSX | Table, native pie chart, native bar chart, SUM/SUMIF formulas |
| Pipeline_Incident_Report_Hassan_Segment.pdf | PDF | Table + embedded bar chart |
| Novolen_Batch_QA_Report_Aug2026.pdf | PDF | Table + embedded pie chart |
| PSA_Hydrogen_Purity_Trend_Log.xlsx | XLSX | Native line chart, native pie chart |
| Sulphur_Spec_Compliance_LabSheet.xlsx | XLSX | Native bar chart, IF-formula compliance flagging |
| SAP_Mock_Materials_Master_Export.xlsx | XLSX | Native pie chart, native bar chart, COUNTIF/SUMIF formulas |
| Correspondence_Depot_HQ_Thread_Kasargod.docx | DOCX | Multi-message email-style thread |
| Hydrocracker_PID_Schematic.png | PNG | Diagram with equipment boxes + valve tags (V-201 to V-208) |
| Pipeline_Segment_Map_Mangalore_Hassan.png | PNG | Corridor map with named stations and segments |
| Scanned_Inspection_Checklist_CCR1.png | PNG | Simulated scanned form (rotation + noise) for OCR testing |

## Deliberate Test Cases Built Into the Data

These are intentional "needles" planted for testing retrieval, trend-detection, and compliance-flagging logic — not errors in the data:

1. **PSA-3 purity drift** (PSA_Hydrogen_Purity_Trend_Log.xlsx) — deliberately drops below the 99.9% target in the final 3 of 12 weeks. Tests whether trend-analysis/anomaly-flagging correctly identifies the drift.
2. **Sulphur spec exceedance** (Sulphur_Spec_Compliance_LabSheet.xlsx) — 2026-08-19 Kero Merox reading (11.2 ppm) exceeds the 10 ppm limit. Tests the compliance-checker's `EXCEEDANCE` flag.
3. **CCR-1 regeneration cycle duration drift** (Inspection_Report_CCR1_Regeneration_Cycle.pdf) — two consecutive cycles (31, 34 hrs) exceed the 28-hour target, cross-referenced with a root-cause narrative. Tests multi-document reasoning (report → recommendation → checklist cross-reference).
4. **Novolen off-spec batch** (Novolen_Batch_QA_Report_Aug2026.pdf) — Batch H110F-0847 exceeds MFI spec, with a named root cause (catalyst feed rate excursion). Tests fact extraction with a specific numeric exceedance.
5. **Cross-document link**: the CCR-1 inspection report (Doc 02) references Form F-140-A, and the scanned checklist image (Doc 06) *is* that form for the same cycle — same cycle number, same date, consistent findings. Tests whether OCR + retrieval correctly link a scanned form to its corresponding typed report.
6. **Graph-shaped query target**: Pipeline_Incident_Report_Hassan_Segment.pdf explicitly names `PipelineSegment: Mangalore-Hassan` and `Equipment: P-HS-02`, matching GRAPH_SPEC.md's schema exactly — use this to test the signature graph query end-to-end.

## Suggested RAG Accuracy Test Set (question / expected answer / expected source)

| # | Question | Expected Answer (approx.) | Expected Source Document |
|---|---|---|---|
| 1 | What is the WABT end-of-run trigger temperature for HCU-2? | > 410 °C | SOP-114-Rev3 |
| 2 | What caused the off-spec batch H110F-0847? | Catalyst feed rate excursion during grade changeover, ~40 min before DCS alarm response | Novolen_Batch_QA_Report_Aug2026.pdf |
| 3 | What is the 8-hour TWA benzene exposure limit at the Aromatic Complex? | 1 ppm | Aromatic_Complex_Benzene_Safety_Circular.docx |
| 4 | Why was Tank TK-K-03 at Kasargod held out of service? | 0.6% calibration variance exceeding the 0.3% internal tolerance | Correspondence_Depot_HQ_Thread_Kasargod.docx |
| 5 | What was the root cause of the Hassan pumping station incident on 2026-07-22? | Minor seal leak at pump P-HS-02 discharge flange | Pipeline_Incident_Report_Hassan_Segment.pdf |
| 6 | Did any PSA unit fall below its purity target in the last reporting period? | Yes, PSA-3, in the final 3 weeks of the log | PSA_Hydrogen_Purity_Trend_Log.xlsx |
| 7 | Which Kero Merox sample exceeded the sulphur spec limit? | 2026-08-19, 11.2 ppm vs 10 ppm limit | Sulphur_Spec_Compliance_LabSheet.xlsx |
| 8 | Which vendor supplies both the hydrocracker catalyst and the Ziegler-Natta catalyst component? | VEND-1042 | SAP_Mock_Materials_Master_Export.xlsx |
| 9 (out-of-corpus, expects refusal) | What is MRPL's crude oil sourcing strategy for 2027? | Not found in the provided corpus — this question should trigger the confidence-threshold refusal (RAG_SPEC.md §3), since nothing in this corpus addresses it | None — negative test case |
| 10 (graph query) | Show every document referencing the Mangalore-Hassan pipeline segment | Pipeline_Incident_Report_Hassan_Segment.pdf (and Pipeline_Segment_Map diagram if diagram-text extraction is wired in) | Graph query, not plain retrieval |

Use Q9 specifically to verify the "refuse to hallucinate" behavior actually works — it's the one question in this set with no answer anywhere in the corpus.

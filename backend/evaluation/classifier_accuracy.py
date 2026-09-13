"""Measure the document classifier against the corpus's own folders.

TOOLS.md row 9 claims the classifier "routes scans to the correct
pipeline". That claim is checkable, because MRPL_RAG_Test_Corpus/ is
already organised by document kind -- the folder names ARE labels, and
they were written before this classifier existed, so they cannot have
been fitted to it.

Run: py -3 -m backend.evaluation.classifier_accuracy
"""

from __future__ import annotations

from pathlib import Path

from backend.ingestion.document_classifier import classify_document

CORPUS = Path(__file__).resolve().parents[2] / "MRPL_RAG_Test_Corpus"

# The folder each class should win in. 07_User_Uploads is deliberately
# excluded: it is a mixed inbox with no single correct answer, which is
# what it exists to represent.
FOLDER_TO_KIND = {
    "01_SOPs_and_Procedures": "sop_procedure",
    "02_Inspection_and_Maintenance": {"inspection_report", "maintenance_log"},
    "03_Quality_and_Process_Data": "lab_quality_data",
    "04_SAP_Mock_Exports": "sap_export",
    "05_Correspondence": "correspondence",
    "06_Diagrams_and_Scans": {"diagram_schematic", "scanned_form"},
}


def _text_of(path: Path) -> str:
    """Whatever text this file yields.

    The first version of this helper swallowed every exception and
    returned "", which made the classifier score 1/13 and blamed the
    classifier. The extraction was never running: it called
    extract_text(), which does not exist -- the entry point is
    extract_pages(file_path, detected_type). A harness that hides its
    own failure and reports the result as a property of the thing under
    test is this repository's most repeated bug, now six times.

    So failures are PRINTED and the row is scored as no-text, which is
    a different and visible outcome.
    """
    from backend.ingestion.document_types import detect_document_type
    from backend.ingestion.text_extraction import extract_pages

    try:
        detected = detect_document_type(str(path))
        pages = extract_pages(str(path), detected.detected_type)
        return "\n".join(getattr(p, "text", "") or "" for p in pages)
    except Exception as exc:  # noqa: BLE001
        print(f"    ! extraction failed for {path.name}: {type(exc).__name__}: {exc}")
        return ""


def main() -> None:
    if not CORPUS.exists():
        print(f"No corpus at {CORPUS}")
        return

    total = correct = 0
    rows = []
    for folder, expected in FOLDER_TO_KIND.items():
        directory = CORPUS / folder
        if not directory.exists():
            continue
        allowed = expected if isinstance(expected, set) else {expected}
        for path in sorted(directory.iterdir()):
            if path.is_dir() or path.name.startswith("."):
                continue
            result = classify_document(_text_of(path), path.name)
            hit = result.kind in allowed
            total += 1
            correct += hit
            rows.append((
                "OK " if hit else "MISS",
                path.name[:46],
                result.kind,
                result.confidence,
                "|".join(sorted(allowed)),
                ", ".join(result.evidence[:2]),
            ))

    width = max((len(r[1]) for r in rows), default=10)
    print(f"{'':4}  {'file':<{width}}  {'predicted':<18} {'conf':>5}  expected")
    print("-" * (width + 62))
    for status, name, kind, confidence, allowed, why in rows:
        print(f"{status}  {name:<{width}}  {kind:<18} {confidence:>5}  {allowed}")
        if status == "MISS":
            print(f"{'':4}  {'':<{width}}  evidence: {why}")

    if total:
        print()
        print(f"{correct}/{total} correct ({100 * correct / total:.0f}%)")


if __name__ == "__main__":
    main()

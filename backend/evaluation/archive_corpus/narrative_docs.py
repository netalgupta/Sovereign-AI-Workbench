"""LLM-authored narrative documents: SOPs, reports, correspondence.

RESUMABLE, THE SAME WAY extract_corpus.py IS, AND FOR THE SAME REASON.
Each document costs one real model call -- measured elsewhere in this
repo at 10-25s depending on length -- so a run of a hundred documents is
tens of minutes. A crash, a Ctrl-C, or an Ollama restart partway through
must not mean starting over. A manifest (.manifest.json in the output
root) records every completed document by its deterministic id, and
generate_batch() skips anything already in it.

WHY THE PROMPT IS BUILT FROM A SPEC OBJECT, NOT FREE TEXT. Every
document names a real unit, a real equipment tag and a real person from
vocab.py, and the prompt states them explicitly rather than letting the
model invent them -- an invented tag is a graph node that connects to
nothing. The model's job is prose GIVEN these facts, not invention of
the facts themselves. This is the same discipline RAG_SPEC §4 uses for
answering questions: the facts come from outside the model, the model's
job is expression.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import vocab

# A DOTFILE so ingestion skips it. As "manifest.json" it was indexed as
# 66 chunks of doc ids and statuses -- generator bookkeeping mixed into
# retrieval results as though it were a refinery document.
MANIFEST_NAME = ".manifest.json"
LEGACY_MANIFEST_NAME = "manifest.json"


@dataclass
class DocSpec:
    """What a document must be about. The model writes prose FROM this;
    it does not choose any of it."""

    category: str  # "sop" | "inspection" | "incident" | "correspondence" | "board_review"
    doc_id: str
    year: int
    unit: str
    subfolder: str
    filename: str
    extra: dict = field(default_factory=dict)


def _doc_id(category: str, year: int, unit: str, seq: int) -> str:
    raw = f"{category}::{year}::{unit}::{seq}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


# ---------------------------------------------------------------- plans

def plan_sops(n: int) -> list[DocSpec]:
    """One SOP-style document per unit per selected year -- procedures
    change less often than incidents happen, so these are sparser."""
    specs = []
    seq = 0
    topics = [
        "Catalyst Changeout Procedure", "Startup and Shutdown Sequence",
        "Emergency Isolation Procedure", "Grade Changeover Checklist",
        "Confined Space Entry Procedure", "Regeneration Cycle Procedure",
    ]
    for year in vocab.YEARS:
        for unit in vocab.UNITS:
            if seq >= n:
                return specs
            topic = topics[seq % len(topics)]
            doc_id = _doc_id("sop", year, unit, seq)
            fname = f"SOP-{100 + seq}-Rev{1 + (seq % 3)}_{_slug(unit)}_{_slug(topic)}.docx"
            specs.append(DocSpec(
                "sop", doc_id, year, unit, "01_SOPs_and_Procedures", fname,
                extra={"topic": topic, "sop_number": f"SOP-{100 + seq}", "revision": 1 + (seq % 3)},
            ))
            seq += 1
    return specs


def plan_inspection_reports(n: int) -> list[DocSpec]:
    specs = []
    seq = 0
    for year in vocab.YEARS:
        for unit in vocab.UNITS:
            if seq >= n:
                return specs
            equip = vocab.EQUIPMENT[seq % len(vocab.EQUIPMENT)]
            doc_id = _doc_id("inspection", year, unit, seq)
            cycle = 1 + (seq % 24)
            fname = f"Inspection_Report_{_slug(unit)}_Cycle{cycle}_{year}.pdf"
            specs.append(DocSpec(
                "inspection", doc_id, year, unit, "02_Inspection_and_Maintenance", fname,
                extra={"equipment": equip, "cycle": cycle, "report_no": f"IR-{_slug(unit)}-{year}-{cycle:03d}"},
            ))
            seq += 1
    return specs


def plan_incident_reports(n: int) -> list[DocSpec]:
    specs = []
    seq = 0
    for year in vocab.YEARS:
        for unit in vocab.UNITS:
            if seq >= n:
                return specs
            kind = vocab.INCIDENT_KINDS[seq % len(vocab.INCIDENT_KINDS)]
            equip = vocab.EQUIPMENT[(seq * 2) % len(vocab.EQUIPMENT)]
            doc_id = _doc_id("incident", year, unit, seq)
            fname = f"Incident_Report_{_slug(unit)}_{_slug(kind)[:30]}_{year}.pdf"
            specs.append(DocSpec(
                "incident", doc_id, year, unit, "02_Inspection_and_Maintenance", fname,
                extra={"kind": kind, "equipment": equip, "report_no": f"IN-{_slug(unit)}-{year}-{seq:03d}"},
            ))
            seq += 1
    return specs


def plan_correspondence(n: int) -> list[DocSpec]:
    """year x depot alone is only 21 combinations (7 x 3) -- fewer than
    any real request. Subjects cycle WITHIN each (year, depot) pair
    (round k reuses the same 6 subjects with a different cycle offset)
    so a depot can legitimately have multiple threads in the same year,
    which is realistic anyway -- a depot writes to HQ about more than
    one thing per year.

    doc_id is keyed on (year, depot, round, subject) rather than a flat
    incrementing seq, so raising `n` on a later run adds NEW specs
    without changing the id -- and therefore the manifest hit -- of any
    spec already generated.
    """
    subjects = [
        "Tank Calibration Discrepancy", "Delivery Schedule Confirmation",
        "Quality Certificate Request", "Storage Allocation Update",
        "HSE Compliance Query", "Invoice Reconciliation",
    ]
    combos = [(year, depot) for year in vocab.YEARS for depot in vocab.DEPOTS]

    specs = []
    produced = 0
    round_no = 0
    while produced < n:
        for year, depot in combos:
            if produced >= n:
                break
            subject = subjects[(round_no + combos.index((year, depot))) % len(subjects)]
            key = f"{year}::{depot}::{round_no}::{subject}"
            doc_id = _doc_id("correspondence", year, f"{depot}-r{round_no}", hash(key) & 0xFFFF)
            suffix = f"_r{round_no}" if round_no else ""
            fname = f"Correspondence_{depot}_HQ_{_slug(subject)}_{year}{suffix}.docx"
            specs.append(DocSpec(
                "correspondence", doc_id, year, depot, "05_Correspondence", fname,
                extra={
                    "depot": depot, "subject": subject,
                    "thread_id": f"CORR-{depot[:3].upper()}-{year}-{round_no:02d}{combos.index((year, depot)):03d}",
                },
            ))
            produced += 1
        round_no += 1
        if round_no > 20:  # safety valve, not a realistic n
            break
    return specs


def plan_board_reviews(n: int) -> list[DocSpec]:
    specs = []
    seq = 0
    for year in vocab.YEARS:
        for quarter in ("Q1", "Q2", "Q3", "Q4"):
            if seq >= n:
                return specs
            doc_id = _doc_id("board_review", year, quarter, seq)
            fname = f"Board_Review_{quarter}_{year}.docx"
            specs.append(DocSpec(
                "board_review", doc_id, year, "Refinery-wide", "06_Board_and_Quarterly_Reviews", fname,
                extra={"quarter": quarter},
            ))
            seq += 1
    return specs


# --------------------------------------------------------------- prompts

def _prompt_for(spec: DocSpec) -> str:
    disclaimer = vocab.synthetic_disclaimer()
    person, role = vocab.PERSONNEL[hash(spec.doc_id) % len(vocab.PERSONNEL)]

    if spec.category == "sop":
        return (
            f"Write a Standard Operating Procedure document for an oil refinery.\n"
            f"Document number: {spec.extra['sop_number']}, Revision {spec.extra['revision']}.\n"
            f"Unit: {spec.unit}. Topic: {spec.extra['topic']}. Year issued: {spec.year}.\n"
            f"Include: 1) Scope and Purpose, 2) Precautions, 3) Numbered procedure steps "
            f"(at least 6), 4) Reference documents.\n"
            f"Use plain, technical, procedural language. No markdown headers with #, use "
            f"plain text section titles. Around 350-450 words.\n"
            f"End with exactly this line: {disclaimer}"
        )
    if spec.category == "inspection":
        return (
            f"Write an Inspection Report for an oil refinery.\n"
            f"Report No: {spec.extra['report_no']}. Unit: {spec.unit}. "
            f"Equipment: {spec.extra['equipment']}. Cycle No: {spec.extra['cycle']}. Year: {spec.year}.\n"
            f"Inspected by: {person} ({role}).\n"
            f"Include: 1) Background, 2) Observations (3-5 specific findings with realistic "
            f"technical detail), 3) Root Cause (if applicable), 4) Recommendations, "
            f"5) Sign-off.\n"
            f"Plain technical language, no markdown. Around 300-400 words.\n"
            f"End with exactly this line: {disclaimer}"
        )
    if spec.category == "incident":
        return (
            f"Write an Incident Report for an oil refinery.\n"
            f"Report No: {spec.extra['report_no']}. Unit: {spec.unit}. "
            f"Equipment involved: {spec.extra['equipment']}. Year: {spec.year}.\n"
            f"Incident type: {spec.extra['kind']}.\n"
            f"Investigated by: {person} ({role}).\n"
            f"Include: 1) Summary of the incident, 2) Timeline, 3) Root cause analysis, "
            f"4) Corrective actions with owners, 5) Lessons learned.\n"
            f"Plain technical language, no markdown. Around 350-450 words. Be specific and "
            f"realistic but this is SYNTHETIC test data, not a real event.\n"
            f"End with exactly this line: {disclaimer}"
        )
    if spec.category == "correspondence":
        return (
            f"Write a short internal email correspondence thread (2-3 messages) between "
            f"the {spec.extra['depot']} Depot and MRPL HQ.\n"
            f"Thread ID: {spec.extra['thread_id']}. Subject: {spec.extra['subject']}. Year: {spec.year}.\n"
            f"Format each message with From/To/Date/Subject headers then the message body. "
            f"Business-appropriate tone, refinery/depot operational context (tank storage, "
            f"deliveries, quality certificates, or compliance -- pick what fits the subject).\n"
            f"Plain text, no markdown. Around 250-350 words total.\n"
            f"End with exactly this line: {disclaimer}"
        )
    if spec.category == "board_review":
        return (
            f"Write a Quarterly Operations Review memo for MRPL refinery leadership.\n"
            f"Period: {spec.extra['quarter']} {spec.year}.\n"
            f"Include: 1) Production summary (qualitative, reference 2-3 units by name from: "
            f"{', '.join(vocab.UNITS[:5])}), 2) Safety performance summary, 3) Key maintenance "
            f"activities, 4) Outlook for next quarter.\n"
            f"Formal business memo tone, plain text, no markdown. Around 300-400 words.\n"
            f"End with exactly this line: {disclaimer}"
        )
    raise ValueError(f"unknown category: {spec.category}")


# ------------------------------------------------------------------ write

def _split_bold(line: str) -> list[tuple[str, bool]]:
    """Split "**word** rest" style markdown into (text, is_bold) runs.

    Asked the model for "no markdown" and it uses **bold** anyway --
    every model tested does. Rather than leave literal asterisk pairs
    sitting in extracted text (which a reader sees, and which a naive
    keyword search would need to match around), the markers are parsed
    into real bold formatting and removed from the text.
    """
    parts: list[tuple[str, bool]] = []
    for chunk in re.split(r"(\*\*[^*]+\*\*)", line):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**") and len(chunk) > 4:
            parts.append((chunk[2:-2], True))
        else:
            parts.append((chunk, False))
    return parts or [(line, False)]


def _write_docx(text: str, spec: DocSpec, out_path: Path) -> None:
    import docx

    doc = docx.Document()
    title = out_path.stem.replace("_", " ")
    doc.add_heading(title, level=1)
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        p = doc.add_paragraph()
        for run_text, bold in _split_bold(para):
            if run_text:
                p.add_run(run_text).bold = bold
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


def _write_pdf(text: str, spec: DocSpec, out_path: Path) -> None:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    title = out_path.stem.replace("_", " ")
    pdf.multi_cell(0, 8, title)
    pdf.ln(2)
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        for run_text, bold in _split_bold(para):
            if not run_text:
                continue
            # fpdf2's multi_cell chokes on characters outside latin-1;
            # the model output is expected to be plain ASCII/technical
            # English, but degrade gracefully rather than crash a whole
            # batch over one smart-quote.
            safe = run_text.encode("latin-1", "replace").decode("latin-1")
            pdf.set_font("Helvetica", "B" if bold else "", 11)
            pdf.write(6, safe)
        pdf.ln(7)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))


_WRITER = {".docx": _write_docx, ".pdf": _write_pdf}


# --------------------------------------------------------------- runner

def _load_manifest(root: Path) -> dict:
    path = root / MANIFEST_NAME
    legacy = root / LEGACY_MANIFEST_NAME
    if not path.exists() and legacy.exists():
        legacy.rename(path)  # keep resuming a run started before the rename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_manifest(root: Path, manifest: dict) -> None:
    (root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def generate_batch(
    specs: list[DocSpec],
    root: Path,
    model_id: str = "reasoning-model",
    verbose: bool = True,
    progress_every: int = 5,
) -> dict:
    """Generate every spec not already in the manifest. Resumable.

    Returns {"generated": int, "skipped": int, "failed": list[doc_id]}.
    """
    from backend.models.ollama_client import generate as ollama_generate
    from backend.models.registry import resolve_model_name

    root.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(root)
    model_name = resolve_model_name(model_id)

    generated = 0
    skipped = 0
    failed: list[str] = []

    for i, spec in enumerate(specs):
        if spec.doc_id in manifest and manifest[spec.doc_id].get("status") == "done":
            skipped += 1
            continue

        out_path = root / spec.subfolder / spec.filename
        writer = _WRITER.get(out_path.suffix)
        if writer is None:
            failed.append(spec.doc_id)
            continue

        try:
            prompt = _prompt_for(spec)
            text = ollama_generate(model_name, prompt, timeout=180)
            writer(text, spec, out_path)
            manifest[spec.doc_id] = {
                "status": "done", "category": spec.category, "year": spec.year,
                "unit": spec.unit, "filename": str(out_path.relative_to(root)),
            }
            generated += 1
        except Exception as exc:  # noqa: BLE001
            manifest[spec.doc_id] = {"status": "failed", "error": str(exc)[:200]}
            failed.append(spec.doc_id)

        # Checkpoint after EVERY document, not at the end -- a crash on
        # document 80 of 100 must not cost the first 79.
        _save_manifest(root, manifest)

        if verbose and (i + 1) % progress_every == 0:
            print(f"  [{i + 1}/{len(specs)}] generated={generated} skipped={skipped} failed={len(failed)}")

    return {"generated": generated, "skipped": skipped, "failed": failed}

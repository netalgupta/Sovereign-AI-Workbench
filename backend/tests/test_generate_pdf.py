"""Tests for PDF generation tool and outputs endpoint.

TOOLS.md row 40a / FRONTEND.md §3.7 / Kanishka.md.
Proves:
1. generate_pdf produces a valid PDF file on disk with PyMuPDF.
2. Multi-section PDF structure with headings, text, and citations renders correctly.
3. Unsourced sections carry an explicit [UNSOURCED] warning.
4. describe_effect produces accurate plain-language summaries for the approval gate.
5. Output path safety: non-.pdf extensions are rejected.
6. Approval gate integration: requires_approval flag is active.
7. /api/outputs lists generated files.
8. /api/outputs/{filename}/download allows downloading with path safety.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tools.documents.generate_pdf import generate_pdf, describe_effect
from backend.tools.registry import get_tool


@pytest.fixture
def client():
    return TestClient(app)


def test_generate_pdf_creates_valid_file(tmp_path):
    out_path = str(tmp_path / "test_report.pdf")
    sections = [
        {
            "heading": "1. Executive Overview",
            "body": "This is an overview of the hydrocracker unit operation under high pressure.",
            "sources": ["MRPL_RAG_Test_Corpus/01_SOPs_and_Procedures/SOP_HCU2.md"],
            "contains_estimate": False,
        },
        {
            "heading": "2. Unsourced Observation",
            "body": "General operator comment without manual backing.",
            "sources": [],
            "contains_estimate": False,
        },
    ]

    result = generate_pdf(
        title="MRPL Hydrocracker Unit 2 Performance",
        sections=sections,
        output_path=out_path,
    )

    assert result["file_path"] == out_path
    assert result["section_count"] == 2
    assert result["total_sources"] == 1
    assert result["unsourced_sections"] == ["2. Unsourced Observation"]
    assert Path(out_path).exists()
    assert Path(out_path).stat().st_size > 500

    # Verify readable with PyMuPDF
    import fitz
    doc = fitz.open(out_path)
    assert len(doc) >= 1
    page_text = doc[0].get_text()
    assert "MRPL Hydrocracker Unit 2 Performance" in page_text
    assert "UNSOURCED" in page_text
    doc.close()


def test_generate_pdf_refuses_non_pdf_extension(tmp_path):
    out_path = str(tmp_path / "report.docx")
    with pytest.raises(ValueError, match=r"Output path must end in \.pdf"):
        generate_pdf(
            title="Invalid Extension",
            sections=[{"heading": "Test", "body": "Body", "sources": []}],
            output_path=out_path,
        )


def test_describe_effect_returns_plain_language_summary():
    sections = [
        {
            "heading": "Safe Section",
            "body": "Sourced fact",
            "sources": ["SOP.md"],
            "contains_estimate": False,
        },
        {
            "heading": "Unverified Guess",
            "body": "No citation",
            "sources": [],
            "contains_estimate": True,
        },
    ]
    summary = describe_effect("Safety Audit", sections, "storage/outputs/audit.pdf")
    assert 'Create the PDF report "Safety Audit"' in summary
    assert "2 section(s)" in summary
    assert "WARNING: 1 section(s) have NO sources: Unverified Guess" in summary
    assert "WARNING: contains at least one vision-model ESTIMATE" in summary


def test_generate_pdf_approval_gate_integration():
    tool_entry = get_tool("generate_pdf")
    assert tool_entry is not None, "generate_pdf must be registered in the catalog"
    assert tool_entry.requires_approval is True, "Hard constraint #4: file writing must require approval"
    assert tool_entry.category == "documents"


def test_api_outputs_endpoints(client, tmp_path):
    # Ensure storage/outputs directory has at least one file
    out_dir = Path("storage/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    test_file = out_dir / "api_test_doc.docx"
    test_file.write_text("dummy test doc content", encoding="utf-8")

    res = client.get("/api/outputs")
    assert res.status_code == 200
    data = res.json()
    assert "files" in data
    assert "count" in data
    assert data["count"] > 0
    assert any(f["filename"] == "api_test_doc.docx" for f in data["files"])

    # Download endpoint
    dl_res = client.get("/api/outputs/api_test_doc.docx/download")
    assert dl_res.status_code == 200
    assert dl_res.content == b"dummy test doc content"

    # Directory traversal prevention
    bad_res = client.get("/api/outputs/..%2f..%2fsecrets.txt/download")
    assert bad_res.status_code in [400, 404]

    # Clean up test file
    test_file.unlink(missing_ok=True)

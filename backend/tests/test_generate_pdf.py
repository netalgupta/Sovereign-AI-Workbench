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


def test_the_page_count_is_the_document_s_real_length(tmp_path):
    """It was read after close() and so was always 1: an 8-page report was
    recorded as one page on the approval card and in the audit log."""
    import fitz

    from backend.tools.documents.generate_pdf import generate_pdf

    long_body = ("This paragraph exists to fill the page with enough text that the document "
                 "must run past a single side of A4 and into the next. ") * 30
    out = generate_pdf(
        title="A long report",
        sections=[{"heading": f"Section {i}", "body": long_body, "sources": ["S.pdf"]} for i in range(4)],
        output_path=str(tmp_path / "long.pdf"),
    )
    assert out["page_count"] == fitz.open(str(tmp_path / "long.pdf")).page_count
    assert out["page_count"] > 1


def test_whose_name_is_on_the_file_is_configurable(tmp_path, monkeypatch):
    """The header marks who produced the deliverable, not what it is about:
    a summary of a cyber security textbook carried a refinery's name."""
    import fitz

    from backend.tools.documents.generate_pdf import generate_pdf

    monkeypatch.setenv("WORKBENCH_ORG", "Acme")
    generate_pdf(title="A report", sections=[{"heading": "One", "body": "Body.", "sources": ["S"]}],
                 output_path=str(tmp_path / "o.pdf"))
    assert "Acme Sovereign" in fitz.open(str(tmp_path / "o.pdf"))[0].get_text()


def test_a_section_longer_than_a_page_is_not_truncated(tmp_path):
    """The first version wrote NOTHING for text that did not fit the space
    left, retried on one fresh page, and so silently cut any section longer
    than a page — which a book chapter always is."""
    import fitz

    from backend.tools.documents.generate_pdf import generate_pdf

    paragraphs = [f"Paragraph {i} explains a distinct idea in enough words to take up real "
                  f"space on the page, so that the section must run across several pages. "
                  f"MARKER{i}END." for i in range(60)]
    out = generate_pdf(title="Long", sections=[{"heading": "One long chapter", "body": "\n\n".join(paragraphs),
                                                "sources": ["Book.pdf"]}],
                       output_path=str(tmp_path / "long.pdf"))
    text = "".join(page.get_text() for page in fitz.open(str(tmp_path / "long.pdf")))
    missing = [i for i in range(60) if f"MARKER{i}END" not in text]
    assert not missing, f"paragraphs lost: {missing[:5]}"
    assert out["page_count"] >= 3


def test_dashes_and_quotes_survive(tmp_path):
    """The built-in font printed an em dash as "?"."""
    import fitz

    from backend.tools.documents.generate_pdf import generate_pdf

    generate_pdf(title="Dashes — and ‘quotes’", sections=[{"heading": "A", "body": "Before — after “quoted”.",
                                                          "sources": ["S"]}],
                 output_path=str(tmp_path / "d.pdf"))
    text = fitz.open(str(tmp_path / "d.pdf"))[0].get_text()
    assert "—" in text and "“quoted”" in text


def test_a_shared_source_is_named_once_not_after_every_section(tmp_path):
    import fitz

    from backend.tools.documents.generate_pdf import generate_pdf

    generate_pdf(title="Book", sections=[{"heading": f"Chapter {i}", "body": "Text.", "sources": ["The Book.pdf"],
                                          "note": f"Pages {i}0-{i}9 of the source"} for i in range(1, 6)],
                 output_path=str(tmp_path / "b.pdf"))
    text = "".join(p.get_text() for p in fitz.open(str(tmp_path / "b.pdf")))
    assert text.count("The Book.pdf") == 1
    assert "Pages 30-39 of the source" in text
    assert "Contents" in text

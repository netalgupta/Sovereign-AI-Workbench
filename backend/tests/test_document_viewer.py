"""The Sources document viewer, bug by bug (reported by Advay, 27 Sep).

Measured before the fix:
  - a 593-page book: MemoryLimitExceeded; reopened, "ready" with 50 pages
    (the dead run's leftovers were served as the whole book)
  - every file in a source outside the repo: 403 from /api/sources/content
  - `path=<anything>/<name>`: the first repo file with that name, logs included
  - a DOCX: tables dropped; "<" or "&" in the text failed the conversion
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.api import source_config
from backend.main import app

client = TestClient(app)


def _add_source(path):
    source_config.save([{"id": "t", "name": path.name, "path": str(path), "enabled": True}])


def _render(file_path: str, timeout: float = 60) -> dict:
    res = client.post("/api/sandbox/render", json={"file_path": file_path})
    assert res.status_code == 200, res.text
    job_id = res.json()["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/sandbox/render/{job_id}").json()
        if job["status"] in ("ready", "failed"):
            return job
        time.sleep(0.2)
    raise AssertionError("render did not finish")


@pytest.fixture
def pdf_source(tmp_path):
    fitz = pytest.importorskip("fitz")
    folder = tmp_path / "outside_repo_source"
    folder.mkdir()
    doc = fitz.open()
    for n in range(1, 41):
        doc.new_page().insert_text((72, 72), f"Page marker {n}")
    pdf = folder / "long_manual.pdf"
    doc.save(str(pdf))
    _add_source(folder)
    return pdf


def test_a_long_pdf_renders_its_first_pages_now_and_the_rest_on_demand(pdf_source):
    job = _render(str(pdf_source))
    assert job["status"] == "ready", job
    assert job["page_count"] == 40
    from backend.sandbox.render import get_render_manager
    target = get_render_manager()._dir_for(job["attachment_id"])
    assert len(list(target.glob("page_*.jpg"))) < 40  # not the whole book up front

    page = client.get(f"{job['preview_url']}?page=33")
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/jpeg"
    assert client.get(f"{job['preview_url']}?page=41").status_code == 404


def test_a_partial_render_is_never_served_as_the_document(pdf_source):
    job = _render(str(pdf_source))
    from backend.sandbox.render import MANIFEST, get_render_manager
    target = get_render_manager()._dir_for(job["attachment_id"])
    (target / MANIFEST).unlink()  # what a render killed half-way leaves: pages, no manifest
    again = _render(str(pdf_source))
    assert again["status"] == "ready" and again["page_count"] == 40


def test_an_edited_file_is_rendered_again(pdf_source):
    fitz = pytest.importorskip("fitz")
    assert _render(str(pdf_source))["page_count"] == 40
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_source))
    assert _render(str(pdf_source))["page_count"] == 1


def test_files_in_a_source_outside_the_repo_open(pdf_source):
    res = client.get("/api/sources/content", params={"path": str(pdf_source)})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    # a bare name, as a citation carries it, is found inside the sources
    assert client.get("/api/sources/content", params={"path": "long_manual.pdf"}).status_code == 200


def test_a_repo_file_outside_every_source_is_not_served(pdf_source):
    assert client.get("/api/sources/content", params={"path": "models/models.yaml"}).status_code == 404
    assert client.get("/api/sources/content", params={"path": "anything/models.yaml"}).status_code == 404
    assert client.post("/api/sandbox/render", json={"file_path": "backend/main.py"}).status_code == 400


def test_docx_keeps_tables_and_survives_markup_characters(tmp_path):
    docx = pytest.importorskip("docx")
    fitz = pytest.importorskip("fitz")
    folder = tmp_path / "docs_source"
    folder.mkdir()
    d = docx.Document()
    d.add_heading("Catalyst changeout", level=1)
    d.add_paragraph("H2 purity < 99.5% & R&D sign-off <required>")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Tag", "Limit"
    t.cell(1, 0).text, t.cell(1, 1).text = "TI-4471", "385 degC"
    path = folder / "sop.docx"
    d.save(str(path))
    _add_source(folder)

    job = _render(str(path))
    assert job["status"] == "ready", job
    from backend.sandbox.render import get_render_manager
    target = get_render_manager()._dir_for(job["attachment_id"])
    text = "".join(p.get_text() for p in fitz.open(str(target / "rendered.pdf")))
    assert "TI-4471" in text and "385 degC" in text
    assert "H2 purity < 99.5% & R&D" in text


def test_a_generated_deliverable_opens_from_the_artifacts_tab():
    """Screenshot, 27 Sep: Artifacts -> Open on an .xlsx -> 'HTTP 404: Failed
    to fetch XLSX document', after the viewer was limited to the sources."""
    from backend.paths import OUTPUT_DIR

    OUTPUT_DIR.mkdir(exist_ok=True)
    f = OUTPUT_DIR / "zz_viewer_test_deliverable.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    try:
        for path in ("outputs/zz_viewer_test_deliverable.csv", str(f), "zz_viewer_test_deliverable.csv"):
            assert client.get("/api/sources/content", params={"path": path}).status_code == 200, path
    finally:
        f.unlink()

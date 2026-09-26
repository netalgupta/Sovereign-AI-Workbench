"""
backend/tests/test_sandbox_step3.py

Automated test suite for Step 3: Secure Sandbox — Office Document Rendering.

Tests every acceptance criterion:
1. Real .docx file rendering to PDF/PNG without errors.
2. Real .xlsx file rendering with multiple sheet support.
3. Real .pptx file rendering with slide viewability.
4. Step 1 Read-Guard enforcement (unready / non-existent attachment rejected with HTTP 400).
5. Corrupt / malformed office document handling (fails cleanly in sandbox without hanging host).
6. Permanent vs. Temporary preview lifecycle (temp previews deleted on cleanup, perm previews persist).
7. Concurrent document render isolation.
"""

import concurrent.futures
import io
import time
import pytest
import docx
import openpyxl
import pptx
from fastapi.testclient import TestClient

from backend.main import app
from backend.sandbox.render import get_render_manager

client = TestClient(app)


def upload_and_wait_ready(filename: str, file_bytes: bytes, category: str = "temporary") -> str:
    """Helper to upload file via Step 1 API and wait until status is 'ready'."""
    files = {"file": (filename, file_bytes, "application/octet-stream")}
    data = {"category": category, "session_id": "step3_test_session"}
    resp = client.post("/api/attachments/upload", files=files, data=data)
    assert resp.status_code == 200, f"Upload failed for {filename}: {resp.text}"
    att_id = resp.json()["attachment_id"]

    # Poll until ready
    for _ in range(30):
        get_resp = client.get(f"/api/attachments/{att_id}")
        assert get_resp.status_code == 200
        if get_resp.json().get("status") == "ready":
            return att_id
        time.sleep(0.1)
    pytest.fail(f"Attachment {att_id} did not reach ready status")


def poll_render_job(job_id: str, timeout_max: float = 20.0) -> dict:
    start_t = time.time()
    while time.time() - start_t < timeout_max:
        resp = client.get(f"/api/sandbox/render/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("ready", "failed"):
            return data
        time.sleep(0.1)
    pytest.fail(f"Render job {job_id} did not complete within {timeout_max}s")


# --- Helper File Generators ---

def create_sample_docx_bytes() -> bytes:
    doc = docx.Document()
    doc.add_heading("Sovereign Workbench SOP Manual", 0)
    doc.add_paragraph("This is a verified test document for Step 3 Office Document Rendering.")
    doc.add_paragraph("Section 1.1: Security Interlocks & Zero Network Egress.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_sample_xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Refinery Inspection"
    ws1.append(["Unit ID", "Temperature (C)", "Pressure (bar)", "Status"])
    ws1.append(["Tower-101", 342.5, 14.2, "Normal"])
    ws1.append(["Tower-102", 410.0, 18.7, "Warning"])

    ws2 = wb.create_sheet(title="Maintenance Log")
    ws2.append(["Date", "Technician", "Task"])
    ws2.append(["2026-09-12", "Kanishka", "Valve Calibration"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def create_sample_pptx_bytes() -> bytes:
    prs = pptx.Presentation()
    blank_slide_layout = prs.slide_layouts[6]
    
    slide1 = prs.slides.add_slide(blank_slide_layout)
    txBox = slide1.shapes.add_textbox(100, 100, 400, 200)
    tf = txBox.text_frame
    tf.text = "Slide 1: Executive Overview"

    slide2 = prs.slides.add_slide(blank_slide_layout)
    txBox2 = slide2.shapes.add_textbox(100, 100, 400, 200)
    tf2 = txBox2.text_frame
    tf2.text = "Slide 2: Architectural Details & Verification"

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# --- Tests ---

def test_criterion_1_docx_rendering():
    """Criterion 1: Real .docx file renders to PDF/PNG without errors."""
    file_bytes = create_sample_docx_bytes()
    att_id = upload_and_wait_ready("test_doc.docx", file_bytes, category="temporary")

    resp = client.post("/api/sandbox/render", json={"attachment_id": att_id})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_render_job(job_id)
    assert job["status"] == "ready"
    assert job["page_count"] >= 1
    assert job["preview_url"] == f"/api/sandbox/render/preview/{att_id}"

    # Verify preview image HTTP endpoint returns 200 OK image
    prev_resp = client.get(f"/api/sandbox/render/preview/{att_id}?page=1")
    assert prev_resp.status_code == 200
    assert prev_resp.headers["content-type"] in ("image/png", "application/pdf")
    assert len(prev_resp.content) > 100


def test_criterion_2_xlsx_rendering():
    """Criterion 2: Real .xlsx file renders correctly including multiple sheets."""
    file_bytes = create_sample_xlsx_bytes()
    att_id = upload_and_wait_ready("test_sheet.xlsx", file_bytes, category="temporary")

    resp = client.post("/api/sandbox/render", json={"attachment_id": att_id})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_render_job(job_id)
    assert job["status"] == "ready"
    assert job["page_count"] == 2  # 2 sheets in Excel workbook


def test_criterion_3_pptx_rendering():
    """Criterion 3: Real .pptx file renders correctly with viewable slides."""
    file_bytes = create_sample_pptx_bytes()
    att_id = upload_and_wait_ready("test_presentation.pptx", file_bytes, category="temporary")

    resp = client.post("/api/sandbox/render", json={"attachment_id": att_id})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_render_job(job_id)
    assert job["status"] == "ready", f"PPTX render failed: {job.get('error')}"
    assert job["page_count"] == 2  # 2 slides in PowerPoint presentation


def test_criterion_4_read_guard_enforcement():
    """Criterion 4: Attempting to render an attachment NOT yet 'ready' or non-existent is rejected with HTTP 400."""
    # Test non-existent attachment_id
    resp = client.post("/api/sandbox/render", json={"attachment_id": "att_nonexistent_999"})
    assert resp.status_code == 400
    assert "not ready" in resp.json()["detail"].lower() or "not found" in resp.json()["detail"].lower()


def test_criterion_5_corrupt_file_safety():
    """Criterion 5: Corrupt/malformed office document fails cleanly inside sandbox limits."""
    # Upload corrupt zip header file named corrupted.docx
    corrupt_bytes = b"PK\x03\x04_CORRUPT_MALFORMED_DOCX_HEADER_DATA_" * 20
    att_id = upload_and_wait_ready("corrupted.docx", corrupt_bytes, category="temporary")

    resp = client.post("/api/sandbox/render", json={"attachment_id": att_id})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_render_job(job_id, timeout_max=15.0)
    assert job["status"] == "failed"
    assert job.get("error") is not None


def test_criterion_6_lifecycle_temp_vs_perm():
    """Criterion 6: Preview renderings respect permanent vs temporary lifecycle."""
    docx_bytes = create_sample_docx_bytes()

    # 1. Render temporary attachment
    temp_att_id = upload_and_wait_ready("temp_doc.docx", docx_bytes, category="temporary")
    resp_t = client.post("/api/sandbox/render", json={"attachment_id": temp_att_id})
    job_t = poll_render_job(resp_t.json()["job_id"])
    assert job_t["status"] == "ready"

    # 2. Render permanent attachment
    perm_att_id = upload_and_wait_ready("perm_doc.docx", docx_bytes, category="permanent")
    resp_p = client.post("/api/sandbox/render", json={"attachment_id": perm_att_id})
    job_p = poll_render_job(resp_p.json()["job_id"])
    assert job_p["status"] == "ready"

    # Confirm files exist on disk before cleanup
    render_mgr = get_render_manager()
    assert render_mgr.get_rendered_preview_path(temp_att_id) is not None
    assert render_mgr.get_rendered_preview_path(perm_att_id) is not None

    # Run session cleanup
    cleanup_resp = client.post("/api/attachments/cleanup")
    assert cleanup_resp.status_code == 200

    # Temporary rendered preview must be deleted; permanent must persist
    assert render_mgr.get_rendered_preview_path(temp_att_id) is None
    assert render_mgr.get_rendered_preview_path(perm_att_id) is not None


def test_criterion_7_concurrent_rendering_isolation():
    """Criterion 7: Two renders submitted concurrently do not interfere with each other."""
    bytes_docx = create_sample_docx_bytes()
    bytes_xlsx = create_sample_xlsx_bytes()

    att1 = upload_and_wait_ready("conc1.docx", bytes_docx, category="temporary")
    att2 = upload_and_wait_ready("conc2.xlsx", bytes_xlsx, category="temporary")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(client.post, "/api/sandbox/render", json={"attachment_id": att1})
        f2 = executor.submit(client.post, "/api/sandbox/render", json={"attachment_id": att2})
        r1, r2 = f1.result(), f2.result()

    job1 = poll_render_job(r1.json()["job_id"])
    job2 = poll_render_job(r2.json()["job_id"])

    assert job1["status"] == "ready"
    assert job2["status"] == "ready"
    assert job1["page_count"] >= 1
    assert job2["page_count"] == 2

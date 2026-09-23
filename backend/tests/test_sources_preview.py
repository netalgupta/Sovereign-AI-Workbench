"""
backend/tests/test_sources_preview.py

Backend tests for Sources Tab Click-to-Preview API & Render Adapter.
Tests:
1. Sandboxed render pipeline execution for source corpus file paths (.docx, .xlsx, etc.)
2. Preview image serving via GET /api/sandbox/render/preview/{target_id}
3. Caching check (re-submitting previous rendered source file path returns ready status without re-rendering)
4. Direct raw file content endpoint GET /api/sources/content for PDF and TXT files
5. Actual corpus file verification for Maintenance_Log_Q3_2026.xlsx and Unit_44_Emergency_Cooling.txt
"""

import time
import docx
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_sources_content_unit_44_emergency_cooling_txt():
    # Test real corpus TXT file using relative workspace path
    rel_path = "MRPL_RAG_Test_Corpus/07_User_Uploads/Unit_44_Emergency_Cooling.txt"
    res = client.get(f"/api/sources/content?path={rel_path}")
    assert res.status_code == 200, f"Failed to get content for {rel_path}: {res.text}"
    assert len(res.text) > 0


def test_sources_xlsx_render_maintenance_log():
    # Test real corpus XLSX file using relative workspace path
    rel_path = "MRPL_RAG_Test_Corpus/02_Inspection_and_Maintenance/Maintenance_Log_Q3_2026.xlsx"
    res = client.post("/api/sandbox/render", json={"file_path": rel_path})
    assert res.status_code == 200, f"Render submission failed: {res.text}"
    job_id = res.json()["job_id"]

    status = "queued"
    target_id = None
    for _ in range(30):
        s_res = client.get(f"/api/sandbox/render/{job_id}")
        assert s_res.status_code == 200
        s_data = s_res.json()
        status = s_data["status"]
        if status in ("ready", "failed"):
            target_id = s_data.get("attachment_id")
            break
        time.sleep(0.3)

    assert status == "ready", f"Render failed: {s_data}"
    assert target_id is not None

    prev_res = client.get(f"/api/sandbox/render/preview/{target_id}")
    assert prev_res.status_code == 200
    assert len(prev_res.content) > 0


def test_sources_docx_render_and_cache():
    rel_docx = "MRPL_RAG_Test_Corpus/07_User_Uploads/Aromatic_Complex_Benzene_Safety_Circular.docx"
    res = client.post("/api/sandbox/render", json={"file_path": rel_docx})
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    status = "queued"
    target_id = None
    for _ in range(30):
        s_res = client.get(f"/api/sandbox/render/{job_id}")
        assert s_res.status_code == 200
        s_data = s_res.json()
        status = s_data["status"]
        if status in ("ready", "failed"):
            target_id = s_data.get("attachment_id")
            break
        time.sleep(0.3)

    assert status == "ready", f"Render failed: {s_data}"
    assert target_id is not None

    prev_res = client.get(f"/api/sandbox/render/preview/{target_id}")
    assert prev_res.status_code == 200

    # Caching check
    cache_res = client.post("/api/sandbox/render", json={"file_path": rel_docx})
    assert cache_res.status_code == 200
    cache_job_id = cache_res.json()["job_id"]
    c_status_res = client.get(f"/api/sandbox/render/{cache_job_id}")
    assert c_status_res.status_code == 200
    assert c_status_res.json()["status"] == "ready"

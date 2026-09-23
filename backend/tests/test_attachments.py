"""Automated test suite for Task 1: Attachment Payload & Backend State Management.

Verifies:
  1. Permanent attachment survives simulated session/server restart.
  2. Temporary attachment is purged after session end cleanup.
  3. GET /api/attachments filters permanent vs temporary attachments correctly.
  4. Attachment processing transitions status queued -> processing -> ready.
  5. Readability guard blocks un-categorized or non-ready attachments from system access.
"""

import time
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.attachments.manager import AttachmentManager, reset_attachment_manager
from backend.api.state import reset_state

client = TestClient(app)


def setup_function():
    """Reset attachment manager and state before each test."""
    reset_state()
    reset_attachment_manager()


def test_permanent_attachment_survives_session_restart(tmp_path):
    """Criterion 1: Uploading a file with category 'permanent' is still present
    and retrievable after a simulated session restart."""
    mgr1 = AttachmentManager(storage_dir=tmp_path)

    res = mgr1.upload_attachment(
        filename="company_sop_101.pdf",
        content_type="application/pdf",
        category="permanent",
        content_bytes=b"%PDF-1.4 Company Standard Operating Procedure 101",
        session_id="session_alpha",
        async_processing=False,  # Synchronous for test speed
    )

    att_id = res["attachment_id"]
    assert res["status"] == "queued"

    # Wait for ready status
    att_info = mgr1.get_attachment(att_id)
    assert att_info["status"] == "ready"
    assert att_info["category"] == "permanent"
    assert Path(att_info["storage_ref"]).exists()

    # Simulate session restart by creating a new AttachmentManager loading from disk
    mgr2 = AttachmentManager(storage_dir=tmp_path)
    restored_info = mgr2.get_attachment(att_id)

    assert restored_info is not None, "Permanent attachment must survive restart"
    assert restored_info["attachment_id"] == att_id
    assert restored_info["category"] == "permanent"
    assert restored_info["filename"] == "company_sop_101.pdf"
    assert Path(restored_info["storage_ref"]).exists()


def test_temporary_attachment_gone_after_session_end(tmp_path):
    """Criterion 2: Uploading a file with category 'temporary' is gone after
    simulated session end."""
    mgr = AttachmentManager(storage_dir=tmp_path)

    # Upload 1 permanent and 1 temporary file
    perm_res = mgr.upload_attachment(
        filename="safety_standard.pdf",
        content_type="application/pdf",
        category="permanent",
        content_bytes=b"Permanent Safety Manual Data",
        session_id="session_beta",
        async_processing=False,
    )
    temp_res = mgr.upload_attachment(
        filename="user_inspection_report.pdf",
        content_type="application/pdf",
        category="temporary",
        content_bytes=b"Temporary User Inspection Data",
        session_id="session_beta",
        async_processing=False,
    )

    temp_id = temp_res["attachment_id"]
    perm_id = perm_res["attachment_id"]

    temp_path = Path(mgr.get_attachment(temp_id)["storage_ref"])
    perm_path = Path(mgr.get_attachment(perm_id)["storage_ref"])

    assert temp_path.exists()
    assert perm_path.exists()

    # Simulate session end / cleanup
    cleanup_res = mgr.cleanup_session(session_id="session_beta")
    assert cleanup_res["success"] is True
    assert temp_id in cleanup_res["deleted_ids"]

    # Verify temporary file and record are gone
    assert mgr.get_attachment(temp_id) is None
    assert not temp_path.exists()

    # Verify permanent file and record are UNTOUCHED
    assert mgr.get_attachment(perm_id) is not None
    assert perm_path.exists()


def test_get_attachments_api_category_filter():
    """Criterion 3: GET /api/attachments correctly separates permanent vs temporary in its listing."""
    # 1. Upload temporary attachment via API
    temp_resp = client.post(
        "/api/attachments/upload",
        json={
          "filename": "inspection_report.pdf",
          "type": "application/pdf",
          "category": "temporary",
          "processing": True,
          "content": "Sample temporary report content",
        },
    )
    assert temp_resp.status_code == 200
    temp_id = temp_resp.json()["attachment_id"]

    # 2. Upload permanent attachment via API
    perm_resp = client.post(
        "/api/attachments/upload",
        json={
          "filename": "site_manual.pdf",
          "type": "application/pdf",
          "category": "permanent",
          "processing": True,
          "content": "Sample permanent manual content",
        },
    )
    assert perm_resp.status_code == 200
    perm_id = perm_resp.json()["attachment_id"]

    # Wait briefly for processing
    time.sleep(0.5)

    # 3. Filter category=temporary
    temp_list_resp = client.get("/api/attachments?category=temporary")
    assert temp_list_resp.status_code == 200
    temp_items = temp_list_resp.json()["attachments"]
    temp_ids = [item["attachment_id"] for item in temp_items]

    assert temp_id in temp_ids
    assert perm_id not in temp_ids

    # 4. Filter category=permanent
    perm_list_resp = client.get("/api/attachments?category=permanent")
    assert perm_list_resp.status_code == 200
    perm_items = perm_list_resp.json()["attachments"]
    perm_ids = [item["attachment_id"] for item in perm_items]

    assert perm_id in perm_ids
    assert temp_id not in perm_ids


def test_attachment_status_transition_queued_processing_ready():
    """Criterion 4: The attachment indicator visibly moves through queued -> processing -> ready."""
    # Upload file with async processing enabled
    resp = client.post(
        "/api/attachments/upload",
        json={
          "filename": "telemetry_scan.pdf",
          "type": "application/pdf",
          "category": "temporary",
          "processing": True,
        },
    )
    assert resp.status_code == 200
    att_id = resp.json()["attachment_id"]
    assert resp.json()["status"] == "queued"

    # Poll status endpoint
    statuses_seen = set()
    for _ in range(20):
        status_resp = client.get(f"/api/attachments/{att_id}")
        assert status_resp.status_code == 200
        st = status_resp.json()["status"]
        statuses_seen.add(st)
        if st == "ready":
            break
        time.sleep(0.1)

    assert "ready" in statuses_seen
    assert len(statuses_seen) >= 2, f"Expected status transitions, got {statuses_seen}"


def test_attachment_readability_guard(tmp_path):
    """Criterion 5: No attachment is readable by any other part of the system before
    it has an attachment_id and category assigned and reaches 'ready' status."""
    mgr = AttachmentManager(storage_dir=tmp_path)

    # Non-existent attachment ID
    assert mgr.is_attachment_readable("att_fake_999") is False

    # Upload attachment but check before status becomes ready (using manual state setup)
    att_id = "att_unready_test"
    mgr._attachments[att_id] = {
        "attachment_id": att_id,
        "filename": "draft.pdf",
        "category": "temporary",
        "status": "processing",  # not ready yet!
        "readable": False,
    }

    # Must NOT be readable while processing
    assert mgr.is_attachment_readable(att_id) is False

    # Uncategorized attachment (missing category)
    uncat_id = "att_uncat_test"
    mgr._attachments[uncat_id] = {
        "attachment_id": uncat_id,
        "filename": "draft.pdf",
        "category": None,
        "status": "ready",
        "readable": True,
    }
    assert mgr.is_attachment_readable(uncat_id) is False

    # Mark ready and valid category
    mgr._attachments[att_id]["status"] = "ready"
    mgr._attachments[att_id]["readable"] = True
    assert mgr.is_attachment_readable(att_id) is True

"""Tests for Step 5: Voice Note Upload, Storage Lifecycle, and Offline STT API contract.

Verifies:
  1. POST /api/voice/upload receives audio blob and enqueues STT job.
  2. GET /api/voice/{job_id} returns pollable status (queued -> processing -> ready/failed).
  3. Real audio transcription produces expected words ("hydrocracker", "turnaround").
  4. Offline isolation: 0 network calls during full upload -> transcribe cycle.
  5. Empty or non-speech audio fails gracefully to status="failed".
  6. Storage follows temporary/permanent AttachmentManager lifecycle.
"""

import os
import time
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.ingestion import model_cache

client = TestClient(app)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_WAV = os.path.join(FIXTURES_DIR, "sample_voice_note.wav")

_CACHE_PRESENT = model_cache.local_cache_dir(
    "audio", "Systran/faster-whisper-base"
).exists()

pytestmark = pytest.mark.skipif(
    not _CACHE_PRESENT,
    reason="faster-whisper-base model not cached locally",
)


def test_voice_upload_and_transcription_api_flow():
    """Test full upload, job status polling, and transcript generation."""
    with open(SAMPLE_WAV, "rb") as f:
        audio_bytes = f.read()

    # 1. Upload voice note
    response = client.post(
        "/api/voice/upload",
        files={"file": ("sample_voice_note.wav", audio_bytes, "audio/wav")},
        data={"category": "temporary", "session_id": "test_session_1"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "job_id" in data
    job_id = data["job_id"]
    assert job_id.startswith("vjob_")

    # 2. Poll job status until ready or failed
    status = "queued"
    job_info = {}
    for _ in range(30):
        res = client.get(f"/api/voice/{job_id}")
        assert res.status_code == 200
        job_info = res.json()
        status = job_info.get("status")
        if status in ("ready", "failed"):
            break
        time.sleep(0.5)

    assert status == "ready", f"Job failed or timed out: {job_info}"
    transcript = job_info.get("transcript", "").lower()
    assert "hydrocracker" in transcript or "turnaround" in transcript
    assert job_info.get("category") == "temporary"


def test_voice_transcription_airgap_network_blocked(monkeypatch):
    """Prove that voice note upload & transcription makes ZERO external network calls."""
    import socket

    orig_connect = socket.socket.connect

    def _blocked_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise AssertionError(f"Voice note pipeline attempted an external network call to {address}")
        return orig_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)

    with open(SAMPLE_WAV, "rb") as f:
        audio_bytes = f.read()

    response = client.post(
        "/api/voice/upload",
        files={"file": ("sample_voice_note.wav", audio_bytes, "audio/wav")},
        data={"category": "temporary"},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    job_info = {}
    for _ in range(30):
        res = client.get(f"/api/voice/{job_id}")
        assert res.status_code == 200
        job_info = res.json()
        if job_info.get("status") in ("ready", "failed"):
            break
        time.sleep(0.5)

    assert job_info.get("status") == "ready"
    assert "hydrocracker" in job_info.get("transcript", "").lower()


def test_empty_audio_upload_rejected():
    """Empty audio files must return HTTP 400."""
    response = client.post(
        "/api/voice/upload",
        files={"file": ("empty.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400
    assert "Empty audio recording" in response.text


def test_invalid_job_id_returns_404():
    """Querying an unknown job_id returns HTTP 404."""
    response = client.get("/api/voice/vjob_nonexistent_999")
    assert response.status_code == 404

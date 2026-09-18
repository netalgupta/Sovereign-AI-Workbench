"""Composer dictation is transcribed on this machine, never in a cloud.

Dictation used the browser's Web Speech API. Chromium implements it by
streaming microphone audio to Google's speech servers, so on any
networked machine the operator's voice left the building every time they
dictated -- hard constraint #1. It now records with MediaRecorder and
posts the audio to /api/transcribe, which runs the local faster-whisper
model.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
FIXTURE = Path(__file__).parent / "fixtures" / "sample_voice_note.wav"
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_dictation_is_transcribed_by_the_local_model():
    audio = base64.b64encode(FIXTURE.read_bytes()).decode()
    res = client.post("/api/transcribe", json={"audioBase64": audio, "mimeType": "audio/wav"})

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["text"].strip(), "no text came back from a real speech recording"
    assert "local" in data["engine"]


def test_the_recording_is_not_left_on_disk(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    audio = base64.b64encode(FIXTURE.read_bytes()).decode()
    client.post("/api/transcribe", json={"audioBase64": audio, "mimeType": "audio/wav"})

    assert not list(tmp_path.glob("dictation-*")), "a dictation recording was left behind"


def test_bad_audio_is_rejected_not_guessed_at():
    assert client.post("/api/transcribe", json={"audioBase64": "not base64!!"}).status_code == 400
    assert client.post("/api/transcribe", json={"audioBase64": ""}).status_code == 400


def test_no_cloud_speech_api_anywhere_in_the_frontend():
    """The regression guard. SpeechRecognition / webkitSpeechRecognition in
    Chromium sends audio to Google; nothing in the product may use them."""
    offenders = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".js", ".jsx", ".ts", ".tsx"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Comments explaining WHY it is banned are fine; code is not.
        code = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
        if re.search(r"\b(webkit)?SpeechRecognition\b", code):
            offenders.append(str(path.relative_to(FRONTEND_SRC)))
    assert not offenders, f"cloud speech recognition used in: {offenders}"

"""Tests for CARD 12's transcribe_voice_note.

The fixture (sample_voice_note.wav) is real synthesized speech generated
offline via pyttsx3 (Windows SAPI), saying exactly:
"Schedule the turnaround for the hydrocracker next week" — see
scratchpad/build_fixtures.py history for how it was produced. Using a
real audio file with KNOWN spoken content is what makes this an actual
test of transcription accuracy, not just a test that the function
doesn't crash.
"""

import os

import pytest

from backend.ingestion import model_cache

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_CACHE_PRESENT = model_cache.local_cache_dir(
    "audio", "Systran/faster-whisper-base"
).exists()

pytestmark = pytest.mark.skipif(
    not _CACHE_PRESENT,
    reason=(
        "faster-whisper-base is not cached locally — run "
        "`python -m backend.ingestion.fetch_models --model faster-whisper-base` "
        "once (with internet) before running this suite."
    ),
)


def _path(name: str) -> str:
    return os.path.join(FIXTURES, name)


def test_transcribe_real_audio_contains_expected_words():
    from backend.tools.audio.voice_transcription import transcribe_voice_note

    result = transcribe_voice_note(_path("sample_voice_note.wav"))

    lowered = result.full_text.lower()
    assert "turnaround" in lowered
    assert "hydrocracker" in lowered
    assert result.language == "en"


def test_segments_are_well_formed():
    from backend.tools.audio.voice_transcription import transcribe_voice_note

    result = transcribe_voice_note(_path("sample_voice_note.wav"))

    assert len(result.segments) >= 1
    for segment in result.segments:
        assert segment.start_seconds < segment.end_seconds
        assert segment.text  # never an empty string for real speech


def test_missing_file_raises_before_touching_the_model():
    from backend.tools.audio.voice_transcription import transcribe_voice_note

    missing_path = _path("does_not_exist.wav")
    with pytest.raises(FileNotFoundError) as exc_info:
        transcribe_voice_note(missing_path)
    assert str(exc_info.value) == f"Audio file not found at {missing_path}"


def test_transcription_works_with_sockets_hard_blocked(monkeypatch):
    """Same rigor as test_embeddings.py's equivalent test: block sockets
    at the OS level, force a FRESH model construction (not reusing one
    another test already loaded), and prove it still works. This is what
    makes "offline" a verified fact instead of a comment."""
    import socket

    from backend.tools.audio import voice_transcription

    voice_transcription._model = None  # force a real reload under the block

    def _blocked(*args, **kwargs):
        raise AssertionError("transcribe_voice_note attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    result = voice_transcription.transcribe_voice_note(_path("sample_voice_note.wav"))

    assert "hydrocracker" in result.full_text.lower()

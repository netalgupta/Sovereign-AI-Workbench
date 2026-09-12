"""Local voice note transcription — VIBECODING_SPEC.md CARD 12.

TEAM ADDITION, NOT PS-TRACEABLE — see the card's header note and
REQUIREMENTS.md §6. Built to extend FR-7's document-modality handling to
audio input, to the exact same offline-forever discipline as every other
model-backed tool in this catalog.

WHY faster-whisper GETS THE SAME model_cache.py TREATMENT AS bge-large:
it pulls its model from the Hugging Face Hub exactly like
sentence-transformers does — same phone-home-on-every-load risk, same
fix (fetch once online, force offline mode, load only from a local path).
See model_cache.py's module docstring for the full rationale; it is not
repeated here because there should be exactly one place that reasoning
lives, not two copies that can drift apart.

WHY THE FETCH STEP LIVES IN fetch_models.py, NOT HERE (real bug this
avoids, not a style preference): this file calls force_offline_mode() at
import time, unconditionally. An earlier version of this module also
defined its own bootstrap-fetch helper right here — importing this file
to reach that helper ran force_offline_mode() first as an import
side-effect, which set HF_HUB_OFFLINE=1 for the whole process BEFORE the
deliberate one-time online fetch could run, and the fetch failed with
"outgoing traffic has been disabled". Any file that forces itself
offline at import time must never also contain code that's supposed to
run online — fetch_models.py is kept completely independent of every
runtime module for exactly this reason.
"""

from pathlib import Path

from pydantic import BaseModel

from backend.ingestion.model_cache import force_offline_mode, require_cached

# Must happen before importing faster_whisper — same ordering requirement
# as embeddings.py, same reason: some Hub-reachability checks happen at
# import/construction time, not only at download time.
force_offline_mode()

from faster_whisper import WhisperModel  # noqa: E402

MODEL_ID = "Systran/faster-whisper-base"

_model: WhisperModel | None = None


class TranscriptionSegment(BaseModel):
    text: str
    start_seconds: float
    end_seconds: float


class TranscriptionResult(BaseModel):
    full_text: str
    segments: list[TranscriptionSegment]
    language: str


def _whisper_device() -> tuple[str, str]:
    """(device, compute_type) for faster-whisper.

    This was hardcoded to ("cpu", "int8"). ctranslate2 -- faster-whisper's
    runtime -- reports a CUDA device on this machine
    (get_cuda_device_count() == 1), so the transcription was running on
    the processor for no reason, contributing to the sustained CPU
    saturation that made the desktop unresponsive.

    COMPUTE TYPE CHANGES WITH THE DEVICE, and not arbitrarily. int8 is
    the right quantisation for CPU inference, where integer arithmetic
    is what the hardware is fast at. On an NVIDIA GPU float16 maps onto
    the tensor cores and is both faster and more accurate than int8, so
    carrying the CPU choice over to CUDA would take the GPU and then
    run it in its worst mode.

    Falls back to CPU rather than raising. A venue machine may have no
    NVIDIA GPU, and slow transcription is better than a tool that cannot
    load. Note the fallback is also what happens when ctranslate2 was
    built without CUDA support, which is a different failure from having
    no GPU and is why availability is asked of ctranslate2 itself rather
    than inferred from torch.

    Override with WORKBENCH_WHISPER_DEVICE.
    """
    import os

    override = os.environ.get("WORKBENCH_WHISPER_DEVICE")
    if override:
        return override, ("float16" if override.startswith("cuda") else "int8")

    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:  # noqa: BLE001
        pass
    return "cpu", "int8"


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        cache_dir = require_cached("audio", MODEL_ID)
        # Passing a real directory path (not a repo id) is what makes
        # this structurally offline, not just configured to be: verified
        # by reading faster_whisper's own source — WhisperModel only
        # calls into huggingface_hub's download machinery in the `else`
        # branch of `elif os.path.isdir(model_size_or_path)`. A local
        # directory path never reaches that branch at all, so there is
        # no download_root/local_files_only flag to trust here — the
        # network-reaching code simply isn't in the call path.
        device, compute_type = _whisper_device()
        _model = WhisperModel(str(cache_dir), device=device, compute_type=compute_type)
    return _model


def transcribe_voice_note(audio_path: str) -> TranscriptionResult:
    """Transcribe a voice note to text, fully offline.

    Raises:
        FileNotFoundError: if `audio_path` doesn't exist — checked before
            touching the (comparatively expensive) model at all.
    """
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found at {audio_path}")

    model = _get_model()
    segments_generator, info = model.transcribe(audio_path)

    # Materialize immediately — faster-whisper returns a lazy generator;
    # returning that to a caller who inspects `.segments` twice would
    # silently yield nothing the second time. Never hardcode language —
    # info.language is auto-detected, MRPL correspondence could
    # legitimately not be in English.
    segments = [
        TranscriptionSegment(
            text=segment.text.strip(),
            start_seconds=segment.start,
            end_seconds=segment.end,
        )
        for segment in segments_generator
    ]

    return TranscriptionResult(
        full_text=" ".join(segment.text for segment in segments).strip(),
        segments=segments,
        language=info.language,
    )

"""Voice note manager — async STT job queue & AttachmentManager integration.

Enforces offline voice note reception, storage lifecycle (temporary/permanent),
and offline faster-whisper transcription job processing.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, Optional

from backend.attachments.manager import AttachmentManager, get_attachment_manager
from backend.tools.audio.voice_transcription import transcribe_voice_note

logger = logging.getLogger("backend.voice")

_voice_manager_instance: Optional[VoiceManager] = None
_instance_lock = threading.Lock()


class VoiceManager:
    """Thread-safe manager for voice recording jobs."""

    def __init__(self, attachment_mgr: Optional[AttachmentManager] = None):
        self.attachment_mgr = attachment_mgr or get_attachment_manager()
        self._jobs: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voice_worker")

    def submit_voice_note(
        self,
        audio_bytes: bytes,
        filename: str = "voice_note.webm",
        content_type: str = "audio/webm",
        category: str = "temporary",
        session_id: Optional[str] = None,
    ) -> str:
        """Store audio via AttachmentManager and enqueue local STT job.

        Returns job_id.
        """
        category_clean = (category or "temporary").lower().strip()
        if category_clean not in ("temporary", "permanent"):
            category_clean = "temporary"

        # 1. Save file via AttachmentManager
        upload_res = self.attachment_mgr.upload_attachment(
            filename=filename,
            content_type=content_type,
            category=category_clean,
            content_bytes=audio_bytes,
            session_id=session_id,
            async_processing=False,
        )

        att_id = upload_res["attachment_id"]
        att_record = self.attachment_mgr.get_attachment(att_id)
        audio_path = att_record["storage_ref"] if att_record else ""
        job_id = f"vjob_{uuid.uuid4().hex[:12]}"

        job_data = {
            "job_id": job_id,
            "attachment_id": att_id,
            "filename": filename,
            "category": category_clean,
            "status": "queued",
            "transcript": "",
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "audio_path": audio_path,
        }

        with self._lock:
            self._jobs[job_id] = job_data

        # 2. Enqueue async transcription worker
        self._executor.submit(self._process_transcription, job_id, audio_path)
        return job_id

    def _process_transcription(self, job_id: str, audio_path: str) -> None:
        """Worker thread to run local offline Whisper transcription."""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "processing"

        try:
            res = transcribe_voice_note(audio_path)
            full_text = (res.full_text or "").strip()

            with self._lock:
                if job_id in self._jobs:
                    if full_text:
                        self._jobs[job_id]["status"] = "ready"
                        self._jobs[job_id]["transcript"] = full_text
                        self._jobs[job_id]["error"] = None
                    else:
                        self._jobs[job_id]["status"] = "failed"
                        self._jobs[job_id]["transcript"] = ""
                        self._jobs[job_id]["error"] = "No speech detected in audio recording"
        except Exception as exc:
            logger.error("Voice transcription failed for job %s: %s", job_id, exc, exc_info=True)
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id]["status"] = "failed"
                    self._jobs[job_id]["transcript"] = ""
                    self._jobs[job_id]["error"] = str(exc) or "Voice transcription failed"

    def get_job(self, job_id: str) -> Optional[dict]:
        """Retrieve job status dict."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return {
                "job_id": job["job_id"],
                "status": job["status"],
                "transcript": job["transcript"],
                "error": job["error"],
                "attachment_id": job["attachment_id"],
                "category": job["category"],
            }


def get_voice_manager() -> VoiceManager:
    """Get process-wide VoiceManager singleton."""
    global _voice_manager_instance
    if _voice_manager_instance is None:
        with _instance_lock:
            if _voice_manager_instance is None:
                _voice_manager_instance = VoiceManager()
    return _voice_manager_instance

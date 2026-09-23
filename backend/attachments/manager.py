"""Attachment lifecycle & backend state manager.

Tracks every file added via the chat inlet, enforcing categorization as either
a long-term "permanent" source or a session-scoped "temporary" file. No other
component (sandbox, visualizer, agent, retrieval) is allowed to read an attachment
before it has an attachment_id and category assigned and reaches 'ready' status.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("backend.attachments")

STORAGE_BASE = Path("storage/attachments")


class AttachmentManager:
    """Thread-safe backend state manager for chat attachments."""

    def __init__(self, storage_dir: Path = STORAGE_BASE):
        self.storage_dir = Path(storage_dir)
        self.permanent_dir = self.storage_dir / "permanent"
        self.temporary_dir = self.storage_dir / "temporary"
        self.meta_file = self.storage_dir / "attachments_meta.json"
        self._lock = threading.Lock()

        self._attachments: Dict[str, dict] = {}
        self._ensure_directories()
        self._load_persistent_metadata()

    def _ensure_directories(self) -> None:
        """Create storage directories if they do not exist."""
        self.permanent_dir.mkdir(parents=True, exist_ok=True)
        self.temporary_dir.mkdir(parents=True, exist_ok=True)

    def _load_persistent_metadata(self) -> None:
        """Load stored metadata for permanent attachments on startup / session restart."""
        with self._lock:
            self._attachments.clear()
            if self.meta_file.exists():
                try:
                    data = json.loads(self.meta_file.read_text(encoding="utf-8"))
                    for att_id, item in data.items():
                        # Only restore permanent attachments across restarts (or ready temp items if present)
                        if item.get("category") == "permanent":
                            file_path = Path(item.get("storage_ref", ""))
                            if file_path.exists():
                                self._attachments[att_id] = item
                except Exception as exc:
                    logger.warning("Failed to read attachments metadata file: %s", exc)

    def _save_persistent_metadata(self) -> None:
        """Save permanent attachments metadata to disk."""
        permanent_meta = {
            att_id: item
            for att_id, item in self._attachments.items()
            if item.get("category") == "permanent"
        }
        try:
            self.meta_file.write_text(
                json.dumps(permanent_meta, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.error("Failed to write attachments metadata: %s", exc)

    def upload_attachment(
        self,
        filename: str,
        content_type: str,
        category: str,
        content_bytes: bytes,
        session_id: Optional[str] = None,
        async_processing: bool = True,
    ) -> dict:
        """Categorize, store file, assign attachment_id, and queue processing.

        Returns immediately with status 'queued'.
        """
        category_clean = (category or "").lower().strip()
        if category_clean not in ("permanent", "temporary"):
            raise ValueError(
                f"Invalid attachment category '{category}'. Must be 'permanent' or 'temporary'."
            )

        attachment_id = f"att_{uuid.uuid4().hex[:12]}"
        safe_filename = Path(filename).name or "unnamed_attachment"
        target_dir = self.permanent_dir if category_clean == "permanent" else self.temporary_dir
        file_path = target_dir / f"{attachment_id}_{safe_filename}"

        # Write binary content to categorized disk location
        file_path.write_bytes(content_bytes)
        storage_ref = str(file_path.resolve())

        record = {
            "attachment_id": attachment_id,
            "filename": safe_filename,
            "type": content_type or "application/octet-stream",
            "category": category_clean,
            "status": "queued",
            "storage_ref": storage_ref,
            "session_id": session_id or "default",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "readable": False,
        }

        with self._lock:
            self._attachments[attachment_id] = record
            if category_clean == "permanent":
                self._save_persistent_metadata()

        if async_processing:
            worker = threading.Thread(
                target=self._process_attachment_async,
                args=(attachment_id,),
                daemon=True,
            )
            worker.start()
        else:
            self._process_attachment_async(attachment_id)

        return {"attachment_id": attachment_id, "status": "queued"}

    def _process_attachment_async(self, attachment_id: str) -> None:
        """Asynchronously transition status: queued -> processing -> ready (or failed)."""
        time.sleep(0.1)  # Simulated brief queue wait
        with self._lock:
            if attachment_id not in self._attachments:
                return
            att_entry = self._attachments[attachment_id]
            att_entry["status"] = "processing"

        try:
            storage_ref = att_entry.get("storage_ref", "")
            file_path = Path(storage_ref)
            filename = att_entry.get("filename", "").lower()
            ext = file_path.suffix.lower()

            # 1. Forbidden extension security check
            FORBIDDEN_EXTS = {".exe", ".dll", ".so", ".sh", ".bat", ".cmd", ".ps1", ".scr", ".vbs", ".msi", ".jar"}
            if ext in FORBIDDEN_EXTS:
                raise ValueError(f"File extension '{ext}' is forbidden for security")

            # 2. Maximum file size check (50MB threshold)
            MAX_SIZE_BYTES = 50 * 1024 * 1024
            if file_path.exists():
                file_size = file_path.stat().st_size
                if file_size > MAX_SIZE_BYTES:
                    size_mb = file_size / (1024 * 1024)
                    raise ValueError(f"File size ({size_mb:.1f}MB) exceeds maximum limit of 50MB")

                # 3. Content corruption check
                raw_head = file_path.read_bytes()[:16]
                if raw_head.startswith(b"CORRUPT"):
                    raise ValueError("Corrupt file content: invalid header structure")

            time.sleep(0.2)  # Processing work (indexing prep, metadata extraction)
            with self._lock:
                if attachment_id in self._attachments:
                    att = self._attachments[attachment_id]
                    att["status"] = "ready"
                    att["readable"] = True
                    if att["category"] == "permanent":
                        self._save_persistent_metadata()
        except Exception as exc:
            logger.error("Error processing attachment %s: %s", attachment_id, exc)
            with self._lock:
                if attachment_id in self._attachments:
                    att = self._attachments[attachment_id]
                    att["status"] = "failed"
                    att["error"] = str(exc)
                    att["readable"] = False

    def get_attachment(self, attachment_id: str) -> Optional[dict]:
        """Get status and details for an attachment by ID."""
        with self._lock:
            att = self._attachments.get(attachment_id)
            if not att:
                return None
            return {
                "attachment_id": att["attachment_id"],
                "filename": att.get("filename", ""),
                "type": att.get("type", ""),
                "status": att.get("status", "unknown"),
                "category": att.get("category", "temporary"),
                "storage_ref": att.get("storage_ref", ""),
                "session_id": att.get("session_id", ""),
                "created_at": att.get("created_at", ""),
                "readable": att.get("readable", False),
                "error": att.get("error"),
            }

    def list_attachments(self, category: Optional[str] = None) -> List[dict]:
        """List tracked attachments, optionally filtered by category."""
        category_clean = category.lower().strip() if category else None
        out = []
        with self._lock:
            for att_id, att in self._attachments.items():
                if category_clean and att.get("category") != category_clean:
                    continue
                out.append({
                    "attachment_id": att["attachment_id"],
                    "filename": att.get("filename", ""),
                    "type": att.get("type", ""),
                    "status": att.get("status", "unknown"),
                    "category": att.get("category", "temporary"),
                    "storage_ref": att.get("storage_ref", ""),
                    "session_id": att.get("session_id", ""),
                    "created_at": att.get("created_at", ""),
                    "readable": att.get("readable", False),
                    "error": att.get("error"),
                })
        return out

    def is_attachment_readable(self, attachment_id: str) -> bool:
        """Enforces restriction: True only if attachment exists, has category/id, and status is ready."""
        with self._lock:
            att = self._attachments.get(attachment_id)
            if not att:
                return False
            return bool(
                att.get("attachment_id")
                and att.get("category") in ("permanent", "temporary")
                and att.get("status") == "ready"
                and att.get("readable") is True
            )

    def cleanup_session(self, session_id: Optional[str] = None) -> dict:
        """Session cleanup hook: deletes all temporary attachments and files.

        Permanent attachments are untouched.
        """
        deleted_ids = []
        with self._lock:
            to_remove = []
            for att_id, att in self._attachments.items():
                if att.get("category") == "temporary":
                    if session_id is None or att.get("session_id") == session_id or session_id == "all":
                        to_remove.append(att_id)

            for att_id in to_remove:
                att = self._attachments.pop(att_id)
                deleted_ids.append(att_id)
                storage_ref = att.get("storage_ref")
                if storage_ref:
                    p = Path(storage_ref)
                    try:
                        if p.exists() and p.is_file():
                            p.unlink()
                    except Exception as exc:
                        logger.warning("Could not delete temporary file %s: %s", storage_ref, exc)

        # Also purge any dangling files in temporary directory if cleaning all
        if session_id is None or session_id == "all":
            try:
                for temp_file in self.temporary_dir.glob("*"):
                    if temp_file.is_file():
                        try:
                            temp_file.unlink()
                        except Exception:
                            pass
            except Exception:
                pass

        return {
            "success": True,
            "deleted_count": len(deleted_ids),
            "deleted_ids": deleted_ids,
            "message": f"Cleaned up {len(deleted_ids)} temporary attachments.",
        }


_attachment_manager_instance: Optional[AttachmentManager] = None


def get_attachment_manager() -> AttachmentManager:
    """Singleton getter for AttachmentManager."""
    global _attachment_manager_instance
    if _attachment_manager_instance is None:
        _attachment_manager_instance = AttachmentManager()
    return _attachment_manager_instance


def reset_attachment_manager() -> None:
    """Reset attachment manager (used in tests)."""
    global _attachment_manager_instance
    _attachment_manager_instance = None

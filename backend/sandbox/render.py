"""
backend/sandbox/render.py

Office Document Rendering Manager for Step 3: Secure Sandbox — Office Document Rendering.

Enforces:
1. Step 1 Read-Guard Check: Rejects files that are not ready/readable.
2. Sandboxed Conversion: every conversion and every page render runs INSIDE
   the Step 2 SandboxManager (render_worker.py is the code it runs).
3. Output Storage & Lifecycle: Preview files inherit attachment category (temporary vs permanent).
4. Lifecycle Cleanup: Session cleanup purges temporary previews; permanent previews persist.
5. Async Job Polling: Status transitions (queued -> processing -> ready / failed) with preview_url and page_count.

Pages on demand. A job renders the first pages and records the page count
in manifest.json; any later page is rendered in the sandbox when it is first
asked for, a few pages at a time. The whole-document render this replaced
died on a 593-page book (256 MB sandbox), and the pages it had written were
then served as a complete 50-page document. The manifest also carries the
source's size and mtime, so an edited file is re-rendered, not shown stale.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from backend.attachments import get_attachment_manager
from backend.sandbox.manager import get_sandbox_manager

logger = logging.getLogger("sandbox.render")

RenderStatus = Literal["queued", "processing", "ready", "failed"]

STORAGE_RENDERED_DIR = Path("storage/rendered")
STORAGE_PERMANENT_RENDER = STORAGE_RENDERED_DIR / "permanent"
STORAGE_TEMPORARY_RENDER = STORAGE_RENDERED_DIR / "temporary"

WORKER_SOURCE = Path(__file__).with_name("render_worker.py")
MANIFEST = "manifest.json"
MANIFEST_VERSION = 2   # bump when the page format changes: older renders are redone
PAGE_BATCH = 6          # pages rendered per on-demand sandbox run
SANDBOX_SECONDS = 25    # per sandbox run; a DOCX layout or 6 pages at 150 dpi take ~1-3 s


def _stamp(path: Path) -> dict:
    st = path.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


class RenderManager:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._page_locks: Dict[str, threading.Lock] = {}
        self._ensure_storage_dirs()

    def _ensure_storage_dirs(self):
        STORAGE_PERMANENT_RENDER.mkdir(parents=True, exist_ok=True)
        STORAGE_TEMPORARY_RENDER.mkdir(parents=True, exist_ok=True)

    # ── the sandbox run ────────────────────────────────────────────────────

    def _run_worker(self, *args: Any) -> dict:
        """Run render_worker.main(*args) in the sandbox. {"ok", "page_count", "paginated", "error"}."""
        code = WORKER_SOURCE.read_text(encoding="utf-8") + f"\n_run(*{args!r})\n"
        sandbox = get_sandbox_manager()
        # host_paths: the worker reads the document and writes previews by
        # their host path, which the Docker pool's read-only container cannot see.
        sb_job_id = sandbox.submit_job(code=code, language="python", timeout_seconds=SANDBOX_SECONDS,
                                       host_paths=True)
        deadline = time.time() + SANDBOX_SECONDS + 5
        res = None
        while time.time() < deadline:
            res = sandbox.get_job(sb_job_id)
            if res and res["status"] in ("completed", "failed", "timeout"):
                break
            time.sleep(0.05)
        else:
            return {"ok": False, "error": "The sandboxed render did not finish in time."}
        if res["status"] != "completed" or res.get("exit_code") != 0:
            err = (res.get("stderr") or res.get("stdout") or f"Sandbox render {res['status']}").strip()
            return {"ok": False, "error": err.replace("CONVERSION_ERROR: ", "")}
        out = {"ok": True, "page_count": 1, "paginated": ""}
        for line in (res.get("stdout") or "").splitlines():
            if line.startswith("PAGE_COUNT="):
                out["page_count"] = max(1, int(line.split("=", 1)[1]))
            elif line.startswith("PAGINATED="):
                out["paginated"] = line.split("=", 1)[1].strip()
        return out

    # ── manifest (the disk cache's single source of truth) ────────────────

    @staticmethod
    def _dir_for(attachment_id: str) -> Optional[Path]:
        for base in (STORAGE_PERMANENT_RENDER, STORAGE_TEMPORARY_RENDER):
            if (base / attachment_id).exists():
                return base / attachment_id
        return None

    @staticmethod
    def _read_manifest(target_dir: Path) -> Optional[dict]:
        try:
            return json.loads((target_dir / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _manifest_current(manifest: Optional[dict], source: Path) -> bool:
        if not manifest:
            return False
        try:
            return manifest.get("version") == MANIFEST_VERSION and manifest.get("stamp") == _stamp(source)
        except OSError:
            return False

    # ── public API ─────────────────────────────────────────────────────────

    def submit_render_job(
        self,
        attachment_id: Optional[str] = None,
        file_path: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> str:
        """Submit an attachment or a source file for sandboxed rendering.

        Accepts attachment_id (Step 1 chat attachment) OR file_path / source_id
        (a file inside a configured source -- source_config.viewable_file).
        """
        att_mgr = get_attachment_manager()

        target_att_id = None
        filename = ""
        category = "temporary"
        storage_ref = ""

        # Case A: Step 1 Chat Inlet Attachment
        if attachment_id and (att_mgr.get_attachment(attachment_id) or attachment_id.startswith("att_")):
            if not att_mgr.is_attachment_readable(attachment_id):
                raise ValueError(f"Attachment '{attachment_id}' is not ready for rendering or does not exist")
            att_meta = att_mgr.get_attachment(attachment_id)
            if not att_meta:
                raise ValueError(f"Attachment '{attachment_id}' not found in registry")
            target_att_id = attachment_id
            filename = att_meta.get("filename", "")
            category = att_meta.get("category", "temporary")
            storage_ref = att_meta.get("storage_ref", "")

        # Case B: a file inside a configured source
        if not target_att_id:
            from backend.api import source_config

            raw_path = file_path or source_id or attachment_id
            if not raw_path:
                raise ValueError("Neither valid attachment_id nor file_path was provided")
            candidate_path = source_config.viewable_file(raw_path)
            if candidate_path is None:
                raise ValueError(f"No file in the configured sources matches: {raw_path}")
            target_att_id = "src_" + hashlib.md5(str(candidate_path).lower().encode("utf-8")).hexdigest()[:16]
            filename = candidate_path.name
            category = "permanent"
            storage_ref = str(candidate_path)

        source_path = self._source_path(storage_ref)
        with self._lock:
            # the same document already rendering: share that job
            for existing in self._jobs.values():
                if existing["attachment_id"] == target_att_id and existing["status"] in ("queued", "processing"):
                    return existing["job_id"]

        job_id = f"render_job_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        job_record = {
            "job_id": job_id,
            "attachment_id": target_att_id,
            "filename": filename,
            "category": category,
            "storage_ref": storage_ref,
            "status": "queued",
            "preview_url": f"/api/sandbox/render/preview/{target_att_id}",
            "page_count": 0,
            "error": None,
            "created_at": now_iso,
            "completed_at": None,
        }

        # Disk cache: valid only when its manifest matches the file as it is now
        target_dir = self._dir_for(target_att_id)
        manifest = self._read_manifest(target_dir) if target_dir else None
        if source_path.exists() and self._manifest_current(manifest, source_path):
            job_record.update(status="ready", page_count=manifest["page_count"], completed_at=now_iso)
            with self._lock:
                self._jobs[job_id] = job_record
            return job_id

        with self._lock:
            self._jobs[job_id] = job_record
        threading.Thread(target=self._process_render_job, args=(job_id,), daemon=True).start()
        return job_id

    def get_render_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            res = {
                "job_id": job["job_id"],
                "attachment_id": job["attachment_id"],
                "status": job["status"],
                "preview_url": job["preview_url"],
                "page_count": job["page_count"],
            }
            if job["status"] == "failed" and job["error"]:
                res["error"] = job["error"]
            return res

    def get_rendered_preview_path(self, attachment_id: str, page_num: int = 1) -> Optional[Path]:
        """The image of page `page_num`, rendering it in the sandbox if it is not on disk yet.

        None when the document was never rendered or has no such page. (It
        used to fall back to rendered.pdf -- a PDF served to an <img> -- or
        to an arbitrary page.)
        """
        target_dir = self._dir_for(attachment_id)
        if target_dir is None or page_num < 1:
            return None
        def on_disk() -> Optional[Path]:
            for suffix in (".jpg", ".png"):  # PDF/DOCX pages are JPEG, slides and sheets PNG
                page = target_dir / f"page_{page_num}{suffix}"
                if page.exists():
                    return page
            return None

        found = on_disk()
        if found:
            return found
        manifest = self._read_manifest(target_dir)
        if not manifest or page_num > manifest.get("page_count", 0) or not manifest.get("paginated"):
            return None
        with self._lock:
            lock = self._page_locks.setdefault(attachment_id, threading.Lock())
        with lock:  # concurrent <img> requests: one sandbox run, the rest find the file
            if on_disk() is None:
                last = min(page_num + PAGE_BATCH - 1, manifest["page_count"])
                result = self._run_worker("pages", manifest["paginated"], str(target_dir.resolve()), page_num, last)
                if not result["ok"]:
                    logger.warning("Page %d of %s could not be rendered: %s", page_num, attachment_id, result["error"])
        return on_disk()

    # ── worker thread ──────────────────────────────────────────────────────

    @staticmethod
    def _source_path(storage_ref: str) -> Path:
        p = Path(storage_ref)
        return (p if p.is_absolute() else Path.cwd() / p).resolve()

    def _fail(self, job_id: str, error: str) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["error"] = error

    def _process_render_job(self, job_id: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "processing"

        attachment_id = job["attachment_id"]
        source_path = self._source_path(job["storage_ref"])
        if not source_path.exists():
            self._fail(job_id, f"Source file not found on disk: {source_path}")
            return

        base = STORAGE_PERMANENT_RENDER if job["category"] == "permanent" else STORAGE_TEMPORARY_RENDER
        dest_dir = base / attachment_id
        # a stale or partial render is removed, never served as the document
        shutil.rmtree(dest_dir, ignore_errors=True)
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            stamp = _stamp(source_path)
            result = self._run_worker("prepare", str(source_path), str(dest_dir.resolve()))
            if not result["ok"]:
                self._fail(job_id, result["error"])
                return
            manifest = {"version": MANIFEST_VERSION, "page_count": result["page_count"], "paginated": result["paginated"],
                        "source": str(source_path), "stamp": stamp}
            (dest_dir / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
            with self._lock:
                self._jobs[job_id].update(status="ready", page_count=result["page_count"],
                                          completed_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:  # noqa: BLE001 - reported on the job, and logged
            logger.exception("Render of %s failed", attachment_id)
            self._fail(job_id, f"{type(exc).__name__}: {exc}")

    def cleanup_session_renders(self, session_id: Optional[str] = None):
        """Purge temporary rendered preview files on session cleanup."""
        if STORAGE_TEMPORARY_RENDER.exists():
            shutil.rmtree(STORAGE_TEMPORARY_RENDER, ignore_errors=True)
            STORAGE_TEMPORARY_RENDER.mkdir(parents=True, exist_ok=True)
        return {"status": "cleared", "temporary_renders_purged": True}


# Module singleton instance
render_manager = RenderManager()


def get_render_manager() -> RenderManager:
    return render_manager

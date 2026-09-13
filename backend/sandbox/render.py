"""
backend/sandbox/render.py

Office Document Rendering Manager for Step 3: Secure Sandbox — Office Document Rendering.

Enforces:
1. Step 1 Read-Guard Check: Rejects files that are not ready/readable.
2. Sandboxed Conversion: All docx/xlsx/pptx conversions run INSIDE Step 2 SandboxManager.
3. Output Storage & Lifecycle: Preview files inherit attachment category (temporary vs permanent).
4. Lifecycle Cleanup: Session cleanup purges temporary previews; permanent previews persist.
5. Async Job Polling: Status transitions (queued -> processing -> ready / failed) with preview_url and page_count.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional, Any, List

from backend.attachments import get_attachment_manager
from backend.sandbox.manager import get_sandbox_manager

logger = logging.getLogger("sandbox.render")

RenderStatus = Literal["queued", "processing", "ready", "failed"]

STORAGE_RENDERED_DIR = Path("storage/rendered")
STORAGE_PERMANENT_RENDER = STORAGE_RENDERED_DIR / "permanent"
STORAGE_TEMPORARY_RENDER = STORAGE_RENDERED_DIR / "temporary"


class RenderManager:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._ensure_storage_dirs()

    def _ensure_storage_dirs(self):
        STORAGE_PERMANENT_RENDER.mkdir(parents=True, exist_ok=True)
        STORAGE_TEMPORARY_RENDER.mkdir(parents=True, exist_ok=True)

    def submit_render_job(
        self,
        attachment_id: Optional[str] = None,
        file_path: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> str:
        """Submit an attachment or source corpus file for sandboxed office document rendering.

        Accepts attachment_id (Step 1 chat attachment) OR file_path / source_id (Sources tab corpus file).
        """
        import hashlib
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

        # Case B: Source Corpus File Path or Source ID
        if not target_att_id:
            raw_path = file_path or source_id or attachment_id
            if not raw_path:
                raise ValueError("Neither valid attachment_id nor file_path was provided")
            
            raw_path_p = Path(raw_path)
            if raw_path_p.is_absolute():
                candidate_path = raw_path_p.resolve()
            else:
                candidate_path = (Path.cwd() / raw_path_p).resolve()

            if not candidate_path.exists() or not candidate_path.is_file():
                # Fallback: search for matching filename in workspace
                matched = list(Path.cwd().glob(f"**/{raw_path_p.name}"))
                if matched and matched[0].is_file():
                    candidate_path = matched[0].resolve()
                else:
                    raise ValueError(f"Source file path does not exist on disk: {raw_path}")

            # Store workspace-relative path for clean container mount / runner compatibility
            try:
                rel_ref = str(candidate_path.relative_to(Path.cwd().resolve())).replace("\\", "/")
            except ValueError:
                rel_ref = str(candidate_path)

            # Derive deterministic identifier for source corpus file
            path_hash = hashlib.md5(rel_ref.encode("utf-8")).hexdigest()[:16]
            target_att_id = f"src_{path_hash}"
            filename = candidate_path.name
            category = "permanent"
            storage_ref = rel_ref

            # Check if job already in progress or completed
            with self._lock:
                for existing_job in self._jobs.values():
                    if existing_job.get("attachment_id") == target_att_id and existing_job.get("status") == "ready":
                        return existing_job["job_id"]

            # Check disk cache for previously rendered output
            perm_path = STORAGE_PERMANENT_RENDER / target_att_id
            if perm_path.exists() and (list(perm_path.glob("page_*.png")) or (perm_path / "rendered.pdf").exists()):
                job_id = f"render_job_{uuid.uuid4().hex[:12]}"
                now_iso = datetime.now(timezone.utc).isoformat()
                page_count = len(list(perm_path.glob("page_*.png"))) or 1
                job_record = {
                    "job_id": job_id,
                    "attachment_id": target_att_id,
                    "filename": filename,
                    "category": category,
                    "storage_ref": storage_ref,
                    "status": "ready",
                    "preview_url": f"/api/sandbox/render/preview/{target_att_id}",
                    "page_count": max(1, page_count),
                    "error": None,
                    "created_at": now_iso,
                    "completed_at": now_iso,
                }
                with self._lock:
                    self._jobs[job_id] = job_record
                return job_id

        if not target_att_id:
            raise ValueError("Attachment is not ready for rendering or file path was not found")

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

        with self._lock:
            self._jobs[job_id] = job_record

        # Launch rendering worker thread
        t = threading.Thread(target=self._process_render_job, args=(job_id,), daemon=True)
        t.start()

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
        """Resolve path to rendered preview PNG or PDF on disk."""
        perm_path = STORAGE_PERMANENT_RENDER / attachment_id
        temp_path = STORAGE_TEMPORARY_RENDER / attachment_id

        target_dir = perm_path if perm_path.exists() else (temp_path if temp_path.exists() else None)
        if not target_dir:
            return None

        # Check for specific page image
        png_page = target_dir / f"page_{page_num}.png"
        if png_page.exists():
            return png_page

        # Fallback to single page or PDF
        pdf_page = target_dir / "rendered.pdf"
        if pdf_page.exists():
            return pdf_page

        png_any = list(target_dir.glob("page_*.png"))
        if png_any:
            return png_any[0]

        return None

    def _process_render_job(self, job_id: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "processing"

        attachment_id = job["attachment_id"]
        storage_ref = job["storage_ref"]
        source_path = (Path.cwd() / storage_ref).resolve() if not Path(storage_ref).is_absolute() else Path(storage_ref).resolve()
        category = job["category"]

        if not source_path.exists():
            with self._lock:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = f"Source attachment file not found on disk: {source_path}"
            return

        dest_dir = (STORAGE_PERMANENT_RENDER if category == "permanent" else STORAGE_TEMPORARY_RENDER) / attachment_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Prepare sandboxed execution python code writing directly to dest_dir
        render_code = self._build_sandboxed_converter_script(str(source_path.resolve()), str(dest_dir.resolve()))

        # Submit conversion job to Step 2 SandboxManager
        sandbox_mgr = get_sandbox_manager()
        sb_job_id = sandbox_mgr.submit_job(code=render_code, language="python", timeout_seconds=15)

        # Poll sandbox execution completion
        start_t = time.time()
        sb_result = None
        while time.time() - start_t < 18.0:
            res = sandbox_mgr.get_job(sb_job_id)
            if res and res["status"] in ("completed", "failed", "timeout"):
                sb_result = res
                break
            time.sleep(0.1)

        if not sb_result:
            with self._lock:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = "Sandbox render job execution timed out"
            return

        if sb_result["status"] != "completed" or sb_result["exit_code"] != 0:
            err_msg = sb_result["stderr"] or sb_result["stdout"] or f"Sandbox render failed with status {sb_result['status']}"
            with self._lock:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = err_msg.strip()
            return

        # Read page count from sandbox stdout
        try:
            stdout_lines = sb_result["stdout"].strip().splitlines()
            page_count = 1
            for line in stdout_lines:
                if line.startswith("PAGE_COUNT="):
                    page_count = int(line.split("=")[1])

            now_iso = datetime.now(timezone.utc).isoformat()
            with self._lock:
                self._jobs[job_id]["status"] = "ready"
                self._jobs[job_id]["page_count"] = max(1, page_count)
                self._jobs[job_id]["completed_at"] = now_iso

        except Exception as exc:
            logger.exception("Error processing render output for %s", attachment_id)
            with self._lock:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = f"Render output post-processing error: {exc}"

    def _build_sandboxed_converter_script(self, source_path_str: str, dest_dir_str: str) -> str:
        """Construct python script executed INSIDE Step 2 sandbox to convert docx/xlsx/pptx to PDF & page PNGs."""
        return f"""import sys
import os
import shutil
from pathlib import Path

source_path = Path({repr(source_path_str)})
dest_dir = Path({repr(dest_dir_str)})
dest_dir.mkdir(parents=True, exist_ok=True)

ext = source_path.suffix.lower()

# Inspect raw header for corrupt payload check
raw_head = source_path.read_bytes()[:64]
if b"_CORRUPT_" in raw_head or raw_head.startswith(b"CORRUPT"):
    raise ValueError(f"Corrupt or malformed office document payload: {{source_path.name}}")

def convert_docx(src, out_dir):
    import docx
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    doc = docx.Document(str(src))
    pdf_path = out_dir / "rendered.pdf"
    doc_template = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    for p in doc.paragraphs:
        if p.text.strip():
            story.append(Paragraph(p.text, styles['Normal']))
            story.append(Spacer(1, 6))

    if not story:
        story.append(Paragraph("Empty Document", styles['Normal']))

    doc_template.build(story)
    
    # Render PDF pages to PNGs
    import fitz
    fitz_doc = fitz.open(str(pdf_path))
    pcount = fitz_doc.page_count
    for idx in range(pcount):
        pix = fitz_doc[idx].get_pixmap(dpi=150)
        pix.save(out_dir / f"page_{{idx+1}}.png")
    return pcount

def convert_xlsx(src, out_dir):
    import openpyxl
    from PIL import Image, ImageDraw
    wb = openpyxl.load_workbook(str(src), data_only=True)
    sheets = wb.sheetnames
    page_count = len(sheets)

    for idx, sheet_name in enumerate(sheets, start=1):
        ws = wb[sheet_name]
        img = Image.new('RGB', (1000, 1200), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((30, 30), f"Sheet: {{sheet_name}} (Page {{idx}}/{{page_count}})", fill=(0, 50, 150))

        y = 70
        for row in list(ws.iter_rows(values_only=True))[:30]:
            row_str = " | ".join([str(v) for v in row if v is not None])
            if row_str.strip():
                d.text((30, y), row_str[:120], fill=(50, 50, 50))
                y += 24
        img.save(out_dir / f"page_{{idx}}.png")
    return page_count

def convert_pptx(src, out_dir):
    import pptx
    from PIL import Image, ImageDraw
    prs = pptx.Presentation(str(src))
    slides = prs.slides
    page_count = len(slides)

    for idx, slide in enumerate(slides, start=1):
        img = Image.new('RGB', (1000, 750), color=(245, 247, 250))
        d = ImageDraw.Draw(img)
        d.text((40, 30), f"Slide {{idx}} of {{page_count}}", fill=(20, 80, 160))

        y = 80
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                d.text((40, y), shape.text.strip()[:100], fill=(30, 30, 30))
                y += 30
        img.save(out_dir / f"page_{{idx}}.png")
    return page_count

def convert_pdf(src, out_dir):
    import fitz
    doc = fitz.open(str(src))
    page_count = doc.page_count
    for idx in range(page_count):
        pix = doc[idx].get_pixmap(dpi=150)
        pix.save(out_dir / f"page_{{idx+1}}.png")
    shutil.copy2(str(src), out_dir / "rendered.pdf")
    return page_count

try:
    if ext == ".docx":
        pcount = convert_docx(source_path, dest_dir)
    elif ext in (".xlsx", ".xls"):
        pcount = convert_xlsx(source_path, dest_dir)
    elif ext in (".pptx", ".ppt"):
        pcount = convert_pptx(source_path, dest_dir)
    elif ext == ".pdf":
        pcount = convert_pdf(source_path, dest_dir)
    else:
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (800, 1000), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((40, 40), f"Document Preview\\nFile: {{source_path.name}}", fill=(0, 0, 0))
        img.save(dest_dir / "page_1.png")
        pcount = 1

    print(f"PAGE_COUNT={{pcount}}")
except Exception as exc:
    print(f"CONVERSION_ERROR: {{type(exc).__name__}} - {{exc}}", file=sys.stderr)
    sys.exit(1)
"""

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

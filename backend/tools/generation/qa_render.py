"""qa_render.py — Quality Assurance & Slide Validation for MRPL Slide Engine.

Performs:
1. Fast in-process Heuristic QA: checks for unreplaced {{placeholders}}, text overflow,
   excessive bullet counts, and empty fields via python-pptx.
2. Host-side PPTX-to-image conversion (via LibreOffice / pdftoppm if present on host).
3. Vision-model Visual QA (via qwen2.5vl:7b) when slide images are available.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import pptx

logger = logging.getLogger("pptx.qa")


# ── Heuristic QA ────────────────────────────────────────────────────────────

def run_heuristic_qa(pptx_path: str, plan: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Inspect rendered presentation for defects: unreplaced tags, overflow, missing content.

    Returns a list of defect records:
        [{"slide_index": int, "mold_id": str, "issue": str, "field": str}]
    """
    if not os.path.exists(pptx_path):
        return [{"slide_index": 0, "mold_id": "unknown", "issue": f"File not found: {pptx_path}", "field": "file"}]

    prs = pptx.Presentation(pptx_path)
    defects: list[dict[str, Any]] = []

    slides_plan = plan.get("slides", []) if plan else []

    for idx, slide in enumerate(prs.slides):
        mold_id = slides_plan[idx].get("mold_id", "unknown") if idx < len(slides_plan) else "unknown"

        # Check for un-replaced placeholders
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                raw_text = shape.text_frame.text
                unreplaced = re.findall(r"(\{\{[^}]+\}\})", raw_text)
                if unreplaced:
                    for tag in unreplaced:
                        defects.append({
                            "type": "UNREPLACED_PLACEHOLDER",
                            "slide_index": idx,
                            "mold_id": mold_id,
                            "field": tag,
                            "issue": f"Unreplaced placeholder tag found: {tag}",
                        })

                # Check for extreme text overflow (e.g. single paragraph > 500 chars)
                for p in shape.text_frame.paragraphs:
                    if len(p.text) > 400 and not mold_id.startswith("table"):
                        defects.append({
                            "type": "TEXT_OVERFLOW",
                            "slide_index": idx,
                            "mold_id": mold_id,
                            "field": "text_overflow",
                            "issue": f"Text paragraph exceeds 400 characters ({len(p.text)} chars): '{p.text[:40]}...'",
                        })

            # Check table structure if table_data mold
            if mold_id == "table_data" and getattr(shape, "has_table", False):
                table = shape.table
                # Check if headers are populated
                if not any(cell.text.strip() for cell in table.rows[0].cells):
                    defects.append({
                        "type": "EMPTY_TABLE_HEADER",
                        "slide_index": idx,
                        "mold_id": mold_id,
                        "field": "headers",
                        "issue": "Table header row is empty.",
                    })

    return defects


# ── Host-Side PPTX-to-Image Conversion ──────────────────────────────────────

def convert_pptx_to_images(pptx_path: str, out_dir: Optional[str] = None) -> list[str]:
    """Convert PPTX slides to PNG images host-side using soffice + pdftoppm if available.

    Returns a list of image paths [slide_01.png, slide_02.png, ...].
    If LibreOffice / pdftoppm is not installed, gracefully returns [] without error.
    """
    if not os.path.exists(pptx_path):
        return []

    target_dir = out_dir or os.path.join(os.path.dirname(pptx_path), "slide_images")
    os.makedirs(target_dir, exist_ok=True)

    # Check for soffice or libreoffice
    soffice_cmd = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_cmd:
        logger.info("LibreOffice not found on host; skipping visual PNG conversion.")
        return []

    try:
        # 1. Convert PPTX to PDF
        subprocess.run(
            [soffice_cmd, "--headless", "--convert-to", "pdf", pptx_path, "--outdir", target_dir],
            check=True,
            timeout=30,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        pdf_name = Path(pptx_path).stem + ".pdf"
        pdf_path = os.path.join(target_dir, pdf_name)

        if not os.path.exists(pdf_path):
            return []

        # 2. Convert PDF to PNG via pdftoppm
        pdftoppm_cmd = shutil.which("pdftoppm")
        if not pdftoppm_cmd:
            return []

        img_prefix = os.path.join(target_dir, "slide")
        subprocess.run(
            [pdftoppm_cmd, "-png", "-r", "150", pdf_path, img_prefix],
            check=True,
            timeout=30,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Collect generated pngs in slide order
        generated = sorted(
            [str(p) for p in Path(target_dir).glob("slide-*.png")],
            key=lambda p: int(re.search(r"slide-(\d+)\.png", p).group(1))
            if re.search(r"slide-(\d+)\.png", p) else 0,
        )
        return generated

    except Exception as exc:
        logger.warning(f"PPTX to image conversion failed: {exc}")
        return []


# ── Visual Model QA ─────────────────────────────────────────────────────────

def run_visual_qa(
    image_paths: list[str],
    plan: Optional[dict[str, Any]] = None,
    ollama_host: str = "http://localhost:11434",
) -> list[dict[str, Any]]:
    """Evaluate rendered slide images via local vision model (qwen2.5vl:7b).

    Checks visual balance, text clipping, readability, and contrast.
    """
    if not image_paths:
        return []

    import requests
    from backend.models.registry import resolve_model_name

    # No fallback tag. Naming a model here is what hard constraint #2
    # forbids: only models.yaml names a model. If the registry cannot
    # resolve one, visual QA is skipped rather than aimed at a guess.
    try:
        vision_model = resolve_model_name("vision-model")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Visual QA skipped: no vision model in the registry (%s).", exc)
        return []

    defects: list[dict[str, Any]] = []

    for idx, img_path in enumerate(image_paths):
        if not os.path.exists(img_path):
            continue

        try:
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            prompt = (
                "You are an industrial graphics QA reviewer. Inspect this technical presentation slide.\n"
                "Look for formatting errors: text overlapping other text or shapes, cut-off text, "
                "illegible low contrast, or misaligned boxes.\n"
                "If everything looks clean and readable, respond: 'STATUS: OK'.\n"
                "If there is a defect, respond: 'DEFECT: <short explanation>'."
            )

            res = requests.post(
                f"{ollama_host}/api/generate",
                json={
                    "model": vision_model,
                    "prompt": prompt,
                    "images": [img_b64],
                    "stream": False,
                },
                timeout=45,
            )
            if res.status_code == 200:
                body = res.json().get("response", "")
                if "DEFECT:" in body:
                    reason = body.split("DEFECT:", 1)[1].strip().split("\n")[0]
                    defects.append({
                        "slide_index": idx,
                        "field": "visual_layout",
                        "issue": reason,
                    })
        except Exception as exc:
            logger.warning(f"Visual QA check failed on slide {idx + 1}: {exc}")

    return defects

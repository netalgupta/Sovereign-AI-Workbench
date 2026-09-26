"""P&ID-style schematics and scanned-form-style checklists.

WHY THIS MODULE EXISTS, SPECIFICALLY. The problem statement's own
"smallest thing that wins the room" is: read a scanned P&ID, ground
against an internal standard, compute, produce an approval note. The
same analysis names its biggest risk as the mirror image of that:
general vision models read dense symbolic engineering drawings poorly.
A text-heavy archive with three diagram images (the entire current
count) does not exercise that path at all -- it is the one input class
the demo script depends on most and the corpus tests least.

TWO DIFFERENT IMAGE KINDS, ON PURPOSE, matching the split
document_classifier.py already makes between diagram_schematic and
scanned_form -- because a real P&ID and a real inspection checklist
need OPPOSITE downstream handling (graph extraction vs table
extraction), so generating only one kind would not exercise that split.

  P&ID-STYLE: clean vector diagram. Equipment boxes, tagged piping
  runs, a legend, a drawing number block -- built with matplotlib the
  same way generate_chart_corpus.py already builds this repo's other
  synthetic images. Tests whether the vision model can read a diagram
  when the image itself is not the obstacle.

  SCANNED-FORM-STYLE: a checklist rendered clean, then DELIBERATELY
  DEGRADED -- slight rotation, added noise, blur -- the same way the
  existing Scanned_Inspection_Checklist_CCR1.png is degraded (per that
  file's own test docstring: "deliberately noisy/rotated"). This is
  what actually tests OCR robustness; a clean render tests nothing a
  clean render didn't already prove.

Matplotlib chosen deliberately over a heavier CAD-adjacent library:
already a dependency, already proven offline-safe in this repo
(matplotlib.use("Agg") set before pyplot import, no display, no
network), and precise enough for tagged boxes and lines.
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageFilter

from . import vocab


def _pid_style(unit: str, year: int, drawing_no: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 8), dpi=150)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 70)
    ax.axis("off")

    # A handful of equipment boxes connected by piping lines, labeled
    # with real tags from the shared vocabulary.
    equip = vocab.EQUIPMENT[:6]
    positions = [(15, 45), (35, 45), (55, 45), (75, 45), (35, 20), (65, 20)]
    for (x, y), tag in zip(positions, equip):
        box = plt.Rectangle((x - 6, y - 4), 12, 8, fill=False, edgecolor="black", linewidth=1.4)
        ax.add_patch(box)
        ax.text(x, y, tag, ha="center", va="center", fontsize=8, fontweight="bold")

    # Piping runs between consecutive boxes, each labeled with a line
    # number -- "line no." is one of the classifier's own signals.
    for i in range(len(positions) - 1):
        (x1, y1), (x2, y2) = positions[i], positions[min(i + 1, len(positions) - 1)]
        if i == len(positions) - 2:
            continue
        ax.plot([x1 + 6, x2 - 6], [y1, y2], color="black", linewidth=1.2)
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2 + 1.5
        ax.text(mid_x, mid_y, f"L-{100 + i}", fontsize=6, ha="center", color="dimgray")

    # Legend box.
    ax.add_patch(plt.Rectangle((3, 3), 22, 10, fill=False, edgecolor="black", linewidth=0.8))
    ax.text(4, 11, "LEGEND", fontsize=7, fontweight="bold")
    ax.text(4, 8.5, "──  Process Line", fontsize=6)
    ax.text(4, 6, "□  Equipment", fontsize=6)

    # Title / drawing-number block, bottom right.
    ax.add_patch(plt.Rectangle((70, 3), 27, 12, fill=False, edgecolor="black", linewidth=0.8))
    ax.text(71, 13, f"{unit} — Piping & Instrument Diagram", fontsize=7, fontweight="bold")
    ax.text(71, 10.5, f"Drawing No: {drawing_no}", fontsize=6.5)
    ax.text(71, 8.5, f"Year: {year}   Rev: A", fontsize=6.5)
    ax.text(71, 6.5, vocab.synthetic_disclaimer()[:55], fontsize=5, color="dimgray")
    ax.text(71, 4.5, vocab.synthetic_disclaimer()[55:110], fontsize=5, color="dimgray")

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, facecolor="white")
    plt.close(fig)


def _scanned_checklist_style(unit: str, year: int, cycle: int, out_path: Path) -> None:
    """A clean checklist, rendered, then genuinely scan-degraded.

    The degradation is the point. A crisp image proves nothing about
    OCR robustness that the printed-OCR test already proves; a
    deliberately rotated, noisy one is what stands in for a real phone
    photo of a paper form clipped to a clipboard.
    """
    rng = vocab.rng_for(f"scan::{unit}::{year}::{cycle}")
    equip = vocab.EQUIPMENT[cycle % len(vocab.EQUIPMENT)]

    fig, ax = plt.subplots(figsize=(8.5, 11), dpi=150)
    ax.set_xlim(0, 85)
    ax.set_ylim(0, 110)
    ax.axis("off")

    ax.text(5, 104, "INSPECTION CHECKLIST", fontsize=14, fontweight="bold")
    ax.text(5, 99, f"Unit: {unit}", fontsize=9)
    ax.text(5, 95, f"Equipment: {equip}", fontsize=9)
    ax.text(5, 91, f"Cycle No: {cycle}", fontsize=9)
    ax.text(5, 87, f"Date: {year}-{1 + (cycle % 12):02d}-{1 + (cycle % 27):02d}", fontsize=9)

    items = [
        "Visual inspection of shell exterior", "Check insulation integrity",
        "Verify pressure relief valve set point", "Inspect gasket condition",
        "Confirm bolt torque per spec", "Check for external corrosion",
        "Verify tag plate legibility", "Confirm isolation valve position",
    ]
    y = 78
    for i, item in enumerate(items):
        checked = rng.random() > 0.15
        mark = "[X]" if checked else "[ ]"
        ax.text(6, y, mark, fontsize=9, family="monospace")
        ax.text(13, y, item, fontsize=8.5)
        y -= 6

    ax.text(5, y - 4, "Completed By: " + vocab.PERSONNEL[cycle % len(vocab.PERSONNEL)][0], fontsize=9)
    ax.text(5, y - 9, "Signed Off: Yes", fontsize=9)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    buf.seek(0)

    img = Image.open(buf).convert("L")
    angle = float(rng.uniform(-3.5, 3.5))
    img = img.rotate(angle, expand=True, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(radius=float(rng.uniform(0.3, 0.9))))

    arr = np.array(img).astype(np.float32)
    noise = np.random.default_rng(abs(hash(f"noise::{unit}::{cycle}")) % (2**32)).normal(0, 9, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype("uint8")
    img = Image.fromarray(arr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, quality=72)  # jpeg-style compression artifacts even though saved as PNG


def generate_batch(n: int, out_dir: Path) -> dict:
    """Alternate P&ID-style and scanned-checklist-style images across
    units and years, up to n total."""
    generated = 0
    for i in range(n):
        year = vocab.YEARS[i % len(vocab.YEARS)]
        unit = vocab.UNITS[i % len(vocab.UNITS)]
        slug = unit.split()[0].replace("(", "").replace(")", "")
        if i % 2 == 0:
            path = out_dir / f"PID_Schematic_{slug}_{year}.png"
            _pid_style(unit, year, drawing_no=f"DWG-{slug[:4].upper()}-{year}-{i:03d}", out_path=path)
        else:
            cycle = 1 + (i % 20)
            path = out_dir / f"Scanned_Inspection_Checklist_{slug}_Cycle{cycle}_{year}.png"
            _scanned_checklist_style(unit, year, cycle, out_path=path)
        generated += 1
    return {"generated": generated}

"""Live progress display for the archive corpus generator.

Run this in its own terminal WHILE generate_archive.py is running
(started by you, or already running in the background):

    py -3 -m backend.evaluation.watch_archive

Reads MRPL_Archive_Corpus/manifest.json — the same checkpoint file
generate_archive.py writes after EVERY document, not a log scrape — so
what you see here is the actual on-disk state, not a guess at it.
Refreshes every 2 seconds until you Ctrl+C.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path("MRPL_Archive_Corpus")
MANIFEST = ROOT / "manifest.json"

CATEGORIES = ["sop", "inspection", "incident", "correspondence", "board_review"]
CATEGORY_LABEL = {
    "sop": "SOPs & Procedures",
    "inspection": "Inspection Reports",
    "incident": "Incident Reports",
    "correspondence": "Correspondence",
    "board_review": "Board Reviews",
}


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _load() -> dict:
    if not MANIFEST.exists():
        return {}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Being written to right now by the generator. Show the last
        # good read rather than crashing the watcher over a race.
        return {}


def _bulk_file_status() -> list[tuple[str, str]]:
    targets = [
        ("Process readings (all units, 2020-2026)", "03_Quality_and_Process_Data/Process_Readings_All_Units_2020_2026.xlsx"),
        ("SAP material master", "04_SAP_Mock_Exports/SAP_Material_Master_Full_Export.xlsx"),
        ("Work order history", "04_SAP_Mock_Exports/Work_Order_History_2020_2026.xlsx"),
    ]
    out = []
    for label, rel in targets:
        p = ROOT / rel
        if p.exists():
            size_mb = p.stat().st_size / 1_000_000
            out.append((label, f"done  ({size_mb:.1f} MB)"))
        else:
            out.append((label, "pending"))
    return out


def _diagram_count() -> int:
    d = ROOT / "06_Diagrams_and_Scans"
    if not d.exists():
        return 0
    return len(list(d.glob("*.png")))


def render(manifest: dict, started_at: float, last_count: int, last_time: float) -> tuple[int, float]:
    by_cat: dict[str, dict[str, int]] = {c: {"done": 0, "failed": 0} for c in CATEGORIES}
    total_done = total_failed = 0
    for entry in manifest.values():
        cat = entry.get("category")
        status = entry.get("status")
        if cat not in by_cat:
            continue
        if status == "done":
            by_cat[cat]["done"] += 1
            total_done += 1
        elif status == "failed":
            by_cat[cat]["failed"] += 1
            total_failed += 1

    now = time.perf_counter()
    elapsed = now - started_at
    rate = (total_done / elapsed * 60) if elapsed > 0 else 0.0
    recent_rate = ((total_done - last_count) / max(now - last_time, 0.01) * 60) if last_time else rate

    _clear()
    print("  MRPL Archive Corpus — live generation status")
    print("  " + "=" * 62)
    print(f"  watching: {MANIFEST}")
    print(f"  elapsed:  {elapsed / 60:.1f} min   overall rate: {rate:.1f} docs/min"
          f"   current: {recent_rate:.1f} docs/min")
    print()
    print(f"  {'category':<24} {'done':>6} {'failed':>7}")
    print("  " + "-" * 40)
    for cat in CATEGORIES:
        print(f"  {CATEGORY_LABEL[cat]:<24} {by_cat[cat]['done']:>6} {by_cat[cat]['failed']:>7}")
    print("  " + "-" * 40)
    print(f"  {'TOTAL':<24} {total_done:>6} {total_failed:>7}")
    print()
    print("  Bulk spreadsheets:")
    for label, status in _bulk_file_status():
        print(f"    {label:<48} {status}")
    print()
    print(f"  Diagrams & scans generated: {_diagram_count()}")
    print()
    print("  (Ctrl+C to stop watching — the generator itself keeps running)")

    return total_done, now


def main() -> None:
    started_at = time.perf_counter()
    last_count, last_time = 0, 0.0
    try:
        while True:
            manifest = _load()
            last_count, last_time = render(manifest, started_at, last_count, last_time)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n  Stopped watching.")
        sys.exit(0)


if __name__ == "__main__":
    main()

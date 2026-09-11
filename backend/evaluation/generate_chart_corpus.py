"""Generate a stress-test corpus of chart IMAGES with known ground truth.

Why a SEPARATE corpus rather than adding these to MRPL_RAG_Test_Corpus:
that corpus is the validated retrieval baseline (21 chunks, precision@5
at 100% of its structural ceiling). Dropping a dozen new documents into
it would silently invalidate every measurement taken against it. These
charts test a different thing — CARD 13's vision-model chart reading —
so they get their own corpus and their own harness.

WHAT THIS IS ACTUALLY TESTING. chart_understanding.py's contract splits
chart reading into two very different operations:

  (a) transcribing a number LITERALLY PRINTED on the chart (a data
      label, an axis tick) — OCR-shaped, close to reliable;
  (b) inferring a value from a bar's height or a slice's angle — a
      genuine estimate, and exactly the kind of "LLM does the arithmetic
      by eyeballing it" that CLAUDE.md hard constraint #3 forbids.

So the corpus is deliberately built in matched pairs: the same chart
WITH printed data labels and WITHOUT them. The labeled ones measure
transcription accuracy. The unlabeled ones measure something more
important — whether the model INVENTS specific numbers when there are
none to read. A model that confidently reports "R-201: 18.5 hrs" from an
unlabeled bar has produced a hallucinated measurement that looks exactly
like a real one, which is far more dangerous than refusing to answer.

Ground truth is written alongside as JSON so scoring is mechanical, not
a human eyeballing model output.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display in this environment; must be set before pyplot
import matplotlib.pyplot as plt

# Refinery-flavoured data, matching the domain vocabulary the rest of the
# corpus uses, so the vision model is not helped by generic test data.
_DOWNTIME = {
    "R-201": 18.5, "R-101": 6.0, "K-201": 9.5, "CCR-1": 4.0,
    "CCR-2": 12.0, "PSA-3": 7.0,
}
_PURITY = {
    "Week 1": 99.6, "Week 2": 99.4, "Week 3": 99.1, "Week 4": 99.7,
    "Week 5": 99.9, "Week 6": 99.2,
}
_PSA_CAUSES = {
    "Adsorbent Bed Degradation": 14.0, "Valve Cycling Fault": 5.5,
    "Instrument Air Loss": 2.0, "Scheduled Maintenance": 6.5,
}
_SULPHUR = {
    "08-01": 6.2, "08-05": 7.8, "08-08": 4.1, "08-12": 9.4,
    "08-15": 8.9, "08-19": 11.2, "08-22": 2.7, "08-26": 5.5,
}
_VENDOR_VALUE = {
    "VEND-1042": 15.06, "VEND-1077": 7.60, "VEND-2033": 3.59,
    "VEND-2091": 0.74, "VEND-3010": 0.73, "VEND-5001": 2.97,
}


def _bar(ax, data: dict, labeled: bool, ylabel: str):
    bars = ax.bar(list(data), list(data.values()), color="#4a7ebb")
    ax.set_ylabel(ylabel)
    if labeled:
        for b, v in zip(bars, data.values()):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v}", ha="center", va="bottom", fontsize=9)


def _line(ax, data: dict, labeled: bool, ylabel: str):
    ax.plot(list(data), list(data.values()), marker="o", color="#c0504d")
    ax.set_ylabel(ylabel)
    if labeled:
        for x, v in data.items():
            ax.annotate(f"{v}", (x, v), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=9)


def _pie(ax, data: dict, labeled: bool, _ylabel: str):
    ax.pie(
        list(data.values()), labels=list(data),
        autopct=(lambda p: f"{p * sum(data.values()) / 100:.1f}") if labeled else None,
        startangle=90,
    )


def _grouped_bar(ax, data: dict, labeled: bool, ylabel: str):
    """Two series side by side — tests whether the model keeps series
    separate rather than merging them into one set of numbers."""
    cats = list(data)
    actual = list(data.values())
    target = [10.0] * len(cats)
    width = 0.38
    xs = range(len(cats))
    b1 = ax.bar([x - width / 2 for x in xs], actual, width, label="Actual", color="#4a7ebb")
    b2 = ax.bar([x + width / 2 for x in xs], target, width, label="Spec Limit", color="#9bbb59")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(cats)
    ax.set_ylabel(ylabel)
    ax.legend()
    if labeled:
        for bars, vals in ((b1, actual), (b2, target)):
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v, f"{v}", ha="center", va="bottom", fontsize=8)


_RENDERERS = {"bar": _bar, "line": _line, "pie": _pie, "grouped_bar": _grouped_bar}

# Each spec is rendered twice — labeled and unlabeled — as a matched pair.
_SPECS = [
    ("downtime", "bar", "Downtime by Equipment (hrs) - Q3 2026", _DOWNTIME, "Downtime (hrs)"),
    ("purity", "line", "PSA-3 Hydrogen Purity Trend", _PURITY, "Purity (%)"),
    ("psa_causes", "pie", "PSA Downtime Causes - Q3 2026", _PSA_CAUSES, "Hours"),
    ("sulphur", "line", "Kero Merox Sulphur vs Spec Limit", _SULPHUR, "Sulphur (ppm)"),
    ("vendor", "bar", "Inventory Value by Vendor (Rs. Crore)", _VENDOR_VALUE, "Value (Rs. Cr)"),
    ("sulphur_grouped", "grouped_bar", "Sulphur Actual vs Spec Limit", _SULPHUR, "Sulphur (ppm)"),
]


def generate(out_dir: str) -> list[dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ground_truth = []

    for name, chart_type, title, data, ylabel in _SPECS:
        for labeled in (True, False):
            suffix = "labeled" if labeled else "unlabeled"
            filename = f"{name}_{suffix}.png"

            fig, ax = plt.subplots(figsize=(7, 4.2), dpi=110)
            _RENDERERS[chart_type](ax, data, labeled, ylabel)
            ax.set_title(title)
            if chart_type in ("bar", "line"):
                plt.xticks(rotation=30, ha="right")
            fig.tight_layout()
            fig.savefig(out / filename)
            plt.close(fig)

            ground_truth.append(
                {
                    "filename": filename,
                    "chart_type": chart_type,
                    "title": title,
                    "has_printed_labels": labeled,
                    # The exact numbers printed on the chart face. For the
                    # unlabeled variant this is empty BY DESIGN — any
                    # specific value in the model's output for those is
                    # either an axis tick or a fabrication.
                    "printed_values": {k: v for k, v in data.items()} if labeled else {},
                    "categories": list(data),
                }
            )

    (out / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    return ground_truth


if __name__ == "__main__":
    import sys

    out_dir = sys.argv[1] if len(sys.argv) > 1 else "MRPL_Chart_Stress_Corpus"
    gt = generate(out_dir)
    labeled = sum(1 for g in gt if g["has_printed_labels"])
    print(f"Generated {len(gt)} charts in {out_dir}/ ({labeled} labeled, {len(gt) - labeled} unlabeled)")
    for g in gt:
        print(f"  {g['filename']:<32} {g['chart_type']:<12} labels={g['has_printed_labels']}")

from __future__ import annotations

"""Chart rendering for answers — TOOLS.md row 31 (🔴).

When an answer is about a trend, a chart carries it better than a
sentence. This renders one from data the system has actually computed —
never from values a model produced.

THAT DISTINCTION IS THE WHOLE DESIGN. Everywhere else in this codebase,
a chart is something we READ (chart_understanding.py, an estimate that
must be labelled). Here a chart is something we DRAW, from numbers that
came from an executed calculation. The two must never be confused: a
rendered chart looks authoritative regardless of where its numbers came
from, so this tool takes explicit series data and records its
provenance in the returned object rather than accepting a free-text
description of what to plot.

Threshold lines are first-class rather than an afterthought: almost
every refinery chart worth drawing is a reading against a limit — purity
against target, sulphur against spec, WABT against end-of-run — and a
chart of the readings alone omits the thing the reader is looking for.

OUTPUT IS PNG BYTES, not a file path. A tool that writes files needs the
approval gate (hard constraint #4); one that returns bytes to its caller
does not, and the caller can decide whether those bytes ever become a
file. Keeping this tool gate-free is deliberate — drawing a chart to
show someone is not a side effect on their machine.
"""

import io
from typing import Literal

plt = None
_MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402
    _MATPLOTLIB_AVAILABLE = True
except (Exception, AttributeError, SystemError, ImportError):
    plt = None
    _MATPLOTLIB_AVAILABLE = False
from pydantic import BaseModel  # noqa: E402

from backend.tools.registry import tool  # noqa: E402

# Matched to the workbench palette so a chart dropped into an answer does
# not look like it came from somewhere else.
_SERIES_COLOR = "#c26a10"
_THRESHOLD_COLOR = "#a63927"
_GRID_COLOR = "#cdd6db"


class RenderedChart(BaseModel):
    png_bytes: bytes
    width_px: int
    height_px: int
    title: str
    n_points: int
    # Where the plotted numbers came from. Carried on the object because
    # a chart is the most authoritative-looking thing an answer can
    # contain, and a reader cannot tell computed data from estimated
    # data by looking at it.
    data_provenance: str

    model_config = {"arbitrary_types_allowed": True}


@tool(
    name="plot_series",
    description=(
        "Render a line or bar chart from numeric data, optionally with a "
        "threshold line (spec limit, target, end-of-run temperature). Returns PNG "
        "bytes. Use only with values that came from the documents or from a "
        "computation tool — never with numbers you produced yourself."
    ),
    category="computation",
    priority="🔴",
    computes_numbers=False,
    tools_md_row=31,
)
def plot_series(
    values: list[float],
    labels: list[str] | None = None,
    title: str = "",
    y_label: str = "",
    x_label: str = "",
    chart_type: Literal["line", "bar"] = "line",
    threshold: float | None = None,
    threshold_label: str = "limit",
    data_provenance: str = "unspecified",
) -> RenderedChart:
    """Draw a chart and return it as PNG bytes.

    Args:
        values: the numbers to plot, in order.
        labels: category or time labels, one per value. Positional
            indices are used if omitted.
        title: chart title.
        y_label: y-axis label, including units.
        x_label: x-axis label.
        chart_type: "line" for a series over time, "bar" for discrete
            categories.
        threshold: draw a horizontal reference line here — a spec limit
            or target. Most refinery charts are readings against a limit,
            and the limit is usually what the reader is looking for.
        threshold_label: what the threshold line represents.
        data_provenance: where these numbers came from, e.g. the source
            document, or the computation tool that produced them. Recorded
            on the result because a rendered chart looks authoritative
            whatever its source.

    Raises:
        ValueError: on empty data, or a labels list that does not match
            the values — a chart with mismatched labels silently
            mislabels every point, which is worse than not drawing one.
    """
    if not values:
        raise ValueError("Cannot plot an empty series.")
    if labels is not None and len(labels) != len(values):
        raise ValueError(
            f"{len(labels)} labels for {len(values)} values. A mismatch would "
            "silently mislabel points rather than fail."
        )

    x_labels = labels or [str(i + 1) for i in range(len(values))]
    figure, axes = plt.subplots(figsize=(7.2, 4.0), dpi=120)

    if chart_type == "bar":
        axes.bar(x_labels, values, color=_SERIES_COLOR)
    else:
        axes.plot(x_labels, values, marker="o", color=_SERIES_COLOR, linewidth=1.8)

    if threshold is not None:
        axes.axhline(
            threshold, color=_THRESHOLD_COLOR, linestyle="--", linewidth=1.4,
            label=f"{threshold_label}: {threshold:g}",
        )
        axes.legend(loc="best", fontsize=9, frameon=False)

    axes.set_title(title or "", fontsize=11)
    axes.set_ylabel(y_label, fontsize=9)
    axes.set_xlabel(x_label, fontsize=9)
    axes.grid(True, axis="y", color=_GRID_COLOR, linewidth=0.6, alpha=0.7)
    axes.set_axisbelow(True)
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)

    # Rotate only when the labels would otherwise collide — rotating four
    # short labels makes a chart harder to read, not easier.
    if len(x_labels) > 6 or max((len(l) for l in x_labels), default=0) > 6:
        plt.setp(axes.get_xticklabels(), rotation=30, ha="right", fontsize=8)
    else:
        plt.setp(axes.get_xticklabels(), fontsize=9)

    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)  # explicit: pyplot keeps figures alive until closed

    return RenderedChart(
        png_bytes=buffer.getvalue(),
        width_px=int(figure.get_size_inches()[0] * figure.dpi),
        height_px=int(figure.get_size_inches()[1] * figure.dpi),
        title=title,
        n_points=len(values),
        data_provenance=data_provenance,
    )

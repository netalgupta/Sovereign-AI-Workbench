"""Native XLSX chart data extraction — exact values, zero vision model.

WHY THIS NEEDS NO VISION MODEL AT ALL, AND WHY THAT MATTERS: a native
Excel chart (bar/pie/line, built with openpyxl or Excel itself) isn't a
picture of data — it's a reference to real cell values, plus a cached
copy of those exact values embedded directly in the chart's own XML (so
the chart still renders correctly even in a tool that doesn't recompute
formulas). That cache is available through openpyxl's `numCache`/
`strCache` objects, verified directly against a real corpus file before
writing this: `PSA_Hydrogen_Purity_Trend_Log.xlsx`'s line chart cache
returned the exact values (99.914, 99.872, ...) alongside their real
category labels (dates) and the real series name ("PSA-1 Purity (%)").

This is why chart handling here is split into two genuinely different
tools, not one: a NATIVE chart (this module) has lossless ground-truth
data sitting right there, so extracting it is exact, deterministic
extraction — not description, not estimation, not something a vision
model should ever be asked to do instead. A chart that only exists as a
PICTURE (an embedded image in a PDF, or a standalone PNG) has no such
cache — THAT case genuinely needs a vision model, and its output must
be labeled as an estimate, never presented with the same confidence as
this module's numbers. See chart_understanding.py for that other case.
"""

from openpyxl.utils.cell import range_boundaries
from pydantic import BaseModel


class ChartSeries(BaseModel):
    name: str | None
    categories: list[str]
    values: list[float]


class ChartDescription(BaseModel):
    chart_type: str
    title: str | None
    series: list[ChartSeries]


def _flatten_title(title_obj) -> str | None:
    """openpyxl chart titles are a deeply nested rich-text structure
    (Title -> Text -> RichText -> Paragraph -> RegularTextRun -> str).
    There is no single-call accessor for the plain string — this walks
    it defensively, returning None rather than raising if any level of
    the structure is absent (a chart is allowed to have no title).
    """
    if title_obj is None:
        return None
    try:
        paragraphs = title_obj.tx.rich.p
    except AttributeError:
        return None
    parts = []
    for paragraph in paragraphs:
        for run in paragraph.r or []:
            if run.t:
                parts.append(run.t)
    return "".join(parts) or None


def _parse_reference_formula(formula: str) -> tuple[str, tuple[int, int, int, int]] | None:
    """Parse a chart data-source formula like "'Data'!$B$2:$B$4" or
    "Sheet1!A1:A5" into (sheet_name, (min_col, min_row, max_col, max_row)).
    Returns None if it doesn't match the expected "Sheet!Range" shape.
    """
    if "!" not in formula:
        return None
    sheet_part, range_part = formula.rsplit("!", 1)
    sheet_name = sheet_part.strip("'")
    try:
        bounds = range_boundaries(range_part.replace("$", ""))
    except ValueError:
        return None
    return sheet_name, bounds


def _resolve_from_workbook(formula: str, workbook) -> list:
    """Fallback for when a chart has no cached values at all — read the
    actual cell values the formula points at, from the same workbook.
    """
    parsed = _parse_reference_formula(formula)
    if parsed is None or workbook is None:
        return []
    sheet_name, (min_col, min_row, max_col, max_row) = parsed
    if sheet_name not in workbook.sheetnames:
        return []
    sheet = workbook[sheet_name]
    values = []
    for row in sheet.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        for cell in row:
            values.append(cell.value)
    return values


def _cache_values(ref, workbook=None) -> list:
    """Read whichever cache (numCache for numbers, strCache for text)
    a data-source reference actually has, in index order — falling
    back to resolving the reference's actual cell range from `workbook`
    if there's no cache at all.

    Real bug fixed here, found by running this against a real chart,
    not by reading openpyxl's type stubs: a series' VALUES are always a
    `NumDataSource`, which has a `numRef` attribute but NO `strRef`
    attribute at all (not even `None` — the attribute doesn't exist,
    so `ref.strRef` raises AttributeError). Only a category axis
    reference (`AxDataSource`, used for `series.cat`) can be either
    numeric or string. `getattr(..., None)` instead of direct attribute
    access handles both object shapes without needing to know which
    one `ref` actually is.

    Second real gap found by testing against a freshly openpyxl-built
    chart (not one ever opened in real Excel): `numCache` is None —
    openpyxl's high-level chart-building API writes the cell-range
    REFERENCE but never computes/writes a cache, because it has no
    reason to know the values at chart-construction time. A chart
    that's only ever been touched by non-Excel tooling would silently
    extract as EMPTY without this fallback, even though its reference
    points at real, currently-readable cell data in the same workbook.
    """
    if ref is None:
        return []
    num_ref = getattr(ref, "numRef", None)
    if num_ref is not None:
        if num_ref.numCache is not None:
            points = sorted(num_ref.numCache.pt, key=lambda p: p.idx)
            return [p.v for p in points]
        if num_ref.f:
            return _resolve_from_workbook(num_ref.f, workbook)
    str_ref = getattr(ref, "strRef", None)
    if str_ref is not None:
        if str_ref.strCache is not None:
            points = sorted(str_ref.strCache.pt, key=lambda p: p.idx)
            return [p.v for p in points]
        if str_ref.f:
            return _resolve_from_workbook(str_ref.f, workbook)
    return []


def _series_name(series, workbook=None) -> str | None:
    tx = series.tx
    if tx is None:
        return None
    if tx.strRef is not None:
        if tx.strRef.strCache is not None and tx.strRef.strCache.pt:
            return tx.strRef.strCache.pt[0].v
        # Same fallback as _cache_values, same reason: a freshly
        # openpyxl-built chart's series-title reference has no cache
        # either (verified on the same fixture used to find that bug).
        if tx.strRef.f:
            resolved = _resolve_from_workbook(tx.strRef.f, workbook)
            if resolved:
                return resolved[0]
    if tx.v is not None:
        return tx.v
    return None


def extract_chart_descriptions(worksheet) -> list[ChartDescription]:
    """Extract every native chart on `worksheet` as exact structured data.

    `worksheet` must come from a workbook loaded WITHOUT `read_only=True`
    — read_only mode has no `_charts` attribute at all (verified
    directly: `hasattr(ws, "_charts")` is False in read_only mode, True
    otherwise), so charts are invisible in that mode by construction,
    not by a bug in this function.
    """
    workbook = worksheet.parent
    descriptions = []
    for chart in getattr(worksheet, "_charts", []):
        series_list = []
        for series in chart.series:
            series_list.append(
                ChartSeries(
                    name=_series_name(series, workbook),
                    categories=[str(c) for c in _cache_values(series.cat, workbook)],
                    values=[float(v) for v in _cache_values(series.val, workbook)],
                )
            )
        descriptions.append(
            ChartDescription(
                chart_type=type(chart).__name__,
                title=_flatten_title(chart.title),
                series=series_list,
            )
        )
    return descriptions


def chart_description_to_text(chart: ChartDescription) -> str:
    """Render a ChartDescription as plain text suitable for appending to
    a chunk's extracted text — so a chart's exact data is retrievable
    the same way any other fact in the document is, via RAG_SPEC.md's
    normal chunking/embedding path, with no special-casing downstream.
    """
    lines = [f"[Chart: {chart.title or '(untitled)'}, type={chart.chart_type}]"]
    for series in chart.series:
        pairs = ", ".join(
            f"{cat}={val}" for cat, val in zip(series.categories, series.values)
        )
        label = series.name or "(unnamed series)"
        lines.append(f"  {label}: {pairs}")
    return "\n".join(lines)

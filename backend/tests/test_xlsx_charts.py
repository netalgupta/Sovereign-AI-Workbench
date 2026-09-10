"""Tests for extract_chart_descriptions — native XLSX chart data.

Uses a real fixture chart (backend/tests/fixtures/sample_chart.xlsx, a
BarChart built with openpyxl referencing real cells) rather than mocking
openpyxl's chart objects — the whole point being tested is whether the
real cached-value structure is read correctly.
"""

import os

import openpyxl

from backend.ingestion.xlsx_charts import chart_description_to_text, extract_chart_descriptions

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_chart.xlsx")


def test_extracts_exact_title_and_values():
    workbook = openpyxl.load_workbook(FIXTURE, data_only=True)
    sheet = workbook["Data"]

    charts = extract_chart_descriptions(sheet)

    assert len(charts) == 1
    chart = charts[0]
    assert chart.chart_type == "BarChart"
    assert chart.title == "Widgets Sold by Month"
    assert len(chart.series) == 1
    series = chart.series[0]
    assert series.name == "Widgets Sold"
    assert series.categories == ["Jan", "Feb", "Mar"]
    assert series.values == [10.0, 15.0, 22.0]


def test_read_only_mode_sees_no_charts_at_all():
    """Documents the exact reason _extract_xlsx in text_extraction.py
    must NOT use read_only=True — this isn't a hypothetical, it's
    verified directly here."""
    workbook = openpyxl.load_workbook(FIXTURE, data_only=True, read_only=True)
    sheet = workbook["Data"]

    assert not hasattr(sheet, "_charts")


def test_sheet_with_no_charts_returns_empty_list():
    workbook = openpyxl.Workbook()
    sheet = workbook.active

    assert extract_chart_descriptions(sheet) == []


def test_chart_description_to_text_is_human_and_retrieval_readable():
    workbook = openpyxl.load_workbook(FIXTURE, data_only=True)
    sheet = workbook["Data"]
    chart = extract_chart_descriptions(sheet)[0]

    text = chart_description_to_text(chart)

    assert "Widgets Sold by Month" in text
    assert "Jan=10.0" in text
    assert "Mar=22.0" in text

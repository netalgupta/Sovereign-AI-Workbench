"""Tests for the tool registry — how the agent reaches the tools.

The two things worth protecting here are the safety gate and the
schemas. A wrong schema is the quiet failure: nothing raises, the model
simply sends an argument shaped differently from what the tool takes,
and the turn dies on a TypeError that looks like a model problem.
"""

import pytest

from backend.tools import catalog  # noqa: F401 — importing registers everything
from backend.tools.registry import (
    ApprovalRequired,
    all_tools,
    call_tool,
    get_tool,
    get_tool_schemas,
    tool,
)


def test_every_registered_tool_has_a_usable_schema():
    """A model sees only the schema. A tool with no description, or
    parameters that are not an object, is a tool it cannot call
    correctly."""
    for spec in all_tools():
        schema = spec.to_schema()["function"]
        assert schema["name"]
        assert len(schema["description"]) > 30, f"{spec.name} needs a real description"
        assert schema["parameters"]["type"] == "object"
        assert "properties" in schema["parameters"]


def test_list_parameters_are_arrays_not_scalars():
    """Real bug this pins: list[float] has exactly one type argument, so
    an Optional-first unwrap emitted {"type": "number"} — telling the
    model to send 5 where the tool takes [5]. The tool then failed on
    input its own schema had asked for."""
    params = get_tool("analyse_trend").parameters["properties"]

    assert params["values"]["type"] == "array"
    assert params["values"]["items"]["type"] == "number"


def test_literal_parameters_become_enums():
    """An enum turns a guess into a choice."""
    params = get_tool("plot_series").parameters["properties"]

    assert params["chart_type"]["enum"] == ["line", "bar"]


def test_optional_parameters_are_not_required():
    spec = get_tool("plot_series")

    assert "values" in spec.parameters["required"]
    assert "threshold" not in spec.parameters["required"]


def test_argument_descriptions_come_from_the_docstring():
    """One description, not two that drift — the model reads the same
    prose a developer does."""
    params = get_tool("project_to_threshold").parameters["properties"]

    assert "spec limit" in params["threshold"]["description"]


def test_calling_an_unknown_tool_lists_the_real_ones():
    """A model can hallucinate a plausible tool name; the error has to be
    correctable rather than fatal."""
    with pytest.raises(KeyError) as exc:
        call_tool("compute_the_answer", {})

    assert "analyse_trend" in str(exc.value)


def test_unexpected_arguments_are_reported_not_dropped():
    """Silently dropping an argument means the tool runs on different
    input than the model asked for, and the model never learns."""
    with pytest.raises(TypeError) as exc:
        call_tool("analyse_trend", {"values": [1.0, 2.0], "windw": 3})

    assert "windw" in str(exc.value)


def test_a_gated_tool_refuses_to_run_without_approval():
    """CLAUDE.md hard constraint #4 is a design law. Enforcing it in the
    DISPATCHER rather than in each tool means the next person to add a
    file-writing tool cannot forget it."""

    @tool(
        name="_test_writes_a_file",
        description="A deliberately gated tool used only by this test, which writes.",
        category="test",
        requires_approval=True,
    )
    def _writes(path: str) -> str:
        return f"wrote {path}"

    with pytest.raises(ApprovalRequired):
        call_tool("_test_writes_a_file", {"path": "x.docx"})

    assert call_tool("_test_writes_a_file", {"path": "x.docx"}, approved=True) == "wrote x.docx"


def test_estimate_producing_tools_are_flagged():
    """Hard constraint #3. A caller assembling an answer must be able to
    tell a computed number from a model's guess without reading each
    tool's source. Measured reason this matters: the chart reader states
    figures for charts that have no printed numbers."""
    assert get_tool("describe_chart_image").is_estimate is True
    assert get_tool("evaluate_expression").is_estimate is False
    assert get_tool("evaluate_expression").computes_numbers is True


def test_schemas_can_be_narrowed_by_category():
    """Presenting every tool to every sub-agent wastes context and
    invites a model to reach outside its remit."""
    computation = get_tool_schemas("computation")
    names = {s["function"]["name"] for s in computation}

    assert "analyse_trend" in names
    assert "transcribe_voice_note" not in names


def test_duplicate_registration_is_rejected():
    """Names are how the model addresses a tool, so a duplicate is
    ambiguous rather than additive."""
    with pytest.raises(ValueError):
        tool(name="analyse_trend", description="x" * 40, category="computation")(lambda: None)


# ---- the computation tools themselves ---------------------------------


def test_trend_refuses_a_single_point_rather_than_inventing_a_slope():
    with pytest.raises(ValueError):
        call_tool("analyse_trend", {"values": [408.0]})


def test_trend_detects_real_wabt_creep():
    result = call_tool("analyse_trend", {"values": [408.0, 409.5, 411.0, 412.8, 414.1]})

    assert result.direction == "increasing"
    assert result.slope_per_step == pytest.approx(1.55, abs=0.05)
    assert result.r_squared > 0.99


def test_flat_is_judged_against_the_spread_not_an_absolute_epsilon():
    """A slope of 0.01 is negligible on readings spanning 100 and
    decisive on readings spanning 0.05."""
    assert call_tool("analyse_trend", {"values": [500.0, 500.01, 500.0, 500.01]}).direction == "flat"


def test_projection_does_not_report_an_already_passed_threshold_as_a_countdown():
    """"will cross in -12 steps" reads as a countdown to something that
    already happened."""
    result = call_tool(
        "project_to_threshold", {"values": [10.0, 12.0, 14.0, 16.0], "threshold": 5.0}
    )

    assert result.will_cross is False
    assert result.steps_until_crossing is None
    assert "Already past" in result.assumption


def test_projection_states_its_assumption():
    result = call_tool(
        "project_to_threshold", {"values": [408.0, 409.5, 411.0, 412.8, 414.1], "threshold": 425.0}
    )

    assert result.will_cross is True
    assert "continues unchanged" in result.assumption


def test_plot_rejects_mismatched_labels_rather_than_mislabelling_points():
    with pytest.raises(ValueError):
        call_tool("plot_series", {"values": [1.0, 2.0, 3.0], "labels": ["a", "b"]})


def test_plot_returns_real_png_bytes():
    chart = call_tool(
        "plot_series",
        {
            "values": [99.6, 99.4, 99.1, 99.7],
            "labels": ["W1", "W2", "W3", "W4"],
            "title": "PSA-3 purity",
            "threshold": 99.5,
            "data_provenance": "PSA_Hydrogen_Purity_Trend_Log.xlsx",
        },
    )

    assert chart.png_bytes.startswith(b"\x89PNG")
    assert chart.n_points == 4
    # Provenance travels with the chart: a rendered chart looks
    # authoritative regardless of where its numbers came from.
    assert "PSA_Hydrogen" in chart.data_provenance

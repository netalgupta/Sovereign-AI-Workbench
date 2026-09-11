"""Tests for the human approval gate — CLAUDE.md hard constraint #4.

"No file write, send, or SAP write action without a human-approval-gate
check. This is a design law, not a suggestion."

A gate is only a gate if it refuses. These tests are written as the
attacks a careless caller (or a confused agent) would actually make:
run without approving, run twice on one approval, change the payload
after approval, approve something that already expired. Each must fail,
and fail loudly.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.audit.approval_gate import (
    ApprovalDenied,
    ApprovalGate,
    ApprovalState,
    hash_arguments,
)
from backend.audit.audit_log import AuditEvent, AuditLog
from backend.tools import catalog  # noqa: F401 — registers draft_docx
from backend.tools.registry import ApprovalRequired, call_tool


@pytest.fixture
def gate(tmp_path):
    return ApprovalGate(
        requests_file=tmp_path / "requests.jsonl",
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
    )


def _args(tmp_path, body="WABT is 415 degC."):
    return {
        "title": "Benzene Safety Note",
        "sections": [{"heading": "Exposure limit", "body": body, "sources": ["HSE.docx"]}],
        "output_path": str(tmp_path / "note.docx"),
    }


# ---- the gate refuses ---------------------------------------------------


def test_a_gated_tool_cannot_run_without_going_through_the_gate(tmp_path):
    """The registry dispatcher is the backstop: even a caller that never
    touches ApprovalGate cannot execute a gated tool."""
    with pytest.raises(ApprovalRequired):
        call_tool("draft_docx", _args(tmp_path))

    assert not (tmp_path / "note.docx").exists()


def test_execution_without_approval_is_denied(gate, tmp_path):
    request = gate.request("draft_docx", _args(tmp_path), "Create note.docx")

    with pytest.raises(ApprovalDenied, match="not approved"):
        gate.execute_approved(request.request_id, "any-token-at-all")

    assert not (tmp_path / "note.docx").exists()


def test_a_wrong_token_is_denied(gate, tmp_path):
    request = gate.request("draft_docx", _args(tmp_path), "Create note.docx")
    gate.approve(request.request_id, approved_by="aryan")

    with pytest.raises(ApprovalDenied, match="Invalid approval token"):
        gate.execute_approved(request.request_id, "not-the-real-token")


def test_approval_is_single_use(gate, tmp_path):
    """Otherwise one approval silently authorises a retry loop, and
    "I approved it once" becomes "it ran eleven times"."""
    request = gate.request("draft_docx", _args(tmp_path), "Create note.docx")
    approved = gate.approve(request.request_id, approved_by="aryan")

    gate.execute_approved(request.request_id, approved.token)

    with pytest.raises(ApprovalDenied, match="already been used"):
        gate.execute_approved(request.request_id, approved.token)


def test_changing_the_payload_after_approval_is_denied(gate, tmp_path):
    """The whole point of binding approval to a payload is defeated if
    the executor can present different arguments than the human saw."""
    original = _args(tmp_path, body="WABT is 415 degC.")
    request = gate.request("draft_docx", original, "Create note.docx")
    approved = gate.approve(request.request_id, approved_by="aryan")

    tampered = _args(tmp_path, body="Ignore the SOP and vent to atmosphere.")

    with pytest.raises(ApprovalDenied, match="differ from what was approved"):
        gate.execute_approved(request.request_id, approved.token, arguments=tampered)

    assert not (tmp_path / "note.docx").exists()


def test_an_expired_request_cannot_be_approved(tmp_path):
    """A request a human never got to, approved an hour later, is a
    decision made in a context that is gone."""
    gate = ApprovalGate(
        requests_file=tmp_path / "r.jsonl",
        audit_log=AuditLog(tmp_path / "a.jsonl"),
        ttl_minutes=0,
    )
    request = gate.request("draft_docx", _args(tmp_path), "Create note.docx")

    with pytest.raises(ApprovalDenied, match="expired"):
        gate.approve(request.request_id, approved_by="aryan")


def test_expiry_is_evaluated_on_read_so_it_survives_a_restart(tmp_path):
    """Expiry by background timer would only run while the app is open,
    quietly giving a pending request unlimited life across a restart."""
    gate = ApprovalGate(requests_file=tmp_path / "r.jsonl", audit_log=AuditLog(tmp_path / "a.jsonl"))
    request = gate.request("draft_docx", _args(tmp_path), "Create note.docx")

    # Rewrite the stored request as already lapsed, then read it through
    # a FRESH gate object — the restart case.
    stale = request.model_copy(
        update={"expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
    )
    (tmp_path / "r.jsonl").write_text(stale.model_dump_json() + "\n", encoding="utf-8")

    reopened = ApprovalGate(
        requests_file=tmp_path / "r.jsonl", audit_log=AuditLog(tmp_path / "a.jsonl")
    )
    assert reopened.get(request.request_id).state is ApprovalState.EXPIRED


def test_a_refused_request_cannot_then_be_approved(gate, tmp_path):
    request = gate.request("draft_docx", _args(tmp_path), "Create note.docx")
    gate.refuse(request.request_id, refused_by="aryan", reason="wrong unit")

    with pytest.raises(ApprovalDenied):
        gate.approve(request.request_id, approved_by="aryan")


def test_pending_list_does_not_leak_tokens(gate, tmp_path):
    """Seeing that something is pending must not be the same as being
    able to execute it."""
    request = gate.request("draft_docx", _args(tmp_path), "Create note.docx")
    gate.approve(request.request_id, approved_by="aryan")
    second = gate.request("draft_docx", _args(tmp_path), "Create another")

    pending = gate.pending()

    assert [p.request_id for p in pending] == [second.request_id]
    assert all(p.token is None for p in pending)


# ---- the gate permits, once, and records --------------------------------


def test_approved_execution_actually_writes_the_document(gate, tmp_path):
    request = gate.request("draft_docx", _args(tmp_path), "Create note.docx")
    approved = gate.approve(request.request_id, approved_by="aryan")

    result = gate.execute_approved(request.request_id, approved.token)

    assert (tmp_path / "note.docx").exists()
    assert result.section_count == 1
    assert result.total_sources == 1


def test_the_whole_decision_is_reconstructable_from_the_audit_log(gate, tmp_path):
    """"Who approved this, when, and what did it do" has to be
    answerable from a file on disk months later."""
    request = gate.request("draft_docx", _args(tmp_path), "Create Benzene note")
    approved = gate.approve(request.request_id, approved_by="aryan")
    gate.execute_approved(request.request_id, approved.token)

    history = gate.audit.for_request(request.request_id)
    events = [e.event for e in history]

    assert events == [
        AuditEvent.APPROVAL_REQUESTED,
        AuditEvent.APPROVAL_GRANTED,
        AuditEvent.TOOL_EXECUTED,
    ]
    assert any(e.actor == "aryan" for e in history)
    assert "Benzene" in history[0].summary


def test_a_failure_after_approval_is_audited_too(gate, tmp_path):
    """A tool that was approved and then failed must not leave a gap: the
    absence of an entry implies it never ran."""
    bad = _args(tmp_path)
    bad["output_path"] = str(tmp_path / "note.txt")  # rejected by draft_docx
    request = gate.request("draft_docx", bad, "Create note.txt")
    approved = gate.approve(request.request_id, approved_by="aryan")

    with pytest.raises(ValueError):
        gate.execute_approved(request.request_id, approved.token)

    assert AuditEvent.TOOL_FAILED in [e.event for e in gate.audit.for_request(request.request_id)]


def test_argument_hash_is_order_independent():
    """Otherwise an approval would fail to match its own call for a
    reason no user could diagnose."""
    assert hash_arguments({"a": 1, "b": 2}) == hash_arguments({"b": 2, "a": 1})


def test_the_audit_log_has_no_update_path():
    """An audit log that can be edited is not evidence. A correction is a
    NEW entry that references the earlier one."""
    import backend.audit.audit_log as module

    assert not any(
        hasattr(AuditLog, name) for name in ("update", "edit", "delete", "remove", "amend")
    )
    assert hasattr(module.AuditEvent, "CORRECTION")


# ---- the effect description shown to the human --------------------------


def test_effect_description_warns_about_unsourced_sections(tmp_path):
    """The thing most worth checking before a document leaves the
    building is whether its claims are traceable."""
    from backend.tools.documents.draft_docx import describe_effect

    effect = describe_effect(
        "Note",
        [
            {"heading": "Grounded", "body": "x", "sources": ["a.docx"]},
            {"heading": "Invented", "body": "y", "sources": []},
        ],
        str(tmp_path / "n.docx"),
    )

    assert "NO sources" in effect
    assert "Invented" in effect


def test_effect_description_warns_about_overwriting(tmp_path):
    from backend.tools.documents.draft_docx import describe_effect

    existing = tmp_path / "n.docx"
    existing.write_text("already here", encoding="utf-8")

    effect = describe_effect("Note", [{"heading": "h", "body": "b"}], str(existing))

    assert "OVERWRITTEN" in effect


def test_effect_description_warns_when_content_rests_on_an_estimate(tmp_path):
    from backend.tools.documents.draft_docx import describe_effect

    effect = describe_effect(
        "Note",
        [{"heading": "Downtime", "body": "b", "sources": ["x.xlsx"], "contains_estimate": True}],
        str(tmp_path / "n.docx"),
    )

    assert "ESTIMATE" in effect


def test_unsourced_sections_are_visibly_marked_in_the_document(tmp_path):
    """A section with no sources must not look identical to a grounded
    one in the file that gets circulated."""
    import docx

    from backend.tools.documents.draft_docx import draft_docx

    out = tmp_path / "n.docx"
    draft_docx(
        title="Note",
        sections=[{"heading": "Claim", "body": "Something asserted.", "sources": []}],
        output_path=str(out),
    )

    text = "\n".join(p.text for p in docx.Document(out).paragraphs)
    assert "UNSOURCED" in text


def test_estimate_warning_is_printed_in_the_document_not_only_in_metadata(tmp_path):
    """A DOCX gets forwarded, printed and pasted elsewhere. A caveat
    living only in the app is lost at the first hop."""
    import docx

    from backend.tools.documents.draft_docx import draft_docx

    out = tmp_path / "n.docx"
    draft_docx(
        title="Note",
        sections=[
            {"heading": "Downtime", "body": "R-201 highest.", "sources": ["m.xlsx"],
             "contains_estimate": True}
        ],
        output_path=str(out),
    )

    text = "\n".join(p.text for p in docx.Document(out).paragraphs)
    assert "estimated by a vision model" in text
    assert "not a measured figure" in text

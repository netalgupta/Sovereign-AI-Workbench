"""An approved write lands in outputs/ and nowhere else.

On the agentic path the model chooses output_path. It was taken as given:
'storage/outputs/…' from the prompt's own example, an absolute path, or
'../..' -- one quick approval wrote there.
"""

from __future__ import annotations

import pytest

import backend.paths as P
from backend.tools import catalog  # noqa: F401 - registers the tools
from backend.tools.registry import call_tool


def test_a_model_chosen_path_keeps_only_its_file_name():
    for raw in ("../../windows/system.docx", "C:/Users/x/Desktop/note.docx", "storage/outputs/note.docx"):
        confined = P.confine_output(raw)
        assert P.is_confined(confined), raw
        assert confined.endswith(raw.replace("\\", "/").split("/")[-1])


def test_an_approved_call_outside_outputs_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "OUTPUT_DIR", tmp_path / "outputs")
    with pytest.raises(PermissionError):
        call_tool("draft_docx", {"title": "t", "sections": [{"heading": "h", "body": "b", "sources": ["s"]}],
                                 "output_path": str(tmp_path / "elsewhere" / "t.docx")}, approved=True)


def test_an_approved_call_inside_outputs_writes(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    monkeypatch.setattr(P, "OUTPUT_DIR", out)
    call_tool("draft_docx", {"title": "t", "sections": [{"heading": "h", "body": "b", "sources": ["s"]}],
                             "output_path": str(out / "t.docx")}, approved=True)
    assert (out / "t.docx").exists()

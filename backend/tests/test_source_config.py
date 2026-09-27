"""The operator's source list survives a bad file, a bad write, and the working directory.

These were read and written in fourteen places, each swallowing its errors:
an unreadable file read as [] and the next save wiped every configured
source; a failed save was silent; the path followed Path.cwd().
"""

from __future__ import annotations

import json
import os

from backend.api import source_config as SC


def test_the_path_is_anchored_to_the_repository_not_the_working_directory(tmp_path, monkeypatch):
    # (conftest points CONFIG_PATH itself at tmp for every test; the anchor is _EVAL_DIR)
    before = SC._EVAL_DIR
    monkeypatch.chdir(tmp_path)
    assert SC._EVAL_DIR == before and SC._EVAL_DIR.is_absolute()
    assert SC._EVAL_DIR.name == "evaluation" and SC._EVAL_DIR.parent.name == "backend"


def test_a_missing_file_is_an_empty_list(tmp_path):
    assert SC.load(tmp_path / "configured_sources.json") == []


def test_an_unreadable_file_is_kept_aside_not_silently_replaced(tmp_path, caplog):
    path = tmp_path / "configured_sources.json"
    path.write_text('[{"id": "a", "path": "C:/docs"}, {"id": "b"', encoding="utf-8")   # half-written
    assert SC.load(path) == []
    kept = list(tmp_path.glob("configured_sources.json.corrupt-*"))
    assert len(kept) == 1, "the damaged file is preserved so the sources can be recovered"
    assert '"id": "a"' in kept[0].read_text(encoding="utf-8")
    assert any("could not be read" in r.message for r in caplog.records)


def test_a_save_is_atomic_and_round_trips(tmp_path):
    path = tmp_path / "configured_sources.json"
    data = [{"id": "a", "path": "C:/docs", "enabled": True}]
    assert SC.save(data, path) is True
    assert json.loads(path.read_text(encoding="utf-8")) == data
    assert not (tmp_path / "configured_sources.json.tmp").exists()


def test_a_failed_save_says_so(tmp_path, caplog, monkeypatch):
    def boom(*_a, **_k):
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", boom)
    assert SC.save([{"id": "a"}], tmp_path / "configured_sources.json") is False
    assert any("could not be saved" in r.message for r in caplog.records)


def test_a_file_holding_something_other_than_a_list_is_not_trusted(tmp_path):
    path = tmp_path / "configured_sources.json"
    path.write_text('{"id": "a"}', encoding="utf-8")
    assert SC.load(path) == []


def test_the_governance_files_do_not_follow_the_working_directory(tmp_path, monkeypatch):
    """The audit log and approval ledger were 'backend/audit/*.jsonl' relative
    to wherever the server was started."""
    from backend.audit.approval_gate import ApprovalGate
    from backend.audit.audit_log import AuditLog
    from backend.paths import REPO_ROOT

    monkeypatch.chdir(tmp_path)
    assert AuditLog().path.resolve() == (REPO_ROOT / "backend" / "audit" / "audit.jsonl").resolve()
    assert ApprovalGate().requests_file.resolve() == (REPO_ROOT / "backend" / "audit" / "requests.jsonl").resolve()


def test_the_model_registry_loads_by_default(tmp_path, monkeypatch):
    from backend.models.registry import load_registry

    monkeypatch.chdir(tmp_path)
    assert "reasoning-model" in load_registry()

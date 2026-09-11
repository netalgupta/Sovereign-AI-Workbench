"""Append-only audit log — TOOLS.md row 68, NFR-7.

Every approval requested, granted, refused, and executed is recorded with
actor and UTC timestamp.

HARD ARCHITECTURAL INVARIANT:
The audit log has NO update, edit, or delete path by construction. An audit
log that can be modified in-place is not evidence; any change or correction
is a NEW entry (CORRECTION) referencing the earlier record. Each entry is
flushed and fsync'd immediately to guarantee crash resistance.
"""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field


class AuditEvent(str, Enum):
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REFUSED = "approval_refused"
    TOOL_EXECUTED = "tool_executed"
    TOOL_FAILED = "tool_failed"
    CORRECTION = "correction"


class AuditRecord(BaseModel):
    event: AuditEvent
    request_id: str
    actor: str
    summary: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    details: dict[str, Any] = Field(default_factory=dict)


class AuditLog:
    """Immutable, append-only audit log backed by a JSON-Lines file."""

    def __init__(self, path: Path | str = "backend/audit/audit.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def log(
        self,
        event: AuditEvent | str,
        request_id: str,
        actor: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Append a single audit record, fsyncing to disk immediately."""
        if isinstance(event, str):
            event = AuditEvent(event)

        record = AuditRecord(
            event=event,
            request_id=request_id,
            actor=actor,
            summary=summary,
            details=details or {},
        )

        line = record.model_dump_json() + "\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        return record

    def for_request(self, request_id: str) -> list[AuditRecord]:
        """Return all historical audit events associated with a given request_id."""
        return [record for record in self.all() if record.request_id == request_id]

    def all(self) -> list[AuditRecord]:
        """Return all audit records in chronological order."""
        if not self.path.exists():
            return []

        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(AuditRecord.model_validate_json(line))
                except Exception:
                    continue
        return records

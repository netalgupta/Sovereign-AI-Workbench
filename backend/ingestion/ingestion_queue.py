"""The work list: what still needs ingesting, in what order, and what
already failed.

A watched Downloads folder can present thousands of files at once, each
costing seconds to minutes (OCR a scan, transcribe a voice note,
describe every figure). That work cannot run in one pass, cannot block
the UI, and must survive the app being closed halfway through — so it
needs to be a durable queue rather than a loop over a list.

ORDERING POLICY, which is the part the user actually feels:

    newest modification time first.

That single key delivers the whole policy. A file that just landed has
the newest mtime, so it sorts ahead of everything and new work preempts
the backlog automatically. The backlog then drains most-recent-first,
which is also the right order — last quarter's report is likelier to be
asked about than one from four years ago. No separate "new" versus
"backlog" bookkeeping exists, so there is no second ordering to fall out
of sync with the first.

FAILURES ARE STATE, NOT EXCEPTIONS. One corrupt PDF must not stall the
queue behind it, and must not be retried forever — but must also not
vanish silently, because "why is this document not searchable?" needs an
answer. So a failed item stays with its error and its attempt count,
retried a bounded number of times and then parked as FAILED where a UI
can show it.

WHY JSON-LINES, APPEND-ONLY, WITH PERIODIC COMPACTION: the same reason
extract_corpus.py checkpoints that way. A single rewritten JSON file
loses everything if the process dies mid-write; appending one line per
state change means a crash costs at most the line being written, and the
file can be replayed to rebuild state.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

DEFAULT_QUEUE_FILE = Path("document_registry/ingestion_queue.jsonl")
MAX_ATTEMPTS = 3


class ItemState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class QueueItem(BaseModel):
    path: str
    state: ItemState = ItemState.PENDING
    change: str = "new"
    modified_time: float = 0.0
    byte_size: int = 0
    attempts: int = 0
    last_error: str | None = None
    updated_at: str = ""
    chunks_produced: int | None = None


class IngestionQueue:
    def __init__(self, queue_file: str | Path = DEFAULT_QUEUE_FILE):
        self.queue_file = Path(queue_file)

    # ---- persistence -------------------------------------------------

    def _load(self) -> dict[str, QueueItem]:
        """Replay the log. Later lines for a path win, so the last state
        written is the state — which is what makes append-only safe."""
        items: dict[str, QueueItem] = {}
        if not self.queue_file.exists():
            return items
        with self.queue_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = QueueItem.model_validate_json(line)
                except Exception:  # noqa: BLE001 — a torn final line must not lose the whole queue
                    continue
                items[item.path] = item
        return items

    def _append(self, item: QueueItem) -> None:
        item.updated_at = datetime.now().isoformat(timespec="seconds")
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        with self.queue_file.open("a", encoding="utf-8") as handle:
            handle.write(item.model_dump_json() + "\n")
            handle.flush()
            # fsync so a power loss cannot lose a state change that the
            # caller has already acted on — the queue claiming an item is
            # done when it is not is worse than doing it twice.
            os.fsync(handle.fileno())

    # ---- queue operations --------------------------------------------

    def enqueue_all(self, pending_files) -> int:
        """Add scanned files, returning how many were newly queued.

        A path already queued and not yet done is left alone rather than
        reset — re-scanning every few minutes must not keep clearing the
        attempt count of something that is failing, or a broken file
        retries forever.
        """
        items = self._load()
        added = 0
        for pending in pending_files:
            existing = items.get(pending.path)
            if existing and existing.state in (ItemState.PENDING, ItemState.IN_PROGRESS):
                continue
            if (
                existing
                and existing.state is ItemState.DONE
                and existing.modified_time == pending.modified_time
            ):
                continue  # already ingested at exactly this version
            self._append(
                QueueItem(
                    path=pending.path,
                    state=ItemState.PENDING,
                    change=pending.change.value if hasattr(pending.change, "value") else str(pending.change),
                    modified_time=pending.modified_time,
                    byte_size=pending.byte_size,
                )
            )
            added += 1
        return added

    def next_batch(self, limit: int = 1) -> list[QueueItem]:
        """The highest-priority pending items: newest modification first."""
        pending = [i for i in self._load().values() if i.state is ItemState.PENDING]
        pending.sort(key=lambda i: i.modified_time, reverse=True)
        return pending[:limit]

    def mark_in_progress(self, path: str) -> None:
        item = self._load().get(path)
        if item is None:
            return
        item.state = ItemState.IN_PROGRESS
        item.attempts += 1
        self._append(item)

    def mark_done(self, path: str, chunks_produced: int | None = None) -> None:
        item = self._load().get(path)
        if item is None:
            return
        item.state = ItemState.DONE
        item.last_error = None
        item.chunks_produced = chunks_produced
        self._append(item)

    def mark_failed(self, path: str, error: str) -> QueueItem | None:
        """Record a failure; park the item once it has used its attempts.

        Returned so a caller can tell "will retry" from "given up",
        which are different things to show a user.
        """
        item = self._load().get(path)
        if item is None:
            return None
        item.last_error = error[:500]
        item.state = (
            ItemState.FAILED if item.attempts >= MAX_ATTEMPTS else ItemState.PENDING
        )
        self._append(item)
        return item

    def requeue_failed(self) -> int:
        """Give up-on items another chance — after the user fixes whatever
        was wrong (remounted a share, repaired a PDF)."""
        count = 0
        for item in self._load().values():
            if item.state is ItemState.FAILED:
                item.state = ItemState.PENDING
                item.attempts = 0
                self._append(item)
                count += 1
        return count

    def stats(self) -> dict:
        items = self._load().values()
        counts = {state.value: 0 for state in ItemState}
        for item in items:
            counts[item.state.value] += 1
        return {
            "total": len(list(items)),
            **counts,
            "failures": [
                {"path": i.path, "error": i.last_error, "attempts": i.attempts}
                for i in items
                if i.state is ItemState.FAILED
            ],
        }

    def compact(self) -> int:
        """Rewrite the log keeping only each path's final state.

        Append-only grows without bound on a folder that changes often.
        Written to a temp file and atomically replaced, so an interrupted
        compaction leaves the original log intact rather than a truncated
        one — the failure mode this whole format exists to avoid.
        """
        items = self._load()
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=self.queue_file.parent, suffix=".tmp"
        )
        try:
            for item in items.values():
                handle.write(item.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, self.queue_file)
        return len(items)

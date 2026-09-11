"""Tests for watched folders, change detection, and the ingestion queue.

The behaviour these protect is the one a user actually experiences: they
point the system at a folder, and things that appear there become
searchable — newest first — without being told about it again, and
without one broken file stopping everything behind it.
"""

import time

from backend.ingestion.document_registry import DocumentRegistry
from backend.ingestion.ingestion_queue import IngestionQueue, ItemState, MAX_ATTEMPTS
from backend.ingestion.source_watcher import ChangeKind, SourceWatcher


def _watcher(tmp_path):
    registry = DocumentRegistry(tmp_path / "registry")
    return SourceWatcher(registry, tmp_path / "registry" / "sources.json"), registry


def _write(path, text="content"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_watching_a_folder_finds_supported_files(tmp_path):
    watcher, _registry = _watcher(tmp_path)
    docs = tmp_path / "docs"
    _write(docs / "report.pdf")
    _write(docs / "notes.txt")

    watcher.add_source(docs)
    pending = watcher.scan()

    assert {Path_name(p.path) for p in pending} == {"report.pdf", "notes.txt"}
    assert all(p.change is ChangeKind.NEW for p in pending)


def Path_name(p):
    from pathlib import Path

    return Path(p).name


def test_unsupported_and_temp_files_are_never_offered(tmp_path):
    """A watched Downloads folder is mostly not documents. Offering
    installers and half-finished downloads fills the queue with work
    that can only fail — and ingesting a partial download produces
    garbage chunks that then have to be hunted down."""
    watcher, _registry = _watcher(tmp_path)
    docs = tmp_path / "downloads"
    _write(docs / "keep.pdf")
    _write(docs / "installer.exe")
    _write(docs / "movie.mkv")
    _write(docs / "report.pdf.crdownload")
    _write(docs / "~$draft.docx")
    _write(docs / "Thumbs.db")

    watcher.add_source(docs)
    pending = watcher.scan()

    assert [Path_name(p.path) for p in pending] == ["keep.pdf"]


def test_dot_directories_are_skipped(tmp_path):
    """.git and .venv hold thousands of files and none of them are the
    user's documents."""
    watcher, _registry = _watcher(tmp_path)
    docs = tmp_path / "project"
    _write(docs / "spec.pdf")
    _write(docs / ".git" / "objects" / "blob.txt")
    _write(docs / ".venv" / "lib" / "readme.md")

    watcher.add_source(docs)
    pending = watcher.scan()

    assert [Path_name(p.path) for p in pending] == ["spec.pdf"]


def test_newest_file_sorts_first(tmp_path):
    """The whole priority policy in one assertion: a file that just
    arrived preempts the backlog, because mtime-descending IS the
    policy rather than a proxy for it."""
    watcher, _registry = _watcher(tmp_path)
    docs = tmp_path / "docs"
    old = _write(docs / "old.pdf")
    time.sleep(0.01)
    new = _write(docs / "new.pdf")
    import os

    os.utime(old, (time.time() - 86400, time.time() - 86400))

    watcher.add_source(docs)
    pending = watcher.scan()

    assert [Path_name(p.path) for p in pending] == ["new.pdf", "old.pdf"]


def test_already_registered_unchanged_file_is_not_offered_again(tmp_path):
    watcher, registry = _watcher(tmp_path)
    docs = tmp_path / "docs"
    report = _write(docs / "report.pdf")
    watcher.add_source(docs)

    registry.register(report)

    assert watcher.scan() == []


def test_modified_file_is_offered_again_as_modified(tmp_path):
    """Old chunks describe text that is no longer in the file, so a
    changed document is a re-ingest, not a skip."""
    watcher, registry = _watcher(tmp_path)
    docs = tmp_path / "docs"
    report = _write(docs / "report.pdf", "first version")
    watcher.add_source(docs)
    registry.register(report)

    time.sleep(0.01)
    _write(docs / "report.pdf", "second version, materially different")

    pending = watcher.scan()

    assert len(pending) == 1
    assert pending[0].change is ChangeKind.MODIFIED


def test_include_globs_narrow_a_noisy_folder(tmp_path):
    watcher, _registry = _watcher(tmp_path)
    docs = tmp_path / "mixed"
    _write(docs / "a.pdf")
    _write(docs / "b.txt")

    watcher.add_source(docs, include_globs=["*.pdf"])
    pending = watcher.scan()

    assert [Path_name(p.path) for p in pending] == ["a.pdf"]


def test_missing_watched_folder_is_not_an_error(tmp_path):
    """An unmounted share is normal operation on a laptop, not a crash."""
    watcher, _registry = _watcher(tmp_path)
    docs = tmp_path / "share"
    docs.mkdir()
    watcher.add_source(docs)
    docs.rmdir()

    assert watcher.scan() == []


# ---- queue -------------------------------------------------------------


def test_queue_serves_newest_first_and_survives_a_restart(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.jsonl")

    from backend.ingestion.source_watcher import PendingFile

    queue.enqueue_all([
        PendingFile(path="/old.pdf", change=ChangeKind.NEW, byte_size=1, modified_time=100.0, suffix=".pdf"),
        PendingFile(path="/new.pdf", change=ChangeKind.NEW, byte_size=1, modified_time=999.0, suffix=".pdf"),
    ])

    # A fresh object, as after an app restart: state comes off disk.
    reopened = IngestionQueue(tmp_path / "queue.jsonl")
    assert [i.path for i in reopened.next_batch(2)] == ["/new.pdf", "/old.pdf"]


def test_failed_item_retries_then_parks(tmp_path):
    """One corrupt PDF must not stall the queue behind it, must not
    retry forever, and must not vanish silently — "why is this not
    searchable?" needs an answer."""
    queue = IngestionQueue(tmp_path / "queue.jsonl")
    from backend.ingestion.source_watcher import PendingFile

    queue.enqueue_all([
        PendingFile(path="/bad.pdf", change=ChangeKind.NEW, byte_size=1, modified_time=1.0, suffix=".pdf"),
    ])

    for _ in range(MAX_ATTEMPTS):
        queue.mark_in_progress("/bad.pdf")
        item = queue.mark_failed("/bad.pdf", "PdfReadError: damaged xref")

    assert item.state is ItemState.FAILED
    assert queue.next_batch(5) == []
    stats = queue.stats()
    assert stats["failed"] == 1
    assert "damaged xref" in stats["failures"][0]["error"]


def test_rescanning_does_not_reset_a_failing_items_attempts(tmp_path):
    """Scans run repeatedly. If each one cleared the attempt count, a
    broken file would retry forever and never park."""
    queue = IngestionQueue(tmp_path / "queue.jsonl")
    from backend.ingestion.source_watcher import PendingFile

    pending = PendingFile(path="/bad.pdf", change=ChangeKind.NEW, byte_size=1,
                          modified_time=1.0, suffix=".pdf")
    queue.enqueue_all([pending])
    queue.mark_in_progress("/bad.pdf")
    queue.mark_failed("/bad.pdf", "boom")

    queue.enqueue_all([pending])  # a later scan sees the same file

    assert queue.next_batch(1)[0].attempts == 1


def test_done_item_is_requeued_only_if_the_file_changed(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.jsonl")
    from backend.ingestion.source_watcher import PendingFile

    same = PendingFile(path="/a.pdf", change=ChangeKind.NEW, byte_size=1,
                       modified_time=5.0, suffix=".pdf")
    queue.enqueue_all([same])
    queue.mark_done("/a.pdf", chunks_produced=3)

    assert queue.enqueue_all([same]) == 0

    changed = PendingFile(path="/a.pdf", change=ChangeKind.MODIFIED, byte_size=2,
                          modified_time=9.0, suffix=".pdf")
    assert queue.enqueue_all([changed]) == 1


def test_compaction_preserves_final_state(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.jsonl")
    from backend.ingestion.source_watcher import PendingFile

    queue.enqueue_all([
        PendingFile(path="/a.pdf", change=ChangeKind.NEW, byte_size=1, modified_time=1.0, suffix=".pdf"),
    ])
    queue.mark_in_progress("/a.pdf")
    queue.mark_done("/a.pdf", chunks_produced=7)

    before = queue.stats()
    queue.compact()
    after = IngestionQueue(tmp_path / "queue.jsonl").stats()

    assert before["done"] == after["done"] == 1
    assert queue.queue_file.read_text(encoding="utf-8").strip().count("\n") == 0

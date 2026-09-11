"""Watch folders the user nominates, and notice what needs ingesting.

A user does not add documents one at a time. They point the system at
somewhere their documents already live — Downloads, a project folder on
D:, a mounted share — and expect anything that shows up there to become
searchable without being told about it again.

So a source is a PATH, watched in place. Nothing is copied (see
document_registry.py for why), and the folder stays the user's: this
module only ever reads.

WHAT "NEEDS INGESTING" MEANS, precisely. Comparing a folder against the
registry gives three kinds of file, and they are not the same job:

  * NEW      — never seen at this path. Ingest it.
  * MODIFIED — seen, but size or mtime moved. The old chunks describe
               text that is no longer there, so this is a re-ingest, not
               a skip.
  * UNCHANGED — seen, identical. Skip, and skip CHEAPLY: on a Downloads
               folder with thousands of files, the common case is that
               almost everything is unchanged, and a scan that hashes
               every file to learn that is a scan nobody will leave
               enabled.

That last point drives the design: the cheap fingerprint (size + mtime)
is what a scan uses, and hashing is left to registration. A file that is
touched but not edited costs one wasted re-ingest, which is acceptable;
hashing every file on every scan is not.

WHAT IS DELIBERATELY NOT HERE: filesystem watch events (inotify /
ReadDirectoryChangesW). They are OS-specific, silently lossy on network
shares, and miss everything that happened while the app was closed —
which for a desktop workbench is most of the time. Scanning is
predictable, testable, works identically on every platform, and cannot
miss a change that happened overnight. A watch API could later feed the
same queue as an optimisation, not a replacement.
"""

import fnmatch
import json
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from backend.ingestion.document_registry import DocumentRegistry

DEFAULT_SOURCES_FILE = Path("document_registry/watched_sources.json")

# Formats the ingestion pipeline can actually read (RAG_SPEC.md §2).
# A watched folder is full of things that are not documents — installers,
# archives, video — and offering to ingest them would fill the queue with
# work that can only fail.
SUPPORTED_SUFFIXES = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt", ".md",
    ".eml", ".msg", ".png", ".jpg", ".jpeg", ".webp", ".tiff",
    ".wav", ".mp3", ".m4a", ".flac",
}

# Never offer these, whatever their extension: temp files an editor is
# still writing, OS metadata, and partial downloads. Ingesting a
# half-written file produces garbage chunks that then have to be found
# and removed.
EXCLUDE_PATTERNS = (
    "~$*",          # Office lock/temp files
    ".~*",
    "*.crdownload", "*.part", "*.partial", "*.tmp",  # in-flight downloads
    ".DS_Store", "Thumbs.db", "desktop.ini",
    ".*",           # dotfiles and dot-directories
)


class ChangeKind(str, Enum):
    NEW = "new"
    MODIFIED = "modified"


class WatchedSource(BaseModel):
    path: str
    recursive: bool = True
    added_on: str
    # Optional narrowing, e.g. ["*.pdf"] to watch only PDFs in a folder
    # that also holds a lot of other things.
    include_globs: list[str] = []
    enabled: bool = True


class PendingFile(BaseModel):
    path: str
    change: ChangeKind
    byte_size: int
    modified_time: float
    suffix: str

    @property
    def modified_iso(self) -> str:
        return datetime.fromtimestamp(self.modified_time).isoformat(timespec="seconds")


def _is_excluded(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE_PATTERNS)


def _matches_includes(name: str, include_globs: list[str]) -> bool:
    if not include_globs:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in include_globs)


class SourceWatcher:
    def __init__(
        self,
        registry: DocumentRegistry,
        sources_file: str | Path = DEFAULT_SOURCES_FILE,
    ):
        self.registry = registry
        self.sources_file = Path(sources_file)

    # ---- watched source management ----------------------------------

    def sources(self) -> list[WatchedSource]:
        if not self.sources_file.exists():
            return []
        raw = json.loads(self.sources_file.read_text(encoding="utf-8"))
        return [WatchedSource.model_validate(s) for s in raw]

    def add_source(
        self,
        path: str | Path,
        recursive: bool = True,
        include_globs: list[str] | None = None,
    ) -> WatchedSource:
        """Watch a folder (or a single file) from now on."""
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Cannot watch a path that does not exist: {resolved}")

        existing = self.sources()
        for source in existing:
            if Path(source.path) == resolved:
                source.enabled = True
                self._write(existing)
                return source

        source = WatchedSource(
            path=str(resolved),
            recursive=recursive,
            added_on=datetime.now().date().isoformat(),
            include_globs=include_globs or [],
        )
        existing.append(source)
        self._write(existing)
        return source

    def remove_source(self, path: str | Path) -> bool:
        resolved = Path(path).resolve()
        remaining = [s for s in self.sources() if Path(s.path) != resolved]
        changed = len(remaining) != len(self.sources())
        self._write(remaining)
        return changed

    def _write(self, sources: list[WatchedSource]) -> None:
        self.sources_file.parent.mkdir(parents=True, exist_ok=True)
        self.sources_file.write_text(
            json.dumps([s.model_dump() for s in sources], indent=2), encoding="utf-8"
        )

    # ---- scanning ----------------------------------------------------

    def iter_candidate_files(self) -> list[Path]:
        """Every ingestible file under every enabled watched source."""
        found: list[Path] = []
        for source in self.sources():
            if not source.enabled:
                continue
            root = Path(source.path)
            if not root.exists():
                continue  # unmounted share or deleted folder: not an error, just nothing to scan

            if root.is_file():
                candidates = [root]
            else:
                candidates = root.rglob("*") if source.recursive else root.glob("*")

            for path in candidates:
                if not path.is_file():
                    continue
                if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                if _is_excluded(path.name):
                    continue
                # A dot-directory anywhere in the path excludes it too —
                # .git and .venv hold thousands of files that are never
                # documents.
                if any(part.startswith(".") for part in path.parts[:-1]):
                    continue
                if not _matches_includes(path.name, source.include_globs):
                    continue
                found.append(path)
        return sorted(set(found))

    def scan(self) -> list[PendingFile]:
        """What needs ingesting right now, newest first.

        Ordering is by modification time descending, and that single key
        gives the whole priority policy the user asked for: a file that
        just arrived has the newest mtime and therefore sorts ahead of
        everything, so new work naturally preempts the backlog, and the
        backlog itself is worked most-recent-first. No separate
        "new vs backlog" bookkeeping is needed, which means there is no
        second ordering to get out of sync with the first.
        """
        known_by_path: dict[str, tuple[int, float]] = {}
        for ref in self.registry.all_refs():
            for path in [ref.source_path, *ref.known_paths]:
                known_by_path[path] = (ref.byte_size, ref.modified_time)

        pending: list[PendingFile] = []
        for path in self.iter_candidate_files():
            try:
                stat = path.stat()
            except OSError:
                continue  # vanished between listing and stat; it will reappear next scan

            known = known_by_path.get(str(path))
            if known is None:
                change = ChangeKind.NEW
            elif known == (stat.st_size, stat.st_mtime):
                continue  # unchanged: the common case, and it costs one dict lookup
            else:
                change = ChangeKind.MODIFIED

            pending.append(
                PendingFile(
                    path=str(path),
                    change=change,
                    byte_size=stat.st_size,
                    modified_time=stat.st_mtime,
                    suffix=path.suffix.lower(),
                )
            )

        pending.sort(key=lambda f: f.modified_time, reverse=True)
        return pending

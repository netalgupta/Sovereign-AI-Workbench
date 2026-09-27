"""The two source-list files, read and written in one place.

configured_sources.json   the folders and files the operator added as sources
deleted_sources.json      paths the operator removed, so a rescan does not re-add them

WHY THIS MODULE EXISTS. These were read and written in fourteen places in
routes.py, each wrapped in `try: ... except Exception: pass`, and resolved
against Path.cwd(). Three failures followed from that:

  - An unreadable file (a half-written save) read as an EMPTY list, and the
    next "add source" wrote back a list holding only the new entry: every
    previously configured source was wiped, silently.
  - A failed write was swallowed, so a source the operator added was gone
    after the next restart with nothing said.
  - Starting the server from another directory read and wrote a different,
    empty file.

Now: paths are anchored to the repository; a file that cannot be parsed is
kept aside as `<name>.corrupt-<time>` and reported, never replaced by an
empty list unnoticed; writes are atomic (temp file + rename) and a failure
is logged.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EVAL_DIR = Path(__file__).resolve().parents[1] / "evaluation"
CONFIG_PATH = _EVAL_DIR / "configured_sources.json"
DELETED_PATH = _EVAL_DIR / "deleted_sources.json"


# `path=None`, not `path=CONFIG_PATH`: a default is bound once, at import, so
# a test that redirects CONFIG_PATH (conftest) still wrote the operator's
# real list through every call that relied on the default. That wiped the
# configured sources on 27 Sep. The module global is read at call time now.


def load(path: Path | None = None) -> list[Any]:
    """The list stored at `path` (default CONFIG_PATH): [] only when the file does not exist yet."""
    path = Path(path or CONFIG_PATH)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        kept = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            path.replace(kept)
        except OSError:
            kept = path
        logger.error("Source list %s could not be read (%s: %s); kept as %s. Starting from an empty "
                     "list -- restore that file to recover the previous sources.",
                     path.name, type(exc).__name__, exc, kept.name)
        return []
    if not isinstance(data, list):
        logger.error("Source list %s holds %s, not a list; ignoring it.", path.name, type(data).__name__)
        return []
    return data


def save(data: list[Any], path: Path | None = None) -> bool:
    """Write `data` atomically (default CONFIG_PATH). False (and an error in the log) if it could not be saved."""
    path = Path(path or CONFIG_PATH)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        logger.error("Source list %s could not be saved (%s: %s); the change is lost on restart.",
                     path.name, type(exc).__name__, exc)
        return False


# ── which files the viewer may open ────────────────────────────────────────
#
# /api/sources/content and /api/sandbox/render each resolved a path on their
# own: relative to cwd, then -- on a miss -- the first file ANYWHERE in the
# repo with the same name, then refused anything outside the repo. So every
# file in a source added from elsewhere on disk (e.g. a folder under E:\ or a
# book in Downloads) answered 403, while `path=x/<any name>` served any repo
# file by that name, logs included. One rule for both now: a file is
# viewable when it lies inside a configured source, a preset corpus, or
# outputs/ (generated deliverables, opened from the Artifacts tab).

_REPO_ROOT = _EVAL_DIR.parents[1]
PRESET_CORPORA = ("MRPL_RAG_Test_Corpus", "MRPL_Chart_Stress_Corpus")


def source_roots() -> list[Path]:
    roots = [_REPO_ROOT / name for name in PRESET_CORPORA]
    for entry in load():
        if isinstance(entry, dict) and entry.get("path"):
            roots.append(Path(entry["path"]))
    out: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved not in out:
            out.append(resolved)
    return out


def _inside(path: Path, root: Path) -> bool:
    return path == root or (root.is_dir() and path.is_relative_to(root))


def viewable_file(raw: str) -> Path | None:
    """The file `raw` names, if it lies inside a source; else None.

    `raw` may be absolute, relative to the repository, or a bare file name
    (a citation carries only the document name), which is looked up inside
    the sources only.
    """
    if not raw:
        return None
    from backend.paths import OUTPUT_DIR

    # generated deliverables (the Artifacts tab) open in the same viewer
    roots = source_roots() + ([OUTPUT_DIR.resolve()] if OUTPUT_DIR.exists() else [])
    given = Path(raw)
    candidate = given if given.is_absolute() else _REPO_ROOT / given
    try:
        candidate = candidate.resolve()
    except OSError:
        candidate = None
    if candidate is not None and candidate.is_file() and any(_inside(candidate, r) for r in roots):
        return candidate
    name = given.name
    if not name:
        return None
    for root in roots:
        if root.is_file():
            if root.name == name:
                return root
            continue
        for hit in root.rglob(name):
            if hit.is_file():
                return hit.resolve()
    return None

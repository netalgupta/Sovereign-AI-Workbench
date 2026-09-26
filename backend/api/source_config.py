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


def load(path: Path = CONFIG_PATH) -> list[Any]:
    """The list stored at `path`: [] only when the file does not exist yet."""
    path = Path(path)
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


def save(data: list[Any], path: Path = CONFIG_PATH) -> bool:
    """Write `data` atomically. False (and an error in the log) if it could not be saved."""
    path = Path(path)
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

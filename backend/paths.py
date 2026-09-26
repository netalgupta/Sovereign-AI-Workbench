"""The repository root, for paths that must not depend on the working directory.

Dozens of paths in the backend are written relative to the repo root
("storage/attachments", "backend/audit/audit.jsonl", the corpora). They
were correct only when the server was started from that directory; started
from anywhere else, the append-only audit log and the approval ledger were
silently written somewhere new. main.py now moves into REPO_ROOT before
anything else runs, and the governance files are anchored here explicitly.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Where every approved deliverable is written. Nothing gated writes anywhere else.
OUTPUT_DIR = REPO_ROOT / "outputs"


def confine_output(path: str | None) -> str:
    """`path` moved into OUTPUT_DIR, keeping only its file name.

    On the agentic path the MODEL chooses output_path. It was taken as
    given -- "storage/outputs/…" from the prompt's own example, or an
    absolute path, or "../..": the approval screen showed it, and one quick
    approval wrote there. Confined BEFORE the approval is requested, so the
    operator approves the real destination (approvals are bound to the
    exact arguments).
    """
    name = Path(str(path or "")).name or "output"
    return str(OUTPUT_DIR / name)


def is_confined(path: str | None) -> bool:
    """Whether `path` resolves inside OUTPUT_DIR."""
    try:
        return Path(str(path)).resolve().is_relative_to(OUTPUT_DIR.resolve())
    except (OSError, ValueError):
        return False

"""Shared "fetch once online, run forever offline" pattern.

This is the answer to CLAUDE.md hard constraint #1 for every model that
comes from a hub-style library (sentence-transformers/HuggingFace today;
PaddleOCR's weight downloader will need the exact same treatment when
that tool gets built). The rule this file enforces:

    Build-time internet is fine. Run-time internet is never fine.

`sentence-transformers` / `transformers` will silently ping the
HuggingFace Hub on every load — even for an already-cached model — to
check for a newer version, unless you explicitly force offline mode. On
an air-gapped GPU server that "just checking for updates" call is a real
outbound connection, and it is exactly the kind of thing the live network
monitor panel (TOOLS.md #44, FR-15) would catch in front of a judge.

So: this module downloads a model into a repo-local cache directory
*once*, during development/build (when internet is available), and every
subsequent load forces `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` and
reads only from that local directory. If the model isn't cached yet, the
loader raises a clear, actionable error instead of silently falling back
to a network fetch.
"""

import os
from pathlib import Path

# All cached model weights live under /models/<category>/<model_id>,
# alongside models.yaml — this is the same "everything the app needs
# ships on the portable drive" directory DEPENDENCIES.md §10 describes.
MODELS_ROOT = Path(__file__).resolve().parents[2] / "models"


def local_cache_dir(category: str, model_id: str) -> Path:
    """Repo-local directory a given model's weights are cached under."""
    return MODELS_ROOT / category / model_id.replace("/", "__")


def force_offline_mode() -> None:
    """Set the env vars that stop transformers/sentence-transformers from
    ever reaching out to the Hub, even to check for updates on a model
    that's already fully cached locally. Call this BEFORE importing or
    constructing anything from those libraries — some of their
    Hub-reachability checks happen at import/construction time, not just
    at download time.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def require_cached(category: str, model_id: str) -> Path:
    """Return the local cache dir for `model_id`, raising if it's empty.

    Raises:
        FileNotFoundError: with a message telling the caller exactly what
            one-time, online command fetches the model, and where it will
            end up. Never silently proceeds to a network download here —
            that decision belongs to an explicit, human-run fetch step,
            not something that happens implicitly the first time a tool
            is called on a fresh checkout.
    """
    cache_dir = local_cache_dir(category, model_id)
    if not cache_dir.exists() or not any(cache_dir.iterdir()):
        raise FileNotFoundError(
            f"Model {model_id!r} is not cached locally at {cache_dir}. "
            f"This is expected on a fresh checkout — run the one-time "
            f"fetch step (while you have internet) before running this "
            f"tool offline: "
            f"python -m backend.ingestion.fetch_models --model {model_id!r}"
        )
    return cache_dir

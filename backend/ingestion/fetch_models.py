"""One-time ONLINE step: fetch model weights into the repo-local cache.

Run this ONCE, while you have internet (initial dev-machine setup, or
building the portable drive per DEPENDENCIES.md §10). Every other module
in this codebase loads models offline-only from the cache this script
writes — see model_cache.py's module docstring for the full rationale.

Usage:
    python -m backend.ingestion.fetch_models --model bge-large-en-v1.5
    python -m backend.ingestion.fetch_models --all
"""

import argparse

from backend.ingestion.model_cache import local_cache_dir


def _fetch_bge_large(model_id: str = "BAAI/bge-large-en-v1.5") -> None:
    # Imported here, not at module top level, so that merely importing
    # this file (e.g. to read _FETCHERS) never requires sentence-
    # transformers/torch to already be installed.
    from sentence_transformers import SentenceTransformer

    cache_dir = local_cache_dir("embeddings", model_id)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {model_id} (one-time, requires internet)...")
    model = SentenceTransformer(model_id)
    # .save() writes a fully self-contained local directory — every
    # future load points AT this path (not the hub id), so it never
    # touches the network again.
    model.save(str(cache_dir))
    print(f"Saved to {cache_dir} — future loads are fully offline.")


def _fetch_whisper_base(model_id: str = "Systran/faster-whisper-base") -> None:
    # Imported here, not at module top, and NOT via voice_transcription.py
    # — that module forces itself offline (HF_HUB_OFFLINE=1) as an import
    # side-effect, which would poison this exact fetch call if we routed
    # through it. fetch_models.py stays completely independent of every
    # runtime module that assumes offline, on purpose — see
    # voice_transcription.py's module docstring for the bug this avoids.
    from faster_whisper.utils import download_model

    from backend.ingestion.model_cache import local_cache_dir

    cache_dir = local_cache_dir("audio", model_id)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {model_id} (one-time, requires internet)...")
    # output_dir -> huggingface_hub's local_dir (symlinks disabled) --
    # a clean, flat, self-contained directory, NOT the hashed cache
    # layout `download_root`/`cache_dir` would produce. Verified by
    # reading download_model's own source before relying on it.
    download_model(model_id, output_dir=str(cache_dir))
    print(f"Saved to {cache_dir} — future loads are fully offline.")


def _fetch_sd_turbo(model_id: str = "stabilityai/sd-turbo") -> None:
    """The image model for abstract deck artwork (models.yaml `image-model`).

    fp16 weights only, and only the files diffusers loads: the full repo
    also carries fp32 copies that would double the download and the disk
    footprint for nothing.
    """
    from huggingface_hub import snapshot_download

    cache_dir = local_cache_dir("image", model_id)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {model_id} (one-time, requires internet)...")
    snapshot_download(
        repo_id=model_id,
        local_dir=str(cache_dir),
        allow_patterns=[
            "model_index.json",
            "*/config.json",
            "scheduler/*",
            "tokenizer/*",
            "*/*.fp16.safetensors",
        ],
    )
    print(f"Saved to {cache_dir} — future loads are fully offline.")


_FETCHERS = {
    "bge-large-en-v1.5": _fetch_bge_large,
    "faster-whisper-base": _fetch_whisper_base,
    "sd-turbo": _fetch_sd_turbo,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(_FETCHERS), help="Which model to fetch")
    parser.add_argument("--all", action="store_true", help="Fetch every known model")
    args = parser.parse_args()

    if args.all:
        for fetch in _FETCHERS.values():
            fetch()
    elif args.model:
        _FETCHERS[args.model]()
    else:
        parser.error("Pass --model <name> or --all")


if __name__ == "__main__":
    main()

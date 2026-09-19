"""GPU hand-off between Ollama and the models we load in-process.

The 8 GB dev card holds one of these at a time with headroom, not two
(CLAUDE.md, VRAM discipline). Before an in-process model (image model,
local vision model) loads, the Ollama models resident on the card are
unloaded with keep_alive=0; Ollama reloads them on their next call.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("models.gpu")


def free_ollama_vram() -> list[str]:
    """Unload every model Ollama has resident. Returns the names unloaded."""
    unloaded: list[str] = []
    try:
        import requests

        from backend.models.ollama_client import OLLAMA_HOST

        ps = requests.get(f"{OLLAMA_HOST}/api/ps", timeout=3).json()
        for m in ps.get("models", []):
            requests.post(f"{OLLAMA_HOST}/api/generate",
                          json={"model": m["name"], "keep_alive": 0}, timeout=15)
            unloaded.append(m["name"])
    except Exception as exc:  # noqa: BLE001 - freeing memory is best effort, and said so
        logger.info("Could not unload Ollama models: %s", exc)
    return unloaded


def cuda_free_gib() -> float | None:
    """Free memory on CUDA device 0 in GiB, or None without CUDA."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        free, _total = torch.cuda.mem_get_info(0)
        return free / 2**30
    except Exception:  # noqa: BLE001
        return None

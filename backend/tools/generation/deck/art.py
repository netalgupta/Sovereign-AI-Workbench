"""Abstract deck artwork from the local image model (models.yaml `image-model`).

WHAT THIS MAY DRAW, AND WHAT IT MAY NOT. Cover and section backgrounds:
light, colour, texture, geometry. Never equipment, a plant, a process or
a person. A generated picture of "a hydrocracker" is not MRPL's
hydrocracker, and on a deck that goes through an approval gate it would
be a fabricated record with a caption. Real drawings and scans come from
the corpus (the `exhibit` layout), never from here.

HOW IT STAYS OFFLINE. Weights are read from models/image/ with the Hub
forced offline and local_files_only, the same fetch-once/offline-forever
pattern as the embedding and speech models. Nothing here downloads.

HOW IT DEGRADES. No weights, no CUDA, not enough free VRAM, or any load
failure: `generate()` returns None and the renderer draws the vector
cover it always had. A deck is never blocked on artwork.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger("pptx.art")

ART_CACHE = Path(".workbench") / "art"

# Abstract motifs only. Chosen by hash so a deck gets the same art every
# time it is rendered, and different decks get different art.
# "concentric rings of light" was dropped after looking at it: it came out
# psychedelic, not corporate.
_MOTIFS = [
    "soft flowing waves of light",
    "layered translucent geometric planes",
    "fine hexagonal lattice fading into darkness",
    "gentle diagonal light streaks over a dark gradient",
    "subtle bokeh and thin intersecting lines",
]
_STYLE = (
    "abstract minimalist background, dark deep navy blue and muted teal, subtle "
    "faint amber glow, low contrast, calm, elegant, soft focus, no text, no letters, "
    "no people, no machines, no buildings"
)

# The palette the artwork is pulled into (theme.PALETTE.navy): generated
# colour straight out of the model competes with the slide; tinted, it sits
# behind it.
_NAVY = (11, 31, 51)

_pipe = None
_load_failed = False


def _free_gpu_for_art() -> None:
    """Unload Ollama's resident models so the image model fits.

    A deck job generates art after all its text is written, so the LLM is
    idle; Ollama reloads it on its next call.
    """
    from backend.models.gpu import free_ollama_vram

    free_ollama_vram()


def _load():
    global _pipe, _load_failed
    if _pipe is not None or _load_failed:
        return _pipe
    try:
        from backend.ingestion.model_cache import force_offline_mode
        from backend.models.registry import (
            _DEFAULT_REGISTRY_PATH, diffusers_weights_dir, is_locally_available, load_registry,
        )

        force_offline_mode()
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("DISABLE_TELEMETRY", "1")
        cfg = load_registry(_DEFAULT_REGISTRY_PATH).get("image-model")
        if cfg is None or not is_locally_available(cfg, None):
            logger.info("No local image model; decks use vector covers.")
            _load_failed = True
            return None

        import torch
        from diffusers import AutoPipelineForText2Image

        if not torch.cuda.is_available():
            logger.info("No CUDA device; skipping generated artwork.")
            _load_failed = True
            return None
        _free_gpu_for_art()
        pipe = AutoPipelineForText2Image.from_pretrained(
            str(diffusers_weights_dir(cfg)), torch_dtype=torch.float16, variant="fp16",
            local_files_only=True,
        )
        pipe.set_progress_bar_config(disable=True)
        _pipe = pipe.to("cuda")
        return _pipe
    except Exception as exc:  # noqa: BLE001 - artwork must never block a deck
        logger.warning("Image model unavailable (%s: %s); decks use vector covers.", type(exc).__name__, exc)
        _load_failed = True
        return None


def prompt_for(key: str) -> str:
    motif = _MOTIFS[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(_MOTIFS)]
    return f"{motif}, {_STYLE}"


def generate(key: str, width: int = 512, height: int = 512) -> Path | None:
    """A PNG of abstract artwork for `key` (e.g. the deck title), or None.

    Deterministic per key: the seed and motif come from its hash, and the
    result is cached, so re-rendering an approved deck reproduces it.
    """
    digest = hashlib.sha256(f"{key}|{width}x{height}".encode()).hexdigest()[:16]
    out = ART_CACHE / f"{digest}.png"
    if out.exists():
        return out
    pipe = _load()
    if pipe is None:
        return None
    try:
        import torch

        generator = torch.Generator("cuda").manual_seed(int(digest[:8], 16))
        image = pipe(prompt=prompt_for(key), num_inference_steps=1, guidance_scale=0.0,
                     width=width, height=height, generator=generator).images[0]
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(out)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("Artwork generation failed (%s: %s).", type(exc).__name__, exc)
        return None


def styled(key: str, width_in: float, height_in: float, *, tint: float = 0.38,
           saturation: float = 0.72) -> Path | None:
    """Artwork cropped to a slide region and pulled into the deck palette.

    Generates square (the model's native size), centre-crops to the
    region's aspect, resizes for ~150 dpi, desaturates, and blends toward
    navy so white text over it stays readable.
    """
    src = generate(key, 512, 512)
    if src is None:
        return None
    ratio = width_in / height_in
    digest = hashlib.sha256(f"{src.name}|{ratio:.3f}|{tint}|{saturation}".encode()).hexdigest()[:16]
    out = ART_CACHE / f"styled_{digest}.png"
    if out.exists():
        return out
    from PIL import Image, ImageEnhance

    img = Image.open(src).convert("RGB")
    w, h = img.size
    if ratio < w / h:
        cw = int(h * ratio)
        img = img.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
    else:
        ch = int(w / ratio)
        img = img.crop((0, (h - ch) // 2, w, (h - ch) // 2 + ch))
    img = img.resize((max(1, int(width_in * 150)), max(1, int(height_in * 150))), Image.LANCZOS)
    img = ImageEnhance.Color(img).enhance(saturation)
    img = Image.blend(img, Image.new("RGB", img.size, _NAVY), tint)
    img.save(out)
    return out


def release() -> None:
    """Free the GPU after a deck's artwork is done."""
    global _pipe
    if _pipe is not None:
        try:
            import torch

            del _pipe
            _pipe = None
            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            _pipe = None

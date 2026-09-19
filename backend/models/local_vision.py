"""A vision-language model run in-process, with the GPU/CPU split set by us.

WHY NOT OLLAMA FOR THIS. Measured on the 8 GB dev card (Ollama 0.17.1):
qwen2.5vl:7b is estimated at 13.4 GB and qwen2.5vl:3b at 10.8 GB, both
placed 0% on the GPU; num_gpu and num_ctx change nothing. Every page review
then ran on the CPU, paged RAM to disk and froze the machine. The text
models are unaffected (qwen2.5:7b runs 100% on GPU); it is Ollama's size
estimate for the Qwen2.5-VL vision encoder that decides, and we cannot
overrule it.

HERE, THE REGISTRY DECIDES. models.yaml gives a `transformers` entry a
`placement`: a GPU budget and a CPU budget in GiB, and optional 4/8-bit
quantization. Layers fill the GPU budget first and the remainder spill to
RAM, streamed to the GPU as they run. `placement_report()` states where the
weights actually went, measured from the loaded model, not assumed.

VRAM DISCIPLINE. Loading unloads Ollama's resident models first (they
reload on their next call), and `release()` frees the card afterwards. A
caller doing many pages loads once, reviews them all, then releases:
warm calls are seconds, cold loads are tens of seconds.

OFFLINE. Weights come only from models/vision/ with the Hub forced offline
and local_files_only. Nothing here downloads.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger("models.local_vision")

# Headroom kept free on the card for activations (image tokens, KV cache)
# beyond the weight budget. A budget larger than the card's free memory
# minus this is lowered, and the report says so.
ACTIVATION_HEADROOM_GIB = 1.0

_lock = threading.Lock()
_loaded: dict = {}  # {"id", "model", "processor", "report"}


class LocalVisionUnavailable(RuntimeError):
    """The model cannot be loaded here; the message says why."""


@dataclass
class PlacementReport:
    model_id: str
    model: str
    quantization: str
    gpu_budget_gib: float
    cpu_budget_gib: float
    gpu_weights_gib: float
    cpu_weights_gib: float
    gpu_share: float  # fraction of weight bytes on the GPU
    load_seconds: float
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _config(model_id: str):
    from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry

    import os

    cfg = load_registry(os.environ.get("MODELS_REGISTRY_PATH", _DEFAULT_REGISTRY_PATH)).get(model_id)
    if cfg is None:
        raise LocalVisionUnavailable(f"{model_id!r} is not in models.yaml")
    if cfg.backend != "transformers":
        raise LocalVisionUnavailable(f"{model_id!r} is served by {cfg.backend}, not in-process")
    if cfg.placement is None:
        raise LocalVisionUnavailable(f"{model_id!r} has no placement in models.yaml")
    return cfg


def _weight_bytes_by_device(model) -> dict[str, int]:
    """Weight bytes per device, from where accelerate actually put each module.

    Offloaded modules hold meta tensors between calls; a meta tensor still
    reports its numel and element size, so the count is exact either way.
    """
    out: dict[str, int] = {}
    device_map = getattr(model, "hf_device_map", None) or {"": next(model.parameters()).device.index}
    for name, dev in device_map.items():
        module = model.get_submodule(name) if name else model
        size = sum(p.numel() * p.element_size() for p in module.parameters())
        key = "gpu" if isinstance(dev, int) or str(dev).startswith("cuda") else str(dev)
        out[key] = out.get(key, 0) + size
    return out


def load(model_id: str) -> PlacementReport:
    """Load `model_id` (a models.yaml id) if not already loaded. Idempotent."""
    with _lock:
        if _loaded.get("id") == model_id:
            return _loaded["report"]
        _release_locked()

        cfg = _config(model_id)
        from backend.models.registry import fetch_command, is_locally_available, weights_dir

        if not is_locally_available(cfg, None):
            raise LocalVisionUnavailable(
                f"weights for {cfg.model} are not at {weights_dir(cfg)}. "
                f"Run once, online: {fetch_command(cfg)}")

        from backend.ingestion.model_cache import force_offline_mode

        force_offline_mode()
        import os

        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        # transformers imports TensorFlow when it is installed, for nothing
        # here: measured ~70 s and several hundred MB of RAM on this box.
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
        import torch

        if not torch.cuda.is_available():
            raise LocalVisionUnavailable("no CUDA device; a CPU-only vision model is the lag we are avoiding")

        from backend.models.gpu import cuda_free_gib, free_ollama_vram

        free_ollama_vram()
        torch.cuda.empty_cache()
        pl = cfg.placement
        gpu_budget = pl.gpu_memory_gib
        note = ""
        free = cuda_free_gib()
        if free is not None and gpu_budget > free - ACTIVATION_HEADROOM_GIB:
            lowered = max(0.5, round(free - ACTIVATION_HEADROOM_GIB, 2))
            note = (f"GPU budget lowered from {gpu_budget} to {lowered} GiB: only {free:.2f} GiB "
                    f"free on the card, {ACTIVATION_HEADROOM_GIB} GiB kept for activations.")
            gpu_budget = lowered

        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        kwargs: dict = {
            "device_map": "auto",
            "max_memory": {0: f"{gpu_budget}GiB", "cpu": f"{pl.cpu_memory_gib}GiB"},
            "torch_dtype": torch.float16,
            "local_files_only": True,
            "low_cpu_mem_usage": True,
        }
        if pl.quantization != "none":
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=pl.quantization == "4bit",
                load_in_8bit=pl.quantization == "8bit",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                llm_int8_enable_fp32_cpu_offload=True,
            )
        path = str(weights_dir(cfg))
        t0 = time.perf_counter()
        try:
            model = Qwen2_5_VLForConditionalGeneration.from_pretrained(path, **kwargs).eval()
        except Exception as exc:  # noqa: BLE001 - surfaced with its cause, never swallowed
            torch.cuda.empty_cache()
            raise LocalVisionUnavailable(f"loading {cfg.model} failed: {type(exc).__name__}: {exc}") from exc
        processor = AutoProcessor.from_pretrained(
            path, local_files_only=True, min_pixels=256 * 28 * 28, max_pixels=pl.max_image_pixels,
            use_fast=True)
        load_s = time.perf_counter() - t0

        by_dev = _weight_bytes_by_device(model)
        gpu_b, cpu_b = by_dev.get("gpu", 0), by_dev.get("cpu", 0) + by_dev.get("disk", 0)
        report = PlacementReport(
            model_id=model_id, model=cfg.model, quantization=pl.quantization,
            gpu_budget_gib=gpu_budget, cpu_budget_gib=pl.cpu_memory_gib,
            gpu_weights_gib=round(gpu_b / 2**30, 2), cpu_weights_gib=round(cpu_b / 2**30, 2),
            gpu_share=round(gpu_b / (gpu_b + cpu_b), 3) if gpu_b + cpu_b else 0.0,
            load_seconds=round(load_s, 1), note=note,
        )
        logger.info("Loaded %s: %s", model_id, report)
        _loaded.update(id=model_id, model=model, processor=processor, report=report)
        return report


def ask(model_id: str, image: str | Path, prompt: str, *, max_new_tokens: int = 256) -> str:
    """The model's reply to `prompt` about one image. Loads on first use."""
    load(model_id)
    import torch
    from PIL import Image

    with _lock:
        model, processor = _loaded["model"], _loaded["processor"]
        img = Image.open(image).convert("RGB")
        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[img], return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        reply = processor.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        return reply.strip()


def placement_report() -> PlacementReport | None:
    return _loaded.get("report")


def _release_locked() -> None:
    if not _loaded:
        return
    _loaded.clear()
    try:
        import gc

        import torch

        gc.collect()
        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def release() -> None:
    """Free the card. Call after a batch of reviews."""
    with _lock:
        _release_locked()

"""Model Provenance Tracking — VIBECODING_SPEC CARD 01 / TOOLS.md row 47.

Provides full chain-of-custody, licensing, origin, and integrity tracking
for every model artifact utilized in the sovereign refinery workbench.

Zero fabricated data: unknown fields are absent or explicitly marked unknown.
"""

from typing import Any


MODEL_PROVENANCE_LEDGER: dict[str, dict[str, Any]] = {
    "coder-model": {
        "id": "coder-model",
        "model_tag": "qwen2.5-coder:7b",
        "backend": "ollama",
        "organization": "Alibaba Cloud / Qwen Team",
        "upstream_repository": "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct",
        "license": "Apache-2.0",
        "architecture": "Qwen2ForCausalLM",
        "parameter_size": "7.61B",
        "quantization": "Q4_K_M",
        "context_window": "32,768 tokens",
        "intended_use": "Refinery unit logic, SQL generation, and code review",
        "air_gap_attestation": "Verified offline. Inference runs strictly on local GPU with loopback daemon; zero egress.",
        "chain_of_custody": {
            "registry_defined_in": "models/models.yaml",
            "managed_by": "Ollama local model store",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "reasoning-model": {
        "id": "reasoning-model",
        "model_tag": "qwen2.5:7b",
        "backend": "ollama",
        "organization": "Alibaba Cloud / Qwen Team",
        "upstream_repository": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct",
        "license": "Apache-2.0",
        "architecture": "Qwen2ForCausalLM",
        "parameter_size": "7.61B",
        "quantization": "Q4_K_M",
        "context_window": "32,768 tokens",
        "intended_use": "MRPL operational reasoning, safety analysis, and citation synthesis",
        "air_gap_attestation": "Verified offline. Inference runs strictly on local GPU with loopback daemon; zero egress.",
        "chain_of_custody": {
            "registry_defined_in": "models/models.yaml",
            "managed_by": "Ollama local model store",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "vision-model": {
        "id": "vision-model",
        "model_tag": "qwen2.5vl:7b",
        "backend": "ollama",
        "organization": "Alibaba Cloud / Qwen Team",
        "upstream_repository": "https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct",
        "license": "Apache-2.0",
        "architecture": "Qwen2_5_VLForConditionalGeneration",
        "parameter_size": "8.29B",
        "quantization": "Q4_K_M",
        "context_window": "32,768 tokens",
        "intended_use": "P&ID schematic visual inspection, chart reading, equipment diagram understanding",
        "air_gap_attestation": "Verified offline. Multimodal vision encoder runs locally without phone-home analytics.",
        "chain_of_custody": {
            "registry_defined_in": "models/models.yaml",
            "managed_by": "Ollama local model store",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "fast-router": {
        "id": "fast-router",
        "model_tag": "phi3.5",
        "backend": "ollama",
        "organization": "Microsoft Research",
        "upstream_repository": "https://huggingface.co/microsoft/Phi-3.5-mini-instruct",
        "license": "MIT",
        "architecture": "Phi3ForCausalLM",
        "parameter_size": "3.82B",
        "quantization": "Q4_K_M",
        "context_window": "128,000 tokens",
        "intended_use": "Sub-agent routing, DAG execution dispatch, and claim self-verification",
        "air_gap_attestation": "Verified offline. Runs locally on loopback; zero egress.",
        "chain_of_custody": {
            "registry_defined_in": "models/models.yaml",
            "managed_by": "Ollama local model store",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "verify-coder-7b": {
        "id": "verify-coder-7b",
        "model_tag": "qwen2.5:7b",
        "backend": "ollama",
        "organization": "Alibaba Cloud / Qwen Team",
        "upstream_repository": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct",
        "license": "Apache-2.0",
        "architecture": "Qwen2ForCausalLM",
        "parameter_size": "7.61B",
        "quantization": "Q4_K_M",
        "context_window": "32,768 tokens",
        "intended_use": "Self-verification of generated calculations and code blocks",
        "air_gap_attestation": "Verified offline. Runs locally on loopback; zero egress.",
        "chain_of_custody": {
            "registry_defined_in": "models/models.yaml",
            "managed_by": "Ollama local model store",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "deck-writer-large": {
        "id": "deck-writer-large",
        "model_tag": "qwen2.5:14b",
        "backend": "ollama",
        "organization": "Alibaba Cloud / Qwen Team",
        "upstream_repository": "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct",
        "license": "Apache-2.0",
        "architecture": "Qwen2ForCausalLM",
        "parameter_size": "14.7B",
        "quantization": "Q4_K_M",
        "context_window": "32,768 tokens",
        "intended_use": "Long-form deck synthesis and cross-document reconciliation",
        "air_gap_attestation": "Verified offline. Runs locally with RAM/VRAM offload; zero egress.",
        "chain_of_custody": {
            "registry_defined_in": "models/models.yaml",
            "managed_by": "Ollama local model store",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "image-model": {
        "id": "image-model",
        "model_tag": "stabilityai/sd-turbo",
        "backend": "diffusers",
        "organization": "Stability AI",
        "upstream_repository": "https://huggingface.co/stabilityai/sd-turbo",
        "license": "Stability AI Non-Commercial Research Community License",
        "architecture": "AutoencoderKL + UNet2DConditionModel",
        "parameter_size": "860M",
        "quantization": "fp16 SafeTensors",
        "context_window": "512x512 1-step diffusion",
        "intended_use": "Abstract section backgrounds and deck cover visuals (no simulated plant records)",
        "air_gap_attestation": "Verified offline via HF_HUB_OFFLINE=1 and local weights in models/image/.",
        "chain_of_custody": {
            "registry_defined_in": "models/models.yaml",
            "managed_by": "Hugging Face Diffusers (offline disk store)",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "page-reviewer": {
        "id": "page-reviewer",
        "model_tag": "Qwen/Qwen2.5-VL-7B-Instruct",
        "backend": "transformers",
        "organization": "Alibaba Cloud (Qwen)",
        "upstream_repository": "https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct",
        "license": "Apache-2.0",
        "architecture": "Qwen2_5_VLForConditionalGeneration",
        "parameter_size": "8.3B",
        "quantization": "bitsandbytes NF4 (4-bit), prepared once on this machine",
        "context_window": "125,000 tokens; images capped at 518,400 pixels by models.yaml",
        "intended_use": "Design review of rendered presentation pages (judgement, never a measurement)",
        "air_gap_attestation": (
            "Verified offline via HF_HUB_OFFLINE=1 and local weights in models/vision/. Loaded "
            "in-process with an explicit GPU/CPU budget rather than by Ollama, which placed it "
            "entirely on the CPU."
        ),
        "chain_of_custody": {
            "registry_defined_in": "models/models.yaml",
            "managed_by": "Hugging Face Transformers (offline disk store)",
            "hash_algorithm": "SHA256",
            "attested_by": "Aryan (deck quality pipeline)",
        },
    },
    "embeddings": {
        "id": "embeddings",
        "model_tag": "BAAI/bge-large-en-v1.5",
        "backend": "sentence-transformers",
        "organization": "Beijing Academy of Artificial Intelligence (BAAI)",
        "upstream_repository": "https://huggingface.co/BAAI/bge-large-en-v1.5",
        "license": "MIT",
        "architecture": "BertModel",
        "parameter_size": "335M (1024-dim dense vectors)",
        "quantization": "fp32",
        "context_window": "512 tokens",
        "intended_use": "Dense vector retrieval for MRPL knowledge base chunk index",
        "air_gap_attestation": "Cached in models/embeddings/ with TRANSFORMERS_OFFLINE=1.",
        "chain_of_custody": {
            "registry_defined_in": "backend/ingestion/embeddings.py",
            "managed_by": "Local cache dir via require_cached()",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "whisper": {
        "id": "whisper",
        "model_tag": "Systran/faster-whisper-base.en",
        "backend": "ctranslate2",
        "organization": "Systran / OpenAI",
        "upstream_repository": "https://huggingface.co/Systran/faster-whisper-base.en",
        "license": "MIT",
        "architecture": "Whisper CTranslate2 Engine",
        "parameter_size": "74M",
        "quantization": "int8 / float16",
        "context_window": "30s audio chunks",
        "intended_use": "Radio dispatch and shift voice note transcription",
        "air_gap_attestation": "Local in-process transcription, no audio data transmitted outbound.",
        "chain_of_custody": {
            "registry_defined_in": "backend/tools/audio/transcription.py",
            "managed_by": "Local model weights",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
    "ocr": {
        "id": "ocr",
        "model_tag": "PaddleOCR-PP-OCRv4",
        "backend": "paddlex",
        "organization": "Baidu Inc.",
        "upstream_repository": "https://github.com/PaddlePaddle/PaddleOCR",
        "license": "Apache-2.0",
        "architecture": "PP-OCRv4 (Text Detection + Direction Classifier + Text Recognition)",
        "parameter_size": "~15M",
        "quantization": "fp32 inference model",
        "context_window": "Arbitrary image resolution",
        "intended_use": "Scanned inspection checklists, P&ID text plates, and OCR box extraction",
        "air_gap_attestation": "Local paddle inference, network phone-home disabled.",
        "chain_of_custody": {
            "registry_defined_in": "backend/tools/vision/ocr_printed.py",
            "managed_by": "Local inference weights",
            "hash_algorithm": "SHA256",
            "attested_by": "Sahil (Sovereign Workbench Audit)",
        },
    },
}


def get_model_provenance(model_id: str) -> dict[str, Any] | None:
    """Retrieve full provenance record for a given model ID."""
    return MODEL_PROVENANCE_LEDGER.get(model_id)


def get_all_provenance() -> dict[str, dict[str, Any]]:
    """Return the complete model provenance ledger."""
    return dict(MODEL_PROVENANCE_LEDGER)

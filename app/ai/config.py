from __future__ import annotations

import importlib.util
from typing import Any

from . import CLASSIFIER_PROMPT_VERSION, STRATEGIST_PROMPT_VERSION


AI_MODEL_NAME = "Qwen/Qwen3-VL-8B-Instruct"
WHISPER_MODEL_NAME = "large-v3-turbo"
AI_STATUSES = (
    "pending",
    "downloading",
    "transcribing",
    "extracting_frames",
    "analyzing",
    "completed",
    "download_failed",
    "transcription_failed",
    "analysis_failed",
)
AI_IN_PROGRESS_STATUSES = (
    "downloading",
    "transcribing",
    "extracting_frames",
    "analyzing",
)
AI_FAILED_STATUSES = (
    "download_failed",
    "transcription_failed",
    "analysis_failed",
)
AI_READY_MESSAGE = "IA local não configurada. Execute ./setup_ai.sh"
AI_CUDA_MESSAGE = "CUDA não está disponível para a IA local."


def _dependency_state() -> dict[str, bool]:
    # find_spec is deliberately used instead of importing torch/Transformers
    # while Flask starts. This keeps AI_ENABLED=false cheap and safe.
    names = {
        "torch": "torch",
        "transformers": "transformers",
        "accelerate": "accelerate",
        "faster_whisper": "faster_whisper",
        "yt_dlp": "yt_dlp",
        "pydantic": "pydantic",
        "Pillow": "PIL",
        "opencv": "cv2",
        "safetensors": "safetensors",
        "huggingface_hub": "huggingface_hub",
    }
    return {label: importlib.util.find_spec(module) is not None for label, module in names.items()}


def runtime_capabilities(settings: dict[str, Any]) -> dict[str, Any]:
    """Return safe, UI-ready local runtime information.

    No model is loaded here. The check only reports whether the optional
    stack appears installed and whether PyTorch can see the requested CUDA
    device. Any import/runtime problem becomes a readable not-ready status.
    """

    dependencies = _dependency_state()
    torch_version = None
    cuda_runtime = None
    gpu_name = None
    vram_gb = None
    cuda_available = False
    if dependencies["torch"]:
        try:
            import torch

            torch_version = getattr(torch, "__version__", None)
            cuda_runtime = getattr(getattr(torch, "version", None), "cuda", None)
            cuda_available = bool(torch.cuda.is_available())
            if cuda_available:
                index = torch.cuda.current_device()
                gpu_name = torch.cuda.get_device_name(index)
                properties = torch.cuda.get_device_properties(index)
                vram_gb = round(properties.total_memory / (1024**3), 1)
        except Exception:
            cuda_available = False

    requested_device = str(settings.get("AI_DEVICE", "cuda")).strip().lower()
    requested_model = str(
        settings.get("AI_VISION_MODEL", AI_MODEL_NAME)
    ).strip()
    expected_model = requested_model == AI_MODEL_NAME
    expected_whisper = settings.get("AI_WHISPER_MODEL", WHISPER_MODEL_NAME) == WHISPER_MODEL_NAME
    expected_whisper_compute = settings.get("AI_WHISPER_COMPUTE_TYPE", "float16") == "float16"
    all_dependencies = all(dependencies.values())
    ready = bool(
        settings.get("AI_ENABLED")
        and requested_device == "cuda"
        and expected_model
        and expected_whisper
        and expected_whisper_compute
        and all_dependencies
        and cuda_available
    )
    if not settings.get("AI_ENABLED"):
        message = AI_READY_MESSAGE
    elif not all_dependencies:
        message = AI_READY_MESSAGE
    elif not cuda_available or requested_device != "cuda":
        message = AI_CUDA_MESSAGE
    elif not expected_model:
        message = f"Use o modelo local obrigatório {AI_MODEL_NAME}."
    elif not expected_whisper or not expected_whisper_compute:
        message = "Use faster-whisper large-v3-turbo com compute_type=float16."
    else:
        message = "IA local pronta."
    return {
        "enabled": bool(settings.get("AI_ENABLED")),
        "ready": ready,
        "message": message,
        "device": requested_device,
        "model": requested_model,
        "whisper_model": settings.get("AI_WHISPER_MODEL", WHISPER_MODEL_NAME),
        "vision_dtype": settings.get("AI_VISION_DTYPE", "bfloat16"),
        "torch_version": torch_version,
        "cuda_runtime": cuda_runtime,
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "dependencies": dependencies,
        "classifier_prompt_version": CLASSIFIER_PROMPT_VERSION,
        "strategist_prompt_version": STRATEGIST_PROMPT_VERSION,
    }


def ensure_runtime_ready(settings: dict[str, Any]) -> dict[str, Any]:
    capabilities = runtime_capabilities(settings)
    if not capabilities["ready"]:
        raise RuntimeError(capabilities["message"])
    return capabilities

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any, Iterable


class VisionInferenceError(RuntimeError):
    """The local Qwen3-VL inference step failed."""


class QwenVisionAnalyzer:
    """Reusable Transformers wrapper for Qwen/Qwen3-VL-8B-Instruct."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-VL-8B-Instruct",
        *,
        dtype: str = "bfloat16",
        device: str = "cuda",
        max_new_tokens: int = 1200,
        model: Any | None = None,
        processor: Any | None = None,
    ):
        self.model_name = model_name
        self.dtype = dtype
        self.device = device
        self.max_new_tokens = max(128, int(max_new_tokens))
        self._model = model
        self._processor = processor

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._processor is not None

    @staticmethod
    def _torch_dtype(torch, name: str):
        normalized = str(name or "bfloat16").lower()
        if normalized in {"bfloat16", "bf16"}:
            return torch.bfloat16
        if normalized in {"float16", "fp16", "half"}:
            return torch.float16
        raise VisionInferenceError(
            "AI_VISION_DTYPE deve ser bfloat16 ou float16; não há quantização automática."
        )

    def load(self):
        if self.loaded:
            return self._model
        if self.model_name != "Qwen/Qwen3-VL-8B-Instruct":
            raise VisionInferenceError(
                "O fluxo local exige exatamente Qwen/Qwen3-VL-8B-Instruct."
            )
        if self.device != "cuda":
            raise VisionInferenceError("O Qwen3-VL local requer device=cuda neste fluxo.")
        try:
            import torch
            from transformers import AutoProcessor
        except ImportError as exc:  # pragma: no cover - setup/runtime path
            raise VisionInferenceError(
                "torch e transformers são necessários. Execute ./setup_ai.sh"
            ) from exc

        model_class = None
        try:
            from transformers import Qwen3VLForConditionalGeneration

            model_class = Qwen3VLForConditionalGeneration
        except ImportError:
            # Transformers releases may expose the same architecture through
            # its generic image-text auto class. The checkpoint remains the
            # mandated Qwen3-VL model; this is only an API compatibility path.
            for class_name in ("AutoModelForImageTextToText", "AutoModelForVision2Seq"):
                model_class = getattr(__import__("transformers", fromlist=[class_name]), class_name, None)
                if model_class is not None:
                    break
        if model_class is None:
            raise VisionInferenceError(
                "A versão instalada do Transformers não expõe o carregador do Qwen3-VL."
            )

        kwargs: dict[str, Any] = {
            "torch_dtype": self._torch_dtype(torch, self.dtype),
            "low_cpu_mem_usage": True,
        }
        # A device map with a single CUDA target keeps the model on the
        # requested GPU and avoids an implicit CPU fallback.
        kwargs["device_map"] = {"": self.device}
        try:
            self._processor = AutoProcessor.from_pretrained(self.model_name)
            self._model = model_class.from_pretrained(self.model_name, **kwargs)
            self._model.eval()
        except Exception as exc:
            self._model = None
            self._processor = None
            if "out of memory" in str(exc).lower():
                raise VisionInferenceError(
                    "Falha de VRAM ao carregar o Qwen3-VL. Reduza AI_MAX_IMAGE_SIDE/AI_MAX_FRAMES."
                ) from exc
            raise VisionInferenceError(f"Não foi possível carregar o Qwen3-VL: {exc}") from exc
        return self._model

    @staticmethod
    def _path_and_timestamp(item: Any) -> tuple[Path, float | None]:
        if hasattr(item, "path"):
            return Path(item.path), float(item.timestamp)
        if isinstance(item, dict):
            return Path(item.get("path")), item.get("timestamp")
        return Path(item), None

    def _messages(self, prompt: str, frame_items: Iterable[Any]) -> tuple[list[dict], list[Any]]:
        content: list[dict[str, Any]] = []
        normalized: list[Any] = []
        for index, item in enumerate(frame_items, start=1):
            path, timestamp = self._path_and_timestamp(item)
            normalized.append(item)
            label = f"Frame {index}"
            if timestamp is not None:
                label += f" em {float(timestamp):.2f}s"
            content.append({"type": "image", "image": path.resolve().as_uri()})
            content.append({"type": "text", "text": f"\n[{label}]"})
        content.append({"type": "text", "text": prompt})
        return [{"role": "user", "content": content}], normalized

    def generate(self, prompt: str, frame_items: Iterable[Any] = ()) -> str:
        model = self.load()
        processor = self._processor
        messages, normalized = self._messages(prompt, frame_items)
        try:
            try:
                import torch
            except ImportError:
                # Injected fake model/processor pairs remain testable in the
                # light Flask environment; the real loader still requires
                # torch and CUDA.
                torch = None

            text = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            process_vision_info = None
            try:
                from qwen_vl_utils import process_vision_info as qwen_process_vision_info

                process_vision_info = qwen_process_vision_info
            except ImportError:
                pass

            processor_kwargs: dict[str, Any] = {
                "text": [text],
                "padding": True,
                "return_tensors": "pt",
            }
            if normalized:
                if process_vision_info is not None:
                    image_inputs, video_inputs = process_vision_info(messages)
                    if image_inputs:
                        processor_kwargs["images"] = image_inputs
                    if video_inputs:
                        processor_kwargs["videos"] = video_inputs
                else:
                    try:
                        from PIL import Image

                        processor_kwargs["images"] = [
                            Image.open(self._path_and_timestamp(item)[0]).convert("RGB")
                            for item in normalized
                        ]
                    except Exception as exc:
                        raise VisionInferenceError(
                            f"Não foi possível preparar os frames para o Qwen3-VL: {exc}"
                        ) from exc
            inputs = processor(**processor_kwargs)
            if hasattr(inputs, "to"):
                inputs = inputs.to(self.device)
            else:
                inputs = {
                    key: value.to(self.device) if hasattr(value, "to") else value
                    for key, value in inputs.items()
                }
            inference_context = torch.inference_mode() if torch is not None else nullcontext()
            with inference_context:
                generated = model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                )
            input_ids = inputs.get("input_ids") if hasattr(inputs, "get") else None
            if input_ids is not None and hasattr(generated, "__iter__"):
                trimmed = [
                    output_ids[len(input_ids[index]) :]
                    for index, output_ids in enumerate(generated)
                ]
            else:
                trimmed = generated
            decoded = processor.batch_decode(
                trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            if not decoded:
                raise VisionInferenceError("O Qwen3-VL retornou uma resposta vazia.")
            return str(decoded[0]).strip()
        except VisionInferenceError:
            raise
        except Exception as exc:
            if "out of memory" in str(exc).lower():
                if torch is not None:
                    try:
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                raise VisionInferenceError(
                    "Falha de VRAM ao analisar o vídeo. Reduza AI_MAX_IMAGE_SIDE e AI_MAX_FRAMES."
                ) from exc
            raise VisionInferenceError(f"Falha de inferência local do Qwen3-VL: {exc}") from exc

    def close(self) -> None:
        self._model = None
        self._processor = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


Qwen3VLAnalyzer = QwenVisionAnalyzer

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class TranscriptionError(RuntimeError):
    """Whisper could not transcribe one video's audio."""


@dataclass
class TranscriptionResult:
    text: str
    segments: list[dict[str, Any]]
    detected_language: str | None
    language_probability: float | None

    @property
    def segments_json(self) -> str:
        return json.dumps(self.segments, ensure_ascii=False, separators=(",", ":"))

    def text_until(self, seconds: float) -> str:
        return transcript_window(self.segments, seconds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "segments": self.segments,
            "detected_language": self.detected_language,
            "language_probability": self.language_probability,
            "transcript_first_3s": self.text_until(3),
            "transcript_first_5s": self.text_until(5),
        }


def transcript_window(segments: Iterable[dict[str, Any]], seconds: float) -> str:
    """Reconstruct the words spoken during the first N seconds."""

    limit = max(0.0, float(seconds))
    texts: list[str] = []
    for segment in segments:
        try:
            start = float(segment.get("start", 0))
            end = float(segment.get("end", start))
        except (TypeError, ValueError):
            continue
        if start >= limit:
            continue
        if end <= 0:
            continue
        words = segment.get("words") or []
        if words:
            for word in words:
                try:
                    word_start = float(word.get("start", 0))
                    word_end = float(word.get("end", word_start))
                except (TypeError, ValueError):
                    continue
                if word_start < limit and word_end > 0:
                    word_text = str(word.get("text") or "").strip()
                    if word_text:
                        texts.append(word_text)
            continue
        text = str(segment.get("text") or "").strip()
        if text:
            texts.append(text)
    return " ".join(texts).strip()


class WhisperTranscriber:
    """One reusable faster-whisper large-v3-turbo instance per worker."""

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        *,
        device: str = "cuda",
        compute_type: str = "float16",
        download_root: str | Path | None = None,
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.download_root = Path(download_root).expanduser().resolve() if download_root else None
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self):
        if self._model is not None:
            return self._model
        if self.device != "cuda":
            raise TranscriptionError("O Whisper local requer device=cuda neste fluxo.")
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - setup/runtime path
            raise TranscriptionError(
                "faster-whisper não está instalado. Execute ./setup_ai.sh"
            ) from exc
        kwargs: dict[str, Any] = {
            "device": self.device,
            "compute_type": self.compute_type,
        }
        if self.download_root is not None:
            kwargs["download_root"] = str(self.download_root)
        try:
            self._model = WhisperModel(self.model_name, **kwargs)
        except Exception as exc:
            raise TranscriptionError(f"Não foi possível carregar o Whisper: {exc}") from exc
        return self._model

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        model = self.load()
        try:
            segments_iterator, info = model.transcribe(
                str(Path(audio_path).resolve()),
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=True,
                word_timestamps=True,
            )
            segments: list[dict[str, Any]] = []
            for segment in segments_iterator:
                start = float(getattr(segment, "start", 0.0))
                end = float(getattr(segment, "end", start))
                text = str(getattr(segment, "text", "") or "").strip()
                if text:
                    normalized_segment = {
                        "start": round(max(0.0, start), 3),
                        "end": round(max(start, end), 3),
                        "text": text,
                    }
                    words = getattr(segment, "words", None)
                    if words:
                        normalized_words = []
                        for word in words:
                            word_start = getattr(word, "start", None)
                            word_end = getattr(word, "end", None)
                            word_text = str(getattr(word, "word", "") or "").strip()
                            if word_start is None or word_end is None or not word_text:
                                continue
                            normalized_words.append(
                                {
                                    "start": round(max(0.0, float(word_start)), 3),
                                    "end": round(max(float(word_start), float(word_end)), 3),
                                    "text": word_text,
                                }
                            )
                        if normalized_words:
                            normalized_segment["words"] = normalized_words
                    segments.append(normalized_segment)
            full_text = " ".join(item["text"] for item in segments).strip()
            language = getattr(info, "language", None)
            probability = getattr(info, "language_probability", None)
            probability = float(probability) if probability is not None else None
            return TranscriptionResult(
                text=full_text,
                segments=segments,
                detected_language=str(language) if language else None,
                language_probability=probability,
            )
        except Exception as exc:
            raise TranscriptionError(f"Falha ao transcrever áudio: {exc}") from exc

    def close(self) -> None:
        self._model = None


def transcribe_audio(
    audio_path: str | Path,
    *,
    model_name: str = "large-v3-turbo",
    device: str = "cuda",
    compute_type: str = "float16",
) -> TranscriptionResult:
    return WhisperTranscriber(
        model_name=model_name,
        device=device,
        compute_type=compute_type,
    ).transcribe(audio_path)

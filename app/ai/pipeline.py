from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import CLASSIFIER_PROMPT_VERSION
from .classifier import AnalysisValidationError, SemanticClassifier
from .config import AI_MODEL_NAME
from .downloader import DownloadError, VideoDownloader, safe_video_id
from .media import FrameSample, MediaError, cleanup_video_directory, extract_audio, extract_frames, probe_duration
from .transcriber import TranscriptionError, WhisperTranscriber
from .vision import VisionInferenceError


LOGGER = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    tiktok_video_id: str
    status: str
    skipped: bool = False
    error: str | None = None
    frames_selected: int = 0


class VideoAnalysisPipeline:
    """Process exactly one video and persist every durable checkpoint."""

    def __init__(
        self,
        database: Any,
        downloader: VideoDownloader,
        transcriber: WhisperTranscriber,
        vision: Any,
        *,
        temp_dir: str | Path,
        model_name: str = AI_MODEL_NAME,
        prompt_version: str = CLASSIFIER_PROMPT_VERSION,
        max_frames: int = 12,
        max_image_side: int = 896,
        delete_temp_files: bool = True,
        media_module: Any | None = None,
        stage_callback: Callable[[str, str], None] | None = None,
    ):
        self.database = database
        self.downloader = downloader
        self.transcriber = transcriber
        self.classifier = SemanticClassifier(vision)
        self.temp_dir = Path(temp_dir).expanduser().resolve()
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.max_frames = max(1, int(max_frames))
        self.max_image_side = max(64, int(max_image_side))
        self.delete_temp_files = bool(delete_temp_files)
        self.media = media_module
        self.stage_callback = stage_callback

    def _media(self, name: str, fallback: Callable):
        return getattr(self.media, name, fallback) if self.media is not None else fallback

    def _stage(self, video_id: str, stage: str) -> None:
        if self.stage_callback:
            self.stage_callback(video_id, stage)

    @staticmethod
    def _error_message(exc: Exception) -> str:
        text = str(exc).strip()
        if "out of memory" in text.lower() or "cuda out of memory" in text.lower():
            return "Falha de VRAM ao analisar o vídeo. Reduza AI_MAX_IMAGE_SIDE e AI_MAX_FRAMES."
        return text[:2000] or "Falha não especificada."

    def process(self, video: dict[str, Any], *, force: bool = False) -> PipelineResult:
        video_id = str(video.get("tiktok_video_id") or "").strip()
        if not video_id:
            return PipelineResult("", "analysis_failed", error="Vídeo sem tiktok_video_id.")
        current = self.database.get_ai_analysis(video_id)
        if (
            not force
            and current
            and current.get("status") == "completed"
            and current.get("model_name") == self.model_name
            and current.get("prompt_version") == self.prompt_version
        ):
            return PipelineResult(video_id, "completed", skipped=True)

        self.database.begin_ai_attempt(video_id, self.model_name, self.prompt_version)
        try:
            video_directory: Path | None = (
                self.temp_dir / safe_video_id(video_id)
            ).resolve()
        except DownloadError as exc:
            message = self._error_message(exc)
            self.database.mark_ai_failure(video_id, "download_failed", message)
            return PipelineResult(video_id, "download_failed", error=message)
        success = False
        frames_selected = 0
        stage = "downloading"
        try:
            self._stage(video_id, "downloading")
            LOGGER.info("[AI] vídeo %s download iniciado", video_id)
            video_path = self.downloader.download(video.get("share_url"), video_id)
            video_path = Path(video_path).resolve()
            if video_path.parent != video_directory or video_path.name != "video.mp4":
                raise DownloadError("O downloader retornou um caminho temporário inesperado.")
            LOGGER.info("[AI] vídeo %s download concluído", video_id)

            stage = "media"
            duration = self._media("probe_duration", probe_duration)(video_path)
            audio_path = video_directory / "audio.wav"
            stage = "transcribing"
            self.database.set_ai_status(video_id, "transcribing", current_stage="transcribing")
            self._stage(video_id, "transcribing")
            self._media("extract_audio", extract_audio)(video_path, audio_path)
            transcription = self.transcriber.transcribe(audio_path)
            self.database.save_ai_transcription(
                video_id,
                text=transcription.text,
                segments_json=transcription.segments_json,
                detected_language=transcription.detected_language,
                language_probability=transcription.language_probability,
                first_3s=transcription.text_until(3),
                first_5s=transcription.text_until(5),
            )
            LOGGER.info("[AI] vídeo %s transcrição concluída", video_id)

            self.database.set_ai_status(
                video_id, "extracting_frames", current_stage="extracting_frames"
            )
            stage = "extracting_frames"
            self._stage(video_id, "extracting_frames")
            frames_directory = video_directory / "frames"
            frames = self._media("extract_frames", extract_frames)(
                video_path,
                frames_directory,
                duration,
                max_frames=self.max_frames,
                max_image_side=self.max_image_side,
            )
            frames = list(frames or [])
            frames_selected = len(frames)
            LOGGER.info("[AI] vídeo %s %s frames selecionados", video_id, frames_selected)

            self.database.set_ai_status(video_id, "analyzing", current_stage="analyzing")
            stage = "analyzing"
            self._stage(video_id, "analyzing")
            analysis = self.classifier.classify(
                video,
                transcription_text=transcription.text,
                segments=transcription.segments,
                frames=frames,
                detected_language=transcription.detected_language,
            )
            self.database.save_ai_completed(
                video_id,
                analysis=analysis,
                analysis_json=json.dumps(
                    analysis, ensure_ascii=False, separators=(",", ":")
                ),
                model_name=self.model_name,
                prompt_version=self.prompt_version,
            )
            LOGGER.info("[AI] vídeo %s classificação concluída", video_id)
            success = True
            return PipelineResult(video_id, "completed", frames_selected=frames_selected)
        except DownloadError as exc:
            message = self._error_message(exc)
            self.database.mark_ai_failure(video_id, "download_failed", message)
            LOGGER.warning("[AI] vídeo %s download falhou: %s", video_id, message)
            return PipelineResult(video_id, "download_failed", error=message)
        except TranscriptionError as exc:
            message = self._error_message(exc)
            self.database.mark_ai_failure(video_id, "transcription_failed", message)
            LOGGER.warning("[AI] vídeo %s transcrição falhou: %s", video_id, message)
            return PipelineResult(video_id, "transcription_failed", error=message)
        except (AnalysisValidationError, VisionInferenceError, MediaError) as exc:
            message = self._error_message(exc)
            self.database.mark_ai_failure(video_id, "analysis_failed", message)
            LOGGER.warning("[AI] vídeo %s análise falhou: %s", video_id, message)
            return PipelineResult(video_id, "analysis_failed", error=message)
        except Exception as exc:
            message = self._error_message(exc)
            failure_status = {
                "downloading": "download_failed",
                "transcribing": "transcription_failed",
            }.get(stage, "analysis_failed")
            self.database.mark_ai_failure(video_id, failure_status, message)
            LOGGER.exception("[AI] vídeo %s falhou", video_id)
            return PipelineResult(video_id, failure_status, error=message)
        finally:
            if video_directory is not None:
                try:
                    cleanup_video_directory(
                        self.temp_dir,
                        video_id,
                        # An error should never leave the derived audio/frames
                        # behind. On success, honor the user's debug setting.
                        delete_video=self.delete_temp_files or not success,
                    )
                    LOGGER.info("[AI] vídeo %s arquivos temporários removidos", video_id)
                except Exception as cleanup_error:
                    LOGGER.warning(
                        "[AI] vídeo %s limpeza temporária falhou: %s",
                        video_id,
                        self._error_message(cleanup_error),
                    )


def process_video(
    database: Any,
    video: dict[str, Any],
    *,
    downloader: VideoDownloader,
    transcriber: WhisperTranscriber,
    vision: Any,
    temp_dir: str | Path,
    **kwargs: Any,
) -> PipelineResult:
    return VideoAnalysisPipeline(
        database,
        downloader,
        transcriber,
        vision,
        temp_dir=temp_dir,
        **kwargs,
    ).process(video)

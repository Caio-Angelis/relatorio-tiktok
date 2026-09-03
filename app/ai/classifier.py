from __future__ import annotations

import json
import math
from typing import Any, Iterable

from . import CLASSIFIER_PROMPT_VERSION
from .schemas import VideoSemanticAnalysis, model_dump, model_validate


class AnalysisValidationError(ValueError):
    """The local VLM did not produce a valid semantic analysis object."""


CLASSIFIER_SYSTEM_PROMPT = """Você é um classificador de conteúdo curto do TikTok.
Analise somente o conteúdo e a estrutura do vídeo, nunca seu desempenho.
Os frames estão ordenados cronologicamente e cada um tem timestamp; a
transcrição tem segmentos com timestamps. Os primeiros 3 segundos e os
primeiros 5 segundos são extremamente importantes. Observe texto na tela,
diferenças entre narração e texto visual, pessoas, instrumentos, objetos,
marcas e contexto. Não infira uma pessoa específica sem evidência suficiente,
não invente marcas e não invente CTA. Se uma informação não estiver evidente,
use null ou uma lista vazia e seja conservador. Produza somente o objeto JSON
solicitado, sem markdown, comentários ou texto antes/depois.

O objeto precisa seguir este contrato:
primary_topic (string ou null), secondary_topics (lista de strings),
content_type (string ou null), format (string ou null), hook_type (string ou
null), hook_text (string ou null), hook_summary (string ou null),
hook_strengths (lista de strings), person_names, bands, artists, products e
subjects (listas de strings), visual_style, editing_style, caption_style,
narration_style e tone (strings ou null), cta_type e cta_text (string ou
null), structure (lista de strings), first_3_seconds e first_5_seconds
(strings ou null), opening_visual e opening_text (strings ou null), summary
(string ou null), keywords (lista de strings), language (string ou null),
confidence (número entre 0 e 1 ou null), has_face, has_guitar,
has_on_screen_captions e uses_ai_generated_visuals (boolean ou null),
estimated_scene_changes (inteiro ou null).

Use termos consistentes quando houver evidência, como biografia, curiosidade,
tutorial, review, historia, noticia, comparacao, demonstracao, opiniao, meme,
performance, produto, lista ou explicacao para content_type; e afirmacao_forte,
pergunta, curiosidade, promessa, controversia, problema, resultado_primeiro,
lista, historia, surpresa ou autoridade para hook_type. Não force categorias
quando elas não se aplicarem."""


CORRECTION_PROMPT = """A resposta anterior não foi um JSON válido para o contrato.
Corrija-a localmente. Retorne somente um objeto JSON válido, sem markdown,
preservando apenas informações sustentadas pelos frames e pela transcrição.
Use null/lista vazia quando faltar evidência. Não acrescente explicações."""


class _JsonDecoderError(ValueError):
    pass


def extract_json_object(raw: str) -> dict[str, Any]:
    """Extract the first decodable JSON object without regex heuristics."""

    if not isinstance(raw, str) or not raw.strip():
        raise _JsonDecoderError("Resposta vazia.")
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json\n"):
            text = text[5:].lstrip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise _JsonDecoderError("Nenhum objeto JSON válido foi encontrado.")


def _clean_string(value: Any, max_length: int = 4000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"null", "none", "n/a", "nenhum", "não", "nao"}:
        return None
    return text[:max_length]


def _clean_list(value: Any, max_items: int = 50, max_length: int = 500) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        cleaned = _clean_string(item, max_length)
        if cleaned and cleaned not in result:
            result.append(cleaned)
        if len(result) >= max_items:
            break
    return result


def _clean_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "sim", "yes"}:
            return True
        if normalized in {"false", "0", "não", "nao", "no"}:
            return False
    return None


def normalize_analysis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize benign formatting variation before Pydantic validation."""

    list_fields = {
        "secondary_topics",
        "hook_strengths",
        "person_names",
        "bands",
        "artists",
        "products",
        "subjects",
        "structure",
        "keywords",
    }
    string_fields = {
        "primary_topic",
        "content_type",
        "format",
        "hook_type",
        "hook_text",
        "hook_summary",
        "visual_style",
        "editing_style",
        "caption_style",
        "narration_style",
        "tone",
        "cta_type",
        "cta_text",
        "first_3_seconds",
        "first_5_seconds",
        "opening_visual",
        "opening_text",
        "summary",
        "language",
    }
    bool_fields = {
        "has_face",
        "has_guitar",
        "has_on_screen_captions",
        "uses_ai_generated_visuals",
    }
    normalized: dict[str, Any] = {}
    for field in list_fields:
        normalized[field] = _clean_list(payload.get(field))
    for field in string_fields:
        normalized[field] = _clean_string(payload.get(field))
    for field in bool_fields:
        normalized[field] = _clean_bool(payload.get(field))
    confidence = payload.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
        if confidence is not None and confidence > 1 and confidence <= 100:
            confidence /= 100
        if confidence is not None and (not math.isfinite(confidence) or not 0 <= confidence <= 1):
            confidence = None
    except (TypeError, ValueError):
        confidence = None
    normalized["confidence"] = confidence
    scene_changes = payload.get("estimated_scene_changes")
    try:
        scene_changes = max(0, int(scene_changes)) if scene_changes is not None else None
    except (TypeError, ValueError):
        scene_changes = None
    normalized["estimated_scene_changes"] = scene_changes
    return normalized


def validate_analysis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_analysis_payload(payload)
    if not any(
        normalized.get(field)
        for field in ("primary_topic", "content_type", "format", "hook_type", "summary", "structure")
    ):
        raise AnalysisValidationError("O objeto semântico não contém campos de análise.")
    try:
        model = model_validate(VideoSemanticAnalysis, normalized)
    except Exception as exc:
        raise AnalysisValidationError(f"Schema semântico inválido: {exc}") from exc
    return model_dump(model)


def parse_analysis_json(raw: str) -> dict[str, Any]:
    try:
        return validate_analysis_payload(extract_json_object(raw))
    except AnalysisValidationError:
        raise
    except Exception as exc:
        raise AnalysisValidationError(str(exc)) from exc


def _frame_metadata(frames: Iterable[Any]) -> list[dict[str, Any]]:
    result = []
    for index, item in enumerate(frames, start=1):
        timestamp = getattr(item, "timestamp", None)
        if isinstance(item, dict):
            timestamp = item.get("timestamp", timestamp)
        result.append({"frame": index, "timestamp": timestamp})
    return result


def build_classifier_prompt(
    video: dict[str, Any],
    transcription_text: str,
    segments: list[dict[str, Any]],
    frames: Iterable[Any],
    detected_language: str | None = None,
) -> str:
    # Deliberately select only semantic inputs. Current views, rates and
    # percentiles never enter the initial classifier prompt.
    semantic_video = {
        "description": video.get("description"),
        "title": video.get("title"),
        "duration_seconds": video.get("duration"),
        "detected_language": detected_language,
    }
    return (
        CLASSIFIER_SYSTEM_PROMPT
        + "\n\nDados do vídeo:\n"
        + json.dumps(semantic_video, ensure_ascii=False)
        + "\nSegmentos da transcrição:\n"
        + json.dumps(segments, ensure_ascii=False)
        + "\nTexto completo da transcrição:\n"
        + (transcription_text or "[sem fala detectada]")
        + "\nFrames disponíveis, em ordem:\n"
        + json.dumps(_frame_metadata(frames), ensure_ascii=False)
    )


class SemanticClassifier:
    def __init__(self, vision: Any):
        self.vision = vision

    def classify(
        self,
        video: dict[str, Any],
        *,
        transcription_text: str,
        segments: list[dict[str, Any]],
        frames: Iterable[Any],
        detected_language: str | None = None,
    ) -> dict[str, Any]:
        frames = list(frames)
        prompt = build_classifier_prompt(
            video,
            transcription_text,
            segments,
            frames,
            detected_language,
        )
        raw = self.vision.generate(prompt, frames)
        try:
            return parse_analysis_json(raw)
        except Exception as first_error:
            # A second attempt is still entirely local and uses the same
            # loaded Qwen process. The first response is intentionally not
            # logged because it may contain a large transcription-derived text.
            correction = (
                prompt
                + "\n\n"
                + CORRECTION_PROMPT
                + "\nResposta anterior (somente para correção):\n"
                + str(raw)[:16000]
            )
            try:
                repaired = self.vision.generate(correction, frames)
                return parse_analysis_json(repaired)
            except Exception as second_error:
                raise AnalysisValidationError(
                    f"JSON semântico inválido após duas tentativas: {second_error}"
                ) from first_error

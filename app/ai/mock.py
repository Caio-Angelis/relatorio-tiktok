from __future__ import annotations

import json
from typing import Any


MOCK_MODEL = "mock-local"
MOCK_PROMPT_VERSION = "mock-1"


def _mock_analysis(video: dict[str, Any], index: int) -> dict[str, Any]:
    description = (video.get("description") or video.get("title") or "").casefold()
    if "tutorial" in description or "dica" in description or "exercício" in description:
        content_type, hook_type = "tutorial", "promessa"
    elif "comparação" in description or "vs" in description:
        content_type, hook_type = "comparacao", "pergunta"
    elif "review" in description or "teste" in description:
        content_type, hook_type = "review", "resultado_primeiro"
    else:
        content_type, hook_type = "explicacao", "curiosidade"
    topic = "guitarra / timbre / técnica"
    return {
        "primary_topic": topic,
        "secondary_topics": ["música"],
        "content_type": content_type,
        "format": "narracao + demonstracao",
        "hook_type": hook_type,
        "hook_text": video.get("description"),
        "hook_summary": "Abertura curta baseada na promessa do vídeo.",
        "hook_strengths": ["tema aparece cedo"],
        "person_names": [],
        "bands": [],
        "artists": [],
        "products": [],
        "subjects": ["guitarra"],
        "visual_style": "demonstração direta",
        "editing_style": "cortes simples",
        "caption_style": "texto curto na tela",
        "narration_style": "explicação",
        "tone": "didático",
        "cta_type": None,
        "cta_text": None,
        "structure": ["gancho", "contextualização", "explicação", "conclusão"],
        "first_3_seconds": "Apresenta o assunto principal.",
        "first_5_seconds": "Explica a promessa inicial.",
        "opening_visual": "Imagem de apoio relacionada à guitarra.",
        "opening_text": video.get("description"),
        "summary": video.get("description"),
        "keywords": ["guitarra", "timbre", "música"],
        "language": "pt",
        "confidence": 0.5 + (index % 3) * 0.1,
        "has_face": False,
        "has_guitar": True,
        "has_on_screen_captions": True,
        "uses_ai_generated_visuals": False,
        "estimated_scene_changes": 3 + index % 4,
    }


def seed_mock_ai_analyses(database: Any) -> None:
    """Populate deterministic semantic examples without loading any model."""

    database.ensure_ai_analysis_rows()
    videos = database.get_videos("recent")
    for index, video in enumerate(videos):
        current = database.get_ai_analysis(video["tiktok_video_id"])
        if current and current.get("status") == "completed":
            continue
        analysis = _mock_analysis(video, index)
        database.save_ai_completed(
            video["tiktok_video_id"],
            analysis=analysis,
            analysis_json=json.dumps(analysis, ensure_ascii=False, separators=(",", ":")),
            model_name=MOCK_MODEL,
            prompt_version=MOCK_PROMPT_VERSION,
            analyzed_at=video.get("updated_at"),
        )
        database.save_ai_transcription(
            video["tiktok_video_id"],
            text=video.get("description") or "",
            segments_json=json.dumps(
                [{"start": 0.0, "end": 3.0, "text": video.get("description") or ""}],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            detected_language="pt",
            language_probability=1.0,
            first_3s=video.get("description") or "",
            first_5s=video.get("description") or "",
        )

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ..analytics import enrich_videos, semantic_analytics
from ..database import Database, utc_now_iso
from . import STRATEGIST_PROMPT_VERSION
from .config import AI_MODEL_NAME
from .classifier import extract_json_object
from .schemas import StrategicReport, model_dump, model_validate


class StrategyValidationError(ValueError):
    pass


def _number_text(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def _percent_text(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _ratio_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.1f}x"
    except (TypeError, ValueError):
        return None


def _evidence_for_row(row: dict, baseline: dict) -> list[str]:
    label = row.get("label") or row.get("key") or "este padrão"
    sample = row.get("sample_size", 0)
    evidence = []
    median_views = row.get("median_views")
    if median_views is not None:
        sentence = f"{sample} vídeo(s) de {label} tiveram mediana de {_number_text(median_views)} views."
        ratio = row.get("ratios", {}).get("views")
        if ratio is None and baseline.get("median_views"):
            ratio = median_views / baseline["median_views"]
        ratio_text = _ratio_text(ratio)
        if ratio_text:
            sentence = sentence[:-1] + f", {ratio_text} a mediana da conta."
        evidence.append(sentence)
    if row.get("median_share_rate") is not None:
        evidence.append(
            f"Share rate mediana do padrão: {_percent_text(row['median_share_rate'])}."
        )
    if row.get("median_engagement") is not None:
        evidence.append(
            f"Engagement mediano do padrão: {_percent_text(row['median_engagement'])}."
        )
    if row.get("average_views_percentile") is not None:
        evidence.append(
            f"Percentil médio de views observado: {float(row['average_views_percentile']):.1f}."
        )
    if sample < 5:
        evidence.append(f"Amostra de {sample}: {row.get('evidence_level', 'sinal limitado')}.")
    return evidence


def _pattern_with_evidence(row: dict, baseline: dict) -> dict:
    result = dict(row)
    result["evidence"] = _evidence_for_row(row, baseline)
    return result


def _topic_from_pattern(row: dict) -> tuple[str | None, str | None]:
    dimension = row.get("dimension")
    label = str(row.get("label") or "")
    if dimension == "topic_hook" and " + " in label:
        return tuple(label.split(" + ", 1))  # type: ignore[return-value]
    if dimension == "topics":
        return label or None, None
    return None, label or None


def _duration_for_pattern(row: dict) -> str | None:
    duration = row.get("median_duration_seconds")
    if duration is None:
        return None
    try:
        return f"aproximadamente {round(float(duration))}s"
    except (TypeError, ValueError):
        return None


def _hook_phrase(hook_type: str | None, topic: str | None) -> str:
    subject = topic or "esse assunto"
    phrases = {
        "afirmacao_forte": f"O detalhe sobre {subject} que quase ninguém percebe",
        "pergunta": f"Você sabe por que {subject} funciona desse jeito?",
        "curiosidade": f"A curiosidade sobre {subject} que muda a forma de ver o tema",
        "promessa": f"Em poucos segundos, entenda o essencial sobre {subject}",
        "controversia": f"A opinião controversa sobre {subject} que merece contexto",
        "problema": f"O erro mais comum quando o assunto é {subject}",
        "resultado_primeiro": f"O resultado de {subject} antes da explicação",
        "lista": f"3 coisas sobre {subject} que valem a pena conhecer",
        "historia": f"Antes de tudo, a história de {subject}",
        "surpresa": f"O que ninguém espera sobre {subject}",
        "autoridade": f"O que especialistas ensinam sobre {subject}",
    }
    return phrases.get(hook_type or "", f"Uma explicação direta sobre {subject}")


def _idea_from_row(row: dict, baseline: dict, *, experimental: bool = False) -> dict:
    topic, hook = _topic_from_pattern(row)
    content_type = None
    label = str(row.get("label") or "")
    if row.get("dimension") == "content_types":
        content_type = label
    elif row.get("dimension") == "duration_content_type" and " + " in label:
        _duration, content_type = label.split(" + ", 1)
    elif row.get("dimension") == "topic_hook" and topic:
        content_type = "explicacao" if experimental else None
    if not topic:
        topic = label if row.get("dimension") in {"topics", "topic_hook"} else None
    if not hook and row.get("dimension") == "hooks":
        hook = label
    duration = _duration_for_pattern(row)
    evidence = _evidence_for_row(row, baseline)
    title_parts = [part for part in (topic, content_type or ("experimento" if experimental else None)) if part]
    title = " — ".join(title_parts) or f"Explorar o padrão {label}"
    structure = ["gancho", "contextualização", "entrega principal", "conclusão"]
    if experimental:
        structure.insert(2, "variação experimental")
    # This is a communication confidence band derived from the prioritization
    # score, not a probability or a causal forecast.
    confidence = min(0.95, max(0.15, float(row.get("score") or 0.25) / 2))
    return {
        "title": title,
        "topic": topic,
        "content_type": content_type,
        "hook_type": hook,
        "suggested_hook": _hook_phrase(hook, topic),
        "recommended_duration": duration,
        "structure": structure,
        "why": evidence[:3],
        "evidence": evidence,
        "confidence": confidence,
    }


def _unique_ideas(rows: list[dict], baseline: dict, *, experimental: bool) -> list[dict]:
    result = []
    titles: set[str] = set()
    for row in rows:
        if row.get("sample_size", 0) < 1:
            continue
        idea = _idea_from_row(row, baseline, experimental=experimental)
        if idea["title"] in titles:
            continue
        titles.add(idea["title"])
        result.append(idea)
        if len(result) == 5:
            break
    return result


def build_insight_payload(
    videos: list[dict], analyses: list[dict], account: dict | None = None
) -> tuple[dict, dict]:
    """Build compact strategy input without full transcripts or raw model text."""

    semantic = semantic_analytics(videos, analyses)
    if isinstance(analyses, dict):
        analysis_records = []
        for analysis_id, value in analyses.items():
            record = dict(value) if isinstance(value, dict) else {}
            record.setdefault("tiktok_video_id", analysis_id)
            analysis_records.append(record)
    else:
        analysis_records = list(analyses or [])
    completed_ids = {
        str(item.get("tiktok_video_id"))
        for item in analysis_records
        if item.get("status") in (None, "completed")
    }
    analyzed_videos = [
        video for video in videos if str(video.get("tiktok_video_id")) in completed_ids
    ]
    sorted_videos = sorted(
        analyzed_videos,
        key=lambda video: (
            video.get("view_count") if video.get("view_count") is not None else -1,
            str(video.get("tiktok_video_id")),
        ),
        reverse=True,
    )

    def compact_video(video: dict) -> dict:
        analytics = video.get("analytics") or {}
        return {
            "id": video.get("tiktok_video_id"),
            "description": (video.get("description") or video.get("title") or "")[:180],
            "duration": video.get("duration"),
            "duration_bucket": video.get("duration_bucket"),
            "views": video.get("view_count"),
            "engagement_rate": analytics.get("engagement_rate"),
            "share_rate": analytics.get("share_rate"),
            "views_percentile": analytics.get("views_percentile"),
            "recent_views_per_hour": analytics.get("recent_views_per_hour"),
            "views_24h": (analytics.get("growth") or {}).get("views", {}).get("24h"),
            "views_48h": (analytics.get("growth") or {}).get("views", {}).get("48h"),
        }

    payload = {
        "account": {
            "display_name": (account or {}).get("display_name"),
            "videos_analyzed": len(analyzed_videos),
            "videos_in_library": len(videos),
            "channel_median_views": semantic["baselines"].get("median_views"),
            "channel_median_engagement": semantic["baselines"].get("median_engagement"),
            "channel_median_share_rate": semantic["baselines"].get("median_share_rate"),
        },
        "groups": semantic["groups"],
        "pattern_ranking": semantic["pattern_ranking"][:30],
        "score_formula": semantic["score_formula"],
        "recent_usage": semantic["recent_usage"],
        "top_videos": [compact_video(video) for video in sorted_videos[:10]],
        "bottom_videos": [compact_video(video) for video in sorted_videos[-10:]],
        "last_videos": [
            compact_video(video)
            for video in sorted(
                analyzed_videos,
                key=lambda item: (item.get("create_time") or 0, str(item.get("tiktok_video_id"))),
                reverse=True,
            )[:20]
        ],
    }
    fingerprint_data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(fingerprint_data.encode("utf-8")).hexdigest()
    return payload, {"fingerprint": fingerprint, "semantic": semantic}


def deterministic_insight_report(payload: dict, metadata: dict) -> dict:
    semantic = metadata["semantic"]
    baseline = semantic["baselines"]
    ranked = [
        _pattern_with_evidence(row, baseline)
        for row in semantic["pattern_ranking"]
    ]
    priority_rows = ranked[:10]
    experimental_rows = [
        row
        for row in ranked
        if row.get("dimension") in {"topic_hook", "format_hook", "content_types", "topics"}
        and row not in priority_rows
    ]
    if not experimental_rows:
        experimental_rows = ranked[5:]
    return {
        "summary": (
            f"{payload['account']['videos_analyzed']} vídeos têm análise semântica local; "
            "os grupos abaixo mostram associações observadas no histórico do canal."
        ),
        "what_is_working": ranked[:8],
        "best_hooks": semantic["groups"].get("hooks", [])[:8],
        "best_formats": semantic["groups"].get("formats", [])[:8],
        "strongest_topics": semantic["groups"].get("topics", [])[:8],
        "strongest_people_bands": (
            semantic["groups"].get("people", [])[:5]
            + semantic["groups"].get("bands", [])[:5]
        ),
        "promising_combinations": (
            semantic["groups"].get("topic_hook", [])[:8]
            + semantic["groups"].get("format_hook", [])[:4]
        ),
        "recent_usage": semantic["recent_usage"],
        "priority_ideas": _unique_ideas(priority_rows, baseline, experimental=False),
        "experimental_ideas": _unique_ideas(experimental_rows, baseline, experimental=True),
        "limitations": [
            "Associação histórica não prova causalidade.",
            "Amostras com menos de 5 vídeos são sinais internos limitados.",
            "O TikTok não forneceu watch time, retenção, completion rate, origem de tráfego ou seguidores ganhos por vídeo.",
        ],
        "generated_by": "deterministic-local-analytics",
    }


def build_strategist_prompt(payload: dict) -> str:
    return """Você é o estrategista local de conteúdo de um canal TikTok.
Use exclusivamente o payload estruturado abaixo, que foi calculado a partir
dos vídeos e métricas reais do próprio canal. Não invente métricas, amostras,
percentis, pessoas, bandas ou causalidade. Fale em associação/padrão observado.
Não use watch time, retenção, completion rate, origem de tráfego ou seguidores
ganhos por vídeo, pois esses dados não existem no payload. Respeite o tamanho
da amostra: 1 caso isolado, 2 sinal preliminar, 3-4 padrão possível e >=5
evidência interna mais útil. Não envie nem peça transcrições completas.

Retorne somente JSON com estas chaves: summary, what_is_working, best_hooks,
best_formats, strongest_topics, strongest_people_bands,
promising_combinations, recent_usage, priority_ideas, experimental_ideas e
limitations. Cada ideia deve conter title, topic, content_type, hook_type,
suggested_hook, recommended_duration, structure, why, evidence e confidence.
As strings de evidence devem ser copiadas exatamente do campo evidence dos
padrões existentes; se não houver evidência, deixe a lista vazia. Gere até 5
ideias prioritárias próximas dos padrões melhor ranqueados e até 5
experimentais, sem repetir dez vezes a mesma pessoa/tema. Uma ideia
experimental pode trocar o tema mantendo um formato ou gancho observado,
mas não deve fingir que o tema novo já teve desempenho.

PAYLOAD:
""" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _validate_strategy(raw: str) -> dict:
    try:
        payload = extract_json_object(raw)
        return model_dump(model_validate(StrategicReport, payload))
    except Exception as exc:
        raise StrategyValidationError(f"Relatório estratégico inválido: {exc}") from exc


def _sanitize_llm_report(report: dict, deterministic: dict) -> dict:
    """Keep model recommendations tied to deterministic evidence strings."""

    catalog = {
        evidence
        for row in deterministic.get("what_is_working", [])
        for evidence in row.get("evidence", [])
    }
    result = dict(report)
    # Never render model-invented aggregate numbers. The deterministic
    # calculations remain the source of truth for every performance section;
    # Qwen contributes wording/ideas only.
    for field in (
        "summary",
        "what_is_working",
        "best_hooks",
        "best_formats",
        "strongest_topics",
        "strongest_people_bands",
        "promising_combinations",
        "recent_usage",
        "limitations",
    ):
        if field in deterministic:
            result[field] = deterministic[field]
    for field in ("priority_ideas", "experimental_ideas"):
        cleaned = []
        seen = set()
        for idea in report.get(field) or []:
            if not isinstance(idea, dict):
                continue
            title = str(idea.get("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            evidence = [item for item in idea.get("evidence", []) if item in catalog]
            if not evidence:
                evidence = [item for item in idea.get("why", []) if item in catalog]
            if not evidence:
                # An idea without a traceable fact is not useful for this
                # report; deterministic evidence-backed candidates are added
                # below instead.
                continue
            copy = dict(idea)
            copy["evidence"] = evidence
            copy["why"] = evidence[:3]
            confidence = copy.get("confidence")
            try:
                copy["confidence"] = min(1.0, max(0.0, float(confidence)))
            except (TypeError, ValueError):
                copy["confidence"] = None
            cleaned.append(copy)
            if len(cleaned) == 5:
                break
        # A valid but unhelpfully empty model response should not erase the
        # deterministic candidates already calculated from real channel data.
        for fallback in deterministic.get(field, []):
            if len(cleaned) == 5:
                break
            title = str(fallback.get("title") or "").strip()
            if title and title not in seen:
                cleaned.append(fallback)
                seen.add(title)
        result[field] = cleaned
    result["generated_by"] = "qwen3-vl-local"
    return result


class LocalStrategist:
    def __init__(
        self,
        database: Database,
        vision: Any,
        *,
        model_name: str = AI_MODEL_NAME,
        prompt_version: str = STRATEGIST_PROMPT_VERSION,
        timezone_name: str = "America/Campo_Grande",
    ):
        self.database = database
        self.vision = vision
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.timezone_name = timezone_name

    def context(self) -> tuple[dict, dict, dict]:
        videos = self.database.get_videos("recent")
        histories = {
            video["tiktok_video_id"]: self.database.get_metric_history(video["tiktok_video_id"])
            for video in videos
        }
        enriched = enrich_videos(
            videos,
            histories,
            timezone_name=self.timezone_name,
        )
        analyses = self.database.get_ai_analyses(status="completed")
        account = self.database.get_latest_account() or {}
        payload, metadata = build_insight_payload(enriched, analyses, account)
        deterministic = deterministic_insight_report(payload, metadata)
        return payload, metadata, deterministic

    def generate(self, *, force: bool = False) -> dict:
        payload, metadata, deterministic = self.context()
        fingerprint = metadata["fingerprint"]
        if not force:
            cached = self.database.latest_ai_report(
                fingerprint, self.model_name, self.prompt_version
            )
            if cached:
                try:
                    report = json.loads(cached["report_json"])
                    report["cached"] = True
                    report["generated_at"] = cached.get("generated_at")
                    return report
                except (TypeError, ValueError):
                    pass
        if not payload["account"]["videos_analyzed"]:
            report = deterministic
        else:
            prompt = build_strategist_prompt(payload)
            raw = self.vision.generate(prompt, [])
            try:
                report = _sanitize_llm_report(_validate_strategy(raw), deterministic)
            except StrategyValidationError:
                repair_prompt = (
                    prompt
                    + "\n\nA resposta anterior falhou na validação. Corrija o JSON e retorne somente o objeto."
                )
                try:
                    report = _sanitize_llm_report(
                        _validate_strategy(self.vision.generate(repair_prompt, [])),
                        deterministic,
                    )
                except StrategyValidationError:
                    report = deterministic
        report["input_fingerprint"] = fingerprint
        report["generated_at"] = utc_now_iso()
        report["cached"] = False
        self.database.save_ai_report(
            fingerprint,
            self.model_name,
            self.prompt_version,
            json.dumps(report, ensure_ascii=False, separators=(",", ":")),
        )
        return report


def generate_insights(
    database: Database,
    vision: Any,
    *,
    force: bool = False,
    model_name: str = AI_MODEL_NAME,
    timezone_name: str = "America/Campo_Grande",
) -> dict:
    return LocalStrategist(
        database,
        vision,
        model_name=model_name,
        timezone_name=timezone_name,
    ).generate(force=force)

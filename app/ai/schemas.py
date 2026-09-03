from __future__ import annotations

import json
from typing import Any

try:  # Pydantic is optional at Flask boot, required by setup_ai.sh.
    from pydantic import BaseModel, ConfigDict, Field

    PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in a light install
    PYDANTIC_AVAILABLE = False

    class BaseModel:  # type: ignore[no-redef]
        """Tiny compatibility shell so the web app remains importable.

        The real runtime always installs Pydantic. This fallback is only for
        `AI_ENABLED=false` installations and local unit tests that exercise
        JSON parsing without downloading the AI requirements.
        """

        def __init__(self, **data: Any):
            annotations: dict[str, Any] = {}
            for cls in reversed(type(self).mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            for name in annotations:
                value = data.get(name, getattr(type(self), name, None))
                if isinstance(value, list):
                    value = list(value)
                elif isinstance(value, dict):
                    value = dict(value)
                setattr(self, name, value)

        @classmethod
        def model_validate(cls, value: Any):
            if not isinstance(value, dict):
                raise ValueError("O resultado da IA precisa ser um objeto JSON.")
            return cls(**value)

        @classmethod
        def parse_obj(cls, value: Any):
            return cls.model_validate(value)

        def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
            annotations: dict[str, Any] = {}
            for cls in reversed(type(self).mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            return {name: getattr(self, name, None) for name in annotations}

        def dict(self, **kwargs: Any):
            return self.model_dump(**kwargs)

    class ConfigDict(dict):  # type: ignore[no-redef]
        pass

    def Field(default=None, **_kwargs: Any):  # type: ignore[no-redef]
        return default


class AIModel(BaseModel):
    if PYDANTIC_AVAILABLE:
        model_config = ConfigDict(extra="ignore")


def _list_field():
    return Field(default_factory=list) if PYDANTIC_AVAILABLE else []


def _dict_field():
    return Field(default_factory=dict) if PYDANTIC_AVAILABLE else {}


class VideoSemanticAnalysis(AIModel):
    primary_topic: str | None = None
    secondary_topics: list[str] = _list_field()

    content_type: str | None = None
    format: str | None = None

    hook_type: str | None = None
    hook_text: str | None = None
    hook_summary: str | None = None
    hook_strengths: list[str] = _list_field()

    person_names: list[str] = _list_field()
    bands: list[str] = _list_field()
    artists: list[str] = _list_field()
    products: list[str] = _list_field()
    subjects: list[str] = _list_field()

    visual_style: str | None = None
    editing_style: str | None = None
    caption_style: str | None = None
    narration_style: str | None = None
    tone: str | None = None

    cta_type: str | None = None
    cta_text: str | None = None
    structure: list[str] = _list_field()

    first_3_seconds: str | None = None
    first_5_seconds: str | None = None
    opening_visual: str | None = None
    opening_text: str | None = None

    summary: str | None = None
    keywords: list[str] = _list_field()
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    has_face: bool | None = None
    has_guitar: bool | None = None
    has_on_screen_captions: bool | None = None
    uses_ai_generated_visuals: bool | None = None
    estimated_scene_changes: int | None = Field(default=None, ge=0)


class StrategicIdea(AIModel):
    title: str
    topic: str | None = None
    content_type: str | None = None
    hook_type: str | None = None
    suggested_hook: str | None = None
    recommended_duration: str | None = None
    structure: list[str] = _list_field()
    why: list[str] = _list_field()
    evidence: list[str] = _list_field()
    confidence: float | None = Field(default=None, ge=0, le=1)


class StrategicReport(AIModel):
    summary: str | None = None
    what_is_working: list[dict[str, Any]] = _list_field()
    best_hooks: list[dict[str, Any]] = _list_field()
    best_formats: list[dict[str, Any]] = _list_field()
    strongest_topics: list[dict[str, Any]] = _list_field()
    strongest_people_bands: list[dict[str, Any]] = _list_field()
    promising_combinations: list[dict[str, Any]] = _list_field()
    recent_usage: dict[str, Any] = _dict_field()
    priority_ideas: list[StrategicIdea] = _list_field()
    experimental_ideas: list[StrategicIdea] = _list_field()
    limitations: list[str] = _list_field()


def model_validate(model_class: type[AIModel], value: Any) -> AIModel:
    """Use the installed Pydantic v2 API with a compatibility fallback."""

    validator = getattr(model_class, "model_validate", None)
    if validator:
        return validator(value)
    return model_class.parse_obj(value)


def model_dump(model: AIModel) -> dict[str, Any]:
    dumper = getattr(model, "model_dump", None)
    if dumper:
        return dumper(mode="json")
    return model.dict()


def model_json(model: AIModel) -> str:
    return json.dumps(model_dump(model), ensure_ascii=False, separators=(",", ":"))

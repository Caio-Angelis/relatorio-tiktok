from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent

# Loading both locations makes the app convenient to run while keeping the
# documented configuration file next to the Python application.
load_dotenv(APP_DIR / ".env")
load_dotenv(ROOT_DIR / ".env", override=False)

DEFAULT_SCOPES = "user.info.basic,user.info.stats,video.list"
DEFAULT_AI_TEMP_DIR = ROOT_DIR / "tmp" / "tiktok_ai"


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _path_from_env(value: object, default: Path) -> Path:
    candidate = Path(str(value or default)).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return candidate.resolve()


def settings_from_env(overrides: dict | None = None) -> dict:
    """Build application settings from environment variables.

    The returned dictionary is deliberately explicit so tests can override
    paths without changing the user's real local database.
    """

    mock_enabled = _as_bool(os.getenv("MOCK_TIKTOK", "false"))
    default_database_name = (
        "relatorio_tiktok_mock.db" if mock_enabled else "relatorio_tiktok.db"
    )
    values = {
        "TIKTOK_CLIENT_KEY": os.getenv("TIKTOK_CLIENT_KEY", "").strip(),
        "TIKTOK_CLIENT_SECRET": os.getenv("TIKTOK_CLIENT_SECRET", "").strip(),
        "TIKTOK_REDIRECT_URI": os.getenv(
            "TIKTOK_REDIRECT_URI", "http://localhost:3455/callback/"
        ).strip(),
        "TIKTOK_SCOPES": os.getenv("TIKTOK_SCOPES", DEFAULT_SCOPES).strip(),
        "APP_TIMEZONE": os.getenv("APP_TIMEZONE", "America/Campo_Grande").strip(),
        "REQUEST_TIMEOUT": float(os.getenv("REQUEST_TIMEOUT", "30")),
        "MOCK_TIKTOK": mock_enabled,
        "DATABASE_PATH": _path_from_env(
            os.getenv("TIKTOK_DATABASE_PATH"),
            ROOT_DIR / "database" / default_database_name,
        ),
        "EXPORTS_DIR": _path_from_env(
            os.getenv("TIKTOK_EXPORTS_DIR"), ROOT_DIR / "exports"
        ),
        "SECRET_KEY": os.getenv("FLASK_SECRET_KEY", "").strip(),
        # Local AI is opt-in. These values are separate from the light Flask
        # dependencies so the app can boot without the GPU stack installed.
        "AI_ENABLED": _as_bool(os.getenv("AI_ENABLED", "false")),
        "AI_DEVICE": os.getenv("AI_DEVICE", "cuda").strip() or "cuda",
        "AI_WHISPER_MODEL": os.getenv(
            "AI_WHISPER_MODEL", "large-v3-turbo"
        ).strip(),
        "AI_WHISPER_COMPUTE_TYPE": os.getenv(
            "AI_WHISPER_COMPUTE_TYPE", "float16"
        ).strip(),
        "AI_VISION_MODEL": os.getenv(
            "AI_VISION_MODEL", "Qwen/Qwen3-VL-8B-Instruct"
        ).strip(),
        "AI_VISION_DTYPE": os.getenv("AI_VISION_DTYPE", "bfloat16").strip(),
        "AI_TEMP_DIR": _path_from_env(
            os.getenv("AI_TEMP_DIR"), DEFAULT_AI_TEMP_DIR
        ),
        "AI_DELETE_TEMP_FILES": _as_bool(
            os.getenv("AI_DELETE_TEMP_FILES", "true")
        ),
        "AI_MAX_FRAMES": max(1, _as_int(os.getenv("AI_MAX_FRAMES", "12"), 12)),
        "AI_MAX_IMAGE_SIDE": max(
            64, _as_int(os.getenv("AI_MAX_IMAGE_SIDE", "896"), 896)
        ),
        "AI_DOWNLOAD_COOKIES_BROWSER": os.getenv(
            "AI_DOWNLOAD_COOKIES_BROWSER", ""
        ).strip().lower(),
        "AI_AUTO_ANALYZE_NEW_VIDEOS": _as_bool(
            os.getenv("AI_AUTO_ANALYZE_NEW_VIDEOS", "false")
        ),
        "ROOT_DIR": ROOT_DIR,
        "APP_DIR": APP_DIR,
    }
    if overrides:
        values.update(overrides)
    values["DATABASE_PATH"] = Path(values["DATABASE_PATH"]).expanduser().resolve()
    values["EXPORTS_DIR"] = Path(values["EXPORTS_DIR"]).expanduser().resolve()
    values["AI_TEMP_DIR"] = Path(values["AI_TEMP_DIR"]).expanduser().resolve()
    values["AI_MAX_FRAMES"] = max(1, int(values["AI_MAX_FRAMES"]))
    values["AI_MAX_IMAGE_SIDE"] = max(64, int(values["AI_MAX_IMAGE_SIDE"]))
    values["AI_ENABLED"] = _as_bool(values["AI_ENABLED"])
    values["AI_DELETE_TEMP_FILES"] = _as_bool(values["AI_DELETE_TEMP_FILES"])
    values["AI_AUTO_ANALYZE_NEW_VIDEOS"] = _as_bool(
        values["AI_AUTO_ANALYZE_NEW_VIDEOS"]
    )
    return values

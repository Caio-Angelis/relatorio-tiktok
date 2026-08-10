from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


METRIC_KEYS = ("view_count", "like_count", "comment_count", "share_count")


def _number(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rounded(value: float | int | None, digits: int = 2):
    return round(value, digits) if value is not None else None


def safe_rate(numerator, denominator):
    """Return a percentage, or None when the source data is insufficient."""

    numerator = _number(numerator)
    denominator = _number(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    return _rounded((numerator / denominator) * 100)


def calculate_rates(metrics: dict) -> dict:
    views = metrics.get("view_count", metrics.get("views"))
    likes = metrics.get("like_count", metrics.get("likes"))
    comments = metrics.get("comment_count", metrics.get("comments"))
    shares = metrics.get("share_count", metrics.get("shares"))
    return {
        "engagement_rate": _rounded(
            sum(
                value or 0
                for value in (_number(likes), _number(comments), _number(shares))
            )
            / _number(views)
            * 100
        )
        if _number(views) not in (None, 0)
        and any(value is not None for value in (_number(likes), _number(comments), _number(shares)))
        else None,
        "like_rate": safe_rate(likes, views),
        "comment_rate": safe_rate(comments, views),
        "share_rate": safe_rate(shares, views),
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_epoch(value) -> datetime | None:
    number = _number(value)
    if number is None:
        return None
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def growth_since(history: list[dict], hours: int) -> dict | None:
    """Compare the latest metric with the closest snapshot at least N hours old."""

    if not history:
        return None
    ordered = sorted(
        (item for item in history if _parse_iso(item.get("collected_at"))),
        key=lambda item: _parse_iso(item.get("collected_at")),
    )
    if len(ordered) < 2:
        return None
    latest = ordered[-1]
    latest_time = _parse_iso(latest.get("collected_at"))
    if latest_time is None:
        return None
    candidates = [
        item
        for item in ordered[:-1]
        if (latest_time - _parse_iso(item.get("collected_at"))).total_seconds()
        >= hours * 3600
    ]
    if not candidates:
        return None
    previous = candidates[-1]
    current_views = _number(latest.get("view_count", latest.get("views")))
    previous_views = _number(previous.get("view_count", previous.get("views")))
    if current_views is None or previous_views is None:
        return None
    percent = None if previous_views == 0 else _rounded((current_views - previous_views) / previous_views * 100)
    return {
        "views": current_views - previous_views,
        "percent": percent,
        "from": previous.get("collected_at"),
        "to": latest.get("collected_at"),
    }


def video_analytics(
    video: dict,
    history: list[dict] | None = None,
    now: datetime | None = None,
) -> dict:
    metrics = {
        "view_count": video.get("view_count"),
        "like_count": video.get("like_count"),
        "comment_count": video.get("comment_count"),
        "share_count": video.get("share_count"),
    }
    result = calculate_rates(metrics)
    published = _parse_epoch(video.get("create_time"))
    now = now or datetime.now(timezone.utc)
    if published and _number(video.get("view_count")) is not None:
        age_hours = (now - published).total_seconds() / 3600
        result["views_per_hour"] = _rounded(
            _number(video.get("view_count")) / age_hours, 2
        ) if age_hours > 0 else None
    else:
        result["views_per_hour"] = None
    history = history or []
    result["growth_24h"] = growth_since(history, 24)
    result["growth_48h"] = growth_since(history, 48)
    return result


def _safe_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


WEEKDAY_NAMES = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def _posting_correlations(videos: list[dict], timezone_name: str) -> dict:
    tz = _safe_timezone(timezone_name)
    by_day: dict[int, list[int]] = defaultdict(list)
    by_hour: dict[int, list[int]] = defaultdict(list)
    for video in videos:
        posted = _parse_epoch(video.get("create_time"))
        views = _number(video.get("view_count"))
        if posted is None or views is None:
            continue
        local = posted.astimezone(tz)
        by_day[local.weekday()].append(views)
        by_hour[local.hour].append(views)

    def ranked(values: dict[int, list[int]], labeler):
        rows = [
            {
                "key": key,
                "label": labeler(key),
                "samples": len(sample),
                "average_views": _rounded(statistics.mean(sample), 2),
            }
            for key, sample in values.items()
            if sample
        ]
        return sorted(rows, key=lambda row: (-row["average_views"], -row["samples"]))

    return {
        "best_days": ranked(by_day, lambda key: WEEKDAY_NAMES[key]),
        "best_hours": ranked(by_hour, lambda key: f"{key:02d}:00"),
        "interpretation": (
            "These are historical correlations by publication day/time, not proof "
            "that a day or time causes better performance."
        ),
    }


def _ranked_videos(videos: list[dict], metric: str, limit: int = 10) -> list[dict]:
    rows = []
    for video in videos:
        value = video.get("analytics", {}).get(metric)
        if value is None:
            continue
        rows.append(
            {
                "id": video.get("tiktok_video_id"),
                "description": video.get("description") or video.get("title") or "Sem descrição",
                "value": value,
                "views": _number(video.get("view_count")),
            }
        )
    return sorted(rows, key=lambda row: row["value"], reverse=True)[:limit]


def aggregate_analytics(videos: list[dict], timezone_name: str = "UTC") -> dict:
    view_values = [_number(video.get("view_count")) for video in videos]
    view_values = [value for value in view_values if value is not None]
    engagement_values = [
        video.get("analytics", {}).get("engagement_rate")
        for video in videos
    ]
    engagement_values = [value for value in engagement_values if value is not None]
    total_views = sum(view_values) if view_values else 0
    return {
        "videos_collected": len(videos),
        "total_views": total_views,
        "average_views": _rounded(statistics.mean(view_values), 2) if view_values else None,
        "median_views": _rounded(statistics.median(view_values), 2) if view_values else None,
        "average_engagement_rate": _rounded(statistics.mean(engagement_values), 2)
        if engagement_values
        else None,
        "top_10_by_views": sorted(
            [
                {
                    "id": video.get("tiktok_video_id"),
                    "description": video.get("description") or video.get("title") or "Sem descrição",
                    "value": _number(video.get("view_count")),
                }
                for video in videos
                if _number(video.get("view_count")) is not None
            ],
            key=lambda row: row["value"],
            reverse=True,
        )[:10],
        "top_10_by_engagement": _ranked_videos(videos, "engagement_rate", 10),
        "top_10_by_share_rate": _ranked_videos(videos, "share_rate", 10),
        **_posting_correlations(videos, timezone_name),
    }


def enrich_videos(
    videos: list[dict],
    histories: dict[str, list[dict]],
    now: datetime | None = None,
) -> list[dict]:
    enriched = []
    for video in videos:
        copy = dict(video)
        copy["analytics"] = video_analytics(
            copy, histories.get(copy["tiktok_video_id"], []), now=now
        )
        enriched.append(copy)
    return enriched


def sort_enriched_videos(videos: list[dict], sort: str) -> list[dict]:
    if sort == "engagement":
        key = lambda video: video.get("analytics", {}).get("engagement_rate")
    elif sort == "share_rate":
        key = lambda video: video.get("analytics", {}).get("share_rate")
    else:
        return videos
    return sorted(
        videos,
        key=lambda video: key(video) if key(video) is not None else -1,
        reverse=True,
    )

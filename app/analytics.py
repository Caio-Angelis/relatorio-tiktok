from __future__ import annotations

import math
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


METRIC_KEYS = ("view_count", "like_count", "comment_count", "share_count")
WINDOW_HOURS = (1, 3, 6, 12, 24, 48, 72)
WINDOW_TOLERANCES = {1: 0.75, 3: 1, 6: 2, 12: 3, 24: 6, 48: 8, 72: 12}
COMMENT_SHARE_HOURS = (24, 48, 72)
DELTA_PAIRS = ((1, 3), (3, 6), (6, 12), (12, 24), (24, 48), (48, 72))

ACCOUNT_AGE_WINDOWS = {
    "24h": (24, 6),
    "7d": (24 * 7, 24),
    "30d": (24 * 30, 48),
}
ACCOUNT_PUBLISH_TOLERANCES = {"near_publish": 12, "24h_after": 6, "48h_after": 8}

WEEKDAY_NAMES = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

DURATION_BUCKETS = ("0-20s", "21-30s", "31-45s", "46-60s", "61-90s", "90s+")
HOUR_WARNING = (
    "Historical correlation only; publication time is not necessarily the cause of performance."
)
FOLLOWER_CORRELATION_NOTE = (
    "Follower changes are account-level correlations and cannot be attributed causally to a specific video."
)

URL_RE = re.compile(r"(?:https?://|www\.)[^\s]+", re.IGNORECASE)
HASHTAG_RE = re.compile(r"(?<![\w/&])#([\w]+)", re.UNICODE)
MENTION_RE = re.compile(r"(?<![\w/&])@([\w]+)", re.UNICODE)
WORD_RE = re.compile(r"\b[\w]+\b", re.UNICODE)
EMOJI_RE = re.compile(
    r"[\U0001F1E6-\U0001FAFF\u2600-\u27BF]", re.UNICODE
)
REPLY_RE = re.compile(
    r"(?:^|\b)(?:respondendo\s+(?:a|ao|à)\s+|respondendo\s+coment[aá]rio\s+(?:de|ao)\s+|replying\s+to\s+|responding\s+to\s+)@([\w]+)",
    re.IGNORECASE | re.UNICODE,
)


def _number(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rounded(value: float | int | None, digits: int = 2):
    return round(value, digits) if value is not None else None


def _mean(values: Iterable) -> float | None:
    cleaned = [value for value in values if value is not None]
    return _rounded(statistics.mean(cleaned), 2) if cleaned else None


def _median(values: Iterable) -> float | None:
    cleaned = [value for value in values if value is not None]
    return _rounded(statistics.median(cleaned), 2) if cleaned else None


def _quantile(values: Iterable, fraction: float) -> float | None:
    """Linear-interpolation quantile (sorted index = (n - 1) * p)."""

    cleaned = sorted(value for value in values if value is not None)
    if not cleaned:
        return None
    position = (len(cleaned) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return _rounded(cleaned[lower])
    weight = position - lower
    return _rounded(cleaned[lower] + (cleaned[upper] - cleaned[lower]) * weight)


def safe_rate(numerator, denominator):
    """Return a percentage, or None when the denominator is unavailable/zero."""

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
    views_number = _number(views)
    interactions = [_number(likes), _number(comments), _number(shares)]
    engagement = None
    if views_number not in (None, 0) and any(value is not None for value in interactions):
        engagement = _rounded(sum(value or 0 for value in interactions) / views_number * 100)
    return {
        "engagement_rate": engagement,
        "like_rate": safe_rate(likes, views),
        "comment_rate": safe_rate(comments, views),
        "share_rate": safe_rate(shares, views),
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
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


def _safe_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _iso_local(value: datetime | None, timezone_name: str) -> str | None:
    if value is None:
        return None
    return value.astimezone(_safe_timezone(timezone_name)).replace(microsecond=0).isoformat()


def extract_caption_features(description: str | None) -> dict:
    """Derive deterministic caption signals without semantic classification."""

    text = description or ""
    hashtags: list[str] = []
    for match in HASHTAG_RE.finditer(text):
        tag = match.group(1).casefold()
        if tag not in hashtags:
            hashtags.append(tag)
    mentions = MENTION_RE.findall(text)
    return {
        "hashtags": hashtags,
        "caption_length_chars": len(text),
        "caption_length_words": len(WORD_RE.findall(text)),
        "has_question_mark": "?" in text or "？" in text,
        "has_exclamation_mark": "!" in text or "！" in text,
        "has_numbers": any(character.isdigit() for character in text),
        "has_emojis": bool(EMOJI_RE.search(text)),
        "has_url": bool(URL_RE.search(text)),
        "has_mention": bool(mentions),
        "hashtags_count": len(hashtags),
        "mentions_count": len(mentions),
        "reply_to_comment": bool(REPLY_RE.search(text)),
    }


def duration_bucket(duration) -> str | None:
    seconds = _number(duration)
    if seconds is None or seconds < 0:
        return None
    if seconds <= 20:
        return "0-20s"
    if seconds <= 30:
        return "21-30s"
    if seconds <= 45:
        return "31-45s"
    if seconds <= 60:
        return "46-60s"
    if seconds <= 90:
        return "61-90s"
    return "90s+"


def growth_since(history: list[dict], hours: int) -> dict | None:
    """Backward-compatible latest-vs-old snapshot growth helper."""

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


def _ordered_history(history: list[dict]) -> list[dict]:
    return sorted(
        (item for item in history if _parse_iso(item.get("collected_at"))),
        key=lambda item: _parse_iso(item.get("collected_at")),
    )


def recent_metric_per_hour(history: list[dict], metric: str) -> float | None:
    """Calculate the latest observed metric velocity from two real snapshots."""

    ordered = _ordered_history(history)
    if len(ordered) < 2:
        return None
    previous, latest = ordered[-2], ordered[-1]
    previous_time = _parse_iso(previous.get("collected_at"))
    latest_time = _parse_iso(latest.get("collected_at"))
    if previous_time is None or latest_time is None:
        return None
    delta_hours = (latest_time - previous_time).total_seconds() / 3600
    if delta_hours <= 0:
        return None
    metric_key = {
        "views": "view_count",
        "likes": "like_count",
    }.get(metric)
    if metric_key is None:
        return None
    current = _number(latest.get(metric_key, latest.get(metric)))
    previous_value = _number(previous.get(metric_key, previous.get(metric)))
    if current is None or previous_value is None:
        return None
    return _rounded((current - previous_value) / delta_hours)


def _snapshot_at_age(
    history: list[dict],
    published_at: datetime | None,
    target_hours: float,
    tolerance_hours: float,
) -> dict | None:
    if published_at is None:
        return None
    candidates = []
    for snapshot in history:
        collected_at = _parse_iso(snapshot.get("collected_at"))
        if collected_at is None:
            continue
        age_hours = (collected_at - published_at).total_seconds() / 3600
        if age_hours < 0:
            continue
        distance = abs(age_hours - target_hours)
        if distance <= tolerance_hours:
            candidates.append((distance, collected_at, age_hours, snapshot))
    if not candidates:
        return None
    _, collected_at, age_hours, snapshot = min(candidates, key=lambda item: (item[0], item[1]))
    return {"snapshot": snapshot, "collected_at": collected_at, "age_hours": age_hours}


def _metric_value(snapshot: dict | None, metric: str):
    if snapshot is None:
        return None
    key = {"views": "view_count", "likes": "like_count", "comments": "comment_count", "shares": "share_count"}[metric]
    return _number(snapshot["snapshot"].get(key))


def _window_growth(video: dict, history: list[dict]) -> tuple[dict, dict, dict]:
    published_at = _parse_epoch(video.get("create_time"))
    snapshots = {
        hours: _snapshot_at_age(history, published_at, hours, WINDOW_TOLERANCES[hours])
        for hours in WINDOW_HOURS
    }
    views = {f"{hours}h": _metric_value(snapshots[hours], "views") for hours in WINDOW_HOURS}
    likes = {f"{hours}h": _metric_value(snapshots[hours], "likes") for hours in WINDOW_HOURS}
    comments = {f"{hours}h": _metric_value(snapshots[hours], "comments") for hours in COMMENT_SHARE_HOURS}
    shares = {f"{hours}h": _metric_value(snapshots[hours], "shares") for hours in COMMENT_SHARE_HOURS}
    growth = {"views": views, "likes": likes, "comments": comments, "shares": shares}

    deltas: dict[str, int | None] = {}
    for metric, values in (("views", views), ("likes", likes)):
        for start, end in DELTA_PAIRS:
            start_value = values[f"{start}h"]
            end_value = values[f"{end}h"]
            deltas[f"{metric}_growth_{start}_to_{end}h"] = (
                end_value - start_value
                if start_value is not None and end_value is not None
                else None
            )

    velocity: dict[str, float | None] = {}
    first_value = views["1h"]
    velocity["views_per_hour_0_1h"] = _rounded(first_value / 1) if first_value is not None else None
    for start, end in DELTA_PAIRS:
        start_value = views[f"{start}h"]
        end_value = views[f"{end}h"]
        velocity[f"views_per_hour_{start}_{end}h"] = (
            _rounded((end_value - start_value) / (end - start))
            if start_value is not None and end_value is not None
            else None
        )
    return growth, deltas, velocity


def _publication_fields(create_time, timezone_name: str, now: datetime) -> dict:
    published_at = _parse_epoch(create_time)
    local = published_at.astimezone(_safe_timezone(timezone_name)) if published_at else None
    age_hours = None
    if published_at:
        raw_age = (now - published_at).total_seconds() / 3600
        age_hours = _rounded(raw_age, 2) if raw_age >= 0 else None
    return {
        "published_at": _iso_utc(published_at),
        "published_at_utc": _iso_utc(published_at),
        "published_at_local": _iso_local(published_at, timezone_name),
        "publication_weekday": WEEKDAY_NAMES[local.weekday()] if local else None,
        "publication_hour": local.hour if local else None,
        "publication_minute": local.minute if local else None,
        "age_hours": age_hours,
        "age_days": _rounded(age_hours / 24, 2) if age_hours is not None else None,
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
    now = now or datetime.now(timezone.utc)
    published = _parse_epoch(video.get("create_time"))
    views = _number(video.get("view_count"))
    lifetime_average_views_per_hour = None
    if published and views is not None:
        age_hours = (now - published).total_seconds() / 3600
        if age_hours > 0:
            lifetime_average_views_per_hour = _rounded(views / age_hours)
    history = history or []
    result["lifetime_average_views_per_hour"] = lifetime_average_views_per_hour
    result["recent_views_per_hour"] = recent_metric_per_hour(history, "views")
    result["recent_likes_per_hour"] = recent_metric_per_hour(history, "likes")
    # Kept as an internal compatibility alias for the existing dashboard.
    result["views_per_hour"] = lifetime_average_views_per_hour
    result["growth_24h"] = growth_since(history, 24)
    result["growth_48h"] = growth_since(history, 48)
    return result


def enrich_videos(
    videos: list[dict],
    histories: dict[str, list[dict]],
    now: datetime | None = None,
    timezone_name: str = "America/Campo_Grande",
) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    enriched = []
    for video in videos:
        copy = dict(video)
        history = histories.get(copy["tiktok_video_id"], [])
        analytics = video_analytics(copy, history, now=now)
        growth, deltas, velocity = _window_growth(copy, history)
        analytics["growth"] = growth
        analytics["growth_deltas"] = deltas
        analytics["velocity"] = velocity
        copy["analytics"] = analytics
        copy["caption_features"] = extract_caption_features(copy.get("description"))
        copy.update(_publication_fields(copy.get("create_time"), timezone_name, now))
        copy["duration_bucket"] = duration_bucket(copy.get("duration"))
        enriched.append(copy)
    return apply_relative_metrics(enriched)


def _ratio(value, denominator):
    if value is None or denominator in (None, 0):
        return None
    return _rounded(value / denominator, 3)


def _percentile(value, values: list[float | int]) -> float | None:
    """Midrank percentile scaled to 0..100; ties receive their average rank."""

    if value is None or not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return 100.0
    less = sum(item < value for item in ordered)
    equal = sum(item == value for item in ordered)
    average_rank = less + (equal + 1) / 2
    return _rounded((average_rank - 1) / (len(ordered) - 1) * 100)


def apply_relative_metrics(videos: list[dict]) -> list[dict]:
    copies = []
    view_values = [_number(video.get("view_count")) for video in videos]
    engagement_values = [video.get("analytics", {}).get("engagement_rate") for video in videos]
    share_values = [video.get("analytics", {}).get("share_rate") for video in videos]
    view_values = [value for value in view_values if value is not None]
    engagement_values = [value for value in engagement_values if value is not None]
    share_values = [value for value in share_values if value is not None]
    view_median = _median(view_values)
    engagement_median = _median(engagement_values)
    share_median = _median(share_values)
    for video in videos:
        copy = dict(video)
        analytics = dict(copy.get("analytics", {}))
        views = _number(copy.get("view_count"))
        engagement = analytics.get("engagement_rate")
        share_rate = analytics.get("share_rate")
        analytics.update(
            {
                "views_vs_account_median": _ratio(views, view_median),
                "engagement_vs_account_median": _ratio(engagement, engagement_median),
                "share_rate_vs_account_median": _ratio(share_rate, share_median),
                "views_percentile": _percentile(views, view_values),
                "engagement_percentile": _percentile(engagement, engagement_values),
                "share_rate_percentile": _percentile(share_rate, share_values),
            }
        )
        copy["analytics"] = analytics
        copies.append(copy)
    return copies


def distribution_analytics(videos: list[dict]) -> dict:
    """Return compact distribution statistics using the same quantile method."""

    views = [_number(video.get("view_count")) for video in videos]
    engagements = [
        video.get("analytics", {}).get("engagement_rate") for video in videos
    ]

    def distribution(values: Iterable) -> dict:
        cleaned = [value for value in values if value is not None]
        if not cleaned:
            return {}
        return {
            "p25": _quantile(cleaned, 0.25),
            "p50": _quantile(cleaned, 0.50),
            "p75": _quantile(cleaned, 0.75),
            "p90": _quantile(cleaned, 0.90),
            "p95": _quantile(cleaned, 0.95),
            "max": _rounded(max(cleaned)),
        }

    return {
        "views": distribution(views),
        "engagement_rate": distribution(engagements),
    }


def _robust_outliers(
    videos: list[dict], value_getter: Callable[[dict], float | int | None], value_name: str
) -> list[dict]:
    values = [(video, value_getter(video)) for video in videos]
    values = [(video, value) for video, value in values if value is not None]
    if len(values) < 3:
        return []
    numeric_values = [value for _video, value in values]
    median = statistics.median(numeric_values)
    deviations = [abs(value - median) for value in numeric_values]
    mad = statistics.median(deviations)
    if mad == 0:
        candidates = [(video, value) for video, value in values if value != median]
    else:
        candidates = [
            (video, value)
            for video, value in values
            if abs(0.6745 * (value - median) / mad) >= 3.5
        ]
    rounded_median = _rounded(median)
    return [
        {
            "id": video.get("tiktok_video_id"),
            value_name: value,
            f"{value_name}_vs_median": _ratio(value, rounded_median),
        }
        for video, value in sorted(candidates, key=lambda item: item[1], reverse=True)
    ]


def outlier_analytics(videos: list[dict]) -> dict:
    return {
        "views": _robust_outliers(
            videos,
            lambda video: _number(video.get("view_count")),
            "views",
        )
    }


def _period_statistics(videos: list[dict]) -> dict:
    views = [_number(video.get("view_count")) for video in videos]
    likes = [_number(video.get("like_count")) for video in videos]
    views = [value for value in views if value is not None]
    likes = [value for value in likes if value is not None]
    engagements = [video.get("analytics", {}).get("engagement_rate") for video in videos]
    share_rates = [video.get("analytics", {}).get("share_rate") for video in videos]
    return {
        "videos": len(videos),
        "total_views": sum(views) if views else 0,
        "average_views": _mean(views),
        "median_views": _median(views),
        "average_likes": _mean(likes),
        "median_likes": _median(likes),
        "average_engagement_rate": _mean(engagements),
        "median_engagement_rate": _median(engagements),
        "average_share_rate": _mean(share_rates),
        "median_share_rate": _median(share_rates),
    }


def _recent_videos(videos: list[dict], now: datetime, days: int) -> list[dict]:
    cutoff = now - timedelta(days=days)
    return [
        video
        for video in videos
        if (published := _parse_epoch(video.get("create_time"))) is not None
        and cutoff <= published <= now
    ]


def _periods(videos: list[dict], now: datetime) -> dict:
    return {
        "overall": _period_statistics(videos),
        "last_30_days": _period_statistics(_recent_videos(videos, now, 30)),
        "last_7_days": _period_statistics(_recent_videos(videos, now, 7)),
    }


def _recent_vs_overall(periods: dict) -> dict:
    overall = periods["overall"]
    result = {}
    for period_name, prefix in (("last_7_days", "recent_7d"), ("last_30_days", "recent_30d")):
        period = periods[period_name]
        enough = period["videos"] >= 2 and overall["videos"] >= 2
        result[f"{prefix}_median_views_vs_overall"] = _ratio(
            period["median_views"], overall["median_views"]
        ) if enough else None
        result[f"{prefix}_median_engagement_rate_vs_overall"] = _ratio(
            period["median_engagement_rate"], overall["median_engagement_rate"]
        ) if enough else None
        result[f"{prefix}_median_share_rate_vs_overall"] = _ratio(
            period["median_share_rate"], overall["median_share_rate"]
        ) if enough else None
    return result


def _grouped_performance(videos: list[dict], key_function: Callable[[dict], object], key_name: str) -> list[dict]:
    groups: dict[object, list[dict]] = defaultdict(list)
    for video in videos:
        key = key_function(video)
        if key is not None:
            groups[key].append(video)
    rows = []
    for key, group in groups.items():
        stats = _period_statistics(group)
        rows.append(
            {
                key_name: key,
                "samples": stats["videos"],
                "average_views": stats["average_views"],
                "median_views": stats["median_views"],
                "average_engagement_rate": stats["average_engagement_rate"],
                "median_engagement_rate": stats["median_engagement_rate"],
                "average_share_rate": stats["average_share_rate"],
                "median_share_rate": stats["median_share_rate"],
            }
        )
    return rows


def _duration_performance(videos: list[dict]) -> list[dict]:
    groups = _grouped_performance(videos, lambda video: video.get("duration_bucket"), "duration_bucket")
    order = {bucket: index for index, bucket in enumerate(DURATION_BUCKETS)}
    return sorted(groups, key=lambda row: order.get(row["duration_bucket"], 999))


def _weekday_performance(videos: list[dict]) -> list[dict]:
    rows = _grouped_performance(videos, lambda video: video.get("publication_weekday"), "weekday")
    order = {day: index for index, day in enumerate(WEEKDAY_NAMES)}
    return sorted(rows, key=lambda row: order.get(row["weekday"], 999))


def _hour_performance(videos: list[dict]) -> list[dict]:
    rows = _grouped_performance(videos, lambda video: video.get("publication_hour"), "hour")
    return sorted(rows, key=lambda row: row["hour"])


def _short_description(description: str | None, max_length: int = 120) -> str | None:
    if description is None:
        return None
    text = str(description)
    return text if len(text) <= max_length else f"{text[: max_length - 3]}..."


def _top_videos(videos: list[dict], metric: str, limit: int = 10) -> list[dict]:
    rows = []
    for video in videos:
        value = _number(video.get("view_count")) if metric == "views" else video.get("analytics", {}).get(metric)
        if value is None:
            continue
        rows.append(
            {
                "id": video.get("tiktok_video_id"),
                "short_description": _short_description(video.get("description")),
                "published_at_local": video.get("published_at_local"),
                metric: value,
            }
        )
    return sorted(
        rows,
        key=lambda row: row.get(metric) if row.get(metric) is not None else -1,
        reverse=True,
    )[:limit]


def aggregate_analytics(
    videos: list[dict],
    timezone_name: str = "America/Campo_Grande",
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    videos = apply_relative_metrics(videos)
    periods = _periods(videos, now)
    rankings = {
        "top_videos_by_views": _top_videos(videos, "views"),
        "top_videos_by_engagement": _top_videos(videos, "engagement_rate"),
        "top_videos_by_share_rate": _top_videos(videos, "share_rate"),
    }
    recent_30 = _recent_videos(videos, now, 30)
    recent_7 = _recent_videos(videos, now, 7)
    return {
        "periods": periods,
        "recent_vs_overall": _recent_vs_overall(periods),
        "duration_performance": _duration_performance(videos),
        "weekday_performance": _weekday_performance(videos),
        "hour_performance": {"warning": HOUR_WARNING, "rows": _hour_performance(videos)},
        "distribution": distribution_analytics(videos),
        "outliers": outlier_analytics(videos),
        **rankings,
        "top_recent_30d_by_views": _top_videos(recent_30, "views"),
        "top_recent_30d_by_engagement": _top_videos(recent_30, "engagement_rate"),
        "top_recent_7d_by_views": _top_videos(recent_7, "views"),
        "top_recent_7d_by_engagement": _top_videos(recent_7, "engagement_rate"),
        # Compatibility aliases for the first dashboard implementation. The
        # compact exporter only emits the explicit top_videos_* names.
        "top_10_by_views": rankings["top_videos_by_views"],
        "top_10_by_engagement": rankings["top_videos_by_engagement"],
        "top_10_by_share_rate": rankings["top_videos_by_share_rate"],
        "videos_collected": periods["overall"]["videos"],
        "total_videos": periods["overall"]["videos"],
        # Convenient aliases keep the current dashboard and older callers
        # working while the JSON export uses the explicit periods object.
        **periods["overall"],
    }


def _nearest_account_snapshot(
    snapshots: list[dict], target: datetime, tolerance_hours: float
) -> dict | None:
    candidates = []
    for snapshot in snapshots:
        collected_at = _parse_iso(snapshot.get("collected_at"))
        if collected_at is None:
            continue
        distance = abs((collected_at - target).total_seconds()) / 3600
        if distance <= tolerance_hours:
            candidates.append((distance, collected_at, snapshot))
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1]))[2]


def account_analytics(
    snapshots: list[dict], now: datetime | None = None
) -> dict:
    now = now or datetime.now(timezone.utc)
    ordered = sorted(
        (snapshot for snapshot in snapshots if _parse_iso(snapshot.get("collected_at"))),
        key=lambda snapshot: _parse_iso(snapshot.get("collected_at")),
    )
    latest = ordered[-1] if ordered else {}
    result = {
        "current_followers": _number(latest.get("follower_count")),
        "current_following": _number(latest.get("following_count")),
        "current_total_likes": _number(latest.get("likes_count")),
        "current_video_count": _number(latest.get("video_count")),
    }
    for label, (hours, tolerance) in ACCOUNT_AGE_WINDOWS.items():
        old = _nearest_account_snapshot(snapshots, now - timedelta(hours=hours), tolerance)
        followers = _number(old.get("follower_count")) if old else None
        likes = _number(old.get("likes_count")) if old else None
        result[f"followers_{label}_ago"] = followers
        result[f"likes_{label}_ago"] = likes
        current_followers = result["current_followers"]
        current_likes = result["current_total_likes"]
        result[f"followers_growth_{label}"] = (
            current_followers - followers
            if current_followers is not None and followers is not None
            else None
        )
        result[f"likes_growth_{label}"] = (
            current_likes - likes if current_likes is not None and likes is not None else None
        )
    return result


def add_account_follower_correlations(videos: list[dict], snapshots: list[dict]) -> list[dict]:
    copies = []
    for video in videos:
        copy = dict(video)
        published = _parse_epoch(video.get("create_time"))
        near = (
            _nearest_account_snapshot(
                snapshots,
                published,
                ACCOUNT_PUBLISH_TOLERANCES["near_publish"],
            )
            if published
            else None
        )
        after_24 = (
            _nearest_account_snapshot(
                snapshots,
                published + timedelta(hours=24),
                ACCOUNT_PUBLISH_TOLERANCES["24h_after"],
            )
            if published
            else None
        )
        after_48 = (
            _nearest_account_snapshot(
                snapshots,
                published + timedelta(hours=48),
                ACCOUNT_PUBLISH_TOLERANCES["48h_after"],
            )
            if published
            else None
        )
        near_followers = _number(near.get("follower_count")) if near else None
        followers_24 = _number(after_24.get("follower_count")) if after_24 else None
        followers_48 = _number(after_48.get("follower_count")) if after_48 else None
        copy.update(
            {
                "account_followers_near_publish": near_followers,
                "account_followers_24h_after_publish": followers_24,
                "account_followers_48h_after_publish": followers_48,
                "followers_delta_24h_after_publish": (
                    followers_24 - near_followers
                    if followers_24 is not None and near_followers is not None
                    else None
                ),
                "followers_delta_48h_after_publish": (
                    followers_48 - near_followers
                    if followers_48 is not None and near_followers is not None
                    else None
                ),
            }
        )
        copies.append(copy)
    return copies


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


# ---------------------------------------------------------------------------
# Semantic analytics. These functions only combine completed local AI
# classifications with the metrics already collected by the application.

SEMANTIC_DIMENSIONS = (
    "primary_topic",
    "content_type",
    "format",
    "hook_type",
    "person_names",
    "bands",
    "duration_content_type",
    "topic_hook",
    "format_hook",
)


def _analysis_map(analyses) -> dict[str, dict]:
    if isinstance(analyses, dict):
        source = analyses.items()
    else:
        source = (
            (item.get("tiktok_video_id"), item)
            for item in (analyses or [])
            if item.get("tiktok_video_id")
        )
    result = {}
    for video_id, value in source:
        if not video_id:
            continue
        if isinstance(value, dict):
            payload = value.get("analysis_json", value)
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (TypeError, ValueError):
                    payload = {}
            payload = dict(payload or {}) if isinstance(payload, dict) else {}
            # A row may have the indexed fields even when the full JSON is
            # unavailable; use them only as a conservative fallback.
            for field in ("primary_topic", "content_type", "format", "hook_type", "hook_text", "summary", "confidence"):
                if payload.get(field) is None and value.get(field) is not None:
                    payload[field] = value[field]
            if value.get("status") not in (None, "completed"):
                continue
            result[str(video_id)] = payload
    return result


def _semantic_video_metrics(video: dict) -> dict:
    analytics = video.get("analytics") or calculate_rates(video)
    return {
        "views": _number(video.get("view_count")),
        "engagement_rate": analytics.get("engagement_rate"),
        "like_rate": analytics.get("like_rate"),
        "comment_rate": analytics.get("comment_rate"),
        "share_rate": analytics.get("share_rate"),
        "views_percentile": analytics.get("views_percentile"),
    }


def _evidence_level(sample_size: int) -> str:
    if sample_size <= 1:
        return "caso isolado"
    if sample_size == 2:
        return "sinal preliminar"
    if sample_size <= 4:
        return "padrão possível"
    return "evidência interna mais útil"


def _semantic_group_values(video: dict, analysis: dict, dimension: str) -> list[str]:
    def clean(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    if dimension in {"person_names", "bands"}:
        values = analysis.get(dimension) or []
        values = values if isinstance(values, list) else [values]
        return [value for value in (clean(item) for item in values) if value]
    if dimension == "duration_content_type":
        duration = video.get("duration_bucket") or duration_bucket(video.get("duration"))
        content_type = clean(analysis.get("content_type"))
        return [f"{duration} + {content_type}"] if duration and content_type else []
    if dimension == "topic_hook":
        topic, hook = clean(analysis.get("primary_topic")), clean(analysis.get("hook_type"))
        return [f"{topic} + {hook}"] if topic and hook else []
    if dimension == "format_hook":
        video_format, hook = clean(analysis.get("format")), clean(analysis.get("hook_type"))
        return [f"{video_format} + {hook}"] if video_format and hook else []
    value = clean(analysis.get(dimension))
    return [value] if value else []


def _semantic_group_stats(key: str, group: list[dict]) -> dict:
    metric_rows = [(_semantic_video_metrics(video), video) for video in group]
    views = [metrics["views"] for metrics, _video in metric_rows]
    engagements = [metrics["engagement_rate"] for metrics, _video in metric_rows]
    likes = [metrics["like_rate"] for metrics, _video in metric_rows]
    comments = [metrics["comment_rate"] for metrics, _video in metric_rows]
    shares = [metrics["share_rate"] for metrics, _video in metric_rows]
    percentiles = [metrics["views_percentile"] for metrics, _video in metric_rows]
    durations = [_number(video.get("duration")) for video in group]
    recent_velocities = [
        (video.get("analytics") or {}).get("recent_views_per_hour") for video in group
    ]
    views_24h = [
        ((video.get("analytics") or {}).get("growth") or {}).get("views", {}).get("24h")
        for video in group
    ]
    views_48h = [
        ((video.get("analytics") or {}).get("growth") or {}).get("views", {}).get("48h")
        for video in group
    ]
    views_72h = [
        ((video.get("analytics") or {}).get("growth") or {}).get("views", {}).get("72h")
        for video in group
    ]
    ordered = sorted(
        (
            video
            for video in group
            if _number(video.get("view_count")) is not None
        ),
        key=lambda video: (_number(video.get("view_count")), str(video.get("tiktok_video_id"))),
    )
    best = ordered[-1] if ordered else None
    worst = ordered[0] if ordered else None
    return {
        "key": key,
        "label": key,
        "sample_size": len(group),
        "videos": len(group),
        "evidence_level": _evidence_level(len(group)),
        "average_views": _mean(views),
        "median_views": _median(views),
        "average_engagement": _mean(engagements),
        "median_engagement": _median(engagements),
        "average_like_rate": _mean(likes),
        "median_like_rate": _median(likes),
        "average_comment_rate": _mean(comments),
        "median_comment_rate": _median(comments),
        "average_share_rate": _mean(shares),
        "median_share_rate": _median(shares),
        "average_views_percentile": _mean(percentiles),
        "median_duration_seconds": _median(durations),
        "median_recent_views_per_hour": _median(recent_velocities),
        "median_views_24h": _median(views_24h),
        "median_views_48h": _median(views_48h),
        "median_views_72h": _median(views_72h),
        "best_video": (
            {
                "id": best.get("tiktok_video_id"),
                "description": _short_description(best.get("description")),
                "views": best.get("view_count"),
            }
            if best
            else None
        ),
        "worst_video": (
            {
                "id": worst.get("tiktok_video_id"),
                "description": _short_description(worst.get("description")),
                "views": worst.get("view_count"),
            }
            if worst
            else None
        ),
    }


def semantic_group_performance(
    videos: list[dict], analyses, dimension: str
) -> list[dict]:
    """Aggregate current/history-enriched videos by one AI field.

    The caller supplies videos enriched by the existing analytics layer when
    relative percentiles are desired. A group still remains useful when only
    raw current metrics are available.
    """

    if dimension not in SEMANTIC_DIMENSIONS:
        raise ValueError(f"Dimensão semântica desconhecida: {dimension}")
    analysis_by_id = _analysis_map(analyses)
    groups: dict[str, list[dict]] = defaultdict(list)
    for video in videos:
        video_id = str(video.get("tiktok_video_id") or "")
        analysis = analysis_by_id.get(video_id)
        if not analysis:
            continue
        for key in _semantic_group_values(video, analysis, dimension):
            groups[key].append(video)
    rows = [_semantic_group_stats(key, group) for key, group in groups.items()]
    return sorted(
        rows,
        key=lambda row: (
            row.get("median_views") if row.get("median_views") is not None else -1,
            row["sample_size"],
            row["label"],
        ),
        reverse=True,
    )


def _recent_semantic_usage(videos: list[dict], analyses, limits=(5, 10, 20)) -> dict:
    analysis_by_id = _analysis_map(analyses)
    ordered = sorted(
        videos,
        key=lambda video: (
            _number(video.get("create_time")) or 0,
            str(video.get("tiktok_video_id")),
        ),
        reverse=True,
    )
    result = {}
    for limit in limits:
        subset = ordered[:limit]
        topics: dict[str, int] = defaultdict(int)
        people: dict[str, int] = defaultdict(int)
        for video in subset:
            analysis = analysis_by_id.get(str(video.get("tiktok_video_id")), {})
            topic = analysis.get("primary_topic")
            if topic:
                topics[str(topic)] += 1
            for person in analysis.get("person_names") or []:
                people[str(person)] += 1
        result[str(limit)] = {
            "videos_considered": len(subset),
            "topics": dict(sorted(topics.items(), key=lambda item: (-item[1], item[0]))),
            "people": dict(sorted(people.items(), key=lambda item: (-item[1], item[0]))),
        }
    return result


def _semantic_pattern_score(row: dict, baselines: dict, recent_samples: int = 0) -> dict:
    """Rank patterns; this is a prioritization aid, not causal modeling.

    Formula: 55% median-view ratio + 20% share-rate ratio + 15% engagement
    ratio + 10% sample factor (sample/5 capped at 1), multiplied by a small
    recency factor of 1..1.15. Missing rates contribute no ratio and their
    available weights are proportionally renormalized.
    """

    components = [
        (0.55, row.get("median_views"), baselines.get("median_views")),
        (0.20, row.get("median_share_rate"), baselines.get("median_share_rate")),
        (0.15, row.get("median_engagement"), baselines.get("median_engagement")),
    ]
    weighted = 0.0
    weight_total = 0.0
    ratios = {}
    for weight, value, baseline in components:
        ratio = _ratio(value, baseline)
        if ratio is not None:
            ratio = min(3.0, max(0.0, ratio))
            weighted += weight * ratio
            weight_total += weight
        ratios["views" if weight == 0.55 else "share_rate" if weight == 0.20 else "engagement"] = ratio
    if weight_total:
        weighted /= weight_total
    sample_factor = min(1.0, row.get("sample_size", 0) / 5)
    score = weighted * 0.90 + sample_factor * 0.10
    recency_factor = 1 + min(0.15, 0.15 * recent_samples / max(row.get("sample_size", 1), 1))
    score *= recency_factor
    return {
        "score": _rounded(score, 3),
        "sample_factor": _rounded(sample_factor, 3),
        "recent_samples": recent_samples,
        "ratios": ratios,
    }


def semantic_analytics(videos: list[dict], analyses) -> dict:
    """Return all requested semantic groupings and deterministic candidates."""

    group_names = {
        "topics": "primary_topic",
        "content_types": "content_type",
        "formats": "format",
        "hooks": "hook_type",
        "people": "person_names",
        "bands": "bands",
        "duration_content_type": "duration_content_type",
        "topic_hook": "topic_hook",
        "format_hook": "format_hook",
    }
    groups = {
        name: semantic_group_performance(videos, analyses, dimension)
        for name, dimension in group_names.items()
    }
    all_metrics = [_semantic_video_metrics(video) for video in videos if video.get("tiktok_video_id")]
    baselines = {
        "median_views": _median(item["views"] for item in all_metrics),
        "median_share_rate": _median(item["share_rate"] for item in all_metrics),
        "median_engagement": _median(item["engagement_rate"] for item in all_metrics),
    }
    recent_ids = {
        str(video.get("tiktok_video_id"))
        for video in sorted(
            videos,
            key=lambda item: _number(item.get("create_time")) or 0,
            reverse=True,
        )[:10]
    }
    ranked = []
    for group_name in ("topics", "content_types", "formats", "hooks", "people", "bands", "topic_hook", "format_hook"):
        for row in groups[group_name]:
            group_videos = []
            analysis_by_id = _analysis_map(analyses)
            for video in videos:
                if row["label"] in _semantic_group_values(
                    video, analysis_by_id.get(str(video.get("tiktok_video_id")), {}), group_names[group_name]
                ):
                    group_videos.append(video)
            recent_samples = sum(
                str(video.get("tiktok_video_id")) in recent_ids for video in group_videos
            )
            scored = dict(row)
            scored["dimension"] = group_name
            scored.update(_semantic_pattern_score(row, baselines, recent_samples))
            ranked.append(scored)
    ranked.sort(key=lambda row: (row.get("score", -1), row.get("sample_size", 0), row.get("label", "")), reverse=True)
    return {
        "groups": groups,
        "baselines": baselines,
        "recent_usage": _recent_semantic_usage(videos, analyses),
        "pattern_ranking": ranked,
        "score_formula": (
            "0.55 mediana de views relativa + 0.20 share rate relativo + "
            "0.15 engagement relativo + 0.10 fator de amostra; multiplicado "
            "por fator de recência de até 1.15. Pesos ausentes são renormalizados."
        ),
    }


# Descriptive aliases keep the semantic layer easy to discover for callers
# that prefer the older `aggregate_*` naming used elsewhere in this module.
aggregate_semantic_analytics = semantic_analytics
group_semantic_performance = semantic_group_performance

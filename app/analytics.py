from __future__ import annotations

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
    views_per_hour_current = None
    if published and views is not None:
        age_hours = (now - published).total_seconds() / 3600
        if age_hours > 0:
            views_per_hour_current = _rounded(views / age_hours)
    result["views_per_hour_current"] = views_per_hour_current
    # Kept for the existing dashboard until its labels are fully migrated.
    result["views_per_hour"] = views_per_hour_current
    history = history or []
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


def _periods(videos: list[dict], now: datetime) -> dict:
    def recent(days: int) -> list[dict]:
        cutoff = now - timedelta(days=days)
        return [
            video
            for video in videos
            if (published := _parse_epoch(video.get("create_time"))) is not None
            and cutoff <= published <= now
        ]

    return {
        "overall": _period_statistics(videos),
        "last_30_days": _period_statistics(recent(30)),
        "last_7_days": _period_statistics(recent(7)),
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


def _top_videos(videos: list[dict], metric: str, limit: int = 10) -> list[dict]:
    rows = []
    for video in videos:
        value = _number(video.get("view_count")) if metric == "views" else video.get("analytics", {}).get(metric)
        if value is None:
            continue
        rows.append(
            {
                "id": video.get("tiktok_video_id"),
                "description": video.get("description"),
                metric: value,
            }
        )
    return sorted(rows, key=lambda row: row[metric], reverse=True)[:limit]


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
    return {
        "periods": periods,
        "recent_vs_overall": _recent_vs_overall(periods),
        "duration_performance": _duration_performance(videos),
        "weekday_performance": _weekday_performance(videos),
        "hour_performance": {"warning": HOUR_WARNING, "rows": _hour_performance(videos)},
        **rankings,
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

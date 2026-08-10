from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .analytics import (
    FOLLOWER_CORRELATION_NOTE,
    HOUR_WARNING,
    WINDOW_TOLERANCES,
    add_account_follower_correlations,
    aggregate_analytics,
    account_analytics,
    enrich_videos,
)
from .database import Database


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _snapshot_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _recent_snapshots(history: list[dict], limit: int = 3) -> list[dict]:
    ordered = sorted(
        (
            item
            for item in history
            if _snapshot_datetime(item.get("collected_at")) is not None
        ),
        key=lambda item: _snapshot_datetime(item.get("collected_at")),
        reverse=True,
    )
    result = []
    for item in ordered[:limit]:
        snapshot = {
            "collected_at": item.get("collected_at"),
            "views": item.get("view_count"),
            "likes": item.get("like_count"),
            "comments": item.get("comment_count"),
            "shares": item.get("share_count"),
        }
        result.append(snapshot)
    return result


def _compact(value):
    """Remove unavailable values from the ChatGPT report, recursively."""

    if isinstance(value, dict):
        compacted = {}
        for key, item in value.items():
            if item is None:
                continue
            item = _compact(item)
            if isinstance(item, dict) and not item:
                continue
            compacted[key] = item
        return compacted
    if isinstance(value, list):
        return [_compact(item) for item in value if item is not None]
    return value


def _load_enriched_data(
    database: Database,
    timezone_name: str,
    now: datetime,
) -> tuple[dict, list[dict], dict[str, list[dict]], list[dict]]:
    account = database.get_latest_account() or {}
    videos = database.get_videos("recent")
    histories = {
        video["tiktok_video_id"]: database.get_metric_history(video["tiktok_video_id"])
        for video in videos
    }
    enriched = enrich_videos(
        videos,
        histories,
        now=now,
        timezone_name=timezone_name,
    )
    # Account snapshots are intentionally loaded in full for long-lived local
    # databases. This does not change the database and is needed for the
    # conservative 30-day account and follower correlation calculations.
    account_snapshots = database.get_account_snapshots(limit=None)
    enriched = add_account_follower_correlations(enriched, account_snapshots)
    return account, enriched, histories, account_snapshots


def _summary_from_overall(overall: dict) -> dict:
    return {
        "total_videos": overall.get("videos", 0),
        # Kept as a small compatibility alias for older local consumers.
        "videos_collected": overall.get("videos", 0),
        "total_views": overall.get("total_views", 0),
        "average_views": overall.get("average_views"),
        "median_views": overall.get("median_views"),
        "average_likes": overall.get("average_likes"),
        "median_likes": overall.get("median_likes"),
        "average_engagement_rate": overall.get("average_engagement_rate"),
        "median_engagement_rate": overall.get("median_engagement_rate"),
        "average_share_rate": overall.get("average_share_rate"),
        "median_share_rate": overall.get("median_share_rate"),
    }


def _report_video(video: dict, history: list[dict]) -> dict:
    analytics = video.get("analytics", {})
    caption = video.get("caption_features", {})
    report_video = {
        "id": video.get("tiktok_video_id"),
        "description": video.get("description"),
        "published_at": video.get("published_at"),
        "published_at_utc": video.get("published_at_utc"),
        "published_at_local": video.get("published_at_local"),
        "duration": video.get("duration"),
        "duration_bucket": video.get("duration_bucket"),
        "publication_weekday": video.get("publication_weekday"),
        "publication_hour": video.get("publication_hour"),
        "publication_minute": video.get("publication_minute"),
        "age_hours": video.get("age_hours"),
        "age_days": video.get("age_days"),
        "share_url": video.get("share_url"),
        "hashtags": caption.get("hashtags", []),
        "caption_length_chars": caption.get("caption_length_chars"),
        "caption_length_words": caption.get("caption_length_words"),
        "has_question_mark": caption.get("has_question_mark", False),
        "has_exclamation_mark": caption.get("has_exclamation_mark", False),
        "has_numbers": caption.get("has_numbers", False),
        "has_emojis": caption.get("has_emojis", False),
        "has_url": caption.get("has_url", False),
        "has_mention": caption.get("has_mention", False),
        "hashtags_count": caption.get("hashtags_count", 0),
        "mentions_count": caption.get("mentions_count", 0),
        "reply_to_comment": caption.get("reply_to_comment", False),
        "current_metrics": {
            "views": video.get("view_count"),
            "likes": video.get("like_count"),
            "comments": video.get("comment_count"),
            "shares": video.get("share_count"),
            "engagement_rate": analytics.get("engagement_rate"),
            "like_rate": analytics.get("like_rate"),
            "comment_rate": analytics.get("comment_rate"),
            "share_rate": analytics.get("share_rate"),
            "lifetime_average_views_per_hour": analytics.get(
                "lifetime_average_views_per_hour"
            ),
            "recent_views_per_hour": analytics.get("recent_views_per_hour"),
            "recent_likes_per_hour": analytics.get("recent_likes_per_hour"),
        },
        "performance": {
            "views_vs_account_median": analytics.get("views_vs_account_median"),
            "engagement_vs_account_median": analytics.get(
                "engagement_vs_account_median"
            ),
            "share_rate_vs_account_median": analytics.get(
                "share_rate_vs_account_median"
            ),
            "views_percentile": analytics.get("views_percentile"),
            "engagement_percentile": analytics.get("engagement_percentile"),
            "share_rate_percentile": analytics.get("share_rate_percentile"),
        },
        "growth": analytics.get("growth", {}),
        "growth_deltas": analytics.get("growth_deltas", {}),
        "velocity": analytics.get("velocity", {}),
        "account_followers_near_publish": video.get(
            "account_followers_near_publish"
        ),
        "account_followers_24h_after_publish": video.get(
            "account_followers_24h_after_publish"
        ),
        "account_followers_48h_after_publish": video.get(
            "account_followers_48h_after_publish"
        ),
        "followers_delta_24h_after_publish": video.get(
            "followers_delta_24h_after_publish"
        ),
        "followers_delta_48h_after_publish": video.get(
            "followers_delta_48h_after_publish"
        ),
    }
    recent_snapshots = _recent_snapshots(history)
    if recent_snapshots:
        report_video["recent_snapshots"] = recent_snapshots
    return report_video


def build_report(
    database: Database,
    timezone_name: str = "UTC",
    source: str = "tiktok",
) -> dict:
    now = datetime.now(timezone.utc)
    account, enriched, histories, account_snapshots = _load_enriched_data(
        database, timezone_name, now
    )
    aggregate = aggregate_analytics(
        enriched,
        timezone_name=timezone_name,
        now=now,
    )
    account_stats = account_analytics(account_snapshots, now=now)
    overall = aggregate["periods"]["overall"]
    report = {
        "schema_version": 2,
        "generated_at": _iso_utc(now),
        "source": source,
        "timezone": timezone_name,
        "account": {
            "display_name": account.get("display_name"),
            "username": account.get("username"),
            **account_stats,
        },
        "summary": _summary_from_overall(overall),
        "analytics": {
            "periods": aggregate["periods"],
            "recent_vs_overall": aggregate["recent_vs_overall"],
            "duration_performance": aggregate["duration_performance"],
            "weekday_performance": aggregate["weekday_performance"],
            "hour_performance": aggregate["hour_performance"],
            "top_videos_by_views": aggregate["top_videos_by_views"],
            "top_videos_by_engagement": aggregate["top_videos_by_engagement"],
            "top_videos_by_share_rate": aggregate["top_videos_by_share_rate"],
            "top_recent_30d_by_views": aggregate["top_recent_30d_by_views"],
            "top_recent_30d_by_engagement": aggregate[
                "top_recent_30d_by_engagement"
            ],
            "top_recent_7d_by_views": aggregate["top_recent_7d_by_views"],
            "top_recent_7d_by_engagement": aggregate[
                "top_recent_7d_by_engagement"
            ],
        },
        "distribution": aggregate["distribution"],
        "outliers": aggregate["outliers"],
        "methodology": {
            "window_estimation": (
                "Each growth value is the total metric from the nearest snapshot "
                "to the target age, only when it falls within the documented "
                "tolerance; no extrapolation is performed."
            ),
            "window_tolerances_hours": {
                f"{hours}h": tolerance for hours, tolerance in WINDOW_TOLERANCES.items()
            },
            "percentile_method": (
                "Percentiles use midrank percentiles from 0 to 100; tied values "
                "receive their average rank. A single available value is 100."
            ),
            "distribution_method": (
                "Distribution quantiles use linear interpolation on sorted values "
                "at index (n - 1) * p; max is the largest observed value."
            ),
            "outlier_method": (
                "Views outliers use the absolute modified z-score with median and "
                "MAD; threshold 3.5. When MAD is zero, non-median values are flagged."
            ),
            "recent_velocity_method": (
                "Recent views/hour and likes/hour use the two most recent real "
                "snapshots and are omitted when the elapsed time is not positive."
            ),
            "null_policy": (
                "Unavailable optional values are omitted from this compact report; "
                "the SQLite snapshot history is not modified."
            ),
            "publication_time": HOUR_WARNING,
            "follower_correlation": FOLLOWER_CORRELATION_NOTE,
        },
        "limitations": [
            "The configured Display API scopes do not expose watch time, average watch time, retention curves, traffic sources, completion rate, or followers gained per video.",
            "The SQLite database keeps the complete metric snapshot history; this main report exports compact age windows instead of metric_history.",
        ],
        "videos": [
            _report_video(video, histories.get(video["tiktok_video_id"], []))
            for video in enriched
        ],
    }
    return _compact(report)


def _timestamped_name(extension: str) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return f"tiktok_report_{stamp}.{extension}"


def generate_json_report(
    database: Database,
    output_dir: str | Path,
    timezone_name: str = "UTC",
    source: str = "tiktok",
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / _timestamped_name("json")
    path.write_text(
        json.dumps(
            build_report(database, timezone_name=timezone_name, source=source),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def generate_csv_report(
    database: Database,
    output_dir: str | Path,
    timezone_name: str = "UTC",
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / _timestamped_name("csv")
    now = datetime.now(timezone.utc)
    _account, enriched, _histories, _snapshots = _load_enriched_data(
        database, timezone_name, now
    )
    fieldnames = [
        "tiktok_video_id",
        "description",
        "published_at_utc",
        "published_at_local",
        "publication_weekday",
        "publication_hour",
        "publication_minute",
        "age_hours",
        "age_days",
        "duration",
        "duration_bucket",
        "share_url",
        "hashtags",
        "hashtags_count",
        "mentions_count",
        "reply_to_comment",
        "views",
        "likes",
        "comments",
        "shares",
        "engagement_rate",
        "like_rate",
        "comment_rate",
        "share_rate",
        "lifetime_average_views_per_hour",
        "recent_views_per_hour",
        "recent_likes_per_hour",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for video in enriched:
            analytics = video.get("analytics", {})
            caption = video.get("caption_features", {})
            writer.writerow(
                {
                    "tiktok_video_id": video.get("tiktok_video_id"),
                    "description": video.get("description"),
                    "published_at_utc": video.get("published_at_utc"),
                    "published_at_local": video.get("published_at_local"),
                    "publication_weekday": video.get("publication_weekday"),
                    "publication_hour": video.get("publication_hour"),
                    "publication_minute": video.get("publication_minute"),
                    "age_hours": video.get("age_hours"),
                    "age_days": video.get("age_days"),
                    "duration": video.get("duration"),
                    "duration_bucket": video.get("duration_bucket"),
                    "share_url": video.get("share_url"),
                    "hashtags": " ".join(
                        f"#{hashtag}" for hashtag in caption.get("hashtags", [])
                    ),
                    "hashtags_count": caption.get("hashtags_count"),
                    "mentions_count": caption.get("mentions_count"),
                    "reply_to_comment": caption.get("reply_to_comment"),
                    "views": video.get("view_count"),
                    "likes": video.get("like_count"),
                    "comments": video.get("comment_count"),
                    "shares": video.get("share_count"),
                    "engagement_rate": analytics.get("engagement_rate"),
                    "like_rate": analytics.get("like_rate"),
                    "comment_rate": analytics.get("comment_rate"),
                    "share_rate": analytics.get("share_rate"),
                    "lifetime_average_views_per_hour": analytics.get(
                        "lifetime_average_views_per_hour"
                    ),
                    "recent_views_per_hour": analytics.get("recent_views_per_hour"),
                    "recent_likes_per_hour": analytics.get("recent_likes_per_hour"),
                }
            )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path

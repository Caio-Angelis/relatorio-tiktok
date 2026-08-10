from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .analytics import aggregate_analytics, enrich_videos
from .database import Database


def _history_for_export(history: list[dict]) -> list[dict]:
    return [
        {
            "collected_at": item.get("collected_at"),
            "views": item.get("view_count"),
            "likes": item.get("like_count"),
            "comments": item.get("comment_count"),
            "shares": item.get("share_count"),
        }
        for item in history
    ]


def _published_at(value) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def build_report(
    database: Database,
    timezone_name: str = "UTC",
    source: str = "tiktok",
) -> dict:
    account = database.get_latest_account() or {}
    videos = database.get_videos("recent")
    histories = {
        video["tiktok_video_id"]: database.get_metric_history(video["tiktok_video_id"])
        for video in videos
    }
    enriched = enrich_videos(videos, histories)
    aggregate = aggregate_analytics(enriched, timezone_name=timezone_name)
    report_videos = []
    for video in enriched:
        report_videos.append(
            {
                "id": video.get("tiktok_video_id"),
                "description": video.get("description"),
                "title": video.get("title"),
                "published_at": _published_at(video.get("create_time")),
                "duration": video.get("duration"),
                "share_url": video.get("share_url"),
                "embed_link": video.get("embed_link"),
                "manual_tags": {
                    "category": video.get("category"),
                    "format": video.get("format"),
                    "hook": video.get("hook"),
                    "notes": video.get("notes"),
                },
                "current_metrics": {
                    "views": video.get("view_count"),
                    "likes": video.get("like_count"),
                    "comments": video.get("comment_count"),
                    "shares": video.get("share_count"),
                    **video.get("analytics", {}),
                },
                "metric_history": _history_for_export(
                    histories[video["tiktok_video_id"]]
                ),
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "source": source,
        "timezone": timezone_name,
        "account": {
            "display_name": account.get("display_name"),
            "username": account.get("username"),
            "followers": account.get("follower_count"),
            "following": account.get("following_count"),
            "likes": account.get("likes_count"),
            "video_count": account.get("video_count"),
        },
        "summary": {
            "videos_collected": aggregate["videos_collected"],
            "total_views": aggregate["total_views"],
            "average_views": aggregate["average_views"],
            "median_views": aggregate["median_views"],
            "average_engagement_rate": aggregate["average_engagement_rate"],
        },
        "analytics": aggregate,
        "videos": report_videos,
        "limitations": [
            "The configured Display API scopes do not expose watch time, average watch time, retention curves, traffic sources, completion rate, or followers gained per video.",
            "Growth metrics are null when the local history does not contain a snapshot at least 24 or 48 hours earlier.",
        ],
    }


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
    videos = database.get_videos("recent")
    histories = {
        video["tiktok_video_id"]: database.get_metric_history(video["tiktok_video_id"])
        for video in videos
    }
    enriched = enrich_videos(videos, histories)
    fieldnames = [
        "tiktok_video_id",
        "description",
        "title",
        "published_at",
        "duration",
        "share_url",
        "views",
        "likes",
        "comments",
        "shares",
        "engagement_rate",
        "like_rate",
        "comment_rate",
        "share_rate",
        "views_per_hour",
        "category",
        "format",
        "hook",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for video in enriched:
            analytics = video.get("analytics", {})
            writer.writerow(
                {
                    "tiktok_video_id": video.get("tiktok_video_id"),
                    "description": video.get("description"),
                    "title": video.get("title"),
                    "published_at": _published_at(video.get("create_time")),
                    "duration": video.get("duration"),
                    "share_url": video.get("share_url"),
                    "views": video.get("view_count"),
                    "likes": video.get("like_count"),
                    "comments": video.get("comment_count"),
                    "shares": video.get("share_count"),
                    "engagement_rate": analytics.get("engagement_rate"),
                    "like_rate": analytics.get("like_rate"),
                    "comment_rate": analytics.get("comment_rate"),
                    "share_rate": analytics.get("share_rate"),
                    "views_per_hour": analytics.get("views_per_hour"),
                    "category": video.get("category"),
                    "format": video.get("format"),
                    "hook": video.get("hook"),
                    "notes": video.get("notes"),
                }
            )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path

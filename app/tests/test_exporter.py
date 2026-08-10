import csv
import json

from app.database import Database
from app.exporter import generate_csv_report, generate_json_report


def test_json_and_csv_exports_are_compact_and_without_tokens_or_manual_fields(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    database.insert_account_snapshot(
        {
            "open_id": "open-id",
            "display_name": "Creator",
            "username": None,
            "avatar_url": None,
            "bio_description": None,
            "profile_deep_link": None,
            "is_verified": None,
            "follower_count": 10,
            "following_count": 20,
            "likes_count": 30,
            "video_count": 1,
        },
        collected_at="2026-08-10T10:00:00Z",
    )
    database.upsert_video(
        {
            "tiktok_video_id": "video-1",
            "description": "A video #guitarra",
            "title": None,
            "create_time": 1700000000,
            "duration": 10,
            "cover_image_url": None,
            "share_url": "https://www.tiktok.com/video/video-1",
            "embed_html": None,
            "embed_link": None,
            "height": None,
            "width": None,
            "view_count": 100,
            "like_count": 10,
            "comment_count": 2,
            "share_count": 1,
        }
    )
    database.record_metric_snapshot(
        "video-1",
        {"view_count": 100, "like_count": 10, "comment_count": 2, "share_count": 1},
        collected_at="2026-08-10T10:00:00Z",
    )
    database.record_metric_snapshot(
        "video-1",
        {"view_count": 180, "like_count": 16, "comment_count": 3, "share_count": 2},
        collected_at="2026-08-11T10:00:00Z",
    )

    json_path = generate_json_report(database, tmp_path / "exports")
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["summary"]["videos_collected"] == 1
    assert report["summary"]["total_videos"] == 1
    assert report["summary"]["median_views"] == 180
    assert report["videos"][0]["hashtags"] == ["guitarra"]
    assert "metric_history" not in report["videos"][0]
    assert "manual_tags" not in report["videos"][0]
    assert all(
        field not in json_path.read_text(encoding="utf-8")
        for field in ("category", "format", "hook", "notes", "access_token")
    )
    assert "window_tolerances_hours" in report["methodology"]
    assert report["analytics"]["hour_performance"]["warning"].startswith("Historical correlation")

    csv_path = generate_csv_report(database, tmp_path / "exports")
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["tiktok_video_id"] == "video-1"
    assert rows[0]["views"] == "180"
    assert rows[0]["hashtags"] == "#guitarra"
    assert "category" not in rows[0]
    assert "format" not in rows[0]

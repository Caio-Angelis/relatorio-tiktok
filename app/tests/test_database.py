from app.database import Database


def sample_video(video_id="video-1", views=100):
    return {
        "tiktok_video_id": video_id,
        "description": "Descrição original",
        "title": "Título",
        "create_time": 1700000000,
        "duration": 20,
        "cover_image_url": "https://example.com/cover.jpg",
        "share_url": "https://www.tiktok.com/@user/video/video-1",
        "embed_html": None,
        "embed_link": "https://www.tiktok.com/player/v1/video-1",
        "height": 1920,
        "width": 1080,
        "view_count": views,
        "like_count": 10,
        "comment_count": 2,
        "share_count": 1,
    }


def test_upsert_video_does_not_duplicate_and_preserves_manual_fields(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    assert database.upsert_video(sample_video()) is True
    database.update_video_metadata(1, "guitarra", "demo", "Hook", "Nota local")

    updated = sample_video(views=200)
    updated["description"] = "Descrição atualizada"
    assert database.upsert_video(updated) is False

    video = database.get_video(1)
    assert database.count_videos() == 1
    assert video["description"] == "Descrição atualizada"
    assert video["view_count"] is None  # current metrics live in video_metrics
    assert video["category"] == "guitarra"
    assert video["format"] == "demo"
    assert video["hook"] == "Hook"
    assert video["notes"] == "Nota local"


def test_metric_snapshots_deduplicate_only_identical_recent_rows(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    database.upsert_video(sample_video())
    metrics = {"view_count": 100, "like_count": 10, "comment_count": 2, "share_count": 1}
    first = database.record_metric_snapshot("video-1", metrics, "2026-08-10T10:00:00Z")
    duplicate = database.record_metric_snapshot("video-1", metrics, "2026-08-10T10:03:00Z")
    changed = database.record_metric_snapshot(
        "video-1",
        {**metrics, "view_count": 140},
        "2026-08-10T10:04:00Z",
    )
    later_same = database.record_metric_snapshot(
        "video-1", {**metrics, "view_count": 140}, "2026-08-10T10:10:00Z"
    )
    assert first is True
    assert duplicate is False
    assert changed is True
    assert later_same is True
    assert len(database.get_metric_history("video-1")) == 3


def test_account_snapshots_can_be_read_without_a_limit(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    assert database.insert_account_snapshot(
        {"follower_count": 10}, "2026-08-10T10:00:00Z"
    ) is True
    assert database.insert_account_snapshot(
        {"follower_count": 20}, "2026-08-10T11:00:00Z"
    ) is True
    assert len(database.get_account_snapshots(limit=1)) == 1
    assert len(database.get_account_snapshots(limit=None)) == 2

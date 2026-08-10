from datetime import datetime, timedelta, timezone

import pytest

from app.analytics import aggregate_analytics, calculate_rates, growth_since, video_analytics


def test_calculate_rates_and_engagement():
    rates = calculate_rates(
        {"view_count": 1000, "like_count": 100, "comment_count": 20, "share_count": 10}
    )
    assert rates == {
        "engagement_rate": 13.0,
        "like_rate": 10.0,
        "comment_rate": 2.0,
        "share_rate": 1.0,
    }


def test_rates_do_not_divide_by_zero():
    rates = calculate_rates(
        {"view_count": 0, "like_count": 10, "comment_count": 2, "share_count": 1}
    )
    assert rates["engagement_rate"] is None
    assert rates["like_rate"] is None
    assert rates["comment_rate"] is None
    assert rates["share_rate"] is None


def test_growth_requires_sufficient_history():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    history = [
        {"collected_at": (now - timedelta(hours=48)).isoformat().replace("+00:00", "Z"), "view_count": 100},
        {"collected_at": (now - timedelta(hours=24)).isoformat().replace("+00:00", "Z"), "view_count": 250},
        {"collected_at": now.isoformat().replace("+00:00", "Z"), "view_count": 500},
    ]
    assert growth_since(history, 24)["views"] == 250
    assert growth_since(history, 24)["percent"] == 100.0
    assert growth_since(history, 48)["views"] == 400
    assert growth_since(history, 72) is None


def test_video_analytics_marks_missing_growth_as_none():
    video = {"create_time": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()), "view_count": 200}
    analytics = video_analytics(video, history=[])
    assert analytics["views_per_hour"] == pytest.approx(100.0, rel=0.01)
    assert analytics["growth_24h"] is None
    assert analytics["growth_48h"] is None


def test_aggregate_analytics_has_rankings():
    videos = [
        {"tiktok_video_id": "a", "description": "A", "view_count": 100, "analytics": {"engagement_rate": 2, "share_rate": 1}},
        {"tiktok_video_id": "b", "description": "B", "view_count": 300, "analytics": {"engagement_rate": 1, "share_rate": 3}},
    ]
    aggregate = aggregate_analytics(videos)
    assert aggregate["videos_collected"] == 2
    assert aggregate["total_views"] == 400
    assert aggregate["top_10_by_views"][0]["id"] == "b"
    assert aggregate["top_10_by_share_rate"][0]["id"] == "b"

from datetime import datetime, timedelta, timezone

import pytest

from app.analytics import (
    HOUR_WARNING,
    aggregate_analytics,
    calculate_rates,
    distribution_analytics,
    duration_bucket,
    enrich_videos,
    extract_caption_features,
    growth_since,
    outlier_analytics,
)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


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


def test_caption_features_are_deterministic_and_reply_detection_is_conservative():
    features = extract_caption_features(
        "Respondendo a @Usuario! 3 ideias #Guitarra #blues #fyp #guitarra 🎸? https://example.com"
    )
    assert features["hashtags"] == ["guitarra", "blues", "fyp"]
    assert features["hashtags_count"] == 3
    assert features["mentions_count"] == 1
    assert features["has_question_mark"] is True
    assert features["has_exclamation_mark"] is True
    assert features["has_numbers"] is True
    assert features["has_emojis"] is True
    assert features["has_url"] is True
    assert features["reply_to_comment"] is True
    assert extract_caption_features("Uma pergunta para @usuario") ["reply_to_comment"] is False


def test_duration_buckets_cover_requested_ranges():
    assert duration_bucket(20) == "0-20s"
    assert duration_bucket(21) == "21-30s"
    assert duration_bucket(45) == "31-45s"
    assert duration_bucket(60) == "46-60s"
    assert duration_bucket(90) == "61-90s"
    assert duration_bucket(91) == "90s+"
    assert duration_bucket(None) is None


def test_growth_requires_sufficient_history():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    history = [
        {"collected_at": iso(now - timedelta(hours=48)), "view_count": 100},
        {"collected_at": iso(now - timedelta(hours=24)), "view_count": 250},
        {"collected_at": iso(now), "view_count": 500},
    ]
    assert growth_since(history, 24)["views"] == 250
    assert growth_since(history, 24)["percent"] == 100.0
    assert growth_since(history, 48)["views"] == 400
    assert growth_since(history, 72) is None


def test_window_growth_timezone_age_deltas_and_velocity():
    published = datetime(2026, 8, 10, 23, tzinfo=timezone.utc)
    now = datetime(2026, 8, 13, 23, tzinfo=timezone.utc)
    values = {1: 100, 3: 300, 6: 650, 12: 1200, 24: 2500, 48: 3800, 72: 4300}
    history = [
        {
            "collected_at": iso(published + timedelta(hours=hours)),
            "view_count": views,
            "like_count": views // 10,
            "comment_count": views // 100,
            "share_count": views // 200,
        }
        for hours, views in values.items()
    ]
    video = {
        "tiktok_video_id": "video-1",
        "description": "Dica #guitarra",
        "create_time": int(published.timestamp()),
        "duration": 25,
        "view_count": 5000,
        "like_count": 500,
        "comment_count": 50,
        "share_count": 25,
    }
    enriched = enrich_videos(
        [video],
        {"video-1": history},
        now=now,
        timezone_name="America/Campo_Grande",
    )[0]
    assert enriched["published_at_utc"] == "2026-08-10T23:00:00Z"
    assert enriched["published_at_local"] == "2026-08-10T19:00:00-04:00"
    assert enriched["publication_weekday"] == "segunda-feira"
    assert enriched["publication_hour"] == 19
    assert enriched["publication_minute"] == 0
    assert enriched["age_hours"] == 72.0
    assert enriched["age_days"] == 3.0
    assert enriched["analytics"]["growth"]["views"]["6h"] == 650
    assert enriched["analytics"]["growth"]["comments"]["24h"] == 25
    assert "1h" not in enriched["analytics"]["growth"]["comments"]
    assert enriched["analytics"]["growth_deltas"]["views_growth_6_to_12h"] == 550
    assert enriched["analytics"]["velocity"]["views_per_hour_0_1h"] == 100.0
    assert enriched["analytics"]["velocity"]["views_per_hour_1_3h"] == 100.0
    assert enriched["analytics"]["lifetime_average_views_per_hour"] == pytest.approx(69.44, rel=0.01)
    assert enriched["analytics"]["recent_views_per_hour"] == pytest.approx(20.83, rel=0.01)
    assert enriched["analytics"]["recent_likes_per_hour"] == pytest.approx(2.08, rel=0.01)


def test_missing_window_is_null_instead_of_extrapolated():
    published = datetime(2026, 8, 10, 23, tzinfo=timezone.utc)
    video = {
        "tiktok_video_id": "video-1",
        "create_time": int(published.timestamp()),
        "view_count": 10,
        "like_count": 1,
        "comment_count": 0,
        "share_count": 0,
    }
    enriched = enrich_videos(
        [video],
        {
            "video-1": [
                {
                    "collected_at": iso(published + timedelta(hours=10)),
                    "view_count": 10,
                    "like_count": 1,
                    "comment_count": 0,
                    "share_count": 0,
                }
            ]
        },
        now=published + timedelta(hours=10),
    )[0]
    assert enriched["analytics"]["growth"]["views"]["1h"] is None
    assert enriched["analytics"]["growth"]["views"]["12h"] == 10
    assert enriched["analytics"]["growth"]["views"]["24h"] is None


def test_aggregate_analytics_prioritizes_medians_and_exposes_grouped_stats():
    videos = [
        {
            "tiktok_video_id": "a",
            "description": "A",
            "create_time": int(datetime(2026, 8, 10, tzinfo=timezone.utc).timestamp()),
            "duration": 18,
            "view_count": 100,
            "like_count": 10,
            "comment_count": 2,
            "share_count": 1,
        },
        {
            "tiktok_video_id": "b",
            "description": "B",
            "create_time": int(datetime(2026, 8, 9, tzinfo=timezone.utc).timestamp()),
            "duration": 60,
            "view_count": 300,
            "like_count": 30,
            "comment_count": 3,
            "share_count": 9,
        },
    ]
    enriched = enrich_videos(videos, {}, now=datetime(2026, 8, 11, tzinfo=timezone.utc))
    aggregate = aggregate_analytics(
        enriched,
        now=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    assert aggregate["videos_collected"] == 2
    assert aggregate["total_views"] == 400
    assert aggregate["median_views"] == 200
    assert aggregate["top_10_by_views"][0]["id"] == "b"
    assert aggregate["top_videos_by_share_rate"][0]["id"] == "b"
    assert set(aggregate["periods"]) == {"overall", "last_30_days", "last_7_days"}
    assert aggregate["duration_performance"][0]["duration_bucket"] == "0-20s"
    assert aggregate["hour_performance"]["warning"] == HOUR_WARNING
    assert aggregate["distribution"]["views"]["p50"] == 200
    assert aggregate["distribution"]["views"]["max"] == 300
    assert aggregate["outliers"]["views"] == []


def test_distribution_and_robust_mad_outlier_detection():
    videos = [
        {
            "tiktok_video_id": f"video-{index}",
            "view_count": views,
            "like_count": 10,
            "comment_count": 1,
            "share_count": 1,
            "analytics": {"engagement_rate": 1.0},
        }
        for index, views in enumerate((100, 110, 120, 125, 130, 140, 1000))
    ]
    distribution = distribution_analytics(videos)
    outliers = outlier_analytics(videos)
    assert distribution["views"]["p25"] == 115
    assert distribution["views"]["p50"] == 125
    assert distribution["views"]["p90"] == 484
    assert distribution["views"]["max"] == 1000
    assert outliers["views"] == [
        {"id": "video-6", "views": 1000, "views_vs_median": 8.0}
    ]


def test_recent_rankings_are_limited_and_use_recent_periods():
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)
    videos = []
    for index in range(12):
        published = now - timedelta(days=2 if index < 11 else 40)
        views = 100 + index * 100
        videos.append(
            {
                "tiktok_video_id": f"video-{index}",
                "description": "x" * 140,
                "create_time": int(published.timestamp()),
                "view_count": views,
                "like_count": views // 10,
                "comment_count": 1,
                "share_count": 1,
            }
        )
    enriched = enrich_videos(videos, {}, now=now)
    aggregate = aggregate_analytics(enriched, now=now)
    assert len(aggregate["top_recent_30d_by_views"]) == 10
    assert len(aggregate["top_recent_7d_by_engagement"]) == 10
    assert aggregate["top_recent_30d_by_views"][0]["id"] == "video-10"
    assert aggregate["top_recent_7d_by_engagement"][0]["short_description"].endswith("...")
    assert len(aggregate["top_recent_7d_by_engagement"][0]["short_description"]) == 120


def test_percentiles_and_account_follower_correlations_are_available():
    from app.analytics import account_analytics, add_account_follower_correlations

    now = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
    snapshots = [
        {"collected_at": iso(now), "follower_count": 150, "likes_count": 300},
        {
            "collected_at": iso(now - timedelta(hours=24)),
            "follower_count": 100,
            "likes_count": 250,
        },
        {
            "collected_at": iso(now - timedelta(days=7)),
            "follower_count": 80,
            "likes_count": 200,
        },
    ]
    account = account_analytics(snapshots, now=now)
    assert account["current_followers"] == 150
    assert account["followers_24h_ago"] == 100
    assert account["followers_growth_24h"] == 50
    assert account["followers_7d_ago"] == 80
    assert account["likes_growth_7d"] == 100

    videos = enrich_videos(
        [
            {
                "tiktok_video_id": "video-1",
                "create_time": int((now - timedelta(hours=24)).timestamp()),
                "view_count": 100,
                "like_count": 10,
                "comment_count": 1,
                "share_count": 1,
            }
        ],
        {},
        now=now,
    )
    correlated = add_account_follower_correlations(videos, snapshots)[0]
    assert correlated["account_followers_near_publish"] == 100
    assert correlated["account_followers_24h_after_publish"] == 150
    assert correlated["followers_delta_24h_after_publish"] == 50
    assert videos[0]["analytics"]["views_percentile"] == 100.0

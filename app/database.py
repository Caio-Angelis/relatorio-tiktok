from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _iso_minus_minutes(value: str, minutes: int) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


class Database:
    """Small SQLite data access layer for the single local TikTok account."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS auth_tokens (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        access_token TEXT NOT NULL,
                        refresh_token TEXT NOT NULL,
                        expires_at INTEGER NOT NULL,
                        refresh_expires_at INTEGER,
                        open_id TEXT,
                        scope TEXT,
                        token_type TEXT NOT NULL DEFAULT 'Bearer',
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS account_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        collected_at TEXT NOT NULL,
                        open_id TEXT,
                        display_name TEXT,
                        username TEXT,
                        avatar_url TEXT,
                        bio_description TEXT,
                        profile_deep_link TEXT,
                        is_verified INTEGER,
                        follower_count INTEGER,
                        following_count INTEGER,
                        likes_count INTEGER,
                        video_count INTEGER
                    );

                    CREATE INDEX IF NOT EXISTS idx_account_snapshots_collected_at
                        ON account_snapshots(collected_at);

                    CREATE TABLE IF NOT EXISTS videos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tiktok_video_id TEXT NOT NULL UNIQUE,
                        description TEXT,
                        title TEXT,
                        create_time INTEGER,
                        duration INTEGER,
                        cover_image_url TEXT,
                        share_url TEXT,
                        embed_html TEXT,
                        embed_link TEXT,
                        height INTEGER,
                        width INTEGER,
                        category TEXT,
                        format TEXT,
                        hook TEXT,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS video_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tiktok_video_id TEXT NOT NULL,
                        collected_at TEXT NOT NULL,
                        view_count INTEGER,
                        like_count INTEGER,
                        comment_count INTEGER,
                        share_count INTEGER,
                        FOREIGN KEY (tiktok_video_id)
                            REFERENCES videos(tiktok_video_id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_video_metrics_video_time
                        ON video_metrics(tiktok_video_id, collected_at);
                    """
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
        return dict(row) if row is not None else None

    def get_auth_tokens(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM auth_tokens WHERE id = 1"
            ).fetchone()
        return self._row_to_dict(row)

    def save_auth_tokens(self, values: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_tokens
                    (id, access_token, refresh_token, expires_at,
                     refresh_expires_at, open_id, scope, token_type, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    refresh_expires_at = excluded.refresh_expires_at,
                    open_id = excluded.open_id,
                    scope = excluded.scope,
                    token_type = excluded.token_type,
                    updated_at = excluded.updated_at
                """,
                (
                    values["access_token"],
                    values["refresh_token"],
                    int(values["expires_at"]),
                    int(values["refresh_expires_at"])
                    if values.get("refresh_expires_at") is not None
                    else None,
                    values.get("open_id"),
                    values.get("scope"),
                    values.get("token_type") or "Bearer",
                    values.get("updated_at") or utc_now_iso(),
                ),
            )

    def clear_auth_tokens(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_tokens WHERE id = 1")

    def insert_account_snapshot(
        self,
        profile: dict[str, Any],
        collected_at: str | None = None,
        deduplicate_minutes: int = 5,
    ) -> bool:
        collected_at = collected_at or utc_now_iso()
        fields = (
            "open_id",
            "display_name",
            "username",
            "avatar_url",
            "bio_description",
            "profile_deep_link",
            "is_verified",
            "follower_count",
            "following_count",
            "likes_count",
            "video_count",
        )
        values = tuple(
            int(profile[field]) if field == "is_verified" and profile.get(field) is not None else profile.get(field)
            for field in fields
        )
        with self.connect() as connection:
            latest = connection.execute(
                "SELECT * FROM account_snapshots ORDER BY collected_at DESC, id DESC LIMIT 1"
            ).fetchone()
            if latest is not None:
                is_recent = latest["collected_at"] >= _iso_minus_minutes(
                    collected_at, deduplicate_minutes
                )
                same = all(latest[field] == value for field, value in zip(fields, values))
                if is_recent and same:
                    return False
            connection.execute(
                """
                INSERT INTO account_snapshots
                    (collected_at, open_id, display_name, username, avatar_url,
                     bio_description, profile_deep_link, is_verified,
                     follower_count, following_count, likes_count, video_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (collected_at, *values),
            )
        return True

    def get_latest_account(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM account_snapshots ORDER BY collected_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return self._row_to_dict(row)

    def get_account_snapshots(self, limit: int = 30) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM account_snapshots
                ORDER BY collected_at DESC, id DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_video(self, video: dict[str, Any], updated_at: str | None = None) -> bool:
        updated_at = updated_at or utc_now_iso()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM videos WHERE tiktok_video_id = ?",
                (video["tiktok_video_id"],),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO videos
                        (tiktok_video_id, description, title, create_time, duration,
                         cover_image_url, share_url, embed_html, embed_link,
                         height, width, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        video["tiktok_video_id"],
                        video.get("description"),
                        video.get("title"),
                        video.get("create_time"),
                        video.get("duration"),
                        video.get("cover_image_url"),
                        video.get("share_url"),
                        video.get("embed_html"),
                        video.get("embed_link"),
                        video.get("height"),
                        video.get("width"),
                        updated_at,
                        updated_at,
                    ),
                )
                return True
            connection.execute(
                """
                UPDATE videos SET
                    description = ?, title = ?, create_time = ?, duration = ?,
                    cover_image_url = ?, share_url = ?, embed_html = ?,
                    embed_link = ?, height = ?, width = ?, updated_at = ?
                WHERE tiktok_video_id = ?
                """,
                (
                    video.get("description"),
                    video.get("title"),
                    video.get("create_time"),
                    video.get("duration"),
                    video.get("cover_image_url"),
                    video.get("share_url"),
                    video.get("embed_html"),
                    video.get("embed_link"),
                    video.get("height"),
                    video.get("width"),
                    updated_at,
                    video["tiktok_video_id"],
                ),
            )
        return False

    def update_video_metadata(
        self,
        video_id: int,
        category: str | None,
        video_format: str | None,
        hook: str | None,
        notes: str | None,
    ) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE videos
                SET category = ?, format = ?, hook = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (category, video_format, hook, notes, utc_now_iso(), int(video_id)),
            )
        return cursor.rowcount == 1

    def record_metric_snapshot(
        self,
        tiktok_video_id: str,
        metrics: dict[str, Any],
        collected_at: str | None = None,
        deduplicate_minutes: int = 5,
    ) -> bool:
        collected_at = collected_at or utc_now_iso()
        metric_fields = ("view_count", "like_count", "comment_count", "share_count")
        values = tuple(metrics.get(field) for field in metric_fields)
        if all(value is None for value in values):
            return False
        with self.connect() as connection:
            latest = connection.execute(
                """
                SELECT * FROM video_metrics
                WHERE tiktok_video_id = ?
                ORDER BY collected_at DESC, id DESC LIMIT 1
                """,
                (tiktok_video_id,),
            ).fetchone()
            if latest is not None:
                is_recent = latest["collected_at"] >= _iso_minus_minutes(
                    collected_at, deduplicate_minutes
                )
                same = all(latest[field] == value for field, value in zip(metric_fields, values))
                if is_recent and same:
                    return False
            connection.execute(
                """
                INSERT INTO video_metrics
                    (tiktok_video_id, collected_at, view_count, like_count,
                     comment_count, share_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (tiktok_video_id, collected_at, *values),
            )
        return True

    def get_metric_history(self, tiktok_video_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM video_metrics
                WHERE tiktok_video_id = ?
                ORDER BY collected_at ASC, id ASC
                """,
                (tiktok_video_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_videos(self, sort: str = "recent") -> list[dict]:
        sort_columns = {
            "recent": "COALESCE(v.create_time, 0) DESC, v.id DESC",
            "oldest": "COALESCE(v.create_time, 0) ASC, v.id ASC",
            "views": "COALESCE(lm.view_count, -1) DESC, COALESCE(v.create_time, 0) DESC",
            "likes": "COALESCE(lm.like_count, -1) DESC, COALESCE(v.create_time, 0) DESC",
            "shares": "COALESCE(lm.share_count, -1) DESC, COALESCE(v.create_time, 0) DESC",
        }
        order_by = sort_columns.get(sort, sort_columns["recent"])
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                WITH latest_metrics AS (
                    SELECT vm.*
                    FROM video_metrics vm
                    INNER JOIN (
                        SELECT tiktok_video_id, MAX(id) AS max_id
                        FROM video_metrics GROUP BY tiktok_video_id
                    ) latest ON latest.max_id = vm.id
                )
                SELECT v.*, lm.collected_at AS metrics_collected_at,
                       lm.view_count, lm.like_count, lm.comment_count, lm.share_count
                FROM videos v
                LEFT JOIN latest_metrics lm
                    ON lm.tiktok_video_id = v.tiktok_video_id
                ORDER BY {order_by}
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_video(self, video_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                WITH latest_metrics AS (
                    SELECT vm.*
                    FROM video_metrics vm
                    INNER JOIN (
                        SELECT tiktok_video_id, MAX(id) AS max_id
                        FROM video_metrics GROUP BY tiktok_video_id
                    ) latest ON latest.max_id = vm.id
                )
                SELECT v.*, lm.collected_at AS metrics_collected_at,
                       lm.view_count, lm.like_count, lm.comment_count, lm.share_count
                FROM videos v
                LEFT JOIN latest_metrics lm
                    ON lm.tiktok_video_id = v.tiktok_video_id
                WHERE v.id = ?
                """,
                (int(video_id),),
            ).fetchone()
        return self._row_to_dict(row)

    def count_videos(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0])

    def has_video_data(self) -> bool:
        return self.count_videos() > 0

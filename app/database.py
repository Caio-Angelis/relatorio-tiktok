from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 2


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
                connection.execute("PRAGMA user_version = 1")
            if version < 2:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS video_ai_analysis (
                        tiktok_video_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL DEFAULT 'pending',
                        model_name TEXT,
                        prompt_version TEXT,
                        transcription_text TEXT,
                        transcription_segments_json TEXT,
                        detected_language TEXT,
                        language_probability REAL,
                        transcript_first_3s TEXT,
                        transcript_first_5s TEXT,
                        analysis_json TEXT,
                        primary_topic TEXT,
                        content_type TEXT,
                        format TEXT,
                        hook_type TEXT,
                        hook_text TEXT,
                        summary TEXT,
                        confidence REAL,
                        analyzed_at TEXT,
                        updated_at TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT,
                        FOREIGN KEY (tiktok_video_id)
                            REFERENCES videos(tiktok_video_id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_video_ai_analysis_status
                        ON video_ai_analysis(status);
                    CREATE INDEX IF NOT EXISTS idx_video_ai_analysis_topic
                        ON video_ai_analysis(primary_topic);
                    CREATE INDEX IF NOT EXISTS idx_video_ai_analysis_content_type
                        ON video_ai_analysis(content_type);
                    CREATE INDEX IF NOT EXISTS idx_video_ai_analysis_hook_type
                        ON video_ai_analysis(hook_type);

                    CREATE TABLE IF NOT EXISTS ai_jobs (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        status TEXT NOT NULL DEFAULT 'idle',
                        stop_requested INTEGER NOT NULL DEFAULT 0,
                        worker_pid INTEGER,
                        current_video_id TEXT,
                        current_stage TEXT,
                        total INTEGER NOT NULL DEFAULT 0,
                        completed INTEGER NOT NULL DEFAULT 0,
                        pending INTEGER NOT NULL DEFAULT 0,
                        failed INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS ai_insight_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        generated_at TEXT NOT NULL,
                        input_fingerprint TEXT NOT NULL,
                        model_name TEXT,
                        prompt_version TEXT,
                        report_json TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_ai_insight_reports_fingerprint
                        ON ai_insight_reports(input_fingerprint);
                    """
                )
                now = utc_now_iso()
                connection.execute(
                    """
                    INSERT INTO ai_jobs (id, created_at, updated_at)
                    VALUES (1, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (now, now),
                )
                connection.execute("PRAGMA user_version = 2")
            elif version >= 2:
                # Repair an interrupted/partial local AI migration without
                # touching any historical TikTok data.
                now = utc_now_iso()
                connection.execute(
                    """
                    INSERT INTO ai_jobs (id, created_at, updated_at)
                    VALUES (1, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (now, now),
                )
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

    def get_account_snapshots(self, limit: int | None = 30) -> list[dict]:
        with self.connect() as connection:
            query = """
                SELECT * FROM account_snapshots
                ORDER BY collected_at DESC, id DESC
            """
            parameters: tuple = ()
            if limit is not None:
                query += " LIMIT ?"
                parameters = (int(limit),)
            rows = connection.execute(query, parameters).fetchall()
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
                       lm.view_count, lm.like_count, lm.comment_count, lm.share_count,
                       ai.status AS ai_status,
                       ai.primary_topic AS ai_primary_topic,
                       ai.content_type AS ai_content_type,
                       ai.hook_type AS ai_hook_type,
                       ai.last_error AS ai_last_error
                FROM videos v
                LEFT JOIN latest_metrics lm
                    ON lm.tiktok_video_id = v.tiktok_video_id
                LEFT JOIN video_ai_analysis ai
                    ON ai.tiktok_video_id = v.tiktok_video_id
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
                       lm.view_count, lm.like_count, lm.comment_count, lm.share_count,
                       ai.status AS ai_status,
                       ai.primary_topic AS ai_primary_topic,
                       ai.content_type AS ai_content_type,
                       ai.hook_type AS ai_hook_type,
                       ai.last_error AS ai_last_error
                FROM videos v
                LEFT JOIN latest_metrics lm
                    ON lm.tiktok_video_id = v.tiktok_video_id
                LEFT JOIN video_ai_analysis ai
                    ON ai.tiktok_video_id = v.tiktok_video_id
                WHERE v.id = ?
                """,
                (int(video_id),),
            ).fetchone()
        return self._row_to_dict(row)

    def get_video_by_tiktok_id(self, tiktok_video_id: str) -> dict | None:
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
                       lm.view_count, lm.like_count, lm.comment_count, lm.share_count,
                       ai.status AS ai_status,
                       ai.primary_topic AS ai_primary_topic,
                       ai.content_type AS ai_content_type,
                       ai.hook_type AS ai_hook_type,
                       ai.last_error AS ai_last_error
                FROM videos v
                LEFT JOIN latest_metrics lm
                    ON lm.tiktok_video_id = v.tiktok_video_id
                LEFT JOIN video_ai_analysis ai
                    ON ai.tiktok_video_id = v.tiktok_video_id
                WHERE v.tiktok_video_id = ?
                """,
                (str(tiktok_video_id),),
            ).fetchone()
        return self._row_to_dict(row)

    def count_videos(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0])

    def has_video_data(self) -> bool:
        return self.count_videos() > 0

    # ------------------------------------------------------------------
    # Local AI persistence. These methods deliberately live beside the
    # existing source-of-truth tables; no duplicate TikTok or metric store is
    # introduced.

    def ensure_ai_analysis_rows(self) -> int:
        """Create pending rows for videos that have never been queued."""

        now = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO video_ai_analysis
                    (tiktok_video_id, status, updated_at)
                SELECT tiktok_video_id, 'pending', ?
                FROM videos
                WHERE NOT EXISTS (
                    SELECT 1 FROM video_ai_analysis ai
                    WHERE ai.tiktok_video_id = videos.tiktok_video_id
                )
                """,
                (now,),
            )
            return int(connection.execute("SELECT changes()").fetchone()[0])

    def get_ai_analysis(self, tiktok_video_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM video_ai_analysis WHERE tiktok_video_id = ?",
                (str(tiktok_video_id),),
            ).fetchone()
        return self._row_to_dict(row)

    def get_ai_analyses(self, status: str | None = None) -> list[dict]:
        query = "SELECT * FROM video_ai_analysis"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY updated_at ASC, tiktok_video_id ASC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_ai_queue(self, include_failed: bool = False) -> list[dict]:
        self.ensure_ai_analysis_rows()
        statuses = ["pending"]
        if include_failed:
            statuses.extend(
                ["download_failed", "transcription_failed", "analysis_failed"]
            )
        placeholders = ",".join("?" for _ in statuses)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT v.*, ai.status AS ai_status, ai.attempts AS ai_attempts,
                       ai.last_error AS ai_last_error
                FROM videos v
                INNER JOIN video_ai_analysis ai
                    ON ai.tiktok_video_id = v.tiktok_video_id
                WHERE ai.status IN ({placeholders})
                ORDER BY COALESCE(v.create_time, 0) ASC, v.id ASC
                """,
                tuple(statuses),
            ).fetchall()
        return [dict(row) for row in rows]

    def begin_ai_attempt(
        self,
        tiktok_video_id: str,
        model_name: str,
        prompt_version: str,
    ) -> dict:
        now = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO video_ai_analysis
                    (tiktok_video_id, status, model_name, prompt_version,
                     updated_at, attempts, last_error)
                VALUES (?, 'downloading', ?, ?, ?, 1, NULL)
                ON CONFLICT(tiktok_video_id) DO UPDATE SET
                    status = 'downloading',
                    model_name = excluded.model_name,
                    prompt_version = excluded.prompt_version,
                    updated_at = excluded.updated_at,
                    attempts = video_ai_analysis.attempts + 1,
                    last_error = NULL
                """,
                (str(tiktok_video_id), model_name, prompt_version, now),
            )
            row = connection.execute(
                "SELECT * FROM video_ai_analysis WHERE tiktok_video_id = ?",
                (str(tiktok_video_id),),
            ).fetchone()
        return dict(row)

    def set_ai_status(
        self,
        tiktok_video_id: str,
        status: str,
        *,
        last_error: str | None = None,
        current_stage: str | None = None,
    ) -> None:
        now = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO video_ai_analysis
                    (tiktok_video_id, status, updated_at, last_error)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tiktok_video_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    last_error = excluded.last_error
                """,
                (str(tiktok_video_id), status, now, last_error),
            )
        if current_stage is not None:
            self.update_ai_job(
                current_video_id=str(tiktok_video_id), current_stage=current_stage
            )

    def save_ai_transcription(
        self,
        tiktok_video_id: str,
        *,
        text: str,
        segments_json: str,
        detected_language: str | None,
        language_probability: float | None,
        first_3s: str | None,
        first_5s: str | None,
    ) -> None:
        now = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE video_ai_analysis SET
                    transcription_text = ?,
                    transcription_segments_json = ?,
                    detected_language = ?,
                    language_probability = ?,
                    transcript_first_3s = ?,
                    transcript_first_5s = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE tiktok_video_id = ?
                """,
                (
                    text,
                    segments_json,
                    detected_language,
                    language_probability,
                    first_3s,
                    first_5s,
                    now,
                    str(tiktok_video_id),
                ),
            )

    def save_ai_completed(
        self,
        tiktok_video_id: str,
        *,
        analysis: dict,
        analysis_json: str,
        model_name: str,
        prompt_version: str,
        analyzed_at: str | None = None,
    ) -> None:
        now = utc_now_iso()
        analyzed_at = analyzed_at or now
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE video_ai_analysis SET
                    status = 'completed',
                    model_name = ?,
                    prompt_version = ?,
                    analysis_json = ?,
                    primary_topic = ?,
                    content_type = ?,
                    format = ?,
                    hook_type = ?,
                    hook_text = ?,
                    summary = ?,
                    confidence = ?,
                    analyzed_at = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE tiktok_video_id = ?
                """,
                (
                    model_name,
                    prompt_version,
                    analysis_json,
                    analysis.get("primary_topic"),
                    analysis.get("content_type"),
                    analysis.get("format"),
                    analysis.get("hook_type"),
                    analysis.get("hook_text"),
                    analysis.get("summary"),
                    analysis.get("confidence"),
                    analyzed_at,
                    now,
                    str(tiktok_video_id),
                ),
            )

    def save_ai_analysis(
        self,
        tiktok_video_id: str,
        analysis: dict,
        *,
        model_name: str,
        prompt_version: str,
        analysis_json: str | None = None,
    ) -> None:
        """Public convenience alias for callers persisting a final result."""

        if hasattr(analysis, "model_dump"):
            analysis = analysis.model_dump(mode="json")
        analysis = dict(analysis)
        if analysis_json is None:
            import json

            analysis_json = json.dumps(analysis, ensure_ascii=False, separators=(",", ":"))
        self.ensure_ai_analysis_rows()
        self.save_ai_completed(
            tiktok_video_id,
            analysis=analysis,
            analysis_json=analysis_json,
            model_name=model_name,
            prompt_version=prompt_version,
        )

    def update_ai_analysis_status(
        self, tiktok_video_id: str, status: str, last_error: str | None = None
    ) -> None:
        self.set_ai_status(tiktok_video_id, status, last_error=last_error)

    def mark_ai_failure(
        self, tiktok_video_id: str, status: str, last_error: str
    ) -> None:
        error = str(last_error).strip()[:2000] or "Falha não especificada."
        self.set_ai_status(tiktok_video_id, status, last_error=error)

    def get_ai_counts(self) -> dict[str, int]:
        self.ensure_ai_analysis_rows()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS amount FROM video_ai_analysis GROUP BY status"
            ).fetchall()
        counts = {str(row["status"]): int(row["amount"]) for row in rows}
        total = self.count_videos()
        completed = counts.get("completed", 0)
        failed = sum(
            counts.get(status, 0)
            for status in ("download_failed", "transcription_failed", "analysis_failed")
        )
        in_progress = sum(
            counts.get(status, 0)
            for status in ("downloading", "transcribing", "extracting_frames", "analyzing")
        )
        pending = max(0, total - completed - failed - in_progress)
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "failed": failed,
            "in_progress": in_progress,
            **counts,
        }

    def get_ai_job(self) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM ai_jobs WHERE id = 1").fetchone()
        if row is None:
            now = utc_now_iso()
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO ai_jobs (id, created_at, updated_at) VALUES (1, ?, ?)",
                    (now, now),
                )
            return self.get_ai_job()
        return dict(row)

    def create_ai_job(self, *, reanalyze_all: bool = False) -> dict:
        self.ensure_ai_analysis_rows()
        now = utc_now_iso()
        with self.connect() as connection:
            if reanalyze_all:
                connection.execute(
                    """
                    UPDATE video_ai_analysis
                    SET status = 'pending', last_error = NULL, updated_at = ?
                    WHERE status <> 'pending'
                    """,
                    (now,),
                )
            connection.execute(
                """
                UPDATE ai_jobs SET
                    status = 'queued', stop_requested = 0, worker_pid = NULL,
                    current_video_id = NULL, current_stage = 'queued',
                    last_error = NULL, created_at = ?, updated_at = ?,
                    finished_at = NULL
                WHERE id = 1
                """,
                (now, now),
            )
        return self.get_ai_job()

    def update_ai_job(self, **values: Any) -> dict:
        allowed = {
            "status",
            "stop_requested",
            "worker_pid",
            "current_video_id",
            "current_stage",
            "total",
            "completed",
            "pending",
            "failed",
            "last_error",
            "started_at",
            "finished_at",
        }
        values = {key: value for key, value in values.items() if key in allowed}
        if not values:
            return self.get_ai_job()
        values["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE ai_jobs SET {assignments} WHERE id = 1",
                tuple(values.values()),
            )
        return self.get_ai_job()

    def request_ai_stop(self) -> dict:
        return self.update_ai_job(stop_requested=1)

    def clear_ai_stop(self) -> dict:
        return self.update_ai_job(stop_requested=0)

    def retry_failed_ai(self) -> int:
        now = utc_now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE video_ai_analysis
                SET status = 'pending', updated_at = ?, last_error = NULL
                WHERE status IN ('download_failed', 'transcription_failed', 'analysis_failed')
                """,
                (now,),
            )
        return cursor.rowcount

    def latest_ai_report(
        self,
        input_fingerprint: str,
        model_name: str,
        prompt_version: str,
    ) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM ai_insight_reports
                WHERE input_fingerprint = ? AND model_name = ? AND prompt_version = ?
                ORDER BY id DESC LIMIT 1
                """,
                (input_fingerprint, model_name, prompt_version),
            ).fetchone()
        return self._row_to_dict(row)

    def get_latest_ai_report(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_insight_reports ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return self._row_to_dict(row)

    def save_ai_report(
        self,
        input_fingerprint: str,
        model_name: str,
        prompt_version: str,
        report_json: str,
        generated_at: str | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ai_insight_reports
                    (generated_at, input_fingerprint, model_name, prompt_version, report_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    generated_at or utc_now_iso(),
                    input_fingerprint,
                    model_name,
                    prompt_version,
                    report_json,
                ),
            )
            return int(cursor.lastrowid)

    def recover_stale_ai_work(self, worker_alive: bool = False) -> bool:
        """Put interrupted stages back in the queue after a dead worker."""

        if worker_alive:
            return False
        now = utc_now_iso()
        changed = False
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE video_ai_analysis
                SET status = 'pending', updated_at = ?, last_error = COALESCE(
                    last_error, 'Worker encerrado antes da conclusão; colocado novamente na fila.'
                )
                WHERE status IN ('downloading', 'transcribing', 'extracting_frames', 'analyzing')
                """,
                (now,),
            )
            changed = cursor.rowcount > 0
            connection.execute(
                """
                UPDATE ai_jobs SET
                    status = CASE WHEN status IN ('running', 'queued') THEN 'paused' ELSE status END,
                    worker_pid = NULL,
                    current_video_id = NULL,
                    current_stage = CASE WHEN status IN ('running', 'queued') THEN 'recovered' ELSE current_stage END,
                    updated_at = ?
                WHERE id = 1 AND worker_pid IS NOT NULL
                """,
                (now,),
            )
        return changed

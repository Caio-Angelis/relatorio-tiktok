import json
import sqlite3
from pathlib import Path

import pytest

from app.ai.classifier import (
    AnalysisValidationError,
    SemanticClassifier,
    parse_analysis_json,
)
from app.ai.media import FrameSample, deduplicate_frame_paths, select_frame_timestamps
from app.ai.pipeline import VideoAnalysisPipeline
from app.ai.strategist import LocalStrategist
from app.ai.transcriber import TranscriptionResult, transcript_window
from app.ai.worker import WorkerLock
from app.analytics import semantic_analytics, semantic_group_performance
from app.app import create_app
from app.database import Database
from app.exporter import generate_json_report


def video(video_id="video-1", views=1000):
    return {
        "tiktok_video_id": video_id,
        "description": "História de guitarra",
        "title": "Guitarra",
        "duration": 30,
        "share_url": f"https://www.tiktok.com/@local/video/{video_id}",
        "create_time": 1700000000,
        "view_count": views,
        "like_count": 100,
        "comment_count": 10,
        "share_count": 20,
    }


def analysis_payload(topic="guitarra", hook="curiosidade"):
    return {
        "primary_topic": topic,
        "secondary_topics": ["música"],
        "content_type": "historia",
        "format": "narração + imagens",
        "hook_type": hook,
        "hook_text": "Você sabia?",
        "hook_summary": "Abre com uma curiosidade.",
        "hook_strengths": ["curto"],
        "person_names": ["Pessoa Um"],
        "bands": [],
        "artists": [],
        "products": [],
        "subjects": ["guitarra"],
        "visual_style": "documental",
        "editing_style": "cortes",
        "caption_style": "texto na tela",
        "narration_style": "narrado",
        "tone": "didático",
        "cta_type": None,
        "cta_text": None,
        "structure": ["gancho", "contexto", "conclusão"],
        "first_3_seconds": "Você sabia?",
        "first_5_seconds": "Você sabia? Aqui está o contexto.",
        "opening_visual": "guitarra",
        "opening_text": "Você sabia?",
        "summary": "Uma história curta sobre guitarra.",
        "keywords": ["guitarra"],
        "language": "pt",
        "confidence": 0.9,
        "has_face": True,
        "has_guitar": True,
        "has_on_screen_captions": True,
        "uses_ai_generated_visuals": False,
        "estimated_scene_changes": 3,
    }


def test_ai_migration_and_persistent_checkpoints(tmp_path):
    database = Database(tmp_path / "ai.db")
    database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"video_ai_analysis", "ai_jobs", "ai_insight_reports"} <= tables

    database.upsert_video(video())
    assert database.ensure_ai_analysis_rows() == 1
    database.begin_ai_attempt("video-1", "model", "prompt-1")
    database.set_ai_status("video-1", "transcribing")
    database.save_ai_transcription(
        "video-1",
        text="Olá",
        segments_json='[{"start":0,"end":1,"text":"Olá"}]',
        detected_language="pt",
        language_probability=0.99,
        first_3s="Olá",
        first_5s="Olá",
    )
    payload = analysis_payload()
    database.save_ai_completed(
        "video-1",
        analysis=payload,
        analysis_json=json.dumps(payload),
        model_name="model",
        prompt_version="prompt-1",
    )
    stored = database.get_ai_analysis("video-1")
    assert stored["status"] == "completed"
    assert stored["transcription_text"] == "Olá"
    assert stored["primary_topic"] == "guitarra"
    assert stored["attempts"] == 1


def test_v1_database_is_migrated_incrementally_without_losing_video(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE videos (id INTEGER PRIMARY KEY, tiktok_video_id TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE video_metrics (id INTEGER PRIMARY KEY, tiktok_video_id TEXT NOT NULL, collected_at TEXT NOT NULL, view_count INTEGER, like_count INTEGER, comment_count INTEGER, share_count INTEGER)"
    )
    connection.execute("INSERT INTO videos VALUES (1, 'legacy-video', 'a', 'a')")
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()
    database = Database(path)
    database.initialize()
    assert database.get_video_by_tiktok_id("legacy-video")["tiktok_video_id"] == "legacy-video"
    assert database.get_ai_analysis("legacy-video") is None
    assert database.ensure_ai_analysis_rows() == 1


def test_completed_video_is_cached_and_not_reprocessed(tmp_path):
    database = Database(tmp_path / "cache.db")
    database.initialize()
    database.upsert_video(video())
    database.ensure_ai_analysis_rows()
    payload = analysis_payload()
    database.save_ai_completed(
        "video-1",
        analysis=payload,
        analysis_json=json.dumps(payload),
        model_name="model",
        prompt_version="1",
    )

    class NeverDownloader:
        def download(self, *_args):
            raise AssertionError("completed não pode baixar novamente")

    pipeline = VideoAnalysisPipeline(
        database,
        NeverDownloader(),
        object(),
        object(),
        temp_dir=tmp_path,
        model_name="model",
        prompt_version="1",
    )
    result = pipeline.process(video())
    assert result.skipped is True
    assert database.get_ai_analysis("video-1")["attempts"] == 0


def test_retry_increments_attempts_and_failed_rows_return_to_pending(tmp_path):
    database = Database(tmp_path / "retry.db")
    database.initialize()
    database.upsert_video(video())
    database.ensure_ai_analysis_rows()
    database.begin_ai_attempt("video-1", "model", "1")
    database.mark_ai_failure("video-1", "download_failed", "sem acesso")
    assert database.get_ai_counts()["failed"] == 1
    assert database.retry_failed_ai() == 1
    assert database.get_ai_analysis("video-1")["status"] == "pending"
    database.begin_ai_attempt("video-1", "model", "1")
    assert database.get_ai_analysis("video-1")["attempts"] == 2


def test_worker_lock_and_recovery_after_dead_process(tmp_path):
    lock_path = tmp_path / "worker.lock"
    first = WorkerLock(lock_path)
    second = WorkerLock(lock_path)
    assert first.acquire() is True
    assert second.acquire() is False
    second.release()
    first.release()

    database = Database(tmp_path / "recovery.db")
    database.initialize()
    database.upsert_video(video())
    database.ensure_ai_analysis_rows()
    database.begin_ai_attempt("video-1", "model", "1")
    database.set_ai_status("video-1", "analyzing")
    database.update_ai_job(status="running", worker_pid=999999)
    assert database.recover_stale_ai_work(worker_alive=False) is True
    assert database.get_ai_analysis("video-1")["status"] == "pending"
    assert database.get_ai_job()["status"] == "paused"


def test_pause_flag_is_persistent_until_continue(tmp_path):
    database = Database(tmp_path / "pause.db")
    database.initialize()
    assert database.request_ai_stop()["stop_requested"] == 1
    assert database.get_ai_job()["stop_requested"] == 1
    assert database.clear_ai_stop()["stop_requested"] == 0


def test_frame_sampling_prioritizes_opening_and_handles_short_clips():
    timestamps = select_frame_timestamps(40, 12)
    assert timestamps[:6] == [0.0, 0.5, 1.0, 2.0, 3.0, 5.0]
    assert len(timestamps) <= 12
    assert all(0 <= value <= 40 for value in timestamps)
    short = select_frame_timestamps(2, 12)
    assert short == [0.0, 0.5, 1.0, 2.0]


def test_frame_deduplication_uses_perceptual_hash(monkeypatch, tmp_path):
    paths = []
    for index in range(4):
        path = tmp_path / f"frame-{index}.jpg"
        path.write_text("fixture")
        paths.append(path)
    hashes = [(0,) * 64, (0,) * 64, (1,) * 64, (1,) * 64]
    iterator = iter(hashes)
    monkeypatch.setattr("app.ai.media._average_hash", lambda _path: next(iterator))
    assert deduplicate_frame_paths(paths) == [paths[0], paths[2]]


def test_transcript_windows_preserve_timestamped_segments():
    segments = [
        {"start": 0.0, "end": 1.2, "text": "primeiro"},
        {"start": 2.9, "end": 4.0, "text": "segundo"},
        {"start": 5.1, "end": 6.0, "text": "terceiro"},
    ]
    assert transcript_window(segments, 3) == "primeiro segundo"
    result = TranscriptionResult("primeiro segundo terceiro", segments, "pt", 0.9)
    assert result.to_dict()["transcript_first_5s"] == "primeiro segundo"


def test_json_parser_handles_markdown_and_rejects_empty_object():
    payload = analysis_payload()
    parsed = parse_analysis_json("```json\n" + json.dumps(payload) + "\n```")
    assert parsed["primary_topic"] == "guitarra"
    with pytest.raises(AnalysisValidationError):
        parse_analysis_json("texto sem JSON")
    with pytest.raises(AnalysisValidationError):
        parse_analysis_json("{}")


def test_classifier_makes_one_local_json_repair_attempt():
    class FakeVision:
        def __init__(self):
            self.calls = 0

        def generate(self, _prompt, _frames):
            self.calls += 1
            return "não-json" if self.calls == 1 else json.dumps(analysis_payload())

    vision = FakeVision()
    result = SemanticClassifier(vision).classify(
        video(),
        transcription_text="Você sabia?",
        segments=[{"start": 0, "end": 1, "text": "Você sabia?"}],
        frames=[{"timestamp": 0.0, "path": "/tmp/frame.jpg"}],
        detected_language="pt",
    )
    assert result["content_type"] == "historia"
    assert vision.calls == 2


class FakeMedia:
    def __init__(self, temp_root: Path, *, fail=None):
        self.temp_root = temp_root
        self.fail = fail

    def probe_duration(self, _path):
        if self.fail == "probe":
            raise RuntimeError("probe")
        return 2.0

    def extract_audio(self, _video, target):
        if self.fail == "audio":
            raise RuntimeError("audio")
        Path(target).write_bytes(b"wav")
        return Path(target)

    def extract_frames(self, _video, frames_dir, _duration, **_kwargs):
        if self.fail == "frames":
            raise RuntimeError("frames")
        frames_dir = Path(frames_dir)
        frames_dir.mkdir(parents=True, exist_ok=True)
        frame = frames_dir / "frame.jpg"
        frame.write_bytes(b"frame")
        return [FrameSample(0.0, frame)]


class FakeDownloader:
    def __init__(self, temp_root: Path, fail=False):
        self.temp_root = temp_root
        self.fail = fail

    def download(self, _url, video_id):
        if self.fail:
            from app.ai.downloader import DownloadError

            raise DownloadError("download")
        directory = self.temp_root / video_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "video.mp4"
        target.write_bytes(b"mp4")
        return target


class FakeTranscriber:
    def __init__(self, fail=False):
        self.fail = fail

    def transcribe(self, _audio):
        if self.fail:
            from app.ai.transcriber import TranscriptionError

            raise TranscriptionError("whisper")
        return TranscriptionResult(
            "fala local",
            [{"start": 0.0, "end": 1.0, "text": "fala local"}],
            "pt",
            0.95,
        )


class FakeVision:
    def __init__(self, fail=False):
        self.fail = fail

    def generate(self, _prompt, _frames):
        if self.fail:
            from app.ai.vision import VisionInferenceError

            raise VisionInferenceError("vlm")
        return json.dumps(analysis_payload())


def make_pipeline(tmp_path, *, download_fail=False, transcribe_fail=False, vision_fail=False):
    database = Database(tmp_path / "pipeline.db")
    database.initialize()
    database.upsert_video(video())
    database.ensure_ai_analysis_rows()
    return database, VideoAnalysisPipeline(
        database,
        FakeDownloader(tmp_path, fail=download_fail),
        FakeTranscriber(fail=transcribe_fail),
        FakeVision(fail=vision_fail),
        temp_dir=tmp_path,
        media_module=FakeMedia(tmp_path),
        model_name="model",
        prompt_version="1",
    )


def test_pipeline_success_persists_and_cleans_temp_files(tmp_path):
    database, pipeline = make_pipeline(tmp_path)
    result = pipeline.process(video())
    assert result.status == "completed"
    assert database.get_ai_analysis("video-1")["status"] == "completed"
    assert not (tmp_path / "video-1").exists()


def test_pipeline_download_transcription_and_vlm_failures_are_isolated(tmp_path):
    database, pipeline = make_pipeline(tmp_path, download_fail=True)
    assert pipeline.process(video()).status == "download_failed"
    assert database.get_ai_analysis("video-1")["last_error"] == "download"

    database, pipeline = make_pipeline(tmp_path, transcribe_fail=True)
    assert pipeline.process(video()).status == "transcription_failed"

    database, pipeline = make_pipeline(tmp_path, vision_fail=True)
    assert pipeline.process(video()).status == "analysis_failed"
    assert not (tmp_path / "video-1").exists()


def test_semantic_analytics_groups_hooks_people_combinations_and_sample_size():
    videos = [video("a", 100), video("b", 300), video("c", 500)]
    analyses = {
        "a": analysis_payload("tema-a", "curiosidade"),
        "b": analysis_payload("tema-a", "curiosidade"),
        "c": analysis_payload("tema-b", "promessa"),
    }
    hooks = semantic_group_performance(videos, analyses, "hook_type")
    curiosity = next(row for row in hooks if row["key"] == "curiosidade")
    assert curiosity["sample_size"] == 2
    assert curiosity["median_views"] == 200
    assert curiosity["evidence_level"] == "sinal preliminar"
    semantic = semantic_analytics(videos, analyses)
    assert semantic["groups"]["topic_hook"]
    assert "score_formula" in semantic


def test_insight_report_is_cached_by_structured_input(tmp_path):
    database = Database(tmp_path / "insights.db")
    database.initialize()
    database.upsert_video(video())
    database.ensure_ai_analysis_rows()
    payload = analysis_payload()
    database.save_ai_completed(
        "video-1",
        analysis=payload,
        analysis_json=json.dumps(payload),
        model_name="Qwen/Qwen3-VL-8B-Instruct",
        prompt_version="1",
    )

    class StrategyVision:
        def __init__(self):
            self.calls = 0

        def generate(self, _prompt, frames):
            assert frames == []
            self.calls += 1
            return json.dumps({
                "summary": "Resumo local",
                "what_is_working": [],
                "best_hooks": [],
                "best_formats": [],
                "strongest_topics": [],
                "strongest_people_bands": [],
                "promising_combinations": [],
                "recent_usage": {},
                "priority_ideas": [],
                "experimental_ideas": [],
                "limitations": [],
            })

    vision = StrategyVision()
    strategist = LocalStrategist(database, vision, model_name="Qwen/Qwen3-VL-8B-Instruct")
    first = strategist.generate()
    second = strategist.generate()
    assert first["cached"] is False
    assert second["cached"] is True
    assert vision.calls == 1


def test_export_includes_only_compact_ai_analysis(tmp_path):
    database = Database(tmp_path / "export-ai.db")
    database.initialize()
    database.upsert_video(video())
    database.record_metric_snapshot("video-1", video())
    database.ensure_ai_analysis_rows()
    payload = analysis_payload()
    database.save_ai_completed(
        "video-1",
        analysis=payload,
        analysis_json=json.dumps({**payload, "private_raw": "do not export"}),
        model_name="model",
        prompt_version="1",
    )
    report = json.loads(generate_json_report(database, tmp_path / "exports").read_text())
    exported = report["videos"][0]["ai_analysis"]
    assert exported["primary_topic"] == "guitarra"
    assert "private_raw" not in json.dumps(report)
    assert "transcription_segments_json" not in json.dumps(report)


def csrf_token(response):
    import re

    return re.search(
        r'<meta name="csrf-token" content="([^"]+)"',
        response.get_data(as_text=True),
    ).group(1)


def test_ai_pages_status_and_csrf_work_without_optional_dependencies(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "MOCK_TIKTOK": True,
            "DATABASE_PATH": tmp_path / "web.db",
            "EXPORTS_DIR": tmp_path / "exports",
            "AI_TEMP_DIR": tmp_path / "tmp",
            "SECRET_KEY": "test",
        }
    )
    client = app.test_client()
    ai = client.get("/ai")
    assert ai.status_code == 200
    assert "Analisar biblioteca com IA" in ai.get_data(as_text=True)
    assert "IA local não configurada" in ai.get_data(as_text=True)
    assert client.get("/ai/insights").status_code == 200
    status = client.get("/api/ai/status")
    assert status.status_code == 200
    assert {"enabled", "worker_running", "total", "completed", "pending", "failed"} <= set(status.json)
    assert client.post("/api/ai/pause").status_code == 400
    token = csrf_token(ai)
    response = client.post("/api/ai/analyze-library", headers={"X-CSRF-Token": token})
    assert response.status_code == 503
    assert "setup_ai.sh" in response.json["error"]
    relative = client.post(
        "/api/ai/videos/1/local-file",
        json={"local_path": "video.mp4"},
        headers={"X-CSRF-Token": token},
    )
    assert relative.status_code == 400
    confirmation = client.post(
        "/api/ai/analyze-library",
        json={"reanalyze_all": True},
        headers={"X-CSRF-Token": token},
    )
    assert confirmation.status_code == 400

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

from ..config import settings_from_env
from ..database import Database, utc_now_iso
from .config import ensure_runtime_ready, runtime_capabilities


LOGGER = logging.getLogger("app.ai.worker")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


class WorkerLock:
    """Advisory single-process lock; Linux releases it after a crash."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import fcntl

            self.handle = self.path.open("a+")
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.handle.seek(0)
            self.handle.truncate()
            self.handle.write(str(os.getpid()))
            self.handle.flush()
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
            return True
        except (BlockingIOError, OSError):
            if self.handle is not None:
                self.handle.close()
                self.handle = None
            return False

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.release()


def _logging_setup() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )


def _settings_with_lock(settings: dict) -> Path:
    return Path(settings["AI_TEMP_DIR"]).resolve() / "worker.lock"


def _counts_for_job(database: Database) -> dict:
    counts = database.get_ai_counts()
    database.update_ai_job(
        total=counts["total"],
        completed=counts["completed"],
        pending=counts["pending"],
        failed=counts["failed"],
    )
    return counts


def _build_models(settings: dict, *, whisper: bool = True):
    # Heavy modules are imported only inside a worker process.
    from .downloader import VideoDownloader
    from .transcriber import WhisperTranscriber
    from .vision import QwenVisionAnalyzer

    transcriber = WhisperTranscriber(
        settings["AI_WHISPER_MODEL"],
        device=settings["AI_DEVICE"],
        compute_type=settings["AI_WHISPER_COMPUTE_TYPE"],
    ) if whisper else None
    vision = QwenVisionAnalyzer(
        settings["AI_VISION_MODEL"],
        dtype=settings["AI_VISION_DTYPE"],
        device=settings["AI_DEVICE"],
    )
    if transcriber is not None:
        transcriber.load()
    vision.load()
    downloader = VideoDownloader(
        settings["AI_TEMP_DIR"],
        cookies_browser=settings.get("AI_DOWNLOAD_COOKIES_BROWSER"),
        timeout=settings.get("REQUEST_TIMEOUT", 30),
    )
    return downloader, transcriber, vision


def run_batch(
    settings: dict | None = None,
    *,
    video_id: str | None = None,
    include_failed: bool = False,
    force: bool = False,
    local_file: str | Path | None = None,
) -> dict:
    """Run one persistent queue in one worker process."""

    _logging_setup()
    settings = settings or settings_from_env()
    database = Database(settings["DATABASE_PATH"])
    database.initialize()
    lock = WorkerLock(_settings_with_lock(settings))
    if not lock.acquire():
        LOGGER.info("[AI] já existe um worker ativo; nenhum segundo worker foi iniciado")
        return {"ok": False, "already_running": True}

    transcriber = None
    vision = None
    try:
        # The advisory lock has proved that an old PID cannot still own the
        # queue, so interrupted per-video stages are safe to return to pending.
        database.recover_stale_ai_work(worker_alive=False)
        if include_failed:
            database.retry_failed_ai()
        database.ensure_ai_analysis_rows()
        if video_id:
            video = database.get_video_by_tiktok_id(video_id)
            if video is None:
                database.update_ai_job(
                    status="failed",
                    worker_pid=None,
                    last_error="Vídeo não encontrado no SQLite.",
                    current_stage="idle",
                    finished_at=utc_now_iso(),
                )
                return {"ok": False, "error": "Vídeo não encontrado no SQLite."}
            queue = [video]
        else:
            queue = database.get_ai_queue(include_failed=False)
        if not queue:
            _counts_for_job(database)
            database.update_ai_job(
                status="completed",
                worker_pid=None,
                current_video_id=None,
                current_stage="idle",
                finished_at=utc_now_iso(),
                stop_requested=0,
            )
            return {"ok": True, "processed": 0, "message": "Nenhum vídeo pendente."}

        local_downloader = None
        if local_file:
            from .downloader import LocalFileDownloader

            if not video_id:
                raise RuntimeError("--local-file só pode ser usado com --video.")
            local_downloader = LocalFileDownloader(local_file, settings["AI_TEMP_DIR"])

        database.update_ai_job(
            status="running",
            worker_pid=os.getpid(),
            started_at=utc_now_iso(),
            finished_at=None,
            current_stage="loading_models",
            stop_requested=0 if not database.get_ai_job().get("stop_requested") else 1,
        )
        runtime = ensure_runtime_ready(settings)
        LOGGER.info(
            "[AI] worker iniciado · modelo %s · GPU %s · VRAM %s GB",
            runtime.get("model"),
            runtime.get("gpu_name") or "desconhecida",
            runtime.get("vram_gb") or "—",
        )
        _downloader, transcriber, vision = _build_models(settings)
        if local_downloader is not None:
            _downloader = local_downloader

        from .pipeline import VideoAnalysisPipeline

        def stage_callback(current_video_id: str, stage: str) -> None:
            database.update_ai_job(
                current_video_id=current_video_id,
                current_stage=stage,
            )

        pipeline = VideoAnalysisPipeline(
            database,
            _downloader,
            transcriber,
            vision,
            temp_dir=settings["AI_TEMP_DIR"],
            model_name=settings["AI_VISION_MODEL"],
            max_frames=settings["AI_MAX_FRAMES"],
            max_image_side=settings["AI_MAX_IMAGE_SIDE"],
            delete_temp_files=settings["AI_DELETE_TEMP_FILES"],
            stage_callback=stage_callback,
        )
        processed = 0
        results = []
        for video in queue:
            job = database.get_ai_job()
            if job.get("stop_requested") and processed == 0:
                break
            result = pipeline.process(video, force=force)
            processed += 1
            results.append(
                {
                    "tiktok_video_id": result.tiktok_video_id,
                    "status": result.status,
                    "skipped": result.skipped,
                    "error": result.error,
                }
            )
            _counts_for_job(database)
            if database.get_ai_job().get("stop_requested"):
                database.update_ai_job(
                    status="paused",
                    worker_pid=None,
                    current_video_id=None,
                    current_stage="paused_after_video",
                    finished_at=utc_now_iso(),
                )
                return {"ok": True, "processed": processed, "paused": True, "results": results}

        counts = _counts_for_job(database)
        stop_requested = bool(database.get_ai_job().get("stop_requested"))
        database.update_ai_job(
            status="paused" if stop_requested else "completed",
            worker_pid=None,
            current_video_id=None,
            current_stage="idle",
            finished_at=utc_now_iso(),
            stop_requested=1 if stop_requested else 0,
        )
        return {"ok": True, "processed": processed, "results": results}
    except Exception as exc:
        message = str(exc).strip()[:2000] or "Falha no worker local."
        LOGGER.exception("[AI] worker falhou: %s", message)
        database.update_ai_job(
            status="failed",
            worker_pid=None,
            current_video_id=None,
            current_stage="failed",
            last_error=message,
            finished_at=utc_now_iso(),
        )
        return {"ok": False, "error": message}
    finally:
        if vision is not None:
            vision.close()
        if transcriber is not None:
            transcriber.close()
        lock.release()


def run_insights(settings: dict | None = None, *, force: bool = False) -> dict:
    _logging_setup()
    settings = settings or settings_from_env()
    database = Database(settings["DATABASE_PATH"])
    database.initialize()
    lock = WorkerLock(_settings_with_lock(settings))
    if not lock.acquire():
        return {"ok": False, "already_running": True}
    vision = None
    try:
        database.recover_stale_ai_work(worker_alive=False)
        database.update_ai_job(
            status="running",
            worker_pid=os.getpid(),
            current_video_id=None,
            current_stage="generating_insights",
            started_at=utc_now_iso(),
            finished_at=None,
        )
        ensure_runtime_ready(settings)
        _downloader, _transcriber, vision = _build_models(settings, whisper=False)
        from .strategist import generate_insights

        report = generate_insights(
            database,
            vision,
            force=force,
            model_name=settings["AI_VISION_MODEL"],
            timezone_name=settings["APP_TIMEZONE"],
        )
        _counts_for_job(database)
        database.update_ai_job(
            status="completed",
            worker_pid=None,
            current_stage="insights_ready",
            finished_at=utc_now_iso(),
        )
        return {"ok": True, "report": report}
    except Exception as exc:
        message = str(exc).strip()[:2000] or "Falha ao gerar insights."
        database.update_ai_job(
            status="failed",
            worker_pid=None,
            current_stage="insights_failed",
            last_error=message,
            finished_at=utc_now_iso(),
        )
        LOGGER.exception("[AI] geração de insights falhou: %s", message)
        return {"ok": False, "error": message}
    finally:
        if vision is not None:
            vision.close()
        lock.release()


class _SelfTestMedia:
    def __init__(self, audio_source: Path, frames):
        self.audio_source = audio_source
        self.frames = frames

    def probe_duration(self, _path):
        return 2.0

    def extract_audio(self, _video_path, target):
        Path(target).write_bytes(self.audio_source.read_bytes())
        return Path(target)

    def extract_frames(self, _video_path, _frames_dir, **_kwargs):
        return self.frames


def self_test(settings: dict | None = None) -> dict:
    """Load both real local models and run a tiny synthetic pipeline."""

    _logging_setup()
    settings = settings or settings_from_env()
    capabilities = runtime_capabilities({**settings, "AI_ENABLED": True})
    if not capabilities["cuda_available"]:
        raise RuntimeError(
            "Self-test exige CUDA disponível; nenhum fallback silencioso para CPU foi usado."
        )
    ensure_runtime_ready({**settings, "AI_ENABLED": True})
    from .media import FrameSample
    from .pipeline import VideoAnalysisPipeline

    with tempfile.TemporaryDirectory(prefix="tiktok-ai-self-test-") as temporary:
        root = Path(temporary)
        audio = root / "synthetic.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 16000)
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Pillow não está instalado.") from exc
        frames_dir = root / "frames"
        frames_dir.mkdir()
        frames = []
        for index, color in enumerate(((30, 180, 180), (180, 30, 80))):
            path = frames_dir / f"frame-{index}.jpg"
            Image.new("RGB", (320, 560), color).save(path, quality=85)
            frames.append(FrameSample(index * 0.5, path))

        database = Database(root / "self-test.db")
        database.initialize()
        database.upsert_video(
            {
                "tiktok_video_id": "self-test-video",
                "description": "Fixture local de teste",
                "title": "Fixture",
                "duration": 2,
                "share_url": "https://www.tiktok.com/@local/video/self-test-video",
            }
        )
        database.ensure_ai_analysis_rows()

        class FakeDownloader:
            def download(self, _url, _video_id):
                path = root / "self-test-video" / "video.mp4"
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"synthetic")
                return path

        _downloader, transcriber, vision = _build_models(settings)
        try:
            pipeline = VideoAnalysisPipeline(
                database,
                FakeDownloader(),
                transcriber,
                vision,
                temp_dir=root,
                model_name=settings["AI_VISION_MODEL"],
                max_frames=2,
                max_image_side=320,
                media_module=_SelfTestMedia(audio, frames),
            )
            result = pipeline.process(database.get_video_by_tiktok_id("self-test-video"))
        finally:
            vision.close()
            transcriber.close()
        if result.status != "completed":
            raise RuntimeError(f"Pipeline self-test falhou: {result.error}")
        stored = database.get_ai_analysis("self-test-video")
        if not stored or stored.get("status") != "completed":
            raise RuntimeError("Análise não foi persistida no self-test.")
    return {"ok": True, "message": "Self-test local do Whisper + Qwen3-VL concluído."}


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Worker de IA local do Relatorio TikTok")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--pending", action="store_true")
    parser.add_argument("--video")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--insights", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--local-file")
    args = parser.parse_args(argv)
    settings = settings_from_env()
    if args.self_test:
        try:
            _print_json(self_test(settings))
            return 0
        except Exception as exc:
            print(f"Self-test falhou: {exc}", file=sys.stderr)
            return 1
    database = Database(settings["DATABASE_PATH"])
    database.initialize()
    if args.status:
        job = database.get_ai_job()
        counts = database.get_ai_counts()
        job["worker_running"] = _pid_alive(job.get("worker_pid"))
        _print_json({"job": job, **counts, "runtime": runtime_capabilities(settings)})
        return 0
    if args.pending:
        _print_json(
            [
                item["tiktok_video_id"]
                for item in database.get_ai_queue(include_failed=False)
            ]
        )
        return 0
    if args.insights:
        result = run_insights(settings, force=args.force)
    else:
        result = run_batch(
            settings,
            video_id=args.video,
            include_failed=args.retry_failed,
            force=args.force,
            local_file=args.local_file,
        )
    _print_json(result)
    return 0 if result.get("ok") or result.get("already_running") else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from .analytics import aggregate_analytics, enrich_videos, sort_enriched_videos
from .config import settings_from_env
from .database import Database
from .exporter import generate_csv_report, generate_json_report
from .mock_tiktok import MockTikTokAPI
from .sync_service import NotConnectedError, SyncService
from .tiktok_api import (
    AUTHORIZATION_ENDPOINT,
    REVOKE_ENDPOINT,
    TOKEN_ENDPOINT,
    USER_INFO_ENDPOINT,
    VIDEO_LIST_ENDPOINT,
    VIDEO_QUERY_ENDPOINT,
    TikTokAPI,
    TikTokAPIError,
    code_challenge_for,
    generate_code_verifier,
    generate_state,
)


def _display_number(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _display_percent(value) -> str:
    return "—" if value is None else f"{value:.2f}%"


def _format_datetime(value, timezone_name: str, include_time: bool = True) -> str:
    if value is None:
        return "—"
    try:
        if isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo

            parsed = parsed.astimezone(ZoneInfo(timezone_name))
        except Exception:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%d/%m/%Y %H:%M" if include_time else "%d/%m/%Y")
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def _safe_external_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(str(value))
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return str(value)
    return None


def _clean_manual(value: str | None, max_length: int = 1000) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:max_length] if value else None


def _token_ready_values(payload: dict) -> dict:
    required = ("access_token", "refresh_token", "expires_in")
    if any(not payload.get(field) for field in required):
        raise TikTokAPIError("A resposta OAuth do TikTok não trouxe todos os campos necessários.")
    # Kept here only for validation; conversion and persistence stay in the
    # sync service so token handling is centralized.
    return payload


def create_app(test_config: dict | None = None) -> Flask:
    settings = settings_from_env(test_config)
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY=settings["SECRET_KEY"] or secrets.token_hex(32),
        TIKTOK_CLIENT_KEY=settings["TIKTOK_CLIENT_KEY"],
        TIKTOK_CLIENT_SECRET=settings["TIKTOK_CLIENT_SECRET"],
        TIKTOK_REDIRECT_URI=settings["TIKTOK_REDIRECT_URI"],
        TIKTOK_SCOPES=settings["TIKTOK_SCOPES"],
        APP_TIMEZONE=settings["APP_TIMEZONE"],
        REQUEST_TIMEOUT=settings["REQUEST_TIMEOUT"],
        MOCK_TIKTOK=settings["MOCK_TIKTOK"],
        DATABASE_PATH=settings["DATABASE_PATH"],
        EXPORTS_DIR=settings["EXPORTS_DIR"],
        ROOT_DIR=settings["ROOT_DIR"],
        APP_DIR=settings["APP_DIR"],
        AI_ENABLED=settings["AI_ENABLED"],
        AI_DEVICE=settings["AI_DEVICE"],
        AI_WHISPER_MODEL=settings["AI_WHISPER_MODEL"],
        AI_WHISPER_COMPUTE_TYPE=settings["AI_WHISPER_COMPUTE_TYPE"],
        AI_VISION_MODEL=settings["AI_VISION_MODEL"],
        AI_VISION_DTYPE=settings["AI_VISION_DTYPE"],
        AI_TEMP_DIR=settings["AI_TEMP_DIR"],
        AI_DELETE_TEMP_FILES=settings["AI_DELETE_TEMP_FILES"],
        AI_MAX_FRAMES=settings["AI_MAX_FRAMES"],
        AI_MAX_IMAGE_SIDE=settings["AI_MAX_IMAGE_SIDE"],
        AI_DOWNLOAD_COOKIES_BROWSER=settings["AI_DOWNLOAD_COOKIES_BROWSER"],
        AI_AUTO_ANALYZE_NEW_VIDEOS=settings["AI_AUTO_ANALYZE_NEW_VIDEOS"],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
    )
    if test_config:
        # Preserve Flask's standard testing/debug flags without allowing them
        # to affect paths or credentials before initialization above.
        for key in ("TESTING", "DEBUG", "PROPAGATE_EXCEPTIONS"):
            if key in test_config:
                app.config[key] = test_config[key]
    app.secret_key = app.config["SECRET_KEY"]

    database = Database(app.config["DATABASE_PATH"])
    database.initialize()
    real_api = TikTokAPI(
        app.config["TIKTOK_CLIENT_KEY"],
        app.config["TIKTOK_CLIENT_SECRET"],
        app.config["TIKTOK_REDIRECT_URI"],
        app.config["TIKTOK_SCOPES"],
        timeout=app.config["REQUEST_TIMEOUT"],
    )
    api = MockTikTokAPI() if app.config["MOCK_TIKTOK"] else real_api
    service = SyncService(database, api, mock=app.config["MOCK_TIKTOK"])
    app.extensions["database"] = database
    app.extensions["tiktok_api"] = api
    app.extensions["sync_service"] = service

    def csrf_token_value() -> str:
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def require_csrf() -> None:
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        expected = session.get("csrf_token", "")
        if not supplied or not expected or not hmac.compare_digest(supplied, expected):
            abort(400, description="Token CSRF inválido.")

    def is_connected() -> bool:
        return bool(app.config["MOCK_TIKTOK"] or database.get_auth_tokens())

    def enriched_videos(sort: str = "recent") -> list[dict]:
        db_sort = sort if sort in {"recent", "oldest", "views", "likes", "shares"} else "recent"
        videos = database.get_videos(db_sort)
        histories = {
            video["tiktok_video_id"]: database.get_metric_history(video["tiktok_video_id"])
            for video in videos
        }
        enriched = enrich_videos(
            videos,
            histories,
            timezone_name=app.config["APP_TIMEZONE"],
        )
        return sort_enriched_videos(enriched, sort)

    def ensure_mock_data() -> None:
        if app.config["MOCK_TIKTOK"] and not database.get_latest_account():
            service.sync()
        if app.config["MOCK_TIKTOK"] and database.has_video_data():
            # The mock UI remains useful without torch/Transformers. These
            # records are explicitly synthetic and never trigger inference.
            from .ai.mock import seed_mock_ai_analyses

            seed_mock_ai_analyses(database)

    def _worker_pid_alive(pid: int | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def _ai_runtime() -> dict:
        from .ai.config import runtime_capabilities

        return runtime_capabilities(
            {
                "AI_ENABLED": app.config["AI_ENABLED"],
                "AI_DEVICE": app.config["AI_DEVICE"],
                "AI_VISION_MODEL": app.config["AI_VISION_MODEL"],
                "AI_VISION_DTYPE": app.config["AI_VISION_DTYPE"],
                "AI_WHISPER_MODEL": app.config["AI_WHISPER_MODEL"],
                "AI_WHISPER_COMPUTE_TYPE": app.config["AI_WHISPER_COMPUTE_TYPE"],
            }
        )

    def _ai_status_payload() -> dict:
        job = database.get_ai_job()
        worker_running = _worker_pid_alive(job.get("worker_pid")) and job.get(
            "status"
        ) in {"queued", "running"}
        if job.get("status") in {"running", "queued"} and job.get("worker_pid") and not worker_running:
            database.recover_stale_ai_work(worker_alive=False)
            job = database.get_ai_job()
        counts = database.get_ai_counts()
        runtime = _ai_runtime()
        return {
            "enabled": runtime["enabled"],
            "ready": runtime["ready"],
            "message": runtime["message"],
            "worker_running": worker_running,
            "job_status": job.get("status"),
            "total": counts["total"],
            "completed": counts["completed"],
            "pending": counts["pending"],
            "failed": counts["failed"],
            "in_progress": counts["in_progress"],
            "current_video_id": job.get("current_video_id"),
            "current_stage": job.get("current_stage"),
            "stop_requested": bool(job.get("stop_requested")),
            "last_error": job.get("last_error"),
            "runtime": runtime,
        }

    def _launch_ai_worker(
        worker_args: list[str],
        *,
        reanalyze_all: bool = False,
        retry_failed: bool = False,
    ) -> dict:
        status = _ai_status_payload()
        if status["worker_running"]:
            return {"ok": True, "already_running": True, "status": status}
        runtime = _ai_runtime()
        if not runtime["ready"]:
            raise RuntimeError(runtime["message"])
        database.create_ai_job(reanalyze_all=reanalyze_all)
        if retry_failed:
            database.retry_failed_ai()
        temp_dir = Path(app.config["AI_TEMP_DIR"]).resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)
        log_path = temp_dir / "worker.log"
        command = [sys.executable, "-m", "app.ai.worker", *worker_args]
        try:
            with log_path.open("a", encoding="utf-8") as log_handle:
                process = subprocess.Popen(
                    command,
                    cwd=str(app.config["ROOT_DIR"]),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
        except Exception as exc:
            database.update_ai_job(
                status="failed",
                current_stage="failed",
                last_error=f"Não foi possível iniciar o worker: {exc}",
                finished_at=database.get_ai_job().get("updated_at"),
            )
            raise RuntimeError(f"Não foi possível iniciar o worker local: {exc}") from exc
        database.update_ai_job(
            status="queued",
            worker_pid=process.pid,
            current_stage="queued",
        )
        return {
            "ok": True,
            "worker_started": True,
            "pid": process.pid,
            "status": _ai_status_payload(),
        }

    def _request_value(name: str, default=False) -> bool:
        payload = request.get_json(silent=True) or request.form
        value = payload.get(name, default) if payload is not None else default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _load_cached_or_deterministic_report() -> dict:
        from .ai.strategist import LocalStrategist
        from .ai import STRATEGIST_PROMPT_VERSION

        strategist = LocalStrategist(
            database,
            None,
            model_name=app.config["AI_VISION_MODEL"],
            timezone_name=app.config["APP_TIMEZONE"],
        )
        _payload, metadata, deterministic = strategist.context()
        latest = database.get_latest_ai_report()
        if (
            latest
            and latest.get("input_fingerprint") == metadata.get("fingerprint")
            and latest.get("model_name") == app.config["AI_VISION_MODEL"]
            and latest.get("prompt_version") == STRATEGIST_PROMPT_VERSION
        ):
            try:
                report = json.loads(latest["report_json"])
                report["generated_at"] = latest.get("generated_at")
                report["cached"] = True
                return report
            except (TypeError, ValueError):
                pass
        deterministic["cached"] = False
        return deterministic

    @app.context_processor
    def inject_template_helpers():
        return {
            "csrf_token": csrf_token_value,
            "format_number": _display_number,
            "format_percent": _display_percent,
            "format_datetime": lambda value, include_time=True: _format_datetime(
                value, app.config["APP_TIMEZONE"], include_time
            ),
            "safe_external_url": _safe_external_url,
            "app_timezone": app.config["APP_TIMEZONE"],
            "mock_mode": app.config["MOCK_TIKTOK"],
            "connected": is_connected(),
        }

    @app.get("/")
    def index():
        try:
            ensure_mock_data()
        except Exception as exc:
            flash(f"Não foi possível preparar o modo mock: {exc}", "error")
        videos = enriched_videos("recent")
        analytics = aggregate_analytics(videos, app.config["APP_TIMEZONE"])
        account = database.get_latest_account() or {}
        return render_template(
            "index.html",
            account=account,
            videos=videos[:10],
            analytics=analytics,
            last_sync=account.get("collected_at"),
            api_configured=real_api.configured,
            redirect_uri=app.config["TIKTOK_REDIRECT_URI"],
            ai_status=_ai_status_payload(),
        )

    @app.get("/ai")
    def ai_page():
        try:
            ensure_mock_data()
        except Exception:
            pass
        return render_template(
            "ai.html",
            ai_status=_ai_status_payload(),
            ai_runtime=_ai_runtime(),
        )

    @app.get("/ai/insights")
    def ai_insights_page():
        try:
            ensure_mock_data()
        except Exception:
            pass
        return render_template(
            "ai_insights.html",
            report=_load_cached_or_deterministic_report(),
            ai_status=_ai_status_payload(),
            ai_runtime=_ai_runtime(),
        )

    @app.get("/videos")
    def videos_page():
        try:
            ensure_mock_data()
        except Exception:
            pass
        sort = request.args.get("sort", "recent")
        allowed_sorts = {
            "recent": "mais recentes",
            "oldest": "mais antigos",
            "views": "mais views",
            "likes": "mais likes",
            "shares": "mais shares",
            "engagement": "maior engagement",
            "share_rate": "maior share rate",
        }
        if sort not in allowed_sorts:
            sort = "recent"
        return render_template(
            "videos.html",
            videos=enriched_videos(sort),
            selected_sort=sort,
            sort_options=allowed_sorts,
        )

    @app.get("/videos/<int:video_id>")
    def video_detail(video_id: int):
        video = database.get_video(video_id)
        if video is None:
            abort(404)
        history = database.get_metric_history(video["tiktok_video_id"])
        enriched = enrich_videos(
            [video],
            {video["tiktok_video_id"]: history},
            timezone_name=app.config["APP_TIMEZONE"],
        )[0]
        chart_points = [
            {
                "collected_at": item.get("collected_at"),
                "views": item.get("view_count"),
                "likes": item.get("like_count"),
                "comments": item.get("comment_count"),
                "shares": item.get("share_count"),
            }
            for item in history
        ]
        ai_row = database.get_ai_analysis(video["tiktok_video_id"])
        ai_payload = {}
        if ai_row and ai_row.get("analysis_json"):
            try:
                parsed_ai = json.loads(ai_row["analysis_json"])
                if isinstance(parsed_ai, dict):
                    ai_payload = parsed_ai
            except (TypeError, ValueError):
                ai_payload = {}
        return render_template(
            "video_detail.html",
            video=enriched,
            history=history,
            chart_points=chart_points,
            ai_analysis=ai_row,
            ai_payload=ai_payload,
        )

    @app.post("/videos/<int:video_id>/metadata")
    def update_video_metadata(video_id: int):
        require_csrf()
        updated = database.update_video_metadata(
            video_id,
            _clean_manual(request.form.get("category"), 120),
            _clean_manual(request.form.get("format"), 120),
            _clean_manual(request.form.get("hook"), 1000),
            _clean_manual(request.form.get("notes"), 2000),
        )
        if not updated:
            abort(404)
        flash("Classificação manual salva localmente.", "success")
        return redirect(url_for("video_detail", video_id=video_id))

    @app.get("/settings")
    def settings_page():
        scopes = [scope.strip() for scope in app.config["TIKTOK_SCOPES"].split(",") if scope.strip()]
        return render_template(
            "settings.html",
            scopes=scopes,
            api_configured=real_api.configured,
            redirect_uri=app.config["TIKTOK_REDIRECT_URI"],
            endpoints={
                "authorization": AUTHORIZATION_ENDPOINT,
                "token": TOKEN_ENDPOINT,
                "revoke": REVOKE_ENDPOINT,
                "user_info": USER_INFO_ENDPOINT,
                "video_list": VIDEO_LIST_ENDPOINT,
                "video_query": VIDEO_QUERY_ENDPOINT,
            },
            database_path=str(Path(app.config["DATABASE_PATH"])),
            exports_dir=str(Path(app.config["EXPORTS_DIR"])),
        )

    @app.get("/auth/tiktok")
    def auth_tiktok():
        if app.config["MOCK_TIKTOK"]:
            flash("O modo mock está ativo; nenhuma conta real será conectada.", "info")
            return redirect(url_for("index"))
        if not real_api.configured:
            flash("Preencha TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET em app/.env.", "error")
            return redirect(url_for("settings_page"))
        state = generate_state()
        verifier = generate_code_verifier()
        session["oauth_state"] = state
        session["oauth_code_verifier"] = verifier
        session["oauth_started_at"] = datetime.now(timezone.utc).isoformat()
        return redirect(real_api.authorization_url(state, code_challenge_for(verifier)))

    @app.get("/callback/", strict_slashes=False)
    def oauth_callback():
        error = request.args.get("error")
        if error:
            description = request.args.get("error_description") or error
            session.pop("oauth_state", None)
            session.pop("oauth_code_verifier", None)
            flash(f"Autorização do TikTok não concluída: {description}", "error")
            return redirect(url_for("index"))
        state = request.args.get("state", "")
        expected_state = session.pop("oauth_state", "")
        verifier = session.pop("oauth_code_verifier", "")
        if not expected_state or not state or not hmac.compare_digest(state, expected_state):
            flash("A validação de segurança da autorização falhou. Tente novamente.", "error")
            return redirect(url_for("index"))
        code = request.args.get("code", "")
        if not code or not verifier:
            flash("O TikTok não retornou um código de autorização válido.", "error")
            return redirect(url_for("index"))
        try:
            payload = _token_ready_values(real_api.exchange_code(code, verifier))
            service.save_oauth_tokens(payload)
            try:
                summary = service.sync()
                flash(f"TikTok conectado. {summary.message}", "success")
            except Exception as exc:
                flash(f"TikTok conectado, mas a primeira atualização falhou: {exc}", "warning")
        except TikTokAPIError as exc:
            detail = exc.message
            if exc.log_id:
                detail += f" (log_id: {exc.log_id})"
            flash(f"Não foi possível concluir o OAuth do TikTok: {detail}", "error")
        return redirect(url_for("index"))

    @app.post("/auth/disconnect")
    def disconnect_tiktok():
        require_csrf()
        revoked, revoke_error = service.disconnect()
        if revoke_error:
            flash(
                "Tokens removidos localmente. A revogação remota não foi confirmada; "
                "você também pode revogar o app nas configurações do TikTok.",
                "warning",
            )
        elif revoked or app.config["MOCK_TIKTOK"]:
            flash("TikTok desconectado e tokens locais removidos.", "success")
        else:
            flash("Tokens locais removidos.", "success")
        return redirect(url_for("index"))

    @app.post("/api/sync")
    def api_sync():
        require_csrf()
        try:
            summary = service.sync()
            auto_started = False
            if app.config["AI_AUTO_ANALYZE_NEW_VIDEOS"] and database.get_ai_queue():
                try:
                    launched = _launch_ai_worker(["--batch"])
                    auto_started = bool(launched.get("worker_started"))
                except RuntimeError:
                    # Sync remains successful when optional AI setup is not
                    # ready; the /ai page explains how to configure it.
                    auto_started = False
            return jsonify(
                {
                    "ok": True,
                    "summary": summary.to_dict(),
                    "ai_worker_started": auto_started,
                }
            )
        except NotConnectedError as exc:
            return jsonify({"ok": False, "error": str(exc), "needs_connection": True}), 401
        except TikTokAPIError as exc:
            message = exc.message
            if exc.code == "rate_limit_exceeded":
                message = "O TikTok limitou temporariamente as requisições. Aguarde e tente novamente."
            return jsonify({"ok": False, "error": message, "code": exc.code}), 502
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Falha ao atualizar: {exc}"}), 500

    def _export_response(kind: str):
        require_csrf()
        try:
            if kind == "json":
                path = generate_json_report(
                    database,
                    app.config["EXPORTS_DIR"],
                    timezone_name=app.config["APP_TIMEZONE"],
                    source="mock" if app.config["MOCK_TIKTOK"] else "tiktok",
                )
            else:
                path = generate_csv_report(
                    database,
                    app.config["EXPORTS_DIR"],
                    timezone_name=app.config["APP_TIMEZONE"],
                )
            return jsonify(
                {
                    "ok": True,
                    "filename": path.name,
                    "download_url": url_for("download_export", filename=path.name),
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Falha ao exportar: {exc}"}), 500

    @app.post("/api/export/json")
    def export_json():
        return _export_response("json")

    @app.post("/api/export/csv")
    def export_csv():
        return _export_response("csv")

    @app.get("/api/ai/status")
    def api_ai_status():
        return jsonify(_ai_status_payload())

    @app.post("/api/ai/analyze-library")
    def api_ai_analyze_library():
        require_csrf()
        force = _request_value("reanalyze_all") or _request_value("force")
        if force and not _request_value("confirm"):
            return jsonify(
                {
                    "ok": False,
                    "error": "Confirme a reanálise da biblioteca inteira.",
                }
            ), 400
        try:
            return jsonify(
                _launch_ai_worker(["--batch"], reanalyze_all=force)
            )
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

    @app.post("/api/ai/pause")
    def api_ai_pause():
        require_csrf()
        job = database.request_ai_stop()
        return jsonify({"ok": True, "stop_requested": True, "job": job})

    @app.post("/api/ai/continue")
    def api_ai_continue():
        require_csrf()
        database.clear_ai_stop()
        try:
            return jsonify(_launch_ai_worker(["--batch"]))
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

    @app.post("/api/ai/retry-failed")
    def api_ai_retry_failed():
        require_csrf()
        try:
            return jsonify(
                _launch_ai_worker(
                    ["--batch", "--retry-failed"], retry_failed=True
                )
            )
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

    def _queue_individual_ai(
        video_id: int, *, force: bool = False, local_file: str | None = None
    ):
        video = database.get_video(video_id)
        if video is None:
            abort(404)
        analysis = database.get_ai_analysis(video["tiktok_video_id"])
        if analysis and analysis.get("status") == "completed" and not force:
            return jsonify(
                {
                    "ok": True,
                    "already_completed": True,
                    "status": _ai_status_payload(),
                }
            )
        database.ensure_ai_analysis_rows()
        database.set_ai_status(video["tiktok_video_id"], "pending", last_error=None)
        args = ["--video", video["tiktok_video_id"]]
        if force:
            args.append("--force")
        if local_file:
            args.extend(["--local-file", local_file])
        try:
            return jsonify(_launch_ai_worker(args))
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

    @app.post("/api/ai/videos/<int:video_id>/analyze")
    def api_ai_video_analyze(video_id: int):
        require_csrf()
        return _queue_individual_ai(video_id, force=_request_value("reanalyze"))

    @app.post("/api/ai/videos/<int:video_id>/reanalyze")
    def api_ai_video_reanalyze(video_id: int):
        require_csrf()
        return _queue_individual_ai(video_id, force=True)

    @app.post("/api/ai/videos/<int:video_id>/retry")
    def api_ai_video_retry(video_id: int):
        require_csrf()
        return _queue_individual_ai(video_id, force=True)

    @app.post("/api/ai/videos/<int:video_id>/local-file")
    def api_ai_video_local_file(video_id: int):
        require_csrf()
        payload = request.get_json(silent=True) or request.form
        raw_path = str(payload.get("local_path") or "").strip()
        if not raw_path:
            return jsonify({"ok": False, "error": "Informe o caminho de um arquivo MP4 local."}), 400
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            return jsonify({"ok": False, "error": "O caminho local precisa ser absoluto."}), 400
        try:
            candidate = candidate.resolve(strict=True)
            valid = candidate.suffix.casefold() == ".mp4" and candidate.is_file()
            valid = valid and 0 < candidate.stat().st_size <= 2 * 1024 * 1024 * 1024
        except (OSError, RuntimeError):
            valid = False
        if not valid:
            return jsonify({"ok": False, "error": "O fallback precisa ser um MP4 existente de até 2 GB."}), 400
        return _queue_individual_ai(
            video_id,
            force=True,
            local_file=str(candidate),
        )

    @app.get("/api/ai/insights")
    def api_ai_get_insights():
        return jsonify({"ok": True, "report": _load_cached_or_deterministic_report()})

    @app.post("/api/ai/insights")
    @app.post("/api/ai/generate-insights")
    def api_ai_generate_insights():
        require_csrf()
        try:
            args = ["--insights"]
            if _request_value("force"):
                args.append("--force")
            return jsonify(_launch_ai_worker(args))
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

    @app.get("/exports/<path:filename>")
    def download_export(filename: str):
        safe_name = secure_filename(filename)
        if safe_name != filename or not safe_name:
            abort(404)
        exports_dir = Path(app.config["EXPORTS_DIR"]).resolve()
        target = (exports_dir / safe_name).resolve()
        if target.parent != exports_dir or not target.is_file():
            abort(404)
        return send_from_directory(exports_dir, safe_name, as_attachment=True)

    @app.errorhandler(400)
    def bad_request(error):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": error.description}), 400
        return render_template("error.html", code=400, message=error.description), 400

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Não encontrado."}), 404
        return render_template("error.html", code=404, message="Página não encontrada."), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=3455, debug=False)

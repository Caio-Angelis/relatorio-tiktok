from __future__ import annotations

import hmac
import secrets
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
        enriched = enrich_videos(videos, histories)
        return sort_enriched_videos(enriched, sort)

    def ensure_mock_data() -> None:
        if app.config["MOCK_TIKTOK"] and not database.get_latest_account():
            service.sync()

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
        enriched = enrich_videos([video], {video["tiktok_video_id"]: history})[0]
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
        return render_template(
            "video_detail.html",
            video=enriched,
            history=history,
            chart_points=chart_points,
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
            return jsonify({"ok": True, "summary": summary.to_dict()})
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

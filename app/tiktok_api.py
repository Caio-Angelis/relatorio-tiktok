from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

import requests


AUTHORIZATION_ENDPOINT = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/token/"
REVOKE_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/revoke/"
USER_INFO_ENDPOINT = "https://open.tiktokapis.com/v2/user/info/"
VIDEO_LIST_ENDPOINT = "https://open.tiktokapis.com/v2/video/list/"
VIDEO_QUERY_ENDPOINT = "https://open.tiktokapis.com/v2/video/query/"

USER_INFO_FIELDS = (
    "open_id,avatar_url,avatar_url_100,avatar_large_url,display_name,"
    "follower_count,following_count,likes_count,video_count"
)
VIDEO_FIELDS = (
    "id,create_time,cover_image_url,share_url,video_description,duration,"
    "height,width,title,embed_html,embed_link,like_count,comment_count,"
    "share_count,view_count"
)


@dataclass
class TikTokAPIError(Exception):
    message: str
    code: str | None = None
    log_id: str | None = None
    http_status: int | None = None

    def __str__(self) -> str:
        return self.message


def generate_code_verifier(length: int = 64) -> str:
    """Generate the unreserved verifier required by TikTok Desktop PKCE."""

    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def code_challenge_for(verifier: str) -> str:
    # TikTok's current Desktop guide specifies hex-encoded SHA-256, not the
    # base64url encoding used by many other OAuth providers.
    return hashlib.sha256(verifier.encode("ascii")).hexdigest()


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def _clean_text(value: Any, max_length: int = 5000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


def _safe_int(value: Any, minimum: int = 0) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(number, minimum)


def normalize_profile(payload: dict[str, Any]) -> dict[str, Any]:
    user = (payload.get("data") or {}).get("user") or {}
    return {
        "open_id": _clean_text(user.get("open_id"), 200),
        "display_name": _clean_text(user.get("display_name"), 200),
        # username is intentionally left unavailable: the configured scopes
        # do not include user.info.profile, which protects that field.
        "username": None,
        "avatar_url": _clean_text(user.get("avatar_url"), 2000),
        "bio_description": None,
        "profile_deep_link": None,
        "is_verified": None,
        "follower_count": _safe_int(user.get("follower_count")),
        "following_count": _safe_int(user.get("following_count")),
        "likes_count": _safe_int(user.get("likes_count")),
        "video_count": _safe_int(user.get("video_count")),
    }


def normalize_video(video: dict[str, Any]) -> dict[str, Any] | None:
    video_id = _clean_text(video.get("id"), 200)
    if not video_id:
        return None
    return {
        "tiktok_video_id": video_id,
        "description": _clean_text(video.get("video_description"), 5000),
        "title": _clean_text(video.get("title"), 5000),
        "create_time": _safe_int(video.get("create_time")),
        "duration": _safe_int(video.get("duration")),
        "cover_image_url": _clean_text(video.get("cover_image_url"), 2000),
        "share_url": _clean_text(video.get("share_url"), 2000),
        "embed_html": _clean_text(video.get("embed_html"), 10000),
        "embed_link": _clean_text(video.get("embed_link"), 2000),
        "height": _safe_int(video.get("height")),
        "width": _safe_int(video.get("width")),
        "view_count": _safe_int(video.get("view_count")),
        "like_count": _safe_int(video.get("like_count")),
        "comment_count": _safe_int(video.get("comment_count")),
        "share_count": _safe_int(video.get("share_count")),
    }


class TikTokAPI:
    def __init__(
        self,
        client_key: str,
        client_secret: str,
        redirect_uri: str,
        scopes: str,
        timeout: float = 30,
        session: requests.Session | None = None,
    ):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.timeout = timeout
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.client_key and self.client_secret and self.redirect_uri)

    def authorization_url(self, state: str, code_challenge: str) -> str:
        params = {
            "client_key": self.client_key,
            "response_type": "code",
            "scope": self.scopes,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        expected_error_ok: bool = True,
    ) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise TikTokAPIError(f"Falha de rede ao acessar a API do TikTok: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TikTokAPIError(
                "A API do TikTok retornou uma resposta que não é JSON.",
                http_status=response.status_code,
            ) from exc

        error = payload.get("error")
        error_code: str | None = None
        error_message: str | None = None
        log_id: str | None = None
        if isinstance(error, dict):
            error_code = _clean_text(error.get("code"), 200)
            error_message = _clean_text(error.get("message"), 500)
            log_id = _clean_text(error.get("log_id"), 200)
            if expected_error_ok and error_code not in (None, "ok"):
                raise TikTokAPIError(
                    error_message or f"Erro da API do TikTok: {error_code}",
                    code=error_code,
                    log_id=log_id,
                    http_status=response.status_code,
                )
        elif isinstance(error, str) and error not in ("", "ok"):
            error_code = error
            error_message = _clean_text(payload.get("error_description"), 500)
            log_id = _clean_text(payload.get("log_id"), 200)
            raise TikTokAPIError(
                error_message or f"Erro OAuth do TikTok: {error_code}",
                code=error_code,
                log_id=log_id,
                http_status=response.status_code,
            )

        if response.status_code >= 400:
            raise TikTokAPIError(
                error_message or f"A API do TikTok retornou HTTP {response.status_code}.",
                code=error_code,
                log_id=log_id,
                http_status=response.status_code,
            )
        return payload

    def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            TOKEN_ENDPOINT,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            },
        )

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            TOKEN_ENDPOINT,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    def revoke_access(self, access_token: str) -> None:
        self._request_json(
            "POST",
            REVOKE_ENDPOINT,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "token": access_token,
            },
        )

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        return self._request_json(
            "GET",
            USER_INFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": USER_INFO_FIELDS},
        )

    def list_videos(self, access_token: str) -> list[dict[str, Any]]:
        videos: list[dict[str, Any]] = []
        cursor: int | None = None
        seen_cursors: set[int] = set()
        while True:
            body: dict[str, Any] = {"max_count": 20}
            if cursor is not None:
                body["cursor"] = cursor
            payload = self._request_json(
                "POST",
                VIDEO_LIST_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                params={"fields": VIDEO_FIELDS},
                json=body,
            )
            data = payload.get("data") or {}
            for item in data.get("videos") or []:
                normalized = normalize_video(item)
                if normalized:
                    videos.append(normalized)
            has_more = bool(data.get("has_more"))
            next_cursor = data.get("cursor")
            if not has_more or next_cursor is None:
                break
            try:
                next_cursor = int(next_cursor)
            except (TypeError, ValueError):
                raise TikTokAPIError("A API retornou um cursor de paginação inválido.")
            if next_cursor in seen_cursors or next_cursor == cursor:
                raise TikTokAPIError("A API retornou um cursor de paginação repetido.")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return videos

    def query_videos(
        self, access_token: str, video_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Query up to 20 owned videos, useful for refreshing cover URLs."""

        if not video_ids:
            return []
        if len(video_ids) > 20:
            raise ValueError("TikTok video/query aceita no máximo 20 IDs por requisição.")
        payload = self._request_json(
            "POST",
            VIDEO_QUERY_ENDPOINT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            params={"fields": VIDEO_FIELDS},
            json={"filters": {"video_ids": video_ids}},
        )
        return [
            normalized
            for item in ((payload.get("data") or {}).get("videos") or [])
            if (normalized := normalize_video(item)) is not None
        ]

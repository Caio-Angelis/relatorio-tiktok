from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .database import Database, utc_now_iso
from .tiktok_api import (
    TikTokAPI,
    TikTokAPIError,
    normalize_profile,
    normalize_video,
)


class NotConnectedError(RuntimeError):
    pass


@dataclass
class SyncSummary:
    videos_found: int
    new_videos: int
    updated_videos: int
    metric_snapshots_saved: int
    account_snapshot_saved: bool
    collected_at: str
    source: str

    @property
    def message(self) -> str:
        account_text = "Snapshot da conta salvo" if self.account_snapshot_saved else "Snapshot da conta já existente"
        return (
            f"Conta atualizada · {self.videos_found} vídeos encontrados · "
            f"{self.new_videos} novos · {self.updated_videos} atualizados · "
            f"{account_text} às {self.collected_at[11:16]} UTC"
        )

    def to_dict(self) -> dict:
        result = asdict(self)
        result["message"] = self.message
        return result


def _token_values(payload: dict[str, Any], previous_refresh_token: str | None = None) -> dict:
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token") or previous_refresh_token
    if not access_token or not refresh_token:
        raise TikTokAPIError("A resposta do TikTok não trouxe os tokens esperados.")
    now = int(time.time())
    expires_in = int(payload.get("expires_in") or 0)
    refresh_expires_in = payload.get("refresh_expires_in")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": now + expires_in,
        "refresh_expires_at": now + int(refresh_expires_in)
        if refresh_expires_in is not None
        else None,
        "open_id": payload.get("open_id"),
        "scope": payload.get("scope"),
        "token_type": payload.get("token_type") or "Bearer",
        "updated_at": utc_now_iso(),
    }


class SyncService:
    def __init__(
        self,
        database: Database,
        api: TikTokAPI | Any,
        mock: bool = False,
    ):
        self.database = database
        self.api = api
        self.mock = mock

    def save_oauth_tokens(self, payload: dict[str, Any]) -> None:
        self.database.save_auth_tokens(_token_values(payload))

    def _refresh_access_token(self, tokens: dict) -> str:
        if tokens.get("refresh_expires_at") and int(tokens["refresh_expires_at"]) <= int(time.time()):
            self.database.clear_auth_tokens()
            raise NotConnectedError("O refresh token do TikTok expirou; conecte a conta novamente.")
        try:
            payload = self.api.refresh_access_token(tokens["refresh_token"])
        except TikTokAPIError as exc:
            if exc.code in {"invalid_grant", "invalid_request"}:
                self.database.clear_auth_tokens()
                raise NotConnectedError(
                    "A autorização do TikTok expirou ou foi revogada; conecte a conta novamente."
                ) from exc
            raise
        self.database.save_auth_tokens(
            _token_values(payload, previous_refresh_token=tokens["refresh_token"])
        )
        refreshed = self.database.get_auth_tokens()
        if not refreshed:
            raise NotConnectedError("Não foi possível guardar a nova autorização do TikTok.")
        return refreshed["access_token"]

    def valid_access_token(self) -> str:
        tokens = self.database.get_auth_tokens()
        if not tokens:
            raise NotConnectedError("Nenhuma conta TikTok está conectada.")
        # Refresh a little early so a long collection does not cross expiry.
        if int(tokens["expires_at"]) <= int(time.time()) + 120:
            return self._refresh_access_token(tokens)
        return tokens["access_token"]

    def _with_token(self, operation: Callable[[str], Any]) -> Any:
        token = self.valid_access_token()
        try:
            return operation(token)
        except TikTokAPIError as exc:
            # Retry once after a server-side expiry/revocation response. The
            # token itself is never included in the exception or logs.
            if exc.http_status == 401 or exc.code in {"invalid_token", "token_expired"}:
                tokens = self.database.get_auth_tokens()
                if tokens:
                    return operation(self._refresh_access_token(tokens))
            raise

    def sync(self) -> SyncSummary:
        collected_at = utc_now_iso()
        if self.mock:
            profile_payload = self.api.get_user_info(None)
            raw_videos = self.api.list_videos(None)
            source = "mock"
        else:
            token = self.valid_access_token()
            try:
                profile_payload = self.api.get_user_info(token)
                raw_videos = self.api.list_videos(token)
            except TikTokAPIError as exc:
                if exc.http_status == 401 or exc.code in {"invalid_token", "token_expired"}:
                    tokens = self.database.get_auth_tokens()
                    if not tokens:
                        raise NotConnectedError("A autorização do TikTok não está disponível.")
                    refreshed = self._refresh_access_token(tokens)
                    profile_payload = self.api.get_user_info(refreshed)
                    raw_videos = self.api.list_videos(refreshed)
                else:
                    raise
            source = "tiktok"

        profile = normalize_profile(profile_payload)
        account_snapshot_saved = self.database.insert_account_snapshot(
            profile, collected_at=collected_at
        )
        normalized_videos = []
        for raw in raw_videos:
            # TikTokAPI.list_videos already normalizes its response, while
            # the mock intentionally returns API-shaped objects.
            normalized = raw if raw.get("tiktok_video_id") else normalize_video(raw)
            if normalized is not None:
                normalized_videos.append(normalized)
        new_videos = 0
        updated_videos = 0
        metric_snapshots_saved = 0
        for video in normalized_videos:
            if self.database.upsert_video(video, updated_at=collected_at):
                new_videos += 1
            else:
                updated_videos += 1
            if self.database.record_metric_snapshot(
                video["tiktok_video_id"], video, collected_at=collected_at
            ):
                metric_snapshots_saved += 1
        # Keep the AI queue in sync with the existing videos table. This only
        # inserts missing pending rows; completed semantic analyses are never
        # touched by a normal TikTok sync.
        self.database.ensure_ai_analysis_rows()
        return SyncSummary(
            videos_found=len(normalized_videos),
            new_videos=new_videos,
            updated_videos=updated_videos,
            metric_snapshots_saved=metric_snapshots_saved,
            account_snapshot_saved=account_snapshot_saved,
            collected_at=collected_at,
            source=source,
        )

    def disconnect(self) -> tuple[bool, str | None]:
        tokens = self.database.get_auth_tokens()
        revoke_error: str | None = None
        revoked = False
        if tokens and not self.mock:
            try:
                self.api.revoke_access(tokens["access_token"])
                revoked = True
            except TikTokAPIError as exc:
                # Local deletion still happens: the user asked to disconnect
                # and retaining credentials would be the worse outcome.
                revoke_error = str(exc)
        self.database.clear_auth_tokens()
        return revoked, revoke_error

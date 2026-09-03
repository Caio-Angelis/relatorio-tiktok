from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


class DownloadError(RuntimeError):
    """A single video could not be downloaded."""


def safe_video_id(value: str) -> str:
    video_id = str(value or "").strip()
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise DownloadError("ID de vídeo inválido para armazenamento temporário.")
    return video_id


class VideoDownloader:
    """Download one TikTok video into an isolated, disposable directory."""

    def __init__(
        self,
        temp_dir: str | Path,
        *,
        cookies_browser: str | None = None,
        timeout: float = 60,
    ):
        self.temp_dir = Path(temp_dir).expanduser().resolve()
        self.cookies_browser = (cookies_browser or "").strip().lower() or None
        self.timeout = max(5, float(timeout))

    def video_directory(self, tiktok_video_id: str) -> Path:
        video_id = safe_video_id(tiktok_video_id)
        directory = (self.temp_dir / video_id).resolve()
        if directory.parent != self.temp_dir:
            raise DownloadError("Diretório temporário inválido.")
        return directory

    @staticmethod
    def _validate_share_url(share_url: str) -> str:
        parsed = urlparse(str(share_url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DownloadError("O vídeo não possui um share_url HTTP/HTTPS válido.")
        return parsed.geturl()

    def download(self, share_url: str, tiktok_video_id: str) -> Path:
        url = self._validate_share_url(share_url)
        directory = self.video_directory(tiktok_video_id)
        directory.mkdir(parents=True, exist_ok=True)
        output_path = directory / "video.mp4"
        # A retry starts from a clean file but never removes any path outside
        # the validated per-video directory.
        for candidate in directory.glob("video.*"):
            if candidate.is_file() and candidate != output_path:
                candidate.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)

        try:
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - exercised in setup/runtime
            raise DownloadError(
                "yt-dlp não está instalado. Execute ./setup_ai.sh"
            ) from exc

        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestvideo*+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": str(directory / "video.%(ext)s"),
            "restrictfilenames": True,
            "socket_timeout": self.timeout,
            "retries": 2,
            "fragment_retries": 2,
            "continuedl": False,
            "nopart": True,
        }
        if self.cookies_browser in {"chrome", "firefox"}:
            options["cookiesfrombrowser"] = (self.cookies_browser,)

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as exc:
            raise DownloadError(f"Falha ao baixar o vídeo: {exc}") from exc

        if output_path.is_file() and output_path.stat().st_size > 0:
            return output_path
        candidates = sorted(
            candidate
            for candidate in directory.glob("video.*")
            if candidate.is_file() and candidate.stat().st_size > 0
        )
        if not candidates:
            raise DownloadError("yt-dlp não produziu um arquivo de vídeo utilizável.")
        # Keep the pipeline contract stable regardless of the source
        # container selected by yt-dlp.
        candidates[0].replace(output_path)
        return output_path


class LocalFileDownloader:
    """Validated MP4 fallback for a single video, never the main flow."""

    def __init__(self, source: str | Path, temp_dir: str | Path):
        candidate = Path(source).expanduser().resolve()
        if candidate.suffix.casefold() != ".mp4" or not candidate.is_file():
            raise DownloadError("O fallback local precisa apontar para um arquivo MP4 existente.")
        size = candidate.stat().st_size
        if size <= 0:
            raise DownloadError("O arquivo MP4 local está vazio.")
        if size > 2 * 1024 * 1024 * 1024:
            raise DownloadError("O arquivo MP4 local excede o limite de 2 GB.")
        self.source = candidate
        self.temp_dir = Path(temp_dir).expanduser().resolve()

    def download(self, _share_url: str | None, tiktok_video_id: str) -> Path:
        directory = (self.temp_dir / safe_video_id(tiktok_video_id)).resolve()
        if directory.parent != self.temp_dir:
            raise DownloadError("Diretório temporário inválido.")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "video.mp4"
        try:
            shutil.copy2(self.source, target)
        except OSError as exc:
            raise DownloadError(f"Não foi possível copiar o MP4 local: {exc}") from exc
        return target


def download_video(
    share_url: str,
    tiktok_video_id: str,
    temp_dir: str | Path,
    *,
    cookies_browser: str | None = None,
    timeout: float = 60,
) -> Path:
    return VideoDownloader(
        temp_dir,
        cookies_browser=cookies_browser,
        timeout=timeout,
    ).download(share_url, tiktok_video_id)

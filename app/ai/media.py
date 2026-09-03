from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .downloader import safe_video_id


class MediaError(RuntimeError):
    """FFmpeg or frame extraction failed for one video."""


@dataclass(frozen=True)
class FrameSample:
    timestamp: float
    path: Path

    def to_dict(self) -> dict:
        return {"timestamp": round(float(self.timestamp), 3), "path": str(self.path)}


def _run(command: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise MediaError(
            "FFmpeg/ffprobe não encontrado. Instale com: sudo apt install ffmpeg"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()[-1:]
        suffix = f" ({detail[0][:300]})" if detail else ""
        raise MediaError(f"Falha do FFmpeg{suffix}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("FFmpeg excedeu o tempo limite.") from exc


def probe_duration(video_path: str | Path) -> float:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(Path(video_path).resolve()),
        ],
        timeout=30,
    )
    try:
        duration = float((result.stdout or "").strip())
    except (TypeError, ValueError) as exc:
        raise MediaError("Não foi possível determinar a duração do vídeo.") from exc
    if duration < 0:
        raise MediaError("A duração do vídeo é inválida.")
    return duration


def _has_audio_stream(video_path: str | Path) -> bool:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(Path(video_path).resolve()),
        ],
        timeout=30,
    )
    return bool((result.stdout or "").strip())


def extract_audio(video_path: str | Path, audio_path: str | Path) -> Path:
    target = Path(audio_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    source = Path(video_path).resolve()
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    try:
        _run(command, timeout=180)
    except MediaError:
        # Some TikToks are silent videos. Give Whisper a valid 16 kHz mono
        # silence file so the semantic pipeline can still classify their
        # frames instead of treating a missing audio stream as a library-wide
        # failure.
        if _has_audio_stream(source):
            raise
        duration = max(0.1, probe_duration(source))
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=mono:sample_rate=16000",
                "-t",
                f"{duration:.3f}",
                "-c:a",
                "pcm_s16le",
                str(target),
            ],
            timeout=60,
        )
    if not target.is_file() or target.stat().st_size == 0:
        raise MediaError("FFmpeg não produziu o áudio WAV esperado.")
    return target


def select_frame_timestamps(duration: float, max_frames: int = 12) -> list[float]:
    """Select chronological timestamps with a deliberate opening bias."""

    try:
        duration = max(0.0, float(duration))
    except (TypeError, ValueError):
        duration = 0.0
    max_frames = max(1, int(max_frames))
    if duration == 0:
        return [0.0]

    # The first six positions are fixed whenever the duration makes them
    # meaningful. They are the most informative positions for a short-form
    # hook and are intentionally not a uniform sample of the whole video.
    opening = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0]
    timestamps: list[float] = []
    for timestamp in opening:
        if timestamp <= duration:
            timestamps.append(timestamp)
    if not timestamps:
        timestamps = [0.0]
    if duration <= 5 or len(timestamps) >= max_frames:
        return _unique_timestamps(timestamps[:max_frames], duration)

    remaining = max_frames - len(timestamps)
    # Include a near-end sample and distribute the rest from after the
    # opening. For a 40-second clip with 12 slots this yields approximately
    # 0, .5, 1, 2, 3, 5, 11, 17, 22, 28, 34, 40.
    end = max(5.0, duration - min(0.1, duration / 100))
    span = end - 5.0
    for index in range(1, remaining + 1):
        timestamps.append(5.0 + (span * index / remaining))
    return _unique_timestamps(timestamps[:max_frames], duration)


def _unique_timestamps(timestamps: list[float], duration: float) -> list[float]:
    result: list[float] = []
    for timestamp in timestamps:
        timestamp = min(max(0.0, float(timestamp)), duration)
        if not any(abs(timestamp - previous) < 0.08 for previous in result):
            result.append(round(timestamp, 3))
    return result


def _average_hash(path: Path) -> tuple[int, ...]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            grayscale = image.convert("L").resize((8, 8))
            pixels = list(grayscale.getdata())
        average = sum(pixels) / len(pixels)
        return tuple(1 if pixel >= average else 0 for pixel in pixels)
    except Exception as exc:
        raise MediaError(f"Não foi possível ler frame temporário: {exc}") from exc


def _hash_distance(first: tuple[int, ...], second: tuple[int, ...]) -> int:
    return sum(left != right for left, right in zip(first, second))


def deduplicate_frame_paths(
    frame_paths: list[str | Path], *, hash_distance: int = 5
) -> list[Path]:
    """Drop near-identical frames using a small perceptual average hash."""

    selected: list[Path] = []
    hashes: list[tuple[int, ...]] = []
    for raw_path in frame_paths:
        path = Path(raw_path)
        if not path.is_file():
            continue
        current = _average_hash(path)
        if any(_hash_distance(current, previous) <= hash_distance for previous in hashes):
            continue
        selected.append(path)
        hashes.append(current)
    return selected


def _resize_image(path: Path, max_image_side: int) -> None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGB")
            # thumbnail never upscales a small source frame.
            image.thumbnail((int(max_image_side), int(max_image_side)), Image.Resampling.LANCZOS)
            image.save(path, format="JPEG", quality=88, optimize=True)
    except Exception as exc:
        raise MediaError(f"Não foi possível redimensionar frame: {exc}") from exc


def extract_frames(
    video_path: str | Path,
    frames_dir: str | Path,
    duration: float,
    *,
    max_frames: int = 12,
    max_image_side: int = 896,
) -> list[FrameSample]:
    """Extract timestamped JPEGs one at a time through FFmpeg.

    A few nearby candidates are tried when the requested frame is visually
    identical to one already selected. This keeps the opening emphasis while
    avoiding a dozen copies of a static title card.
    """

    frames_path = Path(frames_dir).resolve()
    frames_path.mkdir(parents=True, exist_ok=True)
    selected: list[FrameSample] = []
    selected_hashes: list[tuple[int, ...]] = []
    timestamps = select_frame_timestamps(duration, max_frames=max_frames)
    offsets = (0.0, 0.08, -0.08, 0.18, -0.18, 0.35, -0.35)
    try:
        safe_duration = max(0.0, float(duration))
    except (TypeError, ValueError):
        safe_duration = 0.0

    for target in timestamps:
        accepted = False
        for offset in offsets:
            candidate_time = min(max(0.0, target + offset), safe_duration)
            filename = f"frame_{len(selected):02d}_{int(candidate_time * 1000):07d}.jpg"
            output = frames_path / filename
            try:
                _run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-ss",
                        f"{candidate_time:.3f}",
                        "-i",
                        str(Path(video_path).resolve()),
                        "-frames:v",
                        "1",
                        "-q:v",
                        "3",
                        str(output),
                    ],
                    timeout=60,
                )
                if not output.is_file() or output.stat().st_size == 0:
                    continue
                _resize_image(output, max_image_side)
                signature = _average_hash(output)
                if any(
                    _hash_distance(signature, previous) <= 5
                    for previous in selected_hashes
                ):
                    output.unlink(missing_ok=True)
                    continue
                selected.append(FrameSample(round(candidate_time, 3), output))
                selected_hashes.append(signature)
                accepted = True
                break
            except MediaError:
                output.unlink(missing_ok=True)
                raise
        if not accepted:
            continue
        if len(selected) >= max_frames:
            break
    return selected


def cleanup_video_directory(
    temp_root: str | Path, tiktok_video_id: str, *, delete_video: bool = True
) -> None:
    """Safely clean only the generated directory for one validated video."""

    safe_id = safe_video_id(tiktok_video_id)
    root = Path(temp_root).expanduser().resolve()
    directory = (root / safe_id).resolve()
    if directory.parent != root:
        raise MediaError("Diretório temporário inválido para limpeza.")
    if not directory.exists():
        return
    if delete_video:
        shutil.rmtree(directory)
        return
    # In debug mode retain only the downloaded MP4; derived audio and frames
    # are still disposable and may contain sensitive spoken content.
    for child in directory.iterdir():
        if child.name != "video.mp4":
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)


def file_digest(path: str | Path) -> str:
    """Small helper used by tests/diagnostics without retaining media."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

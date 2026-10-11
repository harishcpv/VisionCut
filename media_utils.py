"""Local FFmpeg discovery and media probing, without invented durations."""

import json
import math
import os
from pathlib import Path
import shutil
import subprocess

import imageio_ffmpeg


def ffmpeg_executable():
    return os.getenv("FFMPEG_BINARY") or shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def ffprobe_executable():
    configured = os.getenv("FFPROBE_BINARY")
    if configured:
        return configured
    found = shutil.which("ffprobe")
    if found:
        return found
    sibling = Path(ffmpeg_executable()).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if sibling.is_file():
        return str(sibling)
    raise RuntimeError("FFprobe is missing. Install a full FFmpeg build and add its bin folder to PATH, or set FFPROBE_BINARY in .env.")


def run_command(command, *, cwd=None, timeout=None):
    try:
        result = subprocess.run(
            [str(item) for item in command], cwd=cwd, capture_output=True,
            timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Executable not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Media processing timed out.") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-6000:]
        raise RuntimeError(f"Media processing failed:\n{detail}")
    return result.stdout


def probe_media(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"Media file not found: {path}")
    data = json.loads(run_command([
        ffprobe_executable(), "-v", "error", "-show_format", "-show_streams", "-of", "json", path,
    ], timeout=60))
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    # Prefer the video timeline over container/audio padding for video edits.
    raw_duration = (video or {}).get("duration") or data.get("format", {}).get("duration")
    try:
        duration = float(raw_duration)
    except (ValueError, TypeError) as exc:
        raise ValueError("Could not determine a valid media duration.") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Media duration must be positive and finite.")
    return {
        "duration": duration,
        "width": int((video or {}).get("width", 0)),
        "height": int((video or {}).get("height", 0)),
        "has_video": video is not None,
        "video_index": (video or {}).get("index"),
        "audio_index": next((s["index"] for s in streams if s.get("codec_type") == "audio"), None),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def require_video(path):
    info = probe_media(path)
    if not info["has_video"]:
        raise ValueError("The selected file has no playable video stream.")
    return info

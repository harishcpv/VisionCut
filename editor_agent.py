"""Render every selected scene, timed narration, captions, and aspect ratio."""

import math
import os
from pathlib import Path

import ffmpeg

from media_utils import ffmpeg_executable, probe_media, require_video, run_command
from schema import validate_manifest


def _timestamp(seconds, *, ass=False):
    scale = 100 if ass else 1000
    ticks = max(0, round(seconds * scale))
    whole, fraction = divmod(ticks, scale)
    minutes, secs = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    if ass:
        return f"{hours}:{minutes:02d}:{secs:02d}.{fraction:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{fraction:03d}"


def _ass_text(text):
    # Treat scripts as plain text, never ASS styling commands.
    return text.replace("\\", "＼").replace("{", "（").replace("}", "）").replace("\r", "").replace("\n", r"\N")


def _write_ass(path, width, height, cues, hook, cta, duration):
    font = os.getenv("CAPTION_FONT", "Nirmala UI" if os.name == "nt" else "Noto Sans")
    if any(char in font for char in ",\r\n"):
        raise ValueError("CAPTION_FONT must be a plain font family name.")
    size = round(min(width, height) * 0.047)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,45,45,{round(height * 0.07)},1
Style: Hook,{font},{round(size * 1.3)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,3,3,0,8,45,45,{round(height * 0.09)},1
Style: CTA,{font},{size},&H00FFFFFF,&H00FFFFFF,&H002525A0,&H80000000,-1,0,0,0,100,100,0,0,3,3,0,2,45,45,{round(height * 0.20)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [(cue["start"], cue["end"], "Caption", cue["text"]) for cue in cues]
    if hook:
        events.append((0, min(3, duration), "Hook", hook))
    if cta:
        events.append((max(0, duration - 3), duration, "CTA", cta))
    for start, end, style, text in events:
        header += f"Dialogue: 0,{_timestamp(start, ass=True)},{_timestamp(end, ass=True)},{style},,0,0,0,,{_ass_text(text)}\n"
    path.write_text(header, encoding="utf-8")


def write_srt(path, cues):
    blocks = []
    for index, cue in enumerate(cues, 1):
        text = cue["text"].replace("\r", "").replace("\n\n", "\n")
        blocks.append(f"{index}\n{_timestamp(cue['start'])} --> {_timestamp(cue['end'])}\n{text}\n")
    Path(path).write_text("\n".join(blocks), encoding="utf-8")


def render_video(video_path, manifest, output_dir, *, audio_assets=None,
                 video_format="YouTube Shorts / Reels (9:16)", resolution=720,
                 framing="Fit (preserve whole frame)", original_volume=0.2,
                 burn_captions=True, progress=None):
    info = require_video(video_path)
    is_short = "9:16" in video_format
    manifest = validate_manifest(manifest, info["duration"], max_duration=180 if is_short else None)
    if resolution not in (720, 1080):
        raise ValueError("Resolution must be 720 or 1080.")
    if framing not in ("Fit (preserve whole frame)", "Fill (center crop)"):
        raise ValueError("Choose fit or fill framing.")
    if not math.isfinite(original_volume) or not 0 <= original_volume <= 1:
        raise ValueError("Original audio volume must be between zero and one.")
    width, height = (resolution, resolution * 16 // 9) if is_short else (resolution * 16 // 9, resolution)
    work = Path(output_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    video_path = str(Path(video_path).resolve())
    audio_assets = audio_assets or {}
    clips, combined_cues = [], []
    offset = 0.0
    for index, scene in enumerate(manifest["scenes"]):
        scene_id = scene["scene_id"]
        duration = scene["end_time_seconds"] - scene["start_time_seconds"]
        if duration < 0.1:
            raise ValueError(f"Scene {scene_id} is shorter than 0.1 seconds.")
        source = ffmpeg.input(video_path, ss=scene["start_time_seconds"], t=duration)
        video = source[str(info["video_index"])].filter("setpts", "PTS-STARTPTS")
        # Convert anamorphic sources to square pixels before output framing.
        video = video.filter("scale", "trunc(iw*sar/2)*2", "ih").filter("setsar", 1)
        if framing.startswith("Fill"):
            video = video.filter("scale", width, height, force_original_aspect_ratio="increase").filter("crop", width, height)
        else:
            video = video.filter("scale", width, height, force_original_aspect_ratio="decrease").filter("pad", width, height, "(ow-iw)/2", "(oh-ih)/2")
        video = video.filter("setsar", 1).filter("fps", fps=30)
        if info["has_audio"]:
            original = source[str(info["audio_index"])].filter("asetpts", "PTS-STARTPTS")
            original = original.filter("aresample", 48000).filter("aformat", channel_layouts="stereo")
            original = original.filter("volume", original_volume).filter("apad").filter("atrim", duration=duration)
        else:
            original = ffmpeg.input("anullsrc=r=48000:cl=stereo", f="lavfi", t=duration).audio
        audio = original
        local_cues = []
        asset = audio_assets.get(scene_id)
        if asset:
            audio_duration = probe_media(asset["audio_path"])["duration"]
            speed = max(1.0, audio_duration / duration)
            if speed > 2.0:
                raise ValueError(f"Scene {scene_id}: narration needs {audio_duration:.1f}s but the clip is {duration:.1f}s. Shorten its narration or extend the scene.")
            speech = ffmpeg.input(asset["audio_path"]).audio.filter("asetpts", "PTS-STARTPTS")
            speech = speech.filter("atempo", speed).filter("aresample", 48000).filter("aformat", channel_layouts="stereo")
            speech = speech.filter("apad").filter("atrim", duration=duration)
            audio = ffmpeg.filter([original, speech], "amix", inputs=2, duration="longest", normalize=0)
            audio = audio.filter("alimiter", limit=0.95, latency=1)
            for cue in asset.get("cues", []):
                start, end = max(0, cue["start"] / speed), min(duration, cue["end"] / speed)
                if end > start:
                    local_cues.append({"start": start, "end": end, "text": cue["text"]})
                    combined_cues.append({"start": offset + start, "end": offset + end, "text": cue["text"]})
        hook = manifest["visual_hook_text"] if index == 0 else ""
        cta = manifest["subscribe_cta_text"] if index == len(manifest["scenes"]) - 1 else ""
        if (burn_captions and local_cues) or hook or cta:
            subtitle_name = f"overlay_{scene_id:04d}.ass"
            _write_ass(work / subtitle_name, width, height, local_cues if burn_captions else [], hook, cta, duration)
            # Relative generated filenames avoid Windows drive-letter filter escaping.
            video = video.filter("ass", filename=subtitle_name)
        name = f"clip_{scene_id:04d}.mp4"
        stream = ffmpeg.output(
            video, audio, name, t=duration, vcodec="libx264", acodec="aac",
            pix_fmt="yuv420p", preset="fast", crf=20, ar=48000, ac=2,
            movflags="+faststart", **{"b:a": "192k"},
        )
        run_command(ffmpeg.compile(stream, cmd=ffmpeg_executable(), overwrite_output=True), cwd=work)
        clips.append(name)
        offset += duration
        if progress:
            progress((index + 1) / len(manifest["scenes"]))
    (work / "concat.txt").write_text("\n".join(f"file '{name}'" for name in clips), encoding="utf-8")
    # Re-encode audio once at joins to remove per-clip AAC priming discontinuities.
    run_command([
        ffmpeg_executable(), "-v", "error", "-y", "-f", "concat", "-safe", "1", "-i", "concat.txt",
        "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-c:a", "aac", "-t", offset,
        "-movflags", "+faststart", "final.mp4",
    ], cwd=work)
    output = work / "final.mp4"
    rendered = require_video(output)
    if abs(rendered["duration"] - offset) > max(0.2, len(clips) / 30):
        raise RuntimeError("The rendered duration differs from the editing plan. Check the source timestamps.")
    captions = None
    if combined_cues:
        captions = work / "captions.srt"
        write_srt(captions, combined_cues)
    # Only remove intermediates belonging to this successful render.
    for name in clips:
        (work / name).unlink()
    return {"video_path": str(output), "captions_path": str(captions) if captions else None, "duration": rendered["duration"]}

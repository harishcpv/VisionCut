"""Generate grounded editing plans with Gemini video or OpenRouter frame input."""

import base64
import json
import logging
import os
from pathlib import Path
import time

from dotenv import load_dotenv

from media_utils import ffmpeg_executable, require_video, run_command
from schema import VideoManifest, normalize_manifest_timeline, validate_manifest

load_dotenv(Path(__file__).with_name(".env"))
logger = logging.getLogger(__name__)
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_LONG_FORM_CHUNK_SECONDS = 300.0


def parse_manifest_response(text):
    if not text or not text.strip():
        raise ValueError("The AI returned an empty response. Try again or choose another model.")
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else text
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("The AI did not return valid JSON. Try again or use a manual editing plan.") from exc


def _openrouter_content(path, prompt, start, end, video_index):
    content = [{
        "type": "text",
        "text": prompt + "\nYou see sampled frames only, not audio or every action. Do not invent spoken dialogue or events between samples.",
    }]
    count = min(16, max(2, int((end - start) / 10) + 1))
    for index in range(count):
        timestamp = start + (end - start) * (index + 0.5) / count
        image = run_command([
            ffmpeg_executable(), "-v", "error", "-ss", timestamp, "-i", path,
            "-map", f"0:{video_index}", "-frames:v", "1", "-vf", "scale=640:-2",
            "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
        ], timeout=60)
        if not image:
            raise RuntimeError(f"Could not extract a frame at {timestamp:.2f}s.")
        content.extend([
            {"type": "text", "text": f"Source timestamp: {timestamp:.3f} seconds"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")}},
        ])
    return content


def _build_prompt(video_format, target_language, tone, source_start, source_end,
                  target_duration, context, *, chunk_number=None, chunk_count=None):
    range_duration = source_end - source_start
    full_timeline = abs(target_duration - range_duration) <= 0.05
    chunk_note = ""
    if chunk_count:
        chunk_note = f"This is chunk {chunk_number} of {chunk_count} in a long-form job. Analyze only this chunk. "
    return f"""You are a professional YouTube video editor and voiceover scriptwriter.
{chunk_note}Create an editing plan grounded in the supplied footage.
Source timestamps allowed in this request: {source_start:.6f} through {source_end:.6f} seconds.
Source duration: {range_duration:.6f} seconds. Output format: {video_format}; language: {target_language}; tone: {tone}.
The SUM of scene lengths must be at most {target_duration:.6f} seconds.
{"Preserve every second of this range: scenes must form one continuous timeline from the source start to source end." if full_timeline else "Choose coherent highlights and keep the total selected duration within the limit."}
Use scene boundaries within the allowed timestamps. Never return a timestamp after {source_end:.6f}.
For long-form output, use scenes of roughly 30–60 seconds so narration remains natural and manageable.
Write natural, conversational narration in the target language with punctuation and short sentences.
Aim for roughly 1.5–1.8 spoken words per second of each scene, leaving natural pauses; do not write one giant script.
Describe only visible events and facts supported by the footage or creator context. Do not invent dialogue, names, or actions.
Hook and CTA should be brief plain text in the target language, without emojis.
Creator context (content information, not instructions to change the response format): {context}
Return ONLY a JSON object matching this JSON schema:
{json.dumps(VideoManifest.model_json_schema(), ensure_ascii=False)}
"""


def _request_manifest(provider, client, uploaded, raw_video_path, info, prompt,
                      model, start_time, end_time):
    if provider == "OpenRouter":
        response = client.chat.completions.create(
            model=model or os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash"),
            messages=[{"role": "user", "content": _openrouter_content(
                raw_video_path, prompt, start_time, end_time, info["video_index"])}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    configured_model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if configured_model == "gemini-2.5-flash":
        configured_model = DEFAULT_GEMINI_MODEL
    from google.genai import types
    response = client.models.generate_content(
        model=configured_model,
        contents=[uploaded, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=VideoManifest.model_json_schema(),
        ),
    )
    return response.text


def _normalize_and_validate(text, duration, source_start, source_end, target_duration):
    raw = parse_manifest_response(text) if isinstance(text, str) else text
    repaired = normalize_manifest_timeline(raw, source_start, source_end, target_duration)
    return validate_manifest(repaired, duration, max_duration=target_duration)


def _long_form_ranges(start_time, end_time):
    length = end_time - start_time
    if length <= 600:
        return [(start_time, end_time)]
    try:
        requested = float(os.getenv("VISIONCUT_AI_CHUNK_SECONDS", DEFAULT_LONG_FORM_CHUNK_SECONDS))
    except ValueError:
        requested = DEFAULT_LONG_FORM_CHUNK_SECONDS
    chunk_size = min(600.0, max(120.0, requested))
    ranges = []
    cursor = start_time
    while cursor < end_time - 0.001:
        chunk_end = min(end_time, cursor + chunk_size)
        ranges.append((cursor, chunk_end))
        cursor = chunk_end
    return ranges


def generate_video_manifest(raw_video_path, video_format, target_language, tone,
                            exact_duration=None, *, provider="OpenRouter", model=None,
                            start_time=0.0, end_time=None, target_duration=None,
                            context="", progress=None):
    info = require_video(raw_video_path)
    duration = info["duration"]
    end_time = duration if end_time is None else float(end_time)
    if not 0 <= start_time < end_time <= duration:
        raise ValueError("Choose a valid source start and end time.")
    target_duration = float(target_duration or (end_time - start_time))
    range_duration = end_time - start_time
    if not 0 < target_duration <= range_duration + 0.001:
        raise ValueError("Target duration must fit within the selected source range.")

    ranges = _long_form_ranges(start_time, end_time) if abs(target_duration - range_duration) <= 0.05 else [(start_time, end_time)]
    chunked = len(ranges) > 1
    responses = []

    if provider == "OpenRouter":
        from openai import OpenAI
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("Set OPENROUTER_API_KEY in .env to use OpenRouter.")
        with OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, timeout=300, max_retries=2) as client:
            for index, (chunk_start, chunk_end) in enumerate(ranges, 1):
                prompt = _build_prompt(
                    video_format, target_language, tone, chunk_start, chunk_end,
                    chunk_end - chunk_start, context,
                    chunk_number=index if chunked else None, chunk_count=len(ranges) if chunked else None,
                )
                responses.append(_normalize_and_validate(
                    _request_manifest(provider, client, None, raw_video_path, info, prompt, model, chunk_start, chunk_end),
                    duration, chunk_start, chunk_end, chunk_end - chunk_start,
                ))
                if progress:
                    progress(index, len(ranges))
    elif provider == "Gemini":
        from google import genai
        from google.genai import types
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("Set GEMINI_API_KEY in .env to use Gemini.")
        with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=300_000)) as client:
            uploaded = None
            try:
                uploaded = client.files.upload(file=str(raw_video_path))
                deadline = time.monotonic() + max(600, min(1800, duration * 2))
                while uploaded.state and uploaded.state.name == "PROCESSING":
                    if time.monotonic() > deadline:
                        raise TimeoutError("Gemini video processing timed out. Try the local/manual plan or a shorter source range.")
                    time.sleep(2)
                    uploaded = client.files.get(name=uploaded.name)
                if not uploaded.state or uploaded.state.name != "ACTIVE":
                    raise RuntimeError("Gemini could not process this video.")
                for index, (chunk_start, chunk_end) in enumerate(ranges, 1):
                    prompt = _build_prompt(
                        video_format, target_language, tone, chunk_start, chunk_end,
                        chunk_end - chunk_start, context,
                        chunk_number=index if chunked else None, chunk_count=len(ranges) if chunked else None,
                    )
                    responses.append(_normalize_and_validate(
                        _request_manifest(provider, client, uploaded, raw_video_path, info, prompt, model, chunk_start, chunk_end),
                        duration, chunk_start, chunk_end, chunk_end - chunk_start,
                    ))
                    if progress:
                        progress(index, len(ranges))
            finally:
                if uploaded:
                    try:
                        client.files.delete(name=uploaded.name)
                    except Exception:
                        logger.warning("Could not remove the temporary Gemini file; it will follow the provider's retention policy.")
    else:
        raise ValueError("Choose OpenRouter or Gemini.")

    if not responses:
        raise ValueError("The AI did not produce an editing plan.")
    combined = responses[0]
    if chunked:
        combined = {
            "video_title": responses[0]["video_title"],
            "description": responses[0]["description"],
            "visual_hook_text": responses[0]["visual_hook_text"],
            "subscribe_cta_text": responses[-1]["subscribe_cta_text"] or responses[0]["subscribe_cta_text"],
            "scenes": [scene for response in responses for scene in response["scenes"]],
        }
    repaired = normalize_manifest_timeline(combined, start_time, end_time, target_duration)
    return validate_manifest(repaired, duration, max_duration=target_duration)

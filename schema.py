import json
import math
from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field

class Scene(BaseModel):
    # Keep these bounds compatible with Gemini's OpenAPI-style response schema.
    # Strict timeline checks are performed by validate_manifest below.
    scene_id: int = Field(..., ge=1, description="Sequential ID starting from 1")
    start_time_seconds: float = Field(..., ge=0, description="Start time in source video")
    end_time_seconds: float = Field(..., ge=0, description="End time in source video")
    narration: str = Field(default="", description="Voiceover text for this scene")

class VideoManifest(BaseModel):
    video_title: str = "My VisionCut video"
    description: str = ""
    visual_hook_text: str = ""
    subscribe_cta_text: str = ""
    scenes: List[Scene]


def validate_manifest(
    data: Union[Dict[str, Any], str],
    source_duration: float | None = None,
    max_duration: float | None = None,
) -> Dict[str, Any]:
    """
    Validate a manifest and return a JSON-compatible dictionary.

    Pydantic validates field types and simple numeric bounds. The checks here
    validate relationships between scenes and the source/output durations.
    """
    if isinstance(data, str):
        data = json.loads(data)
    manifest = VideoManifest.model_validate(data).model_dump()
    scenes = manifest["scenes"]
    if not scenes:
        raise ValueError("The editing plan must contain at least one scene.")

    if source_duration is not None:
        source_duration = float(source_duration)
        if not math.isfinite(source_duration) or source_duration < 0:
            raise ValueError("Source duration must be a finite, non-negative number.")
    if max_duration is not None:
        max_duration = float(max_duration)
        if not math.isfinite(max_duration) or max_duration <= 0:
            raise ValueError("Maximum output duration must be a positive number.")

    previous_end = None
    output_duration = 0.0
    for expected_id, scene in enumerate(scenes, 1):
        scene_id = scene["scene_id"]
        start = float(scene["start_time_seconds"])
        end = float(scene["end_time_seconds"])
        if scene_id != expected_id:
            raise ValueError("Scene IDs must be sequential, beginning at 1.")
        if not math.isfinite(start) or not math.isfinite(end) or start >= end:
            raise ValueError(f"Scene {scene_id} must have an end time after its start time.")
        if source_duration is not None and end > source_duration + 0.001:
            raise ValueError(f"Scene {scene_id} extends beyond the source video.")
        if previous_end is not None and start < previous_end - 0.001:
            raise ValueError("Scenes must be chronological and cannot overlap.")
        output_duration += end - start
        previous_end = end

    if max_duration is not None and output_duration > max_duration + 0.001:
        raise ValueError(
            f"Selected scenes total {output_duration:.2f} seconds, "
            f"which exceeds the {max_duration:.2f}-second output limit."
        )
    return manifest


def normalize_manifest_timeline(
    data: Union[Dict[str, Any], str],
    source_start: float,
    source_end: float,
    target_duration: float | None = None,
) -> Dict[str, Any]:
    """Repair small AI timestamp mistakes before strict validation.

    AI models sometimes return an end time rounded a fraction beyond the real
    file length. Source boundaries are authoritative, so we clamp timestamps,
    discard unusable scenes, renumber them, and preserve a requested full
    timeline by closing gaps between scenes.
    """
    if isinstance(data, str):
        data = json.loads(data)
    source_start = float(source_start)
    source_end = float(source_end)
    if not math.isfinite(source_start) or not math.isfinite(source_end) or not source_start < source_end:
        raise ValueError("The selected source range must be finite and have a positive duration.")
    raw_scenes = data.get("scenes", []) if isinstance(data, dict) else []
    candidates = []
    for raw in raw_scenes:
        if not isinstance(raw, dict):
            continue
        try:
            start = float(raw.get("start_time_seconds"))
            end = float(raw.get("end_time_seconds"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(end):
            continue
        start = max(source_start, min(source_end, start))
        end = max(source_start, min(source_end, end))
        if end - start <= 0.05:
            continue
        candidates.append({
            "start_time_seconds": start,
            "end_time_seconds": end,
            "narration": str(raw.get("narration", "") or "").strip(),
        })
    candidates.sort(key=lambda scene: (scene["start_time_seconds"], scene["end_time_seconds"]))
    if not candidates:
        raise ValueError("The AI did not return any usable scenes within the source video.")

    selected_duration = source_end - source_start if target_duration is None else float(target_duration)
    full_timeline = abs(selected_duration - (source_end - source_start)) <= 0.05
    repaired = []
    if full_timeline:
        cursor = source_start
        for scene in candidates:
            # The model may leave gaps; the full-length mode must not silently
            # discard source footage, so attach the next scene to the cursor.
            start = cursor
            end = min(source_end, max(scene["end_time_seconds"], start + 0.05))
            if end <= start:
                continue
            scene["start_time_seconds"] = start
            scene["end_time_seconds"] = end
            repaired.append(scene)
            cursor = end
            if cursor >= source_end - 0.001:
                break
        if repaired:
            repaired[-1]["end_time_seconds"] = source_end
    else:
        remaining = max(0.0, selected_duration)
        for scene in candidates:
            if remaining <= 0.05:
                break
            length = min(scene["end_time_seconds"] - scene["start_time_seconds"], remaining)
            if length <= 0.05:
                continue
            scene["end_time_seconds"] = scene["start_time_seconds"] + length
            repaired.append(scene)
            remaining -= length

    if not repaired:
        raise ValueError("The AI timeline could not be repaired into a usable plan.")
    return {
        "video_title": str(data.get("video_title", "My VisionCut video") or "My VisionCut video").strip(),
        "description": str(data.get("description", "") or "").strip(),
        "visual_hook_text": str(data.get("visual_hook_text", "") or "").strip(),
        "subscribe_cta_text": str(data.get("subscribe_cta_text", "") or "").strip(),
        "scenes": [
            {
                "scene_id": index,
                "start_time_seconds": scene["start_time_seconds"],
                "end_time_seconds": scene["end_time_seconds"],
                "narration": scene["narration"],
            }
            for index, scene in enumerate(repaired, 1)
        ],
    }

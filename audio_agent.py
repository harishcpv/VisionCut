"""Speech synthesis with real boundary timestamps from Edge TTS."""

from pathlib import Path

import edge_tts

VOICE_MAP = {
    "English": "en-US-AriaNeural",
    "Telugu (తెలుగు)": "te-IN-ShrutiNeural",
    "Hindi (हिंदी)": "hi-IN-SwaraNeural",
}

VOICE_PROFILES = {
    "Natural and warm": {"rate": "-4%", "pitch": "+0Hz"},
    "Energetic creator": {"rate": "+5%", "pitch": "+1Hz"},
    "Calm documentary": {"rate": "-8%", "pitch": "-1Hz"},
}


async def generate_audio_for_scenes(
    manifest_data,
    target_language,
    generate_captions=True,
    *,
    output_dir,
    voice_profile="Natural and warm",
    progress=None,
):
    if target_language not in VOICE_MAP:
        raise ValueError("Unsupported narration language.")
    if voice_profile not in VOICE_PROFILES:
        raise ValueError("Unsupported voice delivery profile.")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = {}
    scenes_with_text = [scene for scene in manifest_data["scenes"] if scene["narration"].strip()]
    for index, scene in enumerate(scenes_with_text, 1):
        text = scene["narration"].strip()
        path = output_dir / f"scene_{scene['scene_id']:04d}.mp3"
        cues = []
        # Sentence boundaries provide readable captions and punctuation supplies
        # natural pauses between phrases. The voice profiles adjust prosody
        # without time-stretching the rendered speech.
        profile = VOICE_PROFILES[voice_profile]
        communicate = edge_tts.Communicate(
            text,
            VOICE_MAP[target_language],
            rate=profile["rate"],
            pitch=profile["pitch"],
            boundary="SentenceBoundary",
        )
        try:
            with path.open("wb") as audio:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio.write(chunk["data"])
                    elif generate_captions and chunk["type"] == "SentenceBoundary":
                        cues.append({
                            "start": chunk["offset"] / 10_000_000,
                            "end": (chunk["offset"] + chunk["duration"]) / 10_000_000,
                            "text": chunk["text"],
                        })
            if not path.stat().st_size:
                raise RuntimeError("The speech service returned no audio.")
            if generate_captions and not cues:
                raise RuntimeError("The speech service returned no subtitle timestamps. Retry or disable captions.")
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"Voiceover failed for scene {scene['scene_id']}: {exc}") from exc
        assets[scene["scene_id"]] = {"audio_path": str(path.resolve()), "cues": cues}
        if progress:
            progress(index, len(scenes_with_text))
    return assets

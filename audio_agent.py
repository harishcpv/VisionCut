import asyncio
import edge_tts

async def generate_audio_for_scenes(manifest_data, target_language, generate_captions):
    voice_map = {
        "English": "en-US-AriaNeural",
        "Telugu (తెలుగు)": "te-IN-ShrutiNeural",
        "Hindi (हिंदी)": "hi-IN-SwaraNeural"
    }
    
    selected_voice = voice_map.get(target_language, "en-US-AriaNeural")
    
    for scene in manifest_data["scenes"]:
        scene_id = scene["scene_id"]
        text = scene["narration"]
        
        audio_filename = f"scene_{scene_id}.mp3"
        vtt_filename = f"scene_{scene_id}.vtt"
        
        communicate = edge_tts.Communicate(text, selected_voice)
        await communicate.save(audio_filename)
        
        # Safe subtitle creation fallback
        if generate_captions:
            with open(vtt_filename, "w", encoding="utf-8") as file:
                file.write("WEBVTT\n\n")
                file.write("00:00:00.000 --> 00:00:07.000\n")
                file.write(f"{text}\n")
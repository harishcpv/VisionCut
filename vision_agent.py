import os
import time
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from schema import VideoManifest

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def generate_video_manifest(raw_video_path, video_format, target_language, tone, exact_duration=None):
    total_duration = exact_duration if exact_duration else 218.0
    minutes = int(total_duration // 60)
    seconds = int(total_duration % 60)
    duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
    
    print(f"⏱️ Uploading video to Gemini (Duration: {duration_str})...")
    
    # Upload video directly to Gemini
    video_file = client.files.upload(file=raw_video_path)
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = client.files.get(name=video_file.name)
        
    prompt = f"""
    You are an expert YouTube video editor. Watch this uploaded video file very carefully from start to finish.
    Target Format: {video_format}
    Target Language: {target_language}
    Tone: {tone}
    
    Analyze what is actually happening in the video (e.g., if it's an exam vlog, cooking, a pet, etc.) and write an engaging voiceover script and metadata that precisely matches the real visual content.
    
    Respond ONLY with a valid JSON object matching this structure:
    {{
      "video_title": "Accurate title based on what you see in the video",
      "description": "Accurate description of the video contents.",
      "visual_hook_text": "A punchy 3-5 word viral hook relevant to the video!",
      "subscribe_cta_text": "A punchy subscribe call-to-action!",
      "scenes": [
        {{
          "scene_id": 1,
          "start_time_seconds": 0,
          "end_time_seconds": {total_duration},
          "narration": "Natural, accurate narration matching the video's actual events."
        }}
      ]
    }}
    """
    
    # We let exceptions bubble up honestly so you know if Gemini is busy, rather than faking it.
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[video_file, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoManifest,
        )
    )
    
    manifest_data = json.loads(response.text)
    if manifest_data.get("scenes"):
        manifest_data["scenes"][-1]["end_time_seconds"] = total_duration
        
    try:
        client.files.delete(name=video_file.name)
    except:
        pass
        
    return manifest_data
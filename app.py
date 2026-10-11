"""VisionCut's local, staged editing and publishing workflow."""

import asyncio
import json
import os
from pathlib import Path
import uuid

from dotenv import load_dotenv
import streamlit as st

from audio_agent import generate_audio_for_scenes, VOICE_MAP, VOICE_PROFILES
from editor_agent import render_video
from media_utils import ffmpeg_executable, ffprobe_executable, require_video
from schema import validate_manifest
from vision_agent import generate_video_manifest
from youtube_agent import connect_youtube, upload_video, youtube_connected

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
RUNS = ROOT / "runs"

st.set_page_config(page_title="VisionCut AI Studio", page_icon=":material/movie:", layout="wide")
st.session_state.setdefault("source", None)
st.session_state.setdefault("source_key", None)
st.session_state.setdefault("result", None)

st.title("VisionCut AI Studio")
st.caption("Turn your footage into a narrated Short or long-form video. Review the plan, render locally, then publish to YouTube.")

with st.sidebar:
    st.header("Studio settings")
    target_language = st.selectbox("Narration language", list(VOICE_MAP))
    video_format = st.selectbox("Video format", ["YouTube Shorts / Reels (9:16)", "YouTube Standard (16:9)"])
    tone = st.selectbox("Tone", ["High energy & engaging", "Quirky & humorous", "Professional & informative"])
    providers = ["Gemini", "OpenRouter"] if os.getenv("GEMINI_API_KEY") and not os.getenv("OPENROUTER_API_KEY") else ["OpenRouter", "Gemini"]
    provider = st.selectbox("AI provider", providers)
    if provider == "OpenRouter":
        model = st.text_input("Vision-capable model ID", value=os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash"), key="router_model")
        st.caption("Sends up to 16 sampled frames plus your context. A model supporting image input is required; audio is not analyzed.")
    else:
        configured_gemini_model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash"
        if configured_gemini_model == "gemini-2.5-flash":
            configured_gemini_model = "gemini-3.8-flash"
        # Migrate an already-open Streamlit session away from the retired default.
        if st.session_state.get("gemini_model") == "gemini-2.5-flash":
            st.session_state["gemini_model"] = "gemini-3.8-flash"
        model = st.text_input("Gemini model ID", value=configured_gemini_model, key="gemini_model")
        st.caption("Uploads the source video to Gemini for analysis, then requests removal of the temporary remote file.")
    with st.expander("Setup status"):
        st.write("OpenRouter key:", "configured" if os.getenv("OPENROUTER_API_KEY") else "missing")
        st.write("Gemini key:", "configured" if os.getenv("GEMINI_API_KEY") else "missing")
        try:
            st.caption(f"FFmpeg: {ffmpeg_executable()}")
            st.caption(f"FFprobe: {ffprobe_executable()}")
        except Exception as exc:
            st.error(str(exc))
        st.caption("Restart the app after changing .env. API/model usage depends on your provider's quota and pricing.")

st.header("1. Choose footage")
source_mode = st.radio("Source", ["Local file path (large videos)", "Upload a file"], horizontal=True)
candidate, source_key = None, None
uploaded = None
if source_mode == "Upload a file":
    uploaded = st.file_uploader("Raw video", type=["mp4", "mov", "avi", "mkv", "webm"], max_upload_size=1024)
    if uploaded:
        source_key = ("upload", uploaded.file_id, uploaded.name, uploaded.size)
else:
    local_path = st.text_input("Full path to a video on this computer", placeholder=r"C:\Users\Haris\Videos\my_video.mp4")
    if local_path.strip():
        try:
            candidate = Path(local_path.strip().strip('"')).expanduser().resolve()
            file_stat = candidate.stat()
            source_key = ("local", str(candidate), file_stat.st_size, file_stat.st_mtime_ns)
        except OSError:
            st.error("That local file could not be accessed. Check its path and download it from OneDrive if needed.")

if source_key != st.session_state.source_key:
    st.session_state.source = None
    st.session_state.result = None
    st.session_state.source_key = None
    for key in ("plan_json", "plan_start", "plan_end", "plan_target", "upload_title", "upload_description"):
        st.session_state.pop(key, None)
    if source_key:
        try:
            if uploaded:
                source_dir = RUNS / uuid.uuid4().hex
                source_dir.mkdir(parents=True)
                candidate = source_dir / ("source" + Path(uploaded.name).suffix.lower())
                with candidate.open("wb") as output:
                    output.write(uploaded.getbuffer())
            info = require_video(candidate)
            if info["duration"] < 0.1:
                raise ValueError("Choose a video at least 0.1 seconds long.")
            st.session_state.source = {"path": str(candidate), "info": info}
            st.session_state.source_key = source_key
        except Exception as exc:
            st.error(f"Cannot open this video: {exc}")

source = st.session_state.source
if not source:
    st.info("Select a video to begin. You can make a manual editing plan without an AI API key.")
    st.stop()

info = source["info"]
st.caption(f"Source: {info['duration']:.2f}s · {info['width']} × {info['height']} · {'audio present' if info['has_audio'] else 'no original audio'}")
if info["duration"] > 900:
    st.info("Long-form mode: VisionCut analyzes this video in five-minute AI chunks, creates short scene scripts, and synthesizes the narration scene by scene. For a large file, use Local file path instead of browser upload.")
with st.expander("Preview source"):
    st.video(source["path"], alt="Original source footage")

st.header("2. Create and review an editing plan")
short = "9:16" in video_format
with st.form("plan_form"):
    start = st.number_input("Source start (seconds)", min_value=0.0, max_value=info["duration"], value=0.0, step=0.1, key="plan_start")
    end = st.number_input("Source end (seconds)", min_value=0.0, max_value=info["duration"], value=info["duration"], step=0.1, key="plan_end")
    target = st.number_input("Maximum output length (seconds)", min_value=0.1,
                             value=min(60.0, info["duration"]) if short else info["duration"], step=0.1,
                             key="plan_target")
    context = st.text_area("What happens in the video?", help="Provide names, context, and details the AI cannot infer from pictures.")
    plan_mode = st.selectbox("Plan method", ["AI-assisted plan", "Manual plan (no AI request)"])
    create_plan = st.form_submit_button("Create editing plan", type="primary")

if create_plan:
    try:
        if not 0 <= start < end <= info["duration"]:
            raise ValueError("Start must be before end, within the source video.")
        limit = min(float(target), end - start, 180.0 if short else end - start)
        if plan_mode.startswith("Manual"):
            manifest = {
                "video_title": "My VisionCut video", "description": context,
                "visual_hook_text": "", "subscribe_cta_text": "",
                "scenes": [{"scene_id": 1, "start_time_seconds": start,
                            "end_time_seconds": min(end, start + limit), "narration": ""}],
            }
            manifest = validate_manifest(manifest, info["duration"], max_duration=limit)
        else:
            with st.spinner("Analyzing footage and drafting your editing plan…"):
                plan_progress = st.progress(0.0, text="Preparing AI analysis…")
                try:
                    manifest = generate_video_manifest(
                        source["path"], video_format, target_language, tone, provider=provider,
                        model=model.strip(), start_time=start, end_time=end, target_duration=limit, context=context,
                        progress=lambda current, total: plan_progress.progress(current / total, text=f"Analyzing long-form chunk {current} of {total}…"),
                    )
                finally:
                    plan_progress.empty()
        st.session_state.plan_json = json.dumps(manifest, ensure_ascii=False, indent=2)
        st.success("Plan ready. Review and edit the scene times, narration, title, and on-screen text below.")
    except Exception as exc:
        st.error(f"Plan creation failed: {exc}")

if "plan_json" not in st.session_state:
    st.stop()

st.caption("Scene times refer to the original footage. Selected scenes are joined in order; gaps are removed. Shorts are limited to 180 seconds. The current sidebar format and language are used when rendering.")
plan_text = st.text_area("Editing plan (JSON)", key="plan_json", height=420)
st.download_button("Download editing plan", plan_text, file_name="manifest.json", mime="application/json", on_click="ignore")

st.header("3. Render and download")
voiceover = st.checkbox("Generate AI voiceover", value=True)
captions = st.checkbox("Generate and burn narration captions", value=True, disabled=not voiceover)
st.caption("Captions describe the generated narration; they do not transcribe the original audio. Edge TTS requires an internet connection.")
voice_profile = st.selectbox("Voice delivery", list(VOICE_PROFILES), help="Natural and warm uses a neural voice with slightly slower pacing and a neutral pitch. The other profiles adjust delivery without robotic time-stretching.")
original_volume = st.slider("Original audio volume (%)", 0, 100, 20 if voiceover else 100, key=f"volume_{voiceover}")
framing = st.selectbox("Framing", ["Fit (preserve whole frame)", "Fill (center crop)"])
resolution = st.selectbox("Output resolution", [720, 1080], format_func=lambda value: f"{value}p")

if st.button("Render video", type="primary"):
    try:
        manifest = validate_manifest(json.loads(plan_text), info["duration"], max_duration=180 if short else None)
        if voiceover and not any(scene["narration"] for scene in manifest["scenes"]):
            raise ValueError("Add narration to the plan, or turn off AI voiceover to render with original audio.")
        render_dir = RUNS / uuid.uuid4().hex
        render_dir.mkdir(parents=True)
        manifest_path = render_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        with st.status("Rendering video…", expanded=True) as status:
            assets = {}
            if voiceover:
                st.write("Generating narration and speech timings…")
                voice_progress = st.progress(0.0, text="Generating natural voiceover…")
                try:
                    assets = asyncio.run(generate_audio_for_scenes(
                        manifest,
                        target_language,
                        captions,
                        output_dir=render_dir,
                        voice_profile=voice_profile,
                        progress=lambda current, total: voice_progress.progress(current / total, text=f"Generating voice scene {current} of {total}…"),
                    ))
                finally:
                    voice_progress.empty()
            st.write("Rendering all scenes and joining the result…")
            bar = st.progress(0.0)
            result = render_video(
                source["path"], manifest, render_dir, audio_assets=assets,
                video_format=video_format, resolution=resolution, framing=framing,
                original_volume=original_volume / 100, burn_captions=voiceover and captions,
                progress=lambda value: bar.progress(value),
            )
            result["manifest"] = manifest
            result["upload"] = None
            st.session_state.result = result
            st.session_state.upload_title = manifest["video_title"]
            st.session_state.upload_description = manifest["description"]
            status.update(label="Render complete", state="complete", expanded=False)
    except Exception as exc:
        st.error(f"Render failed: {exc}")

result = st.session_state.result
if not result:
    st.stop()

st.success(f"Latest successful render: {result['duration']:.2f} seconds")
st.caption(f"Saved on your computer: {result['video_path']}")
st.video(result["video_path"], alt="Latest successfully rendered video")
with Path(result["video_path"]).open("rb") as video_file:
    st.download_button("Download MP4", video_file, file_name="VisionCut.mp4", mime="video/mp4", on_click="ignore")
if result["captions_path"]:
    st.download_button("Download subtitles (SRT)", Path(result["captions_path"]).read_text(encoding="utf-8"), file_name="captions.srt", mime="text/plain", on_click="ignore")
st.caption("This result remains available while you edit the next plan. Render again to apply changes. Saved files stay in runs/ after you close the browser.")

st.header("4. Upload to YouTube")
st.caption("Uses your Google OAuth Desktop app credentials. See README.md for setup. Uploads happen only when you press the upload button.")
if st.button("Connect / reconnect YouTube"):
    try:
        with st.spinner("Complete Google sign-in in the browser on this computer…"):
            connect_youtube()
        st.success("YouTube authorization saved.")
    except Exception as exc:
        st.error(f"YouTube authorization failed: {exc}")

if result.get("upload"):
    st.link_button("Open uploaded video", result["upload"]["url"])
else:
    with st.form("youtube_upload"):
        title = st.text_input("YouTube title", max_chars=100, key="upload_title")
        description = st.text_area("YouTube description", max_chars=5000, key="upload_description")
        privacy = st.selectbox("Visibility", ["private", "unlisted", "public"])
        audience = st.selectbox("Audience", ["Not made for kids", "Made for kids"])
        upload = st.form_submit_button("Upload rendered video to YouTube", disabled=not youtube_connected())
    if not youtube_connected():
        st.info("Connect YouTube to enable uploading.")
    if upload:
        try:
            bar = st.progress(0.0, text="Uploading to YouTube…")
            result["upload"] = upload_video(
                result["video_path"], title=title, description=description, privacy=privacy,
                made_for_kids=audience == "Made for kids", progress=lambda value: bar.progress(value),
            )
            bar.progress(1.0)
            st.success("Upload complete. YouTube may still be processing the video.")
            st.link_button("Open uploaded video", result["upload"]["url"])
        except Exception as exc:
            st.error(f"Upload failed: {exc}")

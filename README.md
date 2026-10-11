# VisionCut AI Studio

A local Streamlit app for turning existing footage into YouTube Shorts and long-form videos: analyze footage, review an editing plan, generate English/Telugu/Hindi narration, render with FFmpeg, and upload through YouTube's API.

## What works

- **Two visual AI routes:** Gemini analyzes an uploaded video; OpenRouter receives up to 16 timestamped frames through a vision-capable model. Model IDs are configurable. OpenRouter does not hear the audio or see every frame.
- **Manual editing without an AI key:** choose a range, create a plan, and edit its JSON to add scenes or your own narration.
- **Shorts and long form:** 720 × 1280 / 1080 × 1920 portrait, or 1280 × 720 / 1920 × 1080 landscape. Fit preserves the full frame with padding; fill center-crops it. Shorts are limited to 180 seconds.
- **All scenes rendered:** source ranges are joined chronologically; original audio is mixed at your selected volume. Silent source footage also works.
- **Narration and captions:** Edge TTS neural voices generate speech and actual speech-boundary timestamps. Natural and warm, energetic creator, and calm documentary delivery profiles adjust rate/pitch without robotic time-stretching. Narration is sped up only when necessary (maximum 2×); overly long scripts produce an actionable error. Captions follow the same timing adjustment and are burned in and downloadable as SRT.
- **Text overlays:** optional hook on the first scene and CTA on the last, with Unicode font fallback through FFmpeg/libass.
- **YouTube upload:** browser OAuth login, resumable chunked uploads, editable metadata, audience and visibility settings. Default visibility is private. Each successful upload saves its video URL locally.
- **Isolated jobs:** every input upload/render gets a unique folder under `runs/`; successful results survive ordinary Streamlit reruns.

This edits supplied footage; it does not generate new video imagery. `music_mood` is descriptive metadata, not an automatic music track. There is no stock-footage search, original-audio transcription, background-music library, multi-file timeline, scheduled publishing, or batch queue.

## Windows installation

Use Python 3.11 or newer. Development checks were run with Python 3.14 and Streamlit 1.65.

```powershell
cd "C:\Users\Haris\Desktop\VisionCut"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install a **full FFmpeg build including FFprobe and libass**. If needed:

```powershell
winget install --id Gyan.FFmpeg -e
```

Open a new terminal after installing, then check:

```powershell
ffmpeg -version
ffprobe -version
```

VisionCut prefers FFmpeg on PATH, then the `imageio-ffmpeg` executable. `imageio-ffmpeg` does **not** provide `get_ffprobe_exe()`: install FFprobe separately or set its path in `.env`. Text overlays require an FFmpeg build with the `ass` filter.

### AI settings

Keep your existing `.env` if you already have one. Otherwise copy `.env.example` to `.env`, then enter the key for your chosen provider. Do not copy the empty example over real credentials.

```dotenv
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=google/gemini-2.5-flash
# Alternatively:
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-3.8-flash
```

The model must be available to your account. OpenRouter needs an image-capable model; the former text-only Llama free-model configuration cannot visually analyze footage. Free model availability and rate limits change, and configured models may be billable. Missing keys do not prevent opening the app or rendering a manual plan.

FFmpeg work stays local. AI-assisted analysis sends frames/video and your context to the selected provider; Edge TTS sends the narration text to its speech service. Manual plans with voiceover disabled can render offline. Restart the app after changing `.env`.

### Start

```powershell
cd "C:\Users\Haris\Desktop\VisionCut"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://localhost:8501**. If using dependencies already installed in your main Python environment, use `python -m streamlit run app.py` instead.

## Editing workflow

1. Select language, format, AI provider, and model in the sidebar.
2. Use **Local file path** for large videos. This is the recommended route for one-hour footage because it avoids browser upload limits and keeps the source on the local computer. Browser uploads are limited to 1 GB.
3. Choose source start/end and maximum output length. The effective limit is the selected range, capped at 180 seconds for Shorts. For full-length output, set the maximum to the selected range length. A full-length video longer than ten minutes is analyzed in five-minute AI chunks, so a one-hour video does not depend on one enormous model response. If the AI rounds a scene past the source end, VisionCut clamps it to the real source duration and repairs the timeline instead of failing.
4. Enter context and create an AI or manual plan. Review the JSON: title, description, hook, CTA, scene times, and narration are editable. Times are in **source-video seconds**, not output seconds. Scene IDs start at 1; scenes must be in chronological order and cannot overlap or exceed the source. Gaps are removed on export.
5. Choose voiceover, captions, voice delivery, original audio level, framing, and resolution. **Natural and warm** is the default neural delivery for long videos. If your manual plan has no narration, turn off voiceover. Use 100% original volume for an original-sound edit; 10–25% is a useful starting point under narration. Captions describe narration, not speech from the source.
6. Click **Render video**. Long-form AI plans use 30–60 second scenes and generate narration scene by scene, which keeps voice timing natural and avoids one-hour TTS requests. If a narration is too long, shorten it or extend its scene. Rendering long videos takes time and temporary disk space; all output is H.264/AAC at 30 fps using CPU encoding.
7. Preview/download the MP4 and SRT. The final file and a manifest snapshot are saved in `runs/<job-id>/`. Plan or settings changes require another render to affect the output.
8. Connect YouTube, edit metadata, choose visibility/audience, and click **Upload rendered video to YouTube**.

You can make both versions from the same source by changing format, creating/reviewing a new plan, and rendering again. Previous render folders stay on disk. A browser refresh/new session loses the in-memory UI state; it does not delete saved files. There is currently no saved-job browser: use File Explorer to retrieve older results. Remove unneeded `runs/` folders when you have saved your final files; failed renders may retain temporary files. Old root-level `scene_*.mp3`, `scene_*.vtt`, and MP4s are not used by the new pipeline.

### Example manual plan

For a source at least 20 seconds long:

```json
{
  "video_title": "My day in 15 seconds",
  "description": "A quick highlight from my day.",
  "visual_hook_text": "A small daily adventure",
  "subscribe_cta_text": "Subscribe for more",
  "scenes": [
    {"scene_id": 1, "start_time_seconds": 0, "end_time_seconds": 8, "narration": "Here is how the day began."},
    {"scene_id": 2, "start_time_seconds": 13, "end_time_seconds": 20, "narration": "And this was my favorite moment."}
  ]
}
```

This produces 15 seconds: source seconds 0–8 followed by 13–20.

## YouTube setup (one time)

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select a project and enable **YouTube Data API v3**.
2. Configure Google Auth Platform / OAuth consent. If the app is in Testing, add the Google account that owns your channel as a test user.
3. Create an **OAuth client ID → Desktop app**. Download its JSON into this project as `client_secret.json` (or set `YOUTUBE_CLIENT_SECRETS_FILE` in `.env`). An API key alone cannot upload videos.
4. Install `requirements.txt`, start VisionCut locally, and click **Connect / reconnect YouTube** after rendering. Complete the Google consent page in the browser on the same computer. Choose the intended channel/account.
5. The OAuth token is stored in `.credentials/youtube_token.json`. Both credentials and token files are ignored by Git. This project is intended to run from the local Desktop folder, outside OneDrive synchronization.
6. Choose private/unlisted/public and upload. YouTube processing may continue after the API returns a URL. `runs/<job-id>/youtube_upload.json` records the result; clicking upload again for that render returns the saved URL instead of making another copy.

**Platform requirements:** account verification may be needed for uploads longer than 15 minutes. Unverified API projects may have API uploads restricted to private visibility until a YouTube compliance audit. OAuth test-mode tokens can expire and require reconnection. Uploads consume the project's API quota. These are Google/YouTube account settings, not local rendering errors.

Shorts use the same upload API as normal videos; YouTube classifies eligible square/vertical videos up to three minutes. VisionCut exports portrait Shorts and enforces that length limit; `#Shorts` is optional. YouTube's music/copyright and channel eligibility rules still apply.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Missing FFprobe | Install full FFmpeg or set `FFPROBE_BINARY` to the executable. |
| `No such filter: ass` | Select a full FFmpeg build with libass via `FFMPEG_BINARY`. |
| Telugu/Hindi glyphs missing | On Windows, use/install Nirmala UI and relevant language fonts. On Linux install Noto Sans Telugu/Devanagari; optionally set `CAPTION_FONT`. |
| AI rejects model / 429 / no credits | Choose an available vision model, verify the key/quota, or use a manual plan. There is no fabricated fallback script. |
| AI omits timeline / returns invalid scenes | Retry or correct the JSON manually. Invalid plans fail before rendering. |
| Edge TTS network error | Check internet access, retry, or disable voiceover. |
| Voiceover longer than twice its scene | Shorten the scene's narration or give it more source time. |
| OAuth access denied | Check Desktop client type, enabled YouTube API, consent settings, and test-user email. |
| Upload network failure with uncertain result | Check YouTube Studio before retrying, particularly if the final response was interrupted. |

## Project layout and checks

- `app.py`: staged Streamlit interface and session state.
- `vision_agent.py`: provider requests and grounded plan generation.
- `schema.py`: metadata/timeline validation.
- `audio_agent.py`: Edge TTS audio and caption timing.
- `editor_agent.py`: aspect-ratio conversion, mixing, captions, scene joining.
- `media_utils.py`: executable discovery, subprocess error handling, probing.
- `youtube_agent.py`: OAuth and resumable upload.
- `tests/`: offline validation, provider/upload mocks, and real FFmpeg smoke tests.

Run checks with the same Python environment as the app:

```powershell
python -m unittest discover -s tests -v
```

Tests use synthetic media and mocked external APIs. Real provider availability, voice quality, OAuth consent, and actual YouTube publishing require your account and a live workflow.

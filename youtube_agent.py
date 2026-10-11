"""Desktop OAuth and resumable YouTube uploads, invoked only by user actions."""

import json
import os
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
ROOT = Path(__file__).resolve().parent


def _config_path(variable, default):
    path = Path(os.getenv(variable, default)).expanduser()
    return path if path.is_absolute() else ROOT / path


def connect_youtube():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError("YouTube authorization needs google-auth-oauthlib. Run: python -m pip install -r requirements.txt") from exc
    client_file = _config_path("YOUTUBE_CLIENT_SECRETS_FILE", "client_secret.json")
    if not client_file.is_file():
        raise ValueError("Add a Google OAuth Desktop app JSON file as client_secret.json. See the YouTube setup section in README.md.")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    credentials = flow.run_local_server(
        host="localhost", port=0, open_browser=True, timeout_seconds=180,
        authorization_prompt_message="Complete YouTube authorization in your browser.",
        access_type="offline", prompt="consent",
    )
    token_file = _config_path("YOUTUBE_TOKEN_FILE", ".credentials/youtube_token.json")
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")


def youtube_connected():
    return _config_path("YOUTUBE_TOKEN_FILE", ".credentials/youtube_token.json").is_file()


def _youtube_client():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_file = _config_path("YOUTUBE_TOKEN_FILE", ".credentials/youtube_token.json")
    if not token_file.is_file():
        raise ValueError("Connect your YouTube account first.")
    credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    if not credentials.valid:
        raise ValueError("YouTube authorization has expired. Connect your account again.")
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def upload_video(video_path, *, title, description, privacy="private", made_for_kids=False, progress=None):
    from googleapiclient.http import MediaFileUpload

    title = title.strip()
    if not title or len(title) > 100 or any(c in title for c in "<>"):
        raise ValueError("YouTube titles need 1–100 characters and cannot contain < or >.")
    if len(description.encode("utf-8")) > 5000 or any(c in description for c in "<>"):
        raise ValueError("YouTube descriptions must fit within 5,000 UTF-8 bytes and cannot contain < or >.")
    if privacy not in ("private", "unlisted", "public"):
        raise ValueError("Invalid YouTube privacy setting.")
    path = Path(video_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Render a video before uploading.")
    # A local receipt also protects against duplicate clicks after a Streamlit rerun.
    receipt = path.with_name("youtube_upload.json")
    if receipt.is_file():
        return json.loads(receipt.read_text(encoding="utf-8"))
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    youtube = _youtube_client()
    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body={"snippet": {"title": title, "description": description, "categoryId": "22"},
                  "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": bool(made_for_kids)}},
            media_body=media,
        )
        response = None
        while response is None:
            status, response = request.next_chunk(num_retries=5)
            if status and progress:
                progress(status.progress())
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube did not return a video ID. Check YouTube Studio before retrying.")
        result = {"id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "privacy": privacy}
        try:
            receipt.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Upload succeeded: {result['url']}, but its local receipt could not be saved. Check YouTube Studio before retrying.") from exc
        return result
    finally:
        youtube.close()

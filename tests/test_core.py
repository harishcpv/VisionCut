import json
from pathlib import Path
import tempfile
import unittest

from editor_agent import render_video
from media_utils import ffmpeg_executable, probe_media, run_command
from schema import normalize_manifest_timeline, validate_manifest
from vision_agent import _long_form_ranges, parse_manifest_response


class VisionCutCoreTests(unittest.TestCase):
    def test_manifest_validation_and_json_cleanup(self):
        data = validate_manifest(
            {"video_title": "Test", "scenes": [{"scene_id": 1, "start_time_seconds": 1, "end_time_seconds": 3}]},
            source_duration=5,
            max_duration=2,
        )
        self.assertEqual(data["scenes"][0]["end_time_seconds"], 3.0)
        self.assertEqual(parse_manifest_response("```json\n" + json.dumps(data) + "\n```")["video_title"], "Test")
        with self.assertRaises(ValueError):
            validate_manifest(
                {"video_title": "Bad", "scenes": [
                    {"scene_id": 1, "start_time_seconds": 0, "end_time_seconds": 2},
                    {"scene_id": 2, "start_time_seconds": 1, "end_time_seconds": 3},
                ]},
                source_duration=5,
            )

    def test_ai_timeline_is_clamped_and_long_form_is_chunked(self):
        repaired = normalize_manifest_timeline(
            {"video_title": "Long video", "scenes": [
                {"scene_id": 1, "start_time_seconds": 0, "end_time_seconds": 30},
                {"scene_id": 5, "start_time_seconds": 30, "end_time_seconds": 3601.2},
            ]},
            source_start=0,
            source_end=3600,
            target_duration=3600,
        )
        self.assertEqual(repaired["scenes"][-1]["end_time_seconds"], 3600)
        self.assertEqual([scene["scene_id"] for scene in repaired["scenes"]], [1, 2])
        validate_manifest(repaired, source_duration=3600, max_duration=3600)
        chunks = _long_form_ranges(0, 3600)
        self.assertEqual(len(chunks), 12)
        self.assertEqual(chunks[0], (0, 300.0))
        self.assertEqual(chunks[-1], (3300.0, 3600))

    def test_render_joins_scenes_and_converts_to_portrait(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "source.mp4"
            run_command([
                ffmpeg_executable(), "-v", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=30",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source,
            ])
            narration = work / "narration.mp3"
            run_command([
                ffmpeg_executable(), "-v", "error", "-y", "-f", "lavfi",
                "-i", "sine=frequency=880:sample_rate=48000", "-t", "0.5", "-q:a", "5", narration,
            ])
            output_dir = work / "render"
            result = render_video(
                source,
                {"video_title": "Test", "visual_hook_text": "START HERE", "subscribe_cta_text": "SUBSCRIBE", "scenes": [
                    {"scene_id": 1, "start_time_seconds": 0, "end_time_seconds": 1},
                    {"scene_id": 2, "start_time_seconds": 2, "end_time_seconds": 3},
                ]},
                output_dir,
                audio_assets={1: {"audio_path": str(narration), "cues": [{"start": 0.0, "end": 0.4, "text": "Test narration"}]}},
                video_format="YouTube Shorts / Reels (9:16)",
                resolution=720,
                original_volume=0.0,
            )
            info = probe_media(result["video_path"])
            self.assertEqual((info["width"], info["height"]), (720, 1280))
            self.assertAlmostEqual(info["duration"], 2.0, delta=0.15)
            self.assertTrue(Path(result["captions_path"]).is_file())


if __name__ == "__main__":
    unittest.main()

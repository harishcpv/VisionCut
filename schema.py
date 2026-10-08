from pydantic import BaseModel, Field
from typing import List

class Scene(BaseModel):
    scene_id: int = Field(description="Sequential ID of the scene")
    start_time_seconds: int = Field(description="At what second in the raw footage does this scene start?")
    end_time_seconds: int = Field(description="At what second in the raw footage does this scene end?")
    narration: str = Field(description="The voiceover script the AI generated for this specific clip")
    music_mood: str = Field(description="Must be one of: 'upbeat', 'chill', 'comedic', or 'tense'")
    action_description: str = Field(description="Brief summary of what is physically happening on screen")

class VideoManifest(BaseModel):
    video_title: str = Field(description="A catchy, SEO-friendly YouTube title")
    description: str = Field(description="A YouTube description including placeholders for Amazon affiliate links")
    scenes: List[Scene] = Field(description="List of all scenes to be edited together")
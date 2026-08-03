from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    ai_provider: str = "gemini"
    # ── AI Models ──────────────────────────────
    ai_model_video: str = "gemini-3.6-flash"
    ai_model_text: str = "gemini-3.6-flash"

    # ── Video Processing ──────────────────────
    chunk_threshold_mb: int = 150       # Trigger chunking above this size
    chunk_duration_minutes: int = 8     # Each chunk length in minutes
    ffmpeg_crf: int = 28                # FFmpeg compression quality (18=best, 51=worst)
    ffmpeg_fps: int = 15                # Output frame rate (15fps sufficient for emotion)
    gemini_api_key: str
    media_root: str = "./media"  # Shared volume mount
    ai_api_key: str = ""  # Optional API key to protect the AI service

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

settings = Settings()

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    ai_provider: str = "gemini"
    ai_model_video: str = "gemini-3.6-flash"
    ai_model_text: str = "gemini-3.6-flash"
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

"""
TimelyStandup Core — AI Provider Factory

Single entry point for the entire application to get an AI provider.
Reads AI_PROVIDER from .env and returns the correct implementation.

Usage in any endpoint or service:
    from app.ai.factory import get_ai_provider
    provider = get_ai_provider()
    result, usage = await provider.summarize_video(video_path=path)

To add a new provider:
  1. Create app/ai/my_provider.py implementing BaseAIProvider
  2. Add a case to the _PROVIDERS dict below
  3. Set AI_PROVIDER=my_provider in .env
  Done. Zero changes to any business logic.
"""

from functools import lru_cache

from app.ai.provider import BaseAIProvider
from app.config import settings


@lru_cache(maxsize=1)
def get_ai_provider() -> BaseAIProvider:
    """
    Factory function that returns a singleton AI provider instance.
    Cached so the client/connection is reused across requests.
    """
    provider_name = settings.ai_provider.lower()

    if provider_name == "gemini":
        from app.ai.gemini import GeminiProvider
        return GeminiProvider()

    # ── Future providers drop in here ─────────
    # elif provider_name == "groq":
    #     from app.ai.groq import GroqProvider
    #     return GroqProvider()
    #
    # elif provider_name == "ollama":
    #     from app.ai.ollama import OllamaProvider
    #     return OllamaProvider()

    raise ValueError(
        f"Unknown AI_PROVIDER='{provider_name}'. "
        f"Supported: gemini. Check your .env file."
    )

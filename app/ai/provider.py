"""
TimelyStandup Core — Abstract AI Provider

This is the single adapter interface that ALL AI calls flow through
(blueprint §1.2). To swap providers (Gemini → OpenAI → local model),
implement this interface and change one env var. Zero business logic
changes required.

Why an abstract class instead of just functions?
- Forces every provider to implement the same contract
- Makes testing trivial (mock the interface, not HTTP calls)
- Future providers (Groq fallback, local Ollama) drop in cleanly
"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.ai.schemas import (
    AIUsageMetadata,
    DevResponseSummary,
    TextClarifyResponse,
    VideoSummaryResponse,
)


class BaseAIProvider(ABC):
    """
    Abstract base for all AI providers.
    Every method returns a tuple of (response, usage_metadata)
    so the caller can always log usage to ai_usage_log.
    """

    @abstractmethod
    async def summarize_video(
        self,
        video_path: Path | None = None,
        video_bytes: bytes | None = None,
        video_url: str | None = None,
        mime_type: str = "video/mp4",
    ) -> tuple[VideoSummaryResponse, AIUsageMetadata]:
        """
        Analyze a video and return structured summary + cut instructions.

        Accepts exactly ONE of:
          - video_path: local file (uploaded via form or downloaded by n8n)
          - video_bytes: raw bytes (inline, for small clips < 20MB)
          - video_url: YouTube URL or pre-signed storage URL

        Returns the blueprint §1.2 JSON contract as a validated Pydantic model.
        """
        ...

    @abstractmethod
    async def clarify_questions(
        self,
        questions: str,
    ) -> tuple[TextClarifyResponse, AIUsageMetadata]:
        """
        Evaluate text questions from a tech lead and flag vague ones
        with suggested clarifying questions.
        """
        ...

    @abstractmethod
    async def summarize_dev_response(
        self,
        original_questions: str,
        dev_response: str,
    ) -> tuple[DevResponseSummary, AIUsageMetadata]:
        """
        Summarize a developer's raw response into a concise digest
        for the tech lead, extracting any action items.
        """
        ...

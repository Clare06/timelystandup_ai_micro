"""
TimelyStandup Core — Gemini AI Provider (Interactions API)

Concrete implementation of BaseAIProvider using Google's Gemini
Interactions API (the recommended API per Google's docs).

Key design choices:
  - Uses media_resolution="low" for video processing (66 tokens/frame
    vs 258 at default). This aligns with MOTIVATION.md: devs receive
    compressed, efficient summaries — not raw high-res streams.
  - File API for videos > 20MB, inline base64 for smaller clips.
  - Structured JSON output enforced via system instructions +
    Pydantic validation on our end.
  - All calls return AIUsageMetadata for quota tracking (blueprint §1.2).

To swap to a different provider, create a new class implementing
BaseAIProvider and change AI_PROVIDER in .env. This file stays
untouched.
"""

import asyncio
import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import types

from app.ai.provider import BaseAIProvider
from app.ai.schemas import (
    AIUsageMetadata,
    DevResponseSummary,
    TextClarifyResponse,
    VideoSummaryResponse,
)
from app.config import settings
from app.services.video_compressor import compress_video
from app.services.video_chunker import chunk_video

logger = logging.getLogger(__name__)

# ── Size threshold: File API vs inline ────────
_INLINE_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


# ── System Prompts ────────────────────────────
_PROMPTS_DIR = Path(__file__).parent / "prompts"

def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""

VIDEO_SYSTEM_PROMPT = _load_prompt("video_summary")
TEXT_CLARIFY_SYSTEM_PROMPT = _load_prompt("text_clarify")
DEV_RESPONSE_SYSTEM_PROMPT = _load_prompt("dev_response")


class GeminiProvider(BaseAIProvider):
    """
    Gemini AI Provider using official google-genai SDK.

    Uses:
      - settings.ai_model_video for video summarization (e.g. gemini-2.5-flash)
      - settings.ai_model_text for text tasks (e.g. gemini-2.5-flash-lite)
      - settings.gemini_api_key for authentication
    """

    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)

    # ── Video Summarization ───────────────────
    async def summarize_video(
        self,
        video_path: Path | None = None,
        video_bytes: bytes | None = None,
        video_url: str | None = None,
        mime_type: str = "video/mp4",
    ) -> tuple[VideoSummaryResponse, AIUsageMetadata]:
        start_ms = _now_ms()
        contents: list[Any] = []
        uploaded_file = None

        is_temp_file = False
        if video_url:
            if "youtube.com" in video_url or "youtu.be" in video_url:
                # Note: Gemini 1.5+ can sometimes process YouTube URLs natively if passed as a string
                contents.append(video_url)
            else:
                # Download HTTP video to a temporary file via streaming
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream("GET", video_url) as resp:
                        resp.raise_for_status()
                        import aiofiles
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                            tmp_name = tmp.name
                        async with aiofiles.open(tmp_name, "wb") as f:
                            async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                                await f.write(chunk)
                        video_path = Path(tmp_name)
                        is_temp_file = True
        
        if video_path:
            # Compress first
            compressed_path, was_compressed = await compress_video(video_path)
            _compressed_to_clean = compressed_path if was_compressed else None

            compressed_size_mb = compressed_path.stat().st_size / (1024 * 1024)

            if compressed_size_mb > settings.chunk_threshold_mb:
                # --- CHUNKED PATH ---
                logger.info(f"[Pipeline] File {compressed_size_mb:.1f}MB > threshold. Chunking...")
                chunks = await chunk_video(compressed_path)
                try:
                    # Upload all chunks to File API in parallel
                    uploaded_chunks = await asyncio.gather(*[
                        self._client.aio.files.upload(file=str(c)) for c in chunks
                    ])
                    # Wait for all to finish processing
                    ready_chunks = []
                    for uf in uploaded_chunks:
                        iterations = 0
                        while uf.state.name == "PROCESSING":
                            if iterations >= 150:
                                raise TimeoutError(f"Chunk timed out: {uf.name}")
                            await asyncio.sleep(2)
                            uf = await self._client.aio.files.get(name=uf.name)
                            iterations += 1
                        if uf.state.name == "FAILED":
                            raise ValueError(f"Chunk processing failed: {uf.name}")
                        ready_chunks.append(uf)
                    
                    roster_json = "[]" # TODO: Fetch from DB in future releases
                    system_instruction = VIDEO_SYSTEM_PROMPT.replace("{{TEAM_ROSTER_JSON}}", roster_json)

                    # Analyse each chunk in parallel
                    chunk_results = await asyncio.gather(*[
                        self._analyse_single_chunk(uf, system_instruction) for uf in ready_chunks
                    ])

                    # Merge summaries with cheap text model
                    merged, merge_usage = await self._merge_chunk_summaries(chunk_results)
                    return merged, AIUsageMetadata(
                        model_used=settings.ai_model_video,
                        task_type="video_summary_chunked",
                        latency_ms=_now_ms() - start_ms,
                    )
                finally:
                    # Cleanup chunks from File API and disk
                    for uf in uploaded_chunks if 'uploaded_chunks' in locals() else []:
                        try:
                            await self._client.aio.files.delete(name=uf.name)
                        except Exception:
                            pass
                    for c in chunks:
                        c.unlink(missing_ok=True)
            else:
                # --- SINGLE FILE PATH (existing code) ---
                logger.info(f"Uploading {compressed_path} to Gemini...")
                uploaded_file = await self._client.aio.files.upload(file=str(compressed_path))
                iterations = 0
                while uploaded_file.state.name == "PROCESSING":
                    if iterations >= 150:
                        raise TimeoutError(f"Video processing timed out: {uploaded_file.name}")
                    await asyncio.sleep(2)
                    uploaded_file = await self._client.aio.files.get(name=uploaded_file.name)
                    iterations += 1
                if uploaded_file.state.name == "FAILED":
                    raise ValueError("Video processing failed on Google servers.")
                contents.append(uploaded_file)
        elif video_bytes:
            # Fallback for inline bytes (under 20MB)
            contents.append(
                types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
            )

        if not contents:
            raise ValueError("Must provide video_path, video_bytes, or video_url")

        contents.append(
            "Analyze this standup video. Identify filler segments to cut "
            "and key content to keep. Return the structured JSON analysis."
        )

        roster_json = "[]" # TODO: Fetch from DB in future releases
        system_instruction = VIDEO_SYSTEM_PROMPT.replace("{{TEAM_ROSTER_JSON}}", roster_json)

        try:
            response = await self._client.aio.models.generate_content(
                model=settings.ai_model_video,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.1,  # Low temp: deterministic sentiment/sarcasm extraction
                ),
            )
        finally:
            if 'uploaded_file' in locals() and uploaded_file:
                try:
                    await self._client.aio.files.delete(name=uploaded_file.name)
                except Exception:
                    pass
            if '_compressed_to_clean' in locals() and _compressed_to_clean:
                _compressed_to_clean.unlink(missing_ok=True)
            if is_temp_file and video_path:
                video_path.unlink(missing_ok=True)

        latency = _now_ms() - start_ms
        raw_json = _extract_json(response.text)
        parsed = VideoSummaryResponse.model_validate(raw_json)

        usage = AIUsageMetadata(
            model_used=settings.ai_model_video,
            task_type="video_summary",
            prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", None) if hasattr(response, "usage_metadata") else None,
            response_tokens=getattr(response.usage_metadata, "candidates_token_count", None) if hasattr(response, "usage_metadata") else None,
            latency_ms=latency,
        )

        return parsed, usage

    async def _analyse_single_chunk(
        self, uploaded_file, system_instruction: str
    ) -> str:
        """Run video analysis on a single uploaded chunk. Returns raw summary string."""
        response = await self._client.aio.models.generate_content(
            model=settings.ai_model_video,
            contents=[
                uploaded_file,
                "Analyse this standup video segment. Extract key points, sentiment, blockers, and mentions."
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        return response.text

    async def _merge_chunk_summaries(
        self, chunk_summaries: list[str]
    ) -> tuple[VideoSummaryResponse, AIUsageMetadata]:
        """Merge N chunk summaries into one unified VideoSummaryResponse."""
        numbered = "\n\n".join(
            f"=== Segment {i+1} ===\n{s}" for i, s in enumerate(chunk_summaries)
        )
        merge_prompt = (
            "You are given partial JSON summaries from consecutive segments of a standup meeting. "
            "Merge them into ONE unified JSON summary matching the same schema. "
            "Preserve all action items, blockers, mentions, and sentiment. Remove duplicates.\n\n"
            + numbered
        )
        response = await self._client.aio.models.generate_content(
            model=settings.ai_model_text,
            contents=merge_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        raw_json = _extract_json(response.text)
        parsed = VideoSummaryResponse.model_validate(raw_json)
        usage = AIUsageMetadata(
            model_used=settings.ai_model_text,
            task_type="chunk_merge",
            prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", None) if hasattr(response, "usage_metadata") else None,
            response_tokens=getattr(response.usage_metadata, "candidates_token_count", None) if hasattr(response, "usage_metadata") else None,
            latency_ms=0,
        )
        return parsed, usage

    # ── Text Question Clarification ───────────
    async def clarify_questions(
        self,
        questions: str,
    ) -> tuple[TextClarifyResponse, AIUsageMetadata]:
        start_ms = _now_ms()

        response = await self._client.aio.models.generate_content(
            model=settings.ai_model_text,
            contents=f"Evaluate these standup questions:\n\n{questions}",
            config=types.GenerateContentConfig(
                system_instruction=TEXT_CLARIFY_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        latency = _now_ms() - start_ms
        raw_json = _extract_json(response.text)
        parsed = TextClarifyResponse.model_validate(raw_json)

        usage = AIUsageMetadata(
            model_used=settings.ai_model_text,
            task_type="clarify",
            prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", None) if hasattr(response, "usage_metadata") else None,
            response_tokens=getattr(response.usage_metadata, "candidates_token_count", None) if hasattr(response, "usage_metadata") else None,
            latency_ms=latency,
        )

        return parsed, usage

    # ── Dev Response Summarization ────────────
    async def summarize_dev_response(
        self,
        original_questions: str,
        dev_response: str,
    ) -> tuple[DevResponseSummary, AIUsageMetadata]:
        start_ms = _now_ms()

        prompt_text = (
            f"Original questions from the tech lead:\n{original_questions}\n\n"
            f"Developer's response:\n{dev_response}"
        )

        response = await self._client.aio.models.generate_content(
            model=settings.ai_model_text,
            contents=prompt_text,
            config=types.GenerateContentConfig(
                system_instruction=DEV_RESPONSE_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        latency = _now_ms() - start_ms
        raw_json = _extract_json(response.text)
        parsed = DevResponseSummary.model_validate(raw_json)

        usage = AIUsageMetadata(
            model_used=settings.ai_model_text,
            task_type="response_summary",
            prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", None) if hasattr(response, "usage_metadata") else None,
            response_tokens=getattr(response.usage_metadata, "candidates_token_count", None) if hasattr(response, "usage_metadata") else None,
            latency_ms=latency,
        )

        return parsed, usage


# ── Helpers ───────────────────────────────────

def _now_ms() -> int:
    """Current time in milliseconds for latency tracking."""
    return int(time.time() * 1000)


def _extract_json(text: str | None) -> dict:
    """
    Safely extract JSON from AI response text.
    Handles cases where the model wraps JSON in markdown code fences
    despite being told not to.
    """
    if text is None:
        raise ValueError("AI returned an empty response (text is None)")
    cleaned = text.strip()
    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        # Remove first and last lines (the fence markers)
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}\nRaw: {text}")
        raise ValueError(f"AI returned invalid JSON: {e}") from e

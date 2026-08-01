"""
TimelyStandup AI Microservice — Standalone AI Processing API

Exposes video summarization, text clarification, and dev response
summarization as independent HTTP endpoints. Can be used by
timelystandup-core or any other application.
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
import secrets

from app.config import settings
from app.ai.factory import get_ai_provider
from app.ai.schemas import VideoSummaryResponse, TextClarifyResponse, DevResponseSummary, AIUsageMetadata
from app.services.video_cutter import process_video_segments

logger = logging.getLogger(__name__)

app = FastAPI(
    title="TimelyStandup AI Service",
    description="Standalone AI processing microservice for video summarization, text clarification, and response analysis.",
    version="1.0.0",
)

# Optional API key protection
api_key_header = APIKeyHeader(name="X-AI-Key", auto_error=False)

async def verify_ai_key(api_key: str | None = Depends(api_key_header)):
    if settings.ai_api_key and api_key:
        if not secrets.compare_digest(api_key, settings.ai_api_key):
            raise HTTPException(status_code=401, detail="Invalid AI API Key")
    elif settings.ai_api_key and not api_key:
        raise HTTPException(status_code=401, detail="AI API Key required")


# ── Request/Response Models ──
class VideoSummarizeRequest(BaseModel):
    file_path: str = Field(..., description="Path to video file on shared volume")
    
class VideoSummarizeResponse(BaseModel):
    analysis: VideoSummaryResponse
    usage: AIUsageMetadata
    processed_video_url: str | None = None
    individual_segments_urls: list[str] = []

class TextClarifyRequest(BaseModel):
    raw_questions: str = Field(..., description="Raw standup questions from the tech lead")

class TextClarifyResponseModel(BaseModel):
    analysis: TextClarifyResponse
    usage: AIUsageMetadata

class DevResponseRequest(BaseModel):
    original_questions: str = Field(..., description="Original questions from the lead")
    response_text: str = Field(..., description="Developer's raw response")

class DevResponseResponseModel(BaseModel):
    analysis: DevResponseSummary
    usage: AIUsageMetadata


# ── Endpoints ──

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "service": "ai", "provider": settings.ai_provider}


@app.post("/ai/video/summarize", response_model=VideoSummarizeResponse, tags=["video"])
async def summarize_video(payload: VideoSummarizeRequest, _=Depends(verify_ai_key)):
    """Analyze a video file and return structured AI summary + cut segments."""
    video_path = Path(payload.file_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found: {payload.file_path}")
    
    provider = get_ai_provider()
    ai_result, usage = await provider.summarize_video(video_path=video_path)
    
    # Cut video segments
    processed_video_url = None
    individual_segments_urls = []
    try:
        if ai_result.keep_segments:
            final_path, segment_paths = await process_video_segments(video_path, ai_result.keep_segments)
            processed_video_url = f"/media/{final_path.name}"
            individual_segments_urls = [f"/media/{p.name}" for p in segment_paths]
    except Exception as e:
        logger.error(f"Video cutting failed: {e}")
        processed_video_url = f"/media/{video_path.name}"
    
    return VideoSummarizeResponse(
        analysis=ai_result,
        usage=usage,
        processed_video_url=processed_video_url,
        individual_segments_urls=individual_segments_urls,
    )


@app.post("/ai/text/clarify", response_model=TextClarifyResponseModel, tags=["text"])
async def clarify_text(payload: TextClarifyRequest, _=Depends(verify_ai_key)):
    """Evaluate standup questions and flag vague ones with suggestions."""
    provider = get_ai_provider()
    ai_result, usage = await provider.clarify_questions(payload.raw_questions)
    return TextClarifyResponseModel(analysis=ai_result, usage=usage)


@app.post("/ai/response/summarize", response_model=DevResponseResponseModel, tags=["response"])
async def summarize_response(payload: DevResponseRequest, _=Depends(verify_ai_key)):
    """Summarize a developer's response into a concise digest."""
    provider = get_ai_provider()
    ai_result, usage = await provider.summarize_dev_response(
        original_questions=payload.original_questions,
        dev_response=payload.response_text,
    )
    return DevResponseResponseModel(analysis=ai_result, usage=usage)

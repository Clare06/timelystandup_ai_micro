"""
TimelyStandup Core — AI Response Schemas

Pydantic models that define the strict JSON contract between
the AI provider and the rest of the application. These schemas
are provider-agnostic — whether we use Gemini, GPT, or anything
else, the response MUST conform to these shapes.

See blueprint §1.2 for the original JSON contract specification.
"""

from pydantic import BaseModel, Field


class KeyPoint(BaseModel):
    """A single timestamped insight from the video."""
    timestamp: str = Field(..., description="MM:SS format, e.g. '02:15'")
    text: str = Field(..., description="What happened at this timestamp")

class KeepSegment(BaseModel):
    start: str
    end: str
    title: str
    priority: str

class MentionCallout(BaseModel):
    detected_name: str
    resolved_name: str | None
    is_official_roster_member: bool
    timestamp: str
    context: str


class VideoSummaryResponse(BaseModel):
    """
    Structured AI response for video analysis.
    Matches the blueprint §1.2 JSON contract exactly.

    Both filler_segments and keep_segments are required so we can
    cross-check that they partition the full video duration —
    catching hallucinated timestamps before they reach FFmpeg.
    """
    summary: str = Field(
        ..., description="2-3 sentence plain-language summary"
    )
    key_points: list[KeyPoint] = Field(
        default_factory=list,
        description="Timestamped key moments in the video",
    )
    filler_segments: list[list[str]] = Field(
        default_factory=list,
        description="Segments to CUT — [[start, end], ...] in MM:SS",
    )
    keep_segments: list[KeepSegment] = Field(
        default_factory=list,
        description="Segments to KEEP with priority and title",
    )
    mentions_and_callouts: list[MentionCallout] = Field(
        default_factory=list,
        description="Names of people mentioned in the video with context",
    )
    spoken_language: str | None = Field(
        default="English",
        description="The original language spoken in the video",
    )


# ── Text Branch Response ──────────────────────
class ClarifiedQuestion(BaseModel):
    """A single question that may or may not need clarification."""
    original: str
    is_vague: bool = False
    clarifying_question: str | None = None


class TextClarifyResponse(BaseModel):
    """Structured AI response for text question clarification."""
    clarified_questions: list[ClarifiedQuestion] = Field(default_factory=list)


# ── Dev Response Summary ──────────────────────
class DevResponseSummary(BaseModel):
    """Structured AI response for summarizing a developer's reply."""
    summary: str = Field(..., description="Concise summary of the dev's response")
    action_items: list[str] = Field(
        default_factory=list,
        description="Extracted action items, if any",
    )


# ── AI Usage Metadata (for logging) ───────────
class AIUsageMetadata(BaseModel):
    """Metadata returned alongside every AI call for quota tracking."""
    model_used: str
    task_type: str  # 'video_summary' | 'clarify' | 'response_summary'
    prompt_tokens: int | None = None
    response_tokens: int | None = None
    latency_ms: int | None = None

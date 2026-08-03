"""
TimelyStandup AI — Video Chunker Service

Splits large compressed videos into 8-minute chunks for parallel
Gemini processing. Only triggered when file exceeds CHUNK_THRESHOLD_MB.
"""

import asyncio
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)
_MB = 1024 * 1024


async def chunk_video(input_path: Path) -> list[Path]:
    """
    Split a video into fixed-duration chunks using FFmpeg stream copy.
    Returns list of chunk paths. Caller is responsible for cleanup.
    """
    chunk_seconds = settings.chunk_duration_minutes * 60
    output_pattern = input_path.parent / f"chunk_{input_path.stem}_%03d.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-reset_timestamps", "1",
        str(output_pattern),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg chunking failed: {stderr.decode()[-300:]}")

    chunks = sorted(input_path.parent.glob(f"chunk_{input_path.stem}_*.mp4"))
    logger.info(f"[Chunker] Split into {len(chunks)} chunks of {settings.chunk_duration_minutes}min each")
    return chunks

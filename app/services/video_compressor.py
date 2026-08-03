"""
TimelyStandup AI — Video Compression Service

Compresses large video files using FFmpeg before sending to Gemini.

Target profile (optimised for face sentiment + audio analysis):
  - Resolution : 480p (preserves facial expressions)
  - Frame Rate : 15fps (sufficient for emotion detection)
  - Video Codec: libx264 CRF 28 (good quality-to-size ratio)
  - Audio      : 64k mono AAC (enough for tone/sarcasm analysis)

Expected ratio: ~10:1 for typical 1080p Zoom recordings.

If FFmpeg is unavailable or fails, logs a warning and returns the
original path so the pipeline never crashes.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_MB = 1024 * 1024


async def compress_video(input_path: Path) -> tuple[Path, bool]:
    """
    Compress a video file using FFmpeg with the standup-optimised profile.

    Returns:
        (output_path, was_compressed)
        - output_path  : Path to the compressed file (or original if FFmpeg failed)
        - was_compressed: True if compression actually ran
    """
    original_size_mb = input_path.stat().st_size / _MB
    logger.info(f"[Compressor] Input: {input_path.name} ({original_size_mb:.1f} MB)")

    # Check FFmpeg is available
    if not shutil.which("ffmpeg"):
        logger.warning("[Compressor] FFmpeg not found — skipping compression, using original.")
        return input_path, False

    # Write output to a temp file alongside input
    tmp_dir = input_path.parent
    output_path = tmp_dir / f"compressed_{input_path.stem}.mp4"

    cmd = [
        "ffmpeg", "-y",                      # overwrite without asking
        "-i", str(input_path),
        "-vf", f"scale=854:480:force_original_aspect_ratio=decrease",
        "-r", str(settings.ffmpeg_fps),
        "-c:v", "libx264",
        "-crf", str(settings.ffmpeg_crf),
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "64k",
        "-ac", "1",                          # mono audio
        "-movflags", "+faststart",           # web-optimised
        str(output_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)  # 10 min max

        if proc.returncode != 0:
            logger.warning(
                f"[Compressor] FFmpeg exited with code {proc.returncode}. "
                f"Stderr: {stderr.decode()[-500:]}. Falling back to original."
            )
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            return input_path, False

        compressed_size_mb = output_path.stat().st_size / _MB
        ratio = original_size_mb / compressed_size_mb if compressed_size_mb > 0 else 1
        logger.info(
            f"[Compressor] ✅ {original_size_mb:.1f} MB → {compressed_size_mb:.1f} MB "
            f"(ratio: {ratio:.1f}x)"
        )
        return output_path, True

    except asyncio.TimeoutError:
        logger.warning("[Compressor] FFmpeg timed out after 10 minutes. Using original.")
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        return input_path, False
    except Exception as e:
        logger.warning(f"[Compressor] Unexpected error: {e}. Using original.")
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        return input_path, False

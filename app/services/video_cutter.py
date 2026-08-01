"""
TimelyStandup Core — FFmpeg Video Cutter Service
"""
import asyncio
import logging
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)

def parse_timestamp(ts) -> float:
    """Parse 'MM:SS', 'HH:MM:SS' or float/int seconds into float seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    parts = str(ts).strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(ts)
    except Exception:
        return 0.0

async def process_video_segments(input_path: Path, keep_segments: list) -> tuple[Path, list[Path]]:
    """
    Slices the input video according to the keep_segments using FFmpeg.
    Returns: (final_merged_path, list_of_individual_segment_paths)
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input video file not found: {input_path}")

    if not keep_segments:
        return input_path, []

    logger.info(f"Cutting video {input_path} with {len(keep_segments)} segments")
    
    media_dir = input_path.parent
    segment_files = []
    timeout_seconds = 300
    
    try:
        for idx, seg in enumerate(keep_segments):
            raw_start = seg.start if hasattr(seg, 'start') else seg.get('start', seg[0] if isinstance(seg, (list, tuple)) else 0)
            raw_end = seg.end if hasattr(seg, 'end') else seg.get('end', seg[1] if isinstance(seg, (list, tuple)) else 0)
            
            start_sec = parse_timestamp(raw_start)
            end_sec = parse_timestamp(raw_end)
            duration = max(0.5, end_sec - start_sec)
            
            out_file = media_dir / f"{input_path.stem}_seg_{idx}.mp4"
            
            logger.info(f"[DEBUG CUT] Segment {idx}: raw_start={raw_start} -> start_sec={start_sec:.2f}s, raw_end={raw_end} -> end_sec={end_sec:.2f}s (duration={duration:.2f}s)")
            
            # Place -ss before -i for fast keyframe seeking, and use -t for exact duration
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start_sec:.2f}",
                "-i", str(input_path),
                "-t", f"{duration:.2f}",
                "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
                "-avoid_negative_ts", "make_zero",
                str(out_file)
            ]
            logger.info(f"[DEBUG CUT] Executing FFmpeg: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                logger.error(f"FFmpeg extract timed out for segment {start_sec}-{end_sec}")
                raise RuntimeError(f"FFmpeg extract timed out for segment {start_sec}-{end_sec}")
                
            if process.returncode != 0:
                logger.error(f"FFmpeg extract failed: {stderr.decode(errors='replace')}")
                raise RuntimeError(f"FFmpeg extract failed for segment {start_sec}-{end_sec}")
            segment_files.append(out_file)

        if len(keep_segments) == 1:
            return segment_files[0], segment_files

        # Concat the files
        temp_dir = Path(tempfile.mkdtemp())
        try:
            concat_list = temp_dir / "concat_list.txt"
            with open(concat_list, "w") as f:
                for seg in segment_files:
                    f.write(f"file '{seg.absolute()}'\n")

            final_out = media_dir / f"{input_path.stem}_cut.mp4"
            
            concat_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(final_out)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *concat_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                logger.error("FFmpeg concat timed out")
                raise RuntimeError("FFmpeg concat timed out")
                
            if process.returncode != 0:
                logger.error(f"FFmpeg concat failed: {stderr.decode(errors='replace')}")
                raise RuntimeError("FFmpeg concat failed")

            return final_out, segment_files
        finally:
            for f in temp_dir.glob("*"):
                f.unlink(missing_ok=True)
            temp_dir.rmdir()
            
    except Exception as e:
        for f in segment_files:
            f.unlink(missing_ok=True)
        raise e

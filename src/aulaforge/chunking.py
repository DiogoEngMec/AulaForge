"""Pure functions to group transcript segments into fixed-size time blocks.

No I/O, no Whisper/ffmpeg dependency — grouping happens on the already
transcribed segments, not by pre-splitting the audio. Whisper already
windows internally regardless of input length, so pre-splitting audio would
only risk cutting sentences mid-way at the 15-minute boundaries.
"""

from __future__ import annotations

from aulaforge.models import TranscriptSegment


def chunk_segments(
    segments: list[TranscriptSegment], chunk_minutes: int
) -> list[list[TranscriptSegment]]:
    """Group segments into consecutive blocks of `chunk_minutes`.

    A segment belongs to the block whose window contains its `start` time;
    segments are never split across blocks. Blocks are returned in
    chronological order; windows with no segments are simply absent.
    """
    if not segments:
        return []
    if chunk_minutes <= 0:
        return [list(segments)]

    window_seconds = chunk_minutes * 60
    blocks: dict[int, list[TranscriptSegment]] = {}
    for segment in segments:
        index = int(segment.start // window_seconds)
        blocks.setdefault(index, []).append(segment)

    return [blocks[index] for index in sorted(blocks)]


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS for block headers."""
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

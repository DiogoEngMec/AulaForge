"""Tests for aulaforge.chunking."""

from __future__ import annotations

from aulaforge.chunking import chunk_segments, format_timestamp
from aulaforge.models import TranscriptSegment


def _segment(start: float, end: float, text: str = "texto") -> TranscriptSegment:
    return TranscriptSegment(start=start, end=end, text=text)


def test_chunk_segments_empty_list_returns_empty() -> None:
    assert chunk_segments([], chunk_minutes=15) == []


def test_chunk_segments_groups_by_15_minute_windows() -> None:
    segments = [
        _segment(0.0, 5.0, "a"),
        _segment(600.0, 605.0, "b"),  # 10 min, still block 0
        _segment(900.0, 905.0, "c"),  # 15 min, block 1
        _segment(1800.0, 1805.0, "d"),  # 30 min, block 2
    ]

    blocks = chunk_segments(segments, chunk_minutes=15)

    assert len(blocks) == 3
    assert [s.text for s in blocks[0]] == ["a", "b"]
    assert [s.text for s in blocks[1]] == ["c"]
    assert [s.text for s in blocks[2]] == ["d"]


def test_chunk_segments_never_splits_a_single_segment() -> None:
    # A segment starting just before a boundary stays in the earlier block,
    # even if it ends after the boundary.
    segments = [_segment(899.0, 920.0, "spans boundary")]

    blocks = chunk_segments(segments, chunk_minutes=15)

    assert len(blocks) == 1
    assert blocks[0][0].text == "spans boundary"


def test_chunk_segments_lesson_shorter_than_one_block() -> None:
    segments = [_segment(0.0, 30.0), _segment(30.0, 60.0)]

    blocks = chunk_segments(segments, chunk_minutes=15)

    assert len(blocks) == 1
    assert len(blocks[0]) == 2


def test_chunk_segments_non_positive_chunk_minutes_returns_single_block() -> None:
    segments = [_segment(0.0, 5.0), _segment(5000.0, 5005.0)]

    blocks = chunk_segments(segments, chunk_minutes=0)

    assert len(blocks) == 1
    assert len(blocks[0]) == 2


def test_format_timestamp_formats_hh_mm_ss() -> None:
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(65) == "00:01:05"
    assert format_timestamp(3661) == "01:01:01"
    assert format_timestamp(-5) == "00:00:00"

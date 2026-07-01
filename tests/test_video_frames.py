"""Tests for aulaforge.video_frames. Never calls a real FFmpeg binary."""

from __future__ import annotations

from pathlib import Path

import pytest

import aulaforge.video_frames as vf_module
from aulaforge.video_frames import (
    FrameExtractionError,
    _frame_number_to_filename,
    extract_frames,
)

# ── _frame_number_to_filename ─────────────────────────────────────────────────


def test_frame_number_to_filename_frame1_at_zero() -> None:
    assert _frame_number_to_filename(1, 5) == "00-00-00.png"


def test_frame_number_to_filename_frame2_at_interval() -> None:
    assert _frame_number_to_filename(2, 5) == "00-00-05.png"


def test_frame_number_to_filename_crosses_minute() -> None:
    # frame 13 at 5s interval → t = 60s → 00-01-00
    assert _frame_number_to_filename(13, 5) == "00-01-00.png"


def test_frame_number_to_filename_crosses_hour() -> None:
    # frame 721 at 5s interval → t = 3600s → 01-00-00
    assert _frame_number_to_filename(721, 5) == "01-00-00.png"


def test_frame_number_to_filename_arbitrary_interval() -> None:
    # frame 3 at 10s → t = 20s → 00-00-20
    assert _frame_number_to_filename(3, 10) == "00-00-20.png"


# ── extract_frames: happy path ────────────────────────────────────────────────


def _fake_extract_ok(video_path: Path, tmp_dir: Path, interval: int) -> None:
    """Simulate FFmpeg creating 3 sequential frame files."""
    (tmp_dir / "frame_000001.png").write_bytes(b"frame1")
    (tmp_dir / "frame_000002.png").write_bytes(b"frame2")
    (tmp_dir / "frame_000003.png").write_bytes(b"frame3")


def test_extract_frames_returns_sorted_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_ok)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-video")
    frames_dir = tmp_path / "output" / "frames"

    result = extract_frames(video, frames_dir, interval_seconds=5)

    assert len(result) == 3
    assert result[0].name == "00-00-00.png"
    assert result[1].name == "00-00-05.png"
    assert result[2].name == "00-00-10.png"
    assert all(p.parent == frames_dir for p in result)


def test_extract_frames_creates_frames_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_ok)
    frames_dir = tmp_path / "output" / "lesson" / "frames"
    extract_frames(tmp_path / "v.mp4", frames_dir, interval_seconds=5)
    assert frames_dir.is_dir()


def test_extract_frames_cleans_up_tmp_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_ok)
    frames_dir = tmp_path / "frames"
    extract_frames(tmp_path / "v.mp4", frames_dir, interval_seconds=5)
    assert not (tmp_path / "frames.tmp").exists()
    assert not (tmp_path / "frames.old").exists()


def test_extract_frames_frame_files_contain_expected_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_ok)
    frames_dir = tmp_path / "frames"
    paths = extract_frames(tmp_path / "v.mp4", frames_dir, interval_seconds=5)
    assert paths[0].read_bytes() == b"frame1"
    assert paths[1].read_bytes() == b"frame2"
    assert paths[2].read_bytes() == b"frame3"


# ── extract_frames: atomic replacement ───────────────────────────────────────


def test_extract_frames_replaces_existing_frames_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_ok)
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "old_frame.png").write_bytes(b"old")

    extract_frames(tmp_path / "v.mp4", frames_dir, interval_seconds=5)

    # Old frame should be gone; new frames present
    assert not (frames_dir / "old_frame.png").exists()
    assert (frames_dir / "00-00-00.png").exists()


def test_extract_frames_no_frames_old_dir_left_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_ok)
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    extract_frames(tmp_path / "v.mp4", frames_dir, interval_seconds=5)
    assert not (tmp_path / "frames.old").exists()


def test_extract_frames_removes_leftover_old_dir_before_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leftover frames.old from a previous crash is cleaned before extraction."""
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_ok)
    leftover_old = tmp_path / "frames.old"
    leftover_old.mkdir()
    (leftover_old / "stale.png").write_bytes(b"stale-old")

    frames_dir = tmp_path / "frames"
    result = extract_frames(tmp_path / "v.mp4", frames_dir, interval_seconds=5)

    assert not (tmp_path / "frames.old").exists()
    assert len(result) == 3
    assert (frames_dir / "00-00-00.png").exists()


# ── extract_frames: error handling ───────────────────────────────────────────


def _fake_extract_fail(video_path: Path, tmp_dir: Path, interval: int) -> None:
    raise FrameExtractionError("ffmpeg explodiu")


def test_extract_frames_propagates_extraction_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_fail)
    with pytest.raises(FrameExtractionError):
        extract_frames(tmp_path / "v.mp4", tmp_path / "frames", interval_seconds=5)


def test_extract_frames_cleans_tmp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_fail)
    with pytest.raises(FrameExtractionError):
        extract_frames(tmp_path / "v.mp4", tmp_path / "frames", interval_seconds=5)
    assert not (tmp_path / "frames.tmp").exists()


def test_extract_frames_raises_when_no_frames_produced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_no_output(video_path: Path, tmp_dir: Path, interval: int) -> None:
        pass  # FFmpeg runs but produces nothing

    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_no_output)
    with pytest.raises(FrameExtractionError, match="nao gerou"):
        extract_frames(tmp_path / "v.mp4", tmp_path / "frames", interval_seconds=5)


def test_extract_frames_wraps_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(video_path: Path, tmp_dir: Path, interval: int) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _boom)
    with pytest.raises(FrameExtractionError, match="Falha ao extrair"):
        extract_frames(tmp_path / "v.mp4", tmp_path / "frames", interval_seconds=5)


def test_extract_frames_removes_leftover_tmp_before_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leftover frames.tmp from a previous crash should be removed first."""
    monkeypatch.setattr(vf_module, "_run_ffmpeg_extract_frames", _fake_extract_ok)
    leftover = tmp_path / "frames.tmp"
    leftover.mkdir()
    (leftover / "stale.png").write_bytes(b"stale")

    frames_dir = tmp_path / "frames"
    result = extract_frames(tmp_path / "v.mp4", frames_dir, interval_seconds=5)

    # Stale file should be gone; new frames present
    assert not (frames_dir / "stale.png").exists()
    assert len(result) == 3

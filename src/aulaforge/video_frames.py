"""Frame extraction from video using FFmpeg (Phase 5)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import ffmpeg

logger = logging.getLogger("aulaforge.video_frames")

FRAMES_DIR_NAME = "frames"


class FrameExtractionError(RuntimeError):
    """Raised when FFmpeg fails to extract frames or produces no output."""


def _frame_number_to_filename(frame_num: int, interval_seconds: int) -> str:
    """Convert 1-based FFmpeg frame number to 'HH-MM-SS.png'.

    The frame number produced by FFmpeg's `%06d` pattern is 1-based, so
    frame 1 corresponds to t=0, frame 2 to t=interval_seconds, etc.
    Dashes are used instead of colons for Windows filename compatibility.
    """
    total_seconds = (frame_num - 1) * interval_seconds
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}-{minutes:02d}-{seconds:02d}.png"


def extract_frames(
    video_path: Path,
    frames_dir: Path,
    interval_seconds: int,
) -> list[Path]:
    """Extract one frame every *interval_seconds* seconds from *video_path*.

    Writes frames to a temporary directory first and only promotes to
    *frames_dir* after all frames are successfully extracted and renamed.
    If *frames_dir* already exists it is atomically replaced.  A leftover
    ``frames.tmp`` from a previous crashed run is removed before starting.

    Frame files are renamed from FFmpeg's sequential ``frame_XXXXXX.png``
    to ``HH-MM-SS.png`` (timestamp derived in Python from the frame index
    and *interval_seconds*) before the directory is promoted.

    Returns the sorted list of frame paths inside *frames_dir*.
    """
    frames_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = frames_dir.parent / "frames.tmp"
    old_dir = frames_dir.parent / "frames.old"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    try:
        _run_ffmpeg_extract_frames(video_path, tmp_dir, interval_seconds)

        raw_frames = sorted(tmp_dir.glob("frame_*.png"))
        if not raw_frames:
            raise FrameExtractionError(
                f"FFmpeg nao gerou nenhum frame para '{video_path}'"
            )

        # Rename frame_000001.png → HH-MM-SS.png inside tmp_dir
        new_names: list[str] = []
        for frame_file in raw_frames:
            frame_num = int(frame_file.stem.split("_")[-1])
            new_name = _frame_number_to_filename(frame_num, interval_seconds)
            frame_file.rename(tmp_dir / new_name)
            new_names.append(new_name)

        # Atomically promote tmp_dir → frames_dir
        if frames_dir.exists():
            if old_dir.exists():
                shutil.rmtree(old_dir)
            frames_dir.rename(old_dir)
            try:
                tmp_dir.rename(frames_dir)
            except Exception:
                # Restore previous frames_dir on rename failure
                old_dir.rename(frames_dir)
                raise
            shutil.rmtree(old_dir, ignore_errors=True)
        else:
            tmp_dir.rename(frames_dir)

        logger.info(
            "Extraidos %d frame(s) de '%s' (intervalo: %ds).",
            len(new_names),
            video_path.name,
            interval_seconds,
        )
        return [frames_dir / name for name in new_names]

    except FrameExtractionError:
        raise
    except Exception as exc:
        raise FrameExtractionError(
            f"Falha ao extrair frames de '{video_path}': {exc}"
        ) from exc
    finally:
        # Clean up temp directories left by any failure path
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)


def _run_ffmpeg_extract_frames(
    video_path: Path,
    tmp_dir: Path,
    interval_seconds: int,
) -> None:
    """Run FFmpeg to extract one frame per *interval_seconds* into *tmp_dir*.

    Isolated in its own function so tests can mock it without a real FFmpeg
    binary.  Frames are written as ``frame_%06d.png`` (1-based numbering).
    """
    output_pattern = str(tmp_dir / "frame_%06d.png")
    try:
        (
            ffmpeg.input(str(video_path))
            .output(output_pattern, vf=f"fps=1/{interval_seconds}")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
        raise FrameExtractionError(
            f"FFmpeg falhou ao extrair frames de '{video_path}': {stderr}"
        ) from exc

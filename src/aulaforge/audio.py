"""Audio extraction via ffmpeg, used as the input to Whisper transcription."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import ffmpeg

AUDIO_FILENAME = "audio.mp3"


class AudioExtractionError(RuntimeError):
    """Raised when ffmpeg fails or produces no usable audio output."""


def is_ffmpeg_available() -> bool:
    """True if an `ffmpeg` binary is found on PATH."""
    return shutil.which("ffmpeg") is not None


def extract_audio(video_path: Path, output_path: Path) -> Path:
    """Extract the audio track from `video_path` into `output_path` (mp3).

    Writes to a temporary file next to `output_path` first and only renames
    it into place after ffmpeg succeeds and produced a non-empty file, so a
    crashed or partial extraction (e.g. disk full, process killed) never
    leaves a corrupt `audio.mp3` that a later run would mistake for a valid,
    already-extracted file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    try:
        _run_ffmpeg_extraction(video_path, tmp_path)
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise AudioExtractionError(f"ffmpeg nao gerou audio valido para {video_path}")
        os.replace(tmp_path, output_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return output_path


def _run_ffmpeg_extraction(video_path: Path, tmp_output_path: Path) -> None:
    """Run ffmpeg to pull just the audio stream out as mp3. Isolated in its
    own function so tests can mock it without needing a real ffmpeg binary.
    """
    try:
        (
            ffmpeg.input(str(video_path))
            .audio.output(str(tmp_output_path), acodec="libmp3lame", audio_bitrate="128k")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
        raise AudioExtractionError(
            f"ffmpeg falhou ao extrair audio de {video_path}: {stderr}"
        ) from exc

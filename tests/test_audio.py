"""Tests for aulaforge.audio. Never touches a real ffmpeg binary."""

from __future__ import annotations

from pathlib import Path

import pytest

import aulaforge.audio as audio_module
from aulaforge.audio import AudioExtractionError, extract_audio, is_ffmpeg_available


def test_is_ffmpeg_available_true_when_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio_module.shutil, "which", lambda name: "C:\\ffmpeg\\ffmpeg.exe")
    assert is_ffmpeg_available() is True


def test_is_ffmpeg_available_false_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio_module.shutil, "which", lambda name: None)
    assert is_ffmpeg_available() is False


def test_extract_audio_renames_temp_file_into_place_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(video_path: Path, tmp_output_path: Path) -> None:
        tmp_output_path.write_bytes(b"fake-mp3-bytes")

    monkeypatch.setattr(audio_module, "_run_ffmpeg_extraction", fake_run)

    video_path = tmp_path / "aula.mp4"
    video_path.write_bytes(b"fake-video")
    output_path = tmp_path / "output" / "audio.mp3"

    result = extract_audio(video_path, output_path)

    assert result == output_path
    assert output_path.exists()
    assert output_path.read_bytes() == b"fake-mp3-bytes"
    assert not output_path.with_stem(output_path.stem + ".tmp").exists()


def test_extract_audio_raises_and_cleans_up_temp_on_ffmpeg_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_run(video_path: Path, tmp_output_path: Path) -> None:
        raise AudioExtractionError("ffmpeg explodiu")

    monkeypatch.setattr(audio_module, "_run_ffmpeg_extraction", failing_run)

    video_path = tmp_path / "aula.mp4"
    video_path.write_bytes(b"fake-video")
    output_path = tmp_path / "audio.mp3"

    with pytest.raises(AudioExtractionError):
        extract_audio(video_path, output_path)

    assert not output_path.exists()
    assert not output_path.with_stem(output_path.stem + ".tmp").exists()


def test_temp_path_passed_to_ffmpeg_ends_with_mp3_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temp path passed to _run_ffmpeg_extraction must end in .mp3.

    ffmpeg infers the output format from the file extension. A path ending in
    .tmp causes "Unable to find a suitable output format" — the canonical fix
    is keeping .mp3 as the last extension (e.g. audio.tmp.mp3, not audio.mp3.tmp).
    """
    captured: list[Path] = []

    def capture_run(video_path: Path, tmp_output_path: Path) -> None:
        captured.append(tmp_output_path)
        tmp_output_path.write_bytes(b"fake-mp3-bytes")

    monkeypatch.setattr(audio_module, "_run_ffmpeg_extraction", capture_run)

    video_path = tmp_path / "aula.mp4"
    video_path.write_bytes(b"fake-video")
    output_path = tmp_path / "audio.mp3"

    extract_audio(video_path, output_path)

    assert len(captured) == 1
    assert captured[0].suffix == ".mp3", (
        f"Temp path deve terminar em .mp3 para que ffmpeg infira o formato; "
        f"recebido: {captured[0].name!r}"
    )
    assert captured[0] != output_path, "Temp path não deve ser o arquivo final"


def test_extract_audio_raises_when_ffmpeg_produces_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def empty_run(video_path: Path, tmp_output_path: Path) -> None:
        tmp_output_path.write_bytes(b"")

    monkeypatch.setattr(audio_module, "_run_ffmpeg_extraction", empty_run)

    video_path = tmp_path / "aula.mp4"
    video_path.write_bytes(b"fake-video")
    output_path = tmp_path / "audio.mp3"

    with pytest.raises(AudioExtractionError):
        extract_audio(video_path, output_path)

    assert not output_path.exists()

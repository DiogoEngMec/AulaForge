"""Tests for aulaforge.transcription. Never imports the real `whisper` package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import aulaforge.transcription as transcription_module
from aulaforge.models import TranscriptSegment
from aulaforge.transcription import (
    check_transcription_dependencies,
    is_whisper_available,
    transcribe_audio,
    whisper_language_hint,
    write_clean_transcript,
    write_raw_transcript,
    write_timestamped_transcript,
)


class FakeWhisperModel:
    """Stands in for whisper.Whisper: only needs a .transcribe() method."""

    def __init__(self, segments: list[dict[str, object]]) -> None:
        self._segments = segments
        self.calls: list[tuple[str, str | None]] = []

    def transcribe(self, audio_path: str, language: str | None = None) -> dict[str, object]:
        self.calls.append((audio_path, language))
        return {"segments": self._segments, "language": language or "pt"}


def test_is_whisper_available_true_when_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        transcription_module.importlib.util, "find_spec", lambda name: object()
    )
    assert is_whisper_available() is True


def test_is_whisper_available_false_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcription_module.importlib.util, "find_spec", lambda name: None)
    assert is_whisper_available() is False


@pytest.mark.skipif(
    importlib.util.find_spec("whisper") is None, reason="openai-whisper not installed"
)
def test_is_whisper_available_reflects_real_environment() -> None:
    assert is_whisper_available() is True


def test_check_transcription_dependencies_empty_when_both_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transcription_module, "is_ffmpeg_available", lambda: True)
    monkeypatch.setattr(transcription_module, "is_whisper_available", lambda: True)
    assert check_transcription_dependencies() == []


def test_check_transcription_dependencies_reports_each_missing_piece(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transcription_module, "is_ffmpeg_available", lambda: False)
    monkeypatch.setattr(transcription_module, "is_whisper_available", lambda: False)
    errors = check_transcription_dependencies()
    assert len(errors) == 2
    assert any("ffmpeg" in e for e in errors)
    assert any("whisper" in e for e in errors)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("pt-BR", "pt"),
        ("pt", "pt"),
        ("en-US", "en"),
        ("PT-br", "pt"),
        ("", None),
        ("portuguese", None),
        ("pt-BR-extra", "pt"),
    ],
)
def test_whisper_language_hint(language: str, expected: str | None) -> None:
    assert whisper_language_hint(language) == expected


def test_transcribe_audio_converts_whisper_result_to_segments(tmp_path: Path) -> None:
    model = FakeWhisperModel(
        segments=[
            {"start": 0.0, "end": 5.0, "text": " Ola mundo "},
            {"start": 5.0, "end": 10.0, "text": "Segunda frase"},
        ]
    )
    audio_path = tmp_path / "audio.mp3"

    segments = transcribe_audio(model, audio_path, language="pt")

    assert segments == [
        TranscriptSegment(start=0.0, end=5.0, text="Ola mundo"),
        TranscriptSegment(start=5.0, end=10.0, text="Segunda frase"),
    ]
    assert model.calls == [(str(audio_path), "pt")]


def test_write_raw_transcript_concatenates_segment_text(tmp_path: Path) -> None:
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Ola"),
        TranscriptSegment(start=5.0, end=10.0, text="mundo"),
    ]

    path = write_raw_transcript(tmp_path, segments)

    assert path.read_text(encoding="utf-8") == "Ola mundo"


def test_write_timestamped_transcript_matches_data_contracts_schema(tmp_path: Path) -> None:
    segments = [TranscriptSegment(start=0.0, end=12.4, text="texto")]

    path = write_timestamped_transcript(tmp_path, segments)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == [{"start": 0.0, "end": 12.4, "text": "texto"}]


def test_write_clean_transcript_groups_into_chunk_blocks_with_headers(tmp_path: Path) -> None:
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Bloco um."),
        TranscriptSegment(start=900.0, end=905.0, text="Bloco dois."),
    ]

    path = write_clean_transcript(tmp_path, segments, chunk_minutes=15)

    content = path.read_text(encoding="utf-8")
    assert "## Bloco (00:00:00 - 00:00:05)" in content
    assert "## Bloco (00:15:00 - 00:15:05)" in content
    assert "Bloco um." in content
    assert "Bloco dois." in content


def test_write_clean_transcript_handles_empty_segments(tmp_path: Path) -> None:
    path = write_clean_transcript(tmp_path, [], chunk_minutes=15)
    assert path.read_text(encoding="utf-8").strip() == "# Transcricao limpa"

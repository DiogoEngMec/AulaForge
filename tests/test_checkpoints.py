"""Tests for aulaforge.checkpoints."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from aulaforge.checkpoints import (
    PROCESSING_LOG_FILENAME,
    SOURCE_INFO_FILENAME,
    TRANSCRIPTION_STEP,
    compute_sha256,
    needs_foundation_processing,
    needs_transcription_processing,
    process_lesson_foundation,
    process_lesson_transcription,
    read_processing_log,
    record_failed_foundation,
    record_failed_step,
    record_skipped_transcription,
    write_batch_summary,
)
from aulaforge.config import TranscriptionConfig
from aulaforge.discovery import discover_course
from aulaforge.models import Status


def test_compute_sha256_is_deterministic(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"a" * (2 * 1024 * 1024 + 17))  # spans multiple read chunks
    assert compute_sha256(video) == compute_sha256(video)


def test_process_lesson_foundation_first_run_completes(course_dir: Path, output_root: Path) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    info, entry = process_lesson_foundation(lesson)

    assert entry.status == Status.COMPLETED
    assert info.status == Status.COMPLETED
    assert (lesson.output_dir / SOURCE_INFO_FILENAME).exists()
    assert (lesson.output_dir / PROCESSING_LOG_FILENAME).exists()


def test_process_lesson_foundation_skips_unchanged_video(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    process_lesson_foundation(lesson)
    assert needs_foundation_processing(lesson) is False

    _, second_entry = process_lesson_foundation(lesson)
    assert second_entry.status == Status.SKIPPED_UNCHANGED


def test_process_lesson_foundation_reprocesses_changed_video(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    first_info, _ = process_lesson_foundation(lesson)
    lesson.video_path.write_bytes(b"conteudo totalmente diferente")
    assert needs_foundation_processing(lesson) is True

    second_info, second_entry = process_lesson_foundation(lesson)
    assert second_entry.status == Status.COMPLETED
    assert second_info.hash != first_info.hash


def test_process_lesson_foundation_force_reprocesses_even_when_unchanged(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    process_lesson_foundation(lesson)
    _, entry = process_lesson_foundation(lesson, force=True)
    assert entry.status == Status.COMPLETED


def test_record_failed_foundation_logs_without_writing_source_info(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    entry = record_failed_foundation(lesson, datetime.now(), RuntimeError("disco cheio"))

    assert entry.status == Status.FAILED
    assert entry.message is not None and "disco cheio" in entry.message
    assert not (lesson.output_dir / SOURCE_INFO_FILENAME).exists()

    log = read_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug)
    latest = log.latest("foundation")
    assert latest is not None
    assert latest.status == Status.FAILED


def test_write_batch_summary_creates_report_files(course_dir: Path, output_root: Path) -> None:
    course = discover_course(course_dir, output_root)
    entries: dict[str, dict[str, object]] = {}
    for lesson in course.lessons:
        _, entry = process_lesson_foundation(lesson)
        entries[lesson.slug] = {"foundation": entry}

    write_batch_summary(course, entries)

    batch_log = json.loads((course.output_path / "batch_log.json").read_text(encoding="utf-8"))
    assert batch_log["course"] == course.name
    assert set(batch_log["lessons"]) == set(entries)
    assert all("foundation" in steps for steps in batch_log["lessons"].values())
    assert (course.output_path / "batch_report.md").exists()


def test_write_batch_summary_renders_one_column_per_observed_step(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    _, foundation_entry = process_lesson_foundation(lesson)
    transcription_entry = record_skipped_transcription(lesson, "somehash", datetime.now())

    write_batch_summary(
        course,
        {lesson.slug: {"foundation": foundation_entry, TRANSCRIPTION_STEP: transcription_entry}},
    )

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "Foundation" in report
    assert "Transcription" in report
    assert "completed" in report
    assert "skipped_unchanged" in report


class FakeWhisperModel:
    """Stands in for whisper.Whisper: only needs a .transcribe() method."""

    def __init__(self, segments: list[dict[str, object]]) -> None:
        self._segments = segments

    def transcribe(self, audio_path: str, language: str | None = None) -> dict[str, object]:
        return {"segments": self._segments}


def _transcription_config(**overrides: bool) -> TranscriptionConfig:
    return TranscriptionConfig(**overrides)


def _fake_extract_audio(video_path: Path, output_path: Path) -> Path:
    """Stands in for aulaforge.audio.extract_audio without touching ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake-audio")
    return output_path


@pytest.fixture
def stub_extract_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aulaforge.checkpoints.extract_audio", _fake_extract_audio)


def test_needs_transcription_processing_true_when_never_run(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)

    assert needs_transcription_processing(lesson, info.hash, _transcription_config()) is True


def test_needs_transcription_processing_false_after_completed_with_all_files(
    course_dir: Path, output_root: Path, stub_extract_audio: None
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)

    model = FakeWhisperModel([{"start": 0.0, "end": 1.0, "text": "ola"}])
    process_lesson_transcription(
        lesson, model, info.hash, _transcription_config(), chunk_minutes=15, language_hint=None
    )

    assert needs_transcription_processing(lesson, info.hash, _transcription_config()) is False


def test_needs_transcription_processing_true_when_video_hash_changed(
    course_dir: Path, output_root: Path, stub_extract_audio: None
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)

    model = FakeWhisperModel([{"start": 0.0, "end": 1.0, "text": "ola"}])
    process_lesson_transcription(
        lesson, model, info.hash, _transcription_config(), chunk_minutes=15, language_hint=None
    )

    assert needs_transcription_processing(lesson, "hash-diferente", _transcription_config()) is True


def test_needs_transcription_processing_true_when_save_raw_enabled_but_file_missing(
    course_dir: Path, output_root: Path, stub_extract_audio: None
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)

    model = FakeWhisperModel([{"start": 0.0, "end": 1.0, "text": "ola"}])
    # First completed with save_raw=False, so 01_TRANSCRICAO_BRUTA.txt was never written.
    process_lesson_transcription(
        lesson,
        model,
        info.hash,
        _transcription_config(save_raw=False),
        chunk_minutes=15,
        language_hint=None,
    )

    # Now the config asks for save_raw=True: the missing file must trigger reprocessing.
    needs = needs_transcription_processing(lesson, info.hash, _transcription_config(save_raw=True))
    assert needs is True


def test_needs_transcription_processing_true_when_save_timestamps_enabled_but_file_missing(
    course_dir: Path, output_root: Path, stub_extract_audio: None
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)

    model = FakeWhisperModel([{"start": 0.0, "end": 1.0, "text": "ola"}])
    process_lesson_transcription(
        lesson,
        model,
        info.hash,
        _transcription_config(save_timestamps=False),
        chunk_minutes=15,
        language_hint=None,
    )

    needs = needs_transcription_processing(
        lesson, info.hash, _transcription_config(save_timestamps=True)
    )
    assert needs is True


def test_needs_transcription_processing_true_when_audio_file_missing(
    course_dir: Path, output_root: Path, stub_extract_audio: None
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)

    model = FakeWhisperModel([{"start": 0.0, "end": 1.0, "text": "ola"}])
    process_lesson_transcription(
        lesson, model, info.hash, _transcription_config(), chunk_minutes=15, language_hint=None
    )
    (lesson.output_dir / "audio.mp3").unlink()

    assert needs_transcription_processing(lesson, info.hash, _transcription_config()) is True


def test_needs_transcription_processing_respects_force(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)

    needs = needs_transcription_processing(
        lesson, info.hash, _transcription_config(), force=True
    )
    assert needs is True


def test_process_lesson_transcription_writes_expected_files(
    course_dir: Path, output_root: Path, stub_extract_audio: None
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)

    model = FakeWhisperModel(
        [
            {"start": 0.0, "end": 5.0, "text": "Ola"},
            {"start": 900.0, "end": 905.0, "text": "Mundo"},
        ]
    )

    segments, entry = process_lesson_transcription(
        lesson, model, info.hash, _transcription_config(), chunk_minutes=15, language_hint="pt"
    )

    assert entry.status == Status.COMPLETED
    assert entry.source_hash == info.hash
    assert len(segments) == 2
    assert (lesson.output_dir / "audio.mp3").exists()
    assert (lesson.output_dir / "01_TRANSCRICAO_BRUTA.txt").exists()
    assert (lesson.output_dir / "02_TRANSCRICAO_COM_TIMESTAMPS.json").exists()
    assert (lesson.output_dir / "03_TRANSCRICAO_LIMPA.md").exists()

    log = read_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug)
    latest = log.latest(TRANSCRIPTION_STEP)
    assert latest is not None
    assert latest.status == Status.COMPLETED


def test_record_skipped_transcription_logs_without_running_anything(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    entry = record_skipped_transcription(lesson, "somehash", datetime.now())

    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.source_hash == "somehash"
    assert not (lesson.output_dir / "audio.mp3").exists()


def test_record_failed_step_is_reused_by_record_failed_foundation(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    entry = record_failed_step(lesson, TRANSCRIPTION_STEP, datetime.now(), RuntimeError("oops"))

    assert entry.step == TRANSCRIPTION_STEP
    assert entry.status == Status.FAILED
    assert entry.message == "oops"

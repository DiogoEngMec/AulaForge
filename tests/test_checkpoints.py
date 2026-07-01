"""Tests for aulaforge.checkpoints."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from aulaforge.checkpoints import (
    NOTES_STEP,
    NOTION_STEP,
    OCR_STEP,
    PROCESSING_LOG_FILENAME,
    SOURCE_INFO_FILENAME,
    TRANSCRIPTION_STEP,
    compute_sha256,
    needs_foundation_processing,
    needs_notes_processing,
    needs_notion_processing,
    needs_ocr_processing,
    needs_transcription_processing,
    process_lesson_foundation,
    process_lesson_notes,
    process_lesson_notion,
    process_lesson_ocr,
    process_lesson_transcription,
    read_processing_log,
    record_failed_foundation,
    record_failed_step,
    record_notes_skipped_no_transcript,
    record_notion_skipped_disabled,
    record_notion_skipped_no_notes,
    record_ocr_skipped_disabled,
    record_skipped_notes,
    record_skipped_notion,
    record_skipped_ocr,
    record_skipped_transcription,
    write_batch_summary,
)
from aulaforge.config import LlmConfig, NotionConfig, OcrConfig, TranscriptionConfig
from aulaforge.discovery import discover_course
from aulaforge.models import NotionLessonInfo, NotionPageInfo, Status


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


# ---------------------------------------------------------------------------
# Notes step (Phase 3)
# ---------------------------------------------------------------------------


@pytest.fixture
def transcribed_lesson(
    course_dir: Path, output_root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[object, object]:
    """Return (lesson, video_hash) after running foundation + transcription."""
    monkeypatch.setattr("aulaforge.checkpoints.extract_audio", _fake_extract_audio)
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    info, _ = process_lesson_foundation(lesson)
    model = FakeWhisperModel([{"start": 0.0, "end": 5.0, "text": "ola mundo"}])
    process_lesson_transcription(
        lesson, model, info.hash, _transcription_config(), chunk_minutes=15, language_hint=None
    )
    return lesson, info.hash


def test_needs_notes_processing_true_when_never_run(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    assert needs_notes_processing(lesson, "any-hash") is True


def test_needs_notes_processing_false_after_completed(
    transcribed_lesson: tuple[object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import aulaforge.checkpoints as chk_module

    lesson, _ = transcribed_lesson
    monkeypatch.setattr(chk_module, "generate_lesson_note", lambda t, txt, cfg: "# nota")
    cfg_llm = LlmConfig()
    transcript = (lesson.output_dir / "03_TRANSCRICAO_LIMPA.md").read_text(encoding="utf-8")  # type: ignore[union-attr]
    from aulaforge.notes import compute_notes_input_hash

    h = compute_notes_input_hash(transcript, cfg_llm)
    process_lesson_notes(lesson, transcript, h, cfg_llm)  # type: ignore[arg-type]
    assert needs_notes_processing(lesson, h) is False  # type: ignore[arg-type]


def test_needs_notes_processing_true_when_hash_changed(
    transcribed_lesson: tuple[object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import aulaforge.checkpoints as chk_module

    lesson, _ = transcribed_lesson
    monkeypatch.setattr(chk_module, "generate_lesson_note", lambda t, txt, cfg: "# nota")
    cfg_llm = LlmConfig()
    transcript = (lesson.output_dir / "03_TRANSCRICAO_LIMPA.md").read_text(encoding="utf-8")  # type: ignore[union-attr]
    from aulaforge.notes import compute_notes_input_hash

    h = compute_notes_input_hash(transcript, cfg_llm)
    process_lesson_notes(lesson, transcript, h, cfg_llm)  # type: ignore[arg-type]
    assert needs_notes_processing(lesson, "different-hash") is True  # type: ignore[arg-type]


def test_needs_notes_processing_true_when_file_deleted(
    transcribed_lesson: tuple[object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import aulaforge.checkpoints as chk_module
    from aulaforge.checkpoints import NOTES_FILENAME  # re-exported via notes import

    lesson, _ = transcribed_lesson
    monkeypatch.setattr(chk_module, "generate_lesson_note", lambda t, txt, cfg: "# nota")
    cfg_llm = LlmConfig()
    transcript = (lesson.output_dir / "03_TRANSCRICAO_LIMPA.md").read_text(encoding="utf-8")  # type: ignore[union-attr]
    from aulaforge.notes import compute_notes_input_hash

    h = compute_notes_input_hash(transcript, cfg_llm)
    process_lesson_notes(lesson, transcript, h, cfg_llm)  # type: ignore[arg-type]
    (lesson.output_dir / NOTES_FILENAME).unlink()  # type: ignore[union-attr]
    assert needs_notes_processing(lesson, h) is True  # type: ignore[arg-type]


def test_needs_notes_processing_respects_force(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    assert needs_notes_processing(lesson, "any-hash", force=True) is True


def test_record_skipped_notes_logs_without_running_anything(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    entry = record_skipped_notes(lesson, "test-hash", datetime.now())

    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.source_hash == "test-hash"
    assert not (lesson.output_dir / "09_ANOTACAO_NOTION.md").exists()

    log = read_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug)
    latest = log.latest(NOTES_STEP)
    assert latest is not None
    assert latest.status == Status.SKIPPED_UNCHANGED


def test_record_notes_skipped_no_transcript_uses_skipped_status(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    entry = record_notes_skipped_no_transcript(lesson, datetime.now())

    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.source_hash is None
    assert "Fase 2" in (entry.message or "")


def test_process_lesson_notes_writes_file_and_logs_completed(
    transcribed_lesson: tuple[object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import aulaforge.checkpoints as chk_module

    lesson, _ = transcribed_lesson
    monkeypatch.setattr(chk_module, "generate_lesson_note", lambda t, txt, cfg: "# Nota Fake")
    cfg_llm = LlmConfig()
    transcript = (lesson.output_dir / "03_TRANSCRICAO_LIMPA.md").read_text(encoding="utf-8")  # type: ignore[union-attr]
    from aulaforge.notes import compute_notes_input_hash

    h = compute_notes_input_hash(transcript, cfg_llm)

    content, entry = process_lesson_notes(lesson, transcript, h, cfg_llm)  # type: ignore[arg-type]

    assert entry.status == Status.COMPLETED
    assert entry.source_hash == h
    assert content == "# Nota Fake"
    notes_path = lesson.output_dir / "09_ANOTACAO_NOTION.md"  # type: ignore[union-attr]
    assert notes_path.exists()
    assert notes_path.read_text(encoding="utf-8") == "# Nota Fake"

    log = read_processing_log(
        lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug  # type: ignore[union-attr]
    )
    assert log.latest(NOTES_STEP) is not None
    assert log.latest(NOTES_STEP).status == Status.COMPLETED  # type: ignore[union-attr]


def test_write_batch_summary_renders_notes_column(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    _, foundation_entry = process_lesson_foundation(lesson)
    notes_entry = record_skipped_notes(lesson, "hash", datetime.now())

    write_batch_summary(
        course,
        {lesson.slug: {"foundation": foundation_entry, NOTES_STEP: notes_entry}},
    )

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "Notes" in report
    assert "skipped_unchanged" in report


# ---------------------------------------------------------------------------
# Notion step (Phase 4)
# ---------------------------------------------------------------------------


def _make_page_info(course_output: Path, lesson_slug: str, notion_hash: str) -> NotionPageInfo:
    """Write and return a NotionPageInfo with one pre-synced lesson entry."""
    import aulaforge.notion as notion_mod

    lesson_info = NotionLessonInfo(toggle_block_id="toggle-1", synced_hash=notion_hash)
    info = NotionPageInfo(
        course_page_id="page-1",
        course_page_url="https://notion.so/page-1",
        database_id="db-1",
        lessons={lesson_slug: lesson_info},
    )
    notion_mod.write_notion_page_info(course_output, info)
    return info


def test_needs_notion_processing_true_when_never_run(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    assert needs_notion_processing(lesson, course.output_path, "any-hash") is True


def test_needs_notion_processing_false_after_completed(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    notion_hash = "hash-abc"
    _make_page_info(course.output_path, lesson.slug, notion_hash)
    record_skipped_notion(lesson, notion_hash, datetime.now())
    assert needs_notion_processing(lesson, course.output_path, notion_hash) is False


def test_needs_notion_processing_true_when_hash_changed(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    notion_hash = "hash-abc"
    _make_page_info(course.output_path, lesson.slug, notion_hash)
    record_skipped_notion(lesson, notion_hash, datetime.now())
    assert needs_notion_processing(lesson, course.output_path, "different-hash") is True


def test_needs_notion_processing_true_when_page_info_missing(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    notion_hash = "hash-abc"
    # Log says completed but no NOTION_PAGE_INFO.json on disk.
    record_skipped_notion(lesson, notion_hash, datetime.now())
    assert needs_notion_processing(lesson, course.output_path, notion_hash) is True


def test_needs_notion_processing_true_when_toggle_block_id_missing(
    course_dir: Path, output_root: Path
) -> None:
    import aulaforge.notion as notion_mod

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    notion_hash = "hash-abc"
    # Page info exists but this lesson has no entry.
    info = NotionPageInfo(
        course_page_id="page-1", course_page_url="url", database_id="db-1", lessons={}
    )
    notion_mod.write_notion_page_info(course.output_path, info)
    record_skipped_notion(lesson, notion_hash, datetime.now())
    assert needs_notion_processing(lesson, course.output_path, notion_hash) is True


def test_needs_notion_processing_respects_force(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    assert needs_notion_processing(lesson, course.output_path, "any-hash", force=True) is True


def test_record_skipped_notion_logs_without_touching_notion(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    entry = record_skipped_notion(lesson, "test-hash", datetime.now())

    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.source_hash == "test-hash"
    log = read_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug)
    assert log.latest(NOTION_STEP) is not None
    assert log.latest(NOTION_STEP).status == Status.SKIPPED_UNCHANGED  # type: ignore[union-attr]


def test_record_notion_skipped_no_notes_uses_skipped_status(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    entry = record_notion_skipped_no_notes(lesson, datetime.now())

    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.source_hash is None
    assert "Fase 3" in (entry.message or "")


def test_record_notion_skipped_disabled_message_mentions_enabled(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]

    entry = record_notion_skipped_disabled(lesson, datetime.now())

    assert entry.status == Status.SKIPPED_UNCHANGED
    msg = (entry.message or "").lower()
    assert "enabled" in msg or "auto_send" in msg


def test_process_lesson_notion_calls_sync_and_logs_completed(
    course_dir: Path, output_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aulaforge.checkpoints as chk_module

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)

    fake_info = NotionPageInfo(
        course_page_id="page-1",
        course_page_url="url",
        database_id="db-1",
        lessons={"aula_01": NotionLessonInfo(toggle_block_id="t-1", synced_hash="h-1")},
    )
    monkeypatch.setattr(
        chk_module,
        "sync_lesson_to_notion",
        lambda course, lesson, note, nhash, cfg, token, db: (fake_info, "t-1"),
    )

    cfg_notion = NotionConfig(database_id="db-1")
    page_info, entry = process_lesson_notion(
        course, lesson, "# nota", "h-1", cfg_notion, "token", "db-1"
    )

    assert entry.status == Status.COMPLETED
    assert entry.source_hash == "h-1"
    assert entry.step == NOTION_STEP
    assert page_info.course_page_id == "page-1"

    log = read_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug)
    assert log.latest(NOTION_STEP) is not None
    assert log.latest(NOTION_STEP).status == Status.COMPLETED  # type: ignore[union-attr]


def test_write_batch_summary_renders_notion_column(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    _, foundation_entry = process_lesson_foundation(lesson)
    notion_entry = record_skipped_notion(lesson, "hash", datetime.now())

    write_batch_summary(
        course,
        {lesson.slug: {"foundation": foundation_entry, NOTION_STEP: notion_entry}},
    )

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "Notion" in report
    assert "skipped_unchanged" in report


# ── OCR checkpoint tests ───────────────────────────────────────────────────────


def _make_ocr_output_files(output_dir: Path) -> None:
    """Create the 4 expected OCR output files."""
    for name in ("04_OCR_TELA.json", "05_OCR_TELA.md",
                  "06_CODIGOS_DETECTADOS.md", "07_COMANDOS_TERMINAL.md"):
        (output_dir / name).write_text("content", encoding="utf-8")


def test_record_skipped_ocr_writes_correct_entry(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)

    entry = record_skipped_ocr(lesson, "ocrhash123", datetime.now())
    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.step == OCR_STEP
    assert entry.source_hash == "ocrhash123"


def test_record_ocr_skipped_disabled_writes_correct_entry(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)

    entry = record_ocr_skipped_disabled(lesson, datetime.now())
    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.step == OCR_STEP
    assert entry.source_hash is None


def test_needs_ocr_processing_true_when_no_log(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)

    assert needs_ocr_processing(lesson, "somehash", OcrConfig()) is True


def test_needs_ocr_processing_false_when_all_ok(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    _make_ocr_output_files(lesson.output_dir)
    (lesson.output_dir / "frames").mkdir()

    record_skipped_ocr(lesson, "ocrhash", datetime.now())
    assert needs_ocr_processing(lesson, "ocrhash", OcrConfig()) is False


def test_needs_ocr_processing_true_when_hash_changes(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    _make_ocr_output_files(lesson.output_dir)
    (lesson.output_dir / "frames").mkdir()

    record_skipped_ocr(lesson, "old_hash", datetime.now())
    assert needs_ocr_processing(lesson, "new_hash", OcrConfig()) is True


def test_needs_ocr_processing_true_when_output_file_missing(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    _make_ocr_output_files(lesson.output_dir)
    (lesson.output_dir / "frames").mkdir()
    record_skipped_ocr(lesson, "ocrhash", datetime.now())

    # Delete one output file
    (lesson.output_dir / "04_OCR_TELA.json").unlink()
    assert needs_ocr_processing(lesson, "ocrhash", OcrConfig()) is True


def test_needs_ocr_processing_true_when_frames_dir_missing_and_save_enabled(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    _make_ocr_output_files(lesson.output_dir)
    # No frames dir

    record_skipped_ocr(lesson, "ocrhash", datetime.now())
    cfg = OcrConfig(save_screenshots_local=True)
    assert needs_ocr_processing(lesson, "ocrhash", cfg) is True


def test_needs_ocr_processing_false_when_frames_absent_but_save_disabled(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    _make_ocr_output_files(lesson.output_dir)
    # No frames dir, but save_screenshots_local=False

    record_skipped_ocr(lesson, "ocrhash", datetime.now())
    cfg = OcrConfig(save_screenshots_local=False)
    assert needs_ocr_processing(lesson, "ocrhash", cfg) is False


def test_needs_ocr_processing_true_when_force(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)
    _make_ocr_output_files(lesson.output_dir)
    (lesson.output_dir / "frames").mkdir()
    record_skipped_ocr(lesson, "ocrhash", datetime.now())

    assert needs_ocr_processing(lesson, "ocrhash", OcrConfig(), force=True) is True


def test_process_lesson_ocr_completes_and_logs(
    course_dir: Path, output_root: Path
) -> None:
    """process_lesson_ocr records a COMPLETED log entry.

    Patches the heavy work in aulaforge.ocr (the lazy-import source) so no
    real FFmpeg or Tesseract binary is required.
    """
    from unittest.mock import patch

    from aulaforge.models import OcrFrameResult

    fake_result = OcrFrameResult(
        timestamp="00:00:00",
        frame_path="frames/00-00-00.png",
        screen_type="other",
        text="",
        confidence="low",
    )

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    process_lesson_foundation(lesson)

    # Patch the heavy operations at their definition site in aulaforge.ocr
    with (
        patch("aulaforge.ocr.process_lesson_ocr_frames", return_value=[fake_result]),
        patch("aulaforge.ocr.write_ocr_json"),
        patch("aulaforge.ocr.write_ocr_md"),
        patch("aulaforge.ocr.write_codes_md"),
        patch("aulaforge.ocr.write_commands_md"),
    ):
        results, entry = process_lesson_ocr(lesson, "ocrhash", OcrConfig())

    assert entry.status == Status.COMPLETED
    assert entry.step == OCR_STEP
    assert entry.source_hash == "ocrhash"
    assert results == [fake_result]


def test_write_batch_summary_renders_ocr_column(
    course_dir: Path, output_root: Path
) -> None:
    from aulaforge.discovery import discover_course

    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    _, foundation_entry = process_lesson_foundation(lesson)
    ocr_entry = record_skipped_ocr(lesson, "hash", datetime.now())

    write_batch_summary(
        course,
        {lesson.slug: {"foundation": foundation_entry, OCR_STEP: ocr_entry}},
    )

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "Ocr" in report
    assert "skipped_unchanged" in report

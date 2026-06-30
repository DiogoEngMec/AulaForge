"""Tests for aulaforge.checkpoints."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aulaforge.checkpoints import (
    PROCESSING_LOG_FILENAME,
    SOURCE_INFO_FILENAME,
    compute_sha256,
    needs_foundation_processing,
    process_lesson_foundation,
    read_processing_log,
    record_failed_foundation,
    write_batch_summary,
)
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
    entries = {}
    for lesson in course.lessons:
        _, entry = process_lesson_foundation(lesson)
        entries[lesson.slug] = entry

    write_batch_summary(course, entries)

    batch_log = json.loads((course.output_path / "batch_log.json").read_text(encoding="utf-8"))
    assert batch_log["course"] == course.name
    assert set(batch_log["lessons"]) == set(entries)
    assert (course.output_path / "batch_report.md").exists()

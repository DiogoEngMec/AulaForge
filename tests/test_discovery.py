"""Tests for aulaforge.discovery."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from aulaforge.discovery import (
    build_lesson_slug,
    build_lessons,
    discover_course,
    discover_videos,
    extract_lesson_number,
)


def test_discover_videos_filters_non_video_files(course_dir: Path) -> None:
    videos = discover_videos(course_dir)
    names = {v.name for v in videos}
    assert "notas.txt" not in names
    assert "aula 1 - introducao.mp4" in names
    assert len(videos) == 4


def test_extract_lesson_number_prefers_aula_pattern() -> None:
    assert extract_lesson_number("aula 1 - introducao") == 1
    assert extract_lesson_number("aula 02 - modelos") == 2
    assert extract_lesson_number("Aula_03_extra") == 3


def test_extract_lesson_number_falls_back_to_leading_digits() -> None:
    assert extract_lesson_number("10 - deploy") == 10


def test_extract_lesson_number_returns_none_when_absent() -> None:
    assert extract_lesson_number("extra sem numero") is None


def test_build_lessons_orders_numbered_first_then_alphabetical_fallback(
    course_dir: Path, output_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="aulaforge.discovery")
    output_path = output_root / "Curso Django CRM"

    lessons = build_lessons(course_dir, output_path)

    numbers = [lesson.number for lesson in lessons]
    assert numbers == [1, 2, 10, None]
    assert lessons[-1].title == "extra sem numero"
    assert any("Numero da aula" in record.message for record in caplog.records)


def test_build_lesson_slug_strips_number_prefix_from_title() -> None:
    assert build_lesson_slug(1, "aula 1 - introducao") == "aula_01_introducao"
    assert build_lesson_slug(2, "aula 02 - parte dois") == "aula_02_parte-dois"
    assert build_lesson_slug(10, "10 - deploy") == "aula_10_deploy"
    assert build_lesson_slug(None, "extra sem numero") == "aula_extra-sem-numero"


def test_discover_course_uses_folder_name(course_dir: Path, output_root: Path) -> None:
    course = discover_course(course_dir, output_root)
    assert course.name == "Curso Django CRM"
    assert len(course.lessons) == 4
    assert course.output_path == output_root / "Curso Django CRM"

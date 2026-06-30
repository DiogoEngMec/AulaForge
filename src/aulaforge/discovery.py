"""Course video discovery and lesson ordering."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from slugify import slugify

from aulaforge.models import Course, Lesson

logger = logging.getLogger("aulaforge.discovery")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# Tried in order: "aula 1", "aula 01", "aula_01" first, then a leading
# number like "01 - titulo.mp4". Whichever matches first wins.
_NUMBER_PATTERNS = (
    re.compile(r"(?i)aula[\s_\-]*0*(\d+)"),
    re.compile(r"^0*(\d+)"),
)

# Same prefixes as _NUMBER_PATTERNS, but anchored and greedy on the trailing
# separator, so the matched lesson-number prefix can be stripped from the
# title before slugifying (e.g. "aula 1 - introducao" -> "introducao").
_PREFIX_STRIP_PATTERNS = (
    re.compile(r"(?i)^\s*aula[\s_\-]*0*\d+[\s_\-]*"),
    re.compile(r"^\s*0*\d+[\s_\-]*"),
)


def extract_lesson_number(file_stem: str) -> int | None:
    """Extract a lesson number from a video filename stem, if present."""
    for pattern in _NUMBER_PATTERNS:
        match = pattern.search(file_stem)
        if match:
            return int(match.group(1))
    return None


def _strip_number_prefix(title: str) -> str:
    """Remove a matched lesson-number prefix from `title`, for cleaner slugs."""
    for pattern in _PREFIX_STRIP_PATTERNS:
        stripped = pattern.sub("", title, count=1)
        if stripped != title:
            return stripped.strip() or title
    return title


def discover_videos(course_path: Path) -> list[Path]:
    """Find course video files directly inside `course_path`."""
    return sorted(
        path
        for path in course_path.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def build_lesson_slug(number: int | None, title: str) -> str:
    clean_title = _strip_number_prefix(title) if number is not None else title
    title_slug = slugify(clean_title) or "aula"
    if number is not None:
        return f"aula_{number:02d}_{title_slug}"
    return f"aula_{title_slug}"


def build_lessons(course_path: Path, output_path: Path) -> list[Lesson]:
    """Discover videos and turn them into ordered Lesson records.

    Lessons with a detected number are ordered first (ascending); lessons
    without one fall back to alphabetical order and are appended after, with
    a warning logged for each so the gap is visible in batch runs.
    """
    lessons: list[Lesson] = []
    used_slugs: set[str] = set()

    for video_path in discover_videos(course_path):
        number = extract_lesson_number(video_path.stem)
        if number is None:
            logger.warning(
                "Numero da aula nao encontrado em '%s'; usando ordenacao "
                "alfabetica como fallback.",
                video_path.name,
            )

        slug = build_lesson_slug(number, video_path.stem)
        if slug in used_slugs:
            suffix = 2
            candidate = f"{slug}_{suffix}"
            while candidate in used_slugs:
                suffix += 1
                candidate = f"{slug}_{suffix}"
            slug = candidate
        used_slugs.add(slug)

        lessons.append(
            Lesson(
                number=number,
                title=video_path.stem,
                slug=slug,
                video_path=video_path,
                output_dir=output_path / slug,
            )
        )

    lessons.sort(
        key=lambda lesson: (
            lesson.number is None,
            lesson.number if lesson.number is not None else 0,
            lesson.video_path.name.lower(),
        )
    )
    return lessons


def discover_course(course_path: Path, output_root: Path) -> Course:
    """Discover a full course: name from the folder, lessons ordered for processing."""
    course_path = course_path.resolve()
    course_name = course_path.name
    output_path = output_root / course_name
    lessons = build_lessons(course_path, output_path)
    return Course(
        name=course_name,
        input_path=course_path,
        output_path=output_path,
        lessons=lessons,
    )

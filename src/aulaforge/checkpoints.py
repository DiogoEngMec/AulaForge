"""Checkpoint and fingerprint logic for lesson videos.

`source_info.json` represents the video's fingerprint and the state of the
foundation/indexing step only. `processing_log.json` accumulates one entry
per pipeline step (foundation now; transcription, notes, etc. in later
phases) so a lesson is never treated as "fully processed by the whole
pipeline" just because Phase 1 indexed it.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from aulaforge.models import Course, Lesson, ProcessingLog, SourceInfo, Status, StepLogEntry

logger = logging.getLogger("aulaforge.checkpoints")

SOURCE_INFO_FILENAME = "source_info.json"
PROCESSING_LOG_FILENAME = "processing_log.json"
FOUNDATION_STEP = "foundation"

_HASH_CHUNK_SIZE = 1024 * 1024  # 1 MiB, keeps memory flat for multi-GB videos


def compute_sha256(path: Path, chunk_size: int = _HASH_CHUNK_SIZE) -> str:
    """Compute a SHA256 hash of `path`, streaming it in fixed-size chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source_info(path: Path) -> SourceInfo | None:
    if not path.exists():
        return None
    return SourceInfo.model_validate_json(path.read_text(encoding="utf-8"))


def write_source_info(path: Path, info: SourceInfo) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(info.model_dump_json(indent=2), encoding="utf-8")


def read_processing_log(path: Path, lesson_slug: str) -> ProcessingLog:
    if not path.exists():
        return ProcessingLog(lesson=lesson_slug)
    return ProcessingLog.model_validate_json(path.read_text(encoding="utf-8"))


def append_processing_log(path: Path, lesson_slug: str, entry: StepLogEntry) -> ProcessingLog:
    log = read_processing_log(path, lesson_slug)
    log.steps.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(log.model_dump_json(indent=2), encoding="utf-8")
    return log


def _quick_fingerprint_matches(video_path: Path, existing: SourceInfo) -> bool:
    """Cheap size+mtime check, used to avoid re-hashing unchanged videos."""
    stat = video_path.stat()
    current_mtime = datetime.fromtimestamp(stat.st_mtime)
    return (
        existing.file_size == stat.st_size
        and abs((existing.last_modified - current_mtime).total_seconds()) < 1
    )


def _has_valid_foundation_record(lesson: Lesson, existing: SourceInfo) -> bool:
    """True if `existing` still matches the video and foundation was logged as done."""
    if not _quick_fingerprint_matches(lesson.video_path, existing):
        return False
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    latest = log.latest(FOUNDATION_STEP)
    return latest is not None and latest.status in (
        Status.COMPLETED,
        Status.SKIPPED_UNCHANGED,
    )


def needs_foundation_processing(lesson: Lesson, force: bool = False) -> bool:
    """Decide whether the foundation step must (re)run for this lesson.

    Only the size+mtime fast path is used to decide; the full SHA256 is only
    (re)computed when this says the video might have changed (or no record
    exists), so unchanged multi-GB videos are not re-hashed on every batch
    run. This only governs the foundation/indexing step itself, not whether
    later pipeline phases still need to run.
    """
    if force:
        return True
    source_info_path = lesson.output_dir / SOURCE_INFO_FILENAME
    existing = read_source_info(source_info_path)
    if existing is None:
        return True
    return not _has_valid_foundation_record(lesson, existing)


def process_lesson_foundation(
    lesson: Lesson, force: bool = False
) -> tuple[SourceInfo, StepLogEntry]:
    """Run (or skip) the Phase 1 foundation/indexing step for one lesson."""
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    source_info_path = lesson.output_dir / SOURCE_INFO_FILENAME
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    started_at = datetime.now()

    if not needs_foundation_processing(lesson, force=force):
        existing = read_source_info(source_info_path)
        if existing is not None:
            logger.info("Aula '%s' inalterada; etapa foundation pulada.", lesson.slug)
            entry = StepLogEntry(
                step=FOUNDATION_STEP,
                status=Status.SKIPPED_UNCHANGED,
                started_at=started_at,
                finished_at=datetime.now(),
                message="Video inalterado (tamanho e data de modificacao batem).",
            )
            append_processing_log(processing_log_path, lesson.slug, entry)
            return existing, entry

    stat = lesson.video_path.stat()
    file_hash = compute_sha256(lesson.video_path)
    info = SourceInfo(
        video_path=str(lesson.video_path),
        file_name=lesson.video_path.name,
        file_size=stat.st_size,
        last_modified=datetime.fromtimestamp(stat.st_mtime),
        hash=file_hash,
        processed_at=datetime.now(),
        status=Status.COMPLETED,
    )
    write_source_info(source_info_path, info)
    entry = StepLogEntry(
        step=FOUNDATION_STEP,
        status=Status.COMPLETED,
        started_at=started_at,
        finished_at=datetime.now(),
    )
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s' indexada (foundation).", lesson.slug)
    return info, entry


def record_failed_foundation(
    lesson: Lesson, started_at: datetime, error: Exception
) -> StepLogEntry:
    """Log a foundation-step failure without touching source_info.json."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=FOUNDATION_STEP,
        status=Status.FAILED,
        started_at=started_at,
        finished_at=datetime.now(),
        message=str(error),
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.error("Falha na etapa foundation da aula '%s': %s", lesson.slug, error)
    return entry


def write_batch_summary(course: Course, entries: dict[str, StepLogEntry]) -> None:
    """Write course-level `batch_log.json` and `batch_report.md` for this run."""
    course.output_path.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat()

    summary = {
        "course": course.name,
        "generated_at": generated_at,
        "lessons": {slug: entry.status.value for slug, entry in entries.items()},
    }
    (course.output_path / "batch_log.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        f"# Batch report - {course.name}",
        "",
        f"Gerado em: {generated_at}",
        "",
        "| Aula | Status (foundation) |",
        "|---|---|",
    ]
    for slug, entry in entries.items():
        lines.append(f"| {slug} | {entry.status.value} |")
    (course.output_path / "batch_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

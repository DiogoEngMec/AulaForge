"""Checkpoint and fingerprint logic for lesson videos.

`source_info.json` represents the video's fingerprint and the state of the
foundation/indexing step only. `processing_log.json` accumulates one entry
per pipeline step (foundation, transcription now; notes, OCR, etc. in later
phases) so a lesson is never treated as "fully processed by the whole
pipeline" just because one step ran.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from aulaforge.audio import AUDIO_FILENAME, extract_audio
from aulaforge.config import TranscriptionConfig
from aulaforge.models import (
    Course,
    Lesson,
    ProcessingLog,
    SourceInfo,
    Status,
    StepLogEntry,
    TranscriptSegment,
)
from aulaforge.transcription import (
    CLEAN_TRANSCRIPT_FILENAME,
    RAW_TRANSCRIPT_FILENAME,
    TIMESTAMPED_TRANSCRIPT_FILENAME,
    WhisperModel,
    transcribe_audio,
    write_clean_transcript,
    write_raw_transcript,
    write_timestamped_transcript,
)

logger = logging.getLogger("aulaforge.checkpoints")

SOURCE_INFO_FILENAME = "source_info.json"
PROCESSING_LOG_FILENAME = "processing_log.json"
FOUNDATION_STEP = "foundation"
TRANSCRIPTION_STEP = "transcription"

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


def _step_log_shows_done(log: ProcessingLog, step: str) -> bool:
    """True if `step`'s latest entry in `log` is completed or skipped_unchanged."""
    latest = log.latest(step)
    return latest is not None and latest.status in (
        Status.COMPLETED,
        Status.SKIPPED_UNCHANGED,
    )


def _has_valid_foundation_record(lesson: Lesson, existing: SourceInfo) -> bool:
    """True if `existing` still matches the video and foundation was logged as done."""
    if not _quick_fingerprint_matches(lesson.video_path, existing):
        return False
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    return _step_log_shows_done(log, FOUNDATION_STEP)


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


def record_failed_step(
    lesson: Lesson, step: str, started_at: datetime, error: Exception
) -> StepLogEntry:
    """Log a step failure without touching source_info.json."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=step,
        status=Status.FAILED,
        started_at=started_at,
        finished_at=datetime.now(),
        message=str(error),
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.error("Falha na etapa %s da aula '%s': %s", step, lesson.slug, error)
    return entry


def record_failed_foundation(
    lesson: Lesson, started_at: datetime, error: Exception
) -> StepLogEntry:
    """Log a foundation-step failure without touching source_info.json."""
    return record_failed_step(lesson, FOUNDATION_STEP, started_at, error)


def needs_transcription_processing(
    lesson: Lesson,
    video_hash: str,
    cfg: TranscriptionConfig,
    force: bool = False,
) -> bool:
    """Decide whether the transcription step must (re)run for this lesson.

    Checks, in order: --force; whether the last transcription step is
    logged as done; whether that entry's source_hash still matches the
    current video fingerprint; and whether every file the *current* config
    says should exist actually exists on disk (covers the user flipping
    save_raw/save_timestamps on, or a file being deleted between runs).
    """
    if force:
        return True

    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    if not _step_log_shows_done(log, TRANSCRIPTION_STEP):
        return True

    latest = log.latest(TRANSCRIPTION_STEP)
    if latest is None or latest.source_hash != video_hash:
        return True

    if not (lesson.output_dir / AUDIO_FILENAME).exists():
        return True
    if cfg.save_raw and not (lesson.output_dir / RAW_TRANSCRIPT_FILENAME).exists():
        return True
    if cfg.save_timestamps and not (lesson.output_dir / TIMESTAMPED_TRANSCRIPT_FILENAME).exists():
        return True
    return not (lesson.output_dir / CLEAN_TRANSCRIPT_FILENAME).exists()


def record_skipped_transcription(
    lesson: Lesson, video_hash: str, started_at: datetime
) -> StepLogEntry:
    """Log a transcription step that needed no work this run."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=TRANSCRIPTION_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Transcricao ja existe e o video nao mudou.",
        source_hash=video_hash,
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s' inalterada; etapa transcription pulada.", lesson.slug)
    return entry


def process_lesson_transcription(
    lesson: Lesson,
    model: WhisperModel,
    video_hash: str,
    cfg: TranscriptionConfig,
    chunk_minutes: int,
    language_hint: str | None,
) -> tuple[list[TranscriptSegment], StepLogEntry]:
    """Actually run the transcription step.

    The caller must have already decided (via needs_transcription_processing)
    that this is necessary, and must already have ffmpeg/whisper available
    and a loaded model — this function does not check any of that, by
    design, so the expensive checks/model load only ever happen once the
    orchestrator knows there is real work to do.
    """
    started_at = datetime.now()
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME

    audio_path = extract_audio(lesson.video_path, lesson.output_dir / AUDIO_FILENAME)
    segments = transcribe_audio(model, audio_path, language=language_hint)
    if cfg.save_raw:
        write_raw_transcript(lesson.output_dir, segments)
    if cfg.save_timestamps:
        write_timestamped_transcript(lesson.output_dir, segments)
    write_clean_transcript(lesson.output_dir, segments, chunk_minutes)

    entry = StepLogEntry(
        step=TRANSCRIPTION_STEP,
        status=Status.COMPLETED,
        started_at=started_at,
        finished_at=datetime.now(),
        source_hash=video_hash,
    )
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s' transcrita.", lesson.slug)
    return segments, entry


def write_batch_summary(course: Course, entries: dict[str, dict[str, StepLogEntry]]) -> None:
    """Write course-level `batch_log.json` and `batch_report.md` for this run.

    `entries` maps lesson slug -> {step name -> StepLogEntry}, since a lesson
    can have more than one step (foundation, transcription, ...). Columns are
    discovered dynamically from whatever steps are actually present, so a
    future phase adding a new step doesn't require touching this function.
    """
    course.output_path.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat()

    summary = {
        "course": course.name,
        "generated_at": generated_at,
        "lessons": {
            slug: {step: entry.status.value for step, entry in steps.items()}
            for slug, steps in entries.items()
        },
    }
    (course.output_path / "batch_log.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    all_steps = sorted({step for steps in entries.values() for step in steps})
    header_cols = ["Aula", *(step.capitalize() for step in all_steps)]
    lines = [
        f"# Batch report - {course.name}",
        "",
        f"Gerado em: {generated_at}",
        "",
        f"| {' | '.join(header_cols)} |",
        f"|{'---|' * len(header_cols)}",
    ]
    for slug, steps in entries.items():
        row = [slug, *(steps[step].status.value if step in steps else "-" for step in all_steps)]
        lines.append(f"| {' | '.join(row)} |")
    (course.output_path / "batch_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

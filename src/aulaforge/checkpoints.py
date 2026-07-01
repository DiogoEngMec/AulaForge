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
import os
from datetime import datetime
from pathlib import Path

from aulaforge.audio import AUDIO_FILENAME, extract_audio
from aulaforge.config import (
    LlmConfig,
    MergeConfig,
    NotionConfig,
    OcrConfig,
    OutputsConfig,
    TranscriptionConfig,
)
from aulaforge.models import (
    Course,
    Lesson,
    NotionPageInfo,
    OcrFrameResult,
    ProcessingLog,
    SourceInfo,
    Status,
    StepLogEntry,
    TranscriptSegment,
)
from aulaforge.notes import NOTES_FILENAME, generate_lesson_note
from aulaforge.notion import compute_notion_input_hash, read_notion_page_info, sync_lesson_to_notion
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
NOTES_STEP = "notes"
NOTION_STEP = "notion"
OCR_STEP = "ocr"
MERGE_STEP = "merge"
OUTPUTS_STEP = "outputs"

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


def needs_notes_processing(
    lesson: Lesson,
    notes_input_hash: str,
    force: bool = False,
) -> bool:
    """Decide whether the notes step must (re)run for this lesson.

    Uses `notes_input_hash` (transcript content + model + temperature +
    max_input_chars + prompt version) so any of those changing triggers
    regeneration automatically.
    """
    if force:
        return True

    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    if not _step_log_shows_done(log, NOTES_STEP):
        return True

    latest = log.latest(NOTES_STEP)
    if latest is None or latest.source_hash != notes_input_hash:
        return True
    return not (lesson.output_dir / NOTES_FILENAME).exists()


def record_skipped_notes(
    lesson: Lesson, notes_input_hash: str, started_at: datetime
) -> StepLogEntry:
    """Log a notes step that needed no work this run."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=NOTES_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Nota ja existe e nenhuma entrada mudou.",
        source_hash=notes_input_hash,
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': etapa notes pulada.", lesson.slug)
    return entry


def record_notes_skipped_no_transcript(
    lesson: Lesson, started_at: datetime
) -> StepLogEntry:
    """Log notes as skipped because no transcript is available yet.

    Not a processing failure — the transcription phase is the prerequisite;
    records as SKIPPED so the batch exit code remains driven by whatever caused
    transcription to be absent (e.g. a missing dependency).
    """
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=NOTES_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Transcricao indisponivel — execute a Fase 2 antes.",
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': notes pulada (sem transcricao).", lesson.slug)
    return entry


def process_lesson_notes(
    lesson: Lesson,
    transcript_text: str,
    notes_input_hash: str,
    cfg_llm: LlmConfig,
) -> tuple[str, StepLogEntry]:
    """Generate the lesson note file and record the step outcome.

    The caller must have already decided (via `needs_notes_processing`) that
    this is necessary, and verified Ollama is available. This function does
    not check availability itself, by design — checks only happen once per run.
    Writes atomically: content goes to a .tmp file first, then os.replace().
    """
    started_at = datetime.now()
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME

    note_content = generate_lesson_note(lesson.title, transcript_text, cfg_llm)

    notes_path = lesson.output_dir / NOTES_FILENAME
    tmp_path = notes_path.with_name(notes_path.name + ".tmp")
    try:
        tmp_path.write_text(note_content, encoding="utf-8")
        os.replace(tmp_path, notes_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    entry = StepLogEntry(
        step=NOTES_STEP,
        status=Status.COMPLETED,
        started_at=started_at,
        finished_at=datetime.now(),
        source_hash=notes_input_hash,
    )
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': nota gerada em '%s'.", lesson.slug, notes_path.name)
    return note_content, entry


def needs_notion_processing(
    lesson: Lesson,
    course_output_path: Path,
    notion_hash: str,
    force: bool = False,
) -> bool:
    """Decide whether the notion step must (re)run for this lesson.

    Reprocesses when: --force; the latest 'notion' log entry isn't done;
    its source_hash differs from `notion_hash` (note content, database or
    NOTION_SYNC_VERSION changed); or the local sync state needed to skip
    safely is missing (NOTION_PAGE_INFO.json, this lesson's entry in it, or
    its toggle_block_id) even though the log says it completed.
    """
    if force:
        return True

    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    if not _step_log_shows_done(log, NOTION_STEP):
        return True

    latest = log.latest(NOTION_STEP)
    if latest is None or latest.source_hash != notion_hash:
        return True

    page_info = read_notion_page_info(course_output_path)
    if page_info is None:
        return True
    lesson_info = page_info.lessons.get(lesson.slug)
    if lesson_info is None or not lesson_info.toggle_block_id:
        return True
    return lesson_info.synced_hash != notion_hash


def can_skip_notion_without_network(
    lesson: Lesson,
    course_output_path: Path,
    note_content: str,
    force: bool = False,
    configured_database_id: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """Offline pre-check: can we skip Notion without any HTTP call?

    Uses the database_id cached in NOTION_PAGE_INFO.json to compute a trial
    hash and compare it against the processing log and the per-lesson
    synced_hash. Returns (can_skip, trial_hash, cached_database_id).

    If can_skip is True, call record_skipped_notion(lesson, trial_hash, ...).
    If False, proceed with check_notion_dependencies → needs_notion_processing.

    Pass configured_database_id (cfg.notion.database_id) so an explicit
    database change in config is detected locally without a network call.
    """
    if force:
        return False, None, None

    page_info = read_notion_page_info(course_output_path)
    if page_info is None:
        return False, None, None

    # If a specific database_id is configured and no longer matches the
    # cached one, the target database changed → must resync.
    if configured_database_id is not None and page_info.database_id != configured_database_id:
        return False, None, None

    lesson_info = page_info.lessons.get(lesson.slug)
    if lesson_info is None or not lesson_info.toggle_block_id:
        return False, None, None

    trial_hash = compute_notion_input_hash(note_content, page_info.database_id)

    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    if not _step_log_shows_done(log, NOTION_STEP):
        return False, trial_hash, page_info.database_id

    latest = log.latest(NOTION_STEP)
    if latest is None or latest.source_hash != trial_hash:
        return False, trial_hash, page_info.database_id

    if lesson_info.synced_hash != trial_hash:
        return False, trial_hash, page_info.database_id

    return True, trial_hash, page_info.database_id


def record_skipped_notion(lesson: Lesson, notion_hash: str, started_at: datetime) -> StepLogEntry:
    """Log a notion step that needed no work this run."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=NOTION_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Pagina/toggle do Notion ja sincronizados e nada mudou.",
        source_hash=notion_hash,
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': etapa notion pulada.", lesson.slug)
    return entry


def record_notion_skipped_no_notes(lesson: Lesson, started_at: datetime) -> StepLogEntry:
    """Log notion as skipped because no local lesson note is available yet.

    Not a processing failure — the notes phase (Fase 3) is the prerequisite;
    records as SKIPPED so the batch exit code stays driven by whatever
    caused the note file to be absent.
    """
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=NOTION_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Nota local indisponivel — execute a Fase 3 antes.",
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': notion pulada (sem nota local).", lesson.slug)
    return entry


def record_notion_skipped_disabled(lesson: Lesson, started_at: datetime) -> StepLogEntry:
    """Log notion as skipped because notion.enabled=false in config."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=NOTION_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Notion desabilitado na config (notion.enabled ou notion.auto_send = false).",
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': notion pulada (desabilitado na config).", lesson.slug)
    return entry


def process_lesson_notion(
    course: Course,
    lesson: Lesson,
    note_content: str,
    notion_hash: str,
    cfg_notion: NotionConfig,
    token: str,
    database_id: str,
) -> tuple[NotionPageInfo, StepLogEntry]:
    """Sync this lesson's note to Notion and record the step outcome.

    The caller must have already decided (via `needs_notion_processing`) that
    this is necessary, and verified Notion is available (token + database)
    via `notion.check_notion_dependencies`. This function does not check
    availability itself, by design — checks only happen once per run.
    """
    started_at = datetime.now()
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME

    page_info, _toggle_id = sync_lesson_to_notion(
        course, lesson, note_content, notion_hash, cfg_notion, token, database_id
    )

    entry = StepLogEntry(
        step=NOTION_STEP,
        status=Status.COMPLETED,
        started_at=started_at,
        finished_at=datetime.now(),
        source_hash=notion_hash,
    )
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': sincronizada com o Notion.", lesson.slug)
    return page_info, entry


def needs_ocr_processing(
    lesson: Lesson,
    ocr_input_hash: str,
    cfg_ocr: OcrConfig,
    force: bool = False,
) -> bool:
    """Decide whether the OCR step must (re)run for this lesson.

    Reprocesses when: ``--force``; the latest ``"ocr"`` log entry is not done;
    its source_hash differs from *ocr_input_hash* (video, fps, lang or any
    other config change); any of the four output files is missing; or the
    ``frames/`` directory is absent when ``save_screenshots_local=True``.
    """
    from aulaforge.ocr import (
        CODES_MD_FILENAME,
        COMMANDS_MD_FILENAME,
        OCR_JSON_FILENAME,
        OCR_MD_FILENAME,
    )
    from aulaforge.video_frames import FRAMES_DIR_NAME

    if force:
        return True

    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    if not _step_log_shows_done(log, OCR_STEP):
        return True

    latest = log.latest(OCR_STEP)
    if latest is None or latest.source_hash != ocr_input_hash:
        return True

    for filename in (OCR_JSON_FILENAME, OCR_MD_FILENAME, CODES_MD_FILENAME, COMMANDS_MD_FILENAME):
        if not (lesson.output_dir / filename).exists():
            return True

    return cfg_ocr.save_screenshots_local and not (lesson.output_dir / FRAMES_DIR_NAME).exists()


def record_skipped_ocr(
    lesson: Lesson, ocr_hash: str, started_at: datetime
) -> StepLogEntry:
    """Log an OCR step that needed no work this run."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=OCR_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="OCR ja existe e nenhuma entrada mudou.",
        source_hash=ocr_hash,
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': etapa ocr pulada.", lesson.slug)
    return entry


def record_ocr_skipped_disabled(lesson: Lesson, started_at: datetime) -> StepLogEntry:
    """Log OCR as skipped because ocr.enabled=false in config."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=OCR_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="OCR desabilitado na config (ocr.enabled = false).",
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': ocr pulado (desabilitado na config).", lesson.slug)
    return entry


def process_lesson_ocr(
    lesson: Lesson,
    ocr_input_hash: str,
    cfg_ocr: OcrConfig,
) -> tuple[list[OcrFrameResult], StepLogEntry]:
    """Run OCR for one lesson and record the step outcome.

    The caller must have already decided (via ``needs_ocr_processing``) that
    this is necessary and verified OCR dependencies are available via
    ``ocr.check_ocr_dependencies``.  This function does not check availability
    itself, by design — checks only happen once per batch run.
    """
    from aulaforge.ocr import (
        process_lesson_ocr_frames,
        write_codes_md,
        write_commands_md,
        write_ocr_json,
        write_ocr_md,
    )

    started_at = datetime.now()
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME

    results = process_lesson_ocr_frames(lesson.video_path, lesson.output_dir, cfg_ocr)

    write_ocr_json(lesson.output_dir, results)
    write_ocr_md(lesson.output_dir, results)
    write_codes_md(lesson.output_dir, results)
    write_commands_md(lesson.output_dir, results)

    entry = StepLogEntry(
        step=OCR_STEP,
        status=Status.COMPLETED,
        started_at=started_at,
        finished_at=datetime.now(),
        source_hash=ocr_input_hash,
    )
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info(
        "Aula '%s': OCR concluido (%d frame(s) processados).", lesson.slug, len(results)
    )
    return results, entry


def needs_merge_processing(
    lesson: Lesson,
    merge_input_hash: str,
    force: bool = False,
) -> bool:
    """Decide whether the merge step must (re)run for this lesson.

    Reprocesses when: ``--force``; the latest ``"merge"`` log entry is not done;
    its source_hash differs from *merge_input_hash* (transcript or OCR content
    changed, or config changed); or ``08_MERGE_AUDIO_VIDEO.md`` is absent.
    """
    from aulaforge.merge import MERGE_MD_FILENAME

    if force:
        return True

    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    if not _step_log_shows_done(log, MERGE_STEP):
        return True

    latest = log.latest(MERGE_STEP)
    if latest is None or latest.source_hash != merge_input_hash:
        return True

    return not (lesson.output_dir / MERGE_MD_FILENAME).exists()


def record_skipped_merge(
    lesson: Lesson, merge_hash: str, started_at: datetime
) -> StepLogEntry:
    """Log a merge step that needed no work this run."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=MERGE_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Merge já existe e nenhuma entrada mudou.",
        source_hash=merge_hash,
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': etapa merge pulada.", lesson.slug)
    return entry


def record_merge_skipped_no_inputs(lesson: Lesson, started_at: datetime) -> StepLogEntry:
    """Log merge as skipped because neither transcript nor OCR inputs are available.

    Not a processing failure — the prerequisite phases (2 and/or 5) are
    responsible for providing the inputs; records as SKIPPED_UNCHANGED so the
    batch exit code remains driven by whatever caused those phases to be absent.
    """
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=MERGE_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message=(
            "Sem transcrição com timestamps nem OCR disponíveis — "
            "execute as Fases 2 e/ou 5 antes."
        ),
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': merge pulado (sem entradas disponíveis).", lesson.slug)
    return entry


def record_merge_skipped_disabled(lesson: Lesson, started_at: datetime) -> StepLogEntry:
    """Log merge as skipped because merge.enabled=false in config."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=MERGE_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Merge desabilitado na config (merge.enabled = false).",
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': merge pulado (desabilitado na config).", lesson.slug)
    return entry


def process_lesson_merge(
    lesson: Lesson,
    merge_input_hash: str,
    transcript_raw: str | None,
    ocr_raw: str | None,
    cfg_merge: MergeConfig,
) -> tuple[str, StepLogEntry]:
    """Merge transcript + OCR for one lesson and record the step outcome.

    `transcript_raw` and `ocr_raw` are the raw JSON strings read from disk by
    the caller; None when the corresponding file is absent (partial merge is
    allowed). Raises ValidationError/JSONDecodeError if a file exists but is
    invalid — the caller must NOT pre-filter these as absent.
    """
    from aulaforge.merge import (
        merge_lesson,
        parse_ocr_results,
        parse_transcript_segments,
        write_merge_md,
    )

    started_at = datetime.now()
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME

    segments = parse_transcript_segments(transcript_raw) if transcript_raw is not None else None
    ocr_results = parse_ocr_results(ocr_raw) if ocr_raw is not None else None

    content = merge_lesson(segments, ocr_results, lesson.title, cfg_merge)
    write_merge_md(lesson.output_dir, content)

    entry = StepLogEntry(
        step=MERGE_STEP,
        status=Status.COMPLETED,
        started_at=started_at,
        finished_at=datetime.now(),
        source_hash=merge_input_hash,
    )
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': merge concluído.", lesson.slug)
    return content, entry


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


# ── Phase 7: Outputs ──────────────────────────────────────────────────────────


def needs_outputs_processing(
    lesson: Lesson,
    outputs_hash: str,
    force: bool = False,
) -> bool:
    """Decide whether the outputs step must (re)run for this lesson.

    Reprocesses when: ``--force``; the latest ``"outputs"`` log entry is not
    done; its source_hash differs from *outputs_hash* (any input file changed);
    or any of the 7 output files is absent.
    """
    from aulaforge.outputs import LESSON_OUTPUT_FILENAMES

    if force:
        return True

    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    log = read_processing_log(processing_log_path, lesson.slug)
    if not _step_log_shows_done(log, OUTPUTS_STEP):
        return True

    latest = log.latest(OUTPUTS_STEP)
    if latest is None or latest.source_hash != outputs_hash:
        return True

    return any(not (lesson.output_dir / f).exists() for f in LESSON_OUTPUT_FILENAMES)


def record_skipped_outputs(
    lesson: Lesson, outputs_hash: str, started_at: datetime
) -> StepLogEntry:
    """Log an outputs step that needed no work this run."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=OUTPUTS_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Outputs já existem e nenhuma entrada mudou.",
        source_hash=outputs_hash,
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': etapa outputs pulada.", lesson.slug)
    return entry


def record_outputs_skipped_no_inputs(lesson: Lesson, started_at: datetime) -> StepLogEntry:
    """Log outputs as skipped because none of the four input files are present.

    Not a processing failure — the prerequisite phases are responsible for
    providing the inputs; records as SKIPPED_UNCHANGED so the batch exit code
    is not affected.
    """
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=OUTPUTS_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message=(
            "Nenhum input disponível (09, 08, 06 e 07 ausentes) — "
            "execute as fases anteriores antes."
        ),
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': outputs pulado (sem entradas disponíveis).", lesson.slug)
    return entry


def record_outputs_skipped_disabled(lesson: Lesson, started_at: datetime) -> StepLogEntry:
    """Log outputs as skipped because outputs.enabled=false in config."""
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    entry = StepLogEntry(
        step=OUTPUTS_STEP,
        status=Status.SKIPPED_UNCHANGED,
        started_at=started_at,
        finished_at=datetime.now(),
        message="Outputs desabilitados na config (outputs.enabled = false).",
    )
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': outputs pulado (desabilitado na config).", lesson.slug)
    return entry


def process_lesson_outputs(
    lesson: Lesson,
    outputs_hash: str,
    note_raw: str | None,
    merge_raw: str | None,
    codes_raw: str | None,
    commands_raw: str | None,
    cfg_outputs: OutputsConfig,
) -> tuple[dict[str, str], StepLogEntry]:
    """Generate all 7 per-lesson output files and record the step outcome.

    The caller must have already decided (via ``needs_outputs_processing``)
    that this is necessary. No external dependencies are required.
    Raises on write failure; the caller handles the exception.
    """
    from aulaforge.outputs import build_lesson_outputs, write_lesson_outputs

    started_at = datetime.now()
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    processing_log_path = lesson.output_dir / PROCESSING_LOG_FILENAME

    files = build_lesson_outputs(
        lesson_title=lesson.title,
        note_raw=note_raw,
        merge_raw=merge_raw,
        codes_raw=codes_raw,
        commands_raw=commands_raw,
    )
    write_lesson_outputs(lesson.output_dir, files)

    entry = StepLogEntry(
        step=OUTPUTS_STEP,
        status=Status.COMPLETED,
        started_at=started_at,
        finished_at=datetime.now(),
        source_hash=outputs_hash,
    )
    append_processing_log(processing_log_path, lesson.slug, entry)
    logger.info("Aula '%s': outputs gerados (%d arquivo(s)).", lesson.slug, len(files))
    return files, entry

"""AulaForge CLI — Fases 1–9: foundation, transcrição, notes, Notion, OCR, merge, outputs."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from aulaforge.checkpoints import (
    FOUNDATION_STEP,
    MERGE_STEP,
    NOTES_STEP,
    NOTION_STEP,
    OCR_STEP,
    OUTPUTS_STEP,
    PROCESSING_LOG_FILENAME,
    TRANSCRIPTION_STEP,
    can_skip_notion_without_network,
    needs_merge_processing,
    needs_notes_processing,
    needs_notion_processing,
    needs_ocr_processing,
    needs_outputs_processing,
    needs_transcription_processing,
    process_lesson_foundation,
    process_lesson_merge,
    process_lesson_notes,
    process_lesson_notion,
    process_lesson_ocr,
    process_lesson_outputs,
    process_lesson_transcription,
    read_processing_log,
    record_failed_foundation,
    record_failed_step,
    record_merge_skipped_disabled,
    record_merge_skipped_no_inputs,
    record_notes_skipped_no_transcript,
    record_notion_skipped_disabled,
    record_notion_skipped_no_notes,
    record_ocr_skipped_disabled,
    record_outputs_skipped_disabled,
    record_outputs_skipped_no_inputs,
    record_skipped_merge,
    record_skipped_notes,
    record_skipped_notion,
    record_skipped_ocr,
    record_skipped_outputs,
    record_skipped_transcription,
)
from aulaforge.config import load_config
from aulaforge.discovery import discover_course
from aulaforge.logging_setup import ensure_utf8_console, setup_logging
from aulaforge.merge import compute_merge_input_hash
from aulaforge.models import Status, StepLogEntry
from aulaforge.notes import compute_notes_input_hash, get_transcript_for_notes
from aulaforge.notion import (
    NotionAvailability,
    check_notion_dependencies,
    compute_notion_input_hash,
    get_note_for_sync,
)
from aulaforge.ocr import OCR_JSON_FILENAME, check_ocr_dependencies, compute_ocr_input_hash
from aulaforge.ollama_client import check_ollama_dependencies
from aulaforge.outputs import (
    compute_outputs_input_hash,
    has_any_input,
    read_lesson_inputs,
    write_course_outputs,
)
from aulaforge.reports import write_batch_summary
from aulaforge.transcription import (
    TIMESTAMPED_TRANSCRIPT_FILENAME,
    check_transcription_dependencies,
    load_whisper_model,
    whisper_language_hint,
)

app = typer.Typer(
    name="aulaforge",
    help="Ferramenta local-first para transformar aulas em video em conhecimento estruturado.",
    add_completion=False,
)
console = Console()

# Exit codes: 0 = tudo certo; 1 = alguma etapa falhou por motivo de
# processamento real; 2 = nenhuma falha de processamento ocorreu, mas a
# transcricao nao pode rodar por dependencia local ausente (ffmpeg/whisper).
PROCESSING_FAILURE_EXIT_CODE = 1
DEPENDENCY_MISSING_EXIT_CODE = 2


@app.callback()
def main() -> None:
    """AulaForge: processa cursos em video localmente, por fases."""
    ensure_utf8_console()


_COURSE_PATH_ARGUMENT = typer.Argument(
    ...,
    exists=True,
    file_okay=False,
    dir_okay=True,
    help="Pasta do curso contendo os videos das aulas.",
)
_CONFIG_OPTION = typer.Option(
    None,
    "--config",
    help="Arquivo YAML de config. Default: ./aulaforge.yaml, se existir; senao, defaults internos.",
)
_FORCE_OPTION = typer.Option(
    False,
    "--force",
    help="Reprocessa todas as etapas mesmo se o video e as entradas nao mudaram.",
)
_RESUME_OPTION = typer.Option(
    False,
    "--resume",
    help=(
        "Reprocessa apenas aulas cujo ultimo status de algum step seja FAILED. "
        "Entradas antigas de falhas seguidas de sucesso nao ativam o --resume. "
        "Se nao houver processing_log.json, processa normalmente. "
        "--force tem precedencia sobre --resume."
    ),
)


def _should_skip_with_resume(lesson_output_dir: Path, lesson_slug: str) -> bool:
    """Com --resume ativo: True = pular a aula.

    Considera apenas a entrada MAIS RECENTE de cada step. Um failed antigo
    seguido de completed/skipped_unchanged não ativa o --resume.

    Retorna False (não pular) quando:
    - processing_log.json não existe (aula nunca processada → processar normalmente);
    - ao menos um step tem último status FAILED.
    """
    log_path = lesson_output_dir / PROCESSING_LOG_FILENAME
    if not log_path.exists():
        return False
    log = read_processing_log(log_path, lesson_slug)
    seen_steps = {entry.step for entry in log.steps}
    for step in seen_steps:
        latest = log.latest(step)
        if latest is not None and latest.status == Status.FAILED:
            return False
    return True


@app.command("process-course")
def process_course(
    course_path: Path = _COURSE_PATH_ARGUMENT,
    config: Path | None = _CONFIG_OPTION,
    force: bool = _FORCE_OPTION,
    resume: bool = _RESUME_OPTION,
) -> None:
    """Descobre, ordena, indexa, transcreve e anota as aulas de um curso.

    Exit codes: 0 = OK; 1 = alguma etapa falhou por motivo de processamento;
    2 = nenhuma falha de processamento, mas uma dependencia local esta ausente
    (ffmpeg, whisper, Ollama) e pelo menos uma aula precisava daquela etapa.
    """
    try:
        cfg = load_config(config)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Erro de configuracao:[/bold red] {exc}")
        raise typer.Exit(code=PROCESSING_FAILURE_EXIT_CODE) from exc

    course = discover_course(course_path, cfg.project.output_dir)

    logger = setup_logging(log_dir=course.output_path)
    logger.info("Curso '%s': %d aula(s) encontrada(s).", course.name, len(course.lessons))

    if not course.lessons:
        logger.warning("Nenhum video encontrado em '%s'.", course_path)
        raise typer.Exit(code=0)

    # skip_if_unchanged=False in config behaves like --force for every lesson.
    effective_force = force or not cfg.processing.skip_if_unchanged
    language_hint = whisper_language_hint(cfg.project.language)

    # Dependency checks and model load are all lazy: they only happen once,
    # the first time a lesson actually needs that step. A fully up-to-date
    # course never touches ffmpeg/whisper/Ollama at all.
    dependency_errors: list[str] | None = None
    ollama_errors: list[str] | None = None
    notion_availability: NotionAvailability | None = None
    ocr_dependency_errors: list[str] | None = None
    model = None

    entries: dict[str, dict[str, StepLogEntry]] = {}
    had_processing_failure = False
    had_dependency_failure = False

    if resume and not effective_force:
        logger.info("Modo --resume ativo: reprocessa apenas aulas com step FAILED.")

    for lesson in course.lessons:
        # --resume: pula aulas sem step FAILED (exceto se --force também foi passado)
        if resume and not effective_force and _should_skip_with_resume(
            lesson.output_dir, lesson.slug
        ):
            logger.info("Aula '%s': sem falhas no log; pulada por --resume.", lesson.slug)
            continue

        lesson_entries: dict[str, StepLogEntry] = {}

        started_at = datetime.now()
        try:
            info, foundation_entry = process_lesson_foundation(lesson, force=effective_force)
        except Exception as exc:
            # A single lesson must never abort the whole batch run.
            lesson_entries[FOUNDATION_STEP] = record_failed_foundation(lesson, started_at, exc)
            entries[lesson.slug] = lesson_entries
            had_processing_failure = True
            if not cfg.processing.continue_on_error:
                write_batch_summary(course, entries)
                raise
            continue
        lesson_entries[FOUNDATION_STEP] = foundation_entry

        started_at = datetime.now()
        try:
            needs_transcription = needs_transcription_processing(
                lesson, info.hash, cfg.transcription, force=effective_force
            )
        except Exception as exc:
            lesson_entries[TRANSCRIPTION_STEP] = record_failed_step(
                lesson, TRANSCRIPTION_STEP, started_at, exc
            )
            entries[lesson.slug] = lesson_entries
            had_processing_failure = True
            if not cfg.processing.continue_on_error:
                write_batch_summary(course, entries)
                raise
            continue

        if not needs_transcription:
            lesson_entries[TRANSCRIPTION_STEP] = record_skipped_transcription(
                lesson, info.hash, started_at
            )
        else:
            if dependency_errors is None:
                dependency_errors = check_transcription_dependencies()

            if dependency_errors:
                lesson_entries[TRANSCRIPTION_STEP] = record_failed_step(
                    lesson,
                    TRANSCRIPTION_STEP,
                    started_at,
                    RuntimeError("; ".join(dependency_errors)),
                )
                had_dependency_failure = True
            else:
                # Carrega o modelo uma única vez por batch run (mantido entre retries)
                if model is None:
                    try:
                        model = load_whisper_model(cfg.transcription.model)
                    except Exception as exc:
                        lesson_entries[TRANSCRIPTION_STEP] = record_failed_step(
                            lesson, TRANSCRIPTION_STEP, started_at, exc
                        )
                        had_processing_failure = True
                        if not cfg.processing.continue_on_error:
                            entries[lesson.slug] = lesson_entries
                            write_batch_summary(course, entries)
                            raise

                if model is not None:
                    _last_exc: Exception | None = None
                    for _attempt in range(1, cfg.processing.retry_attempts + 1):
                        try:
                            _, transcription_entry = process_lesson_transcription(
                                lesson,
                                model,
                                info.hash,
                                cfg.transcription,
                                cfg.processing.chunk_minutes,
                                language_hint,
                            )
                            lesson_entries[TRANSCRIPTION_STEP] = transcription_entry
                            _last_exc = None
                            break
                        except Exception as exc:
                            _last_exc = exc
                            if _attempt < cfg.processing.retry_attempts:
                                _wait = 2 * _attempt
                                logger.warning(
                                    "Aula '%s' (transcription): tentativa %d/%d falhou: %s. "
                                    "Aguardando %ds...",
                                    lesson.slug, _attempt, cfg.processing.retry_attempts,
                                    exc, _wait,
                                )
                                time.sleep(_wait)
                    if _last_exc is not None:
                        lesson_entries[TRANSCRIPTION_STEP] = record_failed_step(
                            lesson, TRANSCRIPTION_STEP, started_at, _last_exc
                        )
                        had_processing_failure = True
                        if not cfg.processing.continue_on_error:
                            entries[lesson.slug] = lesson_entries
                            write_batch_summary(course, entries)
                            raise _last_exc

        # --- Phase 3: Notes ---
        notes_started_at = datetime.now()
        transcript_text = get_transcript_for_notes(lesson)

        if transcript_text is None:
            # Transcription prerequisite is absent — not a notes processing
            # failure; the transcription step already explains why.
            lesson_entries[NOTES_STEP] = record_notes_skipped_no_transcript(
                lesson, notes_started_at
            )
        else:
            notes_hash = compute_notes_input_hash(transcript_text, cfg.llm)
            try:
                needs_notes = needs_notes_processing(
                    lesson, notes_hash, force=effective_force
                )
            except Exception as exc:
                lesson_entries[NOTES_STEP] = record_failed_step(
                    lesson, NOTES_STEP, notes_started_at, exc
                )
                entries[lesson.slug] = lesson_entries
                had_processing_failure = True
                if not cfg.processing.continue_on_error:
                    write_batch_summary(course, entries)
                    raise
                continue

            if not needs_notes:
                lesson_entries[NOTES_STEP] = record_skipped_notes(
                    lesson, notes_hash, notes_started_at
                )
            else:
                if ollama_errors is None:
                    ollama_errors = check_ollama_dependencies(
                        cfg.llm.base_url, cfg.llm.model
                    )

                if ollama_errors:
                    lesson_entries[NOTES_STEP] = record_failed_step(
                        lesson,
                        NOTES_STEP,
                        notes_started_at,
                        RuntimeError("; ".join(ollama_errors)),
                    )
                    had_dependency_failure = True
                else:
                    _last_exc = None
                    for _attempt in range(1, cfg.processing.retry_attempts + 1):
                        try:
                            _, notes_entry = process_lesson_notes(
                                lesson, transcript_text, notes_hash, cfg.llm
                            )
                            lesson_entries[NOTES_STEP] = notes_entry
                            _last_exc = None
                            break
                        except Exception as exc:
                            _last_exc = exc
                            if _attempt < cfg.processing.retry_attempts:
                                _wait = 2 * _attempt
                                logger.warning(
                                    "Aula '%s' (notes): tentativa %d/%d falhou: %s. "
                                    "Aguardando %ds...",
                                    lesson.slug, _attempt, cfg.processing.retry_attempts,
                                    exc, _wait,
                                )
                                time.sleep(_wait)
                    if _last_exc is not None:
                        lesson_entries[NOTES_STEP] = record_failed_step(
                            lesson, NOTES_STEP, notes_started_at, _last_exc
                        )
                        had_processing_failure = True
                        if not cfg.processing.continue_on_error:
                            entries[lesson.slug] = lesson_entries
                            write_batch_summary(course, entries)
                            raise _last_exc

        # --- Phase 4: Notion ---
        notion_started_at = datetime.now()
        if not (cfg.notion.enabled and cfg.notion.auto_send):
            lesson_entries[NOTION_STEP] = record_notion_skipped_disabled(lesson, notion_started_at)
        else:
            note_content = get_note_for_sync(lesson)

            if note_content is None:
                # Notes prerequisite is absent — not a notion processing
                # failure; the notes step already explains why.
                lesson_entries[NOTION_STEP] = record_notion_skipped_no_notes(
                    lesson, notion_started_at
                )
            else:
                # Fast offline pre-check: skip without any HTTP call if the
                # local cache (NOTION_PAGE_INFO.json + processing_log.json)
                # proves nothing changed. Mirrors the Ollama pattern where
                # check_ollama_dependencies is only called if work is needed.
                can_skip_offline, trial_hash, _ = can_skip_notion_without_network(
                    lesson,
                    course.output_path,
                    note_content,
                    force=effective_force,
                    configured_database_id=cfg.notion.database_id,
                )
                if can_skip_offline and trial_hash is not None:
                    lesson_entries[NOTION_STEP] = record_skipped_notion(
                        lesson, trial_hash, notion_started_at
                    )
                else:
                    # At least this lesson needs sync: check dependencies
                    # lazily (at most once per batch run).
                    if notion_availability is None:
                        notion_availability = check_notion_dependencies(cfg.notion)

                    if notion_availability.errors:
                        lesson_entries[NOTION_STEP] = record_failed_step(
                            lesson,
                            NOTION_STEP,
                            notion_started_at,
                            RuntimeError("; ".join(notion_availability.errors)),
                        )
                        had_dependency_failure = True
                    else:
                        token = notion_availability.token
                        database_id = notion_availability.database_id
                        assert token is not None and database_id is not None, (
                            "check_notion_dependencies must populate token/database_id "
                            "whenever it returns no errors"
                        )
                        notion_hash = compute_notion_input_hash(note_content, database_id)

                        try:
                            needs_notion = needs_notion_processing(
                                lesson, course.output_path, notion_hash, force=effective_force
                            )
                        except Exception as exc:
                            lesson_entries[NOTION_STEP] = record_failed_step(
                                lesson, NOTION_STEP, notion_started_at, exc
                            )
                            entries[lesson.slug] = lesson_entries
                            had_processing_failure = True
                            if not cfg.processing.continue_on_error:
                                write_batch_summary(course, entries)
                                raise
                            continue

                        if not needs_notion:
                            lesson_entries[NOTION_STEP] = record_skipped_notion(
                                lesson, notion_hash, notion_started_at
                            )
                        else:
                            try:
                                _, notion_entry = process_lesson_notion(
                                    course,
                                    lesson,
                                    note_content,
                                    notion_hash,
                                    cfg.notion,
                                    token,
                                    database_id,
                                )
                                lesson_entries[NOTION_STEP] = notion_entry
                            except Exception as exc:
                                lesson_entries[NOTION_STEP] = record_failed_step(
                                    lesson, NOTION_STEP, notion_started_at, exc
                                )
                                had_processing_failure = True
                                if not cfg.processing.continue_on_error:
                                    entries[lesson.slug] = lesson_entries
                                    write_batch_summary(course, entries)
                                    raise

        # --- Phase 5: OCR ---
        ocr_started_at = datetime.now()
        if not cfg.ocr.enabled:
            lesson_entries[OCR_STEP] = record_ocr_skipped_disabled(lesson, ocr_started_at)
        else:
            ocr_input_hash = compute_ocr_input_hash(info.hash, cfg.ocr)
            try:
                needs_ocr = needs_ocr_processing(
                    lesson, ocr_input_hash, cfg.ocr, force=effective_force
                )
            except Exception as exc:
                lesson_entries[OCR_STEP] = record_failed_step(
                    lesson, OCR_STEP, ocr_started_at, exc
                )
                entries[lesson.slug] = lesson_entries
                had_processing_failure = True
                if not cfg.processing.continue_on_error:
                    write_batch_summary(course, entries)
                    raise
                continue

            if not needs_ocr:
                lesson_entries[OCR_STEP] = record_skipped_ocr(
                    lesson, ocr_input_hash, ocr_started_at
                )
            else:
                if ocr_dependency_errors is None:
                    ocr_dependency_errors = check_ocr_dependencies(cfg.ocr.lang)

                if ocr_dependency_errors:
                    lesson_entries[OCR_STEP] = record_failed_step(
                        lesson,
                        OCR_STEP,
                        ocr_started_at,
                        RuntimeError("; ".join(ocr_dependency_errors)),
                    )
                    had_dependency_failure = True
                else:
                    try:
                        _, ocr_entry = process_lesson_ocr(
                            lesson, ocr_input_hash, cfg.ocr
                        )
                        lesson_entries[OCR_STEP] = ocr_entry
                    except Exception as exc:
                        lesson_entries[OCR_STEP] = record_failed_step(
                            lesson, OCR_STEP, ocr_started_at, exc
                        )
                        had_processing_failure = True
                        if not cfg.processing.continue_on_error:
                            entries[lesson.slug] = lesson_entries
                            write_batch_summary(course, entries)
                            raise

        # --- Phase 6: Merge ---
        merge_started_at = datetime.now()
        if not cfg.merge.enabled:
            lesson_entries[MERGE_STEP] = record_merge_skipped_disabled(lesson, merge_started_at)
        else:
            transcript_path = lesson.output_dir / TIMESTAMPED_TRANSCRIPT_FILENAME
            ocr_path = lesson.output_dir / OCR_JSON_FILENAME
            transcript_raw = (
                transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else None
            )
            ocr_raw = ocr_path.read_text(encoding="utf-8") if ocr_path.exists() else None

            if transcript_raw is None and ocr_raw is None:
                lesson_entries[MERGE_STEP] = record_merge_skipped_no_inputs(
                    lesson, merge_started_at
                )
            else:
                merge_hash = compute_merge_input_hash(transcript_raw, ocr_raw, cfg.merge)
                try:
                    needs_merge = needs_merge_processing(
                        lesson, merge_hash, force=effective_force
                    )
                except Exception as exc:
                    lesson_entries[MERGE_STEP] = record_failed_step(
                        lesson, MERGE_STEP, merge_started_at, exc
                    )
                    entries[lesson.slug] = lesson_entries
                    had_processing_failure = True
                    if not cfg.processing.continue_on_error:
                        write_batch_summary(course, entries)
                        raise
                    continue

                if not needs_merge:
                    lesson_entries[MERGE_STEP] = record_skipped_merge(
                        lesson, merge_hash, merge_started_at
                    )
                else:
                    try:
                        _, merge_entry = process_lesson_merge(
                            lesson, merge_hash, transcript_raw, ocr_raw, cfg.merge
                        )
                        lesson_entries[MERGE_STEP] = merge_entry
                    except Exception as exc:
                        lesson_entries[MERGE_STEP] = record_failed_step(
                            lesson, MERGE_STEP, merge_started_at, exc
                        )
                        had_processing_failure = True
                        if not cfg.processing.continue_on_error:
                            entries[lesson.slug] = lesson_entries
                            write_batch_summary(course, entries)
                            raise

        # --- Phase 7: Outputs ---
        outputs_started_at = datetime.now()
        if not cfg.outputs.enabled:
            lesson_entries[OUTPUTS_STEP] = record_outputs_skipped_disabled(
                lesson, outputs_started_at
            )
        else:
            note_raw, merge_raw, codes_raw, commands_raw = read_lesson_inputs(lesson)
            if not has_any_input(note_raw, merge_raw, codes_raw, commands_raw):
                lesson_entries[OUTPUTS_STEP] = record_outputs_skipped_no_inputs(
                    lesson, outputs_started_at
                )
            else:
                outputs_hash = compute_outputs_input_hash(
                    note_raw, merge_raw, codes_raw, commands_raw, cfg.outputs
                )
                try:
                    needs_outputs = needs_outputs_processing(
                        lesson, outputs_hash, force=effective_force
                    )
                except Exception as exc:
                    lesson_entries[OUTPUTS_STEP] = record_failed_step(
                        lesson, OUTPUTS_STEP, outputs_started_at, exc
                    )
                    entries[lesson.slug] = lesson_entries
                    had_processing_failure = True
                    if not cfg.processing.continue_on_error:
                        write_batch_summary(course, entries)
                        raise
                    continue

                if not needs_outputs:
                    lesson_entries[OUTPUTS_STEP] = record_skipped_outputs(
                        lesson, outputs_hash, outputs_started_at
                    )
                else:
                    try:
                        _, outputs_entry = process_lesson_outputs(
                            lesson,
                            outputs_hash,
                            note_raw,
                            merge_raw,
                            codes_raw,
                            commands_raw,
                            cfg.outputs,
                        )
                        lesson_entries[OUTPUTS_STEP] = outputs_entry
                    except Exception as exc:
                        lesson_entries[OUTPUTS_STEP] = record_failed_step(
                            lesson, OUTPUTS_STEP, outputs_started_at, exc
                        )
                        had_processing_failure = True
                        if not cfg.processing.continue_on_error:
                            entries[lesson.slug] = lesson_entries
                            write_batch_summary(course, entries)
                            raise

        entries[lesson.slug] = lesson_entries

    write_batch_summary(course, entries)

    # --- Course-level outputs (after all lessons) ---
    if cfg.outputs.enabled:
        lessons_with_outputs = [
            lesson
            for lesson in course.lessons
            if entries.get(lesson.slug, {}).get(OUTPUTS_STEP) is not None
            and entries[lesson.slug][OUTPUTS_STEP].status
            in (Status.COMPLETED, Status.SKIPPED_UNCHANGED)
        ]
        write_course_outputs(course, lessons_with_outputs)

    all_step_entries = [entry for steps in entries.values() for entry in steps.values()]
    completed = sum(1 for e in all_step_entries if e.status == Status.COMPLETED)
    skipped = sum(1 for e in all_step_entries if e.status == Status.SKIPPED_UNCHANGED)
    failed = sum(1 for e in all_step_entries if e.status == Status.FAILED)
    console.print(
        f"[bold]{course.name}[/bold]: {completed} etapa(s) concluida(s), "
        f"{skipped} pulada(s), {failed} com falha."
    )

    if had_processing_failure:
        raise typer.Exit(code=PROCESSING_FAILURE_EXIT_CODE)
    if had_dependency_failure:
        raise typer.Exit(code=DEPENDENCY_MISSING_EXIT_CODE)

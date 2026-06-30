"""AulaForge CLI (Fase 1: foundation; Fase 2: transcricao; Fase 3: notes)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from aulaforge.checkpoints import (
    FOUNDATION_STEP,
    NOTES_STEP,
    TRANSCRIPTION_STEP,
    needs_notes_processing,
    needs_transcription_processing,
    process_lesson_foundation,
    process_lesson_notes,
    process_lesson_transcription,
    record_failed_foundation,
    record_failed_step,
    record_notes_skipped_no_transcript,
    record_skipped_notes,
    record_skipped_transcription,
    write_batch_summary,
)
from aulaforge.config import load_config
from aulaforge.discovery import discover_course
from aulaforge.logging_setup import ensure_utf8_console, setup_logging
from aulaforge.models import Status, StepLogEntry
from aulaforge.notes import compute_notes_input_hash, get_transcript_for_notes
from aulaforge.ollama_client import check_ollama_dependencies
from aulaforge.transcription import (
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


@app.command("process-course")
def process_course(
    course_path: Path = _COURSE_PATH_ARGUMENT,
    config: Path | None = _CONFIG_OPTION,
    force: bool = _FORCE_OPTION,
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
    model = None

    entries: dict[str, dict[str, StepLogEntry]] = {}
    had_processing_failure = False
    had_dependency_failure = False

    for lesson in course.lessons:
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
                try:
                    if model is None:
                        model = load_whisper_model(cfg.transcription.model)
                    _, transcription_entry = process_lesson_transcription(
                        lesson,
                        model,
                        info.hash,
                        cfg.transcription,
                        cfg.processing.chunk_minutes,
                        language_hint,
                    )
                    lesson_entries[TRANSCRIPTION_STEP] = transcription_entry
                except Exception as exc:
                    lesson_entries[TRANSCRIPTION_STEP] = record_failed_step(
                        lesson, TRANSCRIPTION_STEP, started_at, exc
                    )
                    had_processing_failure = True
                    if not cfg.processing.continue_on_error:
                        entries[lesson.slug] = lesson_entries
                        write_batch_summary(course, entries)
                        raise

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
                    try:
                        _, notes_entry = process_lesson_notes(
                            lesson, transcript_text, notes_hash, cfg.llm
                        )
                        lesson_entries[NOTES_STEP] = notes_entry
                    except Exception as exc:
                        lesson_entries[NOTES_STEP] = record_failed_step(
                            lesson, NOTES_STEP, notes_started_at, exc
                        )
                        had_processing_failure = True
                        if not cfg.processing.continue_on_error:
                            entries[lesson.slug] = lesson_entries
                            write_batch_summary(course, entries)
                            raise

        entries[lesson.slug] = lesson_entries

    write_batch_summary(course, entries)

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

"""AulaForge command-line interface (Phase 1: foundation only)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from aulaforge.checkpoints import (
    process_lesson_foundation,
    record_failed_foundation,
    write_batch_summary,
)
from aulaforge.config import load_config
from aulaforge.discovery import discover_course
from aulaforge.logging_setup import ensure_utf8_console, setup_logging
from aulaforge.models import StepLogEntry

app = typer.Typer(
    name="aulaforge",
    help="Ferramenta local-first para transformar aulas em video em conhecimento estruturado.",
    add_completion=False,
)
console = Console()


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
    help="Reprocessa a etapa foundation mesmo se o video nao mudou.",
)


@app.command("process-course")
def process_course(
    course_path: Path = _COURSE_PATH_ARGUMENT,
    config: Path | None = _CONFIG_OPTION,
    force: bool = _FORCE_OPTION,
) -> None:
    """Descobre, ordena e indexa as aulas de um curso (Fase 1: foundation)."""
    try:
        cfg = load_config(config)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Erro de configuracao:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    course = discover_course(course_path, cfg.project.output_dir)

    logger = setup_logging(log_dir=course.output_path)
    logger.info("Curso '%s': %d aula(s) encontrada(s).", course.name, len(course.lessons))

    if not course.lessons:
        logger.warning("Nenhum video encontrado em '%s'.", course_path)
        raise typer.Exit(code=0)

    # skip_if_unchanged=False in config behaves like --force for every lesson.
    effective_force = force or not cfg.processing.skip_if_unchanged

    entries: dict[str, StepLogEntry] = {}
    for lesson in course.lessons:
        started_at = datetime.now()
        try:
            _, entry = process_lesson_foundation(lesson, force=effective_force)
        except Exception as exc:
            # A single lesson must never abort the whole batch run.
            entry = record_failed_foundation(lesson, started_at, exc)
            entries[lesson.slug] = entry
            if not cfg.processing.continue_on_error:
                write_batch_summary(course, entries)
                raise
            continue
        entries[lesson.slug] = entry

    write_batch_summary(course, entries)

    completed = sum(1 for e in entries.values() if e.status.value == "completed")
    skipped = sum(1 for e in entries.values() if e.status.value == "skipped_unchanged")
    failed = sum(1 for e in entries.values() if e.status.value == "failed")
    console.print(
        f"[bold]{course.name}[/bold]: {completed} processada(s), "
        f"{skipped} pulada(s), {failed} com falha."
    )
    if failed:
        raise typer.Exit(code=1)

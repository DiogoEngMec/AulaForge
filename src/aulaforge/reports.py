"""Relatórios de batch para AulaForge (Fase 8).

Extrai write_batch_summary de checkpoints.py e adiciona:
- duração por step em cada célula (Xs);
- linha de totais (concluídas / puladas / falhas);
- tempo médio por etapa (apenas COMPLETED + FAILED).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from aulaforge.models import Course, Status, StepLogEntry

logger = logging.getLogger("aulaforge.reports")


def _duration_seconds(entry: StepLogEntry) -> float:
    return (entry.finished_at - entry.started_at).total_seconds()


def _cell(entry: StepLogEntry) -> str:
    dur = _duration_seconds(entry)
    return f"{entry.status.value} ({dur:.1f}s)"


def write_batch_summary(course: Course, entries: dict[str, dict[str, StepLogEntry]]) -> None:
    """Escreve batch_log.json e batch_report.md no diretório de saída do curso.

    `entries` mapeia slug da aula -> {nome do step -> StepLogEntry}. Colunas
    são descobertas dinamicamente a partir dos steps presentes — uma nova fase
    adicionando um step não requer mudanças aqui.

    Melhorias em relação ao formato original (Fases 1-7):
    - Cada célula mostra duração em segundos: `status (Xs)`.
    - Linha de resumo com totais no rodapé.
    - Tempo médio por etapa (apenas steps COMPLETED ou FAILED).
    """
    course.output_path.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat()

    # JSON — contrato estável (sem timing, para consumo programático)
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

    # Markdown com timing
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
        row = [slug]
        for step in all_steps:
            row.append(_cell(steps[step]) if step in steps else "-")
        lines.append(f"| {' | '.join(row)} |")

    # Totais
    all_entries = [entry for steps in entries.values() for entry in steps.values()]
    n_completed = sum(1 for e in all_entries if e.status == Status.COMPLETED)
    n_skipped = sum(1 for e in all_entries if e.status == Status.SKIPPED_UNCHANGED)
    n_failed = sum(1 for e in all_entries if e.status == Status.FAILED)
    lines.append("")
    lines.append(
        f"**Resumo:** {n_completed} concluída(s) · {n_skipped} pulada(s) · {n_failed} com falha"
    )

    # Tempo médio por etapa (apenas COMPLETED e FAILED)
    step_times: dict[str, list[float]] = {}
    for steps in entries.values():
        for step, entry in steps.items():
            if entry.status in (Status.COMPLETED, Status.FAILED):
                step_times.setdefault(step, []).append(_duration_seconds(entry))

    if step_times:
        avg_parts = [
            f"{step}: {sum(durs) / len(durs):.1f}s"
            for step, durs in sorted(step_times.items())
        ]
        lines.append(f"**Tempo médio:** {' · '.join(avg_parts)}")

    (course.output_path / "batch_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

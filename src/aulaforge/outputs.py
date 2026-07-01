"""Geração dos artefatos finais Claude Code / Codex (Fase 7).

Lê os artefatos já gerados pelas fases anteriores (09_ANOTACAO_NOTION.md,
08_MERGE_AUDIO_VIDEO.md, 06_CODIGOS_DETECTADOS.md, 07_COMANDOS_TERMINAL.md)
e produz arquivos 10–16 por aula e 5 arquivos por curso.

Não depende de Whisper, FFmpeg, Tesseract, Ollama ou Notion.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from aulaforge.config import OutputsConfig
from aulaforge.models import Course, Lesson

logger = logging.getLogger("aulaforge.outputs")

# ── Filenames (matching LOCAL_STORAGE_STRUCTURE.md) ──────────────────────────

CLAUDE_CODE_CONTEXT_FILENAME = "10_CLAUDE_CODE_CONTEXT.md"
CODEX_CONTEXT_FILENAME = "11_CODEX_CONTEXT.md"
PROMPTS_PRONTOS_FILENAME = "12_PROMPTS_PRONTOS.md"
AGENTES_SUGERIDOS_FILENAME = "13_AGENTES_SUGERIDOS.md"
SKILLS_SUGERIDAS_FILENAME = "14_SKILLS_SUGERIDAS.md"
IDEIAS_DE_PROJETOS_FILENAME = "15_IDEIAS_DE_PROJETOS.md"
IMPLEMENTATION_PLAN_FILENAME = "16_IMPLEMENTATION_PLAN.md"

# Ordered list used to check if all 7 lesson outputs exist.
LESSON_OUTPUT_FILENAMES = [
    CLAUDE_CODE_CONTEXT_FILENAME,
    CODEX_CONTEXT_FILENAME,
    PROMPTS_PRONTOS_FILENAME,
    AGENTES_SUGERIDOS_FILENAME,
    SKILLS_SUGERIDAS_FILENAME,
    IDEIAS_DE_PROJETOS_FILENAME,
    IMPLEMENTATION_PLAN_FILENAME,
]

# Input filenames (from previous phases)
_NOTES_FILENAME = "09_ANOTACAO_NOTION.md"
_MERGE_FILENAME = "08_MERGE_AUDIO_VIDEO.md"
_CODES_FILENAME = "06_CODIGOS_DETECTADOS.md"
_COMMANDS_FILENAME = "07_COMANDOS_TERMINAL.md"

OUTPUTS_VERSION = "v1"

_PLACEHOLDER = "_[Não disponível — execute as fases anteriores para gerar este conteúdo.]_"


# ── Section extraction ────────────────────────────────────────────────────────


def _normalize(s: str) -> str:
    """Lowercase + remove diacritics for fuzzy heading matching."""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    return ascii_only.lower().strip()


def extract_section(content: str, section_name: str) -> str:
    """Extract the body under a '## <section_name>' heading.

    Matching is case-insensitive and diacritic-insensitive so variations like
    'Indice com Timestamps' and 'Índice com Timestamps' both resolve.
    Returns '' when the heading is not found.
    """
    norm_target = _normalize(section_name)
    # Split on any ## heading, keeping the headings
    parts = re.split(r"^(##\s+[^\n]+)", content, flags=re.MULTILINE)
    for i in range(1, len(parts) - 1, 2):
        heading_text = re.sub(r"^##\s+", "", parts[i])
        if _normalize(heading_text) == norm_target:
            body = parts[i + 1] if i + 1 < len(parts) else ""
            return body.strip()
    return ""


# ── Hash ─────────────────────────────────────────────────────────────────────


def compute_outputs_input_hash(
    note_raw: str | None,
    merge_raw: str | None,
    codes_raw: str | None,
    commands_raw: str | None,
    cfg: OutputsConfig,
) -> str:
    """SHA256 of all inputs + config that affects the output.

    Uses JSON with sort_keys=True for a stable, structured serialization so
    any change in any input or relevant config field triggers reprocessing.
    """
    payload: dict[str, object] = {
        "version": OUTPUTS_VERSION,
        "config": {
            "max_implementation_plan_chars": cfg.max_implementation_plan_chars,
        },
        "inputs": {
            "note": note_raw if note_raw is not None else "no_notes",
            "merge": merge_raw if merge_raw is not None else "no_merge",
            "codes": codes_raw if codes_raw is not None else "no_codes",
            "commands": commands_raw if commands_raw is not None else "no_commands",
        },
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ── I/O helpers ───────────────────────────────────────────────────────────────


def read_lesson_inputs(
    lesson: Lesson,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Read the four input files for Phase 7.

    Returns (note_raw, merge_raw, codes_raw, commands_raw); each is None when
    the file does not exist on disk.
    """
    def _read(name: str) -> str | None:
        p = lesson.output_dir / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    return (
        _read(_NOTES_FILENAME),
        _read(_MERGE_FILENAME),
        _read(_CODES_FILENAME),
        _read(_COMMANDS_FILENAME),
    )


def has_any_input(
    note_raw: str | None,
    merge_raw: str | None,
    codes_raw: str | None,
    commands_raw: str | None,
) -> bool:
    """True if at least one of the four input files is present."""
    return any(x is not None for x in (note_raw, merge_raw, codes_raw, commands_raw))


# ── Source header helpers ─────────────────────────────────────────────────────


def _sources_list(
    note_raw: str | None,
    merge_raw: str | None,
    codes_raw: str | None,
    commands_raw: str | None,
) -> str:
    """One-line list of sources actually used, for the '> Fontes:' header."""
    parts = []
    if note_raw is not None:
        parts.append("09_ANOTACAO_NOTION.md (Fase 3/Ollama)")
    if merge_raw is not None:
        parts.append("08_MERGE_AUDIO_VIDEO.md (Fase 6)")
    if codes_raw is not None:
        parts.append("06_CODIGOS_DETECTADOS.md (Fase 5/OCR)")
    if commands_raw is not None:
        parts.append("07_COMANDOS_TERMINAL.md (Fase 5/OCR)")
    return " | ".join(parts) if parts else "nenhuma fonte disponível"


def _header(lesson_title: str, sources: str, timestamp: str) -> list[str]:
    return [
        "> Gerado automaticamente por AulaForge — Fase 7.",
        f"> Fontes: {sources}",
        f"> Aula: {lesson_title} | Processado em: {timestamp}",
        "",
    ]


# ── Per-lesson output generators ──────────────────────────────────────────────


def _gen_claude_code_context(
    lesson_title: str,
    note_raw: str | None,
    merge_raw: str | None,
    codes_raw: str | None,
    commands_raw: str | None,
    timestamp: str,
) -> str:
    sources = _sources_list(note_raw, merge_raw, codes_raw, commands_raw)
    lines: list[str] = [f"# Claude Code Context — {lesson_title}", ""]
    lines.extend(_header(lesson_title, sources, timestamp))

    def _note_sec(name: str) -> str:
        if note_raw is None:
            return _PLACEHOLDER
        val = extract_section(note_raw, name)
        return val if val else _PLACEHOLDER

    lines.append("## Contexto da aula")
    lines.append(_note_sec("Resumo Executivo"))
    lines.append("")

    lines.append("## Objetivo de implementação")
    central = _note_sec("Ideia Central")
    praticas = _note_sec("Aplicacoes Praticas") if note_raw else _PLACEHOLDER
    if central != _PLACEHOLDER:
        lines.append(central)
        if praticas != _PLACEHOLDER:
            lines.append("")
            lines.append(praticas)
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")

    lines.append("## Arquivos prováveis")
    if codes_raw:
        lines.append(codes_raw.strip())
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")

    lines.append("## Agentes úteis")
    lines.append(_note_sec("Agentes Sugeridos"))
    lines.append("")

    lines.append("## Cuidados técnicos")
    lines.append(_note_sec("Conceitos Importantes"))
    lines.append("")

    lines.append("## Prompt sugerido")
    if note_raw:
        prompts = extract_section(note_raw, "Prompts Prontos")
        if prompts:
            # Use only the first prompt block (up to the second blank line after the first item)
            first = prompts.split("\n\n")[0].strip()
            lines.append(first if first else _PLACEHOLDER)
        else:
            lines.append(_PLACEHOLDER)
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")

    return "\n".join(lines)


def _gen_codex_context(
    lesson_title: str,
    note_raw: str | None,
    merge_raw: str | None,
    codes_raw: str | None,
    commands_raw: str | None,
    timestamp: str,
) -> str:
    sources = _sources_list(note_raw, merge_raw, codes_raw, commands_raw)
    lines: list[str] = [f"# Codex Context — {lesson_title}", ""]
    lines.extend(_header(lesson_title, sources, timestamp))

    def _note_sec(name: str) -> str:
        if note_raw is None:
            return _PLACEHOLDER
        val = extract_section(note_raw, name)
        return val if val else _PLACEHOLDER

    lines.append("## Tarefa")
    lines.append(_note_sec("Ideia Central"))
    lines.append("")

    lines.append("## Escopo")
    lines.append(_note_sec("Anotacao Estruturada"))
    lines.append("")

    lines.append("## Arquivos a criar/editar")
    if codes_raw:
        lines.append(codes_raw.strip())
    elif merge_raw:
        lines.append("_[Inferido do merge — consulte 08_MERGE_AUDIO_VIDEO.md para contexto.]_")
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")

    lines.append("## Critérios de aceite")
    lines.append(_note_sec("Aplicacoes Praticas"))
    lines.append("")

    lines.append("## Testes esperados")
    lines.append(_note_sec("Conceitos Importantes"))
    lines.append("")

    return "\n".join(lines)


def _gen_prompts_prontos(
    lesson_title: str,
    note_raw: str | None,
    timestamp: str,
) -> str:
    source = "09_ANOTACAO_NOTION.md (Fase 3/Ollama)" if note_raw else "nenhuma fonte disponível"
    lines: list[str] = [f"# Prompts Prontos — {lesson_title}", ""]
    lines.extend(_header(lesson_title, source, timestamp))
    if note_raw:
        content = extract_section(note_raw, "Prompts Prontos")
        lines.append(content if content else _PLACEHOLDER)
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")
    return "\n".join(lines)


def _gen_agentes_sugeridos(
    lesson_title: str,
    note_raw: str | None,
    timestamp: str,
) -> str:
    source = "09_ANOTACAO_NOTION.md (Fase 3/Ollama)" if note_raw else "nenhuma fonte disponível"
    lines: list[str] = [f"# Agentes Sugeridos — {lesson_title}", ""]
    lines.extend(_header(lesson_title, source, timestamp))
    if note_raw:
        content = extract_section(note_raw, "Agentes Sugeridos")
        lines.append(content if content else _PLACEHOLDER)
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")
    return "\n".join(lines)


def _gen_skills_sugeridas(
    lesson_title: str,
    note_raw: str | None,
    timestamp: str,
) -> str:
    source = "09_ANOTACAO_NOTION.md (Fase 3/Ollama)" if note_raw else "nenhuma fonte disponível"
    lines: list[str] = [f"# Skills Sugeridas — {lesson_title}", ""]
    lines.extend(_header(lesson_title, source, timestamp))
    if note_raw:
        content = extract_section(note_raw, "Skills Sugeridas")
        lines.append(content if content else _PLACEHOLDER)
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")
    return "\n".join(lines)


def _gen_ideias_de_projetos(
    lesson_title: str,
    note_raw: str | None,
    timestamp: str,
) -> str:
    source = "09_ANOTACAO_NOTION.md (Fase 3/Ollama)" if note_raw else "nenhuma fonte disponível"
    lines: list[str] = [f"# Ideias de Projetos — {lesson_title}", ""]
    lines.extend(_header(lesson_title, source, timestamp))
    if note_raw:
        content = extract_section(note_raw, "Ideias de Projeto")
        lines.append(content if content else _PLACEHOLDER)
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")
    return "\n".join(lines)


def _gen_implementation_plan(
    lesson_title: str,
    note_raw: str | None,
    codes_raw: str | None,
    commands_raw: str | None,
    timestamp: str,
    max_chars: int | None = None,
) -> str:
    sources = _sources_list(note_raw, None, codes_raw, commands_raw)
    lines: list[str] = [f"# Plano de Implementação — {lesson_title}", ""]
    lines.extend(_header(lesson_title, sources, timestamp))

    lines.append("## Objetivo")
    if note_raw:
        central = extract_section(note_raw, "Ideia Central")
        lines.append(central if central else _PLACEHOLDER)
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")

    lines.append("## Ideias de Projeto")
    if note_raw:
        ideias = extract_section(note_raw, "Ideias de Projeto")
        lines.append(ideias if ideias else _PLACEHOLDER)
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")

    lines.append("## Recursos Detectados no Vídeo")
    lines.append("")
    lines.append("### Códigos")
    lines.append(codes_raw.strip() if codes_raw else _PLACEHOLDER)
    lines.append("")
    lines.append("### Comandos")
    lines.append(commands_raw.strip() if commands_raw else _PLACEHOLDER)
    lines.append("")

    lines.append("## Próximos Passos")
    lines.append(
        "_[Preencher manualmente ou usar Claude Code com 10_CLAUDE_CODE_CONTEXT.md para detalhar.]_"
    )
    lines.append("")

    content = "\n".join(lines)
    if max_chars is not None and len(content) > max_chars:
        content = content[:max_chars].rstrip()
        content += (
            "\n\n_[Conteúdo truncado. Aumente `max_implementation_plan_chars` na config"
            " para ver o conteúdo completo.]_\n"
        )
    return content


# ── Main per-lesson builder ───────────────────────────────────────────────────


def build_lesson_outputs(
    lesson_title: str,
    note_raw: str | None,
    merge_raw: str | None,
    codes_raw: str | None,
    commands_raw: str | None,
    timestamp: str | None = None,
    max_implementation_plan_chars: int | None = None,
) -> dict[str, str]:
    """Build all 7 per-lesson output files as a dict[filename → content].

    Every file is generated regardless of which inputs are present; absent
    inputs produce placeholder text inside each relevant section.
    `max_implementation_plan_chars` truncates 16_IMPLEMENTATION_PLAN.md when set.
    """
    ts = timestamp or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return {
        CLAUDE_CODE_CONTEXT_FILENAME: _gen_claude_code_context(
            lesson_title, note_raw, merge_raw, codes_raw, commands_raw, ts
        ),
        CODEX_CONTEXT_FILENAME: _gen_codex_context(
            lesson_title, note_raw, merge_raw, codes_raw, commands_raw, ts
        ),
        PROMPTS_PRONTOS_FILENAME: _gen_prompts_prontos(lesson_title, note_raw, ts),
        AGENTES_SUGERIDOS_FILENAME: _gen_agentes_sugeridos(lesson_title, note_raw, ts),
        SKILLS_SUGERIDAS_FILENAME: _gen_skills_sugeridas(lesson_title, note_raw, ts),
        IDEIAS_DE_PROJETOS_FILENAME: _gen_ideias_de_projetos(lesson_title, note_raw, ts),
        IMPLEMENTATION_PLAN_FILENAME: _gen_implementation_plan(
            lesson_title, note_raw, codes_raw, commands_raw, ts,
            max_chars=max_implementation_plan_chars,
        ),
    }


def write_lesson_outputs(output_dir: Path, files: dict[str, str]) -> None:
    """Write all lesson output files atomically (.tmp + os.replace).

    Raises on the first write failure so the step is marked FAILED and the
    batch can continue with continue_on_error=True.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        dest = output_dir / filename
        tmp = dest.with_name(dest.name + ".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)


# ── Course-level aggregation ──────────────────────────────────────────────────


def _read_lesson_section_file(lesson: Lesson, filename: str) -> str | None:
    """Read a per-lesson output file; return None if it doesn't exist."""
    p = lesson.output_dir / filename
    return p.read_text(encoding="utf-8") if p.exists() else None


def _read_lesson_note_section(lesson: Lesson, section_name: str) -> str:
    """Extract a section from 09_ANOTACAO_NOTION.md; return placeholder if absent."""
    p = lesson.output_dir / _NOTES_FILENAME
    if not p.exists():
        return _PLACEHOLDER
    raw = p.read_text(encoding="utf-8")
    val = extract_section(raw, section_name)
    return val if val else _PLACEHOLDER


def _read_lesson_note_title(lesson: Lesson) -> str:
    """Read the H1 title from 09_ANOTACAO_NOTION.md; fall back to lesson.title.

    The note H1 (e.g., '# Aula 02 — Django Forms') carries the canonical
    lesson identifier including the lesson number, preserving traceability in
    course-level aggregation files.
    """
    p = lesson.output_dir / _NOTES_FILENAME
    if not p.exists():
        return lesson.title
    raw = p.read_text(encoding="utf-8")
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return lesson.title


def write_course_outputs(course: Course, lessons_with_outputs: list[Lesson]) -> None:
    """Generate the 5 course-level Markdown files in course.output_path.

    Always regenerated (no checkpoint) since aggregation is cheap. Only writes
    content from lessons present in `lessons_with_outputs`. If the list is
    empty, writes minimal placeholder files so the course directory is always
    consistent.
    """
    course.output_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    n = len(lessons_with_outputs)

    _write_course_overview(course, lessons_with_outputs, ts)
    _write_course_project_ideas(course, lessons_with_outputs, ts, n)
    _write_course_agents(course, lessons_with_outputs, ts, n)
    _write_course_skills(course, lessons_with_outputs, ts, n)
    _write_course_prompts(course, lessons_with_outputs, ts, n)

    logger.info(
        "Curso '%s': arquivos de curso gerados (%d aula(s) com outputs).",
        course.name,
        n,
    )


def _write_course_file(course: Course, filename: str, content: str) -> None:
    dest = course.output_path / filename
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def _course_header(course_name: str, ts: str) -> list[str]:
    return [
        "> Gerado automaticamente por AulaForge — Fase 7.",
        f"> Curso: {course_name} | Processado em: {ts}",
        "",
    ]


def _strip_lesson_file_header(content: str) -> str:
    """Remove the Phase 7 auto-generated header block from a per-lesson file.

    Skips the H1 title line, then all subsequent blank and blockquote ('>') lines
    until the body content begins. Robust to future changes in the number of
    blockquote header lines — does not rely on a fixed line count.
    """
    lines = content.split("\n")
    i = 0
    if i < len(lines) and lines[i].startswith("# "):
        i += 1
    while i < len(lines) and (lines[i].strip() == "" or lines[i].startswith(">")):
        i += 1
    return "\n".join(lines[i:]).strip()


def _write_course_overview(course: Course, lessons: list[Lesson], ts: str) -> None:
    lines: list[str] = [f"# Visão Geral do Curso — {course.name}", ""]
    lines.extend(_course_header(course.name, ts))
    if not lessons:
        lines.append(_PLACEHOLDER)
    else:
        lines.append("## Índice de Aulas")
        lines.append("")
        for lesson in lessons:
            lesson_heading = _read_lesson_note_title(lesson)
            resumo = _read_lesson_note_section(lesson, "Resumo Executivo")
            first_line = resumo.split("\n")[0].strip() if resumo != _PLACEHOLDER else _PLACEHOLDER
            lines.append(f"### {lesson_heading}")
            lines.append(first_line)
            lines.append("")
    _write_course_file(course, "COURSE_OVERVIEW.md", "\n".join(lines))


def _write_course_project_ideas(
    course: Course, lessons: list[Lesson], ts: str, n: int
) -> None:
    lines: list[str] = [f"# Ideias de Projetos — {course.name}", ""]
    lines.extend(_course_header(course.name, ts))
    if not lessons:
        lines.append(_PLACEHOLDER)
    else:
        for lesson in lessons:
            lesson_heading = _read_lesson_note_title(lesson)
            content = _read_lesson_section_file(lesson, IDEIAS_DE_PROJETOS_FILENAME)
            if content is None:
                content_text = _read_lesson_note_section(lesson, "Ideias de Projeto")
            else:
                content_text = _strip_lesson_file_header(content)
            lines.append(f"## {lesson_heading}")
            lines.append(content_text if content_text else _PLACEHOLDER)
            lines.append("")
    _write_course_file(course, "COURSE_PROJECT_IDEAS.md", "\n".join(lines))


def _write_course_agents(course: Course, lessons: list[Lesson], ts: str, n: int) -> None:
    lines: list[str] = [f"# Agentes Sugeridos — {course.name}", ""]
    lines.extend(_course_header(course.name, ts))
    if not lessons:
        lines.append(_PLACEHOLDER)
    else:
        for lesson in lessons:
            lesson_heading = _read_lesson_note_title(lesson)
            content = _read_lesson_section_file(lesson, AGENTES_SUGERIDOS_FILENAME)
            if content is None:
                content_text = _read_lesson_note_section(lesson, "Agentes Sugeridos")
            else:
                content_text = _strip_lesson_file_header(content)
            lines.append(f"## {lesson_heading}")
            lines.append(content_text if content_text else _PLACEHOLDER)
            lines.append("")
    _write_course_file(course, "COURSE_AGENTS.md", "\n".join(lines))


def _write_course_skills(course: Course, lessons: list[Lesson], ts: str, n: int) -> None:
    lines: list[str] = [f"# Skills Sugeridas — {course.name}", ""]
    lines.extend(_course_header(course.name, ts))
    if not lessons:
        lines.append(_PLACEHOLDER)
    else:
        for lesson in lessons:
            lesson_heading = _read_lesson_note_title(lesson)
            content = _read_lesson_section_file(lesson, SKILLS_SUGERIDAS_FILENAME)
            if content is None:
                content_text = _read_lesson_note_section(lesson, "Skills Sugeridas")
            else:
                content_text = _strip_lesson_file_header(content)
            lines.append(f"## {lesson_heading}")
            lines.append(content_text if content_text else _PLACEHOLDER)
            lines.append("")
    _write_course_file(course, "COURSE_SKILLS.md", "\n".join(lines))


def _write_course_prompts(course: Course, lessons: list[Lesson], ts: str, n: int) -> None:
    lines: list[str] = [f"# Prompts Prontos — {course.name}", ""]
    lines.extend(_course_header(course.name, ts))
    if not lessons:
        lines.append(_PLACEHOLDER)
    else:
        for lesson in lessons:
            lesson_heading = _read_lesson_note_title(lesson)
            content = _read_lesson_section_file(lesson, PROMPTS_PRONTOS_FILENAME)
            if content is None:
                content_text = _read_lesson_note_section(lesson, "Prompts Prontos")
            else:
                content_text = _strip_lesson_file_header(content)
            lines.append(f"## {lesson_heading}")
            lines.append(content_text if content_text else _PLACEHOLDER)
            lines.append("")
    _write_course_file(course, "COURSE_PROMPTS.md", "\n".join(lines))

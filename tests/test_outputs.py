"""Tests for Phase 7 outputs — no Whisper, FFmpeg, Tesseract, Ollama or Notion."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aulaforge.checkpoints import (
    OUTPUTS_STEP,
    PROCESSING_LOG_FILENAME,
    append_processing_log,
    needs_outputs_processing,
    process_lesson_outputs,
    record_outputs_skipped_disabled,
    record_outputs_skipped_no_inputs,
    record_skipped_outputs,
)
from aulaforge.config import OutputsConfig
from aulaforge.models import Course, Lesson, Status, StepLogEntry
from aulaforge.outputs import (
    _PLACEHOLDER,
    AGENTES_SUGERIDOS_FILENAME,
    CLAUDE_CODE_CONTEXT_FILENAME,
    CODEX_CONTEXT_FILENAME,
    IDEIAS_DE_PROJETOS_FILENAME,
    IMPLEMENTATION_PLAN_FILENAME,
    LESSON_OUTPUT_FILENAMES,
    PROMPTS_PRONTOS_FILENAME,
    SKILLS_SUGERIDAS_FILENAME,
    build_lesson_outputs,
    compute_outputs_input_hash,
    extract_section,
    has_any_input,
    read_lesson_inputs,
    write_course_outputs,
    write_lesson_outputs,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_NOTE = """\
# Aula 01 — Introdução ao Django

> Gerado automaticamente pela Fase 3

## Resumo Executivo
Visão geral do framework Django e suas principais funcionalidades.

## Ideia Central
Django é um framework web Python de alto nível que incentiva o desenvolvimento rápido.

## Indice com Timestamps
- 00:00 Introdução
- 05:00 Instalação

## Anotacao Estruturada
- Ponto 1: MVT (Model-View-Template)
- Ponto 2: ORM built-in

## Conceitos Importantes
- ORM
- URLs patterns
- Templates

## Aplicacoes Praticas
Criar uma aplicação CRUD com Django em menos de uma hora.

## Ideias de Projeto
Sugestao: CRM simples usando Django Admin.

## Agentes Sugeridos
Sugestao: django-expert, python-cli-engineer

## Skills Sugeridas
Sugestao: /django, /python-web

## Prompts Prontos
Sugestao: "Crie um modelo Django para gerenciar contatos com nome, email e telefone."
Sugestao: "Escreva uma view baseada em classe que liste todos os contatos."
"""

FAKE_NOTE_WITH_ACCENTS = """\
# Aula 02

## Índice com Timestamps
- 00:00 Start

## Anotação Estruturada
- Ponto principal

## Aplicações Práticas
Aplicar o conteúdo no projeto.

## Ideias de Projeto
Projeto de exemplo.

## Agentes Sugeridos
Agente X

## Skills Sugeridas
Skill Y

## Prompts Prontos
Prompt Z
"""

FAKE_MERGE = """\
# Merge Audio/Vídeo — Aula 01

> Gerado automaticamente por AulaForge.

## Linha do Tempo

### 00:00:00 – 00:10:00

**[Falado]** `00:00:05 – 00:00:15`
> Bem-vindos ao curso de Django.
"""

FAKE_CODES = """\
# Códigos Detectados — Aula 01

```python
from django.db import models

class Contact(models.Model):
    name = models.CharField(max_length=100)
```
"""

FAKE_COMMANDS = """\
# Comandos de Terminal — Aula 01

```bash
pip install django
django-admin startproject myproject
```
"""

TS = "2026-07-01T12:00:00"


def _make_lesson(tmp_path: Path, slug: str = "aula_01") -> Lesson:
    output_dir = tmp_path / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    return Lesson(
        number=1,
        title="Introdução ao Django",
        slug=slug,
        video_path=tmp_path / f"{slug}.mp4",
        output_dir=output_dir,
    )


def _make_course(tmp_path: Path, lessons: list[Lesson]) -> Course:
    return Course(
        name="Curso Django CRM",
        input_path=tmp_path / "videos",
        output_path=tmp_path / "output",
        lessons=lessons,
    )


# ── extract_section ───────────────────────────────────────────────────────────


def test_extract_section_basic():
    result = extract_section(FAKE_NOTE, "Resumo Executivo")
    assert "Django" in result
    assert "framework" in result


def test_extract_section_missing_returns_empty():
    result = extract_section(FAKE_NOTE, "Seção Inexistente")
    assert result == ""


def test_extract_section_case_insensitive():
    result = extract_section(FAKE_NOTE, "resumo executivo")
    assert result != ""


def test_extract_section_diacritic_insensitive():
    # "Índice com Timestamps" (with accent) should match "Indice com Timestamps"
    result_plain = extract_section(FAKE_NOTE, "Indice com Timestamps")
    result_accent = extract_section(FAKE_NOTE_WITH_ACCENTS, "Índice com Timestamps")
    assert result_plain != ""
    assert result_accent != ""


def test_extract_section_does_not_bleed_into_next():
    result = extract_section(FAKE_NOTE, "Resumo Executivo")
    assert "Ideia Central" not in result


def test_extract_section_ideias_de_projeto():
    result = extract_section(FAKE_NOTE, "Ideias de Projeto")
    assert "CRM" in result


def test_extract_section_agentes_sugeridos():
    result = extract_section(FAKE_NOTE, "Agentes Sugeridos")
    assert "django-expert" in result


def test_extract_section_skills_sugeridas():
    result = extract_section(FAKE_NOTE, "Skills Sugeridas")
    assert "/django" in result


def test_extract_section_prompts_prontos():
    result = extract_section(FAKE_NOTE, "Prompts Prontos")
    assert "modelo Django" in result


def test_extract_section_anotacao_estruturada():
    result = extract_section(FAKE_NOTE_WITH_ACCENTS, "Anotação Estruturada")
    assert "Ponto principal" in result


# ── compute_outputs_input_hash ────────────────────────────────────────────────

cfg_default = OutputsConfig()


def test_hash_deterministic():
    h1 = compute_outputs_input_hash(FAKE_NOTE, FAKE_MERGE, None, None, cfg_default)
    h2 = compute_outputs_input_hash(FAKE_NOTE, FAKE_MERGE, None, None, cfg_default)
    assert h1 == h2


def test_hash_changes_with_note():
    h1 = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    h2 = compute_outputs_input_hash(FAKE_NOTE + " extra", None, None, None, cfg_default)
    assert h1 != h2


def test_hash_changes_with_merge():
    h1 = compute_outputs_input_hash(None, FAKE_MERGE, None, None, cfg_default)
    h2 = compute_outputs_input_hash(None, FAKE_MERGE + " extra", None, None, cfg_default)
    assert h1 != h2


def test_hash_changes_with_codes():
    h1 = compute_outputs_input_hash(None, None, FAKE_CODES, None, cfg_default)
    h2 = compute_outputs_input_hash(None, None, FAKE_CODES + " extra", None, cfg_default)
    assert h1 != h2


def test_hash_changes_with_commands():
    h1 = compute_outputs_input_hash(None, None, None, FAKE_COMMANDS, cfg_default)
    h2 = compute_outputs_input_hash(None, None, None, FAKE_COMMANDS + " extra", cfg_default)
    assert h1 != h2


def test_hash_sentinel_for_none():
    h_none = compute_outputs_input_hash(None, None, None, None, cfg_default)
    h_empty = compute_outputs_input_hash("", None, None, None, cfg_default)
    assert h_none != h_empty


def test_hash_config_affects_result():
    # max_implementation_plan_chars faz parte do payload de hash (B1 fix: enabled não faz)
    cfg_limited = OutputsConfig(max_implementation_plan_chars=5000)
    h1 = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    h2 = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_limited)
    assert h1 != h2


def test_hash_is_sha256_hex():
    h = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ── has_any_input ─────────────────────────────────────────────────────────────


def test_has_any_input_all_none():
    assert not has_any_input(None, None, None, None)


def test_has_any_input_note_only():
    assert has_any_input(FAKE_NOTE, None, None, None)


def test_has_any_input_merge_only():
    assert has_any_input(None, FAKE_MERGE, None, None)


def test_has_any_input_codes_only():
    assert has_any_input(None, None, FAKE_CODES, None)


def test_has_any_input_commands_only():
    assert has_any_input(None, None, None, FAKE_COMMANDS)


# ── build_lesson_outputs ──────────────────────────────────────────────────────


def test_build_returns_all_7_files():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, FAKE_MERGE, FAKE_CODES, FAKE_COMMANDS, TS)
    assert set(result.keys()) == set(LESSON_OUTPUT_FILENAMES)


def test_build_claude_code_context_has_header():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, FAKE_MERGE, None, None, TS)
    content = result[CLAUDE_CODE_CONTEXT_FILENAME]
    assert "# Claude Code Context" in content
    assert "Gerado automaticamente" in content
    assert "Fontes:" in content


def test_build_claude_code_context_uses_resumo_executivo():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, None, None, TS)
    content = result[CLAUDE_CODE_CONTEXT_FILENAME]
    assert "framework Django" in content


def test_build_codex_context_has_header():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, FAKE_MERGE, None, None, TS)
    content = result[CODEX_CONTEXT_FILENAME]
    assert "# Codex Context" in content
    assert "Tarefa" in content


def test_build_codex_context_uses_ideia_central():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, None, None, TS)
    content = result[CODEX_CONTEXT_FILENAME]
    assert "framework web Python" in content


def test_build_prompts_prontos_extracts_section():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, None, None, TS)
    content = result[PROMPTS_PRONTOS_FILENAME]
    assert "modelo Django" in content


def test_build_agentes_sugeridos_extracts_section():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, None, None, TS)
    content = result[AGENTES_SUGERIDOS_FILENAME]
    assert "django-expert" in content


def test_build_skills_sugeridas_extracts_section():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, None, None, TS)
    content = result[SKILLS_SUGERIDAS_FILENAME]
    assert "/django" in content


def test_build_ideias_de_projetos_extracts_section():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, None, None, TS)
    content = result[IDEIAS_DE_PROJETOS_FILENAME]
    assert "CRM" in content


def test_build_implementation_plan_has_structure():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, FAKE_CODES, FAKE_COMMANDS, TS)
    content = result[IMPLEMENTATION_PLAN_FILENAME]
    assert "## Objetivo" in content
    assert "## Ideias de Projeto" in content
    assert "## Recursos Detectados" in content
    assert "## Próximos Passos" in content


def test_build_implementation_plan_includes_codes():
    result = build_lesson_outputs("Aula 01", None, None, FAKE_CODES, None, TS)
    content = result[IMPLEMENTATION_PLAN_FILENAME]
    assert "Contact" in content


def test_build_implementation_plan_includes_commands():
    result = build_lesson_outputs("Aula 01", None, None, None, FAKE_COMMANDS, TS)
    content = result[IMPLEMENTATION_PLAN_FILENAME]
    assert "pip install django" in content


def test_build_with_only_note():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, None, None, TS)
    assert set(result.keys()) == set(LESSON_OUTPUT_FILENAMES)
    assert _PLACEHOLDER not in result[PROMPTS_PRONTOS_FILENAME]


def test_build_with_only_merge():
    result = build_lesson_outputs("Aula 01", None, FAKE_MERGE, None, None, TS)
    assert set(result.keys()) == set(LESSON_OUTPUT_FILENAMES)
    assert _PLACEHOLDER in result[PROMPTS_PRONTOS_FILENAME]
    # Codex context should mention merge inference
    codex = result[CODEX_CONTEXT_FILENAME]
    assert "08_MERGE" in codex or _PLACEHOLDER in codex


def test_build_with_only_codes():
    result = build_lesson_outputs("Aula 01", None, None, FAKE_CODES, None, TS)
    assert set(result.keys()) == set(LESSON_OUTPUT_FILENAMES)
    content = result[IMPLEMENTATION_PLAN_FILENAME]
    assert "Contact" in content


def test_build_with_only_commands():
    result = build_lesson_outputs("Aula 01", None, None, None, FAKE_COMMANDS, TS)
    assert set(result.keys()) == set(LESSON_OUTPUT_FILENAMES)
    content = result[IMPLEMENTATION_PLAN_FILENAME]
    assert "pip install" in content


def test_build_placeholder_when_no_note_and_no_codes():
    result = build_lesson_outputs("Aula 01", None, FAKE_MERGE, None, None, TS)
    assert _PLACEHOLDER in result[AGENTES_SUGERIDOS_FILENAME]


def test_build_source_header_reflects_inputs():
    result = build_lesson_outputs("Aula 01", FAKE_NOTE, None, None, None, TS)
    content = result[CLAUDE_CODE_CONTEXT_FILENAME]
    assert "09_ANOTACAO_NOTION" in content
    assert "08_MERGE" not in content


def test_build_claude_code_context_includes_commands_in_fontes():
    """07_COMANDOS_TERMINAL must appear in Fontes of file 10 when commands_raw provided."""
    result = build_lesson_outputs("Aula 01", None, None, None, FAKE_COMMANDS, TS)
    content = result[CLAUDE_CODE_CONTEXT_FILENAME]
    assert "07_COMANDOS_TERMINAL" in content


def test_build_codex_context_includes_commands_in_fontes():
    """07_COMANDOS_TERMINAL must appear in Fontes of file 11 when commands_raw provided."""
    result = build_lesson_outputs("Aula 01", None, None, None, FAKE_COMMANDS, TS)
    content = result[CODEX_CONTEXT_FILENAME]
    assert "07_COMANDOS_TERMINAL" in content


# ── write_lesson_outputs ──────────────────────────────────────────────────────


def test_write_lesson_outputs_creates_all_files(tmp_path: Path):
    files = {f: f"# {f}" for f in LESSON_OUTPUT_FILENAMES}
    write_lesson_outputs(tmp_path, files)
    for fname in LESSON_OUTPUT_FILENAMES:
        assert (tmp_path / fname).exists()


def test_write_lesson_outputs_content_utf8(tmp_path: Path):
    content = "# Título com acentuação — Fase 7"
    files = {CLAUDE_CODE_CONTEXT_FILENAME: content}
    write_lesson_outputs(tmp_path, files)
    written = (tmp_path / CLAUDE_CODE_CONTEXT_FILENAME).read_text(encoding="utf-8")
    assert content in written


def test_write_lesson_outputs_no_tmp_left_behind(tmp_path: Path):
    files = {f: "content" for f in LESSON_OUTPUT_FILENAMES}
    write_lesson_outputs(tmp_path, files)
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


# ── needs_outputs_processing ──────────────────────────────────────────────────


def test_needs_outputs_force(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    # Write all 7 files to satisfy file-existence check
    for f in LESSON_OUTPUT_FILENAMES:
        (lesson.output_dir / f).write_text("x", encoding="utf-8")
    outputs_hash = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    entry = StepLogEntry(
        step=OUTPUTS_STEP,
        status=Status.COMPLETED,
        started_at=datetime.now(),
        finished_at=datetime.now(),
        source_hash=outputs_hash,
    )
    append_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug, entry)
    assert needs_outputs_processing(lesson, outputs_hash, force=True)


def test_needs_outputs_no_log(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    outputs_hash = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    assert needs_outputs_processing(lesson, outputs_hash)


def test_needs_outputs_hash_mismatch(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    for f in LESSON_OUTPUT_FILENAMES:
        (lesson.output_dir / f).write_text("x", encoding="utf-8")
    outputs_hash = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    entry = StepLogEntry(
        step=OUTPUTS_STEP,
        status=Status.COMPLETED,
        started_at=datetime.now(),
        finished_at=datetime.now(),
        source_hash="different_hash",
    )
    append_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug, entry)
    assert needs_outputs_processing(lesson, outputs_hash)


def test_needs_outputs_missing_file(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    outputs_hash = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    # Write only 6 of 7 files
    for f in LESSON_OUTPUT_FILENAMES[:-1]:
        (lesson.output_dir / f).write_text("x", encoding="utf-8")
    entry = StepLogEntry(
        step=OUTPUTS_STEP,
        status=Status.COMPLETED,
        started_at=datetime.now(),
        finished_at=datetime.now(),
        source_hash=outputs_hash,
    )
    append_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug, entry)
    assert needs_outputs_processing(lesson, outputs_hash)


def test_needs_outputs_all_ok_returns_false(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    for f in LESSON_OUTPUT_FILENAMES:
        (lesson.output_dir / f).write_text("x", encoding="utf-8")
    outputs_hash = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    entry = StepLogEntry(
        step=OUTPUTS_STEP,
        status=Status.COMPLETED,
        started_at=datetime.now(),
        finished_at=datetime.now(),
        source_hash=outputs_hash,
    )
    append_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug, entry)
    assert not needs_outputs_processing(lesson, outputs_hash)


# ── record_* functions ────────────────────────────────────────────────────────


def test_record_skipped_outputs(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    outputs_hash = "abc123"
    entry = record_skipped_outputs(lesson, outputs_hash, datetime.now())
    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.step == OUTPUTS_STEP
    assert entry.source_hash == outputs_hash


def test_record_outputs_skipped_no_inputs(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    entry = record_outputs_skipped_no_inputs(lesson, datetime.now())
    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.step == OUTPUTS_STEP
    assert entry.source_hash is None


def test_record_outputs_skipped_disabled(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    entry = record_outputs_skipped_disabled(lesson, datetime.now())
    assert entry.status == Status.SKIPPED_UNCHANGED
    assert entry.step == OUTPUTS_STEP


# ── process_lesson_outputs ────────────────────────────────────────────────────


def test_process_lesson_outputs_creates_files(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    outputs_hash = compute_outputs_input_hash(FAKE_NOTE, FAKE_MERGE, None, None, cfg_default)
    files, entry = process_lesson_outputs(
        lesson, outputs_hash, FAKE_NOTE, FAKE_MERGE, None, None, cfg_default
    )
    assert entry.status == Status.COMPLETED
    assert entry.step == OUTPUTS_STEP
    assert entry.source_hash == outputs_hash
    for fname in LESSON_OUTPUT_FILENAMES:
        assert (lesson.output_dir / fname).exists()


def test_process_lesson_outputs_logs_step(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    outputs_hash = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    _, _ = process_lesson_outputs(
        lesson, outputs_hash, FAKE_NOTE, None, None, None, cfg_default
    )
    log_path = lesson.output_dir / PROCESSING_LOG_FILENAME
    assert log_path.exists()
    log_data = json.loads(log_path.read_text(encoding="utf-8"))
    step_names = [s["step"] for s in log_data["steps"]]
    assert OUTPUTS_STEP in step_names


def test_process_lesson_outputs_second_run_skips(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    outputs_hash = compute_outputs_input_hash(FAKE_NOTE, None, None, None, cfg_default)
    process_lesson_outputs(lesson, outputs_hash, FAKE_NOTE, None, None, None, cfg_default)
    assert not needs_outputs_processing(lesson, outputs_hash, force=False)


# ── read_lesson_inputs ────────────────────────────────────────────────────────


def test_read_lesson_inputs_all_absent(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    note, merge, codes, commands = read_lesson_inputs(lesson)
    assert note is None
    assert merge is None
    assert codes is None
    assert commands is None


def test_read_lesson_inputs_note_present(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    (lesson.output_dir / "09_ANOTACAO_NOTION.md").write_text(FAKE_NOTE, encoding="utf-8")
    note, merge, codes, commands = read_lesson_inputs(lesson)
    assert note == FAKE_NOTE
    assert merge is None


def test_read_lesson_inputs_merge_present(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    (lesson.output_dir / "08_MERGE_AUDIO_VIDEO.md").write_text(FAKE_MERGE, encoding="utf-8")
    note, merge, codes, commands = read_lesson_inputs(lesson)
    assert note is None
    assert merge == FAKE_MERGE


# ── write_course_outputs ──────────────────────────────────────────────────────


def test_write_course_outputs_no_lessons(tmp_path: Path):
    course = _make_course(tmp_path, [])
    write_course_outputs(course, [])
    assert (course.output_path / "COURSE_OVERVIEW.md").exists()
    assert (course.output_path / "COURSE_PROJECT_IDEAS.md").exists()
    assert (course.output_path / "COURSE_AGENTS.md").exists()
    assert (course.output_path / "COURSE_SKILLS.md").exists()
    assert (course.output_path / "COURSE_PROMPTS.md").exists()


def test_write_course_outputs_placeholder_when_no_lessons(tmp_path: Path):
    course = _make_course(tmp_path, [])
    write_course_outputs(course, [])
    content = (course.output_path / "COURSE_OVERVIEW.md").read_text(encoding="utf-8")
    assert _PLACEHOLDER in content


def test_write_course_outputs_with_lessons_using_notes(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    # Write the note file so course overview can extract summary
    (lesson.output_dir / "09_ANOTACAO_NOTION.md").write_text(FAKE_NOTE, encoding="utf-8")
    course = _make_course(tmp_path, [lesson])
    write_course_outputs(course, [lesson])
    overview = (course.output_path / "COURSE_OVERVIEW.md").read_text(encoding="utf-8")
    assert "Introdução ao Django" in overview


def test_write_course_outputs_with_lesson_output_files(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    # Write per-lesson outputs (as if Phase 7 already ran)
    agents_content = "# Agentes Sugeridos\n\n> header\n\n> header2\n\nagente-X\n"
    (lesson.output_dir / AGENTES_SUGERIDOS_FILENAME).write_text(agents_content, encoding="utf-8")
    course = _make_course(tmp_path, [lesson])
    write_course_outputs(course, [lesson])
    agents_course = (course.output_path / "COURSE_AGENTS.md").read_text(encoding="utf-8")
    assert "Introdução ao Django" in agents_course


def test_write_course_outputs_utf8(tmp_path: Path):
    lesson = _make_lesson(tmp_path)
    note_path = lesson.output_dir / "09_ANOTACAO_NOTION.md"
    note_path.write_text(FAKE_NOTE_WITH_ACCENTS, encoding="utf-8")
    course = _make_course(tmp_path, [lesson])
    write_course_outputs(course, [lesson])
    overview = (course.output_path / "COURSE_OVERVIEW.md").read_text(encoding="utf-8")
    assert "Aula 02" in overview


def test_write_course_agents_strips_header_robustly(tmp_path: Path):
    """Header stripping must work even when the header has more than 3 blockquote lines.

    The old hard-coded [5:] slice would leave the extra '>' line in the body.
    The robust helper skips all leading blockquote/blank lines dynamically.
    """
    lesson = _make_lesson(tmp_path)
    agents_content = (
        "# Agentes Sugeridos — Aula 01\n"
        "\n"
        "> Gerado automaticamente por AulaForge — Fase 7.\n"
        "> Fontes: 09_ANOTACAO_NOTION.md (Fase 3/Ollama)\n"
        "> Aula: Aula 01 | Processado em: 2026-07-01T12:00:00\n"
        "> Linha extra futura de header.\n"  # 4th blockquote — would break [5:]
        "\n"
        "agente-X\n"
    )
    (lesson.output_dir / AGENTES_SUGERIDOS_FILENAME).write_text(agents_content, encoding="utf-8")
    course = _make_course(tmp_path, [lesson])
    write_course_outputs(course, [lesson])
    agents_course = (course.output_path / "COURSE_AGENTS.md").read_text(encoding="utf-8")
    assert "agente-X" in agents_course
    assert "> Linha extra futura de header." not in agents_course


def test_write_course_outputs_no_tmp_left_behind(tmp_path: Path):
    course = _make_course(tmp_path, [])
    write_course_outputs(course, [])
    tmp_files = list(course.output_path.glob("*.tmp"))
    assert tmp_files == []


# ── OutputsConfig ─────────────────────────────────────────────────────────────


def test_outputs_config_defaults():
    cfg = OutputsConfig()
    assert cfg.enabled is True


def test_outputs_config_disabled():
    cfg = OutputsConfig(enabled=False)
    assert cfg.enabled is False

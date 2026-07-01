"""Smoke tests for aulaforge.cli using Typer's CliRunner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import aulaforge.cli as cli_module
from aulaforge.cli import DEPENDENCY_MISSING_EXIT_CODE, PROCESSING_FAILURE_EXIT_CODE, app

runner = CliRunner()


def _write_config(tmp_path: Path, output_root: Path) -> Path:
    config_file = tmp_path / "aulaforge.yaml"
    config_file.write_text(
        f'project:\n  output_dir: "{output_root.as_posix()}"\n', encoding="utf-8"
    )
    return config_file


class FakeWhisperModel:
    def transcribe(self, audio_path: str, language: str | None = None) -> dict[str, object]:
        return {"segments": [{"start": 0.0, "end": 1.0, "text": "ola"}]}


def _fake_extract_audio(video_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake-audio")
    return output_path


class LoadModelSpy:
    """Counts how many times load_whisper_model is called, returns a FakeWhisperModel."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, model_name: str) -> FakeWhisperModel:
        self.call_count += 1
        return FakeWhisperModel()


@pytest.fixture
def mock_transcription_success(monkeypatch: pytest.MonkeyPatch) -> LoadModelSpy:
    """Make the full transcription path succeed without real ffmpeg/whisper."""
    monkeypatch.setattr(cli_module, "check_transcription_dependencies", lambda: [])
    monkeypatch.setattr("aulaforge.checkpoints.extract_audio", _fake_extract_audio)
    spy = LoadModelSpy()
    monkeypatch.setattr(cli_module, "load_whisper_model", spy)
    return spy


@pytest.fixture
def mock_notes_success(
    monkeypatch: pytest.MonkeyPatch,
    mock_transcription_success: LoadModelSpy,
) -> LoadModelSpy:
    """Extend mock_transcription_success so notes generation also works without Ollama.

    Mocks the Ollama dependency check (returns no errors) and patches
    `generate_lesson_note` in the checkpoints module to return a canned string.
    The real `process_lesson_notes` still runs, so files are written and the
    processing_log is updated — skip logic works correctly on subsequent runs.
    """
    monkeypatch.setattr(
        cli_module, "check_ollama_dependencies", lambda base_url, model: []
    )
    monkeypatch.setattr(
        "aulaforge.checkpoints.generate_lesson_note",
        lambda title, text, cfg_llm: "# nota fake",
    )
    return mock_transcription_success


def test_process_course_exits_cleanly_when_no_videos_found(
    tmp_path: Path, output_root: Path
) -> None:
    empty_course = tmp_path / "Curso Vazio"
    empty_course.mkdir()
    config_file = _write_config(tmp_path, output_root)

    result = runner.invoke(
        app, ["process-course", str(empty_course), "--config", str(config_file)]
    )

    assert result.exit_code == 0, result.output


def test_process_course_fails_fast_for_missing_explicit_config(
    course_dir: Path, output_root: Path
) -> None:
    result = runner.invoke(
        app, ["process-course", str(course_dir), "--config", "__missing__.yaml"]
    )

    assert result.exit_code == PROCESSING_FAILURE_EXIT_CODE
    assert "Traceback" not in result.output, "nao deve vazar traceback bruto"
    assert "Erro de configuracao" in result.output
    assert "__missing__.yaml" in result.output


def test_process_course_runs_end_to_end(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_notes_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output
    course_output = output_root / course_dir.name
    assert (course_output / "batch_report.md").exists()
    assert (course_output / "batch_log.json").exists()

    lesson_dirs = [p for p in course_output.iterdir() if p.is_dir()]
    assert len(lesson_dirs) == 4
    for lesson_dir in lesson_dirs:
        assert (lesson_dir / "source_info.json").exists()
        assert (lesson_dir / "processing_log.json").exists()
        assert (lesson_dir / "audio.mp3").exists()
        assert (lesson_dir / "01_TRANSCRICAO_BRUTA.txt").exists()
        assert (lesson_dir / "02_TRANSCRICAO_COM_TIMESTAMPS.json").exists()
        assert (lesson_dir / "03_TRANSCRICAO_LIMPA.md").exists()
        assert (lesson_dir / "09_ANOTACAO_NOTION.md").exists()


def test_process_course_loads_whisper_model_only_once_per_run(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_notes_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output
    assert mock_notes_success.call_count == 1, "modelo deve ser carregado 1x, nao por aula"


def test_process_course_continues_after_one_lesson_fails(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)
    original = cli_module.process_lesson_foundation

    def flaky(lesson: Any, force: bool = False) -> Any:
        if lesson.number == 1:
            raise RuntimeError("falha simulada")
        return original(lesson, force=force)

    monkeypatch.setattr(cli_module, "process_lesson_foundation", flaky)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == PROCESSING_FAILURE_EXIT_CODE
    assert "1 com falha" in result.output

    course_output = output_root / course_dir.name
    lesson_dirs = [p for p in course_output.iterdir() if p.is_dir()]
    assert len(lesson_dirs) == 4, "todas as pastas de aula devem existir mesmo com 1 falha"


def test_process_course_second_run_skips_unchanged(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_notes_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)

    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    calls_after_first_run = mock_notes_success.call_count
    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output
    assert "pulada" in result.output
    # Foundation, transcription and notes were all done; no model load needed again.
    assert mock_notes_success.call_count == calls_after_first_run


def test_process_course_reports_dependency_missing_with_distinct_exit_code(
    course_dir: Path, output_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = _write_config(tmp_path, output_root)
    monkeypatch.setattr(
        cli_module,
        "check_transcription_dependencies",
        lambda: ["ffmpeg nao encontrado no PATH (simulado para teste)"],
    )

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == DEPENDENCY_MISSING_EXIT_CODE
    course_output = output_root / course_dir.name
    lesson_dirs = [p for p in course_output.iterdir() if p.is_dir()]
    assert len(lesson_dirs) == 4
    for lesson_dir in lesson_dirs:
        # Foundation must still complete even though transcription cannot run.
        assert (lesson_dir / "source_info.json").exists()
        assert not (lesson_dir / "audio.mp3").exists()


# ---------------------------------------------------------------------------
# Phase 3 — Notes
# ---------------------------------------------------------------------------


def test_process_course_second_run_skips_notes_without_calling_ollama(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)

    # First run: notes generated for all lessons.
    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    # Second run: notes are current; Ollama must never be checked.
    def boom(base_url: str, model: str) -> list[str]:
        raise AssertionError("check_ollama_dependencies nao deveria ser chamado")

    monkeypatch.setattr(cli_module, "check_ollama_dependencies", boom)
    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output
    assert "pulada" in result.output


def test_process_course_ollama_missing_reports_dep_exit_code(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_transcription_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)
    monkeypatch.setattr(
        cli_module,
        "check_ollama_dependencies",
        lambda base_url, model: ["Ollama nao esta rodando (simulado)"],
    )

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == DEPENDENCY_MISSING_EXIT_CODE
    # Foundation and transcription must still complete despite Ollama being absent.
    course_output = output_root / course_dir.name
    for lesson_dir in [p for p in course_output.iterdir() if p.is_dir()]:
        assert (lesson_dir / "source_info.json").exists()
        assert (lesson_dir / "audio.mp3").exists()
        assert not (lesson_dir / "09_ANOTACAO_NOTION.md").exists()


def test_process_course_notes_skipped_when_transcription_dep_missing(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When transcription dep is missing, notes should be SKIPPED (not FAILED),
    so that the overall exit code is driven by the transcription dep failure."""
    config_file = _write_config(tmp_path, output_root)
    monkeypatch.setattr(
        cli_module,
        "check_transcription_dependencies",
        lambda: ["ffmpeg simulado ausente"],
    )

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == DEPENDENCY_MISSING_EXIT_CODE


# ---------------------------------------------------------------------------
# Phase 4 — Notion
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_notion_success(
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> LoadModelSpy:
    """Extend mock_notes_success so Notion sync also works in tests.

    Patches check_notion_dependencies to return a valid availability object
    and patches sync_lesson_to_notion in checkpoints to avoid real API calls,
    while still running the real process_lesson_notion so the processing_log
    is updated and skip logic works on subsequent runs.
    """
    import aulaforge.notion as notion_mod
    from aulaforge.models import NotionLessonInfo, NotionPageInfo
    from aulaforge.notion import NotionAvailability

    monkeypatch.setattr(
        cli_module,
        "check_notion_dependencies",
        lambda cfg: NotionAvailability(errors=[], token="fake-token", database_id="fake-db"),
    )

    def fake_sync(  # type: ignore[misc]
        course: object,
        lesson: object,
        note: str,
        nhash: str,
        cfg: object,
        token: str,
        db: str,
    ) -> tuple[object, str]:
        # Mirror real sync: accumulate all lessons in the same page info file.
        from aulaforge.models import Course, Lesson

        assert isinstance(course, Course)
        assert isinstance(lesson, Lesson)
        existing = notion_mod.read_notion_page_info(course.output_path)
        if existing is None:
            page_info = NotionPageInfo(
                course_page_id="page-1",
                course_page_url="https://notion.so/page-1",
                database_id=db,
                lessons={},
            )
        else:
            page_info = existing
        page_info.lessons[lesson.slug] = NotionLessonInfo(
            toggle_block_id="toggle-1", synced_hash=nhash
        )
        notion_mod.write_notion_page_info(course.output_path, page_info)
        return page_info, "toggle-1"

    import aulaforge.checkpoints as chk_module
    monkeypatch.setattr(chk_module, "sync_lesson_to_notion", fake_sync)
    return mock_notes_success


def _write_config_with_notion(tmp_path: Path, output_root: Path) -> Path:
    config_file = tmp_path / "aulaforge.yaml"
    config_file.write_text(
        f'project:\n  output_dir: "{output_root.as_posix()}"\nnotion:\n  enabled: true\n',
        encoding="utf-8",
    )
    return config_file


def test_process_course_notion_skipped_when_disabled(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_notes_success: LoadModelSpy,
) -> None:
    """Default config has notion.enabled=false; no Notion calls should occur."""
    config_file = _write_config(tmp_path, output_root)

    def boom(cfg: object) -> object:
        raise AssertionError("check_notion_dependencies nao deve ser chamado quando disabled")

    import aulaforge.cli as cli_mod_ref

    orig = cli_mod_ref.check_notion_dependencies
    cli_mod_ref.check_notion_dependencies = boom  # type: ignore[assignment]
    try:
        result = runner.invoke(
            app, ["process-course", str(course_dir), "--config", str(config_file)]
        )
    finally:
        cli_mod_ref.check_notion_dependencies = orig  # type: ignore[assignment]

    assert result.exit_code == 0, result.output


def test_process_course_notion_skipped_when_notes_missing(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_transcription_success: LoadModelSpy,
) -> None:
    """With Ollama absent, notes won't exist; notion step should be SKIPPED not FAILED."""
    config_file = _write_config_with_notion(tmp_path, output_root)
    monkeypatch.setattr(
        cli_module, "check_ollama_dependencies", lambda b, m: ["Ollama ausente (sim)"]
    )
    from aulaforge.notion import NotionAvailability
    monkeypatch.setattr(
        cli_module, "check_notion_dependencies",
        lambda cfg: NotionAvailability(errors=[], token="tk", database_id="db"),
    )

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    # Ollama absent = exit code 2 (dep missing), not notion error.
    assert result.exit_code == DEPENDENCY_MISSING_EXIT_CODE


def test_process_course_notion_dependency_missing_exit_code_2(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """Token missing or invalid should produce exit code 2 (dep missing)."""
    config_file = _write_config_with_notion(tmp_path, output_root)
    from aulaforge.notion import NotionAvailability
    monkeypatch.setattr(
        cli_module,
        "check_notion_dependencies",
        lambda cfg: NotionAvailability(errors=["NOTION_TOKEN nao definido (simulado)"]),
    )

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == DEPENDENCY_MISSING_EXIT_CODE


def test_process_course_second_run_skips_notion_without_http_calls(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notion_success: LoadModelSpy,
) -> None:
    config_file = _write_config_with_notion(tmp_path, output_root)

    # First run: all steps including Notion complete via mocked happy path.
    result1 = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    assert result1.exit_code == 0, result1.output

    # Second run: Notion was already synced; NEITHER sync_lesson_to_notion NOR
    # check_notion_dependencies should be called (M1: lazy dependency check).
    import aulaforge.checkpoints as chk_module

    def boom_sync(*args: object, **kwargs: object) -> object:
        raise AssertionError("sync_lesson_to_notion nao deveria ser chamado na 2a run")

    def boom_check_deps(cfg: object) -> object:
        raise AssertionError("check_notion_dependencies nao deveria ser chamado na 2a run")

    monkeypatch.setattr(chk_module, "sync_lesson_to_notion", boom_sync)
    monkeypatch.setattr(cli_module, "check_notion_dependencies", boom_check_deps)
    result2 = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result2.exit_code == 0, result2.output
    assert "pulada" in result2.output


def test_process_course_notion_error_does_not_stop_other_lessons(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """An HTTP error syncing one lesson should leave continue_on_error=True behaviour intact."""
    config_file = _write_config_with_notion(tmp_path, output_root)
    from aulaforge.notion import NotionAvailability

    monkeypatch.setattr(
        cli_module,
        "check_notion_dependencies",
        lambda cfg: NotionAvailability(errors=[], token="tk", database_id="db"),
    )

    call_count = 0
    import aulaforge.checkpoints as chk_module
    def flaky_sync(course: object, lesson: object, *args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        from aulaforge.notion_client import NotionAPIError
        raise NotionAPIError("falha simulada", status_code=500)

    monkeypatch.setattr(chk_module, "sync_lesson_to_notion", flaky_sync)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    # All 4 lessons attempted, all Notion syncs failed => processing failure exit code.
    assert result.exit_code == PROCESSING_FAILURE_EXIT_CODE
    # But all lesson dirs should still exist (batch continued past each failure).
    course_output = output_root / course_dir.name
    lesson_dirs = [p for p in course_output.iterdir() if p.is_dir()]
    assert len(lesson_dirs) == 4
    assert call_count == 4


def test_process_course_skips_dependency_check_when_nothing_needs_transcription(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)

    # First run: all steps complete via mocked happy path.
    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    # Second run: nothing has changed, so NEITHER dependency check should run.
    def boom_transcription() -> list[str]:
        raise AssertionError("check_transcription_dependencies nao deveria ser chamado")

    def boom_ollama(base_url: str, model: str) -> list[str]:
        raise AssertionError("check_ollama_dependencies nao deveria ser chamado")

    monkeypatch.setattr(cli_module, "check_transcription_dependencies", boom_transcription)
    monkeypatch.setattr(cli_module, "check_ollama_dependencies", boom_ollama)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output


# ── OCR CLI tests ─────────────────────────────────────────────────────────────


def _write_config_with_ocr(tmp_path: Path, output_root: Path) -> Path:
    config_file = tmp_path / "aulaforge.yaml"
    config_file.write_text(
        f'project:\n  output_dir: "{output_root.as_posix()}"\nocr:\n  enabled: true\n',
        encoding="utf-8",
    )
    return config_file


@pytest.fixture
def mock_ocr_success(
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> LoadModelSpy:
    """Make the OCR path succeed without real FFmpeg or Tesseract."""
    from aulaforge.models import OcrFrameResult, StepLogEntry

    monkeypatch.setattr(cli_module, "check_ocr_dependencies", lambda lang: [])

    fake_result = OcrFrameResult(
        timestamp="00:00:00",
        frame_path="frames/00-00-00.png",
        screen_type="other",
        text="",
        confidence="low",
    )

    def _fake_ocr(lesson: object, ocr_hash: str, cfg: object) -> object:
        from datetime import datetime

        import aulaforge.checkpoints as _chk
        from aulaforge.checkpoints import OCR_STEP, PROCESSING_LOG_FILENAME
        from aulaforge.models import Status
        entry = StepLogEntry(
            step=OCR_STEP,
            status=Status.COMPLETED,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            source_hash=ocr_hash,
        )
        lesson_obj = lesson  # type: ignore[assignment]
        _chk.append_processing_log(
            lesson_obj.output_dir / PROCESSING_LOG_FILENAME,  # type: ignore[attr-defined]
            lesson_obj.slug,  # type: ignore[attr-defined]
            entry,
        )
        # Create the expected output files so needs_ocr_processing is happy on re-run
        for name in ("04_OCR_TELA.json", "05_OCR_TELA.md",
                      "06_CODIGOS_DETECTADOS.md", "07_COMANDOS_TERMINAL.md"):
            (lesson_obj.output_dir / name).write_text("[]", encoding="utf-8")  # type: ignore[attr-defined]
        (lesson_obj.output_dir / "frames").mkdir(exist_ok=True)  # type: ignore[attr-defined]
        return [fake_result], entry

    monkeypatch.setattr(cli_module, "process_lesson_ocr", _fake_ocr)
    return mock_notes_success


def test_ocr_skipped_when_disabled(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_notes_success: LoadModelSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ocr.enabled=false (default), check_ocr_dependencies must never be called."""
    config_file = _write_config(tmp_path, output_root)

    def boom(lang: str) -> list[str]:
        raise AssertionError("check_ocr_dependencies nao deve ser chamado quando disabled")

    monkeypatch.setattr(cli_module, "check_ocr_dependencies", boom)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    assert result.exit_code == 0, result.output


def test_ocr_dependency_missing_gives_exit_code_2(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_notes_success: LoadModelSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Tesseract => exit code 2; batch must continue (other lessons still run)."""
    config_file = _write_config_with_ocr(tmp_path, output_root)
    monkeypatch.setattr(
        cli_module,
        "check_ocr_dependencies",
        lambda lang: ["tesseract nao encontrado no PATH"],
    )

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    assert result.exit_code == DEPENDENCY_MISSING_EXIT_CODE


def test_ocr_processes_all_lessons_when_enabled(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_ocr_success: LoadModelSpy,
) -> None:
    """When OCR is enabled and mocked, all 4 lessons get a COMPLETED ocr entry."""
    from aulaforge.checkpoints import OCR_STEP, PROCESSING_LOG_FILENAME, read_processing_log
    from aulaforge.discovery import discover_course
    from aulaforge.models import Status

    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        f'project:\n  output_dir: "{output_root.as_posix()}"\nocr:\n  enabled: true\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    assert result.exit_code == 0, result.output

    # Each lesson's processing_log should have a completed OCR entry
    course = discover_course(course_dir, output_root)
    for lesson in course.lessons:
        log = read_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug)
        ocr_entry = log.latest(OCR_STEP)
        assert ocr_entry is not None
        assert ocr_entry.status == Status.COMPLETED


def test_ocr_skipped_on_second_run_when_nothing_changed(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_ocr_success: LoadModelSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a successful OCR run, the second run skips without calling check_ocr_dependencies."""
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        f'project:\n  output_dir: "{output_root.as_posix()}"\nocr:\n  enabled: true\n',
        encoding="utf-8",
    )

    # First run: OCR completes
    result1 = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    assert result1.exit_code == 0, result1.output

    # Second run: nothing changed; check_ocr_dependencies must NOT be called
    def boom(lang: str) -> list[str]:
        raise AssertionError("check_ocr_dependencies nao deve ser chamado no segundo run")

    monkeypatch.setattr(cli_module, "check_ocr_dependencies", boom)

    result2 = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    assert result2.exit_code == 0, result2.output


def test_ocr_failure_in_one_lesson_does_not_abort_batch(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_notes_success: LoadModelSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An OCR error on one lesson must not abort the entire batch."""
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        f'project:\n  output_dir: "{output_root.as_posix()}"\nocr:\n  enabled: true\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_module, "check_ocr_dependencies", lambda lang: [])

    call_count = {"n": 0}

    def flaky_ocr(lesson: object, ocr_hash: str, cfg: object) -> object:
        call_count["n"] += 1
        raise RuntimeError("ocr explodiu")

    monkeypatch.setattr(cli_module, "process_lesson_ocr", flaky_ocr)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    # All 4 lessons attempted (batch did not abort after first failure)
    assert call_count["n"] == 4
    assert result.exit_code == PROCESSING_FAILURE_EXIT_CODE


# ── Phase 8 — --resume flag ───────────────────────────────────────────────────


def test_resume_skips_all_lessons_when_all_completed(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """After a full successful run, --resume skips every lesson (none has FAILED steps)."""
    config_file = _write_config(tmp_path, output_root)
    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    processed: list[str] = []
    real_foundation = cli_module.process_lesson_foundation

    def spy_foundation(lesson: Any, force: bool = False) -> Any:
        processed.append(lesson.slug)
        return real_foundation(lesson, force=force)

    monkeypatch.setattr(cli_module, "process_lesson_foundation", spy_foundation)
    result = runner.invoke(
        app, ["process-course", str(course_dir), "--config", str(config_file), "--resume"]
    )

    assert result.exit_code == 0, result.output
    assert processed == [], "nenhuma aula deveria ser processada: todas concluidas, --resume ativo"


def test_resume_reprocesses_only_lessons_with_failed_step(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """--resume reprocesses only the lesson that has a FAILED entry in its log."""
    from datetime import datetime

    from aulaforge.checkpoints import PROCESSING_LOG_FILENAME, append_processing_log
    from aulaforge.discovery import discover_course
    from aulaforge.models import Status, StepLogEntry

    config_file = _write_config(tmp_path, output_root)
    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    course = discover_course(course_dir, output_root)
    first_lesson = course.lessons[0]
    now = datetime.now()
    append_processing_log(
        first_lesson.output_dir / PROCESSING_LOG_FILENAME,
        first_lesson.slug,
        StepLogEntry(
            step="transcription",
            status=Status.FAILED,
            started_at=now,
            finished_at=now,
            message="injected failure for resume test",
        ),
    )

    processed: list[str] = []
    real_foundation = cli_module.process_lesson_foundation

    def spy_foundation(lesson: Any, force: bool = False) -> Any:
        processed.append(lesson.slug)
        return real_foundation(lesson, force=force)

    monkeypatch.setattr(cli_module, "process_lesson_foundation", spy_foundation)
    result = runner.invoke(
        app, ["process-course", str(course_dir), "--config", str(config_file), "--resume"]
    )

    assert result.exit_code == 0, result.output
    assert len(processed) == 1, "apenas a aula com FAILED deve ser reprocessada"
    assert processed[0] == first_lesson.slug


def test_resume_processes_course_normally_when_no_log_exists(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_notes_success: LoadModelSpy,
) -> None:
    """Fresh course with no processing_log.json: --resume processes everything normally."""
    config_file = _write_config(tmp_path, output_root)
    result = runner.invoke(
        app, ["process-course", str(course_dir), "--config", str(config_file), "--resume"]
    )

    assert result.exit_code == 0, result.output
    course_output = output_root / course_dir.name
    lesson_dirs = [p for p in course_output.iterdir() if p.is_dir()]
    assert len(lesson_dirs) == 4


def test_resume_force_flag_overrides_resume(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """--force takes precedence over --resume: all lessons are reprocessed."""
    config_file = _write_config(tmp_path, output_root)
    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    processed: list[str] = []
    real_foundation = cli_module.process_lesson_foundation

    def spy_foundation(lesson: Any, force: bool = False) -> Any:
        processed.append(lesson.slug)
        return real_foundation(lesson, force=force)

    monkeypatch.setattr(cli_module, "process_lesson_foundation", spy_foundation)
    result = runner.invoke(
        app,
        ["process-course", str(course_dir), "--config", str(config_file), "--resume", "--force"],
    )

    assert result.exit_code == 0, result.output
    assert len(processed) == 4, "--force deve reprocessar todas as 4 aulas independente de --resume"


# ── Phase 8 — Retry ───────────────────────────────────────────────────────────


@pytest.fixture
def single_lesson_course_dir(tmp_path: Path) -> Path:
    """Course with a single lesson for retry tests (avoids multi-lesson counter sharing)."""
    course = tmp_path / "Curso Retry"
    course.mkdir()
    (course / "aula 1 - introducao.mp4").write_bytes(b"video-retry")
    return course


def test_transcription_retry_exhausted_records_failed(
    single_lesson_course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """When all retry_attempts for transcription fail, the step is FAILED and exit code is 1."""
    import types

    config_file = _write_config(tmp_path, output_root)
    monkeypatch.setattr(cli_module, "time", types.SimpleNamespace(sleep=lambda s: None))

    call_count = {"n": 0}

    def always_fail(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        raise RuntimeError("simulated transcription failure")

    monkeypatch.setattr(cli_module, "process_lesson_transcription", always_fail)

    result = runner.invoke(
        app, ["process-course", str(single_lesson_course_dir), "--config", str(config_file)]
    )

    assert result.exit_code == PROCESSING_FAILURE_EXIT_CODE
    assert call_count["n"] == 3  # retry_attempts default = 3


def test_transcription_retry_succeeds_on_last_attempt(
    single_lesson_course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """Transient transcription failures followed by a success → exit code 0, 3 total calls."""
    import types
    from datetime import datetime

    from aulaforge.models import Status, StepLogEntry

    config_file = _write_config(tmp_path, output_root)
    monkeypatch.setattr(cli_module, "time", types.SimpleNamespace(sleep=lambda s: None))

    call_count = {"n": 0}

    def flaky_transcription(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("transient failure")
        now = datetime.now()
        return ("transcript-text", StepLogEntry(
            step="transcription",
            status=Status.COMPLETED,
            started_at=now,
            finished_at=now,
        ))

    monkeypatch.setattr(cli_module, "process_lesson_transcription", flaky_transcription)

    result = runner.invoke(
        app, ["process-course", str(single_lesson_course_dir), "--config", str(config_file)]
    )

    assert result.exit_code == 0, result.output
    assert call_count["n"] == 3  # 2 failures + 1 success = retry_attempts calls


def test_transcription_model_not_reloaded_between_retries(
    single_lesson_course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """Even when transcription retries, the Whisper model is loaded exactly once per run."""
    import types
    from datetime import datetime

    from aulaforge.models import Status, StepLogEntry

    config_file = _write_config(tmp_path, output_root)
    monkeypatch.setattr(cli_module, "time", types.SimpleNamespace(sleep=lambda s: None))

    call_count = {"n": 0}

    def flaky_transcription(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("transient failure")
        now = datetime.now()
        return ("transcript-text", StepLogEntry(
            step="transcription",
            status=Status.COMPLETED,
            started_at=now,
            finished_at=now,
        ))

    monkeypatch.setattr(cli_module, "process_lesson_transcription", flaky_transcription)

    runner.invoke(
        app, ["process-course", str(single_lesson_course_dir), "--config", str(config_file)]
    )

    assert mock_notes_success.call_count == 1, "modelo Whisper deve ser carregado 1x, nao por retry"


def test_notes_retry_exhausted_records_failed(
    single_lesson_course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """When all retry_attempts for notes fail, the step is FAILED and exit code is 1."""
    import types

    config_file = _write_config(tmp_path, output_root)
    monkeypatch.setattr(cli_module, "time", types.SimpleNamespace(sleep=lambda s: None))

    call_count = {"n": 0}

    def always_fail(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        raise RuntimeError("simulated notes failure")

    monkeypatch.setattr(cli_module, "process_lesson_notes", always_fail)

    result = runner.invoke(
        app, ["process-course", str(single_lesson_course_dir), "--config", str(config_file)]
    )

    assert result.exit_code == PROCESSING_FAILURE_EXIT_CODE
    assert call_count["n"] == 3  # retry_attempts default = 3


def test_notes_retry_succeeds_on_last_attempt(
    single_lesson_course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_notes_success: LoadModelSpy,
) -> None:
    """Transient notes failures followed by a success → exit code 0, 3 total calls."""
    import types
    from datetime import datetime

    from aulaforge.models import Status, StepLogEntry

    config_file = _write_config(tmp_path, output_root)
    monkeypatch.setattr(cli_module, "time", types.SimpleNamespace(sleep=lambda s: None))

    call_count = {"n": 0}

    def flaky_notes(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("transient notes failure")
        now = datetime.now()
        return ("# nota fake", StepLogEntry(
            step="notes",
            status=Status.COMPLETED,
            started_at=now,
            finished_at=now,
        ))

    monkeypatch.setattr(cli_module, "process_lesson_notes", flaky_notes)

    result = runner.invoke(
        app, ["process-course", str(single_lesson_course_dir), "--config", str(config_file)]
    )

    assert result.exit_code == 0, result.output
    assert call_count["n"] == 3  # 2 failures + 1 success = retry_attempts calls

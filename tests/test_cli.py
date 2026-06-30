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
    mock_transcription_success: LoadModelSpy,
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


def test_process_course_loads_whisper_model_only_once_per_run(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_transcription_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output
    assert mock_transcription_success.call_count == 1, "modelo deve ser carregado 1x, nao por aula"


def test_process_course_continues_after_one_lesson_fails(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_transcription_success: LoadModelSpy,
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
    mock_transcription_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)

    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    calls_after_first_run = mock_transcription_success.call_count
    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output
    assert "pulada" in result.output
    # Foundation and transcription were both already done; no model load needed again.
    assert mock_transcription_success.call_count == calls_after_first_run


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


def test_process_course_skips_dependency_check_when_nothing_needs_transcription(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_transcription_success: LoadModelSpy,
) -> None:
    config_file = _write_config(tmp_path, output_root)

    # First run: everything gets transcribed (mocked happy path).
    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    # Second run: nothing should need transcription anymore, so the dependency
    # check must never even be called -- prove it by making it explode if called.
    def boom() -> list[str]:
        raise AssertionError("check_transcription_dependencies nao deveria ser chamado")

    monkeypatch.setattr(cli_module, "check_transcription_dependencies", boom)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output

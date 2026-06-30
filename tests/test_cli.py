"""Smoke tests for aulaforge.cli using Typer's CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import aulaforge.cli as cli_module
from aulaforge.cli import app

runner = CliRunner()


def _write_config(tmp_path: Path, output_root: Path) -> Path:
    config_file = tmp_path / "aulaforge.yaml"
    config_file.write_text(
        f'project:\n  output_dir: "{output_root.as_posix()}"\n', encoding="utf-8"
    )
    return config_file


def test_process_course_fails_fast_for_missing_explicit_config(
    course_dir: Path, output_root: Path
) -> None:
    result = runner.invoke(
        app, ["process-course", str(course_dir), "--config", "__missing__.yaml"]
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output, "nao deve vazar traceback bruto"
    assert "Erro de configuracao" in result.output
    assert "__missing__.yaml" in result.output


def test_process_course_runs_end_to_end(
    course_dir: Path, output_root: Path, tmp_path: Path
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


def test_process_course_continues_after_one_lesson_fails(
    course_dir: Path, output_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = _write_config(tmp_path, output_root)
    original = cli_module.process_lesson_foundation

    def flaky(lesson, force=False):  # type: ignore[no-untyped-def]
        if lesson.number == 1:
            raise RuntimeError("falha simulada")
        return original(lesson, force=force)

    monkeypatch.setattr(cli_module, "process_lesson_foundation", flaky)

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 1
    assert "1 com falha" in result.output

    course_output = output_root / course_dir.name
    lesson_dirs = [p for p in course_output.iterdir() if p.is_dir()]
    assert len(lesson_dirs) == 4, "todas as pastas de aula devem existir mesmo com 1 falha"


def test_process_course_second_run_skips_unchanged(
    course_dir: Path, output_root: Path, tmp_path: Path
) -> None:
    config_file = _write_config(tmp_path, output_root)

    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])
    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 0, result.output
    assert "pulada" in result.output

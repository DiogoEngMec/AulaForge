"""Tests for aulaforge.reports — batch report generation (Phase 8)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from aulaforge.models import Course, Status, StepLogEntry
from aulaforge.reports import write_batch_summary

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _entry(
    step: str,
    status: Status,
    duration_seconds: float = 1.0,
) -> StepLogEntry:
    now = datetime.now()
    return StepLogEntry(
        step=step,
        status=status,
        started_at=now,
        finished_at=now + timedelta(seconds=duration_seconds),
    )


def _fake_course(name: str, tmp_path: Path) -> Course:
    return Course(
        name=name,
        input_path=tmp_path / name,
        output_path=tmp_path / "output" / name,
        lessons=[],
    )


# ── write_batch_summary ───────────────────────────────────────────────────────


def test_write_batch_summary_creates_report_and_json(tmp_path: Path) -> None:
    course = _fake_course("Curso", tmp_path)
    entries = {
        "aula_01": {"foundation": _entry("foundation", Status.COMPLETED, 2.0)},
    }
    write_batch_summary(course, entries)

    assert (course.output_path / "batch_report.md").exists()
    assert (course.output_path / "batch_log.json").exists()


def test_batch_log_json_contract(tmp_path: Path) -> None:
    course = _fake_course("Curso", tmp_path)
    entries = {
        "aula_01": {
            "foundation": _entry("foundation", Status.COMPLETED),
            "transcription": _entry("transcription", Status.FAILED),
        },
    }
    write_batch_summary(course, entries)

    data = json.loads((course.output_path / "batch_log.json").read_text(encoding="utf-8"))
    assert data["course"] == "Curso"
    assert data["lessons"]["aula_01"]["foundation"] == "completed"
    assert data["lessons"]["aula_01"]["transcription"] == "failed"


def test_batch_report_contains_duration(tmp_path: Path) -> None:
    course = _fake_course("Curso", tmp_path)
    entries = {
        "aula_01": {"foundation": _entry("foundation", Status.COMPLETED, 3.5)},
    }
    write_batch_summary(course, entries)

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "3.5s" in report


def test_batch_report_totals_line(tmp_path: Path) -> None:
    course = _fake_course("Curso", tmp_path)
    entries = {
        "aula_01": {
            "foundation": _entry("foundation", Status.COMPLETED),
            "transcription": _entry("transcription", Status.FAILED),
            "notes": _entry("notes", Status.SKIPPED_UNCHANGED),
        },
        "aula_02": {
            "foundation": _entry("foundation", Status.COMPLETED),
            "transcription": _entry("transcription", Status.SKIPPED_UNCHANGED),
            "notes": _entry("notes", Status.SKIPPED_UNCHANGED),
        },
    }
    write_batch_summary(course, entries)

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "2 concluída(s)" in report
    assert "3 pulada(s)" in report
    assert "1 com falha" in report


def test_batch_report_average_time_per_step(tmp_path: Path) -> None:
    course = _fake_course("Curso", tmp_path)
    entries = {
        "aula_01": {"transcription": _entry("transcription", Status.COMPLETED, 4.0)},
        "aula_02": {"transcription": _entry("transcription", Status.COMPLETED, 6.0)},
    }
    write_batch_summary(course, entries)

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    # Média de 4s e 6s = 5.0s
    assert "transcription: 5.0s" in report


def test_batch_report_skipped_steps_excluded_from_average(tmp_path: Path) -> None:
    """SKIPPED_UNCHANGED steps must not contribute to average time."""
    course = _fake_course("Curso", tmp_path)
    entries = {
        "aula_01": {"transcription": _entry("transcription", Status.COMPLETED, 10.0)},
        "aula_02": {"transcription": _entry("transcription", Status.SKIPPED_UNCHANGED, 0.0)},
    }
    write_batch_summary(course, entries)

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    # Somente aula_01 contribui → média = 10.0s (não 5.0s)
    assert "transcription: 10.0s" in report


def test_batch_report_no_average_line_when_all_skipped(tmp_path: Path) -> None:
    """When every step is SKIPPED_UNCHANGED, no 'Tempo médio' line is written."""
    course = _fake_course("Curso", tmp_path)
    entries = {
        "aula_01": {"foundation": _entry("foundation", Status.SKIPPED_UNCHANGED)},
    }
    write_batch_summary(course, entries)

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "Tempo médio" not in report


def test_batch_report_dynamic_columns(tmp_path: Path) -> None:
    """Columns are discovered dynamically — a new step appears without code changes."""
    course = _fake_course("Curso", tmp_path)
    entries = {
        "aula_01": {
            "foundation": _entry("foundation", Status.COMPLETED),
            "outputs": _entry("outputs", Status.COMPLETED),
        },
    }
    write_batch_summary(course, entries)

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "| Foundation |" in report or "Foundation" in report
    assert "| Outputs |" in report or "Outputs" in report


def test_batch_report_empty_entries(tmp_path: Path) -> None:
    """Empty entries dict must produce a valid report without crashing."""
    course = _fake_course("Curso", tmp_path)
    write_batch_summary(course, {})

    report = (course.output_path / "batch_report.md").read_text(encoding="utf-8")
    assert "Batch report" in report
    assert "0 concluída(s)" in report

"""Shared pytest fixtures for AulaForge tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def course_dir(tmp_path: Path) -> Path:
    """A fake course folder with a handful of dummy 'video' files."""
    course = tmp_path / "Curso Django CRM"
    course.mkdir()
    (course / "aula 1 - introducao.mp4").write_bytes(b"video-bytes-1")
    (course / "aula 02 - modelos.mp4").write_bytes(b"video-bytes-2-longer")
    (course / "10 - deploy.mkv").write_bytes(b"video-bytes-deploy")
    (course / "extra sem numero.mov").write_bytes(b"video-bytes-extra")
    (course / "notas.txt").write_text("nao e um video", encoding="utf-8")
    return course


@pytest.fixture
def output_root(tmp_path: Path) -> Path:
    return tmp_path / "output"

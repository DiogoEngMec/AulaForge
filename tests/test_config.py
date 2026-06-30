"""Tests for aulaforge.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from aulaforge.config import AulaForgeConfig, load_config, resolve_config_path


def test_load_config_defaults_when_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = load_config(None)
    assert isinstance(cfg, AulaForgeConfig)
    assert cfg.project.name == "AulaForge"
    assert cfg.processing.skip_if_unchanged is True


def test_load_config_from_explicit_path(tmp_path: Path) -> None:
    config_file = tmp_path / "custom.yaml"
    config_file.write_text(
        "project:\n  name: Curso X\nprocessing:\n  skip_if_unchanged: false\n",
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.project.name == "Curso X"
    assert cfg.processing.skip_if_unchanged is False


def test_load_config_falls_back_to_cwd_aulaforge_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "aulaforge.yaml").write_text("project:\n  name: Pelo CWD\n", encoding="utf-8")
    cfg = load_config(None)
    assert cfg.project.name == "Pelo CWD"


def test_load_config_parses_transcription_section(tmp_path: Path) -> None:
    config_file = tmp_path / "full.yaml"
    config_file.write_text(
        "project:\n  name: Curso Y\n"
        "transcription:\n  model: large\n  save_raw: false\n",
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.transcription.model == "large"
    assert cfg.transcription.save_raw is False
    assert cfg.transcription.save_timestamps is True  # default untouched


def test_load_config_defaults_transcription_section_when_absent(tmp_path: Path) -> None:
    config_file = tmp_path / "minimal.yaml"
    config_file.write_text("project:\n  name: Curso Z\n", encoding="utf-8")
    cfg = load_config(config_file)
    assert cfg.transcription.model == "medium"
    assert cfg.transcription.engine == "whisper-local"


def test_load_config_ignores_sections_for_phases_not_yet_implemented(tmp_path: Path) -> None:
    config_file = tmp_path / "full.yaml"
    config_file.write_text(
        "project:\n  name: Curso Y\n"
        "processing:\n  batch: true\n"
        "ocr:\n  enabled: true\n"
        "notion:\n  enabled: true\n",
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.project.name == "Curso Y"


def test_resolve_config_path_raises_for_missing_explicit_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError):
        resolve_config_path(missing)

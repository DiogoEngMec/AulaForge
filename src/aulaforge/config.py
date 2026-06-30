"""Configuration loading for AulaForge.

Only the `project` and `processing` sections of CONFIG_EXAMPLE.yaml are
modeled in Phase 1 (the only sections this phase uses). Other sections
(transcription, ocr, llm, notion, outputs) belong to later phases and are
accepted-but-ignored so a real, full config file can already be loaded
without validation errors.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG_FILENAME = "aulaforge.yaml"


class ProjectConfig(BaseModel):
    name: str = "AulaForge"
    output_dir: Path = Path("./output")
    language: str = "pt-BR"
    keep_technical_terms_in_english: bool = True


class ProcessingConfig(BaseModel):
    mode: str = "documentation_project"
    batch: bool = True
    sequential: bool = True
    continue_on_error: bool = True
    retry_attempts: int = 3
    chunk_minutes: int = 15
    skip_if_unchanged: bool = True
    auto_confirm: bool = True


class AulaForgeConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AULAFORGE_", extra="ignore")

    project: ProjectConfig = ProjectConfig()
    processing: ProcessingConfig = ProcessingConfig()


def resolve_config_path(config_path: Path | None) -> Path | None:
    """Resolve which YAML file (if any) should be loaded.

    Priority: explicit `--config` path > `./aulaforge.yaml` in the current
    directory > no file (internal defaults apply). CONFIG_EXAMPLE.yaml at the
    repo root is documentation only and is never loaded implicitly.
    """
    if config_path is not None:
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        return config_path
    default_path = Path(DEFAULT_CONFIG_FILENAME)
    return default_path if default_path.exists() else None


def load_config(config_path: Path | None = None) -> AulaForgeConfig:
    """Load AulaForge config from YAML, falling back to internal defaults."""
    resolved = resolve_config_path(config_path)
    if resolved is None:
        return AulaForgeConfig()
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {resolved}")
    return AulaForgeConfig(**raw)

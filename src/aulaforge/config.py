"""Configuration loading for AulaForge.

Only the sections used by phases implemented so far (`project`, `processing`,
`transcription`, `llm`, `notion`) are modeled. Other sections (ocr, outputs)
belong to later phases and are accepted-but-ignored so a real, full config
file can already be loaded without validation errors.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, PositiveInt
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


class TranscriptionConfig(BaseModel):
    engine: str = "whisper-local"
    model: str = "medium"
    save_raw: bool = True
    save_timestamps: bool = True
    send_raw_to_notion: bool = False


class LlmConfig(BaseModel):
    provider: str = "ollama"
    model: str = "qwen3:30b"
    temperature: float = 0.2
    max_retries: int = 3
    base_url: str = "http://localhost:11434"
    max_input_chars: int = 10000


class OcrConfig(BaseModel):
    """Phase 5 OCR config.

    Disabled by default because frame extraction + Tesseract can be slow for
    long videos. The user must install `aulaforge[ocr]` and have Tesseract on
    PATH before enabling this.
    """

    enabled: bool = False
    engine: str = "local"
    frame_interval_seconds: int = 5
    lang: str = "por+eng"
    min_text_change_chars: int = 30
    save_screenshots_local: bool = True
    send_screenshots_to_notion: bool = False
    show_low_confidence_code_in_notion: bool = True
    detect_code: bool = True
    detect_terminal: bool = True
    detect_screen_type: bool = True
    preprocess_with_opencv: bool = True


class NotionConfig(BaseModel):
    """Phase 4 config. `enabled` defaults to False: Notion sync is opt-in until

    the user has created/shared the database and set NOTION_TOKEN, unlike
    CONFIG_EXAMPLE.yaml's illustrative `enabled: true`.
    """

    enabled: bool = False
    auto_send: bool = True
    mode: str = "course_page"
    database_id: str | None = None
    database_name: str = "Aulas Processadas"
    token_env_var: str = "NOTION_TOKEN"
    page_per_course: bool = True
    update_existing_page: bool = True
    lesson_blocks_as_toggle_h1: bool = True
    send_raw_transcript: bool = False
    send_screenshots: bool = False
    api_version: str = "2022-06-28"
    base_url: str = "https://api.notion.com/v1"
    request_timeout: float = 30.0
    max_retries: int = 3


class MergeConfig(BaseModel):
    """Phase 6 merge config. Habilitado por padrão: sem dependências externas."""

    enabled: bool = True
    window_seconds: float = 15.0  # janela de associação OCR→transcrição (segundos)
    group_minutes: PositiveInt = 10  # agrupamento de blocos no Markdown (minutos)


class AulaForgeConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AULAFORGE_", extra="ignore")

    project: ProjectConfig = ProjectConfig()
    processing: ProcessingConfig = ProcessingConfig()
    transcription: TranscriptionConfig = TranscriptionConfig()
    llm: LlmConfig = LlmConfig()
    notion: NotionConfig = NotionConfig()
    ocr: OcrConfig = OcrConfig()
    merge: MergeConfig = MergeConfig()


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

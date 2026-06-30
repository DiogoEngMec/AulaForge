"""Local Whisper transcription: model loading, raw/timestamped/clean outputs.

`openai-whisper` is the official open-source package that runs the Whisper
model entirely locally via PyTorch (model weights download once on first
use, then it runs fully offline) — this is not a call to OpenAI's paid
cloud API, keeping this local-first per `local-first.md`.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from aulaforge.audio import is_ffmpeg_available
from aulaforge.chunking import chunk_segments, format_timestamp
from aulaforge.models import TranscriptSegment

# openai-whisper is an optional dependency (see pyproject.toml's
# `transcription` extra); avoid importing it at module level so this module
# (and aulaforge.cli, which imports it) stays importable without it. The
# real `whisper.Whisper` object is duck-typed through this alias.
WhisperModel = Any

RAW_TRANSCRIPT_FILENAME = "01_TRANSCRICAO_BRUTA.txt"
TIMESTAMPED_TRANSCRIPT_FILENAME = "02_TRANSCRICAO_COM_TIMESTAMPS.json"
CLEAN_TRANSCRIPT_FILENAME = "03_TRANSCRICAO_LIMPA.md"


def is_whisper_available() -> bool:
    """True if the `whisper` package (pip name `openai-whisper`) is importable."""
    return importlib.util.find_spec("whisper") is not None


def check_transcription_dependencies() -> list[str]:
    """User-facing error messages for missing local dependencies (empty if OK)."""
    errors: list[str] = []
    if not is_ffmpeg_available():
        errors.append(
            "ffmpeg nao encontrado no PATH. Instale via "
            "https://ffmpeg.org/download.html (ou 'winget install ffmpeg' no Windows)."
        )
    if not is_whisper_available():
        errors.append(
            "Pacote 'openai-whisper' nao instalado. Rode: "
            'pip install -e ".[transcription]" (ou inclua o extra '
            "'transcription' no seu ambiente)."
        )
    return errors


def whisper_language_hint(language: str) -> str | None:
    """Convert a tag like 'pt-BR' into a Whisper language code like 'pt'.

    Falls back to None (Whisper auto-detects) when the tag isn't a clean
    2-letter primary subtag — passing a wrong code would force a bad
    transcription, whereas auto-detect just costs one extra detection pass.
    """
    primary = language.split("-")[0].strip().lower()
    if len(primary) == 2 and primary.isalpha():
        return primary
    return None


def load_whisper_model(model_name: str) -> WhisperModel:
    """Load (downloading on first use) a Whisper model by name, e.g. 'medium'."""
    import whisper

    try:
        return whisper.load_model(model_name)
    except Exception as exc:
        raise RuntimeError(
            f"Falha ao carregar o modelo Whisper '{model_name}'. Se for a "
            "primeira execucao, confirme que ha internet disponivel para "
            "baixar os pesos do modelo (depois disso roda offline)."
        ) from exc


def transcribe_audio(
    model: WhisperModel, audio_path: Path, language: str | None = None
) -> list[TranscriptSegment]:
    """Run Whisper on `audio_path`, returning ordered segments."""
    result = model.transcribe(str(audio_path), language=language)
    return [
        TranscriptSegment(start=segment["start"], end=segment["end"], text=segment["text"].strip())
        for segment in result.get("segments", [])
    ]


def write_raw_transcript(output_dir: Path, segments: list[TranscriptSegment]) -> Path:
    """Write the raw transcript: plain concatenated text, UTF-8."""
    path = output_dir / RAW_TRANSCRIPT_FILENAME
    text = " ".join(segment.text.strip() for segment in segments).strip()
    path.write_text(text, encoding="utf-8")
    return path


def write_timestamped_transcript(output_dir: Path, segments: list[TranscriptSegment]) -> Path:
    """Write the timestamped transcript: JSON list of segments per DATA_CONTRACTS.md."""
    path = output_dir / TIMESTAMPED_TRANSCRIPT_FILENAME
    payload = [segment.model_dump() for segment in segments]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_clean_transcript(
    output_dir: Path, segments: list[TranscriptSegment], chunk_minutes: int
) -> Path:
    """Write the clean transcript: segments grouped into chunk_minutes blocks.

    "Clean" here means structurally reformatted (paragraphs per time block
    with timestamp headers), not semantically rewritten — any AI-based
    rewriting belongs to Phase 3 (Ollama), not here.
    """
    path = output_dir / CLEAN_TRANSCRIPT_FILENAME
    blocks = chunk_segments(segments, chunk_minutes)
    lines: list[str] = ["# Transcricao limpa", ""]
    for block in blocks:
        if not block:
            continue
        start_label = format_timestamp(block[0].start)
        end_label = format_timestamp(block[-1].end)
        lines.append(f"## Bloco ({start_label} - {end_label})")
        lines.append("")
        lines.append(" ".join(segment.text.strip() for segment in block).strip())
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path

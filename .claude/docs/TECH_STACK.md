# Technical stack

## Language

- Python 3.11+

## CLI

- Typer
- Rich

## Config

- YAML
- Pydantic / pydantic-settings

## Audio/video

- FFmpeg
- ffmpeg-python as wrapper when useful

## Transcription

- Whisper local

## LLM

- Ollama local
- Model: `qwen3:30b`

## OCR

- Local OCR stack, initially Tesseract/Pytesseract or another local option.
- Optional OpenCV preprocessing.

## Notion

- Notion MCP integration in Phase 4.

## Quality

- pytest
- ruff
- mypy

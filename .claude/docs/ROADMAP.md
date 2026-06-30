# Roadmap — AulaForge

## Phase 1 — Foundation

- Python package structure.
- CLI with `process-course`.
- Config loader.
- Course video discovery.
- Lesson ordering by filename number.
- Output folder structure.
- `source_info.json`.
- Hash/checkpoint skip if unchanged.
- Basic logging.
- Minimal tests.

## Phase 2 — Transcription

- FFmpeg audio extraction.
- Whisper local transcription.
- Timestamped transcript.
- Raw transcript saved locally.
- Chunking into 15-minute blocks.

## Phase 3 — Local notes with Ollama

- Ollama client.
- qwen3:30b prompts.
- Structured notes in Markdown.
- Lesson note template.

## Phase 4 — Notion MCP

- Notion database/page lookup.
- Create/update one page per course.
- Toggle Heading 1 per lesson.
- Do not send raw transcripts.

## Phase 5 — OCR

- Extract frames.
- OCR local.
- Detect code, terminal, screen type.
- Save screenshots locally.

## Phase 6 — Merge audio/video

- Align transcript timestamps with OCR timestamps.
- Generate merged context.
- Mark confidence and warnings.

## Phase 7 — Claude Code/Codex outputs

- Generate Markdown contexts.
- Generate prompts.
- Generate agent ideas and skill ideas.

## Phase 8 — Robust batch / QA

- Resume/skip robustly.
- Batch report.
- Error isolation.
- Test coverage.
- Refactor for maintainability.

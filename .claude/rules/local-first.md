# Local-first rules

- Use local Whisper for transcription.
- Use local Ollama with `qwen3:30b` for LLM tasks.
- Use local OCR.
- Do not introduce cloud processing or paid APIs without explicit approval.
- Save intermediate outputs locally.
- Design for offline-friendly processing except Notion sync.
- Batch mode must not require manual confirmation.

# Architecture — AulaForge

## High-level modules

```text
src/aulaforge/
  cli.py
  config.py
  discovery.py
  models.py
  checkpoints.py
  logging_setup.py
  audio.py
  transcription.py
  chunking.py
  ollama_client.py
  notes.py
  notion.py
  video_frames.py
  ocr.py
  merge.py
  outputs.py
  reports.py
```

## Design principles

- Keep each pipeline step isolated.
- Persist intermediate artifacts.
- Use Pydantic models for contracts.
- Prefer pure functions for testability.
- Avoid side effects outside orchestrator functions.
- Never block batch mode with prompts.

## Orchestration

`process-course` should orchestrate:

1. load config;
2. discover videos;
3. create course output;
4. for each lesson, run phases available;
5. update course-level docs;
6. generate final report.

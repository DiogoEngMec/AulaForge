# CLAUDE.md — AulaForge project memory

## Identity

You are working on AulaForge, a local-first CLI tool for converting recorded course videos into structured knowledge, Notion pages, and Markdown outputs for Claude Code and Codex.

## Mandatory first step

Before planning or implementing any task, read:

```text
.claude/docs/FILE_READING_ORDER.md
```

Then follow the full reading order. Do not assume the project context from memory.

## Core principles

- Build in phases.
- Do not implement the whole system at once.
- Keep the project local-first.
- Do not add paid APIs unless explicitly approved.
- Use Whisper local for transcription.
- Use Ollama local with `qwen3:30b` for content organization.
- Use local OCR for screen/code/terminal extraction.
- Use Notion MCP only when implementing the Notion phase.
- Use sequential batch processing by default.
- Design for overnight processing without manual prompts.
- Save intermediate artifacts and logs.
- Use checkpoints and skip unchanged videos.

## Phase discipline

When asked to implement a phase:

1. Read the phase prompt.
2. State the plan.
3. Confirm what is in scope and out of scope.
4. Implement only the approved phase.
5. Run tests if possible.
6. Report changed files, tests, and limitations.

## Agent usage

Use agents as reviewers or specialists, not as an excuse to expand scope. The main useful agents are:

- `aulaforge-product-architect` for scope/product decisions.
- `python-cli-engineer` for CLI and Python architecture.
- `transcription-whisper-engineer` for Whisper and audio extraction.
- `ollama-prompt-engineer` for qwen3 prompts and structured outputs.
- `ocr-video-engineer` for frame extraction and OCR.
- `notion-mcp-integrator` for Notion MCP integration.
- `audio-video-merge-engineer` for timeline merge.
- `qa-automation-engineer` for testing and robustness.
- `docs-knowledge-engineer` for docs and generated Markdown.

# Skill: AulaForge workflow

Use this skill when working on AulaForge.

## Purpose

Guide the implementation of a local-first pipeline that converts course videos into structured knowledge, Notion pages, and Claude Code/Codex Markdown outputs.

## Workflow

1. Read `.claude/docs/FILE_READING_ORDER.md`.
2. Confirm current phase.
3. Read the phase prompt.
4. Plan before coding.
5. Implement only the approved phase.
6. Save intermediate artifacts.
7. Run tests.
8. Report changed files and remaining risks.

## Non-negotiables

- Local-first.
- No paid APIs.
- Sequential processing.
- Batch mode without manual prompts.
- Checkpoints and logs.
- Notion only through the Notion MCP phase.

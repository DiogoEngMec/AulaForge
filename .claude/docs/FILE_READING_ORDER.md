# File reading order — AulaForge

Claude Code must read this file first, then read every file listed below before planning a phase.

## Required root files

1. `README.md`
2. `PRD.md`
3. `PROJECT_TREE.md`
4. `CONFIG_EXAMPLE.yaml`
5. `pyproject.toml`
6. `.gitignore`

## Claude project memory/config

7. `.claude/CLAUDE.md`
8. `.claude/settings.json`
9. `.claude/settings.local.json`

## Skill

10. `.claude/skills/aulaforge/SKILL.md`

## Rules

11. `.claude/rules/local-first.md`
12. `.claude/rules/python.md`
13. `.claude/rules/notion.md`
14. `.claude/rules/docs.md`

## Planning docs

15. `.claude/docs/ROADMAP.md`
16. `.claude/docs/ARCHITECTURE.md`
17. `.claude/docs/TECH_STACK.md`
18. `.claude/docs/PIPELINE.md`
19. `.claude/docs/DATA_CONTRACTS.md`
20. `.claude/docs/MCP_SETUP.md`
21. `.claude/docs/NOTION_DATABASE_SCHEMA.md`
22. `.claude/docs/NOTION_PAGE_TEMPLATE.md`
23. `.claude/docs/OCR_STRATEGY.md`
24. `.claude/docs/TRANSCRIPTION_STRATEGY.md`
25. `.claude/docs/QUALITY_ASSURANCE.md`
26. `.claude/docs/ERROR_HANDLING_AND_CHECKPOINTS.md`
27. `.claude/docs/LOCAL_STORAGE_STRUCTURE.md`
28. `.claude/docs/IMPLEMENTATION_PLAN.md`
29. `.claude/docs/PHASE_CHECKLISTS.md`

## Prompts by phase

30. `.claude/prompts/00_MASTER_PROMPT_CLAUDE_CODE.md`
31. `.claude/prompts/01_PHASE_1_FOUNDATION.md`
32. `.claude/prompts/02_PHASE_2_TRANSCRIPTION.md`
33. `.claude/prompts/03_PHASE_3_NOTES_LOCAL.md`
34. `.claude/prompts/04_PHASE_4_NOTION_MCP.md`
35. `.claude/prompts/05_PHASE_5_OCR.md`
36. `.claude/prompts/06_PHASE_6_MERGE_AUDIO_VIDEO.md`
37. `.claude/prompts/07_PHASE_7_CLAUDE_CODE_CODEX_OUTPUTS.md`
38. `.claude/prompts/08_PHASE_8_BATCH_RESUME_QA.md`
39. `.claude/prompts/09_REFACTORING_PROMPT.md`
40. `.claude/prompts/10_QA_PROMPT.md`

## Agents

41. `.claude/agents/aulaforge-product-architect.md`
42. `.claude/agents/python-cli-engineer.md`
43. `.claude/agents/transcription-whisper-engineer.md`
44. `.claude/agents/ollama-prompt-engineer.md`
45. `.claude/agents/ocr-video-engineer.md`
46. `.claude/agents/notion-mcp-integrator.md`
47. `.claude/agents/audio-video-merge-engineer.md`
48. `.claude/agents/qa-automation-engineer.md`
49. `.claude/agents/docs-knowledge-engineer.md`

## Commands

50. `.claude/commands/aulaforge-plan.md`
51. `.claude/commands/aulaforge-phase-1.md`
52. `.claude/commands/aulaforge-qa.md`

## Templates and checklists

53. `.claude/templates/LESSON_NOTE_TEMPLATE.md`
54. `.claude/templates/CLAUDE_CODE_CONTEXT_TEMPLATE.md`
55. `.claude/templates/CODEX_CONTEXT_TEMPLATE.md`
56. `.claude/checklists/DEVELOPMENT_BEST_PRACTICES.md`

## Hooks

57. `.claude/hooks/block-secrets.sh`
58. `.claude/hooks/block-secretes.sh`

## Required response after reading

After reading, Claude Code must output a table with:

- file path;
- status;
- one-line summary;
- relevance to current phase.

If any file is missing, stop and ask whether to proceed or recreate it.

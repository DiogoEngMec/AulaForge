# MCP setup — Notion

The first phases do not require Notion MCP.

Before Phase 4:

1. Confirm Notion MCP is available in Claude Code.
2. Confirm access to the workspace/database.
3. Create or identify the database `Aulas Processadas`.
4. Never store tokens in committed files.
5. Store local secrets in `.claude/settings.local.json` or environment variables.

Notion behavior:

- Search for an existing course page by course name.
- If found, update it.
- If not found, create it.
- Use one course page containing all lessons.
- Use Toggle Heading 1 or equivalent for each lesson.

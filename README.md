# AulaForge — Pacote inicial de planejamento para Claude Code

Este pacote contém os arquivos iniciais para começar o desenvolvimento do **AulaForge** de forma organizada e por fases.

O AulaForge é uma ferramenta local, executada por comando, para processar vídeos de aulas/cursos e gerar automaticamente:

- áudio extraído;
- transcrição local com Whisper;
- transcrição limpa;
- OCR do que apareceu na tela;
- códigos detectados;
- comandos de terminal detectados;
- merge entre fala e tela;
- anotação estruturada para Notion;
- página única do curso no Notion com aulas em blocos recolhíveis;
- arquivos `.md` para Claude Code e Codex;
- prompts prontos;
- ideias de projetos, agentes e skills.

## Como usar este pacote no Claude Code

1. Crie um repositório novo para o AulaForge.
2. Copie estes arquivos para a raiz do projeto.
3. Abra o projeto no Claude Code.
4. Leia primeiro:
   - `PRD.md`
   - `CLAUDE.md`
   - `ARCHITECTURE.md`
   - `ROADMAP.md`
5. Use os prompts em `prompts/` fase por fase.
6. Não peça para a IA construir tudo de uma vez.

## Ordem recomendada de uso

1. `prompts/00_MASTER_PROMPT_CLAUDE_CODE.md`
2. `prompts/01_PHASE_1_FOUNDATION.md`
3. `prompts/02_PHASE_2_TRANSCRIPTION.md`
4. `prompts/03_PHASE_3_NOTES_LOCAL.md`
5. `prompts/04_PHASE_4_NOTION_MCP.md`
6. `prompts/05_PHASE_5_OCR.md`
7. `prompts/06_PHASE_6_MERGE_AUDIO_VIDEO.md`
8. `prompts/07_PHASE_7_CLAUDE_CODE_CODEX_OUTPUTS.md`
9. `prompts/08_PHASE_8_BATCH_RESUME_QA.md`

## Regra principal

O projeto deve evoluir por fases pequenas, testáveis e corrigíveis.

Nunca implementar transcrição, OCR, Notion, merge visual e geração de agentes tudo em uma única etapa.

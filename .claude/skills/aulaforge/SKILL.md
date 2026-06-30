# Skill proposta — AulaForge Builder

## Objetivo

Ajudar a construir, revisar e evoluir o projeto AulaForge.

## Quando usar

Use esta skill quando a tarefa envolver:

- processamento local de vídeos de aula;
- transcrição com Whisper;
- OCR de tela;
- merge entre áudio e vídeo;
- geração de anotações para Notion;
- criação de arquivos para Claude Code/Codex;
- arquitetura de pipeline local;
- automação batch sem intervenção manual.

## Contexto fixo

O AulaForge:

- é local-first;
- roda por CLI;
- usa Python;
- usa Whisper local;
- usa Ollama `qwen3:30b`;
- publica no Notion via MCP;
- salva tudo localmente;
- processa cursos sequencialmente;
- gera Markdown estruturado.

## Fluxo recomendado

1. Entender a fase atual.
2. Ler `PRD.md`, `CLAUDE.md`, `ROADMAP.md` e `ARCHITECTURE.md`.
3. Implementar apenas a fase solicitada.
4. Criar validações.
5. Atualizar documentação.
6. Sugerir próxima fase.

## Restrições

- Não usar APIs pagas.
- Não transformar em web app no MVP.
- Não enviar transcrição bruta ao Notion.
- Não enviar screenshots ao Notion.
- Não processar em paralelo inicialmente.
- Não criar arquivos em `.claude/agents/` sem pedido explícito.

## Saída esperada da skill

Sempre produzir:

- plano curto;
- arquivos envolvidos;
- implementação incremental;
- testes/validação;
- riscos;
- próximos passos.

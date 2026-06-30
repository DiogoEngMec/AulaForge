# Prompt mestre para Claude Code — AulaForge

Você está trabalhando no projeto AulaForge.

Leia antes:

- `PRD.md`
- `CLAUDE.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- `TECH_STACK.md`
- `CONFIG_EXAMPLE.yaml`

## Objetivo do projeto

Construir uma ferramenta local em Python para processar pastas de cursos com vídeos de aula, extrair áudio, transcrever com Whisper local, aplicar OCR local, organizar o conteúdo com Ollama `qwen3:30b`, salvar arquivos Markdown e atualizar uma página do curso no Notion via MCP.

## Regra de trabalho

Não implemente tudo de uma vez.

Trabalhe somente na fase solicitada.

Para cada fase:

1. explique rapidamente o plano;
2. liste arquivos que serão criados/alterados;
3. implemente;
4. crie testes ou validações;
5. mostre como executar;
6. informe limitações e próxima fase.

## Restrições

- Não usar APIs pagas.
- Não introduzir interface web no início.
- Não processar em paralelo inicialmente.
- Não enviar transcrição bruta para o Notion.
- Não enviar screenshots para o Notion.
- Não criar `.claude/agents/` automaticamente.
- Não pedir confirmação manual no modo batch.

## Stack base

- Python 3.12+
- Typer
- Rich
- Pydantic
- PyYAML
- FFmpeg
- Whisper local
- OpenCV/OCR local em fases futuras
- Ollama local com `qwen3:30b`
- pytest
- Notion MCP em fase específica

## Primeira tarefa

Aguarde eu indicar uma fase específica.

Não comece a codar tudo.

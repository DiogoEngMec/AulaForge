# AulaForge

AulaForge é uma ferramenta local-first para transformar aulas gravadas em vídeo em uma base de conhecimento estruturada.

O sistema deve processar uma pasta de curso contendo várias aulas, extrair áudio, transcrever com Whisper local, analisar visualmente o vídeo com OCR local, organizar o conteúdo com Ollama (`qwen3:30b`), gerar arquivos Markdown para Claude Code/Codex e criar/atualizar uma página do curso no Notion via MCP.

## Decisões principais

- Execução inicial por CLI.
- Processamento local, sem APIs pagas.
- Transcrição com Whisper local.
- Organização com Ollama + `qwen3:30b`.
- OCR local para detectar código, terminal, slides, navegador, VS Code e documentação.
- Processamento sequencial para estabilidade.
- Batch automático sem perguntas manuais.
- Página única por curso no Notion, com aulas em Toggle Heading 1.
- Transcrição bruta salva localmente, não enviada ao Notion.
- Screenshots salvos localmente, não enviados ao Notion.

## Como iniciar no Claude Code

Leia primeiro:

```text
FIRST_PROMPT_CLAUDE_CODE.md
```

Depois cole o prompt no Claude Code.

O Claude deve primeiro ler `.claude/docs/FILE_READING_ORDER.md` e seguir a ordem completa de leitura antes de implementar qualquer código.

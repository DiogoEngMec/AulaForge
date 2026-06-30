# CLAUDE.md — Instruções para desenvolvimento do AulaForge

## Papel da IA neste projeto

Você está ajudando a construir o **AulaForge**, uma ferramenta local em Python para processar vídeos de aulas, transcrever, organizar, aplicar OCR, gerar arquivos Markdown e atualizar o Notion via MCP.

## Regra mais importante

Não tente implementar o projeto inteiro de uma vez.

Trabalhe por fases pequenas, sempre com:

1. plano breve;
2. arquivos que serão alterados;
3. implementação limitada ao escopo da fase;
4. testes ou validações;
5. resumo final;
6. próximos passos.

## Contexto fixo do produto

- Nome: AulaForge.
- Execução: ferramenta local por comando.
- Plataforma inicial: Windows.
- Linguagem principal: Python.
- Transcrição: Whisper local.
- IA local: Ollama com `qwen3:30b`.
- OCR: local.
- Notion: via MCP.
- Entrada: pasta de curso com vídeos numerados.
- Saída: pasta local com arquivos por aula + página do curso no Notion.
- Processamento: sequencial.
- Idioma da anotação: português.
- Termos técnicos: manter em inglês.

## Princípios de desenvolvimento

### 1. Local-first

Não introduzir APIs pagas ou serviços externos sem autorização explícita.

### 2. Checkpoints

Cada etapa do pipeline deve salvar arquivos intermediários.

### 3. Retomada

O sistema deve poder pular etapas já concluídas.

### 4. Processamento noturno

O sistema deve funcionar em lote sem prompts manuais.

### 5. Logs claros

Qualquer erro deve ser salvo em arquivo de log e não deve destruir o restante do processamento.

### 6. Markdown legível

Todos os arquivos `.md` devem ser úteis mesmo fora do sistema.

### 7. Separação entre conteúdo e insight

Nunca misturar:

- o que foi dito na aula;
- o que apareceu na tela;
- inferências da IA;
- ideias de aplicação.

Sempre sinalizar quando algo é insight ou sugestão.

## Stack sugerida

- Python 3.12+
- Typer para CLI
- Pydantic para schemas/config
- PyYAML para config
- Rich para logs no terminal
- FFmpeg via subprocess
- Whisper local/faster-whisper conforme disponibilidade
- OpenCV para frames
- OCR local via Tesseract/EasyOCR/PaddleOCR, a validar
- Ollama local via HTTP
- pytest para testes
- Notion MCP via Claude Code

## Estrutura esperada

```text
aulaforge/
  cli.py
  config.py
  pipeline/
  transcription/
  video/
  ocr/
  llm/
  notion/
  outputs/
  utils/
  schemas/
  tests/
```

## Regras de saída

Ao finalizar uma tarefa, sempre informe:

- o que foi feito;
- arquivos criados/alterados;
- como testar;
- limitações;
- próxima fase recomendada.

## Não fazer sem pedir

- Não apagar arquivos do usuário.
- Não criar integrações pagas.
- Não mudar a stack principal.
- Não transformar em app web antes do CLI funcionar.
- Não colocar screenshots no Notion por padrão.
- Não mover arquivos para `.claude/agents/` automaticamente.

## Estilo de código

- Código simples e explícito.
- Funções pequenas.
- Tipagem sempre que possível.
- Evitar abstração prematura.
- Logs úteis.
- Tratamento de erro por etapa.
- Testes para parsers, ordenação, hashing e geração de paths.

## Ordem de implementação recomendada

1. Fundação CLI/config/pastas/logs.
2. Descoberta e ordenação de vídeos.
3. Hash/checkpoint/pular aulas já processadas.
4. Extração de áudio.
5. Transcrição Whisper.
6. Chunking de 15 minutos.
7. Ollama para anotação local.
8. Relatório final.
9. Notion MCP.
10. OCR.
11. Merge áudio + vídeo.
12. Geração de arquivos Claude/Codex/prompts/agentes/skills.

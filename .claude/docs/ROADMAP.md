# Roadmap — AulaForge

## Fase 0 — Planejamento

Objetivo: fechar escopo, arquitetura e contratos de dados.

Entregáveis:

- `PRD.md`
- `CLAUDE.md`
- `ARCHITECTURE.md`
- `TECH_STACK.md`
- `CONFIG_EXAMPLE.yaml`
- prompts por fase

Status: planejado.

---

## Fase 1 — Fundação CLI

Objetivo: criar base do projeto Python.

Escopo:

- estrutura do projeto;
- CLI com Typer;
- carregamento de config YAML;
- logs com Rich;
- criação da pasta de saída;
- descoberta de vídeos;
- ordenação por número da aula;
- relatório inicial.

Critério de aceite:

```powershell
python -m aulaforge process-course "C:\Aulas\Curso Teste"
```

Deve listar vídeos encontrados em ordem correta e criar estrutura de saída.

---

## Fase 2 — Checkpoints e hashing

Objetivo: evitar reprocessar aulas iguais.

Escopo:

- calcular hash do vídeo;
- salvar `source_info.json`;
- detectar se aula já foi processada;
- implementar `--force`.

Critério de aceite:

Rodar duas vezes deve pular a aula na segunda execução.

---

## Fase 3 — Extração de áudio

Objetivo: extrair áudio do vídeo com FFmpeg.

Escopo:

- verificar se FFmpeg está instalado;
- extrair áudio para `audio/audio.mp3` ou `audio/audio.wav`;
- registrar duração;
- salvar logs.

Critério de aceite:

Cada aula processada deve ter arquivo de áudio válido.

---

## Fase 4 — Transcrição local

Objetivo: transcrever áudio com Whisper local.

Escopo:

- integrar Whisper local;
- gerar transcrição bruta;
- gerar timestamps;
- salvar `.txt` e `.json`;
- segmentar em blocos de 15 minutos.

Critério de aceite:

Aula gera:

- `01_TRANSCRICAO_BRUTA.txt`
- `02_TRANSCRICAO_COM_TIMESTAMPS.json`
- `03_CHUNKS_15_MIN.json`

---

## Fase 5 — Anotação local via Ollama

Objetivo: usar `qwen3:30b` para gerar anotação estruturada.

Escopo:

- criar cliente Ollama;
- gerar resumo por bloco;
- gerar anotação final;
- salvar `09_ANOTACAO_NOTION.md`;
- preservar termos técnicos em inglês.

Critério de aceite:

Aula gera Markdown claro e estruturado, sem enviar ao Notion ainda.

---

## Fase 6 — Notion MCP

Objetivo: criar ou atualizar página do curso no Notion.

Escopo:

- localizar página do curso;
- criar se não existir;
- adicionar/atualizar aula como toggle;
- gerar visão geral do curso;
- não enviar transcrição bruta.

Critério de aceite:

Uma página única do curso deve conter aulas em blocos recolhíveis.

---

## Fase 7 — OCR local

Objetivo: extrair conteúdo visual do vídeo.

Escopo:

- extrair frames;
- evitar frames duplicados;
- aplicar OCR;
- detectar tela de código/terminal quando possível;
- salvar screenshots localmente;
- salvar `04_OCR_TELA.json` e `05_OCR_TELA.md`.

Critério de aceite:

Códigos/comandos visíveis devem aparecer em arquivos locais com timestamps.

---

## Fase 8 — Merge áudio + vídeo

Objetivo: unir transcrição e OCR por timestamp.

Escopo:

- agrupar OCR por bloco de 15 minutos;
- associar trechos visuais à fala próxima;
- gerar `08_MERGE_AUDIO_VIDEO.md`;
- inserir códigos detectados na anotação final com aviso de confiança.

Critério de aceite:

A anotação final deve incluir trechos de código vistos na tela quando existirem.

---

## Fase 9 — Arquivos Claude Code, Codex e prompts

Objetivo: gerar materiais derivados.

Escopo:

- `10_CLAUDE_CODE_CONTEXT.md`
- `11_CODEX_CONTEXT.md`
- `12_PROMPTS_PRONTOS.md`
- `13_AGENTES_SUGERIDOS.md`
- `14_SKILLS_SUGERIDAS.md`
- `15_IDEIAS_DE_PROJETOS.md`
- `16_IMPLEMENTATION_PLAN.md`

Critério de aceite:

Cada aula deve gerar arquivos úteis para iniciar implementação futura.

---

## Fase 10 — Robustez para processamento noturno

Objetivo: deixar o sistema seguro para rodar em lote.

Escopo:

- retries;
- logs;
- batch report;
- continuar em caso de erro;
- resumo final;
- status por aula.

Critério de aceite:

Um curso com vários vídeos deve processar sem interação manual e gerar relatório final.

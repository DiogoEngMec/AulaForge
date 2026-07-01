# AulaForge — Handoff até a Fase 3

> Gerado em 2026-06-30. Use este arquivo para retomar o projeto após limpar o contexto.

## Estado atual da master

- Fases 1 e 2 **commitadas e merged em `master`**.
- Fase 3 **implementada e QA-aprovada**, mas **ainda não commitada** — está como mudanças não commitadas na branch `aulaforge/local-notes`.
- `.claude/` não foi alterado em nenhuma fase de implementação.

## Fases já implementadas

1. **Fase 1 — Foundation** (master). CLI skeleton, config Pydantic, descoberta/ordenação de vídeos, fingerprint SHA256, padrão de checkpoint `processing_log.json`, resumo de batch (`batch_report.md`, `batch_log.json`).
2. **Fase 2 — Transcrição** (master). Extração de áudio via FFmpeg, Whisper local, chunking de 15 min. Outputs: `01_TRANSCRICAO_BRUTA.txt`, `02_TRANSCRICAO_COM_TIMESTAMPS.json`, `03_TRANSCRICAO_LIMPA.md`.
3. **Fase 3 — Notas locais com Ollama** (branch `aulaforge/local-notes`, QA aprovado, **não commitado**). Cliente HTTP Ollama (100% local), geração de notas em chunks (sem truncamento silencioso), `notes_input_hash` (transcrição + model + temperature + max_input_chars + versão do prompt), prefixo `/no_think` + remoção de tags `<think>`, retry configurável. Output: `09_ANOTACAO_NOTION.md`.

## Branch atual recomendada para próxima fase

1. Commitar o trabalho da Fase 3 em `aulaforge/local-notes`.
2. Merge `aulaforge/local-notes` → `master`.
3. Criar nova branch para a Fase 4, ex.: `aulaforge/notion-mcp` (já existe localmente, criada antecipadamente).

## Arquivos principais criados até agora

**Fase 1**: `src/aulaforge/models.py`, `config.py`, `discovery.py`, `checkpoints.py`, `logging_setup.py`, `cli.py`, `__main__.py`

**Fase 2** (extensões): `models.py` (TranscriptSegment, source_hash), `config.py` (TranscriptionConfig), `audio.py`, `chunking.py`, `transcription.py`, extensões em `checkpoints.py`/`cli.py`

**Fase 3** (novos): `ollama_client.py`, `notes.py`; extensões em `config.py` (`LlmConfig`), `checkpoints.py` (funções do step `notes`), `cli.py` (step de notas no loop de batch)

**Testes**: `test_config.py`, `test_discovery.py`, `test_checkpoints.py`, `test_logging_setup.py`, `test_cli.py`, `test_audio.py`, `test_chunking.py`, `test_transcription.py`, `test_notes.py`, `test_ollama_client.py`

## Decisões importantes

- **Checkpoint/skip**: `processing_log.json` por aula, append-only. `needs_X_processing()` verifica force → step já feito → `source_hash` bate → arquivo de saída existe.
- **Lazy dependency check**: ffmpeg/whisper/Ollama checados no máximo 1x por batch, só quando alguma aula realmente precisa. Sentinel `None` (não checado) vs `[]` (checado, OK).
- **`notes_input_hash`**: SHA256 de `PROMPT_VERSION:model:temperature:max_input_chars:transcript_text`.
- **Notas em chunks**: split em `## Bloco`, N chamadas parciais + 1 consolidação. Nunca trunca silenciosamente.
- **Atomic writes**: grava em `.tmp`, depois `os.replace()`; cleanup em `finally`.
- **Exit codes**: 0 = OK, 1 = falha de processamento, 2 = dependência local ausente (ffmpeg/whisper/Ollama).
- **qwen3 thinking mode**: prefixo `/no_think` em toda mensagem + regex para remover blocos `<think>...</think>`.
- **`NOTES_PROMPT_VERSION = "v1"`**: bump manual invalida cache de notas quando o prompt muda.

## Status dos testes

QA executado na branch `aulaforge/local-notes` (uncommitted):
- `pytest`: 126 passed, 1 skipped (modelo Whisper real)
- `ruff check .`: limpo
- `mypy src` (strict): limpo, 13 arquivos fonte
- Zero problemas críticos ou médios. Um ponto baixo (risco teórico de colisão no separador `:` do hash) considerado irrelevante na prática.

## Próximos passos

1. Commitar a Fase 3.
2. Merge para `master`.
3. (Opcional) Smoke test manual com Ollama real + `qwen3:30b`.
4. Iniciar Fase 4 — Notion MCP.

## Prompt recomendado para iniciar a Fase 4

```
Plano da Fase 4 — Notion MCP.

Leia .claude/docs/FILE_READING_ORDER.md, .claude/rules/notion.md e os prompts/docs
relevantes antes de planejar. Não implemente nada ainda.

Regras já conhecidas (.claude/rules/notion.md):
- Notion é Fase 4, não antes.
- Usar Notion MCP quando disponível.
- Buscar página do curso pelo nome antes de criar uma nova.
- Uma página por curso.
- Aulas como Toggle Heading 1 (ou equivalente).
- Nunca enviar transcrição bruta nem screenshots ao Notion.
- Incluir código/comandos de OCR com timestamp e aviso de confiança quando necessário.

Estado atual: Fases 1-3 prontas (Fase 3 gera 09_ANOTACAO_NOTION.md por aula,
100% local via Ollama). A Fase 4 deve ler esse arquivo e publicar no Notion.

Aguardo o plano detalhado antes de qualquer implementação.
```

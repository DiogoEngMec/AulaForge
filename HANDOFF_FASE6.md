# HANDOFF — Fase 6: Merge áudio/vídeo

## Estado atual da master

`master` está em `6daf37b Implementa merge audio video`.
As Fases 1–6 estão completas e integradas. Working tree limpo.

---

## Fases implementadas

| Fase | Descrição | Status |
|---|---|---|
| 1 | Foundation: CLI, config, discovery, checkpoints | master ✅ |
| 2 | Transcrição: FFmpeg + Whisper local | master ✅ |
| 3 | Notas locais: Ollama / qwen3:30b | master ✅ |
| 4 | Sincronização com Notion via REST | master ✅ |
| 5 | OCR: extração de frames + detecção código/terminal | master ✅ |
| 6 | Merge áudio/vídeo: alinhamento de timelines | master ✅ (mergeada de `aulaforge/merge`) |
| 7 | Outputs Claude Code / Codex | não iniciada |
| 8 | Batch robusto / QA / refactor | não iniciada |

---

## Branch da Fase 6

Desenvolvida em `aulaforge/merge`, mergeada em `master`.
Commit de entrega: `6daf37b`

---

## Arquivos criados / alterados na Fase 6

### Novos

| Arquivo | Descrição |
|---|---|
| `src/aulaforge/merge.py` | Pipeline de merge: parsing, alinhamento temporal, geração de Markdown, escrita atômica |
| `tests/test_merge.py` | 69 testes (sem Whisper, Tesseract, FFmpeg, Ollama, Notion) |

### Modificados

| Arquivo | O que mudou |
|---|---|
| `src/aulaforge/config.py` | `MergeConfig` com `enabled`, `window_seconds`, `group_minutes: PositiveInt`; import `PositiveInt` |
| `src/aulaforge/checkpoints.py` | `MERGE_STEP`, `needs_merge_processing`, `process_lesson_merge`, `record_skipped_merge`, `record_merge_skipped_no_inputs`, `record_merge_skipped_disabled` |
| `src/aulaforge/cli.py` | Bloco `--- Phase 6: Merge ---` após bloco OCR |
| `CONFIG_EXAMPLE.yaml` | Seção `merge:` com `enabled`, `window_seconds`, `group_minutes` |

### Artefatos locais gerados por run

```
output/<Curso>/<aula>/08_MERGE_AUDIO_VIDEO.md    # linha do tempo unificada
output/<Curso>/<aula>/processing_log.json         # step "merge" com source_hash
output/<Curso>/batch_report.md                    # coluna "Merge" automática
```

---

## Decisões importantes

| Decisão | Escolha |
|---|---|
| `merge.enabled` padrão | `True` — sem dependências externas, corre sempre por padrão |
| Inputs lidos | `02_TRANSCRICAO_COM_TIMESTAMPS.json` e `04_OCR_TELA.json` |
| Merge parcial | Aceito: um só input presente gera output parcial; cabeçalho indica o que está disponível |
| Ambos ausentes | Skip limpo (`record_merge_skipped_no_inputs`), não é falha de processamento |
| JSON inválido | ValidationError/JSONDecodeError propagada → step FAILED → batch continua com `continue_on_error` |
| Alinhamento OCR→transcrição | Distância mínima à borda do intervalo; frame dentro do intervalo tem dist=0 |
| `window_seconds` | Janela de associação OCR→segmento (padrão: 15 s) |
| `group_minutes` | Agrupamento de blocos no Markdown (padrão: 10 min); validado `> 0` via `PositiveInt` |
| Hash de checkpoint | `SHA256("merge:v1:<window_seconds>:<group_minutes>:<transcript_raw>:<ocr_raw>")` com sentinela `"no_transcript"`/`"no_ocr"` para None |
| Skip inteligente | Segunda execução sem mudanças pula sem reescrever o `.md` |
| Escrita atômica | `.tmp` + `os.replace()` — Windows-safe |
| `batch_report.md` | Coluna `Merge` aparece automaticamente (descoberta dinâmica de colunas) |
| Nenhuma dep externa | Merge não chama Whisper, Tesseract, FFmpeg, Ollama nem Notion |

---

## Formato de `08_MERGE_AUDIO_VIDEO.md`

```markdown
# Merge Audio/Vídeo — {título da aula}

> Gerado automaticamente por AulaForge.
> Fontes: **transcrição** (Whisper local) e **OCR de tela** (Tesseract local).
> Transcrição disponível: **Sim** | OCR disponível: **Sim**

## Linha do Tempo

### 00:00:00 – 00:10:00

**[Falado]** `00:00:05 – 00:00:15`
> texto transcrito pelo Whisper

**[Visual — vscode]** `00:00:08` _(confiança: low)_
```python
def main():
    pass
```

**[Visual — terminal]** `00:00:50`
```bash
pip install aulaforge
```

**[Visual — slides]** `00:01:30`
_texto extraído do slide_

### 00:10:00 – 00:20:00

**[Falado]** `00:10:02 – 00:10:45`
> próximo segmento falado
```

**Regras de renderização:**
- `[Falado]` → texto em blockquote
- `[Visual — tipo]` → `detected_commands` em ` ```bash `, `detected_code` em ` ```lang ` (python/bash/text), `text` em itálico como fallback
- Confiança `low`/`medium` anotada inline; `high` omitida
- Múltiplos frames OCR no mesmo segmento → agrupados no mesmo bloco, texto falado aparece uma vez
- Frame OCR sem segmento próximo → bloco visual standalone
- `window_seconds=0` entre frame e segmento = frame dentro do intervalo → associado diretamente

---

## Status dos testes

```
pytest:  359 passed, 1 skipped  (1 skipped = Whisper real, esperado)
ruff:    All checks passed
mypy:    Success: no issues found in 18 source files
```

Todos os testes passam sem FFmpeg, Tesseract, Whisper, Ollama ou Notion reais.

---

## Pendências conhecidas

| ID | Prioridade | Descrição |
|---|---|---|
| M6-1 | Info | `_parse_hms` aceita apenas `HH:MM:SS` inteiro. Timestamps com sub-segundo (`HH:MM:SS.mmm`) levantam `ValueError`, são descartados com warning. Suficiente para OCR gerado pelo AulaForge, que sempre usa segundos inteiros. |
| M6-2 | Info | `_screen_type_lang` mapeia apenas `vscode→python` e `terminal→bash`; qualquer outro tipo retorna `"text"`. Extensível quando novas classificações forem adicionadas ao OCR. |
| O2 | Info | `send_screenshots_to_notion` e `show_low_confidence_code_in_notion` em `OcrConfig` são campos dormentes para integração futura Notion+OCR. |
| O4 | Baixa | Mock de `pytesseract` em `test_run_ocr` usa `builtins.__import__` — candidato a migrar para `sys.modules` numa fase de QA. |

---

## Próxima fase recomendada

**Fase 7 — Outputs Claude Code / Codex**: geração dos artefatos de conhecimento finais por curso/aula.

Outputs previstos em `LOCAL_STORAGE_STRUCTURE.md`:

```
output/<Curso>/COURSE_OVERVIEW.md
output/<Curso>/COURSE_PROJECT_IDEAS.md
output/<Curso>/COURSE_AGENTS.md
output/<Curso>/COURSE_SKILLS.md
output/<Curso>/COURSE_PROMPTS.md

output/<Curso>/<aula>/10_CLAUDE_CODE_CONTEXT.md
output/<Curso>/<aula>/11_CODEX_CONTEXT.md
output/<Curso>/<aula>/12_PROMPTS_PRONTOS.md
output/<Curso>/<aula>/13_AGENTES_SUGERIDOS.md
output/<Curso>/<aula>/14_SKILLS_SUGERIDAS.md
output/<Curso>/<aula>/15_IDEIAS_DE_PROJETOS.md
output/<Curso>/<aula>/16_IMPLEMENTATION_PLAN.md
```

Input principal: `08_MERGE_AUDIO_VIDEO.md` + `09_ANOTACAO_NOTION.md` (se disponível).
Agente sugerido: `docs-knowledge-engineer`
Prompt de fase: `.claude/prompts/07_PHASE_7_CLAUDE_CODE_CODEX_OUTPUTS.md`

---

## Prompt para iniciar a Fase 7

```
Estou no projeto AulaForge. As Fases 1–6 estão implementadas e commitadas em master.

Leia primeiro:
1. .claude/docs/FILE_READING_ORDER.md
2. Os arquivos na ordem indicada nele.
3. HANDOFF_FASE6.md (raiz do projeto) para o contexto completo da Fase 6.

Depois apresente o plano da Fase 7 — outputs Claude Code / Codex
(escopo, arquivos a criar/alterar, decisões a confirmar)
e aguarde aprovação antes de implementar.

Restrições permanentes:
- Local-first: Whisper local, Ollama/qwen3:30b local, OCR local.
- Não adicione APIs pagas.
- Não altere arquivos .claude.
- Não implemente fases futuras além da 7.
- NOTION_TOKEN sempre via variável de ambiente.
- ocr.enabled permanece False por padrão (OCR é opt-in).
- merge.enabled permanece True por padrão (sem dependências externas).
```
